"""A compact index of selected paired clips on one continuous 30 Hz timeline."""
from bisect import bisect_right
from dataclasses import dataclass

PLAYLIST_KEYS = ('playlist_actions_a', 'playlist_actions_b')


@dataclass(frozen=True)
class PlaylistClip:
    info: object
    segment: object
    offset: int


class ActivitiesPlaylist:
    fps = 30.

    def __init__(self, infos, catalog, selections):
        self.selections = tuple(tuple(sorted(s)) for s in selections)
        self.clips = []
        self.frame_count = 0
        for info in sorted(infos, key=lambda i: i.name):
            for segment in catalog.segments(info, self.selections):
                self.clips.append(PlaylistClip(info, segment, self.frame_count))
                self.frame_count += segment.end - segment.start
        self.offsets = [c.offset for c in self.clips]

    @property
    def duration_s(self):
        return self.frame_count / self.fps

    @property
    def summary(self):
        return f'{len(self.clips)} clips · {self.duration_s:.2f} s combined duration'

    def locate(self, frame):
        if not 0 <= frame < self.frame_count:
            raise IndexError('Frame outside activities playlist')
        clip = self.clips[bisect_right(self.offsets, frame)-1]
        return clip, clip.segment.start + frame - clip.offset
