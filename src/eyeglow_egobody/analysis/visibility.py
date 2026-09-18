"""Vectorized potential visibility; direction 0 is A sees B, 1 is B sees A."""
from dataclasses import dataclass
from enum import IntEnum
import numpy as np
from eyeglow_egobody.model.parameters import OpticalParameters
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
    facing_angle_deg: np.ndarray  # frames
    facing_pass: np.ndarray
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


def analyze_visibility(heads, eyes, valid=None, parameters=None):
    """heads (2,F,4,4), eye centers (2,F,2,3), valid (2,F).

    Reject nonfinite eyes and nonrigid head transforms even when marked valid.
    Maximum distance is Euclidean from each emitting window center to each
    receiving eye (inclusive). Facing compares receiver head +Y to emitter lens
    midpoint from receiver head origin. Coincident head/target has no direction.
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
    lens_offset = np.array([0, (parameters.eyeball_radius_mm+parameters.eye_relief_mm)/1000, 0])
    centers = waveguide_centers(safe_eyes, rotations, parameters)
    lens_midpoints = safe_eyes.mean(axis=2) + np.einsum('pfij,j->pfi', rotations, lens_offset)
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
        toward = lens_midpoints[emitter] - safe_heads[receiver,:,:3,3]
        length = np.linalg.norm(toward, axis=-1)
        cosine = np.divide(np.sum(toward * rotations[receiver,:,:,1],axis=-1), length,
                           out=np.zeros(count), where=length > 0)
        angle = np.degrees(np.arccos(np.clip(cosine,-1,1)))
        facing = (length > BOUNDARY_TOLERANCE_M) & (angle <= parameters.head_facing_threshold_deg + 1e-9)
        visible = (contained & distance_pass & active[None,:,None]).any(axis=1)
        visible &= (pair_valid & facing)[:,None]
        states.append(reduce_state(visible, pair_valid))
        # Invalid diagnostics are explicitly unavailable, never plausible replacement values.
        planes[~pair_valid] = np.nan
        distances[~pair_valid] = np.nan
        angle[~pair_valid] = np.nan
        contained &= pair_valid[:,None,None]
        distance_pass &= pair_valid[:,None,None]
        facing &= pair_valid
        diagnostics.append(DirectionDiagnostics(pair_valid.copy(), planes, contained, distances,
                                               distance_pass, angle, facing, active.copy(), visible))
    return VisibilityResult(np.asarray(states), tuple(diagnostics))


def analyze_recording(recording, parameters=None):
    if recording.eyes is None:
        raise ValueError('Analysis requires explicit eye-center positions')
    return analyze_visibility(recording.heads, recording.eyes, recording.valid, parameters)
