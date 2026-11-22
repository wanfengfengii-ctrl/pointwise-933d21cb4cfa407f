from dataclasses import dataclass

from reports.receipt import ReportSnapshot
from reports.storage import ReportStore


@dataclass(frozen=True, slots=True)
class MissingReport:
    number: int


def read_report(store: ReportStore, number: int) -> ReportSnapshot | MissingReport:
    snapshot = store.load(number)
    return MissingReport(number) if snapshot is None else snapshot
