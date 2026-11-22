import json
import sqlite3
from collections.abc import Iterable

from evidence.codec import StationFormatError, encode_station
from evidence.panel_codec import PanelFormatError, encode_panel
from evidence.panel_projection import project_panel_body
from evidence.projection import project_station_body
from records.identity import (
    RevisionKey,
    RevisionMissing,
    RevisionRejected,
    is_identifier,
)
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


def _declaration(revision, lit_action_ids: object) -> tuple[str, ...]:
    if not isinstance(lit_action_ids, Iterable) or isinstance(
        lit_action_ids, (str, bytes, bytearray)
    ):
        raise FreezeRejected('lit action identifiers must be a non-string collection')
    public_rows = {row.row_id for row in revision.draft.actions if row.kind == 'public'}
    declared = set()
    for row_id in lit_action_ids:
        if not is_identifier(row_id) or row_id not in public_rows:
            raise FreezeRejected(f'{row_id!r} is not a public action of revision {revision.key.number}')
        declared.add(row_id)
    return tuple(sorted(declared))


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


class PanelIssueRegistry:
    def __init__(self, store: RevisionStore):
        self.connection = store.connection

    def register(self, key: RevisionKey, declaration: tuple[str, ...], raw: str) -> str:
        """Bind one lamp declaration to a revision; reissue returns the original text."""
        scope = (key.station.job, key.station.station, key.number)
        publishable = json.dumps(declaration, ensure_ascii=True, separators=(',', ':'))
        scope = (key.station.job, key.station.station, key.number)
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            self.connection.execute(
                '''INSERT INTO panel_issues(revision, declaration, artifact)
                   SELECT number, ?, ? FROM revisions WHERE job = ? AND station = ? AND number = ?
                   ON CONFLICT(revision) DO NOTHING''',
                (publishable, raw, *scope),
            )
            row = self.connection.execute(
                '''SELECT i.declaration, i.artifact FROM panel_issues AS i
                   JOIN revisions AS r ON r.number = i.revision
                   WHERE r.job = ? AND r.station = ? AND r.number = ?''',
                scope,
            ).fetchone()
            if row is None:
                raise FreezeRejected('cannot register an absent revision')
            stored_declaration, stored_artifact = row
            if stored_declaration != publishable:
                raise FreezeRejected(
                    f'revision {key.number} already froze a different lamp declaration'
                )
        return stored_artifact


def freeze_panel(store: RevisionStore, key: RevisionKey, lit_action_ids: Iterable[str]) -> str:
    if not isinstance(key, RevisionKey):
        raise FreezeRejected('a fixed revision key is required')
    try:
        revision = read_revision(store, key)
        declaration = _declaration(revision, lit_action_ids)
        body = project_panel_body(revision, frozenset(declaration))
        station = revision.key.station
        raw = encode_panel(station.job, station.station, revision.key.number, body)
        return PanelIssueRegistry(store).register(revision.key, declaration, raw)
    except (RevisionMissing, RevisionRejected, PanelFormatError, StationFormatError, sqlite3.Error) as error:
        raise FreezeRejected(f'cannot freeze panel revision {key.number}: {error}') from error
