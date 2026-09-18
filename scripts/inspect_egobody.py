"""Print a bounded read-only inspection; optionally validate a complete recording.

Run with .venv/bin/python scripts/inspect_egobody.py ../egobody-data.
Redirect stdout into code-repo/.runtime to save the report.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from eyeglow_egobody.egobody.discovery import discover
from eyeglow_egobody.egobody.loading import calibration, load_recording, read_fit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('dataset',type=Path)
parser.add_argument('--recording')
parser.add_argument('--model-dir',type=Path)
args = parser.parse_args()
infos = discover(args.dataset)
if not infos:
    parser.error('No paired SMPL-X recording directories found')
info = next((i for i in infos if i.name == args.recording), None) if args.recording else infos[0]
if info is None:
    parser.error('Recording not found')
files = info.frames()
report = dict(recordings=len(infos), splits=dict(Counter(i.split for i in infos)),
              representative=info.name, scene=info.scene, body_indices=info.body_indices,
              genders=info.genders, frame_range=[info.start,info.end],
              role_file_counts=[len(f) for f in files], paired_files=len(set(files[0])&set(files[1])),
              kinect_to_scene=calibration(info).tolist(), samples=[])
for group in files:
    if not group:
        continue
    path = group[min(group)]
    data = read_fit(path)
    report['samples'].append(dict(path=str(path),fields={k:dict(shape=list(v.shape),dtype=str(v.dtype))
                                                       if hasattr(v,'shape') else v for k,v in data.items()}))
if args.model_dir:
    recording = load_recording(info,args.model_dir)
    report['normalized'] = recording.metadata
print(json.dumps(report,indent=2))
