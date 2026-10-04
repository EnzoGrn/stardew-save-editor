"""Where saves live on each operating system."""
import os
import sys
from pathlib import Path

from . import xmlio
from .constants import SEASONS


def default_saves_dir():
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:  # macOS and Linux
        base = Path.home() / ".config"
    return base / "StardewValley" / "Saves"


def backups_root(saves_dir):
    """Backups go next to the Saves folder (not inside it, so the game isn't confused).

    The folder keeps the project's former name, so existing backups stay listed.
    """
    return Path(saves_dir).parent / "SaveManagerBackups"


def is_save_folder(folder):
    folder = Path(folder)
    return folder.is_dir() and (folder / folder.name).is_file() and (folder / "SaveGameInfo").is_file()


def list_saves(saves_dir):
    """Summary of each save, read from the small SaveGameInfo file."""
    saves_dir = Path(saves_dir)
    if not saves_dir.is_dir():
        return []
    result = []
    for folder in sorted(saves_dir.iterdir()):
        if not is_save_folder(folder):
            continue
        try:
            info = xmlio.load(folder / "SaveGameInfo").getroot()
            result.append({
                "id": folder.name,
                "farmer": info.findtext("name") or "?",
                "farm": info.findtext("farmName") or "?",
                "money": int(info.findtext("money") or 0),
                "day": info.findtext("dayOfMonthForSaveGame") or "?",
                "season": SEASONS[int(info.findtext("seasonForSaveGame") or 0) % 4],
                "year": info.findtext("yearForSaveGame") or "?",
                "version": info.findtext("gameVersion") or "?",
                "error": None,
            })
        except Exception as exc:  # one corrupt save must not break the whole list
            result.append({"id": folder.name, "error": str(exc)})
    return result