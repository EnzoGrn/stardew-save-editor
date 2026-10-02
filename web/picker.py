"""Native folder picker window.

A browser never reveals the full path of a folder the user picks. Since the
server runs on the same computer, the server opens the file explorer window
itself, through Tkinter (bundled with Python on Windows and macOS).

The window runs in a separate process: Tkinter must run on a program's main
thread (mandatory on macOS), which a Flask request thread is not.
"""
import subprocess
import sys
from pathlib import Path

_SCRIPT = r"""
import sys, tkinter
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
chosen = filedialog.askdirectory(
    parent=root, initialdir=sys.argv[1] or None, mustexist=True, title=sys.argv[2])
root.destroy()
sys.stdout.write(chosen or "")
"""


class PickerUnavailable(Exception):
    """Tkinter is missing (some Linux installs). key: message key."""

    def __init__(self, key):
        super().__init__(key)
        self.key = key


def ask_directory(initial="", title=""):
    """Returns the chosen folder, or None if the user cancelled."""
    initial = str(initial) if initial and Path(initial).is_dir() else ""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _SCRIPT, initial, title],
            capture_output=True, text=True, encoding="utf-8", timeout=600)
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