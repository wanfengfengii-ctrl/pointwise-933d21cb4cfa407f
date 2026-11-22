from collections import deque
from collections.abc import Set

from qualification.pairing import PairGraph, PairState


def first_commands(graph: PairGraph, repeatable: Set[PairState]) -> tuple[str, ...]:
    commands = set()
    visited = {graph.opening}
    pending = deque([graph.opening])
    while pending:
        for step in graph.outgoing[pending.popleft()]:
            if step.command is not None:
                if step.target in repeatable:
                    commands.add(step.command)
            elif step.target not in visited:
                visited.add(step.target)
                pending.append(step.target)
    return tuple(sorted(commands))
