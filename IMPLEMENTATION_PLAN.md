# EyeGlow EgoBody — Implementation Phases

## Purpose

This document breaks the MVP defined in [`INTENT.md`](INTENT.md) into small,
testable implementation phases that follow the boundaries in
[`ARCHITECTURE.md`](ARCHITECTURE.md).

The phases are deliberately incremental. Each implementation phase must produce
something that can be run, inspected, or measured. It is followed by a test
phase in which both the developer and the project owner test the software.
Work does not begin on the next implementation phase until both agree that the
current phase's completion criteria have been met, or explicitly agree to carry
a documented issue forward.

The source dataset at `../egobody-data` is read-only throughout every phase.
All caches, indexes, logs, test outputs, screenshots, and exports must be written
outside that directory.

## Working Rules

- Build the smallest useful vertical increment in each phase.
- Keep numeric analysis independent of Qt, PyVista, and VTK.
- Prefer deterministic synthetic fixtures for geometry tests.
- Add real EgoBody data only after the basic application and rendering stack are
  proven.
- Treat skeleton playback as the MVP participant representation. SMPL-X meshes
  are optional and must not delay the MVP.
- Reuse live VTK actors and update them in place rather than rebuilding the scene
  on every frame.
- Keep expensive loading, preprocessing, analysis, and export work off the Qt
  event loop.
- Record known limitations and approximations, especially coordinate transforms,
  head pose, and eye-socket placement.
- A passing automated test suite is necessary but not sufficient: each phase also
  requires a short hands-on review.

## Phase 1 — Application and Rendering Technical Spike

### Rationale

The largest early integration risks are the PySide6/PyVistaQt/VTK combination,
responsive actor updates, and packaging native dependencies. Proving these with
synthetic data is faster and easier to diagnose than introducing EgoBody file
formats and coordinate systems at the same time.

### Implementation goal

Create a minimal installable project and a runnable desktop application that
demonstrates the chosen architecture without reading EgoBody data.

The spike will include:

- The proposed package boundaries, test directories, dependency definition, and
  application entry point.
- A PyVistaQt viewport embedded in a PySide6 main window.
- Two distinct, labeled synthetic stick figures moving through a short generated
  sequence.
- Simple head-locked glasses markers and translucent placeholder frustums.
- Play, pause, frame stepping, basic scrubbing, and a frame counter.
- Orbit, pan, zoom, camera reset, and fit-to-participants behavior.
- One parameter control that updates the placeholder frustums without reloading.
- In-place VTK actor updates during playback.
- Screenshot capture and a short numbered-frame export.
- A PyInstaller one-folder build for the supported Linux baseline.

This phase does not implement final frustum mathematics, visibility scoring, or
EgoBody loading. Placeholder geometry must be clearly labeled as such.

### Completion criteria

- The application launches from source, and its standalone one-folder package
  launches outside the development environment on the supported Linux baseline.
- The UI remains interactive during synthetic playback.
- Both figures, their head-locked geometry, and the frame display stay in sync.
- Camera controls and the live parameter control behave correctly.
- Screenshot and numbered-frame export produce usable files outside the dataset.
- Core model modules can be imported without creating a Qt application or render
  window.

## Test Phase 1 — Technical Spike Review

### Developer tests

- Run automated startup/import smoke tests.
- Verify actor identities remain stable during frame updates.
- Exercise playback at multiple speeds and watch for UI stalls or memory growth.
- Verify screenshots and frame sequences are created in approved output paths.
- On Linux, build and launch the one-folder package and record the operating-system
  version, CPU architecture, Python version, build command, and result.
- Confirm that no file is written anywhere under `egobody-data`.

### Joint hands-on test

Together, launch the app on Linux, manipulate the camera, play and scrub the
synthetic motion, change the parameter, and create an export. Review whether the
basic viewport interaction is understandable before it becomes the foundation
of the full UI.

### Gate to Phase 2

Both testers agree that the desktop/rendering stack is viable and responsive,
and a standalone Linux package has passed the Phase 1 smoke test. Any packaging
or interaction issue that could invalidate the architecture must be resolved
before proceeding.

## Phase 2 — Windows and Apple Silicon Deployment Spike

### Rationale

PyInstaller packages include platform-specific Python, Qt, VTK, and native
libraries and therefore must be built and tested on their target operating
systems. Validating deployment immediately after the Linux technical spike
catches platform incompatibilities before significant application functionality
depends on the stack.

### Implementation goal

Build the Phase 1 synthetic application natively on both additional MVP target
platforms:

- Windows 11 x64 using the available Windows development machine.
- A recent macOS release on Apple Silicon using the available Mac.
- Intel Macs are explicitly unsupported.
- Use equivalent pinned application dependencies across all three platforms,
  allowing only documented platform-specific differences.
- Produce a PyInstaller one-folder package on each native target system; do not
  cross-compile.
- Document reproducible environment setup and build commands for each platform.
- Make only the minimum platform-specific code or packaging changes required to
  preserve the same behavior demonstrated in Phase 1.

### Completion criteria

- The packaged application launches outside the development environment on
  Windows 11 x64 and recent macOS on Apple Silicon.
- Synthetic playback, camera interaction, parameter updates, screenshots, and
  numbered-frame export work on both platforms.
- Platform-specific fixes do not break the tested Linux package.
- The exact OS version, CPU architecture, Python version, dependency versions,
  build command, warnings, and result are recorded for all three platforms.
- Any unsupported behavior is documented and does not conflict with the MVP
  acceptance criteria.

## Test Phase 2 — Cross-Platform Deployment Review

### Developer tests

- Create each package on its native operating system from a clean checkout or
  documented clean environment.
- Launch each package without relying on the development virtual environment.
- Run the same startup, playback, camera, parameter, screenshot, and frame-export
  smoke-test checklist on Windows 11 x64, Apple Silicon macOS, and Linux.
- Inspect packaged output for missing Qt or VTK plugins and unintended absolute
  paths or undeclared runtime dependencies.
- Confirm that outputs are written to permitted user-writable locations and that
  no file is written under `egobody-data`.

### Joint hands-on test

Together, review the Windows 11 and Apple Silicon macOS builds using the same
core workflow approved on Linux. Compare behavior and record platform-specific
differences rather than accepting silent divergence.

### Gate to Phase 3

Both testers agree that the application can be built, launched, and exercised as
a standalone package on Linux, Windows 11 x64, and recent Apple Silicon macOS.
Any platform issue that threatens later MVP deployment is resolved before the
analysis engine is implemented.

## Phase 3 — Geometry and Visibility Analysis Engine

### Rationale

Visibility results are the scientific core of the application. Implementing and
testing them independently prevents visual output from becoming an unverified
source of truth.

### Implementation goal

Implement the pure NumPy model and analysis layers using synthetic fixtures:

- Validated shared optical-parameter model with explicit units and defaults.
- Glasses coordinate frames and documented left/right eye and waveguide
  conventions.
- Chief-ray construction from pitch and yaw.
- Rectangular waveguide near planes and rectangular frustum construction.
- Stable point-in-frustum tests, including boundary behavior.
- Monocular-left, monocular-right, and binocular activation.
- Maximum-distance, valid-data, and receiver head-facing tests.
- Per-eye and bidirectional visibility-state reduction using the explicit states
  `INVALID`, `NONE`, `LEFT_EYE`, `RIGHT_EYE`, and `BOTH_EYES`.
- Duration-weighted scores and event detection for uniform and irregular
  timestamps.
- Numeric diagnostic outputs sufficient to explain why a test passed or failed.

### Completion criteria

- Analysis modules have no Qt, PyVista, or VTK dependency.
- Coordinate handedness, angle signs, boundary inclusion, and units are documented
  in code and tests.
- Synthetic scenarios cover obvious visible, invisible, one-eye, two-eye,
  orientation-rejected, distance-rejected, and invalid-data cases.
- Summary percentages, simultaneous visibility, event counts, and longest events
  match hand-calculated expectations.

## Test Phase 3 — Mathematical Validation

### Developer tests

- Run unit tests for chief rays, frustum planes, containment boundaries, display
  modes, facing thresholds, invalid frames, state reduction, scores, and events.
- Add invariance checks for rigid transforms and participant swapping where
  applicable.
- Check numerical behavior at exact angular, distance, and frustum boundaries.

### Joint hands-on test

Review a small set of illustrated or printed synthetic scenarios and compare the
expected result with the engine output. Agree on ambiguous conventions such as
boundary inclusion and positive pitch/yaw before real data is introduced.

### Gate to Phase 4

Both testers agree that the visibility definition is represented correctly and
the synthetic results are explainable. Mathematical disagreements are resolved
in tests and documentation before proceeding.

## Phase 4 — EgoBody Discovery, Loading, and Coordinate Validation

### Rationale

Real-data integration carries a separate class of risk: paired-frame discovery,
file-format variation, coordinate transforms, missing data, and accidental
double transformation. It should be validated before it is coupled to final
optical rendering or scoring UI.

### Implementation goal

Build the read-only EgoBody data pipeline and connect one representative
recording to skeleton playback:

- Discover recordings with matching participant motion and paired frames.
- Display basic recording metadata and validation status.
- Load and normalize a selected recording into compact contiguous NumPy arrays.
- Establish a shared coordinate system without applying transforms twice.
- Derive documented head pose, head-forward direction, eye-socket estimates, and
  glasses transforms from the available data.
- Mark missing or unusable frames invalid rather than silently fabricating data.
- Write versioned derived caches only under `code-repo/.runtime/`.
- Load and preprocess in a worker so the UI remains responsive.
- Animate both real participant skeletons synchronously in the existing viewport.
- Provide transformation and placement diagnostics needed for validation.

### Completion criteria

- At least one representative paired recording loads and plays from its compact
  normalized representation.
- Participant scale, floor height, separation, orientation, and contact moments
  are physically plausible on manual inspection.
- Every derived or approximated value is identified in metadata.
- Cache invalidation accounts for source identity, transformation/schema version,
  and relevant derivation rules.
- A cache failure safely falls back to rebuilding outside the dataset.

## Test Phase 4 — Real-Data Validation

### Developer tests

- Run discovery, pairing, normalization, cache, and invalid-frame integration
  tests against a small representative fixture or bounded dataset sample.
- Verify cold-load and cached-load behavior.
- Audit filesystem activity and confirm the dataset remains unchanged.
- Inspect diagnostic coordinate frames and numeric ranges.

### Joint hands-on test

Select and review at least one recording together. Check body heights, floor
alignment, facing direction, approach/contact moments, participant identity,
head orientation, and glasses/eye-socket placement. Record any approximation
that is acceptable for the MVP.

### Gate to Phase 5

Both testers agree that the real motion is synchronized and physically plausible
enough to support visibility analysis. Coordinate-system uncertainty is not
carried forward silently.

## Phase 5 — Final Glasses and EyeGlow Rendering

### Rationale

With coordinate placement and numeric geometry established, the renderer can
faithfully visualize the analysis inputs without inventing a second definition
of visibility.

### Implementation goal

Replace placeholder optics with final MVP rendering:

- Recognizable generic glasses with bridge, frames, lenses, and fixed visual
  pantoscopic tilt of 5 degrees.
- Independently addressable left and right rectangular waveguides.
- Rendered frustums generated from analysis geometry.
- Chief-ray and coordinate-frame diagnostics.
- Monocular-left, monocular-right, and binocular display modes.
- Controls for waveguide size, horizontal/vertical FOV, chief-ray pitch/yaw,
  maximum distance, opacity, visibility toggles, and reset to defaults.
- Immediate current-frame geometry updates when parameters change.
- Render-camera containment that turns each waveguide white independently when
  the camera lies inside its frustum; this remains unscored.

### Completion criteria

- Glasses, waveguides, rays, and frustums remain head-locked throughout playback.
- Rendered frustum corners agree numerically with the analysis engine.
- All shared optical controls affect both participants consistently.
- Camera containment changes only visual waveguide state and never participant
  scores.

## Test Phase 5 — Optical Rendering Review

### Developer tests

- Compare actor geometry with known numeric frustum fixtures.
- Test all display modes and parameter limits.
- Verify independent left/right camera containment.
- Stress playback and repeated parameter changes for leaks or stale actors.

### Joint hands-on test

Inspect the glasses from several camera angles, exercise every optical control,
toggle diagnostics, and deliberately move the camera into and out of individual
frustums. Confirm that the visualization explains the underlying geometry.

### Gate to Phase 6

Both testers agree that optical geometry is correctly placed, understandable,
and responsive.

## Phase 6 — Integrated Bidirectional Visibility

### Rationale

This phase connects validated motion and validated geometry to deliver the
project's central could-have-seen result before investing in the full timeline
and presentation layer.

### Implementation goal

Run whole-recording bidirectional analysis and expose its current-frame and
summary results:

- Analyze A's active frustums against B's eye sockets and vice versa.
- Apply head-facing, maximum-distance, and valid-data conditions.
- Show above-head indicators describing what each participant can currently see.
- Display current per-eye state and the core directional percentages.
- Recompute results in a background worker when relevant parameters change.
- Debounce rapid control changes and discard superseded worker results.
- Keep current-frame feedback responsive while whole-recording results update.
- Expose diagnostic pass/fail information for containment, facing, distance, and
  data validity.

### Completion criteria

- Current indicators and displayed state always match the analysis result for the
  selected frame.
- Scores are duration-weighted when timestamps are irregular.
- Rapid parameter changes cannot display results from an older request.
- Invalid intervals are excluded from denominators and visibly distinguishable
  from valid-but-invisible intervals.

## Test Phase 6 — Visibility Result Review

### Developer tests

- Run end-to-end tests from normalized arrays through visibility states and
  scores.
- Spot-check selected real frames by independently inspecting diagnostics and
  numeric values.
- Exercise rapid parameter changes, cancellation/supersession, invalid frames,
  and both analysis directions.

### Joint hands-on test

Review several predicted visible and invisible moments in both directions. Use
diagnostics to explain each outcome, and test whether parameter changes produce
directionally sensible changes rather than merely plausible-looking animation.

### Gate to Phase 7

Both testers agree that representative visibility results are correct and
explainable. Any suspected false positive or false negative is resolved or
documented as an accepted MVP limitation.

## Phase 7 — Complete Playback, Timeline, and Score Experience

### Rationale

Once the results are trustworthy, the remaining interaction can be organized
around exploring them efficiently. Deferring the polished workflow prevents UI
work from hiding uncertainty in the data or analysis.

### Implementation goal

Complete the primary application workflow:

- Recording browser with available metadata, paired-frame count, validation, and
  cache status.
- Play, pause, step, reset, speed, loop, scrub, current frame, and total frames.
- Two-lane synchronized timeline for A-sees-B and B-sees-A.
- Clear encodings for invalid, none, one-eye, and two-eye states.
- Click or drag timeline navigation with a synchronized playhead.
- Score panel containing every MVP summary listed in `INTENT.md`, including
  either-direction, mutual, one-eye/two-eye, event count, and longest event.
- Camera presets for reset, fit, front, side, and top.
- Useful loading, analysis, empty-state, and error feedback.
- A diagnostic-mode control and clear labeling of potential visibility.

### Completion criteria

- Playback controls, scene, indicators, timeline, frame labels, and scores all
  derive from controller-owned state and remain synchronized.
- Timeline scrubbing remains usable for a representative recording.
- Parameter-dependent recalculation clearly indicates pending versus current
  results.
- A new user can select a recording and find a visibility event without developer
  guidance.

## Test Phase 7 — End-to-End Usability Review

### Developer tests

- Run state-synchronization and integration tests for playback, scrubbing,
  timeline, selection, and recalculation.
- Test empty, invalid, loading, error, and cache-rebuild states.
- Exercise a representative full recording for responsiveness and memory use.

### Joint hands-on test

Perform the core experience from launch through recording selection, playback,
event discovery, parameter adjustment, and score interpretation. Note confusing
labels or controls, and verify that the interface never overstates geometric
opportunity as actual perception.

### Gate to Phase 8

Both testers agree that the complete analysis workflow is coherent, synchronized,
and understandable.

## Phase 8 — Export, Packaging, and Complete MVP

### Rationale

Export and distribution cross-cut the stable application and should be finalized
only after playback, rendering, state, and analysis behavior are settled.

### Implementation goal

Finish the shareable output and release path:

- Screenshot export with recording identity, relevant settings, and current
  visibility context.
- Numbered-frame animation export for a selected interval as the reliable
  baseline.
- Direct MP4 export through a separate FFmpeg process when available; otherwise
  provide a clear frame-sequence result and conversion guidance.
- Progress, cancellation, errors, and collision-safe output naming.
- Diagnostic-overlay inclusion controlled by the user.
- PyInstaller one-folder builds on each available target platform.
- Release documentation covering launch, dataset selection, limitations,
  supported outputs, and the read-only data policy.
- A final audit against all acceptance criteria in `INTENT.md`.

### Completion criteria

- Still and animation/frame-sequence exports reproduce the selected scene and
  visibility state correctly.
- Export work does not freeze normal UI progress reporting and does not write to
  the source dataset.
- The packaged application launches and completes the core workflow on every
  target platform claimed as supported.
- All 20 MVP acceptance criteria in `INTENT.md` are either demonstrated or have
  an explicitly agreed disposition.
- Deferred features remain deferred unless both testers deliberately change the
  MVP scope.

## Test Phase 8 — MVP Acceptance Test

### Developer tests

- Run the complete unit and integration suites from a clean environment.
- Perform packaged-application launch and workflow smoke tests on the supported
  Windows 11 x64, Apple Silicon macOS, and Linux targets.
- Validate screenshot, frame-sequence, and MP4 paths where supported.
- Audit generated files, logs, and caches and verify the source dataset is
  unchanged.
- Check documented dependency versions and reproducibility of the build.

### Joint hands-on test

Walk through the 20 acceptance criteria in `INTENT.md` using the packaged
application and one or more representative recordings. Inspect exported output,
review known limitations, and decide whether any remaining issue blocks the MVP.

### MVP completion gate

The MVP is complete only when both testers explicitly agree that the acceptance
criteria have been met and that remaining issues are documented, understood, and
non-blocking.

## Phase Sign-Off Record

Use this table as the project advances. A phase is not approved merely because
implementation stopped; approval follows the corresponding joint test phase.

| Phase | Developer test | Joint test | Approved to proceed | Notes |
|---|---|---|---|---|
| 1 — Technical spike | Passed on Linux | Pending | No | Implementation and one-folder package ready; see [validation record](docs/PHASE1_VALIDATION.md). |
| 2 — Cross-platform deployment | Not run | Not run | No | |
| 3 — Analysis engine | Not run | Not run | No | |
| 4 — EgoBody pipeline | Not run | Not run | No | |
| 5 — Optical rendering | Not run | Not run | No | |
| 6 — Integrated visibility | Not run | Not run | No | |
| 7 — Timeline and UX | Not run | Not run | No | |
| 8 — Export and MVP | Not run | Not run | No | |

## Scope-Change Rule

If testing reveals that a planned approach is invalid, update this document
before starting the next phase. Record the reason, affected acceptance criteria,
and whether the change is a correction, an MVP scope change, or a post-MVP
deferral. This keeps the plan useful as evidence of decisions rather than treating
it as an immutable schedule.

## Authorized Phase 1 export refinement

After the initial spike, the project owner requested visible save dialogs for
screenshots and video, an inclusive two-handle export-range bar below playback,
an **Export Video** button, and the entire recording selected by default.
These changes bring MP4 encoding forward from Phase 8 without starting the
remaining Phase 2 or Phase 8 work. The screenshot dialog saves PNG; video saves
H.264 MP4 via a bundled FFmpeg executable. Cancellation preserves existing output,
and temporary frame files are removed. The synthetic-data and read-only dataset
boundaries remain in force.

### Export dialog revision

The project owner subsequently replaced the export-range bar with a modal
**Export Video ...** settings dialog. It contains output filename/browse,
inclusive start/end frame fields, Full range, current/FHD/4K frame size,
1–120 FPS with data-native reset, 0–100 encoder quality, and selection count
and duration. **Save Screenshot ...** remains a PNG-only scene capture at the
current size. Default Linux filenames use the recording name in Videos/Pictures.
This supersedes the range-bar UI above; it does not authorize later phase work.
