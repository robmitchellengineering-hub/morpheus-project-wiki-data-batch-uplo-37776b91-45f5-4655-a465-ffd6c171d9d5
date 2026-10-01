"""Diagnostic utilities for the WikiData Batch Uploader.

This module provides a single function, run_diagnostics(), that can be
invoked from the command line (via --diagnose) to collect environment
information, package versions, and import test results for every module
in the application. The output is written to a timestamped file in the
application's base directory.
"""

import os
import sys
import importlib
import importlib.metadata
import threading
import traceback
import datetime
from pathlib import Path


def _ensure_base_dir() -> Path:
    """Return the writable base directory, creating if necessary."""
    # Try to use config.BASE_DIR; if that fails, fall back to APPDATA/UserProfile.
    try:
        import config
        base = config.BASE_DIR
    except Exception:
        appdata = os.getenv('APPDATA')
        if appdata:
            base = Path(appdata) / 'WikidataBatchUploader'
        else:
            base = Path.home() / '.wikidata_batch_uploader'
    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_env_snapshot() -> dict:
    """Return a snapshot of relevant environment variables (secrets redacted)."""
    env_keys = [
        'APPDATA', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH',
        'SYSTEMROOT', 'TEMP', 'TMP', 'OS', 'COMPUTERNAME',
        'PROCESSOR_ARCHITECTURE', 'PATH',
    ]
    return {key: os.environ.get(key, '<not set>') for key in env_keys}


# A KEYCHAIN READ CAN BLOCK FOREVER, AND THE SELF-TEST MUST NOT.
#
# MEASURED 2026-10-01 by running the app from a source checkout: `python main.py --diagnose` never finished
# and never printed a verdict. It was not the unreachable `return` alone — the run hung earlier, inside
# `_get_ai_config_snapshot`, on `credential_storage.load_morpheus_token()`. That reads the macOS Keychain,
# and when the item needs authorising from a process macOS has not seen before, the read blocks on a system
# prompt that never appears for a command-line run. The report was never written and the verdict was never
# reached, so the failure looked like "the app did nothing".
#
# A diagnostic that can hang is not a diagnostic. The read gets a deadline in a daemon thread; if the
# keychain does not answer, the snapshot says so and the run continues. A daemon thread cannot hold the
# process open, so a stuck read costs the timeout and nothing else.
KEYCHAIN_TIMEOUT_SECONDS = 5


def _read_with_timeout(read, seconds=KEYCHAIN_TIMEOUT_SECONDS):
    """Run `read()` in a daemon thread. Returns (answered, value); never blocks longer than `seconds`."""
    box = {}

    def run():
        try:
            box['value'] = read()
        except Exception as exc:  # the caller's own except turns this into a report line
            box['error'] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        return False, None
    if 'error' in box:
        raise box['error']
    return True, box.get('value')


def _get_ai_config_snapshot() -> dict:
    """Return AI mapping configuration status — Morpheus Connect first
    (the primary path), then the Advanced custom endpoint if that's what's
    actually configured instead. No env vars anymore (2026-09-15): AI
    mapping config used to be read from MORPHEUS_AI_ENDPOINT/
    MORPHEUS_AI_API_KEY/GEMINI_API_KEY/GEMINI_MODEL; it's now Settings ->
    Connect to Morpheus (or the Advanced endpoint fields), so that's what
    this reports instead."""
    try:
        from core import credential_storage
        from core import settings as app_settings
        answered, token = _read_with_timeout(credential_storage.load_morpheus_token)
        connected = bool(token) if answered else False
        snapshot = {'morpheus_connect': (
            ('connected' if connected else 'not connected') if answered
            else f'unknown - the keychain did not answer within {KEYCHAIN_TIMEOUT_SECONDS}s (it can be '
                 'waiting on an authorisation prompt; the rest of this report is unaffected)'
        )}
        if not connected:
            endpoint = app_settings.get_ai_endpoint_url()
            snapshot['advanced_endpoint'] = endpoint if endpoint else '<not set>'
            snapshot['advanced_api_key'] = f'<set, length {len(app_settings.get_ai_api_key())}>' if app_settings.get_ai_api_key() else '<not set>'
        return snapshot
    except Exception as exc:
        return {'error': f'Could not read AI config: {exc}'}


def _get_package_versions() -> dict:
    """Return versions for key packages, or error strings if not found."""
    packages = [
        'PyQt6', 'pandas', 'numpy', 'openpyxl', 'Pillow', 'exifread',
        'wikidataintegrator', 'requests', 'requests-oauthlib', 'oauthlib',
        'urllib3', 'certifi', 'idna', 'charset-normalizer', 'chardet', 'lxml',
    ]
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = 'NOT INSTALLED'
        except Exception as exc:
            versions[package] = f'ERROR: {exc}'
    return versions


def _run_import_tests() -> dict:
    """Attempt to import every core and ui module, recording results."""
    # Kept exhaustive on purpose: this list skipped core.commons_uploader and
    # ui.commons_upload_dialog — the two largest modules in the app — so the
    # self-test reported a clean sweep while importing neither of them.
    modules = [
        'core.commons_uploader',
        'core.credential_storage',
        'core.data_loader',
        'core.duplicate_checker',
        'core.morpheus_connect',
        'core.lazy_loader',
        'core.metadata_extractor',
        'core.photo_metadata_merge',
        'core.reference_tables',
        'core.schema_mapper',
        'core.settings',
        'core.uploader',
        'core.validator',
        'core.workers',
        'ui.auth_dialog',
        'ui.commons_upload_dialog',
        'ui.connect_dialog',
        'ui.image_preview',
        'ui.main_window',
        'ui.mapping_panel',
        'ui.mapping_view',
        'ui.photo_fill_dialog',
        'ui.preview_table',
        'ui.reference_table_editor',
        'ui.settings_dialog',
        'ui.styles',
    ]
    results = {}
    for module in modules:
        try:
            importlib.import_module(module)
            results[module] = 'OK'
        except Exception:
            results[module] = traceback.format_exc()
    return results


def run_diagnostics(base_dir=None) -> int:
    r"""Collect diagnostics, write a report, print the verdict and return its exit code.

    Args:
        base_dir: Optional path (str or Path) to the writable base directory.
            If None, attempts to import and use config.BASE_DIR, then falls
            back to %APPDATA%\WikidataBatchUploader.

    Raw because of that backslash: a plain string made Python warn
    `SyntaxWarning: invalid escape sequence '\W'` on every run, on stderr — in the one command whose whole
    job is to be read back cleanly by a person or an installer.
    """
    if base_dir is None:
        base_dir = _ensure_base_dir()
    elif isinstance(base_dir, str):
        base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    report_path = base_dir / 'diagnostic_report.txt'

    lines = []
    lines.append("=== WikiData Batch Uploader Diagnostic Report ===")
    lines.append(f"Generated: {datetime.datetime.now().isoformat()}")
    lines.append(f"Base directory: {base_dir}")
    lines.append(f"Python version: {sys.version}")
    lines.append(f"Executable: {sys.executable}")
    lines.append(f"Platform: {sys.platform}")
    lines.append(f"Frozen (PyInstaller): {getattr(sys, 'frozen', False)}")
    lines.append("")
    lines.append("--- sys.path ---")
    for p in sys.path:
        lines.append(f"  {p}")
    lines.append("")
    lines.append("--- Environment snapshot ---")
    for key, value in _get_env_snapshot().items():
        lines.append(f"  {key} = {value}")
    lines.append("")
    lines.append("--- AI mapping configuration ---")
    for key, value in _get_ai_config_snapshot().items():
        lines.append(f"  {key} = {value}")
    lines.append("")
    lines.append("--- Package versions ---")
    for package, version in _get_package_versions().items():
        lines.append(f"  {package}: {version}")
    lines.append("")
    lines.append("--- Import tests ---")
    import_results = _run_import_tests()
    success_count = 0
    failure_count = 0
    for module, result in import_results.items():
        if result == 'OK':
            success_count += 1
            lines.append(f"  {module}: OK")
        else:
            failure_count += 1
            lines.append(f"  {module}: FAILED")
            lines.append(f"  --- Traceback for {module} ---")
            lines.append(result.strip())
            lines.append(f"  --- End traceback ---")
    lines.append("")
    lines.append(f"Import summary: {success_count} succeeded, {failure_count} failed.")
    lines.append("")
    lines.append("=== End of report ===")

    report_content = "\n".join(lines)

    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
    except Exception:
        # Attempt to write to current working directory as last resort.
        fallback_path = Path.cwd() / 'diagnostic_report.txt'
        try:
            with open(fallback_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
        except Exception:
            # If both fail, there is nothing more we can safely do.
            pass

    # THE VERDICT IS THE LAST THING THIS FUNCTION DOES, AND UNTIL 2026-10-01 IT NEVER HAPPENED.
    #
    # The print-and-exit that carried the verdict sat after a `return` at the very bottom of this module —
    # unreachable — so `--diagnose` counted its failures, wrote the report, printed nothing and exited 0,
    # and main.py then fell through into the GUI. `selftest_verdict` was correct the whole time and its unit
    # test passed, because that test calls the pure function and never the wiring. A self-test whose failure
    # cannot be observed is worse than no self-test: the app's own manual, the compiled-app installer and
    # the whole `MORPHEUS-SELFTEST:` contract all tell the operator to run this and believe it.
    #
    # Returning the code rather than calling sys.exit() keeps this testable: main.py exits with it, and the
    # test asserts the printed line and the code together, which is the pair a caller actually reads.
    code, line = selftest_verdict(success_count, failure_count)
    print(line)
    return code

# The line Morpheus (or an installer, or a person) reads back. Same contract the generated apps use, so one
# reader understands both: one marker line, and an exit code that is NOT zero when the app is not well.
SELFTEST_MARKER = 'MORPHEUS-SELFTEST:'


def selftest_verdict(success_count, failure_count):
    """The (exit_code, marker_line) pair for a finished run.

    WHY THIS EXISTS. `run_diagnostics` counted its failures, wrote a report, and then let `main.py` call
    `sys.exit(0)` — so `--diagnose` could not fail, whatever it found. A check that cannot fail is worse than
    no check: it reads as a pass, and the report it writes is the only thing that says otherwise, which is
    exactly the "a window that did nothing" shape this app has already been on the wrong end of. The verdict
    is a pure function so it can be tested without importing PyQt6 — the app's tests are standard-library
    only on purpose.
    """
    if failure_count:
        return 1, f'{SELFTEST_MARKER} fail: {failure_count} module(s) failed to import ({success_count} loaded)'
    if not success_count:
        # NOTHING EXAMINED IS NOT A CLEAN BILL OF HEALTH. The module list is fixed, so zero modules tested
        # means the run itself is broken — and reporting that as ok is the precise trap this app's own
        # verification-coverage rule names.
        return 1, f'{SELFTEST_MARKER} fail: no modules were examined'
    return 0, f'{SELFTEST_MARKER} ok: {success_count} module(s) loaded'
