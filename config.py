import os
from pathlib import Path
import sys

APP_NAME = "Wikidata Batch Uploader"
APP_VERSION = "0.1.0"
DATA_DIR_NAME = "WikidataBatchUploader"


def get_base_dir() -> Path:
    """Return the directory for writable data files.

    In development, this is the project root. In a frozen (PyInstaller)
    executable, this is a user-writable directory that follows the
    platform convention:
      - Windows: %APPDATA%\\WikidataBatchUploader
      - macOS:   ~/Library/Application Support/WikidataBatchUploader
      - Linux:   $XDG_DATA_HOME/WikidataBatchUploader or
                 ~/.local/share/WikidataBatchUploader
    so that reference tables persist and can be edited without
    administrator rights.
    """
    if getattr(sys, 'frozen', False):
        if sys.platform == 'win32':
            appdata = os.getenv('APPDATA')
            base = Path(appdata) / DATA_DIR_NAME if appdata else Path.home() / '.wikidata_batch_uploader'
        elif sys.platform == 'darwin':
            base = Path.home() / 'Library' / 'Application Support' / DATA_DIR_NAME
        else:  # Linux and other POSIX
            xdg_data_home = os.getenv('XDG_DATA_HOME')
            if xdg_data_home:
                base = Path(xdg_data_home) / DATA_DIR_NAME
            else:
                base = Path.home() / '.local' / 'share' / DATA_DIR_NAME
        base.mkdir(parents=True, exist_ok=True)
        return base
    else:
        return Path(__file__).parent


BASE_DIR = get_base_dir()
REFERENCE_TABLES_DIR = BASE_DIR / 'reference_tables'
