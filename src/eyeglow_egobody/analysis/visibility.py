"""Vectorized potential visibility; direction 0 is A sees B, 1 is B sees A."""
from dataclasses import dataclass
from enum import IntEnum
import numpy as np
from eyeglow_egobody.model.parameters import OpticalParameters, ReceiverFovShape
from .geometry import build_frustum, waveguide_centers, BOUNDARY_TOLERANCE_M


class VisibilityState(IntEnum):
    INVALID = -1
    NONE = 0
    LEFT_EYE = 1
    RIGHT_EYE = 2
    BOTH_EYES = 3


@dataclass(frozen=True)
class DirectionDiagnostics:
    valid: np.ndarray  # frames
    plane_distances_m: np.ndarray  # frames, emitting waveguide, receiving eye, plane
    contained: np.ndarray  # frames, emitting waveguide, receiving eye
    distances_m: np.ndarray
    distance_pass: np.ndarray
    receiver_azimuth_deg: np.ndarray  # frames, emitting waveguide, receiving eye
    receiver_elevation_deg: np.ndarray
    receiver_fov_pass: np.ndarray
    active_waveguides: np.ndarray  # left, right
    visible_eyes: np.ndarray  # frames, receiving eye


@dataclass(frozen=True)
class VisibilityResult:
    states: np.ndarray  # (2, frames), receiver A then receiver B
    diagnostics: tuple[DirectionDiagnostics, DirectionDiagnostics]


def reduce_state(visible_eyes, valid):
    eyes = np.asarray(visible_eyes, dtype=bool)
    return np.where(valid, eyes[..., 0].astype(np.int8) + 2*eyes[..., 1],
                    VisibilityState.INVALID).astype(np.int8)


def receiver_fov_contains(local_vectors, parameters):
    """Test patch-center bearings in receiver-local coordinates.

    Local +X is right, +Y is face-forward, and +Z is up. Elliptical limits use
    the configured horizontal and vertical extent for the bearing's quadrant.
    """
    vectors = np.asarray(local_vectors, dtype=float)
    azimuth = np.degrees(np.arctan2(vectors[..., 0], vectors[..., 1]))
    elevation = np.degrees(np.arctan2(vectors[..., 2],
                                      np.hypot(vectors[..., 0], vectors[..., 1])))
    horizontal_limit = np.where(azimuth < 0, parameters.receiver_fov_left_deg,
                                parameters.receiver_fov_right_deg)
    vertical_limit = np.where(elevation < 0, parameters.receiver_fov_bottom_deg,
                              parameters.receiver_fov_top_deg)
    if parameters.receiver_fov_shape == ReceiverFovShape.ELLIPTICAL:
        inside = ((azimuth / horizontal_limit) ** 2
                  + (elevation / vertical_limit) ** 2 <= 1 + 1e-12)
    else:
        inside = ((np.abs(azimuth) <= horizontal_limit + 1e-9)
                  & (np.abs(elevation) <= vertical_limit + 1e-9))
    inside &= np.linalg.norm(vectors, axis=-1) > BOUNDARY_TOLERANCE_M
    return azimuth, elevation, inside


def analyze_visibility(heads, eyes, valid=None, parameters=None):
    """heads (2,F,4,4), eye centers (2,F,2,3), valid (2,F).

    Reject nonfinite eyes and nonrigid head transforms even when marked valid.
    Maximum distance is Euclidean from each emitting window center to each
    receiving eye (inclusive). Receiver FOV tests each emitting patch center from
    each receiving eye in receiver-head coordinates. Coincident eye/patch center
    has no direction and fails the FOV test.
    """
    parameters = parameters or OpticalParameters()
    heads, eyes = np.asarray(heads, dtype=float), np.asarray(eyes, dtype=float)
    if heads.ndim != 4 or heads.shape[0] != 2 or heads.shape[2:] != (4,4):
        raise ValueError('heads must have shape (2, frames, 4, 4)')
    count = heads.shape[1]
    if eyes.shape != (2, count, 2, 3):
        raise ValueError('eyes must have shape (2, frames, 2, 3)')
    valid = np.ones((2,count), dtype=bool) if valid is None else np.asarray(valid, dtype=bool)
    if valid.shape != (2, count):
        raise ValueError('valid must have shape (2, frames)')
    finite = np.isfinite(heads).all(axis=(-2,-1)) & np.isfinite(eyes).all(axis=(-2,-1))
    # Replace unusable poses before matrix arithmetic; validity retains the rejection.
    safe_heads = np.where(finite[...,None,None], heads, np.eye(4))
    safe_eyes = np.where(finite[...,None,None], eyes, 0)
    rotations = safe_heads[..., :3, :3]
    orthogonal = np.max(np.abs(np.swapaxes(rotations,-1,-2) @ rotations-np.eye(3)), axis=(-2,-1)) <= 1e-5
    rigid = orthogonal & (np.abs(np.linalg.det(rotations)-1) <= 1e-5)
    rigid &= np.max(np.abs(safe_heads[...,3,:]-[0,0,0,1]),axis=-1) <= 1e-6
    pair_valid = (valid & finite & rigid).all(axis=0)
    centers = waveguide_centers(safe_eyes, rotations, parameters)
    template = build_frustum(np.zeros(3), np.eye(3), parameters)
    active = np.asarray(parameters.active_eyes)
    diagnostics, states = [], []
    for receiver, emitter in ((0,1), (1,0)):
        delta = safe_eyes[receiver,:,None,:,:] - centers[emitter,:,:,None,:]
        local = np.einsum('fwei,fij->fwej', delta, rotations[emitter])
        planes = template.signed_distances(local)
        contained = (planes <= BOUNDARY_TOLERANCE_M).all(axis=-1)
        distances = np.linalg.norm(delta, axis=-1)
        distance_pass = distances <= parameters.maximum_distance_m + BOUNDARY_TOLERANCE_M
        toward = centers[emitter,:,:,None,:] - safe_eyes[receiver,:,None,:,:]
        receiver_local = np.einsum('fwei,fij->fwej', toward, rotations[receiver])
        azimuth, elevation, receiver_fov_pass = receiver_fov_contains(receiver_local, parameters)
        pair_visible = contained & distance_pass & receiver_fov_pass & active[None,:,None]
        visible = pair_visible.any(axis=1) & pair_valid[:,None]
        states.append(reduce_state(visible, pair_valid))
        # Invalid diagnostics are explicitly unavailable, never plausible replacement values.
        planes[~pair_valid] = np.nan
        distances[~pair_valid] = np.nan
        azimuth[~pair_valid] = np.nan
        elevation[~pair_valid] = np.nan
        contained &= pair_valid[:,None,None]
        distance_pass &= pair_valid[:,None,None]
        receiver_fov_pass &= pair_valid[:,None,None]
        diagnostics.append(DirectionDiagnostics(pair_valid.copy(), planes, contained, distances,
                                               distance_pass, azimuth, elevation, receiver_fov_pass,
                                               active.copy(), visible))
    return VisibilityResult(np.asarray(states), tuple(diagnostics))


def analyze_recording(recording, parameters=None):
    if recording.eyes is None:
        raise ValueError('Analysis requires explicit eye-center positions')
    return analyze_visibility(recording.heads, recording.eyes, recording.valid, parameters)
