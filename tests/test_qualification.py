import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from evidence.acceptance import accept_station
from evidence.freeze import freeze_station
from records.identity import StationKey
from records.intake import accept_revision
from records.storage import RevisionStore
from reports.publish import ReportIssueError, issue_report
from reports.retrieve import read_report
from reports.storage import ReportStore
from review.commands import CommandCatalog
from tests.fixtures import (
    ALPHA, BETA, CATALOG, GATE, OPENING, SPENT, bypass, draft, offline_pair, publication_counts, steady,
)


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.reports = self.enterContext(ReportStore(self.root / 'reports.sqlite3'))
        self.reports.initialize()

    def _sign(self, left_route, right_route, permissions=('p',)):
        left, right = offline_pair(self.root, left_route, right_route)
        return issue_report(self.reports, left, right, permissions)

    def test_repeatable_and_one_way(self):
        good = self._sign(steady(), steady())
        self.assertEqual(good.first_commands, ('p',))
        one_way = self._sign(bypass(False), steady())
        actual = list(one_way.first_commands)
        self.assertEqual(actual, [], f'REPEAT_QUALIFICATION_MISMATCH actual={actual!r} expected=[]')
        self.assertEqual(read_report(self.reports, one_way.number), one_way)
        self.assertEqual(publication_counts(self.reports), (2, 4, 2))

    def test_offline_variants(self):
        with RevisionStore(self.root / 'alpha.sqlite3') as source:
            source.initialize((CATALOG,))
            first = accept_revision(source, ALPHA, bypass(False))
            corrected = accept_revision(source, ALPHA, bypass(True), parent=first)
            out = freeze_station(source, first)
            back = freeze_station(source, corrected)
        with RevisionStore(self.root / 'beta.sqlite3') as source:
            source.initialize((CATALOG,))
            key = accept_revision(source, BETA, steady())
            right_raw = freeze_station(source, key)
        a0 = accept_station(out, ALPHA.job, ALPHA.station)
        a1 = accept_station(back, ALPHA.job, ALPHA.station)
        b = accept_station(right_raw, BETA.job, BETA.station)
        old = issue_report(self.reports, a0, b, ['p'])
        new = issue_report(self.reports, a1, b, ['p'])
        actual = list(old.first_commands)
        self.assertEqual(actual, [], f'REPEAT_QUALIFICATION_MISMATCH actual={actual!r} expected=[]')
        self.assertEqual(list(new.first_commands), ['p'])
        self.assertNotEqual(json.loads(out)['body'], json.loads(back)['body'])
        self.assertEqual(read_report(self.reports, old.number).parents, (out, right_raw))
        self.assertEqual(read_report(self.reports, new.number).parents, (back, right_raw))

    def test_one_way_accurate_parents(self):
        route = draft((
            (OPENING, GATE, 'public', 'p'),
            (GATE, GATE, 'public', 'p'),
        ), (0,))
        report = self._sign(route, steady())
        self.assertEqual(report.first_commands, ())

    def test_staggered_witnesses(self):
        alternating = ((OPENING, GATE, 'public', 'p'), (GATE, OPENING, 'public', 'p'))
        left = draft(alternating, (0,))
        right = draft(alternating, (1,))
        report = self._sign(left, right)
        self.assertEqual(report.first_commands, ('p',))

    def test_public_progress(self):
        finite = draft(((OPENING, GATE, 'public', 'p'), (GATE, GATE, 'local', 'inspect')), (1,))
        report = self._sign(finite, finite)
        self.assertEqual(report.first_commands, ())

    def test_incompatible_continuations(self):
        edges = (
            (OPENING, GATE, 'public', 'p'), (OPENING, SPENT, 'public', 'p'),
            (GATE, GATE, 'public', 'q'), (SPENT, SPENT, 'public', 'r'),
        )
        report = self._sign(draft(edges, (2,)), draft(edges, (3,)), ('p', 'q', 'r'))
        self.assertEqual(report.first_commands, ())

    def test_first_command(self):
        route = draft(((OPENING, GATE, 'public', 'q'), (GATE, GATE, 'public', 'p')), (1,))
        report = self._sign(route, route, ('p', 'q'))
        self.assertEqual(report.first_commands, ('q',))

    def test_sorted_starts(self):
        route = draft(((OPENING, OPENING, 'public', 'q'), (OPENING, OPENING, 'public', 'p')), (0, 1))
        report = self._sign(route, route, ('q', 'p', 'q', 'r'))
        self.assertEqual(report.first_commands, ('p', 'q'))
        self.assertEqual(report.permissions, ('p', 'q', 'r'))

    def test_empty_permissions(self):
        report = self._sign(steady(), steady(), ())
        self.assertEqual((report.permissions, report.first_commands), ((), ()))
        self.assertEqual(report.receipt.report_number, report.number)
        self.assertEqual(publication_counts(self.reports), (1, 2, 1))

    def test_reject_foreign_parent(self):
        external = CommandCatalog('external-job', CATALOG.commands)
        left, right = offline_pair(
            self.root, steady(), steady(), right_station=StationKey(external.job, BETA.station),
            right_catalog=external,
        )
        self.assertEqual(left.body.commands, right.body.commands)
        with self.assertRaisesRegex(ReportIssueError, 'same job'):
            issue_report(self.reports, left, right, {'p'})
        self.assertEqual(publication_counts(self.reports), (0, 0, 0))

    def test_reject_same_station_and_catalog_mismatch(self):
        left, right = offline_pair(
            self.root, steady(), steady(), right_catalog=CommandCatalog(CATALOG.job, ('p',)),
        )
        with self.assertRaisesRegex(ReportIssueError, 'different stations'):
            issue_report(self.reports, left, left, {'p'})
        with self.assertRaisesRegex(ReportIssueError, 'catalogs differ'):
            issue_report(self.reports, left, right, {'p'})
        self.assertEqual(publication_counts(self.reports), (0, 0, 0))

    def test_reject_damaged_parent(self):
        left, right = offline_pair(self.root, steady(), steady())
        with self.assertRaises(ReportIssueError):
            issue_report(self.reports, left, replace(right, raw='{}'), {'p'})
        self.assertEqual(publication_counts(self.reports), (0, 0, 0))

    def test_reject_unknown_command(self):
        left, right = offline_pair(self.root, steady(), steady())
        for permissions in (('z',), ('p', 'z')):
            with self.subTest(permissions=permissions), self.assertRaisesRegex(ReportIssueError, 'unknown permitted'):
                issue_report(self.reports, left, right, permissions)
            self.assertEqual(publication_counts(self.reports), (0, 0, 0))
        self.assertEqual(issue_report(self.reports, left, right, ['p']).first_commands, ('p',))
