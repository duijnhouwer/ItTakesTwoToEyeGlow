"""NumPy skeletal forward kinematics; no surface mesh or rendering dependency.

Body joints are regressed from the shape-dependent rest template, then posed
along the model's tree. Skinning and pose corrective surface offsets do not
change these kinematic joint centers. Licensed model assets are user supplied.
"""
from pathlib import Path
import numpy as np

# 22 SMPL-X body joints, including root. Head = 15.
PARENTS = np.array([-1,0,0,0,1,2,3,4,5,6,7,8,9,9,9,12,13,14,16,17,18,19])
BONES = np.array([(int(parent), child) for child, parent in enumerate(PARENTS) if parent >= 0])
# Convert our right/forward/up optics basis to SMPL-X's rest x/y/z basis.
# Local right is -model X; forward +model Z; up +model Y (proper rotation).
OPTICS_BASIS = np.array([[-1.,0,0],[0,0,1],[0,1,0]])


def rotations(vectors):
    vectors = np.asarray(vectors, dtype=np.float64)
    angle = np.linalg.norm(vectors, axis=-1)
    x, y, z = np.moveaxis(vectors, -1, 0)
    skew = np.zeros(vectors.shape[:-1] + (3,3))
    skew[...,0,1], skew[...,0,2] = -z, y
    skew[...,1,0], skew[...,1,2] = z, -x
    skew[...,2,0], skew[...,2,1] = -y, x
    # sinc avoids division by zero and remains accurate at tiny angles.
    a = np.sinc(angle / np.pi)[...,None,None]
    b = (.5 * np.sinc(angle / (2*np.pi))**2)[...,None,None]
    return np.eye(3) + a*skew + b*(skew @ skew)


def model_path(folder, gender):
    if gender not in ('male', 'female', 'neutral'):
        raise ValueError(f'Unsupported model gender: {gender}')
    path = (Path(folder[gender]) if isinstance(folder, dict)
            else Path(folder) / f'SMPLX_{gender.upper()}.npz')
    if not path.is_file():
        raise FileNotFoundError(f'Required model missing: {path}. Select the licensed SMPL-X template files in Select input data ...')
    return path


class BodyModel:
    def __init__(self, path):
        with np.load(path, allow_pickle=False) as data:
            template = data['v_template']
            regressor = data['J_regressor'][list(range(22)) + [23,24]]
            if not np.array_equal(data['kintree_table'][0,23:25], [15,15]):
                raise ValueError('Unsupported SMPL-X eye joint hierarchy')
            dirs = data['shapedirs']
            shapes = dirs[...,:10]
            tree = data['kintree_table'][0,:22].astype(np.int64)
            tree[0] = -1
            if not np.array_equal(tree, PARENTS):
                raise ValueError('Unsupported SMPL-X body joint hierarchy')
            self.rest = regressor @ template
            self.shapes = np.einsum('jv,vck->jck', regressor, shapes)
            # SMPL-X expression components affect regressed joint centers too.
            expression_start = 300 if dirs.shape[-1] > 300 else 10
            self.expressions = np.einsum('jv,vck->jck', regressor, dirs[...,expression_start:expression_start+10])
        if (self.rest.shape != (24,3) or self.shapes.shape != (24,3,10)
                or self.expressions.shape != (24,3,10)
                or not all(np.isfinite(a).all() for a in (self.rest,self.shapes,self.expressions))):
            raise ValueError('Invalid SMPL-X model dimensions')

    def pose(self, params, *, include_eyes=False):
        def field(name, count):
            value = np.asarray(params[name], dtype=float)
            if value.size != count or not np.isfinite(value).all():
                raise ValueError(f'Invalid {name}: expected {count} finite values')
            return value.reshape(-1)
        betas = field('betas',10)
        expression = field('expression',10)
        local = rotations(np.concatenate((field('global_orient',3),field('body_pose',63))).reshape(22,3))
        rest = self.rest + self.shapes @ betas
        rest = rest + self.expressions @ expression
        position, world = np.empty((22,3)), np.empty((22,3,3))
        position[0], world[0] = rest[0], local[0]
        for j in range(1,22):
            parent = PARENTS[j]
            world[j] = world[parent] @ local[j]
            position[j] = position[parent] + world[parent] @ (rest[j]-rest[parent])
        position += field('transl',3)
        head = np.eye(4)
        head[:3,:3], head[:3,3] = world[15] @ OPTICS_BASIS, position[15]
        if include_eyes:
            # Eye rotations change orientation, not the centers of these leaf joints.
            eyes = position[15] + (rest[22:24] - rest[15]) @ world[15].T
            return position, head, eyes
        return position, head
