"""Deterministic synthetic fixture. Meters, Z up, local +Y forward, +X right."""
from dataclasses import dataclass
import numpy as np

BONES = np.array([(0,1),(1,2),(2,3),(2,4),(4,5),(5,6),(2,7),(7,8),(8,9),
                  (0,10),(10,11),(11,12),(0,13),(13,14),(14,15)])

@dataclass(frozen=True)
class Recording:
    timestamps: np.ndarray
    joints: np.ndarray
    heads: np.ndarray
    fps: float = 30.0
    name: str = "synthetic_motion"

    @property
    def frame_count(self):
        return len(self.timestamps)


def synthetic_recording():
    """Ten-second loop; all poses and head transforms are invented, not measured."""
    times = np.arange(300) / 30.0
    base = np.array([[0,0,.95],[0,0,1.2],[0,0,1.45],[0,0,1.7],
                     [-.22,0,1.44],[-.35,0,1.17],[-.4,0,.95],
                     [.22,0,1.44],[.35,0,1.17],[.4,0,.95],
                     [-.13,0,.9],[-.14,0,.48],[-.14,.08,.06],
                     [.13,0,.9],[.14,0,.48],[.14,.08,.06]], dtype=float)
    joints = np.empty((2,len(times),16,3))
    heads = np.tile(np.eye(4), (2,len(times),1,1))
    for p in range(2):
        for f,t in enumerate(times):
            phase = 2*np.pi*t/10
            yaw = (np.pi/2 if p == 0 else -np.pi/2) + .3*np.sin(phase)
            c,s = np.cos(yaw),np.sin(yaw)
            rot = np.array([[c,-s,0],[s,c,0],[0,0,1]])
            pose = base.copy()
            pose[[5,6,8,9],1] += .16*np.sin(phase*2 + p)
            position = np.array([(1 if p == 0 else -1)*(1+.25*np.cos(phase)),
                                 .2*np.sin(phase+p),0])
            joints[p,f] = pose @ rot.T + position
            heads[p,f,:3,:3] = rot
            heads[p,f,:3,3] = joints[p,f,3]
    return Recording(times, np.ascontiguousarray(joints), heads)
