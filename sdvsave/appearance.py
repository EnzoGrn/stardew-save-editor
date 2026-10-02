"""A farmer's look: body, colors and the clothes they wear.

How 1.6 saves it, on the <player> / <Farmer> element (and its SaveGameInfo copy):
  - <gender> and <Gender>: "Male" or "Female" (<isMale> is an old field, left alone)
  - <skin>, <hair>, <accessory> (-1 = none): indexes into the game's sprite sheets
  - <hairstyleColor>, <newEyeColor>, <pantsColor>: XNA colors, written as
    <B><G><R><A><PackedValue> with PackedValue = A << 24 | B << 16 | G << 8 | R
  - worn items, in this order: <hat>, <boots>, <leftRing>, <rightRing>,
    <shirtItem>, <pantsItem>; a hat or boots tag is simply absent when nothing is worn
  - <shoes>: color of the shoes on the farmer sprite, from the boots worn
    (the game draws plain shoes with color 2 when no boots are worn)
  - <pantsColor> follows the color of the pants worn

New worn items copy the exact tag list of the same items in a real 1.6 save.
"""
import re

from lxml import etree

from .constants import XSI
from .errors import SaveError, T

_XSI_NS = XSI[1:-1]
_XSD_NS = "http://www.w3.org/2001/XMLSchema"

GENDERS = ("Male", "Female")
SKIN_COUNT = 24
#: Hairstyles when no game data says otherwise: 0-55 on hairstyles.png, 100-117 on hairstyles2.png
DEFAULT_HAIRS = (*range(56), *range(100, 118))
#: Accessories (beards, glasses, earrings…); -1 is none
ACCESSORY_COUNT = 30
#: Accessories 0 to 5 are facial hair: the game tints them with the hair color
TINTED_ACCESSORIES = 6
NO_BOOTS_SHOE_COLOR = "2"

#: Worn item tags, in the order the game writes them after <newEyeColor>
_WORN_ORDER = ("newEyeColor", "hat", "boots", "leftRing", "rightRing", "shirtItem", "pantsItem")

_COLOR = re.compile(r"#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})")

_ITEM_HEAD = (f'<{{tag}} xmlns:xsi="{_XSI_NS}" xmlns:xsd="{_XSD_NS}">'
              "<isLostItem>false</isLostItem><category>{category}</category>"
              "<hasBeenInInventory>true</hasBeenInInventory><name>{name}</name><itemId>{item_id}</itemId>"
              "<specialItem>false</specialItem><isRecipe>false</isRecipe><quality>0</quality>"
              "<stack>1</stack><SpecialVariable>0</SpecialVariable>")

_CLOTHING_TEMPLATE = _ITEM_HEAD + (
    "<price>{price}</price><indexInTileSheet>{sprite}</indexInTileSheet>"
    '<indexInTileSheetFemale xsi:nil="true" /><clothesType>{clothes_type}</clothesType>'
    "<dyeable>{dyeable}</dyeable><clothesColor><B>0</B><G>0</G><R>0</R><A>255</A>"
    "<PackedValue>0</PackedValue></clothesColor><isPrismatic>{prismatic}</isPrismatic>"
    "<Price>{price}</Price></{tag}>")

_HAT_TEMPLATE = _ITEM_HEAD + (
    '<which xsi:nil="true" /><skipHairDraw>false</skipHairDraw>'
    "<ignoreHairstyleOffset>{ignore_offset}</ignoreHairstyleOffset>"
    "<hairDrawType>{hair_draw}</hairDrawType><isPrismatic>{prismatic}</isPrismatic></{tag}>")

_BOOTS_TEMPLATE = _ITEM_HEAD + (
    "<defenseBonus>{defense}</defenseBonus><immunityBonus>{immunity}</immunityBonus>"
    "<indexInTileSheet>{sprite}</indexInTileSheet><price>{price}</price>"
    "<indexInColorSheet>{color_index}</indexInColorSheet></{tag}>")


# ---------------------------------------------------------------------- colors
def read_color(element):
    """"#rrggbb" of a color element, or None."""
    if element is None:
        return None
    try:
        return hex_color(int(element.findtext(c)) for c in "RGB")
    except (TypeError, ValueError):
        return None


def parse_color(value, field):
    """(r, g, b) from "#rrggbb"; field: key of the field name, for the error message."""
    match = _COLOR.fullmatch((value or "").strip())
    if not match:
        raise SaveError("error.bad_color", field=T(field), value=value)
    return tuple(int(part, 16) for part in match.groups())


def write_color(element, rgb):
    """Writes a color element in the game's format, keeping its alpha."""
    r, g, b = rgb
    try:
        alpha = int(element.findtext("A"))
    except (TypeError, ValueError):
        alpha = 255
    values = {"B": b, "G": g, "R": r, "A": alpha, "PackedValue": alpha << 24 | b << 16 | g << 8 | r}
    for tag, value in values.items():
        node = element.find(tag)
        if node is None:
            node = etree.SubElement(element, tag)
        node.text = str(value)


def hex_color(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


_NAMED_COLORS = {"white": (255, 255, 255), "black": (0, 0, 0)}


def rgb_from_data(value):
    """(r, g, b) from the game data's color text (clothes' DefaultColor): "r g b" or a
    color name such as "White"; white when there is none."""
    text = str(value or "").strip()
    if text.lower() in _NAMED_COLORS:
        return _NAMED_COLORS[text.lower()]
    try:
        r, g, b = (int(part) for part in text.split()[:3])
        return r, g, b
    except ValueError:
        return 255, 255, 255


# ---------------------------------------------------------------------- worn items
def _escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bool(value):
    return "true" if value else "false"


def _int_field(fields, index, default=0):
    try:
        return int(fields[index])
    except (IndexError, ValueError):
        return default


def _check(gamedata, qualified_id, prefix):
    if not qualified_id.startswith(prefix + ":") or qualified_id not in gamedata.items:
        raise SaveError("error.unknown_clothing", item=qualified_id)
    return qualified_id.split(":", 1)[1], gamedata.items[qualified_id]


def new_clothing(gamedata, qualified_id, color=None):
    """A <shirtItem> (S:…) or <pantsItem> (P:…) element; color (r, g, b) if it can be dyed."""
    prefix = qualified_id.split(":", 1)[0]
    if prefix not in ("S", "P"):
        raise SaveError("error.unknown_clothing", item=qualified_id)
    item_id, item = _check(gamedata, qualified_id, prefix)
    data = item["data"]
    dyeable = bool(data.get("CanBeDyed"))
    element = etree.fromstring(_CLOTHING_TEMPLATE.format(
        tag="shirtItem" if prefix == "S" else "pantsItem", category=-100,
        name=_escape(data.get("Name") or item_id), item_id=_escape(item_id),
        price=data.get("Price", 50), sprite=data.get("SpriteIndex", 0),
        clothes_type="SHIRT" if prefix == "S" else "PANTS",
        dyeable=_bool(dyeable), prismatic=_bool(data.get("IsPrismatic"))))
    rgb = color if (dyeable and color) else rgb_from_data(data.get("DefaultColor"))
    write_color(element.find("clothesColor"), rgb)
    return element


#: Hats that hide the hair although hats.json says "false" (seen in real saves: the game
#: writes hairDrawType 2 for both beanies)
_HAIR_HIDING_HATS = {"Beanie", "Floppy Beanie"}


def hat_fields(fields):
    """(hair draw type, ignore hairstyle offset, prismatic) from a hats.json entry.

    hats.json: name/description/show hair/skip hair offset/tags/…
    The game's HairDrawType: 0 full hair, 1 hair hidden under the hat's brim, 2 no hair.
    """
    show_hair = fields[2].strip().lower() if len(fields) > 2 else "true"
    hair_draw = 2 if show_hair == "hide" else 0 if show_hair == "true" else 1
    if fields and fields[0] in _HAIR_HIDING_HATS:
        hair_draw = 2
    ignore_offset = len(fields) > 3 and fields[3].strip().lower() == "true"
    tags = fields[4].split() if len(fields) > 4 else []
    return hair_draw, ignore_offset, "Prismatic" in tags


def new_hat(gamedata, qualified_id):
    """A <hat> element."""
    item_id, item = _check(gamedata, qualified_id, "H")
    hair_draw, ignore_offset, prismatic = hat_fields(item.get("fields", []))
    return etree.fromstring(_HAT_TEMPLATE.format(
        tag="hat", category=-95, name=_escape(item["name"]), item_id=_escape(item_id),
        ignore_offset=_bool(ignore_offset), hair_draw=hair_draw, prismatic=_bool(prismatic)))


def new_boots(gamedata, qualified_id):
    """A <boots> element. Boots.json: name/description/price/defense/immunity/color index/…"""
    item_id, item = _check(gamedata, qualified_id, "B")
    fields = item.get("fields", [])
    sprite = _int_field(fields, 8, -1)
    if sprite < 0:
        sprite = int(item_id) if item_id.isdigit() else 0
    return etree.fromstring(_BOOTS_TEMPLATE.format(
        tag="boots", category=-97, name=_escape(item["name"]), item_id=_escape(item_id),
        defense=_int_field(fields, 3), immunity=_int_field(fields, 4), sprite=sprite,
        price=_int_field(fields, 2), color_index=_int_field(fields, 5)))


def place(farmer, tag, element):
    """Puts a worn item in its tag, where the game expects it; None takes it off."""
    current = farmer.find(tag)
    if element is not None and element.tag != tag:
        raise ValueError(f"{element.tag} given for <{tag}>")
    if current is not None:
        if element is None:
            farmer.remove(current)
        else:
            farmer.replace(current, element)
        return
    if element is None:
        return
    # Absent: insert right after the closest tag that comes before it
    for before in reversed(_WORN_ORDER[:_WORN_ORDER.index(tag)]):
        anchor = farmer.find(before)
        if anchor is not None:
            anchor.addnext(element)
            return
    raise SaveError("error.missing_tag", tag="newEyeColor", parent=farmer.tag)