"""Check live surface geometry without opening an OpenGL context."""
import numpy as np
import pyvista as pv
import pytest
from eyeglow_egobody.rendering.materials import eye_sphere_source, eye_spheres
from eyeglow_egobody.rendering.viewport import ROOM_SIZE_M, room_geometry
from eyeglow_egobody.model.recording import synthetic_recording


def test_eye_spheres_follow_centers_and_millimeter_radius_changes():
    centers = pv.PolyData(np.array([[-.03,0,1.6],[.03,0,1.6]]))
    source = eye_sphere_source(.012)
    spheres = eye_spheres(centers, source)
    spheres.Update()
    bounds = spheres.GetOutput().GetBounds()
    assert bounds[4] == pytest.approx(1.588, abs=1e-6)
    assert bounds[5] == pytest.approx(1.612, abs=1e-6)
    source.SetRadius(.015)
    centers.points[:,2] += .2
    centers.GetPoints().Modified()
    centers.Modified()
    spheres.Update()
    assert spheres.GetOutput().GetBounds()[4] == pytest.approx(1.785, abs=1e-6)
    assert spheres.GetOutput().GetBounds()[5] == pytest.approx(1.815, abs=1e-6)
    assert spheres.GetOutput().GetPointData().GetNormals() is not None


def test_room_uses_square_ground_as_floor_of_invisible_cube():
    recording = synthetic_recording()
    center, bounds = room_geometry(recording)
    assert bounds[1] - bounds[0] == pytest.approx(ROOM_SIZE_M)
    assert bounds[3] - bounds[2] == pytest.approx(ROOM_SIZE_M)
    assert bounds[5] - bounds[4] == pytest.approx(ROOM_SIZE_M)
    assert center[2] == bounds[4] == recording.metadata.get('floor_proxy_z_m', 0.)
    assert center[0] == pytest.approx((bounds[0] + bounds[1]) / 2)
    assert center[1] == pytest.approx((bounds[2] + bounds[3]) / 2)
    room = pv.Box(bounds=bounds)
    assert room.n_cells == 6
    np.testing.assert_allclose(room.bounds, bounds)
