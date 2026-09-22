"""Persistent optical actors fed by the shared NumPy geometry and visibility model."""
from dataclasses import dataclass
import numpy as np
import pyvista as pv
from vtkmodules.vtkCommonDataModel import vtkPlane, vtkPlaneCollection
from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D
from eyeglow_egobody.analysis.geometry import build_frustum, waveguide_centers, valid_transform
from eyeglow_egobody.model.parameters import EYEBALL_RADIUS_MM
from .materials import eye_sphere_source, eye_spheres

FRUSTUM_FACES = np.array([4,0,1,2,3, 4,4,7,6,5, 4,0,4,5,1, 4,1,5,6,2,
                          4,2,6,7,3, 4,3,7,4,0])
FRUSTUM_EDGES = ((0,1),(1,2),(2,3),(3,0), (4,5),(5,6),(6,7),(7,4),
                 (0,4),(1,5),(2,6),(3,7))
COLORS = ('#59c9f1', '#ffb56b')
PASS_COLOR, FAIL_COLOR, INVALID_COLOR = '#64f59b', '#ff647c', '#a4acb6'


def update_points(mesh, points):
    mesh.points[:] = points
    mesh.GetPoints().Modified()
    mesh.Modified()


def update_polygons(mesh, polygons):
    """Replace persistent polygon faces without replacing their shared actor."""
    polygons = [np.asarray(points, dtype=float).reshape((-1, 3))
                for points in polygons if len(points) >= 3]
    if polygons:
        mesh.points = np.vstack(polygons)
        faces, offset = [], 0
        for points in polygons:
            faces.extend((len(points), *(offset + np.arange(len(points)))))
            offset += len(points)
        mesh.faces = np.asarray(faces, dtype=int)
    else:
        mesh.points = np.empty((0, 3))
        mesh.faces = np.empty(0, dtype=int)
    mesh.Modified()


def _clip_polygon_axis(polygon, coordinate, boundary, keep_greater):
    """Sutherland-Hodgman clipping for one 2-D axis-aligned boundary."""
    if not polygon:
        return []
    result = []
    previous = polygon[-1]
    previous_inside = (previous[coordinate] >= boundary if keep_greater
                       else previous[coordinate] <= boundary)
    for current in polygon:
        current_inside = (current[coordinate] >= boundary if keep_greater
                          else current[coordinate] <= boundary)
        if current_inside != previous_inside:
            delta = current[coordinate] - previous[coordinate]
            fraction = 0. if abs(delta) < 1e-12 else (boundary - previous[coordinate]) / delta
            result.append(previous + fraction * (current - previous))
        if current_inside:
            result.append(current)
        previous, previous_inside = current, current_inside
    return result


def wall_footprints(geometry, bounds, tolerance=1e-9):
    """Return clipped frustum cross-sections on every intersected room surface."""
    bounds = np.asarray(bounds, dtype=float).reshape((3, 2))
    footprints = []
    for axis in range(3):
        plane_axes = [value for value in range(3) if value != axis]
        for boundary in bounds[axis]:
            intersections = []
            for first, second in FRUSTUM_EDGES:
                start, end = geometry.corners[first], geometry.corners[second]
                start_delta, end_delta = start[axis] - boundary, end[axis] - boundary
                if abs(start_delta) <= tolerance:
                    intersections.append(start)
                if abs(end_delta) <= tolerance:
                    intersections.append(end)
                if start_delta * end_delta < -tolerance ** 2:
                    fraction = -start_delta / (end_delta - start_delta)
                    intersections.append(start + fraction * (end - start))
            if len(intersections) < 3:
                continue
            points = np.unique(np.round(intersections, 12), axis=0)
            projected = points[:, plane_axes]
            center = projected.mean(axis=0)
            angles = np.arctan2(projected[:, 1] - center[1], projected[:, 0] - center[0])
            polygon = [point for point in projected[np.argsort(angles)]]
            for coordinate, room_axis in enumerate(plane_axes):
                polygon = _clip_polygon_axis(
                    polygon, coordinate, bounds[room_axis, 0], True)
                polygon = _clip_polygon_axis(
                    polygon, coordinate, bounds[room_axis, 1], False)
            if len(polygon) < 3:
                continue
            footprint = np.full((len(polygon), 3), boundary, dtype=float)
            footprint[:, plane_axes] = polygon
            footprints.append(footprint)
    return footprints


@dataclass
class OpticalEye:
    window: object
    frustum: object
    wall_footprint: object
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
        self.clip_planes = None
        self.room_bounds = None
        self.marker_source = eye_sphere_source(.015)
        for participant, color in enumerate(COLORS):
            pair = []
            for eye in range(2):
                window = pv.PolyData(np.zeros((4,3)), faces=[4,0,1,2,3])
                frustum = pv.PolyData(np.zeros((8,3)), faces=FRUSTUM_FACES)
                wall = pv.PolyData(np.zeros((3,3)), faces=[3,0,1,2])
                ui_line = pv.PolyData(np.zeros((2,3)), lines=[2,0,1])
                # Independent window actors; UI-line colors distinguish left/right.
                window_actor = plotter.add_mesh(window, color=color, opacity=.65,
                                                show_edges=True, edge_color='white', lighting=False)
                frustum_actor = plotter.add_mesh(frustum, color=color, opacity=.05,
                                                 show_edges=True, line_width=1, lighting=False)
                wall_actor = plotter.add_mesh(wall, color=color, opacity=.40, lighting=False)
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
                actors = (window_actor,frustum_actor,line_actor,*axis_actors,marker_actor,label,
                          wall_actor)
                pair.append(OpticalEye(window,frustum,wall,ui_line,tuple(axes),marker,label,actors))
                self.actors.extend(actors)
            self.eyes.append(pair)

    def set_clip_bounds(self, bounds):
        """Clip rendered frustum surfaces to an axis-aligned room."""
        self.room_bounds = tuple(bounds)
        x_min, x_max, y_min, y_max, z_min, z_max = bounds
        planes = vtkPlaneCollection()
        for origin, normal in (
            ((x_min, 0., 0.), (1., 0., 0.)),
            ((x_max, 0., 0.), (-1., 0., 0.)),
            ((0., y_min, 0.), (0., 1., 0.)),
            ((0., y_max, 0.), (0., -1., 0.)),
            ((0., 0., z_min), (0., 0., 1.)),
            ((0., 0., z_max), (0., 0., -1.)),
        ):
            plane = vtkPlane()
            plane.SetOrigin(*origin)
            plane.SetNormal(*normal)
            planes.AddItem(plane)
        self.clip_planes = planes
        for pair in self.eyes:
            for part in pair:
                mapper = part.actors[1].GetMapper()
                if mapper is not None:
                    mapper.SetClippingPlanes(planes)

    def update(self, recording, frame, parameters, result, opacity=.05, wall_opacity=.40,
               show_frustums=True, show_ui_lines=True, show_axes=False, show_eye_tests=True,
               subject_colors=COLORS, eye_glow_color=PASS_COLOR):
        self.marker_source.SetRadius(EYEBALL_RADIUS_MM / 1000 + .003)
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
                update_polygons(part.wall_footprint, wall_footprints(geometry, self.room_bounds)
                                if self.room_bounds is not None else ())
                update_points(part.ui_line,[geometry.center,geometry.center + geometry.direction*parameters.maximum_distance_m])
                for axis, mesh in enumerate(part.axes):
                    update_points(mesh,[geometry.center,geometry.center + rotation[:,axis]*.06])
                update_points(part.marker,eyes[eye:eye+1])
                part.actors[0].SetVisibility(active)
                subject_color = pv.Color(subject_colors[participant]).float_rgb
                glow_color = pv.Color(eye_glow_color).float_rgb
                # The expander patch and frustum surface show the emitted glow;
                # their outlines remain subject-colored for attribution.
                for actor in part.actors[:2]:
                    actor.GetProperty().SetColor(glow_color)
                    actor.GetProperty().SetEdgeColor(subject_color)
                part.actors[8].GetProperty().SetColor(glow_color)
                part.actors[2].GetProperty().SetColor(subject_color)
                part.actors[1].SetVisibility(active and show_frustums)
                part.actors[1].GetProperty().SetOpacity(opacity)
                part.actors[8].SetVisibility(
                    active and show_frustums and len(part.wall_footprint.points) >= 3)
                part.actors[8].GetProperty().SetOpacity(wall_opacity)
                part.actors[2].SetVisibility(active and show_ui_lines)
                for actor in part.actors[3:6]:
                    actor.SetVisibility(active and show_axes)
                # Eye state is now communicated by the anatomical eyeball color in Viewport.
                # Retain the old actors for stable scene lifetime, but never show pass/fail text.
                part.actors[6].SetVisibility(False)
                part.label.SetVisibility(False)
