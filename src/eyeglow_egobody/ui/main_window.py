from time import monotonic
from functools import wraps
from pathlib import Path
import json
import numpy as np
from PySide6.QtCore import Qt, QSignalBlocker, QSize
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
                               QPushButton,QSlider,QDoubleSpinBox,QComboBox,QCheckBox,
                               QMessageBox,QDialog,QStyle,QDockWidget,QToolButton,
                               QFileDialog,QProgressBar,QMenu,QSizePolicy)
from eyeglow_egobody.model.recording import Recording, synthetic_recording
from eyeglow_egobody.rendering.viewport import Viewport
from eyeglow_egobody.runtime_paths import default_models
from eyeglow_egobody.controller import Controller
from eyeglow_egobody.model.panel_settings import PanelSettings
from eyeglow_egobody.ui.settings_dialog import SettingsDialog, SettingsEditor
from eyeglow_egobody.ui.export_dialog import VideoExportDialog, choose_file, default_filename
from eyeglow_egobody.ui.file_dialogs import paused_animation, save_file
from eyeglow_egobody.model.playlist import (ActivitiesPlaylist, PLAYLIST_KEYS,
                                            playlist_selections)
from eyeglow_egobody.ui.playlist_analysis import PlaylistAnalysis

def suspend_animation(method):
    """Stop the render clock throughout modal dialogs, including nested pickers."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with paused_animation(self):
            return method(self, *args, **kwargs)
    return wrapped


class MainWindow(QMainWindow):
    def __init__(self, output_root, dataset=None, model_dir=None, settings_session=None):
        super().__init__()
        self.setWindowTitle('ItTakesTwoToEyeGlow')
        self.dataset = dataset
        default_templates = default_models()
        self.model_dir = model_dir or {'female': default_templates/'SMPLX_FEMALE.npz',
                                       'male': default_templates/'SMPLX_MALE.npz'}
        self.infos = []
        self.activity_catalog = None
        self.activities_playlist = None
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
        initial_settings = self.panel_settings.values
        self.viewport.optical_settings = initial_settings
        self.viewport.set_frame(0, initial_settings['frustum_opacity'],
                                initial_settings['frustum_wall_opacity'])
        layout.addWidget(self.viewport.interactor,1)
        self.controller = Controller(recording,self.viewport,output_root,self)
        self.controller.frustum_opacity = initial_settings['frustum_opacity']
        self.controller.frustum_wall_opacity = initial_settings['frustum_wall_opacity']
        self.playlist_analysis = PlaylistAnalysis(self.controller, self)

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
        self.smartglasses_toggle = button(
            '◀ Geometry', lambda: self._toggle_dock(self.smartglasses_dock))
        self.visualization_toggle = button('Visualization ▼', lambda: self._toggle_dock(self.visualization_dock))
        self.recordings_toggle = button(
            'Playlist and analysis ▶',
            lambda: self._toggle_dock(self.recordings_dock))
        for toggle in (self.smartglasses_toggle, self.visualization_toggle,
                       self.recordings_toggle):
            toggle.setCheckable(True)
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
        button('Fit participants',self.fit_participants,camera)
        self.inspect_a_button = button(
            'Track A', lambda:self.track_participant(0), camera)
        self.inspect_b_button = button(
            'Track B', lambda:self.track_participant(1), camera)
        self.orbit = QPushButton('Orbit')
        self.orbit.setToolTip('Automatically orbit around world Z, including while playback is paused.')
        self.orbit.toggled.connect(self._set_orbit)
        camera.addWidget(self.orbit)
        for mode_button in (self.inspect_a_button, self.inspect_b_button, self.orbit):
            mode_button.setCheckable(True)
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
        actions = QHBoxLayout()
        controls_layout.addLayout(actions)
        self.display_settings_button = QToolButton()
        self.display_settings_button.setText('⚙ Viewport settings...')
        self.display_settings_button.setToolTip('Display settings')
        self.display_settings_button.setAccessibleName('Display settings')
        actions.addWidget(self.display_settings_button)
        self.screenshot_button = button(
            'Export screenshot…', lambda:self.choose_export(False), actions)
        self.video_button = button(
            'Export video…', lambda:self.choose_export(True), actions)
        for action_button in (self.display_settings_button, self.screenshot_button,
                              self.video_button):
            action_button.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        actions.addStretch(1)
        self.display_settings_dialog = QDialog(self)
        self.display_settings_dialog.setWindowTitle('Viewport settings')
        self.display_settings_dialog.setModal(False)
        self.display_settings_dialog.setFixedWidth(round(620 * .70))
        display_settings_layout = QVBoxLayout(self.display_settings_dialog)
        self.display_settings_editor = SettingsEditor(
            self.panel_settings, ('visualization',), self.display_settings_dialog,
            save_user_defaults=self._save_user_defaults,
            flat_groups=('visualization',), scrollable=False)
        self.display_settings_editor.saved.connect(self._apply_panel_settings)
        self.frustum_opacity = self.display_settings_editor.fields['frustum_opacity']
        self.frustum_wall_opacity = self.display_settings_editor.fields['frustum_wall_opacity']
        display_settings_layout.addWidget(self.display_settings_editor)
        self.display_settings_button.clicked.connect(self.show_display_settings)
        self.viewport_context_menu = QMenu(self.viewport.interactor)
        self.viewport_settings_action = self.viewport_context_menu.addAction(
            'Viewport settings...')
        self.viewport_settings_action.triggered.connect(self.show_display_settings)
        self.viewport.interactor.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.viewport.interactor.customContextMenuRequested.connect(
            lambda position: self.viewport_context_menu.exec(
                self.viewport.interactor.mapToGlobal(position)))
        row = QHBoxLayout()
        controls_layout.addLayout(row)
        self.previous_pair_clip_button = button(
            '', self._seek_previous_pair_clip, row, 'Previous activity pair clip')
        self.play = button('',self.controller.toggle,row,'Play/Pause')
        self.next_pair_clip_button = button(
            '', self._seek_next_pair_clip, row, 'Next activity pair clip')
        playback_buttons = (self.previous_pair_clip_button, self.play,
                            self.next_pair_clip_button)
        self._play_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self._pause_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        self.previous_pair_clip_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.next_pair_clip_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        self.play.setIcon(self._play_icon)
        for widget in playback_buttons:
            widget.setIconSize(QSize(14,14))
        height = max(widget.sizeHint().height() for widget in playback_buttons)
        width = 30
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
        self.models_button = button('Select input data ...', self.select_input_data, recordings_layout)
        self.activity_button = button('Edit activities playlist ...', self.edit_activities_playlist, recordings_layout)
        self.playlist_summary = QLabel('No activities playlist selected.')
        self.playlist_summary.setWordWrap(True)
        recordings_layout.addWidget(self.playlist_summary)
        self.analyze_playlist_button = button('Analyze activities playlist ...', self.analyze_activities_playlist, recordings_layout)
        self.analysis_progress = QProgressBar()
        self.analysis_progress.hide()
        recordings_layout.addWidget(self.analysis_progress)
        self.analysis_status = QLabel()
        self.analysis_status.setWordWrap(True)
        self.analysis_status.setTextFormat(Qt.TextFormat.PlainText)
        recordings_layout.addWidget(self.analysis_status)
        self.cancel_analysis_button = button('Cancel analysis', self.playlist_analysis.cancel, recordings_layout)
        self.cancel_analysis_button.hide()
        self.playlist_analysis.changed.connect(self.sync_analysis)
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
        self.controller.recordings_found.connect(self.found_recordings)
        self.controller.load_failed.connect(lambda message: self.statusBar().showMessage(message))
        self.controller.loading_changed.connect(self.sync)
        self.controller.changed.connect(self.sync)
        self.controller.status.connect(self.statusBar().showMessage)
        self.controller.export_failed.connect(lambda message: QMessageBox.warning(self, 'Export failed', message))
        self.visualization_dock.show()
        self._sync_panel_buttons()
        self.statusBar().showMessage('Choose where to save each screenshot or video.')
        self.statusBar().hide()
        self.controller.state.playing = True
        self.controller.refresh()
        if dataset:
            self.controller.discover_recordings(dataset)
            # Discovery has no playable frames yet, but the requested startup
            # state remains active and is reflected by the playback control.
            self.controller.state.playing = True
            self.controller.changed.emit()

    def _make_dock(self, title, widget, area, object_name):
        dock = QDockWidget(title,self)
        dock.setObjectName(object_name)
        dock.setWidget(widget)
        title_bar = QWidget(dock)
        title_bar.setFixedHeight(0)
        dock.setTitleBarWidget(title_bar)
        dock.setAllowedAreas(area)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(area,dock)
        return dock

    def _toggle_dock(self, dock):
        dock.setVisible(dock.isHidden())
        self._sync_panel_buttons()

    def _sync_panel_buttons(self, *_):
        self.smartglasses_toggle.setChecked(not self.smartglasses_dock.isHidden())
        self.visualization_toggle.setChecked(not self.visualization_dock.isHidden())
        self.recordings_toggle.setChecked(not self.recordings_dock.isHidden())
        self.smartglasses_toggle.setText(
            ('▶' if not self.smartglasses_dock.isHidden() else '◀') + ' Geometry')
        self.visualization_toggle.setText(
            'Visualization ' + ('▲' if not self.visualization_dock.isHidden() else '▼'))
        self.recordings_toggle.setText(
            'Playlist and analysis '
            + ('◀' if not self.recordings_dock.isHidden() else '▶'))

    def _apply_panel_settings(self):
        values = self.panel_settings.values
        self.controller.optical_parameters = self.panel_settings.optical_parameters
        self.viewport.optical_settings = values
        self.controller.frustum_opacity = values['frustum_opacity']
        self.controller.frustum_wall_opacity = values['frustum_wall_opacity']
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

    def show_display_settings(self):
        self.display_settings_dialog.adjustSize()
        self.display_settings_dialog.show()
        self.display_settings_dialog.raise_()
        self.display_settings_dialog.activateWindow()

    def _set_orbit(self, enabled):
        if enabled:
            self.inspect_a_button.setChecked(False)
            self.inspect_b_button.setChecked(False)
            self.controller.set_tracked_participant(None)
        self.controller.set_orbit_enabled(enabled)

    def track_participant(self, participant):
        selected = self.inspect_a_button if participant == 0 else self.inspect_b_button
        other = self.inspect_b_button if participant == 0 else self.inspect_a_button
        if selected.isChecked():
            other.setChecked(False)
            self.orbit.setChecked(False)
            self.controller.set_tracked_participant(participant)
        else:
            self.controller.set_tracked_participant(None)
            self.viewport.fit_participants()

    def inspect_participant(self, participant):
        """Select participant tracking for callers outside the button rail."""
        selected = self.inspect_a_button if participant == 0 else self.inspect_b_button
        selected.setChecked(True)
        self.track_participant(participant)

    def fit_participants(self):
        self.inspect_a_button.setChecked(False)
        self.inspect_b_button.setChecked(False)
        self.controller.set_tracked_participant(None)
        self.viewport.fit_participants()

    def _seek_previous_pair_clip(self):
        playlist = self.controller.playlist
        if playlist is not None:
            target = playlist.previous_pair_clip_offset(self.controller.state.frame)
            if target is not None:
                self.controller.seek(target)

    def _seek_next_pair_clip(self):
        playlist = self.controller.playlist
        if playlist is not None:
            target = playlist.next_pair_clip_offset(self.controller.state.frame)
            if target is not None:
                self.controller.seek(target)

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
        if infos:
            try:
                self.ensure_activity_catalog()
                self.apply_activities_playlist()
            except (OSError, ValueError, KeyError) as exc:
                self.statusBar().showMessage(f'Activities playlist unavailable: {exc}')
                self.controller.load_recording(infos[0], self.model_dir)

    def ensure_activity_catalog(self):
        from eyeglow_egobody.analysis.activities import ActivityCatalog
        if self.activity_catalog is None:
            self.activity_catalog = ActivityCatalog(Path(self.dataset) / 'Motion-X-main' /
                'mocap-dataset-process' / 'egobody_description_all.csv')

    def apply_activities_playlist(self):
        selections = playlist_selections(self.panel_settings.values,
                                         self.activity_catalog.labels)
        self.activities_playlist = ActivitiesPlaylist(self.infos, self.activity_catalog,
                                                       selections)
        self.playlist_summary.setText(self.activities_playlist.summary)
        self.controller.set_playlist(self.activities_playlist, self.model_dir)
        self.sync()

    @suspend_animation
    def edit_activities_playlist(self):
        from eyeglow_egobody.ui.activity_dialog import ActivitiesPlaylistDialog
        try:
            self.ensure_activity_catalog()
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, 'Activity annotations unavailable', str(exc))
            return
        self.controller.state.playing = False
        dialog = ActivitiesPlaylistDialog(self.infos, self.activity_catalog, self.panel_settings,
                                           self._save_user_defaults, self)
        dialog.exec()
        self.apply_activities_playlist()
        dialog.deleteLater()

    @suspend_animation
    def analyze_activities_playlist(self):
        playlist = self.activities_playlist
        if playlist is None or not playlist.frame_count or self.playlist_analysis.busy:
            return
        name, _ = save_file(self, 'Analyze activities playlist ...',
            str(Path.home()/'activity-analysis.jsonl'), 'JSON Lines (*.jsonl)',
            options=QFileDialog.Option.DontConfirmOverwrite)
        if not name:
            return
        destination = Path(name)
        if not destination.suffix:
            destination = destination.with_suffix('.jsonl')
        overwrite = destination.exists()
        if overwrite and QMessageBox.question(self, 'Replace file?', f'Replace {destination.name}?') != QMessageBox.StandardButton.Yes:
            return
        self.playlist_analysis.start(self.infos, self.activity_catalog, playlist,
            self.panel_settings.document, self.model_dir, destination, overwrite)

    def sync_analysis(self):
        analysis = self.playlist_analysis
        self.analysis_status.setText(analysis.message)
        self.analysis_progress.setVisible(analysis.busy)
        current, total = analysis.progress
        self.analysis_progress.setRange(0, total)
        self.analysis_progress.setValue(current)
        self.cancel_analysis_button.setVisible(analysis.busy)
        self.sync()

    @suspend_animation
    def select_input_data(self):
        from eyeglow_egobody.ui.input_data_dialog import InputDataDialog
        dialog = InputDataDialog(self.panel_settings, self._save_user_defaults, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            from eyeglow_egobody.ui.input_data_dialog import FIELDS
            values = self.panel_settings.values
            self.dataset = Path(values[FIELDS[0]])
            self.model_dir = {'female': Path(values[FIELDS[1]]), 'male': Path(values[FIELDS[2]])}
            self.infos = []
            self.activity_catalog = None
            self.activities_playlist = None
            self.controller.discover_recordings(self.dataset)

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
                timeline = controller.playlist or controller.recording
                dialog = VideoExportDialog(
                    timeline, self.viewport.capture_size(),
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
        state = self.controller.state
        with QSignalBlocker(self.slider):
            self.slider.setRange(0,state.frame_count-1)
            self.slider.setValue(state.frame)
        recording = self.controller.recording
        frame = self.controller.source_frame
        playlist = self.controller.playlist
        if playlist is not None:
            current_clip = playlist.pair_clip_number(state.frame) if playlist.frame_count else 0
            current_seconds = state.frame / playlist.fps if playlist.frame_count else 0
            self.counter.setText(
                f'{current_clip} / {len(playlist.pair_clip_offsets)} activity pair clips · '
                f'{current_seconds:.2f} / {playlist.duration_s:.2f} s')
        else:
            self.counter.setText(f'{state.frame+1} / {state.frame_count} · '
                                 f'{recording.timestamps[frame]:.2f} s · ID {recording.frame_ids[frame]}')
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
        analyzing = self.playlist_analysis.busy
        locked = busy or analyzing
        usable = bool(playlist.frame_count) if playlist is not None else bool(recording.valid.any())
        self.activity_button.setEnabled(not locked and bool(self.infos))
        self.analyze_playlist_button.setEnabled(not locked and self.activities_playlist is not None
                                                and bool(self.activities_playlist.frame_count))
        self.models_button.setEnabled(not locked and not loading)
        self.controls.setEnabled(not locked and usable and (not loading or playlist is not None))
        self.play.setEnabled(not locked and not loading and usable)
        can_navigate = not locked and not loading and playlist is not None
        self.previous_pair_clip_button.setEnabled(
            can_navigate
            and playlist.previous_pair_clip_offset(state.frame) is not None)
        self.next_pair_clip_button.setEnabled(
            can_navigate and playlist.next_pair_clip_offset(state.frame) is not None)
        self.smartglasses_panel.setEnabled(not locked)
        self.screenshot_button.setEnabled(not locked and not loading and usable)
        self.video_button.setEnabled(not locked and not loading and usable)
        self.viewport.setEnabled(not busy)
        self.cancel.setVisible(busy)

    def closeEvent(self,event):
        self.playlist_analysis.shutdown()
        self.controller.close()
        self.viewport.close()
        self.display_settings_dialog.close()
        if self.settings_session is not None:
            try:
                self.settings_session.clean_close()
            except OSError as exc:
                # Leaving Current in place is safer than pretending a clean close succeeded.
                QMessageBox.warning(self, 'Settings recovery retained',
                                    f'Could not clear live settings: {exc}')
        event.accept()
