# Pitstop

Private Mario Kart Wii launcher for Dolphin: **Wiimmfi**, **separate save**, optional **custom title screen**, no permanent ISO patch.

## Test on your Mac (right now)

1. **One-time setup** (installs patch + enables Wiimmfi cheat for RMCE01):

```bash
cd /Users/madesh/Pitstop
python3 launcher/pitstop.py setup
```

2. **Launch**:

```bash
python3 launcher/pitstop.py launch
```

Dolphin should boot your WBFS with:
- A **separate Dolphin user folder** (`~/.config/pitstop/dolphin-user`) so vanilla licenses stay untouched
- Private WWFC + force 150cc + everything unlocked on new Pitstop licenses

3. **In game**: Nintendo WFC → Friends → create a friend room. Host presses A to start → pick VS Race + race count. Track voting is per race. Pitstop forces **150cc** for the host.

## Custom title screen

1. Extract `Title.szs` and `Title_U.szs` from your dump (Wiimms SZS Tools / BrawlCrate).
2. Edit the TPL textures inside.
3. Copy them to:

```
~/Library/Application Support/Dolphin/Load/Riivolution/Pitstop/assets/UI/
```

4. Run `python3 launcher/pitstop.py launch` again.

## Paths (defaults)

| Setting | Default |
|---------|---------|
| Dolphin | `/Applications/Dolphin.app/Contents/MacOS/Dolphin` |
| User folder | `~/Library/Application Support/Dolphin` |
| Game | Your MKWii WBFS path |

Change with:

```bash
python3 launcher/pitstop.py configure
```

## Manual test (without launcher)

1. Copy `patch/` to `~/Library/Application Support/Dolphin/Load/Riivolution/Pitstop/`
2. In Dolphin: right-click MKWii → **Start with Riivolution Patches** → enable **Pitstop**
3. Enable `$Pitstop Wiimmfi` under Config → Gecko codes for RMCE01

## Notes

- Your WBFS file is never modified.
- Friend rooms: host picks race count after pressing A; Pitstop forces 150cc. Track voting is per race (vanilla).
- Disable `$NewWFC` in Dolphin gecko codes when using Pitstop (only one WFC server at a time).
