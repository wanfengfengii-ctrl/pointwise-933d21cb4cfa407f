import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from evidence.acceptance import StationAcceptanceError, accept_station
from evidence.freeze import FreezeRejected, freeze_station
from records.identity import RevisionKey
from records.intake import accept_revision
from records.storage import RevisionStore
from review.script_check import review_script
from tests.fixtures import ALPHA, BETA, CATALOG, GATE, OPENING, SPENT, bypass, offline_parent, steady


def _seal_envelope(envelope):
    body = json.dumps(envelope['body'], ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    fields = [envelope['version'], envelope['job'], envelope['station'], envelope['revision'], body]
    identity = json.dumps(fields, ensure_ascii=True, separators=(',', ':'))
    envelope['digest'] = hashlib.sha256(identity.encode('ascii')).hexdigest()
    return json.dumps(envelope)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_freeze_and_accept(self):
        path = self.root / 'alpha.sqlite3'
        with RevisionStore(path) as source:
            source.initialize((CATALOG,))
            first = accept_revision(source, ALPHA, bypass(False))
            check = review_script(source, first, ['p'])
            self.assertTrue(check.executable)
            self.assertEqual([match.action_id for match in check.witnesses], ['raw-action-2'])
            raw = freeze_station(source, first)
            accept_revision(source, ALPHA, bypass(True), parent=first)
        parent = accept_station(raw, ALPHA.job, ALPHA.station)
        self.assertEqual(parent.identity.revision, first.number)
        self.assertEqual(parent.body.commands, CATALOG.commands)
        self.assertEqual(parent.raw, raw)
        for private in (OPENING, GATE, SPENT, 'private-inspection', 'raw-action-', 'raw-reading-', 'raw-witness-'):
            self.assertNotIn(private, raw)
        with RevisionStore(path) as reopened:
            reopened.initialize()
            self.assertEqual(freeze_station(reopened, first), raw)
            row = reopened.connection.execute('SELECT revision, artifact FROM station_issues').fetchall()
            self.assertEqual(row, [(first.number, raw)])

    def test_explicit_revision(self):
        with RevisionStore(self.root / 'alpha.sqlite3') as source:
            source.initialize((CATALOG,))
            first = accept_revision(source, ALPHA, bypass(False))
            corrected = accept_revision(source, ALPHA, bypass(True), parent=first)
            old_raw = freeze_station(source, first)
            new_raw = freeze_station(source, corrected)
        old = accept_station(old_raw, ALPHA.job, ALPHA.station)
        new = accept_station(new_raw, ALPHA.job, ALPHA.station)
        self.assertEqual((old.identity.revision, new.identity.revision), (first.number, corrected.number))
        self.assertNotEqual(old.identity.digest, new.identity.digest)

    def test_invalid_revision(self):
        with RevisionStore(self.root / 'alpha.sqlite3') as source:
            source.initialize((CATALOG,))
            key = accept_revision(source, ALPHA, steady())
            for invalid in (RevisionKey(BETA, key.number), RevisionKey(ALPHA, key.number + 1)):
                with self.subTest(key=invalid), self.assertRaises(FreezeRejected):
                    freeze_station(source, invalid)
            self.assertEqual(source.connection.execute('SELECT COUNT(*) FROM station_issues').fetchone(), (0,))

    def test_corrupt_payload(self):
        parent = offline_parent(self.root / 'alpha.sqlite3', ALPHA, CATALOG, steady())
        corrupt = json.loads(parent.raw)
        corrupt['body']['steps'][0]['witness'] = False
        with self.assertRaisesRegex(StationAcceptanceError, 'digest mismatch'):
            accept_station(json.dumps(corrupt), ALPHA.job, ALPHA.station)
        bad_reference = json.loads(parent.raw)
        bad_reference['body']['steps'][0]['to'] = bad_reference['body']['state_count']
        with self.assertRaisesRegex(StationAcceptanceError, 'state outside'):
            accept_station(_seal_envelope(bad_reference), ALPHA.job, ALPHA.station)
        with self.assertRaisesRegex(StationAcceptanceError, 'duplicate'):
            accept_station(parent.raw[:-1] + ',"version":1}', ALPHA.job, ALPHA.station)
        wrong_version = json.loads(parent.raw)
        wrong_version['version'] = True
        with self.assertRaisesRegex(StationAcceptanceError, 'version'):
            accept_station(json.dumps(wrong_version), ALPHA.job, ALPHA.station)

    def test_wrong_scope(self):
        parent = offline_parent(self.root / 'alpha.sqlite3', ALPHA, CATALOG, steady())
        with self.assertRaisesRegex(StationAcceptanceError, 'another job'):
            accept_station(parent.raw, 'other-job', ALPHA.station)
        with self.assertRaisesRegex(StationAcceptanceError, 'another station'):
            accept_station(parent.raw, ALPHA.job, BETA.station)
