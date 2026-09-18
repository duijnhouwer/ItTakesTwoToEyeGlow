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

The source dataset at `../assets/egobody-data` is read-only throughout every phase.
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

> **Phase 1 complete**
>
> Concluded on 2026-09-18 11:40AM EDT. Commit: `116e7bff632e185c0e9d87ca872c21834bab9c9b`.

## Phase 2 — EgoBody Data Inspection, Loading, and Two-Person Playback

### Rationale

The immediate priority is to establish what the local EgoBody dataset actually
contains and replace synthetic motion with a real two-person recording. Inspect
its organization and stored values before choosing a loader or assuming joint,
pose, timing, or coordinate conventions. Validate paired playback before
implementing visibility mathematics or final optical rendering.

### Implementation goal

Inspect the dataset read-only, document the observed structure, and connect one
representative paired recording to the existing application:

- Document the directory layout, recording identifiers, participant roles,
  representative file formats, field names, array shapes, and available metadata.
- Establish how the two people are paired and synchronized, including frame IDs,
  timestamps or frame rate, missing frames, units, and coordinate transforms.
- Confirm whether files contain usable joints or body-model parameters requiring
  reconstruction; identify any required model assets before implementing loading.
- Discover recordings with matching participant motion and paired frames.
- Display basic recording metadata and validation status.
- Load and normalize a selected recording into compact contiguous NumPy arrays.
- Establish a shared coordinate system without applying transforms twice.
- Document available head-pose information and any approximations needed for
  existing placeholder optics; calibrated eye/glasses geometry remains later work.
- Mark missing or unusable frames invalid rather than silently fabricating data.
- Write versioned derived caches only under `code-repo/.runtime/`.
- Load and preprocess in a worker so the UI remains responsive.
- Replace the synthetic demo as the primary playback path with both real
  participant skeletons, synchronized in the existing viewport. Keep synthetic
  fixtures available for deterministic tests.
- Reuse play/pause, stepping, scrubbing, and camera controls with the recording
  actual frame count and timing rather than synthetic constants.
- Provide transformation and placement diagnostics needed for validation.

### Completion criteria

- A dataset inspection note shows representative paths, fields, shapes, pairing
  rules, and coordinate/timing evidence, separating observations from assumptions.
- At least one actual two-person recording loads and plays in the application
  from its compact normalized representation, with both people visible together.
- Playback controls and frame labels follow the loaded recording length and timing.
- Participant scale, floor height, separation, orientation, and contact moments
  are physically plausible on manual inspection.
- Every derived or approximated value is identified in metadata.
- Cache invalidation accounts for source identity, transformation/schema version,
  and relevant derivation rules.
- A cache failure safely falls back to rebuilding outside the dataset.

## Test Phase 2 — Real-Data Validation

### Developer tests

- Run discovery, pairing, normalization, cache, and invalid-frame integration
  tests against a small representative fixture or bounded dataset sample.
- Verify cold-load and cached-load behavior.
- Audit filesystem activity and confirm the dataset remains unchanged.
- Inspect diagnostic coordinate frames and numeric ranges.

### Joint hands-on test

Select and review at least one recording together. Check body heights, floor
alignment, facing direction, approach/contact moments, participant identity,
head orientation where available, and any placeholder-optics placement. Record any approximation
that is acceptable for the MVP.

### Gate to Phase 3

Both testers agree that the dataset organization and pairing are understood and
that the application shows actual synchronized two-person motion. Known data
and coordinate limitations are documented before beginning the analysis engine.

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
boundary inclusion and positive pitch/yaw before visibility analysis is applied
to the real recordings loaded in Phase 2.

### Gate to Phase 4

Both testers agree that the visibility definition is represented correctly and
the synthetic results are explainable. Mathematical disagreements are resolved
in tests and documentation before proceeding.

## Phase 4 — Final Glasses and EyeGlow Rendering

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

## Test Phase 4 — Optical Rendering Review

### Developer tests

- Compare actor geometry with known numeric frustum fixtures.
- Test all display modes and parameter limits.
- Verify independent left/right camera containment.
- Stress playback and repeated parameter changes for leaks or stale actors.

### Joint hands-on test

Inspect the glasses from several camera angles, exercise every optical control,
toggle diagnostics, and deliberately move the camera into and out of individual
frustums. Confirm that the visualization explains the underlying geometry.

### Gate to Phase 5

Both testers agree that optical geometry is correctly placed, understandable,
and responsive.

## Phase 5 — Integrated Bidirectional Visibility

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

## Test Phase 5 — Visibility Result Review

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

### Gate to Phase 6

Both testers agree that representative visibility results are correct and
explainable. Any suspected false positive or false negative is resolved or
documented as an accepted MVP limitation.

## Phase 6 — Complete Playback, Timeline, and Score Experience

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

## Test Phase 6 — End-to-End Usability Review

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

### Gate to Phase 7

Both testers agree that the complete analysis workflow is coherent, synchronized,
and understandable.

## Phase 7 — Activity Filtering, Selection, and Reporting

### Rationale

The project owner wants to report potential EyeGlow visibility during selected
activities, for example casual conversation, and isolate or combine activities
without selecting from 147 raw activity names individually. Design the selection
interface together before implementing it, once the visibility and timeline
workflow is available.

### Annotation evidence and starting proposal

The read-only source is
`../assets/egobody-data/Motion-X-main/mocap-dataset-process/egobody_description_all.csv`.
The inspected file contains 980 participant-specific intervals across all 125
recordings and both participants: 147 distinct activity names after removing
`_clip<number>` suffixes, or 146 after normalizing spaces and underscores.
Fifteen of the 250 participant tracks have gaps in interval coverage; an activity
label must not be silently carried through an unlabeled interval.

The EgoBody paper describes cooperation, social exchange, conflict, conformity,
and others ([Table 2](https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136660176.pdf#page=6)).
The local CSV supplies no mapping from activity labels to these categories.
The following six groups are a **proposed application grouping**, not an official
EgoBody taxonomy or an approved exhaustive mapping:

| Proposed activity group | Example labels / activities |
|---|---|
| Conversation | `casual_chat`, `stand_casual_chat`, seated-chat variants |
| Teaching / learning | teaching, learning, instructing, attending class |
| Dance | `dance`, `teach_dance`, `learn_to_dance` |
| Exercise | stretching, squatting, jumping jacks, Tai Chi |
| Object interaction | passing, catching, tossing, taking objects |
| Acting / guessing | performing actions, drawing with hands, guessing |

Preserve these proposals for the design discussion. Groups may overlap:
`teach_dance`, for example, can belong to both Teaching / learning and Dance.
Keep original labels available. Consider posture (sitting/standing/walking) and
location as separate selection dimensions rather than multiplying activity groups.
Ambiguous labels and labels not yet mapped to a group must remain visible.

### Interface and semantics decisions — before implementation

- Review alternatives for searchable label selection, group checkboxes with
  expandable members, custom combinations, and saved selection presets. Agree on
  the interface with the project owner before building it.
- Review the six proposed groups and their exact label membership; decide how to
  handle spelling variants, compound activities, overlaps, and unmapped labels.
- Decide whose annotation selects an interval: the viewer, the EyeGlow emitter,
  either participant, or both. Define this explicitly for each visibility direction;
  camera wearer/interactee identity remains separate from viewer/emitter role.
- Decide union versus intersection behavior for combined selections, and whether
  the first implementation aggregates within one recording or across recordings.
- Resolve shared annotation endpoints and missing labels; define how selections
  appear on the timeline and whether they affect playback navigation.
- Agree on the report wording and denominator: potential visibility during valid
  selected time, accompanied by selected duration, usable duration, recording
  count, and excluded/unlabeled time where relevant.

### Implementation goal

Implement the agreed interface and selection semantics as one testable increment:

- Load participant/frame-range annotations without modifying the source CSV.
- Keep a versioned, inspectable mapping from original labels to normalized labels
  and application groups, stored outside the dataset.
- Select individual labels, groups, and user-defined combinations; retain the
  exact selection and grouping version so reported results can be reproduced.
- Apply selection masks consistently to the timeline and visibility summaries.
  Use duration-weighted aggregation; do not average clip percentages or double
  count time that matches overlapping groups. Do not join visibility events
  across excluded intervals or recording boundaries.
- Provide clear empty-selection, no-match, invalid-data, and unlabeled feedback.

### Completion criteria

- The project owner has agreed to the interface, group membership, participant
  semantics, and aggregation scope before implementation.
- Conversation variants can be selected together; individual labels can still
  be isolated and groups combined without counting an interval twice.
- Every filtered result identifies the activity selection, direction/participant
  rule, denominator, and included recordings. Original labels remain traceable.
- Filtered intervals and reported results agree with hand-checked examples.

## Test Phase 7 — Activity Selection and Reporting Review

### Developer tests

Test source participant identity and frame alignment, label normalization, group
membership, overlapping selections, union/intersection rules, annotation gaps and
shared boundaries. Verify duration-weighted denominators, empty results, event
boundaries, and multi-recording aggregation if included in the agreed scope.

### Joint hands-on test

Build a Conversation selection, isolate one label, combine Dance with Teaching /
learning, and inspect the selected timeline intervals and resulting report.
Review cases where the two participants have different activities. Confirm that
the selection is understandable and that its exact membership can be recovered.

### Gate to Phase 8

Both testers agree that activity selection and filtered visibility reports are
understandable, reproducible, and numerically consistent with the selected time.

## Phase 8 — Complete Export Workflow

### Rationale

Finalize shareable output after playback, rendering, and analysis behavior are
settled, so cross-platform validation can exercise the complete workflow.

### Implementation goal

- Finish screenshot and MP4 export for representative recordings and selected
  intervals, building on the Phase 1 export implementation.
- Preserve the approved scene-only PNG capture and modal video settings workflow.
- Provide progress, cancellation, clear errors, and safe overwrite handling.
- Let the user control diagnostic-overlay inclusion in exported scenes.
- Document supported outputs and relevant recording/settings context.

### Completion criteria

- Screenshots and videos reproduce the selected scene and visibility state.
- Export settings, selected interval, frame dimensions, and timing are respected.
- Progress reporting remains responsive; cancellation preserves existing output.
- Outputs and temporary files remain outside the source dataset.

## Test Phase 8 — Export Review

### Developer tests

- Validate PNG and MP4 output, interval boundaries, dimensions, and timing.
- Exercise cancellation, encoder failure, overwrite handling, and cleanup.
- Confirm exports remain synchronized with analysis and rendered geometry.

### Joint hands-on test

Export stills and videos from a representative recording, inspect the results,
and review the settings, progress, cancellation, and error experience.

### Gate to Phase 9

Both testers agree that the complete Linux workflow and exports are ready for
native packaging and validation on the other target platforms.

## Phase 9 — Cross-Platform Packaging and Validation

### Rationale

PyInstaller packages include platform-specific Python, Qt, VTK, and native
libraries and therefore must be built and tested on their target operating
systems. Deployment validation is deliberately deferred until the core workflow
and exports are complete, so development can continue on Linux. Platform
compatibility remains unverified until this phase; resolve any resulting issues
before final polishing.

### Implementation goal

Package the complete application on Linux and build it natively on both
additional MVP target platforms:

- Windows 11 x64 using the available Windows development machine.
- A recent macOS release on Apple Silicon using the available Mac.
- Intel Macs are explicitly unsupported.
- Use equivalent pinned application dependencies across all three platforms,
  allowing only documented platform-specific differences.
- Produce a PyInstaller one-folder package on each native target system; do not
  cross-compile.
- Document reproducible environment setup and build commands for each platform.
- Make only the minimum platform-specific code or packaging changes required to
  preserve the completed Linux workflow, analysis results, and exports.

### Completion criteria

- The packaged application launches outside the development environment on
  Windows 11 x64 and recent macOS on Apple Silicon.
- Recording discovery/loading, playback, optical controls, visibility analysis,
  timeline, scores, screenshots, and MP4 export work on all three platforms.
- Synthetic fixtures produce equivalent numeric analysis results across platforms.
- Platform-specific fixes do not break the tested Linux package.
- The exact OS version, CPU architecture, Python version, dependency versions,
  build command, warnings, and result are recorded for all three platforms.
- Any unsupported behavior is documented and does not conflict with the MVP
  acceptance criteria.

## Test Phase 9 — Cross-Platform Deployment Review

### Developer tests

- Create each package on its native operating system from a clean checkout or
  documented clean environment.
- Launch each package without relying on the development virtual environment.
- Run the same startup, recording-loading, playback, camera, analysis, timeline,
  screenshot, and MP4 export checks on Windows 11 x64, Apple Silicon macOS, and
  Linux, using synthetic fixtures and a representative recording.
- Check display scaling, transparency, high-resolution capture, and bundled FFmpeg.
- Inspect packaged output for missing Qt or VTK plugins and unintended absolute
  paths or undeclared runtime dependencies.
- Confirm that outputs are written to permitted user-writable locations and that
  no file is written under `egobody-data`.

### Joint hands-on test

Together, review the Windows 11 and Apple Silicon macOS builds using the same
core workflow approved on Linux. Compare behavior and record platform-specific
differences rather than accepting silent divergence.

### Gate to Phase 10

Both testers agree that the application can be built, launched, and exercised as
a standalone package on Linux, Windows 11 x64, and recent Apple Silicon macOS.
Any platform issue that blocks the core workflow is resolved before final
polishing begins.

## Phase 10 — Final Polishing and MVP Acceptance

### Rationale

Polish the application after native platform validation, so final refinements
account for the behavior of all supported systems.

### Implementation goal

- Resolve usability issues found during end-to-end and cross-platform review.
- Refine labels, layout, display scaling, feedback, and visual consistency.
- Address measured responsiveness or stability issues in the completed workflow.
- Finish release documentation covering launch, dataset selection, limitations,
  supported outputs, and the read-only data policy.
- Rebuild final packages and audit all acceptance criteria in `INTENT.md`.
- Keep deferred features outside the MVP unless explicitly agreed otherwise.

### Completion criteria

- Final packages complete the core workflow on Linux, Windows 11 x64, and recent
  Apple Silicon macOS.
- Polishing changes preserve validated geometry, analysis, and export behavior.
- All 20 MVP acceptance criteria in `INTENT.md` are demonstrated or have an
  explicitly agreed disposition.
- Remaining limitations are documented and accepted as non-blocking.

## Test Phase 10 — Final MVP Acceptance Test

### Developer tests

- Run the complete unit and integration suites from a clean environment.
- Repeat packaged launch and core workflow smoke tests on all three platforms
  after final changes, including screenshot and MP4 export.
- Audit generated files, logs, and caches and verify the dataset is unchanged.
- Check documented dependency versions and build reproducibility.

### Joint hands-on test

Walk through the 20 acceptance criteria in `INTENT.md` using final packaged
applications and representative recordings. Inspect exports, review known
limitations, and decide whether any remaining issue blocks the MVP.

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
| 2 — EgoBody inspection and playback | Automated and real-playback checks passed | Pending | No | Supplied v1.1 models connected; 1,290- and 760-frame recordings loaded. See [inspection and validation](docs/PHASE2_DATA_INSPECTION.md). |
| 3 — Analysis engine | Not run | Not run | No | |
| 4 — Optical rendering | Not run | Not run | No | |
| 5 — Integrated visibility | Not run | Not run | No | |
| 6 — Timeline and UX | Not run | Not run | No | |
| 7 — Activity filtering and reporting | Not run | Not run | No | Interface and mapping decisions first; six proposed groups recorded above. |
| 8 — Export workflow | Not run | Not run | No | Builds on Phase 1 export refinements. |
| 9 — Cross-platform packaging | Not run | Not run | No | Deferred until the complete Linux workflow is ready. |
| 10 — Final polishing and MVP | Not run | Not run | No | |

## Scope-Change Rule

If testing reveals that a planned approach is invalid, update this document
before starting the next phase. Record the reason, affected acceptance criteria,
and whether the change is a correction, an MVP scope change, or a post-MVP
deferral. This keeps the plan useful as evidence of decisions rather than treating
it as an immutable schedule.

## Authorized Phase 1 export refinement

Historical phase numbers in the following decision records reflect the plan at
the time; the activity-selection addition below supplies the current numbering.

After the initial spike, the project owner requested visible save dialogs for
screenshots and video, an inclusive two-handle export-range bar below playback,
an **Export Video** button, and the entire recording selected by default.
These changes bring MP4 encoding forward from Phase 7 without starting the
remaining analysis-engine or export-workflow work. The screenshot dialog saves PNG; video saves
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

## Authorized phase reorder — 2026-09-18

The project owner requested continued development on Linux, with cross-platform
packaging toward the end and before a final polishing phase. The former Phase 2
deployment spike is now Phase 8 and validates the complete application. Data inspection/loading,
geometry analysis, optical rendering, integrated visibility, and timeline work occupy
Phases 2–6; export completion is Phase 7; final polishing and acceptance are Phase 9.
Windows 11 x64 and Apple Silicon macOS remain required MVP targets. Their native
validation is deferred, not waived, and compatibility fixes may require revisiting
earlier work. The MVP acceptance criteria and read-only dataset policy are unchanged.

### Real-data playback first

The project owner subsequently requested that dataset inspection and actual
paired-person playback become Phase 2, with geometry and visibility mathematics
moving to Phase 3. The immediate deliverable is evidence of how EgoBody data is
organized and a real two-person recording replacing the synthetic demo in the
viewport. This reorder does not require visibility scores in Phase 2 or change
Phases 4–9.


## Authorized activity-selection phase — 2026-09-18

The project owner requested a separate phase to decide on an interface for
filtering/selecting activities and to preserve the six proposed activity groups.
This adds Phase 7 after the main timeline/score experience. Export completion,
cross-platform packaging, and final polishing move to Phases 8, 9, and 10.
Phases 1–6 retain their scope and numbering. This is an authorized addition to
the plan for activity-specific visibility reporting; it does not authorize
starting later-phase implementation now or approve the proposed group mapping.
The existing MVP visibility criteria remain in force; the selection and reporting
criteria above extend them with explicit activity scope and reproducibility.

## Authorized Phase 2 eye placement and settings addition — 2026-09-18

During visual review, the owner requested SMPL-X eye-center point markers and
placeholder glasses positioned by eyeball radius plus eye relief, with defaults
12 mm and 13 mm. The owner also requested `config/settings_panel.json` containing
values, display names, min/max, and precision, and a functional File → Settings ...
dialog for editing values. This small placement/settings increment is authorized
before Phase 3; final optical geometry and visibility analysis retain their later
phase scope. See the latest [Phase 2 validation note](docs/PHASE2_DATA_INSPECTION.md).

### Authorized surface and lighting refinement

The owner subsequently requested participant-colored spherical eyeballs, modest
Phong shine on all segments and eyes, and an invisible overhead white light
casting ground shadows. This extends the Phase 2 visual representation with real
sphere/tube surfaces and a shadow-receiving ground, without starting visibility
analysis or final optical modeling.

### Surface and lighting rollback

The owner subsequently rejected the shadow appearance and opaque floor. Restore
the original lines, lighting, and translucent ground; retain only the colored,
radius-controlled eyeball spheres from the surface/lighting refinement. No Phong
highlights, overhead light, or shadows remain.

### Authorized frame styling

The owner supplied a Wayfarer-style reference and requested white frames with
that silhouette. This authorizes rounded trapezoid rim surfaces, a curved bridge,
and tapered temples while retaining the current eye-relative placement and
no-shadow rendering. Final optical geometry and analysis remain later work.
