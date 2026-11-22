import sqlite3
from collections.abc import Iterable

from evidence.acceptance import (
    AcceptedPanel,
    AcceptedStation,
    StationAcceptanceError,
    accept_panel,
    accept_station,
)
from evidence.identity import ArtifactIdentity
from qualification.panel import (
    PanelQualificationRejected,
    PanelRequest,
    prepare_panel_request,
    qualify_panel,
)
from qualification.policy import QualificationRejected, prepare_request
from qualification.result import qualify_request
from reports.receipt import PanelSnapshot, ReportSnapshot
from reports.storage import ReportStore


class ReportIssueError(ValueError):
    pass


def _fixed_parent(parent: AcceptedStation) -> AcceptedStation:
    if not isinstance(parent, AcceptedStation) or not isinstance(parent.identity, ArtifactIdentity):
        raise StationAcceptanceError('expected an accepted station parent')
    checked = accept_station(parent.raw, parent.identity.job, parent.identity.station)
    if checked != parent:
        raise StationAcceptanceError('accepted parent does not match its original artifact')
    return checked


def _fixed_panel(parent: AcceptedPanel) -> AcceptedPanel:
    if not isinstance(parent, AcceptedPanel) or not isinstance(parent.identity, ArtifactIdentity):
        raise StationAcceptanceError('expected an accepted panel parent')
    checked = accept_panel(parent.raw, parent.identity.job, parent.identity.station)
    if checked != parent:
        raise StationAcceptanceError('accepted panel parent does not match its original artifact')
    return checked


def issue_report(
    store: ReportStore, left: AcceptedStation, right: AcceptedStation, permissions: Iterable[str]
) -> ReportSnapshot:
    try:
        request = prepare_request(_fixed_parent(left), _fixed_parent(right), permissions)
        result = qualify_request(request)
        return store.publish(result)
    except (StationAcceptanceError, QualificationRejected, sqlite3.Error) as error:
        raise ReportIssueError(str(error)) from error


def issue_panel(
    store: ReportStore,
    left: AcceptedPanel,
    right: AcceptedPanel,
    permissions: Iterable[str],
    max_steps: int,
) -> PanelSnapshot:
    try:
        request = prepare_panel_request(
            _fixed_panel(left), _fixed_panel(right), permissions, max_steps
        )
        result = qualify_panel(request)
        return store.publish_panel(result)
    except (StationAcceptanceError, PanelQualificationRejected, sqlite3.Error) as error:
        raise ReportIssueError(str(error)) from error


__all__ = ['ReportIssueError', 'issue_panel', 'issue_report', 'PanelRequest']

