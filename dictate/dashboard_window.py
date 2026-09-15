"""Open the dashboard as a native webview window.

The dashboard is a small web app (built from ``dashboard/``) rendered in a
pywebview window. It runs as its **own process** — the tray / menu-bar app simply
spawns it — so pywebview can own its process's main run loop without fighting
AppKit's NSApplication loop (or the tray loop). The window talks to Python through
:class:`dictate.bridge.DashboardAPI`, reading the same local SQLite history.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import __version__
from .bridge import DashboardAPI

WINDOW_TITLE = "Voca"


def _assets_dir() -> Path | None:
    """Locate the built dashboard (index.html + assets)."""
    candidates: list[Path] = []
    # PyInstaller bundle: assets copied next to the frozen app.
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(Path(base) / "dashboard")
    # macOS .app Resources (py2app / PyInstaller onedir).
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "dashboard")
    # Dev checkout: dashboard/dist next to the repo.
    repo = Path(__file__).resolve().parent.parent
    candidates.append(repo / "dashboard" / "dist")

    for c in candidates:
        if (c / "index.html").exists():
            return c
    return None


_PLACEHOLDER = """<!doctype html><html><head><meta charset="utf-8">
<title>Voca</title>
<style>
  html,body{margin:0;height:100%;background:#0b0b0f;color:#e7e7ea;
    font:15px/1.5 -apple-system,Segoe UI,system-ui,sans-serif;
    display:grid;place-items:center;text-align:center}
  .card{max-width:32rem;padding:2rem}
  code{background:#1b1b22;padding:.15rem .4rem;border-radius:.35rem}
</style></head><body><div class="card">
  <h1>Dashboard not built yet</h1>
  <p>From the repo root run <code>./build_app.sh</code> (or
  <code>npm ci &amp;&amp; npm --workspace dashboard run build</code>), then reopen.</p>
</div></body></html>"""


def open_window() -> None:
    import webview

    api = DashboardAPI(app_version=__version__)
    assets = _assets_dir()
    if assets is not None:
        target = str(assets / "index.html")
    else:
        target = _PLACEHOLDER

    webview.create_window(
        WINDOW_TITLE,
        url=target if assets is not None else None,
        html=None if assets is not None else _PLACEHOLDER,
        js_api=api,
        width=1180,
        height=820,
        min_size=(900, 600),
        background_color="#0b0b0f",
    )
    # gui=None lets pywebview pick the best native backend per OS
    # (Cocoa/WKWebView on macOS, EdgeChromium/WebView2 on Windows).
    webview.start()


def main() -> int:
    # Help pywebview find WebView2 etc.; harmless elsewhere.
    os.environ.setdefault("PYWEBVIEW_GUI", "")
    open_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
