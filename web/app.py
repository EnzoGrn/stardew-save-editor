"""Local web UI of the save manager."""
import re
from pathlib import Path

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request,
                   send_file, url_for)

from sdvsave import SaveGame, SaveError, backup, default_saves_dir, gamefolder, list_saves
from sdvsave.constants import QUALITIES, POINTS_PER_HEART, MAX_FRIENDSHIP_POINTS, BACKPACK_SIZES
from sdvsave import items
from sdvsave.constants import XSI
from sdvsave.gamedata import GameData, find_data_dir
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

    The backup is only made once the change has been validated, so a
    mistyped field doesn't fill the folder with useless backups.
    """
    try:
        sg = load(save_id)
        result = change(sg)
        name = backup.create(saves_dir(), save_id, reason)
        sg.write()
        params = {result_as: result} if result_as else {}
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
                           has_game_data=data is not None, tab=uid)


def describe_item(element):
    """Extra fields for an inventory item, from the game data."""
    data, lang = game_data(), current_lang()
    qualified = data.qualified_id(element)
    return {
        "name": data.item_name(element, lang),
        "icon": icon_style(data.icon(qualified)) if qualified else None,
        "tool_levels": data.tool_levels(element.get(XSI + "type") or ""),
    }


def icon_style(icon, scale=2):
    """CSS showing one sprite of a sheet, scaled up with crisp pixels."""
    if not icon:
        return None
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