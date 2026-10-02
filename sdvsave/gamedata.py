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
import struct
import unicodedata
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

# Save item class (xsi:type) > catalogue prefix
_TOOL_TYPES = {"Axe", "Hoe", "Pickaxe", "WateringCan", "FishingRod", "Pan", "Shears",
               "MilkPail", "Wand", "GenericTool", "Lantern", "Raft"}
_FURNITURE_TYPES = {"Furniture", "BedFurniture", "StorageFurniture", "TV",
                    "FishTankFurniture", "RandomizedPlantFurniture"}

# Icons: default sprite sheet per catalogue and where an icon is on it:
# (sheet, icon width, icon height, step between icons across, step down,
#  width of the sheet part holding icons (None: all of it), icon offset x, y).
# Hats have one sprite per facing direction, stacked: the step down is 4 sprites.
# Shirts: the left half holds the shirts (8x8 icon over 8x32), the right half
# the parts that take the dye color. Pants: one 192x688 block per pair, with the
# 16x16 icon at its bottom left.
_SHEETS = {
    "O": ("Maps/springobjects", 16, 16, 16, 16, None, 0, 0),
    "BC": ("TileSheets/Craftables", 16, 32, 16, 32, None, 0, 0),
    "T": ("TileSheets/tools", 16, 16, 16, 16, None, 0, 0),
    "W": ("TileSheets/weapons", 16, 16, 16, 16, None, 0, 0),
    "H": ("Characters/Farmer/hats", 20, 20, 20, 80, None, 0, 0),
    "B": ("Maps/springobjects", 16, 16, 16, 16, None, 0, 0),
    "S": ("Characters/Farmer/shirts", 8, 8, 8, 32, 128, 0, 0),
    "P": ("Characters/Farmer/pants", 16, 16, 192, 688, None, 0, 672),
}
_SHIRT_DYE_OFFSET = 128  # dye layer of a shirt: same place, in the right half of the sheet
# Slash data fields giving a custom sprite index and texture: (index field, texture field)
_SLASH_SPRITE_FIELDS = {"H": (6, 7), "B": (8, 9)}

# Farmer sheets for the look: hairstyles (16x32 front sprite, 96 px per style
# for the three facings), accessories (16x16, 32 px per row) and skin colors
# (3 shades per skin, read pixel by pixel)
HAIR_SHEET = "Characters/Farmer/hairstyles"
ACCESSORY_SHEET = "Characters/Farmer/accessories"
SKIN_SHEET = "Characters/Farmer/skinColors"

# Items the app can create from scratch: plain objects and big craftables.
# Some ids are their own class in the game (with extra fields a plain object
# doesn't have), so creating them as plain objects could break a save.
ADDABLE_PREFIXES = ("O", "BC")
SPECIAL_CLASS_IDS = {
    "O:93",      # Torch
    "O:710",     # Crab Pot
    "BC:62",     # Garden Pot
    "BC:130", "BC:232", "BC:BigChest", "BC:BigStoneChest",  # chests
    "BC:163",    # Cask
    "BC:208",    # Workbench
    "BC:211",    # Wood Chipper
    "BC:214",    # Phonograph
    "BC:216",    # Mini-Fridge
    "BC:248",    # Mini-Shipping Bin
    "BC:256",    # Junimo Chest
    "BC:275",    # Hopper
}

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
        self.items = {}           # "O:330" > {"name", "display" (raw display name), "data"}
        self._strings = {}        # (asset, lang suffix) > dict, loaded on demand
        self._localized_data = {}  # (file, lang suffix) > dict, loaded on demand
        self._sheet_sizes = {}    # sprite sheet > (width, height), read on demand
        self._search_index = {}   # lang > [(folded text, qualified id)], built on demand
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
                        "data": data,
                    }
        for prefix, (file, name_at, display_at) in _SLASH_FILES.items():
            for item_id, raw in (_read_json(self.data_dir / "Data" / f"{file}.json") or {}).items():
                if isinstance(raw, str):
                    fields = raw.split("/")
                    self.items[f"{prefix}:{item_id}"] = {
                        "name": fields[name_at] if len(fields) > name_at else item_id,
                        "display": fields[display_at] if len(fields) > display_at else None,
                        "slash": (file, display_at),
                        "fields": fields,
                        "data": {},
                    }

    def _suffix(self, lang):
        """Strings file suffix for a UI language: "fr" > "fr-FR", English > ""."""
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

    # ------------------------------------------------------------------ icons
    def _sheet_size(self, sheet):
        """(width, height) of a sprite sheet PNG, read from its header; None if missing."""
        if sheet not in self._sheet_sizes:
            size = None
            try:
                with open(self.data_dir.joinpath(*sheet.split("/")).with_suffix(".png"), "rb") as f:
                    header = f.read(24)
                if header[:8] == b"\x89PNG\r\n\x1a\n":
                    size = struct.unpack(">II", header[16:24])
            except OSError:
                pass
            self._sheet_sizes[sheet] = size
        return self._sheet_sizes[sheet]

    def _icon_at(self, sheet, index, w, h, step_x=None, step_y=None, area_w=None, dx=0, dy=0):
        """Icon dict for sprite number `index` on a sheet laid out in a grid, or None."""
        size = self._sheet_size(sheet)
        if size is None or index < 0:
            return None
        step_x, step_y = step_x or w, step_y or h
        columns = max(1, (area_w or size[0]) // step_x)
        return {"sheet": sheet, "x": index % columns * step_x + dx, "y": index // columns * step_y + dy,
                "w": w, "h": h, "sheet_w": size[0], "sheet_h": size[1]}

    def sprite(self, qualified_id):
        """(sheet, sprite index) of an item, or None: where the game draws it from."""
        item = self.items.get(qualified_id)
        prefix = qualified_id.split(":", 1)[0]
        if item is None or prefix not in _SHEETS:
            return None
        sheet = _SHEETS[prefix][0]
        data = item["data"]
        if data.get("Texture"):
            sheet = data["Texture"].replace("\\", "/")
        fields = item.get("fields", [])
        sprite_at, texture_at = _SLASH_SPRITE_FIELDS.get(prefix, (None, None))
        if prefix == "T" and data.get("MenuSpriteIndex", -1) >= 0:
            return sheet, data["MenuSpriteIndex"]
        if "SpriteIndex" in data:
            return sheet, data["SpriteIndex"]
        if sprite_at is not None and len(fields) > sprite_at and fields[sprite_at].strip().lstrip("-").isdigit():
            # 1.6 hats and boots with their own sprite
            if len(fields) > texture_at and fields[texture_at].strip():
                sheet = fields[texture_at].strip().replace("\\", "/")
            return sheet, int(fields[sprite_at])
        item_id = qualified_id.split(":", 1)[1]
        return (sheet, int(item_id)) if item_id.isdigit() else None  # hats and boots: the id

    def icon(self, qualified_id, dye_layer=False):
        """Where an item's sprite is: {"sheet", "x", "y", "w", "h", "sheet_w", "sheet_h"}, or None.

        dye_layer: for a dyeable shirt, the part of the icon that takes the dye color.
        """
        found = self.sprite(qualified_id)
        if found is None:
            return None
        sheet, index = found
        prefix = qualified_id.split(":", 1)[0]
        _, w, h, step_x, step_y, area_w, dx, dy = _SHEETS[prefix]
        if dye_layer:
            if prefix != "S" or not self.items[qualified_id]["data"].get("CanBeDyed"):
                return None
            dx += _SHIRT_DYE_OFFSET
        return self._icon_at(sheet, index, w, h, step_x, step_y, area_w, dx, dy)

    def sheet_exists(self, sheet):
        return self._sheet_size(sheet) is not None

    # ------------------------------------------------------------------ farmer look
    def hairstyles(self, covered=False):
        """{hair index: icon or None} for every hairstyle a farmer can pick.

        0-55 are on hairstyles.png (8 per row, 96 px per row of styles). Data/HairData.json
        adds the others: "texture/tile x/tile y/unique left sprite/covered index/bald", tiles
        being 16 px. Negative ids there are "covered" versions, drawn under some hats
        instead of the style that names them: listed only with covered=True.
        Icons also say whether the style uses the bald body ("bald") and its covered
        version ("covered", -1 for none).
        """
        result = {}
        for i in range(56):
            icon = self._icon_at(HAIR_SHEET, i, 16, 32, 16, 96)
            result[i] = icon and {**icon, "bald": False, "covered": -1}
        for key, raw in (_read_json(self.data_dir / "Data" / "HairData.json") or {}).items():
            fields = raw.split("/") if isinstance(raw, str) else []
            if not str(key).lstrip("-").isdigit() or len(fields) < 3 or (int(key) < 0 and not covered):
                continue
            sheet = "Characters/Farmer/" + fields[0].replace("\\", "/").split("/")[-1]
            size = self._sheet_size(sheet)
            try:
                tile_x, tile_y = int(fields[1]), int(fields[2])
                covered_index = int(fields[4]) if len(fields) > 4 else -1
            except ValueError:
                continue
            result[int(key)] = None if size is None else {
                "sheet": sheet, "x": tile_x * 16, "y": tile_y * 16, "w": 16, "h": 32,
                "sheet_w": size[0], "sheet_h": size[1],
                "bald": len(fields) > 5 and fields[5].strip().lower() == "true",
                "covered": covered_index}
        return dict(sorted(result.items()))

    def accessory_icon(self, index):
        return self._icon_at(ACCESSORY_SHEET, index, 16, 16, 16, 32)

    def skin_icon(self, index):
        """One pixel of the skin color sheet: the middle shade of that skin."""
        return self._icon_at(SKIN_SHEET, index * 3 + 1, 1, 1)

    def clothing(self, prefix, lang):
        """[(qualified id, display name)] of every shirt (S), pants (P), hat (H) or boots (B)."""
        names = {q: self.display_name(q, lang) for q in self.items if q.startswith(prefix + ":")}
        counts = {}
        for name in names.values():
            counts[name] = counts.get(name, 0) + 1
        # Different items can share a name (several plain "Shirt"s): the id tells them apart
        result = [(q, f"{name} ({q.split(':', 1)[1]})" if counts[name] > 1 else name) for q, name in names.items()]
        result.sort(key=lambda pair: (self._fold(pair[1]), pair[0]))
        return result

    def sheet_path(self, sheet):
        """File of a sprite sheet named by icon(), or None if it isn't a sheet of this data."""
        path = self.data_dir.joinpath(*sheet.split("/")).with_suffix(".png").resolve()
        root = self.data_dir.resolve()
        return path if root in path.parents and path.is_file() else None

    # ------------------------------------------------------------------ tools
    # Tools upgraded at the blacksmith, level by level (copper, steel, gold, iridium).
    # Fishing rods also have levels, but each is a different rod with its own
    # attachments, so they aren't changed this way.
    UPGRADABLE_TOOLS = ("Axe", "Hoe", "Pickaxe", "WateringCan", "Pan")

    def tool_levels(self, class_name):
        """{upgrade level: tool id} for an upgradable tool class; empty for others."""
        if class_name not in self.UPGRADABLE_TOOLS:
            return {}
        levels = {}
        for qualified, item in self.items.items():
            data = item["data"]
            if qualified.startswith("T:") and data.get("ClassName") == class_name \
                    and data.get("UpgradeLevel", -1) >= 0:
                levels.setdefault(data["UpgradeLevel"], qualified[2:])
        return dict(sorted(levels.items())) if len(levels) > 1 else {}

    # ------------------------------------------------------------------ adding items
    def addable(self, qualified_id):
        return (qualified_id.split(":", 1)[0] in ADDABLE_PREFIXES
                and qualified_id in self.items and qualified_id not in SPECIAL_CLASS_IDS
                and self.items[qualified_id]["data"].get("Type") != "Ring")

    @staticmethod
    def _fold(text):
        """Lowercase, without accents: "Été" and "ete" match."""
        decomposed = unicodedata.normalize("NFKD", text or "")
        return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()

    def search(self, query, lang, limit=40):
        """Items that can be added, matching a query in the UI language or in English.

        Returns [(qualified id, display name)], names starting with the query first.
        """
        query = self._fold(query.strip())
        if not query:
            return []
        if lang not in self._search_index:
            index = []
            for qualified in self.items:
                if self.addable(qualified):
                    name = self.display_name(qualified, lang)
                    index.append((self._fold(name), self._fold(self.items[qualified]["name"]), name, qualified))
            self._search_index[lang] = sorted(index)
        found = [(not (shown.startswith(query) or english.startswith(query)), shown, qualified, name)
                 for shown, english, name, qualified in self._search_index[lang]
                 if query in shown or query in english]
        found.sort()
        seen, result = set(), []
        for _, _, qualified, name in found:
            if name not in seen:  # the game has a few duplicates (unused copies)
                seen.add(name)
                result.append((qualified, name))
        return result[:limit]

    # ------------------------------------------------------------------ recipes
    # Data/CookingRecipes.json and Data/CraftingRecipes.json: recipe name > "/"-separated
    # fields. The output item is field 2 ("id" or "id count", sometimes qualified like
    # "(BC)238"); crafting recipes say in field 3 whether it's a big craftable. An
    # optional display name comes last (field 4 for cooking, 5 for crafting);
    # otherwise the game shows the output item's name.
    _RECIPE_FILES = {"cooking": ("CookingRecipes", None, 4), "crafting": ("CraftingRecipes", 3, 5)}

    def recipes(self, kind, lang):
        """Every recipe of a kind ("cooking" or "crafting"), sorted by display name.

        Returns [{"name": key used in saves, "display": name in the language,
                  "output": qualified id of the item it makes, or None}].
        """
        file, big_at, display_at = self._RECIPE_FILES[kind]
        result = []
        for name, raw in (_read_json(self.data_dir / "Data" / f"{file}.json") or {}).items():
            fields = raw.split("/") if isinstance(raw, str) else []
            output = None
            if len(fields) > 2 and fields[2].split():
                item_id = fields[2].split()[0]
                match = re.fullmatch(r"\((\w+)\)(.+)", item_id)
                if match:
                    output = f"{match.group(1)}:{match.group(2)}"
                else:
                    big = big_at is not None and len(fields) > big_at and fields[big_at] == "true"
                    output = f"{'BC' if big else 'O'}:{item_id}"
                if output not in self.items:
                    output = None
            explicit = fields[display_at] if len(fields) > display_at else ""
            display = (self.text(explicit, lang) if explicit else None) \
                or (self.display_name(output, lang) if output else None) or name
            result.append({"name": name, "display": display, "output": output})
        return sorted(result, key=lambda r: self._fold(r["display"]))