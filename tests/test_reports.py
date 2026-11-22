import sqlite3
import tempfile
import unittest
from pathlib import Path

from evidence.acceptance import accept_station
from evidence.freeze import freeze_station
from records.intake import accept_revision
from records.storage import RevisionStore
from reports.publish import ReportIssueError, issue_report
from reports.retrieve import MissingReport, read_report
from reports.storage import ReportStore
from tests.fixtures import ALPHA, CATALOG, bypass, offline_pair, publication_counts, steady


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.root / 'reports.sqlite3'

    def test_atomic_failure(self):
        left, right = offline_pair(self.root, steady(), steady())
        with ReportStore(self.path) as store:
            store.initialize()
            old = issue_report(store, left, right, ['p'])
            # The trigger writes successfully. SQLite checks this foreign key at COMMIT.
            store.connection.executescript('''
                CREATE TABLE commit_targets (id INTEGER PRIMARY KEY);
                CREATE TABLE commit_requirements (
                    id INTEGER REFERENCES commit_targets(id) DEFERRABLE INITIALLY DEFERRED
                );
                CREATE TRIGGER fail_next_commit AFTER INSERT ON publications
                BEGIN
                    INSERT INTO commit_requirements(id) VALUES (1);
                END;
            ''')
            with self.assertRaisesRegex(ReportIssueError, 'FOREIGN KEY') as failure:
                issue_report(store, left, right, ['p'])
            self.assertIsInstance(failure.exception.__cause__, sqlite3.IntegrityError)
            self.assertFalse(store.connection.in_transaction)
            self.assertEqual(store.connection.execute('SELECT COUNT(*) FROM commit_requirements').fetchone(), (0,))
        with ReportStore(self.path) as reopened:
            self.assertEqual(publication_counts(reopened), (1, 2, 1))
            self.assertEqual(read_report(reopened, old.number), old)
            self.assertEqual(read_report(reopened, old.number + 1), MissingReport(old.number + 1))

    def test_publish_boundary(self):
        left, right = offline_pair(self.root, steady(), steady())
        with ReportStore(self.path) as store:
            store.initialize()
            original = issue_report(store, left, right, ['p'])
            store.connection.execute('''CREATE TRIGGER stop_publication BEFORE INSERT ON publications
                BEGIN SELECT RAISE(ABORT, 'publication unavailable'); END''')
            with self.assertRaisesRegex(ReportIssueError, 'publication unavailable'):
                issue_report(store, left, right, ())
        with ReportStore(self.path) as reopened:
            self.assertEqual(publication_counts(reopened), (1, 2, 1))
            self.assertEqual(read_report(reopened, original.number), original)
            reopened.connection.execute('DROP TRIGGER stop_publication')
            later = issue_report(reopened, left, right, ())
            self.assertEqual(later.first_commands, ())
            self.assertEqual(publication_counts(reopened), (2, 4, 2))

    def test_read_after_source_revision(self):
        left, right = offline_pair(self.root, bypass(False), steady())
        with ReportStore(self.path) as store:
            store.initialize()
            # Submit the opposite station order to verify preservation at retrieval.
            old = issue_report(store, right, left, ['p'])
        with RevisionStore(self.root / 'alpha.sqlite3') as source:
            from records.identity import RevisionKey

            parent = RevisionKey(ALPHA, left.identity.revision)
            new_key = accept_revision(source, ALPHA, bypass(True), parent=parent)
            raw = freeze_station(source, new_key)
        new_left = accept_station(raw, ALPHA.job, ALPHA.station)
        with ReportStore(self.path) as store:
            new = issue_report(store, right, new_left, ['p'])
        with ReportStore(self.path) as reopened:
            reopened.initialize()
            reopened.initialize()
            self.assertEqual(publication_counts(reopened), (2, 4, 2))
            old_again = read_report(reopened, old.number)
            new_again = read_report(reopened, new.number)
            self.assertEqual(old_again, old)
            self.assertEqual(new_again, new)
            self.assertEqual(old_again.stations, ('beta', 'alpha'))
            self.assertEqual(old_again.parents, (right.raw, left.raw))
            self.assertEqual(new_again.parents, (right.raw, raw))
            self.assertEqual(old_again.permissions, ('p',))
            self.assertEqual(old_again.first_commands, ())
            self.assertEqual(new_again.first_commands, ('p',))
            missing = new.number + 100
            self.assertEqual(read_report(reopened, missing), MissingReport(missing))
