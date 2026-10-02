"""FastAPI companion for any-device access on LAN/VPN."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.app import AppContext
from src.database.repository import LibraryRepository
from src.utils.validation import parse_url_list, validate_url


class EnqueueRequest(BaseModel):
    url: str = Field(min_length=8)
    title: str | None = None


class BulkEnqueueRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)
    text: str | None = None


def create_web_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title=ctx.config.app.name, version=ctx.config.app.version)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        checks = [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in ctx.diagnostics()]
        return {"status": "ok", "checks": checks}

    @app.get("/api/tracks")
    def tracks(q: str = "", limit: int = 100) -> list[dict[str, Any]]:
        session = ctx.session()
        repo = LibraryRepository(session)
        try:
            rows = repo.search_tracks(q, limit=limit)
            return [
                {
                    "id": t.id,
                    "uuid": t.uuid,
                    "title": t.title,
                    "artist": t.artist.name if t.artist else None,
                    "album": t.album.title if t.album else None,
                    "duration": t.duration_seconds,
                    "codec": t.codec,
                    "bitrate": t.bitrate,
                    "bpm": t.bpm,
                    "date_added": t.date_added.isoformat() if t.date_added else None,
                }
                for t in rows
            ]
        finally:
            session.close()

    @app.get("/api/downloads")
    def downloads() -> list[dict[str, Any]]:
        session = ctx.session()
        repo = LibraryRepository(session)
        try:
            return [
                {
                    "id": j.id,
                    "title": j.title,
                    "artist": j.artist,
                    "status": j.status,
                    "progress": j.progress,
                    "speed": j.speed,
                    "eta": j.eta,
                    "stage": j.stage,
                    "error": j.error_message,
                }
                for j in repo.list_downloads()
            ]
        finally:
            session.close()

    @app.post("/api/downloads")
    def enqueue(body: EnqueueRequest) -> dict[str, Any]:
        try:
            url = validate_url(body.url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session = ctx.session()
        repo = LibraryRepository(session)
        try:
            job = repo.create_download_job(url=url, title=body.title)
            repo.commit()
            return {"id": job.id, "status": job.status}
        finally:
            session.close()

    @app.post("/api/downloads/bulk")
    def enqueue_bulk(body: BulkEnqueueRequest) -> dict[str, Any]:
        raw = body.urls
        if body.text:
            from_text, _invalid = parse_url_list(body.text)
            raw = [*raw, *from_text]
        valid: list[str] = []
        invalid: list[str] = []
        seen: set[str] = set()
        for item in raw:
            try:
                url = validate_url(item)
            except ValueError:
                invalid.append(item)
                continue
            if url not in seen:
                seen.add(url)
                valid.append(url)
        if not valid:
            raise HTTPException(status_code=400, detail="No valid URLs provided")
        session = ctx.session()
        repo = LibraryRepository(session)
        try:
            ids = [repo.create_download_job(url=url).id for url in valid]
            repo.commit()
            return {
                "queued": len(ids),
                "ids": ids,
                "skipped_invalid": len(invalid),
                "status": "queued",
            }
        finally:
            session.close()

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{ctx.config.app.name}</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{
      font-family: Segoe UI, system-ui, sans-serif;
      margin: 0; background:#070B14; color:#E8EEF7;
    }}
    header {{ padding: 1rem 1.25rem; background:#0B1220; border-bottom:1px solid #1B2A44; }}
    header strong {{ color:#22D3EE; }}
    main {{ padding: 1.25rem; max-width: 960px; margin: 0 auto; }}
    input, button {{ font: inherit; padding: .7rem .9rem; border-radius: 10px; border:0; }}
    input {{ width: min(100%, 520px); background:#0F172A; color:#fff; border:1px solid #24324A; }}
    button {{ background:#22D3EE; color:#04202A; font-weight:700; cursor:pointer; }}
    .card {{ background:#0B1220; border-radius:12px; padding:1rem; margin-top:1rem; border:1px solid #1B2A44; }}
    table {{ width:100%; border-collapse: collapse; }}
    td, th {{ text-align:left; padding:.55rem; border-bottom:1px solid #1B2A44; }}
    .muted {{ color:#8BA3C7; }}
  </style>
</head>
<body>
  <header>
    <strong>{ctx.config.app.name}</strong>
    <div class="muted">Any-device companion UI · authorized downloads only</div>
  </header>
  <main>
    <section class="card">
      <h2>Queue downloads</h2>
      <p class="muted">Paste one URL per line (authorized downloads only). Desktop app runs them in parallel.</p>
      <form id="form">
        <textarea id="urls" rows="6" placeholder="https://music.youtube.com/watch?v=...&#10;https://www.youtube.com/watch?v=..." required
          style="width:100%;background:#0F172A;color:#fff;border:1px solid #24324A;border-radius:12px;padding:.7rem;font:inherit;"></textarea>
        <div style="margin-top:.75rem"><button type="submit">Queue all</button></div>
      </form>
      <p id="msg" class="muted"></p>
    </section>
    <section class="card">
      <h2>Library</h2>
      <input id="q" placeholder="Search…" />
      <table><thead><tr><th>Title</th><th>Artist</th><th>Album</th></tr></thead>
      <tbody id="tracks"></tbody></table>
    </section>
    <section class="card">
      <h2>Downloads</h2>
      <table><thead><tr><th>Title</th><th>Status</th><th>Progress</th><th>Stage</th></tr></thead>
      <tbody id="jobs"></tbody></table>
    </section>
  </main>
  <script>
    async function loadTracks() {{
      const q = document.getElementById('q').value;
      const rows = await fetch('/api/tracks?q=' + encodeURIComponent(q)).then(r => r.json());
      document.getElementById('tracks').innerHTML = rows.map(t =>
        `<tr><td>${{t.title}}</td><td>${{t.artist||''}}</td><td>${{t.album||''}}</td></tr>`
      ).join('');
    }}
    async function loadJobs() {{
      const rows = await fetch('/api/downloads').then(r => r.json());
      document.getElementById('jobs').innerHTML = rows.map(j =>
        `<tr><td>${{j.title||'—'}}</td><td>${{j.status}}</td><td>${{Math.round(j.progress)}}%</td><td>${{j.stage||''}}</td></tr>`
      ).join('');
    }}
    document.getElementById('form').addEventListener('submit', async (e) => {{
      e.preventDefault();
      const text = document.getElementById('urls').value;
      const res = await fetch('/api/downloads/bulk', {{
        method:'POST', headers:{{'Content-Type':'application/json'}},
        body: JSON.stringify({{urls: [], text}})
      }});
      const data = await res.json();
      document.getElementById('msg').textContent = res.ok
        ? ('Queued ' + data.queued + ' URL(s)' + (data.skipped_invalid ? (' · skipped ' + data.skipped_invalid + ' invalid') : '') + ' — desktop app processes in parallel')
        : (data.detail || 'Failed');
      loadJobs();
    }});
    document.getElementById('q').addEventListener('input', loadTracks);
    loadTracks(); loadJobs(); setInterval(loadJobs, 4000);
  </script>
</body>
</html>"""

    return app


def start_web_server(ctx: AppContext) -> None:
    import threading

    import uvicorn

    app = create_web_app(ctx)
    # log_config=None: uvicorn's ColorFormatter calls sys.stdout.isatty(), which
    # crashes under pythonw / PyInstaller windowed builds where stdout is None.
    config = uvicorn.Config(
        app,
        host=ctx.config.ui.web_host,
        port=ctx.config.ui.web_port,
        log_level="warning",
        log_config=None,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="music-library-web", daemon=True)
    thread.start()
