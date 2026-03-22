# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['mysql', 'mysql.connector']
hiddenimports += collect_submodules('mysql.connector')


a = Analysis(
    ['C:\\fullstack\\jhcis-node-agent\\node-script\\desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\fullstack\\jhcis-node-agent\\node-script\\.env.example', '.'), ('C:\\fullstack\\jhcis-node-agent\\node-script\\config.example.json', '.')],
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
    name='JHCISSyncDesktop',
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
    strip=False,
    upx=True,
    upx_exclude=[],
    name='JHCISSyncDesktop',
)
