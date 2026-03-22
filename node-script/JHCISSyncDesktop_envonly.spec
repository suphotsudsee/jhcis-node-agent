# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['mysql', 'mysql.connector']
hiddenimports += collect_submodules('mysql.connector')

project_root = Path.cwd()
docs_candidates = [
    project_root / 'docs' / 'queries.sql',
    project_root.parent / 'docs' / 'queries.sql',
]
datas = [
    ('.\\.env.example', '.'),
    ('install_service.ps1', '.'),
    ('uninstall_service.ps1', '.'),
]

for docs_path in docs_candidates:
    if docs_path.exists():
        datas.append((str(docs_path), 'docs'))
        break

service_dist = project_root / 'dist' / 'JHCISSyncService'
service_tree = None
if service_dist.exists():
    service_tree = Tree(str(service_dist), prefix='JHCISSyncService')

a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='JHCISSyncDesktop_envonly',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    *( [service_tree] if service_tree is not None else [] ),
    strip=False,
    upx=True,
    upx_exclude=[],
    name='JHCISSyncDesktop_envonly',
)
