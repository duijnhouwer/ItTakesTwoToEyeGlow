from time import monotonic
from functools import wraps
from pathlib import Path
import json
import numpy as np
from PySide6.QtCore import Qt, QSignalBlocker, QSize
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
                               QPushButton,QSlider,QDoubleSpinBox,QComboBox,QCheckBox,
                               QMessageBox,QDialog,QStyle,QFileDialog,QTextEdit,QDockWidget,
                               QToolButton)
from eyeglow_egobody.model.recording import Recording, synthetic_recording
from eyeglow_egobody.rendering.viewport import Viewport
from eyeglow_egobody.runtime_paths import default_models
from eyeglow_egobody.controller import Controller
from eyeglow_egobody.model.panel_settings import PanelSettings
from eyeglow_egobody.ui.settings_dialog import SettingsDialog, SettingsEditor
from eyeglow_egobody.analysis.diagnostics import visibility_summary, visibility_details
from eyeglow_egobody.ui.export_dialog import VideoExportDialog, choose_file, default_filename

def suspend_animation(method):
    """Stop the render clock throughout modal dialogs, including nested pickers."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        controller = self.controller
        running = controller.timer.isActive()
        controller.timer.stop()
        try:
            return method(self, *args, **kwargs)
        finally:
            # Never advance by the time spent interacting with the dialog.
            controller.last = monotonic()
            if running:
                controller.timer.start()
    return wrapped


class MainWindow(QMainWindow):
    def __init__(self, output_root, dataset=None, model_dir=None, settings_session=None):
        super().__init__()
        self.setWindowTitle('EyeGlow EgoBody — Paired motion playback')
        self.dataset = dataset
        self.model_dir = model_dir or default_models()
        self.infos = []
        self.settings_session = settings_session
        self.panel_settings = (settings_session.current if settings_session is not None
                               else PanelSettings())
        # Size the first-run viewport at 3:2 landscape while leaving room for the
        # bottom button rail and the desktop's reserved areas.
        available = self.screen().availableGeometry().size()
        rail_height = 48
        viewport_width = min(
            1200,
            int(available.width() * .80),
            int((available.height() * .88 - rail_height) * 1.5),
        )
        viewport_width = max(720, viewport_width)
        viewport_height = round(viewport_width * 2 / 3)
        self.resize(viewport_width, viewport_height + rail_height)
        self.setMinimumSize(720, 480 + rail_height)
        self._export_size_limits = None
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        recording = (Recording(np.array([0.]), np.zeros((2,1,16,3)),
                               np.tile(np.eye(4),(2,1,1,1)), name='No recording loaded',
                               valid=np.zeros((2,1),dtype=bool)) if dataset else synthetic_recording())
        self.viewport = Viewport(root,recording)
        self.viewport.optical_settings = self.panel_settings.values
        self.viewport.show_ui_lines = False
        self.viewport.set_frame(0,.10)
        layout.addWidget(self.viewport.interactor,1)
        self.controller = Controller(recording,self.viewport,output_root,self)

        def button(label, callback, row=None, tooltip=None):
            widget = QPushButton(label)
            if tooltip:
                widget.setToolTip(tooltip)
                widget.setAccessibleName(tooltip)
            widget.clicked.connect(callback)
            if row is not None:
                row.addWidget(widget)
            return widget

        # The only persistent chrome around the viewport is this three-button rail.
        panel_buttons = QHBoxLayout()
        panel_buttons.setContentsMargins(8,6,8,6)
        self.smartglasses_toggle = button('◀ Smartglasses', lambda: self._toggle_dock(self.smartglasses_dock))
        self.visualization_toggle = button('Visualization ▼', lambda: self._toggle_dock(self.visualization_dock))
        self.recordings_toggle = button('Recordings ▶', lambda: self._toggle_dock(self.recordings_dock))
        panel_buttons.addWidget(self.smartglasses_toggle)
        panel_buttons.addStretch(1)
        panel_buttons.addWidget(self.visualization_toggle)
        panel_buttons.addStretch(1)
        panel_buttons.addWidget(self.recordings_toggle)
        layout.addLayout(panel_buttons)
        self.setCentralWidget(root)

        self.smartglasses_panel = SettingsEditor(
            self.panel_settings, ('smartglasses','receiver_fov'), self,
            save_user_defaults=self._save_user_defaults)
        self.smartglasses_panel.setMinimumWidth(340)
        self.smartglasses_panel.saved.connect(self._apply_panel_settings)
        self.smartglasses_dock = self._make_dock(
            'Smartglasses', self.smartglasses_panel, Qt.DockWidgetArea.LeftDockWidgetArea,
            'smartglasses_panel')

        self.controls = QWidget()
        controls_layout = QVBoxLayout(self.controls)
        camera = QHBoxLayout()
        controls_layout.addLayout(camera)
        button('Reset camera',self.viewport.reset_view,camera)
        button('Fit participants',self.viewport.fit_participants,camera)
        button('Fit optics',lambda:self.viewport.fit_optics(),camera)
        button('Inspect A',lambda:self.inspect_participant(0),camera)
        button('Inspect B',lambda:self.inspect_participant(1),camera)
        self.orbit = QCheckBox('Orbit')
        self.orbit.setToolTip('Automatically orbit around world Z, including while playback is paused.')
        self.orbit.toggled.connect(self.controller.set_orbit_enabled)
        camera.addWidget(self.orbit)
        self.orbit_speed = QDoubleSpinBox()
        self.orbit_speed.setRange(-360,360)
        self.orbit_speed.setDecimals(1)
        self.orbit_speed.setValue(5)
        self.orbit_speed.setSuffix(' deg/s')
        self.orbit_speed.setAccessibleName('Orbit speed in degrees per second')
        self.orbit_speed.setToolTip('Orbit speed. Negative values reverse direction; zero stops rotation.')
        self.orbit_speed.valueChanged.connect(self.controller.set_orbit_speed)
        camera.addWidget(self.orbit_speed)
        self.orbit.setChecked(True)
        self.viewport.interactor.setToolTip(
            'Orbit (upright): drag · Pan: Shift + drag · Zoom: scroll')
        camera.addStretch()
        self.display_settings_button = QToolButton()
        self.display_settings_button.setText('⚙ Viewport settings...')
        self.display_settings_button.setToolTip('Display settings')
        self.display_settings_button.setAccessibleName('Display settings')
        camera.addWidget(self.display_settings_button)
        self.display_settings_dialog = QDialog(self)
        self.display_settings_dialog.setWindowTitle('Viewport settings')
        self.display_settings_dialog.setModal(False)
        self.display_settings_dialog.resize(620,520)
        display_settings_layout = QVBoxLayout(self.display_settings_dialog)
        optical = QHBoxLayout()
        display_settings_layout.addLayout(optical)
        for title, attribute, checked in (('Frustums','show_frustums',True),
                                         ('UI lines','show_ui_lines',False),
                                         ('Local axes','show_axes',False)):
            checkbox = QCheckBox(title)
            checkbox.setChecked(checked)
            checkbox.toggled.connect(lambda value, key=attribute: self.set_optical_visibility(key,value))
            setattr(self, attribute, checkbox)
            optical.addWidget(checkbox)
        optical.addWidget(QLabel('Frustum opacity'))
        self.frustum_opacity = QDoubleSpinBox()
        self.frustum_opacity.setRange(0,1)
        self.frustum_opacity.setSingleStep(.05)
        self.frustum_opacity.setValue(.10)
        self.frustum_opacity.valueChanged.connect(self.controller.set_frustum_opacity)
        optical.addWidget(self.frustum_opacity)
        optical.addStretch()
        self.display_settings_editor = SettingsEditor(
            self.panel_settings, ('visualization',), self.display_settings_dialog,
            save_user_defaults=self._save_user_defaults)
        self.display_settings_editor.saved.connect(self._apply_panel_settings)
        display_settings_layout.addWidget(self.display_settings_editor)
        self.display_settings_button.clicked.connect(self.show_display_settings)
        eye_test_row = QHBoxLayout()
        eye_test_row.addStretch(1)
        self.eye_test_button = button('Eye-test details...',self.show_eye_test_details,eye_test_row)
        controls_layout.addLayout(eye_test_row)
        self.visibility_dialog = QDialog(self)
        self.visibility_dialog.setWindowTitle('Current-frame eye tests')
        self.visibility_dialog.resize(520,560)
        visibility_layout = QVBoxLayout(self.visibility_dialog)
        self.visibility_text = QTextEdit()
        self.visibility_text.setReadOnly(True)
        self.visibility_text.setMinimumWidth(320)
        visibility_layout.addWidget(self.visibility_text)
        self.visibility_label = QLabel()
        self.visibility_label.setWordWrap(True)
        controls_layout.addWidget(self.visibility_label)
        row = QHBoxLayout()
        controls_layout.addLayout(row)
        self.jump_start = button('',lambda:self.controller.seek(0),row,'Jump to Start')
        self.previous_frame = button('−1',lambda:self.controller.seek(self.controller.state.frame-1),row,'Previous Frame')
        self.play = button('',self.controller.toggle,row,'Play/Pause')
        self.next_frame = button('+1',lambda:self.controller.seek(self.controller.state.frame+1),row,'Next Frame')
        playback_buttons = (self.jump_start, self.previous_frame, self.play, self.next_frame)
        self._play_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self._pause_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        self.jump_start.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.play.setIcon(self._play_icon)
        for widget in (self.jump_start, self.play):
            widget.setIconSize(QSize(14,14))
        height = max(widget.sizeHint().height() for widget in playback_buttons)
        # Fit the numeric labels and equally sized icons with modest padding.
        width = max(14, *(widget.fontMetrics().horizontalAdvance(label)
                         for widget in playback_buttons for label in ('−1', '+1'))) + 16
        for widget in playback_buttons:
            widget.setFixedSize(width, height)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0,recording.frame_count-1)
        self.slider.valueChanged.connect(self.controller.seek)
        row.addWidget(self.slider,1)
        self.counter = QLabel()
        row.addWidget(self.counter)
        self.speed = QComboBox()
        self.speed.addItems(['0.25×','0.5×','1×','2×'])
        self.speed.setCurrentIndex(2)
        self.speed.currentIndexChanged.connect(lambda i:setattr(self.controller.state,'speed',[.25,.5,1,2][i]))
        row.addWidget(self.speed)
        loop = QCheckBox('Loop')
        loop.setToolTip('Loop')
        loop.setAccessibleName('Loop')
        loop.setChecked(True)
        loop.toggled.connect(lambda v:setattr(self.controller.state,'loop',v))
        row.addWidget(loop)
        self.visualization_dock = self._make_dock(
            'Visualization', self.controls, Qt.DockWidgetArea.BottomDockWidgetArea,
            'visualization_panel')

        recordings_panel = QWidget()
        recordings_panel.setMinimumWidth(280)
        recordings_layout = QVBoxLayout(recordings_panel)
        self.recordings = QComboBox()
        self.recordings.setMinimumContentsLength(28)
        recordings_layout.addWidget(self.recordings)
        self.metadata_label = QLabel('Discovering recordings…' if dataset else 'Synthetic fixture · invented motion')
        self.metadata_label.setWordWrap(True)
        self.metadata_label.setTextFormat(Qt.TextFormat.PlainText)
        recordings_layout.addWidget(self.metadata_label)
        self.synthetic_button = button('Synthetic review', self.load_synthetic_review, recordings_layout)
        self.load_button = button('Load recording', self.load_selected, recordings_layout)
        self.models_button = button('SMPL-X model folder…', self.choose_models, recordings_layout)
        self.diagnostics_button = button('Diagnostics…', self.show_diagnostics, recordings_layout)
        self.screenshot_button = button('Export screenshot…', lambda:self.choose_export(False), recordings_layout)
        self.video_button = button('Export video…', lambda:self.choose_export(True), recordings_layout)
        recordings_layout.addStretch(1)
        self.cancel = QPushButton('Cancel export')
        self.cancel.clicked.connect(self.controller.cancel_export)
        policy = self.cancel.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.cancel.setSizePolicy(policy)
        self.cancel.setVisible(False)
        recordings_layout.addWidget(self.cancel)
        self.recordings_panel = recordings_panel
        self.recordings_dock = self._make_dock(
            'Recordings', recordings_panel, Qt.DockWidgetArea.RightDockWidgetArea,
            'recordings_panel')

        # Side panels own both corners so they extend beside (and visually eat
        # into) the bottom Visualization dock instead of stopping above it.
        self.setCorner(Qt.Corner.TopLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)

        for dock in (self.smartglasses_dock,self.visualization_dock,self.recordings_dock):
            dock.hide()
        self.smartglasses_dock.visibilityChanged.connect(self._sync_panel_buttons)
        self.visualization_dock.visibilityChanged.connect(self._sync_panel_buttons)
        self.recordings_dock.visibilityChanged.connect(self._sync_panel_buttons)
        self.recordings.currentIndexChanged.connect(self.describe_selected)
        self.controller.recordings_found.connect(self.found_recordings)
        self.controller.load_failed.connect(self.metadata_label.setText)
        self.controller.loading_changed.connect(self.sync)
        self.controller.changed.connect(self.sync)
        self.controller.status.connect(self.statusBar().showMessage)
        self.controller.export_failed.connect(lambda message: QMessageBox.warning(self, 'Export failed', message))
        self.statusBar().showMessage('Choose where to save each screenshot or video.')
        self.statusBar().hide()
        self.controller.refresh()
        if dataset:
            self.controller.discover_recordings(dataset)

    def _make_dock(self, title, widget, area, object_name):
        dock = QDockWidget(title,self)
        dock.setObjectName(object_name)
        dock.setWidget(widget)
        dock.setAllowedAreas(area)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(area,dock)
        return dock

    def _toggle_dock(self, dock):
        dock.setVisible(dock.isHidden())
        self._sync_panel_buttons()

    def _sync_panel_buttons(self, *_):
        self.smartglasses_toggle.setText(
            ('▶' if not self.smartglasses_dock.isHidden() else '◀') + ' Smartglasses')
        self.visualization_toggle.setText(
            'Visualization ' + ('▲' if not self.visualization_dock.isHidden() else '▼'))
        self.recordings_toggle.setText(
            'Recordings ' + ('◀' if not self.recordings_dock.isHidden() else '▶'))

    def _apply_panel_settings(self):
        self.controller.optical_parameters = self.panel_settings.optical_parameters
        self.viewport.optical_settings = self.panel_settings.values
        self.controller.refresh()
        self.statusBar().showMessage('Settings updated')

    def _save_user_defaults(self, values):
        if self.settings_session is not None:
            try:
                self.settings_session.save_user_defaults(values)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Could not save new defaults', str(exc))
                return False
        self.statusBar().showMessage('Saved as new defaults')
        return True

    def show_eye_test_details(self):
        self.visibility_dialog.show()
        self.visibility_dialog.raise_()
        self.visibility_dialog.activateWindow()

    def show_display_settings(self):
        self.display_settings_dialog.show()
        self.display_settings_dialog.raise_()
        self.display_settings_dialog.activateWindow()

    def inspect_participant(self, participant):
        self.orbit.setChecked(False)
        self.viewport.inspect_participant(participant,self.controller.state.frame)

    def load_synthetic_review(self):
        if self.controller.job or self.controller.loading:
            return
        self.controller.set_recording(synthetic_recording())
        self.metadata_label.setText('Synthetic review · invented paired motion · settings apply to both participants')
        self.orbit.setChecked(False)
        self.show_eye_test_details()

    def set_optical_visibility(self, key, visible):
        setattr(self.viewport,key,visible)
        self.controller.refresh()

    @suspend_animation
    def show_settings(self):
        try:
            # Pick up manual edits to values or display metadata between openings.
            store = PanelSettings(self.panel_settings.path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.warning(self, 'Settings unavailable', str(exc))
            return
        dialog = SettingsDialog(store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.panel_settings = store
            self.controller.optical_parameters = store.optical_parameters
            self.viewport.optical_settings = store.values
            self.controller.refresh()
            self.statusBar().showMessage('Settings saved')

    def found_recordings(self, infos):
        self.infos = infos
        self.recordings.clear()
        for info in infos:
            self.recordings.addItem(f'{info.name} · {info.split}', info)
        if infos:
            self.load_selected()
        else:
            self.metadata_label.setText('No matching camera-wearer/interactee SMPL-X recording directories found.')

    def describe_selected(self):
        info = self.recordings.currentData()
        if info:
            self.metadata_label.setText(
                f'{info.scene} · source frames {info.start}–{info.end} · 30 Hz Kinect cadence · '
                f'A: wearer/body {info.body_indices[0]} · B: interactee/body {info.body_indices[1]} · '
                'Select Load recording to validate paired frames.')

    def load_selected(self):
        info = self.recordings.currentData()
        if info:
            self.controller.load_recording(info, self.model_dir)

    @suspend_animation
    def choose_models(self):
        folder = QFileDialog.getExistingDirectory(self, 'Folder containing SMPLX_MALE.npz / SMPLX_FEMALE.npz', str(self.model_dir))
        if folder:
            self.model_dir = Path(folder)
            self.load_selected()

    @suspend_animation
    def show_diagnostics(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Recording and placement diagnostics')
        dialog.resize(760,560)
        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setReadOnly(True)
        recording, frame = self.controller.recording, self.controller.state.frame
        diagnostics = {**recording.metadata, 'current_source_frame': int(recording.frame_ids[frame]),
                       'current_valid': recording.valid[:,frame].tolist(),
                       'current_pelvis_m': recording.joints[:,frame,0].tolist(),
                       'current_head_transforms': recording.heads[:,frame].tolist(),
                       'current_eye_centers_m': None if recording.eyes is None else recording.eyes[:,frame].tolist(),
                       'optical_settings': self.panel_settings.values}
        text.setPlainText(json.dumps(diagnostics, indent=2))
        layout.addWidget(text)
        dialog.exec()

    @suspend_animation
    def choose_export(self, video):
        controller = self.controller
        was_playing = controller.state.playing
        controller.state.playing = False
        controller.orbit_suspended = True
        self.sync()
        destination, settings = None, None
        try:
            if video:
                dialog = VideoExportDialog(
                    controller.recording, self.viewport.capture_size(),
                    controller.export_start, controller.export_end, self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    destination, settings = dialog.destination, dialog.settings
                    controller.set_export_range(dialog.start_frame.value()-1, dialog.end_frame.value()-1)
            else:
                destination = choose_file(self, default_filename(controller.recording, False), False)
        finally:
            controller.orbit_suspended = False
            controller.state.playing = was_playing
            controller.last = monotonic()
            self.sync()
        if destination:
            if video:
                controller.export_video(destination, overwrite=True, settings=settings)
            else:
                controller.save_screenshot(destination, overwrite=True)

    def sync(self):
        result = self.controller.current_visibility
        self.visibility_label.setText(visibility_summary(result))
        details = visibility_details(result,self.controller.optical_parameters)
        if details != self.visibility_text.toPlainText():
            scroll = self.visibility_text.verticalScrollBar().value()
            self.visibility_text.setPlainText(details)
            self.visibility_text.verticalScrollBar().setValue(scroll)
        state = self.controller.state
        with QSignalBlocker(self.slider):
            self.slider.setRange(0,state.frame_count-1)
            self.slider.setValue(state.frame)
        recording = self.controller.recording
        self.counter.setText(f'{state.frame+1} / {state.frame_count} · '
                             f'{recording.timestamps[state.frame]:.2f} s · ID {recording.frame_ids[state.frame]}')
        if recording.metadata and getattr(self, "_described_recording", None) is not recording:
            self.metadata_label.setText(f'{recording.name} · {recording.metadata["scene"]} · '
                                       f'{recording.metadata["paired_frames"]}/{recording.frame_count} paired valid · '
                                       f'{recording.fps:g} Hz · {recording.metadata["cache_status"]}')
            self._described_recording = recording
        self.play.setIcon(self._pause_icon if state.playing else self._play_icon)
        self.play.setAccessibleName('Pause' if state.playing else 'Play')
        busy = self.controller.job is not None
        if busy and self._export_size_limits is None:
            self._export_size_limits = (self.minimumSize(), self.maximumSize())
            self.setFixedSize(self.size())
        elif not busy and self._export_size_limits is not None:
            minimum, maximum = self._export_size_limits
            self.setMinimumSize(minimum)
            self.setMaximumSize(maximum)
            self._export_size_limits = None
        loading = self.controller.loading is not None
        usable = bool(recording.valid.any())
        self.synthetic_button.setEnabled(not busy and not loading)
        self.load_button.setEnabled(not busy and not loading and bool(self.infos))
        self.recordings.setEnabled(not busy and not loading)
        self.models_button.setEnabled(not busy and not loading)
        self.controls.setEnabled(not busy and not loading and usable)
        self.smartglasses_panel.setEnabled(not busy)
        self.screenshot_button.setEnabled(not busy and not loading and usable)
        self.video_button.setEnabled(not busy and not loading and usable)
        self.viewport.setEnabled(not busy)
        self.cancel.setVisible(busy)

    def closeEvent(self,event):
        self.controller.close()
        self.viewport.close()
        self.display_settings_dialog.close()
        self.visibility_dialog.close()
        if self.settings_session is not None:
            try:
                self.settings_session.clean_close()
            except OSError as exc:
                # Leaving Current in place is safer than pretending a clean close succeeded.
                QMessageBox.warning(self, 'Settings recovery retained',
                                    f'Could not clear live settings: {exc}')
        event.accept()
