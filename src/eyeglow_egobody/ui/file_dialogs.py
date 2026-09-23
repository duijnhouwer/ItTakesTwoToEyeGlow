"""Native file pickers must not compete with viewport animation."""
from contextlib import contextmanager
from time import monotonic
from PySide6.QtWidgets import QFileDialog


@contextmanager
def paused_animation(parent):
    """Find the owning controller through nested dialogs; preserve timer state."""
    owner = parent
    while owner is not None and not hasattr(owner, 'controller'):
        owner = owner.parent()
    controller = owner.controller if owner is not None else None
    running = controller is not None and controller.timer.isActive()
    if controller is not None:
        controller.timer.stop()
    try:
        yield
    finally:
        if controller is not None:
            # Time in the picker must not become a playback/orbit jump.
            controller.last = monotonic()
            if running:
                controller.timer.start()


def file_dialog(parent, operation, *args, **kwargs):
    """Run any blocking file-picker operation with animation suspended.

    `operation` may be a standard static picker or a configured dialog's exec.
    Parent must belong to the owning main window (nested dialogs are supported).
    """
    with paused_animation(parent):
        return operation(*args, **kwargs)


def save_file(parent, *args, **kwargs):
    return file_dialog(parent, QFileDialog.getSaveFileName, parent, *args, **kwargs)


def open_file(parent, *args, **kwargs):
    return file_dialog(parent, QFileDialog.getOpenFileName, parent, *args, **kwargs)


def existing_directory(parent, *args, **kwargs):
    return file_dialog(parent, QFileDialog.getExistingDirectory, parent, *args, **kwargs)
