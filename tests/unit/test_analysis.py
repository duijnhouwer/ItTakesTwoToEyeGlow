from dataclasses import replace
import subprocess
import sys
import numpy as np
import pytest
from eyeglow_egobody.model.parameters import OpticalParameters, DisplayMode
from eyeglow_egobody.analysis.geometry import build_frustum, ui_line_direction, waveguide_centers
from eyeglow_egobody.analysis.visibility import analyze_visibility, reduce_state, VisibilityState as S
from eyeglow_egobody.analysis.scores import summarize, detect_events


def pair(count=1, separation=1.):
    heads = np.tile(np.eye(4), (2,count,1,1))
    heads[1,:,:3,:3] = np.diag([-1,-1,1])
    heads[1,:,1,3] = separation
    eyes = np.einsum('pfij,ej->pfei', heads[...,:3,:3], [[-.032,0,0],[.032,0,0]]) + heads[...,:3,3][:,:,None,:]
    return heads, eyes


def test_analysis_imports_are_headless():
    subprocess.run([sys.executable,'-c',
        'from eyeglow_egobody.analysis import geometry,visibility,scores; '
        'from eyeglow_egobody.model import parameters,panel_settings; import sys; '
        'assert not any(k.startswith(("PySide6","pyvista","vtk")) for k in sys.modules)'],check=True)


@pytest.mark.parametrize('change', [dict(expander_width_mm=0),dict(expander_height_mm=-1),
    dict(diagonal_fov_deg=180),dict(diagonal_fov_deg=0),dict(horizontal_vertical_fov_ratio=0),
    dict(ui_line_azimuth_deg=89),dict(ui_line_elevation_deg=-89),dict(eye_relief_mm=-1),
    dict(maximum_distance_m=0),dict(head_facing_threshold_deg=181),dict(expander_offset_up_mm=np.nan),
    dict(display_mode='nope')])
def test_invalid_parameters(change):
    with pytest.raises(ValueError):
        OpticalParameters(**change)


@pytest.mark.parametrize('ratio',[.01,.5,1,2,100])
@pytest.mark.parametrize('diagonal',[.1,20,179])
def test_fov_angular_ratio_and_diagonal(ratio, diagonal):
    p = OpticalParameters(diagonal_fov_deg=diagonal,horizontal_vertical_fov_ratio=ratio)
    h,v = p.fov_degrees
    assert h/v == pytest.approx(ratio)
    assert np.hypot(np.tan(np.radians(h)/2),np.tan(np.radians(v)/2)) == pytest.approx(np.tan(np.radians(diagonal)/2))


def test_ui_line_signs_and_unit_length():
    np.testing.assert_allclose(ui_line_direction(0,0),[0,1,0])
    assert ui_line_direction(20,0)[0] > 0
    assert ui_line_direction(0,20)[2] > 0
    assert np.linalg.norm(ui_line_direction(-40,30)) == pytest.approx(1)


def test_waveguide_placement_and_eye_order():
    eyes = np.array([[-.032,0,0],[.032,0,0]])
    p = OpticalParameters(expander_offset_right_mm=3,expander_offset_up_mm=-4)
    np.testing.assert_allclose(waveguide_centers(eyes,np.eye(3),p), eyes + [.003,.025,-.004])


@pytest.mark.parametrize('azimuth,elevation',[(0,0),(25,-15),(-45,30)])
def test_frustum_corners_planes_boundaries_and_outside(azimuth,elevation):
    p = OpticalParameters(ui_line_azimuth_deg=azimuth,ui_line_elevation_deg=elevation)
    frustum = build_frustum([0,0,0],np.eye(3),p)
    assert frustum.contains(frustum.corners).all()
    np.testing.assert_allclose(frustum.corners[:4].mean(axis=0),[0,0,0],atol=1e-12)
    np.testing.assert_allclose(frustum.corners[4:].mean(axis=0),frustum.direction*5)
    np.testing.assert_allclose(np.linalg.norm(frustum.planes[:,:3],axis=1),1)
    for indices, plane in zip(((0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)),frustum.planes):
        midpoint = frustum.corners[list(indices)].mean(axis=0)
        assert frustum.contains(midpoint)
        assert not frustum.contains(midpoint + plane[:3]*1e-6)
    assert not frustum.contains([np.nan,0,0])


def test_containment_matches_independent_sheared_rectangle_formula():
    p = OpticalParameters(ui_line_azimuth_deg=25,ui_line_elevation_deg=-15)
    f = build_frustum([0,0,0],np.eye(3),p)
    points = np.random.default_rng(9).uniform([-3,-1,-3],[3,6,3],(3000,3))
    t = points[:,1]/f.direction[1]
    offset = points - t[:,None]*f.direction
    h,v = np.radians(p.fov_degrees)
    expected = (t>=0)&(t<=5)&(np.abs(offset[:,0])<=.01+t*np.tan(h/2))&(np.abs(offset[:,2])<=.01+t*np.tan(v/2))
    np.testing.assert_array_equal(f.contains(points),expected)


def test_bidirectional_visible_none_and_invalid():
    heads, eyes = pair(4)
    eyes[:,1,:,0] += np.array([0,10])[:,None]
    heads[1,2,:3,:3] = np.eye(3)  # same facing: B fails facing; B emits away
    eyes[0,3,0,0] = np.nan
    result = analyze_visibility(heads,eyes)
    np.testing.assert_array_equal(result.states,[[3,0,0,-1],[3,0,0,-1]])
    assert not result.diagnostics[1].facing_pass[2]
    assert np.isnan(result.diagnostics[0].plane_distances_m[3]).all()


@pytest.mark.parametrize('mode,expected',[(DisplayMode.BINOCULAR,[3,3]),
    (DisplayMode.MONOCULAR_LEFT,[2,2]),(DisplayMode.MONOCULAR_RIGHT,[1,1])])
def test_activation_and_receiving_eye_state(mode,expected):
    heads,eyes = pair(separation=.2)
    p = OpticalParameters(diagonal_fov_deg=1,display_mode=mode)
    np.testing.assert_array_equal(analyze_visibility(heads,eyes,parameters=p).states[:,0],expected)


def test_reduce_state_all_states():
    np.testing.assert_array_equal(reduce_state([[0,0],[1,0],[0,1],[1,1],[1,1]],
                                               [True,True,True,True,False]),[0,1,2,3,-1])


def test_distance_exact_boundary_and_just_beyond():
    heads,eyes = pair(separation=1.025)
    p = OpticalParameters(maximum_distance_m=1,diagonal_fov_deg=1)
    result = analyze_visibility(heads,eyes,parameters=p)
    np.testing.assert_array_equal(result.states,[[3],[3]])
    eyes[1,:,:,1] += 1e-6
    result = analyze_visibility(heads,eyes,parameters=p)
    np.testing.assert_array_equal(result.states,[[0],[0]])
    assert not result.diagnostics[0].distance_pass.any()


def test_facing_exact_boundary_and_just_beyond():
    heads,eyes = pair()
    p = OpticalParameters(head_facing_threshold_deg=0)
    assert (analyze_visibility(heads,eyes,parameters=p).states == 3).all()
    heads[0,0,:3,:3] = np.array([[0,-1,0],[1,0,0],[0,0,1]])
    p = replace(p,head_facing_threshold_deg=90)
    d = analyze_visibility(heads,eyes,parameters=p).diagnostics[0]
    assert d.facing_angle_deg[0] == pytest.approx(90)
    assert d.facing_pass[0]
    assert not analyze_visibility(heads,eyes,parameters=replace(p,head_facing_threshold_deg=89.999)).diagnostics[0].facing_pass[0]


@pytest.mark.parametrize('kind',['flag','nan','reflection','scale','homogeneous'])
def test_invalid_frames(kind):
    heads,eyes = pair()
    valid = np.ones((2,1),dtype=bool)
    if kind == 'flag': valid[1,0] = False
    if kind == 'nan': heads[0,0,0,0] = np.nan
    if kind == 'reflection': heads[0,0,0,0] = -1
    if kind == 'scale': heads[0,0,0,0] = 2
    if kind == 'homogeneous': heads[0,0,3,0] = 1
    assert (analyze_visibility(heads,eyes,valid).states == S.INVALID).all()


def test_rigid_transform_and_participant_swap_invariance():
    heads,eyes = pair(3)
    eyes[0,1,:,2] += .2
    p = OpticalParameters(ui_line_azimuth_deg=10,ui_line_elevation_deg=4)
    original = analyze_visibility(heads,eyes,parameters=p)
    from eyeglow_egobody.egobody.skeleton import rotations
    rotation = rotations(np.array([.3,-.7,1.2]))
    transform = np.eye(4)
    transform[:3,:3], transform[:3,3] = rotation,[4,-3,2]
    moved = analyze_visibility(transform@heads,eyes@rotation.T+transform[:3,3],parameters=p)
    np.testing.assert_array_equal(moved.states,original.states)
    for a,b in zip(moved.diagnostics,original.diagnostics):
        np.testing.assert_allclose(a.plane_distances_m,b.plane_distances_m,atol=1e-12)
        np.testing.assert_allclose(a.distances_m,b.distances_m,atol=1e-12)
    swapped = analyze_visibility(heads[::-1],eyes[::-1],parameters=p)
    np.testing.assert_array_equal(swapped.states,original.states[::-1])


def test_irregular_duration_scores_and_event_breaks():
    states = [[3,1,-1,0,2],[0,3,-1,2,2]]
    times = [0,1,3,4,7]
    scores = summarize(states,times,end_time=8)
    a,b = scores['a_sees_b'],scores['b_sees_a']
    assert a['valid_duration_s'] == 7
    assert a['percentage'] == pytest.approx(400/7)
    assert a['one_eye_percentage'] == pytest.approx(300/7)
    assert a['two_eyes_percentage'] == pytest.approx(100/7)
    assert b['percentage'] == pytest.approx(600/7)
    assert a['event_count'] == 2 and a['longest_event_s'] == 3
    assert b['event_count'] == 2 and b['longest_event_s'] == 4
    assert scores['either_direction']['percentage'] == 100
    assert scores['either_direction']['event_count'] == 2
    assert scores['mutual']['percentage'] == pytest.approx(300/7)


def test_uniform_scores_explicit_terminal_interval_and_empty_denominator():
    scores = summarize([[1,0,3],[0,2,3]],[0,1,2],end_time=3)
    assert scores['a_sees_b']['percentage'] == pytest.approx(200/3)
    assert scores['mutual']['percentage'] == pytest.approx(100/3)
    assert summarize([[3],[3]],[0])['mutual']['percentage'] is None
    assert summarize([[-1,-1],[-1,-1]],[0,1],2)['mutual']['percentage'] is None
    assert summarize([[0,3],[0,3]],[0,1])['mutual']['event_count'] == 0
    assert detect_events([True,False,True],[0,1,2],3)[1].duration_s == 1


@pytest.mark.parametrize('times,end', [([0,0],None),([1,0],None),([0,np.nan],None),([0,1],.9)])
def test_invalid_timing(times,end):
    with pytest.raises(ValueError): summarize([[0,0],[0,0]],times,end)
