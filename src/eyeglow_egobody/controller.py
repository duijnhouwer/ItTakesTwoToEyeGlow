from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
import os
import logging
from PySide6.QtCore import QObject, QTimer, Signal
from eyeglow_egobody.model.state import PlaybackState
from eyeglow_egobody.model.parameters import OpticalParameters
from eyeglow_egobody.analysis.visibility import analyze_visibility
from eyeglow_egobody.model.export_settings import VideoSettings
from eyeglow_egobody.export.animation import ImageWriter, VideoStream
from eyeglow_egobody.export.paths import safe_destination


class Controller(QObject):
    changed = Signal()
    recordings_found = Signal(object)
    loading_changed = Signal()
    load_failed = Signal(str)
    status = Signal(str)
    export_finished = Signal(str)
    export_failed = Signal(str)

    def __init__(self, recording, viewport, output_root, parent=None):
        super().__init__(parent)
        self.recording, self.viewport = recording, viewport
        self.output_root = output_root
        self.state = PlaybackState(recording.frame_count, recording.fps)
        self.export_start, self.export_end = 0, recording.frame_count-1
        self.optical_parameters = OpticalParameters.from_settings(getattr(viewport, "optical_settings", {}))
        self.frustum_opacity = .10
        self.current_visibility = None
        self.orbit_enabled = False
        self.orbit_speed = 5.0
        self.orbit_suspended = False
        self.writer = ImageWriter()
        self.job = None
        self.load_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="egobody")
        self.loading = None
        self.load_cancel = Event()
        self.load_generation = 0
        self.last = monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def discover_recordings(self, dataset):
        from eyeglow_egobody.egobody.discovery import discover
        self._submit_load('discovery', discover, dataset)

    def load_recording(self, info, model_dir):
        from eyeglow_egobody.egobody.loading import load_recording
        self._submit_load('recording', load_recording, info, model_dir)

    def _submit_load(self, kind, function, *args):
        if self.job:
            return
        self.load_cancel.set()
        if self.loading:
            self.loading[1].cancel()
        self.load_cancel = Event()
        self.load_generation += 1
        self.state.playing = False
        kwargs = {'cancelled': self.load_cancel} if kind == 'recording' else {}
        self.loading = (kind, self.load_pool.submit(function, *args, **kwargs), self.load_generation)
        self.status.emit('Discovering recordings…' if kind == 'discovery' else 'Loading and validating paired motion…')
        self.loading_changed.emit()
        self.changed.emit()

    def _poll_load(self):
        if not self.loading or not self.loading[1].done():
            return
        kind, future, generation = self.loading
        self.loading = None
        try:
            result = future.result()
            if generation != self.load_generation:
                return
            if kind == 'discovery':
                self.recordings_found.emit(result)
            else:
                self.set_recording(result)
                self.status.emit(f'Loaded {result.name} · {result.metadata.get("cache_status", "")}')
        except CancelledError:
            pass
        except Exception as exc:
            logging.getLogger(__name__).exception('%s loading failed', kind)
            self.status.emit(str(exc))
            self.load_failed.emit(str(exc))
        finally:
            self.loading_changed.emit()
            self.changed.emit()

    def set_recording(self, recording):
        if self.job:
            return
        speed, loop = self.state.speed, self.state.loop
        self.viewport.set_recording(recording)
        self.recording = recording
        self.state = PlaybackState(recording.frame_count, recording.fps, speed=speed, loop=loop)
        self.export_start, self.export_end = 0, recording.frame_count-1
        self.last = monotonic()
        self.refresh()

    def refresh(self):
        frame = self.state.frame
        recording = self.recording
        self.current_visibility = (None if recording.eyes is None else analyze_visibility(
            recording.heads[:,frame:frame+1], recording.eyes[:,frame:frame+1],
            recording.valid[:,frame:frame+1], self.optical_parameters))
        self.viewport.optical_parameters = self.optical_parameters
        self.viewport.current_visibility = self.current_visibility
        self.viewport.set_frame(frame, self.frustum_opacity)
        self.changed.emit()

    def seek(self, frame):
        if self.job or self.loading:
            return
        self.state.seek(frame)
        self.last = monotonic()
        self.refresh()

    def toggle(self):
        if not self.job and not self.loading:
            self.state.playing = not self.state.playing
            self.last = monotonic()
            self.changed.emit()

    def set_frustum_opacity(self, value):
        if not self.job:
            self.frustum_opacity = max(0., min(1., float(value)))
            self.refresh()

    def set_orbit_enabled(self, enabled):
        self.orbit_enabled = bool(enabled)
        self.last = monotonic()

    def set_orbit_speed(self, speed):
        self.orbit_speed = float(speed)
        self.last = monotonic()

    def set_export_range(self, start, end):
        if not 0 <= start <= end < self.recording.frame_count:
            raise ValueError('The export range must be inside the recording.')
        if not self.job:
            self.export_start, self.export_end = int(start), int(end)
            self.changed.emit()

    def tick(self):
        self._poll_load()
        now = monotonic()
        elapsed, self.last = now-self.last, now
        if self.job:
            self._export_tick()
        else:
            if self.orbit_enabled and not self.orbit_suspended:
                self.viewport.orbit_by(self.orbit_speed * elapsed)
            self._advance_playback(elapsed)

    def _advance_playback(self, elapsed):
        if self.state.playing:
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
        if self.job or self.loading or not self.recording.valid.any():
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
                            screenshot_size=self.viewport.capture_size() if not video else None, index=0, future=None, encoding=False, stream=None,
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
            if self.job['stream'] is not None:
                self.job['stream'].abort()

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
                    self.status.emit('Finalizing MP4 video…')
                    job['future'] = self.writer.pool.submit(job['stream'].finish)
                else:
                    self._commit_export(job['folder']/'frame_00000.png')
                return
            self.state.seek(job['frames'][job['index']])
            self.refresh()
            size = job['settings'].size if job['video'] else job['screenshot_size']
            pixels = self.viewport.capture(size) if size else self.viewport.capture()
            if job['video']:
                if job['stream'] is None:
                    job['stream'] = VideoStream(job['folder'], job['settings'], job['cancelled'])
                job['future'] = self.writer.pool.submit(job['stream'].write, pixels)
            else:
                job['future'] = self.writer.submit(pixels, job['folder']/'frame_00000.png')
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
        if job['stream'] is not None:
            job['stream'].close()
        job['temporary'].cleanup()
        self.state.seek(job['saved_frame'])
        self.state.playing = job['saved_playing']
        self.last = monotonic()
        self.refresh()
        self.status.emit(message)
        self.export_finished.emit(message)

    def close(self):
        self.timer.stop()
        self.load_cancel.set()
        self.load_generation += 1
        self.load_pool.shutdown(wait=False, cancel_futures=True)
        self.cancel_export()
        self.writer.close()
        if self.job:
            if self.job['stream'] is not None:
                self.job['stream'].close()
            self.job['temporary'].cleanup()
            self.job = None
