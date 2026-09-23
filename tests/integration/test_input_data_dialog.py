from pathlib import Path
import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox, QDialogButtonBox
from eyeglow_egobody.model.panel_settings import SettingsSession, PanelSettings, factory_settings_path
from eyeglow_egobody.ui.input_data_dialog import InputDataDialog, FIELDS, default_paths


@pytest.fixture
def session(tmp_path):
    factory = tmp_path/'factory.json'
    factory.write_bytes(factory_settings_path().read_bytes())
    return SettingsSession(factory, tmp_path/'settings')


def test_default_paths_apply_reset_and_save_defaults(qt_app, session, tmp_path):
    root = tmp_path/'EgoBody'
    root.mkdir()
    (root/'data_info_release.csv').write_text('recording_name\n')
    female, male = tmp_path/'female.npz', tmp_path/'male.npz'
    female.write_bytes(b'female')
    male.write_bytes(b'male')
    dialog = InputDataDialog(session.current, session.save_user_defaults)
    try:
        assert len(dialog.findChildren(QDialogButtonBox)) == 1
        assert dialog.fields[FIELDS[0]].text() == default_paths()[FIELDS[0]]
        dialog.fields[FIELDS[0]].setText(str(root))
        dialog.fields[FIELDS[1]].setText(str(female))
        dialog.fields[FIELDS[2]].setText(str(male))
        dialog.accept()
        assert session.current.values[FIELDS[0]] == str(root)
        dialog.save_as_defaults()
        assert PanelSettings(session.user_default_path, session.factory_path).values[FIELDS[2]] == str(male)
        dialog.reset_to_factory()
        assert session.current.values[FIELDS[0]] == default_paths()[FIELDS[0]]
    finally:
        dialog.close()


def test_browsers_are_specific_to_folder_or_file(qt_app, session, monkeypatch):
    dialog = InputDataDialog(session.current)
    calls = []
    monkeypatch.setattr('eyeglow_egobody.ui.input_data_dialog.existing_directory',
                        lambda *args: calls.append(('folder', args)) or '/data')
    monkeypatch.setattr('eyeglow_egobody.ui.input_data_dialog.file_dialog',
                        lambda *args: calls.append(('file', args)) or ('/female.npz', ''))
    try:
        dialog.browse(FIELDS[0])
        dialog.browse(FIELDS[1])
        assert calls[0][0] == 'folder' and calls[1][0] == 'file'
        assert dialog.fields[FIELDS[0]].text() == '/data'
        assert dialog.fields[FIELDS[1]].text() == '/female.npz'
    finally:
        dialog.close()


def test_invalid_paths_do_not_close_or_update(qt_app, session, monkeypatch):
    dialog = InputDataDialog(session.current)
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: errors.append(args[2]))
    try:
        dialog.fields[FIELDS[0]].setText('/not-a-dataset')
        dialog.accept()
        assert errors and dialog.result() != dialog.DialogCode.Accepted
        assert session.current.values[FIELDS[0]] == ''
    finally:
        dialog.close()
