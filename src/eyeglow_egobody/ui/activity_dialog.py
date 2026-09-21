"""Independent action selection and asynchronous batch export."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Event
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QWidget,
                               QFileDialog, QMessageBox, QProgressBar)
from eyeglow_egobody.analysis.batch import run_batch
from eyeglow_egobody.ui.file_dialogs import save_file


class ActionList(QWidget):
    changed = Signal()

    def __init__(self, title, labels, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search actions…')
        layout.addWidget(self.search)
        self.items = QListWidget()
        for label in labels:
            item = QListWidgetItem(label, self.items)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
        layout.addWidget(self.items)
        row = QHBoxLayout()
        for title, checked in (('Select all', True), ('Clear', False)):
            button = QPushButton(title)
            button.setToolTip('Applies to all actions, including hidden search results.')
            button.clicked.connect(lambda _, value=checked: self.select_all(value))
            row.addWidget(button)
        layout.addLayout(row)
        self.search.textChanged.connect(self.filter)
        self.items.itemChanged.connect(lambda _: self.changed.emit())

    def filter(self, text):
        text = text.lower().replace(' ', '_')
        for i in range(self.items.count()):
            item = self.items.item(i)
            item.setHidden(text not in item.text().lower())

    def select_all(self, checked):
        self.items.blockSignals(True)
        for i in range(self.items.count()):
            self.items.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.items.blockSignals(False)
        self.changed.emit()

    def selected(self):
        return tuple(self.items.item(i).text() for i in range(self.items.count())
                     if self.items.item(i).checkState() == Qt.CheckState.Checked)


class ActivityAnalysisDialog(QDialog):
    progress_changed = Signal(int, int)

    def __init__(self, infos, catalog, settings_provider, model_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Activity Analysis')
        self.resize(850, 600)
        self.infos, self.catalog = tuple(infos), catalog
        self.settings_provider, self.model_dir = settings_provider, model_dir
        self.future = None
        self.cancelled = Event()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='activity-analysis')
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Analyze time where both participants match their selected actions.'))
        row = QHBoxLayout()
        self.lists = tuple(ActionList(title, catalog.labels) for title in
                           ('A — wearer actions', 'B — interactee actions'))
        for pane in self.lists:
            row.addWidget(pane)
            pane.changed.connect(self.sync)
        layout.addLayout(row)
        self.status = QLabel('Select at least one action for each participant.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.run = QPushButton('Analyze and save JSONL…')
        self.run.clicked.connect(self.start)
        buttons.addWidget(self.run)
        self.cancel = QPushButton('Cancel batch')
        self.cancel.clicked.connect(self.cancel_batch)
        self.cancel.hide()
        buttons.addWidget(self.cancel)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.progress_changed.connect(self.update_progress)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.poll)
        self.sync()

    def sync(self):
        busy = self.future is not None
        for pane in self.lists:
            pane.setEnabled(not busy)
        self.run.setEnabled(not busy and all(p.selected() for p in self.lists))
        self.cancel.setVisible(busy)

    def start(self):
        if self.future is not None or not all(p.selected() for p in self.lists):
            return
        name, _ = save_file(self, 'Save activity analysis',
                                             str(Path.home()/'activity-analysis.jsonl'),
                                             'JSON Lines (*.jsonl)',
                                             options=QFileDialog.Option.DontConfirmOverwrite)
        if not name:
            return
        destination = Path(name)
        if not destination.suffix:
            destination = destination.with_suffix('.jsonl')
        overwrite = destination.exists()
        if overwrite and QMessageBox.question(self, 'Replace file?', f'Replace {destination.name}?') != QMessageBox.StandardButton.Yes:
            return
        settings = deepcopy(self.settings_provider())
        selections = tuple(p.selected() for p in self.lists)
        self.cancelled = Event()
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText('Preparing activity analysis…')
        self.future = self.pool.submit(run_batch, self.infos, self.catalog, selections,
                                       settings, self.model_dir, destination, self.cancelled,
                                       self.progress_changed.emit, overwrite)
        self.timer.start()
        self.sync()

    def update_progress(self, current, total):
        self.progress.setRange(0, total)
        self.progress.setValue(current)
        self.status.setText(f'Analyzing motion: {current} / {total}')

    def cancel_batch(self):
        self.cancelled.set()
        self.status.setText('Cancelling…')

    def poll(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.timer.stop()
        try:
            destination = future.result()
            self.status.setText(f'Saved {destination}')
        except CancelledError:
            self.status.setText('Batch cancelled. No output was published.')
        except Exception as exc:
            self.status.setText(f'Analysis failed: {exc}')
        self.sync()

    def reject(self):
        if self.future is not None:
            self.cancel_batch()
            return
        super().reject()

    def shutdown(self):
        self.cancelled.set()
        self.timer.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
