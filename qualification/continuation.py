from collections import deque

from qualification.cycles import strongly_connected_regions
from qualification.pairing import PairGraph, PairState


def repeatable_targets(graph: PairGraph) -> frozenset[PairState]:
    """Find states with a continuation that repeats all three obligations."""
    partition = strongly_connected_regions(graph)
    good = set()
    for region, internal in zip(partition.regions, partition.internal):
        # Strong connectivity allows the run to revisit each selected edge in turn.
        if (
            any(step.command is not None for step in internal)
            and any(step.left_witness for step in internal)
            and any(step.right_witness for step in internal)
        ):
            good.update(region)
    pending = deque(good)
    while pending:
        for parent in partition.predecessors[pending.popleft()]:
            if parent not in good:
                good.add(parent)
                pending.append(parent)
    return frozenset(good)
