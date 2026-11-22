from dataclasses import dataclass

from reports.receipt import PanelSnapshot, ReportSnapshot
from reports.storage import ReportStore


@dataclass(frozen=True, slots=True)
class MissingReport:
    number: int


def read_report(store: ReportStore, number: int) -> ReportSnapshot | MissingReport:
    snapshot = store.load(number)
    return MissingReport(number) if snapshot is None else snapshot


def read_panel(store: ReportStore, number: int) -> PanelSnapshot | MissingReport:
    snapshot = store.load_panel(number)
    return MissingReport(number) if snapshot is None else snapshot
