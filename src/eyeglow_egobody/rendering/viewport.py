"""Presentation-only placeholder optics; no visibility analysis is performed."""
import numpy as np
import pyvista as pv
from eyeglow_egobody.model.glasses import GLASSES_FACES, GLASSES_POINT_COUNT, glasses_points
from pyvistaqt import QtInteractor
from .materials import eye_sphere_source, eye_spheres
from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D

FACES = np.array([4,0,1,2,3, 4,4,7,6,5, 4,0,4,5,1, 4,1,5,6,2,
                  4,2,6,7,3, 4,3,7,4,0])

def placeholder_points(spread):
    # Visual prototype only: near rectangle and manually scaled far rectangle.
    return np.array([[-.07,.1,-.025],[.07,.1,-.025],[.07,.1,.025],[-.07,.1,.025],
                     [-spread,1.15,-spread/2],[spread,1.15,-spread/2],
                     [spread,1.15,spread/2],[-spread,1.15,spread/2]])

class Viewport(QtInteractor):
    def __init__(self, parent, recording):
        super().__init__(parent, auto_update=False, multi_samples=0)
        self.recording = recording
        self.optical_settings = dict(eyeball_radius_mm=12., eye_relief_mm=13.)
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
            frustum = pv.PolyData(np.zeros((8,3)), faces=FACES)
            self.stable_actors.append(self.add_mesh(skeleton, color=color, line_width=5))
            self.stable_actors.append(self.add_mesh(glasses, color='white', ambient=.4, diffuse=.6, specular=0.))
            self.stable_actors.append(self.add_mesh(frustum, color=color, opacity=.18, show_edges=True))
            label = vtkBillboardTextActor3D()
            label.SetInput('A' if p == 0 else 'B')
            label.GetTextProperty().SetFontSize(24)
            label.GetTextProperty().SetColor(pv.Color(color).float_rgb)
            self.renderer.AddActor(label)
            self.stable_actors.append(label)
            self.parts.append((skeleton,glasses,frustum,label))
            eyes = pv.PolyData(np.zeros((2,3)))
            eye_actor = self.add_mesh(eye_spheres(eyes, self.eye_sphere), color=color, specular=0.)
            eye_actor.GetProperty().SetInterpolationToGouraud()
            self.eye_parts.append((eyes, eye_actor))
            self.stable_actors.append(eye_actor)
        # Keep captions plain: pipes trigger VTK MathText table rendering.
        self.caption = self.add_text('Synthetic motion - Placeholder optics - No visibility scores',font_size=10,color='white')
        self.set_frame(0,.35)
        self.reset_view()

    def set_recording(self, recording):
        self.recording = recording
        valid_points = recording.joints[recording.valid]
        center = valid_points.mean(axis=(0,1)) if valid_points.size else np.zeros(3)
        center[2] = recording.metadata.get('floor_proxy_z_m', 0.)
        self.ground.points = pv.Plane(center=center, i_size=5, j_size=4).points
        lines = np.column_stack((np.full(len(recording.bones),2),recording.bones)).ravel()
        for p, (skeleton, _, _, label) in enumerate(self.parts):
            skeleton.points = np.nan_to_num(recording.joints[p,0]).copy()
            skeleton.lines = lines
            roles = recording.metadata.get('roles', ['A', 'B'])
            label.SetInput(f'{"A" if p == 0 else "B"}: {roles[p]}')
        self.set_frame(0,.35)
        self.reset_view()

    def set_frame(self, frame, spread):
        self.eye_sphere.SetRadius(self.optical_settings['eyeball_radius_mm']/1000.)
        for p,(skeleton,glasses,frustum,label) in enumerate(self.parts):
            valid = bool(self.recording.valid[p,frame])
            for actor in self.stable_actors[p*5:p*5+5]:
                actor.SetVisibility(valid)
            if not valid:
                continue
            transform = self.recording.heads[p,frame]
            rot,origin = transform[:3,:3],transform[:3,3]
            skeleton.points[:] = self.recording.joints[p,frame]
            eyes_mesh, eye_actor = self.eye_parts[p]
            eye_centers = None if self.recording.eyes is None else self.recording.eyes[p,frame]
            have_eyes = bool(eye_centers is not None and np.isfinite(eye_centers).all())
            for actor in (self.stable_actors[p*5+1], self.stable_actors[p*5+2], eye_actor):
                actor.SetVisibility(have_eyes)
            if have_eyes:
                eyes_mesh.points[:] = eye_centers
                eyes_mesh.GetPoints().Modified()
                eyes_mesh.Modified()
                radius = self.optical_settings['eyeball_radius_mm']
                relief = self.optical_settings['eye_relief_mm']
                glasses.points[:] = glasses_points(eye_centers, rot, radius, relief)
                near = eye_centers.mean(axis=0) + rot[:,1] * ((radius+relief)/1000.)
                local_frustum = placeholder_points(spread)
                local_frustum[:,1] -= .1
                frustum.points[:] = local_frustum @ rot.T + near
            for mesh in (skeleton,glasses,frustum):
                mesh.GetPoints().Modified()
                mesh.Modified()
            label.SetPosition(*(origin + [0,0,.25]))
        invalid = ', '.join('AB'[p] for p in range(2) if not self.recording.valid[p,frame])
        self.caption.SetText(2,f'{self.recording.name} - Frame {frame+1}/{self.recording.frame_count}'
                             f' - source {self.recording.frame_ids[frame]}\n'
                             f'Placeholder optics - no visibility scores' +
                             (f' - INVALID: {invalid}' if invalid else ''))
        # Qt coalesces paints; an immediate render here would render twice
        # with the PyVistaQt 0.13 QOpenGLWidget paint path.
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
