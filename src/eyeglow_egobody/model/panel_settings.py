"""JSON-backed numeric settings, independent of Qt and rendering."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import tempfile
from eyeglow_egobody.runtime_paths import project_root


def settings_path():
    return project_root() / 'config' / 'settings_panel.json'


def validate_value(spec, value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or not spec['min'] <= number <= spec['max']:
            raise ValueError(f"must be between {spec['min']:g} and {spec['max']:g}")
        if number != number.quantize(Decimal(1).scaleb(-spec['precision'])):
            raise ValueError(f"use at most {spec['precision']} decimal places")
        return float(number)
    except InvalidOperation as exc:
        raise ValueError('enter a valid number') from exc


class PanelSettings:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else settings_path()
        self.document = json.loads(self.path.read_text())
        if self.document.get('schema_version') != 1:
            raise ValueError('Unsupported settings schema')
        specs = self.document.get('settings')
        if not isinstance(specs, dict) or not {'eyeball_radius_mm', 'eye_relief_mm'} <= specs.keys():
            raise ValueError('Required optical settings are missing')
        for key, spec in specs.items():
            if (not isinstance(spec, dict) or not isinstance(spec.get('display_name'), str)
                    or not spec['display_name']
                    or type(spec.get('precision')) is not int or not 0 <= spec['precision'] <= 6
                    or any(type(spec.get(k)) not in (int, float) or not math.isfinite(spec[k])
                           for k in ('min', 'max')) or spec['min'] > spec['max']):
                raise ValueError(f'Invalid setting definition: {key}')
            for field in ('value', 'default'):
                validate_value(spec, spec.get(field))
        if specs['eyeball_radius_mm']['min'] <= 0 or specs['eye_relief_mm']['min'] < 0:
            raise ValueError('Eyeball radius must be positive and eye relief nonnegative')

    @property
    def values(self):
        return {key: float(spec['value']) for key, spec in self.document['settings'].items()}

    def save(self, values):
        updated = deepcopy(self.document)
        if values.keys() != updated['settings'].keys():
            raise ValueError('Settings keys do not match the document')
        for key, value in values.items():
            updated['settings'][key]['value'] = validate_value(updated['settings'][key], value)
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
