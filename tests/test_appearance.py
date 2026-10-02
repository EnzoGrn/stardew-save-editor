"""Appearance editing: body, colors and worn clothes.

The host wears a hat, boots, a shirt and pants, written like in a real 1.6
save; the farmhand wears no hat and no boots, so those tags are absent.
"""
import pytest

from sdvsave import SaveError, SaveGame, appearance, xmlio
from sdvsave.gamedata import GameData

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
HOST, FARMHAND = "-123", "456"


def color(r, g, b):
    return f"<B>{b}</B><G>{g}</G><R>{r}</R><A>255</A><PackedValue>{255 << 24 | b << 16 | g << 8 | r}</PackedValue>"


def clothes(tag, name, item_id, sprite, kind, dyeable, rgb):
    return (f"<{tag}><isLostItem>false</isLostItem><category>-100</category><hasBeenInInventory>true</hasBeenInInventory>"
            f"<name>{name}</name><itemId>{item_id}</itemId><specialItem>false</specialItem><isRecipe>false</isRecipe>"
            "<quality>0</quality><stack>1</stack><SpecialVariable>0</SpecialVariable><price>50</price>"
            f'<indexInTileSheet>{sprite}</indexInTileSheet><indexInTileSheetFemale xsi:nil="true" />'
            f"<clothesType>{kind}</clothesType><dyeable>{dyeable}</dyeable><clothesColor>{color(*rgb)}</clothesColor>"
            f"<isPrismatic>false</isPrismatic><Price>50</Price></{tag}>")


HAT = ("<hat><isLostItem>false</isLostItem><category>-95</category><hasBeenInInventory>true</hasBeenInInventory>"
       "<name>Floppy Beanie</name><itemId>54</itemId><specialItem>false</specialItem><isRecipe>false</isRecipe>"
       "<quality>0</quality><stack>1</stack><SpecialVariable>0</SpecialVariable><which xsi:nil=\"true\" />"
       "<skipHairDraw>false</skipHairDraw><ignoreHairstyleOffset>true</ignoreHairstyleOffset>"
       "<hairDrawType>2</hairDrawType><isPrismatic>false</isPrismatic></hat>")
BOOTS = ("<boots><isLostItem>false</isLostItem><category>-97</category><hasBeenInInventory>true</hasBeenInInventory>"
         "<name>Space Boots</name><itemId>514</itemId><specialItem>false</specialItem><isRecipe>false</isRecipe>"
         "<quality>0</quality><stack>1</stack><SpecialVariable>0</SpecialVariable><defenseBonus>4</defenseBonus>"
         "<immunityBonus>4</immunityBonus><indexInTileSheet>514</indexInTileSheet><price>450</price>"
         "<indexInColorSheet>10</indexInColorSheet></boots>")


def farmer(uid, name, worn_head):
    return (f"<name>{name}</name><gender>Female</gender><shoes>{10 if worn_head else 2}</shoes>"
            "<skin>3</skin><hair>26</hair><accessory>-1</accessory>"
            f"<hairstyleColor>{color(135, 70, 24)}</hairstyleColor><pantsColor>{color(105, 105, 105)}</pantsColor>"
            f"<newEyeColor>{color(21, 117, 105)}</newEyeColor>"
            + (HAT + BOOTS if worn_head else "")
            + '<leftRing xsi:nil="true" /><rightRing xsi:nil="true" />'
            + clothes("shirtItem", "Gold Trimmed Shirt", 1222, 222, "SHIRT", "true", (220, 0, 0))
            + clothes("pantsItem", "Baggy Pants", 10, 10, "PANTS", "false", (105, 105, 105))
            + f"<divorceTonight>false</divorceTonight><Gender>Female</Gender>"
            f"<UniqueMultiplayerID>{uid}</UniqueMultiplayerID>")


def write_save(folder):
    folder.mkdir()
    host = farmer(HOST, "Host", True)
    (folder / folder.name).write_text(
        f'<SaveGame xmlns:xsi="{XSI_NS}"><player>{host}</player>'
        f"<farmhands><Farmer>{farmer(FARMHAND, 'Hand', False)}</Farmer></farmhands></SaveGame>", encoding="utf-8")
    (folder / "SaveGameInfo").write_text(f'<Farmer xmlns:xsi="{XSI_NS}">{host}</Farmer>', encoding="utf-8")
    return folder


@pytest.fixture
def save(tmp_path):
    return SaveGame(write_save(tmp_path / "Test_1"))


@pytest.fixture
def data(game):
    return GameData.load(game)


def tags(element):
    return [child.tag for child in element]


def values(element):
    return {child.tag: child.text for child in element}


# ---------------------------------------------------------------------- reading
def test_appearance_of_the_host(save):
    look = save.appearance(HOST)
    assert (look["gender"], look["skin"], look["hair"], look["accessory"]) == ("Female", 3, 26, -1)
    assert (look["hair_color"], look["eye_color"], look["pants_color"]) == ("#874618", "#157569", "#696969")
    assert look["worn"]["shirt"] == {"item_id": "1222", "name": "Gold Trimmed Shirt",
                                     "color": "#dc0000", "dyeable": True, "sprite": 222}
    assert look["worn"]["hat"] == {"item_id": "54", "name": "Floppy Beanie", "hair_draw": 2, "ignore_offset": True}
    assert look["worn"]["boots"]["color_index"] == 10


def test_farmhand_without_hat_or_boots(save):
    worn = save.appearance(FARMHAND)["worn"]
    assert worn["hat"] is None and worn["boots"] is None


# ---------------------------------------------------------------------- body and colors
def test_body_and_colors_change_in_both_files(save):
    save.set_appearance(HOST, {"gender": "Male", "skin": "5", "hair": "40", "accessory": "2",
                               "hair_color": "#FF8000", "eye_color": "#000102"})
    for copy in save._copies(HOST):
        assert (copy.findtext("gender"), copy.findtext("Gender")) == ("Male", "Male")
        assert (copy.findtext("skin"), copy.findtext("hair"), copy.findtext("accessory")) == ("5", "40", "2")
        assert values(copy.find("hairstyleColor")) == {"B": "0", "G": "128", "R": "255", "A": "255",
                                                       "PackedValue": str(255 << 24 | 128 << 8 | 255)}
        assert copy.find("newEyeColor").findtext("PackedValue") == str(255 << 24 | 2 << 16 | 1 << 8)


@pytest.mark.parametrize("change, key", [
    ({"gender": "Robot"}, "error.bad_choice"),
    ({"skin": "24"}, "error.out_of_range"),
    ({"accessory": "-2"}, "error.out_of_range"),
    ({"hair": "80"}, "error.bad_choice"),     # no game data: 0-55 and 100-117
    ({"hair_color": "red"}, "error.bad_color"),
    ({"hat": "H:54"}, None),                  # already worn: nothing to do, no game data needed
    ({"hat": "H:0"}, "error.needs_game_data"),
])
def test_invalid_values_are_refused(save, change, key):
    if key is None:
        save.set_appearance(HOST, change)
        return
    with pytest.raises(SaveError) as error:
        save.set_appearance(HOST, change)
    assert error.value.key == key


def test_hairstyles_come_from_the_game_data(save, data):
    assert list(data.hairstyles())[-3:] == [55, 100, 101]   # covered versions aren't choices
    assert data.hairstyles()[101] == {"sheet": "Characters/Farmer/hairstyles2", "x": 16, "y": 0,
                                      "w": 16, "h": 32, "sheet_w": 128, "sheet_h": 672,
                                      "bald": True, "covered": -101}
    assert data.hairstyles(covered=True)[-101]["y"] == 16 * 16
    assert data.hairstyles()[9] == {"sheet": "Characters/Farmer/hairstyles", "x": 16, "y": 96,
                                    "w": 16, "h": 32, "sheet_w": 128, "sheet_h": 672,
                                    "bald": False, "covered": -1}
    save.set_appearance(HOST, {"hair": "101"}, data)
    for refused in ("60", "-101"):
        with pytest.raises(SaveError):
            save.set_appearance(HOST, {"hair": refused}, data)


def test_a_mod_hairstyle_already_worn_is_accepted(save, data):
    with pytest.raises(SaveError):  # out of the list: refused when it's new…
        save.set_appearance(HOST, {"hair": "301"}, data)
    save._player(HOST).find("hair").text = "301"
    save.set_appearance(HOST, {"hair": "301"}, data)  # …but kept when the farmer already has it


# ---------------------------------------------------------------------- clothes
def test_new_worn_items_follow_the_game_format(save, data):
    host = save._player(HOST)
    beanie = appearance.new_hat(data, "H:54")
    assert tags(beanie) == tags(host.find("hat")) and values(beanie) == values(host.find("hat"))
    boots = appearance.new_boots(data, "B:514")
    assert tags(boots) == tags(host.find("boots")) and values(boots) == values(host.find("boots"))
    pants = appearance.new_clothing(data, "P:10")
    assert tags(pants) == tags(host.find("pantsItem"))
    assert {k: v for k, v in values(pants).items() if k != "clothesColor"} == \
        {k: v for k, v in values(host.find("pantsItem")).items() if k != "clothesColor"}
    assert values(pants.find("clothesColor")) == values(host.find("pantsItem/clothesColor"))


def test_hat_fields_from_the_game_data(data):
    cowboy = values(appearance.new_hat(data, "H:0"))
    assert (cowboy["hairDrawType"], cowboy["ignoreHairstyleOffset"], cowboy["isPrismatic"]) == ("1", "true", "false")
    beanie = values(appearance.new_hat(data, "H:54"))
    assert beanie["hairDrawType"] == "2"       # the game hides the hair under beanies
    bowler = values(appearance.new_hat(data, "H:13"))
    assert (bowler["hairDrawType"], bowler["ignoreHairstyleOffset"], bowler["isPrismatic"]) == ("0", "false", "true")


def test_boots_with_their_own_sprite(data):
    crystal = values(appearance.new_boots(data, "B:878"))
    assert (crystal["indexInTileSheet"], crystal["indexInColorSheet"]) == ("42", "12")
    assert data.icon("B:878")["sheet"] == "TileSheets/Objects_2"


def test_change_shirt_and_dye(save, data):
    save.set_appearance(HOST, {"shirt": "S:1000", "shirt_color": "#102030"}, data)
    for copy in save._copies(HOST):
        shirt = copy.find("shirtItem")
        assert (shirt.findtext("itemId"), shirt.findtext("indexInTileSheet"), shirt.findtext("dyeable")) == \
            ("1000", "0", "true")
        assert appearance.read_color(shirt.find("clothesColor")) == "#102030"
        assert tags(copy)[tags(copy).index("shirtItem") + 1] == "pantsItem"  # same place
    save.set_appearance(HOST, {"shirt": "S:1001", "shirt_color": "#102030"}, data)  # can't be dyed
    assert appearance.read_color(save._player(HOST).find("shirtItem/clothesColor")) == "#ffffff"


def test_dyeing_the_worn_shirt_only_when_dyeable(save):
    save.set_appearance(HOST, {"shirt_color": "#00ff00", "pants_color": "#00ff00"})
    host = save._player(HOST)
    assert appearance.read_color(host.find("shirtItem/clothesColor")) == "#00ff00"
    assert appearance.read_color(host.find("pantsItem/clothesColor")) == "#696969"  # baggy pants: not dyeable


def test_new_pants_set_the_farmer_pants_color(save, data):
    save.set_appearance(HOST, {"pants": "P:0", "pants_color": "#abcdef"}, data)
    for copy in save._copies(HOST):
        assert appearance.read_color(copy.find("pantsItem/clothesColor")) == "#abcdef"
        assert appearance.read_color(copy.find("pantsColor")) == "#abcdef"


def test_take_off_hat_and_boots(save):
    save.set_appearance(HOST, {"hat": "", "boots": ""})
    for copy in save._copies(HOST):
        assert copy.find("hat") is None and copy.find("boots") is None
        assert copy.findtext("shoes") == appearance.NO_BOOTS_SHOE_COLOR
        assert tags(copy)[tags(copy).index("newEyeColor") + 1] == "leftRing"


def test_put_on_hat_and_boots_where_the_game_expects_them(save, data):
    save.set_appearance(FARMHAND, {"boots": "B:514"}, data)
    hand = save._player(FARMHAND)
    assert tags(hand)[tags(hand).index("newEyeColor"):][:3] == ["newEyeColor", "boots", "leftRing"]
    assert hand.findtext("shoes") == "10"
    save.set_appearance(FARMHAND, {"hat": "H:0"}, data)
    assert tags(hand)[tags(hand).index("newEyeColor"):][:4] == ["newEyeColor", "hat", "boots", "leftRing"]


def test_only_clothes_go_in_clothes_slots(save, data):
    for change in ({"hat": "B:514"}, {"boots": "H:0"}, {"shirt": "P:0"}, {"hat": "H:999"}):
        with pytest.raises(SaveError) as error:
            save.set_appearance(HOST, change, data)
        assert error.value.key == "error.unknown_clothing"


def test_unchanged_form_leaves_the_files_identical(save, tmp_path):
    before = (xmlio.serialize(save.main), xmlio.serialize(save.info))
    look = save.appearance(HOST)
    save.set_appearance(HOST, {"gender": look["gender"], "skin": look["skin"], "hair": look["hair"],
                               "accessory": look["accessory"], "hair_color": look["hair_color"],
                               "eye_color": look["eye_color"], "shirt_color": look["worn"]["shirt"]["color"],
                               "hat": "H:54", "boots": "B:514"})
    assert (xmlio.serialize(save.main), xmlio.serialize(save.info)) == before


def test_changes_survive_writing_and_reading(save, data, tmp_path):
    save.set_appearance(FARMHAND, {"hat": "H:54", "hair_color": "#123456"}, data)
    save.write()
    again = SaveGame(tmp_path / "Test_1")
    assert again.appearance(FARMHAND)["worn"]["hat"]["name"] == "Floppy Beanie"
    assert again.appearance(FARMHAND)["hair_color"] == "#123456"
    assert b"<hat>" in xmlio.serialize(again.main)  # no stray namespace declarations


# ---------------------------------------------------------------------- icons
def test_clothes_icons(data):
    assert data.icon("H:54") == {"sheet": "Characters/Farmer/hats", "x": 54 % 12 * 20, "y": 54 // 12 * 80,
                                 "w": 20, "h": 20, "sheet_w": 240, "sheet_h": 1600}
    shirt = data.icon("S:1222")
    assert (shirt["x"], shirt["y"], shirt["w"]) == (222 % 16 * 8, 222 // 16 * 32, 8)
    assert data.icon("S:1222", dye_layer=True)["x"] == 222 % 16 * 8 + 128
    assert data.icon("S:1001", dye_layer=True) is None
    pants = data.icon("P:10")
    assert (pants["x"], pants["y"], pants["w"]) == (10 % 10 * 192, 10 // 10 * 688 + 672, 16)
    assert data.skin_icon(2)["x"] == 1 and data.skin_icon(2)["y"] == 2


def test_clothing_list_tells_same_names_apart(data):
    assert data.clothing("S", "en") == [("S:1222", "Gold Trimmed Shirt"), ("S:1000", "Shirt (1000)"),
                                        ("S:1001", "Shirt (1001)")]