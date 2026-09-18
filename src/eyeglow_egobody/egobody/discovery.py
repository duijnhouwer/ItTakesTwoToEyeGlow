"""Read-only discovery of the paired SMPL-X release directories."""
from dataclasses import dataclass
from pathlib import Path
import csv


@dataclass(frozen=True)
class RecordingInfo:
    root: Path
    name: str
    split: str
    scene: str
    start: int
    end: int
    body_indices: tuple[int, int]  # camera wearer, interactee
    genders: tuple[str, str]
    folders: tuple[Path, Path]

    def frames(self):
        return tuple({int(p.parent.name[6:]): p for p in folder.glob('frame_*/000.pkl')
                      if p.parent.name[6:].isdigit() and self.start <= int(p.parent.name[6:]) <= self.end}
                     for folder in self.folders)


def discover(root):
    root = Path(root).resolve()
    with (root / 'data_info_release.csv').open(newline='') as stream:
        metadata = list(csv.DictReader(stream))
    with (root / 'data_splits.csv').open(newline='') as stream:
        splits = {name: split for row in csv.DictReader(stream)
                  for split, name in row.items() if name}
    results = []
    for row in metadata:
        name = row['recording_name']
        split = splits.get(name)
        if split not in ('train', 'val', 'test'):
            continue
        interactee = int(row['body_idx_fpv'].split()[0])
        if interactee not in (0, 1):
            raise ValueError(f'{name}: invalid interactee body index')
        indices = (1-interactee, interactee)
        folders = tuple(root / f'smplx_{role}_{split}' / name / f'body_idx_{idx}' / 'results'
                        for role, idx in zip(('camera_wearer', 'interactee'), indices))
        if all(folder.is_dir() for folder in folders):
            start, end = int(row['start_frame']), int(row['end_frame'])
            if start > end:
                raise ValueError(f'{name}: reversed frame interval')
            results.append(RecordingInfo(root, name, split, row['scene_name'], start, end,
                                        indices, tuple(row[f'body_idx_{i}'].split()[1] for i in indices), folders))
    return sorted(results, key=lambda item: item.name)
