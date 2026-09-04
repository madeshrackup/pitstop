#!/usr/bin/env python3
"""Pitstop friend-facing tkinter launcher."""

from __future__ import annotations

import io
import platform
import threading
import tkinter as tk
from contextlib import redirect_stdout
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pitstop as core


class _LogWriter(io.TextIOBase):
    def __init__(self, append_fn):
        self._append = append_fn

    def write(self, s: str) -> int:
        if s:
            self._append(s)
        return len(s)

    def flush(self) -> None:
        pass


class PitstopApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Pitstop")
        self.minsize(560, 420)
        self.geometry("640x480")

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

        self._build()

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Pitstop", font=("Helvetica", 18, "bold")).pack(anchor=tk.W)

        ttk.Label(
            frm,
            text="Private Mario Kart Wii online — your dump stays untouched.",
        ).pack(anchor=tk.W, pady=(0, 8))

        # Dolphin
        row1 = ttk.Frame(frm)
        row1.pack(fill=tk.X, **pad)
        ttk.Label(row1, text="Dolphin", width=14).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.dolphin_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6)
        )
        ttk.Button(row1, text="Browse…", command=self._browse_dolphin).pack(side=tk.LEFT)

        # Game
        row2 = ttk.Frame(frm)
        row2.pack(fill=tk.X, **pad)
        ttk.Label(row2, text="MKWii dump", width=14).pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.game_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6)
        )
        ttk.Button(row2, text="Browse…", command=self._browse_game).pack(side=tk.LEFT)

        ttk.Label(
            frm,
            text="NTSC-U (RMCE01) rev 00 · WBFS or ISO",
            foreground="#555",
        ).pack(anchor=tk.W, padx=12)

        # Buttons
        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X, pady=12)
        self.setup_btn = ttk.Button(btns, text="Setup / Update", command=self._on_setup)
        self.setup_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.play_btn = ttk.Button(btns, text="Play", command=self._on_play)
        self.play_btn.pack(side=tk.LEFT)

        ttk.Label(frm, text="Status").pack(anchor=tk.W)
        self.log = tk.Text(frm, height=14, wrap=tk.WORD, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        scroll = ttk.Scrollbar(self.log, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)

        self._log(
            "1) Install Dolphin\n"
            "2) Pick your NTSC-U Mario Kart Wii dump\n"
            "3) Setup / Update — downloads the latest pack, then builds cache\n"
            "4) Play\n"
        )
        url = (self.cfg.get("pack_manifest_url") or core.DEFAULT_PACK_MANIFEST_URL or "").strip()
        if url:
            self._log(f"Pack updates from:\n  {url}\n")
        else:
            self._log(
                "WARNING: no pack_manifest_url set — set it in config or bake\n"
                "DEFAULT_PACK_MANIFEST_URL (see launcher/HOSTING.md).\n"
            )
        ver = core.installed_pack_version()
        if ver:
            self._log(f"Installed pack: v{ver}\n  {core.pack_install_dir()}\n")

    def _log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        if not text.endswith("\n"):
            self.log.insert(tk.END, "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _append_raw(self, s: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, s)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

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

    def _save_paths(self) -> dict:
        self.cfg["dolphin_path"] = self.dolphin_var.get().strip()
        self.cfg["game_path"] = self.game_var.get().strip()
        if not self.cfg.get("dolphin_user_path"):
            self.cfg["dolphin_user_path"] = core.default_dolphin_user()
        if not self.cfg.get("pitstop_user_path"):
            self.cfg["pitstop_user_path"] = core.default_pitstop_user()
        core.save_config(self.cfg)
        return self.cfg

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.setup_btn.configure(state=state)
        self.play_btn.configure(state=state)

    def _run_bg(self, label: str, fn) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._log(f"\n— {label} —")

        def work() -> None:
            err: Exception | None = None
            code = 0
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
                    self._log(f"ERROR: {err}")
                    messagebox.showerror("Pitstop", str(err))
                elif code != 0:
                    self._log(f"Finished with exit code {code}")
                else:
                    self._log("Done.")

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _on_setup(self) -> None:
        cfg = self._save_paths()
        self._run_bg("Setup / Update", lambda: core.setup(cfg))

    def _on_play(self) -> None:
        cfg = self._save_paths()

        def play() -> int:
            return core.launch(cfg)

        self._run_bg("Play", play)


def run_gui() -> int:
    app = PitstopApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_gui())
