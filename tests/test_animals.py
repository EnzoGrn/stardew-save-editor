"""Farm animals: names, friendship, happiness, moving between houses.

Like real 1.6 saves, each house writes its animals twice (<animals> and <Animals>)
and lists them in <animalsThatLiveHere>. The mini-save has two coops (the second
one full) and a barn.
"""
import pytest

from sdvsave import SaveError, SaveGame, xmlio

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def animal(animal_id, name, kind="White Chicken", lives_in="Coop", x=100, y=200):
    return (f"<item><key><long>{animal_id}</long></key><value><FarmAnimal><name>{name}</name>"
            f"<Position><X>{x}</X><Y>{y}</Y></Position><friendshipTowardFarmer>300</friendshipTowardFarmer>"
            f"<age>10</age><happiness>200</happiness><type>{kind}</type>"
            f"<buildingTypeILiveIn>{lives_in}</buildingTypeILiveIn><myID>{animal_id}</myID>"
            f"<ownerID>-123</ownerID><displayName>{name}</displayName></FarmAnimal></value></item>")


def house(building_type, unique, animals, capacity=4, x=0):
    ids = "".join(f"<long>{a[0]}</long>" for a in animals)
    entries = "".join(animal(*a) for a in animals)
    return (f"<Building><indoors xsi:type=\"AnimalHouse\"><animals>{entries}</animals>"
            f"<name>{building_type.split()[-1]}</name><uniqueName>{unique}</uniqueName>"
            f"<animalsThatLiveHere>{ids}</animalsThatLiveHere>"
            f"<Animals><SerializableDictionaryOfInt64FarmAnimal>{entries}</SerializableDictionaryOfInt64FarmAnimal></Animals>"
            f"</indoors><tileX>{x}</tileX><tileY>0</tileY><maxOccupants>{capacity}</maxOccupants>"
            f"<currentOccupants>{len(animals)}</currentOccupants><buildingType>{building_type}</buildingType></Building>")


def write_save(folder):
    folder.mkdir()
    farmer = "<name>Host</name><UniqueMultiplayerID>-123</UniqueMultiplayerID>"
    buildings = (house("Coop", "Coop1", [("1", "Cluck"), ("2", "Peep", "Duck")])
                 + house("Big Coop", "Coop2", [("3", "Full1", "White Chicken", "Coop", 640, 320),
                                              ("4", "Full2")], capacity=2, x=10)
                 + house("Deluxe Barn", "Barn1", [("5", "Bessie", "White Cow", "Barn")], capacity=12, x=20)
                 + house("Big Coop", "Coop3", [], capacity=8, x=30))
    (folder / folder.name).write_text(
        f'<SaveGame xmlns:xsi="{XSI_NS}"><player>{farmer}</player><locations><GameLocation><name>Farm</name>'
        f"<animals /><buildings>{buildings}</buildings></GameLocation></locations><farmhands /></SaveGame>",
        encoding="utf-8")
    (folder / "SaveGameInfo").write_text(f'<Farmer xmlns:xsi="{XSI_NS}">{farmer}</Farmer>', encoding="utf-8")
    return folder


@pytest.fixture
def save(tmp_path):
    return SaveGame(write_save(tmp_path / "Test_1"))


def residents(save, key):
    """Animal ids of a house, in its three lists (both copies and the residents list)."""
    location = next(loc for k, loc, _ in save._locations() if k == key)
    return ([i.findtext("key/long") for i in location.find("animals")],
            [i.findtext("key/long") for i in location.find("Animals/SerializableDictionaryOfInt64FarmAnimal")],
            [n.text for n in location.find("animalsThatLiveHere")])


def building_of(save, key):
    return next(b for k, _, b in save._locations() if k == key)


# ---------------------------------------------------------------------- reading
def test_animals_and_houses(save):
    animals = {a["id"]: a for a in save.animals()}
    assert sorted(animals) == ["1", "2", "3", "4", "5"]
    assert (animals["1"]["name"], animals["1"]["friendship"], animals["1"]["happiness"]) == ("Cluck", 300, 200)
    assert animals["1"]["owner"] == "Host" and animals["5"]["lives_in"] == "Barn"
    homes = {h["key"]: h for h in save.animal_homes()}
    assert (homes["Coop2"]["kind"], homes["Coop2"]["count"], homes["Coop2"]["capacity"]) == ("Coop", 2, 2)
    assert homes["Coop3"]["kind"] == "Coop"   # empty: kind from the building type


# ---------------------------------------------------------------------- editing
def test_rename_and_stats_in_both_copies(save):
    save.set_animals({"1": {"name": "Henrietta", "friendship": "1000", "happiness": "255"}})
    location = next(loc for k, loc, _ in save._locations() if k == "Coop1")
    for copy in (location.find("animals")[0], location.find("Animals/SerializableDictionaryOfInt64FarmAnimal")[0]):
        a = copy.find("value/FarmAnimal")
        assert (a.findtext("name"), a.findtext("displayName")) == ("Henrietta", "Henrietta")
        assert (a.findtext("friendshipTowardFarmer"), a.findtext("happiness")) == ("1000", "255")


@pytest.mark.parametrize("change, key", [
    ({"friendship": "1001"}, "error.out_of_range"),
    ({"happiness": "-1"}, "error.out_of_range"),
    ({"name": "  "}, "error.name_empty"),
    ({"name": "<b>"}, "error.name_forbidden"),
])
def test_invalid_values_are_refused(save, change, key):
    with pytest.raises(SaveError) as error:
        save.set_animals({"1": change})
    assert error.value.key == key


# ---------------------------------------------------------------------- moving
def test_move_to_another_coop_updates_every_list(save):
    save.move_animal("2", "Coop3")
    assert residents(save, "Coop1") == (["1"], ["1"], ["1"])
    assert residents(save, "Coop3") == (["2"], ["2"], ["2"])
    assert building_of(save, "Coop1").findtext("currentOccupants") == "1"
    assert building_of(save, "Coop3").findtext("currentOccupants") == "1"
    assert {a["id"]: a["home"] for a in save.animals()}["2"] == "Coop3"


def test_moved_animal_takes_a_resident_position(save):
    save.move_animal("4", "Coop1")  # Coop1 has residents: their spot is used
    location = next(loc for k, loc, _ in save._locations() if k == "Coop1")
    moved = [i for i in location.find("animals") if i.findtext("key/long") == "4"][0]
    assert (moved.findtext("value/FarmAnimal/Position/X"), moved.findtext("value/FarmAnimal/Position/Y")) == ("100", "200")


@pytest.mark.parametrize("animal_id, target, key", [
    ("1", "Barn1", "error.wrong_animal_home"),   # a chicken in a barn
    ("1", "Coop2", "error.animal_home_full"),
    ("1", "Nowhere", "error.no_animal_home"),
    ("99", "Coop3", "error.no_animal"),
])
def test_moves_that_are_refused(save, animal_id, target, key):
    with pytest.raises(SaveError) as error:
        save.move_animal(animal_id, target)
    assert error.value.key == key


def test_animal_changes_survive_writing_and_reading(save, tmp_path):
    save.move_animal("2", "Coop3")
    save.set_animals({"5": {"name": "Daisy"}})
    save.write()
    again = SaveGame(tmp_path / "Test_1")
    assert {a["id"]: (a["name"], a["home"]) for a in again.animals()}["5"] == ("Daisy", "Barn1")
    assert residents(again, "Coop3") == (["2"], ["2"], ["2"])
    assert b"<animalsThatLiveHere><long>2</long></animalsThatLiveHere>" in xmlio.serialize(again.main)