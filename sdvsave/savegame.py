"""A save: reading and editing its data.

A save is made of two files that must stay consistent:
  - <Folder>/<Folder>      : all the data (SaveGame)
  - <Folder>/SaveGameInfo  : a copy of the host farmer, read by the load screen
Every change to the host is therefore applied to both.
"""
import os
from pathlib import Path

from lxml import etree

from . import appearance as look, items, xmlio
from .constants import (
    SKILLS, XP_FOR_LEVEL, QUALITIES, POINTS_PER_HEART, MAX_FRIENDSHIP_POINTS,
    BACKPACK_SIZES, SEASONS, XSI,
)
from .errors import NotFound, SaveChangedError, SaveError, T

#: Item classes with a quantity and a quality: plain objects, and colored ones (flowers…)
STACKABLE_TYPES = ("Object", "ColoredObject")


def _int(el, tag, default=0):
    try:
        return int(el.findtext(tag))
    except (TypeError, ValueError):
        return default


def _set(el, tag, value):
    """Replaces the text of an existing tag (None = empty tag)."""
    node = el.find(tag)
    if node is None:
        raise NotFound("error.missing_tag", tag=tag, parent=el.tag)
    node.text = None if value is None else str(value)


#: Characters the game uses as markup in dialogue: a name containing them
#: displays wrongly in villagers' conversations.
FORBIDDEN_IN_NAMES = "%[]^<>"
MAX_NAME_LENGTH = 32


def _name(value, field):
    """field: key of the field name, for the error message."""
    value = (value or "").strip()
    if not value:
        raise SaveError("error.name_empty", field=T(field))
    if len(value) > MAX_NAME_LENGTH:
        raise SaveError("error.name_too_long", field=T(field), max=MAX_NAME_LENGTH)
    bad = sorted({c for c in value if c in FORBIDDEN_IN_NAMES or ord(c) < 32})
    if bad:
        raise SaveError("error.name_forbidden", field=T(field), chars=" ".join(bad))
    return value


def bounded(value, low, high, field, **extra):
    """field: key of the field name; extra: parameters of that name (e.g. the villager)."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise SaveError("error.not_integer", field=T(field), value=value, **extra)
    if not low <= value <= high:
        raise SaveError("error.out_of_range", field=T(field), low=low, high=high,
                        value=value, **extra)
    return value


class SaveGame:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.id = self.folder.name
        self.main_path = self.folder / self.id
        self.info_path = self.folder / "SaveGameInfo"
        self.main = xmlio.load(self.main_path)
        self.info = xmlio.load(self.info_path)
        self._mtimes = self._current_mtimes()

    # ------------------------------------------------------------------ files
    def _current_mtimes(self):
        return (os.path.getmtime(self.main_path), os.path.getmtime(self.info_path))

    def write(self):
        if self._current_mtimes() != self._mtimes:
            raise SaveChangedError()
        xmlio.save(self.main, self.main_path)
        xmlio.save(self.info, self.info_path)
        self._mtimes = self._current_mtimes()

    # ------------------------------------------------------------------ players
    @property
    def root(self):
        return self.main.getroot()

    def _farmers(self):
        """(element, is_host) for the host, then each farmhand."""
        yield self.root.find("player"), True
        for fh in self.root.findall("farmhands/Farmer"):
            yield fh, False

    def _copies(self, uid):
        """Every XML element that represents this player (2 for the host)."""
        for el, is_host in self._farmers():
            if el.findtext("UniqueMultiplayerID") == str(uid):
                return [el, self.info.getroot()] if is_host else [el]
        raise NotFound("error.no_player", uid=uid)

    def _player(self, uid):
        return self._copies(uid)[0]

    def _describe(self, el, is_host):
        xp = [int(x.text) for x in el.find("experiencePoints")]
        skills = []
        for idx, tag, skill_id in SKILLS:
            level = _int(el, tag)
            skills.append({"index": idx, "tag": tag, "id": skill_id, "level": level,
                           "xp": xp[idx] if idx < len(xp) else 0})
        name = el.findtext("name") or ""
        return {
            "uid": el.findtext("UniqueMultiplayerID"),
            "name": name,
            "is_host": is_host,
            "customized": el.findtext("isCustomized") == "true",
            "user_id": el.findtext("userID") or "",
            "home": el.findtext("homeLocation") or "",
            "money": _int(el, "money"),
            "total_earned": _int(el, "totalMoneyEarned"),
            "qi_gems": _int(el, "qiGems"),
            "club_coins": _int(el, "clubCoins"),
            "max_stamina": _int(el, "maxStamina"),
            "max_health": _int(el, "maxHealth"),
            "max_items": _int(el, "maxItems"),
            "deepest_mine": _int(el, "deepestMineLevel"),
            "played_ms": _int(el, "millisecondsPlayed"),
            "skills": skills,
        }

    def players(self):
        return [self._describe(el, host) for el, host in self._farmers()]

    def player(self, uid):
        for p in self.players():
            if p["uid"] == str(uid):
                return p
        raise NotFound("error.no_player", uid=uid)

    # ------------------------------------------------------------------ farm
    def farm(self):
        r = self.root
        host = r.find("player")
        return {
            "id": self.id,
            "farm_name": host.findtext("farmName"),
            "farm_type": r.findtext("whichFarm"),
            "season": r.findtext("currentSeason"),
            "day": r.findtext("dayOfMonth"),
            "year": r.findtext("year"),
            "golden_walnuts": _int(r, "goldenWalnuts"),
            "version": r.findtext("gameVersion"),
            "unique_id": r.findtext("uniqueIDForThisGame"),
            "shared_wallet": host.findtext("useSeparateWallets") != "true",
            "played_ms": _int(host, "millisecondsPlayed"),
        }

    def set_golden_walnuts(self, value):
        _set(self.root, "goldenWalnuts", bounded(value, 0, 130, "field.golden_walnuts"))

    # ------------------------------------------------------------------ names
    def rename_farm(self, new_name):
        """The farm name is copied into every farmer: they must all be updated."""
        new_name = _name(new_name, "field.farm_name")
        for el, _ in self._farmers():
            _set(el, "farmName", new_name)
        _set(self.info.getroot(), "farmName", new_name)
        return new_name

    def rename_player(self, uid, new_name):
        """The game shows this name everywhere it's needed: nothing else to change."""
        new_name = _name(new_name, "field.player_name")
        for el in self._copies(uid):
            _set(el, "name", new_name)
        return new_name

    # ------------------------------------------------------------------ identifiers
    def clear_user_id(self, uid):
        """Clears the userID (the Steam / Xbox / GOG account linked to this farmer).

        Needed for example when a save moves from Game Pass to Steam: the Xbox
        ID left in the save prevents taking the farmer back. The farmer is kept;
        its slot simply becomes free again.
        """
        for el in self._copies(uid):
            _set(el, "userID", None)

    def clear_all_user_ids(self):
        count = 0
        for el, _ in self._farmers():
            if el.findtext("userID"):
                self.clear_user_id(el.findtext("UniqueMultiplayerID"))
                count += 1
        return count

    # ------------------------------------------------------------------ stats
    def update_stats(self, uid, form):
        """form: dictionary of the fields sent by the UI."""
        money = bounded(form["money"], 0, 99_999_999, "field.money")
        values = {
            "qiGems": bounded(form["qi_gems"], 0, 99_999, "field.qi_gems"),
            "clubCoins": bounded(form["club_coins"], 0, 99_999_999, "field.club_coins"),
            "maxStamina": bounded(form["max_stamina"], 270, 508, "field.max_stamina"),
            "maxHealth": bounded(form["max_health"], 100, 300, "field.max_health"),
        }
        max_items = bounded(form["max_items"], 12, 36, "field.max_items")
        if max_items not in BACKPACK_SIZES:
            raise SaveError("error.backpack_size")
        values["maxItems"] = max_items

        for el in self._copies(uid):
            for tag, v in values.items():
                _set(el, tag, v)
        self._resize_backpack(uid, max_items)
        self.set_money(uid, money)

    def set_money(self, uid, money):
        """With a shared wallet, every farmer has the same amount."""
        if self.farm()["shared_wallet"]:
            targets = [el for el, _ in self._farmers()] + [self.info.getroot()]
        else:
            targets = self._copies(uid)
        for el in targets:
            _set(el, "money", money)

    def _resize_backpack(self, uid, size):
        """Adds the missing empty slots when the backpack gets bigger."""
        for el in self._copies(uid):
            items = el.find("items")
            while len(items) < size:
                empty = etree.SubElement(items, "Item")
                empty.set(XSI + "nil", "true")

    # ------------------------------------------------------------------ skills
    def set_skills(self, uid, levels, show_levelup=True):
        """levels: {skill_index: level}.

        If show_levelup is true, the gained levels are added to <newLevels>: the
        game will show the level-up screen the next time the farmer sleeps, which
        grants the recipes and lets you pick professions at levels 5 and 10.
        """
        for el in self._copies(uid):
            xp_nodes = list(el.find("experiencePoints"))
            new_levels = el.find("newLevels")
            pending = {(p.findtext("X"), p.findtext("Y")) for p in new_levels}
            for idx, tag, skill_id in SKILLS:
                if idx not in levels:
                    continue
                level = bounded(levels[idx], 0, 10, f"skill.{skill_id}")
                old = _int(el, tag)
                if level == old:
                    continue
                _set(el, tag, level)
                xp = int(xp_nodes[idx].text)
                high = XP_FOR_LEVEL[level + 1] if level < 10 else float("inf")
                if not XP_FOR_LEVEL[level] <= xp < high:
                    xp_nodes[idx].text = str(XP_FOR_LEVEL[level])
                if show_levelup and level > old and idx != 5:  # no level-up screen for luck
                    for lvl in range(old + 1, level + 1):
                        if (str(idx), str(lvl)) not in pending:
                            point = etree.SubElement(new_levels, "Point")
                            etree.SubElement(point, "X").text = str(idx)
                            etree.SubElement(point, "Y").text = str(lvl)

    # ------------------------------------------------------------------ friendships
    def friendships(self, uid):
        result = []
        for item in self._player(uid).find("friendshipData"):
            npc = item.findtext("key/string")
            fr = item.find("value/Friendship")
            points = _int(fr, "Points")
            status = fr.findtext("Status")
            result.append({
                "npc": npc, "points": points,
                "hearts": points // POINTS_PER_HEART,
                "status": status,  # game identifier: Friendly, Dating, Married…
            })
        return sorted(result, key=lambda f: f["npc"])

    def set_friendships(self, uid, points_by_npc):
        for el in self._copies(uid):
            for item in el.find("friendshipData"):
                npc = item.findtext("key/string")
                if npc in points_by_npc:
                    value = bounded(points_by_npc[npc], 0, MAX_FRIENDSHIP_POINTS,
                                     "field.friendship", npc=npc)
                    _set(item.find("value/Friendship"), "Points", value)

    # ------------------------------------------------------------------ recipes
    # <cookingRecipes> and <craftingRecipes>: recipe name → times made. Cooking keeps
    # 0 there (dishes cooked are counted in <recipesCooked>, by item, left untouched);
    # crafting counts how many times the recipe was crafted.
    _RECIPE_TAGS = {"cooking": "cookingRecipes", "crafting": "craftingRecipes"}

    def recipes(self, uid):
        """{"cooking": {name: times made}, "crafting": {…}} for a player."""
        player = self._player(uid)
        return {kind: {item.findtext("key/string"): _int(item, "value/int")
                       for item in player.find(tag)}
                for kind, tag in self._RECIPE_TAGS.items()}

    def set_recipes(self, uid, kind, names):
        """Makes the player know exactly these recipes of a kind.

        Recipes kept keep their count; new ones start at 0; removed ones lose it.
        Returns (added, removed) counts.
        """
        names = set(names)
        tag = self._RECIPE_TAGS[kind]
        added = removed = 0
        for i, farmer in enumerate(self._copies(uid)):
            known = farmer.find(tag)
            present = set()
            for item in list(known):
                name = item.findtext("key/string")
                if name in names:
                    present.add(name)
                else:
                    known.remove(item)
                    removed += i == 0
            for name in sorted(names - present):
                item = etree.SubElement(known, "item")
                etree.SubElement(etree.SubElement(item, "key"), "string").text = name
                etree.SubElement(etree.SubElement(item, "value"), "int").text = "0"
                added += i == 0
        return added, removed

    # ------------------------------------------------------------------ inventory
    def inventory(self, uid, describe=None):
        """Inventory slots of a player.

        describe: optional function giving extra fields for an item element
        (translated "name", "icon", "tool_levels"… from the game data).
        """
        slots = []
        for i, it in enumerate(self._player(uid).find("items")):
            if items.is_empty(it):
                slots.append({"slot": i, "empty": True})
                continue
            kind = it.get(XSI + "type") or "Item"
            slot = {
                "slot": i, "empty": False, "type": kind,
                "name": it.findtext("name") or "?",
                "item_id": it.findtext("itemId") or "",
                "stack": _int(it, "stack", 1),
                "quality": _int(it, "quality"),
                "upgrade_level": _int(it, "upgradeLevel", -1),
                # Tools and weapons have no quantity or quality
                "editable": kind in STACKABLE_TYPES,
                "has_quality": kind in STACKABLE_TYPES and it.findtext("bigCraftable") != "true",
            }
            extra = describe(it) if describe else {}
            slot.update({k: v for k, v in extra.items() if v is not None})
            slots.append(slot)
        return slots

    def _slots(self, uid, slot):
        """The item lists of every copy of the player, after checking the slot exists."""
        lists = [el.find("items") for el in self._copies(uid)]
        if not 0 <= slot < len(lists[0]):
            raise SaveError("error.no_slot", slot=slot + 1)
        return lists

    def set_inventory(self, uid, changes, tool_levels=None, gamedata=None):
        """changes: {slot: {"stack": n, "quality": q}} for plain objects.
        tool_levels: {slot: level} for upgradable tools (needs gamedata).
        """
        for el in self._copies(uid):
            slots = list(el.find("items"))
            for slot, change in changes.items():
                it = slots[slot]
                if it.get(XSI + "type") not in STACKABLE_TYPES:
                    continue
                name = it.findtext("name")
                _set(it, "stack", bounded(change["stack"], 1, 999, "field.quantity", item=name))
                if it.findtext("bigCraftable") == "true":
                    continue  # machines have no quality
                quality = bounded(change["quality"], 0, 4, "field.quality", item=name)
                if quality not in QUALITIES:
                    raise SaveError("error.unknown_quality", item=name)
                _set(it, "quality", quality)
            for slot, level in (tool_levels or {}).items():
                it = slots[slot]
                level = bounded(level, 0, 4, "field.tool_level", item=it.findtext("name"))
                if _int(it, "upgradeLevel", -1) != level:
                    items.set_tool_level(it, gamedata, level)

    def add_item(self, uid, slot, element):
        """Puts a new item element in an empty slot."""
        lists = self._slots(uid, slot)
        if not items.is_empty(lists[0][slot]):
            raise SaveError("error.slot_taken", slot=slot + 1)
        for i, slots in enumerate(lists):
            slots.replace(slots[slot], element if i == 0 else items.copy_for(element))

    def remove_item(self, uid, slot):
        """Empties a slot; the item is gone."""
        for slots in self._slots(uid, slot):
            slots.replace(slots[slot], items.empty_slot())

    def move_item(self, uid, source, target):
        """Moves an item to another slot, swapping with what is there."""
        self._slots(uid, target)
        for slots in self._slots(uid, source):
            a, b = slots[source], slots[target]
            placeholder = items.empty_slot()
            slots.replace(a, placeholder)
            slots.replace(b, a)
            slots.replace(placeholder, b)

    # ------------------------------------------------------------------ appearance
    # Worn item tags → keys used by the UI
    _WORN = {"shirt": "shirtItem", "pants": "pantsItem", "hat": "hat", "boots": "boots"}

    def appearance(self, uid):
        """A player's look: body, colors and worn clothes (see appearance.py)."""
        farmer = self._player(uid)
        worn = {}
        for key, tag in self._WORN.items():
            element = farmer.find(tag)
            if element is None or items.is_empty(element):
                worn[key] = None
                continue
            worn[key] = {"item_id": element.findtext("itemId") or "",
                         "name": element.findtext("name") or "?"}
            if key in ("shirt", "pants"):
                worn[key].update(color=look.read_color(element.find("clothesColor")),
                                 dyeable=element.findtext("dyeable") == "true",
                                 sprite=_int(element, "indexInTileSheet"))
            elif key == "hat":
                worn[key].update(hair_draw=_int(element, "hairDrawType"),
                                 ignore_offset=element.findtext("ignoreHairstyleOffset") == "true")
            else:
                worn[key]["color_index"] = _int(element, "indexInColorSheet")
        return {
            "gender": farmer.findtext("Gender") or farmer.findtext("gender") or "Male",
            "skin": _int(farmer, "skin"),
            "hair": _int(farmer, "hair"),
            "accessory": _int(farmer, "accessory", -1),
            "hair_color": look.read_color(farmer.find("hairstyleColor")) or "#000000",
            "eye_color": look.read_color(farmer.find("newEyeColor")) or "#000000",
            "pants_color": look.read_color(farmer.find("pantsColor")) or "#000000",
            "worn": worn,
        }

    def set_appearance(self, uid, values, gamedata=None):
        """values: the fields to change, others are left as they are.

        gender ("Male"/"Female"), skin, hair, accessory (-1 = none),
        hair_color, eye_color ("#rrggbb"),
        shirt, pants: qualified id of the item to wear instead ("" = keep it),
        shirt_color, pants_color: dye color, used when the item can be dyed,
        hat, boots: qualified id ("" = take off).
        Clothes come from the game data, needed to change them.
        """
        current = self.appearance(uid)
        changes = {}  # save tag → new text
        if "gender" in values:
            if values["gender"] not in look.GENDERS:
                raise SaveError("error.bad_choice", field=T("field.gender"), value=values["gender"])
            changes["gender"] = changes["Gender"] = values["gender"]
        if "skin" in values:
            changes["skin"] = bounded(values["skin"], 0, look.SKIN_COUNT - 1, "field.skin")
        if "hair" in values:
            hair = bounded(values["hair"], 0, 9999, "field.hair")
            known = gamedata.hairstyles() if gamedata else look.DEFAULT_HAIRS
            if hair not in known and hair != current["hair"]:
                raise SaveError("error.bad_choice", field=T("field.hair"), value=hair)
            changes["hair"] = hair
        if "accessory" in values:
            changes["accessory"] = bounded(values["accessory"], -1, look.ACCESSORY_COUNT - 1, "field.accessory")
        colors = {}  # color tag → (r, g, b)
        for key, tag in (("hair_color", "hairstyleColor"), ("eye_color", "newEyeColor")):
            if key in values:
                colors[tag] = look.parse_color(values[key], f"field.{key}")

        # Worn items: (tag, new element or None to take off), built once then copied
        worn = []
        dyes = {}  # tag of a worn item kept → new dye color
        for key, prefix in (("shirt", "S"), ("pants", "P")):
            tag = self._WORN[key]
            color = look.parse_color(values[f"{key}_color"], f"field.{key}_color") \
                if values.get(f"{key}_color") else None
            if values.get(key):
                if not values[key].startswith(prefix + ":"):
                    raise SaveError("error.unknown_clothing", item=values[key])
                if gamedata is None:
                    raise SaveError("error.needs_game_data")
                worn.append((tag, look.new_clothing(gamedata, values[key], color)))
            elif color and current["worn"][key] and current["worn"][key]["dyeable"]:
                dyes[tag] = color
            elif color and key == "pants" and current["worn"][key] is None:
                colors["pantsColor"] = color  # default pants: only the farmer's color
        for key, build in (("hat", look.new_hat), ("boots", look.new_boots)):
            if key not in values:
                continue
            wanted = values[key] or None
            now = current["worn"][key]
            prefix = "H" if key == "hat" else "B"
            if wanted is None:
                if now is not None:
                    worn.append((self._WORN[key], None))
            elif now is None or f"{prefix}:{now['item_id']}" != wanted:
                if gamedata is None:
                    raise SaveError("error.needs_game_data")
                worn.append((self._WORN[key], build(gamedata, wanted)))

        for farmer in self._copies(uid):
            for tag, value in changes.items():
                if farmer.find(tag) is not None:  # older saves may lack one of the gender tags
                    _set(farmer, tag, value)
            for tag, rgb in colors.items():
                look.write_color(farmer.find(tag), rgb)
            for tag, element in worn:
                look.place(farmer, tag, items.copy_for(element) if element is not None else None)
                if tag == "boots":
                    _set(farmer, "shoes", element.findtext("indexInColorSheet")
                         if element is not None else look.NO_BOOTS_SHOE_COLOR)
            for tag, rgb in dyes.items():
                look.write_color(farmer.find(tag).find("clothesColor"), rgb)
            # The pants color drawn on the farmer follows the pants worn
            pants = farmer.find("pantsItem")
            pants_changed = "pantsItem" in dyes or any(tag == "pantsItem" for tag, _ in worn)
            if pants_changed and pants is not None and farmer.find("pantsColor") is not None:
                look.write_color(farmer.find("pantsColor"),
                                 look.parse_color(look.read_color(pants.find("clothesColor")), "field.pants_color"))

    # ------------------------------------------------------------------ museum
    # The museum is the location named ArchaeologyHouse (class LibraryMuseum). Its
    # <museumPieces> maps a display tile (Vector2 X, Y) to the id of the item shown there.
    # Gunther's rewards are recorded apart, in each farmer's <mailReceived>
    # ("museumCollectedReward…", "museum5"… "museumComplete"): they are never changed here,
    # so taking a piece back doesn't take a reward back, and donating it again gives none.
    MUSEUM = "ArchaeologyHouse"

    def _museum(self):
        for location in self.root.findall("locations/GameLocation"):
            if location.findtext("name") == self.MUSEUM:
                pieces = location.find("museumPieces")
                if pieces is None:
                    raise NotFound("error.missing_tag", tag="museumPieces", parent=self.MUSEUM)
                return pieces
        raise NotFound("error.no_museum")

    @staticmethod
    def _spot(entry):
        return _int(entry, "key/Vector2/X"), _int(entry, "key/Vector2/Y")

    @staticmethod
    def museum_item_id(value):
        """Plain object id of a donation: saves write "589", newer ones may write "(O)589"."""
        value = (value or "").strip()
        return value[3:] if value.startswith("(O)") else value

    def museum(self):
        """Donations, by display tile: [{"x", "y", "item_id"}], top to bottom, left to right."""
        pieces = [{"x": x, "y": y, "item_id": self.museum_item_id(entry.findtext("value/string"))}
                  for entry in self._museum() for x, y in [self._spot(entry)]]
        return sorted(pieces, key=lambda p: (p["y"], p["x"]))

    def _donation(self, spot):
        for entry in self._museum():
            if self._spot(entry) == tuple(spot):
                return entry
        return None

    def remove_donation(self, spot):
        """Takes a piece off its display; returns its item id."""
        entry = self._donation(spot)
        if entry is None:
            raise SaveError("error.no_donation", x=spot[0], y=spot[1])
        self._museum().remove(entry)
        return self.museum_item_id(entry.findtext("value/string"))

    def move_donation(self, source, target, spots=None):
        """Moves a piece to another display tile, swapping with the piece already there.

        spots: the display tiles of the museum map, needed to move onto an empty one.
        """
        entry = self._donation(source)
        if entry is None:
            raise SaveError("error.no_donation", x=source[0], y=source[1])
        other = self._donation(target)
        if other is None and (spots is None or tuple(target) not in spots):
            raise SaveError("error.not_a_display", x=target[0], y=target[1])
        for element, (x, y) in ((entry, target), (other, source)):
            if element is not None:
                _set(element.find("key/Vector2"), "X", x)
                _set(element.find("key/Vector2"), "Y", y)

    def donate(self, item_id, spot, spots):
        """Puts an item on a free display tile of the museum map."""
        item_id = self.museum_item_id(item_id)
        if any(p["item_id"] == item_id for p in self.museum()):
            raise SaveError("error.already_donated")
        if tuple(spot) not in spots:
            raise SaveError("error.not_a_display", x=spot[0], y=spot[1])
        if self._donation(spot) is not None:
            raise SaveError("error.display_taken", x=spot[0], y=spot[1])
        entry = etree.SubElement(self._museum(), "item")
        vector = etree.SubElement(etree.SubElement(entry, "key"), "Vector2")
        etree.SubElement(vector, "X").text = str(spot[0])
        etree.SubElement(vector, "Y").text = str(spot[1])
        etree.SubElement(etree.SubElement(entry, "value"), "string").text = item_id

    def first_free_item_slot(self, uid):
        """Index of the first empty inventory slot of a player, or None."""
        for i, element in enumerate(self._player(uid).find("items")):
            if items.is_empty(element):
                return i
        return None

    def take_one(self, uid, slot):
        """Takes one item from an inventory slot (the whole slot if it holds one)."""
        for slots in self._slots(uid, slot):
            element = slots[slot]
            stack = _int(element, "stack", 1)
            if stack > 1:
                _set(element, "stack", stack - 1)
            else:
                slots.replace(element, items.empty_slot())

    # ------------------------------------------------------------------ chests
    # Containers are found in every location's <objects> (a chest, or an auto-grabber
    # whose <heldObject> is a chest) and in the <fridge> of the farmhouse and cabins.
    # A container is named by "<location key>|<x>,<y>" (or "|fridge"), where the
    # location key is the location's name, or for a building interior its uniqueName.
    # Unlike a farmer's inventory, a chest's <items> list has no empty slots: items
    # are appended and removed.
    CHEST_CAPACITY = 36
    _SPECIAL_CAPACITY = {"BigChest": 70, "MiniShippingBin": 9, "JunimoChest": 9, "Enricher": 1}

    def _locations(self):
        """(key, location element, building element or None) for every location and building interior."""
        for location in self.root.findall("locations/GameLocation"):
            yield location.findtext("name"), location, None
            for building in location.findall("buildings/Building"):
                indoors = building.find("indoors")
                if indoors is None or indoors.get(XSI + "nil") == "true":
                    continue
                key = indoors.findtext("uniqueName") or \
                    f"{indoors.findtext('name')}@{building.findtext('tileX')},{building.findtext('tileY')}"
                yield key, indoors, building

    def _containers(self):
        """(key, container element, info) for every container of the save."""
        for key, location, building in self._locations():
            where = {"location": location.findtext("name") or key, "location_key": key,
                     "building": building.findtext("buildingType") if building is not None else None}
            fridge = location.find("fridge")
            if fridge is not None and fridge.find("items") is not None:
                yield f"{key}|fridge", fridge, {**where, "x": None, "y": None, "fridge": True}
            for entry in location.findall("objects/item"):
                obj = entry.find("value/Object")
                if obj is None:
                    continue
                chest = obj if obj.get(XSI + "type") == "Chest" else obj.find("heldObject")
                if chest is None or chest.get(XSI + "type") != "Chest" or chest.find("items") is None:
                    continue
                x, y = _int(entry, "key/Vector2/X"), _int(entry, "key/Vector2/Y")
                yield f"{key}|{x},{y}", chest, {**where, "x": x, "y": y, "fridge": False,
                                                 "holder": obj.findtext("name") if chest is not obj else None,
                                                 "holder_id": obj.findtext("itemId") if chest is not obj else None}

    def _container(self, key):
        for found, chest, _ in self._containers():
            if found == key:
                return chest
        raise NotFound("error.no_chest")

    def _capacity(self, chest):
        return self._SPECIAL_CAPACITY.get(chest.findtext("specialChestType") or "", self.CHEST_CAPACITY)

    def chests(self):
        """Every container: key, where it is, what it is, how full."""
        homes = {el.findtext("homeLocation"): el.findtext("name") for el, _ in self._farmers()}
        result = []
        for key, chest, info in self._containers():
            special = chest.findtext("specialChestType") or "None"
            color = chest.find("playerChoiceColor")
            shared = special == "JunimoChest" or bool(chest.findtext("globalInventoryId"))
            result.append({
                **info, "key": key,
                "name": info.get("holder") or chest.findtext("name") or "Chest",
                "item_id": info.get("holder_id") or chest.findtext("itemId") or "",
                "big_craftable": chest.findtext("bigCraftable") == "true",
                "special": special,
                "owner": homes.get(info["location_key"]),  # whose cabin or farmhouse
                "count": len(chest.find("items")), "capacity": self._capacity(chest),
                # Black is the game's "no color chosen"
                "color": None if color is None or _int(color, "PackedValue") in (0, 0xFF000000) else
                         "#{:02x}{:02x}{:02x}".format(_int(color, "R"), _int(color, "G"), _int(color, "B")),
                # Junimo chests share one inventory kept elsewhere: not edited here
                "editable": not shared,
            })
        return result

    def chest_items(self, key, describe=None):
        """Items of a container, like inventory() (no empty slots)."""
        slots = []
        for i, it in enumerate(self._container(key).find("items")):
            if items.is_empty(it):
                continue
            kind = it.get(XSI + "type") or "Item"
            slot = {"slot": i, "empty": False, "type": kind, "name": it.findtext("name") or "?",
                    "item_id": it.findtext("itemId") or "", "stack": _int(it, "stack", 1),
                    "quality": _int(it, "quality"), "upgrade_level": _int(it, "upgradeLevel", -1),
                    "editable": kind in STACKABLE_TYPES,
                    "has_quality": kind in STACKABLE_TYPES and it.findtext("bigCraftable") != "true"}
            extra = describe(it) if describe else {}
            slot.update({k: v for k, v in extra.items() if v is not None})
            slots.append(slot)
        return slots

    def _chest_list(self, key, editing=True):
        chest = self._container(key)
        if editing and not next(c for c in self.chests() if c["key"] == key)["editable"]:
            raise SaveError("error.chest_shared")
        return chest, chest.find("items")

    def set_chest_items(self, key, changes):
        """changes: {index: {"stack": n, "quality": q}} for plain objects."""
        _, slots = self._chest_list(key)
        listed = list(slots)
        for index, change in changes.items():
            if not 0 <= index < len(listed):
                raise SaveError("error.no_slot", slot=index + 1)
            it = listed[index]
            if it.get(XSI + "type") not in STACKABLE_TYPES:
                continue
            name = it.findtext("name")
            _set(it, "stack", bounded(change["stack"], 1, 999, "field.quantity", item=name))
            if it.findtext("bigCraftable") == "true":
                continue
            quality = bounded(change["quality"], 0, 4, "field.quality", item=name)
            if quality not in QUALITIES:
                raise SaveError("error.unknown_quality", item=name)
            _set(it, "quality", quality)

    def add_to_chest(self, key, element):
        chest, slots = self._chest_list(key)
        if len(slots) >= self._capacity(chest):
            raise SaveError("error.chest_full")
        slots.append(element)

    def remove_from_chest(self, key, index):
        """Takes an item out of a container; returns its element."""
        _, slots = self._chest_list(key)
        if not 0 <= index < len(slots):
            raise SaveError("error.no_slot", slot=index + 1)
        element = slots[index]
        slots.remove(element)
        return element

    def chest_to_inventory(self, key, index, uid):
        """Moves an item from a container into a farmer's first free inventory slot."""
        slot = self.first_free_item_slot(uid)
        if slot is None:
            raise SaveError("error.inventory_full", name=self._player(uid).findtext("name"))
        element = self.remove_from_chest(key, index)
        element.tail = None
        self.add_item(uid, slot, element)

    # ------------------------------------------------------------------ animals
    # Farm animals live in a location's <animals> (an animal house, or the farm itself for
    # animals left outside), keyed by their <myID>. 1.6 saves write each animal twice in a
    # location: in <animals> and again in <Animals><SerializableDictionaryOfInt64FarmAnimal>;
    # both copies are kept identical. An animal house's building also lists its residents
    # (<animalsThatLiveHere>) and counts them (<currentOccupants>, up to <maxOccupants>).
    MAX_ANIMAL_FRIENDSHIP = 1000  # 5 hearts of 200 points
    MAX_ANIMAL_HAPPINESS = 255

    def _animal_lists(self, location):
        """Both dictionaries of animals of a location (the second may be missing)."""
        lists = [location.find("animals")]
        second = location.find("Animals/SerializableDictionaryOfInt64FarmAnimal")
        if second is not None:
            lists.append(second)
        return [l for l in lists if l is not None]

    def _animal_places(self):
        """(key, location, building or None) for animal houses, and the farm (animals outside)."""
        for key, location, building in self._locations():
            if location.get(XSI + "type") == "AnimalHouse" or (building is None and key == "Farm"):
                yield key, location, building

    @staticmethod
    def _house_kind(location, building):
        """"Coop" or "Barn": the kind of animal a house takes (buildingTypeILiveIn of its animals).

        Taken from an animal living there, else from the building type ("Big Coop" → "Coop"),
        as Data/Buildings.json lets each coop or barn level take that kind of animal.
        """
        resident = location.findtext("animals/item/value/FarmAnimal/buildingTypeILiveIn")
        if resident:
            return resident
        building_type = building.findtext("buildingType") or ""
        return next((kind for kind in ("Coop", "Barn") if kind in building_type), building_type)

    def animal_homes(self):
        """Animal houses: key, building type, residents and capacity."""
        homes = []
        for key, location, building in self._animal_places():
            if building is None:
                continue
            homes.append({"key": key, "building": building.findtext("buildingType"),
                          "kind": self._house_kind(location, building),
                          "count": len(location.find("animals")), "capacity": _int(building, "maxOccupants")})
        return homes

    def animals(self):
        """Every farm animal: id, name, type, friendship, happiness, where it is."""
        owners = {el.findtext("UniqueMultiplayerID"): el.findtext("name") for el, _ in self._farmers()}
        result = []
        for key, location, building in self._animal_places():
            for item in location.find("animals"):
                animal = item.find("value/FarmAnimal")
                if animal is None:
                    continue
                result.append({
                    "id": animal.findtext("myID") or item.findtext("key/long"),
                    "name": animal.findtext("name") or "",
                    "type": animal.findtext("type") or "",
                    "lives_in": animal.findtext("buildingTypeILiveIn") or "",
                    "friendship": _int(animal, "friendshipTowardFarmer"),
                    "happiness": _int(animal, "happiness"),
                    "age": _int(animal, "age"),
                    "owner": owners.get(animal.findtext("ownerID")),
                    "home": key, "outside": building is None,
                })
        return result

    def _animal_entries(self, animal_id):
        """(location key, location, building, [entry in each copy]) of an animal."""
        for key, location, building in self._animal_places():
            entries = [item for animals in self._animal_lists(location) for item in animals
                       if item.findtext("key/long") == str(animal_id)]
            if entries:
                return key, location, building, entries
        raise NotFound("error.no_animal")

    def set_animals(self, changes):
        """changes: {animal id: {"name", "friendship", "happiness"}} (any of them)."""
        for animal_id, change in changes.items():
            *_, entries = self._animal_entries(animal_id)
            current = entries[0].find("value/FarmAnimal").findtext("name")
            values = {}
            if "name" in change:
                name = _name(change["name"], "field.animal_name")
                values["name"] = values["displayName"] = name
            if "friendship" in change:
                values["friendshipTowardFarmer"] = bounded(change["friendship"], 0, self.MAX_ANIMAL_FRIENDSHIP,
                                                           "field.animal_friendship", animal=current)
            if "happiness" in change:
                values["happiness"] = bounded(change["happiness"], 0, self.MAX_ANIMAL_HAPPINESS,
                                              "field.animal_happiness", animal=current)
            for entry in entries:
                animal = entry.find("value/FarmAnimal")
                for tag, value in values.items():
                    if animal.find(tag) is not None:
                        _set(animal, tag, value)

    def move_animal(self, animal_id, target_key):
        """Moves an animal into another animal house of the same kind (coop or barn) with room."""
        source_key, source, source_building, entries = self._animal_entries(animal_id)
        target = next(((loc, b) for k, loc, b in self._animal_places() if k == target_key and b is not None), None)
        if target is None:
            raise SaveError("error.no_animal_home")
        location, building = target
        animal = entries[0].find("value/FarmAnimal")
        name = animal.findtext("name")
        if target_key == source_key:
            return
        if self._house_kind(location, building) != animal.findtext("buildingTypeILiveIn"):
            raise SaveError("error.wrong_animal_home", animal=name, building=building.findtext("buildingType"))
        if len(location.find("animals")) >= _int(building, "maxOccupants"):
            raise SaveError("error.animal_home_full", building=building.findtext("buildingType"))
        # Somewhere the game already put an animal of that house, so it doesn't start inside a wall
        resident = location.find("animals/item/value/FarmAnimal/Position")
        for target_list, entry in zip(self._animal_lists(location), entries):
            entry.getparent().remove(entry)
            entry.tail = None
            if resident is not None:
                position = entry.find("value/FarmAnimal/Position")
                for axis in ("X", "Y"):
                    _set(position, axis, resident.findtext(axis))
            target_list.append(entry)
        for house, home_building, add in ((source, source_building, False), (location, building, True)):
            if home_building is None:
                continue
            residents = house.find("animalsThatLiveHere")
            if residents is not None:
                for node in [n for n in residents if n.text == str(animal_id)]:
                    residents.remove(node)
                if add:
                    etree.SubElement(residents, "long").text = str(animal_id)
            if home_building.find("currentOccupants") is not None:
                _set(home_building, "currentOccupants", len(house.find("animals")))

    # ------------------------------------------------------------------ calendar and weather
    # The date is on the save root (<currentSeason> as "spring"…, <dayOfMonth>, <year>), and on
    # each farmer for the load screen (<seasonForSaveGame> 0-3, <dayOfMonthForSaveGame>,
    # <yearForSaveGame>), with the days they played in <stats><Values> "daysPlayed".
    # A farmhand keeps the date of their last session: only the farmers at the current
    # date move with it, and their days played shift by the same number of days.
    # Tomorrow's weather is on the root (<weatherForTomorrow>, for the valley) and in
    # <locationWeather>, one entry per weather context ("Default", "Island"), each writing
    # it twice (<weatherForTomorrow><string> and <WeatherForTomorrow>).
    DAYS_PER_SEASON = 28
    WEATHERS = ("Sun", "Rain", "Storm", "Wind", "Snow", "GreenRain")
    ISLAND_WEATHERS = ("Sun", "Rain")
    #: Weather contexts that can be changed (the desert is always sunny)
    WEATHER_CONTEXTS = ("Default", "Island")

    @classmethod
    def _total_days(cls, season, day, year):
        return ((year - 1) * len(SEASONS) + SEASONS.index(season)) * cls.DAYS_PER_SEASON + day

    def _weather_contexts(self):
        """{context: LocationWeather element} from <locationWeather>."""
        found = {}
        for item in self.root.findall("locationWeather/item"):
            weather = item.find("value/LocationWeather")
            if weather is not None:
                found[item.findtext("key/string")] = weather
        return found

    def calendar(self):
        root = self.root
        tomorrow = {context: weather.findtext("WeatherForTomorrow") or weather.findtext("weatherForTomorrow/string")
                    for context, weather in self._weather_contexts().items() if context in self.WEATHER_CONTEXTS}
        if not tomorrow:  # older saves: only the root field
            tomorrow = {"Default": root.findtext("weatherForTomorrow")}
        return {"season": root.findtext("currentSeason"), "day": _int(root, "dayOfMonth"),
                "year": _int(root, "year"), "weather_tomorrow": tomorrow}

    @staticmethod
    def _days_played(farmer):
        for item in farmer.findall("stats/Values/item"):
            if item.findtext("key/string") == "daysPlayed":
                return item.find("value/unsignedInt")
        return None

    def set_date(self, season, day, year):
        """Moves the game to another date; returns the change in days (negative going back)."""
        if season not in SEASONS:
            raise SaveError("error.bad_choice", field=T("field.season"), value=season)
        day = bounded(day, 1, self.DAYS_PER_SEASON, "field.day")
        year = bounded(year, 1, 999, "field.year")
        root = self.root
        old_season, old_day, old_year = root.findtext("currentSeason"), _int(root, "dayOfMonth"), _int(root, "year")
        delta = self._total_days(season, day, year) - self._total_days(old_season, old_day, old_year)
        _set(root, "currentSeason", season)
        _set(root, "dayOfMonth", day)
        _set(root, "year", year)
        old = (str(old_day), str(SEASONS.index(old_season)), str(old_year))
        for farmer in [el for el, _ in self._farmers()] + [self.info.getroot()]:
            date = tuple(farmer.findtext(t) for t in ("dayOfMonthForSaveGame", "seasonForSaveGame", "yearForSaveGame"))
            if date != old:
                continue  # a farmhand away since an earlier day
            _set(farmer, "dayOfMonthForSaveGame", day)
            _set(farmer, "seasonForSaveGame", SEASONS.index(season))
            _set(farmer, "yearForSaveGame", year)
            played = self._days_played(farmer)
            if played is not None:
                played.text = str(max(1, int(played.text or 0) + delta))
        return delta

    def set_weather_tomorrow(self, context, weather):
        if context not in self.WEATHER_CONTEXTS:
            raise SaveError("error.bad_choice", field=T("field.weather"), value=context)
        allowed = self.ISLAND_WEATHERS if context == "Island" else self.WEATHERS
        if weather not in allowed:
            raise SaveError("error.bad_choice", field=T("field.weather"), value=weather)
        contexts = self._weather_contexts()
        if context not in contexts and not (context == "Default" and not contexts):
            raise SaveError("error.bad_choice", field=T("field.weather"), value=context)
        if context in contexts:
            entry = contexts[context]
            for path in ("weatherForTomorrow/string", "WeatherForTomorrow"):
                node = entry.find(path)
                if node is not None:
                    node.text = weather
        if context == "Default" and self.root.find("weatherForTomorrow") is not None:
            _set(self.root, "weatherForTomorrow", weather)

    # ------------------------------------------------------------------ community center
    # <bundleData> (save root): "Room/id" → "name/reward/ingredients/color/required/sprite/
    # display name", ingredients being "id count quality" triples (id -1: gold).
    # The CommunityCenter location keeps, per bundle id, <bundles>: one flag per token of
    # the ingredients (the first ones, one per ingredient, say what was given; the game
    # sets them all when a bundle is completed), and <bundleRewards>: a reward waiting to
    # be collected. A room is restored when <areasComplete> says so, and the host's
    # "cc…" mail flags unlock what it gives (greenhouse, bus, minecarts…).
    CC_ROOMS = ("Pantry", "Crafts Room", "Fish Tank", "Boiler Room", "Vault", "Bulletin Board", "Abandoned Joja Mart")
    CC_MAIL = ("ccPantry", "ccCraftsRoom", "ccFishTank", "ccBoilerRoom", "ccVault", "ccBulletin")

    def _community_center(self):
        for location in self.root.findall("locations/GameLocation"):
            if location.findtext("name") == "CommunityCenter":
                return location
        raise NotFound("error.no_community_center")

    @staticmethod
    def _int_dict(element):
        """{int key: value element} of a serialized dictionary keyed by <int>."""
        return {int(item.findtext("key/int")): item.find("value") for item in element} if element is not None else {}

    def _host_mail(self):
        return [self.root.find("player/mailReceived"), self.info.getroot().find("mailReceived")]

    def community_center(self):
        """Rooms and bundles with their progress; read-only when the farm chose Joja."""
        cc = self._community_center()
        flags = self._int_dict(cc.find("bundles"))
        rewards = self._int_dict(cc.find("bundleRewards"))
        areas = [node.text == "true" for node in cc.find("areasComplete")] if cc.find("areasComplete") is not None else []
        joja = any(m.text == "JojaMember" for m in self.root.find("player/mailReceived"))
        rooms = {}
        for item in self.root.findall("bundleData/item"):
            room, _, raw_id = (item.findtext("key/string") or "").partition("/")
            fields = (item.findtext("value/string") or "").split("/")
            if not raw_id.isdigit() or len(fields) < 3:
                continue
            bundle_id = int(raw_id)
            tokens = fields[2].split()
            states = [node.text == "true" for node in flags[bundle_id].iter("boolean")] if bundle_id in flags else []
            ingredients = [{"item_id": tokens[i], "count": int(tokens[i + 1]), "quality": int(tokens[i + 2]),
                            "donated": i // 3 < len(states) and states[i // 3]}
                           for i in range(0, len(tokens) - 2, 3)]
            need = int(fields[4]) if len(fields) > 4 and fields[4].strip().isdigit() else len(ingredients)
            given = sum(1 for ing in ingredients if ing["donated"])
            area = self.CC_ROOMS.index(room) if room in self.CC_ROOMS else -1
            restored = 0 <= area < len(areas) and areas[area]
            rooms.setdefault(room, {"room": room, "area": area, "restored": restored, "bundles": []})
            rooms[room]["bundles"].append({
                "id": bundle_id, "name": fields[0], "display": fields[6] if len(fields) > 6 and fields[6] else "",
                "reward": fields[1], "ingredients": ingredients, "need": need, "given": min(given, need),
                "complete": given >= need,
                "reward_waiting": bundle_id in rewards and rewards[bundle_id].findtext("boolean") == "true",
                # The missing bundle (Joja Mart) and the Joja route are left to the game
                "editable": not joja and 0 <= area < len(self.CC_MAIL),
            })
        return {"joja": joja, "rooms": list(rooms.values())}

    def _bundle(self, bundle_id):
        for room in self.community_center()["rooms"]:
            for bundle in room["bundles"]:
                if bundle["id"] == bundle_id:
                    return room, bundle
        raise NotFound("error.no_bundle")

    def _set_flags(self, dictionary_tag, bundle_id, value):
        node = self._int_dict(self._community_center().find(dictionary_tag)).get(bundle_id)
        if node is None:
            return
        for flag in node.iter("boolean"):
            flag.text = "true" if value else "false"

    def complete_bundle(self, bundle_id):
        """Marks every ingredient given and the reward waiting at the Community Center.

        When it was the room's last bundle, the room is marked restored and the host gets
        its mail flag, which unlocks what the room gives. Returns True in that case.
        """
        room, bundle = self._bundle(bundle_id)
        if not bundle["editable"]:
            raise SaveError("error.bundle_locked")
        if bundle["complete"]:
            return False
        self._set_flags("bundles", bundle_id, True)
        if bundle["reward"]:
            self._set_flags("bundleRewards", bundle_id, True)
        others_done = all(b["complete"] for b in room["bundles"] if b["id"] != bundle_id)
        if not others_done or room["restored"]:
            return False
        areas = list(self._community_center().find("areasComplete"))
        if room["area"] < len(areas):
            areas[room["area"]].text = "true"
        flag = self.CC_MAIL[room["area"]]
        for mail in self._host_mail():
            if mail is not None and not any(m.text == flag for m in mail):
                etree.SubElement(mail, "string").text = flag
        return True

    def reset_bundle(self, bundle_id):
        """Takes every ingredient back out of a bundle (not in a room already restored)."""
        room, bundle = self._bundle(bundle_id)
        if not bundle["editable"]:
            raise SaveError("error.bundle_locked")
        if room["restored"]:
            raise SaveError("error.room_restored")
        self._set_flags("bundles", bundle_id, False)
        self._set_flags("bundleRewards", bundle_id, False)

    # ------------------------------------------------------------------ quests
    # Each farmer's <questLog> holds their quests (xsi:type ItemDeliveryQuest, SlayMonsterQuest…),
    # with the title and texts saved in the game's language. A completed quest stays in the
    # log until the farmer clicks it to collect its reward: the game then pays <moneyReward>
    # and adds the quests in <nextQuests>. Completing here only sets <completed>, so the
    # reward and what follows still go through the game.

    def quests(self, uid):
        result = []
        for index, quest in enumerate(self._player(uid).find("questLog")):
            result.append({
                "index": index, "id": quest.findtext("id") or "",
                "type": quest.get(XSI + "type") or "Quest",
                "title": quest.findtext("_questTitle") or quest.findtext("questTitle") or "",
                "description": quest.findtext("_questDescription") or "",
                "objective": quest.findtext("_currentObjective") or "",
                "completed": quest.findtext("completed") == "true",
                "daily": quest.findtext("dailyQuest") == "true",
                "days_left": _int(quest, "daysLeft"),
                "reward": _int(quest, "moneyReward"),
                # What a delivery or collection quest asks, when it says so
                "target": quest.findtext("target") or "",
                "item": quest.findtext("item") or quest.findtext("ItemId") or "",
                "number": _int(quest, "number", 0),
                # Story quests can't be dropped in the game: removing one may block what follows
                "cancellable": quest.findtext("canBeCancelled") == "true" or quest.findtext("dailyQuest") == "true",
            })
        return result

    def _quest_copies(self, uid, index):
        logs = [farmer.find("questLog") for farmer in self._copies(uid)]
        if not 0 <= index < len(logs[0]):
            raise SaveError("error.no_quest")
        return [log[index] for log in logs if log is not None and index < len(log)]

    def complete_quest(self, uid, index):
        """Marks a quest done: the farmer collects its reward in the journal."""
        for quest in self._quest_copies(uid, index):
            _set(quest, "completed", "true")
            if quest.find("showNew") is not None:
                _set(quest, "showNew", "true")  # highlighted in the journal, like a quest just done
        return self.quests(uid)[index]["title"]

    def remove_quest(self, uid, index):
        """Takes a quest out of the journal; returns its title."""
        title = self.quests(uid)[index]["title"] if 0 <= index < len(self.quests(uid)) else ""
        for quest in self._quest_copies(uid, index):
            quest.getparent().remove(quest)
        return title

    # ------------------------------------------------------------------ special items and powers
    # A power's condition (see GameData.parse_power_condition) points at a mail flag, an event
    # seen or a stat, of the farmer ("Current") or of the host ("Host": shared by the farm).

    def _power_farmers(self, uid, who):
        host = self.root.find("player").findtext("UniqueMultiplayerID")
        return self._copies(host if who == "Host" else uid)

    @staticmethod
    def _stat_entry(farmer, key):
        for item in farmer.findall("stats/Values/item"):
            if item.findtext("key/string") == key:
                return item
        return None

    def has_power(self, uid, condition):
        kind, who, key, minimum = condition
        farmer = self._power_farmers(uid, who)[0]
        if kind == "mail":
            return any(m.text == key for m in farmer.find("mailReceived"))
        if kind == "event":
            return any(e.text == key for e in farmer.find("eventsSeen"))
        entry = self._stat_entry(farmer, key)
        return entry is not None and _int(entry, "value/unsignedInt") >= minimum

    def set_power(self, uid, condition, owned):
        """Gives or takes a special item or power, in every copy of the farmer it belongs to."""
        kind, who, key, minimum = condition
        if self.has_power(uid, condition) == owned:
            return False
        for farmer in self._power_farmers(uid, who):
            if kind in ("mail", "event"):
                container = farmer.find("mailReceived" if kind == "mail" else "eventsSeen")
                if container is None:
                    continue
                if owned:
                    tag = container[0].tag if len(container) else ("string" if kind == "mail" else "int")
                    etree.SubElement(container, tag).text = key
                else:
                    for node in [n for n in container if n.text == key]:
                        container.remove(node)
                continue
            values = farmer.find("stats/Values")
            if values is None:
                continue
            entry = self._stat_entry(farmer, key)
            if owned:
                if entry is None:
                    entry = etree.SubElement(values, "item")
                    etree.SubElement(etree.SubElement(entry, "key"), "string").text = key
                    etree.SubElement(etree.SubElement(entry, "value"), "unsignedInt").text = str(minimum)
                else:
                    _set(entry.find("value"), "unsignedInt", max(minimum, _int(entry, "value/unsignedInt")))
            elif entry is not None:
                values.remove(entry)
        return True