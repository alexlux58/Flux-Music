@echo off
setlocal
cd /d "%~dp0"
tasklist /FI "IMAGENAME eq MusicLibrary.exe" /NH | find /I "MusicLibrary.exe" >nul
if not errorlevel 1 (
    echo Close the running Music Library app first, then launch this shortcut again.
    pause
    exit /b 1
)
if not exist "dist-bpm\MusicLibrary\MusicLibrary.exe" (
    echo Build the BPM version with scripts\build.ps1 first.
    pause
    exit /b 1
)
start "Music Library" "dist-bpm\MusicLibrary\MusicLibrary.exe"
