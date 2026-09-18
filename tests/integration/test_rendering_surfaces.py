"""Check live surface geometry without opening an OpenGL context."""
import numpy as np
import pyvista as pv
import pytest
from eyeglow_egobody.rendering.materials import eye_sphere_source, eye_spheres


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

