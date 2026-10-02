"""Running the unpacker, with a stand-in for StardewXnbHack.

The stand-in behaves like the real tool where it matters: it writes the
unpacked files in its working folder, then waits for a key press.
Windows runs the tool in its own console window, which can't be tested here.
"""
import sys
import textwrap
import time

import pytest

from web import unpacker

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"),
                                reason="the pseudo-terminal runner is for macOS and Linux")


@pytest.fixture
def game(tmp_path):
    game = tmp_path / "game"
    (game / "Content" / "Data").mkdir(parents=True)
    for name in ("Objects", "Tools", "Weapons"):
        (game / "Content" / "Data" / f"{name}.xnb").write_bytes(b"xnb")
    (game / "Stardew Valley.dll").write_bytes(b"dll")
    return game


def fake_tool(tmp_path, body):
    exe = tmp_path / "tools" / "StardewXnbHack"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body))
    exe.chmod(0o755)
    return exe


WORKING_TOOL = """
    import os, sys, time
    os.makedirs("Content (unpacked)/Data", exist_ok=True)
    for name in ("Objects", "Tools", "Weapons"):
        with open(f"Content (unpacked)/Data/{name}.json", "w") as f:
            f.write("{}")
        time.sleep(0.1)
    print("Done! Unpacked 3 files.")
    print("Press any key to exit.", flush=True)
    sys.stdin.read(1)   # waits like Console.ReadKey()
"""


def test_unpack_runs_tool_and_answers_the_key_prompt(game, tmp_path):
    job = unpacker.Job()
    job._unpack(fake_tool(tmp_path, WORKING_TOOL), game)
    assert (game / "Content (unpacked)" / "Data" / "Objects.json").is_file()
    assert not (game / "StardewXnbHack").exists()  # the copy is removed after the run


def test_unpack_reports_a_tool_that_writes_nothing(game, tmp_path):
    broken = fake_tool(tmp_path, """
        print("Oops! StardewXnbHack must be placed in the Stardew Valley game folder.")
        print("Press any key to exit.", flush=True)
        input()
    """)
    with pytest.raises(unpacker.UnpackError) as error:
        unpacker.Job()._unpack(broken, game)
    assert error.value.key == "error.unpack_failed"
    assert "must be placed" in error.value.params["detail"]


def test_job_runs_in_background_with_a_cached_tool(game, tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    cached = tools / f"StardewXnbHack-{unpacker.PINNED_VERSION}" / "StardewXnbHack"
    cached.parent.mkdir(parents=True)
    fake_tool(tmp_path, WORKING_TOOL).rename(cached)
    # No network: the pinned version is used, and it is already downloaded
    monkeypatch.setattr(unpacker.Job, "_latest_release",
                        staticmethod(lambda platform: (_ for _ in ()).throw(OSError("offline"))))

    job = unpacker.Job()
    assert job.start(game, tools)
    assert not job.start(game, tools)  # one job at a time
    deadline = time.time() + 30
    while job.running() and time.time() < deadline:
        time.sleep(0.1)
    assert job.state()["step"] == unpacker.DONE
    assert job.state()["percent"] == 100