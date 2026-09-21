from concurrent.futures import Future
from dataclasses import replace
from types import SimpleNamespace
from threading import Event
import json
import numpy as np
import pytest
from eyeglow_egobody.analysis.activities import ActivityCatalog
from eyeglow_egobody.model.playlist import ActivitiesPlaylist
from eyeglow_egobody.model.recording import synthetic_recording
from eyeglow_egobody.model.panel_settings import PanelSettings
from eyeglow_egobody.controller import Controller
from eyeglow_egobody.analysis import batch
from eyeglow_egobody.ui.playlist_analysis import PlaylistAnalysis


@pytest.fixture
def playlist_data(tmp_path):
    path = tmp_path/'annotations.csv'
    path.write_text('recording_name,body_idx_0,frame_interval_start,frame_interval_end,body_0_des\n'
                    'r1,0 male,10,13,talk_clip1\n'
                    'r1,1 male,10,18,listen_clip1\n'
                    'r1,0 male,16,18,talk_clip2\n'
                    'r2,0 male,10,14,talk_clip3\n'
                    'r2,1 male,11,14,listen_clip2\n')
    catalog = ActivityCatalog(path)
    infos = [SimpleNamespace(name=n, start=10, end=20, body_indices=(0,1), root=tmp_path/'dataset')
             for n in ('r1','r2')]
    recordings = {i.name: replace(synthetic_recording(), name=i.name, frame_ids=np.arange(10,310)) for i in infos}
    playlist = ActivitiesPlaylist(infos, catalog, (['talk'], ['listen']))
    return infos, catalog, recordings, playlist


def test_combined_index_has_no_gaps_or_duplicate_frames(playlist_data):
    _, _, _, playlist = playlist_data
    assert len(playlist.clips) == 3
    assert playlist.frame_count == 8
    assert playlist.duration_s == pytest.approx(8/30)
    actual = [(playlist.locate(f)[0].info.name, playlist.locate(f)[1]) for f in range(8)]
    assert actual == [('r1',10),('r1',11),('r1',12),('r1',16),('r1',17),('r2',11),('r2',12),('r2',13)]


def test_lazy_playback_scrub_cross_recording_resume_and_empty(qt_app, tmp_path, playlist_data, monkeypatch):
    _, catalog, recordings, playlist = playlist_data
    frames = []
    viewport = SimpleNamespace(set_recording=lambda r: None, set_frame=lambda f,*_: frames.append(f))
    c = Controller(recordings['r1'], viewport, tmp_path)
    c.timer.stop()
    pending = []
    def submit(function, info, *args, **kwargs):
        future = Future()
        pending.append((future, info))
        return future
    monkeypatch.setattr(c.load_pool, 'submit', submit)
    try:
        c.set_playlist(playlist, tmp_path)
        assert c.state.frame_count == 8 and frames[-1] == 0
        c.seek(3)
        assert frames[-1] == 6  # source frame 16, gap skipped
        c.toggle()
        c._advance_playback(2/30)
        assert c.loading and c.playlist_resume and not c.state.playing
        pending[-1][0].set_result(recordings['r2'])
        c._poll_load()
        assert c.state.playing and c.state.frame == 5 and frames[-1] == 1
        c.state.playing = False
        c.seek(0)
        # A later seek supersedes a pending source load.
        c.seek(6)
        assert c.loading is None and frames[-1] == 2
        c.state.loop = False
        c.state.playing = True
        c._advance_playback(1)
        assert not c.state.playing and c.state.frame == 7
        empty = ActivitiesPlaylist([], catalog, ([], []))
        c.set_playlist(empty, tmp_path)
        c.toggle()
        assert not c.state.playing and c.playlist.frame_count == 0
    finally:
        c.close()


def test_chunked_analysis_matches_export_and_preview_timeline(tmp_path, playlist_data, monkeypatch):
    infos, catalog, recordings, playlist = playlist_data
    monkeypatch.setattr(batch, 'load_recording', lambda info, *args, **kw: recordings[info.name])
    paths = [tmp_path/'plain.jsonl', tmp_path/'preview.jsonl']
    previews = []
    for path, preview in zip(paths, (None, lambda r,f: previews.append((r.name,f)))):
        batch.run_batch(infos, catalog, playlist.selections, PanelSettings().document, tmp_path,
                        path, Event(), preview=preview)
    rows = [[json.loads(line) for line in p.read_text().splitlines()][1:] for p in paths]
    assert rows[0] == rows[1]
    assert previews == [('r1',2),('r1',4),('r2',7)]
    assert sum(r['selected_duration_s'] for r in rows[1]) == pytest.approx(playlist.duration_s)


def test_preview_mailbox_is_bounded_and_completion_unlocks(qt_app, tmp_path, playlist_data, monkeypatch):
    infos, catalog, recordings, playlist = playlist_data
    viewport = SimpleNamespace(set_recording=lambda r: None, set_frame=lambda *a: None)
    c = Controller(recordings['r1'], viewport, tmp_path)
    c.timer.stop()
    runner = PlaylistAnalysis(c)
    future = Future()
    monkeypatch.setattr(runner.pool, 'submit', lambda *args: future)
    try:
        runner.start(infos, catalog, playlist, PanelSettings().document, tmp_path, tmp_path/'out.jsonl')
        assert c.analysis_active
        for f in range(5):
            runner._preview(recordings['r1'], f)
        assert runner.latest[1] == 4
        runner.poll()
        assert c.state.frame == 4 and runner.latest is None
        runner.cancel()
        assert runner.cancelled.is_set()
        from concurrent.futures import CancelledError
        future.set_exception(CancelledError())
        runner.poll()
        assert not c.analysis_active and 'cancelled' in runner.message
    finally:
        runner.shutdown()
        c.close()
