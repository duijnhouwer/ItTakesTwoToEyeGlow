# Phase 2: local EgoBody inspection and implementation

Updated 2026-09-18 after the owner supplied SMPL-X v1.1 assets and moved the
dataset under `assets/`. **Real paired playback now passes developer checks;
the owner explicitly signed off Phase 2 on 2026-09-18.** Earlier missing-asset
checks below document the initial implementation; see the final validation update
for the current result.

## Observed local data

Read-only root: `/home/jacob/Documents/EyeGlowEgoBody/assets/egobody-data`.

- `data_info_release.csv`: recording name, scene name, inclusive start/end frame,
  `body_idx_0`, `body_idx_1`, and `body_idx_fpv` (body index plus gender).
- `data_splits.csv`: train/val/test columns. Discovery finds **125** paired
  SMPL-X recording directories: **65 train, 17 val, 43 test**.
- `smplx_camera_wearer_{train,val,test}/<recording>/body_idx_<n>/results/frame_<id>/000.pkl`
  and matching `smplx_interactee_*` directories contain per-frame fits.
- `smpl_camera_wearer_test` is also present. It is not mixed with SMPL-X fits.
- `calibrations.zip` contains 1,002 entries, including
  `calibrations/<recording>/cal_trans/kinect12_to_world/<scene>.json` with a
  numeric `trans` matrix of shape `(4,4)`. Read directly from ZIP; never extract
  into the dataset. An already extracted calibration takes precedence.
- `annotation_egocentric_smpl_npz.zip` holds train/val/test egocentric annotations.
  The inspected training NPZ contains 90,120 samples: `3d_joints` and
  `3d_joints_pv` `(90120,45,3)`, body pose `(90120,69)`, shape `(90120,10)`,
  image names, 2D keypoints, camera intrinsics, root rotations/translations.
  This is an egocentric interactee SMPL annotation subset, not a paired SMPL-X
  skeleton source; it does not replace the missing models for both participants.
- `transf_matrices_all_seqs.pkl` contains recording-keyed Kinect-to-HoloLens and
  timestamp-keyed world-to-PV transforms. Those transforms are **not** applied
  to the already paired Kinect-space fits.
- Scene meshes, gaze, and Kinect camera parameters are available as ZIPs.
  Several large media/point-cloud ZIP downloads have no valid ZIP directory,
  and `.part` downloads also exist. None are needed for this skeleton loader.
- `Motion-X-main` contains upstream processing code/assets; no SMPL-X model
  NPZ was found there or elsewhere under the local home directory during the initial inspection.

### Representative paired recording

`recording_20210907_S02_S01_01`, train, scene `seminar_g110`:

| Property | Observed value |
|---|---|
| Inclusive source frame IDs | 1551–2840 |
| Camera wearer | body index 1, female |
| Interactee | body index 0, female |
| Files per participant | 1,290 |
| Matching frame IDs | 1,290 |
| Nominal duration | 43 s at the documented Kinect 30 Hz cadence |

Example input:
`smplx_camera_wearer_train/recording_20210907_S02_S01_01/body_idx_1/results/frame_01551/000.pkl`.
Both roles' first frames were successfully read by the restricted NumPy
unpickler (the legacy protocol also requires `_codecs.encode`).

| Fit field | Observed shape/type |
|---|---|
| `betas` | `(1,10)` float32 |
| `global_orient`, `transl` | `(1,3)` float32 |
| `body_pose` | `(1,63)` float32 |
| `left_hand_pose`, `right_hand_pose` | `(1,12)` float32 |
| `jaw_pose`, `leye_pose`, `reye_pose` | `(1,3)` float32 |
| `expression` | `(1,10)` float32 |
| `pose_embedding` | `(1,32)` float32 |
| `gender` | string |

These dictionaries contain **parameters, not joints**. Reconstruction needs
`SMPLX_FEMALE.npz` and `SMPLX_MALE.npz` from the user's licensed SMPL-X release.
For this representative recording, only the female model is needed. The
NumPy-only skeleton implementation uses `v_template`, `J_regressor`,
`shapedirs`, and `kintree_table`; it neither redistributes assets nor needs
Torch/mesh skinning. It includes ten shape and ten expression coefficients,
then propagates axis-angle rotations through the first 22 kinematic joints.
Hand, jaw, and eye rotations do not affect these upstream body joint centers.

## Pairing, timing, and coordinate evidence

The [official EgoBody documentation](https://github.com/sanweiliti/EgoBody)
identifies `body_idx_fpv` as the **interactee**, despite its name. Participant A
is always camera wearer (`1 - interactee index`), B is always interactee.
Recording folder, split, role, body index, and numeric source frame ID determine
pairing. The inclusive metadata interval defines the timeline. Missing or
malformed files produce NaN poses and false per-participant validity, with no
interpolation, holding, or timeline compression. Rendering hides invalid bodies
and explicitly labels them INVALID.

The official documentation places both roles' SMPL-X fits in the **master
Kinect RGB camera coordinates**. The
[official third-person renderer](https://github.com/sanweiliti/EgoBody/blob/main/release_renderer_kinect.py)
uses the inverse Kinect-to-scene calibration to bring the scene to the bodies.
This implementation instead applies the forward calibration once to both bodies.
Source units are meters, consistent with the SMPL-X convention. No individual
centering/scaling is applied.

The [EgoBody paper](https://arxiv.org/abs/2112.07642) describes synchronized
30 FPS Kinect capture (also verified in the local `assets/EgoBody-2112.07642v3.pdf`,
Section 3.2, page 7). The capture rate is documented, not guessed; it is the
per-frame relative timestamps that are derived. Fit files have frame IDs, not timestamps. The loader
explicitly derives relative time `(frame_id - start_frame) / 30`, including gaps.
It does not claim these are measured timestamps or use the irregular HoloLens
PV timeline.

Local calibration samples strongly indicate scene **Y up**: the master-camera
Y-down basis maps predominantly onto negative scene Y (for the first recording,
`[-0.08541, -0.99398, 0.06859]`). Nine recordings across different scenes showed
the same dominant direction. The display makes the explicit proper rotation
`(x,y,z) -> (x,-z,y)` so world Z is up. Both matrices and the composite transform
are retained in diagnostics. This convention still needs visual confirmation
with reconstructed bodies.

## Approximations and diagnostics

- Body joint centers are reconstructed from fitted parameters, not measured
  Kinect joint positions. Surface meshes and face landmarks are not generated.
- Head rotation follows the fitted chain to SMPL-X joint 15. It is not measured
  eye gaze or a separately calibrated headset pose. The optics basis maps local
  right/forward/up to model `-X/+Z/+Y`; facing direction remains a visual-review item.
- Placeholder optics now use reconstructed eye centers plus configurable radius
  and eye relief along head-forward (25 mm total by default). Frame dimensions
  remain placeholders; see the eye-placement update below.
- The ground plane is placed at the minimum display-world Z over all reconstructed
  body and eye joint centers, both people, and the full sequence. Invalid
  participant frames and nonfinite positions are excluded. This is a joint-center
  minimum, not a measured floor or body-surface minimum; a single low fitted joint
  can determine it. It is fixed during playback and does not alter motion coordinates.
- Diagnostics expose source IDs, per-person validity, current pelvis positions
  and head transforms, XYZ bounds, pelvis-separation range, role/body identity,
  transform matrices, source/model identity, errors, and every derivation above.

## Cache and UI behavior

Arrays: float32 joints `(2,F,22,3)`, float32 head transforms `(2,F,4,4)`,
float32 eye centers `(2,F,2,3)`, bool validity `(2,F)`, int source IDs `(F,)`, float64 seconds `(F,)`. Geometry arrays
are contiguous. The controller replaces recording length, native FPS, scrub
range, and export range together. VTK actors are reused across frames and loads.

Discovery and loading run on one background executor. The Qt timer consumes
completed results; workers never touch Qt/VTK. Superseded requests are cancelled
or ignored, and close requests cooperative cancellation. A failed load retains
the prior recording; startup failure leaves an empty scene and disables playback
and exports. Synthetic motion is available explicitly with `--synthetic` and in
the existing rendering smoke test.

Caches are compressed, pickle-free NPZs under `code-repo/.runtime/cache/egobody`.
Keys cover schema/derivation version, dataset and source absolute paths, size,
mtime/ctime, model identity, pairing metadata, frame interval, cadence, and the
actual composite calibration. Source addition/removal or mutation invalidates
the key. Reads validate identity, shapes, timeline, paired validity, and finite
valid geometry. Corruption triggers rebuilding. Writes publish atomically;
ordinary write failure returns usable arrays with an uncached warning. Symlink
escapes from `.runtime` and paths inside the dataset are rejected.

## Reproduce

```bash
.venv/bin/python scripts/inspect_egobody.py ../assets/egobody-data > .runtime/phase2-inspection.json
.venv/bin/python scripts/inspect_egobody.py ../assets/egobody-data --model-dir /path/to/smplx-models
.venv/bin/python -m eyeglow_egobody --model-dir /path/to/smplx-models
```

The app defaults to `../assets/egobody-data`. Override it with `--dataset`.
Use **SMPL-X model folder…**, `--model-dir`, or `EYEGLOW_MODEL_DIR`; point directly to
files such as `SMPLX_FEMALE.npz`, not to an enclosing release folder.

## Initial validation record (before model assets arrived)

- Automated suite: **61 passed**, including 12 Phase 2 tests using small,
  deterministic release-shaped fixtures and deliberately synthetic model assets.
- Tests cover role inversion, exact transforms, shape and joint kinematics,
  missing/corrupt frames, cold/hot/corrupt caches, source/schema/calibration
  invalidation, ZIP calibrations, cache write failure, read-only snapshots,
  symlink protection, restricted pickle loading, cancellation, supersession,
  UI missing-asset feedback, and controller replacement/native timing.
- Real-data bounded inspection: discovery, calibration reads, and both initial
  fit dictionaries passed. No actual model-backed reconstruction has run.
- GUI smoke test and final dataset metadata audit are recorded separately below
  after execution. Synthetic rendering is not evidence of real-body accuracy.
- Joint hands-on review and approval to proceed to Phase 3: **pending**.

### Executed desktop and dataset checks

- Native Linux desktop smoke **passed** on Python 3.12.14, NVIDIA RTX 3080 Ti:
  eight stable participant actors, native/FHD/4K capture, 60-frame FHD MP4 at
  24 FPS (2.5 seconds), playback heartbeat p95 57.7 ms. Report:
  `.runtime/phase2-synthetic-smoke/smoke-result.json`.
- Native Phase 2 startup **passed**: all 125 recordings shown, missing female
  model reported, playback/export disabled for the empty scene, and model-folder
  selection available. Screenshot: `.runtime/phase2-missing-models.png`.
- A rendering-only 22-joint fixture successfully replaced the scene while
  retaining all actor identities. Individual and simultaneous invalid poses hid
  the correct actors; subsequent valid poses restored them. This checks renderer
  integration, not the correctness of real SMPL-X reconstruction.
- Before/after read-only dataset metadata snapshots matched across **1,027,826**
  entries (paths, modes, sizes, modification times). SHA-256:
  `fedc644f9d7f549b1be031aacd2dc662a592083e31c657560b5b3c189fe3dfa2`.
  Reports: `.runtime/phase2-before.json`, `.runtime/phase2-after.json`.
  This is a metadata audit, not a full file-content hash or syscall trace.
- Final automated suite: **61 passed**. `git diff --check` passed.

Next required validation: supply the model folder, cold-load and cache-load the
representative recording, compare skeletal centers against the official model
implementation, inspect both participants and head directions together, and
review approach/contact frames with the project owner. Do not advance to Phase 3
until this real-data gate is agreed.

### Rebuilt desktop package — 2026-09-18

Rebuilt `dist/EyeGlowEgoBody/EyeGlowEgoBody` with the documented clean PyInstaller
command. Frozen path resolution now uses the executable's repository build
location rather than the bundled `_internal` module location, keeping default
dataset/model discovery and derived caches aligned with source runs. This path
layout targets the current repository build; portable installation remains
later packaging work.

All **63 tests passed**. The rebuilt executable's `--help` exposes Phase 2
options. Its native desktop smoke passed outside the virtual environment:
eight stable actors, screenshot/FHD/4K capture, 60-frame MP4, 2.5 seconds at
24 FPS. Report: `.runtime/phase2-package-smoke/smoke-result.json`.

### Assets supplied and real playback validated — 2026-09-18

The owner moved the dataset to `../assets/egobody-data` and supplied original
v1.1 female, male, and neutral models in
`../assets/models_smplx_v1_1/models/smplx`. These are now the source and packaged
application defaults. Both asset directories were read only; caches and captures
remain under `code-repo/.runtime`.

Verified model arrays: `v_template (10475,3)`, `J_regressor (55,10475)`,
`shapedirs (10475,3,400)`, `kintree_table (2,55)`.

- `recording_20210907_S02_S01_01`: 1,290/1,290 paired valid frames, both female.
  Initial load 0.881 s, cached load 0.111 s on this machine.
- `recording_20210907_S03_S04_01`: 760/760 paired valid frames, female wearer and
  male interactee. Initial load 0.827 s, cached load 0.067 s.
- Native desktop real-data test: first recording loaded in a worker, frames
  0/430/860/1289 matched normalized arrays, actor identities stayed stable,
  and two seconds of playback advanced 60 frames. Both skeletons were visible
  and upright in the inspected captures. Joint centers lack a head outline;
  optics remain placeholders. Ground is still the documented foot-height proxy.
- An independent calculation formed shape-dependent vertices, regressed joints,
  converted rotations through quaternions, and composed 4x4 transforms. Across
  six sampled male/female poses it agreed with the optimized skeleton loader
  within `3.83e-7` meters. This is not a comparison with the official Torch runtime.
- Corrected diagnostic XYZ bounds to aggregate all joint positions into a single
  three-component minimum/maximum; bumped cache schema to v3.
- Automated suite: **64 passed**. The one-folder package was rebuilt.
- Dataset metadata audit unchanged across 1,028,130 entries; digest
  `dbc19a51395db12976c19a9ea56caf30cb4ab419c4ef080022a237610d8308e1`.
- Captures and machine-readable reports:
  `.runtime/real-playback/window.png`, `frame-*.png`, `result.json`, and
  `model-verification.json`.

Missing model assets no longer block playback. Joint review of participant
identity, body proportions, contact moments, and placeholder head placement
remains pending; no Phase 3 sign-off is implied.

### Eye centers and editable placement settings — 2026-09-18

The owner requested visible eye centers and eye-relative glasses placement during
Phase 2 visual review. The loader now also reconstructs the anatomical left/right
SMPL-X eye joints (zero-based 23/24), both children of head joint 15. Their
shape/expression-dependent rest centers follow the fitted head transform and the
same scene/display transform as the body. Leaf eye rotations do not change their
joint-center positions; these are fitted anatomical centers, not measured gaze.

The normalized recording adds float32 contiguous `eyes (2,F,2,3)` in meters,
ordered left/right. Invalid participant frames have NaN eyes and hidden markers.
Cache schema v4 includes and validates eyes; older caches rebuild automatically.
The 22 body joints and their skeleton connections remain unchanged. Synthetic
fixtures use explicitly invented eye offsets.

Bright, unshaded point markers display the centers. Each placeholder rear lens
plane sits forward of its corresponding eye center by
`(eyeball_radius_mm + eye_relief_mm) / 1000` along head-forward: 25 mm by default.
The plane center represents the rear optical vertex; no lens thickness, curvature,
or final calibrated optical geometry is implemented. Temple arms follow the
frames. Lens rectangles are 50 mm wide by 60 mm high, centered on their respective
eyes; their size and temple dimensions remain placeholders.

`config/settings_panel.json` stores schema version, display names, current/default
values, min/max, and decimal precision. **File → Settings ...** generates text
fields from these definitions. Save validates and atomically persists values,
then refreshes current geometry; Cancel leaves values unchanged. The JSON metadata
is not exposed as editable settings. Values are in millimeters: radius defaults
to 12 (range 1–30), relief to 13 (range 0–100), both with one decimal place.
These ranges are application input limits, not anatomical assertions. Source and
repository-built desktop runs share this external config file.

Validation: 77 automated tests passed, including rotated lens clearance,
eye/head kinematics, cache round-trip and invalidation, input validation,
Save/Cancel/write failure, and menu-to-viewport updates. Two real recordings
(1,290 and 760 paired valid frames) passed cold/cache loading. Independent full
vertex regression on 12 sampled participant poses agreed with cached eye centers
within 1.77e-7 m. Close-up and settings-dialog captures were visually inspected;
artifacts are in `.runtime/eye-settings/`. Joint Phase 2 sign-off remains pending.

Rebuilt standalone Linux package smoke passed on the native NVIDIA desktop:
10 stable actors, playback, PNG/FHD/4K captures, and a 60-frame FHD MP4 at 24 FPS
(2.5 seconds). Report: `.runtime/eye-settings/package-smoke/smoke-result.json`.

### Spherical eyes, Phong surfaces, and ground shadows — 2026-09-18

At the owner's request, eye markers are now actual sphere geometry in each
participant's color. Sphere radius follows `eyeball_radius_mm` (12 mm by default)
and updates immediately with settings. Skeleton segments and glasses use live
capped tube filters (9 mm and 2.5 mm radii respectively), with Phong interpolation
and modest specular highlights. Eye sphere glyphs and tube filters reuse their
actors during playback; recorded joints and eye-center coordinates are unchanged.

An invisible white scene light sits above the recording bounds. VTK's shadow
pass requires a positional light's cone angle to be less than 90 degrees, so this
uses a broad 50-degree downward beam with uniform angular intensity, rather than
an omnidirectional light. Its height adjusts to cover the ground. The ground is
now opaque to receive shadows and expands to cover the recording. Shadow-camera
aspect is explicitly square to avoid VTK dark-band artifacts in rectangular
windows and exports. Participant labels remain unlit annotations.

Native real-recording captures, including shadow-on/off comparisons and a close-up
of the spheres and Phong highlights, are in `.runtime/shiny/`. Automated tests
cover physical sphere radius and live center/radius changes, live tube geometry,
hidden positional lighting, and the shadow-camera aspect correction.

Validation: all 80 tests passed. The rebuilt standalone Linux package passed
native desktop playback, stable actor checks, PNG/FHD/4K captures, and 60-frame
FHD MP4 export (24 FPS, 2.5 seconds). Report:
`.runtime/shiny/package-smoke/smoke-result.json`. Real-data shadow-on/off captures
confirmed localized ground shadows without the earlier aspect-ratio bands.

### Lighting rollback, retaining spherical eyes — 2026-09-18

The owner rejected the rough shadows and opaque floor obscuring the frustums.
Restored the original line-based skeleton/glasses rendering, default scene lights,
and 30%-opaque, fixed-size ground plane. Removed the overhead light, shadow pass,
shadow-camera workaround, tube surfaces, and Phong/specular highlights.
Participant-colored eyeball spheres remain, with matte Gouraud shading under the
original lights and radius controlled by `eyeball_radius_mm`. Eye-center loading,
eye-relative glasses placement, settings, and caching are unchanged. This
supersedes the surface/lighting refinement above.

Rollback validation: 78 tests passed; real-data captures were inspected, and the
rebuilt package passed native playback and PNG/FHD/4K/MP4 export checks. Artifacts:
`.runtime/matte/`, with package report at `package-smoke/smoke-result.json`.

### White Wayfarer-style frames — 2026-09-18

The owner supplied a Wayfarer reference and requested that silhouette in white.
Replaced rectangular outlines with closed, matte white frame surfaces: rounded
trapezoid rims, a thicker brow, raised curved bridge, and tapered temple arms with
curved ear tips. The frame uses fixed mesh topology and in-place point updates.
Rear rim planes remain radius + relief in front of each fitted eye (25 mm with
default settings); front frame surfaces extend another 4 mm. Frame styling and
temple dimensions remain illustrative rather than calibrated. Colored spherical
eyes, line skeletons, default lighting, and the translucent floor are retained;
Phong shine, overhead light, and shadows remain absent. Front/angled real-data
captures are in `.runtime/wayfarer/`.

Frame-style validation: 78 tests passed, including rotated rear-plane clearance
and live renderer updates. The rebuilt package passed stable-actor playback and
PNG/FHD/4K/MP4 exports; report: `.runtime/wayfarer/package-smoke/smoke-result.json`.


### Floor at the lowest joint — 2026-09-18

Replaced the ankle/foot percentile proxy with the minimum finite display-world Z
across all valid participant frames, including all 22 reconstructed body joints
and both eye centers. The loading worker computes it once and stores it in
`floor_proxy_z_m`; cache derivation v5 forces older caches to rebuild. Rendering
continues to use the stored height, preserving the translucent floor and original
motion coordinates. This is not a measured floor or a surface/sole-contact minimum.

Validation: 83 automated tests passed, covering minima across either person,
different frames/joints, eye centers, invalid frames, nonfinite positions, and
cache persistence. The 1,290-frame real recording rebuilt successfully; the floor
was -1.68041313 m, versus the prior percentile's -1.67204177 m (8.37 mm lower).
The cached reload matched, and desktop inspection confirmed fixed floor height at
frames 0, 430, and 1289. Captures/report: `.runtime/min-floor/`.

### Factory Reset in settings — 2026-09-18

Every parameter now includes an explicit validated `factory_default` in
`config/settings_panel.json`: 12 mm for eyeball radius and 13 mm for eye relief.
The Settings dialog's **Factory Reset** button fills every field from that
parameter's factory value using its configured precision and clears validation
errors. Reset is staged: Save persists/applies it, while Cancel leaves the current
settings unchanged. Existing current values, including the owner's 30 mm radius
adjustment, are preserved until Save. The earlier `default` metadata is retained;
Factory Reset explicitly uses `factory_default`.

Validation: 86 tests passed, including reset/save/cancel behavior, invalid factory
values, preservation of factory metadata, and use of factory values independently
of the earlier default field. Dialog layout inspected in
`.runtime/factory-reset/settings.png`.

### Recording-load decompression error — 2026-09-18

The owner reported `Error -3 while decompressing data: incorrect header check`
when selecting `recording_20211002_S17_S15_02`. A fresh source load reconstructed
all 360 paired frames without invalid frames. All seven existing recording caches
and all 1,885 modules in the current packaged Python archive decompressed
successfully; the exact reported failure was not reproduced. A packaged process
left running across an in-place rebuild is a possible cause, not a confirmed one.

Fixed an independently verified recovery gap: a `zlib.error` while reading a
derived cache now rebuilds it, like other cache corruption errors. A regression
test damages an actual compressed array while preserving the ZIP directory,
checks reconstruction and the subsequent cache hit, and verifies unchanged source
data. Worker failures now log their full traceback to stderr for diagnosis.

Validation: 87 tests passed. The loading controller switched from the 1,290-frame
`recording_20210907_S02_S01_01` to the reported 360-frame recording and back.
This remains Phase 2; the joint playback review and phase gate remain pending.
The updated package is in `dist/EyeGlowEgoBody-loading-fix/`, separate from the
existing build to avoid replacing files beneath an open application. Its desktop
smoke test passed, including playback, PNG capture, and MP4 export; report:
`.runtime/loading-fix/package-smoke-display/smoke-result.json`. Offscreen Qt could
not create an OpenGL context, so this check used the desktop display.

### Phase 2 sign-off — 2026-09-18

The project owner confirmed Phase 2 complete after the playback and eye-placement
review. This supersedes the pending-sign-off statements in the historical notes
above. The documented minimum-joint floor approximation and deferred improvement
carry forward. Phase 3 is approved to begin; no Phase 3 implementation is included
in this completion record.
