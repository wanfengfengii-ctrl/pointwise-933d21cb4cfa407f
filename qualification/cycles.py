from dataclasses import dataclass

from qualification.pairing import PairGraph, PairState, PairTransition


@dataclass(frozen=True, slots=True)
class ComponentPartition:
    regions: tuple[frozenset[PairState], ...]
    internal: tuple[tuple[PairTransition, ...], ...]
    predecessors: dict[PairState, list[PairState]]


def _finishing_order(graph: PairGraph) -> list[PairState]:
    seen = set()
    order = []
    for root in graph.outgoing:
        if root in seen:
            continue
        seen.add(root)
        stack = [(root, iter(graph.outgoing[root]))]
        while stack:
            state, remaining = stack[-1]
            step = next(remaining, None)
            if step is None:
                order.append(state)
                stack.pop()
            elif step.target not in seen:
                seen.add(step.target)
                stack.append((step.target, iter(graph.outgoing[step.target])))
    return order


def strongly_connected_regions(graph: PairGraph) -> ComponentPartition:
    predecessors = {state: [] for state in graph.outgoing}
    for state, steps in graph.outgoing.items():
        for step in steps:
            predecessors[step.target].append(state)

    region_by_state = {}
    regions = []
    for root in reversed(_finishing_order(graph)):
        if root in region_by_state:
            continue
        number = len(regions)
        region_by_state[root] = number
        members = {root}
        pending = [root]
        while pending:
            for parent in predecessors[pending.pop()]:
                if parent not in region_by_state:
                    region_by_state[parent] = number
                    members.add(parent)
                    pending.append(parent)
        regions.append(frozenset(members))

    internal = [[] for _ in regions]
    for state, steps in graph.outgoing.items():
        number = region_by_state[state]
        for step in steps:
            if region_by_state[step.target] == number:
                internal[number].append(step)
    return ComponentPartition(tuple(regions), tuple(tuple(steps) for steps in internal), predecessors)
