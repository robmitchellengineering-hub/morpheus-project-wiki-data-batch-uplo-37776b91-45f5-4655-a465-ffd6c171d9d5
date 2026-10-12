import sys
import os
import traceback


def _ensure_base_dir() -> str:
    """Return the writable base directory, creating it if needed.

    Prefers ``config.BASE_DIR`` so the crash log lands in the same per-user
    data directory the rest of the app documents (and, when frozen, the same
    directory the reference tables live in). Falls back to the platform
    default only if ``config`` itself cannot be imported.
    """
    try:
        import config
        return str(config.BASE_DIR)
    except Exception:
        appdata = os.getenv('APPDATA')
        if appdata:
            base = os.path.join(appdata, 'WikidataBatchUploader')
        else:
            base = os.path.join(os.path.expanduser('~'), '.wikidata_batch_uploader')
        os.makedirs(base, exist_ok=True)
        return base


def _write_crash_log() -> str:
    """Append crash details to crash_log.txt and return the log path."""
    import datetime

    base = _ensure_base_dir()
    log_path = os.path.join(base, 'crash_log.txt')
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"\n--- Crash {datetime.datetime.now().isoformat()} ---\n")
        traceback.print_exc(file=f)
    return log_path


def _has_display() -> bool:
    """True when a real window session is available (False on headless CI).

    The offscreen platform is what the build's smoke test asks Qt for on a
    headless runner; a modal message box there would block forever with no one
    to dismiss it, so it is treated the same as having no display.
    """
    if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        return False
    if sys.platform == 'darwin' and os.environ.get('CI'):
        return False
    if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
        return False
    return True


def _fatal_startup_error(exc) -> None:
    """Surface a startup failure loudly instead of dying to a dead window.

    A ``--windowed`` frozen build has no console, so an uncaught traceback is
    invisible: the process exits and the user is left with "a window that did
    nothing". Write the crash log, print to stderr (visible in a ``--console``
    build), show a message box when there is a real display, and exit non-zero.
    """
    log_path = _write_crash_log()
    message = (
        "The app could not start.\n\n"
        f"{exc}\n\n"
        f"A crash log was written to:\n{log_path}"
    )
    print(message, file=sys.stderr)
    if _has_display():
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "WikiData Batch Uploader", message)
        except Exception:
            pass
    sys.exit(1)


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
    except Exception as exc:
        _fatal_startup_error(exc)
