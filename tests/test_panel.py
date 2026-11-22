import json
import tempfile
import unittest
from pathlib import Path

from evidence.acceptance import StationAcceptanceError, accept_panel, accept_station
from evidence.freeze import freeze_panel, freeze_station
from panel_fixtures import ALPHA, ALPHA_ROUTE, CATALOG, stage_sources
from records.intake import accept_revision
from records.storage import RevisionStore
from reports.publish import issue_panel
from reports.retrieve import MissingReport, read_panel
from reports.storage import ReportStore


class PanelFixtureMixin:
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.raws = stage_sources(
            self.root / 'alpha.sqlite3', self.root / 'beta.sqlite3', freeze_panel
        )
        self.report_path = self.root / 'panel.sqlite3'
        self.reports = self.enterContext(ReportStore(self.report_path))
        self.reports.initialize()

    def parent(self, name):
        station = 'alpha' if name in ('alpha', 'alpha_flat', 'witness_left') else 'beta'
        return accept_panel(self.raws[name], CATALOG.job, station)

    def counts(self):
        connection = self.reports.connection
        return (
            connection.execute('SELECT COUNT(*) FROM panel_reports').fetchone()[0],
            connection.execute('SELECT COUNT(*) FROM panel_report_parents').fetchone()[0],
            connection.execute('SELECT COUNT(*) FROM panel_publications').fetchone()[0],
        )


def final_commands(strategy):
    """Map each observable lamp history to the last command issued on it."""
    found = {}

    def walk(node, lamps):
        for lamp, child in node['next'].items():
            history = lamps + (int(lamp),)
            if 'stop' in child:
                found[history] = node['command']
            else:
                walk(child, history)

    walk(strategy, ())
    return found


class PanelArtifactTests(PanelFixtureMixin, unittest.TestCase):
    def test_body_is_anonymous_and_joint(self):
        raw = self.raws['alpha']
        for private in ('private-opening', 'private-before-0', 'a-p1', 'reading-a-p1',
                        'witness-a-p1', 'private-preparation'):
            self.assertNotIn(private, raw)
        wire = json.loads(raw)
        self.assertEqual(wire['version'], 2)
        body = wire['body']
        self.assertEqual(tuple(body['commands']), CATALOG.commands)
        opening = body['opening']
        p_outcomes = next(
            move['outcomes'] for move in body['moves']
            if move['state'] == opening and move['command'] == 'p'
        )
        # p lands in either anonymous state; only the 1-road lights this station.
        self.assertEqual({item['lit'] for item in p_outcomes}, {False, True})
        self.assertEqual(len({item['to'] for item in p_outcomes}), 2)
        self.assertTrue(all(not item['witness'] for item in p_outcomes))

    def test_reissue_and_conflict(self):
        path = self.root / 'reissue.sqlite3'
        with RevisionStore(path) as source:
            source.initialize((CATALOG,))
            key = accept_revision(source, ALPHA, ALPHA_ROUTE)
            one = freeze_panel(source, key, ('a-p1', 'a-q1'))
            again = freeze_panel(source, key, ['a-q1', 'a-p1', 'a-p1'])
            self.assertEqual(one, again)
            for bad in (('a-p0',), ('missing',), (1,)):
                with self.subTest(bad=bad), self.assertRaises(Exception):
                    freeze_panel(source, key, bad)
            with self.subTest(bad='a-p1'), self.assertRaises(Exception):
                freeze_panel(source, key, 'a-p1')
            # A conflicting declaration must not overwrite the registered text.
            with self.assertRaisesRegex(Exception, 'different lamp declaration'):
                freeze_panel(source, key, ('a-p0',))
            self.assertEqual(freeze_panel(source, key, ('a-q1', 'a-p1')), one)

    def test_empty_declaration_and_version_isolation(self):
        self.assertEqual(json.loads(self.raws['witness_left'])['version'], 2)
        with self.assertRaises(StationAcceptanceError):
            accept_station(self.raws['alpha'], CATALOG.job, 'alpha')
        v1_like = json.loads(self.raws['alpha'])
        v1_like['version'] = 1
        with self.assertRaisesRegex(StationAcceptanceError, 'version'):
            accept_panel(json.dumps(v1_like), CATALOG.job, 'alpha')
        with self.assertRaisesRegex(StationAcceptanceError, 'another job'):
            accept_panel(self.raws['alpha'], 'other-job', 'alpha')
        with self.assertRaisesRegex(StationAcceptanceError, 'another station'):
            accept_panel(self.raws['alpha'], CATALOG.job, 'beta')

    def test_corrupt_panel(self):
        wire = json.loads(self.raws['alpha'])
        wire['body']['moves'][0]['outcomes'][0]['lit'] = (
            not wire['body']['moves'][0]['outcomes'][0]['lit']
        )
        with self.assertRaisesRegex(StationAcceptanceError, 'digest mismatch'):
            accept_panel(json.dumps(wire), CATALOG.job, 'alpha')
        duplicate = self.raws['alpha'][:-1] + ',"version":2}'
        with self.assertRaisesRegex(StationAcceptanceError, 'duplicate'):
            accept_panel(duplicate, CATALOG.job, 'alpha')
        bad = json.loads(self.raws['alpha'])
        bad['body']['moves'][0]['outcomes'][0]['to'] = bad['body']['state_count']
        with self.assertRaisesRegex(StationAcceptanceError, 'outside the body'):
            accept_panel(json.dumps(bad), CATALOG.job, 'alpha')
        bad = json.loads(self.raws['alpha'])
        bad['body']['moves'].append(dict(bad['body']['moves'][0]))
        with self.assertRaisesRegex(StationAcceptanceError, 'duplicate panel move'):
            accept_panel(json.dumps(bad), CATALOG.job, 'alpha')


class PanelQualificationTests(PanelFixtureMixin, unittest.TestCase):
    def test_original_beta_lamp_correction(self):
        left = self.parent('alpha')
        original = issue_panel(self.reports, left, self.parent('beta'), CATALOG.commands, 3)
        corrected = issue_panel(
            self.reports, left, self.parent('beta_reversed'), CATALOG.commands, 3
        )
        self.assertEqual(
            final_commands(original.strategy), {(0, 0, 0): 's', (1, 0, 0): 'r', (1, 1, 0): 't'}
        )
        self.assertEqual(
            final_commands(corrected.strategy), {(0, 0, 0): 'r', (1, 0, 0): 's', (1, 1, 0): 't'}
        )
        # Same lamp history, same first two commands, different final step.
        self.assertEqual(original.strategy['command'], corrected.strategy['command'])
        self.assertEqual(original.strategy['next'].keys(), corrected.strategy['next'].keys())

    def test_two_steps_are_impossible(self):
        left = self.parent('alpha')
        for right in (self.parent('beta'), self.parent('beta_reversed')):
            report = issue_panel(self.reports, left, right, CATALOG.commands, 2)
            self.assertEqual((report.status, report.strategy), ('impossible', None))

    def test_flat_alpha_impossible(self):
        report = issue_panel(
            self.reports, self.parent('alpha_flat'), self.parent('beta'), CATALOG.commands, 3
        )
        self.assertEqual((report.status, report.strategy), ('impossible', None))

    def test_unobservable_witness_route(self):
        report = issue_panel(
            self.reports, self.parent('witness_left'), self.parent('witness_right'), ('p',), 1
        )
        self.assertEqual((report.status, report.strategy), ('impossible', None))

    def test_bounds_and_rejections(self):
        left, right = self.parent('alpha'), self.parent('beta')
        for bad in (True, False, -1, 9, 1.0, '3', None):
            with self.subTest(max_steps=bad), self.assertRaisesRegex(Exception, 'max_steps'):
                issue_panel(self.reports, left, right, CATALOG.commands, bad)
        with self.assertRaisesRegex(Exception, 'unknown permitted'):
            issue_panel(self.reports, left, right, ('z',), 3)
        with self.assertRaisesRegex(Exception, 'different stations'):
            issue_panel(self.reports, left, left, CATALOG.commands, 3)
        with self.assertRaisesRegex(Exception, 'panel parent'):
            issue_panel(self.reports, self._v1_station(), right, CATALOG.commands, 3)
        self.assertEqual(self.counts(), (0, 0, 0))

    def _v1_station(self):
        path = self.root / 'v1.sqlite3'
        with RevisionStore(path) as source:
            source.initialize((CATALOG,))
            key = accept_revision(source, ALPHA, ALPHA_ROUTE)
            raw = freeze_station(source, key)
        return accept_station(raw, CATALOG.job, 'alpha')

    def test_zero_steps_and_empty_permissions(self):
        left, right = self.parent('alpha'), self.parent('beta')
        zero = issue_panel(self.reports, left, right, CATALOG.commands, 0)
        self.assertEqual((zero.status, zero.strategy), ('impossible', None))
        empty = issue_panel(self.reports, left, right, (), 5)
        self.assertEqual((empty.permissions, empty.status, empty.strategy), ((), 'impossible', None))


class PanelReportTests(PanelFixtureMixin, unittest.TestCase):
    def test_retrieve_after_reopen(self):
        left, right = self.parent('alpha'), self.parent('beta')
        with ReportStore(self.report_path) as store:
            store.initialize()
            old = issue_panel(store, left, right, CATALOG.commands, 2)
            new = issue_panel(store, left, self.parent('beta_reversed'), CATALOG.commands, 3)
        with ReportStore(self.report_path) as reopened:
            reopened.initialize()
            self.assertEqual(read_panel(reopened, old.number), old)
            self.assertEqual(read_panel(reopened, new.number), new)
            self.assertEqual(read_panel(reopened, new.number + 50), MissingReport(new.number + 50))
            self.assertEqual((old.status, old.strategy), ('impossible', None))
            self.assertEqual(new.status, 'guaranteed')
            self.assertEqual(old.stations, ('alpha', 'beta'))
            self.assertEqual(old.parents, (self.raws['alpha'], self.raws['beta']))
            self.assertEqual(old.receipt.report_number, old.number)
            self.assertEqual(old.receipt.event, 'issued')

    def test_atomic_failure_and_retry(self):
        left, right = self.parent('alpha'), self.parent('beta')
        self.reports.connection.executescript('''
            CREATE TABLE panel_commit_targets (id INTEGER PRIMARY KEY);
            CREATE TABLE panel_commit_requirements (
                id INTEGER REFERENCES panel_commit_targets(id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER fail_panel_commit AFTER INSERT ON panel_publications
            BEGIN
                INSERT INTO panel_commit_requirements(id) VALUES (1);
            END;
        ''')
        with self.assertRaisesRegex(Exception, 'FOREIGN KEY'):
            issue_panel(self.reports, left, right, CATALOG.commands, 3)
        self.assertFalse(self.reports.connection.in_transaction)
        self.assertEqual(self.counts(), (0, 0, 0))
        self.reports.connection.execute('DROP TRIGGER fail_panel_commit')
        retried = issue_panel(self.reports, left, right, CATALOG.commands, 3)
        self.assertEqual((retried.number, retried.status), (1, 'guaranteed'))
        self.assertEqual(self.counts(), (1, 2, 1))
