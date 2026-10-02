"""Every sentence the app shows about a keychain read or an AI mapping attempt, as pure functions.

WHY THIS EXISTS (2026-10-01). The mapping panel's Morpheus call succeeded -- 21.1 seconds, 4,780
output tokens, HTTP 200 -- and the operator could not tell whether anything had happened, so he had
to ask someone to check from the server side. The panel said "Falling back to local suggestion.."
when the AI path failed and nothing at all on success. The decisions live here, apart from the
widgets, so every branch can be tested without a display -- this app's tests are standard-library
only and cannot build a QDialog.

Two rules these functions exist to enforce:

  * A keychain that did not answer is not "not connected". Those are different facts.
  * Raw provider text (an HTTP body, a stack trace) is never the user-facing line. The reason is
    classified into a sentence in the operator's language; the raw text may be logged.
"""

import re
from typing import NamedTuple, Optional

from core.blocking_read import ANSWERED, TIMED_OUT

# --- Fix 1: the saved connection, while and after it is read ------------------------------------

# The label while the read is in flight. Wording follows the rest of the dialog's controls.
CHECKING_TEXT = 'Checking…'


def morpheus_connection_text(outcome) -> str:
    """The Morpheus Connect status line for a finished keychain read."""
    if outcome.status == ANSWERED:
        return 'Connected' if outcome.value else 'Not connected'
    if outcome.status == TIMED_OUT:
        return 'Could not read the saved connection (the keychain did not answer)'
    return 'Could not read the saved connection'


def wikidata_account_text(outcome) -> str:
    """The Wikidata account status line for a finished keychain read."""
    if outcome.status == ANSWERED:
        creds = outcome.value or {}
        if creds.get('type') == 'oauth':
            return 'Saved: OAuth tokens'
        if creds.get('username'):
            return f"Saved: {creds['username']}"
        return 'Not signed in'
    if outcome.status == TIMED_OUT:
        return 'Could not read the saved account (the keychain did not answer)'
    return 'Could not read the saved account'


def morpheus_button_state(outcome):
    """(connect_enabled, disconnect_enabled) for a finished keychain read.

    On an unreadable keychain we do not know whether a connection is saved. Connect stays available:
    it is the action the operator actually came here to take, and it is what was being pressed while
    the window was frozen. Disconnect needs a known token to mean anything, so it stays off.
    """
    if outcome.status == ANSWERED:
        connected = bool(outcome.value)
        return (not connected, connected)
    return (True, False)


# --- Fix 2: the AI mapping attempt --------------------------------------------------------------

MORPHEUS = 'Morpheus'


def format_elapsed(seconds) -> str:
    """Seconds -> m:ss, or h:mm:ss past an hour. The busy line has to look alive on a long wait."""
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        total = 0
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{secs:02d}'
    return f'{minutes}:{secs:02d}'


def busy_text(what: str, elapsed_seconds) -> str:
    """The ticking line while an AI call runs -- e.g. "Asking Morpheus… 0:07"."""
    return f'Asking {what}… {format_elapsed(elapsed_seconds)}'


def morpheus_busy_text(elapsed_seconds) -> str:
    return busy_text(MORPHEUS, elapsed_seconds)


def busy_button_text(what: str) -> str:
    """The action's label while it runs -- the button is disabled and says what it is doing."""
    return f'Asking {what}…'


# "Checking your Morpheus connection…" while the saved token is read; the source is only known
# once that answers, so the first line cannot name it more precisely than Morpheus.
CHECKING_CONNECTION_TEXT = 'Checking your Morpheus connection…'

# The reason categories. Kept apart from the sentences so a test can assert the decision itself.
REFUSED = 'refused'
TIMEOUT = 'timeout'
UNREACHABLE = 'unreachable'
UNREADABLE = 'unreadable'
NOT_CONNECTED = 'not_connected'
EMPTY = 'empty'
UNKNOWN = 'unknown'

_HTTP_STATUS = re.compile(r'\(HTTP\s+(\d{3})\)')


class FallbackReason(NamedTuple):
    """What `core.morpheus_connect.MappingSuggestion.error` amounts to.

    category: one of the constants above.
    status:   the HTTP status when category is REFUSED and one could be read, else None.
    """

    category: str
    status: Optional[int] = None


def classify_morpheus_error(error) -> FallbackReason:
    """Turn the error text Morpheus already returns into one reason the panel can speak about.

    The raw text is an operator-facing diagnostic ("HTTP 402" and the body, or the exception text);
    the panel must not show it verbatim, so this picks out the fact worth saying.
    """
    text = (error or '').strip()
    if not text:
        return FallbackReason(EMPTY)
    lowered = text.lower()
    if 'not connected' in lowered:
        return FallbackReason(NOT_CONNECTED)
    # Checked before the timeout branch: an error body may mention a timeout, and the status is the
    # more specific fact.
    match = _HTTP_STATUS.search(text)
    if match:
        return FallbackReason(REFUSED, int(match.group(1)))
    if 'rejected the mapping request' in lowered:
        return FallbackReason(REFUSED)
    if 'timed out' in lowered or 'timeout' in lowered:
        return FallbackReason(TIMEOUT)
    if 'unexpected response' in lowered:
        return FallbackReason(UNREADABLE)
    if 'connection' in lowered or 'could not be reached' in lowered:
        return FallbackReason(UNREACHABLE)
    return FallbackReason(UNKNOWN)


def morpheus_fallback_text(error) -> str:
    """The sentence for the local-suggestion fallback, with the reason in the operator's words."""
    reason = classify_morpheus_error(error)
    if reason.category == TIMEOUT:
        return 'Morpheus did not answer in time — using local suggestions.'
    if reason.category == REFUSED:
        status = f' ({reason.status})' if reason.status else ''
        return f'Morpheus refused the request{status} — using local suggestions.'
    if reason.category == UNREACHABLE:
        return 'Morpheus could not be reached — using local suggestions.'
    if reason.category == UNREADABLE:
        return 'Morpheus sent a reply this app could not read — using local suggestions.'
    if reason.category == NOT_CONNECTED:
        return ('Not connected to Morpheus — connect in Settings, then try again. '
                'Using local suggestions.')
    if reason.category == EMPTY:
        return 'Morpheus had no suggestions for these columns — using local suggestions.'
    return 'Morpheus could not suggest mappings — using local suggestions.'


# The same sentence when the failure is the keychain read itself, not the call.
MORPHEUS_FAILED_TEXT = 'Morpheus could not suggest mappings — using local suggestions.'


def morpheus_read_failed_text(outcome) -> str:
    """Fallback line when the saved connection could not be read, keyed on which way it failed."""
    if outcome.status == TIMED_OUT:
        return ('Could not read the saved connection (the keychain did not answer) — '
                'using local suggestions.')
    return 'Could not read the saved connection — using local suggestions.'


# The Advanced custom-endpoint path, and the case where no AI mapping is configured at all.
NOT_CONFIGURED_TEXT = ('AI mapping is not set up — connect to Morpheus in Settings, or add an '
                       'endpoint under Advanced. Using local suggestions.')
CUSTOM_ENDPOINT_FAILED_TEXT = ('The custom AI endpoint did not answer usably — '
                               'using local suggestions.')


def apply_verdict_text(source_label: str, applied_count: int, column_count: int) -> str:
    """The success line: how much of what the operator asked for actually happened."""
    if applied_count <= 0:
        return f'{source_label} suggested nothing this app could map.'
    if column_count == 1:
        return f'{source_label} mapped the column.'
    return f'{source_label} mapped {applied_count} of {column_count} columns.'
