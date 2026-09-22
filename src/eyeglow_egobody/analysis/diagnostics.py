"""Plain-text current-frame explanations derived exclusively from engine results."""
from .visibility import VisibilityState


def visibility_summary(result):
    labels = {
        VisibilityState.INVALID: 'unavailable',
        VisibilityState.NONE: 'none',
        VisibilityState.LEFT_EYE: 'left',
        VisibilityState.RIGHT_EYE: 'right',
        VisibilityState.BOTH_EYES: 'both',
    }
    if result is None:
        states = (VisibilityState.INVALID, VisibilityState.INVALID)
    else:
        states = tuple(VisibilityState(int(result.states[i, 0])) for i in range(2))
    return '\n'.join(f'{receiver} sees eyeglow: {labels[state]}'
                     for receiver, state in zip(('A', 'B'), states))


def visibility_details(result, parameters):
    if result is None:
        return 'INVALID: explicit eye-center data is required.'
    lines = ['Potential visibility at eye centers; this is not measured gaze.',
             'Green eye rings = pass; red = fail; gray = invalid.',
             'Axes: red = right, green = forward, blue = up.',
             'Containment and radial distance must pass for the SAME active window.', '']
    for index,(receiver,emitter) in enumerate((('A','B'),('B','A'))):
        d = result.diagnostics[index]
        lines.append(f'{receiver} sees {emitter}: {VisibilityState(int(result.states[index,0])).name}')
        if not d.valid[0]:
            lines.extend(['  INVALID: one or both participant frames / poses / eyes are unusable.', ''])
            continue
        for eye in range(2):
            lines.append(f'  Receiver {"LR"[eye]} eye: {"PASS" if d.visible_eyes[0,eye] else "FAIL"}')
            for window in range(2):
                if not d.active_waveguides[window]:
                    lines.append(f'    Emitter {"LR"[window]} window: inactive')
                    continue
                contained, distance = d.contained[0,window,eye], d.distance_pass[0,window,eye]
                fov = d.receiver_fov_pass[0,window,eye]
                margin = d.plane_distances_m[0,window,eye].max()*1000
                lines.append(f'    Emitter {"LR"[window]}: containment {"PASS" if contained else "FAIL"} '
                             f'(max plane distance {margin:+.3f} mm); '
                             f'distance {"PASS" if distance else "FAIL"} '
                             f'({d.distances_m[0,window,eye]:.3f} / {parameters.maximum_distance_m:g} m); '
                             f'receiver FOV {"PASS" if fov else "FAIL"} '
                             f'(az {d.receiver_azimuth_deg[0,window,eye]:+.3f} deg, '
                             f'el {d.receiver_elevation_deg[0,window,eye]:+.3f} deg; '
                             f'{parameters.receiver_fov_shape.value})')
        lines.append('')
    h,v = parameters.fov_degrees
    lines.append(f'Derived FOV: H {h:.3f} deg, V {v:.3f} deg. Boundary points are included.')
    return '\n'.join(lines)
