(() => {
  const RELEASE =
    "https://github.com/madeshrackup/pitstop/releases/latest/download";

  /** Flip `available` to true once Pitstop.exe is on the GitHub release. */
  const PLATFORMS = {
    mac: {
      id: "mac",
      label: "macOS",
      button: "Download for macOS",
      url: `${RELEASE}/Pitstop.dmg`,
      available: true,
    },
    win: {
      id: "win",
      label: "Windows",
      button: "Download for Windows",
      url: `${RELEASE}/Pitstop.exe`,
      available: false,
      soonLabel: "Windows coming soon",
    },
  };

  function detectOs() {
    const ua = navigator.userAgent || "";
    const platform = navigator.platform || "";
    if (/Windows/i.test(ua) || /Win/i.test(platform)) return "win";
    if (/Mac|iPhone|iPad|iPod/i.test(ua) || /Mac/i.test(platform)) return "mac";
    return "mac";
  }

  function render() {
    const primaryId = detectOs();
    const primary = PLATFORMS[primaryId];
    const others = Object.values(PLATFORMS).filter((p) => p.id !== primaryId);

    const primaryBtn = document.getElementById("primary-download");
    if (primary.available) {
      primaryBtn.href = primary.url;
      primaryBtn.textContent = primary.button;
      primaryBtn.classList.remove("is-disabled");
      primaryBtn.removeAttribute("aria-disabled");
    } else {
      primaryBtn.href = "#";
      primaryBtn.textContent = primary.soonLabel || `${primary.label} coming soon`;
      primaryBtn.classList.add("is-disabled");
      primaryBtn.setAttribute("aria-disabled", "true");
    }

    const menu = document.getElementById("other-menu");
    menu.replaceChildren();
    for (const p of others) {
      const a = document.createElement(p.available ? "a" : "span");
      a.className = "other-link" + (p.available ? "" : " is-disabled");
      if (p.available) {
        a.href = p.url;
        a.textContent = `Download for ${p.label}`;
      } else {
        a.textContent = p.soonLabel || `${p.label} coming soon`;
        const hint = document.createElement("span");
        hint.className = "hint";
        hint.textContent = "Available after the Windows build is uploaded";
        a.appendChild(hint);
      }
      menu.appendChild(a);
    }
  }

  function setupDropdown() {
    const toggle = document.getElementById("other-toggle");
    const menu = document.getElementById("other-menu");
    const root = document.getElementById("other");

    const setOpen = (open) => {
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      menu.hidden = !open;
    };

    toggle.addEventListener("click", (e) => {
      e.stopPropagation();
      setOpen(menu.hidden);
    });

    document.addEventListener("click", (e) => {
      if (!root.contains(e.target)) setOpen(false);
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setOpen(false);
    });
  }

  render();
  setupDropdown();
})();
