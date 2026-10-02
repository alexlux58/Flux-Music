$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
if (-not (Test-Path .venv)) {
  python -m venv .venv
  .\.venv\Scripts\pip.exe install -e ".[dev,build]"
}
.\.venv\Scripts\python.exe -m PyInstaller MusicLibrary.spec --distpath dist-bpm --workpath build-bpm
Write-Host "Built dist-bpm/MusicLibrary/MusicLibrary.exe"
Write-Host "Install FFmpeg separately and ensure ffmpeg/ffprobe are on PATH."
