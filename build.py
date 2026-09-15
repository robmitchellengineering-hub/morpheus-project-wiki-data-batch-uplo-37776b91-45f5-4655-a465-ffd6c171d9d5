import os
import subprocess
import sys
import time
import shutil

EXE_NAME = "WikiDataBatchUploader.exe"

COLLECT_PACKAGES = [
    ('PyQt6', 'submodules'),
    ('PyQt6', 'data'),
    ('pandas', 'submodules'),
    ('pandas', 'data'),
    ('wikidataintegrator', 'submodules'),
    ('wikidataintegrator', 'data'),
    ('pyshex', 'submodules'),
    ('pyshex', 'data'),
    ('sparqlslurper', 'submodules'),
    ('sparqlslurper', 'data'),
    ('lxml', 'submodules'),
    ('lxml', 'data'),
]

HIDDEN_IMPORTS = [
    'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtNetwork',
    'pkg_resources', 'setuptools',
]

EXCLUDE_MODULES = [
    'matplotlib', 'scipy', 'IPython', 'tkinter',
    'PyQt6.QtWebEngineWidgets', 'PyQt6.QtPdf', 'PyQt6.QtQml',
    'PyQt6.QtCharts', 'PyQt6.QtDataVisualization',
]


def smoke_test(executable_path):
    print('Running smoke test: launching executable...')
    try:
        proc = subprocess.Popen([executable_path])
    except Exception as e:
        print(f'Failed to launch executable: {e}')
        sys.exit(1)
    time.sleep(5)
    if proc.poll() is not None:
        print(f'Smoke test failed: executable exited early with code {proc.returncode}.')
        sys.exit(1)
    print('Executable stayed alive for 5 seconds; terminating.')
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _clean_previous_build():
    for name in os.listdir('.'):
        if name.endswith('.spec'):
            os.remove(name)
    dist_dir = os.path.join(os.getcwd(), 'dist')
    build_dir = os.path.join(os.getcwd(), 'build')
    for dir_path in (dist_dir, build_dir):
        if os.path.exists(dir_path):
            print(f'Cleaning previous build directory {dir_path}')
            shutil.rmtree(dir_path, ignore_errors=True)
    return dist_dir, build_dir


def _pyinstaller_base_cmd(app_name, dist_dir, build_dir):
    cmd = [sys.executable, '-m', 'PyInstaller', '--onefile']
    cmd += ['--name', app_name, '--clean', '--noconfirm',
            '--distpath', dist_dir, '--workpath', build_dir, '--specpath', build_dir]
    for pkg, flag in COLLECT_PACKAGES:
        cmd += [f'--collect-{flag}', pkg]
    for imp in HIDDEN_IMPORTS:
        cmd += ['--hidden-import', imp]
    for mod in EXCLUDE_MODULES:
        cmd += ['--exclude-module', mod]
    return cmd


def _run_pyinstaller(cmd):
    print('Running PyInstaller...')
    print(' '.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print('PyInstaller failed. Output tail:')
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        sys.exit(result.returncode)


def build_windows(console_mode):
    if console_mode:
        print('Building debug console version.')
    else:
        print('Building standard windowed version.')

    dist_dir, build_dir = _clean_previous_build()

    app_name = 'WikiDataBatchUploader_debug' if console_mode else 'WikiDataBatchUploader'
    target_exe_name = app_name + '.exe'
    cmd = _pyinstaller_base_cmd(app_name, 'dist', 'build')
    if not console_mode:
        cmd.insert(3, '--windowed')  # after --onefile
    cmd.append('main.py')

    _run_pyinstaller(cmd)

    # PyInstaller may name the artifact differently (e.g., app.exe). Locate the
    # first .exe in dist/ and rename it to our target name.
    exe_path = os.path.join(dist_dir, target_exe_name)
    if not os.path.exists(exe_path):
        candidates = [f for f in os.listdir(dist_dir) if f.lower().endswith('.exe') and os.path.isfile(os.path.join(dist_dir, f))]
        if not candidates:
            print(f'PyInstaller produced no .exe in {dist_dir}.')
            sys.exit(1)
        source_path = None
        for candidate in candidates:
            if candidate.lower() == 'app.exe':
                source_path = os.path.join(dist_dir, candidate)
                break
        if source_path is None:
            source_path = os.path.join(dist_dir, candidates[0])
        try:
            os.replace(source_path, exe_path)
            print(f'Renamed {source_path} to {exe_path}')
        except OSError as e:
            print(f'Failed to rename {source_path} to {exe_path}: {e}')
            sys.exit(1)

    if not os.path.exists(exe_path) or os.path.getsize(exe_path) == 0:
        print(f'PyInstaller produced no valid .exe at expected location: {exe_path}')
        sys.exit(1)

    smoke_test(exe_path)
    print('Build complete. Executable is in dist/')


def build_macos(console_mode):
    # Mirrors build_windows above -- same PyInstaller args/collected
    # packages, since PyQt6/pandas/wikidataintegrator etc. need the same
    # explicit submodule/data collection on every platform (PyInstaller's
    # default import-following can't see them either way). What differs:
    # --windowed produces a real .app bundle here (not a plain .exe), and
    # the bundle needs an --osx-bundle-id; the smoke test launches the
    # binary inside Contents/MacOS/ instead of a top-level .exe.
    if console_mode:
        print('Building debug console version.')
    else:
        print('Building standard windowed version.')

    dist_dir, build_dir = _clean_previous_build()

    app_name = 'WikiDataBatchUploader_debug' if console_mode else 'WikiDataBatchUploader'
    cmd = _pyinstaller_base_cmd(app_name, 'dist', 'build')
    if not console_mode:
        cmd.insert(3, '--windowed')  # after --onefile
        cmd.insert(4, '--osx-bundle-id')
        cmd.insert(5, 'com.valiantmusic.wikidatauploader')
    cmd.append('main.py')

    _run_pyinstaller(cmd)

    if console_mode:
        # --onefile without --windowed produces a plain executable on
        # macOS too, not a .app bundle.
        executable_path = os.path.join(dist_dir, app_name)
        if not os.path.exists(executable_path) or os.path.getsize(executable_path) == 0:
            print(f'PyInstaller produced no valid executable at expected location: {executable_path}')
            sys.exit(1)
    else:
        app_bundle = os.path.join(dist_dir, app_name + '.app')
        executable_path = os.path.join(app_bundle, 'Contents', 'MacOS', app_name)
        if not os.path.isdir(app_bundle) or not os.path.exists(executable_path):
            print(f'PyInstaller produced no valid .app bundle at expected location: {app_bundle}')
            sys.exit(1)

    smoke_test(executable_path)
    print('Build complete. Output is in dist/')


def main():
    console_mode = '--console' in sys.argv
    if os.name == 'nt':
        build_windows(console_mode)
    elif sys.platform == 'darwin':
        build_macos(console_mode)
    else:
        print(f'This build script supports Windows and macOS only (detected: {sys.platform}).')
        sys.exit(1)


if __name__ == '__main__':
    main()
