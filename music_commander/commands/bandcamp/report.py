"""Bandcamp HTML report with local download server."""

from __future__ import annotations

import json
import logging
import signal
import threading
import time
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import click
from jinja2 import Template
from sqlalchemy.orm import Session

from music_commander.bandcamp.client import BandcampClient
from music_commander.bandcamp.cookies import get_session_cookie, validate_cookie
from music_commander.bandcamp.matcher import MatchResult, MatchTier, batch_match
from music_commander.cache.models import (
    BandcampRelease,
    BandcampSyncState,
    BandcampTrack,
    CacheTrack,
)
from music_commander.cache.session import get_cache_session
from music_commander.cli import pass_context
from music_commander.commands.bandcamp import (
    EXIT_AUTH_ERROR,
    EXIT_MATCH_ERROR,
    EXIT_SUCCESS,
    EXIT_SYNC_ERROR,
    cli,
)
from music_commander.exceptions import BandcampAuthError, BandcampError
from music_commander.utils.output import error, info, success

logger = logging.getLogger(__name__)

_AUTO_SHUTDOWN_SECONDS = 30 * 60  # 30 minutes
_SHUTDOWN_CHECK_INTERVAL = 60  # check every 60s


# ---------------------------------------------------------------------------
# T036 – HTML Jinja2 template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bandcamp Collection Report</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
         "Helvetica Neue", Arial, sans-serif; background: #f5f5f5; color: #333;
         padding: 2rem; max-width: 1200px; margin: 0 auto; }
  h1 { margin-bottom: 0.5rem; }
  .meta { color: #666; margin-bottom: 1.5rem; font-size: 0.9rem; }
  .controls { margin-bottom: 1rem; display: flex; gap: 1rem; align-items: center; }
  .controls input { padding: 0.4rem 0.8rem; border: 1px solid #ccc;
                    border-radius: 4px; font-size: 0.9rem; width: 300px; }
  .controls select { padding: 0.4rem; border: 1px solid #ccc; border-radius: 4px; }
  table { width: 100%; border-collapse: collapse; background: #fff;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  th { background: #2d2d2d; color: #fff; padding: 0.6rem 0.8rem;
       text-align: left; font-size: 0.85rem; }
  td { padding: 0.5rem 0.8rem; border-bottom: 1px solid #eee; font-size: 0.85rem; }
  tr:hover { background: #f9f9f9; }
  .match-exact { color: #2e7d32; font-weight: bold; }
  .match-high { color: #f57f17; }
  .match-low { color: #e65100; }
  .match-none { color: #999; }
  a.dl-link { color: #1565c0; text-decoration: none; cursor: pointer; }
  a.dl-link:hover { text-decoration: underline; }
  .status { display: inline-block; padding: 0.1rem 0.4rem; border-radius: 3px;
            font-size: 0.75rem; }
  .status.resolving { background: #fff3e0; color: #e65100; }
  .status.error { background: #ffebee; color: #c62828; }
  .hidden { display: none; }
  .summary { margin-top: 1rem; color: #666; font-size: 0.85rem; }
</style>
</head>
<body>
<h1>Bandcamp Collection Report</h1>
<div class="meta">
  Generated: {{ generated_at }} | Format: {{ encoding }} |
  Total: {{ releases | length }} releases
  {% if server_url %}| Server: <code>{{ server_url }}</code>{% endif %}
</div>

<div class="controls">
  <input type="text" id="search" placeholder="Filter by artist or album..."
         oninput="filterRows()">
  <select id="matchFilter" onchange="filterRows()">
    <option value="all">All</option>
    <option value="matched">Matched</option>
    <option value="unmatched">Unmatched</option>
  </select>
</div>

<table>
<thead>
<tr>
  <th>#</th><th>Artist</th><th>Album</th><th>Purchased</th>
  <th>Match</th><th>Score</th><th>Download</th>
</tr>
</thead>
<tbody id="releaseTable">
{% for r in releases %}
<tr data-artist="{{ r.band_name | lower }}"
    data-album="{{ r.album_title | lower }}"
    data-matched="{{ 'yes' if r.match_tier != 'none' else 'no' }}">
  <td>{{ loop.index }}</td>
  <td>{{ r.band_name }}</td>
  <td>{{ r.album_title }}</td>
  <td>{{ r.purchase_date or '' }}</td>
  <td><span class="match-{{ r.match_tier }}">{{ r.match_tier }}</span></td>
  <td>{{ r.match_score }}</td>
  <td>
    {% if server_url and r.sale_item_id and r.has_redownload %}
    <a class="dl-link" href="#"
       onclick="downloadRelease({{ r.sale_item_id }}, '{{ encoding }}', this); return false;">
       Download</a>
    {% elif r.has_redownload %}
    <span class="match-none">start server</span>
    {% else %}
    <span class="match-none">N/A</span>
    {% endif %}
  </td>
</tr>
{% endfor %}
</tbody>
</table>

<div class="summary" id="summary"></div>

<script>
const SERVER_URL = {{ server_url | tojson }};

function filterRows() {
  const query = document.getElementById('search').value.toLowerCase();
  const matchFilter = document.getElementById('matchFilter').value;
  const rows = document.querySelectorAll('#releaseTable tr');
  let visible = 0;
  rows.forEach(row => {
    const artist = row.dataset.artist || '';
    const album = row.dataset.album || '';
    const matched = row.dataset.matched;
    let show = true;
    if (query && !artist.includes(query) && !album.includes(query)) show = false;
    if (matchFilter === 'matched' && matched !== 'yes') show = false;
    if (matchFilter === 'unmatched' && matched !== 'no') show = false;
    row.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  document.getElementById('summary').textContent = visible + ' of ' + rows.length + ' releases shown';
}

function downloadRelease(saleItemId, encoding, link) {
  if (!SERVER_URL) {
    alert('Report server is not running. Start with: bandcamp report --format ' + encoding);
    return;
  }
  const oldText = link.textContent;
  link.innerHTML = '<span class="status resolving">Resolving...</span>';
  const url = SERVER_URL + '/download/' + saleItemId + '/' + encoding;
  fetch(url)
    .then(resp => {
      if (resp.ok) {
        return resp.json().then(data => {
          if (data.url) {
            window.open(data.url, '_blank');
          }
          link.textContent = oldText;
        });
      } else {
        return resp.text().then(text => {
          link.innerHTML = '<span class="status error">' + (text || 'Failed') + '</span>';
          setTimeout(() => { link.textContent = oldText; }, 5000);
        });
      }
    })
    .catch(err => {
      link.innerHTML = '<span class="status error">Server unavailable</span>';
      setTimeout(() => { link.textContent = oldText; }, 5000);
    });
}

filterRows();
</script>
</body>
</html>
""")


# ---------------------------------------------------------------------------
# T037 – Local HTTP server
# ---------------------------------------------------------------------------


class _DownloadHandler(BaseHTTPRequestHandler):
    """HTTP handler that resolves fresh download URLs."""

    client: BandcampClient
    release_map: dict[int, BandcampRelease]
    last_request_time: float  # shared mutable via class attr

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")

        # GET /download/<sale_item_id>/<encoding>
        if len(parts) == 3 and parts[0] == "download":
            self._handle_download(parts[1], parts[2])
            return

        # GET /health
        if parts == ["health"]:
            self._respond(200, "ok")
            return

        self._respond(404, "Not found")

    def _handle_download(self, sale_item_id_str: str, encoding: str) -> None:
        _DownloadHandler.last_request_time = time.time()

        try:
            sale_item_id = int(sale_item_id_str)
        except ValueError:
            self._respond(400, "Invalid sale_item_id")
            return

        release = self.release_map.get(sale_item_id)
        if release is None:
            self._respond(404, "Release not found")
            return

        if not release.redownload_url:
            self._respond(404, "No redownload URL for this release")
            return

        try:
            url = self.client.resolve_download_url(release.redownload_url, encoding)
        except BandcampError as e:
            self._respond(502, str(e))
            return

        # Return JSON with the resolved URL so JS can open it directly
        payload = json.dumps({"url": url}).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _respond(self, code: int, message: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(message.encode())

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("ReportServer: %s", format % args)


class ReportServer:
    """Local HTTP server for resolving fresh Bandcamp download URLs."""

    def __init__(
        self,
        client: BandcampClient,
        release_map: dict[int, BandcampRelease],
    ) -> None:
        handler_class = type(
            "_BoundHandler",
            (_DownloadHandler,),
            {
                "client": client,
                "release_map": release_map,
                "last_request_time": time.time(),
            },
        )
        self._server = HTTPServer(("127.0.0.1", 0), handler_class)
        self._handler_class = handler_class
        self._thread: threading.Thread | None = None
        self._shutdown_thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        """Start the server in a background thread."""
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._start_auto_shutdown()

    def _start_auto_shutdown(self) -> None:
        """Start background thread that shuts down server after inactivity."""

        def _checker() -> None:
            while True:
                time.sleep(_SHUTDOWN_CHECK_INTERVAL)
                elapsed = time.time() - self._handler_class.last_request_time
                if elapsed >= _AUTO_SHUTDOWN_SECONDS:
                    logger.info(
                        "Auto-shutting down report server after %d min inactivity",
                        _AUTO_SHUTDOWN_SECONDS // 60,
                    )
                    self._server.shutdown()
                    return

        self._shutdown_thread = threading.Thread(target=_checker, daemon=True)
        self._shutdown_thread.start()

    def shutdown(self) -> None:
        self._server.shutdown()

    def serve_forever(self) -> None:
        """Block until server is shut down (for foreground use)."""
        self._start_auto_shutdown()
        self._server.serve_forever()


# ---------------------------------------------------------------------------
# T035 – Report CLI subcommand
# ---------------------------------------------------------------------------


@cli.command("report")
@click.argument("query", nargs=-1)
@click.option(
    "--format",
    "-f",
    "fmt",
    default=None,
    help="Download format for report links (default from config).",
)
@click.option(
    "--output",
    "-o",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("bandcamp-report.html"),
    help="Output HTML file (default: bandcamp-report.html).",
)
@click.option(
    "--unmatched",
    is_flag=True,
    default=False,
    help="Only show releases without local matches.",
)
@click.option(
    "--no-server",
    is_flag=True,
    default=False,
    help="Generate HTML without starting the download server.",
)
@pass_context
def report(
    ctx: object,
    query: tuple[str, ...],
    fmt: str | None,
    output_path: Path,
    unmatched: bool,
    no_server: bool,
) -> None:
    """Generate an HTML report of your Bandcamp collection.

    Starts a local server that resolves fresh download URLs when
    links in the report are clicked.

    Examples:

        bandcamp report --format flac

        bandcamp report --unmatched --no-server

        bandcamp report radiohead --output radiohead.html
    """
    config = ctx.config  # type: ignore[attr-defined]
    repo_path = config.music_repo

    if not repo_path.exists():
        error(f"Music repository not found: {repo_path}")
        raise SystemExit(EXIT_MATCH_ERROR)

    if fmt is None:
        fmt = config.bandcamp_default_format

    # Authenticate
    try:
        cookie = get_session_cookie(config)
        fan_id, _username = validate_cookie(cookie)
    except BandcampAuthError as e:
        error(str(e))
        raise SystemExit(EXIT_AUTH_ERROR)

    client = BandcampClient(cookie, fan_id)

    try:
        with get_cache_session(repo_path) as session:
            sync_state = session.query(BandcampSyncState).filter_by(id=1).first()
            if sync_state is None:
                error("No Bandcamp collection data found. Run 'bandcamp sync' first.")
                raise SystemExit(EXIT_SYNC_ERROR)

            # Load releases and compute matches
            releases_data = _build_report_data(session, query, unmatched)

            if not releases_data:
                error("No releases to report after filtering.")
                raise SystemExit(EXIT_MATCH_ERROR)

            # Build release map for server
            release_map = {r.sale_item_id: r for r in session.query(BandcampRelease).all()}

            # Start server if requested
            server: ReportServer | None = None
            server_url: str | None = None
            if not no_server:
                server = ReportServer(client, release_map)
                server.start()
                server_url = server.url

            # Render HTML
            html = _HTML_TEMPLATE.render(
                generated_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                encoding=fmt,
                server_url=server_url,
                releases=releases_data,
            )

            output_path.write_text(html, encoding="utf-8")
            success(f"Report written to {output_path}")

            if server:
                info(f"Download server running at {server_url}")
                info("Press Ctrl+C to stop the server.")
                info(
                    f"Server will auto-shutdown after {_AUTO_SHUTDOWN_SECONDS // 60} min inactivity."
                )

                # Handle SIGINT gracefully
                def _signal_handler(sig: int, frame: Any) -> None:
                    info("\nShutting down server...")
                    if server:
                        server.shutdown()

                signal.signal(signal.SIGINT, _signal_handler)

                # Block until server stops
                try:
                    while server._thread and server._thread.is_alive():
                        server._thread.join(timeout=1)
                except KeyboardInterrupt:
                    server.shutdown()

                info("Server stopped.")

    except SystemExit:
        raise
    except BandcampError as e:
        error(str(e))
        raise SystemExit(EXIT_MATCH_ERROR)

    raise SystemExit(EXIT_SUCCESS)


# ---------------------------------------------------------------------------
# T040 – Report filtering & data assembly
# ---------------------------------------------------------------------------


def _build_report_data(
    session: Session,
    query: tuple[str, ...],
    unmatched_only: bool,
) -> list[dict[str, Any]]:
    """Build the template data for all releases, with match info."""
    bc_releases = session.query(BandcampRelease).all()
    local_tracks = session.query(CacheTrack).all()
    bc_tracks = session.query(BandcampTrack).all()

    # Run matching to get match status
    match_results = batch_match(local_tracks, bc_releases, bc_tracks, threshold=60)
    match_by_bc_id: dict[int, MatchResult] = {}
    for mr in match_results:
        # Keep best match per BC release
        existing = match_by_bc_id.get(mr.bc_sale_item_id)
        if existing is None or mr.score > existing.score:
            match_by_bc_id[mr.bc_sale_item_id] = mr

    query_str = " ".join(query).lower() if query else ""

    result: list[dict[str, Any]] = []
    for r in bc_releases:
        # Filter by query
        if query_str:
            if query_str not in r.band_name.lower() and query_str not in r.album_title.lower():
                continue

        mr = match_by_bc_id.get(r.sale_item_id)
        tier = mr.tier.value if mr else "none"
        score = f"{mr.score:.0f}" if mr else ""

        # Filter unmatched only
        if unmatched_only and mr is not None:
            continue

        result.append(
            {
                "sale_item_id": r.sale_item_id,
                "band_name": r.band_name,
                "album_title": r.album_title,
                "purchase_date": r.purchase_date or "",
                "match_tier": tier,
                "match_score": score,
                "has_redownload": bool(r.redownload_url),
            }
        )

    return result
