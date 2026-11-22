import json
import tempfile
from dataclasses import replace
from pathlib import Path

from evidence.acceptance import accept_panel, accept_station
from evidence.freeze import freeze_panel, freeze_station
from panel_fixtures import CATALOG, stage_sources
from records.identity import StationKey
from records.intake import accept_revision
from records.readings import ActionRow, RevisionDraft, WitnessRow
from records.storage import RevisionStore
from reports.publish import issue_panel, issue_report
from reports.retrieve import read_panel, read_report
from reports.storage import ReportStore
from review.commands import CommandCatalog
from review.script_check import review_script


def _load_sample(name):
    path = Path(__file__).resolve().parent / 'samples' / name
    value = json.loads(path.read_text(encoding='utf-8'))
    key = StationKey(value['job'], value['station'])
    catalog = CommandCatalog(value['job'], tuple(value['commands']))
    draft = RevisionDraft(
        value['opening'],
        tuple(ActionRow(**row) for row in value['actions']),
        tuple(WitnessRow(**row) for row in value['witnesses']),
    )
    return key, catalog, draft, value.get('correction')


def _day_shift(path, station, catalog, draft):
    with RevisionStore(path) as source:
        source.initialize((catalog,))
        revision = accept_revision(source, station, draft)
        review = review_script(source, revision, ('p',))
        if not review.executable or not review.witnesses:
            raise RuntimeError(f'{station.station}: daytime review did not find the recorded witness')
        raw = freeze_station(source, revision)
    return revision, raw


def _correct(path, station, parent, draft, correction):
    target_row = correction['action_id']
    if sum(row.row_id == target_row for row in draft.actions) != 1:
        raise ValueError('the sample correction must select one action row')
    revised = replace(draft, actions=tuple(
        replace(row, target=correction['target']) if row.row_id == target_row else row
        for row in draft.actions
    ))
    with RevisionStore(path) as source:
        source.initialize()
        new = accept_revision(source, station, revised, parent=parent)
        review = review_script(source, new, ('p', 'p'))
        if not review.executable or not review.witnesses:
            raise RuntimeError('the corrected script has no witnessed path')
        return new, freeze_station(source, new)


def legacy_v1_demo():
    """Original V1 station replay, kept runnable alongside the panel scheme."""
    alpha, alpha_catalog, alpha_draft, correction = _load_sample('alpha.json')
    beta, beta_catalog, beta_draft, _ = _load_sample('beta.json')
    with tempfile.TemporaryDirectory(prefix='station-replay-') as folder:
        root = Path(folder)
        alpha_path = root / 'alpha.sqlite3'
        report_path = root / 'reports.sqlite3'
        old_key, old_raw = _day_shift(alpha_path, alpha, alpha_catalog, alpha_draft)
        _, beta_raw = _day_shift(root / 'beta.sqlite3', beta, beta_catalog, beta_draft)
        first_parent = accept_station(old_raw, alpha.job, alpha.station)
        second_station = accept_station(beta_raw, beta.job, beta.station)
        with ReportStore(report_path) as reports:
            reports.initialize()
            old = issue_report(reports, first_parent, second_station, {'p'})
        new_key, new_raw = _correct(alpha_path, alpha, old_key, alpha_draft, correction)
        new_parent = accept_station(new_raw, alpha.job, alpha.station)
        with ReportStore(report_path) as reports:
            reports.initialize()
            new = issue_report(reports, new_parent, second_station, {'p'})
        with ReportStore(report_path) as reopened:
            reopened.initialize()
            old_snapshot = read_report(reopened, old.number)
            new_snapshot = read_report(reopened, new.number)
    return old, new, old_snapshot, new_snapshot


def _lamp_paths(strategy):
    """List observable lamp histories and the command that closes each one."""
    found = {}

    def walk(node, history):
        for lamp, child in node['next'].items():
            branch = history + (int(lamp),)
            if 'stop' in child:
                found[branch] = node['command']
            else:
                walk(child, branch)

    walk(strategy, ())
    return found


def main():
    with tempfile.TemporaryDirectory(prefix='panel-retest-') as folder:
        root = Path(folder)
        # stage_sources opens both station stores and closes them before returning.
        raws = stage_sources(
            root / 'alpha.sqlite3', root / 'beta.sqlite3', freeze_panel
        )
        left = accept_panel(raws['alpha'], CATALOG.job, 'alpha')
        original = accept_panel(raws['beta'], CATALOG.job, 'beta')
        corrected = accept_panel(raws['beta_reversed'], CATALOG.job, 'beta')
        report_path = root / 'reports.sqlite3'
        with ReportStore(report_path) as reports:
            reports.initialize()
            first = issue_panel(reports, left, original, CATALOG.commands, 3)
            second = issue_panel(reports, left, corrected, CATALOG.commands, 3)
        with ReportStore(report_path) as reopened:
            reopened.initialize()
            first_again = read_panel(reopened, first.number)
            second_again = read_panel(reopened, second.number)
            first_parents = (
                accept_panel(first_again.parents[0], CATALOG.job, 'alpha').identity.revision,
                accept_panel(first_again.parents[1], CATALOG.job, 'beta').identity.revision,
            )
            second_parents = (
                accept_panel(second_again.parents[0], CATALOG.job, 'alpha').identity.revision,
                accept_panel(second_again.parents[1], CATALOG.job, 'beta').identity.revision,
            )

    original_paths = _lamp_paths(first.strategy)
    corrected_paths = _lamp_paths(second.strategy)
    shared = sorted({history[:2] for history in original_paths} & {history[:2] for history in corrected_paths})
    if not shared:
        raise SystemExit('the two revisions do not share a lamp history')
    shared = shared[0]
    expected = {
        'original': original_paths[shared + (0,)],
        'corrected': corrected_paths[shared + (0,)],
    }
    if expected != {'original': 's', 'corrected': 'r'}:
        raise SystemExit(f'PANEL_CORRECTION_MISMATCH actual={expected!r} expected={{original: s, corrected: r}}')
    if (first_again, second_again) != (first, second):
        raise RuntimeError('panel report changed after reopening')
    print('PANEL_SCENARIO ' + json.dumps({
        'case_id': 'panel.beta_lamp_correction',
        'shared_lamp_history': list(shared),
        'final_step': expected,
        'reports': [first.number, second.number],
        'statuses': [first.status, second.status],
        'original_parent_revisions': list(first_parents),
        'corrected_parent_revisions': list(second_parents),
        'oracle': (
            'Both revisions see the same p and q lamps; for lamp history '
            f'{list(shared)} the original beta can only finish with s while the '
            'corrected beta can only finish with r.'
        ),
    }, ensure_ascii=False, sort_keys=True))
    print(f'Shared lamp history {list(shared)}: original -> {expected["original"]}, '
          f'corrected -> {expected["corrected"]}')
    print(f'Report {first.number}: {first.status} (original beta parent revision {first_parents[1]})')
    print(f'Report {second.number}: {second.status} (corrected beta parent revision {second_parents[1]})')
    print('V1 legacy demo:')
    old, new, old_snapshot, new_snapshot = legacy_v1_demo()
    print(f'  Report {old_snapshot.number}: {list(old_snapshot.first_commands)}')
    print(f'  Report {new_snapshot.number}: {list(new_snapshot.first_commands)}')


if __name__ == '__main__':
    main()
