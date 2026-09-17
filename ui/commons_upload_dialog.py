import os
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton, QListWidget,
    QListWidgetItem, QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QGroupBox, QDialogButtonBox, QMessageBox, QFileDialog, QSplitter, QWidget,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.image_preview import ImagePreviewWidget
from core.metadata_extractor import extract_image_metadata
from core.settings import get_commons_default_category, get_commons_license_template


class CommonsUploadDialog(QDialog):
    """Dialog for selecting files and editing their Commons metadata."""
    accepted_with_data = pyqtSignal(list, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Commons Batch Upload')
        self.resize(1000, 620)

        self.file_paths = []
        self.file_metadata = {}  # path -> dict with editable fields
        self.extracted_raw = {}  # path -> raw extraction result (cached)
        self.current_path = None

        self._build_ui()
        self._populate_mapping_table()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        top_layout = QHBoxLayout()
        self.add_files_btn = QPushButton('Add Files...')
        self.remove_btn = QPushButton('Remove Selected')
        self.clear_btn = QPushButton('Clear')
        self.mapping_btn = QPushButton('Mapping...')
        self.extract_btn = QPushButton('Extract Metadata')
        top_layout.addWidget(self.add_files_btn)
        top_layout.addWidget(self.remove_btn)
        top_layout.addWidget(self.clear_btn)
        top_layout.addStretch()
        top_layout.addWidget(self.mapping_btn)
        top_layout.addWidget(self.extract_btn)
        main_layout.addLayout(top_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.currentItemChanged.connect(self._on_file_selection_changed)
        splitter.addWidget(self.file_list)

        self.preview = ImagePreviewWidget()
        splitter.addWidget(self.preview)

        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(6, 6, 6, 6)
        self.filename_edit = QLineEdit()
        self.description_edit = QTextEdit()
        self.description_edit.setMinimumHeight(80)
        self.date_edit = QLineEdit()
        self.categories_edit = QLineEdit()
        self.license_edit = QLineEdit()
        form_layout.addRow('Destination Filename:', self.filename_edit)
        form_layout.addRow('Description:', self.description_edit)
        form_layout.addRow('Date Taken:', self.date_edit)
        form_layout.addRow('Categories (comma-sep):', self.categories_edit)
        form_layout.addRow('License Template:', self.license_edit)
        splitter.addWidget(form_widget)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([200, 450, 350])
        main_layout.addWidget(splitter, 1)

        # Hidden metadata mapping table
        self.mapping_group = QGroupBox('Metadata Mapping')
        self.mapping_group.setVisible(False)
        self.mapping_table = QTableWidget(2, 2)
        self.mapping_table.setHorizontalHeaderLabels(['Target Field', 'Metadata Key(s)'])
        self.mapping_table.horizontalHeader().setStretchLastSection(True)
        self.mapping_table.verticalHeader().setVisible(False)
        group_layout = QVBoxLayout(self.mapping_group)
        group_layout.addWidget(self.mapping_table)
        main_layout.addWidget(self.mapping_group)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        self.add_files_btn.clicked.connect(self._add_files)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn.clicked.connect(self._clear_files)
        self.mapping_btn.clicked.connect(self._toggle_mapping)
        self.extract_btn.clicked.connect(self._extract_current)

        self.filename_edit.editingFinished.connect(self._on_filename_edited)
        self.description_edit.textChanged.connect(self._on_description_edited)
        self.date_edit.editingFinished.connect(self._on_date_edited)
        self.categories_edit.editingFinished.connect(self._on_categories_edited)
        self.license_edit.editingFinished.connect(self._on_license_edited)

    def _populate_mapping_table(self):
        """Set default metadata keys in the hidden mapping table."""
        self.mapping_table.setItem(0, 0, QTableWidgetItem('Description'))
        self.mapping_table.setItem(0, 1, QTableWidgetItem(
            'EXIF:ImageDescription, IPTC:Caption/Abstract, XMP:Description'))
        self.mapping_table.setItem(1, 0, QTableWidgetItem('Date Taken'))
        self.mapping_table.setItem(1, 1, QTableWidgetItem(
            'EXIF:DateTimeOriginal, IPTC:DateCreated'))

    def _toggle_mapping(self):
        """Show or hide the mapping group."""
        visible = not self.mapping_group.isVisible()
        self.mapping_group.setVisible(visible)

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            'Select Files',
            '',
            'Images (*.jpg *.jpeg *.png *.tif *.tiff)'
        )
        for path in paths:
            if path not in self.file_paths:
                self.file_paths.append(path)
                item = QListWidgetItem(os.path.basename(path))
                item.setData(Qt.ItemDataRole.UserRole, path)
                self.file_list.addItem(item)
                if path not in self.file_metadata:
                    self.file_metadata[path] = self._create_default_metadata(path)
                # Do not extract yet; lazy extraction on selection.
        if paths and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)

    def _remove_selected(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path in self.file_paths:
                self.file_paths.remove(path)
            self.file_metadata.pop(path, None)
            self.extracted_raw.pop(path, None)
            row = self.file_list.row(item)
            self.file_list.takeItem(row)
        self.current_path = None
        self._clear_form()
        if self.file_list.count() > 0:
            self.file_list.setCurrentRow(0)

    def _clear_files(self):
        self.file_list.clear()
        self.file_paths.clear()
        self.file_metadata.clear()
        self.extracted_raw.clear()
        self.current_path = None
        self._clear_form()

    def _clear_form(self):
        self.filename_edit.clear()
        self.description_edit.clear()
        self.date_edit.clear()
        self.categories_edit.clear()
        self.license_edit.clear()

    def _create_default_metadata(self, path):
        return {
            'filename': os.path.basename(path),
            'description': '',
            'date': '',
            'categories': get_commons_default_category(),
            'license': get_commons_license_template(),
        }

    def _on_file_selection_changed(self, current, previous):
        # Save current form before switching.
        if self.current_path:
            self._save_current_metadata()
        if not current:
            self.current_path = None
            self._clear_form()
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        self.current_path = path
        # Ensure metadata entry exists.
        if path not in self.file_metadata:
            self.file_metadata[path] = self._create_default_metadata(path)
        # Lazy extraction: if no raw metadata and not extracted yet, extract and populate.
        if path not in self.extracted_raw:
            self._extract_and_populate(path)
        self._load_metadata(path)
        self.preview.set_image(path)

    def _load_metadata(self, path):
        meta = self.file_metadata[path]
        self.filename_edit.setText(meta['filename'])
        self.description_edit.setPlainText(meta['description'])
        self.date_edit.setText(meta['date'])
        self.categories_edit.setText(meta['categories'])
        self.license_edit.setText(meta['license'])

    def _save_current_metadata(self):
        if not self.current_path or self.current_path not in self.file_metadata:
            return
        meta = self.file_metadata[self.current_path]
        meta['filename'] = self.filename_edit.text().strip()
        meta['description'] = self.description_edit.toPlainText()
        meta['date'] = self.date_edit.text().strip()
        meta['categories'] = self.categories_edit.text().strip()
        meta['license'] = self.license_edit.text().strip()

    def _on_filename_edited(self):
        self._update_current_field('filename', self.filename_edit.text().strip())

    def _on_description_edited(self):
        self._update_current_field('description', self.description_edit.toPlainText())

    def _on_date_edited(self):
        self._update_current_field('date', self.date_edit.text().strip())

    def _on_categories_edited(self):
        self._update_current_field('categories', self.categories_edit.text().strip())

    def _on_license_edited(self):
        self._update_current_field('license', self.license_edit.text().strip())

    def _update_current_field(self, key, value):
        if self.current_path and self.current_path in self.file_metadata:
            self.file_metadata[self.current_path][key] = value

    def _get_mapping_keys(self, row):
        item = self.mapping_table.item(row, 1)
        if not item:
            return []
        raw = item.text()
        keys = [k.strip() for k in raw.split(',') if k.strip()]
        return keys

    def _extract_current(self):
        """Re-run extraction for the currently selected file."""
        if not self.current_path:
            QMessageBox.information(self, 'No Selection', 'Please select a file first.')
            return
        self._extract_and_populate(self.current_path, overwrite=True)
        self._load_metadata(self.current_path)

    def _extract_and_populate(self, path, overwrite=False):
        """Extract raw metadata and populate description/date if empty or overwrite."""
        try:
            raw = extract_image_metadata(path)
        except Exception:
            raw = {}
        self.extracted_raw[path] = raw
        meta = self.file_metadata.setdefault(path, self._create_default_metadata(path))

        desc_keys = self._get_mapping_keys(0)
        desc_val = self._first_non_empty(raw, desc_keys)
        if desc_val is not None and (overwrite or not meta['description']):
            meta['description'] = str(desc_val)

        date_keys = self._get_mapping_keys(1)
        date_val = self._first_non_empty(raw, date_keys)
        if date_val is not None:
            formatted = self._format_exif_date(str(date_val))
            if formatted and (overwrite or not meta['date']):
                meta['date'] = formatted

    def _first_non_empty(self, data_dict, keys):
        for key in keys:
            val = data_dict.get(key)
            if val is not None and str(val).strip():
                return val
        return None

    def _format_exif_date(self, value):
        """Convert EXIF date (YYYY:MM:DD HH:MM:SS) to YYYY-MM-DD."""
        value = value.strip()
        if not value:
            return None
        # Already ISO-like?
        if len(value) >= 10 and value[4] == '-' and value[7] == '-':
            return value[:10]
        # EXIF format: YYYY:MM:DD HH:MM:SS
        if len(value) >= 10 and value[4] == ':' and value[7] == ':':
            return value[:4] + '-' + value[5:7] + '-' + value[8:10]
        # Fallback: take first token
        first = value.split(' ')[0]
        return first if first else None

    def _on_accept(self):
        self._save_current_metadata()
        if not self.file_paths:
            QMessageBox.warning(self, 'No Files', 'Add at least one file to upload.')
            return
        result_paths = self.file_paths[:]
        result_metadata = {p: self.file_metadata[p] for p in result_paths if p in self.file_metadata}
        self.accepted_with_data.emit(result_paths, result_metadata)
        self.accept()
