"""Write screenshots and stream video off the GUI thread with one pending frame."""
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from eyeglow_egobody.export.paths import safe_directory

class ImageWriter:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='png-writer')

    def submit(self, pixels, path):
        safe_directory(path.parent)
        return self.pool.submit(self._write, pixels, path)

    @staticmethod
    def _write(pixels, path):
        with path.open('xb') as output:
            Image.fromarray(pixels).save(output, format='PNG')
        return path

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)


class VideoStream:
    """Feed RGB frames from the writer thread; abort can interrupt a blocked pipe."""
    def __init__(self, folder, settings, cancelled):
        from threading import Lock
        self.result = folder / 'video.mp4'
        self.settings = settings
        self.cancelled = cancelled
        self.lock = Lock()
        self.process = None
        self.error_file = None
        self.size = None

    def write(self, pixels):
        from concurrent.futures import CancelledError
        import subprocess
        import tempfile
        import numpy as np
        from imageio_ffmpeg import get_ffmpeg_exe
        if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 3:
            raise ValueError('Video frames must be uint8 RGB arrays.')
        size = (pixels.shape[1], pixels.shape[0])
        with self.lock:
            if self.cancelled.is_set():
                raise CancelledError()
            if self.process is None:
                self.size = size
                self.error_file = tempfile.TemporaryFile()
                command = [get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                           '-nostdin', '-f', 'rawvideo', '-pixel_format', 'rgb24',
                           '-video_size', f'{size[0]}x{size[1]}',
                           '-framerate', str(self.settings.fps), '-i', 'pipe:0',
                           '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:v', 'libx264',
                           '-preset', 'fast', '-crf', str(self.settings.crf),
                           '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                           '-n', str(self.result)]
                options = {}
                if __import__('os').name == 'nt':
                    options['creationflags'] = subprocess.CREATE_NO_WINDOW
                self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL, stderr=self.error_file, **options)
        if size != self.size:
            raise ValueError('Video frame dimensions changed during export.')
        try:
            self.process.stdin.write(np.ascontiguousarray(pixels).tobytes())
        except (BrokenPipeError, OSError):
            if self.cancelled.is_set():
                raise CancelledError()
            self.process.wait()
            raise RuntimeError(self._error()) from None

    def _error(self):
        self.error_file.seek(0)
        return 'Video encoding failed: ' + self.error_file.read().decode(errors='replace')[-1500:]

    def finish(self):
        from concurrent.futures import CancelledError
        import subprocess
        if self.cancelled.is_set():
            raise CancelledError()
        self.process.stdin.close()
        while True:
            if self.cancelled.is_set():
                self.abort()
                raise CancelledError()
            try:
                code = self.process.wait(timeout=.1)
                break
            except subprocess.TimeoutExpired:
                pass
        if code:
            raise RuntimeError(self._error())
        return self.result

    def abort(self):
        # Kill without waiting so cancellation unblocks the worker's pipe write.
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                self.process.kill()

    def close(self):
        self.abort()
        if self.process is not None:
            self.process.wait()
            try:
                self.process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        if self.error_file is not None:
            self.error_file.close()
