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
- Inventory: item quantity and quality
- Friendship with each villager
- Automatic backup before every change, manual backups, restore

Backups are stored next to the `Saves` folder, in `SaveManagerBackups/<save>/`. The 30 most recent automatic backups are kept; manual backups are never deleted automatically.

## Languages

The UI is available in English and French. The switcher in the top-right corner changes the language, and the choice is remembered. Without a choice, the app follows the browser's language (English by default).

To add a language:

1. Copy `web/locales/en.json` to a file named after the language code, for example `de.json`.
2. Translate the values (not the keys). `_name` is the language name shown in the switcher, `_thousands` the thousands separator.
3. Run `python -m web.i18n`: it lists any missing keys.

The language shows up in the switcher on the next launch. Item and villager names are the ones stored in the save, which are always in English.

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
web/                Flask UI
  app.py            routes
  i18n.py           translation; `python -m web.i18n` checks the language files
  locales/          one JSON file per language
  picker.py         native folder picker
  settings.py       remembered settings (folder, language)
  templates/        HTML pages
  static/style.css
```

To add a feature: a method on `SaveGame` (reading + writing), a route in `web/app.py` that calls it through `edit(...)` (the backup is then automatic), and the form in the template. UI text is written `{{ t('my.key') }}` in templates and goes into every file in `web/locales/`; errors in the save logic raise `SaveError("error.my_key", param=...)`.
