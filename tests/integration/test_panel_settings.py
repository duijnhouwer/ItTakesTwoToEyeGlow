import json
import numpy as np
import pytest
from PySide6.QtWidgets import QDialog
from eyeglow_egobody.model.panel_settings import PanelSettings, settings_path
from eyeglow_egobody.model.glasses import glasses_points, GLASSES_POINT_COUNT, REAR_RIM_INDICES
from eyeglow_egobody.ui.settings_dialog import SettingsDialog


@pytest.fixture
def store(tmp_path):
    path = tmp_path/'settings_panel.json'
    path.write_bytes(settings_path().read_bytes())
    return PanelSettings(path)


def test_settings_dialog_persists_values_and_preserves_metadata(qt_app, store):
    dialog = SettingsDialog(store)
    original = json.loads(store.path.read_text())
    dialog.fields['eye_relief_mm'].setText('17.5')
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert PanelSettings(store.path).values['eye_relief_mm'] == 17.5
    assert store.document['settings']['eye_relief_mm']['default'] == 13
    original['settings']['eye_relief_mm']['value'] = 17.5
    assert json.loads(store.path.read_text()) == original


@pytest.mark.parametrize('text', ['nan', 'inf', 'abc', '', '-1', '101', '13.123'])
def test_settings_invalid_input_leaves_file_unchanged(qt_app, store, text):
    before = store.path.read_bytes()
    dialog = SettingsDialog(store)
    dialog.fields['eye_relief_mm'].setText(text)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.error.text()
    assert store.path.read_bytes() == before


def test_cancel_and_write_failure_leave_settings_unchanged(qt_app, store, monkeypatch):
    from eyeglow_egobody.model import panel_settings
    before = store.path.read_bytes()
    dialog = SettingsDialog(store)
    dialog.fields['eye_relief_mm'].setText('20')
    dialog.reject()
    assert store.path.read_bytes() == before
    dialog = SettingsDialog(store)
    dialog.fields['eye_relief_mm'].setText('20')
    monkeypatch.setattr(panel_settings.os, 'replace', lambda *args: (_ for _ in ()).throw(OSError('full')))
    dialog.accept()
    assert 'Could not save' in dialog.error.text()
    assert store.values['eye_relief_mm'] == 13
    assert store.path.read_bytes() == before


def test_rear_lens_vertex_clearance_in_rotated_world_coordinates():
    from eyeglow_egobody.egobody.skeleton import rotations
    rotation = rotations(np.array([.4, -.7, 1.2]))
    eyes = np.array([[-.03,.08,.02],[.03,.08,.02]]) @ rotation.T + [1,2,3]
    points = glasses_points(eyes, rotation, 12, 13)
    for eye, rim in zip(eyes, (points[REAR_RIM_INDICES[0]],points[REAR_RIM_INDICES[1]])):
        np.testing.assert_allclose((rim-eye) @ rotation[:,1], .025, atol=1e-12)
    updated = glasses_points(eyes, rotation, 14, 18)
    np.testing.assert_allclose(updated-points, np.tile(rotation[:,1]*.007,(GLASSES_POINT_COUNT,1)), atol=1e-12)


def test_file_settings_updates_current_view(qt_app, store, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QWidget
    from eyeglow_egobody.ui import main_window
    class Viewport(QWidget):
        def __init__(self, parent, recording):
            super().__init__(parent)
            self.interactor = self
            self.refreshes = 0
        def reset_view(self): pass
        def fit_participants(self): pass
        def set_frame(self, *args): self.refreshes += 1
    monkeypatch.setattr(main_window, 'Viewport', Viewport)
    monkeypatch.setattr(main_window, 'PanelSettings', lambda *args: store)
    def save(dialog):
        dialog.fields['eye_relief_mm'].setText('19')
        dialog.accept()
        return dialog.result()
    monkeypatch.setattr(SettingsDialog, 'exec', save)
    window = main_window.MainWindow(tmp_path)
    window.controller.timer.stop()
    try:
        before = window.viewport.refreshes
        window.settings_action.trigger()
        assert window.viewport.optical_settings['eye_relief_mm'] == 19
        assert window.viewport.refreshes == before+1
        assert PanelSettings(store.path).values['eye_relief_mm'] == 19
    finally:
        window.close()


def test_renderer_updates_and_hides_eye_actors_without_recreating_them():
    from types import SimpleNamespace
    import pyvista as pv
    from vtkmodules.vtkRenderingCore import vtkActor
    from eyeglow_egobody.rendering.viewport import Viewport
    from eyeglow_egobody.model.recording import synthetic_recording
    recording = synthetic_recording()
    from eyeglow_egobody.rendering.materials import eye_sphere_source
    viewport = SimpleNamespace(recording=recording, optical_settings=dict(eyeball_radius_mm=12, eye_relief_mm=13),
                               parts=[], eye_parts=[], stable_actors=[], eye_sphere=eye_sphere_source(.012), update=lambda: None,
                               caption=SimpleNamespace(SetText=lambda *args: None))
    for p in range(2):
        actors = [vtkActor() for _ in range(5)]
        viewport.stable_actors.extend(actors)
        viewport.parts.append((pv.PolyData(np.zeros((16,3))),pv.PolyData(np.zeros((GLASSES_POINT_COUNT,3))),
                               pv.PolyData(np.zeros((8,3))),actors[3]))
        viewport.eye_parts.append((pv.PolyData(np.zeros((2,3))),actors[4]))
    actors = tuple(viewport.stable_actors)
    Viewport.set_frame(viewport, 120, .35)
    for p in range(2):
        np.testing.assert_allclose(viewport.eye_parts[p][0].points, recording.eyes[p,120])
        assert viewport.eye_parts[p][1].GetVisibility()
    recording.valid[0,120] = False
    Viewport.set_frame(viewport, 120, .35)
    assert all(not a.GetVisibility() for a in actors[:5])
    assert all(a.GetVisibility() for a in actors[5:])
    recording.valid[0,120] = True
    Viewport.set_frame(viewport, 120, .35)
    assert all(a.GetVisibility() for a in actors)
    assert tuple(viewport.stable_actors) == actors
