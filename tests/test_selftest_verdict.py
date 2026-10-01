"""--diagnose must be able to FAIL, and must say so in a line a machine can read.

WHY THIS EXISTS. `run_diagnostics` counted the modules that failed to import, wrote a report, and then
main.py called `sys.exit(0)` regardless — so the one command whose entire job is to tell you whether the app
is well always reported success. It is the same shape as the "a window that did nothing" complaint this app
started with, one layer down, and nothing could catch it because nothing looked at the exit code.

Standard library only, like the rest of this suite: it runs BEFORE PyInstaller in the build, so a diagnostic
that cannot fail cannot ship again.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.diagnostics import selftest_verdict, SELFTEST_MARKER  # noqa: E402


class SelftestVerdictTest(unittest.TestCase):
    def test_a_clean_run_exits_zero(self):
        code, line = selftest_verdict(26, 0)
        self.assertEqual(code, 0)
        self.assertTrue(line.startswith(SELFTEST_MARKER))
        self.assertIn('ok', line)
        self.assertIn('26', line)

    def test_a_failure_exits_non_zero(self):
        code, line = selftest_verdict(24, 2)
        self.assertEqual(code, 1)
        self.assertIn('fail', line)
        self.assertIn('2', line)

    def test_the_line_is_one_line(self):
        # A marker split across lines cannot be read back by a caller that reads the last line.
        for counts in ((0, 0), (26, 0), (0, 26), (1, 1)):
            self.assertEqual(len(selftest_verdict(*counts)[1].splitlines()), 1)

    def test_it_never_reports_ok_with_failures(self):
        # The one outcome this file exists to prevent, checked over a range rather than at a point.
        for failures in range(1, 6):
            code, line = selftest_verdict(26 - failures, failures)
            self.assertNotEqual(code, 0, f'{failures} failures reported as success')
            self.assertNotIn(' ok', line)

    def test_an_empty_run_is_not_a_pass(self):
        # Zero modules examined is not a clean bill of health: that is the same trap the app's own
        # verification coverage rule names, and it is reachable if the module list is ever emptied.
        code, line = selftest_verdict(0, 0)
        self.assertEqual(code, 1)
        self.assertIn('no modules were examined', line)


if __name__ == '__main__':
    unittest.main()
