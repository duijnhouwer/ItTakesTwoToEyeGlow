"""Editable values generated from the settings JSON definitions."""
import json
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QLabel,
                               QDialogButtonBox, QGroupBox, QScrollArea, QWidget, QComboBox,
                               QPushButton, QColorDialog, QCheckBox, QHBoxLayout,
                               QDoubleSpinBox)
from eyeglow_egobody.model.panel_settings import validate_value, format_value


class SettingsEditor(QWidget):
    """Reusable settings form for the main-window panels and modal dialog."""

    saved = Signal()

    PAIRED_ROWS = {
        'receiver_fov_left_deg': ('receiver_fov_right_deg', 'Left / Right (deg)', None),
        'receiver_fov_top_deg': ('receiver_fov_bottom_deg', 'Top / Bottom (deg)', None),
        'frustum_opacity': ('frustum_wall_opacity', 'Frustum opacity', 'on wall'),
    }

    def __init__(self, store, groups=None, parent=None, show_buttons=True,
                 save_user_defaults=None, flat_groups=(), scrollable=True):
        super().__init__(parent)
        self.store = store
        self.save_user_defaults = save_user_defaults
        self.live_updates = show_buttons
        self.groups = tuple(groups or store.document['settings'])
        self.flat_groups = frozenset(flat_groups)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        form = QFormLayout()
        content_layout.addLayout(form)
        if scrollable:
            scroll.setWidget(content)
            layout.addWidget(scroll)
        else:
            layout.addWidget(content)
        self.fields = {}
        self.group_fields = {}
        self.group_forms = {}
        self.group_factory_reset = {}
        self.group_save = {}
        for key, entry in store.document['settings'].items():
            if key not in self.groups:
                continue
            self.group_fields[key] = tuple(({key: entry} if 'display_name' in entry else entry).keys())
            if 'display_name' in entry or key in self.flat_groups:
                entries, target = {key: entry}, form
                if 'display_name' not in entry:
                    entries = entry
            else:
                title = key.replace('_', ' ').title().replace('Fov', 'FOV')
                group = QGroupBox(title)
                group.setObjectName(key)
                target = QFormLayout(group)
                content_layout.addWidget(group)
                entries = entry
            self.group_forms[key] = target
            entries = list(entries.items())
            index = 0
            while index < len(entries):
                name, spec = entries[index]
                pair = self.PAIRED_ROWS.get(name)
                if pair and index + 1 < len(entries) and entries[index + 1][0] == pair[0]:
                    second_name, second_spec = entries[index + 1]
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    for field_name, field_spec in ((name, spec), (second_name, second_spec)):
                        field = self._make_field(field_name, field_spec, field_spec['value'])
                        field.setObjectName(field_name)
                        field.setAccessibleName(field_spec['display_name'])
                        field.setToolTip(f"Range: {field_spec['min']} to {field_spec['max']}")
                        self.fields[field_name] = field
                        row_layout.addWidget(field, 1)
                        if field_name == name and pair[2]:
                            row_layout.addWidget(QLabel(pair[2]))
                    target.addRow(pair[1], row)
                    index += 2
                    continue
                field = self._make_field(name, spec, spec['value'])
                field.setObjectName(name)
                field.setAccessibleName(spec['display_name'])
                if 'choices' not in spec and spec.get('kind') not in {'color', 'text', 'boolean', 'string_list'}:
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
                    if spec.get('kind') == 'boolean':
                        target.addRow(field)
                    else:
                        target.addRow(spec['display_name'], field)
                    index += 1
            if show_buttons and 'display_name' not in entry:
                self._add_group_buttons(key, target)
        if scrollable:
            content_layout.addStretch()
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.setStyleSheet('color: #d9534f')
        layout.addWidget(self.error)
        if self.live_updates:
            for name, field in self.fields.items():
                self._enable_live_update(name, field)

    def _add_group_buttons(self, group_name, form):
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save)
        factory_reset = buttons.addButton('Factory Reset', QDialogButtonBox.ButtonRole.ResetRole)
        factory_reset.setObjectName(f'{group_name}_factory_reset')
        factory_reset.setToolTip(f'Restore factory values for {group_name.replace("_", " ")} immediately.')
        factory_reset.clicked.connect(lambda: self.reset_group(group_name))
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setObjectName(f'{group_name}_save')
        save.setText('Save as new defaults')
        save.setToolTip(f'Use these {group_name.replace("_", " ")} values as the defaults next time the app opens.')
        save.clicked.connect(lambda: self.save_group(group_name))
        # QDialogButtonBox supplies the platform's standard green Save arrow.
        form.addRow(buttons)
        self.group_factory_reset[group_name] = factory_reset
        self.group_save[group_name] = save

    @staticmethod
    def _display_choice(value):
        return {'binocular': 'Binocular', 'monocular_left': 'Mono left',
                'monocular_right': 'Mono right', 'elliptical': 'Elliptical',
                'rectangular': 'Rectangular'}.get(value, value)

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
            field.clicked.connect(lambda: self._choose_color(name, field))
            self._set_color_button(field, value)
            return field
        if spec.get('control') == 'spinbox':
            field = QDoubleSpinBox()
            field.setRange(spec['min'], spec['max'])
            field.setDecimals(spec['precision'])
            field.setSingleStep(spec.get('step', 1))
            field.setValue(value)
            return field
        return QLineEdit(format_value(spec, value))

    @staticmethod
    def _set_color_button(field, color):
        field.setProperty('color', color)
        field.setText(color.upper())
        field.setStyleSheet(f'QPushButton {{ background-color: {color}; border: 1px solid #555; min-height: 20px; }}')

    def _choose_color(self, name, field):
        color = QColorDialog.getColor(
            QColor(field.property('color')), self, 'Choose color',
            QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if color.isValid():
            self._set_color_button(field, color.name())
            if self.live_updates:
                self._commit_fields((name,))

    def _enable_live_update(self, name, field):
        if isinstance(field, QLineEdit):
            field.editingFinished.connect(lambda: self._commit_fields((name,)))
        elif isinstance(field, QComboBox):
            field.currentIndexChanged.connect(lambda: self._commit_fields((name,)))
        elif isinstance(field, QCheckBox):
            field.toggled.connect(lambda: self._commit_fields((name,)))
        elif isinstance(field, QDoubleSpinBox):
            field.valueChanged.connect(lambda: self._commit_fields((name,)))

    @staticmethod
    def _field_value(field, spec):
        if spec.get('kind') == 'string_list':
            return json.loads(field.text())
        if 'choices' in spec:
            return field.currentData()
        if spec.get('kind') == 'boolean':
            return field.isChecked()
        if spec.get('kind') == 'color':
            return field.property('color')
        if isinstance(field, QDoubleSpinBox):
            return field.value()
        return field.text().strip()

    def _set_field_value(self, field, spec, value):
        if 'choices' in spec:
            field.setCurrentIndex(field.findData(value))
        elif spec.get('kind') == 'boolean':
            field.setChecked(value)
        elif spec.get('kind') == 'color':
            self._set_color_button(field, value)
        elif isinstance(field, QDoubleSpinBox):
            field.setValue(value)
        else:
            field.setText(format_value(spec, value))

    def reset_to_factory(self):
        for key, field in self.fields.items():
            spec = self.store.specs[key]
            self._set_field_value(field, spec, spec['factory_default'])
        self.error.clear()

    def reset_group(self, group_name):
        factory_values = self.store.factory_values if self.store.factory_path is not None else {
            key: self.store.specs[key]['factory_default'] for key in self.group_fields[group_name]}
        blockers = [QSignalBlocker(self.fields[key]) for key in self.group_fields[group_name]]
        for key in self.group_fields[group_name]:
            field = self.fields[key]
            spec = self.store.specs[key]
            self._set_field_value(field, spec, factory_values[key])
        del blockers
        self.error.clear()
        if self.live_updates:
            self._commit_fields(self.group_fields[group_name])

    def save_group(self, group_name):
        if self.save_user_defaults is not None:
            # A button click is also an explicit commit for a text field that still
            # owns focus, before promoting the resulting live values to defaults.
            if not self._commit_fields(self.group_fields[group_name]):
                return False
            return self.save_user_defaults(
                {key: self.store.values[key] for key in self.group_fields[group_name]})
        return self.save((group_name,))

    def save(self, groups=None):
        field_names = self.fields if groups is None else (
            key for group_name in groups for key in self.group_fields[group_name])
        return self._commit_fields(tuple(field_names))

    def _commit_fields(self, field_names):
        values = self.store.values
        for key in field_names:
            field = self.fields[key]
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
            return False
        self.error.clear()
        self.saved.emit()
        return True


class SettingsDialog(QDialog):
    """Legacy all-settings dialog retained for focused modal use and tests."""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle('Settings')
        self.setModal(True)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        self.editor = SettingsEditor(store, parent=self, show_buttons=False)
        layout.addWidget(self.editor)
        self.fields = self.editor.fields
        self.error = self.editor.error
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.factory_reset = self.buttons.addButton('Factory Reset', QDialogButtonBox.ButtonRole.ResetRole)
        self.factory_reset.setToolTip('Restore factory values in this dialog. Save to apply them.')
        self.factory_reset.clicked.connect(self.reset_to_factory)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.resize(560, 700)

    def reset_to_factory(self):
        self.editor.reset_to_factory()

    def accept(self):
        if self.editor.save():
            super().accept()
