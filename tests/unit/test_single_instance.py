from PySide6.QtCore import QCoreApplication

from eyeglow_egobody.ui.single_instance import SingleInstance


class FakeHandle:
    def __init__(self):
        self.activations = 0

    def requestActivate(self):
        self.activations += 1


class FakeWindow:
    def __init__(self):
        self.shown = self.raised = self.activated = 0
        self.handle = FakeHandle()

    def isMinimized(self):
        return False

    def show(self):
        self.shown += 1

    def raise_(self):
        self.raised += 1

    def activateWindow(self):
        self.activated += 1

    def windowHandle(self):
        return self.handle


def test_desktop_activation_raises_existing_window(qt_app):
    primary = SingleInstance('eyeglow-test')
    window = FakeWindow()
    try:
        primary.set_window(window)
        primary._activate('')
        for _ in range(5):
            QCoreApplication.processEvents()
        assert (window.shown, window.raised, window.activated) == (1, 1, 1)
        assert window.handle.activations == 1
    finally:
        primary.close()


def test_existing_endpoint_makes_process_a_secondary(qt_app, monkeypatch):
    instance = SingleInstance('eyeglow-test-secondary')
    try:
        monkeypatch.setattr(instance, '_notify_existing', lambda timeout_ms=100: True)
        assert not instance.start()
    finally:
        instance.close()
