from concurrent.futures import Future, CancelledError
from types import SimpleNamespace
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QFileDialog
from eyeglow_egobody.ui.activity_dialog import ActivityAnalysisDialog


def test_lists_save_cancel_snapshot_progress(qt_app, monkeypatch, tmp_path):
    catalog = SimpleNamespace(labels=('<undefined>', 'casual_chat', 'dance'))
    settings = {'value': 1}
    infos = [object(), object()]
    dialog = ActivityAnalysisDialog(infos, catalog, lambda: settings, tmp_path)
    assert not dialog.run.isEnabled()
    dialog.lists[0].select_all(True)
    assert not dialog.run.isEnabled()
    dialog.lists[1].select_all(True)
    assert dialog.run.isEnabled()
    dialog.lists[0].search.setText('casual chat')
    assert dialog.lists[0].items.item(0).isHidden()
    assert not dialog.lists[0].items.item(1).isHidden()
    assert len(dialog.lists[0].selected()) == 3
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: ('', ''))
    dialog.start()
    assert dialog.future is None
    future = Future()
    submitted = []
    def submit(*args):
        submitted.append(args)
        return future
    monkeypatch.setattr(dialog.pool, 'submit', submit)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(tmp_path/'out.jsonl'), ''))
    dialog.start()
    settings['value'] = 2
    assert submitted[0][1] == tuple(infos)
    assert submitted[0][4] == {'value': 1}
    assert not dialog.run.isEnabled()
    dialog.update_progress(1, 2)
    assert dialog.progress.value() == 1
    dialog.cancel_batch()
    assert dialog.cancelled.is_set()
    future.set_exception(CancelledError())
    dialog.poll()
    assert 'cancelled' in dialog.status.text()
    assert dialog.run.isEnabled()
    dialog.shutdown()
    dialog.close()
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
