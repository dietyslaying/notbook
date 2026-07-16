#!/usr/bin/env python3
"""Launch the Notbook Deploy Console (retro management UI)."""

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

    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask>=3.0.0", "pyyaml>=6.0"])

from app import app, _ensure_dirs  # noqa: E402

if __name__ == "__main__":
    _ensure_dirs()
    port = int(os.getenv("CONSOLE_PORT", "8787"))
    url = f"http://127.0.0.1:{port}"
    print("=" * 50)
    print("  NOTBOOK DEPLOY CONSOLE")
    print(f"  {url}")
    print("=" * 50)
    if os.getenv("CONSOLE_NO_BROWSER") != "1":
        try:
            webbrowser.open(url)
        except Exception:
            pass
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
