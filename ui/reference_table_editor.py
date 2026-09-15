from PyQt6 import QtCore, QtWidgets
import pandas as pd
from core.reference_tables import load_wikidata_properties, load_project_constants, save_wikidata_properties, save_project_constants
from config import REFERENCE_TABLES_DIR


class ReferenceTableEditor(QtWidgets.QDialog):
    """Dialog for editing local reference tables (wikidata_properties.xlsx and project_constants.xlsx)."""

    def __init__(self, ref_dir=None, parent=None):
        super().__init__(parent)
        if ref_dir is None:
            ref_dir = REFERENCE_TABLES_DIR
        self.ref_dir = ref_dir
        self.setWindowTitle("Edit Reference Tables")
        self.setModal(True)
        self.resize(600, 400)
        self._create_ui()
        self._load_data()

    def _create_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        self.tab_widget = QtWidgets.QTabWidget()
        layout.addWidget(self.tab_widget)

        # Properties tab
        self.properties_tab = QtWidgets.QWidget()
        self.tab_widget.addTab(self.properties_tab, "Wikidata Properties")
        self._setup_table_tab(self.properties_tab, ["Property ID", "Label"], "properties")

        # Constants tab
        self.constants_tab = QtWidgets.QWidget()
        self.tab_widget.addTab(self.constants_tab, "Project Constants")
        self._setup_table_tab(self.constants_tab, ["Property ID", "Value"], "constants")

        # Dialog buttons
        button_layout = QtWidgets.QHBoxLayout()
        self.save_button = QtWidgets.QPushButton("Save")
        self.save_button.clicked.connect(self._save)
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def _setup_table_tab(self, tab_widget, headers, attr_name):
        layout = QtWidgets.QVBoxLayout(tab_widget)
        table = QtWidgets.QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)

        # Store table reference
        setattr(self, f"{attr_name}_table", table)

        # Row buttons
        row_buttons = QtWidgets.QHBoxLayout()
        add_button = QtWidgets.QPushButton("Add Row")
        add_button.clicked.connect(lambda: self._add_row(table))
        delete_button = QtWidgets.QPushButton("Delete Row")
        delete_button.clicked.connect(lambda: self._delete_row(table))
        row_buttons.addWidget(add_button)
        row_buttons.addWidget(delete_button)
        row_buttons.addStretch()
        layout.addLayout(row_buttons)

    def _load_data(self):
        try:
            properties_df = load_wikidata_properties(self.ref_dir)
        except Exception:
            properties_df = pd.DataFrame(columns=['property_id', 'label'])
        self._populate_table(self.properties_table, properties_df, ['property_id', 'label'])

        try:
            constants_df = load_project_constants(self.ref_dir)
        except Exception:
            constants_df = pd.DataFrame(columns=['property_id', 'value'])
        self._populate_table(self.constants_table, constants_df, ['property_id', 'value'])

    def _populate_table(self, table, df, columns):
        table.setRowCount(len(df))
        for row_idx, (_, row) in enumerate(df.iterrows()):
            for col_idx, col in enumerate(columns):
                value = row[col]
                if value is not None:
                    item = QtWidgets.QTableWidgetItem(str(value))
                else:
                    item = QtWidgets.QTableWidgetItem("")
                table.setItem(row_idx, col_idx, item)

    def _add_row(self, table):
        row = table.rowCount()
        table.insertRow(row)
        for col in range(table.columnCount()):
            table.setItem(row, col, QtWidgets.QTableWidgetItem(""))

    def _delete_row(self, table):
        selected_rows = set()
        for item in table.selectedItems():
            selected_rows.add(item.row())
        rows_to_delete = sorted(selected_rows, reverse=True)
        for row in rows_to_delete:
            table.removeRow(row)

    def _collect_table_data(self, table):
        data = []
        for row in range(table.rowCount()):
            row_data = []
            for col in range(table.columnCount()):
                item = table.item(row, col)
                text = item.text().strip() if item else ""
                row_data.append(text)
            data.append(row_data)
        return data

    def _validate_rows(self, data):
        """Check that all fields are non-empty."""
        for row in data:
            if not all(field for field in row):
                QtWidgets.QMessageBox.warning(self, "Validation Error", "All fields must be non-empty.")
                return False
        return True

    def _is_valid_property_id(self, pid):
        """Property ID must be like 'P123'."""
        pid = pid.strip()
        return pid.startswith('P') and pid[1:].isdigit()

    def _is_valid_qid(self, value):
        """QID must be like 'Q123'."""
        value = value.strip()
        return value.startswith('Q') and value[1:].isdigit()

    def _save(self):
        properties_data = self._collect_table_data(self.properties_table)
        constants_data = self._collect_table_data(self.constants_table)

        # Enforce at least one row per table
        if not properties_data:
            QtWidgets.QMessageBox.warning(self, "Validation Error", "Wikidata Properties table must have at least one row.")
            return
        if not constants_data:
            QtWidgets.QMessageBox.warning(self, "Validation Error", "Project Constants table must have at least one row.")
            return

        # Check non-empty fields
        if not self._validate_rows(properties_data):
            return
        if not self._validate_rows(constants_data):
            return

        # Validate property ID format for properties table
        for row in properties_data:
            if not self._is_valid_property_id(row[0]):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Validation Error",
                    f"Invalid Property ID '{row[0]}'. Must start with 'P' followed by digits."
                )
                return

        # Validate constants table: property ID format and value QID format
        for row in constants_data:
            if not self._is_valid_property_id(row[0]):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Validation Error",
                    f"Invalid Property ID '{row[0]}' in Project Constants. Must start with 'P' followed by digits."
                )
                return
            if not self._is_valid_qid(row[1]):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Validation Error",
                    f"Invalid Value '{row[1]}' in Project Constants. Must start with 'Q' followed by digits."
                )
                return

        # Check for duplicate property IDs in properties table
        property_ids = [row[0] for row in properties_data]
        if len(property_ids) != len(set(property_ids)):
            QtWidgets.QMessageBox.warning(self, "Validation Error", "Duplicate Property IDs found in Wikidata Properties table.")
            return

        # Save both tables
        try:
            properties_df = pd.DataFrame(properties_data, columns=["property_id", "label"])
            save_wikidata_properties(self.ref_dir, properties_df)

            constants_df = pd.DataFrame(constants_data, columns=["property_id", "value"])
            save_project_constants(self.ref_dir, constants_df)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save Error", f"Failed to save reference tables: {e}")
            return

        self.accept()
