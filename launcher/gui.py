#!/usr/bin/env python3
"""Pitstop friend-facing launcher — dark sidebar UI inspired by modern MKW launchers."""

from __future__ import annotations

import io
import platform
import threading
import tkinter as tk
from contextlib import redirect_stdout
from pathlib import Path
from tkinter import filedialog, messagebox

import pitstop as core
import rfldb as rfldb_mod
import rksys as rksys_mod
import wii_chars as wii_chars_mod

# Logo palette — black ground + lavender / amethyst (matches assets/pitstop-logo.png)
C = {
    "bg": "#050508",
    "sidebar": "#000000",
    "surface": "#12121a",
    "surface2": "#1a1a26",
    "elevated": "#262636",
    "text": "#f3eefc",
    "muted": "#b5a8d4",
    "dim": "#7a6f96",
    "accent": "#b794f6",
    "accent_hover": "#c9b0fa",
    "accent_press": "#9b74e8",
    "accent_soft": "#2a1a48",
    "accent_ink": "#1a0a2e",
    "nav_active_bg": "#1a1428",
    "danger": "#e5484d",
    "ok": "#3ecf8e",
    "border": "#3d3558",
}


def _asset(name: str) -> Path | None:
    here = Path(__file__).resolve().parent
    roots = [here / "assets", here]
    try:
        import sys

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            roots.insert(0, Path(sys._MEIPASS) / "assets")  # type: ignore[attr-defined]
        roots.append(Path(core.resource_root()) / "launcher" / "assets")
        roots.append(Path(core.resource_root()) / "assets")
    except Exception:  # noqa: BLE001
        pass
    for root in roots:
        p = root / name
        if p.is_file():
            return p
    return None

FONT_UI = ("Helvetica Neue", 13) if platform.system() == "Darwin" else ("Segoe UI", 11)
FONT_UI_SM = ("Helvetica Neue", 11) if platform.system() == "Darwin" else ("Segoe UI", 9)
FONT_TITLE = ("Helvetica Neue", 22, "bold") if platform.system() == "Darwin" else ("Segoe UI", 18, "bold")
FONT_BRAND = ("Helvetica Neue", 15, "bold") if platform.system() == "Darwin" else ("Segoe UI", 13, "bold")
FONT_SECTION = ("Helvetica Neue", 10) if platform.system() == "Darwin" else ("Segoe UI", 8)
FONT_HERO = ("Helvetica Neue", 28, "bold") if platform.system() == "Darwin" else ("Segoe UI", 24, "bold")
FONT_BTN = ("Helvetica Neue", 14, "bold") if platform.system() == "Darwin" else ("Segoe UI", 12, "bold")
# CTMKF renders Mario Kart / Wii private-use symbols (registered at startup)
FONT_WII = (wii_chars_mod.FONT_FAMILY, 16)
FONT_WII_SM = (wii_chars_mod.FONT_FAMILY, 14)
FONT_WII_BRAND = (wii_chars_mod.FONT_FAMILY, 15, "bold")

RADIUS = 14
RADIUS_SM = 10
RADIUS_PILL = 18


class _LogWriter(io.TextIOBase):
    def __init__(self, append_fn):
        self._append = append_fn

    def write(self, s: str) -> int:
        if s:
            self._append(s)
        return len(s)

    def flush(self) -> None:
        pass


def _round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, r: float, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [
        x1 + r,
        y1,
        x2 - r,
        y1,
        x2,
        y1,
        x2,
        y1 + r,
        x2,
        y2 - r,
        x2,
        y2,
        x2 - r,
        y2,
        x1 + r,
        y2,
        x1,
        y2,
        x1,
        y2 - r,
        x1,
        y1 + r,
        x1,
        y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class RoundCard(tk.Frame):
    """Panel with a rounded fill + optional outline. Put children on `.body`."""

    def __init__(
        self,
        master,
        *,
        fill: str = C["surface"],
        outline: str = C["border"],
        radius: int = RADIUS,
        pad: int = 0,
        parent_bg: str | None = None,
        **kw,
    ):
        bg = parent_bg if parent_bg is not None else master.cget("bg")
        super().__init__(master, bg=bg, **kw)
        self.pack_propagate(False)
        self._fill = fill
        self._outline = outline
        self._radius = radius
        self._pad = pad
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.body = tk.Frame(self.canvas, bg=fill)
        self._win = self.canvas.create_window(pad, pad, anchor="nw", window=self.body)
        self.bind("<Configure>", self._redraw)
        self.body.bind("<Configure>", lambda _e: self.after_idle(self._sync_height))

    def _expanding(self) -> bool:
        try:
            mgr = self.winfo_manager()
            if mgr == "pack":
                exp = self.pack_info().get("expand")
                return exp in ("1", 1, True)
            if mgr == "grid":
                # License tiles stretch with sticky nsew
                sticky = str(self.grid_info().get("sticky") or "")
                return "n" in sticky and "s" in sticky
        except tk.TclError:
            pass
        return False

    def _sync_height(self) -> None:
        if self._expanding():
            self._redraw()
            return
        self.body.update_idletasks()
        h = self.body.winfo_reqheight() + 2 * self._pad
        self.configure(height=max(h, 36))
        self._redraw()

    def _redraw(self, _e=None) -> None:
        w = max(self.winfo_width(), 2)
        h = max(self.winfo_height(), 2)
        self.canvas.delete("shape")
        inset = 1.5
        _round_rect(
            self.canvas,
            inset,
            inset,
            w - inset,
            h - inset,
            self._radius,
            fill=self._fill,
            outline=self._outline,
            width=1.5,
            tags="shape",
        )
        self.canvas.tag_lower("shape")
        inner_w = max(w - 2 * self._pad, 1)
        inner_h = max(h - 2 * self._pad, 1)
        self.canvas.coords(self._win, self._pad, self._pad)
        # Always size the body to the card so .place() heroes (Home) stay visible;
        # non-expanding cards grow via _sync_height when content is added.
        self.canvas.itemconfigure(self._win, width=inner_w, height=inner_h)


class RoundButton(tk.Canvas):
    """Rounded pill button drawn on a canvas."""

    def __init__(
        self,
        master,
        text: str,
        command,
        *,
        primary: bool = False,
        width: int = 260,
        height: int = 44,
        radius: int = RADIUS_PILL,
        **kw,
    ):
        parent_bg = master.cget("bg")
        super().__init__(
            master,
            width=width,
            height=height,
            bg=parent_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            **kw,
        )
        self._command = command
        self._primary = primary
        self._enabled = True
        self._text = text
        self._radius = radius
        self._bw = width
        self._bh = height
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self._paint(C["accent"] if primary else C["elevated"])

    def _colors(self) -> tuple[str, str]:
        if not self._enabled:
            return C["surface2"], C["dim"]
        if self._primary:
            return C["accent"], C["accent_ink"]
        return C["elevated"], C["text"]

    def _paint(self, fill: str | None = None) -> None:
        bg, fg = self._colors()
        if fill is not None and self._enabled:
            bg = fill
        self.delete("all")
        outline = C["border"] if not self._primary and self._enabled else bg
        _round_rect(
            self,
            1,
            1,
            self._bw - 1,
            self._bh - 1,
            self._radius,
            fill=bg,
            outline=outline,
            width=1,
        )
        self.create_text(
            self._bw / 2,
            self._bh / 2,
            text=self._text,
            fill=fg,
            font=FONT_BTN,
        )

    def _click(self, _e=None) -> None:
        if self._enabled:
            self._command()

    def _enter(self, _e=None) -> None:
        if not self._enabled:
            return
        self._paint(C["accent_hover"] if self._primary else C["border"])

    def _leave(self, _e=None) -> None:
        if not self._enabled:
            return
        self._paint(None)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._paint(None)


class _NavButton(tk.Canvas):
    def __init__(self, master, label: str, icon: str, command, **kw):
        super().__init__(
            master,
            height=40,
            bg=C["sidebar"],
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            **kw,
        )
        self._command = command
        self._label = label
        self._icon = icon
        self._active = False
        self.bind("<Button-1>", lambda _e: self._command())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Configure>", lambda _e: self._paint())
        self._paint()

    def _enter(self, _e=None) -> None:
        if not self._active:
            self._paint(hover=True)

    def _leave(self, _e=None) -> None:
        if not self._active:
            self._paint()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._paint()

    def _paint(self, hover: bool = False) -> None:
        w = max(self.winfo_width(), 190)
        h = 40
        self.delete("all")
        if self._active or hover:
            fill = C["nav_active_bg"]
            _round_rect(self, 4, 2, w - 4, h - 2, RADIUS_SM, fill=fill, outline=fill)
            if self._active:
                self.create_rectangle(4, 8, 7, h - 8, fill=C["accent"], outline="")
        fg = C["accent"] if self._active else (C["text"] if hover else C["muted"])
        self.create_text(28, h / 2, text=self._icon, fill=fg, font=FONT_UI, anchor="w")
        self.create_text(52, h / 2, text=self._label, fill=fg, font=FONT_UI, anchor="w")


class RoundSelect(tk.Frame):
    """In-app dropdown (avoids native OptionMenu so CTMKF glyphs render)."""

    def __init__(
        self,
        master,
        *,
        font=FONT_UI,
        parent_bg: str = C["surface"],
        on_change=None,
        on_toggle=None,
    ):
        super().__init__(master, bg=parent_bg)
        self._font = font
        self._on_change = on_change
        self._on_toggle = on_toggle
        self._choices: list[str] = []
        self._value = ""
        self._open = False

        self._trigger = tk.Frame(self, bg=C["surface2"], highlightthickness=1, highlightbackground=C["border"])
        self._trigger.pack(fill=tk.X)
        self._label = tk.Label(
            self._trigger,
            text="",
            font=font,
            bg=C["surface2"],
            fg=C["text"],
            anchor="w",
            cursor="hand2",
        )
        self._label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 4), pady=10)
        self._chevron = tk.Label(
            self._trigger,
            text="▾",
            font=FONT_UI_SM,
            bg=C["surface2"],
            fg=C["muted"],
            cursor="hand2",
            padx=10,
        )
        self._chevron.pack(side=tk.RIGHT)
        for w in (self._trigger, self._label, self._chevron):
            w.bind("<Button-1>", lambda _e: self.toggle())

        self._list = tk.Frame(self, bg=C["border"])

    def get(self) -> str:
        return self._value

    def set_options(self, options: list[str], selected: str | None = None) -> None:
        self._choices = list(options)
        if selected and selected in self._choices:
            self._value = selected
        elif self._choices:
            self._value = self._choices[0]
        else:
            self._value = ""
        self._label.configure(
            text=self._value or "(no Miis synced)",
            fg=C["text"] if self._value else C["dim"],
        )
        if self._open:
            self._rebuild_list()

    def toggle(self) -> None:
        if self._open:
            self.close()
        else:
            self.open()

    def open(self) -> None:
        if self._open:
            return
        self._open = True
        self._chevron.configure(text="▴")
        self._rebuild_list()
        self._list.pack(fill=tk.X, pady=(4, 0))
        if self._on_toggle:
            self._on_toggle(True)

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        self._chevron.configure(text="▾")
        self._list.pack_forget()
        if self._on_toggle:
            self._on_toggle(False)

    def _rebuild_list(self) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        rows = self._choices or ["(no Miis synced)"]
        for i, label in enumerate(rows):
            selectable = bool(self._choices)
            row = tk.Label(
                self._list,
                text=label,
                font=self._font,
                bg=C["surface2"] if label != self._value else C["accent_soft"],
                fg=C["text"] if selectable else C["dim"],
                anchor="w",
                cursor="hand2" if selectable else "arrow",
                padx=12,
                pady=8,
            )
            row.pack(fill=tk.X, padx=1, pady=(1 if i else 0, 0))
            if selectable:
                row.bind("<Button-1>", lambda _e, v=label: self._pick(v))
                row.bind(
                    "<Enter>",
                    lambda _e, w=row: w.configure(bg=C["elevated"]),
                )
                row.bind(
                    "<Leave>",
                    lambda _e, w=row, v=label: w.configure(
                        bg=C["accent_soft"] if v == self._value else C["surface2"]
                    ),
                )

    def _pick(self, label: str) -> None:
        self._value = label
        self._label.configure(text=label, fg=C["text"])
        self.close()
        if self._on_change:
            self._on_change(label)


class RoundField(tk.Frame):
    """Rounded path entry row. Pass browse=None for a read-only path display."""

    def __init__(
        self,
        master,
        textvariable: tk.StringVar,
        browse=None,
        *,
        parent_bg: str = C["surface"],
        readonly: bool = False,
    ):
        super().__init__(master, bg=parent_bg, height=40)
        self.pack_propagate(False)
        self._canvas = tk.Canvas(self, height=40, bg=parent_bg, highlightthickness=0, bd=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._inner = tk.Frame(self._canvas, bg=C["surface2"])
        self._win = self._canvas.create_window(0, 0, anchor="nw", window=self._inner)
        entry = tk.Entry(
            self._inner,
            textvariable=textvariable,
            font=FONT_UI_SM,
            bg=C["surface2"],
            fg=C["text"],
            insertbackground=C["text"],
            relief=tk.FLAT,
            highlightthickness=0,
            state="readonly" if readonly or browse is None else "normal",
            readonlybackground=C["surface2"],
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 4), pady=10)
        if browse is not None:
            btn = tk.Label(
                self._inner,
                text="Browse",
                font=FONT_UI_SM,
                fg=C["accent"],
                bg=C["surface2"],
                cursor="hand2",
                padx=12,
            )
            btn.pack(side=tk.RIGHT, pady=10, padx=(0, 8))
            btn.bind("<Button-1>", lambda _e: browse())
        self.bind("<Configure>", self._redraw)
        self._inner.bind("<Configure>", lambda _e: self.after_idle(self._redraw))

    def _redraw(self, _e=None) -> None:
        w = max(self.winfo_width(), 40)
        h = 40
        self._canvas.configure(width=w, height=h)
        self._canvas.delete("shape")
        _round_rect(
            self._canvas,
            1,
            1,
            w - 1,
            h - 1,
            RADIUS_SM,
            fill=C["surface2"],
            outline=C["border"],
            width=1,
            tags="shape",
        )
        self._canvas.tag_lower("shape")
        self._canvas.coords(self._win, 0, 0)
        self._canvas.itemconfigure(self._win, width=w, height=h)


class RoundBadge(tk.Canvas):
    def __init__(self, master, text: str, **kw):
        super().__init__(master, height=24, highlightthickness=0, bd=0, bg=master.cget("bg"), **kw)
        self._text = text
        self.bind("<Configure>", lambda _e: self._paint())
        # size from text
        self.update_idletasks()
        tw = max(len(text) * 7 + 20, 60)
        self.configure(width=tw)
        self._paint()

    def _paint(self) -> None:
        w = max(self.winfo_width(), 60)
        h = 24
        self.delete("all")
        _round_rect(self, 0, 0, w, h, 12, fill=C["surface2"], outline=C["surface2"])
        self.create_text(w / 2, h / 2, text=self._text, fill=C["muted"], font=FONT_SECTION)

class PitstopApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Pitstop")
        self.minsize(820, 560)
        self.geometry("920x620")
        self.configure(bg=C["bg"])

        try:
            self.tk.call("tk", "scaling", 1.25)
        except tk.TclError:
            pass

        self._wii_font_ok = wii_chars_mod.register_ctmkf_font()
        self._photos: list[tk.PhotoImage] = []
        self._set_window_icon()

        self.cfg = core.load_config()
        if not self.cfg.get("dolphin_path"):
            self.cfg["dolphin_path"] = core.default_dolphin_binary()
        if not self.cfg.get("dolphin_user_path"):
            self.cfg["dolphin_user_path"] = core.default_dolphin_user()
        if not self.cfg.get("pitstop_user_path"):
            self.cfg["pitstop_user_path"] = core.default_pitstop_user()

        self.dolphin_var = tk.StringVar(value=self.cfg.get("dolphin_path", ""))
        self.game_var = tk.StringVar(value=self.cfg.get("game_path", ""))
        self._busy = False
        self._page = "home"
        self._nav: dict[str, _NavButton] = {}
        self._pages: dict[str, tk.Frame] = {}
        self._licenses_cache: list[rksys_mod.License] = rksys_mod.empty_licenses()

        self._build()
        self._refresh_licenses()
        self._show_page("home")
        self.after(200, self._maybe_first_run)

    def _set_window_icon(self) -> None:
        """Dock / taskbar / window icon (dev run + frozen when PNG is bundled)."""
        path = _asset("pitstop-icon.png")
        if path is None:
            return
        try:
            img = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return
        self._photos.append(img)
        try:
            self.iconphoto(True, img)
        except tk.TclError:
            pass

    def _photo(self, name: str) -> tk.PhotoImage | None:
        path = _asset(name)
        if not path:
            return None
        try:
            img = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return None
        self._photos.append(img)
        return img

    def _build(self) -> None:
        root = tk.Frame(self, bg=C["bg"])
        root.pack(fill=tk.BOTH, expand=True)

        self._build_sidebar(root)
        self._content = tk.Frame(root, bg=C["bg"])
        self._content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._pages["home"] = self._build_home(self._content)
        self._pages["licenses"] = self._build_licenses(self._content)
        self._pages["settings"] = self._build_settings(self._content)
        self._pages["about"] = self._build_about(self._content)

    def _build_sidebar(self, parent: tk.Frame) -> None:
        side = tk.Frame(parent, bg=C["sidebar"], width=220)
        side.pack(side=tk.LEFT, fill=tk.Y)
        side.pack_propagate(False)

        brand = tk.Frame(side, bg=C["sidebar"])
        brand.pack(fill=tk.X, padx=12, pady=(14, 6))
        mark_img = self._photo("pitstop-logo-mark.png")
        if mark_img is not None:
            tk.Label(brand, image=mark_img, bg=C["sidebar"]).pack(anchor="w")
        else:
            mark = tk.Canvas(brand, width=28, height=28, bg=C["sidebar"], highlightthickness=0)
            mark.pack(side=tk.LEFT)
            self._draw_mark(mark)
            tk.Label(
                brand,
                text="Pitstop",
                font=FONT_BRAND,
                fg=C["accent"],
                bg=C["sidebar"],
            ).pack(side=tk.LEFT, padx=(10, 0))

        blurb = RoundCard(side, fill=C["surface"], outline=C["border"], radius=RADIUS_SM, pad=0, parent_bg=C["sidebar"])
        blurb.pack(fill=tk.X, padx=14, pady=(4, 16))
        name_font = FONT_WII_SM if self._wii_font_ok else FONT_UI_SM
        self._primary_name_lbl = tk.Label(
            blurb.body,
            text="Your Name",
            font=name_font,
            fg=C["dim"],
            bg=C["surface"],
            anchor="w",
        )
        self._primary_name_lbl.pack(fill=tk.X, padx=12, pady=(10, 2))
        self._primary_vr_lbl = tk.Label(
            blurb.body,
            text="VR: XXXX",
            font=FONT_UI_SM,
            fg=C["dim"],
            bg=C["surface"],
            anchor="w",
        )
        self._primary_vr_lbl.pack(fill=tk.X, padx=12, pady=(0, 10))
        self._primary_blurb_card = blurb

        tk.Label(
            side,
            text="GENERAL",
            font=FONT_SECTION,
            fg=C["dim"],
            bg=C["sidebar"],
            anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(4, 4))

        self._nav["home"] = _NavButton(side, "Home", "⌂", lambda: self._show_page("home"))
        self._nav["home"].pack(fill=tk.X, padx=8, pady=1)
        self._nav["licenses"] = _NavButton(
            side, "Licenses", "▣", lambda: self._show_page("licenses")
        )
        self._nav["licenses"].pack(fill=tk.X, padx=8, pady=1)
        self._nav["settings"] = _NavButton(
            side, "Settings", "⚙", lambda: self._show_page("settings")
        )
        self._nav["settings"].pack(fill=tk.X, padx=8, pady=1)

        tk.Label(
            side,
            text="INFO",
            font=FONT_SECTION,
            fg=C["dim"],
            bg=C["sidebar"],
            anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(14, 4))
        self._nav["about"] = _NavButton(side, "About", "ℹ", lambda: self._show_page("about"))
        self._nav["about"].pack(fill=tk.X, padx=8, pady=1)

        footer = tk.Frame(side, bg=C["sidebar"])
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=14)
        ver = core.installed_pack_version() or "dev"
        RoundBadge(footer, f"pack {ver}").pack(side=tk.LEFT)
        quit_lbl = tk.Label(
            footer,
            text="Quit",
            font=FONT_UI_SM,
            fg=C["danger"],
            bg=C["sidebar"],
            cursor="hand2",
        )
        quit_lbl.pack(side=tk.RIGHT)
        quit_lbl.bind("<Button-1>", lambda _e: self.destroy())

    def _draw_mark(self, canvas: tk.Canvas) -> None:
        # Fallback mark if logo PNG missing
        canvas.create_oval(2, 2, 26, 26, fill=C["accent_soft"], outline=C["accent"], width=2)
        canvas.create_rectangle(12, 7, 16, 21, fill=C["accent"], outline="")
        canvas.create_polygon(16, 8, 23, 12, 16, 16, fill=C["accent"], outline="")

    def _page_header(self, parent: tk.Frame, title: str) -> None:
        tk.Label(
            parent,
            text=title,
            font=FONT_TITLE,
            fg=C["muted"],
            bg=C["bg"],
            anchor="w",
        ).pack(fill=tk.X, padx=28, pady=(22, 8))
        tk.Frame(parent, bg=C["border"], height=1).pack(fill=tk.X, padx=28, pady=(0, 12))

    def _build_home(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=C["bg"])
        self._page_header(page, "Home")

        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=28, pady=(0, 20))

        hero = RoundCard(
            body,
            fill=C["surface"],
            outline=C["border"],
            radius=RADIUS,
            pad=0,
            parent_bg=C["bg"],
        )
        hero.pack(fill=tk.BOTH, expand=True)

        center = tk.Frame(hero.body, bg=C["surface"])
        center.place(relx=0.5, rely=0.48, anchor="center")

        hero_img = self._photo("pitstop-logo-hero.png")
        if hero_img is not None:
            tk.Label(center, image=hero_img, bg=C["surface"]).pack()
        else:
            tk.Label(
                center,
                text="PITSTOP",
                font=FONT_HERO,
                fg=C["accent"],
                bg=C["surface"],
            ).pack(pady=(8, 4))

        tk.Label(
            center,
            text="Created by Madesh",
            font=FONT_UI_SM,
            fg=C["muted"],
            bg=C["surface"],
        ).pack(pady=(10, 18))

        self.play_btn = RoundButton(center, "▶   Play", self._on_play, primary=True, width=260)
        self.play_btn.pack(pady=(0, 10))
        self.setup_btn = RoundButton(
            center, "↻   Check for updates", self._on_check_updates, primary=False, width=260
        )
        self.setup_btn.pack()

        return page

    def _build_licenses(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=C["bg"])
        self._page_header(page, "Licenses")

        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=28, pady=(0, 20))

        self._licenses_stack = tk.Frame(body, bg=C["bg"])
        self._licenses_stack.pack(fill=tk.BOTH, expand=True)

        self._licenses_grid = tk.Frame(self._licenses_stack, bg=C["bg"])
        self._licenses_detail = tk.Frame(self._licenses_stack, bg=C["bg"])

        # 2x2 license tiles
        self._license_tiles: list[RoundCard] = []
        self._license_tile_name: list[tk.Label] = []
        self._license_tile_sub: list[tk.Label] = []
        self._license_primary_vars: list[tk.BooleanVar] = []
        self._license_primary_cbs: list[tk.Checkbutton] = []
        grid = tk.Frame(self._licenses_grid, bg=C["bg"])
        grid.pack(fill=tk.BOTH, expand=True)
        for i in range(4):
            r, c = divmod(i, 2)
            tile = RoundCard(
                grid,
                fill=C["surface"],
                outline=C["border"],
                radius=RADIUS,
                pad=0,
                parent_bg=C["bg"],
            )
            tile.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            grid.rowconfigure(r, weight=1)
            grid.columnconfigure(c, weight=1)
            inner = tk.Frame(tile.body, bg=C["surface"], height=148)
            inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)
            inner.pack_propagate(False)
            name_lbl = tk.Label(
                inner,
                text="No license",
                font=FONT_WII_BRAND if self._wii_font_ok else FONT_BRAND,
                fg=C["dim"],
                bg=C["surface"],
                anchor="w",
            )
            name_lbl.pack(fill=tk.X)
            sub_lbl = tk.Label(
                inner,
                text="Create in-game",
                font=FONT_UI_SM,
                fg=C["dim"],
                bg=C["surface"],
                anchor="w",
            )
            sub_lbl.pack(fill=tk.X, pady=(6, 0))
            primary_var = tk.BooleanVar(value=False)
            primary_cb = tk.Checkbutton(
                inner,
                text="Set as primary",
                variable=primary_var,
                command=lambda idx=i: self._on_primary_toggle(idx),
                font=FONT_UI_SM,
                bg=C["surface"],
                fg=C["muted"],
                activebackground=C["surface"],
                activeforeground=C["accent"],
                selectcolor=C["surface2"],
                highlightthickness=0,
                bd=0,
                cursor="hand2",
                anchor="w",
            )
            primary_cb.pack(fill=tk.X, pady=(10, 0), anchor="w")
            self._license_tiles.append(tile)
            self._license_tile_name.append(name_lbl)
            self._license_tile_sub.append(sub_lbl)
            self._license_primary_vars.append(primary_var)
            self._license_primary_cbs.append(primary_cb)
            for w in (tile, tile.body, inner, name_lbl, sub_lbl):
                w.bind("<Button-1>", lambda _e, idx=i: self._on_license_click(idx))
                w.configure(cursor="hand2")

        self._miis_cache: list[rfldb_mod.MiiEntry] = []
        self._mii_label_to_id: dict[str, int] = {}

        # Detail view
        back = tk.Label(
            self._licenses_detail,
            text="←  All licenses",
            font=FONT_UI_SM,
            fg=C["accent"],
            bg=C["bg"],
            cursor="hand2",
            anchor="w",
        )
        back.pack(fill=tk.X, pady=(0, 12))
        back.bind("<Button-1>", lambda _e: self._show_licenses_grid())

        detail_card = RoundCard(
            self._licenses_detail,
            fill=C["surface"],
            outline=C["border"],
            radius=RADIUS,
            pad=0,
            parent_bg=C["bg"],
        )
        detail_card.pack(fill=tk.X)

        tk.Label(
            detail_card.body,
            text="License / Mii name",
            font=FONT_UI_SM,
            fg=C["muted"],
            bg=C["surface"],
            anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(14, 4))

        name_row = tk.Frame(detail_card.body, bg=C["surface"])
        name_row.pack(fill=tk.X, padx=16, pady=(0, 8))
        self._license_name_var = tk.StringVar()
        name_font = FONT_WII if self._wii_font_ok else FONT_UI
        self._license_name_entry = tk.Entry(
            name_row,
            textvariable=self._license_name_var,
            font=name_font,
            bg=C["surface2"],
            fg=C["text"],
            insertbackground=C["text"],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
            validate="key",
            validatecommand=(self.register(self._validate_name_key), "%P"),
        )
        self._license_name_entry.pack(
            side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 10)
        )
        RoundButton(
            name_row,
            "Save name",
            self._on_save_license_name,
            primary=True,
            width=130,
            height=40,
        ).pack(side=tk.RIGHT)
        self._license_name_hint = tk.Label(
            detail_card.body,
            text="",
            font=FONT_UI_SM,
            fg=C["dim"],
            bg=C["surface"],
            anchor="w",
            wraplength=520,
            justify="left",
        )
        self._license_name_hint.pack(fill=tk.X, padx=16, pady=(0, 4))

        symbols_hdr = tk.Frame(detail_card.body, bg=C["surface"])
        symbols_hdr.pack(fill=tk.X, padx=16, pady=(4, 0))
        tk.Label(
            symbols_hdr,
            text="Wii symbols",
            font=FONT_UI_SM,
            fg=C["muted"],
            bg=C["surface"],
            anchor="w",
        ).pack(side=tk.LEFT)
        self._wii_symbols_toggle = tk.Label(
            symbols_hdr,
            text="Show",
            font=FONT_UI_SM,
            fg=C["accent"],
            bg=C["surface"],
            cursor="hand2",
        )
        self._wii_symbols_toggle.pack(side=tk.RIGHT)
        self._wii_symbols_toggle.bind("<Button-1>", lambda _e: self._toggle_wii_symbols())

        self._wii_symbols_wrap = tk.Frame(detail_card.body, bg=C["surface"])
        # Filled lazily on first show
        self._wii_symbols_built = False
        self._wii_symbols_visible = False
        self._license_detail_card = detail_card

        mii_assign = tk.Frame(detail_card.body, bg=C["surface"])
        self._license_mii_assign = mii_assign
        mii_assign.pack(fill=tk.X, padx=16, pady=(8, 4))
        tk.Label(
            mii_assign,
            text="Assign Mii",
            font=FONT_UI_SM,
            fg=C["muted"],
            bg=C["surface"],
            anchor="w",
        ).pack(fill=tk.X)
        assign_row = tk.Frame(mii_assign, bg=C["surface"])
        assign_row.pack(fill=tk.X, pady=(4, 0))
        self._license_mii_select = RoundSelect(
            assign_row,
            font=FONT_WII if self._wii_font_ok else FONT_UI,
            parent_bg=C["surface"],
            on_toggle=lambda _open: self.after_idle(self._license_detail_card._sync_height),
        )
        self._license_mii_select.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        RoundButton(
            assign_row,
            "Use Mii",
            self._on_assign_license_mii,
            primary=False,
            width=110,
            height=40,
        ).pack(side=tk.RIGHT)

        stats = tk.Frame(detail_card.body, bg=C["surface"])
        stats.pack(fill=tk.X, padx=16, pady=(8, 8))
        tk.Label(
            stats,
            text="VR",
            font=FONT_UI_SM,
            fg=C["muted"],
            bg=C["surface"],
            anchor="w",
        ).pack(fill=tk.X)
        self._license_vr_lbl = tk.Label(
            stats,
            text="—",
            font=FONT_TITLE,
            fg=C["accent"],
            bg=C["surface"],
            anchor="w",
        )
        self._license_vr_lbl.pack(fill=tk.X, pady=(2, 0))

        fc_wrap = tk.Frame(detail_card.body, bg=C["surface"])
        fc_wrap.pack(fill=tk.X, padx=16, pady=(12, 16))
        tk.Label(
            fc_wrap,
            text="Friend code",
            font=FONT_UI_SM,
            fg=C["muted"],
            bg=C["surface"],
            anchor="w",
        ).pack(fill=tk.X)
        fc_row = tk.Frame(fc_wrap, bg=C["surface"])
        fc_row.pack(fill=tk.X, pady=(4, 0))
        self._license_fc_lbl = tk.Label(
            fc_row,
            text="—",
            font=FONT_UI,
            fg=C["text"],
            bg=C["surface"],
            anchor="w",
        )
        self._license_fc_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._license_fc_copy = RoundButton(
            fc_row,
            "Copy",
            self._on_copy_friend_code,
            primary=False,
            width=90,
            height=36,
        )
        self._license_fc_copy.pack(side=tk.RIGHT)

        self._license_detail_index: int | None = None
        self._licenses_cache: list[rksys_mod.License] = rksys_mod.empty_licenses()
        self._show_licenses_grid()
        return page

    def _rksys_path(self) -> Path | None:
        try:
            return rksys_mod.find_rksys(self.cfg)
        except rksys_mod.IsolationError as e:
            messagebox.showerror("Pitstop", str(e))
            return None

    def _load_licenses(self) -> list[rksys_mod.License]:
        try:
            core.ensure_pitstop_user(self.cfg)
            core.ensure_pitstop_save(self.cfg)
            core.assert_save_isolation(self.cfg)
        except (OSError, RuntimeError, rksys_mod.IsolationError) as e:
            messagebox.showerror("Pitstop", str(e))
            return rksys_mod.empty_licenses()

        try:
            rfldb_mod.sync_from_dolphin(self.cfg)
            self._miis_cache = rfldb_mod.list_miis(rfldb_mod.pitstop_rfldb_path(self.cfg))
        except (OSError, ValueError, RuntimeError, rksys_mod.IsolationError):
            self._miis_cache = []

        path = self._rksys_path()
        if path is None:
            return rksys_mod.empty_licenses()
        try:
            return rksys_mod.read_licenses(path)
        except ValueError as e:
            messagebox.showerror("Pitstop", str(e))
            return rksys_mod.empty_licenses()

    def _dolphin_running(self) -> bool:
        try:
            import subprocess

            out = subprocess.check_output(["pgrep", "-f", "Dolphin.app"], text=True)
            return bool(out.strip())
        except (OSError, subprocess.CalledProcessError):
            return False

    def _toggle_wii_symbols(self) -> None:
        if self._wii_symbols_visible:
            self._wii_symbols_wrap.pack_forget()
            self._wii_symbols_visible = False
            self._wii_symbols_toggle.configure(text="Show")
            self.after_idle(self._license_detail_card._sync_height)
            return
        if not self._wii_symbols_built:
            self._build_wii_symbols_grid()
            self._wii_symbols_built = True
        # Insert directly under the name / symbols header (not below friend code)
        self._wii_symbols_wrap.pack(
            fill=tk.X,
            padx=16,
            pady=(6, 4),
            before=self._license_mii_assign,
        )
        self._wii_symbols_visible = True
        self._wii_symbols_toggle.configure(text="Hide")
        self.after_idle(self._license_detail_card._sync_height)

    def _build_wii_symbols_grid(self) -> None:
        if not self._wii_font_ok:
            tk.Label(
                self._wii_symbols_wrap,
                text="Wii symbol font missing (ctmkf.ttf).",
                font=FONT_UI_SM,
                fg=C["danger"],
                bg=C["surface"],
                anchor="w",
            ).pack(fill=tk.X)
            return
        cols = 10
        # Dark cells — macOS tk.Button ignores colors (white face); Labels keep contrast.
        cell_bg = "#0c0a12"
        cell_fg = "#f3eefc"
        grid = tk.Frame(self._wii_symbols_wrap, bg=C["border"])
        grid.pack(fill=tk.X)
        btn_font = FONT_WII_SM
        for i, ch in enumerate(wii_chars_mod.custom_characters()):
            r, c = divmod(i, cols)
            cell = tk.Label(
                grid,
                text=ch,
                font=btn_font,
                width=3,
                bg=cell_bg,
                fg=cell_fg,
                relief=tk.FLAT,
                padx=4,
                pady=6,
                cursor="hand2",
            )
            cell.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
            cell.bind("<Button-1>", lambda _e, c=ch: self._insert_wii_char(c))
            cell.bind(
                "<Enter>",
                lambda _e, w=cell: w.configure(bg=C["accent_soft"], fg=C["accent"]),
            )
            cell.bind(
                "<Leave>",
                lambda _e, w=cell: w.configure(bg=cell_bg, fg=cell_fg),
            )
        for c in range(cols):
            grid.columnconfigure(c, weight=1)

    def _validate_name_key(self, proposed: str) -> bool:
        """Block typing/paste beyond the Wii 10-character name limit."""
        return len(proposed) <= rksys_mod.NAME_MAX_CHARS

    def _insert_wii_char(self, ch: str) -> None:
        entry = self._license_name_entry
        try:
            before = entry.get()
            if len(before) >= rksys_mod.NAME_MAX_CHARS:
                return
            entry.insert(tk.INSERT, ch)
        except tk.TclError:
            cur = self._license_name_var.get()
            if len(cur) < rksys_mod.NAME_MAX_CHARS:
                self._license_name_var.set(cur + ch)
        entry.focus_set()

    def _on_save_license_name(self) -> None:
        if self._license_detail_index is None:
            return
        if self._dolphin_running():
            messagebox.showwarning(
                "Pitstop",
                "Quit Dolphin completely before renaming a license.\n"
                "If Dolphin is open it can overwrite the save when it exits.",
            )
            return
        path = self._rksys_path()
        if path is None:
            messagebox.showerror("Pitstop", "No Pitstop save found.")
            return
        try:
            path = rksys_mod.assert_pitstop_only(path, self.cfg)
        except rksys_mod.IsolationError as e:
            messagebox.showerror("Pitstop", str(e))
            return
        name = self._license_name_var.get()
        try:
            updated = rksys_mod.set_license_name(
                path, self._license_detail_index, name, cfg=self.cfg
            )
        except (OSError, ValueError) as e:
            messagebox.showerror("Pitstop", str(e))
            return
        self._licenses_cache[self._license_detail_index] = updated
        self._refresh_licenses()
        messagebox.showinfo(
            "Pitstop",
            "Name saved on this Pitstop license and its Mii.\n\n"
            "Dolphin’s Mii Channel is unchanged.\n"
            "Play from Pitstop to see it in-game.",
        )

    def _on_assign_license_mii(self) -> None:
        if self._license_detail_index is None:
            return
        if self._dolphin_running():
            messagebox.showwarning(
                "Pitstop",
                "Quit Dolphin completely before assigning a Mii.\n"
                "If Dolphin is open it can overwrite the save when it exits.",
            )
            return
        label = self._license_mii_select.get().strip()
        mii_id = self._mii_label_to_id.get(label)
        mii = next((m for m in self._miis_cache if m.mii_id == mii_id), None)
        if mii is None:
            messagebox.showerror("Pitstop", "Pick a Mii synced from Dolphin first.")
            return
        path = self._rksys_path()
        if path is None:
            messagebox.showerror("Pitstop", "No Pitstop save found.")
            return
        try:
            path = rksys_mod.assert_pitstop_only(path, self.cfg)
            updated = rksys_mod.set_license_mii(path, self._license_detail_index, mii.raw)
        except (OSError, ValueError, rksys_mod.IsolationError) as e:
            messagebox.showerror("Pitstop", str(e))
            return
        self._licenses_cache[self._license_detail_index] = updated
        self._refresh_licenses()
        messagebox.showinfo(
            "Pitstop",
            f"Assigned Mii “{mii.name}” to this Pitstop license.\n\n"
            "Licenses stay Pitstop-only — Dolphin licenses were not changed.\n"
            "Play from Pitstop, then try renaming here if you want.",
        )

    def _mii_label(self, mii: rfldb_mod.MiiEntry) -> str:
        same = [m for m in self._miis_cache if m.name == mii.name]
        if len(same) <= 1:
            return mii.name
        return f"{mii.name} (#{mii.slot + 1})"

    def _refresh_licenses(self) -> None:
        self._licenses_cache = self._load_licenses()
        primary = self.cfg.get("primary_license_index")
        try:
            primary = int(primary) if primary is not None else None
        except (TypeError, ValueError):
            primary = None
        if primary is not None and (
            primary not in range(4) or not self._licenses_cache[primary].active
        ):
            primary = None
            self.cfg["primary_license_index"] = None
            core.save_config(self.cfg)

        for i, lic in enumerate(self._licenses_cache):
            name_lbl = self._license_tile_name[i]
            sub_lbl = self._license_tile_sub[i]
            cb = self._license_primary_cbs[i]
            var = self._license_primary_vars[i]
            if lic.active:
                name_lbl.configure(text=lic.name, fg=C["text"])
                sub_lbl.configure(text=f"VR  {lic.vr}", fg=C["muted"])
                cb.configure(state=tk.NORMAL)
                var.set(primary == i)
            else:
                name_lbl.configure(text="No license", fg=C["dim"])
                sub_lbl.configure(text="Create in-game", fg=C["dim"])
                var.set(False)
                cb.configure(state=tk.DISABLED)
        self._update_primary_sidebar()
        if self._license_detail_index is not None:
            self._fill_license_detail(self._license_detail_index)

    def _on_primary_toggle(self, index: int) -> None:
        lic = self._licenses_cache[index]
        if not lic.active:
            self._license_primary_vars[index].set(False)
            return
        if self._license_primary_vars[index].get():
            self.cfg["primary_license_index"] = index
            for i, var in enumerate(self._license_primary_vars):
                if i != index:
                    var.set(False)
        else:
            if self.cfg.get("primary_license_index") == index:
                self.cfg["primary_license_index"] = None
        core.save_config(self.cfg)
        self._update_primary_sidebar()

    def _update_primary_sidebar(self) -> None:
        primary = self.cfg.get("primary_license_index")
        try:
            primary = int(primary) if primary is not None else None
        except (TypeError, ValueError):
            primary = None
        lic = None
        if primary in range(4) and self._licenses_cache:
            cand = self._licenses_cache[primary]
            if cand.active:
                lic = cand
        if lic is None:
            self._primary_name_lbl.configure(
                text="Your Name",
                font=FONT_WII_SM if self._wii_font_ok else FONT_UI_SM,
                fg=C["dim"],
            )
            self._primary_vr_lbl.configure(
                text="VR: XXXX",
                fg=C["dim"],
            )
        else:
            self._primary_name_lbl.configure(
                text=lic.name,
                font=FONT_WII_SM if self._wii_font_ok else FONT_UI_SM,
                fg=C["text"],
            )
            self._primary_vr_lbl.configure(
                text=f"VR: {lic.vr}",
                fg=C["accent"],
            )
        self.after_idle(self._primary_blurb_card._sync_height)

    def _show_licenses_grid(self) -> None:
        self._license_detail_index = None
        self._license_mii_select.close()
        self._licenses_detail.pack_forget()
        self._licenses_grid.pack(fill=tk.BOTH, expand=True)

    def _show_license_detail(self, index: int) -> None:
        self._fill_license_detail(index)
        self._licenses_grid.pack_forget()
        self._licenses_detail.pack(fill=tk.BOTH, expand=True)

    def _fill_license_detail(self, index: int) -> None:
        lic = self._licenses_cache[index]
        self._license_detail_index = index
        self._license_name_var.set(lic.name)
        self._license_vr_lbl.configure(text=str(lic.vr))
        if lic.friend_code:
            self._license_fc_lbl.configure(text=lic.friend_code, fg=C["text"])
            self._license_fc_copy.set_enabled(True)
        else:
            self._license_fc_lbl.configure(
                text="Go online once to create a friend code",
                fg=C["dim"],
            )
            self._license_fc_copy.set_enabled(False)
        # Hint when this is a guest Mii that can't be renamed via save edit
        path = self._rksys_path()
        guest = False
        if path is not None:
            try:
                guest = rksys_mod.is_guest_mii(path.read_bytes(), index)
            except OSError:
                guest = False
        if guest:
            self._license_name_hint.configure(
                text="Guest Mii — assign a synced Dolphin Mii below, or change Mii in-game.",
                fg=C["dim"],
            )
        else:
            self._license_name_hint.configure(text="", fg=C["dim"])

        self._mii_label_to_id = {}
        labels: list[str] = []
        for m in self._miis_cache:
            label = self._mii_label(m)
            labels.append(label)
            self._mii_label_to_id[label] = m.mii_id
        assigned = next(
            (self._mii_label(m) for m in self._miis_cache if m.mii_id == lic.avatar_id),
            None,
        )
        self._license_mii_select.set_options(labels, selected=assigned)
        self._license_mii_select.close()

    def _on_license_click(self, index: int) -> None:
        lic = self._licenses_cache[index]
        if not lic.active:
            messagebox.showinfo(
                "Pitstop",
                "This slot is empty. Create a license in Mario Kart Wii first.",
            )
            return
        self._show_license_detail(index)

    def _on_copy_friend_code(self) -> None:
        if self._license_detail_index is None:
            return
        lic = self._licenses_cache[self._license_detail_index]
        if not lic.friend_code:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(lic.friend_code)
            self.update()
        except tk.TclError:
            messagebox.showerror("Pitstop", "Could not copy to clipboard.")
            return
        messagebox.showinfo("Pitstop", f"Copied {lic.friend_code}")

    def _build_settings(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=C["bg"])
        self._page_header(page, "Settings")

        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=28, pady=(0, 24))

        card = RoundCard(
            body,
            fill=C["surface"],
            outline=C["accent"],
            radius=RADIUS,
            pad=0,
            parent_bg=C["bg"],
        )
        card.pack(fill=tk.X)

        tk.Label(
            card.body,
            text="Locations",
            font=FONT_UI,
            fg=C["text"],
            bg=C["surface"],
            anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(14, 4))
        tk.Label(
            card.body,
            text="Saves live in a private Pitstop Dolphin user — not your vanilla MKWii folder.",
            font=FONT_UI_SM,
            fg=C["muted"],
            bg=C["surface"],
            anchor="w",
            wraplength=560,
            justify="left",
        ).pack(fill=tk.X, padx=16, pady=(0, 12))

        self._path_row(card.body, "Dolphin", self.dolphin_var, self._browse_dolphin)
        self._path_row(card.body, "Mario Kart Wii dump", self.game_var, self._browse_game)

        tk.Label(
            card.body,
            text="NTSC-U (RMCE01) rev 00 · WBFS / ISO / RVZ",
            font=FONT_UI_SM,
            fg=C["dim"],
            bg=C["surface"],
            anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(4, 16))

        actions = tk.Frame(card.body, bg=C["surface"])
        actions.pack(fill=tk.X, padx=16, pady=(0, 16))
        RoundButton(actions, "Save paths", self._on_save_paths, primary=True, width=140, height=40).pack(
            side=tk.RIGHT
        )

        data = RoundCard(
            body,
            fill=C["surface"],
            outline=C["border"],
            radius=RADIUS,
            pad=0,
            parent_bg=C["bg"],
        )
        data.pack(fill=tk.X, pady=(16, 0))
        tk.Label(
            data.body,
            text="Pitstop data folder",
            font=FONT_UI,
            fg=C["text"],
            bg=C["surface"],
            anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(14, 6))
        self._data_path_var = tk.StringVar(value=str(core.config_path().parent))
        RoundField(data.body, self._data_path_var, browse=None, parent_bg=C["surface"]).pack(
            fill=tk.X, padx=16, pady=(0, 14)
        )

        return page

    def _path_row(self, parent: tk.Frame, label: str, var: tk.StringVar, browse) -> None:
        wrap = tk.Frame(parent, bg=C["surface"])
        wrap.pack(fill=tk.X, padx=16, pady=6)
        tk.Label(
            wrap,
            text=label,
            font=FONT_UI_SM,
            fg=C["muted"],
            bg=C["surface"],
            anchor="w",
        ).pack(fill=tk.X)
        RoundField(wrap, var, browse, parent_bg=C["surface"]).pack(fill=tk.X, pady=(4, 0))

    def _build_about(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=C["bg"])
        self._page_header(page, "About")
        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=28, pady=(0, 24))

        card = RoundCard(
            body,
            fill=C["surface"],
            outline=C["border"],
            radius=RADIUS,
            pad=0,
            parent_bg=C["bg"],
        )
        card.pack(fill=tk.X)
        lines = [
            ("Pitstop", C["text"], FONT_BRAND),
            ("Private Mario Kart Wii for friends", C["muted"], FONT_UI),
            ("", C["muted"], FONT_UI_SM),
            ("Server  psmk.duckdns.org", C["muted"], FONT_UI_SM),
            ("Dump stays read-only — patch lives in a private Dolphin user", C["dim"], FONT_UI_SM),
            ("150cc Private WWFC", C["dim"], FONT_UI_SM),
            ("Unlock characters / vehicles / cups", C["dim"], FONT_UI_SM),
        ]
        for text, fg, font in lines:
            if not text:
                tk.Frame(card.body, bg=C["surface"], height=8).pack()
                continue
            tk.Label(card.body, text=text, font=font, fg=fg, bg=C["surface"], anchor="w").pack(
                fill=tk.X, padx=16, pady=2
            )
        tk.Frame(card.body, bg=C["surface"], height=12).pack()
        return page

    def _show_page(self, name: str) -> None:
        self._page = name
        for key, frame in self._pages.items():
            if key == name:
                frame.pack(fill=tk.BOTH, expand=True)
            else:
                frame.pack_forget()
        for key, nav in self._nav.items():
            nav.set_active(key == name)
        if name == "licenses":
            self._show_licenses_grid()
            self._refresh_licenses()

    def _log(self, text: str) -> None:
        if text.strip():
            print(text, end="" if text.endswith("\n") else "\n")

    def _append_raw(self, s: str) -> None:
        if s:
            print(s, end="")

    def _browse_dolphin(self) -> None:
        if platform.system() == "Darwin":
            path = filedialog.askopenfilename(
                title="Select Dolphin",
                initialdir="/Applications",
            )
            if path and path.endswith(".app"):
                path = str(Path(path) / "Contents" / "MacOS" / "Dolphin")
        elif platform.system() == "Windows":
            path = filedialog.askopenfilename(
                title="Select Dolphin.exe",
                filetypes=[("Executable", "*.exe"), ("All", "*.*")],
            )
        else:
            path = filedialog.askopenfilename(title="Select dolphin-emu")
        if path:
            self.dolphin_var.set(path)

    def _browse_game(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Mario Kart Wii (NTSC-U)",
            filetypes=[
                ("Wii images", "*.wbfs *.iso *.gcm *.rvz"),
                ("All", "*.*"),
            ],
        )
        if path:
            self.game_var.set(path)

    def _on_save_paths(self) -> None:
        self._save_paths()
        messagebox.showinfo("Pitstop", "Paths saved.")

    def _save_paths(self) -> dict:
        self.cfg["dolphin_path"] = core.normalize_dolphin_path(self.dolphin_var.get())
        self.cfg["game_path"] = self.game_var.get().strip()
        self.dolphin_var.set(self.cfg["dolphin_path"])
        if not self.cfg.get("dolphin_user_path"):
            self.cfg["dolphin_user_path"] = core.default_dolphin_user()
        if not self.cfg.get("pitstop_user_path"):
            self.cfg["pitstop_user_path"] = core.default_pitstop_user()
        core.save_config(self.cfg)
        return self.cfg

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.play_btn.set_enabled(not busy)
        self.setup_btn.set_enabled(not busy)

    def _run_bg(self, label: str, fn, *, on_success=None) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._show_page("home")
        self._log(f"\n— {label} —\n")

        def work() -> None:
            err: Exception | None = None
            code = 0
            result = None
            buf = _LogWriter(lambda s: self.after(0, self._append_raw, s))
            try:
                with redirect_stdout(buf):
                    result = fn()
                    if isinstance(result, int):
                        code = result
            except Exception as e:  # noqa: BLE001 — surface to UI
                err = e

            def done() -> None:
                self._set_busy(False)
                if err is not None:
                    messagebox.showerror("Pitstop", str(err))
                elif code != 0:
                    messagebox.showwarning("Pitstop", f"Finished with exit code {code}")
                elif on_success is not None and err is None:
                    on_success(result)

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _on_check_updates(self) -> None:
        cfg = self._save_paths()
        if not cfg.get("game_path") or not Path(cfg["game_path"]).exists():
            messagebox.showwarning(
                "Pitstop",
                "Set your Mario Kart Wii dump path in Settings first.",
            )
            return
        if not cfg.get("dolphin_path") or not core.dolphin_path_ok(cfg["dolphin_path"]):
            messagebox.showwarning(
                "Pitstop",
                "Set a valid Dolphin path in Settings first.",
            )
            return

        def report(result) -> None:
            if isinstance(result, core.PackSyncResult):
                if result.changed:
                    messagebox.showinfo(
                        "Pitstop",
                        f"Update installed.\n\nPack is now v{result.version}.",
                    )
                else:
                    messagebox.showinfo(
                        "Pitstop",
                        f"You're up to date.\n\nPack v{result.version} — nothing new.",
                    )
            else:
                messagebox.showinfo("Pitstop", "Update check finished.")

        self._run_bg("Check for updates", lambda: core.setup(cfg), on_success=report)

    def _on_play(self) -> None:
        if core.needs_first_run(self.cfg):
            self._maybe_first_run()
            return
        cfg = self._save_paths()

        def play() -> int:
            return core.launch(cfg)

        self._run_bg("Play", play)

    def _maybe_first_run(self) -> None:
        if not core.needs_first_run(self.cfg):
            return
        FirstRunWizard(self)

    def _apply_first_run(self, dolphin: str, game: str) -> None:
        self.dolphin_var.set(dolphin)
        self.game_var.set(game)
        self.cfg["dolphin_path"] = core.normalize_dolphin_path(dolphin)
        self.cfg["game_path"] = game
        self.cfg["setup_complete"] = True
        if not self.cfg.get("dolphin_user_path"):
            self.cfg["dolphin_user_path"] = core.default_dolphin_user()
        if not self.cfg.get("pitstop_user_path"):
            self.cfg["pitstop_user_path"] = core.default_pitstop_user()
        core.save_config(self.cfg)
        self._refresh_licenses()


class FirstRunWizard(tk.Toplevel):
    """Blocking first-launch setup: permission → paths → download pack."""

    def __init__(self, app: PitstopApp):
        super().__init__(app)
        self.app = app
        self.title("Welcome to Pitstop")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._deny_and_quit)
        self.geometry("520x420")
        self._step = 0
        self._dolphin_var = tk.StringVar()
        self._game_var = tk.StringVar()
        self._status = tk.StringVar(value="")
        self._body = tk.Frame(self, bg=C["bg"])
        self._body.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)
        found = core.discover_dolphin_binary()
        if found is not None:
            self._dolphin_var.set(str(found))
        elif app.dolphin_var.get().strip():
            self._dolphin_var.set(app.dolphin_var.get().strip())
        if app.game_var.get().strip():
            self._game_var.set(app.game_var.get().strip())
        self._show_permission()

    def _clear(self) -> None:
        for w in self._body.winfo_children():
            w.destroy()

    def _deny_and_quit(self) -> None:
        messagebox.showinfo(
            "Pitstop",
            "Pitstop can’t run without its own save folders.\n"
            "Opening the app again will show this welcome setup.",
            parent=self,
        )
        self.grab_release()
        self.destroy()
        self.app.destroy()

    def _show_permission(self) -> None:
        self._clear()
        tk.Label(
            self._body,
            text="Welcome to Pitstop",
            font=FONT_TITLE,
            fg=C["accent"],
            bg=C["bg"],
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            self._body,
            text=(
                "Pitstop needs permission to create its own folders for saves, "
                "settings, and the downloadable pack.\n\n"
                "These stay separate from normal Dolphin — your vanilla saves "
                "are never used or overwritten."
            ),
            font=FONT_UI,
            fg=C["text"],
            bg=C["bg"],
            anchor="w",
            justify="left",
            wraplength=460,
        ).pack(fill=tk.X, pady=(0, 20))
        row = tk.Frame(self._body, bg=C["bg"])
        row.pack(fill=tk.X, pady=(12, 0))
        RoundButton(row, "Don’t allow", self._deny_and_quit, primary=False, width=150).pack(
            side=tk.LEFT
        )
        RoundButton(row, "Allow & continue", self._on_allow, primary=True, width=180).pack(
            side=tk.RIGHT
        )

    def _on_allow(self) -> None:
        try:
            self.app.cfg["pitstop_user_path"] = core.default_pitstop_user()
            self.app.cfg["dolphin_user_path"] = (
                self.app.cfg.get("dolphin_user_path") or core.default_dolphin_user()
            )
            core.ensure_pitstop_user(self.app.cfg)
            core.config_path().parent.mkdir(parents=True, exist_ok=True)
            core.save_config(self.app.cfg)
        except OSError as e:
            messagebox.showerror("Pitstop", f"Could not create Pitstop folders:\n{e}", parent=self)
            return
        self._show_paths()

    def _path_entry(self, parent, var: tk.StringVar, browse_cmd) -> tk.Entry:
        row = tk.Frame(parent, bg=C["bg"])
        row.pack(fill=tk.X, pady=(0, 10))
        entry = tk.Entry(
            row,
            textvariable=var,
            font=FONT_UI_SM,
            bg=C["surface2"],
            fg=C["text"],
            insertbackground=C["text"],
            relief=tk.FLAT,
            highlightthickness=2,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 8))
        RoundButton(row, "Browse", browse_cmd, primary=False, width=90, height=36).pack(
            side=tk.RIGHT
        )
        return entry

    def _show_paths(self) -> None:
        self._clear()
        tk.Label(
            self._body,
            text="Find Dolphin & your dump",
            font=FONT_TITLE,
            fg=C["accent"],
            bg=C["bg"],
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            self._body,
            text="Dolphin is highlighted green when found automatically.",
            font=FONT_UI_SM,
            fg=C["muted"],
            bg=C["bg"],
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 14))

        tk.Label(
            self._body, text="Dolphin", font=FONT_UI_SM, fg=C["muted"], bg=C["bg"], anchor="w"
        ).pack(fill=tk.X)
        self._dolphin_entry = self._path_entry(self._body, self._dolphin_var, self._browse_dolphin)
        self._dolphin_var.trace_add("write", lambda *_: self._paint_dolphin())

        tk.Label(
            self._body,
            text="Mario Kart Wii dump (NTSC-U)",
            font=FONT_UI_SM,
            fg=C["muted"],
            bg=C["bg"],
            anchor="w",
        ).pack(fill=tk.X, pady=(8, 0))
        self._game_entry = self._path_entry(self._body, self._game_var, self._browse_game)

        self._status_lbl = tk.Label(
            self._body,
            textvariable=self._status,
            font=FONT_UI_SM,
            fg=C["dim"],
            bg=C["bg"],
            anchor="w",
            wraplength=460,
            justify="left",
        )
        self._status_lbl.pack(fill=tk.X, pady=(12, 0))

        row = tk.Frame(self._body, bg=C["bg"])
        row.pack(fill=tk.X, pady=(18, 0))
        RoundButton(
            row, "Download pack & finish", self._finish, primary=True, width=220
        ).pack(side=tk.RIGHT)
        self._paint_dolphin()

    def _paint_dolphin(self) -> None:
        ok = core.dolphin_path_ok(self._dolphin_var.get())
        color = C["ok"] if ok else C["border"]
        self._dolphin_entry.configure(highlightbackground=color, highlightcolor=color)

    def _browse_dolphin(self) -> None:
        if platform.system() == "Darwin":
            path = filedialog.askopenfilename(
                parent=self,
                title="Select Dolphin",
                filetypes=[("Dolphin", "Dolphin*"), ("All", "*.*")],
            )
            if not path:
                path = filedialog.askdirectory(parent=self, title="Select Dolphin.app")
        else:
            path = filedialog.askopenfilename(
                parent=self,
                title="Select Dolphin.exe",
                filetypes=[("Executable", "*.exe"), ("All", "*.*")],
            )
        if path:
            self._dolphin_var.set(core.normalize_dolphin_path(path))

    def _browse_game(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Select Mario Kart Wii dump",
            filetypes=[
                ("Wii images", "*.wbfs *.iso *.gcm *.rvz"),
                ("All", "*.*"),
            ],
        )
        if path:
            self._game_var.set(path)

    def _finish(self) -> None:
        dolphin = core.normalize_dolphin_path(self._dolphin_var.get())
        game = self._game_var.get().strip()
        if not core.dolphin_path_ok(dolphin):
            messagebox.showerror("Pitstop", "Select a valid Dolphin app / executable.", parent=self)
            return
        if not game or not Path(game).is_file():
            messagebox.showerror(
                "Pitstop",
                "Select your Mario Kart Wii dump (WBFS/ISO/RVZ).",
                parent=self,
            )
            return

        self._status.set("Downloading latest pack and preparing…")
        self.update_idletasks()
        cfg = dict(self.app.cfg)
        cfg["dolphin_path"] = dolphin
        cfg["game_path"] = game
        cfg["pitstop_user_path"] = cfg.get("pitstop_user_path") or core.default_pitstop_user()
        cfg["dolphin_user_path"] = cfg.get("dolphin_user_path") or core.default_dolphin_user()

        def work() -> core.PackSyncResult:
            result = core.setup(cfg)
            try:
                import rfldb as rfldb_mod

                rfldb_mod.sync_from_dolphin(cfg)
            except Exception:  # noqa: BLE001
                pass
            return result

        def run() -> None:
            try:
                result = work()
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: self._fail(str(e)))
                return
            self.after(0, lambda: self._done(dolphin, game, result))

        threading.Thread(target=run, daemon=True).start()

    def _fail(self, err: str) -> None:
        self._status.set("")
        messagebox.showerror("Pitstop", err, parent=self)

    def _done(self, dolphin: str, game: str, result: core.PackSyncResult) -> None:
        self.app._apply_first_run(dolphin, game)
        self.grab_release()
        self.destroy()
        note = (
            f"Pack v{result.version} ready."
            if not result.changed
            else f"Downloaded pack v{result.version}."
        )
        messagebox.showinfo(
            "Pitstop",
            "Setup complete.\n\n"
            f"{note}\n\n"
            "Miis sync from Dolphin automatically.\n"
            "Create a license in-game, then use Licenses in Pitstop to rename, "
            "assign Miis, and set a primary.",
            parent=self.app,
        )


def run_gui() -> int:
    app = PitstopApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_gui())
