import json
import sqlite3
from pathlib import Path

from qualification.result import QualificationResult
from records.identity import is_record_number
from reports.receipt import PublicationReceipt, ReportSnapshot, make_snapshot


_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS reports (
        number INTEGER PRIMARY KEY,
        job TEXT NOT NULL,
        permissions TEXT NOT NULL,
        first_commands TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS report_parents (
        report_number INTEGER NOT NULL REFERENCES reports(number),
        position INTEGER NOT NULL CHECK (position IN (0, 1)),
        station TEXT NOT NULL,
        artifact TEXT NOT NULL,
        PRIMARY KEY (report_number, position)
    )''',
    '''CREATE TABLE IF NOT EXISTS publications (
        report_number INTEGER PRIMARY KEY REFERENCES reports(number),
        event TEXT NOT NULL CHECK (event = 'issued')
    )''',
)


def _pack(commands: tuple[str, ...]) -> str:
    return json.dumps(commands, ensure_ascii=True, separators=(',', ':'))


class ReportStore:
    def __init__(self, path: str | Path):
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.execute('PRAGMA foreign_keys = ON')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def close(self) -> None:
        self.connection.close()

    def initialize(self) -> None:
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            for statement in _SCHEMA:
                self.connection.execute(statement)

    def publish(self, result: QualificationResult) -> ReportSnapshot:
        permissions = _pack(result.request.permissions)
        starts = _pack(result.first_commands)
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            cursor = self.connection.execute(
                'INSERT INTO reports(job, permissions, first_commands) VALUES (?, ?, ?)',
                (result.request.left.identity.job, permissions, starts),
            )
            snapshot = make_snapshot(cursor.lastrowid, result)
            self.connection.executemany(
                '''INSERT INTO report_parents(report_number, position, station, artifact)
                   VALUES (?, ?, ?, ?)''',
                (
                    (snapshot.number, position, station, artifact)
                    for position, (station, artifact) in enumerate(zip(snapshot.stations, snapshot.parents))
                ),
            )
            self.connection.execute(
                'INSERT INTO publications(report_number, event) VALUES (?, ?)',
                (snapshot.receipt.report_number, snapshot.receipt.event),
            )
        return snapshot

    def load(self, number: int) -> ReportSnapshot | None:
        if not is_record_number(number):
            return None
        row = self.connection.execute(
            '''SELECT r.job, r.permissions, r.first_commands,
                      l.station, l.artifact, b.station, b.artifact, p.event
               FROM reports AS r
               JOIN report_parents AS l ON l.report_number = r.number AND l.position = 0
               JOIN report_parents AS b ON b.report_number = r.number AND b.position = 1
               JOIN publications AS p ON p.report_number = r.number
               WHERE r.number = ?''',
            (number,),
        ).fetchone()
        if row is None:
            return None
        job, permissions, starts, left_station, left, right_station, right, event = row
        return ReportSnapshot(
            number,
            job,
            (left_station, right_station),
            (left, right),
            tuple(json.loads(permissions)),
            tuple(json.loads(starts)),
            PublicationReceipt(number, event),
        )
