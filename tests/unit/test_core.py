import subprocess
import sys
import numpy as np
import pytest
from eyeglow_egobody.model.recording import synthetic_recording
from eyeglow_egobody.model.state import PlaybackState
from eyeglow_egobody.export.paths import safe_directory, new_export


def test_imports_do_not_load_gui():
    subprocess.run([sys.executable,'-c',
        "from eyeglow_egobody.model import recording,state; import sys; "
        "assert not any(k.startswith(('PySide6','pyvista','vtk')) for k in sys.modules)"],check=True)


def test_synthetic_head_transforms_match_joints():
    recording = synthetic_recording()
    assert recording.joints.shape == (2,300,16,3)
    assert recording.joints.flags.c_contiguous
    np.testing.assert_allclose(recording.heads[:,:,:3,3],recording.joints[:,:,3])
    rotations = recording.heads[:,:,:3,:3]
    np.testing.assert_allclose(np.linalg.det(rotations),1)
    assert np.isfinite(recording.joints).all()
    assert recording.joints[...,2].min() >= 0

@pytest.mark.parametrize('speed',[.25,.5,1,2])
def test_elapsed_playback(speed):
    state = PlaybackState(300,30,playing=True,speed=speed)
    state.advance(2)
    assert state.frame == int(60*speed)


def test_playback_boundaries():
    state = PlaybackState(300,30,playing=True)
    state.seek(299)
    state.advance(.1)
    assert state.frame == 2
    state.loop = False
    state.seek(299)
    state.advance(.1)
    assert state.frame == 299 and not state.playing
    state.seek(-5)
    assert state.frame == 0


def test_dataset_and_symlink_output_rejected(tmp_path):
    dataset = tmp_path/'egobody-data'
    dataset.mkdir()
    alias = tmp_path/'alias'
    alias.symlink_to(dataset,target_is_directory=True)
    for path in (dataset/'exports',alias/'exports'):
        with pytest.raises(ValueError):
            safe_directory(path)
    assert not list(dataset.iterdir())


def test_collision_safe_output(tmp_path):
    assert new_export(tmp_path,'frames') != new_export(tmp_path,'frames')
