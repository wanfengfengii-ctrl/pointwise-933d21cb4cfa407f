"""Guaranteed shared-panel strategies from two offline V2 station artifacts.

The night shift sends one public command per round and only sees whether the
shared panel is lit.  A lamp value is lit when either station's executed public
action is declared lit.  Both stations may spend any finite run of local
preparation before their public action, so one artifact step describes a whole
*set* of possible (landing state, witness this round, lamp) outcomes.

A strategy may only issue a command when every world state still compatible
with the observed command and lamp history has at least one way to complete it,
and may stop only when every compatible state already carries both stations'
qualified witnesses.  The strategy is a finite tree bounded by ``max_steps``.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeAlias

from evidence.acceptance import AcceptedPanel
from evidence.panel_codec import PanelBody, PanelOutcome
from records.identity import is_identifier


class PanelQualificationRejected(ValueError):
    pass


MAX_PANEL_STEPS = 8

# (left state, right state, left witness seen, right witness seen)
World: TypeAlias = tuple[int, int, bool, bool]
Belief: TypeAlias = frozenset[World]

_MoveIndex: TypeAlias = dict[tuple[int, str], tuple[PanelOutcome, ...]]


@dataclass(frozen=True, slots=True)
class PanelRequest:
    left: AcceptedPanel
    right: AcceptedPanel
    permissions: tuple[str, ...]
    max_steps: int


@dataclass(frozen=True, slots=True)
class PanelResult:
    request: PanelRequest
    status: str
    strategy: dict | None


def _move_index(body: PanelBody) -> _MoveIndex:
    return body.move_index()


def _command_outcomes(index: _MoveIndex, state: int, command: str) -> tuple[PanelOutcome, ...]:
    return index.get((state, command), ())


def _selectable(belief: Belief, command: str, left: _MoveIndex, right: _MoveIndex) -> bool:
    for left_state, right_state, _, _ in belief:
        if not _command_outcomes(left, left_state, command):
            return False
        if not _command_outcomes(right, right_state, command):
            return False
    return True


def _advance(
    belief: Belief, command: str, left: _MoveIndex, right: _MoveIndex
) -> dict[int, Belief] | None:
    """Return lamp -> successor belief, or None when some world cannot complete."""
    if not _selectable(belief, command, left, right):
        return None
    groups: dict[int, set[World]] = {0: set(), 1: set()}
    for left_state, right_state, left_witness, right_witness in belief:
        for left_outcome in _command_outcomes(left, left_state, command):
            for right_outcome in _command_outcomes(right, right_state, command):
                lamp = 1 if left_outcome.lit or right_outcome.lit else 0
                groups[lamp].add((
                    left_outcome.target,
                    right_outcome.target,
                    left_witness or left_outcome.witness,
                    right_witness or right_outcome.witness,
                ))
    return {lamp: frozenset(worlds) for lamp, worlds in sorted(groups.items()) if worlds}


def _settled(belief: Belief) -> bool:
    return all(left_witness and right_witness for _, _, left_witness, right_witness in belief)


def _strategy(
    belief: Belief,
    remaining: int,
    permissions: tuple[str, ...],
    left: _MoveIndex,
    right: _MoveIndex,
    memory: dict[tuple[Belief, int], dict | None] | None = None,
) -> dict | None:
    if memory is None:
        memory = {}
    key = (belief, remaining)
    if key in memory:
        return memory[key]
    if _settled(belief):
        memory[key] = {'stop': True}
        return memory[key]
    if remaining <= 0:
        memory[key] = None
        return None
    for command in permissions:
        branches = _advance(belief, command, left, right)
        if branches is None:
            continue
        subtree: dict[str, dict] = {}
        for lamp, successor in branches.items():
            child = _strategy(successor, remaining - 1, permissions, left, right, memory)
            if child is None:
                break
            subtree[str(lamp)] = child
        else:
            memory[key] = {'command': command, 'next': subtree}
            return memory[key]
    memory[key] = None
    return None


def prepare_panel_request(
    left: AcceptedPanel,
    right: AcceptedPanel,
    permissions: Iterable[str],
    max_steps: int,
) -> PanelRequest:
    if not isinstance(left, AcceptedPanel) or not isinstance(right, AcceptedPanel):
        raise PanelQualificationRejected('both parents must be accepted V2 panel artifacts')
    if left.identity.job != right.identity.job:
        raise PanelQualificationRejected('parents must belong to the same job')
    if left.identity.station == right.identity.station:
        raise PanelQualificationRejected('parents must belong to different stations')
    if left.body.commands != right.body.commands:
        raise PanelQualificationRejected('parent command catalogs differ')
    if type(max_steps) is not int or not 0 <= max_steps <= MAX_PANEL_STEPS:
        raise PanelQualificationRejected('max_steps must be an integer from 0 to 8')
    if not isinstance(permissions, Iterable) or isinstance(permissions, (str, bytes, bytearray)):
        raise PanelQualificationRejected('permissions must be a collection of command identifiers')
    known = set(left.body.commands)
    allowed = set()
    for command in permissions:
        if not is_identifier(command) or command not in known:
            raise PanelQualificationRejected(f'unknown permitted command {command!r}')
        allowed.add(command)
    return PanelRequest(left, right, tuple(sorted(allowed)), max_steps)


def qualify_panel(request: PanelRequest) -> PanelResult:
    opening: Belief = frozenset({(request.left.body.opening, request.right.body.opening, False, False)})
    strategy = _strategy(
        opening,
        request.max_steps,
        request.permissions,
        _move_index(request.left.body),
        _move_index(request.right.body),
    )
    if strategy is None:
        return PanelResult(request, 'impossible', None)
    return PanelResult(request, 'guaranteed', strategy)
