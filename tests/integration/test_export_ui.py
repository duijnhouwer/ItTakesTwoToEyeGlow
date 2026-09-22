from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QFileDialog, QDialog, QMessageBox,
                               QSizePolicy, QGroupBox, QPushButton)
from eyeglow_egobody.ui.export_dialog import VideoExportDialog, default_filename, choose_file
from eyeglow_egobody.model.recording import synthetic_recording


def test_video_dialog_defaults_range_fps_quality(qt_app):
    recording = synthetic_recording()
    dialog = VideoExportDialog(recording,(1234,567))
    assert dialog.isModal()
    assert dialog.quality.value() == dialog.quality_slider.value() == 90
    assert dialog.frame_size.currentText() == '1234 × 567 (Current UI display port)'
    dialog.quality_slider.setValue(73)
    assert dialog.quality.value() == 73
    dialog.quality.lineEdit().setText('82%')
    dialog.quality.interpretText()
    assert dialog.quality.value() == dialog.quality_slider.value() == 82
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
        self.fit_count = 0
    def set_frame(self,frame,spread,wall_spread=.40): pass
    def reset_view(self): pass
    def fit_participants(self): self.fit_count += 1
    def inspect_participant(self, participant, frame):
        self.inspected = (participant, frame)
    def track_participant(self, participant, frame): pass
    def stop_tracking(self): pass
    def orbit_by(self,degrees): pass
    def capture_size(self): return (self.width(),self.height())


def test_compact_window_uses_three_retractable_panels(qt_app,monkeypatch,tmp_path):
    from eyeglow_egobody.ui import main_window
    monkeypatch.setattr(main_window,'Viewport',FakeViewport)
    window = main_window.MainWindow(tmp_path)
    window.controller.timer.stop()
    try:
        available = window.screen().availableGeometry().size()
        expected_width = max(720, min(
            1200, int(available.width() * .80),
            int((available.height() * .88 - 48) * 1.5)))
        assert window.size().width() == expected_width
        assert window.size().height() == round(expected_width * 2 / 3) + 48
        assert window.minimumSize().width() == 720
        assert window.minimumSize().height() == 528
        assert window.activity_button.text() == 'Edit activities playlist ...'
        assert window.analyze_playlist_button.text() == 'Analyze activities playlist ...'
        assert window.analyze_playlist_button.parent() is window.recordings_panel
        assert not window.analyze_playlist_button.isEnabled()
        assert window.models_button.text() == 'Select input data ...'
        assert not hasattr(window, 'recordings')
        assert not hasattr(window, 'metadata_label')
        assert not hasattr(window, 'synthetic_button')
        assert not hasattr(window, 'load_button')
        assert not hasattr(window, 'diagnostics_button')
        assert window.orbit.isCheckable() and window.orbit.isChecked()
        assert window.inspect_a_button.isCheckable()
        assert window.inspect_b_button.isCheckable()
        assert window.inspect_a_button.text() == 'Track A'
        assert window.inspect_b_button.text() == 'Track B'
        assert window.controller.orbit_enabled
        assert window.controller.state.playing
        assert window.play.accessibleName() == 'Pause'
        assert not window.visualization_dock.isHidden()
        assert window.visualization_toggle.isChecked()
        assert window.visualization_toggle.text() == 'Visualization ▲'
        assert 'Fit optics' not in [
            child.text() for child in window.controls.findChildren(QPushButton)]
        window.inspect_a_button.click()
        assert window.inspect_a_button.isChecked()
        assert not window.inspect_b_button.isChecked()
        assert not window.orbit.isChecked()
        assert not window.controller.orbit_enabled
        assert window.viewport.inspected[0] == 0
        window.inspect_b_button.click()
        assert not window.inspect_a_button.isChecked()
        assert window.inspect_b_button.isChecked()
        assert not window.orbit.isChecked()
        assert window.viewport.inspected[0] == 1
        window.inspect_b_button.click()
        assert not window.inspect_b_button.isChecked()
        assert window.controller.tracked_participant is None
        assert window.viewport.fit_count == 1
        window.orbit.click()
        assert not window.inspect_a_button.isChecked()
        assert not window.inspect_b_button.isChecked()
        assert window.orbit.isChecked()
        assert window.controller.orbit_enabled
        window.orbit.click()
        assert not window.orbit.isChecked()
        assert not window.controller.orbit_enabled
        window.visualization_toggle.click()
        assert [window.smartglasses_dock.isHidden(), window.visualization_dock.isHidden(),
                window.recordings_dock.isHidden()] == [True, True, True]
        for dock in (window.smartglasses_dock, window.visualization_dock,
                     window.recordings_dock):
            assert dock.titleBarWidget() is not None
            assert dock.titleBarWidget().height() == 0
        assert window.smartglasses_toggle.text() == '◀ Geometry'
        assert window.visualization_toggle.text() == 'Visualization ▼'
        assert window.recordings_toggle.text() == 'Playlist and analysis ▶'
        assert not window.smartglasses_toggle.isChecked()
        assert not window.visualization_toggle.isChecked()
        assert not window.recordings_toggle.isChecked()
        window.smartglasses_toggle.click()
        window.visualization_toggle.click()
        window.recordings_toggle.click()
        assert window.smartglasses_toggle.text() == '▶ Geometry'
        assert window.visualization_toggle.text() == 'Visualization ▲'
        assert window.recordings_toggle.text() == 'Playlist and analysis ◀'
        assert window.smartglasses_toggle.isChecked()
        assert window.visualization_toggle.isChecked()
        assert window.recordings_toggle.isChecked()
        assert set(window.smartglasses_panel.groups) == {'smartglasses','receiver_fov'}
        assert set(window.display_settings_editor.groups) == {'visualization'}
        assert window.display_settings_editor.findChild(QGroupBox, 'visualization') is None
        assert not hasattr(window, 'show_frustums')
        assert not hasattr(window, 'show_ui_lines')
        assert not hasattr(window, 'show_axes')
        assert window.frustum_opacity.value() == .05
        assert window.frustum_wall_opacity.value() == .40
        assert 'eye_glow_color' not in window.smartglasses_panel.fields
        assert tuple(window.display_settings_editor.group_fields['visualization'])[-3:] == (
            'eye_glow_color', 'frustum_opacity', 'frustum_wall_opacity')
        assert window.display_settings_editor.fields['eye_glow_color'].text() == '#55FFFF'
        assert 'subject_a_activity_visible' not in window.display_settings_editor.fields
        assert 'subject_b_activity_visible' not in window.display_settings_editor.fields
        assert window.display_settings_dialog.width() == round(620 * .70)
        assert window.display_settings_button.text() == '⚙ Viewport settings...'
        assert window.display_settings_button.toolTip() == 'Display settings'
        assert window.display_settings_button.parent() is window.controls
        assert window.screenshot_button.parent() is window.controls
        assert window.video_button.parent() is window.controls
        assert (window.display_settings_button.sizePolicy().horizontalPolicy()
                == window.screenshot_button.sizePolicy().horizontalPolicy()
                == window.video_button.sizePolicy().horizontalPolicy()
                == QSizePolicy.Policy.Fixed)
        assert (window.viewport.contextMenuPolicy()
                == Qt.ContextMenuPolicy.CustomContextMenu)
        assert window.viewport_settings_action.text() == 'Viewport settings...'
        window.display_settings_button.click()
        assert not window.display_settings_dialog.isHidden()
        assert not window.display_settings_dialog.isModal()
        assert window.display_settings_dialog.height() < 520
        window.display_settings_dialog.hide()
        window.viewport_settings_action.trigger()
        assert not window.display_settings_dialog.isHidden()
        assert not hasattr(window, 'eye_test_button')
        assert not hasattr(window, 'visibility_label')
        assert not hasattr(window, 'visibility_dialog')
        assert not hasattr(window, 'jump_start')
        assert not window.previous_pair_clip_button.icon().isNull()
        assert not window.next_pair_clip_button.icon().isNull()
        assert window.previous_pair_clip_button.toolTip() == 'Previous activity pair clip'
        assert window.next_pair_clip_button.toolTip() == 'Next activity pair clip'
        assert not window.previous_pair_clip_button.isEnabled()
        assert not window.next_pair_clip_button.isEnabled()
        clip = SimpleNamespace(
            info=SimpleNamespace(name=window.controller.recording.name, start=0))
        playlist = SimpleNamespace(
            frame_count=4, duration_s=4/30, fps=30, clips=[object(), object()],
            pair_clip_offsets=[0, 2],
            locate=lambda frame: (clip, frame),
            pair_clip_number=lambda frame: 1 if frame < 2 else 2,
            previous_pair_clip_offset=lambda frame: None if frame == 0 else 0,
            next_pair_clip_offset=lambda frame: 2 if frame < 2 else None)
        window.controller.playlist = playlist
        window.controller.state.seek(0)
        window.sync()
        assert not window.previous_pair_clip_button.isEnabled()
        assert window.next_pair_clip_button.isEnabled()
        assert window.counter.text() == '1 / 2 activity pair clips · 0.00 / 0.13 s'
        window.controller.state.seek(2)
        window.sync()
        assert window.previous_pair_clip_button.isEnabled()
        assert not window.next_pair_clip_button.isEnabled()
        assert window.counter.text() == '2 / 2 activity pair clips · 0.07 / 0.13 s'
        assert window.corner(Qt.Corner.TopLeftCorner) == Qt.DockWidgetArea.LeftDockWidgetArea
        assert window.corner(Qt.Corner.BottomLeftCorner) == Qt.DockWidgetArea.LeftDockWidgetArea
        assert window.corner(Qt.Corner.TopRightCorner) == Qt.DockWidgetArea.RightDockWidgetArea
        assert window.corner(Qt.Corner.BottomRightCorner) == Qt.DockWidgetArea.RightDockWidgetArea
    finally:
        window.close()


def test_main_window_dialog_cancel_and_screenshot(qt_app,monkeypatch,tmp_path):
    from eyeglow_egobody.ui import main_window
    monkeypatch.setattr(main_window,'Viewport',FakeViewport)
    window = main_window.MainWindow(tmp_path)
    controller = window.controller
    controller.timer.stop()
    try:
        assert not hasattr(window,'export_range')
        assert not window.menuBar().actions()
        assert window.screenshot_button.text() == 'Export screenshot…'
        assert window.video_button.text() == 'Export video…'
        assert window.screenshot_button.parent() is window.controls
        assert window.video_button.parent() is window.controls
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
        controller.job = object()
        window.sync()
        assert not window.screenshot_button.isEnabled()
        assert not window.video_button.isEnabled()
        controller.job = None
        window.sync()
        assert window.screenshot_button.isEnabled()
        assert window.video_button.isEnabled()
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


def test_modal_dialogs_stop_clock_and_restore_after_nested_error(qt_app, monkeypatch, tmp_path):
    import pytest
    from time import monotonic
    from eyeglow_egobody.ui import main_window
    monkeypatch.setattr(main_window, 'Viewport', FakeViewport)
    window = main_window.MainWindow(tmp_path)
    controller = window.controller
    controller.state.playing = True
    controller.set_orbit_enabled(True)
    frame = controller.state.frame
    def nested_dialog(dialog):
        assert not controller.timer.isActive()
        assert controller.state.frame == frame
        controller.last = 0
        raise RuntimeError('picker failed')
    monkeypatch.setattr(main_window.SettingsDialog, 'exec', nested_dialog)
    try:
        with pytest.raises(RuntimeError, match='picker failed'):
            window.show_settings()
        assert controller.timer.isActive()
        assert controller.state.playing and controller.orbit_enabled
        assert monotonic() - controller.last < 1
        assert controller.state.frame == frame
        controller.timer.stop()
        with pytest.raises(RuntimeError):
            window.show_settings()
        assert not controller.timer.isActive()
    finally:
        window.close()
