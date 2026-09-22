from concurrent.futures import Future
import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication
from eyeglow_egobody.controller import Controller
from eyeglow_egobody.model.recording import synthetic_recording


class FakeViewport:
    def set_frame(self, frame, spread, wall_spread=.40):
        self.frame, self.frustum_opacity = frame, spread
        self.frustum_wall_opacity = wall_spread

    def capture_size(self):
        return (16,16)

    def capture(self, size=None):
        width,height = size or (16,16)
        return np.zeros((height,width,3), dtype=np.uint8)


@pytest.fixture
def controller(tmp_path, qt_app):
    viewport = FakeViewport()
    controller = Controller(synthetic_recording(), viewport, tmp_path)
    controller.timer.stop()
    yield controller
    controller.close()


def test_export_cancel_restores_session(controller):
    controller.seek(20)
    controller.state.playing = True
    controller.export_video(controller.output_root/'video.mp4')
    controller._export_tick()
    controller.job['future'].result(timeout=5)
    controller.cancel_export()
    controller._export_tick()
    assert controller.job is None
    assert controller.state.frame == 20 and controller.state.playing
    assert not (controller.output_root/'video.mp4').exists()
    assert not list(controller.output_root.glob('.eyeglow-*'))


def test_export_failure_restores_session(controller):
    messages = []
    controller.status.connect(messages.append)
    controller.seek(42)
    controller.export_video(controller.output_root/'video.mp4')
    failure = Future()
    failure.set_exception(OSError('Disk full'))
    controller.job['future'] = failure
    controller._export_tick()
    assert controller.job is None
    assert controller.state.frame == 42
    assert messages[-1] == 'Export failed: Disk full'


def test_export_locks_frame_and_parameter_mutation(controller):
    controller.seek(10)
    controller.export_video(controller.output_root/'video.mp4')
    controller.seek(50)
    controller.set_frustum_opacity(.8)
    controller.toggle()
    assert controller.state.frame == 10
    assert controller.frustum_opacity == .05
    assert controller.frustum_wall_opacity == .40
    assert not controller.state.playing
    controller.cancel_export()
    controller._export_tick()


def finish_job(controller):
    for _ in range(1000):
        if controller.job is None:
            return
        future = controller.job['future']
        if future is not None:
            future.result(timeout=15)
        controller._export_tick()
    raise AssertionError('Export did not finish')


def test_default_range_and_inclusive_video(controller):
    from imageio_ffmpeg import count_frames_and_secs
    assert (controller.export_start, controller.export_end) == (0,299)
    controller.set_export_range(7,9)
    controller.seek(42)
    destination = controller.output_root/'chosen.mp4'
    controller.export_video(destination)
    finish_job(controller)
    count, duration = count_frames_and_secs(str(destination))
    assert count == 3
    assert duration == pytest.approx(.1, abs=.01)
    assert controller.state.frame == 42
    assert not list(controller.output_root.glob('.eyeglow-*'))


def test_single_frame_video_and_screenshot_replacement(controller):
    from imageio_ffmpeg import count_frames_and_secs
    controller.set_export_range(299,299)
    destination = controller.output_root/'single.mp4'
    controller.export_video(destination)
    finish_job(controller)
    assert count_frames_and_secs(str(destination))[0] == 1
    screenshot = controller.output_root/'chosen.png'
    screenshot.write_bytes(b'previous image')
    controller.save_screenshot(screenshot)
    assert controller.job is None
    assert screenshot.read_bytes() == b'previous image'
    controller.save_screenshot(screenshot, overwrite=True)
    finish_job(controller)
    assert screenshot.read_bytes().startswith(b'\x89PNG')


def test_cancel_preserves_existing_video(controller):
    destination = controller.output_root/'original.mp4'
    destination.write_bytes(b'original')
    controller.export_video(destination, overwrite=True)
    controller.cancel_export()
    controller._export_tick()
    assert destination.read_bytes() == b'original'


def test_default_exports_all_frames(controller):
    from imageio_ffmpeg import count_frames_and_secs
    destination = controller.output_root/'full.mp4'
    controller.seek(250)
    controller.export_video(destination)
    finish_job(controller)
    count, duration = count_frames_and_secs(str(destination))
    assert count == 300
    assert duration == pytest.approx(10, abs=.02)
    assert controller.state.frame == 250


def test_encoder_failure_preserves_existing_destination(controller, monkeypatch):
    monkeypatch.setenv('IMAGEIO_FFMPEG_EXE', str(controller.output_root/'missing-encoder'))
    destination = controller.output_root/'existing.mp4'
    destination.write_bytes(b'previous video')
    controller.set_export_range(0,0)
    controller.export_video(destination, overwrite=True)
    controller._export_tick()
    try:
        controller.job['future'].result(timeout=5)
    except FileNotFoundError:
        pass
    controller._export_tick()
    assert controller.job is None
    assert destination.read_bytes() == b'previous video'
    assert not list(controller.output_root.glob('.eyeglow-*'))


def test_output_file_symlink_into_dataset_is_rejected(controller):
    dataset = controller.output_root/'egobody-data'
    dataset.mkdir()
    original = dataset/'original.png'
    original.write_bytes(b'protected')
    alias = controller.output_root/'alias.png'
    alias.symlink_to(original)
    controller.save_screenshot(alias, overwrite=True)
    assert controller.job is None
    assert original.read_bytes() == b'protected'


def test_video_settings_reach_encoder(controller):
    from imageio_ffmpeg import read_frames, count_frames_and_secs
    from eyeglow_egobody.model.export_settings import VideoSettings
    controller.set_export_range(1,24)
    path = controller.output_root/'custom.mp4'
    controller.export_video(path, settings=VideoSettings((320,180),12,90))
    finish_job(controller)
    reader = read_frames(str(path))
    metadata = next(reader)
    reader.close()
    assert tuple(metadata['size']) == (320,180)
    assert metadata['fps'] == 12
    assert count_frames_and_secs(str(path)) == (24,2.0)


def test_screenshot_keeps_original_scene_pixel_size(controller):
    from PIL import Image
    controller.viewport.capture_size = lambda: (35,21)
    controller.changed.connect(lambda: setattr(controller.viewport, 'capture_size', lambda: (10,10)))
    path = controller.output_root/'original-size.png'
    controller.save_screenshot(path)
    finish_job(controller)
    with Image.open(path) as image:
        assert image.size == (35,21)


def test_auto_orbit_uses_elapsed_seconds_and_works_while_paused(controller,monkeypatch):
    from eyeglow_egobody import controller as module
    clock = [100.0]
    monkeypatch.setattr(module,'monotonic',lambda: clock[0])
    angles = []
    controller.viewport.orbit_by = angles.append
    controller.set_orbit_enabled(True)
    clock[0] += .25
    controller.tick()
    assert angles == [1.25]
    assert not controller.state.playing
    controller.set_orbit_speed(-20)
    clock[0] += .5
    controller.tick()
    assert angles[-1] == -10
    controller.orbit_suspended = True
    clock[0] += 1
    controller.tick()
    assert len(angles) == 2
    controller.orbit_suspended = False
    controller.set_orbit_enabled(False)
    clock[0] += 1
    controller.tick()
    assert len(angles) == 2


def test_stream_has_no_png_staging_and_pads_odd_size(controller):
    from imageio_ffmpeg import read_frames, count_frames_and_secs
    from eyeglow_egobody.model.export_settings import VideoSettings
    controller.set_export_range(0,2)
    path = controller.output_root/'odd.mp4'
    controller.export_video(path, settings=VideoSettings((35,21),30,90))
    controller._export_tick()
    controller.job['future'].result(timeout=5)
    assert not list(controller.job['folder'].glob('*.png'))
    finish_job(controller)
    reader = read_frames(str(path))
    assert next(reader)['size'] == (36,22)
    reader.close()
    assert count_frames_and_secs(str(path))[0] == 3


def test_close_during_stream_preserves_destination(controller):
    path = controller.output_root/'existing.mp4'
    path.write_bytes(b'original')
    controller.export_video(path, overwrite=True)
    controller._export_tick()
    controller.close()
    assert path.read_bytes() == b'original'
    assert not list(controller.output_root.glob('.eyeglow-*'))


def test_stream_preserves_rgb_colors_and_frame_order(controller):
    from imageio_ffmpeg import read_frames
    colors = [(230,20,20), (20,230,20), (20,20,230)]
    def capture(size=None):
        return np.full((16,16,3), colors[controller.viewport.frame], dtype=np.uint8)
    controller.viewport.capture = capture
    controller.set_export_range(0,2)
    path = controller.output_root/'colors.mp4'
    controller.export_video(path)
    finish_job(controller)
    reader = read_frames(str(path))
    next(reader)
    frames = list(reader)
    assert len(frames) == 3
    for frame, color in zip(frames, colors):
        pixels = np.frombuffer(frame, dtype=np.uint8).reshape(16,16,3)
        assert np.allclose(pixels.mean(axis=(0,1)), color, atol=5)
