"""Read-only metadata audit. Output must be outside the dataset."""
import argparse
import hashlib
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('dataset',type=Path)
args = parser.parse_args()
digest = hashlib.sha256()
count = 0
for root, directories, files in os.walk(args.dataset):
    directories.sort()
    for name in sorted(directories + files):
        path = Path(root)/name
        stat = path.lstat()
        record = (str(path.relative_to(args.dataset)),stat.st_mode,stat.st_size,stat.st_mtime_ns)
        digest.update(json.dumps(record).encode())
        count += 1
print(json.dumps({'entries':count,'metadata_sha256':digest.hexdigest()},indent=2))
