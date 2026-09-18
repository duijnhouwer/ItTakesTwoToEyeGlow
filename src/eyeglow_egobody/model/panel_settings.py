"""JSON-backed numeric settings, independent of Qt and rendering."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import tempfile
from eyeglow_egobody.runtime_paths import project_root
from .parameters import OpticalParameters


def settings_path():
    return project_root() / 'config' / 'settings_panel.json'


def validate_value(spec, value):
    if "choices" in spec:
        if value not in spec["choices"]:
            raise ValueError("choose " + ", ".join(spec["choices"]))
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
    return str(value) if 'choices' in spec else f"{value:.{spec['precision']}f}"


class PanelSettings:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else settings_path()
        self.document = json.loads(self.path.read_text())
        if self.document.get('schema_version') != 1:
            raise ValueError('Unsupported settings schema')
        specs = self.document.get('settings')
        if not isinstance(specs, dict) or not {'eyeball_radius_mm', 'eye_relief_mm'} <= specs.keys():
            raise ValueError('Required optical settings are missing')
        specs = setting_specs(self.document)
        for key, spec in specs.items():
            if isinstance(spec, dict) and "choices" in spec:
                if not isinstance(spec.get("display_name"), str) or not spec["display_name"] or not isinstance(spec["choices"], list) or not spec["choices"] or not all(isinstance(v, str) for v in spec["choices"]):
                    raise ValueError(f"Invalid setting definition: {key}")
                for field in ("value", "default", "factory_default"):
                    validate_value(spec, spec.get(field))
                continue
            if (not isinstance(spec, dict) or not isinstance(spec.get('display_name'), str)
                    or not spec['display_name']
                    or type(spec.get('precision')) is not int or not 0 <= spec['precision'] <= 6
                    or any(type(spec.get(k)) not in (int, float) or not math.isfinite(spec[k])
                           for k in ('min', 'max')) or spec['min'] > spec['max']):
                raise ValueError(f'Invalid setting definition: {key}')
            for field in ('value', 'default', 'factory_default'):
                validate_value(spec, spec.get(field))
        if specs['eyeball_radius_mm']['min'] <= 0 or specs['eye_relief_mm']['min'] < 0:
            raise ValueError('Eyeball radius must be positive and eye relief nonnegative')
        for field in ('value', 'default', 'factory_default'):
            OpticalParameters.from_settings({key: spec[field] for key, spec in specs.items()})

    @property
    def values(self):
        return {key: validate_value(spec, spec['value']) for key, spec in self.specs.items()}

    @property
    def specs(self):
        return setting_specs(self.document)

    @property
    def optical_parameters(self):
        return OpticalParameters.from_settings(self.values)

    def save(self, values):
        updated = deepcopy(self.document)
        specs = setting_specs(updated)
        if values.keys() != specs.keys():
            raise ValueError('Settings keys do not match the document')
        for key, value in values.items():
            specs[key]['value'] = validate_value(specs[key], value)
        OpticalParameters.from_settings({key: spec['value'] for key, spec in specs.items()})
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, suffix='.json', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(updated, stream, indent=2, allow_nan=False)
                stream.write('\n')
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.document = updated
