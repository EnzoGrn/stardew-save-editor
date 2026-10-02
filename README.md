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
- Inventory: item quantity and quality, item names in your language (with game data)
- Friendship with each villager
- Automatic backup before every change, manual backups, restore

Backups are stored next to the `Saves` folder, in `SaveManagerBackups/<save>/`. The 30 most recent automatic backups are kept; manual backups are never deleted automatically.

## Game data

Some features need the game's own data: item names in your language now, and adding items, recipes, appearance and the museum later. The app reads it from your copy of the game, unpacked by [StardewXnbHack](https://github.com/Pathoschild/StardewXnbHack) (MIT licence). Without it, everything else keeps working.

On the home page, under **Game data**:

1. Check the game folder. The app looks for Steam, GOG and Game Pass installs; pick it yourself if it isn't found (the folder containing `Stardew Valley.dll`).
2. Click **Prepare game data**. The app downloads StardewXnbHack from its GitHub releases (about 30 MB, kept in the app's settings folder for next time), runs it in the game folder, and shows the progress. On Windows the unpacker opens its own window: press a key in it when it says *Done*.

The data is written to `Content (unpacked)` in the game folder. After a game update, the app notices and offers to prepare it again.

To do it by hand instead: download StardewXnbHack for your system from its [releases page](https://github.com/Pathoschild/StardewXnbHack/releases), unzip it into the game folder, run `StardewXnbHack.exe` (Windows) or `./StardewXnbHack` (macOS, Linux), then delete it once it's done.

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
web/                Flask UI
  app.py            routes
  i18n.py           translation; `python -m web.i18n` checks the language files
  locales/          one JSON file per language
  picker.py         native folder picker
  settings.py       remembered settings (folders, language)
  unpacker.py       one-click game data preparation, in the background
  templates/        HTML pages
  static/style.css
tests/              automated tests: `pip install pytest`, then `python -m pytest`
```

To add a feature: a method on `SaveGame` (reading + writing), a route in `web/app.py` that calls it through `edit(...)` (the backup is then automatic), and the form in the template. UI text is written `{{ t('my.key') }}` in templates and goes into every file in `web/locales/`; errors in the save logic raise `SaveError("error.my_key", param=...)`.