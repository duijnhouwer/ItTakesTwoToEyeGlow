# Phase 1 validation

## Status

Implementation is ready for joint hands-on review. Phase 2 has not started.
Automated tests and a native Linux one-folder build have passed. The project
owner has not yet signed off on the interaction or deployment gate.

## Tested baseline

- Ubuntu 26.04.1 LTS, x86_64; kernel 7.0.0-31-generic, glibc 2.43.
- Python 3.12.14, using the available bundled interpreter to create `.venv`.
- NVIDIA GeForce RTX 3080 Ti, NVIDIA 595.91.07, desktop OpenGL 3.2.
- Native Wayland desktop. Display access requires running outside the agent's
  filesystem/network sandbox; no application workaround is required.
- NumPy 2.5.3, PySide6 Essentials 6.11.2, PyVista 0.49.0, PyVistaQt 0.13.1,
  VTK 9.7.0, PyInstaller 6.22.3. Every resolved dependency is pinned in
  `requirements-lock.txt`; Qt Essentials provides the required PySide6 modules
  without the unused Qt Addons distribution.

## Build and launch

From the repository root:

```bash
PYINSTALLER_CONFIG_DIR="$PWD/.runtime/pyinstaller" MPLCONFIGDIR="$PWD/.runtime/matplotlib" QT_API=pyside6 .venv/bin/python -m PyInstaller --clean --noconfirm eyeglow.spec
```

The executable is `dist/EyeGlowEgoBody/EyeGlowEgoBody`. The complete one-folder
bundle is approximately 838 MB. To reproduce the standalone check, use its
absolute path from `/tmp`, without an activated environment:

```bash
env -u VIRTUAL_ENV -u PYTHONPATH -u PYTHONHOME /absolute/path/to/dist/EyeGlowEgoBody/EyeGlowEgoBody --smoke-test --output-dir /absolute/path/to/code-repo/.runtime/package-smoke
```

The tested executable embeds Python and its application dependencies. This is a
same-machine standalone test, not a claim of compatibility with older Linux
releases or a separate clean machine.

## Checks performed

- 13 unit/integration tests passed: GUI-free model imports, deterministic head
  transforms, elapsed-time playback at four rates, loop/end behavior, dataset and
  symlink output rejection, collision-safe paths, PNG writing, overwrite refusal,
  export cancellation, write-error recovery, and session locking during export.
- Source and frozen GUI smoke tests exercised 240 timer samples across 0.25×,
  0.5×, 1× and 2× playback, scrubbing, camera orbit/elevation/zoom/reset/fit, live
  spread updates, and stable identity of all eight participant actors.
- Each smoke test wrote one screenshot and 60 numbered PNGs, verified nonempty
  image content and changing motion, and restored the initial playback position.
- Viewed the exported viewport and full-window capture to check labels, geometry,
  controls, and caption contrast.
- `pip check` and `git diff --check` passed.
- A before/after read-only metadata snapshot covered 1,027,826 dataset entries;
  names, modes, sizes, and modification times matched. Metadata SHA-256:
  `fedc644f9d7f549b1be031aacd2dc662a592083e31c657560b5b3c189fe3dfa2`.
  This is a metadata audit, not a full content hash of the dataset.
- A `strace -f -e trace=%file` trace of the packaged smoke test contained no
  `egobody-data` access. Unit tests use temporary fake dataset directories only.

## Rendering findings

The first implementation used pipe characters in the dynamic viewport caption.
VTK interpreted these as MathText/table syntax, repeatedly invoking Matplotlib
font processing and growing memory. Plain caption text resolved this problem.
Playback requests coalesced Qt paints rather than forcing duplicate immediate
renders. Export explicitly renders before capture to preserve frame accuracy.
Multisample antialiasing is disabled in this prototype.

The final source test recorded a 66 ms 95th-percentile interval for a nominal
50 ms GUI heartbeat, a maximum interval of 82 ms across playback/export, and
64 KB resident-memory growth over the second half of playback. These are event
loop measurements, not a guarantee of frame rate or proof against long-term
memory leaks. The smoke test deliberately skips display frames as necessary
while advancing playback by elapsed time.

The final frozen test passed in 14.47 seconds, with a 75 ms playback heartbeat
95th percentile, 92 ms maximum heartbeat gap, and 80 KB resident-memory growth
over the second half of playback. Its filesystem trace also contained zero
references to the development virtual environment.

Machine-readable reports, window captures, exported images, build log, and file
traces are retained in the ignored `.runtime/` directory. See `source-verified/`
and `package-verified/` for the final runs.

## Packaging warnings and limits

PyInstaller reported optional `pyvista.trame` support missing (the desktop app
uses no Trame) and Windows-only `shell32`, `ole32`, and `user32` libraries missing
on Linux. It also reported missing XCB support libraries: `libxcb-cursor`,
`libxcb-icccm`, `libxcb-image`, `libxcb-keysyms`, and `libxcb-render-util`.
The tested Wayland launch works; an X11-only deployment is not validated and
would require those system libraries. Windows and Apple Silicon builds remain
Phase 8 under the reordered plan. No real data loading, calibrated optics, visibility scores, or MP4
encoding is claimed by this spike.

## Joint hands-on review (pending)

1. Launch the source app or standalone executable.
2. Orbit, pan, zoom, reset, and fit both participants; judge whether navigation is
   understandable and responsive.
3. Play at several speeds, scrub, step both ways, and disable Loop at the end.
4. Change placeholder spread and confirm both volumes remain attached to heads.
5. Save a screenshot, export a short sequence, and try cancelling an export.
6. Review exported images and agree whether the stack is a viable foundation.

Only after this review should the Phase 1 sign-off row be approved for Phase 2.

## Export refinement requested after the initial spike

The current UI now uses native save dialogs and an inclusive two-handle video
range beneath playback. Its default is the entire recording. Screenshots save
PNG; **Export Video** saves a real H.264 MP4 at the recording frame rate using
`imageio-ffmpeg` 0.6.0's bundled FFmpeg executable. This supersedes the initial
spike's numbered-PNG-only export behavior and MP4 limitation above.

The updated 22-test suite passes, including mouse/keyboard range interaction,
range/spin-box synchronization, save-dialog filters and default suffixes,
dialog cancellation, chosen filenames, all 300 frames by default, a one-frame
range, inclusive range endpoints, video duration, overwrite protection, and
cancellation preserving an existing file, encoder failure recovery, and file-symlink
protection for the dataset. Frame staging and encoding happen
before the destination is published; temporary output is cleaned up.

Updated source and standalone smoke-test outputs are in `.runtime/export-source/`
and `.runtime/export-package/`. Each checks a selected 60-frame / two-second MP4,
decodes the video to verify changing motion, and captures the updated window.

Both updated source and standalone GUI smoke tests passed. The standalone run
completed in 14.43 seconds, exported and decoded exactly 60 frames at 30 fps
(two seconds), and recorded a 63 ms 95th-percentile playback heartbeat.

## Modal export settings revision

The range selector has been removed from the main window. Video settings now
live in a modal **Export Video ...** dialog with filename and Browse, inclusive
start/end fields and Full range, current/FHD/4K size, 1–120 FPS and a native-rate
reset, and 0–100 quality. PNG-only screenshots have no settings and default to
Pictures; MP4 defaults to Videos. Both use the recording name.

The 33-test suite passes, including settings validation, quality mapping,
modal cancellation preserving state, resize-aware current dimensions, extension
rejection, replacement confirmation, and decoding video with a custom size/FPS.
The revised GUI smoke test checks actual 1920×1080 and 3840×2160 scene renders,
restored viewport size, native-size PNG output, and a decoded 60-frame FHD video
at 24 fps (2.5 seconds). Source and packaged results are retained under
`.runtime/dialog-verified-2/` and `.runtime/dialog-package/`.
Screenshot size is snapshotted before export progress appears, with a regression
test verifying that later layout changes cannot change the saved PNG dimensions.

The revised standalone smoke test passed in 17.36 seconds. It decoded exactly
60 FHD frames at 24 fps (2.5 seconds), with a 66 ms playback-heartbeat 95th
percentile. Native-size screenshot assertions and FHD/4K capture checks passed.
