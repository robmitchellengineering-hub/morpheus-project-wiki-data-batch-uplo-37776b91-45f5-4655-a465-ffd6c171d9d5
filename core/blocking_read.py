"""Read something that can block -- the OS keychain above all -- without blocking the caller.

WHY THIS EXISTS (2026-10-01). The app read the saved Morpheus token synchronously, on the Qt GUI
thread, while the Settings dialog was being built (`ui/settings_dialog.py`) and again when the
mapping panel asked for AI suggestions (`ui/mapping_panel.py`). On macOS that read goes through
Python `keyring` to `/usr/bin/security`, which raises an authorisation prompt; while the prompt is
up the GUI thread is blocked, so the window renders half-built, clicks do nothing, and the Connect
dialog that would have started the device login never runs. The owner pressed Connect repeatedly
and no request was ever created -- proved server-side, by the absence of any row in the app's
device-auth table.

`core/diagnostics.py` already solved this for `--diagnose` -- "A KEYCHAIN READ CAN BLOCK FOREVER,
AND THE SELF-TEST MUST NOT" -- but the two UI call sites never got it. The helper lives here now so
there is one implementation, and so `core/diagnostics.py` can keep using it without importing Qt.

`read_with_timeout` keeps the original `(answered, value)` shape and its raise-on-error behaviour,
so `--diagnose` behaves exactly as it did. `attempt_read` is the never-raising form the UI wants:
it turns the same call into an outcome that tells "answered that nothing is saved" apart from "did
not answer", which are different facts and must never be shown as the same sentence.
"""

import threading
from typing import Callable, NamedTuple, Tuple

# A KEYCHAIN READ CAN BLOCK FOREVER, AND THE SELF-TEST MUST NOT.
#
# MEASURED 2026-10-01, running the app from a source checkout: `python main.py --diagnose` never
# finished and never printed a verdict -- it blocked inside `_get_ai_config_snapshot` on
# `credential_storage.load_morpheus_token()`. That reads the macOS Keychain, and when the item needs
# authorising from a process macOS has not seen before, the read blocks on a system prompt that never
# appears for a command-line run. The report was never written and the verdict was never reached, so
# the failure looked like "the app did nothing".
#
# A read that can hang is not a read. The read gets a deadline in a daemon thread; if the keychain
# does not answer, the caller is told so and continues. A daemon thread cannot hold the process open,
# so a stuck read costs the timeout and nothing else.
DEFAULT_KEYCHAIN_TIMEOUT_SECONDS = 5

# The three things a deadline-bounded read can do. ANSWERED covers both a value and None: a keychain
# that answers "nothing is saved" is a fact, not a failure -- and it is a different fact from
# TIMED_OUT, which is why they are separate statuses rather than one falsy value.
ANSWERED = 'answered'
TIMED_OUT = 'timed_out'
FAILED = 'failed'


class ReadOutcome(NamedTuple):
    """What one deadline-bounded read produced.

    status: one of ANSWERED / TIMED_OUT / FAILED.
    value:  the read's return value when status is ANSWERED, else None.
    detail: the exception text when status is FAILED (for the log, never shown raw), else ''.
    """

    status: str
    value: object = None
    detail: str = ''


def read_with_timeout(read: Callable, seconds: float = DEFAULT_KEYCHAIN_TIMEOUT_SECONDS) -> Tuple[bool, object]:
    """Run `read()` in a daemon thread. Returns (answered, value); never blocks longer than `seconds`.

    Raises whatever `read()` raised, if it answered with an exception -- the caller's own `except`
    turns that into a report line.
    """
    box = {}

    def run():
        try:
            box['value'] = read()
        except Exception as exc:  # re-raised below, on the caller's thread
            box['error'] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        return False, None
    if 'error' in box:
        raise box['error']
    return True, box.get('value')


def attempt_read(read: Callable, seconds: float = DEFAULT_KEYCHAIN_TIMEOUT_SECONDS) -> ReadOutcome:
    """`read_with_timeout`, classified and never raising: the form the UI needs.

    A timeout and an answered `None` are deliberately different statuses. The incident this module
    exists for was a dialog that reported "not connected" for a read that never happened.
    """
    try:
        answered, value = read_with_timeout(read, seconds)
    except Exception as exc:
        return ReadOutcome(FAILED, None, f'{type(exc).__name__}: {exc}')
    if not answered:
        return ReadOutcome(TIMED_OUT)
    return ReadOutcome(ANSWERED, value)
