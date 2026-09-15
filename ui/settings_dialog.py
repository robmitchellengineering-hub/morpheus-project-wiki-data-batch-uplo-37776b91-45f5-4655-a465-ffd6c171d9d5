from PyQt6 import QtCore, QtWidgets
from core import settings as app_settings


class SettingsDialog(QtWidgets.QDialog):
    """Dialog for configuring user preferences stored via QSettings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(500, 280)
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

        self.ai_endpoint_edit = QtWidgets.QLineEdit()
        self.ai_endpoint_edit.setPlaceholderText("https://example.com/api/map-columns")
        form.addRow("AI mapping endpoint URL:", self.ai_endpoint_edit)

        self.ai_api_key_edit = QtWidgets.QLineEdit()
        self.ai_api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.ai_api_key_edit.setPlaceholderText("Optional API key")
        form.addRow("AI API key:", self.ai_api_key_edit)

        layout.addLayout(form)

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

    def _save_settings(self):
        summary = self.edit_summary_edit.text().strip() or app_settings.DEFAULT_EDIT_SUMMARY
        app_settings.set_default_edit_summary(summary)
        app_settings.set_upload_delay_seconds(self.delay_spin.value())
        app_settings.set_maxlag_seconds(self.maxlag_spin.value())
        app_settings.set_ai_endpoint_url(self.ai_endpoint_edit.text().strip())
        app_settings.set_ai_api_key(self.ai_api_key_edit.text())
        self.accept()
