"""Dialog for core.photo_metadata_merge -- lets the operator pick which
column holds each row's photo filename and which metadata fields to pull
in from those photos' EXIF/IPTC data."""
from PyQt6 import QtWidgets


class PhotoFillDialog(QtWidgets.QDialog):
    """Collects the inputs merge_photo_metadata needs, then exposes them via
    get_choices() once accepted."""

    def __init__(self, columns, photo_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fill from Photos")
        self.setModal(True)
        self._create_ui(columns, photo_count)

    def _create_ui(self, columns, photo_count):
        layout = QtWidgets.QVBoxLayout(self)

        hint = QtWidgets.QLabel(
            f"{photo_count} photo(s) found in this folder. Rows will be matched to a photo "
            "by filename, and the fields below filled from that photo's metadata."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QtWidgets.QFormLayout()
        self.filename_column_combo = QtWidgets.QComboBox()
        self.filename_column_combo.addItems([str(c) for c in columns])
        form.addRow("Filename column:", self.filename_column_combo)
        layout.addLayout(form)

        fields_label = QtWidgets.QLabel("Fields to fill:")
        layout.addWidget(fields_label)

        self.gps_check = QtWidgets.QCheckBox("GPS coordinates")
        self.gps_check.setChecked(True)
        layout.addWidget(self.gps_check)

        self.date_check = QtWidgets.QCheckBox("Date taken")
        self.date_check.setChecked(True)
        layout.addWidget(self.date_check)

        self.camera_check = QtWidgets.QCheckBox("Camera model")
        self.camera_check.setChecked(True)
        layout.addWidget(self.camera_check)

        self.overwrite_check = QtWidgets.QCheckBox("Overwrite existing values in these columns")
        self.overwrite_check.setChecked(False)
        layout.addWidget(self.overwrite_check)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_accept(self):
        if not (self.gps_check.isChecked() or self.date_check.isChecked() or self.camera_check.isChecked()):
            QtWidgets.QMessageBox.warning(self, "No Fields Selected", "Select at least one field to fill.")
            return
        self.accept()

    def get_choices(self):
        """Return (filename_column, fields, overwrite) once accepted."""
        fields = []
        if self.gps_check.isChecked():
            fields.append('gps')
        if self.date_check.isChecked():
            fields.append('date')
        if self.camera_check.isChecked():
            fields.append('camera')
        return self.filename_column_combo.currentText(), fields, self.overwrite_check.isChecked()
