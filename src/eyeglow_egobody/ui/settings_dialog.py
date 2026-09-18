"""Editable values generated from the settings JSON definitions."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QLabel, QDialogButtonBox, QGroupBox, QScrollArea, QWidget
from eyeglow_egobody.model.panel_settings import validate_value, format_value


class SettingsDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle('Settings')
        self.setModal(True)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        form = QFormLayout()
        content_layout.addLayout(form)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.resize(560, 700)
        self.fields = {}
        for key, entry in store.document['settings'].items():
            if 'display_name' in entry:
                entries, target = {key: entry}, form
            else:
                group = QGroupBox(key.replace('_', ' ').title())
                group.setObjectName(key)
                target = QFormLayout(group)
                content_layout.addWidget(group)
                entries = entry
            for name, spec in entries.items():
                field = QLineEdit(format_value(spec, spec['value']))
                field.setObjectName(name)
                field.setAccessibleName(spec['display_name'])
                if 'choices' in spec:
                    field.setToolTip(', '.join(spec['choices']))
                else:
                    field.setToolTip(f"Range: {spec['min']} to {spec['max']}")
                target.addRow(spec['display_name'], field)
                self.fields[name] = field
        content_layout.addStretch()
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
            spec = self.store.specs[key]
            field.setText(format_value(spec, spec['factory_default']))
        self.error.clear()

    def accept(self):
        values = {}
        for key, field in self.fields.items():
            spec = self.store.specs[key]
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
