"""App settings, kept from one launch to the next.

Stored in a small JSON file in the user's config folder (not in the app
folder, so they survive an update).
"""
import json
import os
import sys
from pathlib import Path


def app_dir():
    """The app's own folder in the user's config folder (settings, downloaded tools)."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    return base / "StardewSaveManager"


def _file():
    return app_dir() / "settings.json"


def load():
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):  # missing or damaged: fall back to defaults
        return {}


def save(**values):
    data = load()
    data.update(values)
    path = _file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # failing to remember a setting must never break the app