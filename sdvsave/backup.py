"""Timestamped backups of a save."""
import re
import shutil
from datetime import datetime
from pathlib import Path

from .errors import NotFound, SaveError
from .paths import backups_root, is_save_folder

MAX_AUTO_BACKUPS = 30  # older automatic backups are deleted

# A backup's origin is written into its folder name. These identifiers never
# change (they predate the English codebase), so existing backups are still
# recognised; their displayed label is translated by the UI
# (keys "backup.reason.<id>").
MANUAL = "manual"
AUTO_EDIT = "auto-modification"
AUTO_RENAME = "auto-renommage"
AUTO_DESYNC = "auto-desync-id"
BEFORE_RESTORE = "avant-restauration"


def _folder(saves_dir, save_id):
    return backups_root(saves_dir) / save_id


def create(saves_dir, save_id, reason=MANUAL):
    src = Path(saves_dir) / save_id
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest = _folder(saves_dir, save_id) / f"{stamp}_{reason}"
    n = 1
    while dest.exists():  # two backups within the same second
        dest = dest.with_name(f"{stamp}_{reason}_{n}")
        n += 1
    shutil.copytree(src, dest)
    _prune(saves_dir, save_id)
    return dest.name


def list_backups(saves_dir, save_id):
    folder = _folder(saves_dir, save_id)
    if not folder.is_dir():
        return []
    result = []
    for b in sorted(folder.iterdir(), reverse=True):
        if not b.is_dir():
            continue
        date, _, rest = b.name.partition("_")
        time, _, reason = rest.partition("_")
        size = sum(f.stat().st_size for f in b.iterdir() if f.is_file())
        result.append({
            "name": b.name,
            "date": f"{date} {time.replace('-', ':')}",
            "reason": re.sub(r"_\d+$", "", reason),  # without the "_2" suffix of duplicates
            "size_kb": round(size / 1024),
            "valid": (b / save_id).is_file() and (b / "SaveGameInfo").is_file(),
        })
    return result


def restore(saves_dir, save_id, backup_name):
    src = _folder(saves_dir, save_id) / backup_name
    if not ((src / save_id).is_file() and (src / "SaveGameInfo").is_file()):
        raise SaveError("error.backup_incomplete")
    create(saves_dir, save_id, BEFORE_RESTORE)
    dest = Path(saves_dir) / save_id
    for f in src.iterdir():
        if f.is_file():
            shutil.copy2(f, dest / f.name)


def delete(saves_dir, save_id, backup_name):
    target = _folder(saves_dir, save_id) / backup_name
    if target.parent != _folder(saves_dir, save_id) or not target.is_dir():
        raise NotFound("error.backup_not_found")
    shutil.rmtree(target)


def _prune(saves_dir, save_id):
    autos = [b for b in list_backups(saves_dir, save_id) if b["reason"].startswith("auto")]
    for b in autos[MAX_AUTO_BACKUPS:]:
        shutil.rmtree(_folder(saves_dir, save_id) / b["name"])