# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [
    ('app_icon.ico', '.'),
    ('app_icon.png', '.'),
]
binaries = []
hiddenimports = [
    'darkdetect',
    'mutagen.mp3',
    'mutagen.id3',
    'mutagen.mp4',
    'mutagen.flac',
    'mutagen.wave',
    'PIL._tkinter_finder',
]

# Comprehensive collection of core packages
for pkg in ['customtkinter', 'yt_dlp', 'mutagen', 'PIL', 'certifi', 'requests']:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'tensorflow', 'scipy', 'numpy', 'matplotlib', 'pandas', 'IPython', 'jupyter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ArgusStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)
