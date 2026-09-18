# Build from the repository root: python -m PyInstaller --clean --noconfirm eyeglow.spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

hidden = collect_submodules('pyvista') + collect_submodules('vtkmodules')
data = collect_data_files('pyvista') + copy_metadata('pyvista') + collect_data_files('imageio_ffmpeg')
a = Analysis(['scripts/launch.py'], pathex=['src'], binaries=[], datas=data,
             hiddenimports=hidden, hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['PyQt5','PyQt6','PySide2','tkinter'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='EyeGlowEgoBody',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='EyeGlowEgoBody')
