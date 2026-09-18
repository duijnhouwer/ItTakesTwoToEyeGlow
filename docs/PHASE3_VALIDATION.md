# Phase 3 — Geometry and visibility validation

Implemented 2026-09-18. Developer tests passed; joint mathematical review and
approval to proceed to Phase 4 are **pending**. The dataset was not used or
modified by this implementation or its synthetic review.

## Settings and scope

`config/settings_panel.json` now contains a `settings.waveguide` group. File →
Settings exposes the group through simple edit fields, including:

| Parameter | Factory default | Meaning |
|---|---:|---|
| Eyebox expander width / height | 20 / 20 mm | Full rectangular window dimensions |
| Center offset right / up | 0 / 0 mm | Relative to each rear lens center, along wearer-local axes |
| Diagonal FOV | 20° | Full diagonal field angle |
| Horizontal / vertical FOV ratio | 1 | Angular H/V ratio; enter 2 for 2:1, 0.5 for 1:2 |
| UI-line azimuth / elevation | 0 / 0° | Positive toward wearer-right / up |
| Maximum analysis distance | 5 m | Finite volume length plus per-pair distance limit |
| Display mode | `binocular` | Also `monocular_left`, `monocular_right` |

The receiver head-facing threshold is separate from the Waveguide group and
defaults to 90°. Eyeball radius and eye relief retain their existing controls.
The user's pre-existing eye-relief value of 12 mm is preserved; its factory
default remains 13 mm. Factory Reset stages changes; Save validates and persists
all values atomically. Cancel does not persist. JSON metadata still controls
labels, precision, and edit ranges; the model also enforces physical constraints.
Earlier flat settings documents remain readable and receive model defaults for
unspecified new values. The committed settings file exposes all new controls.

`PanelSettings.optical_parameters` produces the immutable shared model, also
held by the controller. The Phase 3 controls persist parameters and now immediately update rendered
windows, frustums, and UI lines. Current-frame receiving-eye diagnostics use the
same parameter instance and engine output. Whole-recording UI scores remain
Phase 5; the graphical waveguide editor remains Phase 10.

## Geometry conventions to review

- World positions and geometry use meters. Settings dimensions use millimeters;
  public angles use degrees. Local axes are right-handed: X wearer-right,
  Y head-forward, Z up. Rotation matrices map local vectors into world space.
- Eye order is anatomical left, right. Waveguides use that same order.
- Rear lens centers lie `(eyeball radius + eye relief)` ahead of each fitted eye
  center along head-forward. Expander offsets apply along local right/up on
  both lenses, with the same signs; they are not mirrored. Depth is fixed to
  the lens plane, not a third editable expander offset.
- The UI line (formerly chief ray) is the unit vector
  `(sin(azimuth) cos(elevation), cos(azimuth) cos(elevation), sin(elevation))`.
  Azimuth/elevation must remain strictly inside ±89° to avoid degenerate or
  reversed volumes. The panel offers ±88°.
- The full FOV angles satisfy `h / v = ratio` and
  `tan(d/2)^2 = tan(h/2)^2 + tan(v/2)^2`. A bounded numerical solve preserves the
  specified **angular ratio**, rather than treating it as a screen aspect ratio.
  The default produces **14.214152° horizontal and vertical**.
- The near rectangle stays aligned with the lens. The far rectangle is parallel
  to it, with center `window_center + unit_UI_line * maximum_distance`.
  Its half-extents grow by `maximum_distance * tan(h/2)` and
  `maximum_distance * tan(v/2)`. Thus changing the UI line shears the volume;
  it does not rotate the physical window. This is an explicit rectangular
  leakage approximation. At oblique UI-line angles, the FOV expansion slopes
  do not describe an exact ray-centered angular projection. No refraction or
  optical calibration is inferred. Review this convention before Phase 4.
- Containment uses six outward unit plane normals. All boundaries are inclusive
  within **1 nanometer** of numerical tolerance. Plane distances are meters,
  positive outside, and returned for diagnostic inspection.
- Euclidean distance from each emitting window center to each receiver eye must
  also be within maximum distance, inclusively. This can reject far corners
  inside the rectangular volume. The finite volume and radial cutoff are both
  intentional, distinct diagnostic tests.
- Receiver head-facing compares receiver head +Y with the vector from receiver
  head origin to the emitter's rear-lens midpoint. The angle threshold is
  inclusive within 1e-9 degrees. A coincident origin/target fails facing because
  there is no defined direction. This is potential visibility, never gaze.

## States and diagnostics

`analysis.visibility.analyze_visibility` accepts head transforms `(2,F,4,4)`,
eye centers `(2,F,2,3)`, and optional validity flags `(2,F)`.
`analyze_recording` adapts the existing normalized recording model and requires
explicit eye centers. Computation is vectorized across frames.

Result row 0 means **A sees B**; row 1 means **B sees A**. States identify the
**receiving** left/right eye, not the emitting display:
`INVALID=-1`, `NONE=0`, `LEFT_EYE=1`, `RIGHT_EYE=2`, `BOTH_EYES=3`.
Each receiver eye can be illuminated by either active emitting waveguide.
Containment, radial distance, facing, and data validity must all pass.

Both directions are invalid when either participant has invalid data, nonfinite
eyes/transforms, an improper rotation, or a nonhomogeneous transform. Numeric
diagnostics for invalid frames are NaN and diagnostic pass flags are false.
For valid frames, diagnostics preserve all four emitter/receiver eye pair tests,
per-plane distances, per-pair distances, facing angles, activation, and final
receiver-eye results.

## Time and summary conventions

A sample's state holds on `[timestamp[i], timestamp[i+1])`. Timestamps must be
finite and strictly increasing. The last sample has no duration unless an
explicit `end_time` is passed. For known uniform cadence, a caller can pass
`timestamps[-1] + 1/fps`; irregular timing must provide an evidenced end time
or leave the last point at zero duration.

Invalid intervals are excluded from denominators and split events. No visible
event crosses a none/invalid interval. A change between one and two visible eyes
continues the same potential-visibility event. An empty valid denominator
produces `None` for percentages. Pair summaries require both directions valid.
Summaries contain both directional percentages, one-/two-eye percentages for
each direction, either-direction and mutual percentages, durations, event counts,
longest durations, and timestamped event records.

## Reproducible printed review

Run from `code-repo`:

```sh
.venv/bin/python scripts/review_phase3.py
.venv/bin/python -m pytest -q
```

Developer result: **148 tests passed**, including the existing regression suite.
New coverage includes FOV extremes, signed plane boundaries, independent analytic
containment checks, display activation, each visibility state, exact distance and
facing boundaries, invalid poses, rigid-transform and participant-swap invariance,
uniform/irregular time, events, headless imports, grouped settings persistence,
validation, controller updates, and staged reset/cancel behavior. The settings
dialog was rendered offscreen and visually inspected; evidence is in the ignored
`.runtime/phase3/settings.png`. This is not owner hands-on sign-off.

Synthetic participants have eye centers 64 mm apart. A faces +Y and B faces -Y.
The printed cases use 1° diagonal FOV so the emitting sides remain distinguishable:

| Case | A sees B | B sees A |
|---|---|---|
| Facing each other, 1 m apart | BOTH_EYES | BOTH_EYES |
| Left emitters only, 0.2 m apart | RIGHT_EYE | RIGHT_EYE |
| Right emitters only, 0.2 m apart | LEFT_EYE | LEFT_EYE |
| Separation 6 m, limit 5 m | NONE | NONE |
| B faces away | NONE | NONE |
| A flagged invalid | INVALID | INVALID |

For interval boundaries `0, 1, 3, 4, 7, 8` seconds:

| Interval | Duration | A sees B | B sees A |
|---|---:|---|---|
| 0–1 | 1 s | BOTH_EYES | NONE |
| 1–3 | 2 s | LEFT_EYE | BOTH_EYES |
| 3–4 | 1 s | INVALID | INVALID |
| 4–7 | 3 s | NONE | RIGHT_EYE |
| 7–8 | 1 s | RIGHT_EYE | RIGHT_EYE |

Seven seconds are valid. Expected and observed results:

| Summary | Percentage | Event count | Longest event |
|---|---:|---:|---:|
| A sees B | 4/7 = 57.1429% | 2 | 3 s |
| B sees A | 6/7 = 85.7143% | 2 | 4 s |
| Either direction | 7/7 = 100% | 2 | 4 s |
| Mutual | 3/7 = 42.8571% | 2 | 2 s |

A's one-eye/two-eye percentages are 3/7 and 1/7. B's are 4/7 and 2/7.
The invalid interval separates events even when surrounding intervals are visible.

## Packaged startup correction

The first Phase 3 handoff omitted rebuilding the existing executable. Its older
settings reader rejected the new nested `waveguide` group with
`ValueError: Invalid setting definition: waveguide`, preventing packaged startup.
The source tests did not cover that stale binary. Rebuilt the one-folder package
with the current source using the documented clean PyInstaller command.

The rebuilt executable passed the real-desktop smoke test on Linux x86_64,
Python 3.12.14, NVIDIA RTX 3080 Ti: startup, playback, stable actors, FHD/4K captures,
and a 60-frame FHD MP4 export all passed. Report:
`.runtime/phase3-package-smoke/smoke-result.json`; build log:
`.runtime/phase3-build.log`. No settings values were changed by this correction.
README now explicitly requires rebuilding and testing the packaged executable
when source/settings-format changes are delivered.

## Visual validation implementation (authorized scope move)

The plan-only change is commit `fbe9a12`. Phase 3 now includes visual review:

- Persistent left/right window, frustum, and UI-line actors per person use
  `build_frustum` and `waveguide_centers` directly. No placeholder geometry remains.
- The controller evaluates one frame through `analyze_visibility`, shares the
  same immutable parameter instance with the renderer, and exposes that result
  in the caption, eye-test panel, and colored receiver-eye rings.
- Green means pass, red means fail, gray means invalid. Eye labels identify the
  receiving participant and anatomical left/right eye. Per-window containment
  and distance tests, facing angle/threshold, and validity are inspectable.
- File → Settings / Waveguide settings immediately updates current-frame optics
  after Save. Display mode activates the matching emitting windows only.
- Frustums, UI lines, local axes, and eye tests have visibility toggles. Frustum
  opacity replaces placeholder spread. Presentation controls never affect scores.
- Inspect A/B gives a close view and stops orbit. Fit optics frames active volumes.
  Synthetic review opens the deterministic fixture and diagnostic panel; real
  loaded recordings support the same inspection controls.

Developer checks: 155 tests pass (including the pre-existing NumPy compatibility
addition), with checks for exact rendered/numeric corner agreement, per-eye
activation, offsets, actor reuse, invalid-frame hiding, diagnostic colors/text,
and presentation independence. Native smoke checks additionally mutate optical
parameters and all three display modes on live actors, then restore user values.
No settings file is altered by these smoke checks. Screenshot evidence and smoke
reports are written under `.runtime/phase3-visual-source/` and
`.runtime/phase3-visual-package/`, including `optics-inspection.png`.

Joint visual sign-off remains pending. Phase 4 retains final glasses styling and
unscored camera containment; whole-recording analysis, percentages, and timeline
remain Phase 5 and later.

Both native source and rebuilt-package visual smoke tests passed on Linux with
40 persistent actors, FHD/4K screenshots, and a 60-frame MP4 export. The packaged
playback heartbeat p95 was 0.062 seconds. Real-recording review also loaded
`recording_20210907_S02_S01_01` (1,290 frames) and rendered four active frustums.
At frame 1, both directions correctly reported NONE: facing and distance passed,
but all receiver-eye/window containment tests failed. The visible red eye rings
and numeric panel agreed. Real-data screenshots and the diagnostic report are
in `.runtime/phase3-visual-real/`. Source and packaged inspection screenshots
were visually inspected. Owner review remains outstanding.
