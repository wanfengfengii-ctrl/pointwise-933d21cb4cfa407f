"""Run this project's full unittest suite and panel acceptance from the repository root."""
import sys
import unittest


def _run_panel_checks():
    """Exercise the public V2 panel entries: fixtures, reissue, rejections, retry."""
    import tempfile
    from pathlib import Path

    from evidence.acceptance import accept_panel, accept_station
    from evidence.freeze import FreezeRejected, freeze_panel, freeze_station
    from panel_fixtures import ALPHA, ALPHA_ROUTE, CATALOG, check_v2, stage_sources
    from records.intake import accept_revision
    from records.storage import RevisionStore
    from reports.publish import ReportIssueError, issue_panel
    from reports.retrieve import MissingReport, read_panel
    from reports.storage import ReportStore

    with tempfile.TemporaryDirectory(prefix='check-panel-') as folder:
        root = Path(folder)
        check_v2(root / 'alpha.sqlite3', root / 'beta.sqlite3', root / 'panel.sqlite3')

        # Reissue returns the first registered text; a conflict is rejected.
        with RevisionStore(root / 'reissue.sqlite3') as source:
            source.initialize((CATALOG,))
            key = accept_revision(source, ALPHA, ALPHA_ROUTE)
            first = freeze_panel(source, key, ('a-p1', 'a-q1'))
            assert freeze_panel(source, key, ('a-q1', 'a-p1')) == first
            try:
                freeze_panel(source, key, ('a-p0',))
            except FreezeRejected:
                pass
            else:
                raise AssertionError('conflicting lamp declaration was accepted')

        # A failed publication leaves no new account and can be retried.
        path = root / 'retry.sqlite3'
        with ReportStore(path) as store:
            store.initialize()
            store.connection.executescript('''
                CREATE TABLE retry_targets (id INTEGER PRIMARY KEY);
                CREATE TABLE retry_requirements (
                    id INTEGER REFERENCES retry_targets(id) DEFERRABLE INITIALLY DEFERRED
                );
                CREATE TRIGGER fail_retry AFTER INSERT ON panel_publications
                BEGIN INSERT INTO retry_requirements(id) VALUES (1); END;
            ''')
            raws = stage_sources(
                root / 'ra.sqlite3', root / 'rb.sqlite3', freeze_panel
            )
            left = accept_panel(raws['alpha'], CATALOG.job, 'alpha')
            right = accept_panel(raws['beta'], CATALOG.job, 'beta')
            try:
                issue_panel(store, left, right, CATALOG.commands, 3)
            except ReportIssueError:
                pass
            else:
                raise AssertionError('a blocked publication reported success')
            count = store.connection.execute('SELECT COUNT(*) FROM panel_reports').fetchone()[0]
            assert count == 0, 'a blocked publication left a panel account'
            store.connection.execute('DROP TRIGGER fail_retry')
            retried = issue_panel(store, left, right, CATALOG.commands, 3)
            assert retried.number == 1 and retried.status == 'guaranteed'
            assert read_panel(store, 99) == MissingReport(99)

            # Rejection boundaries: bad step bounds, unknown command, same station, mixed version.
            for bad_steps in (True, 9, -1, 1.5):
                try:
                    issue_panel(store, left, right, CATALOG.commands, bad_steps)
                except ReportIssueError:
                    pass
                else:
                    raise AssertionError(f'max_steps {bad_steps!r} was accepted')
            try:
                issue_panel(store, left, right, ('z',), 3)
            except ReportIssueError:
                pass
            else:
                raise AssertionError('an unknown permission was accepted')
            try:
                issue_panel(store, left, left, CATALOG.commands, 3)
            except ReportIssueError:
                pass
            else:
                raise AssertionError('a same-station pair was accepted')
            with RevisionStore(root / 'v1.sqlite3') as source:
                source.initialize((CATALOG,))
                v1_key = accept_revision(source, ALPHA, ALPHA_ROUTE)
                v1_raw = freeze_station(source, v1_key)
            v1_parent = accept_station(v1_raw, CATALOG.job, ALPHA.station)
            try:
                issue_panel(store, v1_parent, right, CATALOG.commands, 3)
            except ReportIssueError:
                pass
            else:
                raise AssertionError('a V1 parent was accepted by issue_panel')
            count = store.connection.execute('SELECT COUNT(*) FROM panel_reports').fetchone()[0]
            assert count == 1, 'a rejected request created a panel account'


def main():
    suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
    if suite.countTestCases():
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        print('No tests discovered in tests/', file=sys.stderr)
        result = unittest.TestResult()
    panel_ok = True
    try:
        _run_panel_checks()
        print('PANEL CHECKS PASS')
    except Exception as error:  # noqa: BLE001 - report every panel check failure
        panel_ok = False
        print(f'PANEL CHECKS FAIL: {error}', file=sys.stderr)
    for status, failed_cases in (
        ('FAIL', (test for test, _ in result.failures)),
        ('ERROR', (test for test, _ in result.errors)),
        ('UNEXPECTED_SUCCESS', result.unexpectedSuccesses),
    ):
        for test in failed_cases:
            print(f'{status} {test.id()}')
    successful = result.testsRun > 0 and result.wasSuccessful() and panel_ok
    print(f'TEST SUMMARY total={result.testsRun} failures={len(result.failures)} '
          f'errors={len(result.errors)} skipped={len(result.skipped)} '
          f'expected_failures={len(result.expectedFailures)} '
          f'unexpected_successes={len(result.unexpectedSuccesses)} '
          f'panel={"PASS" if panel_ok else "FAIL"} '
          f'result={"PASS" if successful else "FAIL"}')
    return 0 if successful else 1


if __name__ == '__main__':
    raise SystemExit(main())
