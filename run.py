"""Starts the Stardew Valley save manager.

    python run.py                      # save folder detected automatically
    python run.py --saves "D:/Saves"   # another folder
"""
import argparse
import threading
import webbrowser

from web.app import app

parser = argparse.ArgumentParser(description="Stardew Valley save manager")
parser.add_argument("--saves", help="Folder containing the saves (StardewValley/Saves)")
parser.add_argument("--port", type=int, default=5173)
parser.add_argument("--no-browser", action="store_true", help="Don't open the browser")
args = parser.parse_args()

if args.saves:
    app.config["SAVES_DIR"] = args.saves

url = f"http://127.0.0.1:{args.port}"
print(f"Save manager: {url}  (Ctrl+C to stop)")
print(f"Save folder: {app.config['SAVES_DIR']}")
if not args.no_browser:
    threading.Timer(1.0, webbrowser.open, [url]).start()
app.run(host="127.0.0.1", port=args.port, debug=False)