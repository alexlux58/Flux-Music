# Flux Music

A local music library and YouTube / YouTube Music audio downloader with a
PySide6 desktop player and FastAPI browser companion. Download only content
you have permission to obtain. The app does not bypass DRM, paywalls or
account restrictions.

## Technical walkthrough

The detailed [Markdown walkthrough](docs/walkthrough/flux-music-technical-walkthrough.md)
and [PDF walkthrough](docs/walkthrough/dist/flux-music-technical-walkthrough.pdf)
cover architecture, setup, configuration, the download pipeline, queue state,
BPM analysis, verified extra copies, imports, recovery, the catalog schema,
API behavior, tests, Windows packaging and publication. Seven source-controlled
diagrams and checked code excerpts accompany the guide.

Documentation is generated from the adjacent `.md.in` source. Build/check with
`python tools/docs-build/build.py` / `python tools/docs-build/build.py --check`;
the guide documents the pinned PDF toolchain and diagram rendering.

## Features

- Paste multiple URLs, preview a playlist and queue parallel downloads.
- Save audio as M4A, MP3, Opus, FLAC, WAV or AIFF; edit metadata and artwork.
- Estimate BPM locally and organize songs into tempo folders such as
  `BPM/120-129 BPM/Artist/Album/song.m4a`.
- Browse and play a SQLite catalog with artists, albums and playlists.
- Import existing collections without rewriting their files.
- Save additional SHA-256-verified copies to folders you choose, including a
  mounted NAS share. Existing different files are never overwritten.
- Retry a missing extra copy without downloading the song again.

Tempo detection is an estimate, including possible half/double-time errors.
Edit BPM manually when needed. Failed detection uses `Unknown BPM`.
**Organize by BPM** makes verified copies of older songs and retains originals.

## Install and run

Use Python 3.12 or newer and install FFmpeg separately, with both `ffmpeg` and
`ffprobe` on PATH. No FFmpeg executable is redistributed here.

Windows PowerShell, from this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\python.exe -m src.main
```

Or double-click **Start Music Library.bat** after installing Python and FFmpeg.

Linux/macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m src.main
```

Linux needs the Qt platform libraries appropriate to its desktop environment.
CI installs GL, EGL, OpenGL and XKB dependencies and runs Qt offscreen.

## Browser companion

The app starts its companion at `http://127.0.0.1:8787`. Web-only mode:

```powershell
.\.venv\Scripts\python.exe -m src.main --web-only
```

It has **no authentication**. Keep the default loopback binding. If you choose
LAN access, restrict access to trusted devices using your own network controls;
do not expose it to the public internet. No network settings are changed by
this project.

The desktop app processes queued downloads. Web-only mode can browse the
catalog and enqueue jobs, but does not run a headless download worker.

## Where songs go

Source runs default to `music/` under this checkout; packaged Windows runs
default to the current user's Music folder. Settings lets you choose the main
library and **Also save songs to** extra folders, separated by semicolons.
Extra folders must already exist. No NAS address or credentials are supplied.

Portable defaults are in `config/default.yaml`. Optional `config/local.yaml`
and `.env` are ignored. For example, to use an already-mounted extra folder:

```yaml
paths:
  music_root: music
  copy_roots:
    - /path/to/your/mounted/music-folder
```

Restart after changing config. If a copy destination is unavailable, the local
song remains and the job reports the failure; reconnect and retry to repair it.
Copies are not a substitute for backups. Never delete an old build directory
if it holds your catalog or songs; retain it and configure read-only repair
roots before migrating.

## Development and Windows packaging

```sh
make check
```

On Windows without Make:

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest
```

Build on Windows with `scripts/build.ps1`. Output:
`dist-bpm/MusicLibrary/MusicLibrary.exe`. FFmpeg stays an external dependency.
No prebuilt application download is included in this initial source release.

Hosted GitHub CI runs lint, fixture-based tests and an isolated bootstrap;
it does not download YouTube content, deploy anything or access a home network.

## Source and safety

This standalone snapshot is maintained alongside the original app in a
private Home-Lab monorepo. `SOURCE-MANIFEST.json` records source file hashes.
Local config, audio, catalogs, logs, caches, executables and monorepo history
are excluded. Future snapshots use the private reviewed exporter.

Contributors can install the checked-origin/gitleaks pre-push hook with
`python tools/install_push_hook.py` (requires Git and gitleaks on PATH).
No secrets or runtime data belong in a commit. See [AGENTS.md](AGENTS.md).

## License

MIT, with the original copyright notice retained in [LICENSE](LICENSE).
