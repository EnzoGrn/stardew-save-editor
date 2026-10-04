"""What the packaged app (.exe) relies on: the picker relaunch, /ping, offline assets."""
import sys
from pathlib import Path

from web import picker
from web.app import APP_ID, app

ROOT = Path(__file__).resolve().parents[1]


def test_picker_runs_python_from_the_sources(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    command, env = picker._command("C:/start", "Title")
    assert command[0] == sys.executable and command[1] == "-c"
    assert command[-2:] == ["C:/start", "Title"]
    assert str(ROOT) in env["PYTHONPATH"]


def test_packaged_picker_starts_the_app_again_in_picker_mode(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    command, env = picker._command("", "Title")
    assert command == [sys.executable, picker.PICK_FLAG, "", "Title"]
    assert env is None


def test_ping_identifies_the_app():
    assert app.test_client().get("/ping").get_data(as_text=True) == APP_ID


def test_pages_need_no_internet():
    """Fonts and every other asset are served by the app itself."""
    for template in (ROOT / "web" / "templates").glob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert "https://" not in text and "http://" not in text, template.name
    css = (ROOT / "web" / "static" / "fonts" / "fonts.css").read_text(encoding="utf-8")
    for line in css.splitlines():
        if "url(" in line:
            name = line.split('url("')[1].split('"')[0]
            assert (ROOT / "web" / "static" / "fonts" / name).is_file(), name
