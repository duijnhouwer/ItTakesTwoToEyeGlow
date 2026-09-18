"""NumPy optical geometry, meters. Right-handed X right, Y forward, Z up.

Rotations map head-local column vectors into world coordinates. Eyes are ordered
anatomical left, right. Positive azimuth is right; positive elevation is up.
The lens-aligned near/far rectangles stay parallel: the UI line shears the volume.
Their centers are separated by maximum_distance_m * unit UI line. Expansion per
side is distance along that line * tan(FOV/2). This is a geometric leakage model,
not a calibrated off-axis optical projection or refraction simulation.
"""
from dataclasses import dataclass
import numpy as np
from eyeglow_egobody.model.parameters import OpticalParameters

BOUNDARY_TOLERANCE_M = 1e-9


def ui_line_direction(azimuth_deg, elevation_deg):
    azimuth, elevation = np.radians([azimuth_deg, elevation_deg])
    return np.array([np.sin(azimuth)*np.cos(elevation),
                     np.cos(azimuth)*np.cos(elevation), np.sin(elevation)])


def valid_transform(transform):
    transform = np.asarray(transform)
    if transform.shape != (4, 4) or not np.isfinite(transform).all():
        return False
    rotation = transform[:3, :3]
    return (np.allclose(transform[3], [0, 0, 0, 1], atol=1e-6, rtol=0)
            and np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5, rtol=0)
            and np.isclose(np.linalg.det(rotation), 1, atol=1e-5, rtol=0))


def waveguide_centers(eyes, rotation, parameters):
    """Centers relative to each rear lens center; common right/up, not mirrored."""
    offset = np.array([parameters.expander_offset_right_mm,
                       parameters.eyeball_radius_mm + parameters.eye_relief_mm,
                       parameters.expander_offset_up_mm]) / 1000
    return np.asarray(eyes) + (np.asarray(rotation) @ offset)[..., None, :]


@dataclass(frozen=True)
class Frustum:
    corners: np.ndarray  # near then far, each: bottom-left, bottom-right, top-right, top-left
    planes: np.ndarray  # six outward unit normals + offset; inside <= tolerance
    center: np.ndarray
    direction: np.ndarray

    def signed_distances(self, points):
        return np.asarray(points) @ self.planes[:, :3].T + self.planes[:, 3]

    def contains(self, points, tolerance=BOUNDARY_TOLERANCE_M):
        if not np.isfinite(tolerance) or tolerance < 0:
            raise ValueError('tolerance must be finite and nonnegative')
        points = np.asarray(points)
        return np.isfinite(points).all(axis=-1) & (self.signed_distances(points) <= tolerance).all(axis=-1)


def build_frustum(center, rotation, parameters: OpticalParameters):
    center, rotation = np.asarray(center, dtype=float), np.asarray(rotation, dtype=float)
    transform = np.eye(4)
    if center.shape != (3,) or rotation.shape != (3, 3) or not np.isfinite(center).all():
        raise ValueError('Invalid frustum pose')
    transform[:3, :3] = rotation
    if not valid_transform(transform):
        raise ValueError('Frustum rotation must be proper and orthonormal')
    direction = ui_line_direction(parameters.ui_line_azimuth_deg, parameters.ui_line_elevation_deg)
    width, height = parameters.expander_width_mm / 2000, parameters.expander_height_mm / 2000
    horizontal, vertical = np.radians(parameters.fov_degrees)
    distance = parameters.maximum_distance_m
    signs = np.array([[-1, 0, -1], [1, 0, -1], [1, 0, 1], [-1, 0, 1]])
    near = signs * [width, 0, height]
    far = direction * distance + signs * [width + distance*np.tan(horizontal/2), 0,
                                           height + distance*np.tan(vertical/2)]
    corners = np.vstack((near, far)) @ rotation.T + center
    interior = corners.mean(axis=0)
    planes = []
    for a, b, c in ((0,1,2), (4,5,6), (0,1,5), (1,2,6), (2,3,7), (3,0,4)):
        normal = np.cross(corners[b]-corners[a], corners[c]-corners[a])
        normal /= np.linalg.norm(normal)
        if normal @ (interior-corners[a]) > 0:
            normal = -normal
        planes.append(np.r_[normal, -normal @ corners[a]])
    return Frustum(corners, np.asarray(planes), center, rotation @ direction)
