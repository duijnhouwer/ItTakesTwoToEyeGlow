import json
from types import SimpleNamespace
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QDialogButtonBox
from eyeglow_egobody.ui.activity_dialog import ActivitiesPlaylistDialog
from eyeglow_egobody.analysis.activities import ActivityCatalog
from eyeglow_egobody.model.panel_settings import SettingsSession, PanelSettings, factory_settings_path
from eyeglow_egobody.model.playlist import PLAYLIST_KEYS, PLAYLIST_FORCE_ALL_KEYS


def test_playlist_counts_current_defaults_reset_and_reopen(qt_app, tmp_path):
    path = tmp_path/'annotations.csv'
    path.write_text('recording_name,body_idx_0,frame_interval_start,frame_interval_end,body_0_des\n'
                    'r,0 male,0,60,casual_chat_clip1\n'
                    'r,1 male,0,30,dance_clip1\n')
    catalog = ActivityCatalog(path)
    info = SimpleNamespace(name='r', start=0, end=90, body_indices=(0,1))
    factory = tmp_path/'factory.json'
    factory.write_bytes(factory_settings_path().read_bytes())
    session = SettingsSession(factory, tmp_path/'settings')
    dialog = ActivitiesPlaylistDialog([info], catalog, session.current, session.save_user_defaults)
    try:
        assert dialog.status.text() == ''
        assert dialog.findChildren(QDialogButtonBox) == []
        standard = QDialogButtonBox(QDialogButtonBox.StandardButton.Save)
        assert dialog.save_defaults.icon().cacheKey() == standard.button(
            QDialogButtonBox.StandardButton.Save).icon().cacheKey()
        assert dialog.playlist.frame_count == 90
        assert all(len(pane.selected()) == 3 for pane in dialog.lists)
        assert not hasattr(dialog, 'run')
        dialog.lists[0].set_selected(['casual_chat'])
        dialog.lists[1].select_all(True)
        current = PanelSettings(session.current_path, factory).values
        assert current[PLAYLIST_FORCE_ALL_KEYS[0]] is False
        assert current[PLAYLIST_FORCE_ALL_KEYS[1]] is True
        assert len(dialog.playlist.clips) == 2
        assert dialog.playlist.duration_s == 2
        assert '2 activity pair clips' in dialog.summary.text()
        dialog.lists[1].search.setText('dance')
        assert len(dialog.lists[1].selected()) == 3
        assert PanelSettings(session.current_path, factory).values[PLAYLIST_KEYS[0]] == ['casual_chat']
        defaults = PanelSettings(session.user_default_path, factory).values
        assert defaults[PLAYLIST_KEYS[0]] == []
        assert defaults[PLAYLIST_FORCE_ALL_KEYS[0]] is True
        dialog.save_as_defaults()
        assert PanelSettings(session.user_default_path, factory).values[PLAYLIST_KEYS[0]] == ['casual_chat']
        dialog.reject()
        assert session.current.values[PLAYLIST_KEYS[0]] == ['casual_chat']
        dialog.reset_to_factory()
        assert dialog.playlist.frame_count == 90
        assert len(dialog.lists[0].selected()) == 3
        assert session.current.values[PLAYLIST_KEYS[0]] == list(catalog.labels)
        assert session.current.values[PLAYLIST_FORCE_ALL_KEYS[0]] is True
        assert PanelSettings(session.user_default_path, factory).values[PLAYLIST_KEYS[0]] == ['casual_chat']
        session.clean_close()
        reopened = SettingsSession(factory, tmp_path/'settings')
        assert reopened.current.values[PLAYLIST_KEYS[0]] == ['casual_chat']
        # Factory reset comes from the document, not a hard-coded empty list.
        document = json.loads(factory.read_text())
        document['settings']['activities_playlist'][PLAYLIST_KEYS[0]]['value'] = ['dance']
        document['settings']['activities_playlist'][PLAYLIST_FORCE_ALL_KEYS[0]]['value'] = False
        factory.write_text(json.dumps(document))
        store = PanelSettings(reopened.current_path, factory)
        dialog.store = store
        dialog.reset_to_factory()
        assert dialog.lists[0].selected() == ['dance']
    finally:
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
