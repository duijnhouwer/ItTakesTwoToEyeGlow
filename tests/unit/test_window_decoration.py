import pytest
from eyeglow_egobody.ui import window_decoration as module


@pytest.mark.parametrize('system,desktop,session,backend', [
    ('darwin','GNOME','wayland',''), ('win32','GNOME','wayland',''),
    ('linux','KDE','wayland',''), ('linux','GNOME','x11',''),
    ('linux','GNOME','wayland','offscreen'), ('linux','GNOME','wayland','xcb'),
])
def test_other_platforms_keep_native_decorations(monkeypatch, system, desktop, session, backend):
    monkeypatch.setattr(module.sys, 'platform', system)
    monkeypatch.setenv('XDG_CURRENT_DESKTOP', desktop)
    monkeypatch.setenv('XDG_SESSION_TYPE', session)
    monkeypatch.setenv('QT_QPA_PLATFORM', backend)
    monkeypatch.delenv('QT_WAYLAND_DECORATION', raising=False)
    assert not module.configure_window_decoration()
    assert 'QT_WAYLAND_DECORATION' not in module.os.environ


def test_gnome_uses_matching_plugin_and_honors_override(monkeypatch):
    from PySide6.QtCore import QCoreApplication
    monkeypatch.setattr(module.sys, 'platform', 'linux')
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setenv('XDG_CURRENT_DESKTOP', 'ubuntu:GNOME')
    monkeypatch.setenv('XDG_SESSION_TYPE', 'wayland')
    monkeypatch.delenv('QT_QPA_PLATFORM', raising=False)
    monkeypatch.delenv('QT_WAYLAND_DECORATION', raising=False)
    monkeypatch.delenv('QT_WAYLAND_DISABLE_WINDOWDECORATION', raising=False)
    paths = QCoreApplication.libraryPaths()
    try:
        assert module.configure_window_decoration()
        assert module.os.environ['QT_WAYLAND_DECORATION'] == 'qadwaitadecorations'
        assert not module.configure_window_decoration()
        monkeypatch.setenv('QT_WAYLAND_DECORATION', 'adwaita')
        assert not module.configure_window_decoration()
        assert module.os.environ['QT_WAYLAND_DECORATION'] == 'adwaita'
        monkeypatch.delenv('QT_WAYLAND_DECORATION')
        monkeypatch.setattr(module.platform, 'machine', lambda: 'unsupported')
        assert not module.configure_window_decoration()
    finally:
        QCoreApplication.setLibraryPaths(paths)
