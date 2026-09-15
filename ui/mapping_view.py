from PyQt6 import QtCore, QtWidgets
from core.reference_tables import ensure_sample_reference_tables, load_wikidata_properties, load_project_constants
from ui.preview_table import PreviewTableWidget
from ui.mapping_panel import MappingPanel
from ui.auth_dialog import AuthDialog
from core import uploader
from core import settings as app_settings
from core.duplicate_checker import find_duplicate_rows_within_batch, find_existing_items
from config import REFERENCE_TABLES_DIR


class UploadWorker(QtCore.QThread):
    """Worker thread for uploading rows without blocking the UI."""
    progress = QtCore.pyqtSignal(int, int, str)  # done, total, item_id
    error = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(int)  # number of rows uploaded

    def __init__(self, login, df, mapping, constants_df, edit_summary, delay_seconds, maxlag, skip_rows=None, parent=None):
        super().__init__(parent)
        self.login = login
        self.df = df
        self.mapping = mapping
        self.constants_df = constants_df
        self.edit_summary = edit_summary
        self.delay_seconds = delay_seconds
        self.maxlag = maxlag
        self.skip_rows = skip_rows if skip_rows is not None else set()
        self._skipped_count = 0

    def run(self):
        try:
            uploader.upload_rows(
                self.login,
                self.df,
                self.mapping,
                self.constants_df,
                self.edit_summary,
                callback=self._on_progress,
                delay_seconds=self.delay_seconds,
                maxlag=self.maxlag,
                skip_rows=self.skip_rows
            )
            self.finished.emit(len(self.df) - len(self.skip_rows))
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, done, total, item_id):
        self.progress.emit(done, total, item_id)


class ExistingItemsCheckWorker(QtCore.QThread):
    """Worker thread that checks each row for existing Wikidata items using duplicate key columns."""
    found_rows = QtCore.pyqtSignal(list)  # list of row indices (integer positions in df)
    error = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal()

    def __init__(self, df, mapping, duplicate_key_columns, parent=None):
        super().__init__(parent)
        self.df = df
        self.mapping = mapping
        self.duplicate_key_columns = duplicate_key_columns

    def run(self):
        try:
            found = []
            for idx, row in self.df.iterrows():
                if self.duplicate_key_columns:
                    existing_ids = find_existing_items(row, self.mapping, self.duplicate_key_columns)
                    if existing_ids:
                        found.append(idx)
            self.found_rows.emit(found)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class MappingView(QtWidgets.QWidget):
    """Combined view: preview table, mapping panel, and upload controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        ensure_sample_reference_tables(REFERENCE_TABLES_DIR)
        self.properties_df = load_wikidata_properties(REFERENCE_TABLES_DIR)
        self.constants_df = load_project_constants(REFERENCE_TABLES_DIR)
        self.preview_df = None
        self.full_df = None
        self.file_path = None
        self.login_object = None
        self._upload_thread = None
        self._data_loading_thread = None
        self._existing_items_thread = None
        self._pending_callback = None
        self._data_loading_generation = 0  # increments on each new preview to invalidate stale loads
        self._upload_in_progress = False  # prevents concurrent uploads
        self.sleeping_row_ids = set()  # row indices to skip during upload
        self.existing_item_rows = set()  # row indices that already exist on Wikidata
        self.splitter = None
        self._create_ui()

    def _create_ui(self):
        self.preview_table = PreviewTableWidget()
        self.mapping_panel = MappingPanel(self.properties_df, self.constants_df)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.splitter.addWidget(self.preview_table)
        self.splitter.addWidget(self.mapping_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        # Upload section
        upload_widget = QtWidgets.QWidget()
        upload_layout = QtWidgets.QVBoxLayout(upload_widget)
        upload_layout.setContentsMargins(5, 5, 5, 5)
        upload_layout.setSpacing(5)

        self.upload_label = QtWidgets.QLabel("Upload to Wikidata")
        font = self.upload_label.font()
        font.setBold(True)
        self.upload_label.setFont(font)
        upload_layout.addWidget(self.upload_label)

        # Persistent indicator for preview/full data state
        self.preview_mode_label = QtWidgets.QLabel("Preview mode: showing first 500 rows. Full data loads on dry-run or upload.")
        self.preview_mode_label.setWordWrap(True)
        self.preview_mode_label.setStyleSheet("color: #72777d; font-size: 12px;")
        upload_layout.addWidget(self.preview_mode_label)

        self.status_label = QtWidgets.QLabel("Ready.")
        self.status_label.setWordWrap(True)
        upload_layout.addWidget(self.status_label)

        button_layout = QtWidgets.QHBoxLayout()
        self.dry_run_button = QtWidgets.QPushButton("Dry Run")
        self.dry_run_button.clicked.connect(self._run_dry_run)
        button_layout.addWidget(self.dry_run_button)

        self.existing_items_button = QtWidgets.QPushButton("Check Existing Items")
        self.existing_items_button.clicked.connect(self._run_existing_item_check)
        button_layout.addWidget(self.existing_items_button)

        self.upload_button = QtWidgets.QPushButton("Upload")
        self.upload_button.clicked.connect(self._run_upload)
        button_layout.addWidget(self.upload_button)
        upload_layout.addLayout(button_layout)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.splitter, stretch=1)
        main_layout.addWidget(upload_widget, stretch=0)

    def set_preview(self, df, file_path):
        """Set the preview dataframe and file path; reset full data cache and invalidate any running load."""
        self._data_loading_generation += 1  # invalidate any in-flight load
        self.preview_df = df
        self.file_path = file_path
        self.full_df = None
        self._pending_callback = None
        self.preview_table.set_dataframe(df)
        self.mapping_panel.set_columns(list(df.columns))
        self.mapping_panel.set_preview_df(df)
        self._enable_upload_buttons()  # respects _upload_in_progress flag
        self.sleeping_row_ids = set()
        self.existing_item_rows = set()
        # Update state labels
        self.preview_mode_label.setText("Preview mode: showing first 500 rows. Full data loads on dry-run or upload.")
        self.status_label.setText("Ready.")

    def reload_reference_data(self):
        """Reload reference tables from disk and refresh the mapping panel."""
        self.properties_df = load_wikidata_properties(REFERENCE_TABLES_DIR)
        self.constants_df = load_project_constants(REFERENCE_TABLES_DIR)

        # Create new mapping panel with updated data
        new_panel = MappingPanel(self.properties_df, self.constants_df)
        old_panel = self.mapping_panel
        self.mapping_panel = new_panel

        # Replace the old panel in the splitter
        index = self.splitter.indexOf(old_panel)
        if index >= 0:
            self.splitter.replaceWidget(index, new_panel)
        old_panel.deleteLater()

        # If a dataframe is currently loaded, repopulate the mapping combos with its columns
        if self.preview_df is not None:
            self.mapping_panel.set_columns(list(self.preview_df.columns))
            self.mapping_panel.set_preview_df(self.preview_df)
        # Reset status? Not necessary, but we can note that mapping is refreshed.
        self.status_label.setText("Reference tables updated; mappings refreshed.")

    def _run_dry_run(self):
        if self.preview_df is None:
            QtWidgets.QMessageBox.warning(self, "No Data", "No dataframe loaded.")
            return
        mapping = self.mapping_panel.get_column_mapping()
        if not any(pid is not None for pid in mapping.values()):
            QtWidgets.QMessageBox.warning(self, "No Mappings", "Please map at least one column to a Wikidata property.")
            return
        self._ensure_full_data(self._perform_dry_run)

    def _perform_dry_run(self):
        if self.full_df is None:
            QtWidgets.QMessageBox.critical(self, "Error", "Full data not loaded.")
            return
        try:
            summary = uploader.dry_run(self.full_df, self.mapping_panel.get_column_mapping(), self.constants_df, self.properties_df)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Dry Run Error", str(e))
            return
        self.status_label.setText(summary)

    def _run_upload(self):
        if self.preview_df is None:
            QtWidgets.QMessageBox.warning(self, "No Data", "No dataframe loaded.")
            return
        self._ensure_full_data(self._prompt_for_credentials_and_upload)

    def _prompt_for_credentials_and_upload(self):
        if self.full_df is None:
            return
        mapping = self.mapping_panel.get_column_mapping()
        if not any(pid is not None for pid in mapping.values()):
            QtWidgets.QMessageBox.warning(self, "No Mappings", "Please map at least one column to a Wikidata property.")
            return
        # Prompt for credentials if not already stored
        if not self.login_object:
            dialog = AuthDialog(self)
            if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                return
            self.login_object = dialog.get_login_object()
            if not self.login_object:
                QtWidgets.QMessageBox.warning(self, "Login Required", "Valid credentials are required for upload.")
                return

        edit_summary, ok = QtWidgets.QInputDialog.getText(
            self, "Edit Summary", "Enter a summary for Wikidata edits:",
            text=app_settings.get_default_edit_summary()
        )
        if not ok or not edit_summary.strip():
            return
        edit_summary = edit_summary.strip()
        delay_seconds = app_settings.get_upload_delay_seconds()
        maxlag_seconds = app_settings.get_maxlag_seconds()
        upload_df = self.full_df.copy()

        # Within-batch duplicate detection using mapped columns as identity
        duplicate_groups = find_duplicate_rows_within_batch(upload_df, mapping)
        if duplicate_groups:
            # Flatten group tuples to set of row indices (integer positions)
            duplicate_row_indices = set()
            for group in duplicate_groups:
                duplicate_row_indices.update(group)
            total_dup_rows = len(duplicate_row_indices)
            if total_dup_rows > 0:
                msg = f"Found {len(duplicate_groups)} group(s) of duplicate rows within the batch, affecting {total_dup_rows} row(s).\n\n" \
                      "Duplicates will be uploaded as separate items unless skipped. Do you want to continue?"
                ret = QtWidgets.QMessageBox.question(
                    self,
                    "Duplicate Rows Detected",
                    msg,
                    QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                    QtWidgets.QMessageBox.StandardButton.No
                )
                if ret == QtWidgets.QMessageBox.StandardButton.No:
                    self.status_label.setText("Upload aborted due to duplicates.")
                    return

        # Ask about skipping rows that already exist (if any from previous check)
        skip_rows = set()
        if self.existing_item_rows:
            existing_count = len(self.existing_item_rows)
            msg = f"{existing_count} row(s) appear to already exist on Wikidata.\n\n" \
                  "Skip these rows during upload?"
            ret = QtWidgets.QMessageBox.question(
                self,
                "Existing Items Found",
                msg,
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.Yes
            )
            if ret == QtWidgets.QMessageBox.StandardButton.Yes:
                skip_rows = set(self.existing_item_rows)

        self._upload_in_progress = True
        self.dry_run_button.setEnabled(False)
        self.upload_button.setEnabled(False)
        self.existing_items_button.setEnabled(False)
        self.status_label.setText("Uploading...")

        self._upload_thread = UploadWorker(
            self.login_object,
            upload_df,
            mapping,
            self.constants_df,
            edit_summary,
            delay_seconds,
            maxlag_seconds,
            skip_rows=skip_rows,
            parent=self
        )
        self._upload_thread.progress.connect(self._on_upload_progress)
        self._upload_thread.error.connect(self._on_upload_error)
        self._upload_thread.finished.connect(self._on_upload_finished)
        self._upload_thread.start()

    def _run_existing_item_check(self):
        """Check full data against Wikidata for existing items based on duplicate key columns."""
        if self.preview_df is None:
            QtWidgets.QMessageBox.warning(self, "No Data", "No dataframe loaded.")
            return
        duplicate_key_columns = self.mapping_panel.get_duplicate_key_columns()
        if not duplicate_key_columns:
            QtWidgets.QMessageBox.warning(
                self,
                "No Duplicate Key Columns",
                "Please mark at least one column as a duplicate key in the mapping table."
            )
            return
        self._ensure_full_data(self._perform_existing_item_check)

    def _perform_existing_item_check(self):
        if self.full_df is None:
            return
        duplicate_key_columns = self.mapping_panel.get_duplicate_key_columns()
        mapping = self.mapping_panel.get_column_mapping()

        self._upload_in_progress = True  # prevent other operations while checking
        self.dry_run_button.setEnabled(False)
        self.upload_button.setEnabled(False)
        self.existing_items_button.setEnabled(False)
        self.status_label.setText("Checking for existing items on Wikidata...")

        self._existing_items_thread = ExistingItemsCheckWorker(
            self.full_df.copy(),
            mapping,
            duplicate_key_columns,
            parent=self
        )
        self._existing_items_thread.found_rows.connect(self._on_existing_items_found)
        self._existing_items_thread.error.connect(self._on_existing_items_error)
        self._existing_items_thread.finished.connect(self._on_existing_items_finished)
        self._existing_items_thread.start()

    def _on_existing_items_found(self, found_rows):
        self.existing_item_rows = set(found_rows)

    def _on_existing_items_error(self, error_msg):
        self.status_label.setText(f"Existing item check failed: {error_msg}")
        QtWidgets.QMessageBox.critical(self, "Existing Item Check Error", error_msg)

    def _on_existing_items_finished(self):
        self._upload_in_progress = False
        self._enable_upload_buttons()
        if self.existing_item_rows:
            summary = f"Found {len(self.existing_item_rows)} row(s) that may already exist on Wikidata."
        else:
            summary = "No existing items found."
        self.status_label.setText(summary)

    def _ensure_full_data(self, callback):
        """Ensure full DataFrame is loaded; if not, load in background then call callback."""
        if self.full_df is not None:
            callback()
            return
        if self.file_path is None:
            QtWidgets.QMessageBox.warning(self, "No File", "No file path available.")
            return
        # Disable buttons and show loading status
        self.dry_run_button.setEnabled(False)
        self.upload_button.setEnabled(False)
        self.existing_items_button.setEnabled(False)
        self.status_label.setText("Loading full data...")
        self.preview_mode_label.setText("Loading full dataset...")

        generation = self._data_loading_generation
        main_window = self.window()
        if not hasattr(main_window, 'get_full_dataframe'):
            QtWidgets.QMessageBox.warning(self, "Internal Error", "Main window does not support full data caching.")
            return
        self._pending_callback = callback
        main_window.get_full_dataframe(
            self.file_path,
            lambda df, g=generation: self._on_full_data_loaded(df, g),
            lambda msg, g=generation: self._on_full_data_load_error(msg, g)
        )

    def _on_full_data_loaded(self, df, generation):
        if generation != self._data_loading_generation:
            return
        self.full_df = df
        self._enable_upload_buttons()
        self.preview_mode_label.setText(f"Full data loaded: {len(df)} rows.")
        if self._pending_callback is not None:
            callback = self._pending_callback
            self._pending_callback = None
            callback()
        else:
            self.status_label.setText("Full data loaded. Ready.")

    def _on_full_data_load_error(self, error_msg, generation):
        if generation != self._data_loading_generation:
            return
        self._enable_upload_buttons()
        self.status_label.setText(f"Failed to load full data: {error_msg}")
        self.preview_mode_label.setText("Preview mode (full data load failed).")
        QtWidgets.QMessageBox.critical(self, "Data Load Error", f"Could not load full dataset.\n{error_msg}")

    def _on_upload_progress(self, done, total, item_id):
        self.status_label.setText(f"Uploading {done}/{total} (last item {item_id})")

    def _on_upload_error(self, error_msg):
        self._upload_in_progress = False
        QtWidgets.QMessageBox.critical(self, "Upload Error", f"Failed during upload.\nError: {error_msg}")
        self._enable_upload_buttons()

    def _on_upload_finished(self, count):
        self._upload_in_progress = False
        self.status_label.setText(f"Upload completed successfully ({count} item(s)).")
        self._enable_upload_buttons()

    def _enable_upload_buttons(self):
        """Enable upload buttons only if no upload/check is currently running."""
        if self._upload_in_progress:
            return
        self.dry_run_button.setEnabled(True)
        self.upload_button.setEnabled(True)
        self.existing_items_button.setEnabled(True)
