import sys
import os
import traceback


def _ensure_base_dir() -> str:
    """Return the writable base directory, creating it if needed."""
    appdata = os.getenv('APPDATA')
    if appdata:
        base = os.path.join(appdata, 'WikidataBatchUploader')
    else:
        base = os.path.join(os.path.expanduser('~'), '.wikidata_batch_uploader')
    os.makedirs(base, exist_ok=True)
    return base


def _write_crash_log() -> None:
    """Append crash details to crash_log.txt in the base directory."""
    import datetime

    base = _ensure_base_dir()
    log_path = os.path.join(base, 'crash_log.txt')
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"\n--- Crash {datetime.datetime.now().isoformat()} ---\n")
        traceback.print_exc(file=f)


if __name__ == "__main__":
    if '--diagnose' in sys.argv:
        # Run diagnostics mode: gather environment and import tests, then exit.
        base_dir = None
        try:
            import config
            base_dir = config.BASE_DIR
        except Exception:
            base_dir = _ensure_base_dir()
        from core.diagnostics import run_diagnostics
        # run_diagnostics prints the verdict and RETURNS its exit code; the `sys.exit(0)` that used to sit
        # here made --diagnose unable to fail, and doing nothing with the return made it fall through into
        # the GUI — so `--diagnose` on a broken build opened a window instead of reporting. Exit here.
        raise SystemExit(run_diagnostics(base_dir))

    try:
        from PyQt6.QtWidgets import QApplication
        from ui.main_window import MainWindow
        from ui.styles import GLOBAL_STYLESHEET

        app = QApplication(sys.argv)
        app.setStyleSheet(GLOBAL_STYLESHEET)
        window = MainWindow()
        window.show()
        exit_code = app.exec()
        sys.exit(exit_code)
    except Exception:
        _write_crash_log()
        raise
