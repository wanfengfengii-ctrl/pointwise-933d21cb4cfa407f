from pathlib import Path

from evidence.acceptance import accept_station
from evidence.freeze import freeze_station
from records.identity import StationKey
from records.intake import accept_revision
from records.readings import ActionRow, RevisionDraft, WitnessRow
from records.storage import RevisionStore
from review.commands import CommandCatalog


CATALOG = CommandCatalog('materials-17', ('p', 'q', 'r'))
ALPHA = StationKey(CATALOG.job, 'alpha')
BETA = StationKey(CATALOG.job, 'beta')
OPENING = 'private-opening'
GATE = 'private-gate'
SPENT = 'private-spent'


def draft(edges, witnessed=(), *, opening=OPENING):
    actions = tuple(
        ActionRow(f'raw-action-{position}', *edge, f'raw-reading-{position}')
        for position, edge in enumerate(edges, 1)
    )
    witnesses = tuple(
        WitnessRow(f'raw-witness-{position}', actions[action].row_id, 'qualified on site')
        for position, action in enumerate(witnessed, 1)
    )
    return RevisionDraft(opening, actions, witnesses)


def steady():
    return draft(((OPENING, OPENING, 'public', 'p'),), (0,))


def bypass(returnable):
    return draft((
        (OPENING, OPENING, 'public', 'p'),
        (OPENING, GATE, 'local', 'private-inspection'),
        (GATE, OPENING if returnable else SPENT, 'public', 'p'),
        (SPENT, SPENT, 'public', 'p'),
    ), (1,))


def offline_parent(path: Path, station, catalog, route):
    with RevisionStore(path) as source:
        source.initialize((catalog,))
        key = accept_revision(source, station, route)
        raw = freeze_station(source, key)
    return accept_station(raw, station.job, station.station)


def offline_pair(root, left, right, *, right_station=BETA, right_catalog=CATALOG):
    a = offline_parent(root / 'alpha.sqlite3', ALPHA, CATALOG, left)
    b = offline_parent(root / 'beta.sqlite3', right_station, right_catalog, right)
    return a, b


def publication_counts(store):
    return (
        store.connection.execute('SELECT COUNT(*) FROM reports').fetchone()[0],
        store.connection.execute('SELECT COUNT(*) FROM report_parents').fetchone()[0],
        store.connection.execute('SELECT COUNT(*) FROM publications').fetchone()[0],
    )
