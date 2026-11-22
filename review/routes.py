from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass

from records.readings import ActionRow, WitnessRow
from records.revisions import Revision
from review.witnesses import index_qualified_witnesses


@dataclass(frozen=True, slots=True)
class RouteIndex:
    outgoing: Mapping[str, tuple[ActionRow, ...]]
    witnesses: Mapping[str, tuple[WitnessRow, ...]]


@dataclass(frozen=True, slots=True)
class ScriptPath:
    actions: tuple[ActionRow, ...]


_SearchState = tuple[str, int, bool]


def build_route_index(revision: Revision) -> RouteIndex:
    outgoing = defaultdict(list)
    for action in sorted(revision.draft.actions, key=lambda row: row.row_id):
        outgoing[action.source].append(action)
    return RouteIndex(
        {state: tuple(rows) for state, rows in outgoing.items()},
        index_qualified_witnesses(revision),
    )


def _trace(
    end: _SearchState, previous: dict[_SearchState, tuple[_SearchState, ActionRow] | None]
) -> ScriptPath:
    actions = []
    while previous[end] is not None:
        end, action = previous[end]
        actions.append(action)
    return ScriptPath(tuple(reversed(actions)))


def match_script_path(index: RouteIndex, opening: str, script: tuple[str, ...]) -> ScriptPath | None:
    initial = (opening, 0, False)
    pending = deque([initial])
    previous = {initial: None}
    fallback = None
    while pending:
        node = pending.popleft()
        state, position, witnessed = node
        if position == len(script):
            if witnessed:
                return _trace(node, previous)
            if fallback is None:
                fallback = node
        for action in index.outgoing.get(state, ()):
            next_position = position
            if action.kind == 'public':
                if position == len(script) or action.label != script[position]:
                    continue
                next_position += 1
            target = (action.target, next_position, witnessed or action.row_id in index.witnesses)
            if target not in previous:
                previous[target] = (node, action)
                pending.append(target)
    return None if fallback is None else _trace(fallback, previous)
