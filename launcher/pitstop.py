#!/usr/bin/env python3
"""Pitstop launcher — private WWFC online + separate save + friend GUI."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable
from dataclasses import dataclass

APP_NAME = "Pitstop"
GAME_ID = "RMCE01"
# Bump when switching private-server GCT / payload domain / UI branding.
PATCHER_VERSION = "pitstop-private-wwfc-v7-unlock"

# Bake your hosted manifest URL before shipping (GitHub Releases recommended).
# Override: env PITSTOP_PACK_MANIFEST_URL or config.json "pack_manifest_url".
DEFAULT_PACK_MANIFEST_URL = os.environ.get(
    "PITSTOP_PACK_MANIFEST_URL",
    "https://github.com/madeshrackup/pitstop/releases/latest/download/manifest.json",
)

ProgressFn = Callable[[str], None]


def _bundle_search_roots() -> list[Path]:
    """PyInstaller .app can split datas across Frameworks + Resources."""
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            roots.append(Path(sys._MEIPASS))
        exe = Path(sys.executable).resolve()
        # Contents/MacOS/Pitstop → Contents/{Frameworks,Resources}
        contents = exe.parent.parent
        for name in ("Frameworks", "Resources", "MacOS"):
            roots.append(contents / name)
        roots.append(exe.parent)
    roots.append(Path(__file__).resolve().parent.parent)
    # de-dupe preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for r in roots:
        try:
            key = r.resolve()
        except OSError:
            key = r
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def resource_root() -> Path:
    """Repo root in dev; first PyInstaller bundle root when frozen."""
    return _bundle_search_roots()[0]


def pack_install_dir() -> Path:
    """Downloaded pack (updated without reshipping the app)."""
    path = config_path().parent / "pack"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pack_version_path() -> Path:
    return pack_install_dir() / "installed.json"


def host_platform() -> str:
    return "win" if platform.system() == "Windows" else "mac"


def patch_src() -> Path:
    dl = pack_install_dir() / "patch"
    if dl.is_dir() and any(dl.iterdir()):
        return dl
    for root in _bundle_search_roots():
        for cand in (root / "pack" / "patch", root / "patch"):
            if cand.is_dir() and any(cand.iterdir()):
                return cand
    return pack_install_dir() / "patch"


def tools_bin() -> Path:
    plat = host_platform()
    dl = pack_install_dir() / "tools" / plat
    if dl.is_dir() and any(dl.iterdir()):
        return dl
    for root in _bundle_search_roots():
        for cand in (root / "pack" / "tools" / plat, root / "tools" / plat):
            if cand.is_dir() and any(cand.iterdir()):
                return cand
    return pack_install_dir() / "tools" / plat


def pitstop_gct() -> Path:
    return patch_src() / "cheats" / "pitstop-rmced00.gct"


def wiilink_gct() -> Path:
    return patch_src() / "cheats" / "wiilink-rmced00.gct"


def wiilink_txt() -> Path:
    return patch_src() / "cheats" / "wiilink-rmced00.txt"


DEFAULT_CONFIG = {
    "dolphin_path": "",
    # Main Dolphin folder (vanilla saves/controllers live here — never used as Pitstop NAND)
    "dolphin_user_path": "",
    # Isolated Dolphin user for Pitstop launches (own Wii NAND / licenses)
    "pitstop_user_path": "",
    "game_path": "",
    # HTTPS URL to manifest.json (GitHub Releases /latest/download/manifest.json)
    "pack_manifest_url": DEFAULT_PACK_MANIFEST_URL,
    # License slot 0–3 shown under the sidebar logo, or null
    "primary_license_index": None,
    # Set True after the first-run wizard finishes successfully
    "setup_complete": False,
}


def config_path() -> Path:
    if platform.system() == "Windows":
        base = Path.home() / "AppData" / "Roaming" / APP_NAME
    else:
        base = Path.home() / ".config" / APP_NAME.lower()
    base.mkdir(parents=True, exist_ok=True)
    return base / "config.json"


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        cfg = DEFAULT_CONFIG.copy()
        cfg["dolphin_user_path"] = default_dolphin_user()
        cfg["pitstop_user_path"] = default_pitstop_user()
        cfg["dolphin_path"] = default_dolphin_binary()
        save_config(cfg)
        return cfg
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    if not merged.get("dolphin_user_path"):
        merged["dolphin_user_path"] = default_dolphin_user()
    if not merged.get("pitstop_user_path"):
        merged["pitstop_user_path"] = default_pitstop_user()
    return merged


def save_config(cfg: dict) -> None:
    with config_path().open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def default_dolphin_user() -> str:
    if platform.system() == "Windows":
        return str(Path.home() / "Documents" / "Dolphin Emulator")
    if platform.system() == "Darwin":
        return str(Path.home() / "Library" / "Application Support" / "Dolphin")
    return str(Path.home() / ".local" / "share" / "dolphin-emu")


def default_pitstop_user() -> str:
    """Dedicated Dolphin user folder so Pitstop never shares vanilla MKWii NAND/saves."""
    return str(config_path().parent / "dolphin-user")


def ensure_pitstop_user(cfg: dict) -> Path:
    """Create isolated Dolphin user; copy controller/GFX settings from main Dolphin.

    Never copies Wii NAND / saves. Never overwrites Pitstop's Dolphin.ini after first
    create (that used to re-import vanilla WirelessMac and share Wii identity).
    """
    main = Path(cfg.get("dolphin_user_path") or default_dolphin_user())
    pit = Path(cfg.get("pitstop_user_path") or default_pitstop_user())
    pit.mkdir(parents=True, exist_ok=True)
    (pit / "Config").mkdir(parents=True, exist_ok=True)
    (pit / "GameSettings").mkdir(parents=True, exist_ok=True)
    (pit / "Wii").mkdir(parents=True, exist_ok=True)

    # Input / graphics only — not Dolphin.ini (WirelessMac / NAND paths).
    cfg_names = (
        "GCPadNew.ini",
        "WiimoteNew.ini",
        "GFX.ini",
        "Hotkeys.ini",
        "Logger.ini",
    )
    src_cfg = main / "Config"
    dst_cfg = pit / "Config"
    if src_cfg.is_dir():
        for name in cfg_names:
            src = src_cfg / name
            dst = dst_cfg / name
            if src.exists() and (not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime):
                shutil.copy2(src, dst)

    _ensure_isolated_dolphin_ini(pit, main)
    return pit


def _ini_get(content: str, key: str) -> str | None:
    for line in content.splitlines():
        if line.strip().startswith(f"{key}"):
            parts = line.split("=", 1)
            if len(parts) == 2 and parts[0].strip() == key:
                return parts[1].strip()
    return None


def _ini_set(content: str, key: str, value: str) -> str:
    lines = content.splitlines()
    out: list[str] = []
    found = False
    for line in lines:
        if line.strip().startswith(f"{key}") and "=" in line and line.split("=", 1)[0].strip() == key:
            out.append(f"{key} = {value}")
            found = True
        else:
            out.append(line)
    if not found:
        # Prefer [General] section
        inserted = False
        final: list[str] = []
        for line in out:
            final.append(line)
            if not inserted and line.strip() == "[General]":
                final.append(f"{key} = {value}")
                inserted = True
        if not inserted:
            final.extend(["[General]", f"{key} = {value}"])
        return "\n".join(final).rstrip() + "\n"
    return "\n".join(out).rstrip() + "\n"


def _ensure_isolated_dolphin_ini(pit: Path, main: Path) -> None:
    """Keep a Pitstop-owned Dolphin.ini with its own WirelessMac (not vanilla's)."""
    dst = pit / "Config" / "Dolphin.ini"
    src = main / "Config" / "Dolphin.ini"
    if not dst.exists():
        if src.exists():
            shutil.copy2(src, dst)
        else:
            dst.write_text("[General]\nNANDRootPath = \nLoadPath = \n", encoding="utf-8")

    text = dst.read_text(encoding="utf-8", errors="replace")
    main_mac = ""
    if src.exists():
        main_mac = _ini_get(src.read_text(encoding="utf-8", errors="replace"), "WirelessMac") or ""
    pit_mac = _ini_get(text, "WirelessMac") or ""

    # Pin NAND to the Pitstop user Wii folder (never vanilla Application Support/Dolphin).
    text = _ini_set(text, "NANDRootPath", str((pit / "Wii").resolve()))
    text = _ini_set(text, "LoadPath", "")

    # Unique Wii wireless MAC so Pitstop is not the same device as vanilla Dolphin.
    if not pit_mac or (main_mac and pit_mac == main_mac):
        # Stable Pitstop-local MAC (locally administered bit set via 02:…).
        text = _ini_set(text, "WirelessMac", "02:50:17:50:00:01")

    dst.write_text(text, encoding="utf-8")


def ensure_pitstop_save(cfg: dict) -> Path:
    """Ensure Pitstop NAND save directory exists under the isolated user only.

    Canonical save: {pitstop_user}/Wii/title/00010004/524d4345/data/rksys.dat
    Created by the game on first Play. Never reads/writes vanilla Dolphin.
    """
    import rksys as rksys_mod

    path = rksys_mod.nand_rksys_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Remove obsolete Riivolution external save tree (old redirect) so nothing
    # confuses which file is authoritative.
    pit = Path(cfg.get("pitstop_user_path") or default_pitstop_user())
    stale_ext = pit / "Load" / "Riivolution" / APP_NAME / "riivolution" / "save"
    if stale_ext.is_dir():
        try:
            shutil.rmtree(stale_ext)
        except OSError:
            pass
    return path


def vanilla_rksys_path(cfg: dict) -> Path | None:
    """Vanilla Dolphin MKWii save — for isolation checks only. Never write here."""
    main = cfg.get("dolphin_user_path") or default_dolphin_user()
    if not main:
        return None
    return Path(main) / "Wii" / "title" / "00010004" / "524d4345" / "data" / "rksys.dat"


def assert_save_isolation(cfg: dict) -> None:
    """Hard-fail if Pitstop save resolution would touch vanilla Dolphin."""
    import rksys as rksys_mod

    pit_save = rksys_mod.nand_rksys_path(cfg)
    van = vanilla_rksys_path(cfg)
    if van is not None and pit_save.resolve() == van.resolve():
        raise RuntimeError(
            "FATAL: Pitstop save path resolved to vanilla Dolphin rksys.dat — aborting."
        )
    print(f"Pitstop save (isolated): {pit_save}")
    if van is not None:
        print(f"Vanilla Dolphin save (untouched): {van}")
        print(f"  vanilla fingerprint: {rksys_mod.file_fingerprint(van)}")
    if pit_save.is_file():
        print(f"  pitstop fingerprint: {rksys_mod.file_fingerprint(pit_save)}")


def default_dolphin_binary() -> str:
    found = discover_dolphin_binary()
    if found is not None:
        return str(found)
    if platform.system() == "Windows":
        return str(Path.home() / "AppData" / "Local" / "Programs" / "Dolphin" / "Dolphin.exe")
    if platform.system() == "Darwin":
        return "/Applications/Dolphin.app/Contents/MacOS/Dolphin"
    return "/usr/bin/dolphin-emu"


def discover_dolphin_binary() -> Path | None:
    """Return a Dolphin binary if found in common install locations."""
    candidates: list[Path] = []
    system = platform.system()
    if system == "Darwin":
        for base in (Path("/Applications"), Path.home() / "Applications"):
            binary = base / "Dolphin.app" / "Contents" / "MacOS" / "Dolphin"
            candidates.append(binary)
    elif system == "Windows":
        local = Path.home() / "AppData" / "Local"
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        candidates.extend(
            [
                local / "Programs" / "Dolphin" / "Dolphin.exe",
                pf / "Dolphin" / "Dolphin.exe",
                pf86 / "Dolphin" / "Dolphin.exe",
            ]
        )
    else:
        which = shutil.which("dolphin-emu")
        if which:
            candidates.append(Path(which))
    for path in candidates:
        if path.is_file():
            return path
    return None


def normalize_dolphin_path(raw: str) -> str:
    """Resolve Dolphin.app bundles to the inner MacOS binary when needed."""
    path = Path(raw.strip())
    if platform.system() == "Darwin" and path.suffix == ".app":
        inner = path / "Contents" / "MacOS" / "Dolphin"
        if inner.is_file():
            return str(inner)
    return str(path)


def dolphin_path_ok(raw: str) -> bool:
    try:
        return Path(normalize_dolphin_path(raw)).is_file()
    except OSError:
        return False


@dataclass(frozen=True)
class PackSyncResult:
    path: Path
    version: str
    changed: bool


def cache_dir() -> Path:
    path = config_path().parent / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_tool(name: str) -> Path:
    local = tools_bin() / name
    if local.exists():
        return local
    if platform.system() == "Windows":
        exe = tools_bin() / f"{name}.exe"
        if exe.exists():
            return exe
    found = shutil.which(name)
    if found:
        return Path(found)
    raise FileNotFoundError(f"{name} not found. Expected at {local}.")


def patched_image_path() -> Path:
    return cache_dir() / "RMCE01-pitstop.wbfs"


def dump_stamp(game_path: Path) -> str:
    """Stable cache key for the patched WBFS.

    Avoids filesystem mtimes (antivirus / pack re-copy can change them and force a
    full re-extract between setup and Play).
    """
    st = game_path.stat()
    gct = resolve_gct()
    gct_hash = _sha256_file(gct) if gct.is_file() else "missing"
    pack_ver = installed_pack_version() or "none"
    # Normalize so D:/foo and D:\foo match on Windows
    game_key = str(game_path.resolve()).replace("\\", "/").casefold()
    return (
        f"{PATCHER_VERSION}\n{pack_ver}\n{gct.name}\n{gct_hash}\n"
        f"{game_key}\n{st.st_size}\n"
    )


def inject_ui_branding(fst_root: Path) -> int:
    """Copy Pitstop-branded English UI message packs into extracted FST."""
    ui_src = patch_src() / "assets" / "UI"
    names = [
        "MenuSingle_U.szs",
        "MenuMulti_U.szs",
        "Globe_U.szs",
        "Title_U.szs",
        "Channel_U.szs",
        "Title.szs",  # optional custom title-screen art
    ]
    candidates = [
        fst_root / "files" / "Scene" / "UI",
        fst_root / "DATA" / "files" / "Scene" / "UI",
        fst_root / "Scene" / "UI",
    ]
    ui_dest = next((p for p in candidates if p.is_dir()), None)
    if ui_dest is None:
        hits = list(fst_root.rglob("MenuSingle_U.szs"))
        if not hits:
            print("WARNING: could not find Scene/UI in extracted image; UI branding skipped")
            return 0
        ui_dest = hits[0].parent

    n = 0
    for name in names:
        src = ui_src / name
        if not src.exists():
            continue
        shutil.copy2(src, ui_dest / name)
        n += 1
    print(f"Injected Pitstop UI branding ({n} files) → {ui_dest}")
    return n


def inject_title_thp(fst_root: Path) -> int:
    """Replace title-screen THP videos with Pitstop still (full-screen art)."""
    thp_src = patch_src() / "assets" / "thp"
    if not thp_src.is_dir():
        return 0
    names = ["title.thp", "title_SD.thp", "title_50.thp", "title_SD_50.thp"]
    candidates = [
        fst_root / "files" / "thp" / "title",
        fst_root / "DATA" / "files" / "thp" / "title",
        fst_root / "thp" / "title",
    ]
    dest_dir = next((p for p in candidates if p.is_dir()), None)
    if dest_dir is None:
        hits = list(fst_root.rglob("title.thp"))
        if not hits:
            print("WARNING: could not find thp/title in extracted image")
            return 0
        dest_dir = hits[0].parent

    n = 0
    for name in names:
        src = thp_src / name
        if not src.exists():
            # fall back to title.thp for missing variants
            src = thp_src / "title.thp"
        if not src.exists():
            continue
        shutil.copy2(src, dest_dir / name)
        n += 1
    if n:
        print(f"Injected Pitstop title video ({n} files) → {dest_dir}")
    return n


def ensure_public_wiilink_gct() -> Path:
    """Fallback GCT from public WiiLink TXT (not used for the private server)."""
    txt = wiilink_txt()
    gct = wiilink_gct()
    if not txt.exists():
        raise FileNotFoundError(f"Missing WiiLink patch: {txt}")
    need = True
    if gct.exists():
        need = gct.stat().st_mtime < txt.stat().st_mtime
    if need:
        words: list[int] = []
        for line in txt.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line[0] in "#*$":
                continue
            for part in line.replace(",", " ").split():
                words.append(int(part, 16))
        data = struct.pack(">II", 0x00D0C0DE, 0x00D0C0DE)
        data += b"".join(struct.pack(">I", w) for w in words)
        data += struct.pack(">II", 0xF0000000, 0)
        gct.parent.mkdir(parents=True, exist_ok=True)
        gct.write_bytes(data)
    return gct


def resolve_gct() -> Path:
    """Prefer private Pitstop GCT built for your DuckDNS domain."""
    gct = pitstop_gct()
    if gct.exists() and gct.stat().st_size > 32:
        return gct
    return ensure_public_wiilink_gct()


def ensure_patched_image(game_path: Path) -> Path:
    """Build a WWFC-patched WBFS copy. Original dump is never modified.

    Injects the Pitstop (or fallback WiiLink) GCT into main.dol.
    """
    dest = patched_image_path()
    stamp = dest.with_suffix(".stamp")
    key = dump_stamp(game_path)
    if dest.exists() and dest.stat().st_size > 100_000_000:
        if stamp.is_file() and stamp.read_text(encoding="utf-8") == key:
            print(f"Using cached patched image: {dest}")
            return dest
        if stamp.is_file():
            print("Patched image cache outdated — rebuilding…")
        else:
            print("Patched image missing stamp — rebuilding…")

    wit = find_tool("wit")
    wstrt = find_tool("wstrt")
    gct = resolve_gct()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_wbfs = dest.with_suffix(".wbfs.partial")
    if tmp_wbfs.exists():
        tmp_wbfs.unlink()

    if gct == pitstop_gct():
        print("Building Pitstop image for your private WWFC server...")
    else:
        print("WARNING: private Pitstop GCT not found yet.")
        print(f"  Expected: {pitstop_gct()}")
        print("  Falling back to public WiiLink (needs NAND).")
        print("  After DuckDNS is ready: ./tools/build-wwfc-patch.sh your.duckdns.org")
        print("Building image with fallback patch...")
    print("(original dump is not changed; takes a few minutes)")
    with tempfile.TemporaryDirectory(prefix="pitstop-fst-") as tmp:
        fst = Path(tmp) / "fst"
        subprocess.check_call([str(wit), "extract", "--dest", str(fst), str(game_path)])
        dol = fst / "sys" / "main.dol"
        if not dol.exists():
            raise FileNotFoundError(f"Missing DOL after extract: {dol}")
        subprocess.check_call(
            [
                str(wstrt),
                "patch",
                str(dol),
                "--clean-dol",
                "--add-sect",
                str(gct),
                "--gct-move",
            ]
        )
        inject_ui_branding(fst)
        inject_title_thp(fst)
        subprocess.check_call(
            [str(wit), "copy", "--overwrite", str(fst), str(tmp_wbfs)]
        )
    tmp_wbfs.replace(dest)
    # Write stamp after build so it matches the pack/GCT actually used
    stamp.write_text(dump_stamp(game_path), encoding="utf-8")
    print(f"Patched image: {dest}")
    return dest


def install_patch(dolphin_user: Path) -> Path:
    dest = dolphin_user / "Load" / "Riivolution" / APP_NAME
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        patch_src(),
        dest,
        ignore=shutil.ignore_patterns(
            "cheats", "thp", "title-source", "title-work", "*.png", "*.jpg"
        ),
    )
    (dest / "assets" / "UI").mkdir(parents=True, exist_ok=True)
    return dest


def split_ini_sections(content: str) -> tuple[str, dict[str, list[str]]]:
    sections: dict[str, list[str]] = {}
    preamble: list[str] = []
    current: str | None = None
    for line in content.splitlines():
        if line.startswith("[") and line.endswith("]"):
            current = line.strip()
            sections[current] = []
            continue
        if current is None:
            preamble.append(line)
        else:
            sections[current].append(line)
    return "\n".join(preamble).strip(), sections


def join_ini_sections(preamble: str, sections: dict[str, list[str]]) -> str:
    parts: list[str] = []
    if preamble:
        parts.append(preamble)
    for name, lines in sections.items():
        parts.append(name)
        parts.extend(lines)
    return "\n".join(parts).rstrip() + "\n"


def write_mod_game_ini(dolphin_user: Path) -> Path:
    """WiiLink is baked into the DOL — no gecko needed for Pitstop launches."""
    content = join_ini_sections(
        "",
        {
            "[Core]": ["EnableCheats = False"],
            "[Gecko_Enabled]": [],
        },
    )
    settings = dolphin_user / "GameSettings"
    settings.mkdir(parents=True, exist_ok=True)
    written = settings / "ID-Pitstop.ini"
    for name in ("ID-Pitstop.ini", "Pitstop.ini"):
        (settings / name).write_text(content, encoding="utf-8")
    return written


def write_descriptor(
    cfg: dict, patch_root: Path, image_path: Path, pit_user: Path | None = None
) -> Path:
    xml = patch_root / "riivolution" / "pitstop.xml"
    descriptor = {
        "type": "dolphin-game-mod-descriptor",
        "version": 1,
        "base-file": str(image_path),
        "display-name": APP_NAME,
        "config-ini-override": "Pitstop",
        "riivolution": {
            "patches": [
                {
                    "xml": str(xml),
                    "root": str(patch_root),
                    "options": [
                        {
                            "section-name": "Pitstop",
                            "option-id": "Pitstop",
                            "option-name": "Enabled",
                            # Riivolution: 0=disabled, 1=first choice
                            "choice": 1,
                        }
                    ],
                }
            ]
        },
    }
    user = pit_user or Path(cfg.get("pitstop_user_path") or default_pitstop_user())
    out = user / "Load" / "Riivolution" / APP_NAME / "Pitstop.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(descriptor, f, indent=2)
    return out


def _http_get(url: str, dest: Path | None = None, progress: ProgressFn | None = None) -> bytes:
    """Download URL to dest (optional) and return bytes."""
    log = progress or (lambda _m: None)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"{APP_NAME}-launcher/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            chunks: list[bytes] = []
            read = 0
            while True:
                block = resp.read(256 * 1024)
                if not block:
                    break
                chunks.append(block)
                read += len(block)
                if total and progress:
                    pct = int(100 * read / total)
                    log(f"Downloading… {pct}% ({read // (1024 * 1024)} MB)")
            data = b"".join(chunks)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Download failed ({e.code}): {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error fetching {url}: {e.reason}") from e
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return data


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _repo_dev_pack_ok() -> bool:
    """Local checkout: use repo patch/tools without downloading."""
    if getattr(sys, "frozen", False):
        return False
    root = Path(__file__).resolve().parent.parent
    gct = root / "patch" / "cheats" / "pitstop-rmced00.gct"
    wit = root / "tools" / host_platform() / ("wit.exe" if host_platform() == "win" else "wit")
    return gct.exists() and wit.exists()


def installed_pack_version() -> str:
    path = pack_version_path()
    if not path.exists():
        return ""
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("version", ""))
    except (json.JSONDecodeError, OSError):
        return ""


def fetch_manifest(url: str, progress: ProgressFn | None = None) -> dict:
    log = progress or print
    log(f"Fetching pack manifest: {url}")
    raw = _http_get(url, progress=progress)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid pack manifest JSON at {url}") from e


def ensure_pack(cfg: dict, progress: ProgressFn | None = None, force: bool = False) -> PackSyncResult:
    """Download/update pack from hosted manifest into ~/.config/pitstop/pack.

    Manifest shape (GitHub Releases friendly):
    {
      "version": "pitstop-private-wwfc-v7-unlock",
      "mac": {"url": "https://…/pitstop-pack-mac.zip", "sha256": "…"},
      "win": {"url": "https://…/pitstop-pack-win.zip", "sha256": "…"}
    }
    """
    log = progress or print
    plat = host_platform()
    url = (cfg.get("pack_manifest_url") or DEFAULT_PACK_MANIFEST_URL or "").strip()

    # Dev: prefer local repo without network.
    if not url and _repo_dev_pack_ok():
        log("Using local repo pack (dev mode — no manifest URL set).")
        root = Path(__file__).resolve().parent.parent / "patch"
        return PackSyncResult(path=root.parent, version="dev", changed=False)

    if not url:
        # Already downloaded once?
        if (pack_install_dir() / "patch" / "cheats").exists():
            ver = installed_pack_version() or "?"
            log(f"Using cached pack v{ver} (no manifest URL).")
            return PackSyncResult(path=pack_install_dir(), version=ver, changed=False)
        raise RuntimeError(
            "No pack_manifest_url configured.\n"
            "Set it in config.json or bake DEFAULT_PACK_MANIFEST_URL before shipping.\n"
            "See launcher/HOSTING.md"
        )

    manifest = fetch_manifest(url, progress=progress)
    version = str(manifest.get("version") or "").strip()
    if not version:
        raise RuntimeError("Pack manifest missing 'version'")

    entry = manifest.get(plat) or manifest.get("pack")
    if isinstance(entry, str):
        entry = {"url": entry}
    if not isinstance(entry, dict) or not entry.get("url"):
        raise RuntimeError(f"Pack manifest has no '{plat}.url' (or pack.url)")

    zip_url = str(entry["url"]).strip()
    expect_sha = str(entry.get("sha256") or "").strip().lower()

    current = installed_pack_version()
    gct_ok = (pack_install_dir() / "patch" / "cheats" / "pitstop-rmced00.gct").exists()
    if not force and current == version and gct_ok:
        log(f"Pack up to date (v{version}).")
        return PackSyncResult(path=pack_install_dir(), version=version, changed=False)

    log(f"Updating pack: {current or 'none'} → {version}")
    with tempfile.TemporaryDirectory(prefix="pitstop-pack-") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "pack.zip"
        _http_get(zip_url, dest=zip_path, progress=progress)
        if expect_sha:
            got = _sha256_file(zip_path)
            if got != expect_sha:
                raise RuntimeError(f"Pack SHA-256 mismatch (got {got}, expected {expect_sha})")
            log("SHA-256 OK")

        extract_root = tmp_path / "extract"
        extract_root.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_root)

        # Accept either zip root = pack contents, or a single top-level folder
        src = extract_root
        kids = [p for p in extract_root.iterdir() if p.name != "__MACOSX"]
        if len(kids) == 1 and kids[0].is_dir() and (kids[0] / "patch").is_dir():
            src = kids[0]
        if not (src / "patch").is_dir():
            raise RuntimeError("Downloaded zip missing patch/ — rebuild with launcher/build_pack.py --zip")

        dest = pack_install_dir()
        # Replace patch + this platform's tools
        for name in ("patch",):
            d = dest / name
            if d.exists():
                shutil.rmtree(d)
            shutil.copytree(src / name, d)
        tools_src = src / "tools" / plat
        if tools_src.is_dir():
            tools_dst = dest / "tools" / plat
            if tools_dst.exists():
                shutil.rmtree(tools_dst)
            shutil.copytree(tools_src, tools_dst)
            if plat == "mac":
                for exe in tools_dst.iterdir():
                    if exe.is_file() and not exe.suffix:
                        exe.chmod(0o755)

        pack_version_path().write_text(
            json.dumps(
                {
                    "version": version,
                    "platform": plat,
                    "manifest_url": url,
                    "pack_url": zip_url,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    log(f"Pack installed → {dest} (v{version})")
    return PackSyncResult(path=dest, version=version, changed=True)


def prepare(cfg: dict) -> tuple[Path, Path]:
    ensure_pack(cfg)
    pit_user = ensure_pitstop_user(cfg)
    ensure_pitstop_save(cfg)
    assert_save_isolation(cfg)
    try:
        import rfldb as rfldb_mod

        rfldb_mod.sync_from_dolphin(cfg)
    except (OSError, ValueError, RuntimeError) as e:
        print(f"Mii sync skipped: {e}")
    game = Path(cfg["game_path"])
    image = ensure_patched_image(game)
    # Patch + descriptor live only in the isolated Pitstop user — never install into
    # vanilla Dolphin (that made it easy to play Pitstop patches on the shared NAND).
    patch_root = install_patch(pit_user)
    write_mod_game_ini(pit_user)
    _remove_stale_main_user_patch(cfg)
    descriptor = write_descriptor(cfg, patch_root, image, pit_user)
    return image, descriptor


def _remove_stale_main_user_patch(cfg: dict) -> None:
    """Drop old Pitstop Riivolution copy under vanilla Dolphin, if present."""
    main = Path(cfg.get("dolphin_user_path") or default_dolphin_user())
    stale = main / "Load" / "Riivolution" / APP_NAME
    if stale.is_dir():
        try:
            shutil.rmtree(stale)
        except OSError:
            pass


def setup(cfg: dict, progress: ProgressFn | None = None) -> PackSyncResult:
    game = Path(cfg["game_path"])
    if not game.exists():
        raise FileNotFoundError(f"Game not found: {game}")
    result = ensure_pack(cfg, progress=progress)
    image, descriptor = prepare(cfg)
    pit_user = Path(cfg.get("pitstop_user_path") or default_pitstop_user())
    print("Pitstop online backend: private WWFC (GCT baked into main.dol)")
    print(f"Original dump: {game}")
    print(f"Patched image: {image}")
    print(f"Pack: {patch_src()} (tools: {tools_bin()})")
    print(f"Pitstop Dolphin user (isolated saves): {pit_user}")
    print(f"Descriptor: {descriptor}")
    if result.changed:
        print(f"Pack updated to v{result.version}.")
    else:
        print(f"Pack already up to date (v{result.version}).")
    print("Setup complete. Click Play to launch.")
    return result


def needs_first_run(cfg: dict) -> bool:
    if bool(cfg.get("setup_complete")):
        return False
    # Existing installs already configured — don't force the wizard again
    dolphin = str(cfg.get("dolphin_path") or "")
    game = str(cfg.get("game_path") or "")
    if dolphin_path_ok(dolphin) and game and Path(game).is_file():
        cfg["setup_complete"] = True
        save_config(cfg)
        return False
    return True


def launch(cfg: dict) -> int:
    dolphin = Path(cfg["dolphin_path"])
    game = Path(cfg["game_path"])
    if not dolphin.exists():
        raise FileNotFoundError(f"Dolphin not found: {dolphin}")
    if not game.exists():
        raise FileNotFoundError(f"Game not found: {game}")

    pit_user = ensure_pitstop_user(cfg)
    _image, descriptor = prepare(cfg)
    # Re-assert after prepare (install_patch must not have pointed us at vanilla).
    assert_save_isolation(cfg)
    van = vanilla_rksys_path(cfg)
    van_before = None
    if van is not None and van.is_file():
        import rksys as rksys_mod

        van_before = rksys_mod.file_fingerprint(van)
    cmd = [str(dolphin), "-u", str(pit_user.resolve()), "-e", str(descriptor)]
    print(f"Launching Pitstop: {' '.join(cmd)}")
    print("(isolated user folder — vanilla Dolphin saves untouched)")
    code = subprocess.call(cmd)
    if van_before is not None and van is not None:
        import rksys as rksys_mod

        van_after = rksys_mod.file_fingerprint(van)
        if van_after != van_before:
            print(
                "WARNING: vanilla Dolphin rksys.dat changed while Pitstop was running!\n"
                f"  before: {van_before}\n  after:  {van_after}"
            )
        else:
            print(f"Verified vanilla save unchanged: {van_before}")
    return code


def configure(cfg: dict) -> None:
    print("Pitstop setup (press Enter to keep current value)\n")
    for key in ("dolphin_path", "dolphin_user_path", "game_path"):
        current = cfg.get(key, "")
        val = input(f"{key} [{current}]: ").strip()
        if val:
            cfg[key] = val
    save_config(cfg)
    setup(cfg)


def main() -> int:
    cfg = load_config()
    if len(sys.argv) < 2:
        from gui import run_gui

        return run_gui()
    cmd = sys.argv[1].lower()
    if cmd == "gui":
        from gui import run_gui

        return run_gui()
    if cmd == "setup":
        setup(cfg)
    elif cmd == "launch":
        return launch(cfg)
    elif cmd == "configure":
        configure(cfg)
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: pitstop.py [gui | setup | launch | configure]")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
