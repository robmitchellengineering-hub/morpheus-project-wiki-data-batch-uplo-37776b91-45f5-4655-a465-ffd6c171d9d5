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
        connected = bool(credential_storage.load_morpheus_token())
        snapshot = {'morpheus_connect': 'connected' if connected else 'not connected'}
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


def run_diagnostics(base_dir=None) -> None:
    """Collect diagnostics and write a report to the base directory.

    Args:
        base_dir: Optional path (str or Path) to the writable base directory.
            If None, attempts to import and use config.BASE_DIR, then falls
            back to %APPDATA%\WikidataBatchUploader.
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
