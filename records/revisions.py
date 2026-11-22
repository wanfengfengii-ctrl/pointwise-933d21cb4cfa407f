from dataclasses import dataclass

from records.identity import RevisionKey, RevisionRejected, StationKey
from records.readings import RevisionDraft
from records.storage import RevisionStore
from review.commands import CommandCatalog


@dataclass(frozen=True, slots=True)
class Revision:
    key: RevisionKey
    parent: RevisionKey | None
    draft: RevisionDraft
    catalog: CommandCatalog


def create_revision(
    store: RevisionStore, station: StationKey, draft: RevisionDraft, *, parent: RevisionKey | None
) -> RevisionKey:
    """Fix a draft checked by intake and bind its explicit predecessor."""
    if parent is not None and (not isinstance(parent, RevisionKey) or parent.station != station):
        raise RevisionRejected('parent must be a revision of the same job and station')
    return store.append(station, draft, parent)


def read_revision(store: RevisionStore, key: RevisionKey) -> Revision:
    stored = store.load(key)
    return Revision(stored.key, stored.parent, stored.draft, store.catalog(stored.key.station.job))
