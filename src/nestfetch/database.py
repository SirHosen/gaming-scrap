#!/usr/bin/env python3
"""
database.py — SQLite persistence + scrape history for NESTfetch (Phase 2).

Every scrape is recorded into a local SQLite database so NESTfetch can:
  * remember games across runs (a normalised games + mirrors schema);
  * detect what's NEW, CHANGED, or REMOVED between runs;
  * track link health over time — including WHEN a link first went dead;
  * export straight from the database (no re-scrape needed).

Pure standard library (sqlite3) — no extra dependencies.

Schema
  scrape_runs  one row per scrape (site, mode, timestamps, diff counts)
  games        one row per game, keyed by (source_site, detail_url)
  mirrors      one row per download mirror, linked to a game
  link_checks  one row per link URL, with first_dead_at / last_active_at history
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from nestfetch.config import OUTPUT_DIR, DB_FILENAME
from nestfetch.logger import log, Colours
from nestfetch.models import Game, Mirror


# ── Helpers ──────────────────────────────────
def _now() -> str:
    """Current UTC timestamp as a sortable 'YYYY-MM-DD HH:MM:SS' string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def default_db_path() -> Path:
    return Path(OUTPUT_DIR) / DB_FILENAME


# ── Connection / schema ──────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS scrape_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    site          TEXT NOT NULL,
    mode          TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    games_found   INTEGER DEFAULT 0,
    new_count     INTEGER DEFAULT 0,
    changed_count INTEGER DEFAULT 0,
    removed_count INTEGER DEFAULT 0,
    mirror_count  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS games (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_site  TEXT NOT NULL,
    detail_url   TEXT NOT NULL,
    title        TEXT,
    category     TEXT,
    platform     TEXT,
    meta_size    TEXT,
    meta_genre   TEXT,
    content_hash TEXT,
    status       TEXT DEFAULT 'active',
    first_seen   TEXT,
    last_seen    TEXT,
    last_changed TEXT,
    times_seen   INTEGER DEFAULT 1,
    UNIQUE (source_site, detail_url)
);

CREATE TABLE IF NOT EXISTS mirrors (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id      INTEGER NOT NULL,
    format       TEXT,
    size         TEXT,
    hoster       TEXT,
    redirect_url TEXT,
    final_link   TEXT,
    raw_text     TEXT,
    status       TEXT DEFAULT 'active',
    first_seen   TEXT,
    last_seen    TEXT,
    UNIQUE (game_id, format, hoster, final_link),
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS link_checks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    url              TEXT NOT NULL UNIQUE,
    hoster           TEXT,
    link_type        TEXT,
    resolved_link    TEXT,
    status           TEXT,
    http_code        TEXT,
    detail           TEXT,
    first_checked    TEXT,
    last_checked     TEXT,
    last_active_at   TEXT,
    first_dead_at    TEXT,
    times_checked    INTEGER DEFAULT 0,
    consecutive_dead INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_games_site   ON games(source_site);
CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);
CREATE INDEX IF NOT EXISTS idx_mirrors_game ON mirrors(game_id);
CREATE INDEX IF NOT EXISTS idx_link_status  ON link_checks(status);
"""


def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite database and return a connection."""
    path = Path(db_path) if db_path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables + indices if they don't already exist (idempotent)."""
    conn.executescript(_SCHEMA)
    conn.commit()


# ── Change detection ──────────────────────────
def _game_hash(game: Game) -> str:
    """Stable fingerprint of a game's meaningful fields (title, meta, mirrors)."""
    parts = [
        (game.title or "").strip(),
        (game.meta_size or "").strip(),
        (game.meta_genre or "").strip(),
    ]
    parts.extend(sorted(
        f"{m.format}|{m.size}|{m.hoster}|{m.final_link}|{m.redirect_url}"
        for m in game.mirrors
    ))
    blob = "\x1f".join(parts)
    return hashlib.sha256(blob.encode("utf-8", "ignore")).hexdigest()


@dataclass
class RunSummary:
    """Diff outcome of a single scrape vs. what was already in the database."""
    run_id: int
    site: str
    mode: str
    total: int = 0
    new: int = 0
    changed: int = 0
    removed: int = 0
    unchanged: int = 0
    mirror_count: int = 0
    new_titles: List[str] = field(default_factory=list)
    changed_titles: List[str] = field(default_factory=list)
    removed_titles: List[str] = field(default_factory=list)


# ── Saving a scrape ─────────────────────────
def _upsert_mirrors(conn: sqlite3.Connection, game_id: int, mirrors, now: str) -> None:
    """Insert/refresh a game's mirrors; mark any that vanished as 'removed'."""
    seen = set()
    for m in mirrors:
        seen.add((m.format, m.hoster, m.final_link))
        row = conn.execute(
            "SELECT id FROM mirrors WHERE game_id=? AND format=? AND hoster=? AND final_link=?",
            (game_id, m.format, m.hoster, m.final_link),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE mirrors SET size=?, redirect_url=?, raw_text=?, status='active', last_seen=? WHERE id=?",
                (m.size, m.redirect_url, m.raw_text, now, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO mirrors (game_id, format, size, hoster, redirect_url, final_link, raw_text, status, first_seen, last_seen) "
                "VALUES (?,?,?,?,?,?,?, 'active', ?, ?)",
                (game_id, m.format, m.size, m.hoster, m.redirect_url, m.final_link, m.raw_text, now, now),
            )
    for r in conn.execute(
        "SELECT id, format, hoster, final_link FROM mirrors WHERE game_id=? AND status='active'",
        (game_id,),
    ).fetchall():
        if (r["format"], r["hoster"], r["final_link"]) not in seen:
            conn.execute("UPDATE mirrors SET status='removed' WHERE id=?", (r["id"],))


def save_scrape(
    conn: sqlite3.Connection,
    games: List[Game],
    site: str,
    mode: str = "scrape",
    detect_removed: Optional[bool] = None,
) -> RunSummary:
    """
    Persist a scrape and return a RunSummary describing new/changed/removed games.

    Removed detection only runs for full-site scrapes (mode 'all'/'full') unless
    `detect_removed` is set explicitly — a keyword search or single-page sweep
    must not mark the rest of the catalogue as removed.
    """
    init_db(conn)
    now = _now()
    if detect_removed is None:
        detect_removed = mode in ("all", "full")

    cur = conn.execute(
        "INSERT INTO scrape_runs (site, mode, started_at) VALUES (?,?,?)",
        (site, mode, now),
    )
    run_id = cur.lastrowid
    summary = RunSummary(run_id=run_id, site=site, mode=mode, total=len(games))

    current_urls = set()
    mirror_total = 0
    for g in games:
        gsite = g.source_site or site
        url = g.detail_url
        if not url:
            continue
        current_urls.add(url)
        h = _game_hash(g)
        mirror_total += len(g.mirrors)

        existing = conn.execute(
            "SELECT * FROM games WHERE source_site=? AND detail_url=?",
            (gsite, url),
        ).fetchone()

        if existing is None:
            cur = conn.execute(
                "INSERT INTO games (source_site, detail_url, title, category, platform, "
                "meta_size, meta_genre, content_hash, status, first_seen, last_seen, last_changed, times_seen) "
                "VALUES (?,?,?,?,?,?,?,?, 'active', ?, ?, ?, 1)",
                (gsite, url, g.title, g.category, g.platform, g.meta_size, g.meta_genre, h, now, now, now),
            )
            gid = cur.lastrowid
            _upsert_mirrors(conn, gid, g.mirrors, now)
            summary.new += 1
            summary.new_titles.append(g.title)
        else:
            gid = existing["id"]
            changed = (existing["content_hash"] != h) or (existing["status"] == "removed")
            if changed:
                conn.execute(
                    "UPDATE games SET title=?, category=?, platform=?, meta_size=?, meta_genre=?, "
                    "content_hash=?, status='active', last_seen=?, last_changed=?, times_seen=times_seen+1 WHERE id=?",
                    (g.title, g.category, g.platform, g.meta_size, g.meta_genre, h, now, now, gid),
                )
                _upsert_mirrors(conn, gid, g.mirrors, now)
                summary.changed += 1
                summary.changed_titles.append(g.title)
            else:
                conn.execute(
                    "UPDATE games SET last_seen=?, times_seen=times_seen+1 WHERE id=?",
                    (now, gid),
                )
                _upsert_mirrors(conn, gid, g.mirrors, now)
                summary.unchanged += 1

    if detect_removed:
        for r in conn.execute(
            "SELECT id, detail_url, title FROM games WHERE source_site=? AND status='active'",
            (site,),
        ).fetchall():
            if r["detail_url"] not in current_urls:
                conn.execute(
                    "UPDATE games SET status='removed', last_changed=? WHERE id=?",
                    (now, r["id"]),
                )
                summary.removed += 1
                summary.removed_titles.append(r["title"])

    summary.mirror_count = mirror_total
    conn.execute(
        "UPDATE scrape_runs SET finished_at=?, games_found=?, new_count=?, changed_count=?, "
        "removed_count=?, mirror_count=? WHERE id=?",
        (_now(), summary.total, summary.new, summary.changed, summary.removed, mirror_total, run_id),
    )
    conn.commit()
    return summary


# ── Link-health history ───────────────────────
def record_link_checks(conn: sqlite3.Connection, checks) -> Dict[str, int]:
    """
    Upsert link-check results and track link health over time.

    `checks` is an iterable of dicts with keys:
        url, hoster, link_type, resolved_link, status, http_code, detail

    Sets first_dead_at the first time a link is seen DEAD, keeps it stable while
    it stays dead, and resets it (recording last_active_at) if the link recovers.
    Returns counts: {active, dead, unknown, newly_dead}.
    """
    init_db(conn)
    now = _now()
    stats = {"active": 0, "dead": 0, "unknown": 0, "newly_dead": 0, "newly_dead_urls": []}

    for c in checks:
        url = (c.get("url") or "").strip()
        if not url:
            continue
        status = (c.get("status") or "UNKNOWN").upper()
        is_dead = status == "DEAD"
        is_active = status == "ACTIVE"
        row = conn.execute("SELECT * FROM link_checks WHERE url=?", (url,)).fetchone()

        if row is None:
            first_dead = now if is_dead else None
            last_active = now if is_active else None
            conn.execute(
                "INSERT INTO link_checks (url, hoster, link_type, resolved_link, status, http_code, detail, "
                "first_checked, last_checked, last_active_at, first_dead_at, times_checked, consecutive_dead) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?)",
                (url, c.get("hoster", ""), c.get("link_type", ""), c.get("resolved_link", ""),
                 status, str(c.get("http_code", "")), c.get("detail", ""),
                 now, now, last_active, first_dead, 1 if is_dead else 0),
            )
            if is_dead:
                stats["newly_dead"] += 1
                stats["newly_dead_urls"].append(url)
        else:
            first_dead = row["first_dead_at"]
            last_active = row["last_active_at"]
            consecutive = row["consecutive_dead"] or 0
            if is_dead:
                consecutive += 1
                if not first_dead:
                    first_dead = now
                    stats["newly_dead"] += 1
                    stats["newly_dead_urls"].append(url)
            else:
                consecutive = 0
                if is_active:
                    last_active = now
                    first_dead = None  # recovered — reset dead tracking
            conn.execute(
                "UPDATE link_checks SET hoster=?, link_type=?, resolved_link=?, status=?, http_code=?, "
                "detail=?, last_checked=?, last_active_at=?, first_dead_at=?, times_checked=times_checked+1, "
                "consecutive_dead=? WHERE url=?",
                (c.get("hoster", ""), c.get("link_type", ""), c.get("resolved_link", ""), status,
                 str(c.get("http_code", "")), c.get("detail", ""), now, last_active, first_dead,
                 consecutive, url),
            )

        if is_active:
            stats["active"] += 1
        elif is_dead:
            stats["dead"] += 1
        else:
            stats["unknown"] += 1

    conn.commit()
    return stats


def record_link_checks_from_report(
    conn: sqlite3.Connection,
    report_path,
    link_column: str = "Final Direct Link",
    fallback_column: str = "Redirect URL",
    hoster_column: str = "Mirror Hoster",
) -> Dict[str, int]:
    """Read a link-check report CSV (as written by link_checker) and persist it."""
    import csv as _csv
    path = Path(report_path)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.readline()
    delim = "\t" if "\t" in sample else (";" if ";" in sample else ",")

    checks = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in _csv.DictReader(f, delimiter=delim):
            url = (r.get(link_column) or "").strip()
            if not url or url.upper() == "N/A":
                url = (r.get(fallback_column) or "").strip()
            if not url or url.upper() == "N/A":
                continue
            checks.append({
                "url": url,
                "hoster": r.get(hoster_column, ""),
                "link_type": r.get("Link Type", ""),
                "resolved_link": r.get("Resolved Link", ""),
                "status": r.get("Link Status", ""),
                "http_code": r.get("HTTP Code", ""),
                "detail": r.get("Check Detail", ""),
            })
    return record_link_checks(conn, checks)


# ── Reading back ────────────────────────────
def export_from_db(
    conn: sqlite3.Connection,
    site: Optional[str] = None,
    active_only: bool = True,
) -> List[Game]:
    """Reconstruct Game objects from the database for re-export."""
    init_db(conn)
    clauses, params = [], []
    if site:
        clauses.append("source_site=?")
        params.append(site)
    if active_only:
        clauses.append("status='active'")
    q = "SELECT * FROM games"
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY title COLLATE NOCASE"

    games: List[Game] = []
    for row in conn.execute(q, params).fetchall():
        mrows = conn.execute(
            "SELECT * FROM mirrors WHERE game_id=? AND status='active' ORDER BY id",
            (row["id"],),
        ).fetchall()
        mirrors = [
            Mirror(
                raw_text=m["raw_text"] or "",
                format=m["format"] or "N/A",
                size=m["size"] or "N/A",
                hoster=m["hoster"] or "Unknown",
                redirect_url=m["redirect_url"] or "",
                final_link=m["final_link"] or "N/A",
            )
            for m in mrows
        ]
        games.append(Game(
            title=row["title"] or "No Title",
            meta_size=row["meta_size"] or "N/A",
            meta_genre=row["meta_genre"] or "N/A",
            detail_url=row["detail_url"] or "",
            mirrors=mirrors,
            source_site=row["source_site"] or "",
            category=row["category"] or "",
            platform=row["platform"] or "",
        ))
    return games


def recent_runs(conn: sqlite3.Connection, limit: int = 10, site: Optional[str] = None):
    init_db(conn)
    q = "SELECT * FROM scrape_runs"
    params: list = []
    if site:
        q += " WHERE site=?"
        params.append(site)
    q += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(q, params).fetchall()


# ── Pretty console output ─────────────────────
def _preview(titles: List[str], n: int = 5) -> str:
    shown = ", ".join(titles[:n])
    if len(titles) > n:
        shown += f", … (+{len(titles) - n} more)"
    return shown


def log_run_summary(summary: RunSummary) -> None:
    """Log a coloured new/changed/removed diff after a scrape."""
    log.info("%s--- Database history (run #%d) ---%s", Colours.CYAN, summary.run_id, Colours.RESET)
    log.info(
        "  %sNew%s: %d   %sChanged%s: %d   %sRemoved%s: %d   Unchanged: %d",
        Colours.GREEN, Colours.RESET, summary.new,
        Colours.YELLOW, Colours.RESET, summary.changed,
        Colours.RED, Colours.RESET, summary.removed,
        summary.unchanged,
    )
    if summary.new_titles:
        log.info("  %sNEW:%s %s", Colours.GREEN, Colours.RESET, _preview(summary.new_titles))
    if summary.changed_titles:
        log.info("  %sCHANGED:%s %s", Colours.YELLOW, Colours.RESET, _preview(summary.changed_titles))
    if summary.removed_titles:
        log.info("  %sREMOVED:%s %s", Colours.RED, Colours.RESET, _preview(summary.removed_titles))


def print_history(conn: sqlite3.Connection, site: Optional[str] = None, limit: int = 10) -> None:
    """Print a table of recent scrape runs + a dead-link snapshot."""
    runs = recent_runs(conn, limit=limit, site=site)
    if not runs:
        log.warning("No scrape history yet — run a scrape first.")
        try:
            conn.close()
        except Exception:
            pass
        return

    print(f"\n{Colours.CYAN}{Colours.BOLD}══════════ SCRAPE HISTORY (last {len(runs)}) ══════════{Colours.RESET}")
    print(f"  {'#':>3}  {'When (UTC)':<19}  {'Site':<12}  {'Mode':<7}  {'Found':>5}  {'New':>4}  {'Chg':>4}  {'Rem':>4}")
    print(f"  {'-'*3}  {'-'*19}  {'-'*12}  {'-'*7}  {'-'*5}  {'-'*4}  {'-'*4}  {'-'*4}")
    for r in runs:
        print(f"  {r['id']:>3}  {(r['started_at'] or ''):<19}  {(r['site'] or ''):<12}  "
              f"{(r['mode'] or ''):<7}  {r['games_found']:>5}  {r['new_count']:>4}  "
              f"{r['changed_count']:>4}  {r['removed_count']:>4}")

    checked = conn.execute("SELECT COUNT(*) AS c FROM link_checks").fetchone()
    dead = conn.execute("SELECT COUNT(*) AS c FROM link_checks WHERE status='DEAD'").fetchone()
    if checked and checked["c"]:
        print(f"\n  {Colours.RED}Dead links tracked{Colours.RESET}: {dead['c']} of {checked['c']} checked")
    print(f"{Colours.CYAN}══════════════════════════════════════════════════{Colours.RESET}\n")
    try:
        conn.close()
    except Exception:
        pass
