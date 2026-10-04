# Stardew Valley save manager

A local app (Python + your browser) to view and edit your Stardew Valley 1.6 saves.

## Installation

Requires Python 3.9 or later.

```
pip install -r requirements.txt
```

## Running

```
python run.py
```

Your browser opens at http://127.0.0.1:5173. The save folder is detected automatically:

- Windows: `%AppData%\StardewValley\Saves`
- macOS / Linux: `~/.config/StardewValley/Saves`

To use another folder, run `python run.py --saves "D:\MySaves"`, or pick it from the home page. The chosen folder is remembered.

**Always close the game before editing a save.** If the game rewrote the save while the page was open, the app refuses to write and asks you to reload.

## Features

- Save list and farm details (date, farm type, time played, game version, editable Golden Walnuts)
- Renaming the farm and each farmer (the save folder keeps its name: it's an internal identifier)
- Linked accounts: view and clear each farmer's `userID` (moving from Game Pass to Steam, changing accounts)
- Per player: gold, Qi Gems, casino coins, max energy and health, backpack size
- Skills, with an option to trigger the level-up screen (recipes and professions) the next time the farmer sleeps
- Inventory: item quantity and quality, item names in your language, and with game data: item icons, adding objects and machines (search by name), removing items, moving them by drag and drop, tool upgrade levels (basic to iridium)
- Recipes: learn or forget cooking and crafting recipes, all at once or one by one (with game data; without it, known recipes can be removed)
- Appearance: gender, skin, hairstyle, accessory, hair and eye colors, and the clothes worn (shirt, pants, hat, boots) with their dye colors; with game data, every choice shows the game's sprite, tinted like in the game, next to a full preview of the farmer drawn from the game's own sprites
- Calendar and weather: change the day, season and year (with the days played and the load screen date following), and tomorrow's weather in the valley and on Ginger Island
- Community Center: every bundle by room with what was given; complete a bundle (restoring the room when it's the last one, with what it unlocks) or reset one in a room not restored yet
- Animals: every farm animal by house; rename, change friendship (with hearts) and happiness, move to another coop or barn with room
- Chests: every container of the save (chests, big chests, fridges, mini-fridges, auto-grabbers…) by place, with its fill level; open one to change quantities and qualities, take items out (into a farmer's inventory or discarded) and, with game data, add items
- Museum: every donation on a plan of the museum's displays; move pieces by drag and drop, take one back (into a farmer's inventory or discarded), and with game data, donate straight from an inventory and see the missing pieces. Gunther's rewards already received are never touched
- Friendship with each villager
- Automatic backup before every change, manual backups, restore

Backups are stored next to the `Saves` folder, in `SaveManagerBackups/<save>/`. The 30 most recent automatic backups are kept; manual backups are never deleted automatically.

## Game data

Some features need the game's own data: item names and icons, adding items, tool upgrades, the full recipe list, changing clothes and the appearance previews, the museum's empty displays (read from its map), donating and the missing pieces. The app reads it from your copy of the game, unpacked by [StardewXnbHack](https://github.com/Pathoschild/StardewXnbHack) (MIT licence). Without it, everything else keeps working.

On the home page, under **Game data**:

1. Check the game folder. The app looks for Steam, GOG and Game Pass installs; pick it yourself if it isn't found (the folder containing `Stardew Valley.dll`).
2. Click **Prepare game data**. The app downloads StardewXnbHack and the few SMAPI files it needs from their GitHub releases (about 70 MB, kept in the app's settings folder for next time), runs it in the game folder, and shows the progress. On Windows the unpacker opens its own window: press a key in it when it says *Done*.

StardewXnbHack normally requires [SMAPI](https://smapi.io/), the mod loader. You don't need to install it: the app puts SMAPI's toolkit files in the game folder for the run only, then removes them. If SMAPI is already installed, the app uses it and leaves it untouched.

The data is written to `Content (unpacked)` in the game folder. After a game update, the app notices and offers to prepare it again.

To do it by hand instead: install [SMAPI](https://smapi.io/), download StardewXnbHack for your system from its [releases page](https://github.com/Pathoschild/StardewXnbHack/releases), unzip it into the game folder, run `StardewXnbHack.exe` (Windows) or `./StardewXnbHack` (macOS, Linux), then delete it once it's done.

## Languages

The UI is available in English and French. The switcher in the top-right corner changes the language, and the choice is remembered. Without a choice, the app follows the browser's language (English by default).

To add a language:

1. Copy `web/locales/en.json` to a file named after the language code, for example `de.json`.
2. Translate the values (not the keys). `_name` is the language name shown in the switcher, `_thousands` the thousands separator.
3. Run `python -m web.i18n`: it lists any missing keys.

The language shows up in the switcher on the next launch. Item names follow the UI language when game data is prepared; otherwise they are the ones stored in the save, which are always in English.

## Project layout

```
run.py              launcher
sdvsave/            save logic, with no dependency on the UI
  xmlio.py          XML reading/writing identical to the game's format
  savegame.py       a save (reading + editing)
  backup.py         backups
  paths.py          save locations, save list
  constants.py      game data (skills, seasons, qualities…), no display text
  errors.py         errors as translation keys
  gamedata.py       item catalogue and translated names, from the unpacked game
  gamefolder.py     finding the game install, state of its unpacked data
  items.py          building new items and upgrading tools, in the game's own format
  appearance.py     a farmer's look: colors and worn clothes, in the game's own format
web/                Flask UI
  app.py            routes
  i18n.py           translation; `python -m web.i18n` checks the language files
  locales/          one JSON file per language
  picker.py         native folder picker
  settings.py       remembered settings (folders, language)
  unpacker.py       one-click game data preparation, in the background
  templates/        HTML pages
  static/style.css
  static/items.js   item icons and the add-item search, shared by the inventory and chests
  static/farmer.js  full farmer preview, layering the game's sprites like the game does
tests/              automated tests: `pip install pytest`, then `python -m pytest`
```

To add a feature: a method on `SaveGame` (reading + writing), a route in `web/app.py` that calls it through `edit(...)` (the backup is then automatic), and the form in the template. UI text is written `{{ t('my.key') }}` in templates and goes into every file in `web/locales/`; errors in the save logic raise `SaveError("error.my_key", param=...)`.