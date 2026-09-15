import pandas as pd
from PyQt6 import QtCore, QtGui, QtWidgets


class PandasModel(QtCore.QAbstractTableModel):
    """A read-only table model that wraps a pandas DataFrame."""

    def __init__(self, data: pd.DataFrame):
        super().__init__()
        self._data = data

    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return self._data.shape[0]

    def columnCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return self._data.shape[1]

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]
            # Handle NaN and other non-string values gracefully
            if pd.isna(value):
                return ''
            return str(value)
        return None

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == QtCore.Qt.Orientation.Horizontal:
            return str(self._data.columns[section])
        else:
            return str(self._data.index[section])

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags
        return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable

    def get_dataframe(self):
        return self._data


class PreviewTableWidget(QtWidgets.QTableView):
    """QTableView configured for previewing data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setStretchLastSection(True)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(True)
        self.setSortingEnabled(False)

    def set_dataframe(self, df: pd.DataFrame):
        model = PandasModel(df)
        self.setModel(model)
        # Avoid UI freeze on large DataFrames by limiting column auto-resizing
        if df.shape[0] <= 1000:
            self.resizeColumnsToContents()
        else:
            self.horizontalHeader().setDefaultSectionSize(150)
        self.horizontalHeader().setStretchLastSection(True)
