"""Shared fixtures: a fake game folder in StardewXnbHack's output format.

A handful of made-up entries mimic the real files; no game file is included.
"""
import json
import struct

import pytest


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
        "330": {"Name": "Clay", "DisplayName": "[LocalizedText Strings\\Objects:Clay_Name]",
                "Type": "Basic", "Category": -16, "Price": 20, "SpriteIndex": 330},
        "72": {"Name": "Diamond", "DisplayName": "[LocalizedText Strings\\Objects:Diamond_Name]",
               "Type": "Minerals", "Category": -2, "Price": 750, "SpriteIndex": 72},
        "Moss": {"Name": "Moss", "DisplayName": "[LocalizedText Strings\\Objects:Moss_Name]",
                 "Type": "Basic", "Category": -16, "Price": 5, "Texture": "TileSheets\\Objects_2",
                 "SpriteIndex": 38},
        "194": {"Name": "Fried Egg", "DisplayName": "[LocalizedText Strings\\Objects:FriedEgg_Name]",
                "Type": "Cooking", "Category": -7, "SpriteIndex": 194},
        "322": {"Name": "Wood Fence", "DisplayName": "[LocalizedText Strings\\Objects:WoodFence_Name]",
                "Type": "Crafting", "Category": -8, "SpriteIndex": 322},
        "495": {"Name": "Spring Seeds", "DisplayName": "[LocalizedText Strings\\Objects:SpringSeeds_Name]",
                "Type": "Seeds", "Category": -74, "SpriteIndex": 495},
        "516": {"Name": "Small Glow Ring", "DisplayName": "[LocalizedText Strings\\Objects:SmallGlowRing_Name]",
                "Type": "Ring", "Category": -96, "SpriteIndex": 516},
        "24": {"Name": "Parsnip", "DisplayName": "[LocalizedText Strings\\Objects:Parsnip_Name]"},
        "348": {"Name": "Wine", "DisplayName": "[LocalizedText Strings\\Objects:Wine_Name]"},
        "999": {"Name": "Mystery", "DisplayName": "[LocalizedText Strings\\Objects:Missing_Name]"},
        "96": {"Name": "Dwarf Scroll I", "Type": "Arch", "Category": 0, "Price": 1, "SpriteIndex": 96},
        "97": {"Name": "Dwarf Scroll II", "Type": "Arch", "Category": 0, "Price": 1, "SpriteIndex": 97},
        "80": {"Name": "Quartz", "Type": "Minerals", "Category": -2, "Price": 25, "SpriteIndex": 80},
        "Fake": {"Name": "Display Only", "Type": "Arch", "ContextTags": ["not_museum_donatable"]},
    })
    write_json(data / "Data" / "CookingRecipes.json", {
        "Fried Egg": "-5 1/10 10/194/default/",
        "Strange Bun": "246 1 731 1/1 10/731/none/",
    })
    write_json(data / "Data" / "CraftingRecipes.json", {
        "Wood Fence": "388 2/Field/322/false/l 0/",
        "Scarecrow": "388 50 382 1 771 20/Home/8/true/Farming 1/",
        "Wild Seeds (Sp)": "16 1 18 1/Field/495 10/false/Foraging 1/[LocalizedText Strings\\Objects:WildSeedsSp]",
    })
    write_json(data / "Data" / "BigCraftables.json", {
        "130": {"Name": "Chest", "DisplayName": "[LocalizedText Strings\\BigCraftables:Chest_Name]"},
        "8": {"Name": "Scarecrow", "DisplayName": "[LocalizedText Strings\\BigCraftables:Scarecrow_Name]",
              "Price": 50, "SpriteIndex": 8, "CanBePlacedIndoors": False},
    })
    write_json(data / "Data" / "Tools.json", {
        "Axe": {"Name": "Axe", "DisplayName": "[LocalizedText Strings\\Tools:Axe_Name]",
                "ClassName": "Axe", "UpgradeLevel": 0, "SpriteIndex": 189, "MenuSpriteIndex": 215},
        "CopperAxe": {"Name": "Copper Axe", "ClassName": "Axe", "UpgradeLevel": 1,
                      "SpriteIndex": 196, "MenuSpriteIndex": 222},
        "GoldAxe": {"Name": "Gold Axe", "ClassName": "Axe", "UpgradeLevel": 3,
                    "SpriteIndex": 231, "MenuSpriteIndex": 257},
        "WateringCan": {"Name": "Watering Can", "ClassName": "WateringCan", "UpgradeLevel": 0,
                        "SpriteIndex": 273, "MenuSpriteIndex": 296},
        "IridiumWateringCan": {"Name": "Iridium Watering Can", "ClassName": "WateringCan",
                               "UpgradeLevel": 4, "SpriteIndex": 322, "MenuSpriteIndex": 345},
        "BambooPole": {"Name": "Bamboo Pole", "ClassName": "FishingRod", "UpgradeLevel": 0},
        "TrainingRod": {"Name": "Training Rod", "ClassName": "FishingRod", "UpgradeLevel": 1},
    })
    write_json(data / "Data" / "Weapons.json", {
        "47": {"Name": "Scythe", "DisplayName": "[LocalizedText Strings\\Weapons:Scythe_Name]"},
    })
    write_json(data / "Data" / "Pants.json", {
        "0": {"Name": "Farmer Pants", "DisplayName": "[LocalizedText Strings\\Pants:FarmerPants_Name]",
              "Price": 50, "SpriteIndex": 0, "DefaultColor": "255 235 203", "CanBeDyed": True},
        "10": {"Name": "Baggy Pants", "Price": 50, "SpriteIndex": 10, "CanBeDyed": False,
               "DefaultColor": "105 105 105"},
    })
    write_json(data / "Data" / "Shirts.json", {
        "1000": {"Name": "Shirt", "Price": 50, "SpriteIndex": 0, "CanBeDyed": True},
        "1001": {"Name": "Shirt", "Price": 50, "SpriteIndex": 1},
        "1222": {"Name": "Gold Trimmed Shirt", "Price": 80, "SpriteIndex": 222, "CanBeDyed": True,
                 "DefaultColor": "220 0 0"},
    })
    write_json(data / "Data" / "Boots.json", {
        "504": "Sneakers/A little flimsy./50/1/0/0/Sneakers",
        "514": "Space Boots/Out of this world./450/4/4/10/Space Boots",
        "878": "Crystal Shoes/Shiny./0/3/3/12/Crystal Shoes/Characters\\Farmer\\shoeColors/42/TileSheets\\Objects_2"})
    write_json(data / "Data" / "Boots.fr-FR.json", {"504": "Sneakers/Un peu fragiles./50/1/0/0/Baskets"})
    write_json(data / "Data" / "hats.json", {
        "0": "Cowboy Hat/Yeehaw./false/true//Cowboy Hat",
        "54": "Floppy Beanie/Cozy./false/true//Floppy Beanie",  # as in the game
        "13": "Bowler Hat/Classy./true/false/Prismatic/Bowler Hat",
    })
    write_json(data / "Data" / "HairData.json", {  # texture/tile x/tile y/unique left/covered/bald
        "100": "hairstyles2/0/0/true/-1/false",
        "101": "hairstyles2/1/0/true/-101/true",
        "-101": "hairstyles2/2/16/true/-1/false",
    })
    write_json(data / "Strings" / "Objects.json", {
        "Clay_Name": "Clay", "Parsnip_Name": "Parsnip", "Wine_Name": "Wine", "Diamond_Name": "Diamond",
        "Moss_Name": "Moss",
        "Wine_Flavored_Name": "{0} Wine"})
    write_json(data / "Strings" / "Objects.fr-FR.json", {
        "Clay_Name": "Argile", "Parsnip_Name": "Panais", "Wine_Name": "Vin", "Diamond_Name": "Diamant",
        "Moss_Name": "Mousse", "FriedEgg_Name": "Œuf au plat", "WoodFence_Name": "Clôture en bois",
        "SpringSeeds_Name": "Graines de printemps", "WildSeedsSp": "Graines sauvages (Pr)",
        "Wine_Flavored_Name": "Vin de {0}"})
    write_json(data / "Strings" / "Objects.pt-BR.json", {"Clay_Name": "Argila"})
    write_json(data / "Strings" / "BigCraftables.json", {"Chest_Name": "Chest"})
    write_json(data / "Strings" / "Tools.json", {"Axe_Name": "Axe"})
    write_json(data / "Strings" / "Tools.fr-FR.json", {"Axe_Name": "Hache"})
    write_json(data / "Strings" / "Weapons.fr-FR.json", {"Scythe_Name": "Faux"})
    write_json(data / "Strings" / "Weapons.json", {"Scythe_Name": "Scythe"})
    write_json(data / "Strings" / "Pants.json", {"FarmerPants_Name": "Farmer Pants"})
    # Sprite sheets: only the PNG header matters (width and height)
    for sheet, (w, h) in {"Maps/springobjects": (384, 624), "TileSheets/Objects_2": (128, 160),
                          "TileSheets/tools": (336, 384), "TileSheets/Craftables": (128, 1152),
                          "Characters/Farmer/hats": (240, 1600), "Characters/Farmer/shirts": (256, 608),
                          "Characters/Farmer/pants": (1920, 1376), "Characters/Farmer/hairstyles": (128, 672),
                          "Characters/Farmer/hairstyles2": (128, 672), "Characters/Farmer/accessories": (128, 128),
                          "Characters/Farmer/skinColors": (3, 24)}.items():
        png = data.joinpath(*sheet.split("/")).with_suffix(".png")
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sII", 13, b"IHDR", w, h) + b"\0" * 5)
    return game