import os
import json
import logging
import time
import pandas as pd
import requests
from PyQt6 import QtCore, QtWidgets
from core.schema_mapper import suggest_mappings
from core import blocking_read
from core import credential_storage
from core import feedback
from core import settings as app_settings
from core.morpheus_connect import suggest_mappings_with_morpheus
from core.workers import AiMappingWorker
from ui.keychain_read import KeychainRead

logger = logging.getLogger(__name__)


class MappingPanel(QtWidgets.QWidget):
    """Widget for mapping dataframe columns to Wikidata properties and showing project constants."""

    def __init__(self, properties_df, constants_df, parent=None):
        super().__init__(parent)
        self.properties_df = properties_df
        self.constants_df = constants_df
        self.column_mapping = {}  # column name (string) -> property_id or None
        self.duplicate_key_columns = set()
        self.preview_df = None  # dataframe sample for AI mapping
        # AI suggestion state: the keychain read, the in-flight call, and the elapsed clock.
        self._token_read = None
        self._ai_worker = None
        self._ai_columns = []
        self._ai_samples = []
        self._ai_busy_source = feedback.MORPHEUS
        self._ai_started_at = None
        self._ai_timer = None
        self._create_ui()
        self._populate_constants_table()

    def _create_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Column mapping section
        self.mapping_label = QtWidgets.QLabel("Column Mapping")
        font = self.mapping_label.font()
        font.setBold(True)
        self.mapping_label.setFont(font)
        layout.addWidget(self.mapping_label)

        self.mapping_table = QtWidgets.QTableWidget(0, 3)
        self.mapping_table.setHorizontalHeaderLabels(["Column Name", "Mapped Property", "Duplicate Key?"])
        self.mapping_table.verticalHeader().setVisible(False)
        self.mapping_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mapping_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.mapping_table)

        self.suggest_button = QtWidgets.QPushButton("Suggest Mappings")
        self.suggest_button.clicked.connect(self._suggest_mappings)
        layout.addWidget(self.suggest_button)

        self.ai_suggest_button = QtWidgets.QPushButton("AI Suggest")
        self.ai_suggest_button.clicked.connect(self._ai_suggest_mappings)
        layout.addWidget(self.ai_suggest_button)

        # Always says what the last AI attempt did (and what it is doing while it runs), so the
        # operator never has to ask someone else to check from the server side.
        self.ai_status_label = QtWidgets.QLabel("")
        self.ai_status_label.setWordWrap(True)
        layout.addWidget(self.ai_status_label)

        # Project constants section
        self.constants_label = QtWidgets.QLabel("Project Constants")
        font = self.constants_label.font()
        font.setBold(True)
        self.constants_label.setFont(font)
        layout.addWidget(self.constants_label)

        self.constants_table = QtWidgets.QTableWidget(0, 2)
        self.constants_table.setHorizontalHeaderLabels(["Property ID", "Value"])
        self.constants_table.verticalHeader().setVisible(False)
        self.constants_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.constants_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.constants_table)

    def _populate_constants_table(self):
        """Fill the constants table from the loaded constants DataFrame."""
        self.constants_table.setRowCount(len(self.constants_df))
        for row, (_, row_data) in enumerate(self.constants_df.iterrows()):
            prop_item = QtWidgets.QTableWidgetItem(str(row_data['property_id']))
            val_item = QtWidgets.QTableWidgetItem(str(row_data['value']))
            prop_item.setFlags(prop_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            val_item.setFlags(val_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.constants_table.setItem(row, 0, prop_item)
            self.constants_table.setItem(row, 1, val_item)
        self.constants_table.resizeColumnsToContents()

    def _add_mapping_row(self, col_str):
        """Append one mapping-table row for col_str and register it in
        column_mapping. Shared by set_columns (fresh table) and add_columns
        (appending to an existing one) so both stay in sync."""
        row = self.mapping_table.rowCount()
        self.mapping_table.insertRow(row)

        col_item = QtWidgets.QTableWidgetItem(col_str)
        col_item.setFlags(col_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
        self.mapping_table.setItem(row, 0, col_item)

        combo = QtWidgets.QComboBox()
        combo.addItem("-- Select --", None)
        for _, prop in self.properties_df.iterrows():
            label = str(prop['label'])
            pid = str(prop['property_id'])
            combo.addItem(f"{label} ({pid})", pid)
        combo.currentIndexChanged.connect(
            lambda index, r=row, cb=combo: self._on_combo_changed(r, cb)
        )
        self.mapping_table.setCellWidget(row, 1, combo)
        self.column_mapping[col_str] = None

        # Duplicate key checkbox
        check_item = QtWidgets.QTableWidgetItem()
        check_item.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled)
        check_item.setCheckState(QtCore.Qt.CheckState.Unchecked)
        self.mapping_table.setItem(row, 2, check_item)

    def set_columns(self, columns):
        """Populate the mapping table with one row per column, discarding
        any existing mapping. Keys are normalized to strings."""
        self.mapping_table.setRowCount(0)
        self.column_mapping = {}
        self.duplicate_key_columns = set()
        for col in columns:
            self._add_mapping_row(str(col))
        self.mapping_table.resizeColumnsToContents()

    def add_columns(self, new_columns):
        """Append mapping rows for columns not already present, leaving
        existing rows (and their mappings/duplicate-key checks) untouched --
        e.g. after core.photo_metadata_merge adds columns to already-mapped
        data, so a prior mapping pass isn't lost."""
        added = False
        for col in new_columns:
            col_str = str(col)
            if col_str in self.column_mapping:
                continue
            self._add_mapping_row(col_str)
            added = True
        if added:
            self.mapping_table.resizeColumnsToContents()

    def set_preview_df(self, df):
        """Store a preview DataFrame for AI mapping sample extraction."""
        self.preview_df = df

    def _on_combo_changed(self, row, combo):
        """Update the mapping when a combo selection changes."""
        col_name = self.mapping_table.item(row, 0).text()  # already a string
        self.column_mapping[col_name] = combo.currentData()

    def _suggest_mappings(self):
        """Use fuzzy matching to set combo boxes automatically."""
        columns = list(self.column_mapping.keys())  # strings
        if not columns:
            return
        suggested = suggest_mappings(columns, self.properties_df)
        for row in range(self.mapping_table.rowCount()):
            col_name = self.mapping_table.item(row, 0).text()
            pid = suggested.get(col_name)
            combo = self.mapping_table.cellWidget(row, 1)
            if pid:
                idx = combo.findData(pid)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    self.column_mapping[col_name] = pid
                else:
                    combo.setCurrentIndex(0)
                    self.column_mapping[col_name] = None
            else:
                combo.setCurrentIndex(0)
                self.column_mapping[col_name] = None

    def _apply_ai_mappings(self, mappings):
        """Apply a list of {"column", "label"} suggestions (from Morpheus or
        the Advanced custom endpoint) to the mapping table, resolving each
        label to a local property_id via the reference table (falling back
        to a fuzzy match). Returns how many columns it actually mapped.

        Shared by every AI mapping path so there's exactly one place that
        does this instead of three near-identical copies. The caller says what
        happened; this only changes the table.
        """
        label_to_pid = {}
        for _, prop in self.properties_df.iterrows():
            label = str(prop["label"]).strip().lower()
            pid = str(prop["property_id"]).strip()
            label_to_pid[label] = pid

        applied_count = 0
        for entry in mappings:
            col = entry.get("column")
            label = entry.get("label")
            if not col or not label:
                continue
            if col not in self.column_mapping:
                continue
            label_lower = str(label).strip().lower()
            pid = label_to_pid.get(label_lower)
            if pid is None:
                # fuzzy match using suggest_mappings for this single column
                temp_mapping = suggest_mappings([col], self.properties_df)
                pid = temp_mapping.get(col)
            if pid:
                row = list(self.column_mapping.keys()).index(col)
                combo = self.mapping_table.cellWidget(row, 1)
                if combo:
                    idx = combo.findData(pid)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                        self.column_mapping[col] = pid
                        applied_count += 1
        return applied_count

    # --- AI suggestion: off the GUI thread, with an elapsed line and a verdict -----------------

    def _build_samples(self, columns):
        """Column headers + up to 5 sample rows, each a list of stringified values in column order."""
        samples = []
        for _, row in self.preview_df.head(5).iterrows():
            sample_row = []
            for col in columns:
                value = row.get(col, "")
                if pd.isna(value):
                    value = ""
                sample_row.append(str(value))
            samples.append(sample_row)
        return samples

    def _begin_ai_feedback(self):
        """The button is disabled and the panel says what it is doing, from the click onwards."""
        self.ai_suggest_button.setEnabled(False)
        self.ai_suggest_button.setText(feedback.CHECKING_TEXT)
        self.ai_status_label.setText(feedback.CHECKING_CONNECTION_TEXT)

    def _start_ai_elapsed(self, what):
        """Start the ticking elapsed line. A static spinner is not alive enough for a 21 s wait."""
        self._ai_busy_source = what
        self.ai_suggest_button.setText(feedback.busy_button_text(what))
        self._ai_started_at = time.monotonic()
        if self._ai_timer is None:
            self._ai_timer = QtCore.QTimer(self)
            self._ai_timer.setInterval(1000)
            self._ai_timer.timeout.connect(self._tick_ai_elapsed)
        self._ai_timer.start()
        self._tick_ai_elapsed()

    def _tick_ai_elapsed(self):
        if self._ai_started_at is None:
            return
        elapsed = time.monotonic() - self._ai_started_at
        self.ai_status_label.setText(feedback.busy_text(self._ai_busy_source, elapsed))

    def _finish_ai_feedback(self, text):
        """The single exit from every AI path: the action is usable again and the panel says what
        happened. There is no fourth state."""
        if self._ai_timer is not None:
            self._ai_timer.stop()
        self._ai_started_at = None
        self.ai_suggest_button.setEnabled(True)
        self.ai_suggest_button.setText("AI Suggest")
        self.ai_status_label.setText(text)

    def _run_ai_call(self, call, on_done, on_failed):
        """Run a blocking AI call on a worker thread, so the elapsed line can keep ticking."""
        worker = AiMappingWorker(call, self)
        worker.done.connect(on_done)
        worker.failed.connect(on_failed)
        self._ai_worker = worker
        worker.start()

    def _ai_suggest_mappings(self):
        """Suggest column mappings via AI. Tries, in order:
          1. Morpheus Connect (core.credential_storage's saved device token)
             -- the primary path, billed to the operator's own Morpheus
             account. Connect via Settings.
          2. The Advanced custom AI endpoint (Settings), for an operator who
             deliberately wants to bring their own.
          3. Local (non-AI) suggestion, if neither is configured or the call
             fails.

        Both the keychain read and the AI call run off the GUI thread: on
        2026-10-01 a 21.1 s Morpheus call succeeded while the window was frozen
        and showed nothing. While it runs the action is disabled, relabelled and
        an elapsed line ticks; every path ends with a sentence saying what
        happened.
        """
        columns = list(self.column_mapping.keys())
        if not columns:
            QtWidgets.QMessageBox.warning(self, "No Columns", "No columns to map.")
            return

        if self.preview_df is None or self.preview_df.empty:
            QtWidgets.QMessageBox.warning(
                self,
                "No Data",
                "No preview data available for AI suggestion."
            )
            return

        self._ai_columns = columns
        self._ai_samples = self._build_samples(columns)
        self._begin_ai_feedback()

        # A keychain read can block on an authorisation prompt, so it must not run on the GUI
        # thread (see ui/keychain_read.py). "did not answer" is reported as itself, never as
        # "not connected", which is a different fact.
        self._token_read = KeychainRead(credential_storage.load_morpheus_token, parent=self)
        self._token_read.finished_read.connect(self._on_morpheus_token_read)

    def _on_morpheus_token_read(self, outcome):
        if outcome.status != blocking_read.ANSWERED:
            self._finish_ai_feedback(feedback.morpheus_read_failed_text(outcome))
            self._suggest_mappings()
            return
        if not outcome.value:
            self._ai_without_morpheus()
            return
        self._start_ai_elapsed(feedback.MORPHEUS)
        self._run_ai_call(
            lambda: suggest_mappings_with_morpheus(self._ai_columns, self._ai_samples, outcome.value),
            self._on_morpheus_mappings_done,
            self._on_morpheus_mappings_failed,
        )

    def _ai_without_morpheus(self):
        """The Advanced custom-endpoint path, or local suggestion if that is not set up."""
        endpoint = app_settings.get_ai_endpoint_url()
        if not endpoint:
            self._finish_ai_feedback(feedback.NOT_CONFIGURED_TEXT)
            self._suggest_mappings()
            return
        api_key = app_settings.get_ai_api_key()
        self._start_ai_elapsed('the AI endpoint')
        self._run_ai_call(
            lambda: self._ask_custom_endpoint(endpoint, api_key),
            self._on_custom_mappings_done,
            self._on_custom_mappings_failed,
        )

    def _ask_custom_endpoint(self, endpoint, api_key):
        """POST the samples to the operator's own endpoint and return its mappings list.

        Raises on any failure; the worker reports it and the panel says something plain while the
        raw text goes to the log.
        """
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = requests.post(
            endpoint,
            json={"columns": self._ai_columns, "samples": self._ai_samples},
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        mappings = response.json().get("mappings", [])
        if not isinstance(mappings, list):
            raise ValueError("the endpoint returned an unexpected response shape")
        return mappings

    def _on_morpheus_mappings_done(self, suggestion):
        if suggestion.mappings:
            applied = self._apply_ai_mappings(suggestion.mappings)
            self._finish_ai_feedback(
                feedback.apply_verdict_text(feedback.MORPHEUS, applied, len(self._ai_columns))
            )
            return
        # Name the reason when there is one: a 500 from the server, a timeout and a genuinely
        # empty answer are different problems for the operator.
        self._finish_ai_feedback(feedback.morpheus_fallback_text(suggestion.error))
        self._suggest_mappings()

    def _on_morpheus_mappings_failed(self, detail):
        # suggest_mappings_with_morpheus reports its own failures, so reaching here is a bug --
        # log it, and still say plainly what the panel did.
        logger.warning("Morpheus mapping call failed unexpectedly: %s", detail)
        self._finish_ai_feedback(feedback.MORPHEUS_FAILED_TEXT)
        self._suggest_mappings()

    def _on_custom_mappings_done(self, mappings):
        applied = self._apply_ai_mappings(mappings)
        self._finish_ai_feedback(
            feedback.apply_verdict_text('The AI endpoint', applied, len(self._ai_columns))
        )

    def _on_custom_mappings_failed(self, detail):
        logger.warning("Custom AI endpoint mapping call failed: %s", detail)
        self._finish_ai_feedback(feedback.CUSTOM_ENDPOINT_FAILED_TEXT)
        self._suggest_mappings()

    def get_column_mapping(self):
        """Return the current mapping as a dict column_name -> property_id."""
        return self.column_mapping

    def get_duplicate_key_columns(self):
        """Return a list of column names marked as duplicate keys."""
        duplicate_cols = []
        for row in range(self.mapping_table.rowCount()):
            check_item = self.mapping_table.item(row, 2)
            if check_item and check_item.checkState() == QtCore.Qt.CheckState.Checked:
                col_name = self.mapping_table.item(row, 0).text()
                duplicate_cols.append(col_name)
        return duplicate_cols
