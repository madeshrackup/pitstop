"""Read/write Mario Kart Wii license slots from Pitstop's isolated save only."""

from __future__ import annotations

import hashlib
import shutil
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

RKSD_MAGIC = b"RKSD0006"
RKPD_MAGIC = b"RKPD"
RKSYS_SIZE = 0x2BC000
CRC_OFFSET = 0x27FFC
SLOT_SIZE = 0x8CC0
SLOT_OFFSETS = (0x8, 0x8CC8, 0x11988, 0x1A648)

NAME_OFF = 0x14
NAME_BYTES = 0x14  # 10 UTF-16 code units
PID_OFF = 0x5C
VR_OFF = 0xB0
NAME_MAX_CHARS = 10
CACHED_MII_OFF = 0x5684
CACHED_MII_SIZE = 0x4A
CACHED_MII_CRC_OFF = 0x56CE
# RFL Mii: UTF-16 BE name starts at byte 0x02 inside the 0x4A blob
MII_NAME_OFF = 0x02
MII_NAME_BYTES = 0x14  # 10 chars
AVATAR_ID_OFF = 0x28
SYSTEM_ID_OFF = 0x2C
# Guest / placeholder Mii created in-game as "no name"
GUEST_AVATAR_ID = 0x80000000

# Characters available on the Wii Mii Channel Latin keyboards (letters / numbers / symbols),
# plus common Western European accented letters. Rejects pasted emoji, smart quotes, etc.
_WII_NAME_ALLOWED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789 "
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞß"
    "àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ"
)


def _allowed_name_chars() -> frozenset[str]:
    try:
        import wii_chars as wii_chars_mod

        return _WII_NAME_ALLOWED | wii_chars_mod.CUSTOM_CHARS
    except ImportError:
        return _WII_NAME_ALLOWED

# NTSC-U Mario Kart Wii title data under a Dolphin user folder
_NAND_RKSYS = Path("Wii") / "title" / "00010004" / "524d4345" / "data" / "rksys.dat"


@dataclass(frozen=True)
class License:
    index: int
    active: bool
    name: str
    vr: int
    friend_code: str | None  # None if never went online (PID == 0)
    avatar_id: int = 0


class IsolationError(RuntimeError):
    """Raised when a path would touch vanilla Dolphin or leave the Pitstop user."""


def pitstop_user(cfg: dict) -> Path:
    raw = (cfg.get("pitstop_user_path") or "").strip()
    if not raw:
        raise IsolationError("pitstop_user_path is not set")
    return Path(raw).expanduser().resolve()


def vanilla_user(cfg: dict) -> Path | None:
    raw = (cfg.get("dolphin_user_path") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def assert_pitstop_only(path: Path, cfg: dict) -> Path:
    """Refuse any path under the vanilla Dolphin user folder."""
    resolved = path.expanduser().resolve()
    pit = pitstop_user(cfg)
    van = vanilla_user(cfg)

    try:
        resolved.relative_to(pit)
    except ValueError as e:
        raise IsolationError(
            f"Refusing path outside Pitstop user folder.\n"
            f"  path: {resolved}\n"
            f"  pitstop user: {pit}"
        ) from e

    if van is not None:
        try:
            resolved.relative_to(van)
        except ValueError:
            pass
        else:
            raise IsolationError(
                f"Refusing to touch vanilla Dolphin path:\n  {resolved}\n"
                f"Pitstop saves must stay under:\n  {pit}"
            )
    return resolved


def nand_rksys_path(cfg: dict) -> Path:
    """Canonical Pitstop save: NAND under the isolated -u user folder."""
    return assert_pitstop_only(pitstop_user(cfg) / _NAND_RKSYS, cfg)


def find_rksys(cfg: dict) -> Path | None:
    """Resolve Pitstop-only rksys.dat (never vanilla Dolphin / Wheel Wizard)."""
    try:
        path = nand_rksys_path(cfg)
    except IsolationError:
        return None
    return path if path.is_file() else None


def friend_code_from_pid(pid: int) -> str:
    """MKWii friend code: MD5(pid_le + b'JCMR'), checksum = first_byte >> 1."""
    if pid == 0:
        raise ValueError("no profile id")
    buf = struct.pack("<I", pid & 0xFFFFFFFF) + b"JCMR"
    csum = hashlib.md5(buf).digest()[0] >> 1
    fc = (csum << 32) | (pid & 0xFFFFFFFF)
    s = f"{fc:012d}"
    return f"{s[0:4]}-{s[4:8]}-{s[8:12]}"


def _decode_name(raw: bytes) -> str:
    chars: list[str] = []
    for i in range(0, min(len(raw), NAME_BYTES), 2):
        code = struct.unpack_from(">H", raw, i)[0]
        if code == 0:
            break
        chars.append(chr(code))
    return "".join(chars).strip() or "no name"


def validate_mii_name(name: str) -> str:
    """Normalize and enforce Wii Mii Channel name rules. Raises ValueError if invalid."""
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise ValueError("Name cannot be empty.")
    if len(cleaned) > NAME_MAX_CHARS:
        raise ValueError(
            f"Names can be at most {NAME_MAX_CHARS} characters on the Wii "
            f"(yours is {len(cleaned)})."
        )
    bad = sorted({ch for ch in cleaned if ch not in _allowed_name_chars()})
    if bad:
        shown = ", ".join(repr(ch) for ch in bad[:8])
        if len(bad) > 8:
            shown += ", …"
        raise ValueError(
            "That name has characters the Wii doesn’t allow:\n"
            f"  {shown}\n\n"
            "Use letters, numbers, basic punctuation, or the Wii symbols picker."
        )
    return cleaned


def _pack_name(cleaned: str) -> bytes:
    """Pack an already-trusted name into UTF-16 BE (max 10 chars)."""
    cleaned = cleaned[:NAME_MAX_CHARS]
    out = bytearray(NAME_BYTES)
    for i, ch in enumerate(cleaned):
        struct.pack_into(">H", out, i * 2, ord(ch) & 0xFFFF)
    return bytes(out)


def _encode_name(name: str) -> bytes:
    """Validate user input, then pack for rksys / FaceLib."""
    return _pack_name(validate_mii_name(name))


def _parse_slot(data: bytes, index: int) -> License:
    off = SLOT_OFFSETS[index]
    active = data[off : off + 4] == RKPD_MAGIC
    if not active:
        return License(index=index, active=False, name="", vr=0, friend_code=None, avatar_id=0)
    name = _decode_name(data[off + NAME_OFF : off + NAME_OFF + NAME_BYTES])
    vr = struct.unpack_from(">H", data, off + VR_OFF)[0]
    pid = struct.unpack_from(">I", data, off + PID_OFF)[0]
    fc = friend_code_from_pid(pid) if pid else None
    avatar = struct.unpack_from(">I", data, off + AVATAR_ID_OFF)[0]
    return License(
        index=index, active=True, name=name, vr=vr, friend_code=fc, avatar_id=avatar
    )


def read_licenses(path: Path) -> list[License]:
    """Return exactly 4 license slots. Raises ValueError on bad file."""
    data = path.read_bytes()
    if len(data) < RKSYS_SIZE or data[:8] != RKSD_MAGIC:
        raise ValueError(f"invalid rksys.dat at {path}")
    return [_parse_slot(data, i) for i in range(4)]


def empty_licenses() -> list[License]:
    return [
        License(index=i, active=False, name="", vr=0, friend_code=None, avatar_id=0)
        for i in range(4)
    ]


def _mii_crc16(mii: bytes) -> int:
    """CRC-16-CCITT (init 0) over the 0x4A Mii blob — matches rksys cached Mii."""
    crc = 0
    for byte in mii:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def is_guest_mii(data: bytes, index: int) -> bool:
    """True for in-game placeholder Miis (always labeled “no name” / Player)."""
    off = SLOT_OFFSETS[index]
    if data[off : off + 4] != RKPD_MAGIC:
        return False
    avatar = struct.unpack_from(">I", data, off + AVATAR_ID_OFF)[0]
    return avatar == GUEST_AVATAR_ID or avatar == 0


def set_license_mii(path: Path, index: int, mii: bytes, *, backup: bool = True) -> License:
    """Attach a real FaceLib Mii to a Pitstop license (avatar + system + cache).

    Does not touch Dolphin FaceLib or vanilla rksys — only the Pitstop save.
    """
    if index not in range(4):
        raise ValueError("license index must be 0..3")
    if len(mii) != CACHED_MII_SIZE:
        raise ValueError("invalid Mii block size")
    mii_id = struct.unpack_from(">I", mii, 0x18)[0]
    if mii_id == 0 or mii_id == GUEST_AVATAR_ID:
        raise ValueError("Cannot assign a guest / empty Mii to a license.")

    data = bytearray(path.read_bytes())
    if len(data) < RKSYS_SIZE or data[:8] != RKSD_MAGIC:
        raise ValueError(f"invalid rksys.dat at {path}")
    off = SLOT_OFFSETS[index]
    if data[off : off + 4] != RKPD_MAGIC:
        raise ValueError("license slot is empty — create a license in-game first")

    if backup:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            shutil.copy2(path, bak)

    system_id = struct.unpack_from(">I", mii, 0x1C)[0]
    # Keep the Mii’s own name bytes (may include regional chars already on the Wii)
    encoded = bytes(mii[MII_NAME_OFF : MII_NAME_OFF + MII_NAME_BYTES])

    struct.pack_into(">I", data, off + AVATAR_ID_OFF, mii_id)
    struct.pack_into(">I", data, off + SYSTEM_ID_OFF, system_id)
    data[off + NAME_OFF : off + NAME_OFF + NAME_BYTES] = encoded

    mii_out = bytearray(mii)
    mii_start = off + CACHED_MII_OFF
    data[mii_start : mii_start + CACHED_MII_SIZE] = mii_out
    struct.pack_into(">H", data, off + CACHED_MII_CRC_OFF, _mii_crc16(bytes(mii_out)))

    crc = zlib.crc32(bytes(data[:CRC_OFFSET])) & 0xFFFFFFFF
    struct.pack_into(">I", data, CRC_OFFSET, crc)

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return _parse_slot(bytes(data), index)


def set_license_name(
    path: Path,
    index: int,
    name: str,
    *,
    backup: bool = True,
    cfg: dict | None = None,
) -> License:
    """Rewrite license + Mii name for in-game display (real Miis only).

    MKWii shows the FaceLib Mii’s name on the license, so renaming also updates
    that Mii inside Pitstop’s RFL_DB.dat (never Dolphin’s).
    """
    if index not in range(4):
        raise ValueError("license index must be 0..3")
    data = bytearray(path.read_bytes())
    if len(data) < RKSYS_SIZE or data[:8] != RKSD_MAGIC:
        raise ValueError(f"invalid rksys.dat at {path}")
    off = SLOT_OFFSETS[index]
    if data[off : off + 4] != RKPD_MAGIC:
        raise ValueError("license slot is empty")

    if is_guest_mii(data, index):
        raise ValueError(
            "This license uses a guest Mii (“no name” / Player).\n\n"
            "Assign a real Mii first, then rename."
        )

    if backup:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            shutil.copy2(path, bak)

    encoded = _encode_name(name)
    avatar = struct.unpack_from(">I", data, off + AVATAR_ID_OFF)[0]
    data[off + NAME_OFF : off + NAME_OFF + NAME_BYTES] = encoded

    mii_start = off + CACHED_MII_OFF
    mii = bytearray(data[mii_start : mii_start + CACHED_MII_SIZE])
    if len(mii) == CACHED_MII_SIZE:
        mii[MII_NAME_OFF : MII_NAME_OFF + MII_NAME_BYTES] = encoded
        data[mii_start : mii_start + CACHED_MII_SIZE] = mii
        struct.pack_into(">H", data, off + CACHED_MII_CRC_OFF, _mii_crc16(bytes(mii)))

    crc = zlib.crc32(bytes(data[:CRC_OFFSET])) & 0xFFFFFFFF
    struct.pack_into(">I", data, CRC_OFFSET, crc)

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)

    if cfg is not None and avatar not in (0, GUEST_AVATAR_ID):
        import rfldb as rfldb_mod

        rfldb_mod.update_mii_name(cfg, avatar, name)

    return _parse_slot(bytes(data), index)


def file_fingerprint(path: Path) -> str:
    if not path.is_file():
        return "missing"
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"{h[:16]}… ({path.stat().st_size} bytes)"
