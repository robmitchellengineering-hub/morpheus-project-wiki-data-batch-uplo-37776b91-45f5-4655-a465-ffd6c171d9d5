"""`--diagnose` has to actually report a verdict, and that is a WIRING claim.

WHY THIS EXISTS (2026-10-01). `tests/test_selftest_verdict.py` tests `selftest_verdict` — a pure function
that returns `(exit_code, marker_line)`. It was correct, and it passed, while `--diagnose` printed nothing
and exited 0 whatever it found. The print-and-return that carried the verdict sat at the very bottom of
`core/diagnostics.py` AFTER a `return`, unreachable, and `run_diagnostics` never called the pure function at
all. `main.py` then fell through into the GUI, so `--diagnose` on a broken build opened a window.

A test of the pure function could not see any of that, which is the whole lesson: **the half that breaks is
the wiring.** So these tests drive the real entry points and assert what a caller actually reads — the
printed marker line and the exit code, together — rather than the helper's return value.

Standard-library only, like every other test here, so it runs without PyQt6 installed.
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core import diagnostics  # noqa: E402
from core.diagnostics import SELFTEST_MARKER, selftest_verdict  # noqa: E402


class RunDiagnosticsWiringTest(unittest.TestCase):
    """`run_diagnostics` prints the marker and returns the code — in every outcome."""

    def _run_with(self, results):
        """Run the real function with only the import sweep replaced."""
        original = diagnostics._run_import_tests
        diagnostics._run_import_tests = lambda: results
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = diagnostics.run_diagnostics(tempfile.mkdtemp())
            return code, out.getvalue()
        finally:
            diagnostics._run_import_tests = original

    def test_everything_loading_reports_ok_and_exits_zero(self):
        code, printed = self._run_with({'core.uploader': 'OK', 'ui.main_window': 'OK'})
        self.assertEqual(code, 0)
        self.assertIn(SELFTEST_MARKER, printed)
        self.assertIn('ok', printed)

    def test_a_failed_import_reports_a_failure_and_exits_non_zero(self):
        code, printed = self._run_with({'core.uploader': 'OK', 'ui.main_window': 'ImportError: no Qt'})
        self.assertEqual(code, 1)
        self.assertIn(SELFTEST_MARKER, printed)
        self.assertIn('fail', printed)
        self.assertIn('1 module', printed)

    def test_examining_nothing_is_a_failure_rather_than_a_clean_bill(self):
        code, printed = self._run_with({})
        self.assertEqual(code, 1)
        self.assertIn('no modules were examined', printed)

    def test_the_printed_line_is_the_one_the_pure_function_says(self):
        # The two halves are only useful together, so they are asserted together.
        for results in ({'a': 'OK'}, {'a': 'boom'}, {}):
            code, printed = self._run_with(results)
            expected_code, expected_line = selftest_verdict(
                sum(1 for v in results.values() if v == 'OK'),
                sum(1 for v in results.values() if v != 'OK'),
            )
            self.assertEqual(code, expected_code)
            self.assertIn(expected_line, printed)

    def test_something_is_always_printed(self):
        # The regression itself: the old code returned before printing, so this was empty.
        for results in ({'a': 'OK'}, {'a': 'boom'}, {}):
            _, printed = self._run_with(results)
            self.assertTrue(printed.strip(), 'the verdict line must always be printed')


class DiagnoseCommandTest(unittest.TestCase):
    """The command an operator or an installer actually runs."""

    def test_python_main_diagnose_reports_and_exits(self):
        report = REPO / 'diagnostic_report.txt'
        existed = report.exists()
        proc = subprocess.run(
            [sys.executable, str(REPO / 'main.py'), '--diagnose'],
            cwd=str(REPO), capture_output=True, text=True, timeout=600,
        )
        try:
            marker_lines = [l for l in proc.stdout.splitlines() if SELFTEST_MARKER in l]
            self.assertEqual(len(marker_lines), 1,
                             f'expected exactly one verdict line, got {marker_lines!r}\n'
                             f'stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}')
            line = marker_lines[0]
            # The code and the sentence must agree — a caller reads the sentence, a script reads the code,
            # and it is the pair that has to be true.
            self.assertEqual('ok' in line, proc.returncode == 0,
                             f'"{line}" disagrees with exit code {proc.returncode}')
            self.assertIn(proc.returncode, (0, 1))
            # The report is the detail; the marker is the verdict. Both, or the run is not finished.
            self.assertTrue(report.exists(), 'the diagnostic report was not written')
        finally:
            if report.exists() and not existed:
                os.remove(report)


class TheSelfTestCannotHangTest(unittest.TestCase):
    """A diagnostic that can hang is not a diagnostic.

    MEASURED 2026-10-01, running the app from a source checkout: `python main.py --diagnose` never finished
    and never printed a verdict — it blocked inside `_get_ai_config_snapshot` on a macOS Keychain read. The
    report was never written and the verdict was never reached, so the failure looked exactly like "the app
    did nothing". These two tests are that run, reduced.
    """

    def setUp(self):
        from core import credential_storage
        self.credential_storage = credential_storage
        self.original = credential_storage.load_morpheus_token

    def tearDown(self):
        self.credential_storage.load_morpheus_token = self.original

    def test_a_keychain_read_that_never_answers_gives_up_and_says_so(self):
        import time
        self.credential_storage.load_morpheus_token = lambda: time.sleep(300)
        started = time.time()
        snapshot = diagnostics._get_ai_config_snapshot()
        elapsed = time.time() - started
        self.assertLess(elapsed, diagnostics.KEYCHAIN_TIMEOUT_SECONDS + 5,
                        'the snapshot must not wait on the keychain')
        self.assertIn('unknown', str(snapshot.get('morpheus_connect', '')))

    def test_the_verdict_is_still_printed_and_returned_when_the_keychain_is_stuck(self):
        self.credential_storage.load_morpheus_token = lambda: __import__('time').sleep(300)
        original = diagnostics._run_import_tests
        diagnostics._run_import_tests = lambda: {'core.uploader': 'OK'}
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = diagnostics.run_diagnostics(tempfile.mkdtemp())
        finally:
            diagnostics._run_import_tests = original
        self.assertEqual(code, 0)
        self.assertIn(SELFTEST_MARKER, out.getvalue())


if __name__ == '__main__':
    unittest.main()
