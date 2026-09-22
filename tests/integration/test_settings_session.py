import json
import stat

import pytest

from eyeglow_egobody.model.panel_settings import (
    PanelSettings, SettingsSession, factory_settings_path, settings_path,
)
from eyeglow_egobody.ui.settings_dialog import SettingsEditor


@pytest.fixture
def paths(tmp_path):
    factory = tmp_path / 'settings_factory_default.json'
    factory.write_bytes(factory_settings_path().read_bytes())
    return factory, tmp_path / 'user', tmp_path / 'settings_panel.json'


def session(paths):
    factory, user_directory, legacy = paths
    return SettingsSession(factory_path=factory, user_directory=user_directory, legacy_path=legacy)


def test_fresh_install_creates_matching_user_and_current_documents(paths):
    fresh = session(paths)
    factory_values = PanelSettings(paths[0]).values
    assert fresh.recovery_pending is False
    assert fresh.current.values == factory_values
    assert PanelSettings(fresh.user_default_path, paths[0]).values == factory_values
    assert not (fresh.current_path.stat().st_mode & stat.S_IWUSR)


def test_legacy_settings_migrate_once_to_user_defaults(paths):
    factory, _, legacy = paths
    legacy.write_bytes(settings_path().read_bytes())
    old = PanelSettings(legacy)
    old.save({**old.values, 'eye_relief_mm': 18})
    migrated = session(paths)
    assert migrated.current.values['eye_relief_mm'] == 18
    migrated.save_user_defaults({'eye_relief_mm': 19})
    old.save({**old.values, 'eye_relief_mm': 20})
    migrated.clean_close()
    next_session = session(paths)
    assert next_session.current.values['eye_relief_mm'] == 19


def test_live_current_and_group_default_are_independent(paths):
    active = session(paths)
    user_before = PanelSettings(active.user_default_path, paths[0]).values
    active.current.save({**active.current.values, 'eye_relief_mm': 19})
    assert PanelSettings(active.current_path, paths[0]).values['eye_relief_mm'] == 19
    assert PanelSettings(active.user_default_path, paths[0]).values == user_before
    active.save_user_defaults({'eye_relief_mm': 19})
    defaults = PanelSettings(active.user_default_path, paths[0]).values
    assert defaults['eye_relief_mm'] == 19
    assert defaults['receiver_fov_left_deg'] == user_before['receiver_fov_left_deg']


def test_text_edits_apply_on_commit_and_save_button_promotes_only_its_group(qt_app, paths):
    active = session(paths)
    editor = SettingsEditor(active.current, ('smartglasses',),
                            save_user_defaults=active.save_user_defaults)
    field = editor.fields['eye_relief_mm']
    field.setText('19')
    field.editingFinished.emit()
    assert active.current.values['eye_relief_mm'] == 19
    assert not (active.current_path.stat().st_mode & stat.S_IWUSR)
    assert PanelSettings(active.user_default_path, paths[0]).values['eye_relief_mm'] == 13
    assert editor.save_group('smartglasses')
    assert PanelSettings(active.user_default_path, paths[0]).values['eye_relief_mm'] == 19


def test_clean_close_removes_current_and_unclean_close_offers_recovery(paths):
    active = session(paths)
    active.current.save({**active.current.values, 'eye_relief_mm': 19})
    recovered = session(paths)
    assert recovered.recovery_pending
    assert recovered.restore_recovered_settings().values['eye_relief_mm'] == 19
    recovered.clean_close()
    assert not recovered.current_path.exists()
    normal = session(paths)
    assert not normal.recovery_pending


@pytest.mark.parametrize('choice, expected', [
    ('use_user_defaults', 13.0),
    ('use_factory_defaults', 13.0),
])
def test_recovery_replacement_choices_do_not_overwrite_user_defaults(paths, choice, expected):
    active = session(paths)
    active.save_user_defaults({'eye_relief_mm': 17})
    active.current.save({**active.current.values, 'eye_relief_mm': 19})
    recovered = session(paths)
    getattr(recovered, choice)()
    # Factory selection uses bundled values; user selection uses the saved default.
    if choice == 'use_user_defaults':
        expected = 17.0
    assert recovered.current.values['eye_relief_mm'] == expected
    assert PanelSettings(recovered.user_default_path, paths[0]).values['eye_relief_mm'] == 17


def test_invalid_recovered_current_cannot_be_restored_and_cancel_preserves_it(paths):
    active = session(paths)
    active.current_path.chmod(0o644)  # Deliberately override the review-only mode.
    active.current_path.write_text(json.dumps({'not': 'settings'}))
    recovered = session(paths)
    assert recovered.recovery_pending
    assert recovered.recovery_error
    with pytest.raises(ValueError, match='unavailable'):
        recovered.restore_recovered_settings()
    # This is the state the UI leaves behind when Cancel is selected.
    assert recovered.current_path.exists()


def test_new_playlist_fields_do_not_reset_existing_optical_settings(paths):
    active = session(paths)
    active.save_user_defaults({'eye_relief_mm': 19})
    active.current.save({**active.current.values, 'eye_relief_mm': 23})
    for path in (active.user_default_path, active.current_path):
        document = json.loads(path.read_text())
        del document['settings']['activities_playlist']
        path.chmod(0o644)
        path.write_text(json.dumps(document))
    restored = session(paths)
    assert restored.restore_recovered_settings().values['eye_relief_mm'] == 23
    assert restored.current.values['playlist_actions_a'] == []
    assert restored.current.values['force_all_activities_a'] is True
    assert PanelSettings(restored.user_default_path, paths[0]).values['eye_relief_mm'] == 19


def test_new_playlist_flags_do_not_reset_existing_settings(paths):
    active = session(paths)
    active.save_user_defaults({'eye_relief_mm': 19})
    for path in (active.user_default_path, active.current_path):
        document = json.loads(path.read_text())
        group = document['settings']['activities_playlist']
        del group['force_all_activities_a']
        del group['force_all_activities_b']
        path.chmod(0o644)
        path.write_text(json.dumps(document))
    restored = session(paths)
    assert restored.restore_recovered_settings().values['force_all_activities_a'] is True
    defaults = PanelSettings(restored.user_default_path, paths[0]).values
    assert defaults['eye_relief_mm'] == 19
    assert defaults['force_all_activities_b'] is True
