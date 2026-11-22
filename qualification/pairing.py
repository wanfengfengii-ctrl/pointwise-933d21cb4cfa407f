from collections import defaultdict, deque
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TypeAlias

from evidence.codec import EvidenceStep, StationBody
from qualification.policy import QualificationRequest


PairState: TypeAlias = tuple[int, int]


@dataclass(frozen=True, slots=True)
class PairTransition:
    target: PairState
    command: str | None
    left_witness: bool
    right_witness: bool


@dataclass(frozen=True, slots=True)
class PairGraph:
    opening: PairState
    outgoing: dict[PairState, tuple[PairTransition, ...]]


_StepIndex: TypeAlias = dict[int, dict[str | None, list[EvidenceStep]]]


def _index(body: StationBody, allowed: set[str]) -> _StepIndex:
    steps = defaultdict(lambda: defaultdict(list))
    for step in body.steps:
        if step.command is None or step.command in allowed:
            steps[step.source][step.command].append(step)
    return steps


def _successors(state: PairState, left: _StepIndex, right: _StepIndex) -> Iterator[PairTransition]:
    a, b = state
    left_steps = left.get(a, {})
    right_steps = right.get(b, {})
    for step in left_steps.get(None, ()):
        yield PairTransition((step.target, b), None, step.witness, False)
    for step in right_steps.get(None, ()):
        yield PairTransition((a, step.target), None, False, step.witness)
    for command, alternatives in left_steps.items():
        if command is None:
            continue
        for left_step in alternatives:
            for right_step in right_steps.get(command, ()):
                yield PairTransition(
                    (left_step.target, right_step.target), command, left_step.witness, right_step.witness
                )


def build_pair_graph(request: QualificationRequest) -> PairGraph:
    permissions = set(request.permissions)
    left = _index(request.left.body, permissions)
    right = _index(request.right.body, permissions)
    opening = (request.left.body.opening, request.right.body.opening)
    outgoing = {}
    seen = {opening}
    pending = deque([opening])
    while pending:
        state = pending.popleft()
        transitions = tuple(_successors(state, left, right))
        outgoing[state] = transitions
        for transition in transitions:
            if transition.target not in seen:
                seen.add(transition.target)
                pending.append(transition.target)
    return PairGraph(opening, outgoing)
