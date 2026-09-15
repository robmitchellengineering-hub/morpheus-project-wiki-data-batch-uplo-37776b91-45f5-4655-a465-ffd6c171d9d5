import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

from core.data_loader import load_dataframe_full


class DataLoadingWorker(QThread):
    """Worker thread that loads a full DataFrame from disk without blocking the UI."""

    finished = pyqtSignal(pd.DataFrame)
    error = pyqtSignal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        """Load the full dataset and emit the result."""
        try:
            df = load_dataframe_full(self.file_path)
            self.finished.emit(df)
        except Exception as e:
            self.error.emit(str(e))
