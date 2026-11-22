from dataclasses import dataclass

from evidence.codec import StationBody, StationFormatError, decode_station
from evidence.identity import ArtifactIdentity
from evidence.panel_codec import PanelBody, PanelFormatError, decode_panel
from records.identity import is_identifier


class StationAcceptanceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AcceptedStation:
    identity: ArtifactIdentity
    body: StationBody
    raw: str


@dataclass(frozen=True, slots=True)
class AcceptedPanel:
    identity: ArtifactIdentity
    body: PanelBody
    raw: str


def accept_station(raw: str, expected_job: str, expected_station: str) -> AcceptedStation:
    if not is_identifier(expected_job) or not is_identifier(expected_station):
        raise StationAcceptanceError('expected job and station are required')
    try:
        identity, body = decode_station(raw, expected_job=expected_job, expected_station=expected_station)
    except StationFormatError as error:
        raise StationAcceptanceError(str(error)) from error
    return AcceptedStation(identity, body, raw)


def accept_panel(raw: str, expected_job: str, expected_station: str) -> AcceptedPanel:
    if not is_identifier(expected_job) or not is_identifier(expected_station):
        raise StationAcceptanceError('expected job and station are required')
    try:
        identity, body = decode_panel(raw, expected_job=expected_job, expected_station=expected_station)
    except PanelFormatError as error:
        raise StationAcceptanceError(str(error)) from error
    return AcceptedPanel(identity, body, raw)
