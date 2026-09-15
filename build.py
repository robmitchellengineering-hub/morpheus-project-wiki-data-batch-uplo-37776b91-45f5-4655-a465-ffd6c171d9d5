import os
import subprocess
import sys
import time
import shutil

EXE_NAME = "WikiDataBatchUploader.exe"


def smoke_test(exe_path):
    print('Running smoke test: launching executable...')
    try:
        proc = subprocess.Popen([exe_path])
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


def main():
    if os.name != 'nt':
        print('This build script must be run on Windows. It cannot produce a Windows .exe on a non-Windows host.')
        sys.exit(1)

    console_mode = '--console' in sys.argv
    if console_mode:
        print('Building debug console version.')
    else:
        print('Building standard windowed version.')

    # Remove any stale PyInstaller spec files to ensure command-line options are used.
    for name in os.listdir('.'):
        if name.endswith('.spec'):
            os.remove(name)

    # Clean previous build output to avoid stale artifacts
    dist_dir = os.path.join(os.getcwd(), 'dist')
    if os.path.exists(dist_dir):
        print(f'Cleaning previous build directory {dist_dir}')
        shutil.rmtree(dist_dir, ignore_errors=True)

    # Collect PyQt6 and pandas dependencies explicitly; PyInstaller hooks handle the rest.
    collect_packages = [
        ('PyQt6', 'submodules'),
        ('PyQt6', 'data'),
        ('pandas', 'submodules'),
        ('pandas', 'data'),
    ]

    app_name = 'WikiDataBatchUploader_debug' if console_mode else 'WikiDataBatchUploader'
    target_exe_name = app_name + '.exe'
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
    ]
    if not console_mode:
        cmd.append('--windowed')
    cmd += ['--name', app_name,
            '--clean', '--noconfirm',
            '--distpath', 'dist',
            '--workpath', 'build',
            '--specpath', 'build',
    ]
    for pkg, flag in collect_packages:
        if flag == 'submodules':
            cmd += ['--collect-submodules', pkg]
        else:
            cmd += ['--collect-data', pkg]

    cmd += [
        '--hidden-import', 'PyQt6.QtCore',
        '--hidden-import', 'PyQt6.QtGui',
        '--hidden-import', 'PyQt6.QtWidgets',
        '--hidden-import', 'PyQt6.QtNetwork',
        '--hidden-import', 'pkg_resources',
        '--exclude-module', 'matplotlib',
        '--exclude-module', 'scipy',
        '--exclude-module', 'IPython',
        '--exclude-module', 'tkinter',
        '--exclude-module', 'PyQt6.QtWebEngineWidgets',
        '--exclude-module', 'PyQt6.QtPdf',
        '--exclude-module', 'PyQt6.QtQml',
        '--exclude-module', 'PyQt6.QtCharts',
        '--exclude-module', 'PyQt6.QtDataVisualization',
        'main.py'
    ]

    print('Running PyInstaller...')
    print(' '.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print('PyInstaller failed. Output tail:')
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        sys.exit(result.returncode)

    # PyInstaller may name the artifact differently (e.g., app.exe). Locate the
    # first .exe in dist/ and rename it to our target name.
    exe_path = os.path.join(dist_dir, target_exe_name)
    if not os.path.exists(exe_path):
        # Find any .exe in dist/
        candidates = [f for f in os.listdir(dist_dir) if f.lower().endswith('.exe') and os.path.isfile(os.path.join(dist_dir, f))]
        if not candidates:
            print(f'PyInstaller produced no .exe in {dist_dir}.')
            sys.exit(1)
        # Prefer an exe named app.exe if present, but any .exe works.
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


if __name__ == '__main__':
    main()
