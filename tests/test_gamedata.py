"""Game data: reading the unpacked catalogue and resolving translated names.

The fixtures mimic StardewXnbHack's output format with a handful of made-up
entries; no game file is included.
"""
import json
import os
import time

import pytest
from lxml import etree

from sdvsave import gamefolder
from sdvsave.gamedata import GameData, find_data_dir

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def game(tmp_path):
    """A fake game folder with packed content and an unpacked copy."""
    game = tmp_path / "Stardew Valley"
    (game / "Content" / "Data").mkdir(parents=True)
    (game / "Content" / "Data" / "Objects.xnb").write_bytes(b"xnb")
    (game / "Stardew Valley.dll").write_bytes(b"dll")
    data = game / "Content (unpacked)"
    write_json(data / "Data" / "Objects.json", {
        "330": {"Name": "Clay", "DisplayName": "[LocalizedText Strings\\Objects:Clay_Name]"},
        "24": {"Name": "Parsnip", "DisplayName": "[LocalizedText Strings\\Objects:Parsnip_Name]"},
        "348": {"Name": "Wine", "DisplayName": "[LocalizedText Strings\\Objects:Wine_Name]"},
        "999": {"Name": "Mystery", "DisplayName": "[LocalizedText Strings\\Objects:Missing_Name]"},
    })
    write_json(data / "Data" / "BigCraftables.json", {
        "130": {"Name": "Chest", "DisplayName": "[LocalizedText Strings\\BigCraftables:Chest_Name]"},
    })
    write_json(data / "Data" / "Tools.json", {
        "Axe": {"Name": "Axe", "DisplayName": "[LocalizedText Strings\\Tools:Axe_Name]"},
    })
    write_json(data / "Data" / "Weapons.json", {
        "47": {"Name": "Scythe", "DisplayName": "[LocalizedText Strings\\Weapons:Scythe_Name]"},
    })
    write_json(data / "Data" / "Pants.json", {
        "0": {"Name": "Farmer Pants", "DisplayName": "[LocalizedText Strings\\Pants:FarmerPants_Name]"},
    })
    write_json(data / "Data" / "Boots.json", {"504": "Sneakers/A little flimsy./50/1/0/0/Sneakers"})
    write_json(data / "Data" / "Boots.fr-FR.json", {"504": "Sneakers/Un peu fragiles./50/1/0/0/Baskets"})
    write_json(data / "Data" / "hats.json", {"0": "Cowboy Hat/Yeehaw./false/true//Cowboy Hat"})
    write_json(data / "Strings" / "Objects.json", {
        "Clay_Name": "Clay", "Parsnip_Name": "Parsnip", "Wine_Name": "Wine",
        "Wine_Flavored_Name": "{0} Wine"})
    write_json(data / "Strings" / "Objects.fr-FR.json", {
        "Clay_Name": "Argile", "Parsnip_Name": "Panais", "Wine_Name": "Vin",
        "Wine_Flavored_Name": "Vin de {0}"})
    write_json(data / "Strings" / "Objects.pt-BR.json", {"Clay_Name": "Argila"})
    write_json(data / "Strings" / "BigCraftables.json", {"Chest_Name": "Chest"})
    write_json(data / "Strings" / "Tools.json", {"Axe_Name": "Axe"})
    write_json(data / "Strings" / "Tools.fr-FR.json", {"Axe_Name": "Hache"})
    write_json(data / "Strings" / "Weapons.fr-FR.json", {"Scythe_Name": "Faux"})
    write_json(data / "Strings" / "Weapons.json", {"Scythe_Name": "Scythe"})
    write_json(data / "Strings" / "Pants.json", {"FarmerPants_Name": "Farmer Pants"})
    return game


def item(kind, item_id, **tags):
    """A save item element, as the game writes it."""
    root = etree.fromstring(f'<Item xmlns:xsi="{XSI_NS}" xsi:type="{kind}"/>')
    etree.SubElement(root, "itemId").text = item_id
    for tag, value in tags.items():
        etree.SubElement(root, tag).text = value
    return root


# ---------------------------------------------------------------------- catalogue
def test_find_data_dir_accepts_game_or_unpacked_folder(game):
    assert find_data_dir(game) == game / "Content (unpacked)"
    assert find_data_dir(game / "Content (unpacked)") == game / "Content (unpacked)"
    assert find_data_dir(game / "Content") is None
    assert GameData.load(game.parent) is None


def test_languages_are_read_from_strings_files(game):
    assert GameData.load(game).languages == {"fr": "fr-FR", "pt": "pt-BR"}


def test_display_names_follow_the_language(game):
    data = GameData.load(game)
    assert data.display_name("O:330", "fr") == "Argile"
    assert data.display_name("O:330", "en") == "Clay"
    assert data.display_name("O:330", "pt") == "Argila"
    assert data.display_name("O:330", "de") == "Clay"  # no German strings: English


def test_missing_translation_falls_back_to_english_then_internal_name(game):
    data = GameData.load(game)
    assert data.display_name("BC:130", "fr") == "Chest"   # no French file for it
    assert data.display_name("O:999", "fr") == "Mystery"  # token points nowhere
    assert data.display_name("O:12345", "fr") is None     # unknown item


def test_slash_data_uses_localized_data_file(game):
    data = GameData.load(game)
    assert data.display_name("B:504", "fr") == "Baskets"
    assert data.display_name("B:504", "en") == "Sneakers"
    assert data.display_name("H:0", "fr") == "Cowboy Hat"  # plain name, no translation


# ---------------------------------------------------------------------- save items
@pytest.mark.parametrize("element, expected", [
    (item("Object", "330"), "O:330"),
    (item("Object", "130", bigCraftable="true"), "BC:130"),
    (item("Axe", "Axe"), "T:Axe"),
    (item("MeleeWeapon", "47"), "W:47"),
    (item("Boots", "504"), "B:504"),
    (item("Clothing", "0", clothesType="PANTS"), "P:0"),
    (item("SomeModType", "47"), "W:47"),   # unknown class: searched everywhere
    (item("Object", "4242"), None),
])
def test_qualified_id_of_save_items(game, element, expected):
    assert GameData.load(game).qualified_id(element) == expected


def test_item_name_of_save_items(game):
    data = GameData.load(game)
    assert data.item_name(item("Axe", "Axe"), "fr") == "Hache"
    assert data.item_name(item("MeleeWeapon", "47"), "fr") == "Faux"
    assert data.item_name(item("Object", "4242"), "fr") is None


def test_flavored_items_use_the_game_format(game):
    data = GameData.load(game)
    wine = item("Object", "348", preserve="Wine", preservedParentSheetIndex="24")
    assert data.item_name(wine, "fr") == "Vin de Panais"
    assert data.item_name(wine, "en") == "Parsnip Wine"
    qualified = item("Object", "348", preserve="Wine", preservedParentSheetIndex="(O)24")
    assert data.item_name(qualified, "fr") == "Vin de Panais"
    unknown_parent = item("Object", "348", preserve="Wine", preservedParentSheetIndex="777")
    assert data.item_name(unknown_parent, "fr") is None  # the save's own name is kept


# ---------------------------------------------------------------------- game folder
def test_resolve_game_dir_from_folders_people_pick(game):
    assert gamefolder.resolve_game_dir(game) == game
    assert gamefolder.resolve_game_dir(game / "Content") == game
    assert gamefolder.resolve_game_dir(game / "Content (unpacked)") == game
    assert gamefolder.resolve_game_dir(game.parent / "elsewhere") is None


def test_resolve_game_dir_macos_bundle(tmp_path):
    macos = tmp_path / "Stardew Valley.app" / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    (macos / "Stardew Valley.dll").write_bytes(b"dll")
    (tmp_path / "Stardew Valley.app" / "Contents" / "Resources" / "Content").mkdir(parents=True)
    assert gamefolder.resolve_game_dir(tmp_path / "Stardew Valley.app") == macos
    assert gamefolder.resolve_game_dir(tmp_path) == macos


def test_data_status(game, tmp_path):
    assert gamefolder.data_status(None) == gamefolder.NO_GAME
    assert gamefolder.data_status(tmp_path) == gamefolder.NO_GAME
    assert gamefolder.data_status(game) == gamefolder.READY

    later = time.time() + 3600  # the game is updated after the unpack
    os.utime(game / "Stardew Valley.dll", (later, later))
    assert gamefolder.data_status(game) == gamefolder.OUTDATED

    (game / "Content (unpacked)" / "Data" / "Objects.json").unlink()
    assert gamefolder.data_status(game) == gamefolder.MISSING