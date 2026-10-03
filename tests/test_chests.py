"""Chests: every container of a save, its contents, adding and taking out items.

The mini-save has a chest on the farm, an auto-grabber, a big chest in a shed, a
Junimo chest, the farmhouse fridge, and a host with one free inventory slot.
"""
import pytest

from sdvsave import SaveError, SaveGame, items, xmlio
from sdvsave.gamedata import GameData

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
HOST = "-123"


def obj(name, item_id, stack=1, quality=0, kind="Object"):
    return (f'<Item xsi:type="{kind}"><name>{name}</name><itemId>{item_id}</itemId><quality>{quality}</quality>'
            f"<stack>{stack}</stack><bigCraftable>false</bigCraftable></Item>")


def chest(contents, name="Chest", item_id="130", special="None", color=0, extra=""):
    return (f'<Object xsi:type="Chest"><name>{name}</name><itemId>{item_id}</itemId><bigCraftable>true</bigCraftable>'
            f"<items>{contents}</items><playerChoiceColor><B>0</B><G>0</G><R>{color}</R><A>255</A>"
            f"<PackedValue>{255 << 24 | color}</PackedValue></playerChoiceColor>"
            f"<specialChestType>{special}</specialChestType>{extra}</Object>")


def at(x, y, value):
    return f"<item><key><Vector2><X>{x}</X><Y>{y}</Y></Vector2></key><value>{value}</value></item>"


def write_save(folder):
    folder.mkdir()
    farmer = (f'<name>Host</name><homeLocation>FarmHouse</homeLocation><items xmlns:xsi="{XSI_NS}">'
              + obj("Clay", "330") + '<Item xsi:nil="true" /></items>'
              f"<UniqueMultiplayerID>{HOST}</UniqueMultiplayerID>")
    grabber = ("<Object><name>Auto-Grabber</name><itemId>165</itemId><bigCraftable>true</bigCraftable>"
               "<heldObject xsi:type=\"Chest\"><name>Chest</name><itemId>-1</itemId>"
               f"<items>{obj('Milk', '184', 3)}</items><specialChestType>None</specialChestType></heldObject></Object>")
    shed = ('<Building><buildingType>Shed</buildingType><tileX>10</tileX><tileY>20</tileY>'
            '<indoors xsi:type="Shed"><name>Shed</name><uniqueName>Shed123</uniqueName><objects>'
            + at(1, 4, chest(obj("Diamond", "72", 5), name="Chest", item_id="BigChest", special="BigChest", color=200))
            + "</objects></indoors></Building>")
    farm = ("<GameLocation><name>Farm</name><objects>"
            + at(5, 6, chest(obj("Clay", "330", 10) + obj("Tulip", "591", 2, 1, "ColoredObject")))
            + at(7, 8, grabber)
            + at(9, 9, chest("", name="Junimo Chest", item_id="256", special="JunimoChest",
                             extra="<globalInventoryId>JunimoChests</globalInventoryId>"))
            + at(3, 3, "<Object><name>Stone</name><itemId>390</itemId></Object>")
            + f"</objects><buildings>{shed}</buildings></GameLocation>")
    house = ("<GameLocation><name>FarmHouse</name><fridge><name>Chest</name><itemId>130</itemId>"
             f"<items>{obj('Egg', '176')}</items><specialChestType>None</specialChestType></fridge>"
             "<objects /></GameLocation>")
    (folder / folder.name).write_text(
        f'<SaveGame xmlns:xsi="{XSI_NS}"><player>{farmer}</player><locations>{farm}{house}</locations>'
        "<farmhands /></SaveGame>", encoding="utf-8")
    (folder / "SaveGameInfo").write_text(f'<Farmer xmlns:xsi="{XSI_NS}">{farmer}</Farmer>', encoding="utf-8")
    return folder


@pytest.fixture
def save(tmp_path):
    return SaveGame(write_save(tmp_path / "Test_1"))


@pytest.fixture
def data(game):
    return GameData.load(game)


def by_key(save):
    return {c["key"]: c for c in save.chests()}


def names(save, key):
    return [(i["name"], i["stack"]) for i in save.chest_items(key)]


# ---------------------------------------------------------------------- reading
def test_every_container_is_found(save):
    chests = by_key(save)
    assert set(chests) == {"Farm|5,6", "Farm|7,8", "Farm|9,9", "FarmHouse|fridge", "Shed123|1,4"}
    assert chests["Farm|7,8"]["name"] == "Auto-Grabber" and chests["Farm|7,8"]["item_id"] == "165"
    assert (chests["Shed123|1,4"]["building"], chests["Shed123|1,4"]["capacity"]) == ("Shed", 70)
    assert chests["Shed123|1,4"]["color"] == "#c80000"
    assert chests["Farm|5,6"]["color"] is None                 # black: no color chosen
    assert chests["FarmHouse|fridge"]["owner"] == "Host" and chests["FarmHouse|fridge"]["fridge"]
    assert not chests["Farm|9,9"]["editable"]                 # Junimo chest: shared inventory
    assert (chests["Farm|5,6"]["count"], chests["Farm|5,6"]["capacity"]) == (2, 36)


def test_contents_include_flowers_as_editable(save):
    tulip = save.chest_items("Farm|5,6")[1]
    assert (tulip["name"], tulip["type"], tulip["editable"], tulip["has_quality"]) == \
        ("Tulip", "ColoredObject", True, True)


# ---------------------------------------------------------------------- editing
def test_set_quantities_and_qualities(save):
    save.set_chest_items("Farm|5,6", {0: {"stack": "99", "quality": "0"}, 1: {"stack": "5", "quality": "4"}})
    assert names(save, "Farm|5,6") == [("Clay", 99), ("Tulip", 5)]
    assert save.chest_items("Farm|5,6")[1]["quality"] == 4
    with pytest.raises(SaveError) as error:
        save.set_chest_items("Farm|5,6", {0: {"stack": "1000", "quality": "0"}})
    assert error.value.key == "error.out_of_range"


def test_add_and_remove(save, data):
    save.add_to_chest("Farm|7,8", items.new_item(data, "O:72", stack=2))
    assert names(save, "Farm|7,8") == [("Milk", 3), ("Diamond", 2)]
    removed = save.remove_from_chest("Farm|7,8", 0)
    assert removed.findtext("name") == "Milk" and names(save, "Farm|7,8") == [("Diamond", 2)]


def test_full_chest_refuses_more(save, data):
    for _ in range(36 - 2):
        save.add_to_chest("Farm|5,6", items.new_item(data, "O:72"))
    with pytest.raises(SaveError) as error:
        save.add_to_chest("Farm|5,6", items.new_item(data, "O:72"))
    assert error.value.key == "error.chest_full"


def test_junimo_chest_is_not_edited(save, data):
    with pytest.raises(SaveError) as error:
        save.add_to_chest("Farm|9,9", items.new_item(data, "O:72"))
    assert error.value.key == "error.chest_shared"


def test_move_to_inventory_in_both_files(save):
    save.chest_to_inventory("FarmHouse|fridge", 0, HOST)
    assert names(save, "FarmHouse|fridge") == []
    for farmer in save._copies(HOST):
        assert farmer.find("items")[1].findtext("name") == "Egg"
    with pytest.raises(SaveError) as error:  # inventory full now
        save.chest_to_inventory("Farm|5,6", 0, HOST)
    assert error.value.key == "error.inventory_full"
    assert names(save, "Farm|5,6") == [("Clay", 10), ("Tulip", 2)]  # nothing taken out


def test_unknown_container(save):
    with pytest.raises(SaveError) as error:
        save.chest_items("Farm|1,1")
    assert error.value.key == "error.no_chest"


def test_chest_changes_survive_writing_and_reading(save, data, tmp_path):
    save.add_to_chest("Shed123|1,4", items.new_item(data, "BC:8"))
    save.write()
    again = SaveGame(tmp_path / "Test_1")
    assert names(again, "Shed123|1,4") == [("Diamond", 5), ("Scarecrow", 1)]
    assert b'<Item xsi:type="Object"><isLostItem>' in xmlio.serialize(again.main)