# PyInstaller recipe for the packaged app: one StardewSaveEditor.exe, nothing to install.
#
#     pip install -r requirements.txt pyinstaller
#     pyinstaller packaging/StardewSaveEditor.spec
#
# The result is dist/StardewSaveEditor.exe (dist/StardewSaveEditor elsewhere).
# Build on Windows for Windows: PyInstaller doesn't cross-compile.
from pathlib import Path

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root)],
    # Flask finds templates and static files next to web/app.py, translations next to web/i18n.py
    datas=[
        (str(root / "web" / "templates"), "web/templates"),
        (str(root / "web" / "static"), "web/static"),
        (str(root / "web" / "locales"), "web/locales"),
    ],
    # The folder picker (web/picker.py) imports Tkinter inside a function
    hiddenimports=["tkinter", "tkinter.filedialog"],
    excludes=["pytest", "PIL"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="StardewSaveEditor",
    icon=str(root / "packaging" / "icon.ico"),
    # A console window: it shows the address and stops the app when closed
    console=True,
    upx=False,
)
