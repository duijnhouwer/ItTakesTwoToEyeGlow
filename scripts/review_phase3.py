"""Print deterministic Phase 3 review scenarios; no Qt, renderer, or dataset IO.

Run from code-repo: .venv/bin/python scripts/review_phase3.py
"""
import numpy as np
from eyeglow_egobody.model.parameters import OpticalParameters, DisplayMode
from eyeglow_egobody.analysis.visibility import analyze_visibility, VisibilityState
from eyeglow_egobody.analysis.scores import summarize


def scenario(distance=1., mode=DisplayMode.BINOCULAR, invalid=False, facing=True):
    heads = np.tile(np.eye(4), (2,1,1,1))
    heads[1,0,:3,:3] = np.diag([-1,-1,1])
    heads[1,0,1,3] = distance
    eyes = np.einsum('pfij,ej->pfei', heads[...,:3,:3], [[-.032,0,0],[.032,0,0]]) + heads[...,:3,3][:,:,None,:]
    if not facing:
        heads[1,0,:3,:3] = np.eye(3)
    valid = np.array([[not invalid],[True]])
    return heads, eyes, valid, OpticalParameters(diagonal_fov_deg=1, display_mode=mode)


if __name__ == '__main__':
    print('Synthetic eye centers: 64 mm apart; A faces +Y; B faces -Y.')
    print('States name the RECEIVING eye; directions are A sees B / B sees A.\n')
    cases = [('Facing each other', scenario(), ('BOTH_EYES','BOTH_EYES')),
             ('Left emitters only', scenario(.2,DisplayMode.MONOCULAR_LEFT), ('RIGHT_EYE','RIGHT_EYE')),
             ('Right emitters only', scenario(.2,DisplayMode.MONOCULAR_RIGHT), ('LEFT_EYE','LEFT_EYE')),
             ('Beyond 5 m', scenario(6), ('NONE','NONE')),
             ('B facing away', scenario(facing=False), ('NONE','NONE')),
             ('A invalid', scenario(invalid=True), ('INVALID','INVALID'))]
    for name, (heads,eyes,valid,parameters), expected in cases:
        result = analyze_visibility(heads,eyes,valid,parameters)
        actual = tuple(VisibilityState(int(s)).name for s in result.states[:,0])
        assert actual == expected, (name, actual, expected)
        print(f'{name:24s} {actual[0]:12s} / {actual[1]:12s}  PASS')
    p = OpticalParameters()
    print(f'\nDefault diagonal 20 deg, ratio 1:1 -> H {p.horizontal_fov:.6f}, V {p.vertical_fov:.6f} deg')
    scores = summarize([[3,1,-1,0,2],[0,3,-1,2,2]],[0,1,3,4,7],end_time=8)
    print('\nIrregular timing: boundaries 0,1,3,4,7,8 seconds; interval 3–4 invalid.')
    for name, report in scores.items():
        print(f"{name:24s} {report['percentage']:8.4f}%  valid {report['valid_duration_s']:g}s  "
              f"events {report['event_count']}  longest {report['longest_event_s']:g}s")
