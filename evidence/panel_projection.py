"""Project a fixed revision into the V2 anonymous shared-panel body."""
from collections import defaultdict, deque

from evidence.panel_codec import PanelBody, PanelMove, PanelOutcome
from records.revisions import Revision
from review.witnesses import index_qualified_witnesses


def _local_reach(
    start: int, local_edges: dict[int, list[tuple[int, bool]]]
) -> frozenset[tuple[int, bool]]:
    """Reachability of (state, any-witness-on-the-local-run) through local steps."""
    seen = {(start, False)}
    pending = deque([(start, False)])
    while pending:
        state, witnessed = pending.popleft()
        for target, step_witness in local_edges.get(state, ()):
            node = (target, witnessed or step_witness)
            if node not in seen:
                seen.add(node)
                pending.append(node)
    return frozenset(seen)


def project_panel_body(revision: Revision, lit_action_ids: frozenset[str]) -> PanelBody:
    opening = revision.draft.opening
    anonymous = {opening: 0}
    witnesses = index_qualified_witnesses(revision)
    local_edges: dict[int, list[tuple[int, bool]]] = defaultdict(list)
    public_edges: dict[tuple[int, str], list[tuple[int, bool, bool]]] = defaultdict(list)
    for row in revision.draft.actions:
        source = anonymous.setdefault(row.source, len(anonymous))
        target = anonymous.setdefault(row.target, len(anonymous))
        witnessed = row.row_id in witnesses
        if row.kind == 'local':
            local_edges[source].append((target, witnessed))
        else:
            public_edges[(source, row.label)].append(
                (target, witnessed, row.row_id in lit_action_ids)
            )
    count = len(anonymous)
    reach = {state: _local_reach(state, local_edges) for state in range(count)}
    moves = []
    for state in range(count):
        for command in revision.catalog.commands:
            outcomes = {
                (target, local_witness or public_witness, lit)
                for landing, local_witness in reach[state]
                for target, public_witness, lit in public_edges.get((landing, command), ())
            }
            if outcomes:
                moves.append(PanelMove(
                    state,
                    command,
                    tuple(PanelOutcome(*outcome) for outcome in sorted(outcomes)),
                ))
    return PanelBody(anonymous[opening], count, revision.catalog.commands, tuple(moves))
