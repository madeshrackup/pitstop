# Pitstop website

Minimal download page for Vercel.

## Deploy

From this folder:

```bash
npx vercel
```

Or in the Vercel dashboard: import the GitHub repo and set **Root Directory** to `website`.

## Downloads

Links point at GitHub Releases:

- macOS: `…/latest/download/Pitstop.dmg` (live)
- Windows: `…/latest/download/Pitstop.exe` (enable in `main.js` when uploaded)

After you upload `Pitstop.exe`, set `PLATFORMS.win.available = true` in `main.js`.
