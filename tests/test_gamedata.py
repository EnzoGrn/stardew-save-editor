"""Game data: reading the unpacked catalogue and resolving translated names.

The fixtures mimic StardewXnbHack's output format with a handful of made-up
entries; no game file is included.
"""
import os
import time

import pytest
from lxml import etree

from sdvsave import gamefolder
from sdvsave.gamedata import GameData, find_data_dir

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


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
    (item("Slingshot", "0"), None),        # known class missing from its catalogue: not hat 0
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