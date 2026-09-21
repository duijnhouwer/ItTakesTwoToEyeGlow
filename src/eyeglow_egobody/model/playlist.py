"""Selected activity-pair clips on one continuous 30 Hz timeline."""
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
    name = 'activities_playlist'

    def __init__(self, infos, catalog, selections):
        self.selections = tuple(tuple(sorted(s)) for s in selections)
        self.clips = []
        self.frame_count = 0
        for info in sorted(infos, key=lambda i: i.name):
            for segment in catalog.segments(info, self.selections):
                self.clips.append(PlaylistClip(info, segment, self.frame_count))
                self.frame_count += segment.end - segment.start
        self.offsets = [c.offset for c in self.clips]
        self.pair_clip_offsets = []
        previous = None
        for clip in self.clips:
            combination = tuple(clip.segment.labels(person) for person in range(2))
            discontinuous = (previous is None or previous.info.name != clip.info.name
                             or previous.segment.end != clip.segment.start)
            previous_combination = (None if previous is None else
                                    tuple(previous.segment.labels(person)
                                          for person in range(2)))
            if discontinuous or combination != previous_combination:
                self.pair_clip_offsets.append(clip.offset)
            previous = clip

    @property
    def duration_s(self):
        return self.frame_count / self.fps

    @property
    def summary(self):
        return (f'{len(self.pair_clip_offsets)} activity pair clips · '
                f'{self.duration_s:.2f} s combined duration')

    def locate(self, frame):
        if not 0 <= frame < self.frame_count:
            raise IndexError('Frame outside activities playlist')
        clip = self.clips[bisect_right(self.offsets, frame)-1]
        return clip, clip.segment.start + frame - clip.offset

    def previous_pair_clip_offset(self, frame):
        index = bisect_right(self.pair_clip_offsets, frame) - 1
        return self.pair_clip_offsets[index - 1] if index > 0 else None

    def next_pair_clip_offset(self, frame):
        index = bisect_right(self.pair_clip_offsets, frame)
        return (self.pair_clip_offsets[index]
                if index < len(self.pair_clip_offsets) else None)
