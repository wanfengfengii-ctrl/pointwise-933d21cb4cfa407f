import sqlite3

from evidence.codec import StationFormatError, encode_station
from evidence.projection import project_station_body
from records.identity import RevisionKey, RevisionMissing, RevisionRejected
from records.revisions import read_revision
from records.storage import RevisionStore


class FreezeRejected(ValueError):
    pass


class StationIssueRegistry:
    def __init__(self, store: RevisionStore):
        self.connection = store.connection

    def register(self, key: RevisionKey, raw: str) -> str:
        """Register generated text once and return the original on reissue."""
        scope = (key.station.job, key.station.station, key.number)
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            self.connection.execute(
                '''INSERT INTO station_issues(revision, artifact)
                   SELECT number, ? FROM revisions WHERE job = ? AND station = ? AND number = ?
                   ON CONFLICT(revision) DO NOTHING''',
                (raw, *scope),
            )
            row = self.connection.execute(
                '''SELECT i.artifact FROM station_issues AS i
                   JOIN revisions AS r ON r.number = i.revision
                   WHERE r.job = ? AND r.station = ? AND r.number = ?''',
                scope,
            ).fetchone()
            if row is None:
                raise FreezeRejected('cannot register an absent revision')
        return row[0]


def freeze_station(store: RevisionStore, key: RevisionKey) -> str:
    if not isinstance(key, RevisionKey):
        raise FreezeRejected('a fixed revision key is required')
    try:
        revision = read_revision(store, key)
        body = project_station_body(revision)
        station = revision.key.station
        raw = encode_station(station.job, station.station, revision.key.number, body)
        return StationIssueRegistry(store).register(revision.key, raw)
    except (RevisionMissing, RevisionRejected, StationFormatError, sqlite3.Error) as error:
        raise FreezeRejected(f'cannot freeze revision {key.number}: {error}') from error
