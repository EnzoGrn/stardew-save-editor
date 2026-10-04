"""Starts Stardew Save Editor.

    python run.py                      # save folder detected automatically
    python run.py --saves "D:/Saves"   # another folder

The packaged Windows app (StardewSaveEditor.exe) starts here too.
"""
import argparse
import socket
import sys
import threading
import urllib.request
import webbrowser

DEFAULT_PORT = 5173
FROZEN = getattr(sys, "frozen", False)  # running as the packaged .exe


def port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def already_running(port):
    """True if this app is the one answering on the port (launched twice)."""
    from web.app import APP_ID
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=2) as response:
            return response.read().decode("utf-8", "replace").strip() == APP_ID
    except (OSError, ValueError):
        return False


def free_port():
    """A port the system picks: when the usual one is taken by another program."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description="Stardew Save Editor")
    parser.add_argument("--saves", help="Folder containing the saves (StardewValley/Saves)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="Don't open the browser")
    args = parser.parse_args()

    from web.app import app

    port = args.port
    if not port_is_free(port):
        if already_running(port):
            # A second double-click: show the app already open rather than failing
            print(f"Stardew Save Editor is already running: http://127.0.0.1:{port}")
            if not args.no_browser:
                webbrowser.open(f"http://127.0.0.1:{port}")
            return
        port = free_port()

    if args.saves:
        app.config["SAVES_DIR"] = args.saves

    url = f"http://127.0.0.1:{port}"
    print(f"Stardew Save Editor: {url}")
    print(f"Save folder: {app.config['SAVES_DIR']}")
    print("Keep this window open while you use the app; close it (or press Ctrl+C) to stop.")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    # Keep the window readable: no "development server" banner nor a line per request
    # (the app only ever serves this computer)
    import logging
    import flask.cli
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    flask.cli.show_server_banner = lambda *args, **kwargs: None
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    from web import picker
    if len(sys.argv) > 1 and sys.argv[1] == picker.PICK_FLAG:
        # The app started again by itself to show the folder picker (see web/picker.py)
        picker.main(sys.argv[2:])
        sys.exit(0)
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        if not FROZEN:
            raise
        # The .exe's window would close at once: keep the error readable
        import traceback
        traceback.print_exc()
        input("\nStardew Save Editor stopped because of this error. Press Enter to close.")
        sys.exit(1)