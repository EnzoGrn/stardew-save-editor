"""Museum: donations shown, moved, taken back and donated.

The mini-save has a museum with three pieces and a host with a small inventory;
the fake game folder gets a museum map in TMX, as StardewXnbHack writes it.
"""
import base64
import struct
import zlib

import pytest

from sdvsave import SaveError, SaveGame, xmlio
from sdvsave.gamedata import GameData

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
HOST = "-123"
# Display tiles of the fake map (the real museum has a few dozen)
SPOTS = {(2, 1), (3, 1), (4, 1), (2, 3), (3, 3)}


def piece(x, y, item_id):
    return (f"<item><key><Vector2><X>{x}</X><Y>{y}</Y></Vector2></key>"
            f"<value><string>{item_id}</string></value></item>")


def write_save(folder):
    folder.mkdir()
    farmer = (f'<name>Host</name><items xmlns:xsi="{XSI_NS}">'
              '<Item xsi:type="Object"><name>Dwarf Scroll II</name><itemId>97</itemId><quality>0</quality>'
              '<stack>2</stack><bigCraftable>false</bigCraftable></Item>'
              '<Item xsi:type="Object"><name>Clay</name><itemId>330</itemId><quality>0</quality>'
              '<stack>1</stack><bigCraftable>false</bigCraftable></Item>'
              '<Item xsi:nil="true" /></items>'
              f"<UniqueMultiplayerID>{HOST}</UniqueMultiplayerID>")
    museum = ('<GameLocation xsi:type="LibraryMuseum"><name>ArchaeologyHouse</name><museumPieces>'
              + piece(2, 1, "96") + piece(3, 1, "72") + piece(2, 3, "(O)80")
              + "</museumPieces></GameLocation>")
    (folder / folder.name).write_text(
        f'<SaveGame xmlns:xsi="{XSI_NS}"><player>{farmer}</player><locations>'
        f'<GameLocation><name>Farm</name></GameLocation>{museum}</locations><farmhands /></SaveGame>',
        encoding="utf-8")
    (folder / "SaveGameInfo").write_text(f'<Farmer xmlns:xsi="{XSI_NS}">{farmer}</Farmer>', encoding="utf-8")
    return folder


def write_map(game, encoding="csv"):
    """A 6x5 museum map: display tiles (1072, 1237…) of "untitled tile sheet" at SPOTS."""
    width, height, first_gid = 6, 5, 100
    gids = [0] * (width * height)
    for i, (x, y) in enumerate(sorted(SPOTS)):
        gids[y * width + x] = first_gid + (1072, 1073, 1074, 1237, 1238)[i] | (0x80000000 if i == 0 else 0)
    gids[0] = first_gid + 5  # another tile of the sheet: not a display
    if encoding == "csv":
        data = '<data encoding="csv">\n' + ",".join(map(str, gids)) + "\n</data>"
    else:
        packed = base64.b64encode(zlib.compress(struct.pack(f"<{len(gids)}I", *gids))).decode()
        data = f'<data encoding="base64" compression="zlib">{packed}</data>'
    tmx = (f'<?xml version="1.0" encoding="UTF-8"?><map width="{width}" height="{height}">'
           '<tileset firstgid="1" name="walls_and_floors" />'
           f'<tileset firstgid="{first_gid}" name="untitled tile sheet" />'
           f'<layer name="Back" width="{width}" height="{height}"><data encoding="csv">'
           + ",".join(["1"] * (width * height)) + "</data></layer>"
           f'<layer name="Buildings" width="{width}" height="{height}">{data}</layer></map>')
    path = game / "Content (unpacked)" / "Maps" / "ArchaeologyHouse.tmx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tmx, encoding="utf-8")


@pytest.fixture
def save(tmp_path):
    return SaveGame(write_save(tmp_path / "Test_1"))


@pytest.fixture
def data(game):
    write_map(game)
    return GameData.load(game)


def spots_of(save):
    return {(p["x"], p["y"]): p["item_id"] for p in save.museum()}


# ---------------------------------------------------------------------- reading
def test_donations_of_the_museum(save):
    assert save.museum() == [{"x": 2, "y": 1, "item_id": "96"}, {"x": 3, "y": 1, "item_id": "72"},
                             {"x": 2, "y": 3, "item_id": "80"}]  # qualified ids read as plain ones


@pytest.mark.parametrize("encoding", ["csv", "base64"])
def test_display_spots_come_from_the_map(game, encoding):
    write_map(game, encoding)
    assert GameData.load(game).museum_spots() == SPOTS


def test_no_map_no_spots(game):
    assert GameData.load(game).museum_spots() is None


def test_items_the_museum_takes(data):
    assert sorted(data.museum_items()) == ["O:72", "O:80", "O:96", "O:97"]  # no clay, no tagged item


# ---------------------------------------------------------------------- moving
def test_move_onto_a_taken_display_swaps(save):
    save.move_donation((2, 1), (3, 1))
    assert spots_of(save) == {(3, 1): "96", (2, 1): "72", (2, 3): "80"}


def test_move_onto_an_empty_display_needs_the_map(save, data):
    with pytest.raises(SaveError) as error:
        save.move_donation((2, 1), (4, 1))  # no map given
    assert error.value.key == "error.not_a_display"
    save.move_donation((2, 1), (4, 1), data.museum_spots())
    assert spots_of(save)[(4, 1)] == "96" and (2, 1) not in spots_of(save)
    with pytest.raises(SaveError) as error:
        save.move_donation((4, 1), (5, 4), data.museum_spots())  # not a display tile
    assert error.value.key == "error.not_a_display"


# ---------------------------------------------------------------------- taking back, donating
def test_remove_donation(save):
    assert save.remove_donation((2, 3)) == "80"
    assert (2, 3) not in spots_of(save)
    with pytest.raises(SaveError) as error:
        save.remove_donation((2, 3))
    assert error.value.key == "error.no_donation"


def test_donate_on_a_free_display(save, data):
    spots = data.museum_spots()
    save.donate("97", (4, 1), spots)
    assert spots_of(save)[(4, 1)] == "97"
    for item_id, spot, key in (("97", (3, 3), "error.already_donated"),
                               ("330", (5, 4), "error.not_a_display"),
                               ("330", (3, 1), "error.display_taken")):
        with pytest.raises(SaveError) as error:
            save.donate(item_id, spot, spots)
        assert error.value.key == key


def test_take_one_from_a_stack_then_the_last(save):
    save.take_one(HOST, 0)
    for farmer in save._copies(HOST):
        assert farmer.find("items")[0].findtext("stack") == "1"
    save.take_one(HOST, 0)
    assert save.first_free_item_slot(HOST) == 0


def test_museum_changes_survive_writing_and_reading(save, data, tmp_path):
    save.donate("97", (4, 1), data.museum_spots())
    save.move_donation((2, 1), (3, 1))
    save.write()
    again = SaveGame(tmp_path / "Test_1")
    assert spots_of(again) == {(3, 1): "96", (2, 1): "72", (2, 3): "80", (4, 1): "97"}
    assert b"<item><key><Vector2><X>4</X><Y>1</Y></Vector2></key>" in xmlio.serialize(again.main)


def test_save_without_museum(tmp_path):
    folder = tmp_path / "Bare_1"
    folder.mkdir()
    (folder / "Bare_1").write_text("<SaveGame><player /><locations /></SaveGame>", encoding="utf-8")
    (folder / "SaveGameInfo").write_text("<Farmer />", encoding="utf-8")
    with pytest.raises(SaveError) as error:
        SaveGame(folder).museum()
    assert error.value.key == "error.no_museum"