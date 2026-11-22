from dataclasses import dataclass

from qualification.result import QualificationResult


@dataclass(frozen=True, slots=True)
class PublicationReceipt:
    report_number: int
    event: str


@dataclass(frozen=True, slots=True)
class ReportSnapshot:
    number: int
    job: str
    stations: tuple[str, str]
    parents: tuple[str, str]
    permissions: tuple[str, ...]
    first_commands: tuple[str, ...]
    receipt: PublicationReceipt


@dataclass(frozen=True, slots=True)
class PanelSnapshot:
    number: int
    job: str
    stations: tuple[str, str]
    parents: tuple[str, str]
    permissions: tuple[str, ...]
    max_steps: int
    status: str
    strategy: dict | None
    receipt: PublicationReceipt


def make_snapshot(number: int, result: QualificationResult) -> ReportSnapshot:
    left, right = result.request.left, result.request.right
    return ReportSnapshot(
        number,
        left.identity.job,
        (left.identity.station, right.identity.station),
        (left.raw, right.raw),
        result.request.permissions,
        result.first_commands,
        PublicationReceipt(number, 'issued'),
    )
