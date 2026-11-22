from collections.abc import Iterable
from dataclasses import dataclass

from evidence.acceptance import AcceptedStation
from records.identity import is_identifier


class QualificationRejected(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class QualificationRequest:
    left: AcceptedStation
    right: AcceptedStation
    permissions: tuple[str, ...]


def prepare_request(
    left: AcceptedStation, right: AcceptedStation, permissions: Iterable[str]
) -> QualificationRequest:
    if left.identity.job != right.identity.job:
        raise QualificationRejected('parents must belong to the same job')
    if left.identity.station == right.identity.station:
        raise QualificationRejected('parents must belong to different stations')
    if left.body.commands != right.body.commands:
        raise QualificationRejected('parent command catalogs differ')
    if not isinstance(permissions, Iterable) or isinstance(permissions, (str, bytes, bytearray)):
        raise QualificationRejected('permissions must be a collection of command identifiers')
    known = set(left.body.commands)
    allowed = set()
    for command in permissions:
        if not is_identifier(command) or command not in known:
            raise QualificationRejected(f'unknown permitted command {command!r}')
        allowed.add(command)
    return QualificationRequest(left, right, tuple(sorted(allowed)))
