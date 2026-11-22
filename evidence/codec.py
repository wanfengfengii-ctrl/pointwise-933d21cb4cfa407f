import json
from dataclasses import dataclass

from evidence.identity import (
    V1_VERSION,
    ArtifactIdentity,
    ArtifactIdentityError,
    compute_artifact_digest,
    verify_artifact_identity,
)
from records.identity import is_identifier


class StationFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EvidenceStep:
    source: int
    target: int
    command: str | None
    witness: bool


@dataclass(frozen=True, slots=True)
class StationBody:
    opening: int
    state_count: int
    commands: tuple[str, ...]
    steps: tuple[EvidenceStep, ...]


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise StationFormatError(f'duplicate station artifact field {name!r}')
        result[name] = value
    return result


def _body_wire(body: StationBody) -> dict:
    steps = []
    for step in body.steps:
        row = {'from': step.source, 'to': step.target, 'witness': step.witness}
        if step.command is None:
            row['kind'] = 'local'
        else:
            row.update(kind='public', command=step.command)
        steps.append(row)
    return {
        'opening': body.opening,
        'state_count': body.state_count,
        'commands': list(body.commands),
        'steps': steps,
    }


def _fields(value: object, expected: set[str], scope: str) -> None:
    if not isinstance(value, dict) or value.keys() != expected:
        raise StationFormatError(f'invalid {scope} fields')


def _state_in_range(state: object, count: int) -> bool:
    return type(state) is int and 0 <= state < count


def _parse_body(value: dict) -> StationBody:
    _fields(value, {'opening', 'state_count', 'commands', 'steps'}, 'station body')
    count = value['state_count']
    opening = value['opening']
    if type(count) is not int or count <= 0 or not _state_in_range(opening, count):
        raise StationFormatError('invalid opening or anonymous state range')
    raw_commands = value['commands']
    if not isinstance(raw_commands, list) or not all(is_identifier(command) for command in raw_commands):
        raise StationFormatError('invalid station catalog')
    commands = set(raw_commands)
    if raw_commands != sorted(commands):
        raise StationFormatError('station catalog must be sorted and unique')
    if not isinstance(value['steps'], list):
        raise StationFormatError('station steps must be an array')
    steps = []
    for row in value['steps']:
        kind = row.get('kind') if isinstance(row, dict) else None
        fields = {'from', 'to', 'kind', 'witness'}
        command = None
        if kind == 'public':
            _fields(row, fields | {'command'}, 'public step')
            command = row['command']
            if not is_identifier(command) or command not in commands:
                raise StationFormatError('public step outside station catalog')
        elif kind == 'local':
            _fields(row, fields, 'local step')
        else:
            raise StationFormatError('invalid step kind')
        if not all(_state_in_range(row[name], count) for name in ('from', 'to')):
            raise StationFormatError('step references a state outside the body')
        if type(row['witness']) is not bool:
            raise StationFormatError('witness must be a boolean')
        steps.append(EvidenceStep(row['from'], row['to'], command, row['witness']))
    return StationBody(opening, count, tuple(raw_commands), tuple(steps))


def encode_station(job: str, station: str, revision: int, body: StationBody) -> str:
    wire = _body_wire(body)
    _parse_body(wire)
    canonical = _canonical(wire)
    digest = compute_artifact_digest(job, station, revision, canonical)
    try:
        verify_artifact_identity(ArtifactIdentity(job, station, revision, digest), canonical)
    except ArtifactIdentityError as error:
        raise StationFormatError(str(error)) from error
    return _canonical({
        'version': V1_VERSION,
        'job': job,
        'station': station,
        'revision': revision,
        'digest': digest,
        'body': wire,
    })


def decode_station(
    raw: str, *, expected_job: str | None = None, expected_station: str | None = None
) -> tuple[ArtifactIdentity, StationBody]:
    if not isinstance(raw, str):
        raise StationFormatError('station artifact must be JSON text')
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except StationFormatError:
        raise
    except (ValueError, RecursionError) as error:
        raise StationFormatError('invalid station artifact JSON') from error
    _fields(value, {'version', 'job', 'station', 'revision', 'digest', 'body'}, 'V1 envelope')
    if type(value['version']) is not int or value['version'] != V1_VERSION:
        raise StationFormatError('unsupported station artifact version')
    identity = ArtifactIdentity(value['job'], value['station'], value['revision'], value['digest'])
    body = _parse_body(value['body'])
    try:
        verify_artifact_identity(
            identity, _canonical(value['body']), expected_job=expected_job, expected_station=expected_station
        )
    except ArtifactIdentityError as error:
        raise StationFormatError(str(error)) from error
    return identity, body
