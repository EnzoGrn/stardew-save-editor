"""Wallet: special items and powers (Data/Powers.json) given or taken back.

The mini-save has a host and a farmhand; conditions point at mail flags (the
farmer's or the host's), events seen and stats.
"""
import json

import pytest

from sdvsave import SaveGame
from sdvsave.gamedata import GameData

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
HOST, HAND = "-123", "456"

POWERS = {
    "RustyKey": {"DisplayName": "[LocalizedText Strings\\Objects:Diamond_Name]", "TexturePath": "LooseSprites\\Cursors",
                 "TexturePosition": {"X": 144, "Y": 320}, "UnlockedCondition": "PLAYER_HAS_MAIL Host HasRustyKey"},
    "ClubCard": {"DisplayName": "", "TexturePath": "LooseSprites\\Cursors", "TexturePosition": {"X": 160, "Y": 320},
                 "UnlockedCondition": "PLAYER_HAS_MAIL Current HasClubCard"},
    "BearPaw": {"DisplayName": "", "TexturePath": "LooseSprites\\Cursors", "TexturePosition": {"X": 192, "Y": 336},
                "UnlockedCondition": "PLAYER_HAS_SEEN_EVENT Current 2120303"},
    "Book_Void": {"DisplayName": "", "TexturePath": "TileSheets\\Objects_2", "TexturePosition": {"X": 96, "Y": 208},
                  "UnlockedCondition": "PLAYER_STAT Current Book_Void 1"},
    "ModPower": {"DisplayName": "", "TexturePath": "Mods\\Nowhere", "UnlockedCondition": "SOMETHING_ELSE x"},
}


def farmer(uid, mail, events, stats):
    return (f"<name>F{uid}</name><mailReceived>{''.join(f'<string>{m}</string>' for m in mail)}</mailReceived>"
            f"<eventsSeen>{''.join(f'<int>{e}</int>' for e in events)}</eventsSeen><stats><Values>"
            + "".join(f"<item><key><string>{k}</string></key><value><unsignedInt>{v}</unsignedInt></value></item>"
                      for k, v in stats.items())
            + f"</Values></stats><UniqueMultiplayerID>{uid}</UniqueMultiplayerID>")


def write_save(folder):
    folder.mkdir()
    host = farmer(HOST, ["HasRustyKey"], [2120303], {"Book_Void": 1})
    (folder / folder.name).write_text(
        f'<SaveGame xmlns:xsi="{XSI_NS}"><player>{host}</player>'
        f"<farmhands><Farmer>{farmer(HAND, [], [], {})}</Farmer></farmhands></SaveGame>", encoding="utf-8")
    (folder / "SaveGameInfo").write_text(f'<Farmer xmlns:xsi="{XSI_NS}">{host}</Farmer>', encoding="utf-8")
    return folder


@pytest.fixture
def save(tmp_path):
    return SaveGame(write_save(tmp_path / "Test_1"))


@pytest.fixture
def data(game):
    (game / "Content (unpacked)" / "Data" / "Powers.json").write_text(json.dumps(POWERS), encoding="utf-8")
    return GameData.load(game)


def conditions(data):
    return {p["id"]: p["condition"] for p in data.powers("en")}


def test_powers_from_the_game_data(data):
    powers = {p["id"]: p for p in data.powers("fr")}
    assert powers["RustyKey"]["name"] == "Diamant"                 # translated name
    assert powers["ClubCard"]["name"] == "Club Card"               # no text: a name made from the id
    assert powers["RustyKey"]["icon"]["sheet"] == "LooseSprites/Cursors" and powers["RustyKey"]["icon"]["w"] == 16
    assert (powers["Book_Void"]["group"], powers["RustyKey"]["group"]) == ("book", "item")
    assert powers["RustyKey"]["condition"] == ("mail", "Host", "HasRustyKey", 1)
    assert powers["ModPower"]["condition"] is None and powers["ModPower"]["icon"] is None


def test_what_each_farmer_owns(save, data):
    c = conditions(data)
    assert [save.has_power(HOST, c[k]) for k in ("RustyKey", "ClubCard", "BearPaw", "Book_Void")] == [True, False, True, True]
    # The rusty key is the host's: the farmhand has it too; the rest is their own
    assert [save.has_power(HAND, c[k]) for k in ("RustyKey", "ClubCard", "BearPaw", "Book_Void")] == [True, False, False, False]


def test_give_and_take_in_both_files(save, data):
    c = conditions(data)
    assert save.set_power(HOST, c["ClubCard"], True) and save.set_power(HOST, c["Book_Void"], False)
    assert save.set_power(HOST, c["BearPaw"], False)
    for copy in save._copies(HOST):
        assert [m.text for m in copy.find("mailReceived")] == ["HasRustyKey", "HasClubCard"]
        assert len(copy.find("eventsSeen")) == 0 and save._stat_entry(copy, "Book_Void") is None
    assert not save.set_power(HOST, c["ClubCard"], True)   # already owned: nothing to do


def test_farmhand_changing_a_host_power_changes_the_host(save, data):
    save.set_power(HAND, conditions(data)["RustyKey"], False)
    assert not save.has_power(HOST, conditions(data)["RustyKey"])
    save.set_power(HAND, conditions(data)["Book_Void"], True)
    assert save._stat_entry(save._player(HAND), "Book_Void").findtext("value/unsignedInt") == "1"