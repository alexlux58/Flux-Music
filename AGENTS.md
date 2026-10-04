# Agent instructions — Flux Music

This is a generated standalone source snapshot. Upstream development remains
in `services/music-library/` of the private Home-Lab project. Refresh snapshots
with its reviewed exporter; do not copy local settings or source history.

- Run `make check` before publishing. Tests use temporary fixture catalogs;
  never inspect or modify a user's songs, database, local config or secrets.
- UI/web code goes through services and the database repository. No shell
  interpolation with untrusted input, DRM bypasses or credential collection.
- FFmpeg is external. Review licenses before redistributing binaries.
- Keep the unauthenticated web companion on loopback by default.
- GitHub runs hosted checks only, without secrets or deployment access.
- Agent pushes are authorized only to origin at the exact URL
  `https://github.com/alexlux58/Flux-Music.git`, after checks and with the
  pre-push gitleaks guard. Never force, delete refs, mirror, bypass hooks or
  push to another remote/URL. Install `python tools/install_push_hook.py`.
- Retain the MIT copyright notice. Never commit runtime audio, SQLite data,
  logs, caches, local overrides, credentials or packaged executables.
- Maintain the technical walkthrough in `docs/walkthrough/flux-music-technical-walkthrough.md.in`.
  Generate its readable Markdown and PDF with `tools/docs-build/build.py`;
  check excerpt hashes and diagram provenance, and visually review PDF pages.
  Never hand-edit generated Markdown/PDF or blindly accept changed excerpts.
  Run `python tools/docs-build/build.py --check` alongside application checks.
