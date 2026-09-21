from types import SimpleNamespace
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QDialog, QFileDialog
from eyeglow_egobody.ui.file_dialogs import file_dialog, save_file, existing_directory


@pytest.mark.parametrize('running', [True, False])
@pytest.mark.parametrize('fails', [True, False])
def test_nested_picker_restores_timer_on_cancel_or_error(qt_app, running, fails):
    window = QWidget()
    timer = QTimer(window)
    timer.setInterval(16)
    window.controller = SimpleNamespace(timer=timer, last=0)
    nested = QDialog(QDialog(window))
    if running:
        timer.start()
    def picker():
        assert not timer.isActive()
        assert file_dialog(nested, lambda: 'nested') == 'nested'
        assert not timer.isActive()
        if fails:
            raise RuntimeError('picker failed')
        return ('', '')
    try:
        if fails:
            with pytest.raises(RuntimeError, match='picker failed'):
                file_dialog(nested, picker)
        else:
            assert file_dialog(nested, picker) == ('', '')
        assert timer.isActive() == running
        assert timer.interval() == 16
        assert window.controller.last > 0
    finally:
        timer.stop()
        window.close()


def test_standard_pickers_pause_before_opening(qt_app, monkeypatch):
    window = QWidget()
    timer = QTimer(window)
    timer.start(16)
    window.controller = SimpleNamespace(timer=timer, last=0)
    def picker(parent, *args, **kwargs):
        assert parent is window
        assert not timer.isActive()
        return 'result'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', picker)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', picker)
    try:
        assert save_file(window, 'Save') == 'result'
        assert timer.isActive()
        assert existing_directory(window, 'Folder') == 'result'
        assert timer.isActive()
    finally:
        timer.stop()
        window.close()
