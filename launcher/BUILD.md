# Building friend Pitstop launchers

Pack is **not** bundled in the app. Host it (GitHub Releases) and bake the manifest URL — see [HOSTING.md](HOSTING.md).

## Prerequisites

- Python 3.10+ with working **tkinter** (macOS Homebrew: `brew install python-tk@3.12` and build with that Python — system `/usr/bin/python3` Tk often breaks on newer macOS)
- `pip install pyinstaller` (in a venv)

## Dev UI (look at the launcher)

```bash
# Mac — use Homebrew Python that has python-tk
/opt/homebrew/bin/python3.12 launcher/gui.py
```

## 1. Build + publish pack

```bash
python3 launcher/build_pack.py --platform both --zip \
  --version pitstop-private-wwfc-v7-unlock \
  --release-url https://github.com/YOU/Pitstop/releases/download/pack-v7
# Upload dist/manifest.json + dist/pitstop-pack-*.zip to that release
```

## 2. Bake manifest URL into the app

In `launcher/pitstop.py` set:

```python
DEFAULT_PACK_MANIFEST_URL = "https://github.com/YOU/Pitstop/releases/latest/download/manifest.json"
```

## 3. Mac `.app` → `.dmg`

```bash
# Prefer the same Homebrew python3.12 that has python-tk
python3.12 -m PyInstaller launcher/pitstop-mac.spec --noconfirm
# → dist/Pitstop.app (uses launcher/assets/pitstop.icns)

# Optional single-file download for the website:
hdiutil create -volname Pitstop -srcfolder dist/Pitstop.app -ov -format UDZO dist/Pitstop.dmg
```

Ship `dist/Pitstop.dmg` (or the `.app` zip). Website OS detection can come later.

## 4. Windows `.exe` (build on Windows)

```bat
python -m PyInstaller launcher\pitstop-win.spec --noconfirm
```

Ship `dist/Pitstop.exe` (one-file) or the folder build from the spec.

## Friend handoff

See [FRIENDS.md](FRIENDS.md). First launch runs the welcome wizard (permission → paths → pack download).
