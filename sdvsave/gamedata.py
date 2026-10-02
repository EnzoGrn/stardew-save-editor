"""Game data read from the game's own unpacked files.

StardewXnbHack turns the game's Content folder into "Content (unpacked)":
JSON for data, PNG for images. This module reads the item catalogue from it
and resolves display names in any language the game ships.

Nothing here is required: every caller must keep working when no game data
is available (GameData.load returns None).

In 1.6, most display names are tokens pointing into a strings file:
    [LocalizedText Strings\\Objects:Clay_Name]
which reads key "Clay_Name" from Strings/Objects.json, or from
Strings/Objects.fr-FR.json for French.
"""
import json
import re
from pathlib import Path

from .constants import XSI

UNPACKED_FOLDER = "Content (unpacked)"

# Catalogues, keyed by the game's qualified item type prefix.
# Data files with a JSON object per item.
_MODEL_FILES = {
    "O": "Objects",
    "BC": "BigCraftables",
    "T": "Tools",
    "W": "Weapons",
    "S": "Shirts",
    "P": "Pants",
    "TR": "Trinkets",
    "M": "Mannequins",
}
# Older data files where each item is a "/"-separated string:
# (file, index of the internal name, index of the display name)
_SLASH_FILES = {
    "H": ("hats", 0, 5),
    "B": ("Boots", 0, 6),
    "F": ("Furniture", 0, 7),
}

# Save item class (xsi:type) → catalogue prefix
_TOOL_TYPES = {"Axe", "Hoe", "Pickaxe", "WateringCan", "FishingRod", "Pan", "Shears",
               "MilkPail", "Wand", "GenericTool", "Lantern", "Raft"}
_FURNITURE_TYPES = {"Furniture", "BedFurniture", "StorageFurniture", "TV",
                    "FishTankFurniture", "RandomizedPlantFurniture"}

_TOKEN = re.compile(r"\[LocalizedText\s+([^\]\s:]+):([^\]\s]+)((?:\s+[^\]\s]+)*)\]")


def find_data_dir(folder):
    """The unpacked data folder for a game folder, or the folder itself if it is one."""
    if folder is None:
        return None
    folder = Path(folder)
    for candidate in (folder / UNPACKED_FOLDER, folder):
        if (candidate / "Data" / "Objects.json").is_file():
            return candidate
    return None


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


class GameData:
    """Item catalogue and translated names from one unpacked data folder."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.items = {}           # "O:330" → {"name": ..., "display": raw display name}
        self._strings = {}        # (asset, lang suffix) → dict, loaded on demand
        self._localized_data = {}  # (file, lang suffix) → dict, loaded on demand
        self.languages = self._find_languages()
        self._load_items()

    @classmethod
    def load(cls, folder):
        """GameData for a game or unpacked folder, or None when there is none."""
        data_dir = find_data_dir(folder)
        return cls(data_dir) if data_dir else None

    # ------------------------------------------------------------------ loading
    def _find_languages(self):
        """{"fr": "fr-FR", …}: language codes with translated strings, by language."""
        result = {}
        for path in (self.data_dir / "Strings").glob("Objects.*.json"):
            suffix = path.name[len("Objects."):-len(".json")]
            result.setdefault(suffix.split("-")[0].lower(), suffix)
        return result

    def _load_items(self):
        for prefix, file in _MODEL_FILES.items():
            for item_id, data in (_read_json(self.data_dir / "Data" / f"{file}.json") or {}).items():
                if isinstance(data, dict):
                    self.items[f"{prefix}:{item_id}"] = {
                        "name": data.get("Name") or item_id,
                        "display": data.get("DisplayName"),
                    }
        for prefix, (file, name_at, display_at) in _SLASH_FILES.items():
            for item_id, raw in (_read_json(self.data_dir / "Data" / f"{file}.json") or {}).items():
                if isinstance(raw, str):
                    fields = raw.split("/")
                    self.items[f"{prefix}:{item_id}"] = {
                        "name": fields[name_at] if len(fields) > name_at else item_id,
                        "display": fields[display_at] if len(fields) > display_at else None,
                        "slash": (file, display_at),
                    }

    def _suffix(self, lang):
        """Strings file suffix for a UI language: "fr" → "fr-FR", English → ""."""
        return self.languages.get((lang or "").lower(), "")

    def _strings_file(self, asset, suffix):
        key = (asset, suffix)
        if key not in self._strings:
            path = self.data_dir.joinpath(*asset.split("\\"))
            name = f"{path.name}.{suffix}.json" if suffix else f"{path.name}.json"
            self._strings[key] = _read_json(path.with_name(name)) or {}
        return self._strings[key]

    def _localized_slash(self, file, suffix):
        key = (file, suffix)
        if key not in self._localized_data:
            self._localized_data[key] = (
                _read_json(self.data_dir / "Data" / f"{file}.{suffix}.json") or {} if suffix else {})
        return self._localized_data[key]

    # ------------------------------------------------------------------ names
    def text(self, value, lang):
        """Resolves every LocalizedText token in a string; None if one can't be found."""
        if not value:
            return None
        suffix = self._suffix(lang)
        missing = False

        def replace(match):
            nonlocal missing
            asset, key, args = match.group(1), match.group(2), match.group(3).split()
            found = (self._strings_file(asset, suffix).get(key)
                     or self._strings_file(asset, "").get(key))
            if found is None:
                missing = True
                return match.group(0)
            for i, arg in enumerate(args):
                found = found.replace("{%d}" % i, arg)
            return found

        result = _TOKEN.sub(replace, value)
        return None if missing else result

    def _flavored_key(self, display):
        """The "…_Flavored_Name" token next to a "…_Name" token, if the game has one."""
        match = _TOKEN.fullmatch(display or "")
        if not match or not match.group(2).endswith("_Name"):
            return None
        return f"[LocalizedText {match.group(1)}:{match.group(2)[:-5]}_Flavored_Name]"

    def display_name(self, qualified_id, lang, preserved_from=None):
        """Name of an item in a language, or None if the item is unknown.

        preserved_from: qualified id of the ingredient of a flavored item
        (Parsnip Wine, Blueberry Jelly…), used when the game has a format for it.
        """
        item = self.items.get(qualified_id)
        if item is None:
            return None
        if preserved_from:
            flavored = self._flavored_key(item["display"])
            parent = self.display_name(preserved_from, lang)
            text = self.text(flavored, lang) if flavored and parent else None
            if text and "{0}" in text:
                return text.replace("{0}", parent)
            return None  # no known format: the caller keeps the save's own name
        if "slash" in item:
            file, display_at = item["slash"]
            localized = self._localized_slash(file, self._suffix(lang)).get(qualified_id.split(":", 1)[1])
            if isinstance(localized, str):
                fields = localized.split("/")
                if len(fields) > display_at and fields[display_at]:
                    return self.text(fields[display_at], lang) or fields[display_at]
        return self.text(item["display"], lang) or item["name"]

    # ------------------------------------------------------------------ save items
    def qualified_id(self, element):
        """Catalogue id of an item element from a save, or None."""
        item_id = element.findtext("itemId")
        if not item_id:
            return None
        kind = element.get(XSI + "type") or "Object"
        if kind in ("Object", "ColoredObject"):
            prefix = "BC" if element.findtext("bigCraftable") == "true" else "O"
        elif kind in ("Ring", "CombinedRing"):
            prefix = "O"
        elif kind in _TOOL_TYPES:
            prefix = "T"
        elif kind in ("MeleeWeapon", "Slingshot"):
            prefix = "W"
        elif kind in _FURNITURE_TYPES:
            prefix = "F"
        elif kind == "Clothing":
            prefix = "P" if element.findtext("clothesType") == "PANTS" else "S"
        else:
            prefix = {"Hat": "H", "Boots": "B", "Trinket": "TR", "Mannequin": "M"}.get(kind)
        if prefix and f"{prefix}:{item_id}" in self.items:
            return f"{prefix}:{item_id}"
        # Unknown class (or a mod's): look for the id in every catalogue
        for candidate in (f"{p}:{item_id}" for p in (*_MODEL_FILES, *_SLASH_FILES)):
            if candidate in self.items:
                return candidate
        return None

    def item_name(self, element, lang):
        """Translated name of a save item, or None to keep the save's own name."""
        qualified = self.qualified_id(element)
        if qualified is None:
            return None
        preserve = element.find("preserve")
        parent = element.findtext("preservedParentSheetIndex") or ""
        if preserve is not None and preserve.get(XSI + "nil") != "true" and parent not in ("", "-1", "0"):
            # Stored as "24" or, qualified, as "(O)24"
            match = re.fullmatch(r"\((\w+)\)(.+)", parent)
            parent = f"{match.group(1)}:{match.group(2)}" if match else f"O:{parent}"
            return self.display_name(qualified, lang, preserved_from=parent)
        return self.display_name(qualified, lang)