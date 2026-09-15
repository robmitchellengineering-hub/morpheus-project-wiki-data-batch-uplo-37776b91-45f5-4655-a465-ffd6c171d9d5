import os
from pathlib import Path
import sys

APP_NAME = "Wikidata Batch Uploader"
APP_VERSION = "0.1.0"


def get_base_dir() -> Path:
    """Return the directory for writable data files.

    In development, this is the project root. In a frozen (PyInstaller)
    executable, this is a user-writable directory under %APPDATA%
    so that reference tables persist and can be edited without
    administrator rights.
    """
    if getattr(sys, 'frozen', False):
        appdata = os.getenv('APPDATA')
        if appdata:
            base = Path(appdata) / 'WikidataBatchUploader'
        else:
            base = Path.home() / '.wikidata_batch_uploader'
        base.mkdir(parents=True, exist_ok=True)
        return base
    else:
        return Path(__file__).parent


BASE_DIR = get_base_dir()
REFERENCE_TABLES_DIR = BASE_DIR / 'reference_tables'
