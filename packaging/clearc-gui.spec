# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

# ---- 兼容：不依赖 __file__，优先用 PyInstaller 提供的 SPECPATH ----
try:
    SPEC_DIR = Path(SPECPATH).resolve()  # noqa: F821 (PyInstaller 提供)
except Exception:
    SPEC_DIR = (Path.cwd() / "packaging").resolve()

PROJECT_ROOT = SPEC_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

ENTRY_SCRIPT = SPEC_DIR / "run_clearc_gui.py"

ICON_FILE = PROJECT_ROOT / "your_icon.ico"
ICON_VALUE = str(ICON_FILE) if ICON_FILE.exists() else None

# ---- 关键：让 spec 执行时就能 import 到 src/clearc ----
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

# ---- 关键：runpy 动态加载，PyInstaller 不一定能自动分析，必须强制收集 clearc ----
CLEARC_HIDDEN = collect_submodules("clearc")

block_cipher = None

a = Analysis(
    [str(ENTRY_SCRIPT)],
    pathex=[str(SRC_DIR), str(PROJECT_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=CLEARC_HIDDEN + ["tkinter", "subprocess"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="clearc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_VALUE,
    uac_admin=True,
)