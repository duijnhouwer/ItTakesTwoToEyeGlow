"""Build the bundled GNOME decoration against the exact PySide Qt SDK version."""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from PySide6.QtCore import qVersion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-sdk', type=Path, required=True, help='Matching Qt gcc_64 SDK directory')
    parser.add_argument('--cmake', default='cmake')
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--cmake-arg', action='append', default=[])
    args = parser.parse_args()
    if not sys.platform.startswith('linux'):
        parser.error('This plugin is only built on Linux.')
    root = Path(__file__).resolve().parents[1]
    sdk = args.qt_sdk.resolve()
    sdk_version = subprocess.check_output([str(sdk/'bin/qmake'), '-query', 'QT_VERSION'], text=True).strip()
    if sdk_version != qVersion():
        parser.error(f'SDK {sdk_version} does not match PySide Qt {qVersion()}.')
    build = args.build_dir or root/'.runtime/window-decoration-build'
    subprocess.run([args.cmake, '-S', str(root/'third_party/qadwaitadecorations'),
                    '-B', str(build), '-DUSE_QT6=ON', '-DCMAKE_BUILD_TYPE=Release',
                    '-DCMAKE_SKIP_RPATH=ON', f'-DCMAKE_PREFIX_PATH={sdk}',
                    *args.cmake_arg], check=True)
    subprocess.run([args.cmake, '--build', str(build), '--parallel', '2'], check=True)
    destination = (root/'src/eyeglow_egobody/resources/qt_plugins'/qVersion()
                   /f'linux-{platform.machine()}'/'wayland-decoration-client')
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(build/'src/libqadwaitadecorations.so', destination)
    print(destination/'libqadwaitadecorations.so')


if __name__ == '__main__':
    main()
