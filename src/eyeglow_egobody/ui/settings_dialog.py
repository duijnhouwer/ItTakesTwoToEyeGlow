"""Editable values generated from the settings JSON definitions."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QLabel, QDialogButtonBox
from eyeglow_egobody.model.panel_settings import validate_value


class SettingsDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle('Settings')
        self.setModal(True)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.fields = {}
        for key, spec in store.document['settings'].items():
            field = QLineEdit(f"{spec['value']:.{spec['precision']}f}")
            field.setObjectName(key)
            field.setAccessibleName(spec['display_name'])
            form.addRow(spec['display_name'], field)
            self.fields[key] = field
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.setStyleSheet('color: #d9534f')
        layout.addWidget(self.error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.factory_reset = self.buttons.addButton('Factory Reset', QDialogButtonBox.ButtonRole.ResetRole)
        self.factory_reset.setToolTip('Restore factory values in this dialog. Save to apply them.')
        self.factory_reset.clicked.connect(self.reset_to_factory)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def reset_to_factory(self):
        for key, field in self.fields.items():
            spec = self.store.document['settings'][key]
            field.setText(f"{spec['factory_default']:.{spec['precision']}f}")
        self.error.clear()

    def accept(self):
        values = {}
        for key, field in self.fields.items():
            spec = self.store.document['settings'][key]
            try:
                values[key] = validate_value(spec, field.text().strip())
            except ValueError as exc:
                self.error.setText(f"{spec['display_name']}: {exc}.")
                field.setFocus()
                return
        try:
            self.store.save(values)
        except (OSError, ValueError) as exc:
            self.error.setText(f'Could not save settings: {exc}')
            return
        super().accept()
