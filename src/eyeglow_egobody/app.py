"""Application startup deliberately lazy-imports the desktop stack."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description='EyeGlow Phase 1 synthetic desktop prototype')
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--smoke-test',action='store_true',help='Exercise GUI and exports, then exit')
    args = parser.parse_args()
    os.environ['QT_API'] = 'pyside6'
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtWidgets import QApplication
    from eyeglow_egobody.export.paths import safe_directory
    from eyeglow_egobody.ui.main_window import MainWindow
    app = QApplication(sys.argv[:1])
    app.setOrganizationName('EyeGlow')
    app.setApplicationName('EyeGlowEgoBody')
    if args.output_dir:
        output = args.output_dir
    elif not getattr(sys,'frozen',False) and (Path(__file__).resolve().parents[2]/'pyproject.toml').exists():
        output = Path(__file__).resolve().parents[2]/'exports'
    else:
        output = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))/'exports'
    try:
        output = safe_directory(output)
    except (ValueError,OSError) as exc:
        parser.error(str(exc))
    window = MainWindow(output)
    window.show()
    if args.smoke_test:
        from eyeglow_egobody.smoke import start_smoke
        start_smoke(app,window,output)
    return app.exec()
