from evidence.codec import EvidenceStep, StationBody
from records.revisions import Revision
from review.witnesses import index_qualified_witnesses


def project_station_body(revision: Revision) -> StationBody:
    opening = revision.draft.opening
    anonymous = {opening: 0}
    witnesses = index_qualified_witnesses(revision)
    steps = []
    for row in revision.draft.actions:
        source = anonymous.setdefault(row.source, len(anonymous))
        target = anonymous.setdefault(row.target, len(anonymous))
        command = row.label if row.kind == 'public' else None
        steps.append(EvidenceStep(source, target, command, row.row_id in witnesses))
    return StationBody(anonymous[opening], len(anonymous), revision.catalog.commands, tuple(steps))
