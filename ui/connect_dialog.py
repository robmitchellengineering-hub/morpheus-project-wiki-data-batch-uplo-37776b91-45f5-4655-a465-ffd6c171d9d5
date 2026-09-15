"""Connect-to-Morpheus dialog — the device-flow login UI.

Mirrors ui/auth_dialog.py's structure (a modal QDialog, credentials handled
by a worker thread). Shows the operator a short code, lets them open
morpheus.nz/connect in one click, and polls in the background until they
approve (or deny/it expires) on their own device.
"""
import time
import webbrowser

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import QThread, pyqtSignal

from core.morpheus_connect import start_device_flow, poll_device_flow


class MorpheusConnectWorker(QThread):
    """Background poller for a pending device request. Same
    pyqtSignal-per-outcome style as core/workers.py's DryRunWorker/
    UploadWorker."""
    approved = pyqtSignal(str)  # token
    denied = pyqtSignal()
    expired = pyqtSignal()

    def __init__(self, device_code, interval_seconds, expires_in_seconds, parent=None):
        super().__init__(parent)
        self.device_code = device_code
        self.interval_seconds = max(1, int(interval_seconds or 5))
        self.expires_in_seconds = max(1, int(expires_in_seconds or 600))
        self._stop = False

    def stop(self):
        """Ask the poll loop to exit before its next wait — checked once
        per interval, so this stops within one interval, not instantly."""
        self._stop = True

    def run(self):
        deadline = time.monotonic() + self.expires_in_seconds
        while not self._stop and time.monotonic() < deadline:
            time.sleep(self.interval_seconds)
            if self._stop:
                return
            result = poll_device_flow(self.device_code)
            status = result.get("status")
            if status == "approved":
                self.approved.emit(result.get("token", ""))
                return
            if status == "denied":
                self.denied.emit()
                return
            if status == "expired":
                self.expired.emit()
                return
            # "pending" or a transient "error" from poll_device_flow itself
            # (e.g. a dropped connection) -- keep polling until the deadline.
        if not self._stop:
            self.expired.emit()


class ConnectDialog(QtWidgets.QDialog):
    """Dialog for connecting this app to the operator's own Morpheus
    account via device-flow login. On success, self.token holds the
    dvc_... device token -- the caller is responsible for saving it (see
    ui/settings_dialog.py)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Morpheus")
        self.setModal(True)
        self.resize(420, 240)
        self.token = None
        self._worker = None
        self._verification_uri_complete = None
        self._create_ui()
        self._start()

    def _create_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        self.status_label = QtWidgets.QLabel("Starting...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.code_label = QtWidgets.QLabel("")
        self.code_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        code_font = self.code_label.font()
        code_font.setPointSize(20)
        code_font.setBold(True)
        self.code_label.setFont(code_font)
        self.code_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.code_label)

        self.open_browser_button = QtWidgets.QPushButton("Open morpheus.nz/connect")
        self.open_browser_button.clicked.connect(self._open_browser)
        self.open_browser_button.setEnabled(False)
        layout.addWidget(self.open_browser_button)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _start(self):
        data = start_device_flow()
        if not data:
            self.status_label.setText(
                "Could not reach Morpheus. Check your internet connection, then close this and try again."
            )
            return

        self._verification_uri_complete = data.get("verification_uri_complete") or "https://morpheus.nz/connect"
        self.code_label.setText(data.get("user_code", ""))
        self.status_label.setText(
            "Enter this code at morpheus.nz/connect, or click below to open it directly. "
            "This window will close automatically once you approve it."
        )
        self.open_browser_button.setEnabled(True)

        self._worker = MorpheusConnectWorker(
            data["device_code"], data.get("interval", 5), data.get("expires_in", 600), self
        )
        self._worker.approved.connect(self._on_approved)
        self._worker.denied.connect(self._on_denied)
        self._worker.expired.connect(self._on_expired)
        self._worker.start()

    def _open_browser(self):
        if self._verification_uri_complete:
            webbrowser.open(self._verification_uri_complete)

    def _on_approved(self, token):
        self.token = token
        self.status_label.setText("Connected!")
        self.open_browser_button.setEnabled(False)
        QtCore.QTimer.singleShot(600, self.accept)

    def _on_denied(self):
        self.status_label.setText("Connection request denied. Close this and try again if that wasn't you.")
        self.open_browser_button.setEnabled(False)

    def _on_expired(self):
        self.status_label.setText("Code expired. Close this and try again.")
        self.open_browser_button.setEnabled(False)

    def reject(self):
        self._stop_worker()
        super().reject()

    def closeEvent(self, event):
        self._stop_worker()
        super().closeEvent(event)

    def _stop_worker(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(200)
