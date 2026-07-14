#!/usr/bin/env python3
"""
webapp.py — lightweight web dashboard for NESTfetch (Phase 5).

A ZERO-dependency dashboard built on Python's standard-library http.server.
It reads the SQLite scrape database and lets you:
  * browse / search the scraped catalogue (filter by site & category);
  * see summary stats, recent scrape runs, and tracked dead links;
  * kick off a scrape or a link-check straight from the browser.

No Flask / FastAPI / Django — pure standard library, so it runs anywhere the
scraper does, offline, with nothing extra to install.

Design note: the data-producing functions (stats_payload / games_payload /
runs_payload / dead_links_payload / sites_payload) are deliberately separated
from the HTTP layer so they can be unit-tested against a temp database with no
network or sockets involved. The HTTP handler is a thin shell around them.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import urlparse, parse_qs

import database as db
from logger import log, Colours

try:  # non-secret structural defaults live in config.py
    from config import WEB_DEFAULT_HOST, WEB_DEFAULT_PORT
except Exception:  # pragma: no cover - fallback if config lacks them
    WEB_DEFAULT_HOST = "127.0.0.1"
    WEB_DEFAULT_PORT = 8787

APP_VERSION = "4.4"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _row_dict(row) -> dict:
    return {k: row[k] for k in row.keys()}


# ══ Data payloads (pure, testable) ══════════════════
def stats_payload(conn) -> dict:
    """High-level counts for the dashboard header cards."""
    db.init_db(conn)

    def scalar(query: str, params=()) -> int:
        r = conn.execute(query, params).fetchone()
        return int(r[0]) if r and r[0] is not None else 0

    total_active = scalar("SELECT COUNT(*) FROM games WHERE status='active'")
    total_removed = scalar("SELECT COUNT(*) FROM games WHERE status='removed'")
    total_mirrors = scalar("SELECT COUNT(*) FROM mirrors WHERE status='active'")

    by_site = [
        {"site": r["source_site"] or "?", "count": r["c"]}
        for r in conn.execute(
            "SELECT source_site, COUNT(*) AS c FROM games WHERE status='active' "
            "GROUP BY source_site ORDER BY c DESC"
        ).fetchall()
    ]
    by_category = [
        {"category": r["category"] or "(uncategorised)", "count": r["c"]}
        for r in conn.execute(
            "SELECT category, COUNT(*) AS c FROM games WHERE status='active' "
            "GROUP BY category ORDER BY c DESC"
        ).fetchall()
    ]

    link_total = scalar("SELECT COUNT(*) FROM link_checks")
    link_active = scalar("SELECT COUNT(*) FROM link_checks WHERE status='ACTIVE'")
    link_dead = scalar("SELECT COUNT(*) FROM link_checks WHERE status='DEAD'")
    link_unknown = max(0, link_total - link_active - link_dead)

    runs_total = scalar("SELECT COUNT(*) FROM scrape_runs")
    last = conn.execute(
        "SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()

    return {
        "games_active": total_active,
        "games_removed": total_removed,
        "mirrors_active": total_mirrors,
        "by_site": by_site,
        "by_category": by_category,
        "links": {
            "total": link_total,
            "active": link_active,
            "dead": link_dead,
            "unknown": link_unknown,
        },
        "runs_total": runs_total,
        "last_run": _row_dict(last) if last else None,
        "generated_at": _now(),
    }


def games_payload(
    conn,
    site: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    active_only: bool = True,
    limit: Optional[int] = None,
) -> list:
    """Catalogue rows with per-game mirror + link-health summary."""
    db.init_db(conn)

    clauses, params = [], []
    if active_only:
        clauses.append("status='active'")
    if site:
        clauses.append("source_site=?")
        params.append(site)
    if category:
        clauses.append("category=?")
        params.append(category)
    if search:
        clauses.append("title LIKE ?")
        params.append("%" + search + "%")

    query = "SELECT * FROM games"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY title COLLATE NOCASE"
    if limit:
        query += " LIMIT ?"
        params.append(int(limit))

    rows = conn.execute(query, params).fetchall()

    # url -> status map so we can annotate each mirror's health without N+1 pain
    health = {}
    for r in conn.execute("SELECT url, status FROM link_checks").fetchall():
        if r["url"]:
            health[r["url"]] = (r["status"] or "").upper()

    games = []
    for row in rows:
        mrows = conn.execute(
            "SELECT * FROM mirrors WHERE game_id=? AND status='active' ORDER BY id",
            (row["id"],),
        ).fetchall()
        mirrors = []
        dead = active = 0
        for m in mrows:
            link = m["final_link"] or ""
            status = health.get(link) or health.get(m["redirect_url"] or "") or ""
            if status == "DEAD":
                dead += 1
            elif status == "ACTIVE":
                active += 1
            mirrors.append({
                "format": m["format"] or "N/A",
                "size": m["size"] or "N/A",
                "hoster": m["hoster"] or "Unknown",
                "final_link": link,
                "redirect_url": m["redirect_url"] or "",
                "link_status": status,
            })
        games.append({
            "title": row["title"] or "No Title",
            "source_site": row["source_site"] or "",
            "category": row["category"] or "",
            "platform": row["platform"] or "",
            "meta_size": row["meta_size"] or "",
            "meta_genre": row["meta_genre"] or "",
            "detail_url": row["detail_url"] or "",
            "mirror_count": len(mirrors),
            "active_mirrors": active,
            "dead_mirrors": dead,
            "first_seen": row["first_seen"] or "",
            "last_seen": row["last_seen"] or "",
            "mirrors": mirrors,
        })
    return games


def runs_payload(conn, limit: int = 25, site: Optional[str] = None) -> list:
    """Recent scrape runs, most recent first."""
    return [_row_dict(r) for r in db.recent_runs(conn, limit=limit, site=site)]


def dead_links_payload(conn, limit: int = 100) -> list:
    """Currently-dead links, oldest-dead first (longest-broken at the top)."""
    db.init_db(conn)
    rows = conn.execute(
        "SELECT url, hoster, link_type, http_code, detail, first_dead_at, "
        "last_checked, consecutive_dead FROM link_checks WHERE status='DEAD' "
        "ORDER BY first_dead_at ASC, id ASC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [_row_dict(r) for r in rows]


def sites_payload() -> list:
    """Adapters registered in the scraper (for the site filter dropdown)."""
    from sites.registry import available_sites
    return [
        {
            "name": m.name,
            "platform": m.platform,
            "category": m.category,
            "base_url": m.base_url,
        }
        for m in available_sites()
    ]


# ══ Background job runner (scrape / check triggered from the browser) ════
class JobRunner:
    """Runs one background job at a time and exposes its status as plain dicts."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict = {}
        self._counter = 0
        self.current: Optional[int] = None

    def is_running(self) -> bool:
        with self._lock:
            job = self._jobs.get(self.current) if self.current else None
            return bool(job and job["status"] == "running")

    def start(self, kind: str, target: Callable[[dict], dict], params: dict) -> Optional[int]:
        """Start a job; returns its id, or None if one is already running."""
        with self._lock:
            current = self._jobs.get(self.current) if self.current else None
            if current and current["status"] == "running":
                return None
            self._counter += 1
            jid = self._counter
            self._jobs[jid] = {
                "id": jid,
                "kind": kind,
                "status": "running",
                "detail": "",
                "result": None,
                "started_at": _now(),
                "finished_at": None,
            }
            self.current = jid
        thread = threading.Thread(
            target=self._run, args=(jid, target, params), daemon=True
        )
        thread.start()
        return jid

    def _run(self, jid: int, target: Callable[[dict], dict], params: dict) -> None:
        try:
            result = target(params) or {}
            with self._lock:
                self._jobs[jid]["status"] = "done"
                self._jobs[jid]["result"] = result
                self._jobs[jid]["detail"] = _summarise_result(self._jobs[jid]["kind"], result)
                self._jobs[jid]["finished_at"] = _now()
        except Exception as exc:  # pragma: no cover - defensive
            with self._lock:
                self._jobs[jid]["status"] = "error"
                self._jobs[jid]["detail"] = str(exc)
                self._jobs[jid]["finished_at"] = _now()

    def status(self, jid: Optional[int] = None) -> dict:
        with self._lock:
            if jid is None:
                jid = self.current
            job = self._jobs.get(jid) if jid else None
            return dict(job) if job else {"status": "idle"}


def _summarise_result(kind: str, result: dict) -> str:
    if kind == "scrape":
        return (
            "Scraped %s games (%s new) in %ss"
            % (result.get("games", 0), result.get("new", 0), result.get("elapsed", "?"))
        )
    if kind == "check":
        return (
            "Checked links: %s active, %s dead (%s newly dead)"
            % (result.get("active", 0), result.get("dead", 0), result.get("newly_dead", 0))
        )
    return "Done"


def scrape_params_from(data: dict, db_path: Optional[str]) -> dict:
    """Build a scraper.do_scrape() params dict from a browser request body."""
    from config import CACHE_ENABLED_DEFAULT, PER_HOST_RATE_LIMIT
    return {
        "site": data.get("site") or "switchroms",
        "search": (data.get("search") or "").strip() or None,
        "pages": int(data.get("pages") or 1),
        "format": data.get("format") or "ALL",
        "hoster": data.get("hoster") or "ALL",
        "output": data.get("output") or "both",
        "delay": float(data.get("delay") or 1.0),
        "workers": int(data.get("workers") or 5),
        "verbose": False,
        "scrape_all": bool(data.get("all") or data.get("scrape_all")),
        "no_db": False,
        "db_path": db_path,
        "use_async": False,
        "use_cache": CACHE_ENABLED_DEFAULT,
        "rate_limit": PER_HOST_RATE_LIMIT,
        "notify": bool(data.get("notify")),
        "config": data.get("config"),
    }


def check_params_from(data: dict, db_path: Optional[str]) -> dict:
    """Build a scraper.run_link_check() params dict from a browser request body."""
    from link_checker import default_csv_path
    return {
        "site": data.get("site") or "switchroms",
        "csv_path": data.get("csv_path") or str(default_csv_path()),
        "workers": int(data.get("workers") or 10),
        "delay": float(data.get("delay") or 0.0),
        "output": data.get("output"),
        "verbose": False,
        "no_db": False,
        "db_path": db_path,
        "notify": bool(data.get("notify")),
        "config": data.get("config"),
    }


def _scrape_target(params: dict) -> dict:
    import scraper
    games, summary, elapsed = scraper.do_scrape(params)
    return {
        "games": len(games),
        "new": getattr(summary, "new", 0) if summary else 0,
        "changed": getattr(summary, "changed", 0) if summary else 0,
        "elapsed": round(elapsed, 2),
    }


def _check_target(params: dict) -> dict:
    import scraper
    return scraper.run_link_check(params) or {}


# ══ HTTP layer ══════════════════════════════
def make_handler(db_path: Optional[str], jobs: JobRunner, *, allow_actions: bool = True):
    """Build a BaseHTTPRequestHandler subclass bound to a db path + job runner."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "NESTfetch/" + APP_VERSION

        def log_message(self, fmt, *args):  # keep the console clean
            log.debug("web: " + fmt, *args)

        # -- response helpers --
        def _send_json(self, obj, code: int = 200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str, code: int = 200):
            body = html.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _conn(self):
            return db.connect(db_path)

        # -- GET --
        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            def one(key):
                vals = qs.get(key)
                return vals[0] if vals else None

            try:
                if path in ("/", "/index.html"):
                    return self._send_html(INDEX_HTML)
                if path == "/api/stats":
                    conn = self._conn()
                    try:
                        return self._send_json(stats_payload(conn))
                    finally:
                        conn.close()
                if path == "/api/games":
                    conn = self._conn()
                    try:
                        games = games_payload(
                            conn, site=one("site"), category=one("category"),
                            search=one("search"),
                        )
                        return self._send_json({"games": games, "count": len(games)})
                    finally:
                        conn.close()
                if path == "/api/runs":
                    conn = self._conn()
                    try:
                        return self._send_json({"runs": runs_payload(conn)})
                    finally:
                        conn.close()
                if path == "/api/dead-links":
                    conn = self._conn()
                    try:
                        return self._send_json({"links": dead_links_payload(conn)})
                    finally:
                        conn.close()
                if path == "/api/sites":
                    return self._send_json({"sites": sites_payload()})
                if path == "/api/job":
                    return self._send_json({"job": jobs.status()})
                return self._send_json({"error": "not found"}, 404)
            except Exception as exc:  # pragma: no cover - defensive
                return self._send_json({"error": str(exc)}, 500)

        # -- POST (actions) --
        def do_POST(self):
            if not allow_actions:
                return self._send_json({"error": "actions are disabled"}, 403)
            parsed = urlparse(self.path)
            path = parsed.path
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}

            try:
                if path == "/api/scrape":
                    jid = jobs.start("scrape", _scrape_target,
                                     scrape_params_from(data, db_path))
                    if jid is None:
                        return self._send_json({"error": "a job is already running"}, 409)
                    return self._send_json({"job": jobs.status(jid)})
                if path == "/api/check":
                    jid = jobs.start("check", _check_target,
                                     check_params_from(data, db_path))
                    if jid is None:
                        return self._send_json({"error": "a job is already running"}, 409)
                    return self._send_json({"job": jobs.status(jid)})
                return self._send_json({"error": "not found"}, 404)
            except Exception as exc:  # pragma: no cover - defensive
                return self._send_json({"error": str(exc)}, 500)

    return Handler


def serve(
    host: str = WEB_DEFAULT_HOST,
    port: int = WEB_DEFAULT_PORT,
    db_path: Optional[str] = None,
    *,
    open_browser: bool = False,
    allow_actions: bool = True,
) -> None:
    """Start the dashboard HTTP server (blocks until Ctrl-C)."""
    jobs = JobRunner()
    handler = make_handler(db_path, jobs, allow_actions=allow_actions)
    httpd = ThreadingHTTPServer((host, port), handler)
    url = "http://%s:%d/" % (host, port)

    print(f"\n{Colours.GREEN}{Colours.BOLD}╔══ NESTfetch dashboard ═══════════════════╗{Colours.RESET}")
    print(f"  {Colours.WHITE}Serving at{Colours.RESET} {Colours.CYAN}{url}{Colours.RESET}")
    print(f"  {Colours.GREY}Database:{Colours.RESET} {db_path or db.default_db_path()}")
    print(f"  {Colours.GREY}Press Ctrl-C to stop.{Colours.RESET}")
    print(f"{Colours.GREEN}{Colours.BOLD}╚══════════════════════════════╗{Colours.RESET}\n")

    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{Colours.YELLOW}Dashboard stopped.{Colours.RESET}")
    finally:
        httpd.server_close()


# ══ Single-page dashboard (inline HTML/CSS/JS, no external assets) ══════
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NESTfetch Dashboard</title>
<style>
:root {
  --bg: #0f1117;
  --panel: #171a23;
  --panel2: #1e2230;
  --border: #2a2f3d;
  --text: #e6e8ee;
  --muted: #8b90a0;
  --accent: #4f8cff;
  --green: #3fb950;
  --red: #f85149;
  --yellow: #d29922;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  font-size: 14px;
}
header {
  padding: 18px 24px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--panel);
}
header h1 { margin: 0; font-size: 18px; letter-spacing: 0.5px; }
header .sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
.wrap { padding: 20px 24px; max-width: 1200px; margin: 0 auto; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 20px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.card .n { font-size: 24px; font-weight: 700; }
.card .l { color: var(--muted); font-size: 12px; margin-top: 4px; }
.card .l.red { color: var(--red); }
.card .l.green { color: var(--green); }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
input, select, button {
  background: var(--panel2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
}
input { min-width: 220px; }
button { cursor: pointer; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
button.primary:hover { filter: brightness(1.1); }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.tabs { display: flex; gap: 6px; margin-bottom: 14px; border-bottom: 1px solid var(--border); }
.tab { padding: 8px 14px; cursor: pointer; color: var(--muted); border-bottom: 2px solid transparent; }
.tab.active { color: var(--text); border-bottom-color: var(--accent); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 600; position: sticky; top: 0; background: var(--panel); }
tr:hover td { background: var(--panel2); }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: 600; }
.badge.site { background: #223; color: #9db4ff; }
.badge.ok { background: rgba(63,185,80,0.15); color: var(--green); }
.badge.dead { background: rgba(248,81,73,0.15); color: var(--red); }
.badge.muted { background: #222634; color: var(--muted); }
.status { color: var(--muted); font-size: 12px; margin-left: auto; }
.hidden { display: none; }
.empty { color: var(--muted); padding: 30px; text-align: center; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
</style>
</head>
<body>
<header>
  <div>
    <h1>🪹 NESTfetch Dashboard</h1>
    <div class="sub">Multi-site game-download scraper &middot; v4.4</div>
  </div>
  <div class="status" id="gen"></div>
</header>
<div class="wrap">
  <div class="cards" id="cards"></div>

  <div class="toolbar">
    <input id="search" placeholder="Search games by title...">
    <select id="site"><option value="">All sites</option></select>
    <select id="category"><option value="">All categories</option></select>
    <button class="primary" id="btnScrape">Run scrape</button>
    <button id="btnCheck">Check links</button>
    <span class="status" id="jobStatus"></span>
  </div>

  <div class="tabs">
    <div class="tab active" data-tab="catalogue">Catalogue</div>
    <div class="tab" data-tab="history">History</div>
    <div class="tab" data-tab="dead">Dead links</div>
  </div>

  <div id="catalogue"></div>
  <div id="history" class="hidden"></div>
  <div id="dead" class="hidden"></div>
</div>
<script>
const $ = (s) => document.querySelector(s);
let pollTimer = null;

async function getJSON(url) {
  const r = await fetch(url);
  return await r.json();
}
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  });
  return await r.json();
}
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadStats() {
  const s = await getJSON("/api/stats");
  $("#gen").textContent = "Updated " + (s.generated_at || "");
  const last = s.last_run ? (esc(s.last_run.started_at) + " (" + esc(s.last_run.site) + ")") : "never";
  const cards = [
    ["games_active", s.games_active, "Active games", ""],
    ["mirrors", s.mirrors_active, "Download mirrors", ""],
    ["dead", s.links.dead, "Dead links", "red"],
    ["active", s.links.active, "Active links", "green"],
    ["runs", s.runs_total, "Scrape runs", ""]
  ];
  let html = "";
  for (const c of cards) {
    html += '<div class="card"><div class="n">' + esc(c[1]) +
            '</div><div class="l ' + c[3] + '">' + esc(c[2]) + '</div></div>';
  }
  html += '<div class="card"><div class="n" style="font-size:14px;padding-top:6px">' +
          last + '</div><div class="l">Last run</div></div>';
  $("#cards").innerHTML = html;

  const catSel = $("#category");
  if (catSel.options.length <= 1 && s.by_category) {
    for (const c of s.by_category) {
      const o = document.createElement("option");
      o.value = c.category; o.textContent = c.category + " (" + c.count + ")";
      catSel.appendChild(o);
    }
  }
}

async function loadSites() {
  const d = await getJSON("/api/sites");
  const sel = $("#site");
  for (const s of (d.sites || [])) {
    const o = document.createElement("option");
    o.value = s.name; o.textContent = s.name + " \u2014 " + s.platform;
    sel.appendChild(o);
  }
}

async function loadGames() {
  const q = new URLSearchParams();
  if ($("#search").value) q.set("search", $("#search").value);
  if ($("#site").value) q.set("site", $("#site").value);
  if ($("#category").value) q.set("category", $("#category").value);
  const d = await getJSON("/api/games?" + q.toString());
  const games = d.games || [];
  if (!games.length) {
    $("#catalogue").innerHTML = '<div class="empty">No games found. Run a scrape to populate the catalogue.</div>';
    return;
  }
  let rows = "";
  for (const g of games) {
    let health = '<span class="badge muted">' + g.mirror_count + ' mirrors</span>';
    if (g.dead_mirrors > 0) health += ' <span class="badge dead">' + g.dead_mirrors + ' dead</span>';
    if (g.active_mirrors > 0) health += ' <span class="badge ok">' + g.active_mirrors + ' ok</span>';
    const title = g.detail_url
      ? '<a href="' + esc(g.detail_url) + '" target="_blank">' + esc(g.title) + '</a>'
      : esc(g.title);
    rows += '<tr><td>' + title + '</td><td><span class="badge site">' + esc(g.source_site) +
            '</span></td><td>' + esc(g.platform) + '</td><td>' + esc(g.category) +
            '</td><td>' + health + '</td></tr>';
  }
  $("#catalogue").innerHTML =
    '<table><thead><tr><th>Title</th><th>Site</th><th>Platform</th><th>Category</th><th>Mirrors</th></tr></thead><tbody>' +
    rows + '</tbody></table>';
}

async function loadHistory() {
  const d = await getJSON("/api/runs");
  const runs = d.runs || [];
  if (!runs.length) {
    $("#history").innerHTML = '<div class="empty">No scrape history yet.</div>';
    return;
  }
  let rows = "";
  for (const r of runs) {
    rows += '<tr><td>' + esc(r.id) + '</td><td class="mono">' + esc(r.started_at) +
            '</td><td><span class="badge site">' + esc(r.site) + '</span></td><td>' + esc(r.mode) +
            '</td><td>' + esc(r.games_found) + '</td><td>' + esc(r.new_count) +
            '</td><td>' + esc(r.changed_count) + '</td><td>' + esc(r.removed_count) + '</td></tr>';
  }
  $("#history").innerHTML =
    '<table><thead><tr><th>#</th><th>When (UTC)</th><th>Site</th><th>Mode</th><th>Found</th><th>New</th><th>Chg</th><th>Rem</th></tr></thead><tbody>' +
    rows + '</tbody></table>';
}

async function loadDead() {
  const d = await getJSON("/api/dead-links");
  const links = d.links || [];
  if (!links.length) {
    $("#dead").innerHTML = '<div class="empty">No dead links tracked. Run a link check to populate this.</div>';
    return;
  }
  let rows = "";
  for (const l of links) {
    rows += '<tr><td class="mono"><a href="' + esc(l.url) + '" target="_blank">' + esc(l.url) +
            '</a></td><td>' + esc(l.hoster) + '</td><td>' + esc(l.http_code) +
            '</td><td class="mono">' + esc(l.first_dead_at) + '</td><td>' + esc(l.consecutive_dead) + '</td></tr>';
  }
  $("#dead").innerHTML =
    '<table><thead><tr><th>URL</th><th>Hoster</th><th>Code</th><th>First dead (UTC)</th><th>Dead streak</th></tr></thead><tbody>' +
    rows + '</tbody></table>';
}

function setJobStatus(job) {
  const el = $("#jobStatus");
  if (!job || job.status === "idle") { el.textContent = ""; return; }
  if (job.status === "running") {
    el.textContent = "⏳ " + job.kind + " running...";
    $("#btnScrape").disabled = true;
    $("#btnCheck").disabled = true;
  } else {
    el.textContent = (job.status === "error" ? "⚠ " : "✅ ") + (job.detail || job.status);
    $("#btnScrape").disabled = false;
    $("#btnCheck").disabled = false;
  }
}

async function pollJob() {
  const d = await getJSON("/api/job");
  setJobStatus(d.job);
  if (d.job && d.job.status === "running") {
    if (!pollTimer) pollTimer = setInterval(pollJob, 2500);
  } else if (pollTimer) {
    clearInterval(pollTimer); pollTimer = null;
    loadStats(); loadGames(); loadHistory(); loadDead();
  }
}

async function runScrape() {
  const body = { site: $("#site").value || "switchroms", search: $("#search").value || null };
  const d = await postJSON("/api/scrape", body);
  if (d.error) { alert(d.error); return; }
  setJobStatus(d.job); pollJob();
}
async function runCheck() {
  const d = await postJSON("/api/check", { site: $("#site").value || "switchroms" });
  if (d.error) { alert(d.error); return; }
  setJobStatus(d.job); pollJob();
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  for (const id of ["catalogue", "history", "dead"]) {
    $("#" + id).classList.toggle("hidden", id !== name);
  }
}

document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => switchTab(t.dataset.tab)));
$("#search").addEventListener("input", () => { clearTimeout(window._st); window._st = setTimeout(loadGames, 300); });
$("#site").addEventListener("change", loadGames);
$("#category").addEventListener("change", loadGames);
$("#btnScrape").addEventListener("click", runScrape);
$("#btnCheck").addEventListener("click", runCheck);

loadStats(); loadSites(); loadGames(); loadHistory(); loadDead(); pollJob();
setInterval(loadStats, 30000);
</script>
</body>
</html>"""
