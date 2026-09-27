import os
import json
import pandas as pd
import requests
from PyQt6 import QtCore, QtWidgets
from core.schema_mapper import suggest_mappings
from core import credential_storage
from core import settings as app_settings
from core.morpheus_connect import suggest_mappings_with_morpheus


class MappingPanel(QtWidgets.QWidget):
    """Widget for mapping dataframe columns to Wikidata properties and showing project constants."""

    def __init__(self, properties_df, constants_df, parent=None):
        super().__init__(parent)
        self.properties_df = properties_df
        self.constants_df = constants_df
        self.column_mapping = {}  # column name (string) -> property_id or None
        self.duplicate_key_columns = set()
        self.preview_df = None  # dataframe sample for AI mapping
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

    def _apply_ai_mappings(self, mappings, source_label):
        """Apply a list of {"column", "label"} suggestions (from Morpheus or
        the Advanced custom endpoint) to the mapping table, resolving each
        label to a local property_id via the reference table (falling back
        to a fuzzy match). Shows one summary message box either way.

        Shared by every AI mapping path so there's exactly one place that
        does this instead of three near-identical copies.
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

        if applied_count == 0:
            QtWidgets.QMessageBox.information(
                self, "AI Mapping", f"{source_label} returned no usable mapping suggestions."
            )
        else:
            QtWidgets.QMessageBox.information(
                self, "AI Mapping", f"{source_label} mapping applied for {applied_count} column(s)."
            )

    def _ai_suggest_mappings(self):
        """Suggest column mappings via AI. Tries, in order:
          1. Morpheus Connect (core.credential_storage's saved device token)
             -- the primary path, billed to the operator's own Morpheus
             account. Connect via Settings.
          2. The Advanced custom AI endpoint (Settings), for an operator who
             deliberately wants to bring their own.
          3. Local (non-AI) suggestion, if neither is configured or the call
             fails.
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

        # Build sample data: column headers + up to 5 sample rows
        sample_df = self.preview_df.head(5)
        samples = []
        for _, row in sample_df.iterrows():
            sample_row = []
            for col in columns:
                value = row.get(col, "")
                if pd.isna(value):
                    value = ""
                sample_row.append(str(value))
            samples.append(sample_row)

        morpheus_token = credential_storage.load_morpheus_token()
        if morpheus_token:
            suggestion = suggest_mappings_with_morpheus(columns, samples, morpheus_token)
            if suggestion.mappings:
                self._apply_ai_mappings(suggestion.mappings, "Morpheus")
            else:
                # Name the reason when there is one: a 500 from the server and a
                # genuinely empty answer are different problems for the operator.
                reason = suggestion.error or "Morpheus returned no suggestions for these columns."
                QtWidgets.QMessageBox.information(
                    self,
                    "AI Mapping",
                    f"{reason}\n\nFalling back to local suggestion."
                )
                self._suggest_mappings()
            return

        # Advanced: custom AI endpoint (Settings), only used when Morpheus
        # Connect isn't set up.
        endpoint = app_settings.get_ai_endpoint_url()
        if not endpoint:
            QtWidgets.QMessageBox.information(
                self,
                "AI Mapping Not Configured",
                "Connect to Morpheus in Settings to use AI mapping suggestions "
                "(or configure a custom endpoint under Advanced).\n\n"
                "Falling back to local suggestion."
            )
            self._suggest_mappings()
            return

        payload = {"columns": columns, "samples": samples}
        headers = {"Content-Type": "application/json"}
        api_key = app_settings.get_ai_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            result = response.json()
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "AI Mapping Failed",
                f"Could not contact the AI endpoint:\n{e}\n\nFalling back to local suggestion."
            )
            self._suggest_mappings()
            return

        mappings = result.get("mappings", [])
        if not isinstance(mappings, list):
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid AI Response",
                "The AI endpoint returned an unexpected response.\nFalling back to local suggestion."
            )
            self._suggest_mappings()
            return

        self._apply_ai_mappings(mappings, "AI endpoint")

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
