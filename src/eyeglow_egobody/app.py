"""Application startup deliberately lazy-imports the desktop stack."""
import argparse
import os
from pathlib import Path
import sys
from eyeglow_egobody.runtime_paths import (project_root, default_dataset, default_models,
                                           icon_resource_path)


def main():
    parser = argparse.ArgumentParser(description='ItTakesTwoToEyeGlow paired motion playback')
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--dataset', type=Path, default=default_dataset())
    parser.add_argument('--model-dir', type=Path, default=os.environ.get('EYEGLOW_MODEL_DIR'))
    parser.add_argument('--synthetic', action='store_true', help='Use the deterministic synthetic fixture')
    parser.add_argument('--smoke-test',action='store_true',help='Exercise GUI and exports, then exit')
    parser.add_argument('--single-instance', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    os.environ['QT_API'] = 'pyside6'
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox
    from eyeglow_egobody.export.paths import safe_directory
    from eyeglow_egobody.model.panel_settings import SettingsSession
    from eyeglow_egobody.ui.main_window import MainWindow
    from eyeglow_egobody.ui.window_decoration import configure_window_decoration
    configure_window_decoration()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName('EyeGlow')
    app.setApplicationName('ItTakesTwoToEyeGlow')
    app.setApplicationDisplayName('ItTakesTwoToEyeGlow')
    app.setDesktopFileName('ittakestwotoeyeglow')
    app.setWindowIcon(QIcon(str(icon_resource_path())))
    singleton = None
    if args.single_instance:
        from eyeglow_egobody.ui.single_instance import SingleInstance
        singleton = SingleInstance()
        if not singleton.start():
            return 0
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
    try:
        settings_session = SettingsSession()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(f'Could not initialize settings: {exc}')
    if settings_session.recovery_pending:
        if args.smoke_test:
            # Smoke runs are intentionally disposable and must not wait for UI input.
            settings_session.use_user_defaults()
        elif not _choose_recovered_settings(settings_session, QMessageBox):
            return 0
    saved = settings_session.current.values
    template_root = default_models()
    dataset = Path(saved['egobody_data_path'] or args.dataset)
    models = {'female': Path(saved['smplx_female_template_path'] or template_root/'SMPLX_FEMALE.npz'),
              'male': Path(saved['smplx_male_template_path'] or template_root/'SMPLX_MALE.npz')}
    if args.model_dir:
        models = {'female': args.model_dir/'SMPLX_FEMALE.npz', 'male': args.model_dir/'SMPLX_MALE.npz'}
    window = MainWindow(output, dataset=None if args.synthetic or args.smoke_test else dataset,
                        model_dir=models, settings_session=settings_session)
    if singleton is not None:
        singleton.set_window(window)
    window.show()
    if args.smoke_test:
        from eyeglow_egobody.smoke import start_smoke
        start_smoke(app,window,output)
    return app.exec()


def _choose_recovered_settings(session, message_box_type):
    """Ask before constructing the viewport that would consume recovered state."""
    dialog = message_box_type()
    dialog.setIcon(message_box_type.Icon.Warning)
    dialog.setWindowTitle('Recover settings')
    dialog.setText('ItTakesTwoToEyeGlow did not close properly.')
    detail = ('The saved live settings can be restored for this session, or replaced '
              'with your saved defaults or the bundled factory defaults.')
    if session.recovery_error:
        detail += ('\n\nThe recovered settings are invalid or incompatible and cannot be restored: '
                   f'{session.recovery_error}')
    dialog.setInformativeText(detail)
    restore = dialog.addButton('Restore recovered settings', message_box_type.ButtonRole.AcceptRole)
    restore.setEnabled(session.recovery_error is None)
    user_defaults = dialog.addButton('Use user defaults', message_box_type.ButtonRole.ActionRole)
    factory_defaults = dialog.addButton('Use factory defaults', message_box_type.ButtonRole.ActionRole)
    cancel = dialog.addButton('Cancel', message_box_type.ButtonRole.RejectRole)
    dialog.setDefaultButton(restore if restore.isEnabled() else user_defaults)
    dialog.exec()
    choice = dialog.clickedButton()
    if choice is restore and restore.isEnabled():
        session.restore_recovered_settings()
    elif choice is user_defaults:
        session.use_user_defaults()
    elif choice is factory_defaults:
        session.use_factory_defaults()
    elif choice is cancel:
        return False
    else:
        return False
    return True
