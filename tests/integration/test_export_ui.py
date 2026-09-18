from pathlib import Path
from PySide6.QtWidgets import QWidget, QFileDialog, QDialog, QMessageBox
from eyeglow_egobody.ui.export_dialog import VideoExportDialog, default_filename, choose_file
from eyeglow_egobody.model.recording import synthetic_recording


def test_video_dialog_defaults_range_fps_quality(qt_app):
    recording = synthetic_recording()
    dialog = VideoExportDialog(recording,(1234,567))
    assert dialog.isModal()
    assert dialog.filename.text() == str(Path.home()/'Videos'/'synthetic_motion.mp4')
    assert (dialog.start_frame.value(),dialog.end_frame.value()) == (1,300)
    assert dialog.frame_size.currentData() == (1234,567)
    assert [dialog.frame_size.itemData(i) for i in range(3)] == [(3840,2160),(1920,1080),(1234,567)]
    dialog.start_frame.setValue(41)
    dialog.end_frame.setValue(70)
    assert dialog.summary.text() == '30 frames · 1.00 seconds'
    dialog.fps.setValue(60)
    assert dialog.summary.text() == '30 frames · 0.50 seconds'
    dialog.native_fps.click()
    assert dialog.fps.value() == 30
    dialog.full_range.click()
    assert (dialog.start_frame.value(),dialog.end_frame.value()) == (1,300)
    dialog.start_frame.setValue(299)
    dialog.end_frame.setValue(200)
    assert dialog.start_frame.value() == 200
    assert (dialog.fps.minimum(),dialog.fps.maximum()) == (1,120)
    assert (dialog.quality.minimum(),dialog.quality.maximum()) == (0,100)
    dialog.close()


def test_video_dialog_rejects_formats_and_confirms_replace(qt_app,monkeypatch,tmp_path):
    dialog = VideoExportDialog(synthetic_recording(),(640,480))
    warnings = []
    monkeypatch.setattr(QMessageBox,'warning',lambda *args: warnings.append(args[2]))
    dialog.filename.setText(str(tmp_path/'movie.avi'))
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert 'Only MP4' in warnings[-1]
    path = tmp_path/'movie.mp4'
    path.write_bytes(b'original')
    dialog.filename.setText(str(path))
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.StandardButton.No)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Rejected
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.StandardButton.Yes)
    dialog.quality.setValue(90)
    dialog.fps.setValue(24)
    dialog.frame_size.setCurrentIndex(1)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.destination == path
    assert (dialog.settings.size,dialog.settings.fps,dialog.settings.quality) == ((1920,1080),24,90)
    assert path.read_bytes() == b'original'


class FakeViewport(QWidget):
    def __init__(self,parent,recording):
        super().__init__(parent)
        self.interactor = self
    def set_frame(self,frame,spread): pass
    def reset_view(self): pass
    def fit_participants(self): pass
    def orbit_by(self,degrees): pass
    def capture_size(self): return (self.width(),self.height())


def test_main_window_dialog_cancel_and_screenshot(qt_app,monkeypatch,tmp_path):
    from eyeglow_egobody.ui import main_window
    monkeypatch.setattr(main_window,'Viewport',FakeViewport)
    window = main_window.MainWindow(tmp_path)
    controller = window.controller
    controller.timer.stop()
    try:
        assert not hasattr(window,'export_range')
        assert window.video_button.text() == 'Export Video ...'
        assert window.screenshot_button.text() == 'Save Screenshot ...'
        controller.state.playing = True
        sizes = []
        def reject(dialog):
            assert not controller.state.playing
            sizes.append(dialog.frame_size.currentData())
            dialog.start_frame.setValue(99)
            return QDialog.DialogCode.Rejected
        monkeypatch.setattr(VideoExportDialog,'exec',reject)
        window.viewport.resize(640,480)
        window.video_button.click()
        window.viewport.resize(800,600)
        window.video_button.click()
        assert sizes == [(640,480),(800,600)]
        assert controller.state.playing and controller.export_start == 0
        calls = []
        monkeypatch.setattr(main_window,'choose_file',lambda *args: tmp_path/'scene.png')
        monkeypatch.setattr(controller,'save_screenshot',lambda path,overwrite: calls.append((path,overwrite)))
        window.screenshot_button.click()
        assert calls == [(tmp_path/'scene.png',True)]
        assert default_filename(controller.recording,False) == Path.home()/'Pictures'/'synthetic_motion.png'
    finally:
        window.close()


def test_png_dialog_rejects_other_extensions(qt_app,monkeypatch,tmp_path):
    attempts = iter([QDialog.DialogCode.Accepted,QDialog.DialogCode.Rejected])
    warnings = []
    monkeypatch.setattr(QFileDialog,'exec',lambda dialog: next(attempts))
    monkeypatch.setattr(QFileDialog,'selectedFiles',lambda dialog: [str(tmp_path/'scene.jpg')])
    monkeypatch.setattr(QMessageBox,'warning',lambda *args: warnings.append(args[2]))
    assert choose_file(None,tmp_path/'scene.png',False) is None
    assert 'Only PNG' in warnings[0]
