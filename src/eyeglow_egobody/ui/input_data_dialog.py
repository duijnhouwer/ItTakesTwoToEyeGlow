"""Persistent source-data selection for paired motion and SMPL-X templates."""
from pathlib import Path
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
                               QLineEdit, QPushButton, QDialogButtonBox, QFileDialog,
                               QMessageBox, QStyle)
from eyeglow_egobody.runtime_paths import default_dataset, default_models
from eyeglow_egobody.ui.file_dialogs import existing_directory, file_dialog

FIELDS = ('egobody_data_path', 'smplx_female_template_path', 'smplx_male_template_path')


def default_paths():
    folder = default_models()
    return dict(egobody_data_path=str(default_dataset()),
                smplx_female_template_path=str(folder/'SMPLX_FEMALE.npz'),
                smplx_male_template_path=str(folder/'SMPLX_MALE.npz'))


class InputDataDialog(QDialog):
    def __init__(self, store, save_user_defaults=None, parent=None):
        super().__init__(parent)
        self.store, self.save_user_defaults = store, save_user_defaults
        self.setWindowTitle('Select input data ...')
        self.setMinimumWidth(760)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        current = self.resolved_values()
        self.fields = {}
        labels = ('EgoBody data folder', 'SMPLX_FEMALE_TEMPLATE', 'SMPLX_MALE_TEMPLATE')
        for key, label in zip(FIELDS, labels):
            field = QLineEdit(current[key])
            field.setObjectName(key)
            field.setAccessibleName(label)
            browse = QPushButton('Select folder ...' if key == FIELDS[0] else 'Select file ...')
            browse.clicked.connect(lambda _, name=key: self.browse(name))
            row = QHBoxLayout()
            row.addWidget(field, 1)
            row.addWidget(browse)
            form.addRow(label, row)
            self.fields[key] = field
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.save_defaults = buttons.addButton('Save as new defaults', QDialogButtonBox.ButtonRole.ActionRole)
        standard = QDialogButtonBox(QDialogButtonBox.StandardButton.Save)
        self.save_defaults.setIcon(standard.button(QDialogButtonBox.StandardButton.Save).icon())
        standard.deleteLater()
        self.factory_reset = buttons.addButton('Factory Reset', QDialogButtonBox.ButtonRole.ResetRole)
        self.save_defaults.clicked.connect(self.save_as_defaults)
        self.factory_reset.clicked.connect(self.reset_to_factory)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)

    def resolved_values(self):
        defaults = default_paths()
        return {key: self.store.values[key] or defaults[key] for key in FIELDS}

    def browse(self, key):
        if key == FIELDS[0]:
            value = existing_directory(self, 'Select EgoBody data folder', self.fields[key].text())
        else:
            value = file_dialog(self, QFileDialog.getOpenFileName, self, 'Select SMPL-X template',
                                self.fields[key].text(), 'SMPL-X template (*.npz)')[0]
        if value:
            self.fields[key].setText(value)

    def values(self):
        return {key: self.fields[key].text().strip() for key in FIELDS}

    def validate(self, values):
        root = Path(values[FIELDS[0]])
        if not (root/'data_info_release.csv').is_file():
            raise ValueError('Choose an EgoBody data folder containing data_info_release.csv.')
        for key in FIELDS[1:]:
            if not Path(values[key]).is_file():
                raise ValueError(f'Choose an existing file for {self.fields[key].accessibleName()}.')

    def apply(self):
        values = self.values()
        self.validate(values)
        merged = self.store.values
        merged.update(values)
        self.store.save(merged)
        return values

    def accept(self):
        try:
            self.apply()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Input data unavailable', str(exc))
            return
        super().accept()

    def save_as_defaults(self):
        try:
            values = self.apply()
            if self.save_user_defaults is not None:
                self.save_user_defaults(values)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Input data unavailable', str(exc))

    def reset_to_factory(self):
        defaults = default_paths()
        for key in FIELDS:
            value = self.store.factory_values[key] or defaults[key]
            self.fields[key].setText(value)
        try:
            self.apply()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Input data unavailable', str(exc))
