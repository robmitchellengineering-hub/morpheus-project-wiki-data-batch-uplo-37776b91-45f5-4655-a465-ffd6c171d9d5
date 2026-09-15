import pandas as pd
from pathlib import Path


def load_dataframe_full(file_path):
    """Load the full tabular file into a pandas DataFrame.

    Supports .csv and .xlsx. For CSV, tries UTF-8 first, then latin-1.
    For Excel, reads the first sheet.

    Args:
        file_path: Path to the file.

    Returns:
        pandas.DataFrame

    Raises:
        ValueError: If the file extension is not supported.
        Exception: For any parsing error with a clear message.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == '.csv':
        try:
            df = pd.read_csv(path, encoding='utf-8')
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(path, encoding='latin-1')
            except Exception as e:
                raise Exception(f"Failed to read CSV file: {e}")
        except Exception as e:
            raise Exception(f"Failed to read CSV file: {e}")
        return df

    elif ext in ('.xlsx', '.xlsm'):
        try:
            df = pd.read_excel(path, engine='openpyxl')
        except Exception as e:
            raise Exception(f"Failed to read Excel file: {e}")
        return df

    else:
        raise ValueError(f"Unsupported file type: {ext}")


def load_dataframe_preview(file_path, max_rows=500):
    """Load only the first max_rows rows of a tabular file.

    Supports .csv and .xlsx. For CSV, tries UTF-8 first, then latin-1.
    For Excel, reads the first sheet.

    Args:
        file_path: Path to the file.
        max_rows: Maximum number of rows to load (default 500).

    Returns:
        pandas.DataFrame containing at most max_rows rows.

    Raises:
        ValueError: If the file extension is not supported.
        Exception: For any parsing error with a clear message.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == '.csv':
        try:
            df = pd.read_csv(path, encoding='utf-8', nrows=max_rows)
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(path, encoding='latin-1', nrows=max_rows)
            except Exception as e:
                raise Exception(f"Failed to read CSV file: {e}")
        except Exception as e:
            raise Exception(f"Failed to read CSV file: {e}")
        return df

    elif ext in ('.xlsx', '.xlsm'):
        try:
            df = pd.read_excel(path, engine='openpyxl', nrows=max_rows)
        except Exception as e:
            raise Exception(f"Failed to read Excel file: {e}")
        return df

    else:
        raise ValueError(f"Unsupported file type: {ext}")


# Backwards compatibility alias
load_dataframe = load_dataframe_full
