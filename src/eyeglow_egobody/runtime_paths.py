"""Paths for source runs and the repository's PyInstaller one-folder build."""
from pathlib import Path
import sys


def project_root():
    # Frozen __file__ points into dist/ItTakesTwoToEyeGlow/_internal, not src/.
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parents[2]
    return Path(__file__).resolve().parents[2]


def settings_resource_path(filename):
    """Locate immutable packaged settings without treating the install as writable."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'config' / filename
    return project_root() / 'config' / filename


def icon_resource_path():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'icons' / 'ittakestwotoeyeglow.png'
    return Path(__file__).resolve().parent / 'resources' / 'icons' / 'ittakestwotoeyeglow.png'


def assets_root():
    return project_root().parent / 'assets'


def default_dataset():
    return assets_root() / 'egobody-data'


def default_models():
    return assets_root() / 'models_smplx_v1_1' / 'models' / 'smplx'
