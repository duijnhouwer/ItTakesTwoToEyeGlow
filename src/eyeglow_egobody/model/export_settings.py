"""Numeric video export settings, independent of Qt and rendering."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class VideoSettings:
    size: tuple[int, int] | None = None
    fps: float = 30.0
    quality: int = 90

    def __post_init__(self):
        if not math.isfinite(self.fps) or not 1 <= self.fps <= 120:
            raise ValueError('Frame rate must be between 1 and 120 fps.')
        if not isinstance(self.quality, int) or not 0 <= self.quality <= 100:
            raise ValueError('Quality must be an integer between 0 and 100.')
        if self.size is not None and (len(self.size) != 2 or any(
                not isinstance(value, int) or value < 1 for value in self.size)):
            raise ValueError('Frame dimensions must be positive integers.')

    @property
    def crf(self):
        return round(51 * (100-self.quality) / 100)
