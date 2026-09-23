"""Native two-recording playlist integration review with real motion and exports."""
from pathlib import Path
import json
import sys
from time import monotonic
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from eyeglow_egobody.runtime_paths import default_dataset, default_models
from eyeglow_egobody.model.panel_settings import SettingsSession, factory_settings_path
from eyeglow_egobody.model.playlist import PLAYLIST_KEYS
from eyeglow_egobody.egobody.discovery import discover
from eyeglow_egobody.ui.main_window import MainWindow
from eyeglow_egobody.ui.activity_dialog import ActivitiesPlaylistDialog
from eyeglow_egobody.ui.window_decoration import configure_window_decoration


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    configure_window_decoration()
    app = QApplication([])
    session = SettingsSession(factory_settings_path(), output/'settings')
    if session.recovery_pending:
        session.use_factory_defaults()
    window = MainWindow(output, settings_session=session)
    window.dataset = default_dataset()
    window.infos = discover(window.dataset)[:2]
    window.ensure_activity_catalog()
    editor = ActivitiesPlaylistDialog(window.infos, window.activity_catalog, session.current,
                                       session.save_user_defaults, window)
    for pane in editor.lists:
        pane.select_all(True)
    assert all(session.current.values[k] for k in PLAYLIST_KEYS)
    editor.show()
    window.show()
    step = 0
    start = monotonic()
    initial_frame = None
    target = None

    def tick():
        nonlocal step, initial_frame, target
        try:
            assert monotonic()-start < 120, 'Playlist review timed out'
            c = window.controller
            if step == 0:
                editor.grab().save(str(output/'selector.png'))
                editor.close()
                window.apply_activities_playlist()
                step = 1
            elif step == 1 and c.loading is None:
                assert c.playlist.frame_count > 0
                c.toggle()
                initial_frame = c.state.frame
                step = 2
            elif step == 2 and c.state.frame > initial_frame:
                c.state.playing = False
                second = next(clip for clip in c.playlist.clips if clip.info.name == window.infos[1].name)
                target = second.offset
                c.seek(target)
                step = 3
            elif step == 3 and c.loading is None:
                assert c.recording.name == window.infos[1].name
                assert c.state.frame == target
                window.visualization_dock.show()
                window.recordings_dock.show()
                window.grab().save(str(output/'playlist.png'))
                window.playlist_analysis.start(window.infos, window.activity_catalog,
                    window.activities_playlist, session.current.document, default_models(),
                    output/'analysis.jsonl', overwrite=True)
                step = 4
            elif step == 4 and not window.playlist_analysis.busy:
                assert window.playlist_analysis.message.startswith('Saved'), window.playlist_analysis.message
                rows = [json.loads(line) for line in (output/'analysis.jsonl').read_text().splitlines()]
                assert len(rows)-1 == len(window.activities_playlist.clips)
                assert abs(sum(r['selected_duration_s'] for r in rows[1:])-window.activities_playlist.duration_s) < 1e-8
                window.grab().save(str(output/'analysis.png'))
                print(json.dumps(dict(result='passed', clips=len(rows)-1,
                                      duration_s=window.activities_playlist.duration_s)))
                timer.stop()
                window.close()
                app.quit()
        except Exception:
            import traceback
            traceback.print_exc()
            timer.stop()
            window.close()
            app.exit(1)
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(150)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
