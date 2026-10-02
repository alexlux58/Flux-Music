@echo off
title Music Library
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtualenv and installing dependencies...
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -U pip
  ".venv\Scripts\pip.exe" install -e ".[dev,build]"
)
start "Music Library" ".venv\Scripts\pythonw.exe" -m src.main
