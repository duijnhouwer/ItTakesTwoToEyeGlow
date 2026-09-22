# ItTakesTwoToEyeGlow

The desktop now discovers paired EgoBody SMPL-X recordings and loads them in a
background worker for synchronized skeleton playback. Licensed SMPL-X model NPZ files are loaded by default from
`../assets/models_smplx_v1_1/models/smplx`. The dataset contains fitted motion
parameters; the separate model assets reconstruct the skeleton. Shared waveguide
geometry and current-frame potential-visibility diagnostics are available for
Phase 3 visual review. Whole-recording scores remain a later phase.

See [Phase 2 data inspection and validation](docs/PHASE2_DATA_INSPECTION.md).

## Run from source

Use Python 3.12. From this directory on Linux:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m eyeglow_egobody
```

Qt Widgets are supplied by `PySide6-Essentials`; unused Qt Addons are omitted.
The desktop requires a working display and OpenGL driver. It defaults to the
`../assets/egobody-data` directory. Supply `--model-dir /path/to/smplx-models`
(containing `SMPLX_FEMALE.npz` and `SMPLX_MALE.npz`) or use **SMPL-X model folder…**.
`EYEGLOW_MODEL_DIR` also sets the model folder. `--dataset` selects another dataset.
Choose a recording and press **Load recording**; **Diagnostics…** shows validity,
coordinates, source identity, and approximations. Caches stay under `.runtime/`.
Use `--synthetic` to run the deterministic demo without data or models. Windows and macOS deployment are Phase 9, before final polishing in Phase 10, and are not yet validated.

## Try the prototype

- Drag in the viewport for upright orbit: horizontal motion turns around world Z,
  vertical motion changes elevation, and camera roll is disabled. Shift-drag pans;
  scrolling zooms. This uses PyVista/VTK terrain-style navigation.
- Reset camera restores the initial direction; Fit participants retains direction.
- **Orbit** beside Fit participants automatically turns the camera around world Z
  through its current target, without roll. It starts enabled at **5 deg/s** and
  also runs while motion playback is paused. Untick it to stop; negative speeds
  reverse direction. Automatic orbit pauses during save dialogs and exports.
- Play/Pause, Step, Start, and the slider control the same frame state.
- Try 0.25×, 0.5×, 1×, and 2× playback; Loop controls the end-of-sequence behavior.
- **Waveguide settings…** (also File → Settings) edits both participants' shared
  expander windows, lens offsets, diagonal FOV and H/V ratio, UI-line angles,
  display mode, and maximum distance. Save updates the current scene immediately.
- **Frustums**, **UI lines**, **Local axes**, and **Eye tests** toggle inspection
  layers. **Frustum opacity** changes only presentation. Axes use red/right,
  green/forward, blue/up. There is no placeholder spread control anymore.
- **Inspect A/B** stops camera orbit and frames that person's glasses closely.
  **Fit optics** frames the full active volumes; **Fit participants** returns to
  a view of the people.
- Receiving-eye rings use green/pass, red/fail, gray/invalid. **Eye-test details**
  opens the current-frame explanation: which emitting window contains which
  receiving eye, per-pair distance, receiver FOV, and data validity.
  The summary's left/right eye names always refer to the receiving participant.
- **Synthetic review** switches to deterministic paired motion, pauses orbit,
  and opens the eye-test panel. Use Load recording to return to real motion.
- **File → Export screenshot ...** opens a PNG-only save dialog, defaulting on Linux to
  `~/Pictures/<recording-name>.png`. It captures only the scene at the current
  viewport pixel size; there are no screenshot settings.
- **File → Export video ...** opens a modal settings dialog. Its editable filename
  defaults on Linux to `~/Videos/<recording-name>.mp4`, with a **Browse ...** button.
  Only MP4 is supported; other filename extensions show an explanatory message.
- Start/end frame fields select an inclusive interval, initially the full clip.
  **Full range** restores all frames. No export-range bar appears in the main UI.
- Video frame size options are **3840 × 2160 (4K)**, **1920 × 1080 (FHD)**, and
  the current viewport pixel dimensions, sampled each time the dialog opens.
  Frames are rendered at the selected size; they are not upscaled screenshots.
  For H.264 compatibility, an odd dimension is padded by one pixel.
- Set FPS from **1 to 120**, or reset using the **data native** button. Every
  selected source frame becomes one video frame, so changing FPS changes output
  duration. The dialog shows the selected frame count and resulting duration.
- **Quality (0–100)** maps to H.264 CRF 51–0; higher values give better quality
  and larger files. The default is 90%. MP4 itself has no universal quality scale.
- Save dialogs use normal overwrite confirmation. Typing an existing video path
  directly into the settings dialog also prompts before replacement. Cancelling
  a dialog leaves playback and export selection unchanged.
- During export the camera, controls, and window size are locked; the original
  playback position and play/pause state are restored afterward. Cancel export
  discards temporary files and preserves any existing destination. A completed
  export replaces the confirmed destination only after encoding succeeds.

FFmpeg is bundled via `imageio-ffmpeg`; no separate encoder installation is needed.
Video frames stream directly into FFmpeg without intermediate PNG files.
Temporary output is removed after completion, cancellation, or failure. The synthetic prototype uses `synthetic_motion` as its recording name.
Dataset paths and symlinks into them are rejected. `--output-dir` selects the
output directory for automated smoke tests, not the interactive save dialogs.

## Linux window decoration

On GNOME/Wayland the app uses a bundled Adwaita-style decoration with an external
shadow around the active floating window. Maximized and tiled windows omit the
shadow. Other desktops and operating systems retain native decorations.
The plugin matches the exact Qt version; rebuilding instructions and its LGPL
source/license are in [third_party/qadwaitadecorations](third_party/qadwaitadecorations/README.md).
Set `QT_WAYLAND_DECORATION=adwaita` when launching to use Qt's original decoration.

## Verify and package on Linux

```bash
.venv/bin/python -m pytest
.venv/bin/python -m eyeglow_egobody --smoke-test --output-dir "$PWD/.runtime/source-smoke"
PYINSTALLER_CONFIG_DIR="$PWD/.runtime/pyinstaller" .venv/bin/python -m PyInstaller --clean --noconfirm eyeglow.spec
./dist/ItTakesTwoToEyeGlow/ItTakesTwoToEyeGlow --smoke-test --output-dir "$PWD/.runtime/package-smoke"
./dist/ItTakesTwoToEyeGlow/ItTakesTwoToEyeGlow
```

The packaged executable contains a snapshot of the Python source. Rebuild it after
source changes, especially changes to the settings format: the source app and
packaged app read the same `config/settings_panel.json`. Validate the rebuilt
executable with the packaged smoke command above before handing off a change.

### Linux application launcher

Install the packaged application in the current user's application menu with:

```bash
.venv/bin/python scripts/install_linux_launcher.py
```

The installed ItTakesTwoToEyeGlow launcher supplies the application icon and opts into
single-instance behavior. A second launcher click raises the existing window.
Direct terminal launches remain independent and may run multiple instances.

The smoke test first checks loading fit arrays with both legacy and current NumPy
pickle module names, using the bundled NumPy when run from the packaged executable.
Users do not need to install Python or NumPy separately.
It then drives the actual event loop, exercises playback speeds, scrubbing,
camera changes, live geometry, actor reuse, native-size screenshot, FHD/4K captures, and a 60-frame FHD MP4 export at 24 fps, then
exits with a machine-readable report. It is not a substitute for hands-on review.
Distribute the entire `dist/ItTakesTwoToEyeGlow/` directory, not just the executable.

See [Phase 1 validation](docs/PHASE1_VALIDATION.md) for the tested baseline and
remaining joint review. Dependencies are pinned in `requirements-lock.txt`.
The project follows [ARCHITECTURE.md](ARCHITECTURE.md),
[INTENT.md](INTENT.md), and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Implementation boundaries

`model/` contains NumPy-only normalized recordings, synthetic fixtures, and playback state. `controller.py`
owns session state; `ui/` forwards controls; `rendering/` owns persistent VTK actors;
`export/` writes screenshots and streams RGB video frames through a bounded
background worker into a separate FFmpeg process. Rendering and
capture stay on the Qt thread. `egobody/` handles read-only discovery, skeleton
reconstruction, calibration, and versioned caching without Qt/VTK dependencies.
`analysis/` reserves the later visibility phase. Placeholder optical placement is
an approximation for both real and synthetic motion.

The integration follows the upstream [PyVistaQt usage guide](https://qt.pyvista.org/usage.html)
and [PyVista packaging guidance](https://docs.pyvista.org/extras/pyinstaller).

Video encoding follows the upstream [FFmpeg image-sequence documentation](https://ffmpeg.org/ffmpeg-formats.html)
and uses the [imageio-ffmpeg bundled encoder](https://github.com/imageio/imageio-ffmpeg).

### Eye placement settings

**File → Settings ...** edits eyeball radius (default 12 mm) and eye relief
(default 13 mm). Save persists changes to `config/settings_panel.json` and updates
the current view. Cancel discards edits. The JSON also defines each setting's
friendly display name, default, minimum, maximum, and decimal precision; only
current values appear as editable fields in the dialog. Each parameter also has
a `factory_default`: **Factory Reset** restores these values in the dialog
(12 mm eyeball radius, 13 mm eye relief). Save applies and persists the reset;
Cancel discards it. Source and the current
repository-built package share this external file. Keep it with the repository.

Participant-colored spheres mark reconstructed SMPL-X eye centers, using the
configured eyeball radius. Frames use matte white Wayfarer-style rims and temples.
Skeleton line rendering, default lighting, and the translucent ground are retained,
with no Phong highlights or shadows. Placeholder lens rear planes
sit radius + relief in front of those centers along the head's forward direction
(25 mm by default). Eye centers come from fitted anatomy, not measured gaze.

### Activities playlist

Open **Recordings → Edit activities playlist ...** to select actions independently
for A (camera wearer) and B (interactee). Search either checklist and use Select
all or Clear across the full list. Both participants must match; `<undefined>`
selects unannotated time. The editor shows the matching paired clip count and
combined duration across all recordings. Selections are written immediately to
`settings_current.json` and remain active after closing the editor. **Save as new
defaults** promotes only the playlist choices to `settings_user_default.json`;
**Factory Reset** reads the playlist values from `settings_factory_default.json`
(currently neither participant has actions selected).

Play traverses the selected clips in recording-name/source-frame order, skipping
unselected time. The scrubber represents their combined duration. Recordings load
as needed; playback pauses while loading and resumes at the requested clip. An
empty playlist disables playback and analysis. Loading an individual recording
explicitly switches playback to that recording without discarding saved playlist
choices. Video export is available in individual-recording mode.

**Recordings → Analyze activities playlist ...** asks for a JSONL destination,
snapshots the complete current settings document, and processes the playlist in
the background. The viewport previews the latest analyzed frame at approximately
30 updates per second; computation runs at full speed, so displayed frames may be
skipped. Editing and playback are locked during analysis; Cancel analysis remains
available. Analysis completion leaves the viewport at the latest preview frame.
The first
JSONL record contains configuration and selection metadata. Each following record
describes one paired annotation interval, its original source annotations, and
duration-weighted potential visibility of A seeing B’s eye glow and vice versa.
Seeing at least one active glow counts as visible. Invalid pose time is excluded
from percentages and reported separately; a zero usable duration produces null.
Concurrent labels stay in one record with conflict indicators. The final motion
sample has zero duration because there is no following timestamp.

The source dataset is read-only. Cancellation or any processing error leaves the
destination unchanged; a complete result is published only after the whole batch
succeeds. Groups, occurrence thresholds, and matrix visualizations are deferred.
