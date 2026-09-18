"""Head-locked rendering from the shared numeric geometry and frame results."""
import numpy as np
import pyvista as pv
from eyeglow_egobody.model.glasses import GLASSES_FACES, GLASSES_POINT_COUNT, glasses_points
from pyvistaqt import QtInteractor
from .materials import eye_sphere_source, eye_spheres
from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D

from eyeglow_egobody.model.parameters import OpticalParameters
from eyeglow_egobody.analysis.geometry import valid_transform
from eyeglow_egobody.analysis.diagnostics import visibility_summary
from .optics import OpticalScene, update_points

class Viewport(QtInteractor):
    def __init__(self, parent, recording):
        super().__init__(parent, auto_update=False, multi_samples=0)
        self.recording = recording
        self.optical_settings = dict(eyeball_radius_mm=12., eye_relief_mm=13.)
        self.current_visibility = None
        self.show_frustums = True
        self.show_ui_lines = True
        self.show_axes = False
        self.show_eye_tests = True
        self.participant_actors = []
        self.eye_parts = []
        self.eye_sphere = eye_sphere_source(self.optical_settings['eyeball_radius_mm']/1000.)
        self.set_background('#172330')
        # Azimuth/elevation orbit keeps world Z upright and does not roll.
        self.enable_terrain_style(mouse_wheel_zooms=True, shift_pans=True)
        self.ground = pv.Plane(i_size=5,j_size=4)
        self.add_mesh(self.ground, color='#53606c', opacity=.3)
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
            eye_actor = self.add_mesh(eye_spheres(eyes, self.eye_sphere), color=color, specular=0.)
            eye_actor.GetProperty().SetInterpolationToGouraud()
            self.eye_parts.append((eyes, eye_actor))
            self.stable_actors.append(eye_actor)
            self.participant_actors.append(tuple(self.stable_actors[-4:]))
        # Keep captions plain: pipes trigger VTK MathText table rendering.
        self.optics = OpticalScene(self)
        self.stable_actors.extend(self.optics.actors)
        self.caption = self.add_text('Shared optical geometry - Potential visibility',font_size=10,color='white')
        self.set_frame(0,.10)
        self.reset_view()

    def set_recording(self, recording):
        self.recording = recording
        valid_points = recording.joints[recording.valid]
        center = valid_points.mean(axis=(0,1)) if valid_points.size else np.zeros(3)
        center[2] = recording.metadata.get('floor_proxy_z_m', 0.)
        self.ground.points = pv.Plane(center=center, i_size=5, j_size=4).points
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
        self.eye_sphere.SetRadius(parameters.eyeball_radius_mm/1000.)
        for p,(skeleton,glasses,label) in enumerate(self.parts):
            transform = self.recording.heads[p,frame]
            valid = bool(self.recording.valid[p,frame] and valid_transform(transform))
            for actor in self.participant_actors[p]:
                actor.SetVisibility(valid)
            if not valid:
                continue
            rot,origin = transform[:3,:3],transform[:3,3]
            update_points(skeleton,self.recording.joints[p,frame])
            eyes_mesh, eye_actor = self.eye_parts[p]
            eye_centers = None if self.recording.eyes is None else self.recording.eyes[p,frame]
            have_eyes = bool(eye_centers is not None and np.isfinite(eye_centers).all())
            for actor in (self.participant_actors[p][1], eye_actor):
                actor.SetVisibility(have_eyes)
            if have_eyes:
                update_points(eyes_mesh,eye_centers)
                update_points(glasses,glasses_points(eye_centers,rot,parameters.eyeball_radius_mm,parameters.eye_relief_mm))
            label.SetPosition(*(origin + [0,0,.25]))
        self.optics.update(self.recording,frame,parameters,self.current_visibility,opacity,
                           self.show_frustums,self.show_ui_lines,self.show_axes,self.show_eye_tests)
        self.caption.SetText(2,f'{self.recording.name} - Frame {frame+1}/{self.recording.frame_count}'
                             f' - source {self.recording.frame_ids[frame]}\n'
                             + visibility_summary(self.current_visibility).replace('—','-') + '\n'
                             'Eye rings: green PASS, red FAIL, gray INVALID - potential visibility')
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
