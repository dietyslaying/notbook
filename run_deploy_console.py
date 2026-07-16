#!/usr/bin/env python3
"""Launch the Notbook Deploy Console (retro management UI).

Local:
  python run_deploy_console.py

Render / cloud (Web Service — NOT Static Site):
  Build:  pip install -r requirements-console.txt
  Start:  python run_deploy_console.py
  Env:    PORT (auto), CONSOLE_PASSWORD (required recommended), secrets…

  Bot service uses requirements.txt; console uses requirements-console.txt.

Production uses Waitress (not Flask's built-in server). The dev server +
background PDF embed + aggressive polling was crashing with heap corruption
(malloc_consolidate) on Render free tier.
"""

from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "deploy_console"))

# Ensure Flask is available
try:
    import flask  # noqa: F401
except ImportError:
    print("Installing Flask for Deploy Console…")
    import subprocess

    req = ROOT / "requirements-console.txt"
    if req.is_file():
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(req)]
        )
    else:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "flask>=3.0.0", "pyyaml>=6.0", "waitress>=3.0.0"]
        )

from app import app, _ensure_dirs  # noqa: E402


def _use_waitress() -> bool:
    # Prefer Waitress on Render / Docker / any non-local bind
    if os.getenv("CONSOLE_USE_FLASK_DEV", "").strip() in ("1", "true", "yes"):
        return False
    if os.getenv("RENDER") or os.getenv("PORT"):
        return True
    if os.getenv("CONSOLE_USE_WAITRESS", "1").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return False


if __name__ == "__main__":
    _ensure_dirs()
    # Render injects PORT; local defaults to 8787
    port = int(os.getenv("PORT") or os.getenv("CONSOLE_PORT") or "8787")
    # 0.0.0.0 required for Render / Docker; 127.0.0.1 only for local-only mode
    host = os.getenv("CONSOLE_HOST", "0.0.0.0")
    public = os.getenv("RENDER_EXTERNAL_URL") or f"http://127.0.0.1:{port}"
    threads = int(os.getenv("CONSOLE_THREADS") or "6")
    print("=" * 50)
    print("  NOTBOOK DEPLOY CONSOLE")
    print(f"  bind  {host}:{port}")
    print(f"  open  {public}")
    if os.getenv("CONSOLE_PASSWORD"):
        print("  auth  ENABLED (CONSOLE_PASSWORD)")
    else:
        print("  auth  OFF — set CONSOLE_PASSWORD if public!")
    print("=" * 50)
    if host in ("127.0.0.1", "localhost") and os.getenv("CONSOLE_NO_BROWSER") != "1":
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass

    if _use_waitress():
        try:
            from waitress import serve
        except ImportError:
            print("waitress missing — pip install waitress; falling back to Flask dev server")
            app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
        else:
            print(f"  server  Waitress (threads={threads})")
            # channel_timeout high: long-running status polls while embed holds GIL
            serve(
                app,
                host=host,
                port=port,
                threads=threads,
                channel_timeout=300,
                connection_limit=100,
                ident="notbook-console",
            )
    else:
        print("  server  Flask development (CONSOLE_USE_FLASK_DEV=1)")
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
