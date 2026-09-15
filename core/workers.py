from PyQt6.QtCore import QThread, pyqtSignal
import pandas as pd

from core import uploader, duplicate_checker


class DryRunWorker(QThread):
    """Worker thread that runs a dry-run analysis without blocking the UI."""

    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, df: pd.DataFrame, mapping: dict, constants_df: pd.DataFrame,
                 properties_df: pd.DataFrame | None = None, parent=None):
        super().__init__(parent)
        self.df = df
        self.mapping = mapping
        self.constants_df = constants_df
        self.properties_df = properties_df

    def run(self):
        try:
            result = uploader.dry_run(self.df, self.mapping, self.constants_df, self.properties_df)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class UploadWorker(QThread):
    """Worker thread that uploads rows to Wikidata without blocking the UI."""

    progress = pyqtSignal(int, int, str)  # done_count, total_count, item_id
    finished = pyqtSignal(int)            # uploaded count
    error = pyqtSignal(str)

    def __init__(self, login, df: pd.DataFrame, mapping: dict, constants_df: pd.DataFrame,
                 edit_summary: str, delay_seconds: float = 1.0, maxlag: float = 5.0,
                 skip_rows: set | None = None, parent=None):
        super().__init__(parent)
        self.login = login
        self.df = df
        self.mapping = mapping
        self.constants_df = constants_df
        self.edit_summary = edit_summary
        self.delay_seconds = delay_seconds
        self.maxlag = maxlag
        self.skip_rows = skip_rows

    def run(self):
        try:
            def progress_cb(done: int, total: int, item_id: str):
                self.progress.emit(done, total, item_id)

            uploaded = uploader.upload_rows(
                self.login,
                self.df,
                self.mapping,
                self.constants_df,
                self.edit_summary,
                callback=progress_cb,
                delay_seconds=self.delay_seconds,
                maxlag=self.maxlag,
                skip_rows=self.skip_rows
            )
            self.finished.emit(uploaded)
        except Exception as e:
            self.error.emit(str(e))


class DuplicateCheckExistingWorker(QThread):
    """Worker thread that checks rows against existing Wikidata items without blocking the UI."""

    progress = pyqtSignal(int, int)   # done_count, total_count
    finished = pyqtSignal(dict)       # {row_index: [qid, ...]}
    error = pyqtSignal(str)

    def __init__(self, df: pd.DataFrame, mapping: dict, duplicate_key_columns: list,
                 parent=None):
        super().__init__(parent)
        self.df = df
        self.mapping = mapping
        self.duplicate_key_columns = duplicate_key_columns

    def run(self):
        try:
            total = len(self.df)
            results = {}
            for done_count, (idx, row) in enumerate(self.df.iterrows(), start=1):
                qids = duplicate_checker.find_existing_items(
                    row, self.mapping, self.duplicate_key_columns
                )
                if qids:
                    results[idx] = qids
                self.progress.emit(done_count, total)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
