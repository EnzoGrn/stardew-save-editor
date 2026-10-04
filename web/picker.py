"""Native folder picker window.

A browser never reveals the full path of a folder the user picks. Since the
server runs on the same computer, the server opens the file explorer window
itself, through Tkinter (bundled with Python on Windows and macOS).

The window runs in a separate process: Tkinter must run on a program's main
thread (mandatory on macOS), which a Flask request thread is not.
"""
import os
import subprocess
import sys
from pathlib import Path


def pick(initial, title):
    """Shows the window and returns the chosen folder ("" if cancelled). Runs in its own process."""
    import tkinter
    from tkinter import filedialog
    if sys.platform.startswith("win"):
        # Without this, Windows assumes the program ignores display scaling
        # (125 %, 150 %…) and stretches the window like an image, which makes it
        # blurry. We declare that we handle scaling ourselves.
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)   # Windows 8.1 and later
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()     # Windows 7
            except Exception:
                pass
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)   # show in front of the browser
    chosen = filedialog.askdirectory(parent=root, initialdir=initial or None, mustexist=True, title=title)
    root.destroy()
    return chosen or ""


# The flag run.py looks for: in the packaged app (.exe) there is no Python to run a
# script with, so the app starts itself again in picker mode
PICK_FLAG = "--pick-folder"


def main(args):
    """Entry point of the picker process: prints the chosen folder."""
    initial, title = (list(args) + ["", ""])[:2]
    sys.stdout.write(pick(initial, title))


def _command(initial, title):
    if getattr(sys, "frozen", False):
        return [sys.executable, PICK_FLAG, initial, title], None
    # From the sources: a plain Python process importing this module
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        filter(None, [str(Path(__file__).resolve().parents[1]), os.environ.get("PYTHONPATH")])))
    code = "import sys; from web.picker import main; main(sys.argv[1:])"
    return [sys.executable, "-c", code, initial, title], env


class PickerUnavailable(Exception):
    """Tkinter is missing (some Linux installs). key: message key."""

    def __init__(self, key):
        super().__init__(key)
        self.key = key


def ask_directory(initial="", title=""):
    """Returns the chosen folder, or None if the user cancelled."""
    initial = str(initial) if initial and Path(initial).is_dir() else ""
    try:
        command, env = _command(initial, title)
        result = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600)
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        if "tkinter" in result.stderr.lower():
            raise PickerUnavailable("error.picker_no_tkinter")
        raise PickerUnavailable("error.picker_failed")
    return result.stdout.strip() or None


def resolve_saves_dir(chosen):
    """Also accepts a folder next to the right one, for convenience.

    - the StardewValley folder → its Saves subfolder
    - a save's own folder      → the Saves folder that contains it
    """
    from sdvsave.paths import is_save_folder

    path = Path(chosen)
    if (path / "Saves").is_dir():
        return path / "Saves"
    if is_save_folder(path):
        return path.parent
    return path