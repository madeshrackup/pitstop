"""Wii / Mario Kart special name characters (CTMKF private-use glyphs).

Character ranges match Wheel Wizard’s CustomCharactersService. Glyphs render with
the bundled CTMKF font (launcher/assets/ctmkf.ttf).
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

# Same ranges / leftovers as Wheel Wizard (GPL-3.0) CustomCharactersService.
_CHAR_RANGES: list[tuple[int, int]] = [
    (0x2460, 0x246E),
    (0xE000, 0xE01C),
    (0xF061, 0xF06D),
    (0xF074, 0xF07C),
    (0xF107, 0xF10F),
]

_EXTRA_CHARS: list[int] = [
    0xE028,
    0xE068,
    0xE067,
    0xE06A,
    0xE06B,
    0xF030,
    0xF031,
    0xF034,
    0xF035,
    0xF038,
    0xF039,
    0xF041,
    0xF043,
    0xF044,
    0xF047,
    0xF050,
    0xF058,
    0xF05E,
    0xF05F,
    0xF103,
]


def custom_characters() -> list[str]:
    chars: list[str] = []
    for start, end in _CHAR_RANGES:
        for code in range(start, end + 1):
            chars.append(chr(code))
    chars.extend(chr(c) for c in _EXTRA_CHARS)
    return chars


CUSTOM_CHARS: frozenset[str] = frozenset(custom_characters())

FONT_FAMILY = "CTMKF"


def _font_path() -> Path | None:
    here = Path(__file__).resolve().parent
    candidates = [here / "assets" / "ctmkf.ttf", here / "ctmkf.ttf"]
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        candidates.insert(0, meipass / "assets" / "ctmkf.ttf")
    for p in candidates:
        if p.is_file():
            return p
    return None


def register_ctmkf_font() -> bool:
    """Register CTMKF for this process so Tk can render Wii symbols."""
    path = _font_path()
    if path is None:
        return False
    system = platform.system()
    if system == "Darwin":
        return _register_macos(path)
    if system == "Windows":
        return _register_windows(path)
    return False


def _register_macos(path: Path) -> bool:
    import ctypes
    import ctypes.util

    cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
    ct = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreText"))

    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFURLCreateWithFileSystemPath.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_bool,
    ]
    cf.CFURLCreateWithFileSystemPath.restype = ctypes.c_void_p
    ct.CTFontManagerRegisterFontsForURL.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ct.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool

    kCFStringEncodingUTF8 = 0x08000100
    kCFURLPOSIXPathStyle = 0
    kCTFontManagerScopeProcess = 1

    cfstr = cf.CFStringCreateWithCString(None, str(path).encode(), kCFStringEncodingUTF8)
    if not cfstr:
        return False
    url = cf.CFURLCreateWithFileSystemPath(None, cfstr, kCFURLPOSIXPathStyle, False)
    if not url:
        return False
    err = ctypes.c_void_p()
    return bool(ct.CTFontManagerRegisterFontsForURL(url, kCTFontManagerScopeProcess, ctypes.byref(err)))


def _register_windows(path: Path) -> bool:
    import ctypes

    gdi32 = ctypes.windll.gdi32  # type: ignore[attr-defined]
    # FR_PRIVATE = 0x10
    return bool(gdi32.AddFontResourceExW(str(path), 0x10, 0))
