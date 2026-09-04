# Building friend Pitstop launchers

Pack is **not** bundled in the app. Host it (GitHub Releases) and bake the manifest URL — see [HOSTING.md](HOSTING.md).

## Prerequisites

- Python 3.10+
- `pip install pyinstaller`

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

## 3. Mac `.app`

```bash
python3 -m PyInstaller launcher/pitstop-mac.spec --noconfirm
# → dist/Pitstop.app
```

Dev UI (uses local repo pack if no URL):

```bash
python3 launcher/gui.py
```

## 4. Windows `.exe` (on Windows, later)

```bat
python -m PyInstaller launcher\pitstop-win.spec --noconfirm
```

## Friend handoff

See [FRIENDS.md](FRIENDS.md).
