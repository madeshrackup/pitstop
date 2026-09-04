"""One-way Dolphin → Pitstop FaceLib (RFL_DB.dat) Mii sync.

Miis live in the Wii system FaceLib database. Licenses stay in rksys.dat and are
never copied from vanilla Dolphin.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import rksys as rksys_mod

MII_SIZE = 0x4A
MAX_SLOTS = 100
HEADER_OFF = 0x04
CRC_OFF = 0x1F1DE
DB_SIZE = 779_968
MII_ID_OFF = 0x18
MII_SYS_OFF = 0x1C
MII_NAME_OFF = 0x02
EMPTY = bytes(MII_SIZE)

_FACELIB = Path("Wii") / "shared2" / "menu" / "FaceLib" / "RFL_DB.dat"


@dataclass(frozen=True)
class MiiEntry:
    slot: int
    mii_id: int
    system_id: int
    name: str
    raw: bytes


@dataclass(frozen=True)
class SyncResult:
    added: int
    updated: int
    total: int
    source_missing: bool = False


def _crc16_ccitt(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _decode_name(raw: bytes) -> str:
    chars: list[str] = []
    for i in range(10):
        code = struct.unpack_from(">H", raw, MII_NAME_OFF + i * 2)[0]
        if code == 0:
            break
        chars.append(chr(code))
    return "".join(chars).strip() or "Mii"


def vanilla_rfldb_path(cfg: dict) -> Path | None:
    van = rksys_mod.vanilla_user(cfg)
    if van is None:
        return None
    return van / _FACELIB


def pitstop_rfldb_path(cfg: dict) -> Path:
    return rksys_mod.assert_pitstop_only(rksys_mod.pitstop_user(cfg) / _FACELIB, cfg)


def _mii_id(raw: bytes) -> int:
    return struct.unpack_from(">I", raw, MII_ID_OFF)[0]


def _system_id(raw: bytes) -> int:
    return struct.unpack_from(">I", raw, MII_SYS_OFF)[0]


def _load_blocks(data: bytes) -> list[bytes]:
    blocks: list[bytes] = []
    for i in range(MAX_SLOTS):
        off = HEADER_OFF + i * MII_SIZE
        block = data[off : off + MII_SIZE]
        if len(block) < MII_SIZE:
            break
        blocks.append(bytes(block))
    while len(blocks) < MAX_SLOTS:
        blocks.append(EMPTY)
    return blocks


def ensure_pitstop_db(cfg: dict) -> Path:
    """Create an empty FaceLib DB under the Pitstop user if missing."""
    path = pitstop_rfldb_path(cfg)
    if path.is_file() and path.stat().st_size == DB_SIZE:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    db = bytearray(DB_SIZE)
    db[0:4] = b"RNOD"
    db[0x1CE0 + 0x0C] = 0x80
    db[0x1D00:0x1D04] = b"RNHD"
    db[0x1D04:0x1D08] = b"\xff\xff\xff\xff"
    crc = _crc16_ccitt(bytes(db[:CRC_OFF]))
    struct.pack_into(">H", db, CRC_OFF, crc)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(db)
    tmp.replace(path)
    return path


def list_miis(path: Path) -> list[MiiEntry]:
    if not path.is_file():
        return []
    data = path.read_bytes()
    if len(data) < CRC_OFF + 2 or data[:4] != b"RNOD":
        raise ValueError(f"invalid RFL_DB.dat at {path}")
    out: list[MiiEntry] = []
    for i, block in enumerate(_load_blocks(data)):
        if block == EMPTY or _mii_id(block) == 0:
            continue
        out.append(
            MiiEntry(
                slot=i,
                mii_id=_mii_id(block),
                system_id=_system_id(block),
                name=_decode_name(block),
                raw=block,
            )
        )
    return out


def _save_blocks(path: Path, blocks: list[bytes], cfg: dict) -> None:
    path = rksys_mod.assert_pitstop_only(path, cfg)
    data = bytearray(path.read_bytes())
    if len(data) < CRC_OFF + 2 or data[:4] != b"RNOD":
        raise ValueError(f"invalid RFL_DB.dat at {path}")
    for i in range(MAX_SLOTS):
        block = blocks[i] if i < len(blocks) else EMPTY
        if len(block) != MII_SIZE:
            raise ValueError("invalid Mii block size")
        off = HEADER_OFF + i * MII_SIZE
        data[off : off + MII_SIZE] = block
    crc = _crc16_ccitt(bytes(data[:CRC_OFF]))
    struct.pack_into(">H", data, CRC_OFF, crc)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def update_mii_name(cfg: dict, mii_id: int, name: str) -> None:
    """Rename a Mii in Pitstop FaceLib only (never Dolphin)."""
    if mii_id == 0:
        raise ValueError("invalid Mii id")
    cleaned = rksys_mod.validate_mii_name(name)
    path = ensure_pitstop_db(cfg)
    blocks = _load_blocks(path.read_bytes())
    encoded_name = bytearray(0x14)
    for i, ch in enumerate(cleaned):
        struct.pack_into(">H", encoded_name, i * 2, ord(ch) & 0xFFFF)

    found = False
    for i, block in enumerate(blocks):
        if block == EMPTY or _mii_id(block) != mii_id:
            continue
        updated = bytearray(block)
        updated[MII_NAME_OFF : MII_NAME_OFF + 0x14] = encoded_name
        blocks[i] = bytes(updated)
        found = True
        break
    if not found:
        raise ValueError(
            "Mii not found in Pitstop’s Mii Channel.\n"
            "Assign a synced Mii to this license first."
        )
    _save_blocks(path, blocks, cfg)


def sync_from_dolphin(cfg: dict) -> SyncResult:
    """Copy new Miis from vanilla Dolphin FaceLib into Pitstop only.

    Never writes to Dolphin. Never touches rksys.dat.
    Existing Pitstop Miis are left alone (so renames stick).
    """
    src = vanilla_rfldb_path(cfg)
    dst = ensure_pitstop_db(cfg)

    if src is None or not src.is_file():
        return SyncResult(added=0, updated=0, total=len(list_miis(dst)), source_missing=True)

    src_data = src.read_bytes()
    if len(src_data) < CRC_OFF + 2 or src_data[:4] != b"RNOD":
        raise ValueError(f"invalid Dolphin RFL_DB.dat at {src}")

    dst_blocks = _load_blocks(dst.read_bytes())
    by_id: dict[int, int] = {}
    for i, block in enumerate(dst_blocks):
        mid = _mii_id(block)
        if block != EMPTY and mid != 0:
            by_id[mid] = i

    added = 0
    for block in _load_blocks(src_data):
        if block == EMPTY:
            continue
        mid = _mii_id(block)
        if mid == 0 or mid in by_id:
            continue
        try:
            empty_idx = next(i for i, b in enumerate(dst_blocks) if b == EMPTY)
        except StopIteration as e:
            raise RuntimeError("Pitstop Mii Channel is full (100 Miis).") from e
        dst_blocks[empty_idx] = block
        by_id[mid] = empty_idx
        added += 1

    if added:
        _save_blocks(dst, dst_blocks, cfg)

    return SyncResult(
        added=added,
        updated=0,
        total=sum(1 for b in dst_blocks if b != EMPTY and _mii_id(b) != 0),
        source_missing=False,
    )
