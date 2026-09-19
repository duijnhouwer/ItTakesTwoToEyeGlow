"""White Wayfarer-style frame geometry anchored to fitted eye centers (meters)."""
import numpy as np
from eyeglow_egobody.model.parameters import EYEBALL_RADIUS_MM


def _curve(anchors, steps=8, closed=False):
    anchors = np.asarray(anchors, dtype=float)
    padded = (np.vstack((anchors[-1], anchors, anchors[:2])) if closed else
              np.vstack((anchors[0], anchors, anchors[-1])))
    result = []
    for i in range(len(anchors) if closed else len(anchors)-1):
        a,b,c,d = padded[i:i+4]
        t = np.arange(steps)[:,None]/steps
        result.extend(.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
    if not closed:
        result.append(anchors[-1])
    return np.asarray(result)


# Anatomical left rim: broad brow, rounded corners, and tapered lower edge.
# Right rim mirrors this shape. The opening stays centered around the eye.
_OUTER = _curve([[-.029,.017],[-.011,.021],[.017,.018],[.026,.009],
                 [.022,-.014],[.010,-.021],[-.016,-.021],[-.024,-.014]], closed=True)
_INNER = _OUTER * [.84,.80] + [0,-.001]
RIM_SAMPLES = len(_OUTER)
RIM_POINT_COUNT = 4*RIM_SAMPLES
REAR_RIM_INDICES = (np.arange(2*RIM_SAMPLES), np.arange(2*RIM_SAMPLES)+RIM_POINT_COUNT)


def _geometry(eyes):
    """Build closed rim/bridge/temple surfaces in the head-local coordinate frame."""
    points, faces = [], []
    def quad(a,b,c,d):
        faces.extend((4,a,b,c,d))
    for center, mirror in zip(eyes, (1,-1)):
        start = len(points)
        for depth, contour in ((0,_OUTER),(0,_INNER),(.004,_OUTER),(.004,_INNER)):
            local = np.column_stack((contour[:,0]*mirror, np.full(RIM_SAMPLES,depth), contour[:,1]))
            points.extend(center + local)
        n = RIM_SAMPLES
        for i in range(n):
            j = (i+1)%n
            quad(start+i,start+j,start+n+j,start+n+i)
            quad(start+2*n+i,start+3*n+i,start+3*n+j,start+2*n+j)
            quad(start+i,start+2*n+i,start+2*n+j,start+j)
            quad(start+n+i,start+n+j,start+3*n+j,start+3*n+i)

    def sweep(sections):
        start = len(points)
        points.extend(np.asarray(sections).reshape(-1,3))
        quad(start+3,start+2,start+1,start)
        for i in range(len(sections)-1):
            a,b = start+4*i,start+4*(i+1)
            for j in range(4):
                k = (j+1)%4
                quad(a+j,a+k,b+k,b+j)
        end = start+4*(len(sections)-1)
        quad(end,end+1,end+2,end+3)

    # Raised, gently curved bridge between the upper inner rims.
    left = eyes[0] + [.023,0,.011]
    right = eyes[1] + [-.023,0,.011]
    t = np.linspace(0,1,25)
    bridge = left[None,:]*(1-t[:,None]) + right[None,:]*t[:,None]
    bridge[:,2] += .004*np.sin(np.pi*t)
    bridge_section = np.array([[0,0,-.002],[0,.004,-.002],[0,.004,.002],[0,0,.002]])
    sweep(bridge[:,None,:] + bridge_section)

    # Broad hinges taper into slimmer arms with curved, downward ear tips.
    for center, side in zip(eyes, (-1,1)):
        path = _curve([[side*.028,.002,.015],[side*.032,-.014,.014],
                       [side*.034,-.085,.011],[side*.034,-.112,.007],
                       [side*.032,-.137,-.015],[side*.030,-.147,-.020]])
        sections = []
        for i, point in enumerate(path):
            fraction = i/(len(path)-1)
            half_width = .0018-.0005*fraction
            half_height = .004-.002*fraction
            cross = np.array([[-half_width,0,-half_height],[half_width,0,-half_height],
                              [half_width,0,half_height],[-half_width,0,half_height]])
            sections.append(center+point+cross)
        sweep(sections)
    return np.asarray(points), np.asarray(faces)


_TEMPLATE, GLASSES_FACES = _geometry(np.array([[-.032,0,0],[.032,0,0]]))
GLASSES_POINT_COUNT = len(_TEMPLATE)


def glasses_points(eyes, rotation, eye_relief_mm):
    """Rear lens planes remain 12 mm + relief ahead of each eye along head-forward.

    Styling is illustrative; there is no lens surface, refraction, or gaze rotation.
    """
    origin = np.asarray(eyes).mean(axis=0)
    local_eyes = (np.asarray(eyes)-origin) @ rotation
    local_eyes[:,1] += (EYEBALL_RADIUS_MM + eye_relief_mm) / 1000.
    points, _ = _geometry(local_eyes)
    return points @ rotation.T + origin
