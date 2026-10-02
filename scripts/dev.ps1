$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
if (-not (Test-Path .venv)) {
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -U pip
  .\.venv\Scripts\pip.exe install -e ".[dev,build]"
}
.\.venv\Scripts\python.exe -m src.main @args
