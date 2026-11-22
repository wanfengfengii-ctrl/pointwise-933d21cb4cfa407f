"""V2 shared-panel station artifacts.

A panel artifact is a public, anonymous view of one revision.  It keeps the
complete command catalog and, for every anonymous state and command, the joint
set of possible outcomes of "any finite run of local preparation, then one
public action": the landing state, whether that round yields a qualified
witness, and whether the executed public action lights this station's lamp.

Private state names, action row identifiers, local action names and readings
never enter the artifact.
"""
import json
from dataclasses import dataclass

from evidence.codec import _canonical
from evidence.identity import (
    V2_VERSION,
    ArtifactIdentity,
    ArtifactIdentityError,
    compute_panel_digest,
    verify_artifact_identity,
)
from records.identity import is_identifier


class PanelFormatError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise PanelFormatError(f'duplicate panel artifact field {name!r}')
        result[name] = value
    return result


@dataclass(frozen=True, slots=True)
class PanelOutcome:
    target: int
    witness: bool
    lit: bool


@dataclass(frozen=True, slots=True)
class PanelMove:
    state: int
    command: str
    outcomes: tuple[PanelOutcome, ...]


@dataclass(frozen=True, slots=True)
class PanelBody:
    opening: int
    state_count: int
    commands: tuple[str, ...]
    moves: tuple[PanelMove, ...]

    def move_index(self) -> dict[tuple[int, str], tuple[PanelOutcome, ...]]:
        return {(move.state, move.command): move.outcomes for move in self.moves}


def _wire(body: PanelBody) -> dict:
    moves = []
    for move in sorted(body.moves, key=lambda item: (item.state, item.command)):
        outcomes = sorted(move.outcomes, key=lambda item: (item.target, item.witness, item.lit))
        moves.append({
            'state': move.state,
            'command': move.command,
            'outcomes': [
                {'to': outcome.target, 'witness': outcome.witness, 'lit': outcome.lit}
                for outcome in outcomes
            ],
        })
    return {
        'opening': body.opening,
        'state_count': body.state_count,
        'commands': list(body.commands),
        'moves': moves,
    }


def _fields(value: object, expected: set[str], scope: str) -> None:
    if not isinstance(value, dict) or value.keys() != expected:
        raise PanelFormatError(f'invalid {scope} fields')


def _state_in_range(state: object, count: int) -> bool:
    return type(state) is int and 0 <= state < count


def _parse_body(value: object) -> PanelBody:
    _fields(value, {'opening', 'state_count', 'commands', 'moves'}, 'panel body')
    count = value['state_count']
    opening = value['opening']
    if type(count) is not int or count <= 0 or not _state_in_range(opening, count):
        raise PanelFormatError('invalid opening or anonymous state range')
    raw_commands = value['commands']
    if not isinstance(raw_commands, list) or not all(
        is_identifier(command) for command in raw_commands
    ):
        raise PanelFormatError('invalid panel catalog')
    commands = set(raw_commands)
    if raw_commands != sorted(commands):
        raise PanelFormatError('panel catalog must be sorted and unique')
    raw_moves = value['moves']
    if not isinstance(raw_moves, list):
        raise PanelFormatError('panel moves must be an array')
    seen_pairs = set()
    moves = []
    for entry in raw_moves:
        _fields(entry, {'state', 'command', 'outcomes'}, 'panel move')
        state = entry['state']
        command = entry['command']
        if not _state_in_range(state, count):
            raise PanelFormatError('panel move references a state outside the body')
        if not is_identifier(command) or command not in commands:
            raise PanelFormatError('panel move outside the fixed catalog')
        if (state, command) in seen_pairs:
            raise PanelFormatError('duplicate panel move for one state and command')
        seen_pairs.add((state, command))
        raw_outcomes = entry['outcomes']
        if not isinstance(raw_outcomes, list) or not raw_outcomes:
            raise PanelFormatError('panel move requires possible outcomes')
        outcomes = []
        seen_outcomes = set()
        for item in raw_outcomes:
            _fields(item, {'to', 'witness', 'lit'}, 'panel outcome')
            target = item['to']
            witness = item['witness']
            lit = item['lit']
            if not _state_in_range(target, count):
                raise PanelFormatError('panel outcome references a state outside the body')
            if type(witness) is not bool or type(lit) is not bool:
                raise PanelFormatError('panel outcome witness and lamp must be booleans')
            triple = (target, witness, lit)
            if triple in seen_outcomes:
                raise PanelFormatError('duplicate panel outcome')
            seen_outcomes.add(triple)
            outcomes.append(PanelOutcome(target, witness, lit))
        moves.append(PanelMove(state, command, tuple(outcomes)))
    return PanelBody(opening, count, tuple(raw_commands), tuple(moves))


def encode_panel(job: str, station: str, revision: int, body: PanelBody) -> str:
    wire = _wire(body)
    _parse_body(wire)
    canonical = _canonical(wire)
    digest = compute_panel_digest(V2_VERSION, job, station, revision, canonical)
    try:
        verify_artifact_identity(
            ArtifactIdentity(job, station, revision, digest), canonical, version=V2_VERSION
        )
    except ArtifactIdentityError as error:
        raise PanelFormatError(str(error)) from error
    return _canonical({
        'version': V2_VERSION,
        'job': job,
        'station': station,
        'revision': revision,
        'digest': digest,
        'body': wire,
    })


def decode_panel(
    raw: str, *, expected_job: str | None = None, expected_station: str | None = None
) -> tuple[ArtifactIdentity, PanelBody]:
    if not isinstance(raw, str):
        raise PanelFormatError('panel artifact must be JSON text')
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except PanelFormatError:
        raise
    except (ValueError, RecursionError) as error:
        raise PanelFormatError('invalid panel artifact JSON') from error
    _fields(value, {'version', 'job', 'station', 'revision', 'digest', 'body'}, 'V2 envelope')
    if type(value['version']) is not int or value['version'] != V2_VERSION:
        raise PanelFormatError('unsupported panel artifact version')
    identity = ArtifactIdentity(value['job'], value['station'], value['revision'], value['digest'])
    body = _parse_body(value['body'])
    try:
        verify_artifact_identity(
            identity,
            _canonical(value['body']),
            expected_job=expected_job,
            expected_station=expected_station,
            version=V2_VERSION,
        )
    except ArtifactIdentityError as error:
        raise PanelFormatError(str(error)) from error
    return identity, body
