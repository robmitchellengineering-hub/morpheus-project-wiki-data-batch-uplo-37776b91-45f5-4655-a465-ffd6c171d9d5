from PyQt6 import QtCore, QtWidgets
from core import blocking_read
from core import feedback
from core import settings as app_settings
from core import credential_storage
from ui.connect_dialog import ConnectDialog
from ui.auth_dialog import AuthDialog
from ui.keychain_read import KeychainRead


class SettingsDialog(QtWidgets.QDialog):
    """Dialog for configuring user preferences stored via QSettings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(520, 540)
        self._create_ui()
        self._load_settings()

    def _create_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()

        self.edit_summary_edit = QtWidgets.QLineEdit()
        self.edit_summary_edit.setPlaceholderText("Default edit summary for uploads")
        form.addRow("Default edit summary:", self.edit_summary_edit)

        self.delay_spin = QtWidgets.QDoubleSpinBox()
        self.delay_spin.setRange(0, 60)
        self.delay_spin.setDecimals(1)
        self.delay_spin.setSingleStep(0.5)
        self.delay_spin.setSuffix(" seconds")
        form.addRow("Upload delay between rows:", self.delay_spin)

        self.maxlag_spin = QtWidgets.QDoubleSpinBox()
        self.maxlag_spin.setRange(0, 60)
        self.maxlag_spin.setDecimals(1)
        self.maxlag_spin.setSingleStep(0.5)
        self.maxlag_spin.setSuffix(" seconds")
        form.addRow("Maxlag:", self.maxlag_spin)

        layout.addLayout(form)

        # --- Morpheus Connect: the primary AI mapping path -----------------
        connect_group = QtWidgets.QGroupBox("AI Mapping — Morpheus Connect")
        connect_layout = QtWidgets.QVBoxLayout(connect_group)
        connect_hint = QtWidgets.QLabel(
            "Connect your own Morpheus account so AI column-mapping suggestions "
            "run on your own credits — no shared key, no configuration."
        )
        connect_hint.setWordWrap(True)
        connect_layout.addWidget(connect_hint)

        status_row = QtWidgets.QHBoxLayout()
        self.morpheus_status_label = QtWidgets.QLabel("Not connected")
        status_row.addWidget(self.morpheus_status_label)
        status_row.addStretch()
        self.morpheus_connect_button = QtWidgets.QPushButton("Connect...")
        self.morpheus_connect_button.clicked.connect(self._on_connect_clicked)
        status_row.addWidget(self.morpheus_connect_button)
        self.morpheus_disconnect_button = QtWidgets.QPushButton("Disconnect")
        self.morpheus_disconnect_button.clicked.connect(self._on_disconnect_clicked)
        status_row.addWidget(self.morpheus_disconnect_button)
        connect_layout.addLayout(status_row)

        layout.addWidget(connect_group)

        # --- Wikidata account ----------------------------------------------
        # 2026-10-01 (Rob: "where are the setting to connect it to wiki?"). There wasn't one. The
        # login existed but was reachable ONLY from the Upload button on the mapping panel, so it
        # could not be set up or tested until you already had data loaded and a column mapped -- and
        # Settings, the natural place to look, did not mention Wikidata at all. Same dialog, same
        # storage; the account is just reachable from where people look for it now.
        wikidata_group = QtWidgets.QGroupBox("Wikidata account")
        wikidata_layout = QtWidgets.QVBoxLayout(wikidata_group)
        wikidata_hint = QtWidgets.QLabel(
            "The account your edits are made with. This app takes a BOT password, not your normal "
            "login: create one at wikidata.org/wiki/Special:BotPasswords and give it "
            "\"Create, edit, and move pages\" plus \"Edit existing pages\"."
        )
        wikidata_hint.setWordWrap(True)
        wikidata_layout.addWidget(wikidata_hint)

        wikidata_row = QtWidgets.QHBoxLayout()
        self.wikidata_status_label = QtWidgets.QLabel("Not signed in")
        wikidata_row.addWidget(self.wikidata_status_label)
        wikidata_row.addStretch()
        self.wikidata_login_button = QtWidgets.QPushButton("Log in / Test...")
        self.wikidata_login_button.clicked.connect(self._on_wikidata_login_clicked)
        wikidata_row.addWidget(self.wikidata_login_button)
        self.wikidata_forget_button = QtWidgets.QPushButton("Forget")
        self.wikidata_forget_button.clicked.connect(self._on_wikidata_forget_clicked)
        wikidata_row.addWidget(self.wikidata_forget_button)
        wikidata_layout.addLayout(wikidata_row)

        layout.addWidget(wikidata_group)

        # --- Advanced: bring-your-own AI endpoint, used only when Morpheus
        # Connect isn't set up -- see ui/mapping_panel.py's fallback order. --
        advanced_group = QtWidgets.QGroupBox("Advanced: Custom AI Endpoint (optional)")
        advanced_form = QtWidgets.QFormLayout(advanced_group)

        self.ai_endpoint_edit = QtWidgets.QLineEdit()
        self.ai_endpoint_edit.setPlaceholderText("https://example.com/api/map-columns")
        advanced_form.addRow("Endpoint URL:", self.ai_endpoint_edit)

        self.ai_api_key_edit = QtWidgets.QLineEdit()
        self.ai_api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.ai_api_key_edit.setPlaceholderText("Optional API key")
        advanced_form.addRow("API key:", self.ai_api_key_edit)

        layout.addWidget(advanced_group)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save_settings)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_settings(self):
        self.edit_summary_edit.setText(app_settings.get_default_edit_summary())
        self.delay_spin.setValue(app_settings.get_upload_delay_seconds())
        self.maxlag_spin.setValue(app_settings.get_maxlag_seconds())
        self.ai_endpoint_edit.setText(app_settings.get_ai_endpoint_url())
        self.ai_api_key_edit.setText(app_settings.get_ai_api_key())
        self._refresh_morpheus_status()
        self._refresh_wikidata_status()

    def _refresh_morpheus_status(self):
        """Show whether a Morpheus connection is saved.

        The answer lives in the OS keychain, whose read can block on an authorisation prompt. On the
        GUI thread that froze this dialog mid-build (2026-10-01: the window rendered half-built and
        no Connect request was ever created), so the read runs in the background and the label says
        it is checking until the answer arrives. A read that does not answer is reported as itself --
        never as "Not connected", which is a different fact.
        """
        self.morpheus_status_label.setText(feedback.CHECKING_TEXT)
        self.morpheus_connect_button.setEnabled(False)
        self.morpheus_disconnect_button.setEnabled(False)
        self._morpheus_read = KeychainRead(credential_storage.load_morpheus_token, parent=self)
        self._morpheus_read.finished_read.connect(self._on_morpheus_read)

    def _on_morpheus_read(self, outcome):
        self.morpheus_status_label.setText(feedback.morpheus_connection_text(outcome))
        connect_enabled, disconnect_enabled = feedback.morpheus_button_state(outcome)
        self.morpheus_connect_button.setEnabled(connect_enabled)
        self.morpheus_disconnect_button.setEnabled(disconnect_enabled)

    def _refresh_wikidata_status(self):
        """Say which account is saved, or that none is. Read from the keychain, never remembered in
        the UI -- the same source every other part of the app reads the login from. Off the GUI
        thread for the same reason as the Morpheus read above."""
        self.wikidata_status_label.setText(feedback.CHECKING_TEXT)
        self.wikidata_forget_button.setEnabled(False)
        self._wikidata_read = KeychainRead(credential_storage.load_credentials, parent=self)
        self._wikidata_read.finished_read.connect(self._on_wikidata_read)

    def _on_wikidata_read(self, outcome):
        self.wikidata_status_label.setText(feedback.wikidata_account_text(outcome))
        creds = outcome.value if outcome.status == blocking_read.ANSWERED else None
        self.wikidata_forget_button.setEnabled(bool(creds))

    def _on_wikidata_login_clicked(self):
        # remember_default=True: the reason the user opened Settings is to set the account up, so the
        # "Remember credentials" box starts ticked here. See AuthDialog.__init__.
        dialog = AuthDialog(self, remember_default=True)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.get_login_object():
            self._refresh_wikidata_status()

    def _on_wikidata_forget_clicked(self):
        credential_storage.delete_credentials()
        self._refresh_wikidata_status()

    def _on_connect_clicked(self):
        dialog = ConnectDialog(self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.token:
            if credential_storage.save_morpheus_token(dialog.token):
                self._refresh_morpheus_status()
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Could Not Save Connection",
                    "Connected, but the token could not be saved. The app stores it in your operating "
                    "system's keychain (macOS Keychain, Windows Credential Locker, Linux Secret "
                    "Service); if none is available it falls back to a file beside the app's data. "
                    "The connection itself worked -- only saving it failed."
                )

    def _on_disconnect_clicked(self):
        credential_storage.clear_morpheus_token()
        self._refresh_morpheus_status()

    def _save_settings(self):
        summary = self.edit_summary_edit.text().strip() or app_settings.DEFAULT_EDIT_SUMMARY
        app_settings.set_default_edit_summary(summary)
        app_settings.set_upload_delay_seconds(self.delay_spin.value())
        app_settings.set_maxlag_seconds(self.maxlag_spin.value())
        app_settings.set_ai_endpoint_url(self.ai_endpoint_edit.text().strip())
        app_settings.set_ai_api_key(self.ai_api_key_edit.text())
        self.accept()
