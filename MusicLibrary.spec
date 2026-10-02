# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Music Library (Windows).

FFmpeg is NOT bundled. Install FFmpeg separately and keep it on PATH.
Review licensing before redistributing any third-party binaries.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

librosa_datas, librosa_binaries, librosa_imports = collect_all("librosa")

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    ["src/main.py"],
    pathex=[str(root)],
    binaries=librosa_binaries,
    datas=[
        (str(root / "config" / "default.yaml"), "config"),
        (str(root / "assets" / "icons" / "app-icon.ico"), "assets/icons"),
        (str(root / "assets" / "icons" / "app-icon.png"), "assets/icons"),
    ] + librosa_datas,
    hiddenimports=[
        "yt_dlp",
        "mutagen",
        "sqlalchemy",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ] + librosa_imports,
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
    [],
    exclude_binaries=True,
    name="MusicLibrary",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(root / "assets" / "icons" / "app-icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="MusicLibrary",
)
