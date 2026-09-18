"""All application output paths pass through the dataset guard."""
from pathlib import Path
from uuid import uuid4
from eyeglow_egobody.runtime_paths import default_dataset

DATASET = default_dataset()

def safe_directory(path):
    path = Path(path).expanduser().resolve()
    if path == DATASET or DATASET in path.parents or any(p.name == 'egobody-data' for p in (path,*path.parents)):
        raise ValueError('The EgoBody dataset is read-only. Choose another output directory.')
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_export(root, prefix):
    path = safe_directory(root) / f'{prefix}-{uuid4().hex[:12]}'
    path.mkdir(exist_ok=False)
    return path


def safe_destination(path):
    """Check the resolved file itself as well as its parent (including symlinks)."""
    path = Path(path).expanduser().resolve()
    if path == DATASET or DATASET in path.parents or any(p.name == 'egobody-data' for p in (path,*path.parents)):
        raise ValueError('The EgoBody dataset is read-only. Choose another output file.')
    safe_directory(path.parent)
    if path.is_dir():
        raise ValueError('Choose a file name, not a directory.')
    return path
