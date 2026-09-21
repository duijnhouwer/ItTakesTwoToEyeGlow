import json
from concurrent.futures import CancelledError
from threading import Event
from types import SimpleNamespace
import numpy as np
import pytest
from eyeglow_egobody.analysis.activities import ActivityCatalog, UNDEFINED, normalize
from eyeglow_egobody.analysis import batch
from eyeglow_egobody.model.panel_settings import PanelSettings


@pytest.fixture
def activity_data(tmp_path):
    path = tmp_path/'annotations.csv'
    path.write_text('recording_name,body_idx_0,frame_interval_start,frame_interval_end,body_0_des\n'
                    'r,1 female,10,14,talk_clip1\n'
                    'r,0 male,12,16,listen_clip1\n'
                    'r,1 female,13,15,dance_clip2\n')
    catalog = ActivityCatalog(path)
    info = SimpleNamespace(name='r', start=10, end=17, body_indices=(1, 0), root=tmp_path/'dataset')
    return catalog, info


def test_normalization():
    assert normalize('pantry_sit casual_chat_clip123') == 'pantry_sit_casual_chat'


@pytest.mark.parametrize('mode', ['binocular', 'monocular_left', 'monocular_right'])
def test_at_least_one_active_emitter_counts_as_visible(mode):
    from eyeglow_egobody.analysis.activities import Segment
    from eyeglow_egobody.analysis.visibility import analyze_visibility
    from eyeglow_egobody.model.parameters import OpticalParameters
    heads = np.tile(np.eye(4), (2,2,1,1))
    heads[1,:,:3,:3] = np.diag([-1,-1,1])
    heads[1,:,1,3] = .2
    eyes = np.einsum('pfij,ej->pfei', heads[...,:3,:3], [[-.032,0,0],[.032,0,0]]) + heads[...,:3,3][:,:,None,:]
    result = analyze_visibility(heads, eyes, parameters=OpticalParameters(diagonal_fov_deg=1, display_mode=mode))
    recording = SimpleNamespace(timestamps=np.array([0., 1/30]), frame_ids=np.array([0,1]))
    info = SimpleNamespace(name='test', body_indices=(0,1))
    row = batch.segment_result(info, Segment(0,1,((),())), recording, result)
    assert row['a_sees_b_eyeglow']['percentage'] == row['b_sees_a_eyeglow']['percentage'] == 100


def test_boundaries_roles_conflicts_and_undefined(activity_data):
    catalog, info = activity_data
    segments = list(catalog.segments(info, (catalog.labels, catalog.labels)))
    assert [(s.start, s.end) for s in segments] == [(10,12),(12,13),(13,14),(14,15),(15,16),(16,17)]
    assert segments[0].labels(0) == ('talk',)
    assert segments[0].labels(1) == (UNDEFINED,)
    assert segments[2].labels(0) == ('dance', 'talk')
    assert segments[-1].labels(0) == segments[-1].labels(1) == (UNDEFINED,)
    assert [(s.start,s.end) for s in catalog.segments(info, (['talk'], ['listen']))] == [(12,13),(13,14)]
    assert not list(catalog.segments(info, (['listen'], ['talk'])))


def test_jsonl_snapshot_binary_durations_and_atomic_cancel(activity_data, tmp_path, monkeypatch):
    catalog, info = activity_data
    recording = SimpleNamespace(timestamps=np.arange(8)/30, frame_ids=np.arange(10,18))
    states = np.array([[0,1,2,3,-1,0,1,3], [3,2,1,0,-1,0,0,3]])
    monkeypatch.setattr(batch, 'load_recording', lambda *a, **kw: recording)
    monkeypatch.setattr(batch, 'analyze_recording', lambda *a: SimpleNamespace(states=states))
    settings = PanelSettings().document
    path = tmp_path/'result.jsonl'
    progress = []
    batch.run_batch([info], catalog, (catalog.labels, catalog.labels), settings, tmp_path, path,
                    Event(), lambda a,b: progress.append((a,b)))
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[0]['settings_current'] == settings
    assert len(rows) == 7
    assert progress == [(0,1),(1,1)]
    assert sum(r['selected_duration_s'] for r in rows[1:]) == pytest.approx(7/30)
    assert rows[3]['a']['label_conflict']
    assert rows[3]['a_sees_b_eyeglow']['percentage'] == 100
    assert rows[4]['a_sees_b_eyeglow']['percentage'] is None
    assert rows[4]['a_sees_b_eyeglow']['excluded_invalid_duration_s'] == pytest.approx(1/30)
    assert rows[2]['a_sees_b_eyeglow']['percentage'] == 100  # state 2
    assert 'settings_current' not in rows[1]
    original = path.read_bytes()
    cancelled = Event()
    def cancel(*args):
        cancelled.set()
    with pytest.raises(CancelledError):
        batch.run_batch([info], catalog, (catalog.labels, catalog.labels), settings, tmp_path,
                        path, cancelled, cancel, overwrite=True)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('.activity-*'))


def test_no_match_and_failure_do_not_publish(activity_data, tmp_path, monkeypatch):
    catalog, info = activity_data
    path = tmp_path/'result.jsonl'
    with pytest.raises(ValueError, match='No time'):
        batch.run_batch([info], catalog, (['absent'], ['talk']), PanelSettings().document,
                        tmp_path, path, Event())
    def fail(*args, **kwargs):
        raise RuntimeError('broken fit')
    monkeypatch.setattr(batch, 'load_recording', fail)
    with pytest.raises(RuntimeError, match='broken fit'):
        batch.run_batch([info], catalog, (catalog.labels, catalog.labels), PanelSettings().document,
                        tmp_path, path, Event())
    assert not path.exists()
    assert not list(tmp_path.glob('.activity-*'))
