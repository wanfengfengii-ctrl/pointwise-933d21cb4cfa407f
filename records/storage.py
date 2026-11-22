import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from records.identity import RevisionKey, RevisionMissing, RevisionRejected, StationKey
from records.readings import ActionRow, RevisionDraft, WitnessRow
from review.commands import CommandCatalog


_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS catalogs (
        job TEXT PRIMARY KEY NOT NULL,
        commands TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS revisions (
        number INTEGER PRIMARY KEY,
        job TEXT NOT NULL REFERENCES catalogs(job),
        station TEXT NOT NULL,
        parent INTEGER,
        draft TEXT NOT NULL,
        UNIQUE (job, station, number),
        FOREIGN KEY (job, station, parent) REFERENCES revisions(job, station, number)
    )''',
    '''CREATE TABLE IF NOT EXISTS station_issues (
        revision INTEGER PRIMARY KEY REFERENCES revisions(number),
        artifact TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS panel_issues (
        revision INTEGER PRIMARY KEY REFERENCES revisions(number),
        declaration TEXT NOT NULL,
        artifact TEXT NOT NULL
    )''',
)


@dataclass(frozen=True, slots=True)
class StoredRevision:
    key: RevisionKey
    parent: RevisionKey | None
    draft: RevisionDraft


def _serialize(draft: RevisionDraft) -> str:
    return json.dumps(asdict(draft), ensure_ascii=True, separators=(',', ':'))


def _deserialize(payload: str) -> RevisionDraft:
    value = json.loads(payload)
    return RevisionDraft(
        value['opening'],
        tuple(ActionRow(**row) for row in value['actions']),
        tuple(WitnessRow(**row) for row in value['witnesses']),
    )


class RevisionStore:
    def __init__(self, path: str | Path):
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.execute('PRAGMA foreign_keys = ON')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def close(self) -> None:
        self.connection.close()

    def initialize(self, catalogs=()) -> None:
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            for statement in _SCHEMA:
                self.connection.execute(statement)
            for catalog in catalogs:
                payload = json.dumps(catalog.commands, ensure_ascii=True, separators=(',', ':'))
                self.connection.execute(
                    'INSERT INTO catalogs(job, commands) VALUES (?, ?) ON CONFLICT(job) DO NOTHING',
                    (catalog.job, payload),
                )
                if self.catalog(catalog.job) != catalog:
                    raise RevisionRejected(f'catalog for job {catalog.job} is already fixed')

    def catalog(self, job: str) -> CommandCatalog:
        row = self.connection.execute('SELECT commands FROM catalogs WHERE job = ?', (job,)).fetchone()
        if row is None:
            raise RevisionRejected(f'no command catalog for job {job}')
        return CommandCatalog(job, tuple(json.loads(row[0])))

    def append(
        self, station: StationKey, draft: RevisionDraft, parent: RevisionKey | None
    ) -> RevisionKey:
        """Append a validated draft and check its stored parent within the write transaction."""
        payload = _serialize(draft)
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            self.catalog(station.job)
            if parent is not None:
                if parent.station != station:
                    raise RevisionRejected('parent must have the same job and station')
                present = self.connection.execute(
                    'SELECT 1 FROM revisions WHERE job = ? AND station = ? AND number = ?',
                    (station.job, station.station, parent.number),
                ).fetchone()
                if present is None:
                    raise RevisionRejected(f'parent revision {parent.number} does not exist')
            cursor = self.connection.execute(
                'INSERT INTO revisions(job, station, parent, draft) VALUES (?, ?, ?, ?)',
                (station.job, station.station, None if parent is None else parent.number, payload),
            )
            key = RevisionKey(station, cursor.lastrowid)
        return key

    def load(self, key: RevisionKey) -> StoredRevision:
        row = self.connection.execute(
            'SELECT parent, draft FROM revisions WHERE job = ? AND station = ? AND number = ?',
            (key.station.job, key.station.station, key.number),
        ).fetchone()
        if row is None:
            raise RevisionMissing(key)
        parent = None if row[0] is None else RevisionKey(key.station, row[0])
        return StoredRevision(key, parent, _deserialize(row[1]))
