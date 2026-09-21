"""Background analysis with a bounded latest-frame mailbox, rendered at 30 Hz."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from copy import deepcopy
from threading import Event, Lock
from time import monotonic
from PySide6.QtCore import QObject, QTimer, Signal
from eyeglow_egobody.analysis.batch import run_batch


class PlaylistAnalysis(QObject):
    changed = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='playlist-analysis')
        self.future = None
        self.cancelled = Event()
        self.lock = Lock()
        self.latest = None
        self.progress = (0, 0)
        self.message = ''
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.poll)

    @property
    def busy(self):
        return self.future is not None

    def start(self, infos, catalog, playlist, settings, model_dir, destination, overwrite=False):
        if self.busy:
            return
        c = self.controller
        c.load_cancel.set()
        c.load_generation += 1
        c.loading = None
        c.playlist_resume = False
        c.state.playing = False
        if c.playlist is not playlist:
            # Adopt the exact index used by preview without starting another loader.
            from eyeglow_egobody.model.state import PlaybackState
            c.playlist = playlist
            c.state = PlaybackState(max(1, playlist.frame_count), 30., speed=c.state.speed, loop=c.state.loop)
        c.analysis_active = True
        self.latest = None
        self.progress = (0, 0)
        self.cancelled = Event()
        self.message = 'Preparing activities playlist analysis…'
        self.future = self.pool.submit(run_batch, tuple(infos), catalog, playlist.selections,
                                       deepcopy(settings), model_dir, destination, self.cancelled,
                                       self._progress, overwrite, self._preview)
        self.timer.start()
        self.changed.emit()

    def _progress(self, current, total):
        with self.lock:
            self.progress = (current, total)

    def _preview(self, recording, frame):
        with self.lock:
            self.latest = (recording, frame)

    def poll(self):
        if self.future is None:
            return
        with self.lock:
            latest, self.latest = self.latest, None
            current, total = self.progress
        if latest is not None:
            self.controller.show_analysis_frame(*latest)
        if not self.cancelled.is_set():
            self.message = f'Analyzing activities playlist: {current} / {total}'
        if self.future.done():
            future, self.future = self.future, None
            self.timer.stop()
            self.controller.analysis_active = False
            self.controller.last = monotonic()
            try:
                self.message = f'Saved {future.result()}'
            except CancelledError:
                self.message = 'Analysis cancelled. No output was published.'
            except Exception as exc:
                self.message = f'Analysis failed: {exc}'
        self.changed.emit()

    def cancel(self):
        self.cancelled.set()
        self.message = 'Cancelling analysis…'
        self.changed.emit()

    def shutdown(self):
        self.cancelled.set()
        self.timer.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
