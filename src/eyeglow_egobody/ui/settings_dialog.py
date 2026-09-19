"""Editable values generated from the settings JSON definitions."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QLabel,
                               QDialogButtonBox, QGroupBox, QScrollArea, QWidget, QComboBox,
                               QPushButton, QColorDialog, QCheckBox, QHBoxLayout)
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
            entries = list(entries.items())
            index = 0
            while index < len(entries):
                name, spec = entries[index]
                field = self._make_field(name, spec, spec['value'])
                field.setObjectName(name)
                field.setAccessibleName(spec['display_name'])
                if 'choices' not in spec and spec.get('kind') not in {'color', 'text', 'boolean'}:
                    field.setToolTip(f"Range: {spec['min']} to {spec['max']}")
                self.fields[name] = field
                visible_name = f'{name}_visible'
                if spec.get('kind') == 'text' and index + 1 < len(entries) and entries[index + 1][0] == visible_name:
                    _, visible_spec = entries[index + 1]
                    visible = self._make_field(visible_name, visible_spec, visible_spec['value'])
                    visible.setObjectName(visible_name)
                    visible.setAccessibleName(visible_spec['display_name'])
                    self.fields[visible_name] = visible
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.addWidget(field, 1)
                    row_layout.addWidget(visible)
                    target.addRow(spec['display_name'], row)
                    index += 2
                else:
                    target.addRow(spec['display_name'], field)
                    index += 1
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

    @staticmethod
    def _display_choice(value):
        return {'binocular': 'Binocular', 'monocular_left': 'Mono left',
                'monocular_right': 'Mono right'}.get(value, value)

    def _make_field(self, name, spec, value):
        if 'choices' in spec:
            field = QComboBox()
            for choice in spec['choices']:
                field.addItem(self._display_choice(choice), choice)
            field.setCurrentIndex(field.findData(value))
            return field
        if spec.get('kind') == 'boolean':
            field = QCheckBox(spec['display_name'])
            field.setChecked(value)
            return field
        if spec.get('kind') == 'color':
            field = QPushButton()
            field.setMinimumWidth(88)
            field.setProperty('color', value)
            field.clicked.connect(lambda: self._choose_color(field))
            self._set_color_button(field, value)
            return field
        return QLineEdit(format_value(spec, value))

    @staticmethod
    def _set_color_button(field, color):
        field.setProperty('color', color)
        field.setText(color.upper())
        field.setStyleSheet(f'QPushButton {{ background-color: {color}; border: 1px solid #555; min-height: 20px; }}')

    def _choose_color(self, field):
        color = QColorDialog.getColor(
            QColor(field.property('color')), self, 'Choose color',
            QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if color.isValid():
            self._set_color_button(field, color.name())

    @staticmethod
    def _field_value(field, spec):
        if 'choices' in spec:
            return field.currentData()
        if spec.get('kind') == 'boolean':
            return field.isChecked()
        if spec.get('kind') == 'color':
            return field.property('color')
        return field.text().strip()

    def _set_field_value(self, field, spec, value):
        if 'choices' in spec:
            field.setCurrentIndex(field.findData(value))
        elif spec.get('kind') == 'boolean':
            field.setChecked(value)
        elif spec.get('kind') == 'color':
            self._set_color_button(field, value)
        else:
            field.setText(format_value(spec, value))

    def reset_to_factory(self):
        for key, field in self.fields.items():
            spec = self.store.specs[key]
            self._set_field_value(field, spec, spec['factory_default'])
        self.error.clear()

    def accept(self):
        values = {}
        for key, field in self.fields.items():
            spec = self.store.specs[key]
            try:
                values[key] = validate_value(spec, self._field_value(field, spec))
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
