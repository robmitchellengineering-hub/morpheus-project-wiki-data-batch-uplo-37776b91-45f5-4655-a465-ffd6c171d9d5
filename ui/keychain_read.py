"""Read the OS keychain off the GUI thread, and report the answer back on it.

WHY THIS EXISTS (2026-10-01). `ui/settings_dialog.py` read the saved Morpheus token on the Qt GUI
thread while building the dialog, and `ui/mapping_panel.py` did the same when asked for AI
suggestions. On macOS that read goes through Python `keyring` to `/usr/bin/security`, which raises
an authorisation prompt; while the prompt is up the GUI thread is blocked, so the window renders
half-built, clicks do nothing, and the Connect dialog that would have started the device login never
runs. The owner pressed Connect repeatedly and no request was ever created -- proved server-side, by
the absence of any row in the app's device-auth table.

The read itself is done by `core.blocking_read.attempt_read`, which gives it a deadline in a daemon
thread. It reports an outcome that distinguishes "answered that nothing is saved" from "did not
answer", so a timeout is never shown as "not connected".
"""

import threading

from PyQt6 import QtCore

from core import blocking_read


class KeychainRead(QtCore.QObject):
    """One keychain read, run in the background and delivered by signal on the GUI thread.

    A poll timer (rather than a signal emitted from the worker thread) is deliberate: if the dialog
    is closed and destroyed while a stuck read is still in flight, the timer is destroyed with it and
    nothing is emitted into a deleted object. The abandoned daemon thread simply finishes and stops.
    """

    finished_read = QtCore.pyqtSignal(object)  # blocking_read.ReadOutcome

    def __init__(self, read, seconds=blocking_read.DEFAULT_KEYCHAIN_TIMEOUT_SECONDS, parent=None):
        super().__init__(parent)
        self._outcome = None
        threading.Thread(target=self._run_read, args=(read, seconds), daemon=True).start()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    def _run_read(self, read, seconds):
        # attempt_read never raises; a plain attribute assignment from this thread is safe, and on
        # the GUI thread this is read once and cleared, so no lock is needed.
        self._outcome = blocking_read.attempt_read(read, seconds)

    def _poll(self):
        outcome = self._outcome
        if outcome is None:
            return
        self._outcome = None
        self._timer.stop()
        self.finished_read.emit(outcome)
