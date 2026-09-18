from concurrent.futures import CancelledError
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
import os
from PySide6.QtCore import QObject, QTimer, Signal
from eyeglow_egobody.model.state import PlaybackState
from eyeglow_egobody.model.export_settings import VideoSettings
from eyeglow_egobody.export.animation import ImageWriter, encode_video
from eyeglow_egobody.export.paths import safe_destination


class Controller(QObject):
    changed = Signal()
    status = Signal(str)
    export_finished = Signal(str)
    export_failed = Signal(str)

    def __init__(self, recording, viewport, output_root, parent=None):
        super().__init__(parent)
        self.recording, self.viewport = recording, viewport
        self.output_root = output_root
        self.state = PlaybackState(recording.frame_count, recording.fps)
        self.export_start, self.export_end = 0, recording.frame_count-1
        self.spread = .35
        self.writer = ImageWriter()
        self.job = None
        self.last = monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def refresh(self):
        self.viewport.set_frame(self.state.frame, self.spread)
        self.changed.emit()

    def seek(self, frame):
        if self.job:
            return
        self.state.seek(frame)
        self.last = monotonic()
        self.refresh()

    def toggle(self):
        if not self.job:
            self.state.playing = not self.state.playing
            self.last = monotonic()
            self.changed.emit()

    def set_spread(self, value):
        if not self.job:
            self.spread = value
            self.refresh()

    def set_export_range(self, start, end):
        if not 0 <= start <= end < self.recording.frame_count:
            raise ValueError('The export range must be inside the recording.')
        if not self.job:
            self.export_start, self.export_end = int(start), int(end)
            self.changed.emit()

    def tick(self):
        now = monotonic()
        elapsed, self.last = now-self.last, now
        if self.job:
            self._export_tick()
        elif self.state.playing:
            previous = self.state.frame
            self.state.advance(elapsed)
            if previous != self.state.frame:
                self.refresh()
            else:
                self.changed.emit()

    def save_screenshot(self, destination, overwrite=False):
        self._start_export(destination, False, overwrite)

    def export_video(self, destination, overwrite=False, settings=None):
        self._start_export(destination, True, overwrite, settings)

    def _start_export(self, destination, video, overwrite, settings=None):
        if self.job:
            return
        try:
            destination = safe_destination(destination)
            if destination.suffix.lower() != ('.mp4' if video else '.png'):
                raise ValueError('Choose an .mp4 video file.' if video else 'Choose a .png image file.')
            if destination.exists() and not overwrite:
                raise FileExistsError(f'{destination.name} already exists.')
            temporary = TemporaryDirectory(prefix='.eyeglow-', dir=destination.parent)
            frames = range(self.export_start, self.export_end+1) if video else [self.state.frame]
            self.job = dict(temporary=temporary, folder=Path(temporary.name), destination=destination,
                            frames=frames, video=video, settings=settings or VideoSettings(fps=self.recording.fps),
                            screenshot_size=self.viewport.capture_size() if not video else None, index=0, future=None, encoding=False,
                            overwrite=overwrite, saved_frame=self.state.frame,
                            saved_playing=self.state.playing, cancelled=Event())
            self.state.playing = False
            self.changed.emit()
            self.status.emit(f'Exporting to {destination}')
        except Exception as exc:
            self.status.emit(f'Export failed: {exc}')
            self.export_failed.emit(str(exc))

    def cancel_export(self):
        if self.job:
            self.job['cancelled'].set()

    def _export_tick(self):
        job = self.job
        try:
            if job['future'] is not None:
                if not job['future'].done():
                    return
                result = job['future'].result()
                job['future'] = None
                if job['cancelled'].is_set():
                    self._finish_export('Export cancelled')
                    return
                if job['encoding']:
                    self._commit_export(result)
                    return
                job['index'] += 1
                self.status.emit(f"Rendering {job['index']}/{len(job['frames'])} frames")
            if job['cancelled'].is_set():
                self._finish_export('Export cancelled')
                return
            if job['index'] == len(job['frames']):
                if job['video']:
                    job['encoding'] = True
                    self.status.emit('Encoding MP4 video…')
                    job['future'] = self.writer.pool.submit(
                        encode_video, job['folder'], job['settings'].fps, job['cancelled'], job['settings'].quality)
                else:
                    self._commit_export(job['folder']/'frame_00000.png')
                return
            self.state.seek(job['frames'][job['index']])
            self.refresh()
            size = job['settings'].size if job['video'] else job['screenshot_size']
            pixels = self.viewport.capture(size) if size else self.viewport.capture()
            job['future'] = self.writer.submit(pixels, job['folder']/f"frame_{job['index']:05d}.png")
        except CancelledError:
            self._finish_export('Export cancelled')
        except Exception as exc:
            self._finish_export(f'Export failed: {exc}')
            self.export_failed.emit(str(exc))

    def _commit_export(self, result):
        destination = safe_destination(self.job['destination'])
        if self.job['overwrite']:
            os.replace(result, destination)
        else:
            # Same-filesystem hard link publishes atomically without replacing a
            # destination that appeared after the dialog closed.
            os.link(result, destination)
        self._finish_export(f'Saved {destination}')

    def _finish_export(self, message):
        job, self.job = self.job, None
        job['temporary'].cleanup()
        self.state.seek(job['saved_frame'])
        self.state.playing = job['saved_playing']
        self.last = monotonic()
        self.refresh()
        self.status.emit(message)
        self.export_finished.emit(message)

    def close(self):
        self.timer.stop()
        self.cancel_export()
        self.writer.close()
        if self.job:
            self.job['temporary'].cleanup()
            self.job = None
