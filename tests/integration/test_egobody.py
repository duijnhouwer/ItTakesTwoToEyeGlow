"""Synthetic files with the real release schema; no licensed assets required."""
import csv
import json
import pickle
import struct
import zipfile
import zlib
from pathlib import Path
import numpy as np
import pytest
from eyeglow_egobody.egobody.discovery import discover
from eyeglow_egobody.egobody import loading
from eyeglow_egobody.egobody.skeleton import BodyModel, PARENTS, rotations


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    root = tmp_path/'egobody-data'
    root.mkdir()
    project = tmp_path/'code-repo'
    project.mkdir()
    monkeypatch.setattr(loading, 'PROJECT_ROOT', project)
    name = 'recording_20220101_S01_S02_01'
    (root/'data_info_release.csv').write_text(
        'scene_name,body_idx_0,body_idx_1,start_frame,end_frame,body_idx_fpv,recording_name\n'
        f'test,0 male,1 female,10,13,0 male,{name}\n')
    (root/'data_splits.csv').write_text(f'train,val,test\n{name},,\n')
    models = project/'models'
    models.mkdir()
    rest = np.zeros((25,3))
    rest[:,1] = np.arange(25)*.05
    shapes = np.zeros((25,3,20))
    shapes[15,1,0] = .1
    for gender in ('MALE','FEMALE'):
        np.savez(models/f'SMPLX_{gender}.npz', v_template=rest, J_regressor=np.eye(25),
                 shapedirs=shapes, kintree_table=np.array([np.r_[PARENTS,15,15,15], np.arange(25)]))
    for role, idx, gender in [('camera_wearer',1,'female'),('interactee',0,'male')]:
        for frame in (10,11,13):
            folder = root/f'smplx_{role}_train'/name/f'body_idx_{idx}'/'results'/f'frame_{frame:05}'
            folder.mkdir(parents=True)
            params = dict(betas=np.zeros((1,10)), expression=np.zeros((1,10)),
                          body_pose=np.zeros((1,63)), global_orient=np.zeros((1,3)),
                          transl=np.array([[idx*2,0,frame*.01]]), gender=gender)
            (folder/'000.pkl').write_bytes(pickle.dumps(params, protocol=2))
    path = root/'calibrations'/name/'cal_trans'/'kinect12_to_world'/'test.json'
    path.parent.mkdir(parents=True)
    transform = np.eye(4)
    transform[:3,3] = [1,2,3]
    path.write_text(json.dumps({'trans':transform.tolist()}))
    return root, models


def snapshot(root):
    return {str(p.relative_to(root)):(p.stat().st_size,p.stat().st_mtime_ns,p.read_bytes())
            for p in root.rglob('*') if p.is_file()}


def test_pairing_normalization_cache_and_read_only(dataset):
    root, models = dataset
    before = snapshot(root)
    info, = discover(root)
    assert info.body_indices == (1,0)  # fpv is interactee, NOT wearer
    assert info.genders == ('female','male')
    assert len(set(info.frames()[0]) & set(info.frames()[1])) == 3
    cold = loading.load_recording(info, models)
    assert cold.joints.flags.c_contiguous and cold.heads.flags.c_contiguous
    assert cold.valid.tolist() == [[True,True,False,True]]*2
    assert np.isnan(cold.joints[:,2]).all()
    np.testing.assert_allclose(cold.joints[:,0,0],[[3,-3.1,2],[1,-3.1,2]])
    np.testing.assert_array_equal(cold.frame_ids,[10,11,12,13])
    np.testing.assert_allclose(cold.timestamps,[0,1/30,2/30,3/30])
    hot = loading.load_recording(info, models)
    assert hot.metadata['cache_status'] == 'hit'
    assert hot.metadata['floor_proxy_z_m'] == cold.metadata['floor_proxy_z_m'] == 2.0
    np.testing.assert_array_equal(hot.joints,cold.joints)
    cache, = loading.cache_directory(root).glob('*.npz')
    cache.write_bytes(b'broken cache')
    assert loading.load_recording(info, models).metadata['cache_status'] == 'rebuilt'
    assert snapshot(root) == before


def test_invalid_frame_and_cache_invalidation(dataset):
    root, models = dataset
    info, = discover(root)
    first = loading.load_recording(info,models)
    path = info.frames()[0][11]
    path.write_bytes(b'invalid pickle')
    second = loading.load_recording(info,models)
    assert second.metadata['source_key'] != first.metadata['source_key']
    assert second.valid[0].tolist() == [True,False,False,True]
    assert len(second.metadata['errors']) == 1
    assert second.metadata['paired_frames'] == 2
    # A derivation/schema change must bypass an existing cache.
    old = loading.SCHEMA
    try:
        loading.SCHEMA = 'next-schema'
        assert loading.load_recording(info,models).metadata['source_key'] != second.metadata['source_key']
    finally:
        loading.SCHEMA = old


def test_corrupt_compressed_cache_rebuilds(dataset):
    root, models = dataset
    before = snapshot(root)
    info, = discover(root)
    original = loading.load_recording(info, models)
    cache, = loading.cache_directory(root).glob('*.npz')
    with zipfile.ZipFile(cache) as archive:
        member = archive.getinfo('joints.npy')
        assert member.compress_type == zipfile.ZIP_DEFLATED
    raw = bytearray(cache.read_bytes())
    name_size, extra_size = struct.unpack_from('<HH', raw, member.header_offset + 26)
    offset = member.header_offset + 30 + name_size + extra_size
    # Invalid DEFLATE block type; retain the valid ZIP directory/header so
    # reading an array, rather than opening the archive, raises zlib.error.
    raw[offset] = 0x07
    cache.write_bytes(raw)
    with pytest.raises(zlib.error):
        with np.load(cache, allow_pickle=False) as data:
            data['joints']
    rebuilt = loading.load_recording(info, models)
    assert rebuilt.metadata['cache_status'] == 'rebuilt'
    np.testing.assert_array_equal(rebuilt.joints, original.joints)
    assert loading.load_recording(info, models).metadata['cache_status'] == 'hit'
    assert snapshot(root) == before


def test_missing_model_and_no_pairs_fail_honestly(dataset):
    root, models = dataset
    info, = discover(root)
    with pytest.raises(FileNotFoundError,match='SMPLX_FEMALE'):
        loading.load_recording(info,models/'absent')
    for path in info.frames()[0].values():
        path.unlink()
    with pytest.raises(ValueError,match='No usable paired frames'):
        loading.load_recording(info,models)


def test_cache_write_failure_returns_usable_arrays(dataset,monkeypatch):
    root, models = dataset
    info, = discover(root)
    monkeypatch.setattr(loading.os,'replace',lambda *args: (_ for _ in ()).throw(OSError('full')))
    recording = loading.load_recording(info,models)
    assert recording.valid.any()
    assert recording.metadata['cache_status'] == 'uncached: full'
    assert not list(loading.cache_directory(root).glob('*.npz'))


def test_cache_symlink_cannot_write_dataset(dataset):
    root, models = dataset
    (loading.PROJECT_ROOT/'.runtime').symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError,match='Cache must remain'):
        loading.load_recording(discover(root)[0], models)


def test_restricted_pickle_rejects_code(tmp_path):
    import os
    path = tmp_path/'unsafe.pkl'
    path.write_bytes(pickle.dumps(os.system))
    with pytest.raises(pickle.UnpicklingError):
        loading.read_fit(path)


def test_joint_kinematics_shape_and_root_rotation(dataset):
    _, models = dataset
    model = BodyModel(models/'SMPLX_MALE.npz')
    params = dict(betas=np.zeros(10), expression=np.zeros(10), body_pose=np.zeros(63),
                  global_orient=np.array([0,0,np.pi/2]),transl=np.array([2,3,4]))
    params['betas'][0] = 1
    joints, head = model.pose(params)
    np.testing.assert_allclose(joints[15], [2-.85,3,4], atol=1e-12)
    np.testing.assert_allclose(head[:3,3],joints[15])
    np.testing.assert_allclose(head[:3,:3].T @ head[:3,:3],np.eye(3), atol=1e-12)
    assert np.linalg.det(head[:3,:3]) == pytest.approx(1)
    np.testing.assert_allclose(rotations(np.zeros(3)), np.eye(3))
    # A non-root rotation changes descendants but leaves its own joint center fixed.
    params['global_orient'][:] = 0
    params['body_pose'][11*3:12*3] = [0,0,np.pi/2]  # neck joint 12
    posed, _ = model.pose(params)
    np.testing.assert_allclose(posed[12],model.rest[12]+params['transl'])
    assert not np.allclose(posed[15],model.rest[15]+params['transl'])


def test_cancelled_load_writes_nothing(dataset):
    from concurrent.futures import CancelledError
    from threading import Event
    root, models = dataset
    event = Event(); event.set()
    with pytest.raises(CancelledError):
        loading.load_recording(discover(root)[0],models,event)
    assert not loading.cache_directory(root).exists()


def test_calibration_zip_and_transform_invalidation(dataset):
    import zipfile
    root, models = dataset
    info, = discover(root)
    path = root/'calibrations'/info.name/'cal_trans/kinect12_to_world/test.json'
    original = loading.load_recording(info,models)
    matrix = json.loads(path.read_text())
    matrix['trans'][0][3] += 4
    with zipfile.ZipFile(root/'calibrations.zip','w') as archive:
        archive.writestr(str(path.relative_to(root)),json.dumps(matrix))
    path.unlink()
    updated = loading.load_recording(info,models)
    assert updated.metadata['source_key'] != original.metadata['source_key']
    np.testing.assert_allclose(updated.joints[...,0],original.joints[...,0]+4)


def test_controller_loads_on_worker_and_resets_playback(dataset, qt_app):
    from eyeglow_egobody.controller import Controller
    from eyeglow_egobody.model.recording import synthetic_recording
    from types import SimpleNamespace
    from threading import get_ident
    root, models = dataset
    ui_thread = get_ident()
    calls = []
    viewport = SimpleNamespace(set_recording=lambda r: calls.append((r,get_ident())),
                               set_frame=lambda *args: None)
    controller = Controller(synthetic_recording(),viewport,root.parent)
    controller.timer.stop()
    try:
        controller.state.seek(250)
        controller.state.speed = 2
        controller.load_recording(discover(root)[0],models)
        assert controller.loading is not None
        assert not controller.state.playing
        controller.loading[1].result(timeout=10)
        assert controller.recording.name == 'synthetic_motion'
        controller._poll_load()
        assert calls[0][1] == ui_thread
        assert controller.state.frame_count == 4 and controller.state.frame == 0
        assert controller.state.speed == 2
        assert (controller.export_start,controller.export_end) == (0,3)
        controller.state.playing = True
        controller._advance_playback(1/30)
        assert controller.state.frame == 2  # twice native speed, gap preserved
    finally:
        controller.close()


def test_superseded_worker_cannot_replace_recording(dataset,qt_app):
    from eyeglow_egobody.controller import Controller
    from eyeglow_egobody.model.recording import synthetic_recording
    from threading import Event
    from types import SimpleNamespace
    root, _ = dataset
    entered, release = Event(), Event()
    initial = synthetic_recording()
    controller = Controller(initial,SimpleNamespace(),root.parent)
    controller.timer.stop()
    found = []
    controller.recordings_found.connect(found.append)
    def slow():
        entered.set()
        release.wait(5)
        return ['old']
    try:
        controller._submit_load('discovery',slow)
        assert entered.wait(2)
        controller._submit_load('discovery',lambda: ['new'])
        release.set()
        controller.loading[1].result(timeout=5)
        controller._poll_load()
        assert found == [['new']]
        assert controller.recording is initial
    finally:
        release.set()
        controller.close()


def test_real_data_ui_reports_missing_assets(qt_app,monkeypatch,dataset,tmp_path):
    from PySide6.QtWidgets import QWidget
    from eyeglow_egobody.ui import main_window
    class FakeViewport(QWidget):
        def __init__(self,parent,recording):
            super().__init__(parent)
            self.interactor = self
        def reset_view(self): pass
        def fit_participants(self): pass
        def set_frame(self,*args): pass
    monkeypatch.setattr(main_window,'Viewport',FakeViewport)
    root, models = dataset
    window = main_window.MainWindow(tmp_path,dataset=root,model_dir=models/'missing')
    window.controller.timer.stop()
    try:
        window.controller.loading[1].result(timeout=5)
        window.controller._poll_load()  # discovery auto-starts first load
        try:
            window.controller.loading[1].result(timeout=5)
        except FileNotFoundError:
            pass
        window.controller._poll_load()
        assert window.models_button.isEnabled()
        assert not window.screenshot_button.isEnabled()
        assert not window.controller.recording.valid.any()
    finally:
        window.close()


def test_eye_centers_follow_head_and_survive_cache(dataset):
    root, models = dataset
    model = BodyModel(models/'SMPLX_MALE.npz')
    params = dict(betas=np.zeros(10), expression=np.zeros(10), body_pose=np.zeros(63),
                  global_orient=np.array([0,0,np.pi/2]),transl=np.array([2,3,4]))
    params['body_pose'][14*3:15*3] = [np.pi/2,0,0]  # head joint 15
    joints, head, eyes = model.pose(params, include_eyes=True)
    expected_rotation = rotations(params['global_orient']) @ rotations(np.array([np.pi/2,0,0]))
    expected = joints[15] + (model.rest[22:24]-model.rest[15]) @ expected_rotation.T
    np.testing.assert_allclose(eyes, expected, atol=1e-12)
    info, = discover(root)
    cold = loading.load_recording(info, models)
    assert cold.eyes.shape == (2,4,2,3) and cold.eyes.flags.c_contiguous
    assert np.isnan(cold.eyes[:,2]).all()
    np.testing.assert_allclose(cold.eyes[0,0], [[3,-3.1,3.15],[3,-3.1,3.2]], atol=1e-6)
    hot = loading.load_recording(info, models)
    np.testing.assert_array_equal(hot.eyes, cold.eyes)
    cache, = loading.cache_directory(root).glob('*.npz')
    with np.load(cache, allow_pickle=False) as data:
        arrays = {k:data[k] for k in data.files}
    arrays['eyes'][0,0,0] = np.nan
    np.savez_compressed(cache, **arrays)
    assert loading.load_recording(info, models).metadata['cache_status'] == 'rebuilt'


@pytest.mark.parametrize('participant,frame,joint', [(0,0,0),(1,3,21),(0,2,15),(1,1,7)])
def test_floor_uses_any_joint_participant_and_frame(participant,frame,joint):
    joints = np.ones((2,4,22,3))
    eyes = np.ones((2,4,2,3))
    valid = np.ones((2,4),dtype=bool)
    joints[participant,frame,joint,2] = -.4
    assert loading.lowest_joint_height(joints,eyes,valid) == -.4


def test_floor_includes_eyes_and_excludes_invalid_or_nonfinite_positions():
    joints = np.ones((2,4,22,3))
    eyes = np.ones((2,4,2,3))
    valid = np.ones((2,4),dtype=bool)
    valid[0,0] = False
    joints[0,0,:,2] = -100
    eyes[0,0,:,2] = -200
    joints[0,1,0] = [np.nan,0,-300]
    joints[0,1,1,2] = -np.inf
    eyes[0,2,0] = [0,np.inf,-400]
    eyes[1,3,1,2] = -.2
    # A participant's valid frame contributes even when their partner is invalid.
    valid[0,3] = False
    assert loading.lowest_joint_height(joints,eyes,valid) == -.2
    valid[:] = False
    with pytest.raises(ValueError, match='No finite valid'):
        loading.lowest_joint_height(joints,eyes,valid)
