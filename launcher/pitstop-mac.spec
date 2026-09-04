# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec → Pitstop.app (macOS).

Pack is downloaded at runtime (see HOSTING.md) — not bundled.

Build:
  # Set DEFAULT_PACK_MANIFEST_URL in pitstop.py first
  pip install pyinstaller
  python3 -m PyInstaller launcher/pitstop-mac.spec --noconfirm
  → dist/Pitstop.app
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
    [],
    exclude_binaries=True,
    name="Pitstop",
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Pitstop",
)

app = BUNDLE(
    coll,
    name="Pitstop.app",
    icon=None,
    bundle_identifier="org.pitstop.launcher",
    info_plist={
        "CFBundleName": "Pitstop",
        "CFBundleDisplayName": "Pitstop",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
    },
)
