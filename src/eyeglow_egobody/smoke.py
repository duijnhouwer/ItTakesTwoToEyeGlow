"""Source and frozen GUI smoke test, driven by the real Qt event loop."""
import json
import platform
import os
from pathlib import Path
import time
import traceback
from PySide6.QtCore import QTimer
from PIL import Image
import numpy as np


def check_fit_pickle_loading():
    """Exercise dynamic NumPy imports inside the frozen build as well as source."""
    import io
    import pickle
    from eyeglow_egobody.egobody.loading import ArrayUnpickler

    expected = np.arange(6, dtype=np.float64).reshape(2, 3)
    payload = pickle.dumps({'transl': expected}, protocol=2)
    # Protocol 2 GLOBAL names have no length prefix or frame checksum.
    legacy = payload.replace(b'numpy._core.multiarray\n', b'numpy.core.multiarray\n')
    for data in (legacy, payload, pickle.dumps({'transl': expected}, protocol=5)):
        result = ArrayUnpickler(io.BytesIO(data), encoding='latin1').load()
        np.testing.assert_array_equal(result['transl'], expected)
    # Protocol 5 arrays may refer to either generation of the numeric module.
    unpickler = ArrayUnpickler(io.BytesIO())
    for module in ('numpy.core.numeric', 'numpy._core.numeric'):
        restore = unpickler.find_class(module, '_frombuffer')
        np.testing.assert_array_equal(
            restore(expected.tobytes(), expected.dtype, expected.shape, 'C'), expected)


def check_optical_rendering(window):
    """Exercise geometry changes against live VTK actors, without saving user settings."""
    from dataclasses import replace
    from eyeglow_egobody.analysis.geometry import build_frustum, waveguide_centers
    controller = window.controller
    original = controller.optical_parameters
    actors = tuple(window.viewport.stable_actors)
    try:
        for mode in ('binocular','monocular_left','monocular_right'):
            changed = replace(original, expander_width_mm=28,expander_offset_up_mm=4,
                              diagonal_fov_deg=35,ui_line_azimuth_deg=12,display_mode=mode)
            controller.optical_parameters = changed
            controller.refresh()
            for participant in range(2):
                frame = controller.state.frame
                rotation = controller.recording.heads[participant,frame,:3,:3]
                centers = waveguide_centers(controller.recording.eyes[participant,frame],rotation,changed)
                for eye,part in enumerate(window.viewport.optics.eyes[participant]):
                    np.testing.assert_allclose(part.frustum.points,build_frustum(centers[eye],rotation,changed).corners)
                    assert bool(part.actors[1].GetVisibility()) == changed.active_eyes[eye]
            assert tuple(window.viewport.stable_actors) == actors
            assert window.controller.current_visibility is window.viewport.current_visibility
    finally:
        controller.optical_parameters = original
        controller.refresh()


def start_smoke(app,window,output):
    check_fit_pickle_loading()
    check_optical_rendering(window)
    controller = window.controller
    from imageio_ffmpeg import count_frames_and_secs, read_frames
    from eyeglow_egobody.model.export_settings import VideoSettings
    actors = tuple(id(a) for a in window.viewport.stable_actors)
    state = {'stage':0,'ticks':0,'started':time.monotonic(),'last':time.monotonic(),'gaps':[],'playback_gaps':[],'rss':[]}
    timer = QTimer(window)
    timer.setInterval(50)
    window.smoke_timer = timer

    def tick():
        try:
            now = time.monotonic()
            state['gaps'].append(now-state['last'])
            state['last'] = now
            if now-state['started'] > 180:
                raise TimeoutError('Smoke test exceeded 180 seconds')
            assert tuple(id(a) for a in window.viewport.stable_actors) == actors
            if state['stage'] == 0:
                assert window.viewport.iren.style.IsA('vtkInteractorStyleTerrain')
                assert (controller.export_start,controller.export_end) == (0,299)
                from eyeglow_egobody.ui.export_dialog import VideoExportDialog
                dialog = VideoExportDialog(controller.recording,window.viewport.capture_size(),parent=window)
                dialog.start_frame.setValue(31)
                dialog.end_frame.setValue(90)
                dialog.show()
                dialog.grab().save(str(output/'video-dialog.png'))
                dialog.close()
                controller.set_export_range(30,89)
                original_size = window.viewport.capture_size()
                for size in ((1920,1080),(3840,2160)):
                    resized = window.viewport.capture(size)
                    assert resized.shape[:2] == (size[1],size[0]), resized.shape
                    assert resized.std() > 5
                    Image.fromarray(resized).save(output/f'capture-{size[0]}x{size[1]}.png')
                assert window.viewport.capture_size() == original_size
                controller.seek(120)
                window.frustum_opacity.setValue(.6)
                assert controller.state.frame == 120 and controller.frustum_opacity == .6
                for p,part in enumerate(window.viewport.parts):
                    np.testing.assert_allclose(part[0].points,controller.recording.joints[p,120])
                window.frustum_opacity.setValue(.05)
                window.viewport.reset_view()
                window.viewport.camera.azimuth += 25
                window.viewport.camera.elevation += 10
                window.viewport.camera.zoom(1.1)
                window.viewport.fit_participants()
                controller.toggle()
                state['stage'] = 1
            elif state['stage'] == 1:
                state['ticks'] += 1
                state['playback_gaps'].append(state['gaps'][-1])
                if Path('/proc/self/statm').exists():
                    state['rss'].append(int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE'))
                window.speed.setCurrentIndex((state['ticks']//10)%4)
                if state['ticks'] >= 240:
                    assert controller.state.frame != 120
                    controller.toggle()
                    controller.seek(30)
                    state['screenshot_size'] = window.viewport.capture_size()
                    controller.save_screenshot(output/'screenshot.png', overwrite=True)
                    state['stage'] = 2
            elif state['stage'] == 2 and controller.job is None:
                assert (output/'screenshot.png').exists()
                controller.export_video(output/'video.mp4', overwrite=True,
                                        settings=VideoSettings((1920,1080),24,80))
                state['stage'] = 3
            elif state['stage'] == 3 and controller.job is None:
                count, duration = count_frames_and_secs(str(output/'video.mp4'))
                assert count == 60 and abs(duration-2.5) < .05
                with Image.open(output/'screenshot.png') as image:
                    pixels = np.asarray(image)
                    assert pixels.shape[0] > 100 and pixels.std() > 5
                    assert tuple(image.size) == state['screenshot_size'], (image.size,state['screenshot_size'])
                decoded = read_frames(str(output/'video.mp4'))
                metadata = next(decoded)
                assert tuple(metadata['size']) == (1920,1080)
                assert metadata['fps'] == 24
                first = next(decoded)
                last = first
                for last in decoded:
                    pass
                assert first != last, 'Exported motion must change'
                assert controller.state.frame == 30
                report = dict(result='passed',platform=platform.platform(),architecture=platform.machine(),
                              python=platform.python_version(),actor_count=len(actors),export_frames=count,video_seconds=duration,
                              elapsed_seconds=now-state['started'],max_event_gap_seconds=max(state['gaps']),
                              playback_heartbeat_p95_seconds=float(np.percentile(state['playback_gaps'],95)),
                              playback_rss_growth_bytes=(state['rss'][-1]-state['rss'][len(state['rss'])//2]) if len(state['rss'])>10 else None,
                              graphics='; '.join(line for line in window.viewport.render_window.ReportCapabilities().splitlines() if any(key in line for key in ('vendor string','renderer string','version string'))))
                (output/'smoke-result.json').write_text(json.dumps(report,indent=2))
                window.grab().save(str(output/'window.png'))
                controller.seek(0)
                window.frustum_opacity.setValue(.05)
                window.inspect_participant(0)
                app.processEvents()
                window.viewport.render()
                window.grab().save(str(output/'optics-inspection.png'))
                print(json.dumps(report),flush=True)
                timer.stop()
                window.close()
                app.exit(0)
        except Exception:
            traceback.print_exc()
            timer.stop()
            window.close()
            app.exit(1)
    timer.timeout.connect(tick)
    timer.start()
