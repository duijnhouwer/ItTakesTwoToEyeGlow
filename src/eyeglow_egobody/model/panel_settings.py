"""Validated factory, user-default, and live settings documents."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import re
import tempfile
from eyeglow_egobody.runtime_paths import project_root, settings_resource_path
from .parameters import OpticalParameters

FACTORY_FILENAME = 'settings_factory_default.json'
USER_DEFAULT_FILENAME = 'settings_user_default.json'
CURRENT_FILENAME = 'settings_current.json'


def settings_path():
    """Legacy project settings path, read once when upgrading an installation."""
    return project_root() / 'config' / 'settings_panel.json'


def factory_settings_path():
    return settings_resource_path(FACTORY_FILENAME)


def user_settings_directory():
    """Platform-owned, per-user location for mutable settings."""
    from PySide6.QtCore import QStandardPaths
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    if not location:
        raise OSError('No writable application settings location is available')
    return Path(location)


def validate_value(spec, value):
    kind = spec.get('kind')
    if kind == 'string_list':
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
            raise ValueError('choose a list of actions')
        return sorted(set(value))
    if kind == 'color':
        if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError('choose a valid color')
        return value.lower()
    if kind == 'text':
        if not isinstance(value, str):
            raise ValueError('enter text')
        return value
    if kind == 'boolean':
        if type(value) is not bool:
            raise ValueError('choose on or off')
        return value
    if 'choices' in spec:
        if value not in spec['choices']:
            raise ValueError('choose ' + ', '.join(spec['choices']))
        return value
    try:
        number = Decimal(str(value))
        if not number.is_finite() or not spec['min'] <= number <= spec['max']:
            raise ValueError(f"must be between {spec['min']:g} and {spec['max']:g}")
        if number != number.quantize(Decimal(1).scaleb(-spec['precision'])):
            raise ValueError(f"use at most {spec['precision']} decimal places")
        return float(number)
    except InvalidOperation as exc:
        raise ValueError('enter a valid number') from exc


def setting_specs(document):
    """Flatten one level of named groups; serialized definitions remain grouped."""
    result = {}
    for key, spec in document['settings'].items():
        entries = {key: spec} if 'display_name' in spec else spec
        for name, definition in entries.items():
            if name in result:
                raise ValueError(f'Duplicate setting: {name}')
            result[name] = definition
    return result


def format_value(spec, value):
    if spec.get('kind') == 'string_list':
        return json.dumps(value)
    return str(value) if 'choices' in spec or spec.get('kind') in {'color', 'text'} else f"{value:.{spec['precision']}f}"


def _read_document(path):
    return json.loads(Path(path).read_text())


def _atomic_write(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, suffix='.json', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(document, stream, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _validate_schema(document):
    if document.get('schema_version') != 1:
        raise ValueError('Unsupported settings schema')
    settings = document.get('settings')
    if not isinstance(settings, dict) or not isinstance(settings.get('smartglasses'), dict):
        raise ValueError('Smartglasses settings are missing')
    specs = setting_specs(document)
    if 'eye_relief_mm' not in specs:
        raise ValueError('Eye relief setting is missing')
    for key, spec in specs.items():
        if isinstance(spec, dict) and spec.get('kind') in {'color', 'text', 'boolean', 'string_list'}:
            if not isinstance(spec.get('display_name'), str) or not spec['display_name']:
                raise ValueError(f'Invalid setting definition: {key}')
            for field in ('value', 'default', 'factory_default'):
                validate_value(spec, spec.get(field))
            continue
        if isinstance(spec, dict) and 'choices' in spec:
            if (not isinstance(spec.get('display_name'), str) or not spec['display_name']
                    or not isinstance(spec['choices'], list) or not spec['choices']
                    or not all(isinstance(v, str) for v in spec['choices'])):
                raise ValueError(f'Invalid setting definition: {key}')
            for field in ('value', 'default', 'factory_default'):
                validate_value(spec, spec.get(field))
            continue
        if (not isinstance(spec, dict) or not isinstance(spec.get('display_name'), str)
                or not spec['display_name'] or type(spec.get('precision')) is not int
                or not 0 <= spec['precision'] <= 6
                or any(type(spec.get(k)) not in (int, float) or not math.isfinite(spec[k])
                       for k in ('min', 'max')) or spec['min'] > spec['max']):
            raise ValueError(f'Invalid setting definition: {key}')
        for field in ('value', 'default', 'factory_default'):
            validate_value(spec, spec.get(field))
    if specs['eye_relief_mm']['min'] < 0:
        raise ValueError('Eye relief must be nonnegative')
    for field in ('value', 'default', 'factory_default'):
        OpticalParameters.from_settings({key: spec[field] for key, spec in specs.items()})


class PanelSettings:
    """A mutable document validated against an optional immutable factory schema."""

    def __init__(self, path=None, factory_path=None, read_only=False):
        self.path = Path(path) if path is not None else settings_path()
        self.factory_path = Path(factory_path) if factory_path is not None else None
        self.read_only = read_only
        self.document = _read_document(self.path)
        self.factory_document = (_read_document(self.factory_path)
                                 if self.factory_path is not None else self.document)
        _validate_schema(self.factory_document)
        self._specs = setting_specs(self.factory_document)
        document_specs = setting_specs(self.document)
        if document_specs.keys() != self._specs.keys():
            raise ValueError('Settings keys do not match the factory schema')
        self._validate_values(self.document)

    def _validate_values(self, document):
        values = setting_specs(document)
        for key, spec in self._specs.items():
            validate_value(spec, values[key].get('value'))
        OpticalParameters.from_settings({key: values[key]['value'] for key in self._specs})

    @property
    def values(self):
        values = setting_specs(self.document)
        return {key: validate_value(spec, values[key]['value']) for key, spec in self._specs.items()}

    @property
    def specs(self):
        return self._specs

    @property
    def factory_values(self):
        values = setting_specs(self.factory_document)
        return {key: validate_value(spec, values[key]['value']) for key, spec in self._specs.items()}

    @property
    def optical_parameters(self):
        return OpticalParameters.from_settings(self.values)

    @classmethod
    def write_values(cls, path, factory_path, values, read_only=False):
        factory = PanelSettings(factory_path)
        if values.keys() != factory.specs.keys():
            raise ValueError('Settings keys do not match the factory schema')
        updated = deepcopy(factory.document)
        specs = setting_specs(updated)
        for key, value in values.items():
            specs[key]['value'] = validate_value(factory.specs[key], value)
        OpticalParameters.from_settings({key: specs[key]['value'] for key in factory.specs})
        _atomic_write(path, updated)
        if read_only:
            Path(path).chmod(0o444)

    def save(self, values):
        if values.keys() != self._specs.keys():
            raise ValueError('Settings keys do not match the factory schema')
        updated = deepcopy(self.factory_document)
        specs = setting_specs(updated)
        for key, value in values.items():
            specs[key]['value'] = validate_value(self._specs[key], value)
        OpticalParameters.from_settings({key: specs[key]['value'] for key in self._specs})
        _atomic_write(self.path, updated)
        if self.read_only:
            self.path.chmod(0o444)
        self.document = updated


class SettingsSession:
    """Owns per-launch Current settings and durable User Default settings."""

    def __init__(self, factory_path=None, user_directory=None, legacy_path=None):
        self.factory_path = Path(factory_path) if factory_path is not None else factory_settings_path()
        self.user_directory = Path(user_directory) if user_directory is not None else user_settings_directory()
        self.user_default_path = self.user_directory / USER_DEFAULT_FILENAME
        self.current_path = self.user_directory / CURRENT_FILENAME
        self.legacy_path = Path(legacy_path) if legacy_path is not None else settings_path()
        self.factory = PanelSettings(self.factory_path)
        # Initialize newly introduced state without discarding the
        # user's unrelated optical/display settings in an existing document.
        self._initialize_new_groups(self.user_default_path)
        self._initialize_new_groups(self.current_path, read_only=True)
        self._ensure_user_default()
        self.recovery_error = None
        self.recovery_pending = self.current_path.exists()
        self.current = None
        if self.recovery_pending:
            try:
                PanelSettings(self.current_path, self.factory_path, read_only=True)
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self.recovery_error = str(exc)
        else:
            self.use_user_defaults()

    def _initialize_new_groups(self, path, read_only=False):
        if not path.exists():
            return
        try:
            document = _read_document(path)
            _validate_schema(document)
        except (OSError, ValueError, KeyError, TypeError):
            return  # The normal settings validation/recovery flow handles it.
        missing = [name for name in self.factory.document['settings'] if name not in document['settings']]
        if missing:
            for name in missing:
                document['settings'][name] = deepcopy(self.factory.document['settings'][name])
            if read_only:
                path.chmod(0o644)
            _atomic_write(path, document)
            if read_only:
                path.chmod(0o444)

    def _ensure_user_default(self):
        if self.user_default_path.exists():
            try:
                PanelSettings(self.user_default_path, self.factory_path)
                return
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                pass
        values = self.factory.values
        if self.legacy_path.exists():
            try:
                values = PanelSettings(self.legacy_path).values
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                pass
        PanelSettings.write_values(self.user_default_path, self.factory_path, values)

    def _start_with(self, values):
        PanelSettings.write_values(self.current_path, self.factory_path, values, read_only=True)
        self.current = PanelSettings(self.current_path, self.factory_path, read_only=True)
        self.recovery_pending = False
        return self.current

    def restore_recovered_settings(self):
        if not self.recovery_pending or self.recovery_error is not None:
            raise ValueError('Recovered settings are unavailable')
        self.current = PanelSettings(self.current_path, self.factory_path, read_only=True)
        self.recovery_pending = False
        return self.current

    def use_user_defaults(self):
        defaults = PanelSettings(self.user_default_path, self.factory_path)
        return self._start_with(defaults.values)

    def use_factory_defaults(self):
        return self._start_with(self.factory.values)

    def save_user_defaults(self, values):
        defaults = PanelSettings(self.user_default_path, self.factory_path).values
        defaults.update(values)
        PanelSettings.write_values(self.user_default_path, self.factory_path, defaults)
        return True

    def clean_close(self):
        self.current_path.unlink(missing_ok=True)
