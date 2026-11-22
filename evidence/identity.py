import hashlib
import hmac
import json
from dataclasses import dataclass

from records.identity import is_identifier, is_record_number


V1_VERSION = 1
V2_VERSION = 2
PANEL_VERSION = V2_VERSION


class ArtifactIdentityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    job: str
    station: str
    revision: int
    digest: str


def compute_artifact_digest(job: str, station: str, revision: int, canonical_body: str) -> str:
    return compute_panel_digest(V1_VERSION, job, station, revision, canonical_body)


def compute_panel_digest(
    version: int, job: str, station: str, revision: int, canonical_body: str
) -> str:
    payload = json.dumps(
        [version, job, station, revision, canonical_body],
        ensure_ascii=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(payload.encode('ascii')).hexdigest()


def verify_artifact_identity(
    identity: ArtifactIdentity,
    canonical_body: str,
    *,
    expected_job: str | None = None,
    expected_station: str | None = None,
    version: int = V1_VERSION,
) -> None:
    if not is_identifier(identity.job) or not is_identifier(identity.station):
        raise ArtifactIdentityError('invalid station artifact scope')
    if not is_record_number(identity.revision):
        raise ArtifactIdentityError('invalid station artifact revision')
    if expected_job is not None and identity.job != expected_job:
        raise ArtifactIdentityError('station artifact belongs to another job')
    if expected_station is not None and identity.station != expected_station:
        raise ArtifactIdentityError('station artifact belongs to another station')
    digest = identity.digest
    if not isinstance(digest, str) or len(digest) != 64 or any(
        char not in '0123456789abcdef' for char in digest
    ):
        raise ArtifactIdentityError('invalid station artifact digest')
    expected = compute_panel_digest(
        version, identity.job, identity.station, identity.revision, canonical_body
    )
    if not hmac.compare_digest(digest, expected):
        raise ArtifactIdentityError('station artifact digest mismatch')
