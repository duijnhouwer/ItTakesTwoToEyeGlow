"""Playback state with elapsed-time advancement, independent of GUI imports."""
from dataclasses import dataclass
import math

@dataclass
class PlaybackState:
    frame_count: int
    fps: float
    frame: int = 0
    playing: bool = False
    speed: float = 1.0
    loop: bool = True
    position: float = 0.0

    def seek(self, frame):
        self.frame = max(0, min(self.frame_count-1, int(frame)))
        self.position = float(self.frame)

    def advance(self, elapsed):
        if not self.playing:
            return
        self.position += max(0, elapsed)*self.fps*self.speed
        if self.position >= self.frame_count:
            if self.loop:
                self.position %= self.frame_count
            else:
                self.position = self.frame_count-1
                self.playing = False
        self.frame = min(self.frame_count-1, math.floor(self.position))
