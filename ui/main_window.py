import os
import sys
from PyQt6 import QtCore, QtGui, QtWidgets

from ui.styles import GLOBAL_STYLESHEET
from ui.mapping_view import MappingView
from ui.image_preview import ImagePreviewWidget
from ui.settings_dialog import SettingsDialog
from ui.reference_table_editor import ReferenceTableEditor
from ui.commons_upload_dialog import CommonsUploadDialog
from core.data_loader import load_dataframe_preview
from core.lazy_loader import DataLoadingWorker
from core.workers import DryRunWorker, UploadWorker, DuplicateCheckExistingWorker, CommonsUploadWorker
from core.reference_tables import ensure_sample_reference_tables
from core.settings import get_commons_default_category, get_commons_license_template, get_commons_edit_summary
from config import REFERENCE_TABLES_DIR


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('WikiData Batch Uploader')
        self.resize(1200, 800)

        self.setStyleSheet(GLOBAL_STYLESHEET)
        ensure_sample_reference_tables(REFERENCE_TABLES_DIR)
        
        self._create_actions()
        self._create_menu()
        self._create_ui()
        
        self.file_paths = {}  # item text -> full path (legacy, not used if using item data)
        self.full_paths = []  # store full paths for current scan
        self.current_dataframe = None
        self.full_dataframes = {}  # cache for fully loaded DataFrames, keyed by file path
        self._data_loading_worker = None
        self._dry_run_worker = None
        self._upload_worker = None
        self._duplicate_check_worker = None
        self._commons_upload_worker = None

        # Callback storage for worker signals (so we can connect to bound methods)
        self._dry_run_on_finished = None
        self._dry_run_on_error = None
        self._upload_on_progress = None
        self._upload_on_finished = None
        self._upload_on_error = None
        self._duplicate_check_on_progress = None
        self._duplicate_check_on_finished = None
        self._duplicate_check_on_error = None
        self._commons_upload_on_progress = None
        self._commons_upload_on_finished = None
        self._commons_upload_on_error = None

    def _create_actions(self):
        self.open_folder_action = QtGui.QAction('Open Folder...', self)
        self.open_folder_action.setShortcut('Ctrl+O')
        self.open_folder_action.triggered.connect(self.open_folder_dialog)

        self.commons_upload_action = QtGui.QAction('Upload to Wikimedia Commons...', self)
        self.commons_upload_action.setShortcut('Ctrl+U')
        self.commons_upload_action.triggered.connect(self.open_commons_upload_dialog)

        self.settings_action = QtGui.QAction('Settings...', self)
        self.settings_action.triggered.connect(self.open_settings_dialog)

        self.edit_ref_tables_action = QtGui.QAction('Edit Reference Tables...', self)
        self.edit_ref_tables_action.triggered.connect(self.open_reference_tables_editor)

        self.exit_action = QtGui.QAction('Exit', self)
        self.exit_action.triggered.connect(self.close)

    def _create_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')
        file_menu.addAction(self.open_folder_action)
        file_menu.addAction(self.commons_upload_action)
        file_menu.addSeparator()
        file_menu.addAction(self.edit_ref_tables_action)
        file_menu.addAction(self.settings_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

    def _create_ui(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QtWidgets.QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = QtWidgets.QListWidget()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setFixedWidth(260)
        self.sidebar.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.sidebar.itemClicked.connect(self.on_file_selected)
        main_layout.addWidget(self.sidebar)

        # Central area: stacked widget with placeholder, preview table, and image preview
        self.central_stack = QtWidgets.QStackedWidget()
        self.central_placeholder = QtWidgets.QLabel('Select a folder to begin.\nSupported files: .xlsx, .csv, .jpg, .jpeg, .png, .tif, .tiff')
        self.central_placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.central_placeholder.setWordWrap(True)
        self.central_placeholder.setObjectName('placeholder')
        self.mapping_view = MappingView()
        self.image_preview = ImagePreviewWidget()
        self.central_stack.addWidget(self.central_placeholder)  # index 0
        self.central_stack.addWidget(self.mapping_view)          # index 1
        self.central_stack.addWidget(self.image_preview)        # index 2
        main_layout.addWidget(self.central_stack)

    def open_folder_dialog(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select Folder', '')
        if folder:
            self.scan_folder(folder)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def open_reference_tables_editor(self):
        """Open the reference table editor and refresh mapping view after save."""
        dialog = ReferenceTableEditor(self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.mapping_view.reload_reference_data()

    def open_commons_upload_dialog(self):
        """Open the Commons upload dialog and start a background worker if accepted."""
        dialog = CommonsUploadDialog(self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            queue = dialog.get_upload_queue()
            if not queue:
                return
            # Separate parallel lists for the worker
            file_paths = [item[0] for item in queue]
            metadata_list = [item[1] for item in queue]
            category = get_commons_default_category()
            license_template = get_commons_license_template()
            edit_summary = get_commons_edit_summary()

            self.start_commons_upload_worker(
                file_paths, metadata_list, category, license_template, edit_summary,
                on_progress=self._on_commons_upload_progress,
                on_finished=self._on_commons_upload_finished,
                on_error=self._on_commons_upload_error
            )

    def start_commons_upload_worker(self, file_paths, metadata_list, category, license_template, edit_summary,
                                    on_progress, on_finished, on_error, chunk_size=None):
        """Start a Commons upload in a background thread.

        Args:
            file_paths: List of full paths to media files to upload.
            metadata_list: List of metadata dictionaries, parallel to file_paths.
            category: Commons category to apply.
            license_template: License template to apply.
            edit_summary: Edit summary for the uploads.
            on_progress: Callback receiving (done, total, message) per file.
            on_finished: Callback receiving the summary string.
            on_error: Callback receiving the error message string.
            chunk_size: Optional chunk size for chunked uploads.
        """
        if self._commons_upload_worker is not None and self._commons_upload_worker.isRunning():
            return
        self._commons_upload_on_progress = on_progress
        self._commons_upload_on_finished = on_finished
        self._commons_upload_on_error = on_error
        worker = CommonsUploadWorker(
            file_paths, metadata_list, category, license_template, edit_summary,
            chunk_size=chunk_size, parent=self
        )
        worker.progress.connect(self._handle_commons_upload_progress)
        worker.finished.connect(self._handle_commons_upload_finished)
        worker.error.connect(self._handle_commons_upload_error)
        self._commons_upload_worker = worker
        worker.start()

    def _handle_commons_upload_progress(self, done, total, message):
        if self._commons_upload_on_progress:
            self._commons_upload_on_progress(done, total, message)

    def _handle_commons_upload_finished(self, summary):
        self._clear_worker('_commons_upload_worker')
        callback = self._commons_upload_on_finished
        self._commons_upload_on_progress = None
        self._commons_upload_on_finished = None
        self._commons_upload_on_error = None
        if callback:
            callback(summary)

    def _handle_commons_upload_error(self, msg):
        self._clear_worker('_commons_upload_worker')
        callback = self._commons_upload_on_error
        self._commons_upload_on_progress = None
        self._commons_upload_on_finished = None
        self._commons_upload_on_error = None
        if callback:
            callback(msg)

    def _on_commons_upload_progress(self, done, total, message):
        self.statusBar().showMessage(f"Uploading {done}/{total}: {message}")

    def _on_commons_upload_finished(self, summary):
        self.statusBar().clearMessage()
        QtWidgets.QMessageBox.information(self, "Commons Upload Complete", summary)

    def _on_commons_upload_error(self, msg):
        self.statusBar().clearMessage()
        QtWidgets.QMessageBox.critical(self, "Commons Upload Error", msg)

    def scan_folder(self, folder):
        supported_extensions = {'.xlsx', '.csv', '.jpg', '.jpeg', '.png', '.tif', '.tiff'}
        files = []
        for entry in os.listdir(folder):
            full_path = os.path.join(folder, entry)
            if os.path.isfile(full_path):
                ext = os.path.splitext(entry)[1].lower()
                if ext in supported_extensions:
                    files.append(full_path)

        self.sidebar.clear()
        self.full_paths = files
        self.full_dataframes.clear()  # new folder scan invalidates cached full DataFrames
        for full_path in files:
            file_name = os.path.basename(full_path)
            item = QtWidgets.QListWidgetItem(file_name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, full_path)
            self.sidebar.addItem(item)

        # Update placeholder text and reset central view to placeholder
        if files:
            self.central_placeholder.setText(f'Found {len(files)} supported file(s).\nSelect a file from the sidebar to begin mapping.')
        else:
            self.central_placeholder.setText('No supported files found in the selected folder.')
        self.central_stack.setCurrentWidget(self.central_placeholder)

    def get_full_dataframe(self, file_path, on_success, on_error):
        """Return the cached full DataFrame if available; otherwise load it in background and cache."""
        if file_path in self.full_dataframes:
            on_success(self.full_dataframes[file_path])
            return
        worker = DataLoadingWorker(file_path, parent=self)

        def handle_success(df):
            self.full_dataframes[file_path] = df
            self._data_loading_worker = None
            on_success(df)

        def handle_error(msg):
            self._data_loading_worker = None
            on_error(msg)

        worker.finished.connect(handle_success, QtCore.Qt.ConnectionType.QueuedConnection)
        worker.error.connect(handle_error, QtCore.Qt.ConnectionType.QueuedConnection)
        self._data_loading_worker = worker
        worker.start()

    def _clear_worker(self, attr_name):
        setattr(self, attr_name, None)

    def start_dry_run_worker(self, df, mapping, constants_df, properties_df, on_finished, on_error):
        """Start a dry-run in a background thread.

        Args:
            df: Full pandas DataFrame to evaluate.
            mapping: Column name -> property ID mapping.
            constants_df: Project constants DataFrame.
            properties_df: Optional property reference DataFrame.
            on_finished: Callback receiving the summary string.
            on_error: Callback receiving the error message string.
        """
        if self._dry_run_worker is not None and self._dry_run_worker.isRunning():
            return
        self._dry_run_on_finished = on_finished
        self._dry_run_on_error = on_error
        worker = DryRunWorker(df, mapping, constants_df, properties_df, parent=self)
        worker.finished.connect(self._handle_dry_run_finished)
        worker.error.connect(self._handle_dry_run_error)
        self._dry_run_worker = worker
        worker.start()

    def _handle_dry_run_finished(self, result):
        self._clear_worker('_dry_run_worker')
        callback = self._dry_run_on_finished
        self._dry_run_on_finished = None
        self._dry_run_on_error = None
        if callback:
            callback(result)

    def _handle_dry_run_error(self, msg):
        self._clear_worker('_dry_run_worker')
        callback = self._dry_run_on_error
        self._dry_run_on_finished = None
        self._dry_run_on_error = None
        if callback:
            callback(msg)

    def start_upload_worker(self, login, df, mapping, constants_df, edit_summary, on_progress, on_finished, on_error,
                            delay_seconds=1.0, maxlag=5.0, skip_rows=None):
        """Start an upload in a background thread.

        Args:
            login: Authenticated WDLogin object.
            df: Full pandas DataFrame to upload.
            mapping: Column name -> property ID mapping.
            constants_df: Project constants DataFrame.
            edit_summary: Edit summary for the writes.
            on_progress: Callback receiving (done, total, item_id) per row.
            on_finished: Callback receiving the uploaded count (int).
            on_error: Callback receiving the error message string.
            delay_seconds: Delay between rows.
            maxlag: Maximum server lag.
            skip_rows: Set of original row indices to skip.
        """
        if self._upload_worker is not None and self._upload_worker.isRunning():
            return
        self._upload_on_progress = on_progress
        self._upload_on_finished = on_finished
        self._upload_on_error = on_error
        worker = UploadWorker(
            login, df, mapping, constants_df, edit_summary,
            delay_seconds=delay_seconds, maxlag=maxlag,
            skip_rows=skip_rows, parent=self
        )
        worker.progress.connect(self._handle_upload_progress)
        worker.finished.connect(self._handle_upload_finished)
        worker.error.connect(self._handle_upload_error)
        self._upload_worker = worker
        worker.start()

    def _handle_upload_progress(self, done, total, item_id):
        if self._upload_on_progress:
            self._upload_on_progress(done, total, item_id)

    def _handle_upload_finished(self, count):
        self._clear_worker('_upload_worker')
        callback = self._upload_on_finished
        self._upload_on_progress = None
        self._upload_on_finished = None
        self._upload_on_error = None
        if callback:
            callback(count)

    def _handle_upload_error(self, msg):
        self._clear_worker('_upload_worker')
        callback = self._upload_on_error
        self._upload_on_progress = None
        self._upload_on_finished = None
        self._upload_on_error = None
        if callback:
            callback(msg)

    def start_duplicate_check_worker(self, df, mapping, duplicate_key_columns, on_progress, on_finished, on_error):
        """Start an existing-item duplicate check in a background thread.

        Args:
            df: Full pandas DataFrame to check.
            mapping: Column name -> property ID mapping.
            duplicate_key_columns: List of columns used as duplicate keys.
            on_progress: Callback receiving (done, total) per row.
            on_finished: Callback receiving a dict mapping row index to QID list.
            on_error: Callback receiving the error message string.
        """
        if self._duplicate_check_worker is not None and self._duplicate_check_worker.isRunning():
            return
        self._duplicate_check_on_progress = on_progress
        self._duplicate_check_on_finished = on_finished
        self._duplicate_check_on_error = on_error
        worker = DuplicateCheckExistingWorker(df, mapping, duplicate_key_columns, parent=self)
        worker.progress.connect(self._handle_duplicate_check_progress)
        worker.finished.connect(self._handle_duplicate_check_finished)
        worker.error.connect(self._handle_duplicate_check_error)
        self._duplicate_check_worker = worker
        worker.start()

    def _handle_duplicate_check_progress(self, done, total):
        if self._duplicate_check_on_progress:
            self._duplicate_check_on_progress(done, total)

    def _handle_duplicate_check_finished(self, results):
        self._clear_worker('_duplicate_check_worker')
        callback = self._duplicate_check_on_finished
        self._duplicate_check_on_progress = None
        self._duplicate_check_on_finished = None
        self._duplicate_check_on_error = None
        if callback:
            callback(results)

    def _handle_duplicate_check_error(self, msg):
        self._clear_worker('_duplicate_check_worker')
        callback = self._duplicate_check_on_error
        self._duplicate_check_on_progress = None
        self._duplicate_check_on_finished = None
        self._duplicate_check_on_error = None
        if callback:
            callback(msg)

    def on_file_selected(self, item):
        full_path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not full_path:
            return
        ext = os.path.splitext(full_path)[1].lower()
        if ext in ('.xlsx', '.csv'):
            try:
                df = load_dataframe_preview(full_path)
                self.current_dataframe = df
                self.current_file_path = full_path
                image_extensions = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
                image_paths = [p for p in self.full_paths if os.path.splitext(p)[1].lower() in image_extensions]
                self.mapping_view.set_preview(df, full_path, image_paths)
                self.central_placeholder.setText('Preview mode: showing first 500 rows. Full data loads on dry-run or upload.')
                self.central_stack.setCurrentWidget(self.mapping_view)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, 'Error Loading File', str(e))
                self.central_stack.setCurrentWidget(self.central_placeholder)
        elif ext in ('.jpg', '.jpeg', '.png', '.tif', '.tiff'):
            self.image_preview.set_image(full_path)
            self.central_stack.setCurrentWidget(self.image_preview)
        else:
            # Should not happen given scan filter, but handle gracefully
            self.central_placeholder.setText(f'Unsupported file type: {os.path.basename(full_path)}')
            self.central_stack.setCurrentWidget(self.central_placeholder)
