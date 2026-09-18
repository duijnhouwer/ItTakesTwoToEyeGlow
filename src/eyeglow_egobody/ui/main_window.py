from time import monotonic
from PySide6.QtCore import Qt, QSignalBlocker, QSize
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
                               QPushButton,QSlider,QDoubleSpinBox,QComboBox,QCheckBox,
                               QMessageBox,QDialog,QStyle)
from eyeglow_egobody.model.recording import synthetic_recording
from eyeglow_egobody.rendering.viewport import Viewport
from eyeglow_egobody.controller import Controller
from eyeglow_egobody.ui.export_dialog import VideoExportDialog, choose_file, default_filename

class MainWindow(QMainWindow):
    def __init__(self, output_root):
        super().__init__()
        self.setWindowTitle('EyeGlow EgoBody — Phase 1 synthetic prototype')
        self.resize(1200,840)
        self._export_size_limits = None
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel('EyeGlow EgoBody · Synthetic technical spike')
        title.setStyleSheet('font-size: 21px; font-weight: bold; padding: 8px')
        layout.addWidget(title)
        layout.addWidget(QLabel('Placeholder glasses and frustums · No real recordings or visibility analysis'))
        recording = synthetic_recording()
        self.viewport = Viewport(root,recording)
        layout.addWidget(self.viewport.interactor,1)
        self.controller = Controller(recording,self.viewport,output_root,self)
        self.controls = QWidget()
        controls_layout = QVBoxLayout(self.controls)
        camera = QHBoxLayout()
        controls_layout.addLayout(camera)
        def button(label,callback,row,tooltip=None):
            widget = QPushButton(label)
            if tooltip:
                widget.setToolTip(tooltip)
                widget.setAccessibleName(tooltip)
            widget.clicked.connect(callback)
            row.addWidget(widget)
            return widget
        button('Reset camera',self.viewport.reset_view,camera)
        button('Fit participants',self.viewport.fit_participants,camera)
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
        camera.addWidget(QLabel('Placeholder spread (m)'))
        self.spread = QDoubleSpinBox()
        self.spread.setRange(.05,.8)
        self.spread.setSingleStep(.05)
        self.spread.setValue(.35)
        self.spread.valueChanged.connect(self.controller.set_spread)
        camera.addWidget(self.spread)
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
        file_menu = self.menuBar().addMenu('File')
        self.screenshot_action = file_menu.addAction('Export screenshot ...')
        self.screenshot_action.triggered.connect(lambda:self.choose_export(False))
        self.video_action = file_menu.addAction('Export video ...')
        self.video_action.triggered.connect(lambda:self.choose_export(True))
        layout.addWidget(self.controls)
        self.cancel = QPushButton('Cancel export')
        self.cancel.clicked.connect(self.controller.cancel_export)
        policy = self.cancel.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.cancel.setSizePolicy(policy)
        self.cancel.setVisible(False)
        layout.addWidget(self.cancel)
        self.setCentralWidget(root)
        self.controller.changed.connect(self.sync)
        self.controller.status.connect(self.statusBar().showMessage)
        self.controller.export_failed.connect(lambda message: QMessageBox.warning(self, 'Export failed', message))
        self.statusBar().showMessage('Choose where to save each screenshot or video.')
        self.sync()

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
        state = self.controller.state
        with QSignalBlocker(self.slider):
            self.slider.setValue(state.frame)
        self.counter.setText(f'{state.frame+1} / {state.frame_count}')
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
        self.controls.setEnabled(not busy)
        self.screenshot_action.setEnabled(not busy)
        self.video_action.setEnabled(not busy)
        self.viewport.setEnabled(not busy)
        self.cancel.setVisible(busy)

    def closeEvent(self,event):
        self.controller.close()
        self.viewport.close()
        event.accept()
