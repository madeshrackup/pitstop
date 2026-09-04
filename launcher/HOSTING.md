# Hosting the Pitstop pack (update without reshipping the app)

Friends’ `Pitstop.app` / `.exe` downloads the pack on **first setup** and **Check for updates**. You only re-upload pack zips when GCT/UI/tools change.

## Manifest

`manifest.json`:

```json
{
  "version": "pitstop-private-wwfc-v7-unlock",
  "notes": "Pitstop friend pack (no title THPs)",
  "mac": {
    "url": "https://github.com/YOU/Pitstop/releases/download/pack-v7/pitstop-pack-mac.zip",
    "sha256": "…"
  },
  "win": {
    "url": "https://github.com/YOU/Pitstop/releases/download/pack-v7/pitstop-pack-win.zip",
    "sha256": "…"
  }
}
```

Bump `version` whenever friends should re-download. The launcher compares against `~/.config/pitstop/pack/installed.json`.

## Build + upload (GitHub Releases)

```bash
# 1) Build pack + zips (fill in your release tag URL)
python3 launcher/build_pack.py --platform both --zip \
  --version pitstop-private-wwfc-v7-unlock \
  --release-url https://github.com/YOU/Pitstop/releases/download/pack-v7

# 2) Create a GitHub release tagged e.g. pack-v7 and upload:
#    - dist/manifest.json
#    - dist/pitstop-pack-mac.zip
#    - dist/pitstop-pack-win.zip

gh release create pack-v7 \
  dist/manifest.json \
  dist/pitstop-pack-mac.zip \
  dist/pitstop-pack-win.zip \
  --title "Pitstop pack v7" \
  --notes "Private WWFC + 150cc + unlock"
```

Point the launcher at the **latest** manifest (stable URL):

```text
https://github.com/YOU/Pitstop/releases/latest/download/manifest.json
```

Or a fixed tag URL if you prefer explicit pins.

## Wire the URL into the app

Before building `Pitstop.app`:

1. Set in `launcher/pitstop.py`:

   ```python
   DEFAULT_PACK_MANIFEST_URL = "https://github.com/YOU/Pitstop/releases/latest/download/manifest.json"
   ```

2. Or set for local testing:

   ```bash
   export PITSTOP_PACK_MANIFEST_URL='https://github.com/YOU/Pitstop/releases/latest/download/manifest.json'
   ```

3. Or after install, friends’ `~/.config/pitstop/config.json`:

   ```json
   "pack_manifest_url": "https://github.com/YOU/Pitstop/releases/latest/download/manifest.json"
   ```

Then rebuild the Mac app (no pack bundled):

```bash
python3 -m PyInstaller launcher/pitstop-mac.spec --noconfirm
```

## Private vs public

- **Public release**: simplest; pack has no game dump, only your GCT/UI/tools.
- **Private repo**: GitHub asset URLs need auth; use a public release, a GCS/S3 bucket next to your server, or a DuckDNS HTTPS static file instead.

## Update flow for you

1. Change GCT / UI / bump `PATCHER_VERSION` / `build_pack.py --version`
2. `build_pack.py --zip --release-url …`
3. `gh release create` (or upload over the same tag / new tag + `latest`)
4. Friends click **Setup / Update** — no new `.app` needed
