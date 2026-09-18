"""Modal video options and shared native file-save selection."""
from pathlib import Path
import sys
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
                               QFormLayout, QLineEdit, QPushButton, QSpinBox,
                               QDoubleSpinBox, QComboBox, QLabel, QFileDialog, QMessageBox)
from eyeglow_egobody.model.export_settings import VideoSettings
from eyeglow_egobody.export.paths import safe_destination


def default_filename(recording, video):
    if sys.platform.startswith('linux'):
        directory = Path.home() / ('Videos' if video else 'Pictures')
    else:
        location = (QStandardPaths.StandardLocation.MoviesLocation if video
                    else QStandardPaths.StandardLocation.PicturesLocation)
        directory = Path(QStandardPaths.writableLocation(location) or str(Path.home()))
    return directory / (Path(recording.name).stem + ('.mp4' if video else '.png'))


def choose_file(parent, default, video):
    suffix = 'mp4' if video else 'png'
    dialog = QFileDialog(parent, 'Export Video' if video else 'Save Screenshot')
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialog.setFileMode(QFileDialog.FileMode.AnyFile)
    dialog.setNameFilter('MP4 video (*.mp4)' if video else 'PNG image (*.png)')
    dialog.setDefaultSuffix(suffix)
    dialog.selectFile(str(default))
    while dialog.exec() == QDialog.DialogCode.Accepted:
        path = Path(dialog.selectedFiles()[0]).expanduser()
        if path.suffix.lower() != '.'+suffix:
            QMessageBox.warning(parent, 'Unsupported format', f'Only {suffix.upper()} is supported. Use a .{suffix} filename.')
            dialog.selectFile(str(path))
            continue
        return path
    return None


class VideoExportDialog(QDialog):
    def __init__(self, recording, current_size, start=0, end=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Export Video')
        self.setModal(True)
        self.setMinimumWidth(620)
        self.recording = recording
        self.destination = None
        self.settings = None
        self._browse_approved = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        file_row = QHBoxLayout()
        self.filename = QLineEdit(str(default_filename(recording, True)))
        self.filename.setAccessibleName('Video output filename')
        self.browse = QPushButton('Browse ...')
        self.browse.clicked.connect(self.browse_file)
        file_row.addWidget(self.filename, 1)
        file_row.addWidget(self.browse)
        form.addRow('Output filename', file_row)
        self.start_frame = QSpinBox()
        self.end_frame = QSpinBox()
        for widget in (self.start_frame,self.end_frame):
            widget.setRange(1,recording.frame_count)
        self.start_frame.setValue(start+1)
        self.end_frame.setValue(recording.frame_count if end is None else end+1)
        self.start_frame.valueChanged.connect(self._start_changed)
        self.end_frame.valueChanged.connect(self._end_changed)
        self.start_frame.setAccessibleName('Start frame')
        self.end_frame.setAccessibleName('End frame')
        frame_row = QHBoxLayout()
        frame_row.addWidget(self.start_frame)
        frame_row.addWidget(self.end_frame)
        self.full_range = QPushButton('Full range')
        self.full_range.clicked.connect(self.reset_range)
        frame_row.addWidget(self.full_range)
        form.addRow('Start/end frame:', frame_row)
        self.frame_size = QComboBox()
        self.frame_size.addItem('3840 × 2160 (4K)', (3840,2160))
        self.frame_size.addItem('1920 × 1080 (FHD)', (1920,1080))
        self.frame_size.addItem(f'{current_size[0]} × {current_size[1]} (current)', tuple(current_size))
        self.frame_size.setCurrentIndex(2)
        self.frame_size.setToolTip('Scene pixels, excluding controls. Odd dimensions are padded by one pixel for MP4 compatibility.')
        form.addRow('Frame size', self.frame_size)
        self.fps = QDoubleSpinBox()
        self.fps.setRange(1,120)
        self.fps.setDecimals(3)
        self.fps.setValue(recording.fps)
        fps_row = QHBoxLayout()
        fps_row.addWidget(self.fps)
        self.native_fps = QPushButton(f'{recording.fps:g} (data native)')
        self.native_fps.clicked.connect(lambda: self.fps.setValue(recording.fps))
        fps_row.addWidget(self.native_fps)
        form.addRow('Framerate (fps)', fps_row)
        self.quality = QSpinBox()
        self.quality.setRange(0,100)
        self.quality.setValue(75)
        self.quality.setToolTip('Higher quality produces larger files. 0–100 maps to H.264 CRF 51–0.')
        form.addRow('Quality (0–100)', self.quality)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        help_text = QLabel('Both endpoints are included. Each selected data frame becomes one video frame.\nChanging FPS changes video duration. Higher quality produces larger files.')
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.fps.valueChanged.connect(self.update_summary)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText('Export')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.update_summary()

    def _start_changed(self, value):
        if value > self.end_frame.value():
            self.end_frame.setValue(value)
        self.update_summary()

    def _end_changed(self, value):
        if value < self.start_frame.value():
            self.start_frame.setValue(value)
        self.update_summary()

    def reset_range(self):
        self.start_frame.setValue(1)
        self.end_frame.setValue(self.recording.frame_count)

    def update_summary(self):
        count = self.end_frame.value()-self.start_frame.value()+1
        self.summary.setText(f'{count} frames · {count/self.fps.value():.2f} seconds')

    def browse_file(self):
        path = choose_file(self, self.filename.text(), True)
        if path:
            self.filename.setText(str(path))
            # The file dialog already asked about overwriting this exact file.
            self._browse_approved = path.resolve()

    def accept(self):
        name = self.filename.text().strip()
        if not name or Path(name).suffix.lower() != '.mp4':
            QMessageBox.warning(self, 'Unsupported format', 'Only MP4 is supported. Use a .mp4 filename.')
            return
        try:
            path = safe_destination(name)
            settings = VideoSettings(tuple(self.frame_size.currentData()), self.fps.value(), self.quality.value())
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self, 'Cannot export', str(exc))
            return
        if path.exists() and path != self._browse_approved:
            answer = QMessageBox.question(self, 'Replace file?', f'{path.name} already exists. Replace it?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.destination, self.settings = path, settings
        super().accept()
