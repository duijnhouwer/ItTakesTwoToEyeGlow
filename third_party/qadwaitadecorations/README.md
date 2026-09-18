# QAdwaitaDecorations for EyeGlow

Source: https://github.com/FedoraQt/QAdwaitaDecorations
Revision: `440d4b00ad388be93c2da04b4f316d847c77d6bd` (0.1.7).
License: LGPL-2.1-or-later; see LICENSE and individual source headers.
This is an Adwaita-style Qt decoration, not a GTK dependency.

Local modification: `forceRepaint()` schedules `QWindow::requestUpdate()` instead
of flushing the Wayland software backing store. This follows Qt 6.11's built-in
Adwaita implementation and avoids a fatal Wayland explicit-sync protocol error
when used with the application's OpenGL viewport. The unused backing-store
header is removed. Shadow painting is also adjusted locally: a continuous antialiased silhouette,
24-pixel shadow margins and blur radius, and reduced opacity replace the
upstream narrow blur and rectangular post-blur recoloring. This removes the
opacity step around rounded corners. Frame dimensions retain their fractional
half-pixel offsets instead of truncating them to integers, keeping the painted
frame aligned with the client area at fractional desktop scaling.

The plugin draws an external shadow for active, non-maximized, non-tiled windows.
It also supplies the title bar, window controls and resize borders. Its appearance
is Adwaita-like, not a pixel-for-pixel reproduction of a particular GTK theme.

## Rebuild

The plugin uses private Qt APIs: rebuild for **every Qt version change**.
The distributed binary targets Qt 6.11.2, Linux x86_64, and the documented
Ubuntu 26.04 baseline. It was built with GCC 15.2 and the official Qt 6.11.2 SDK.
There are no build-machine RPATHs in the binary. It links to the application's
Qt libraries plus the Linux C/C++ runtime.

Install a GCC C++ toolchain, CMake, and Wayland/OpenGL development dependencies
(or extract them locally). Obtain the matching Qt SDK with its qtbase, qtwayland,
and qtsvg components including private headers. From the repository root:

```sh
.venv/bin/python scripts/build_window_decoration.py --qt-sdk /path/to/6.11.2/gcc_64
PYINSTALLER_CONFIG_DIR="$PWD/.runtime/pyinstaller" .venv/bin/python -m PyInstaller --clean --noconfirm eyeglow.spec
```

Use repeated `--cmake-arg=-DNAME=value` arguments for local compiler/header
paths. Build output goes into `.runtime/`; the resulting plugin is copied into
`src/eyeglow_egobody/resources/qt_plugins/<Qt-version>/linux-<architecture>/`.
The Python package includes that resource; the standalone Linux build also
includes this complete source directory and license under `_internal/licenses/`.
The shared plugin is replaceable with a compatible rebuilt copy.

Activation is limited to GNOME/Wayland, respects explicit decoration/backend
overrides, and looks up the exact Qt version and CPU architecture. Other
platforms use their native decorations. If no matching plugin is available,
source launches retain Qt's default decoration. Linux x86_64 packaging fails
with a rebuild instruction rather than silently shipping a mismatched plugin.

To opt out, launch with `QT_WAYLAND_DECORATION=adwaita`.
