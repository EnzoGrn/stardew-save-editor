"""Fixed game data used by the app.

Identifiers only: display names live in the UI translation files
(web/locales/), under keys such as "season.spring".
"""

XSI = "{http://www.w3.org/2001/XMLSchema-instance}"

# Order of the <experiencePoints> array in the save
SKILLS = [
    # (index, level tag, identifier → translation key "skill.<id>")
    (0, "farmingLevel", "farming"),
    (1, "fishingLevel", "fishing"),
    (2, "foragingLevel", "foraging"),
    (3, "miningLevel", "mining"),
    (4, "combatLevel", "combat"),
    (5, "luckLevel", "luck"),
]

# Minimum experience for each level (0 to 10)
XP_FOR_LEVEL = [0, 100, 380, 770, 1300, 2150, 3300, 4800, 6900, 10000, 15000]

# Order used by <seasonForSaveGame> (0 to 3); keys "season.<id>"
SEASONS = ["spring", "summer", "fall", "winter"]

# Values of <quality> (the stars on crops, fish, animal products…); keys "quality.<value>"
# 0 = normal, 1 = silver, 2 = gold, 4 = iridium. The game never uses 3.
# Not to be confused with a tool's <upgradeLevel> (basic, copper, steel, gold, iridium).
QUALITIES = [0, 1, 2, 4]

# Values of <whichFarm>; keys "farm_type.<value>"
FARM_TYPES = ["0", "1", "2", "3", "4", "5", "6", "7"]

POINTS_PER_HEART = 250
MAX_FRIENDSHIP_POINTS = 3750  # 14 hearts (spouse)

BACKPACK_SIZES = [12, 24, 36]