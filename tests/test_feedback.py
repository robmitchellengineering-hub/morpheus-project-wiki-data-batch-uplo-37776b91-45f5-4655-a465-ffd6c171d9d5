"""The user-facing sentences, as pure functions: every branch, without a display.

WHY THIS EXISTS (2026-10-01). A Morpheus AI mapping request succeeded in 21.1 s and the panel said
nothing, so the operator had to ask someone to check from the server side; when it failed it showed
raw provider text. The decisions now live in `core.feedback`, separate from the widgets, so this
suite can assert each one -- the app's tests are standard-library only and cannot build a QDialog.

The rules these tests pin:
  * a keychain that did not answer is reported as itself, never as "not connected";
  * an elapsed wait is shown as a ticking m:ss clock;
  * the fallback line is one plain sentence naming the reason, and never raw provider text;
  * every path produces a line, so the panel can never be ambiguous.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import feedback  # noqa: E402
from core.blocking_read import ANSWERED, FAILED, TIMED_OUT, ReadOutcome  # noqa: E402

ANSWERED_WITH_TOKEN = ReadOutcome(ANSWERED, 'dvc_abc')
ANSWERED_EMPTY = ReadOutcome(ANSWERED, None)
TIMED_OUT_OUTCOME = ReadOutcome(TIMED_OUT)
FAILED_OUTCOME = ReadOutcome(FAILED, None, 'RuntimeError: keyring exploded')


class KeychainTextTest(unittest.TestCase):
    """Fix 1: the read's outcome must be told apart, not flattened into "not connected"."""

    def test_connected_and_not_connected_are_shown(self):
        self.assertEqual(feedback.morpheus_connection_text(ANSWERED_WITH_TOKEN), 'Connected')
        self.assertEqual(feedback.morpheus_connection_text(ANSWERED_EMPTY), 'Not connected')

    def test_a_timeout_is_not_reported_as_not_connected(self):
        text = feedback.morpheus_connection_text(TIMED_OUT_OUTCOME)
        self.assertIn('keychain did not answer', text)
        self.assertNotEqual(text, 'Not connected')

    def test_a_read_error_is_reported_as_itself(self):
        self.assertEqual(
            feedback.morpheus_connection_text(FAILED_OUTCOME),
            'Could not read the saved connection',
        )

    def test_the_wikidata_account_line_covers_every_answer(self):
        self.assertEqual(
            feedback.wikidata_account_text(ReadOutcome(ANSWERED, {'type': 'oauth'})),
            'Saved: OAuth tokens',
        )
        self.assertEqual(
            feedback.wikidata_account_text(ReadOutcome(ANSWERED, {'username': 'Bot@Name'})),
            'Saved: Bot@Name',
        )
        self.assertEqual(
            feedback.wikidata_account_text(ReadOutcome(ANSWERED, {})), 'Not signed in')
        self.assertIn('keychain did not answer',
                      feedback.wikidata_account_text(TIMED_OUT_OUTCOME))

    def test_the_buttons_offer_connect_when_the_keychain_did_not_answer(self):
        # The operator's whole complaint was pressing Connect and getting nothing. On an
        # unreadable keychain Connect must stay available; Disconnect needs a known token.
        self.assertEqual(feedback.morpheus_button_state(ANSWERED_WITH_TOKEN), (False, True))
        self.assertEqual(feedback.morpheus_button_state(ANSWERED_EMPTY), (True, False))
        self.assertEqual(feedback.morpheus_button_state(TIMED_OUT_OUTCOME), (True, False))
        self.assertEqual(feedback.morpheus_button_state(FAILED_OUTCOME), (True, False))


class ElapsedFormattingTest(unittest.TestCase):
    """Fix 2: a long wait has to look alive -- the line ticks in m:ss."""

    def test_it_formats_zero_and_seconds(self):
        self.assertEqual(feedback.format_elapsed(0), '0:00')
        self.assertEqual(feedback.format_elapsed(7), '0:07')
        self.assertEqual(feedback.format_elapsed(21.1), '0:21')

    def test_it_rolls_over_at_a_minute(self):
        self.assertEqual(feedback.format_elapsed(59), '0:59')
        self.assertEqual(feedback.format_elapsed(60), '1:00')
        self.assertEqual(feedback.format_elapsed(61), '1:01')
        self.assertEqual(feedback.format_elapsed(125), '2:05')

    def test_it_grows_an_hour_field_only_when_needed(self):
        self.assertEqual(feedback.format_elapsed(3599), '59:59')
        self.assertEqual(feedback.format_elapsed(3600), '1:00:00')
        self.assertEqual(feedback.format_elapsed(3661), '1:01:01')

    def test_nonsense_is_treated_as_zero_rather_than_crashing(self):
        for value in (None, 'nonsense', -5):
            self.assertEqual(feedback.format_elapsed(value), '0:00')

    def test_the_busy_line_names_the_source_and_the_clock(self):
        self.assertEqual(feedback.morpheus_busy_text(7), 'Asking Morpheus… 0:07')
        self.assertEqual(feedback.morpheus_busy_text(67), 'Asking Morpheus… 1:07')
        self.assertEqual(feedback.busy_text('the AI endpoint', 0), 'Asking the AI endpoint… 0:00')

    def test_the_button_is_relabelled_while_it_runs(self):
        self.assertEqual(feedback.busy_button_text('Morpheus'), 'Asking Morpheus…')
        self.assertEqual(feedback.CHECKING_TEXT, 'Checking…')


class ClassifyMorpheusErrorTest(unittest.TestCase):
    """Every branch of the error -> reason decision, against the text the core really returns."""

    def test_nothing_said_is_an_empty_answer(self):
        for error in (None, '', '   '):
            self.assertEqual(feedback.classify_morpheus_error(error).category, feedback.EMPTY)

    def test_a_rejected_request_carries_its_http_status(self):
        error = ('Morpheus rejected the mapping request (HTTP 402). '
                 '{"error":"insufficient credits"}')
        reason = feedback.classify_morpheus_error(error)
        self.assertEqual(reason.category, feedback.REFUSED)
        self.assertEqual(reason.status, 402)

    def test_a_rejected_request_without_a_status_is_still_refused(self):
        reason = feedback.classify_morpheus_error('Morpheus rejected the mapping request.')
        self.assertEqual(reason.category, feedback.REFUSED)
        self.assertIsNone(reason.status)

    def test_an_error_body_mentioning_a_timeout_stays_a_refusal(self):
        # Order matters: the status is the more specific fact than a word in the body.
        error = 'Morpheus rejected the mapping request (HTTP 504). upstream timeout'
        reason = feedback.classify_morpheus_error(error)
        self.assertEqual(reason.category, feedback.REFUSED)
        self.assertEqual(reason.status, 504)

    def test_a_read_timeout_is_a_timeout(self):
        error = ("Could not reach Morpheus: ReadTimeout: HTTPSConnectionPool(host='api.morpheus.nz', "
                 'port=443): Read timed out. (read timeout=30)')
        self.assertEqual(feedback.classify_morpheus_error(error).category, feedback.TIMEOUT)

    def test_a_connect_timeout_is_a_timeout(self):
        error = "Could not reach Morpheus: ConnectTimeout: HTTPSConnectionPool(host='api.morpheus.nz', port=443)"
        self.assertEqual(feedback.classify_morpheus_error(error).category, feedback.TIMEOUT)

    def test_a_connection_error_is_unreachable(self):
        error = ("Could not reach Morpheus: ConnectionError: HTTPSConnectionPool(host='api.morpheus.nz', "
                 'port=443): Max retries exceeded')
        self.assertEqual(feedback.classify_morpheus_error(error).category, feedback.UNREACHABLE)

    def test_an_unexpected_shape_is_unreadable(self):
        error = 'Morpheus returned an unexpected response shape for the mapping request.'
        self.assertEqual(feedback.classify_morpheus_error(error).category, feedback.UNREADABLE)

    def test_not_connected_is_its_own_reason(self):
        error = ('Not connected to Morpheus — connect first, then ask it to map the columns.')
        self.assertEqual(feedback.classify_morpheus_error(error).category, feedback.NOT_CONNECTED)

    def test_anything_unrecognised_still_has_a_reason(self):
        self.assertEqual(feedback.classify_morpheus_error('wat').category, feedback.UNKNOWN)


class MorpheusFallbackTextTest(unittest.TestCase):
    """The sentence the operator reads when Morpheus did not map the columns."""

    def test_a_timeout_says_so(self):
        error = 'Could not reach Morpheus: ReadTimeout: Read timed out. (read timeout=30)'
        self.assertEqual(
            feedback.morpheus_fallback_text(error),
            'Morpheus did not answer in time — using local suggestions.',
        )

    def test_a_refusal_names_the_status(self):
        error = 'Morpheus rejected the mapping request (HTTP 402). insufficient credits'
        self.assertEqual(
            feedback.morpheus_fallback_text(error),
            'Morpheus refused the request (402) — using local suggestions.',
        )

    def test_a_refusal_without_a_status_still_reads(self):
        self.assertEqual(
            feedback.morpheus_fallback_text('Morpheus rejected the mapping request.'),
            'Morpheus refused the request — using local suggestions.',
        )

    def test_unreachable_and_unreadable_and_not_connected_are_distinct(self):
        self.assertEqual(
            feedback.morpheus_fallback_text('Could not reach Morpheus: ConnectionError: nope'),
            'Morpheus could not be reached — using local suggestions.',
        )
        self.assertEqual(
            feedback.morpheus_fallback_text(
                'Morpheus returned an unexpected response shape for the mapping request.'),
            'Morpheus sent a reply this app could not read — using local suggestions.',
        )
        self.assertIn(
            'Not connected to Morpheus',
            feedback.morpheus_fallback_text('Not connected to Morpheus — connect first.'),
        )

    def test_an_empty_answer_and_an_unknown_one_both_produce_a_line(self):
        self.assertEqual(
            feedback.morpheus_fallback_text(None),
            'Morpheus had no suggestions for these columns — using local suggestions.',
        )
        self.assertEqual(
            feedback.morpheus_fallback_text('something new'),
            'Morpheus could not suggest mappings — using local suggestions.',
        )

    def test_raw_provider_text_never_reaches_the_line(self):
        error = ('Morpheus rejected the mapping request (HTTP 500). '
                 'Traceback (most recent call last): File "/srv/app.js", line 1, in <module>')
        line = feedback.morpheus_fallback_text(error)
        self.assertEqual(line, 'Morpheus refused the request (500) — using local suggestions.')
        self.assertNotIn('Traceback', line)
        self.assertNotIn('/srv/app.js', line)
        self.assertNotIn('most recent call', line)

    def test_every_fallback_says_what_it_did_instead(self):
        for error in (None, 'Could not reach Morpheus: ConnectionError', 'wat',
                      'Morpheus rejected the mapping request (HTTP 500).'):
            self.assertIn('using local suggestions', feedback.morpheus_fallback_text(error).lower())


class KeychainFallbackTextTest(unittest.TestCase):
    """The fallback line when it is the keychain, not Morpheus, that failed."""

    def test_a_timeout_is_named_as_a_keychain_timeout(self):
        text = feedback.morpheus_read_failed_text(TIMED_OUT_OUTCOME)
        self.assertIn('keychain did not answer', text)
        self.assertIn('using local suggestions', text)

    def test_a_read_error_is_still_a_line(self):
        text = feedback.morpheus_read_failed_text(FAILED_OUTCOME)
        self.assertIn('Could not read the saved connection', text)
        self.assertIn('using local suggestions', text)


class VerdictTextTest(unittest.TestCase):
    """Fix 2: on success the panel names the result -- how many columns were mapped."""

    def test_it_counts_the_columns_mapped(self):
        self.assertEqual(
            feedback.apply_verdict_text('Morpheus', 6, 9), 'Morpheus mapped 6 of 9 columns.')

    def test_a_single_column_reads_naturally(self):
        self.assertEqual(feedback.apply_verdict_text('Morpheus', 1, 1), 'Morpheus mapped the column.')

    def test_a_success_with_nothing_usable_is_still_a_verdict(self):
        self.assertEqual(
            feedback.apply_verdict_text('Morpheus', 0, 9),
            'Morpheus suggested nothing this app could map.',
        )

    def test_the_source_is_named(self):
        self.assertIn('The AI endpoint', feedback.apply_verdict_text('The AI endpoint', 2, 5))


class EveryPathSaysSomethingTest(unittest.TestCase):
    """The rule the incident bought: after any path, one of these lines is shown."""

    def test_each_terminal_line_is_non_empty(self):
        lines = [
            feedback.CHECKING_CONNECTION_TEXT,
            feedback.morpheus_connection_text(TIMED_OUT_OUTCOME),
            feedback.morpheus_read_failed_text(TIMED_OUT_OUTCOME),
            feedback.morpheus_fallback_text(None),
            feedback.morpheus_fallback_text('wat'),
            feedback.MORPHEUS_FAILED_TEXT,
            feedback.NOT_CONFIGURED_TEXT,
            feedback.CUSTOM_ENDPOINT_FAILED_TEXT,
            feedback.apply_verdict_text('Morpheus', 6, 9),
            feedback.apply_verdict_text('Morpheus', 0, 9),
        ]
        for line in lines:
            self.assertTrue(line and line.strip(), 'every terminal state needs a sentence')


if __name__ == '__main__':
    unittest.main()
