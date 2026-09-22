"""Persistent paired action selection; analysis belongs to the main window."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QWidget,
                               QDialogButtonBox)
from eyeglow_egobody.model.playlist import (ActivitiesPlaylist, PLAYLIST_KEYS,
                                            PLAYLIST_FORCE_ALL_KEYS,
                                            playlist_selections)


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

    def set_selected(self, labels):
        self.items.blockSignals(True)
        for i in range(self.items.count()):
            item = self.items.item(i)
            item.setCheckState(Qt.CheckState.Checked if item.text() in labels else Qt.CheckState.Unchecked)
        self.items.blockSignals(False)

    def select_all(self, checked):
        self.set_selected([self.items.item(i).text() for i in range(self.items.count())] if checked else [])
        self.changed.emit()

    def selected(self):
        return [self.items.item(i).text() for i in range(self.items.count())
                if self.items.item(i).checkState() == Qt.CheckState.Checked]


class ActivitiesPlaylistDialog(QDialog):
    def __init__(self, infos, catalog, store, save_user_defaults=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Edit activities playlist ...')
        self.resize(850, 600)
        self.infos, self.catalog, self.store = tuple(infos), catalog, store
        self.save_user_defaults = save_user_defaults
        self.save_failed = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            'Include activity pair clips where both participants match their selected actions.'))
        row = QHBoxLayout()
        values = store.values
        labels = sorted(set(catalog.labels) | set(values[PLAYLIST_KEYS[0]])
                        | set(values[PLAYLIST_KEYS[1]]))
        self.lists = tuple(ActionList(title, labels) for title in
                           ('A — wearer actions', 'B — interactee actions'))
        selections = playlist_selections(values, catalog.labels)
        for selected, pane in zip(selections, self.lists):
            row.addWidget(pane)
            pane.set_selected(selected)
            pane.changed.connect(self.selection_changed)
        layout.addLayout(row)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.save_defaults = QPushButton('Save as new defaults')
        # Use the same themed Save icon as the Smartglasses settings panel.
        standard = QDialogButtonBox(QDialogButtonBox.StandardButton.Save)
        self.save_defaults.setIcon(
            standard.button(QDialogButtonBox.StandardButton.Save).icon())
        standard.deleteLater()
        self.save_defaults.clicked.connect(self.save_as_defaults)
        self.factory_reset = QPushButton('Factory Reset')
        self.factory_reset.clicked.connect(self.reset_to_factory)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        for button in (self.save_defaults, self.factory_reset, close):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.update_summary()

    def selections(self):
        return tuple(p.selected() for p in self.lists)

    def update_summary(self):
        self.playlist = ActivitiesPlaylist(self.infos, self.catalog, self.selections())
        self.summary.setText(self.playlist.summary)

    def selection_changed(self):
        self.update_summary()
        values = self.store.values
        values.update(dict(zip(PLAYLIST_KEYS, self.selections())))
        values.update(dict(zip(PLAYLIST_FORCE_ALL_KEYS, (
            len(pane.selected()) == pane.items.count() for pane in self.lists))))
        try:
            self.store.save(values)
        except (OSError, ValueError) as exc:
            self.save_failed = True
            self.status.setText(f'Could not save selection: {exc}')
            return False
        self.save_failed = False
        self.status.setText('Selection saved for this session.')
        return True

    def save_as_defaults(self):
        if not self.selection_changed():
            return
        values = dict(zip(PLAYLIST_KEYS, self.selections()))
        values.update({key: self.store.values[key] for key in PLAYLIST_FORCE_ALL_KEYS})
        if self.save_user_defaults is not None and self.save_user_defaults(values) is False:
            return
        self.status.setText('Saved as new defaults.')

    def reset_to_factory(self):
        values = (self.store.factory_values if self.store.factory_path is not None else
                  {key: self.store.specs[key]['factory_default'] for key in PLAYLIST_KEYS})
        for key, force_key, pane in zip(PLAYLIST_KEYS, PLAYLIST_FORCE_ALL_KEYS,
                                        self.lists):
            labels = self.catalog.labels if values[force_key] else values[key]
            existing = {pane.items.item(i).text() for i in range(pane.items.count())}
            for label in sorted(set(labels) - existing):
                item = QListWidgetItem(label, pane.items)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            pane.set_selected(labels)
        self.selection_changed()

    def reject(self):
        if self.save_failed and not self.selection_changed():
            return
        super().reject()
