# EyeGlow EgoBody — Application Architecture

## Status

This document defines the initial architecture for the MVP described in
[`INTENT.md`](INTENT.md). It is intended to guide implementation without
turning provisional details into product requirements.

The architecture prioritizes:

- Delivery of the MVP before Tuesday, September 22, 2026.
- Correct and testable geometric analysis.
- Responsive playback and parameter adjustment.
- A standalone desktop application for Windows, macOS, and Linux.
- Strictly read-only access to `egobody-data`.
- A clear path from skeleton visualization to optional SMPL-X meshes.

## Technology Decisions

### Language and runtime

The application will use Python 3.12 unless a required dependency forces a
different supported Python 3 version.

### Desktop user interface

The UI will use **PySide6 with Qt Widgets**.

Qt Widgets will provide:

- The main application window and layout.
- Recording selection and dataset metadata.
- Playback controls.
- Optical parameter controls.
- Score and current-state displays.
- The synchronized visibility timeline.
- Export and diagnostic controls.
- Worker-thread coordination and progress reporting.

Qt Quick and QML are not part of the initial architecture. They may be
reconsidered after the MVP if a more highly styled interface becomes useful.

### 3D visualization

The 3D viewport will use **PyVista**, backed by **VTK**, embedded in the
PySide6 UI using **PyVistaQt**.

This layer will render:

- Participant skeletons or point-light figures.
- Generic glasses, lenses, and waveguide rectangles.
- EyeGlow frustums and chief rays.
- Eye-socket, head-forward, and coordinate-frame diagnostics.
- Participant visibility indicators and labels.
- Ground plane and world axes.

VTK actors should be created when a recording is loaded and updated in place
during playback. Routine frame changes should update actor transforms, points,
colors, visibility, and labels rather than reconstructing the scene.

### Numeric computation and cached data

**NumPy** arrays will be the standard in-memory representation for motion,
derived geometry, per-frame validity, visibility states, and timestamps.

The analysis layer must not depend on PySide6, PyVista, or VTK. Given numeric
inputs and a parameter set, it will return numeric results. This separation is
required so that geometric behavior can be tested deterministically and used
later in a headless batch-analysis workflow.

## Architectural Boundaries

The application is divided into five primary layers:

```text
User interface
    │
    ├── controls playback, parameters, selection, and exports
    ▼
Application controller
    │
    ├── coordinates state, workers, caching, and synchronization
    ├───────────────┬──────────────────┐
    ▼               ▼                  ▼
Data layer     Analysis engine     Rendering layer
    │               │                  │
    └───────────────┴──────────────────┘
                    ▼
               Export layer
```

### Data layer

The data layer discovers recordings, reads source data, validates paired
frames, transforms motion into a shared coordinate system, and reads or writes
derived caches.

The source dataset is an input only. No cache, index, log, lock file,
thumbnail, export, or temporary file may be written inside `egobody-data`.

### Analysis engine

The analysis engine owns the mathematical definition of potential visibility:

- Head and glasses coordinate frames.
- Eye-socket positions.
- Waveguide rectangles and chief-ray directions.
- Rectangular-frustum construction and containment.
- Receiver head-orientation checks.
- Maximum-distance and valid-data checks.
- Per-eye and bidirectional visibility states.
- Event detection and duration-weighted summary statistics.

It is the single source of truth for participant visibility. Rendering code
must not independently reproduce or redefine scoring logic.

Render-camera containment is also geometric analysis, but it is transient and
unscored. It may be evaluated once per rendered frame from the current VTK
camera position.

### Rendering layer

The rendering layer converts application state and analysis results into VTK
actors. It owns visual presentation but not scoring decisions.

The renderer will expose operations such as:

- Load or clear a recording scene.
- Set the current motion frame.
- Update glasses and frustum parameters.
- Apply current visibility states.
- Toggle diagnostic actors.
- Query or set camera presets.
- Capture the viewport.

### User interface layer

The UI displays state and forwards user intent to the controller. Widgets
should not directly load dataset files, calculate visibility, or modify VTK
actors outside the viewport abstraction.

The visibility timeline will be a custom Qt widget backed by precomputed arrays
of per-frame or per-interval states. It will support a playhead, scrubbing, and
distinct representations for invisible, one-eye, and two-eye visibility.

### Export layer

The export layer will support:

- Still-image capture from the 3D viewport.
- Numbered rendered frames for a selected playback interval.
- Optional direct MP4 creation through FFmpeg when available.

Frame-sequence export is the reliable baseline. FFmpeg should be invoked as a
separate process rather than embedded into the analysis or rendering layers.

## Proposed Package Structure

The precise names may evolve, but dependencies should follow these boundaries:

```text
src/eyeglow_egobody/
    __main__.py
    app.py

    model/
        parameters.py
        recording.py
        results.py
        state.py

    egobody/
        discovery.py
        loading.py
        transforms.py
        validation.py
        cache.py

    analysis/
        coordinate_frames.py
        head_pose.py
        frustum.py
        visibility.py
        events.py
        scores.py

    rendering/
        viewport.py
        scene.py
        skeleton_actor.py
        glasses_actor.py
        frustum_actor.py
        diagnostics.py

    ui/
        main_window.py
        recording_browser.py
        parameter_panel.py
        playback_controls.py
        timeline.py
        score_panel.py

    export/
        screenshot.py
        animation.py

    resources/
        icons/
        models/

tests/
    unit/
    integration/
    fixtures/
```

Core model and analysis modules must remain importable without starting a Qt
application or creating a VTK render window.

## Data Representations

A loaded recording should be normalized into contiguous arrays. A representative
shape convention is:

```text
timestamps                  (frames,)
valid                       (frames,)
joint_positions             (participants, frames, joints, 3)
head_transforms             (participants, frames, 4, 4)
eye_socket_positions        (participants, frames, eyes, 3)
glasses_transforms          (participants, frames, 4, 4)
visibility_state            (directions, frames)
```

World coordinates and physical dimensions will use meters. Angles exposed in
the UI may use degrees, but lower-level geometry functions must clearly specify
their expected units and should use radians internally where practical.

Visibility states should use a small explicit enumeration rather than several
loosely related booleans:

```text
INVALID
NONE
LEFT_EYE
RIGHT_EYE
BOTH_EYES
```

Source-derived values and approximations must be distinguishable in metadata.
In particular, approximated eye-socket offsets must not be labeled as measured
eye positions.

## Data and Cache Flow

```text
egobody-data (read-only)
        │
        ▼
recording discovery and validation
        │
        ▼
normalization into shared coordinates
        │
        ├──► cache under code-repo
        ▼
compact NumPy recording model
        │
        ├──► current-frame renderer
        └──► vectorized visibility analysis
                       │
                       ├──► timeline and scores
                       └──► parameter-dependent cache
```

Caches must carry enough version information to be invalidated when their
source files, transformation rules, array schema, or relevant parameters
change. Cache failure must fall back to rebuilding derived data; it must never
lead to modifying the source dataset.

## Playback and Responsiveness

The Qt event loop must never perform long dataset reads, full-recording
preprocessing, or expensive exports synchronously.

- A Qt timer will advance playback according to recording timestamps and the
  selected playback rate.
- Current-frame rendering should remain on the GUI thread because Qt and VTK
  objects are generally GUI-thread-bound.
- Loading, preprocessing, whole-recording analysis, and export orchestration
  will run in workers.
- Workers will exchange plain Python data and NumPy arrays with the controller;
  they will not mutate UI widgets or live VTK actors.
- Parameter changes should be debounced to avoid launching a complete analysis
  for every intermediate slider event.
- The current frame may update immediately while full timeline and score
  recalculation completes in the background.
- Results from superseded worker requests must be discarded using a request or
  generation identifier.

The analysis should operate on complete arrays where possible instead of using
a Python loop per frame. If timestamps are irregular, score calculations must
weight valid intervals by elapsed duration.

## Shared State and Synchronization

The application controller owns the authoritative session state:

- Selected recording.
- Current frame and playback status.
- Playback rate and loop setting.
- Shared optical parameters.
- Current visibility results and scores.
- Render and diagnostic toggles.
- Active background operations.

Playback controls, the playhead, frame labels, participant indicators, scores,
and the 3D scene must all derive from this state. This avoids feedback loops
between widgets and keeps scrubbing, stepping, playback, and export behavior
consistent.

## Testing Strategy

### Unit tests

Unit tests will cover at least:

- Chief-ray construction from pitch and yaw.
- Frustum planes and point-containment edge cases.
- Left, right, and binocular activation.
- Head-facing-angle thresholds.
- Valid and invalid frame handling.
- Per-eye state reduction.
- Uniform and irregular timestamp scoring.
- Event boundaries, counts, and longest duration.
- Cache versioning and path selection.

Synthetic geometric fixtures should be preferred over dataset-dependent tests
for mathematical correctness.

### Integration tests

Integration tests will cover:

- Discovery and loading of a small representative recording fixture.
- Shared-coordinate normalization.
- Synchronization of playback state, timeline, and scene state.
- Screenshot creation.
- An off-screen rendering smoke test where supported.
- Launching a packaged application on a clean target environment.

Visual rendering tests should supplement, not replace, numeric tests of the
visibility engine.

## Packaging and Distribution

The application will be frozen so users do not need to install Python or its
dependencies.

The initial packaging strategy is **PyInstaller in one-folder mode**. One-folder
mode is preferred during development because native-library and Qt/VTK plugin
problems are easier to inspect, and it avoids extraction overhead on startup.

`pyside6-deploy`, which uses Nuitka, may be evaluated after the dependency set
and application behavior are stable. A single-file executable is not an MVP
requirement; reliability is more important than reducing the distribution to
one file.

Build outputs are platform-specific and must be produced and tested on their
target operating systems:

- Windows: an application directory containing an `.exe`.
- macOS: an `.app` bundle, optionally distributed in a `.dmg`.
- Linux: an application directory initially, with AppImage or distribution
  packages considered later.

Automated CI may build all three platforms using separate native runners.
Code-signing, notarization, polished installers, automatic updates, and broad
Linux distribution compatibility remain post-MVP concerns as specified in
`INTENT.md`.

The frozen application may be large because Qt and VTK include native runtime
libraries. Distribution size is secondary to reproducibility and correct
rendering.

## Filesystem Policy

`egobody-data` is strictly read-only. The application must not create, modify,
move, rename, or delete anything within it.

During development, derived files will be written beneath `code-repo` in
ignored runtime directories such as:

```text
code-repo/.runtime/cache/
code-repo/.runtime/logs/
code-repo/exports/
```

For an installed application, writable files should use the operating system's
standard per-user application-data, cache, log, and document locations through
Qt's standard-path APIs. No implementation should assume that its installation
directory is writable.

## Initial Technical Spike

Before building the complete interface, a vertical prototype will verify:

1. A PyVistaQt viewport embedded in a PySide6 main window.
2. Two animated synthetic skeletons with head-locked translucent frustums.
3. Orbit, pan, zoom, camera reset, and fit-to-participants behavior.
4. A Qt parameter control that updates rendered geometry.
5. In-place actor updates at an acceptable playback rate.
6. Screenshot and short frame-sequence export.
7. A PyInstaller one-folder build that launches outside the development
   environment.

Packaging should be exercised early on every target platform available to the
project. This spike is complete when it demonstrates the architecture; it does
not need to read EgoBody data or implement final visibility scoring.

## Deferred Decisions

The following choices do not need to be fixed before the technical spike:

- Exact dependency versions and lockfile tooling.
- PyInstaller versus Nuitka for final releases.
- Final installer and Linux package formats.
- Direct MP4 encoding versus frame-sequence-only export for the MVP.
- Inclusion of full SMPL-X body meshes.
- Code signing, notarization, and automatic updates.

These decisions must not weaken dataset protection, analysis/rendering
separation, or the ability to build natively on all three target platforms.
