from PyQt6 import QtCore, QtWidgets
from core import settings as app_settings
from core import credential_storage
from ui.connect_dialog import ConnectDialog


class SettingsDialog(QtWidgets.QDialog):
    """Dialog for configuring user preferences stored via QSettings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(500, 380)
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

    def _refresh_morpheus_status(self):
        connected = bool(credential_storage.load_morpheus_token())
        self.morpheus_status_label.setText("Connected" if connected else "Not connected")
        self.morpheus_connect_button.setEnabled(not connected)
        self.morpheus_disconnect_button.setEnabled(connected)

    def _on_connect_clicked(self):
        dialog = ConnectDialog(self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.token:
            if credential_storage.save_morpheus_token(dialog.token):
                self._refresh_morpheus_status()
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Could Not Save Connection",
                    "Connected, but the token could not be saved to disk. "
                    "This feature requires Windows (DPAPI-encrypted local storage)."
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
