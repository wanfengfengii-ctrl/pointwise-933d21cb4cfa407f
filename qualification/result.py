from dataclasses import dataclass

from qualification.continuation import repeatable_targets
from qualification.pairing import build_pair_graph
from qualification.policy import QualificationRequest
from qualification.starts import first_commands


@dataclass(frozen=True, slots=True)
class QualificationResult:
    request: QualificationRequest
    first_commands: tuple[str, ...]


def qualify_request(request: QualificationRequest) -> QualificationResult:
    if not request.permissions:
        return QualificationResult(request, ())
    graph = build_pair_graph(request)
    repeatable = repeatable_targets(graph)
    return QualificationResult(request, first_commands(graph, repeatable))
