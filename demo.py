import json
import tempfile
from dataclasses import replace
from pathlib import Path

from evidence.acceptance import accept_station
from evidence.freeze import freeze_station
from records.identity import StationKey
from records.intake import accept_revision
from records.readings import ActionRow, RevisionDraft, WitnessRow
from records.storage import RevisionStore
from reports.publish import issue_report
from reports.retrieve import read_report
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


def main():
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

        expected = [[], ['p']]
        actual = [list(old.first_commands), list(new.first_commands)]
        if actual != expected:
            raise SystemExit(f'REPEAT_QUALIFICATION_MISMATCH actual={actual!r} expected={expected!r}')
        if old_snapshot != old or new_snapshot != new:
            raise RuntimeError('historical receipt differs after reopening')
        actual_downstream = [
            accept_station(old_snapshot.parents[0], alpha.job, alpha.station).identity.revision,
            accept_station(new_snapshot.parents[0], alpha.job, alpha.station).identity.revision,
        ]
        expected_downstream = [old_key.number, new_key.number]
        if actual_downstream != expected_downstream:
            raise RuntimeError('historical receipt has the wrong source revision')
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'normal_pair.offline_variants',
            'input': {'job': alpha.job, 'permissions': ['p'], 'alpha_bypass_returns': [False, True]},
            'expected': expected,
            'actual': actual,
            'downstream_expected': expected_downstream,
            'downstream_actual': actual_downstream,
            'code_paths': [
                'evidence/freeze.py', 'qualification/result.py', 'reports/storage.py', 'reports/retrieve.py',
            ],
            'oracle': 'Hand trace: first bypass leaves the witness behind; the corrected bypass returns to the inspection opening. Beta witnesses every p. Each report keeps the selected alpha revision.',
        }, ensure_ascii=False, sort_keys=True))
        print(f'Report {old_snapshot.number}: {list(old_snapshot.first_commands)}')
        print(f'Report {new_snapshot.number}: {list(new_snapshot.first_commands)}')


if __name__ == '__main__':
    main()
