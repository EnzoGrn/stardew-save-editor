"""Finding the game's install folder, and the state of its unpacked data."""
import os
import re
import sys
from pathlib import Path

from .gamedata import UNPACKED_FOLDER, find_data_dir

GAME_DLL = "Stardew Valley.dll"

# States of the game data, used by the UI
NO_GAME = "no_game"      # no game folder known
MISSING = "missing"      # game found, data never unpacked
READY = "ready"
OUTDATED = "outdated"    # the game was updated after the data was unpacked


def content_dir(game_dir):
    """The game's packed Content folder (one level up on macOS), or None."""
    game_dir = Path(game_dir)
    for candidate in (game_dir / "Content", game_dir.parent / "Resources" / "Content"):
        if candidate.is_dir():
            return candidate
    return None


def is_game_dir(path):
    return path is not None and (Path(path) / GAME_DLL).is_file() and content_dir(path) is not None


def resolve_game_dir(chosen):
    """The game folder for a folder the user picked, or None.

    Accepts the game folder itself and the folders people usually pick by
    mistake: Content, "Content (unpacked)", a macOS app bundle, the Game Pass
    install folder.
    """
    path = Path(chosen)
    candidates = [
        path,
        path / "Contents" / "MacOS",                       # macOS app bundle or Steam folder
        path / "Stardew Valley.app" / "Contents" / "MacOS",
        path / "Content",                                  # Game Pass: <install>/Content
        path.parent,                                       # Content or Content (unpacked)
    ]
    return next((c for c in candidates if is_game_dir(c)), None)


def _steam_roots():
    home = Path.home()
    if sys.platform.startswith("win"):
        roots = []
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
        roots.append(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam")
        return roots
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "Steam"]
    return [home / ".local" / "share" / "Steam", home / ".steam" / "steam",
            home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam"]


def _steam_libraries():
    """Every Steam library folder, read from libraryfolders.vdf."""
    for root in _steam_roots():
        yield root
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            yield Path(match.group(1).replace("\\\\", "\\"))


def _gog_paths():
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\WOW6432Node\GOG.com\Games\1453375253") as key:
                yield Path(winreg.QueryValueEx(key, "path")[0])
        except OSError:
            pass
        yield Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "GOG Galaxy" / "Games" / "Stardew Valley"
    elif sys.platform == "darwin":
        yield Path("/Applications/Stardew Valley.app/Contents/MacOS")
    else:
        yield Path.home() / "GOG Games" / "Stardew Valley" / "game"


def candidate_game_dirs():
    for library in _steam_libraries():
        game = library / "steamapps" / "common" / "Stardew Valley"
        yield game / "Contents" / "MacOS" if sys.platform == "darwin" else game
    yield from _gog_paths()
    if sys.platform.startswith("win"):
        yield Path(r"C:\XboxGames\Stardew Valley\Content")  # Game Pass


def detect_game_dir():
    """The first game install found in the usual places, or None."""
    seen = set()
    for candidate in candidate_game_dirs():
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            if is_game_dir(candidate):
                return candidate
    return None


def unpacked_dir(game_dir):
    return Path(game_dir) / UNPACKED_FOLDER


def data_status(game_dir):
    """NO_GAME, MISSING, READY or OUTDATED for a game folder (which may be None)."""
    if not is_game_dir(game_dir):
        return NO_GAME
    data_dir = find_data_dir(game_dir)
    if data_dir is None:
        return MISSING
    # A game update always replaces the game DLL; data files only when they change
    unpacked_at = (data_dir / "Data" / "Objects.json").stat().st_mtime
    game_files = [Path(game_dir) / GAME_DLL, content_dir(game_dir) / "Data" / "Objects.xnb"]
    updated_at = max((f.stat().st_mtime for f in game_files if f.is_file()), default=0)
    return OUTDATED if updated_at > unpacked_at + 60 else READY