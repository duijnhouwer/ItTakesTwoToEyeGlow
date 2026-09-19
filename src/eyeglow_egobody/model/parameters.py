"""Shared optical parameters. Public dimensions in mm/m and angles in degrees."""
from dataclasses import dataclass, fields
from enum import Enum
import math

EYEBALL_RADIUS_MM = 12.0


class DisplayMode(str, Enum):
    MONOCULAR_LEFT = 'monocular_left'
    MONOCULAR_RIGHT = 'monocular_right'
    BINOCULAR = 'binocular'


class ReceiverFovShape(str, Enum):
    ELLIPTICAL = 'elliptical'
    RECTANGULAR = 'rectangular'


@dataclass(frozen=True)
class OpticalParameters:
    eye_relief_mm: float = 13.0
    expander_width_mm: float = 20.0
    expander_height_mm: float = 20.0
    expander_offset_right_mm: float = 0.0
    expander_offset_up_mm: float = 0.0
    diagonal_fov_deg: float = 20.0
    horizontal_vertical_fov_ratio: float = 1.0
    ui_line_azimuth_deg: float = 0.0
    ui_line_elevation_deg: float = 0.0
    maximum_distance_m: float = 5.0
    receiver_fov_left_deg: float = 60.0
    receiver_fov_right_deg: float = 60.0
    receiver_fov_top_deg: float = 45.0
    receiver_fov_bottom_deg: float = 70.0
    receiver_fov_shape: ReceiverFovShape = ReceiverFovShape.ELLIPTICAL
    display_mode: DisplayMode = DisplayMode.BINOCULAR

    def __post_init__(self):
        for field in fields(self):
            if field.name not in {'display_mode', 'receiver_fov_shape'} and not math.isfinite(getattr(self, field.name)):
                raise ValueError(f'{field.name} must be finite')
        for name in ('expander_width_mm', 'expander_height_mm',
                     'horizontal_vertical_fov_ratio', 'maximum_distance_m'):
            if getattr(self, name) <= 0:
                raise ValueError(f'{name} must be positive')
        if self.eye_relief_mm < 0:
            raise ValueError('eye_relief_mm must be nonnegative')
        if not 0 < self.diagonal_fov_deg < 180:
            raise ValueError('diagonal_fov_deg must be between 0 and 180, exclusive')
        for name in ('receiver_fov_left_deg', 'receiver_fov_right_deg'):
            if not 0 < getattr(self, name) < 180:
                raise ValueError(f'{name} must be between 0 and 180, exclusive')
        for name in ('receiver_fov_top_deg', 'receiver_fov_bottom_deg'):
            if not 0 < getattr(self, name) <= 90:
                raise ValueError(f'{name} must be greater than 0 and at most 90')
        if any(abs(a) >= 89 for a in (self.ui_line_azimuth_deg, self.ui_line_elevation_deg)):
            raise ValueError('UI line angles must be strictly between -89 and 89 degrees')
        object.__setattr__(self, 'display_mode', DisplayMode(self.display_mode))
        object.__setattr__(self, 'receiver_fov_shape', ReceiverFovShape(self.receiver_fov_shape))

    @classmethod
    def from_settings(cls, values):
        return cls(**{f.name: values[f.name] for f in fields(cls) if f.name in values})

    @property
    def fov_degrees(self):
        """Return (horizontal, vertical); ratio is angular, not screen aspect ratio.

        tan(d/2)^2 = tan(h/2)^2 + tan(v/2)^2, with h/v = ratio.
        Bisection avoids approximation by dividing the diagonal angle directly.
        """
        ratio = self.horizontal_vertical_fov_ratio
        diagonal = math.radians(self.diagonal_fov_deg)
        target = math.tan(diagonal / 2) ** 2
        low, high = 0.0, diagonal / max(1.0, ratio)
        for _ in range(80):
            vertical = (low + high) / 2
            value = math.tan(vertical / 2)**2 + math.tan(ratio * vertical / 2)**2
            if value < target:
                low = vertical
            else:
                high = vertical
        vertical = (low + high) / 2
        return math.degrees(ratio * vertical), math.degrees(vertical)

    @property
    def horizontal_fov(self):
        return self.fov_degrees[0]

    @property
    def vertical_fov(self):
        return self.fov_degrees[1]

    @property
    def active_eyes(self):
        return (self.display_mode != DisplayMode.MONOCULAR_RIGHT,
                self.display_mode != DisplayMode.MONOCULAR_LEFT)
