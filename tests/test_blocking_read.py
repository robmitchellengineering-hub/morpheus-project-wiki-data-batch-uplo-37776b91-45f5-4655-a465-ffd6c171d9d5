"""The deadline-bounded read: the half of the keychain fix that can be tested without a display.

WHY THIS EXISTS (2026-10-01). The app read the saved Morpheus token on the Qt GUI thread, so a
macOS keychain authorisation prompt froze the window mid-build and the Connect request was never
created. The fix puts a deadline around the read; these tests pin the deadline's own behaviour --
answers fast, answers "nothing", never answers, raises -- and, crucially, that a read that never
answered is a different outcome from a read that answered nothing.

Standard-library only, like the rest of this suite, so it runs without PyQt6 installed.
"""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.blocking_read import (  # noqa: E402
    ANSWERED,
    FAILED,
    TIMED_OUT,
    attempt_read,
    read_with_timeout,
)


class ReadWithTimeoutTest(unittest.TestCase):
    """The original shape, kept for `--diagnose`."""

    def test_a_fast_answer_is_returned(self):
        answered, value = read_with_timeout(lambda: 'dvc_abc', seconds=5)
        self.assertTrue(answered)
        self.assertEqual(value, 'dvc_abc')

    def test_an_answer_of_none_is_still_an_answer(self):
        # "nothing is saved" is a fact, not a failure -- and not a timeout.
        answered, value = read_with_timeout(lambda: None, seconds=5)
        self.assertTrue(answered)
        self.assertIsNone(value)

    def test_a_read_that_never_answers_gives_up_at_the_deadline(self):
        started = time.monotonic()
        answered, value = read_with_timeout(lambda: time.sleep(60), seconds=0.2)
        elapsed = time.monotonic() - started
        self.assertFalse(answered)
        self.assertIsNone(value)
        self.assertLess(elapsed, 5, 'the deadline was not honoured')

    def test_an_error_is_raised_rather_than_swallowed(self):
        # `--diagnose` reports the exception, so this behaviour must not change.
        def boom():
            raise RuntimeError('keyring exploded')

        with self.assertRaises(RuntimeError):
            read_with_timeout(boom, seconds=5)


class AttemptReadTest(unittest.TestCase):
    """The classified, never-raising form the UI uses."""

    def test_an_answer_is_classified_answered_with_its_value(self):
        outcome = attempt_read(lambda: {'username': 'bot'}, seconds=5)
        self.assertEqual(outcome.status, ANSWERED)
        self.assertEqual(outcome.value, {'username': 'bot'})

    def test_answering_nothing_is_answered_not_timed_out(self):
        # The incident in one assertion: these two must never be the same outcome.
        outcome = attempt_read(lambda: None, seconds=5)
        self.assertEqual(outcome.status, ANSWERED)
        self.assertIsNone(outcome.value)
        self.assertNotEqual(outcome.status, TIMED_OUT)

    def test_a_read_that_never_answers_is_reported_as_timed_out(self):
        started = time.monotonic()
        outcome = attempt_read(lambda: time.sleep(60), seconds=0.2)
        self.assertEqual(outcome.status, TIMED_OUT)
        self.assertIsNone(outcome.value)
        self.assertLess(time.monotonic() - started, 5)

    def test_a_raising_read_is_reported_not_propagated(self):
        def boom():
            raise RuntimeError('keyring exploded')

        outcome = attempt_read(boom, seconds=5)
        self.assertEqual(outcome.status, FAILED)
        self.assertIsNone(outcome.value)
        self.assertIn('keyring exploded', outcome.detail)

    def test_it_never_raises_whatever_the_read_does(self):
        def boom():
            raise ValueError('nope')

        for read in (lambda: 'x', lambda: None, boom, lambda: time.sleep(60)):
            outcome = attempt_read(read, seconds=0.2)
            self.assertIn(outcome.status, (ANSWERED, TIMED_OUT, FAILED))


class DiagnosticsUsesTheSharedHelperTest(unittest.TestCase):
    """`--diagnose` keeps the same deadline and the same helper -- one implementation, not two."""

    def test_the_diagnostic_uses_the_shared_helper(self):
        from core import blocking_read, diagnostics

        self.assertIs(diagnostics.read_with_timeout, blocking_read.read_with_timeout)
        self.assertEqual(
            diagnostics.KEYCHAIN_TIMEOUT_SECONDS,
            blocking_read.DEFAULT_KEYCHAIN_TIMEOUT_SECONDS,
        )


if __name__ == '__main__':
    unittest.main()
