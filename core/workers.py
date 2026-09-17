import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal
from typing import Optional, Dict, List, Set, Any

from core.uploader import upload_rows, dry_run
from core.duplicate_checker import find_existing_items


class DryRunWorker(QThread):
    """Worker thread for performing a dry run without blocking the UI."""
    finished = pyqtSignal(str)  # summary string
    error = pyqtSignal(str)

    def __init__(self, df: pd.DataFrame, mapping: Dict[str, Optional[str]], constants_df: pd.DataFrame, properties_df: Optional[pd.DataFrame] = None, parent=None):
        super().__init__(parent)
        self.df = df
        self.mapping = mapping
        self.constants_df = constants_df
        self.properties_df = properties_df

    def run(self):
        try:
            result = dry_run(self.df, self.mapping, self.constants_df, self.properties_df)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class UploadWorker(QThread):
    """Worker thread for uploading rows to Wikidata."""
    progress = pyqtSignal(int, int, str)  # done, total, item_id
    finished = pyqtSignal(int)  # number of rows successfully uploaded
    error = pyqtSignal(str)

    def __init__(self, login, df: pd.DataFrame, mapping: Dict[str, Optional[str]], constants_df: pd.DataFrame, edit_summary: str, delay_seconds: float = 1.0, maxlag: float = 5.0, skip_rows: Optional[Set[int]] = None, parent=None):
        super().__init__(parent)
        self.login = login
        self.df = df
        self.mapping = mapping
        self.constants_df = constants_df
        self.edit_summary = edit_summary
        self.delay_seconds = delay_seconds
        self.maxlag = maxlag
        self.skip_rows = skip_rows if skip_rows is not None else set()

    def run(self):
        try:
            count = upload_rows(
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
            self.finished.emit(count)
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, done, total, item_id):
        self.progress.emit(done, total, item_id)


class DuplicateCheckExistingWorker(QThread):
    """Worker thread that checks each row for existing Wikidata items using duplicate key columns."""
    progress = pyqtSignal(int, int)  # done, total
    finished = pyqtSignal(list)      # list of row indices (original DataFrame indices)
    error = pyqtSignal(str)

    def __init__(self, df: pd.DataFrame, mapping: Dict[str, Optional[str]], duplicate_key_columns: List[str], parent=None):
        super().__init__(parent)
        self.df = df
        self.mapping = mapping
        self.duplicate_key_columns = duplicate_key_columns

    def run(self):
        found = []
        total = len(self.df)
        try:
            for i, (idx, row) in enumerate(self.df.iterrows()):
                if self.duplicate_key_columns:
                    existing = find_existing_items(row, self.mapping, self.duplicate_key_columns)
                    if existing:
                        found.append(idx)
                self.progress.emit(i + 1, total)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit(found)


class CommonsUploadWorker(QThread):
    """Worker thread for uploading files to Wikimedia Commons."""
    progress = pyqtSignal(int, int, str)  # done, total, message
    finished = pyqtSignal(str)            # summary string
    error = pyqtSignal(str)

    def __init__(self, file_paths, metadata_list, category, license_template, edit_summary,
                 chunk_size=None, parent=None):
        super().__init__(parent)
        self.file_paths = list(file_paths)
        self.metadata_list = list(metadata_list)
        self.category = category
        self.license_template = license_template
        self.edit_summary = edit_summary
        self.chunk_size = chunk_size

    def run(self):
        try:
            import os
            from core.commons_uploader import upload_file

            if len(self.file_paths) != len(self.metadata_list):
                raise ValueError("File list and metadata list lengths do not match.")

            total = len(self.file_paths)
            success_count = 0
            errors = []

            for i, (file_path, metadata) in enumerate(zip(self.file_paths, self.metadata_list)):
                try:
                    merged_metadata = dict(metadata)
                    merged_metadata.setdefault('category', self.category)
                    merged_metadata.setdefault('license_template', self.license_template)
                    upload_file(file_path, merged_metadata, edit_summary=self.edit_summary)
                    success_count += 1
                    self.progress.emit(i + 1, total, os.path.basename(file_path))
                except Exception as e:
                    errors.append(f"{os.path.basename(file_path)}: {e}")
                    self.progress.emit(i + 1, total, f"ERROR: {e}")

            summary = f"{success_count} of {total} file(s) uploaded successfully."
            if errors:
                summary += "\nErrors:\n" + "\n".join(errors)
            self.finished.emit(summary)
        except Exception as e:
            self.error.emit(str(e))
