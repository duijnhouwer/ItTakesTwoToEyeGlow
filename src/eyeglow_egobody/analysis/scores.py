"""Duration-weighted summaries. Each sample holds over [timestamp, next timestamp).

The last sample has zero duration unless end_time is explicitly supplied. There
is no invented final interval for irregular data. Invalid intervals break events
and are excluded from denominators. Undefined percentages are None, not zero.
"""
from dataclasses import dataclass
import numpy as np
from .visibility import VisibilityState


@dataclass(frozen=True)
class VisibilityEvent:
    start_time: float
    end_time: float
    duration_s: float


def interval_edges(timestamps, end_time=None):
    times = np.asarray(timestamps, dtype=float)
    if times.ndim != 1 or not len(times) or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError('timestamps must be nonempty, finite, and strictly increasing')
    end = times[-1] if end_time is None else float(end_time)
    if not np.isfinite(end) or end < times[-1]:
        raise ValueError('end_time must be finite and at or after the last timestamp')
    return np.r_[times, end]


def detect_events(mask, timestamps, end_time=None):
    edges = interval_edges(timestamps, end_time)
    mask = np.asarray(mask, dtype=bool)
    if mask.shape != (len(edges)-1,):
        raise ValueError('event mask must match timestamps')
    mask = mask & (np.diff(edges) > 0)
    transitions = np.diff(np.r_[False, mask, False].astype(np.int8))
    starts, stops = np.flatnonzero(transitions == 1), np.flatnonzero(transitions == -1)
    return tuple(VisibilityEvent(float(edges[a]), float(edges[b]), float(edges[b]-edges[a]))
                 for a,b in zip(starts, stops))


def summarize(states, timestamps, end_time=None):
    edges = interval_edges(timestamps, end_time)
    states = np.asarray(states)
    if states.shape != (2,len(edges)-1) or not np.isin(states, list(VisibilityState)).all():
        raise ValueError('states must be (2, frames) containing defined visibility states')
    weights = np.diff(edges)
    valid = states != VisibilityState.INVALID
    visible = states > VisibilityState.NONE

    def report(mask, usable):
        duration = float(weights[usable].sum())
        visible_duration = float(weights[mask & usable].sum())
        events = detect_events(mask & usable, timestamps, end_time)
        return dict(valid_duration_s=duration, visible_duration_s=visible_duration,
                    percentage=100*visible_duration/duration if duration else None,
                    event_count=len(events), longest_event_s=max((e.duration_s for e in events), default=0.),
                    events=events)

    result = {}
    for index, name in enumerate(('a_sees_b', 'b_sees_a')):
        result[name] = report(visible[index], valid[index])
        for label, mask in (('one_eye', np.isin(states[index], [1,2])),
                            ('two_eyes', states[index] == VisibilityState.BOTH_EYES)):
            result[name][label+'_percentage'] = report(mask, valid[index])['percentage']
    pair_valid = valid.all(axis=0)
    result['either_direction'] = report(visible.any(axis=0), pair_valid)
    result['mutual'] = report(visible.all(axis=0), pair_valid)
    return result
