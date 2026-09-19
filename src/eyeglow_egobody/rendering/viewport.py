"""Head-locked rendering from the shared numeric geometry and frame results."""
import numpy as np
import pyvista as pv
from eyeglow_egobody.model.glasses import GLASSES_FACES, GLASSES_POINT_COUNT, glasses_points
from pyvistaqt import QtInteractor
from .materials import eye_sphere_source, eye_spheres
from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D

from eyeglow_egobody.model.parameters import EYEBALL_RADIUS_MM, OpticalParameters
from eyeglow_egobody.analysis.geometry import valid_transform
from eyeglow_egobody.analysis.diagnostics import visibility_summary
from .optics import OpticalScene, update_points

ROOM_SIZE_M = 5.0


def room_geometry(recording):
    """Return the visible floor center and invisible cubic room bounds."""
    valid_points = recording.joints[recording.valid]
    finite_points = valid_points[np.isfinite(valid_points).all(axis=-1)]
    xy = finite_points[:, :2].mean(axis=0) if finite_points.size else np.zeros(2)
    floor = float(recording.metadata.get('floor_proxy_z_m', 0.))
    half = ROOM_SIZE_M / 2
    center = np.array([xy[0], xy[1], floor])
    bounds = (xy[0] - half, xy[0] + half,
              xy[1] - half, xy[1] + half,
              floor, floor + ROOM_SIZE_M)
    return center, bounds


class Viewport(QtInteractor):
    def __init__(self, parent, recording):
        super().__init__(parent, auto_update=False, multi_samples=0)
        self.recording = recording
        self.optical_settings = dict(eye_relief_mm=13.)
        self.current_visibility = None
        self.show_frustums = True
        self.show_ui_lines = False
        self.show_axes = False
        self.show_eye_tests = True
        self.participant_actors = []
        self.eye_parts = []
        self.eye_sphere = eye_sphere_source(EYEBALL_RADIUS_MM / 1000)
        self.set_background('#172330')
        # Azimuth/elevation orbit keeps world Z upright and does not roll.
        self.enable_terrain_style(mouse_wheel_zooms=True, shift_pans=True)
        ground_center, self.room_bounds = room_geometry(recording)
        self.ground = pv.Plane(center=ground_center, i_size=ROOM_SIZE_M, j_size=ROOM_SIZE_M)
        self.add_mesh(self.ground, color='#53606c', opacity=.3)
        self.room = pv.Box(bounds=self.room_bounds)
        self.add_mesh(self.room, color='#83909c', style='wireframe', opacity=.45,
                      line_width=1, lighting=False)
        self.add_axes(color='white')
        self.parts = []
        self.stable_actors = []
        lines = np.column_stack((np.full(len(recording.bones),2),recording.bones)).ravel()
        for p,color in enumerate(('#59c9f1','#ffb56b')):
            skeleton = pv.PolyData(np.nan_to_num(recording.joints[p,0]).copy(), lines=lines)
            glasses = pv.PolyData(np.zeros((GLASSES_POINT_COUNT,3)), faces=GLASSES_FACES)
            self.stable_actors.append(self.add_mesh(skeleton, color=color, line_width=5))
            self.stable_actors.append(self.add_mesh(glasses, color='white', ambient=.4, diffuse=.6, specular=0.))
            label = vtkBillboardTextActor3D()
            label.SetInput('A' if p == 0 else 'B')
            label.GetTextProperty().SetFontSize(24)
            label.GetTextProperty().SetColor(pv.Color(color).float_rgb)
            self.renderer.AddActor(label)
            self.stable_actors.append(label)
            self.parts.append((skeleton,glasses,label))
            eyes = pv.PolyData(np.zeros((2,3)))
            eye_actors = []
            for eye in range(2):
                eye_mesh = pv.PolyData(np.zeros((1,3)))
                eye_actor = self.add_mesh(eye_spheres(eye_mesh, self.eye_sphere), color=color, specular=0.)
                eye_actor.GetProperty().SetInterpolationToGouraud()
                eye_actors.append((eye_mesh, eye_actor))
                self.stable_actors.append(eye_actor)
            self.eye_parts.append((eyes, tuple(eye_actors)))
            self.participant_actors.append(tuple(self.stable_actors[-5:]))
        # Keep captions plain: pipes trigger VTK MathText table rendering.
        self.optics = OpticalScene(self)
        self.optics.set_clip_bounds(self.room_bounds)
        self.stable_actors.extend(self.optics.actors)
        self.caption = self.add_text('Shared optical geometry - Potential visibility',font_size=10,color='white')
        self.set_frame(0,.10)
        self.reset_view()

    def set_recording(self, recording):
        self.recording = recording
        center, self.room_bounds = room_geometry(recording)
        self.ground.points = pv.Plane(center=center, i_size=ROOM_SIZE_M, j_size=ROOM_SIZE_M).points
        self.room.points = pv.Box(bounds=self.room_bounds).points
        self.optics.set_clip_bounds(self.room_bounds)
        lines = np.column_stack((np.full(len(recording.bones),2),recording.bones)).ravel()
        for p, (skeleton, _, label) in enumerate(self.parts):
            skeleton.points = np.nan_to_num(recording.joints[p,0]).copy()
            skeleton.lines = lines
            roles = recording.metadata.get('roles', ['A', 'B'])
            label.SetInput(f'{"A" if p == 0 else "B"}: {roles[p]}')
        self.set_frame(0,.10)
        self.reset_view()

    def set_frame(self, frame, opacity):
        parameters = getattr(self, "optical_parameters", None) or OpticalParameters.from_settings(self.optical_settings)
        subject_colors = (self.optical_settings.get('subject_a_color', '#59c9f1'),
                          self.optical_settings.get('subject_b_color', '#ffb56b'))
        labels = (self.optical_settings.get('subject_a_label', 'A'),
                  self.optical_settings.get('subject_b_label', 'B'))
        label_visible = (self.optical_settings.get('subject_a_label_visible', True),
                         self.optical_settings.get('subject_b_label_visible', True))
        glow_color = self.optical_settings.get('eye_glow_color', '#64f59b')
        self.eye_sphere.SetRadius(EYEBALL_RADIUS_MM / 1000)
        for p,(skeleton,glasses,label) in enumerate(self.parts):
            transform = self.recording.heads[p,frame]
            valid = bool(self.recording.valid[p,frame] and valid_transform(transform))
            for actor in self.participant_actors[p]:
                actor.SetVisibility(valid)
            if not valid:
                continue
            self.participant_actors[p][0].GetProperty().SetColor(pv.Color(subject_colors[p]).float_rgb)
            if hasattr(label, 'SetInput'):
                label.SetInput(labels[p])
                label.GetTextProperty().SetColor(pv.Color(subject_colors[p]).float_rgb)
                label.SetVisibility(label_visible[p])
            rot,origin = transform[:3,:3],transform[:3,3]
            update_points(skeleton,self.recording.joints[p,frame])
            eyes_mesh, eye_parts = self.eye_parts[p]
            eye_centers = None if self.recording.eyes is None else self.recording.eyes[p,frame]
            have_eyes = bool(eye_centers is not None and np.isfinite(eye_centers).all())
            for actor in (self.participant_actors[p][1], *(actor for _, actor in eye_parts)):
                actor.SetVisibility(have_eyes)
            if have_eyes:
                update_points(eyes_mesh,eye_centers)
                colors = np.tile(pv.Color(subject_colors[p]).int_rgb, (2, 1))
                if self.current_visibility is not None:
                    diagnostic = self.current_visibility.diagnostics[p]
                    if diagnostic.valid[0]:
                        colors[diagnostic.visible_eyes[0]] = pv.Color(glow_color).int_rgb
                for eye, (eye_mesh, eye_actor) in enumerate(eye_parts):
                    update_points(eye_mesh, eye_centers[eye:eye + 1])
                    eye_actor.GetProperty().SetColor(colors[eye] / 255)
                update_points(glasses,glasses_points(eye_centers,rot,parameters.eye_relief_mm))
            label.SetPosition(*(origin + [0,0,.25]))
        self.optics.update(self.recording,frame,parameters,self.current_visibility,opacity,
                           self.show_frustums,self.show_ui_lines,self.show_axes,self.show_eye_tests,
                           subject_colors=subject_colors, eye_glow_color=glow_color)
        self.caption.SetText(2,f'{self.recording.name} - Frame {frame+1}/{self.recording.frame_count}'
                             f' - source {self.recording.frame_ids[frame]}\n'
                             + visibility_summary(self.current_visibility).replace('—','-'))
        # Qt coalesces paints; render explicitly only for export.
        self.update()

    def orbit_by(self, degrees):
        """Rotate about world Z through the current camera target, without roll."""
        angle = np.deg2rad(degrees % 360)
        c, s = np.cos(angle), np.sin(angle)
        offset = np.array(self.camera.position) - np.array(self.camera.focal_point)
        rotated = np.array([c*offset[0]-s*offset[1], s*offset[0]+c*offset[1], offset[2]])
        self.camera.position = np.array(self.camera.focal_point) + rotated
        self.camera.up = (0,0,1)
        self.reset_camera_clipping_range()
        self.update()

    def fit_optics(self):
        points = [part.geometry.corners for pair in self.optics.eyes for part in pair
                  if part.geometry is not None and part.actors[0].GetVisibility()]
        if not points:
            self.fit_participants()
            return
        points = np.concatenate(points)
        bounds = [value for axis in range(3) for value in
                  (float(points[:,axis].min()-.15),float(points[:,axis].max()+.15))]
        self.reset_camera(bounds=bounds,render=False)
        self.update()

    def inspect_participant(self, participant, frame):
        transform = self.recording.heads[participant,frame]
        if not self.recording.valid[participant,frame] or not valid_transform(transform):
            return
        center = transform[:3,3].copy()
        if self.recording.eyes is not None and np.isfinite(self.recording.eyes[participant,frame]).all():
            center = self.recording.eyes[participant,frame].mean(axis=0)
        position = center + transform[:3,:3] @ np.array([.35,.65,.25])
        self.camera_position = [position,center,(0,0,1)]
        self.reset_camera_clipping_range()
        self.update()

    def reset_view(self):
        self.camera_position = [(4,-6,3.4),(0,0,.9),(0,0,1)]
        self.fit_participants()

    def fit_participants(self):
        pts = self.recording.joints[self.recording.valid]
        if not pts.size:
            return
        bounds = [v for axis in range(3) for v in (float(pts[...,axis].min()-.3),float(pts[...,axis].max()+.3))]
        self.reset_camera(bounds=bounds, render=False)
        self.update()

    def capture_size(self):
        return tuple(self.render_window.GetSize())

    def capture(self, size=None):
        # Export needs this exact frame before the next queued Qt paint.
        self.render()
        return self.screenshot(return_img=True, window_size=size).copy()
