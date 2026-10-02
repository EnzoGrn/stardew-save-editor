"""Building and changing item elements the way the game writes them.

New items copy the exact tag list of real items found in 1.6 saves, so the
game reads them like any item it created itself. Only plain objects and big
craftables are built here; see gamedata.ADDABLE_PREFIXES for why.
"""
import copy

from lxml import etree

from .constants import XSI
from .errors import SaveError

_XSI_NS = XSI[1:-1]
_XSD_NS = "http://www.w3.org/2001/XMLSchema"

# A plain object as the game saves it (taken from a real 1.6 save). The values
# marked {} are filled from the game data; the others are the game's defaults.
_OBJECT_TEMPLATE = f"""<Item xmlns:xsi="{_XSI_NS}" xmlns:xsd="{_XSD_NS}" xsi:type="Object">\
<isLostItem>false</isLostItem><category>{{category}}</category><hasBeenInInventory>true</hasBeenInInventory>\
<name>{{name}}</name><parentSheetIndex>{{sprite}}</parentSheetIndex><itemId>{{item_id}}</itemId>\
<specialItem>false</specialItem><isRecipe>false</isRecipe><quality>{{quality}}</quality><stack>{{stack}}</stack>\
<SpecialVariable>0</SpecialVariable><tileLocation><X>0</X><Y>0</Y></tileLocation><owner>0</owner>\
<type>{{type}}</type><canBeSetDown>true</canBeSetDown><canBeGrabbed>true</canBeGrabbed>\
<isSpawnedObject>false</isSpawnedObject><questItem>false</questItem><isOn>true</isOn>\
<fragility>{{fragility}}</fragility><price>{{price}}</price><edibility>{{edibility}}</edibility>\
<bigCraftable>{{big_craftable}}</bigCraftable><setOutdoors>{{outdoors}}</setOutdoors><setIndoors>{{indoors}}</setIndoors>\
<readyForHarvest>false</readyForHarvest><showNextIndex>false</showNextIndex><flipped>false</flipped>\
<isLamp>{{lamp}}</isLamp><minutesUntilReady>0</minutesUntilReady>\
<boundingBox><X>0</X><Y>0</Y><Width>0</Width><Height>0</Height><Location><X>0</X><Y>0</Y></Location>\
<Size><X>0</X><Y>0</Y></Size></boundingBox><scale><X>0</X><Y>0</Y></scale><uses>0</uses>\
<destroyOvernight>false</destroyOvernight></Item>"""

# Watering can capacity per upgrade level (40 at the start, +15 per level)
_WATER_PER_LEVEL = 15
_BASE_WATER = 40


def _bool(value):
    return "true" if value else "false"


def _escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def new_item(gamedata, qualified_id, stack=1, quality=0):
    """A new plain object or big craftable element, from the game data."""
    if not gamedata.addable(qualified_id):
        raise SaveError("error.item_not_addable", item=qualified_id)
    prefix, item_id = qualified_id.split(":", 1)
    data = gamedata.items[qualified_id]["data"]
    big = prefix == "BC"
    values = {
        "category": data.get("Category", -9 if big else 0),
        "name": _escape(data.get("Name") or item_id),
        "sprite": data.get("SpriteIndex", 0),
        "item_id": _escape(item_id),
        "quality": 0 if big else quality,
        "stack": stack,
        "type": _escape(data.get("Type") or ("Crafting" if big else "Basic")),
        "fragility": data.get("Fragility", 0),
        "price": data.get("Price", 0),
        "edibility": data.get("Edibility", -300),
        "big_craftable": _bool(big),
        "outdoors": _bool(big and data.get("CanBePlacedOutdoors", True)),
        "indoors": _bool(big and data.get("CanBePlacedIndoors", True)),
        "lamp": _bool(data.get("IsLamp", False)),
    }
    return etree.fromstring(_OBJECT_TEMPLATE.format(**values))


def is_empty(element):
    return element.get(XSI + "nil") == "true"


def empty_slot():
    element = etree.Element("Item", nsmap={"xsi": _XSI_NS})
    element.set(XSI + "nil", "true")
    return element


def set_tool_level(element, gamedata, level):
    """Upgrades or downgrades a tool in place (Axe > Gold Axe…), from the game data."""
    class_name = element.get(XSI + "type")
    levels = gamedata.tool_levels(class_name)
    if level not in levels:
        raise SaveError("error.tool_level", level=level)
    tool_id = levels[level]
    data = gamedata.items[f"T:{tool_id}"]["data"]

    def set_text(tag, value):
        node = element.find(tag)
        if node is not None:
            node.text = str(value)

    sprite = data.get("SpriteIndex", 0)
    menu = data.get("MenuSpriteIndex", -1)
    menu = sprite if menu < 0 else menu
    # The current sprite is offset from the initial one by the facing direction: keep the offset
    try:
        offset = int(element.findtext("currentParentTileIndex")) - int(element.findtext("initialParentTileIndex"))
    except (TypeError, ValueError):
        offset = 0
    set_text("itemId", tool_id)
    set_text("name", data.get("Name") or tool_id)
    set_text("upgradeLevel", level)
    for tag in ("initialParentTileIndex", "InitialParentTileIndex"):
        set_text(tag, sprite)
    set_text("currentParentTileIndex", sprite + offset)
    for tag in ("indexOfMenuItemView", "IndexOfMenuItemView"):
        set_text(tag, menu)
    if class_name == "WateringCan":
        capacity = _BASE_WATER + _WATER_PER_LEVEL * level
        try:
            set_text("WaterLeft", min(int(element.findtext("WaterLeft")), capacity))
        except (TypeError, ValueError):
            pass


def copy_for(element):
    """A copy for another file holding the same player (host: save + SaveGameInfo)."""
    return copy.deepcopy(element)