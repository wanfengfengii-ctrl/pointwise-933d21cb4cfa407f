import tempfile
import unittest
from pathlib import Path

from records.identity import RevisionKey, RevisionMissing, RevisionRejected, StationKey
from records.intake import accept_revision
from records.readings import RevisionDraft, WitnessRow
from records.revisions import read_revision
from records.storage import RevisionStore
from review.commands import CommandCatalog, UnknownCommand
from review.script_check import review_script
from tests.fixtures import ALPHA, BETA, CATALOG, GATE, OPENING, SPENT, draft, steady


class RevisionTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(folder) / 'records.sqlite3'
        self.source = self.enterContext(RevisionStore(self.path))
        self.source.initialize((CATALOG,))

    def test_script_review(self):
        route = draft(((OPENING, GATE, 'local', 'align'), (GATE, SPENT, 'public', 'p')), (0,))
        key = accept_revision(self.source, ALPHA, route)
        result = review_script(self.source, key, ['p'])
        self.assertEqual(result.revision, key)
        self.assertEqual(result.commands, ('p',))
        self.assertTrue(result.executable)
        self.assertEqual(result.actions, route.actions)
        self.assertEqual(tuple(match.witness for match in result.witnesses), route.witnesses)
        self.assertEqual(result.witnesses[0].action_id, route.actions[0].row_id)

    def test_branch_witness(self):
        edges = ((OPENING, GATE, 'local', 'inspect'), (OPENING, SPENT, 'public', 'p'))
        unsupported = draft(edges, (0,))
        original = accept_revision(self.source, ALPHA, unsupported)
        check = review_script(self.source, original, ('p',))
        self.assertTrue(check.executable)
        self.assertEqual(check.actions, (unsupported.actions[1],))
        self.assertEqual(check.witnesses, ())

        supported = draft((*edges, (GATE, SPENT, 'public', 'p')), (0,))
        corrected = accept_revision(self.source, ALPHA, supported, parent=original)
        check = review_script(self.source, corrected, ('p',))
        self.assertEqual(check.actions, (supported.actions[0], supported.actions[2]))
        self.assertEqual(tuple(match.witness for match in check.witnesses), supported.witnesses)

    def test_no_matching_path(self):
        route = draft(((OPENING, OPENING, 'local', 'idle'), (OPENING, SPENT, 'public', 'p')))
        key = accept_revision(self.source, ALPHA, route)
        result = review_script(self.source, key, ('p', 'p'))
        self.assertFalse(result.executable)
        self.assertEqual(result.commands, ('p', 'p'))
        self.assertEqual((result.actions, result.witnesses), ((), ()))
        empty = review_script(self.source, key, ())
        self.assertTrue(empty.executable)
        self.assertEqual(empty.actions, ())
        repeating = accept_revision(self.source, ALPHA, steady())
        self.assertEqual(len(review_script(self.source, repeating, ('p', 'p')).actions), 2)

    def test_unknown_script_command(self):
        key = accept_revision(self.source, ALPHA, steady())
        with self.assertRaises(UnknownCommand):
            review_script(self.source, key, ('p', 'z'))
        with self.assertRaises(RevisionMissing):
            review_script(self.source, RevisionKey(ALPHA, key.number + 100), ('p',))

    def test_reject_dangling_witness(self):
        original = accept_revision(self.source, ALPHA, steady())
        before = review_script(self.source, original, ('p',))
        candidate = RevisionDraft(OPENING, steady().actions, (WitnessRow('w', 'missing-row'),))
        with self.assertRaisesRegex(RevisionRejected, 'absent action'):
            accept_revision(self.source, ALPHA, candidate, parent=original)
        self.assertEqual(self.source.connection.execute('SELECT COUNT(*) FROM revisions').fetchone(), (1,))
        self.assertEqual(review_script(self.source, original, ('p',)), before)

    def test_parent_only_witness(self):
        parent_route = steady()
        original = accept_revision(self.source, ALPHA, parent_route)
        candidate = RevisionDraft(OPENING, (), parent_route.witnesses)
        with self.assertRaisesRegex(RevisionRejected, 'absent action'):
            accept_revision(self.source, ALPHA, candidate, parent=original)
        self.assertEqual(read_revision(self.source, original).draft, parent_route)
        self.assertEqual(self.source.connection.execute('SELECT COUNT(*) FROM revisions').fetchone(), (1,))

    def test_revision_chain(self):
        original = accept_revision(self.source, ALPHA, steady())
        corrected = accept_revision(self.source, ALPHA, draft(()), parent=original)
        self.assertNotEqual(original.number, corrected.number)
        self.assertEqual(read_revision(self.source, corrected).parent, original)
        self.assertIsNone(read_revision(self.source, original).parent)
        self.assertTrue(review_script(self.source, original, ['p']).executable)
        self.assertFalse(review_script(self.source, corrected, ['p']).executable)
        with self.assertRaises(RevisionRejected):
            accept_revision(self.source, BETA, steady(), parent=original)
        external = CommandCatalog('different-job', ('p',))
        self.source.initialize((external,))
        with self.assertRaises(RevisionRejected):
            accept_revision(self.source, StationKey(external.job, ALPHA.station), steady(), parent=original)
        with self.assertRaises(RevisionRejected):
            accept_revision(self.source, ALPHA, steady(), parent=RevisionKey(ALPHA, corrected.number + 5))
        self.assertEqual(self.source.connection.execute('SELECT COUNT(*) FROM revisions').fetchone(), (2,))

    def test_reopen_records(self):
        first = accept_revision(self.source, ALPHA, steady())
        second = accept_revision(self.source, ALPHA, draft(()), parent=first)
        with RevisionStore(self.path) as reopened:
            reopened.initialize()
            reopened.initialize((CommandCatalog(CATALOG.job, ('r', 'q', 'p')),))
            with self.assertRaisesRegex(RevisionRejected, 'already fixed'):
                reopened.initialize((CommandCatalog(CATALOG.job, ('p',)),))
            self.assertEqual(read_revision(reopened, second).parent, first)
            self.assertEqual(read_revision(reopened, first).draft, steady())
            self.assertEqual(reopened.catalog(CATALOG.job), CATALOG)
            self.assertEqual(reopened.connection.execute('SELECT COUNT(*) FROM revisions').fetchone(), (2,))

    def test_reject_invalid_action(self):
        for kind, label in (('public', 'z'), ('', 'inspect')):
            with self.subTest(kind=kind, label=label), self.assertRaises(RevisionRejected):
                accept_revision(self.source, ALPHA, draft(((OPENING, GATE, kind, label),)))
        self.assertEqual(self.source.connection.execute('SELECT COUNT(*) FROM revisions').fetchone(), (0,))
