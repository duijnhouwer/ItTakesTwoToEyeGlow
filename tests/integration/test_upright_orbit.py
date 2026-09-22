"""Exercise the VTK orbit style without opening an OpenGL context."""
import numpy as np
import pytest
import pyvista as pv
from types import SimpleNamespace
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindowInteractor
from vtkmodules.vtkRenderingOpenGL2 import vtkGenericOpenGLRenderWindow
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTerrain
from eyeglow_egobody.rendering.viewport import Viewport


class CameraTrackingHarness:
    _participant_eye_center = Viewport._participant_eye_center
    inspect_participant = Viewport.inspect_participant
    track_participant = Viewport.track_participant

    def __init__(self, recording):
        self.recording = recording
        self.camera = pv.Camera()
        self._tracked_eye_center = None

    @property
    def camera_position(self):
        return [self.camera.position, self.camera.focal_point, self.camera.up]

    @camera_position.setter
    def camera_position(self, pose):
        self.camera.position, self.camera.focal_point, self.camera.up = pose

    def reset_camera_clipping_range(self): pass
    def update(self): pass


def tracking_recording():
    heads = np.tile(np.eye(4), (1, 4, 1, 1))
    heads[0, :, :3, 3] = ([0, 0, .8], [1, 2, 1.3], [2, 3, 1.5], [4, 5, 1.8])
    eyes = np.array([[
        [[-.03, 0, 1], [.03, 0, 1]],
        [[.97, 2, 1.5], [1.03, 2, 1.5]],
        [[1.97, 3, 1.7], [2.03, 3, 1.7]],
        [[3.97, 5, 2], [4.03, 5, 2]],
    ]])
    return SimpleNamespace(heads=heads, eyes=eyes,
                           valid=np.array([[True, True, False, True]]))


@pytest.mark.parametrize('delta', [(30,0),(0,20),(30,20),(-30,-20)])
def test_orbit_keeps_world_up_and_pivot(delta):
    renderer = vtkRenderer()
    window = vtkGenericOpenGLRenderWindow()
    window.AddRenderer(renderer)
    window.SetSize(800,600)
    interactor = vtkRenderWindowInteractor()
    interactor.SetRenderWindow(window)
    interactor.EnableRenderOff()
    style = vtkInteractorStyleTerrain()
    interactor.SetInteractorStyle(style)
    style.SetCurrentRenderer(renderer)
    camera = renderer.GetActiveCamera()
    camera.SetPosition(4,-6,3.4)
    camera.SetFocalPoint(0,0,.9)
    camera.SetViewUp(0,0,1)
    distance = camera.GetDistance()
    initial = camera.GetPosition()
    try:
        for _ in range(100):
            interactor.SetEventPosition(400+delta[0],300+delta[1])
            interactor.SetLastEventPosition(400,300)
            style.Rotate()
            np.testing.assert_allclose(camera.GetViewUp(),(0,0,1))
            np.testing.assert_allclose(camera.GetFocalPoint(),(0,0,.9))
            assert camera.GetDistance() == pytest.approx(distance)
            # Positive projected world-up prevents the horizon from flipping.
            forward = np.array(camera.GetDirectionOfProjection())
            assert abs(forward[2]) < 1
        assert not np.allclose(camera.GetPosition(),initial)
    finally:
        window.Finalize()


def test_automatic_orbit_rotates_about_world_z_without_changing_height():
    camera = pv.Camera()
    camera.position = (3,2,5)
    camera.focal_point = (1,2,3)
    camera.up = (0,0,1)
    viewport = SimpleNamespace(camera=camera, reset_camera_clipping_range=lambda: None, update=lambda: None)
    Viewport.orbit_by(viewport,90)
    np.testing.assert_allclose(camera.position,(1,4,5),atol=1e-12)
    np.testing.assert_allclose(camera.focal_point,(1,2,3))
    np.testing.assert_allclose(camera.up,(0,0,1))
    Viewport.orbit_by(viewport,-90)
    np.testing.assert_allclose(camera.position,(3,2,5),atol=1e-12)


def test_tracking_initializes_existing_close_up_pose_at_cyclopean_eye():
    viewport = CameraTrackingHarness(tracking_recording())
    viewport.inspect_participant(0, 0)
    np.testing.assert_allclose(viewport.camera.position, (.35, .65, 1.25))
    np.testing.assert_allclose(viewport.camera.focal_point, (0, 0, 1))
    np.testing.assert_allclose(viewport.camera.up, (0, 0, 1))
    np.testing.assert_allclose(viewport._tracked_eye_center, (0, 0, 1))


def test_tracking_preserves_user_edited_camera_to_eye_vector():
    viewport = CameraTrackingHarness(tracking_recording())
    viewport.inspect_participant(0, 0)
    # This arbitrary pose represents any combination of orbit, zoom, and pan.
    viewport.camera.position = (2, -1, 4)
    viewport.camera.focal_point = (.4, .2, 1.1)
    expected_offset = np.array(viewport.camera.position) - np.array((0, 0, 1))

    viewport.track_participant(0, 1)

    new_eye = np.array((1, 2, 1.5))
    np.testing.assert_allclose(viewport.camera.position, new_eye + expected_offset)
    np.testing.assert_allclose(viewport.camera.focal_point, new_eye)
    np.testing.assert_allclose(viewport.camera.up, (0, 0, 1))
    assert viewport.camera.distance == pytest.approx(np.linalg.norm(expected_offset))


def test_tracking_holds_on_invalid_frame_and_recovers_from_last_valid_eye():
    viewport = CameraTrackingHarness(tracking_recording())
    viewport.inspect_participant(0, 1)
    viewport.camera.position = (3, 1, 3)
    held_position = np.array(viewport.camera.position)
    held_eye = viewport._tracked_eye_center.copy()

    viewport.track_participant(0, 2)
    np.testing.assert_allclose(viewport.camera.position, held_position)
    np.testing.assert_allclose(viewport._tracked_eye_center, held_eye)

    viewport.track_participant(0, 3)
    new_eye = np.array((4, 5, 2))
    np.testing.assert_allclose(
        viewport.camera.position, new_eye + held_position - held_eye)
    np.testing.assert_allclose(viewport.camera.focal_point, new_eye)


def test_tracking_center_falls_back_to_head_origin_without_eye_data():
    recording = tracking_recording()
    recording.eyes = None
    viewport = CameraTrackingHarness(recording)
    np.testing.assert_allclose(
        viewport._participant_eye_center(0, 1), (1, 2, 1.3))
