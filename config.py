import os
import sys
from pathlib import Path

APP_NAME = "Wikidata Batch Uploader"
APP_VERSION = "0.1.0"
DATA_DIR_NAME = "WikidataBatchUploader"


def _frozen_data_dir(platform=None, environ=None, home=None) -> Path:
    """Compute the per-user data directory for a frozen build, without touching disk.

    A frozen (PyInstaller) executable can be installed somewhere read-only
    (e.g. ``C:\\Program Files``), so anything that must persist — credentials,
    OAuth tokens, settings, the diagnostic report, the crash log, and the
    *editable* reference tables — goes in the platform's per-user writable
    location:

      - Windows: %APPDATA%\\WikidataBatchUploader
      - macOS:   ~/Library/Application Support/WikidataBatchUploader
      - Linux:   $XDG_DATA_HOME/WikidataBatchUploader, or
                 ~/.local/share/WikidataBatchUploader when $XDG_DATA_HOME is unset

    The arguments exist only so tests can pin each branch without mocking the
    process; callers pass nothing in real use.
    """
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform == 'win32':
        appdata = environ.get('APPDATA')
        return Path(appdata) / DATA_DIR_NAME if appdata else home / '.wikidata_batch_uploader'
    if platform == 'darwin':
        return home / 'Library' / 'Application Support' / DATA_DIR_NAME
    xdg_data_home = environ.get('XDG_DATA_HOME')
    return Path(xdg_data_home) / DATA_DIR_NAME if xdg_data_home else home / '.local' / 'share' / DATA_DIR_NAME


def get_base_dir() -> Path:
    """Return the directory for writable data files, creating it if needed.

    In development this is the project root. In a frozen executable it is the
    platform's per-user writable directory (see `_frozen_data_dir`), so that
    user data persists and can be written without administrator rights.
    """
    if getattr(sys, 'frozen', False):
        base = _frozen_data_dir()
    else:
        base = Path(__file__).parent
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_reference_tables_dir() -> Path:
    """Return where the reference tables (wikidata_properties.xlsx,
    project_constants.xlsx) live.

    The tables are seeded with defaults on first run and then edited in place
    (in-app or in Excel), so they must live in a writable directory:

      - development: <project root>/reference_tables
      - frozen:      <user data dir>/reference_tables   (see get_base_dir)

    This is deliberate: the tables are NOT read from next to the executable. A
    frozen app may sit somewhere read-only, and edits there would fail or be
    lost on reinstall. The decision is documented in README.md ("Reference
    Tables") and pinned by tests/test_config_paths.py.
    """
    return get_base_dir() / 'reference_tables'


BASE_DIR = get_base_dir()
REFERENCE_TABLES_DIR = get_reference_tables_dir()
