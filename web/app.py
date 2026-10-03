"""Local web UI of the save manager."""
import re
from pathlib import Path

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request,
                   send_file, url_for)

from sdvsave import SaveGame, SaveError, backup, default_saves_dir, gamefolder, list_saves
from sdvsave.constants import QUALITIES, POINTS_PER_HEART, MAX_FRIENDSHIP_POINTS, BACKPACK_SIZES
from sdvsave import appearance, items
from sdvsave.constants import XSI
from sdvsave.gamedata import GameData, find_data_dir
from sdvsave.errors import T
from sdvsave.savegame import bounded
from sdvsave.paths import backups_root, is_save_folder

from . import i18n, picker, settings, unpacker

app = Flask(__name__)
app.secret_key = "stardew-save-manager-local"


def initial_saves_dir():
    """The last chosen folder if it still exists, otherwise the game's standard location."""
    remembered = settings.load().get("saves_dir")
    if remembered and Path(remembered).is_dir():
        return remembered
    return str(default_saves_dir())


def initial_game_dir():
    """The remembered game folder if it is still valid, otherwise one found on disk."""
    remembered = settings.load().get("game_dir")
    if remembered and gamefolder.is_game_dir(remembered):
        return remembered
    detected = gamefolder.detect_game_dir()
    return str(detected) if detected else None


app.config["SAVES_DIR"] = initial_saves_dir()
app.config["GAME_DIR"] = initial_game_dir()

unpack_job = unpacker.Job()
_game_data_cache = {"key": None, "data": None}


# --------------------------------------------------------------------- language
def current_lang():
    """The language chosen in the app, otherwise the browser's."""
    if "lang" not in g:
        chosen = settings.load().get("language")
        g.lang = chosen if chosen in i18n.languages() else i18n.best_match(request.accept_languages)
    return g.lang


def t(key, **params):
    return i18n.translate(current_lang(), key, **params)


@app.context_processor
def globals_():
    return {
        "t": t, "lang": current_lang(), "languages": i18n.languages(),
        "QUALITIES": QUALITIES, "POINTS_PER_HEART": POINTS_PER_HEART,
        "MAX_POINTS": MAX_FRIENDSHIP_POINTS, "BACKPACK_SIZES": BACKPACK_SIZES,
    }


@app.template_filter("gold")
def gold(n):
    return i18n.format_number(current_lang(), n)


@app.template_filter("duration")
def duration(ms):
    minutes = int(ms) // 60000
    return t("format.duration", h=minutes // 60, m=minutes % 60)


@app.post("/language")
def set_language():
    lang = request.form.get("lang")
    if lang in i18n.languages():
        settings.save(language=lang)
    return redirect(request.referrer or url_for("index"))


# --------------------------------------------------------------------- helpers
def saves_dir():
    return Path(app.config["SAVES_DIR"])


def game_dir():
    return Path(app.config["GAME_DIR"]) if app.config["GAME_DIR"] else None


def game_data():
    """The game data of the current game folder, or None; reloaded when it changes."""
    data_dir = find_data_dir(game_dir())
    if data_dir is None:
        return None
    objects = data_dir / "Data" / "Objects.json"
    key = (str(data_dir), objects.stat().st_mtime)
    if _game_data_cache["key"] != key:
        _game_data_cache.update(key=key, data=GameData(data_dir))
    return _game_data_cache["data"]


def save_folder(save_id):
    """Rejects anything that isn't a real save folder (path safety)."""
    if not re.fullmatch(r"[^/\\]+", save_id) or not is_save_folder(saves_dir() / save_id):
        abort(404)
    return saves_dir() / save_id


def load(save_id):
    return SaveGame(save_folder(save_id))


def edit(save_id, change, message, reason=backup.AUTO_EDIT, result_as=None):
    """Loads, applies the change, makes a backup, then writes.

    message   : key of the success message
    result_as : name of the message parameter that receives change's return value
                (a change returning a dict gives all the message parameters itself)

    The backup is only made once the change has been validated, so a
    mistyped field doesn't fill the folder with useless backups.
    """
    try:
        sg = load(save_id)
        result = change(sg)
        name = backup.create(saves_dir(), save_id, reason)
        sg.write()
        params = result if isinstance(result, dict) else ({result_as: result} if result_as else {})
        flash(f"{t(message, **params)} {t('flash.backup_made', name=name)}", "ok")
    except SaveError as exc:
        flash(i18n.translate_error(current_lang(), exc), "error")


def use_saves_dir(path):
    path = picker.resolve_saves_dir(Path(path).expanduser())
    if not path.is_dir():
        flash(t("error.folder_missing", path=path), "error")
        return
    count = len(list_saves(path))
    if not count:  # keep the previous folder rather than an empty list
        flash(t("error.folder_no_saves", path=path), "error")
        return
    app.config["SAVES_DIR"] = str(path)
    settings.save(saves_dir=str(path))
    flash(t("flash.folder_updated", n=count), "ok")


# --------------------------------------------------------------------- pages
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":  # path typed by hand
        use_saves_dir(request.form.get("saves_dir", "").strip().strip('"'))
        return redirect(url_for("index"))
    return render_template("index.html", saves=list_saves(saves_dir()),
                           saves_dir=saves_dir(), exists=saves_dir().is_dir(),
                           game_dir=game_dir(), game_status=gamefolder.data_status(game_dir()),
                           job=unpack_job.state(), job_running=unpack_job.running())


@app.post("/pick-saves-dir")
def pick_saves_dir():
    """Opens the file explorer on the computer running the app."""
    try:
        chosen = picker.ask_directory(initial=saves_dir(), title=t("picker.title"))
    except picker.PickerUnavailable as exc:
        flash(t(exc.key), "error")
        return redirect(url_for("index"))
    if chosen:
        use_saves_dir(chosen)
    return redirect(url_for("index"))


def use_game_dir(chosen):
    found = gamefolder.resolve_game_dir(Path(chosen).expanduser())
    if found is None:
        flash(t("error.not_game_folder", path=chosen), "error")
        return
    app.config["GAME_DIR"] = str(found)
    settings.save(game_dir=str(found))
    flash(t("flash.game_folder_updated", path=found), "ok")


@app.post("/game-folder")
def set_game_dir():
    """Game folder typed by hand."""
    use_game_dir(request.form.get("game_dir", "").strip().strip('"'))
    return redirect(url_for("index") + "#game-data")


@app.post("/pick-game-dir")
def pick_game_dir():
    try:
        chosen = picker.ask_directory(initial=game_dir() or "", title=t("picker.game_title"))
    except picker.PickerUnavailable as exc:
        flash(t(exc.key), "error")
        return redirect(url_for("index") + "#game-data")
    if chosen:
        use_game_dir(chosen)
    return redirect(url_for("index") + "#game-data")


@app.post("/game-data/prepare")
def prepare_game_data():
    if not gamefolder.is_game_dir(game_dir()):
        flash(t("error.not_game_folder", path=game_dir() or ""), "error")
    elif not unpack_job.start(game_dir(), settings.app_dir() / "tools"):
        flash(t("error.unpack_busy"), "error")
    return redirect(url_for("index") + "#game-data")


@app.get("/game-data/status")
def game_data_status():
    """Polled by the home page while the game data is being prepared."""
    state = unpack_job.state()
    return jsonify(step=state["step"], percent=state["percent"],
                   running=unpack_job.running(), message=t(f"unpack.step.{state['step']}"))


@app.route("/save/<save_id>")
def farm(save_id):
    sg = load(save_id)
    return render_template("farm.html", farm=sg.farm(), players=sg.players(), tab="farm")


@app.route("/save/<save_id>/player/<uid>")
def player(save_id, uid):
    sg = load(save_id)
    try:
        p = sg.player(uid)
    except KeyError:
        abort(404)
    data = game_data()
    inventory = sg.inventory(uid, describe_item if data else None)
    return render_template("player.html", farm=sg.farm(), players=sg.players(), p=p,
                           inventory=inventory, friendships=sg.friendships(uid),
                           free_slots=[s["slot"] for s in inventory if s["empty"]],
                           recipes=recipe_lists(sg.recipes(uid), data),
                           look=look_view(sg.appearance(uid), data),
                           has_game_data=data is not None, tab=uid)


def recipe_lists(known, data):
    """For each kind: every recipe (with game data) or the known ones, marked known or not."""
    lang = current_lang()
    lists = {}
    for kind, counts in known.items():
        rows = []
        if data:
            for recipe in data.recipes(kind, lang):
                rows.append({**recipe, "known": recipe["name"] in counts,
                             "count": counts.get(recipe["name"], 0),
                             "icon": icon_style(data.icon(recipe["output"]), fit=24) if recipe["output"] else None})
        listed = {row["name"] for row in rows}
        # Known recipes the game data doesn't list (or no game data): still shown, so they can be removed
        rows += [{"name": name, "display": name, "known": True, "count": count, "icon": None}
                 for name, count in sorted(counts.items()) if name not in listed]
        lists[kind] = {"rows": rows, "known": sum(row["known"] for row in rows)}
    return lists


# Clothes on the appearance form: (worn key, catalogue prefix, icon scale)
_CLOTHES = (("shirt", "S", 4), ("pants", "P", 2), ("hat", "H", 2), ("boots", "B", 2))

# Farmer sheets used by the full preview (static/farmer.js), by the name the script uses
_FARMER_SHEETS = {
    "base": "Characters/Farmer/farmer_base", "girl": "Characters/Farmer/farmer_girl_base",
    "base_bald": "Characters/Farmer/farmer_base_bald", "girl_bald": "Characters/Farmer/farmer_girl_base_bald",
    "skin": "Characters/Farmer/skinColors", "shoes": "Characters/Farmer/shoeColors",
    "accessories": "Characters/Farmer/accessories",
    "shirts": "Characters/Farmer/shirts", "pants": "Characters/Farmer/pants",  # default clothes
    "hairstyles": "Characters/Farmer/hairstyles",  # short styles drawn under some hats
}
# Default sheets of worn items, when the game data doesn't give one
_WORN_SHEETS = {"shirt": "Characters/Farmer/shirts", "pants": "Characters/Farmer/pants",
                "hat": "Characters/Farmer/hats"}


def _render_data(key, qualified, data, worn=None):
    """What the full preview needs to draw a worn item: its sheet, sprite index and drawing rules."""
    found = data.sprite(qualified) if data and qualified in data.items else None
    if found:
        sheet, index = found
    elif worn and key != "boots":
        sheet, index = _WORN_SHEETS[key], worn.get("sprite", int(worn["item_id"]) if worn["item_id"].isdigit() else -1)
    else:
        sheet, index = None, -1
    render = {"sheet": url_for("game_image", sheet=sheet) if sheet and data and data.sheet_exists(sheet) else None,
              "index": index}
    item = data.items.get(qualified) if data else None
    if key == "shirt":
        render["sleeves"] = item["data"].get("HasSleeves", True) if item else True
    elif key == "hat":
        if item:
            render["hair_draw"], render["ignore_offset"], _ = appearance.hat_fields(item.get("fields", []))
        elif worn:
            render["hair_draw"], render["ignore_offset"] = worn["hair_draw"], worn["ignore_offset"]
    elif key == "boots":
        fields = item.get("fields", []) if item else []
        render = {"color_index": int(fields[5]) if len(fields) > 5 and fields[5].strip().isdigit()
                  else (worn or {}).get("color_index", int(appearance.NO_BOOTS_SHOE_COLOR))}
    return render


def _hair_render(icon, covered=None):
    """Where the full preview finds a hairstyle, and its version drawn under brimmed hats."""
    render = {"sheet": url_for("game_image", sheet=icon["sheet"]), "x": icon["x"], "y": icon["y"],
              "bald": icon["bald"]}
    if covered:
        render["covered"] = {"sheet": url_for("game_image", sheet=covered["sheet"]),
                             "x": covered["x"], "y": covered["y"]}
    return render


def look_view(current, data):
    """The appearance form: current values and every choice, with previews when game data is there."""
    lang = current_lang()
    hairs = data.hairstyles() if data else dict.fromkeys(appearance.DEFAULT_HAIRS)
    if current["hair"] not in hairs:  # a hairstyle from a mod: keep it selectable
        hairs[current["hair"]] = None
    covered_hairs = data.hairstyles(covered=True) if data else {}
    view = {
        **current,
        "genders": appearance.GENDERS,
        "skins": [{"value": i, "icon": icon_style(data.skin_icon(i), fit=40) if data else None}
                  for i in range(appearance.SKIN_COUNT)],
        "hairs": [{"value": i, "icon": icon_style(icon),
                   "render": _hair_render(icon, covered_hairs.get(icon["covered"])) if icon else None}
                  for i, icon in sorted(hairs.items())],
        "accessories": [{"value": i, "tinted": 0 <= i < appearance.TINTED_ACCESSORIES,
                         "icon": icon_style(data.accessory_icon(i)) if data and i >= 0 else None}
                        for i in range(-1, appearance.ACCESSORY_COUNT)],
        "clothes": {},
        # The full preview needs the body sheets; without them only the per-choice sprites show
        "sheets": {name: url_for("game_image", sheet=sheet) for name, sheet in _FARMER_SHEETS.items()
                   if data and data.sheet_exists(sheet)},
    }
    view["can_draw_farmer"] = all(name in view["sheets"] for name in ("base", "girl", "skin", "shoes"))
    for key, prefix, scale in _CLOTHES:
        worn = current["worn"][key]
        selected = f"{prefix}:{worn['item_id']}" if worn else ""
        options = []
        if data:
            for qualified, name in data.clothing(prefix, lang):
                item_data = data.items[qualified]["data"]
                options.append({
                    "value": qualified, "label": name,
                    "icon": icon_style(data.icon(qualified), scale=scale),
                    "dye_icon": icon_style(data.icon(qualified, dye_layer=True), scale=scale),
                    "dyeable": bool(item_data.get("CanBeDyed")),
                    "color": appearance.hex_color(appearance.rgb_from_data(item_data.get("DefaultColor"))),
                    "render": _render_data(key, qualified, data),
                })
        if worn and selected not in {o["value"] for o in options}:
            # Not in the game data (a mod's item, or no game data): shown, can be kept
            options.insert(0, {"value": selected, "label": worn["name"], "icon": None, "dye_icon": None,
                               "dyeable": worn.get("dyeable", False), "color": worn.get("color"),
                               "render": _render_data(key, selected, data, worn)})
        view["clothes"][key] = {"selected": selected, "options": options, "worn": worn}
    return view


def describe_item(element):
    """Extra fields for an inventory item, from the game data."""
    data, lang = game_data(), current_lang()
    qualified = data.qualified_id(element)
    return {
        "name": data.item_name(element, lang),
        "icon": icon_style(data.icon(qualified)) if qualified else None,
        "tool_levels": data.tool_levels(element.get(XSI + "type") or ""),
    }


def icon_style(icon, scale=2, fit=None):
    """CSS showing one sprite of a sheet, scaled up with crisp pixels.

    fit: size in pixels of a square box the sprite must fit in (overrides scale).
    """
    if not icon:
        return None
    if fit:
        scale = fit / max(icon["w"], icon["h"])
    url = url_for("game_image", sheet=icon["sheet"])
    return (f"background-image:url('{url}');"
            f"background-position:-{icon['x'] * scale}px -{icon['y'] * scale}px;"
            f"background-size:{icon['sheet_w'] * scale}px {icon['sheet_h'] * scale}px;"
            f"width:{icon['w'] * scale}px;height:{icon['h'] * scale}px")


@app.get("/game-image/<path:sheet>")
def game_image(sheet):
    """A sprite sheet from the unpacked game data (only PNG files inside it)."""
    data = game_data()
    path = data.sheet_path(sheet) if data else None
    if path is None:
        abort(404)
    return send_file(path, mimetype="image/png", max_age=3600)


@app.get("/game-data/search")
def search_items():
    """Items that can be added, for the add-item search box."""
    data = game_data()
    if data is None:
        return jsonify(results=[])
    results = data.search(request.args.get("q", ""), current_lang())
    return jsonify(results=[{"id": qualified, "name": name, "icon": icon_style(data.icon(qualified))}
                            for qualified, name in results])


# ---------------------------------------------------------------------- museum
MUSEUM_SIZE = 95  # pieces in the game's museum, when no game data says otherwise


def _spot_arg(prefix=""):
    try:
        return int(request.form[prefix + "x"]), int(request.form[prefix + "y"])
    except (KeyError, ValueError):
        abort(400)


def museum_view(sg, data):
    """Every display spot of the museum (from its map, or the taken ones), with its piece."""
    lang = current_lang()
    pieces = sg.museum()
    spots = data.museum_spots() if data else None
    taken = {(p["x"], p["y"]): p for p in pieces}
    cells = []
    for x, y in sorted((spots or set()) | set(taken), key=lambda s: (s[1], s[0])):
        piece = taken.get((x, y))
        cell = {"x": x, "y": y, "piece": None}
        if piece:
            qualified = f"O:{piece['item_id']}"
            known = data is not None and qualified in data.items
            cell["piece"] = {
                "item_id": piece["item_id"],
                "name": data.display_name(qualified, lang) if known else piece["item_id"],
                "icon": icon_style(data.icon(qualified)) if known else None,
                "kind": data.items[qualified]["data"].get("Type") if known else None,
            }
        cells.append(cell)
    view = {"cells": cells, "count": len(pieces), "has_map": spots is not None,
            "total": MUSEUM_SIZE, "missing": [], "free": spots is not None and len(spots - set(taken)) > 0}
    if cells:
        view["min_x"], view["min_y"] = min(c["x"] for c in cells), min(c["y"] for c in cells)
    if data:
        donatable = data.museum_items()
        # Fewer donatable items than donations would mean the game data isn't the save's
        view["total"] = len(donatable) if len(donatable) >= len(pieces) else MUSEUM_SIZE
        donated = {p["item_id"] for p in pieces}
        # Per kind (artifacts, minerals): pieces donated out of the pieces the museum takes
        view["kinds"] = [{"kind": kind, "count": sum(1 for q in donatable
                                                      if q[2:] in donated and data.items[q]["data"].get("Type") == kind),
                          "total": sum(1 for q in donatable if data.items[q]["data"].get("Type") == kind)}
                         for kind in data.MUSEUM_TYPES] if len(donatable) >= len(pieces) else []
        view["missing"] = sorted(({"id": q, "name": data.display_name(q, lang), "icon": icon_style(data.icon(q)),
                                   "kind": data.items[q]["data"].get("Type")}
                                  for q in donatable if q[2:] not in donated), key=lambda m: m["name"])
    return view


def donatable_in_inventories(sg, data, donated):
    """Items in the farmers' inventories that the museum would take: [{uid, player, slot, name, icon}]."""
    if not data:
        return []
    museum_ids = set(data.museum_items())
    found = []
    for player in sg.players():
        for slot in sg.inventory(player["uid"]):
            qualified = f"O:{slot.get('item_id')}"
            if not slot["empty"] and slot["type"] == "Object" and qualified in museum_ids \
                    and slot["item_id"] not in donated:
                found.append({"uid": player["uid"], "player": player["name"], "slot": slot["slot"],
                              "name": data.display_name(qualified, current_lang()),
                              "icon": icon_style(data.icon(qualified))})
    return found


@app.route("/save/<save_id>/museum")
def museum(save_id):
    sg = load(save_id)
    data = game_data()
    try:
        view = museum_view(sg, data)
    except SaveError as exc:
        flash(i18n.translate_error(current_lang(), exc), "error")
        return redirect(url_for("farm", save_id=save_id))
    donated = {c["piece"]["item_id"] for c in view["cells"] if c["piece"]}
    players = sg.players()
    return render_template("museum.html", farm=sg.farm(), players=players, museum=view,
                           receivers=[p for p in players if sg.first_free_item_slot(p["uid"]) is not None],
                           to_donate=donatable_in_inventories(sg, data, donated) if view["free"] else [],
                           has_game_data=data is not None, tab="museum")


@app.post("/save/<save_id>/museum/move")
def move_donation(save_id):
    data = game_data()
    source, target = _spot_arg("source_"), _spot_arg("target_")
    edit(save_id, lambda sg: sg.move_donation(source, target, data.museum_spots() if data else None),
         "flash.donation_moved")
    return redirect(url_for("museum", save_id=save_id))


@app.post("/save/<save_id>/museum/remove")
def remove_donation(save_id):
    data = game_data()
    spot = _spot_arg()
    receiver = request.form.get("give_to", "")

    def change(sg):
        item_id = sg.remove_donation(spot)
        name = data.display_name(f"O:{item_id}", current_lang()) if data and f"O:{item_id}" in data.items else item_id
        if not receiver:
            return {"name": name, "where": T("museum.discarded")}
        if data is None:
            raise SaveError("error.needs_game_data")
        slot = sg.first_free_item_slot(receiver)
        if slot is None:
            raise SaveError("error.inventory_full", name=sg.player(receiver)["name"])
        sg.add_item(receiver, slot, items.new_item(data, f"O:{item_id}"))
        # "where" is translated with the other parameters: {player} inside it
        return {"name": name, "where": T("museum.given_to"), "player": sg.player(receiver)["name"]}

    edit(save_id, change, "flash.donation_removed")
    return redirect(url_for("museum", save_id=save_id))


@app.post("/save/<save_id>/museum/donate")
def donate(save_id):
    data = game_data()
    if data is None or data.museum_spots() is None:
        abort(400)
    uid = request.form.get("uid", "")

    def change(sg):
        slot = _slot_arg("slot")
        element = sg._slots(uid, slot)[0][slot]
        qualified = data.qualified_id(element) if not items.is_empty(element) else None
        if qualified not in data.museum_items():
            raise SaveError("error.not_donatable")
        spots = data.museum_spots()
        taken = {(p["x"], p["y"]) for p in sg.museum()}
        free = sorted(spots - taken, key=lambda s: (s[1], s[0]))
        if not free:
            raise SaveError("error.museum_full")
        sg.donate(qualified[2:], free[0], spots)
        sg.take_one(uid, slot)
        return {"name": data.display_name(qualified, current_lang()), "x": free[0][0], "y": free[0][1]}

    edit(save_id, change, "flash.donated")
    return redirect(url_for("museum", save_id=save_id))


@app.route("/save/<save_id>/backups")
def backups(save_id):
    sg = load(save_id)
    return render_template("backups.html", farm=sg.farm(), players=sg.players(),
                           backups=backup.list_backups(saves_dir(), save_id),
                           max_auto=backup.MAX_AUTO_BACKUPS,
                           backup_dir=backups_root(saves_dir()) / save_id, tab="backups")


# --------------------------------------------------------------------- actions
@app.post("/save/<save_id>/walnuts")
def set_walnuts(save_id):
    edit(save_id, lambda sg: sg.set_golden_walnuts(request.form["golden_walnuts"]),
         "flash.walnuts_saved")
    return redirect(url_for("farm", save_id=save_id))


@app.post("/save/<save_id>/rename-farm")
def rename_farm(save_id):
    edit(save_id, lambda sg: sg.rename_farm(request.form["farm_name"]),
         "flash.farm_renamed", backup.AUTO_RENAME, result_as="name")
    return redirect(url_for("farm", save_id=save_id))


@app.post("/save/<save_id>/player/<uid>/rename")
def rename_player(save_id, uid):
    edit(save_id, lambda sg: sg.rename_player(uid, request.form["player_name"]),
         "flash.player_renamed", backup.AUTO_RENAME, result_as="name")
    return redirect(url_for("player", save_id=save_id, uid=uid))


@app.post("/save/<save_id>/player/<uid>/clear-userid")
def clear_userid(save_id, uid):
    edit(save_id, lambda sg: sg.clear_user_id(uid), "flash.id_cleared", backup.AUTO_DESYNC)
    return redirect(request.referrer or url_for("farm", save_id=save_id))


@app.post("/save/<save_id>/clear-all-userids")
def clear_all_userids(save_id):
    edit(save_id, lambda sg: sg.clear_all_user_ids(),
         "flash.ids_cleared", backup.AUTO_DESYNC, result_as="n")
    return redirect(url_for("farm", save_id=save_id))


@app.post("/save/<save_id>/player/<uid>/stats")
def set_stats(save_id, uid):
    edit(save_id, lambda sg: sg.update_stats(uid, request.form), "flash.stats_saved")
    return redirect(url_for("player", save_id=save_id, uid=uid) + "#stats")


@app.post("/save/<save_id>/player/<uid>/skills")
def set_skills(save_id, uid):
    levels = {int(k[6:]): v for k, v in request.form.items() if k.startswith("skill_")}
    show = request.form.get("show_levelup") == "on"
    edit(save_id, lambda sg: sg.set_skills(uid, levels, show), "flash.skills_saved")
    return redirect(url_for("player", save_id=save_id, uid=uid) + "#skills")


@app.post("/save/<save_id>/player/<uid>/friendships")
def set_friendships(save_id, uid):
    points = {k[4:]: v for k, v in request.form.items() if k.startswith("npc_")}
    edit(save_id, lambda sg: sg.set_friendships(uid, points), "flash.friendships_saved")
    return redirect(url_for("player", save_id=save_id, uid=uid) + "#friends")


@app.post("/save/<save_id>/player/<uid>/appearance")
def set_appearance(save_id, uid):
    form = request.form
    values = {key: form[key] for key in ("gender", "skin", "hair", "accessory", "hair_color", "eye_color",
                                         "shirt_color", "pants_color", "hat", "boots") if key in form}
    data = game_data()

    def change(sg):
        worn = sg.appearance(uid)["worn"]
        # A shirt or pants is only replaced when another one was picked
        for key, prefix in (("shirt", "S"), ("pants", "P")):
            picked = form.get(key, "")
            if picked and not (worn[key] and picked == f"{prefix}:{worn[key]['item_id']}"):
                values[key] = picked
        sg.set_appearance(uid, values, data)

    edit(save_id, change, "flash.appearance_saved")
    return redirect(url_for("player", save_id=save_id, uid=uid) + "#appearance")


@app.post("/save/<save_id>/player/<uid>/inventory")
def set_inventory(save_id, uid):
    changes, levels = {}, {}
    for key, value in request.form.items():
        if key.startswith("stack_"):
            slot = int(key[6:])
            changes[slot] = {"stack": value, "quality": request.form.get(f"quality_{slot}", 0)}
        elif key.startswith("tool_level_"):
            levels[int(key[11:])] = value
    edit(save_id, lambda sg: sg.set_inventory(uid, changes, levels, game_data()),
         "flash.inventory_saved")
    return redirect(url_for("player", save_id=save_id, uid=uid) + "#inventory")


def _slot_arg(name):
    try:
        return int(request.form[name])
    except (KeyError, ValueError):
        abort(400)


@app.post("/save/<save_id>/player/<uid>/recipes/<kind>")
def set_recipes(save_id, uid, kind):
    if kind not in ("cooking", "crafting"):
        abort(404)
    names = request.form.getlist("recipe")
    def change(sg):
        added, removed = sg.set_recipes(uid, kind, names)
        return {"added": added, "removed": removed}

    edit(save_id, change, "flash.recipes_saved")
    return redirect(url_for("player", save_id=save_id, uid=uid) + f"#recipes-{kind}")


@app.post("/save/<save_id>/player/<uid>/inventory/add")
def add_item(save_id, uid):
    data = game_data()
    if data is None:
        abort(400)

    def change(sg):
        quality = request.form.get("quality", "0")
        element = items.new_item(
            data, request.form.get("item", ""),
            stack=bounded(request.form.get("stack"), 1, 999, "field.quantity"),
            quality=int(quality) if quality.isdigit() else 0)
        sg.add_item(uid, _slot_arg("slot"), element)
        return data.display_name(request.form["item"], current_lang())

    edit(save_id, change, "flash.item_added", result_as="name")
    return redirect(url_for("player", save_id=save_id, uid=uid) + "#inventory")


@app.post("/save/<save_id>/player/<uid>/inventory/remove")
def remove_item(save_id, uid):
    edit(save_id, lambda sg: sg.remove_item(uid, _slot_arg("slot")), "flash.item_removed")
    return redirect(url_for("player", save_id=save_id, uid=uid) + "#inventory")


@app.post("/save/<save_id>/player/<uid>/inventory/move")
def move_item(save_id, uid):
    edit(save_id, lambda sg: sg.move_item(uid, _slot_arg("source"), _slot_arg("target")),
         "flash.item_moved")
    return redirect(url_for("player", save_id=save_id, uid=uid) + "#inventory")


@app.post("/save/<save_id>/backups/create")
def create_backup(save_id):
    save_folder(save_id)
    name = backup.create(saves_dir(), save_id, backup.MANUAL)
    flash(t("flash.backup_created", name=name), "ok")
    return redirect(url_for("backups", save_id=save_id))


@app.post("/save/<save_id>/backups/<name>/restore")
def restore_backup(save_id, name):
    save_folder(save_id)
    try:
        backup.restore(saves_dir(), save_id, name)
        flash(t("flash.backup_restored", name=name), "ok")
    except SaveError as exc:
        flash(i18n.translate_error(current_lang(), exc), "error")
    return redirect(url_for("backups", save_id=save_id))


@app.post("/save/<save_id>/backups/<name>/delete")
def delete_backup(save_id, name):
    save_folder(save_id)
    try:
        backup.delete(saves_dir(), save_id, name)
        flash(t("flash.backup_deleted", name=name), "ok")
    except SaveError as exc:
        flash(i18n.translate_error(current_lang(), exc), "error")
    return redirect(url_for("backups", save_id=save_id))