"""Persistent optical actors fed by the shared NumPy geometry and visibility model."""
from dataclasses import dataclass
import numpy as np
import pyvista as pv
from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D
from eyeglow_egobody.analysis.geometry import build_frustum, waveguide_centers, valid_transform
from .materials import eye_sphere_source, eye_spheres

FRUSTUM_FACES = np.array([4,0,1,2,3, 4,4,7,6,5, 4,0,4,5,1, 4,1,5,6,2,
                          4,2,6,7,3, 4,3,7,4,0])
COLORS = ('#59c9f1', '#ffb56b')
PASS_COLOR, FAIL_COLOR, INVALID_COLOR = '#64f59b', '#ff647c', '#a4acb6'


def update_points(mesh, points):
    mesh.points[:] = points
    mesh.GetPoints().Modified()
    mesh.Modified()


@dataclass
class OpticalEye:
    window: object
    frustum: object
    ui_line: object
    axes: tuple
    marker: object
    label: object
    actors: tuple
    geometry: object = None


class OpticalScene:
    """Two waveguides per person. No actor creation in playback or settings updates."""
    def __init__(self, plotter):
        self.eyes = []
        self.actors = []
        self.marker_source = eye_sphere_source(.015)
        for participant, color in enumerate(COLORS):
            pair = []
            for eye in range(2):
                window = pv.PolyData(np.zeros((4,3)), faces=[4,0,1,2,3])
                frustum = pv.PolyData(np.zeros((8,3)), faces=FRUSTUM_FACES)
                ui_line = pv.PolyData(np.zeros((2,3)), lines=[2,0,1])
                # Independent window actors; UI-line colors distinguish left/right.
                window_actor = plotter.add_mesh(window, color=color, opacity=.65,
                                                show_edges=True, edge_color='white', lighting=False)
                frustum_actor = plotter.add_mesh(frustum, color=color, opacity=.10,
                                                 show_edges=True, line_width=1, lighting=False)
                line_actor = plotter.add_mesh(ui_line, color='white' if eye == 0 else color,
                                              line_width=2, lighting=False)
                axes, axis_actors = [], []
                for axis_color in ('#fa7373','#6bdd8c','#80aaff'):
                    mesh = pv.PolyData(np.zeros((2,3)), lines=[2,0,1])
                    axes.append(mesh)
                    axis_actors.append(plotter.add_mesh(mesh, color=axis_color, line_width=3, lighting=False))
                marker = pv.PolyData(np.zeros((1,3)))
                marker_actor = plotter.add_mesh(eye_spheres(marker,self.marker_source),
                                                color=INVALID_COLOR, style='wireframe', lighting=False)
                label = vtkBillboardTextActor3D()
                label.GetTextProperty().SetFontSize(12)
                plotter.renderer.AddActor(label)
                actors = (window_actor,frustum_actor,line_actor,*axis_actors,marker_actor,label)
                pair.append(OpticalEye(window,frustum,ui_line,tuple(axes),marker,label,actors))
                self.actors.extend(actors)
            self.eyes.append(pair)

    def update(self, recording, frame, parameters, result, opacity=.10,
               show_frustums=True, show_ui_lines=True, show_axes=False, show_eye_tests=True):
        self.marker_source.SetRadius(parameters.eyeball_radius_mm/1000 + .003)
        for participant, pair in enumerate(self.eyes):
            transform = recording.heads[participant,frame]
            eyes = None if recording.eyes is None else recording.eyes[participant,frame]
            usable = (bool(recording.valid[participant,frame]) and valid_transform(transform)
                      and eyes is not None and np.isfinite(eyes).all())
            for part in pair:
                for actor in part.actors:
                    actor.SetVisibility(False)
                part.geometry = None
            if not usable:
                continue
            rotation = transform[:3,:3]
            centers = waveguide_centers(eyes,rotation,parameters)
            for eye, part in enumerate(pair):
                active = parameters.active_eyes[eye]
                geometry = build_frustum(centers[eye],rotation,parameters)
                part.geometry = geometry
                update_points(part.window,geometry.corners[:4])
                update_points(part.frustum,geometry.corners)
                update_points(part.ui_line,[geometry.center,geometry.center + geometry.direction*parameters.maximum_distance_m])
                for axis, mesh in enumerate(part.axes):
                    update_points(mesh,[geometry.center,geometry.center + rotation[:,axis]*.06])
                update_points(part.marker,eyes[eye:eye+1])
                part.actors[0].SetVisibility(active)
                part.actors[1].SetVisibility(active and show_frustums)
                part.actors[1].GetProperty().SetOpacity(opacity)
                part.actors[2].SetVisibility(active and show_ui_lines)
                for actor in part.actors[3:6]:
                    actor.SetVisibility(active and show_axes)
                valid = result is not None and bool(result.diagnostics[participant].valid[0])
                passed = valid and bool(result.diagnostics[participant].visible_eyes[0,eye])
                color = PASS_COLOR if passed else FAIL_COLOR if valid else INVALID_COLOR
                part.actors[6].GetProperty().SetColor(pv.Color(color).float_rgb)
                part.actors[6].SetVisibility(show_eye_tests)
                part.label.SetInput(f'{"AB"[participant]} {"LR"[eye]}: ' + ('PASS' if passed else 'FAIL' if valid else 'INVALID'))
                part.label.GetTextProperty().SetColor(pv.Color(color).float_rgb)
                # Separate anatomical eye labels in local space.
                part.label.SetPosition(*(eyes[eye] + rotation @ np.array([-.045 if eye == 0 else .045,0,.045])))
                part.label.SetVisibility(show_eye_tests)
