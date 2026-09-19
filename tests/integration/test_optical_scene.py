"""Persistent VTK actor state and points, without requiring a display server."""
from dataclasses import replace
import numpy as np
import pytest
import pyvista as pv
from vtkmodules.vtkRenderingCore import vtkActor, vtkRenderer
from eyeglow_egobody.rendering.optics import OpticalScene
from eyeglow_egobody.analysis.geometry import build_frustum, waveguide_centers
from eyeglow_egobody.analysis.visibility import analyze_recording
from eyeglow_egobody.analysis.diagnostics import visibility_summary, visibility_details
from eyeglow_egobody.model.recording import synthetic_recording
from eyeglow_egobody.model.parameters import OpticalParameters, DisplayMode


class ActorFactory:
    def __init__(self):
        self.renderer = vtkRenderer()
    def add_mesh(self, mesh, **kwargs):
        actor = vtkActor()
        self.renderer.AddActor(actor)
        return actor


@pytest.fixture
def scene():
    return OpticalScene(ActorFactory())


@pytest.mark.parametrize('mode', list(DisplayMode))
def test_rendered_geometry_is_analysis_geometry_and_reuses_actors(scene,mode):
    recording = synthetic_recording()
    parameters = OpticalParameters(display_mode=mode,expander_width_mm=31,expander_height_mm=17,
        expander_offset_right_mm=4,expander_offset_up_mm=-6,diagonal_fov_deg=30,
        horizontal_vertical_fov_ratio=2,ui_line_azimuth_deg=14,ui_line_elevation_deg=-8,
        maximum_distance_m=3)
    actors = tuple(scene.actors)
    for frame in (0,87,120):
        scene.update(recording,frame,parameters,None,.23,show_axes=True)
        for participant in range(2):
            rotation = recording.heads[participant,frame,:3,:3]
            centers = waveguide_centers(recording.eyes[participant,frame],rotation,parameters)
            for eye, part in enumerate(scene.eyes[participant]):
                expected = build_frustum(centers[eye],rotation,parameters)
                np.testing.assert_allclose(part.frustum.points,expected.corners)
                np.testing.assert_allclose(part.window.points,expected.corners[:4])
                np.testing.assert_allclose(part.ui_line.points[1],expected.center+expected.direction*3)
                for axis,mesh in enumerate(part.axes):
                    np.testing.assert_allclose(mesh.points[1]-mesh.points[0],rotation[:,axis]*.06,atol=1e-12)
                assert bool(part.actors[0].GetVisibility()) == parameters.active_eyes[eye]
                assert bool(part.actors[1].GetVisibility()) == parameters.active_eyes[eye]
                assert part.actors[1].GetProperty().GetOpacity() == pytest.approx(.23)
        assert tuple(scene.actors) == actors


def test_immediate_parameters_toggles_and_invalid_pose(scene):
    recording = synthetic_recording()
    p = OpticalParameters()
    scene.update(recording,0,p,None)
    before = scene.eyes[0][0].window.points.copy()
    scene.update(recording,0,replace(p,expander_offset_up_mm=10),None,show_frustums=False,
                 show_ui_lines=False,show_eye_tests=False)
    np.testing.assert_allclose(scene.eyes[0][0].window.points-before,
                               np.tile(recording.heads[0,0,:3,2]*.01,(4,1)),atol=1e-12)
    assert scene.eyes[0][0].actors[0].GetVisibility()
    assert not any(a.GetVisibility() for a in scene.eyes[0][0].actors[1:])
    recording.valid[0,0] = False
    scene.update(recording,0,p,None)
    assert not any(a.GetVisibility() for part in scene.eyes[0] for a in part.actors)
    assert all(part.geometry is None for part in scene.eyes[0])
    recording.valid[0,0] = True
    recording.heads[0,0,0,0] = np.nan
    scene.update(recording,0,p,None)
    assert not any(a.GetVisibility() for part in scene.eyes[0] for a in part.actors)


def test_optical_scene_hides_pass_fail_labels(scene):
    recording = synthetic_recording()
    p = OpticalParameters()
    # Evaluate a one-frame recording so diagnostics index zero is the current frame.
    recording = replace(recording,timestamps=recording.timestamps[:1],heads=recording.heads[:,:1],
                        eyes=recording.eyes[:,:1],joints=recording.joints[:,:1],valid=recording.valid[:,:1])
    for invalid in (False,True):
        recording.valid[0,0] = not invalid
        result = analyze_recording(recording,p)
        scene.update(recording,0,p,result)
        for participant in range(2):
            if not recording.valid[participant,0]:
                continue
            for part in scene.eyes[participant]:
                assert not part.actors[6].GetVisibility()
                assert not part.label.GetVisibility()
        assert ('INVALID' if invalid else 'BOTH_EYES') in visibility_summary(result)
        details = visibility_details(result,p)
        assert ('unusable' if invalid else 'Emitter L: containment') in details


def test_display_toggles_never_change_analysis(scene):
    recording = synthetic_recording()
    p = OpticalParameters()
    expected = analyze_recording(recording,p).states.copy()
    scene.update(recording,0,p,None,show_frustums=False,show_ui_lines=False,show_axes=True,show_eye_tests=False)
    np.testing.assert_array_equal(analyze_recording(recording,p).states,expected)
