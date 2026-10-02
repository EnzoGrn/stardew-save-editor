"""A save: reading and editing its data.

A save is made of two files that must stay consistent:
  - <Folder>/<Folder>      : all the data (SaveGame)
  - <Folder>/SaveGameInfo  : a copy of the host farmer, read by the load screen
Every change to the host is therefore applied to both.
"""
import os
from pathlib import Path

from lxml import etree

from . import items, xmlio
from .constants import (
    SKILLS, XP_FOR_LEVEL, QUALITIES, POINTS_PER_HEART, MAX_FRIENDSHIP_POINTS,
    BACKPACK_SIZES, XSI,
)
from .errors import NotFound, SaveChangedError, SaveError, T


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
                "editable": kind == "Object",
                "has_quality": kind == "Object" and it.findtext("bigCraftable") != "true",
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
                if it.get(XSI + "type") != "Object":
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