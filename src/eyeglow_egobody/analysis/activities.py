"""Read-only annotations and paired, half-open activity intervals."""
from dataclasses import dataclass
from pathlib import Path
import csv
import hashlib
import re

UNDEFINED = '<undefined>'


def normalize(label):
    return re.sub(r'[\s_]+', '_', re.sub(r'_clip\d+$', '', label.strip())).strip('_')


@dataclass(frozen=True)
class Annotation:
    source_id: str
    recording: str
    body: int
    start: int
    end: int
    original: str
    label: str


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    annotations: tuple

    def labels(self, person):
        return tuple(sorted({a.label for a in self.annotations[person]})) or (UNDEFINED,)


class ActivityCatalog:
    def __init__(self, path):
        self.path = Path(path)
        raw = self.path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.by_recording = {}
        labels = {UNDEFINED}
        for index, row in enumerate(csv.DictReader(raw.decode('utf-8-sig').splitlines())):
            original = row['body_0_des'].strip()
            item = Annotation(str(index), row['recording_name'], int(row['body_idx_0'].split()[0]),
                              int(row['frame_interval_start']), int(row['frame_interval_end']),
                              original, normalize(original))
            if item.body not in (0, 1) or item.end <= item.start or not item.label:
                raise ValueError(f'Invalid activity annotation at row {index + 2}')
            self.by_recording.setdefault(item.recording, []).append(item)
            labels.add(item.label)
        self.labels = tuple(sorted(labels))

    def segments(self, info, selections):
        # The declared last frame is present, but has no following timestamp.
        # Its unobserved duration is deliberately not invented.
        rows = self.by_recording.get(info.name, ())
        edges = {info.start, info.end}
        for row in rows:
            edges.update((max(info.start, min(info.end, row.start)),
                          max(info.start, min(info.end, row.end))))
        edges = sorted(edges)
        for start, end in zip(edges, edges[1:]):
            active = tuple(tuple(a for a in rows if a.body == body and a.start <= start < a.end)
                           for body in info.body_indices)
            segment = Segment(start, end, active)
            if all(set(segment.labels(p)) & set(selections[p]) for p in range(2)):
                yield segment
