#!/usr/bin/env python3
"""Assemble a slim friend pack for hosting (download via Pitstop launcher).

Includes: private GCT, UI SZS, riivolution XML, payload (if present), platform wit/wstrt.
Excludes: title THPs (~161MB), title-source/work scratch.

Emits:
  dist/pack/                 (folder)
  dist/pitstop-pack-mac.zip  (with --zip)
  dist/pitstop-pack-win.zip
  dist/manifest.json         (upload to GitHub Releases as manifest.json)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATCH = REPO / "patch"
TOOLS = REPO / "tools"

# Keep in sync with launcher/pitstop.py PATCHER_VERSION when shipping a pack.
DEFAULT_VERSION = "pitstop-private-wwfc-v7-unlock"


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  + {dst}")


def build(out: Path, plats: list[str]) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    patch_out = out / "patch"
    for name in ("pitstop-rmced00.gct", "pitstop-rmced00.txt"):
        src = PATCH / "cheats" / name
        if src.exists():
            copy_file(src, patch_out / "cheats" / name)
        elif name.endswith(".gct"):
            raise SystemExit(f"Missing required {src}")

    ui_src = PATCH / "assets" / "UI"
    for name in (
        "MenuSingle_U.szs",
        "MenuMulti_U.szs",
        "Globe_U.szs",
        "Title_U.szs",
        "Channel_U.szs",
    ):
        src = ui_src / name
        if src.exists():
            copy_file(src, patch_out / "assets" / "UI" / name)

    xml = PATCH / "riivolution" / "pitstop.xml"
    if not xml.exists():
        raise SystemExit(f"Missing {xml}")
    copy_file(xml, patch_out / "riivolution" / "pitstop.xml")

    for p in PATCH.glob("payload*.bin"):
        copy_file(p, patch_out / p.name)

    for plat in plats:
        src_dir = TOOLS / plat
        dst_dir = out / "tools" / plat
        candidates = ["wit", "wstrt"]
        if plat == "win":
            candidates = ["wit.exe", "wstrt.exe", "wit", "wstrt"]
        found_names: set[str] = set()
        for name in candidates:
            src = src_dir / name
            if not src.exists():
                continue
            base = name.replace(".exe", "")
            if base in found_names:
                continue
            dest_name = src.name
            if plat == "win" and not dest_name.endswith(".exe"):
                dest_name = f"{dest_name}.exe"
            copy_file(src, dst_dir / dest_name)
            if plat == "mac":
                dst_dir.joinpath(dest_name).chmod(0o755)
            found_names.add(base)
        if plat == "win" and src_dir.is_dir():
            for dll in sorted(src_dir.glob("cyg*.dll")):
                copy_file(dll, dst_dir / dll.name)
            readme = src_dir / "README.txt"
            if readme.exists():
                copy_file(readme, dst_dir / "README.txt")
        if found_names < {"wit", "wstrt"}:
            print(f"WARNING: {plat} tools incomplete under {src_dir} (need wit + wstrt)")

    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"\nPack ready: {out} ({total / (1024 * 1024):.1f} MB)")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_platform_zip(pack_dir: Path, plat: str, zip_path: Path) -> str:
    """Zip patch/ + tools/<plat>/ for one platform."""
    if zip_path.exists():
        zip_path.unlink()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        patch = pack_dir / "patch"
        for f in sorted(patch.rglob("*")):
            if f.is_file():
                zf.write(f, f"patch/{f.relative_to(patch).as_posix()}")
        tools = pack_dir / "tools" / plat
        if tools.is_dir():
            for f in sorted(tools.rglob("*")):
                if f.is_file():
                    zf.write(f, f"tools/{plat}/{f.relative_to(tools).as_posix()}")
    digest = _sha256(zip_path)
    print(f"  zip {zip_path} ({zip_path.stat().st_size / (1024 * 1024):.1f} MB) sha256={digest}")
    return digest


def write_manifest(
    out: Path,
    version: str,
    digests: dict[str, str],
    release_base_url: str,
) -> Path:
    """Write manifest.json. release_base_url is the Releases download prefix (no trailing slash)."""
    base = release_base_url.rstrip("/")
    manifest: dict = {"version": version, "notes": "Pitstop friend pack (no title THPs)"}
    for plat, digest in digests.items():
        name = f"pitstop-pack-{plat}.zip"
        manifest[plat] = {
            "url": f"{base}/{name}" if base else name,
            "sha256": digest,
        }
    path = out / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"  manifest → {path}")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build slim Pitstop friend pack")
    ap.add_argument("-o", "--out", type=Path, default=REPO / "dist" / "pack")
    ap.add_argument("--platform", choices=("mac", "win", "both"), default="both")
    ap.add_argument(
        "--zip",
        action="store_true",
        help="Also write per-platform zips + manifest.json under dist/",
    )
    ap.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help="Pack version string (must match what friends should update to)",
    )
    ap.add_argument(
        "--release-url",
        default="",
        help=(
            "GitHub release asset base URL, e.g. "
            "https://github.com/YOU/Pitstop/releases/download/pack-v7"
        ),
    )
    args = ap.parse_args()
    plats = ["mac", "win"] if args.platform == "both" else [args.platform]
    if platform.system() == "Darwin" and "mac" not in plats:
        plats.append("mac")

    print(f"Building pack → {args.out}")
    build(args.out, plats)

    if args.zip:
        dist = args.out.parent
        digests: dict[str, str] = {}
        for plat in plats:
            zpath = dist / f"pitstop-pack-{plat}.zip"
            digests[plat] = write_platform_zip(args.out, plat, zpath)
        write_manifest(dist, args.version, digests, args.release_url)
        if not args.release_url:
            print(
                "\nNOTE: re-run with --release-url https://github.com/YOU/REPO/releases/download/TAG\n"
                "  so manifest.json has absolute download URLs before uploading."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
