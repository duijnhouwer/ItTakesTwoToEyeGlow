"""Encode captured arrays off the GUI thread; only one pending frame is allowed."""
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


def encode_video(folder, fps, cancelled, quality=90):
    """Encode staged PNGs in a separate FFmpeg process, with bounded cancellation."""
    import subprocess
    from concurrent.futures import CancelledError
    from imageio_ffmpeg import get_ffmpeg_exe

    if cancelled.is_set():
        raise CancelledError()
    from eyeglow_egobody.model.export_settings import VideoSettings
    settings = VideoSettings(fps=fps, quality=quality)
    result = folder / 'video.mp4'
    command = [get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-framerate', str(fps), '-start_number', '0', '-i', str(folder/'frame_%05d.png'),
               '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:v', 'libx264',
               '-preset', 'fast', '-crf', str(settings.crf), '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', '-n', str(result)]
    options = {}
    if __import__('os').name == 'nt':
        options['creationflags'] = subprocess.CREATE_NO_WINDOW
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **options) as process:
        try:
            while True:
                if cancelled.is_set():
                    raise CancelledError()
                try:
                    _, error = process.communicate(timeout=.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode:
                raise RuntimeError('Video encoding failed: ' + error.decode(errors='replace')[-1500:])
            return result
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
