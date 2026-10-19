from pathlib import Path
import os
root = Path(os.environ['GHOST_BUILD_SOURCE']) / 'packaging/windows'
manifest = Path(os.environ['GHOST_RELEASE_MANIFEST'])
a = Analysis([str(root/'setup.py')], pathex=[str(root)], datas=[(str(manifest),'.')],
             excludes=['torch','funasr','numpy','PySide6','PyQt5','PyQt6','PIL'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,a.binaries,a.datas,[],name='GhostReflex-Setup',console=False,upx=False)
