from PyQt6 import QtCore, QtWidgets, QtGui
from core.metadata_extractor import extract_image_metadata


class ScaledImageLabel(QtWidgets.QLabel):
    """QLabel that scales its pixmap to fit while preserving aspect ratio."""

    def __init__(self):
        super().__init__()
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 200)
        self.setText("No image loaded")
        self.setStyleSheet("border: 1px solid #c8ccd1; background-color: #ffffff;")
        self._pixmap = None

    def set_image_pixmap(self, pixmap: QtGui.QPixmap):
        """Set the image pixmap and trigger rescaling."""
        self._pixmap = pixmap if (pixmap is not None and not pixmap.isNull()) else None
        if self._pixmap is None:
            super().setPixmap(QtGui.QPixmap())  # clear
            self.setText("No image loaded")
        else:
            self._update_scaled_pixmap()

    def resizeEvent(self, event):
        self._update_scaled_pixmap()
        super().resizeEvent(event)

    def _update_scaled_pixmap(self):
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            super().setPixmap(scaled)


class ImagePreviewWidget(QtWidgets.QWidget):
    """Widget for displaying an image and its metadata in a table."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Image area
        self.image_label = ScaledImageLabel()
        layout.addWidget(self.image_label, stretch=3)

        # Metadata section header
        self.metadata_label = QtWidgets.QLabel("Metadata")
        font = self.metadata_label.font()
        font.setBold(True)
        self.metadata_label.setFont(font)
        layout.addWidget(self.metadata_label)

        # Metadata table
        self.metadata_table = QtWidgets.QTableWidget(0, 2)
        self.metadata_table.setHorizontalHeaderLabels(["Key", "Value"])
        self.metadata_table.horizontalHeader().setStretchLastSection(True)
        self.metadata_table.verticalHeader().setVisible(False)
        self.metadata_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.metadata_table.setAlternatingRowColors(True)
        self.metadata_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.metadata_table, stretch=2)

        self.file_path = None

    def set_image(self, file_path: str):
        """Load an image from file_path and display it with metadata."""
        self.file_path = file_path

        # Load image pixmap
        try:
            pixmap = QtGui.QPixmap(file_path)
            if pixmap.isNull():
                raise Exception("Could not load image (unsupported or corrupted).")
            self.image_label.set_image_pixmap(pixmap)
        except Exception as e:
            self.image_label.set_image_pixmap(QtGui.QPixmap())
            self.image_label.setText(f"Error loading image: {str(e)}")
            self.metadata_table.setRowCount(0)
            return

        # Extract metadata
        try:
            metadata = extract_image_metadata(file_path)
        except Exception as e:
            metadata = {}
            self.image_label.setText(f"Image loaded, but metadata extraction failed: {str(e)}")

        if not metadata:
            self.image_label.setText("Image loaded, no metadata found.")
            self.metadata_table.setRowCount(0)
            return

        # Populate table
        self.metadata_table.setRowCount(len(metadata))
        for row, (key, value) in enumerate(metadata.items()):
            key_item = QtWidgets.QTableWidgetItem(str(key))
            value_item = QtWidgets.QTableWidgetItem(str(value))
            # Make items read-only
            key_item.setFlags(key_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            value_item.setFlags(value_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.metadata_table.setItem(row, 0, key_item)
            self.metadata_table.setItem(row, 1, value_item)
        self.metadata_table.resizeColumnsToContents()
        self.metadata_table.horizontalHeader().setStretchLastSection(True)
