from records.identity import RevisionKey, RevisionRejected, StationKey
from records.readings import RevisionDraft, validate_readings
from records.revisions import create_revision
from records.storage import RevisionStore
from review.commands import UnknownCommand


def accept_revision(
    store: RevisionStore, station: StationKey, draft: RevisionDraft, *, parent: RevisionKey | None = None
) -> RevisionKey:
    if not isinstance(station, StationKey):
        raise RevisionRejected('a station key is required')
    candidate = validate_readings(draft)
    catalog = store.catalog(station.job)
    for row in candidate.actions:
        if row.kind == 'public':
            try:
                catalog.require_known(row.label)
            except UnknownCommand as error:
                raise RevisionRejected(f'action {row.row_id}: {error}') from error
    return create_revision(store, station, candidate, parent=parent)
