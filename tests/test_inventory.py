"""Inventory editing: adding, removing, moving items, upgrading tools.

Uses a minimal hand-made save (host with an inventory, in both files) and the
fake game folder from conftest.py.
"""
import pytest

from sdvsave import SaveError, SaveGame, items, xmlio
from sdvsave.constants import XSI
from sdvsave.gamedata import GameData

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
HOST_UID = "-123"

INVENTORY = (
    f'<items xmlns:xsi="{XSI_NS}">'
    '<Item xsi:type="Axe"><name>Axe</name><itemId>Axe</itemId><stack>1</stack>'
    '<initialParentTileIndex>189</initialParentTileIndex><currentParentTileIndex>191</currentParentTileIndex>'
    '<indexOfMenuItemView>215</indexOfMenuItemView><upgradeLevel>0</upgradeLevel>'
    '<InitialParentTileIndex>189</InitialParentTileIndex><IndexOfMenuItemView>215</IndexOfMenuItemView></Item>'
    '<Item xsi:type="Object"><name>Clay</name><itemId>330</itemId><quality>0</quality><stack>2</stack>'
    '<bigCraftable>false</bigCraftable></Item>'
    '<Item xsi:type="WateringCan"><name>Iridium Watering Can</name><itemId>IridiumWateringCan</itemId>'
    '<initialParentTileIndex>322</initialParentTileIndex><currentParentTileIndex>327</currentParentTileIndex>'
    '<indexOfMenuItemView>345</indexOfMenuItemView><upgradeLevel>4</upgradeLevel>'
    '<InitialParentTileIndex>322</InitialParentTileIndex><IndexOfMenuItemView>345</IndexOfMenuItemView>'
    '<WaterLeft>100</WaterLeft></Item>'
    '<Item xsi:nil="true" /><Item xsi:nil="true" />'
    '</items>'
)


def write_save(folder):
    folder.mkdir()
    farmer = f"<name>Host</name>{INVENTORY}<UniqueMultiplayerID>{HOST_UID}</UniqueMultiplayerID>"
    (folder / folder.name).write_text(
        f'<SaveGame xmlns:xsi="{XSI_NS}"><player>{farmer}</player><farmhands /></SaveGame>',
        encoding="utf-8")
    (folder / "SaveGameInfo").write_text(f'<Farmer xmlns:xsi="{XSI_NS}">{farmer}</Farmer>', encoding="utf-8")
    return folder


@pytest.fixture
def save(tmp_path):
    return SaveGame(write_save(tmp_path / "Test_1"))


@pytest.fixture
def data(game):
    return GameData.load(game)


def names(save):
    """Item names of the host, in the save file and in SaveGameInfo."""
    result = []
    for farmer in save._copies(HOST_UID):
        result.append([None if items.is_empty(i) else i.findtext("name") for i in farmer.find("items")])
    return result


# ---------------------------------------------------------------------- game data
def test_icons_point_into_the_right_sheet(data):
    assert data.icon("O:330") == {"sheet": "Maps/springobjects", "x": 330 % 24 * 16, "y": 330 // 24 * 16,
                                  "w": 16, "h": 16, "sheet_w": 384, "sheet_h": 624}
    assert data.icon("O:Moss")["sheet"] == "TileSheets/Objects_2"
    assert (data.icon("T:GoldAxe")["x"], data.icon("T:GoldAxe")["y"]) == (257 % 21 * 16, 257 // 21 * 16)
    assert data.icon("BC:8")["h"] == 32
    assert data.icon("W:47") is None          # no weapons sheet in the fixture
    assert data.sheet_path("../../etc/passwd") is None


def test_tool_levels(data):
    assert data.tool_levels("Axe") == {0: "Axe", 1: "CopperAxe", 3: "GoldAxe"}
    assert data.tool_levels("FishingRod") == {}  # rods are separate tools, not levels


def test_search_matches_translated_and_english_names(data):
    assert data.search("diam", "fr") == [("O:72", "Diamant")]
    assert data.search("DIAMOND", "fr") == [("O:72", "Diamant")]
    assert [name for _, name in data.search("mousse", "fr")] == ["Mousse"]
    assert data.search("ring", "en") == []    # rings have their own class
    assert data.search("chest", "en") == []   # so do chests
    assert data.search("scare", "en") == [("BC:8", "Scarecrow")]


# ---------------------------------------------------------------------- new items
def test_new_object_follows_the_game_format(data):
    element = items.new_item(data, "O:72", stack=5, quality=2)
    # Same tags, in the same order, as a diamond saved by the game itself
    assert [c.tag for c in element] == [
        "isLostItem", "category", "hasBeenInInventory", "name", "parentSheetIndex", "itemId",
        "specialItem", "isRecipe", "quality", "stack", "SpecialVariable", "tileLocation", "owner",
        "type", "canBeSetDown", "canBeGrabbed", "isSpawnedObject", "questItem", "isOn", "fragility",
        "price", "edibility", "bigCraftable", "setOutdoors", "setIndoors", "readyForHarvest",
        "showNextIndex", "flipped", "isLamp", "minutesUntilReady", "boundingBox", "scale", "uses",
        "destroyOvernight"]
    values = {c.tag: c.text for c in element}
    assert element.get(XSI + "type") == "Object"
    assert (values["name"], values["itemId"], values["parentSheetIndex"]) == ("Diamond", "72", "72")
    assert (values["category"], values["type"], values["price"]) == ("-2", "Minerals", "750")
    assert (values["stack"], values["quality"], values["bigCraftable"]) == ("5", "2", "false")


def test_new_big_craftable(data):
    values = {c.tag: c.text for c in items.new_item(data, "BC:8", quality=4)}
    assert (values["bigCraftable"], values["quality"], values["type"]) == ("true", "0", "Crafting")
    assert (values["setOutdoors"], values["setIndoors"]) == ("true", "false")


@pytest.mark.parametrize("qualified", ["O:516", "BC:130", "T:Axe", "O:4242"])
def test_items_with_their_own_class_cant_be_added(data, qualified):
    with pytest.raises(SaveError) as error:
        items.new_item(data, qualified)
    assert error.value.key == "error.item_not_addable"


# ---------------------------------------------------------------------- inventory changes
def test_add_item_to_an_empty_slot_in_both_files(save, data):
    save.add_item(HOST_UID, 3, items.new_item(data, "O:72"))
    assert names(save) == [["Axe", "Clay", "Iridium Watering Can", "Diamond", None]] * 2


def test_add_item_refuses_a_taken_or_missing_slot(save, data):
    with pytest.raises(SaveError) as error:
        save.add_item(HOST_UID, 1, items.new_item(data, "O:72"))
    assert error.value.key == "error.slot_taken"
    with pytest.raises(SaveError) as error:
        save.add_item(HOST_UID, 9, items.new_item(data, "O:72"))
    assert error.value.key == "error.no_slot"


def test_remove_item(save):
    save.remove_item(HOST_UID, 1)
    assert names(save) == [["Axe", None, "Iridium Watering Can", None, None]] * 2


def test_move_item_swaps_slots(save):
    save.move_item(HOST_UID, 0, 2)
    assert names(save) == [["Iridium Watering Can", "Clay", "Axe", None, None]] * 2
    save.move_item(HOST_UID, 1, 4)  # onto an empty slot
    assert names(save) == [["Iridium Watering Can", None, "Axe", None, "Clay"]] * 2


def test_upgrade_tool(save, data):
    save.set_inventory(HOST_UID, {}, {0: "3"}, data)
    for farmer in save._copies(HOST_UID):
        axe = {c.tag: c.text for c in farmer.find("items")[0]}
        assert (axe["name"], axe["itemId"], axe["upgradeLevel"]) == ("Gold Axe", "GoldAxe", "3")
        assert (axe["initialParentTileIndex"], axe["currentParentTileIndex"]) == ("231", "233")
        assert (axe["indexOfMenuItemView"], axe["IndexOfMenuItemView"]) == ("257", "257")


def test_downgrade_watering_can_trims_its_water(save, data):
    save.set_inventory(HOST_UID, {}, {2: "0"}, data)
    can = {c.tag: c.text for c in save._player(HOST_UID).find("items")[2]}
    assert (can["itemId"], can["WaterLeft"]) == ("WateringCan", "40")


def test_unknown_tool_level_is_refused(save, data):
    with pytest.raises(SaveError) as error:
        save.set_inventory(HOST_UID, {}, {0: "2"}, data)  # no steel axe in the fixture
    assert error.value.key == "error.tool_level"


def test_changes_survive_writing_and_reading(save, data, tmp_path):
    save.add_item(HOST_UID, 4, items.new_item(data, "BC:8"))
    save.write()
    again = SaveGame(tmp_path / "Test_1")
    assert again.inventory(HOST_UID)[4]["name"] == "Scarecrow"
    assert b"<Item xsi:type=\"Object\">" in xmlio.serialize(again.main)  # no stray namespace declarations