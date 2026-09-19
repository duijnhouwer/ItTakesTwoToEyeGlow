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
    store = PanelSettings(path)
    store.save({key: spec["factory_default"] for key, spec in store.specs.items()})
    return store


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
        dialog.fields['expander_width_mm'].setText('28')
        dialog.accept()
        return dialog.result()
    monkeypatch.setattr(SettingsDialog, 'exec', save)
    window = main_window.MainWindow(tmp_path)
    window.controller.timer.stop()
    try:
        before = window.viewport.refreshes
        window.settings_action.trigger()
        assert window.viewport.optical_settings['eye_relief_mm'] == 19
        assert window.controller.optical_parameters.eye_relief_mm == 19
        assert window.controller.optical_parameters.expander_width_mm == 28
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
                               parts=[], eye_parts=[], stable_actors=[], participant_actors=[],
                               optics=SimpleNamespace(update=lambda *args, **kwargs: None), current_visibility=None,
                               show_frustums=True, show_ui_lines=True, show_axes=False, show_eye_tests=True,
                               eye_sphere=eye_sphere_source(.012), update=lambda: None,
                               caption=SimpleNamespace(SetText=lambda *args: None))
    for p in range(2):
        actors = [vtkActor() for _ in range(5)]
        viewport.participant_actors.append(actors)
        viewport.stable_actors.extend(actors)
        viewport.parts.append((pv.PolyData(np.zeros((16,3))),pv.PolyData(np.zeros((GLASSES_POINT_COUNT,3))),
                               actors[2]))
        viewport.eye_parts.append((pv.PolyData(np.zeros((2,3))),
                                   ((pv.PolyData(np.zeros((1,3))), actors[3]),
                                    (pv.PolyData(np.zeros((1,3))), actors[4]))))
    actors = tuple(viewport.stable_actors)
    Viewport.set_frame(viewport, 120, .35)
    for p in range(2):
        eyes, eye_parts = viewport.eye_parts[p]
        np.testing.assert_allclose(eyes.points, recording.eyes[p,120])
        for eye, (eye_mesh, eye_actor) in enumerate(eye_parts):
            np.testing.assert_allclose(eye_mesh.points, recording.eyes[p,120,eye:eye + 1])
            assert eye_actor.GetVisibility()
    recording.valid[0,120] = False
    Viewport.set_frame(viewport, 120, .35)
    assert all(not a.GetVisibility() for a in actors[:5])
    assert all(a.GetVisibility() for a in actors[5:])
    recording.valid[0,120] = True
    Viewport.set_frame(viewport, 120, .35)
    assert all(a.GetVisibility() for a in actors)
    assert tuple(viewport.stable_actors) == actors


@pytest.mark.parametrize('save', [False, True])
def test_factory_reset_is_staged_until_saved(qt_app, store, save):
    store.save({**store.values, 'eyeball_radius_mm':30, 'eye_relief_mm':20})
    before = store.path.read_bytes()
    dialog = SettingsDialog(store)
    dialog.fields['eye_relief_mm'].setText('invalid')
    dialog.accept()
    assert dialog.error.text()
    dialog.factory_reset.click()
    assert not dialog.error.text()
    assert dialog.fields['eyeball_radius_mm'].text() == '12.0'
    assert dialog.fields['eye_relief_mm'].text() == '13.0'
    assert store.path.read_bytes() == before
    assert dialog.result() == QDialog.DialogCode.Rejected
    if save:
        dialog.accept()
        loaded = PanelSettings(store.path)
        assert loaded.values == {key: spec['factory_default'] for key, spec in loaded.specs.items()}
        assert loaded.document['settings']['eyeball_radius_mm']['factory_default'] == 12
    else:
        dialog.reject()
        assert store.path.read_bytes() == before


def test_factory_defaults_are_validated_and_distinct_from_default(qt_app, store):
    document = json.loads(store.path.read_text())
    document['settings']['eye_relief_mm']['default'] = 16
    document['settings']['eye_relief_mm']['factory_default'] = 14.5
    store.path.write_text(json.dumps(document))
    dialog = SettingsDialog(PanelSettings(store.path))
    dialog.factory_reset.click()
    assert dialog.fields['eye_relief_mm'].text() == '14.5'
    document['settings']['eye_relief_mm']['factory_default'] = 101
    store.path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='between'):
        PanelSettings(store.path)


def test_waveguide_group_edits_persist_and_derive_fov(qt_app, store):
    from PySide6.QtWidgets import QGroupBox
    dialog = SettingsDialog(store)
    assert dialog.findChild(QGroupBox, 'smartglasses').title() == 'Smartglasses'
    changes = dict(expander_width_mm='24.5', expander_height_mm='18',
                   expander_offset_right_mm='-2', expander_offset_up_mm='3',
                   diagonal_fov_deg='30', horizontal_vertical_fov_ratio='2',
                   ui_line_azimuth_deg='5', ui_line_elevation_deg='-4',
                   maximum_distance_m='4', display_mode='monocular_left')
    for key, value in changes.items():
        field = dialog.fields[key]
        if hasattr(field, 'setCurrentIndex'):
            field.setCurrentIndex(field.findData(value))
        else:
            field.setText(value)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    loaded = PanelSettings(store.path)
    p = loaded.optical_parameters
    assert p.horizontal_fov / p.vertical_fov == pytest.approx(2)
    assert p.active_eyes == (True, False)
    assert p.expander_width_mm == 24.5
    assert p.ui_line_elevation_deg == -4
    for key in changes:
        assert loaded.document['settings']['smartglasses'][key]['value'] == loaded.values[key]
    dialog = SettingsDialog(loaded)
    dialog.factory_reset.click()
    dialog.accept()
    assert loaded.optical_parameters.expander_width_mm == 20
    assert loaded.optical_parameters.diagonal_fov_deg == 20
    assert loaded.optical_parameters.horizontal_vertical_fov_ratio == 1
    assert loaded.optical_parameters.display_mode == 'monocular_right'


@pytest.mark.parametrize('key,value', [('expander_width_mm','0'),('diagonal_fov_deg','180'),
    ('horizontal_vertical_fov_ratio','1:1'),('horizontal_vertical_fov_ratio','0'),
    ('ui_line_elevation_deg','89')])
def test_waveguide_invalid_edits_are_atomic(qt_app, store, key, value):
    before = store.path.read_bytes()
    dialog = SettingsDialog(store)
    dialog.fields[key].setText(value)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.error.text()
    assert store.path.read_bytes() == before


def test_json_metadata_cannot_override_physical_validation(store):
    document = json.loads(store.path.read_text())
    spec = document['settings']['smartglasses']['diagonal_fov_deg']
    spec['max'] = 360
    spec['value'] = 200
    store.path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='diagonal_fov'):
        PanelSettings(store.path)


def test_smartglasses_and_visualization_controls_persist(qt_app, store):
    from PySide6.QtWidgets import QCheckBox, QComboBox, QGroupBox, QPushButton
    dialog = SettingsDialog(store)
    assert dialog.findChild(QGroupBox, 'smartglasses').title() == 'Smartglasses'
    assert dialog.findChild(QGroupBox, 'visualization').title() == 'Visualization'
    mode = dialog.fields['display_mode']
    assert isinstance(mode, QComboBox)
    assert [mode.itemText(i) for i in range(mode.count())] == ['Binocular', 'Mono left', 'Mono right']
    assert mode.currentText() == 'Mono right'
    assert isinstance(dialog.fields['eye_glow_color'], QPushButton)
    assert isinstance(dialog.fields['subject_a_label_visible'], QCheckBox)
    mode.setCurrentIndex(mode.findData('binocular'))
    dialog._set_color_button(dialog.fields['eye_glow_color'], '#123456')
    dialog.fields['subject_a_label'].setText('Lead')
    dialog.fields['subject_a_label_visible'].setChecked(False)
    dialog.accept()
    values = PanelSettings(store.path).values
    assert values['display_mode'] == 'binocular'
    assert values['eye_glow_color'] == '#123456'
    assert values['subject_a_label'] == 'Lead'
    assert values['subject_a_label_visible'] is False
