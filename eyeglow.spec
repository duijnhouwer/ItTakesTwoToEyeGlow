# Build from the repository root: python -m PyInstaller --clean --noconfirm eyeglow.spec
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

hidden = collect_submodules('pyvista') + collect_submodules('vtkmodules')
# Fit pickles import these modules dynamically through ArrayUnpickler. Include
# both NumPy namespace generations so the build can read older dataset files.
hidden += ['numpy.core.multiarray', 'numpy.core.numeric',
           'numpy._core.multiarray', 'numpy._core.numeric']
data = collect_data_files('pyvista') + copy_metadata('pyvista') + collect_data_files('imageio_ffmpeg')
data.append(('config/settings_factory_default.json', 'config'))
data.append(('src/eyeglow_egobody/resources/icons/ittakestwotoeyeglow.png', 'icons'))
binaries = []
if sys.platform.startswith('linux'):
    from PySide6.QtCore import qVersion
    import platform
    plugin_root = Path('src/eyeglow_egobody/resources/qt_plugins') / qVersion() / f'linux-{platform.machine()}'
    plugin = plugin_root / 'wayland-decoration-client/libqadwaitadecorations.so'
    if platform.machine() == 'x86_64' and not plugin.is_file():
        raise RuntimeError('Build the matching window decoration plugin with scripts/build_window_decoration.py first.')
    if plugin.is_file():
        binaries.append((str(plugin), str(plugin.parent.relative_to('src'))))
        data.append(('third_party/qadwaitadecorations', 'licenses/qadwaitadecorations'))
a = Analysis(['scripts/launch.py'], pathex=['src'], binaries=binaries, datas=data,
             hiddenimports=hidden, hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['PyQt5','PyQt6','PySide2','tkinter'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ItTakesTwoToEyeGlow',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ItTakesTwoToEyeGlow')
