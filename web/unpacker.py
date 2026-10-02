"""One-click game data preparation, run in the background.

Downloads StardewXnbHack (https://github.com/Pathoschild/StardewXnbHack, MIT
licence) from its official GitHub releases, runs it in the game folder, and
reports progress so the page can show it.

How StardewXnbHack behaves, which shapes this module:
  - it must sit in the game folder: it loads the game's own DLLs from there,
    so we copy it in for the run and remove it afterwards;
  - it needs SMAPI's toolkit DLLs (normally installed with SMAPI, the mod
    loader, in "<game folder>/smapi-internal"). Players without SMAPI don't
    have them, so we take them from the official SMAPI release, put them in
    place for the run only, and leave an existing SMAPI install untouched;
  - it writes everything to "<game folder>/Content (unpacked)";
  - it waits for a key press before closing. On Windows it runs in its own
    console window (its progress bar needs a real console) and the user
    presses a key there; on macOS and Linux it runs on a pseudo-terminal and
    we send the key ourselves.

Progress is measured the same way everywhere: files written to the unpacked
folder since the start, out of the number of packed files in Content.
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

from sdvsave import gamefolder

# A known-good pair: StardewXnbHack 1.1.2 is built against SMAPI 4.1.4. Both are
# pinned rather than "latest", so an update to one can't break the other.
XNBHACK_VERSION = "1.1.2"
XNBHACK_URL = ("https://github.com/Pathoschild/StardewXnbHack/releases/download/"
               "{v}/StardewXnbHack-{v}-for-{platform}.zip")
SMAPI_VERSION = "4.1.4"
SMAPI_URL = ("https://github.com/Pathoschild/SMAPI/releases/download/"
             "{v}/SMAPI-{v}-installer.zip")
SMAPI_FOLDER = "smapi-internal"
TIMEOUT = 30 * 60  # seconds; a full unpack takes about a minute

# Terminal control sequences (window title, colours, cursor moves) in the tool's output
_TERMINAL_CODES = re.compile(r"\x1b\][^\x07]*\x07|\x1b\[[0-9;?]*[A-Za-z]|\r")

# Job steps, shown by the UI (keys "unpack.step.<step>")
IDLE, DOWNLOADING, EXTRACTING, UNPACKING, WAITING_KEY, DONE, FAILED = (
    "idle", "downloading", "extracting", "unpacking", "waiting_key", "done", "failed")


class UnpackError(Exception):
    def __init__(self, key, **params):
        super().__init__(key)
        self.key = key
        self.params = params


def _platform():
    if sys.platform.startswith("win"):
        return "Windows"
    return "macOS" if sys.platform == "darwin" else "Linux"


def _exe_name():
    return "StardewXnbHack.exe" if sys.platform.startswith("win") else "StardewXnbHack"


class Job:
    """The single unpack job of the app; its state is read by the status route."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {"step": IDLE, "percent": 0, "error": None, "params": {}}
        self._thread = None

    def state(self):
        with self._lock:
            return dict(self._state)

    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def _set(self, **values):
        with self._lock:
            self._state.update(values)

    def start(self, game_dir, tools_dir, on_done=None):
        """Starts the job unless one is already running. Returns False if busy."""
        if self.running():
            return False
        self._set(step=DOWNLOADING, percent=0, error=None, params={})
        self._thread = threading.Thread(
            target=self._run, args=(Path(game_dir), Path(tools_dir), on_done), daemon=True)
        self._thread.start()
        return True

    # ------------------------------------------------------------------ steps
    def _run(self, game_dir, tools_dir, on_done):
        try:
            exe = self._get_tool(tools_dir)
            toolkit = None if (game_dir / SMAPI_FOLDER).is_dir() else self._get_toolkit(tools_dir)
            self._unpack(exe, game_dir, toolkit)
            self._set(step=DONE, percent=100)
            if on_done:
                on_done()
        except UnpackError as exc:
            self._set(step=FAILED, error=exc.key, params=exc.params)
        except Exception as exc:  # never leave the page waiting on a dead job
            self._set(step=FAILED, error="error.unpack_unexpected", params={"detail": str(exc)})

    def _download(self, url, target):
        """Downloads a file, reporting progress; the file only appears once complete."""
        self._set(step=DOWNLOADING, percent=0)
        partial = target.with_name(target.name + ".part")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "stardew-save-editor"})
            with urllib.request.urlopen(request, timeout=60) as response, open(partial, "wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                while chunk := response.read(256 * 1024):
                    out.write(chunk)
                    done += len(chunk)
                    if total:
                        self._set(percent=int(done * 100 / total))
            partial.replace(target)
        except OSError as exc:
            partial.unlink(missing_ok=True)
            raise UnpackError("error.unpack_download", detail=str(exc))

    def _get_tool(self, tools_dir):
        """Path to the StardewXnbHack executable, downloaded once and kept."""
        folder = tools_dir / f"StardewXnbHack-{XNBHACK_VERSION}"
        exe = folder / _exe_name()
        if exe.is_file():
            return exe
        folder.mkdir(parents=True, exist_ok=True)
        archive = folder / "download.zip"
        self._download(XNBHACK_URL.format(v=XNBHACK_VERSION, platform=_platform()), archive)
        self._set(step=EXTRACTING, percent=0)
        try:
            with zipfile.ZipFile(archive) as zf:
                member = next(n for n in zf.namelist() if n.endswith("/" + _exe_name()))
                with zf.open(member) as src, open(exe, "wb") as out:
                    shutil.copyfileobj(src, out)
        except (zipfile.BadZipFile, StopIteration, OSError) as exc:
            exe.unlink(missing_ok=True)
            raise UnpackError("error.unpack_download", detail=str(exc))
        finally:
            archive.unlink(missing_ok=True)
        exe.chmod(0o755)
        return exe

    def _get_toolkit(self, tools_dir):
        """Folder holding SMAPI's toolkit DLLs, downloaded once and kept.

        The SMAPI installer keeps them in "internal/<platform>/install.dat", a
        zip whose "smapi-internal/" folder is what SMAPI installs in the game.
        Only the DLLs are kept: nothing else of SMAPI is used.
        """
        folder = tools_dir / f"SMAPI-{SMAPI_VERSION}" / SMAPI_FOLDER
        if folder.is_dir() and any(folder.glob("SMAPI.Toolkit*.dll")):
            return folder
        folder.mkdir(parents=True, exist_ok=True)
        archive = folder.parent / "download.zip"
        self._download(SMAPI_URL.format(v=SMAPI_VERSION), archive)
        self._set(step=EXTRACTING, percent=0)
        platform = {"Windows": "windows", "macOS": "macOS", "Linux": "linux"}[_platform()]
        try:
            with zipfile.ZipFile(archive) as installer:
                inner = next(n for n in installer.namelist()
                             if n.endswith(f"/internal/{platform}/install.dat"))
                with zipfile.ZipFile(BytesIO(installer.read(inner))) as install:
                    for name in install.namelist():
                        if name.startswith(SMAPI_FOLDER + "/") and name.endswith(".dll") \
                                and name.count("/") == 1:
                            (folder / name.split("/")[1]).write_bytes(install.read(name))
        except (zipfile.BadZipFile, StopIteration, OSError) as exc:
            shutil.rmtree(folder, ignore_errors=True)
            raise UnpackError("error.unpack_download", detail=str(exc))
        finally:
            archive.unlink(missing_ok=True)
        return folder

    def _unpack(self, exe, game_dir, toolkit=None):
        """Runs StardewXnbHack in the game folder.

        toolkit: folder of SMAPI toolkit DLLs to put in the game folder for the
        run, or None when SMAPI is already installed there.
        """
        content = gamefolder.content_dir(game_dir)
        total = sum(1 for _ in content.rglob("*.xnb")) or 1
        target = game_dir / exe.name
        smapi_copy = game_dir / SMAPI_FOLDER if toolkit else None
        try:
            shutil.copy2(exe, target)
            if smapi_copy:
                shutil.copytree(toolkit, smapi_copy)
        except OSError as exc:
            target.unlink(missing_ok=True)
            if smapi_copy:
                shutil.rmtree(smapi_copy, ignore_errors=True)
            raise UnpackError("error.unpack_no_write", path=str(game_dir), detail=str(exc))

        started = time.time()
        self._set(step=UNPACKING, percent=0)
        try:
            if sys.platform.startswith("win"):
                output = self._run_windows(target, game_dir, started, total)
            else:
                output = self._run_pty(target, game_dir, started, total)
        finally:
            try:
                target.unlink()
            except OSError:
                pass  # still locked: harmless, the next run overwrites it
            if smapi_copy:
                # Only the copy made for this run: an existing SMAPI is never touched
                shutil.rmtree(smapi_copy, ignore_errors=True)

        objects = gamefolder.unpacked_dir(game_dir) / "Data" / "Objects.json"
        if not objects.is_file() or objects.stat().st_mtime < started - 1:
            lines = [line for line in _TERMINAL_CODES.sub("", output).splitlines()
                     if line.strip() and "Press any key" not in line]
            raise UnpackError("error.unpack_failed", detail=" ".join(lines)[-500:])

    def _progress(self, game_dir, started, total):
        written = 0
        for root, _, files in os.walk(gamefolder.unpacked_dir(game_dir)):
            for name in files:
                try:
                    if os.path.getmtime(os.path.join(root, name)) >= started - 1:
                        written += 1
                except OSError:
                    pass
        return min(written, total), min(99, int(written * 100 / total))

    def _run_windows(self, target, game_dir, started, total):
        process = subprocess.Popen([str(target)], cwd=game_dir,
                                   creationflags=subprocess.CREATE_NEW_CONSOLE)
        while process.poll() is None:
            if time.time() - started > TIMEOUT:
                process.kill()
                raise UnpackError("error.unpack_timeout")
            written, percent = self._progress(game_dir, started, total)
            # Everything is written: only the "press any key" prompt is left
            self._set(step=WAITING_KEY if written >= total else UNPACKING, percent=percent)
            time.sleep(1)
        return ""

    def _run_pty(self, target, game_dir, started, total):
        import pty
        import select

        master, slave = pty.openpty()
        process = subprocess.Popen([str(target)], cwd=game_dir, stdin=slave, stdout=slave,
                                   stderr=slave, start_new_session=True)
        os.close(slave)
        output, answered, last_check = b"", False, 0.0
        try:
            while True:
                if time.time() - started > TIMEOUT:
                    process.kill()
                    raise UnpackError("error.unpack_timeout")
                ready, _, _ = select.select([master], [], [], 0.5)
                if ready:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:  # the process closed the terminal
                        break
                    if not chunk:
                        break
                    output = (output + chunk)[-20000:]
                    if not answered and b"Press any key" in output:
                        os.write(master, b"\r")
                        answered = True
                elif process.poll() is not None:
                    break
                if time.time() - last_check >= 1:
                    last_check = time.time()
                    self._set(percent=self._progress(game_dir, started, total)[1])
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
        finally:
            os.close(master)
        return output.decode("utf-8", errors="replace")