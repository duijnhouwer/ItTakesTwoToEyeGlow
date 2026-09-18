"""Presentation-only placeholder optics; no visibility analysis is performed."""
import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D
from eyeglow_egobody.model.recording import BONES

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
        self.set_background('#172330')
        self.enable_trackball_style()
        self.add_mesh(pv.Plane(i_size=5,j_size=4), color='#53606c', opacity=.3)
        self.add_axes(color='white')
        self.parts = []
        self.stable_actors = []
        lines = np.column_stack((np.full(len(BONES),2),BONES)).ravel()
        for p,color in enumerate(('#59c9f1','#ffb56b')):
            skeleton = pv.PolyData(recording.joints[p,0].copy(), lines=lines)
            glasses = pv.PolyData(np.zeros((8,3)), lines=np.array([5,0,1,2,3,0,5,4,5,6,7,4,2,1,4]))
            frustum = pv.PolyData(np.zeros((8,3)), faces=FACES)
            for mesh, options in ((skeleton,dict(color=color,line_width=5)),
                                  (glasses,dict(color='white',line_width=4)),
                                  (frustum,dict(color=color,opacity=.18,show_edges=True))):
                self.stable_actors.append(self.add_mesh(mesh,**options))
            label = vtkBillboardTextActor3D()
            label.SetInput('A' if p == 0 else 'B')
            label.GetTextProperty().SetFontSize(24)
            label.GetTextProperty().SetColor(pv.Color(color).float_rgb)
            self.renderer.AddActor(label)
            self.stable_actors.append(label)
            self.parts.append((skeleton,glasses,frustum,label))
        # Keep captions plain: pipes trigger VTK MathText table rendering.
        self.caption = self.add_text('Synthetic motion - Placeholder optics - No visibility scores',font_size=10,color='white')
        self.set_frame(0,.35)
        self.reset_view()

    def set_frame(self, frame, spread):
        for p,(skeleton,glasses,frustum,label) in enumerate(self.parts):
            transform = self.recording.heads[p,frame]
            rot,origin = transform[:3,:3],transform[:3,3]
            skeleton.points[:] = self.recording.joints[p,frame]
            local = np.array([[-.08,.1,-.03],[-.01,.1,-.03],[-.01,.1,.03],[-.08,.1,.03],
                              [.01,.1,-.03],[.08,.1,-.03],[.08,.1,.03],[.01,.1,.03]])
            glasses.points[:] = local @ rot.T + origin
            frustum.points[:] = placeholder_points(spread) @ rot.T + origin
            for mesh in (skeleton,glasses,frustum):
                mesh.GetPoints().Modified()
                mesh.Modified()
            label.SetPosition(*(origin + [0,0,.25]))
        self.caption.SetText(2,f'Synthetic motion - Frame {frame+1}/300\nPlaceholder optics - no visibility scores')
        # Qt coalesces paints; an immediate render here would render twice
        # with the PyVistaQt 0.13 QOpenGLWidget paint path.
        self.update()

    def reset_view(self):
        self.camera_position = [(4,-6,3.4),(0,0,.9),(0,0,1)]
        self.fit_participants()

    def fit_participants(self):
        pts = self.recording.joints
        bounds = [v for axis in range(3) for v in (float(pts[...,axis].min()-.3),float(pts[...,axis].max()+.3))]
        self.reset_camera(bounds=bounds, render=False)
        self.update()

    def capture_size(self):
        return tuple(self.render_window.GetSize())

    def capture(self, size=None):
        # Export needs this exact frame before the next queued Qt paint.
        self.render()
        return self.screenshot(return_img=True, window_size=size).copy()
