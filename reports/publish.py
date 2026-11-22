import sqlite3
from collections.abc import Iterable

from evidence.acceptance import AcceptedStation, StationAcceptanceError, accept_station
from evidence.identity import ArtifactIdentity
from qualification.policy import QualificationRejected, prepare_request
from qualification.result import qualify_request
from reports.receipt import ReportSnapshot
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


def issue_report(
    store: ReportStore, left: AcceptedStation, right: AcceptedStation, permissions: Iterable[str]
) -> ReportSnapshot:
    try:
        request = prepare_request(_fixed_parent(left), _fixed_parent(right), permissions)
        result = qualify_request(request)
        return store.publish(result)
    except (StationAcceptanceError, QualificationRejected, sqlite3.Error) as error:
        raise ReportIssueError(str(error)) from error
