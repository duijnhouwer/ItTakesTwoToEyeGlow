"""Read-only fit loading, normalization and versioned derived-array cache."""
from concurrent.futures import CancelledError
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import os
import pickle
import tempfile
import zipfile
import numpy as np
from eyeglow_egobody.model.recording import Recording
from .skeleton import BodyModel, BONES, model_path
from eyeglow_egobody.runtime_paths import project_root

PROJECT_ROOT = project_root()
SCHEMA = 'smplx-body22-expression-head15-scene-yup-to-zup-v3'
SCENE_TO_DISPLAY = np.array([[1.,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]])


class ArrayUnpickler(pickle.Unpickler):
    """Accept only NumPy array storage used by EgoBody parameter dictionaries."""
    def find_class(self, module, name):
        if (module, name) in {('numpy', 'ndarray'), ('numpy', 'dtype'), ('_codecs', 'encode'),
                             ('numpy.core.multiarray', '_reconstruct'),
                             ('numpy._core.multiarray', '_reconstruct'),
                             ('numpy.core.numeric', '_frombuffer'),
                             ('numpy._core.numeric', '_frombuffer')}:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f'Unsupported pickle class: {module}.{name}')


def read_fit(path):
    with path.open('rb') as stream:
        result = ArrayUnpickler(stream, encoding='latin1').load()
    if not isinstance(result, dict):
        raise ValueError('Expected a parameter dictionary')
    return result


def calibration(info):
    member = f'calibrations/{info.name}/cal_trans/kinect12_to_world/{info.scene}.json'
    path = info.root / member
    if path.is_file():
        raw = path.read_bytes()
    else:
        with zipfile.ZipFile(info.root / 'calibrations.zip') as archive:
            raw = archive.read(member)
    matrix = np.asarray(json.loads(raw)['trans'], dtype=float)
    if (matrix.shape != (4,4) or not np.isfinite(matrix).all()
            or not np.allclose(matrix[3], [0,0,0,1])
            or not np.allclose(matrix[:3,:3].T @ matrix[:3,:3], np.eye(3), atol=.01)
            or not np.isclose(np.linalg.det(matrix[:3,:3]), 1, atol=.01)):
        raise ValueError('Invalid master Kinect to scene transform')
    return matrix


def cache_directory(dataset):
    base = PROJECT_ROOT / '.runtime'
    path = base / 'cache' / 'egobody'
    resolved = path.resolve()
    if not resolved.is_relative_to(PROJECT_ROOT.resolve()) or not resolved.is_relative_to(base.absolute()):
        raise ValueError('Cache must remain under code-repo/.runtime')
    if resolved.is_relative_to(Path(dataset).resolve()):
        raise ValueError('Cache cannot be inside the dataset')
    return resolved


def source_key(info, files, models, transform):
    identities = []
    for path in sorted([p for group in files for p in group.values()] + list(models)):
        stat = path.stat()
        identities.append((str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    spec = dict(schema=SCHEMA, root=str(info.root), name=info.name, split=info.split,
                scene=info.scene, start=info.start, end=info.end, indices=info.body_indices,
                genders=info.genders, transform=transform.tolist(), sources=identities,
                fps=30., timing='uniform Kinect frame IDs')
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()


def validate_arrays(recording, info):
    n = info.end-info.start+1
    if (recording.joints.shape != (2,n,22,3) or recording.heads.shape != (2,n,4,4)
            or recording.valid.shape != (2,n) or recording.valid.dtype != np.bool_
            or not np.array_equal(recording.frame_ids, np.arange(info.start,info.end+1))
            or not np.array_equal(recording.timestamps, np.arange(n)/30.)):
        raise ValueError('Invalid cached recording schema')
    if not recording.valid.all(axis=0).any():
        raise ValueError('No usable participant frames')
    if not np.isfinite(recording.joints[recording.valid]).all() or not np.isfinite(recording.heads[recording.valid]).all():
        raise ValueError('Nonfinite valid poses')


def load_recording(info, model_dir, cancelled=None):
    def check():
        if cancelled is not None and cancelled.is_set():
            raise CancelledError()
    check()
    files = info.frames()
    models = tuple(model_path(model_dir, gender) for gender in info.genders)
    scene_transform = calibration(info)
    transform = SCENE_TO_DISPLAY @ scene_transform
    key = source_key(info, files, models, transform)
    cache = cache_directory(info.root) / f'{key}.npz'
    try:
        with np.load(cache, allow_pickle=False) as data:
            metadata = json.loads(str(data['metadata']))
            if metadata['source_key'] != key or metadata['schema'] != SCHEMA:
                raise ValueError('Cache identity mismatch')
            recording = Recording(data['timestamps'], data['joints'], data['heads'], 30., info.name,
                                  data['valid'], data['frame_ids'], BONES, metadata)
        validate_arrays(recording, info)
        check()
        return replace(recording, metadata={**metadata, 'cache_status': 'hit'})
    except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
        pass
    n = info.end-info.start+1
    joints = np.full((2,n,22,3), np.nan, dtype=np.float32)
    heads = np.full((2,n,4,4), np.nan, dtype=np.float32)
    valid = np.zeros((2,n), dtype=bool)
    errors = []
    loaded_models = {}
    for p in range(2):
        check()
        if models[p] not in loaded_models:
            loaded_models[models[p]] = BodyModel(models[p])
        model = loaded_models[models[p]]
        for frame, path in sorted(files[p].items()):
            check()
            try:
                params = read_fit(path)
                if params.get('gender', info.genders[p]) != info.genders[p]:
                    raise ValueError('Fit gender disagrees with recording metadata')
                points, head = model.pose(params)
                i = frame-info.start
                joints[p,i] = points @ transform[:3,:3].T + transform[:3,3]
                heads[p,i] = transform @ head
                valid[p,i] = True
            except (OSError, ValueError, KeyError, TypeError, EOFError, pickle.UnpicklingError) as exc:
                if len(errors) < 20:
                    errors.append(f'{path.relative_to(info.root)}: {exc}')
    paired = valid.all(axis=0)
    if not paired.any():
        raise ValueError(f'No usable paired frames. Examples: {errors[:3]}')
    points = joints[valid].reshape(-1,3)
    separation = np.linalg.norm(joints[0,paired,0]-joints[1,paired,0], axis=1)
    metadata = dict(schema=SCHEMA, source_key=key, source_root=str(info.root), split=info.split,
                    scene=info.scene, roles=['camera wearer','interactee'], body_indices=info.body_indices,
                    genders=info.genders, model_files=[str(p.resolve()) for p in models], paired_frames=int(paired.sum()), total_frames=n,
                    invalid_frames=(~valid).sum(axis=1).tolist(), errors=errors,
                    units='meters', coordinate_system='scene Y up converted to display Z up: (x,y,z) -> (x,-z,y)',
                    kinect_to_scene=scene_transform.tolist(), scene_to_display=SCENE_TO_DISPLAY.tolist(),
                    kinect_to_display=transform.tolist(),
                    floor_proxy_z_m=float(np.nanpercentile(joints[:,:,[7,8,10,11],2],2)), cache_status='rebuilt',
                    xyz_min=points.min(axis=0).tolist(), xyz_max=points.max(axis=0).tolist(),
                    pelvis_separation_m=[float(separation.min()),float(separation.max())],
                    derivations=['22 SMPL-X kinematic body joint centers; no surface vertices',
                                 'Scene calibration applied once to both participants',
                                 '30 Hz timestamps inferred from synchronized Kinect frame IDs; no measured timestamps',
                                 'Head orientation from fitted body chain to joint 15, not eye tracking',
                                 'Optics centered at head joint with fixed 10 cm forward offset; uncalibrated',
                                 'Ground plane: 2nd percentile ankle/foot joint height, not measured floor; no motion recentering'])
    recording = Recording(np.arange(n)/30., np.ascontiguousarray(joints), np.ascontiguousarray(heads),
                          30., info.name, valid, np.arange(info.start,info.end+1), BONES, metadata)
    validate_arrays(recording, info)
    check()
    temporary = None
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=cache.parent, suffix='.npz', delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, timestamps=recording.timestamps, joints=joints, heads=heads,
                                valid=valid, frame_ids=recording.frame_ids, metadata=json.dumps(metadata))
        check()
        os.replace(temporary, cache)
    except OSError as exc:
        metadata['cache_status'] = f'uncached: {exc}'
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return recording
