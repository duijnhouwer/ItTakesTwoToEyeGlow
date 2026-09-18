"""Opt into bundled Adwaita shadows on GNOME/Wayland only."""
import os
from pathlib import Path
import platform
import sys


def configure_window_decoration():
    """Call before QApplication; other desktops retain their native decoration."""
    if not sys.platform.startswith('linux'):
        return False
    if 'gnome' not in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':'):
        return False
    backend = os.environ.get('QT_QPA_PLATFORM', '').split(':', 1)[0]
    if backend and not backend.startswith('wayland'):
        return False
    if not backend and os.environ.get('XDG_SESSION_TYPE') != 'wayland':
        return False
    if 'QT_WAYLAND_DECORATION' in os.environ or os.environ.get('QT_WAYLAND_DISABLE_WINDOWDECORATION'):
        return False
    from PySide6.QtCore import QCoreApplication, qVersion
    root = (Path(__file__).resolve().parents[1] / 'resources' / 'qt_plugins'
            / qVersion() / f'linux-{platform.machine()}')
    if not (root / 'wayland-decoration-client' / 'libqadwaitadecorations.so').is_file():
        return False
    # Resolve the plugin's SVG dependency from this PySide installation, without
    # embedding SDK paths or changing the process-wide dynamic linker search.
    from PySide6 import QtSvg  # noqa: F401
    QCoreApplication.addLibraryPath(str(root))
    os.environ['QT_WAYLAND_DECORATION'] = 'qadwaitadecorations'
    return True
