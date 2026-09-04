# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec → Pitstop.exe (Windows).

Pack is downloaded at runtime (see HOSTING.md) — not bundled.

Build on Windows:
  python -m PyInstaller launcher/pitstop-win.spec --noconfirm
  → dist/Pitstop.exe
"""

from pathlib import Path

block_cipher = None
SPECDIR = Path(SPECPATH)

a = Analysis(
    [str(SPECDIR / "gui.py")],
    pathex=[str(SPECDIR)],
    binaries=[],
    datas=[],
    hiddenimports=["pitstop"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Pitstop",
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
)
