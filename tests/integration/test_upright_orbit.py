"""Exercise the VTK orbit style without opening an OpenGL context."""
import numpy as np
import pytest
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindowInteractor
from vtkmodules.vtkRenderingOpenGL2 import vtkGenericOpenGLRenderWindow
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTerrain


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
    from types import SimpleNamespace
    import pyvista as pv
    from eyeglow_egobody.rendering.viewport import Viewport
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
