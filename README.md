# EyeGlow EgoBody

Phase 1 is a Python desktop technical spike: two synthetic participants, head-locked
placeholder glasses/frustums, playback, camera navigation, screenshot saving, and MP4 video export.
**It does not load EgoBody recordings or calculate visibility.**

## Run from source

Use Python 3.12. From this directory on Linux:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m eyeglow_egobody
```

Qt Widgets are supplied by `PySide6-Essentials`; unused Qt Addons are omitted.
The desktop requires a working display and OpenGL driver. No dataset or model
assets are required. Windows and macOS deployment are Phase 2, not yet validated.

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
- Change **Placeholder spread** to update both head-locked volumes immediately.
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
./dist/EyeGlowEgoBody/EyeGlowEgoBody --smoke-test --output-dir "$PWD/.runtime/package-smoke"
./dist/EyeGlowEgoBody/EyeGlowEgoBody
```

The smoke test drives the actual event loop, exercises playback speeds, scrubbing,
camera changes, live geometry, actor reuse, native-size screenshot, FHD/4K captures, and a 60-frame FHD MP4 export at 24 fps, then
exits with a machine-readable report. It is not a substitute for hands-on review.
Distribute the entire `dist/EyeGlowEgoBody/` directory, not just the executable.

See [Phase 1 validation](docs/PHASE1_VALIDATION.md) for the tested baseline and
remaining joint review. Dependencies are pinned in `requirements-lock.txt`.
The project follows [ARCHITECTURE.md](ARCHITECTURE.md),
[INTENT.md](INTENT.md), and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Implementation boundaries

`model/` contains NumPy-only synthetic motion and playback state. `controller.py`
owns session state; `ui/` forwards controls; `rendering/` owns persistent VTK actors;
`export/` writes screenshots and streams RGB video frames through a bounded
background worker into a separate FFmpeg process. Rendering and
capture stay on the Qt thread. `analysis/` and `egobody/` reserve the later-phase
package boundaries. All synthetic head frames and shapes are approximations.

The integration follows the upstream [PyVistaQt usage guide](https://qt.pyvista.org/usage.html)
and [PyVista packaging guidance](https://docs.pyvista.org/extras/pyinstaller).

Video encoding follows the upstream [FFmpeg image-sequence documentation](https://ffmpeg.org/ffmpeg-formats.html)
and uses the [imageio-ffmpeg bundled encoder](https://github.com/imageio/imageio-ffmpeg).
