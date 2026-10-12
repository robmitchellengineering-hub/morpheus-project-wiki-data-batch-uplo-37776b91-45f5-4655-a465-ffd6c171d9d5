"""A startup failure must be loud, and must not hang on a headless machine.

Run with:  python -m unittest discover -s tests -v

WHY THIS EXISTS. A ``--windowed`` frozen build has no console, so the old
handler — ``except Exception: _write_crash_log(); raise`` — died to "a window
that did nothing" with no user-visible reason. The replacement prints the error
to stderr, writes the crash log, shows a message box only when there is a real
display, and exits non-zero. These tests pin that wiring and the headless guard.
"""
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class DisplayDetectionTest(unittest.TestCase):
    def test_offscreen_means_headless(self):
        with mock.patch.dict(os.environ, {'QT_QPA_PLATFORM': 'offscreen'}):
            self.assertFalse(main._has_display())

    def test_macos_ci_means_headless(self):
        with mock.patch.dict(os.environ, {'CI': 'true'}, clear=False), \
             mock.patch.object(main.sys, 'platform', 'darwin'):
            self.assertFalse(main._has_display())

    def test_linux_without_display_means_headless(self):
        with mock.patch.dict(os.environ, {'DISPLAY': ''}, clear=False), \
             mock.patch.object(main.sys, 'platform', 'linux'):
            self.assertFalse(main._has_display())

    def test_a_real_desktop_has_a_display(self):
        with mock.patch.dict(os.environ, {'QT_QPA_PLATFORM': '', 'CI': '', 'DISPLAY': ':0'}, clear=False), \
             mock.patch.object(main.sys, 'platform', 'linux'):
            self.assertTrue(main._has_display())


class FatalStartupErrorTest(unittest.TestCase):
    def test_it_writes_the_log_prints_the_reason_and_exits_non_zero(self):
        stderr = io.StringIO()
        with mock.patch.object(main, '_write_crash_log', return_value='/tmp/crash_log.txt'), \
             mock.patch.object(main, '_has_display', return_value=False), \
             mock.patch.object(sys, 'stderr', stderr), \
             mock.patch.object(sys, 'exit') as fake_exit:
            main._fatal_startup_error(RuntimeError('Reference tables are missing or unreadable in /nope: boom'))
        fake_exit.assert_called_once_with(1)
        self.assertIn('could not start', stderr.getvalue())
        self.assertIn('/nope', stderr.getvalue())
        self.assertIn('crash_log.txt', stderr.getvalue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
