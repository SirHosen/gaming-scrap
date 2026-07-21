#!/usr/bin/env python3
"""
Link checker — verify whether previously scraped download links are still alive.

Reads a scraped CSV (produced by exporters.export_csv), checks each mirror's
final direct link against its file host, and writes an annotated report CSV with
three new columns: Link Status (ACTIVE / DEAD / UNKNOWN), HTTP Code, and a
human-readable Check Detail.

Why not just look at the HTTP status code?
  Most file hosts (Mediafire, 1fichier, Terabox, ...) return HTTP 200 even for a
  deleted file and instead show an "Invalid or Deleted File" message in the HTML.
  So we check BOTH the status code AND host-specific "dead" text markers.

The checker is read-only against the network (GET, streamed, first chunk only)
and never modifies the source CSV.
"""

from __future__ import annotations

import csv
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from nestfetch.config import (
    OUTPUT_DIR,
    CSV_FILENAME,
    LINK_CHECK_REPORT_FILENAME,
    LINK_CHECK_ACTIVE_FILENAME,
    LINK_CHECK_RECAP_FILENAME,
    DEFAULT_TIMEOUT,
    DEFAULT_HEADERS,
    MAX_WORKERS,
    RESOLVE_LINKS_DEFAULT,
    RESOLVE_MAX_HOPS,
    RESOLVE_TIMEOUT,
    CACHE_DIRNAME,
    CACHE_TTL,
    PER_HOST_RATE_LIMIT,
)
from nestfetch.logger import log, Colours
from nestfetch.link_resolver import resolve_url, classify_url
from nestfetch.http_client import ResponseCache
from urllib.parse import urlparse


# ── Status constants ───────────────────────────────────────────────────────
STATUS_ACTIVE = "ACTIVE"
STATUS_DEAD = "DEAD"
STATUS_UNKNOWN = "UNKNOWN"

# Extra report columns appended to the original CSV headers.
REPORT_COLUMNS = [
    "Link Type", "Resolved Link",
    "Link Status", "HTTP Code", "Check Detail", "Checked At",
]

# Default column names as written by exporters.export_csv.
DEFAULT_LINK_COLUMN = "Final Direct Link"
DEFAULT_FALLBACK_COLUMN = "Redirect URL"
DEFAULT_HOSTER_COLUMN = "Mirror Hoster"


# ── Host-specific "file is dead" text markers (all lower-case) ─────────────
DEAD_MARKERS: Dict[str, Tuple[str, ...]] = {
    "mediafire": (
        "invalid or deleted file",
        "the key you provided does not exist",
        "file has been removed",
        "removed for violation",
        "file has been deleted",
    ),
    "1fichier": (
        "the requested file has been deleted",
        "file not found",
        "could not be found",
        "the file may have been deleted",
    ),
    "terabox": (
        "page that doesn't exist",
        "share link has expired",
        "file does not exist",
        "shared file does not exist",
    ),
    "megaup": (
        "file not found",
        "the file was deleted",
        "file has been removed",
    ),
    "mega": (
        "no longer available",
        "the file you are trying to download is no longer available",
    ),
    "send.cm": (
        "file not found",
        "no such file",
        "file has been deleted",
    ),
    "up-4ever": (
        "file not found",
        "the file was deleted",
    ),
    "buzzheavier": (
        "not found",
    ),
}

# Applied to every host as a last-resort fallback.
GENERIC_DEAD_MARKERS: Tuple[str, ...] = (
    "file not found",
    "404 not found",
    "page not found",
    "file does not exist",
    "no longer available",
    "has been deleted",
)


# ── Thread-local sessions (requests.Session is not meant to be shared) ─────
_local = threading.local()


def _session() -> requests.Session:
    sess = getattr(_local, "session", None)
    if sess is None:
        sess = requests.Session()
        sess.headers.update(DEFAULT_HEADERS)
        _local.session = sess
    return sess


# ── Per-host rate limiting + optional on-disk verdict cache ────────────────
_rate_lock = threading.Lock()
_last_hit: Dict[str, float] = {}


def _respect_rate_limit(url: str, rate_limit: float) -> None:
    """Ensure at least `rate_limit` seconds pass between hits to the same host.

    The next slot per host is reserved under a lock, then we sleep OUTSIDE the
    lock so requests to *different* hosts never block one another.
    """
    if not rate_limit or rate_limit <= 0:
        return
    host = urlparse(url).netloc.lower()
    with _rate_lock:
        now = time.time()
        earliest = _last_hit.get(host, 0.0) + rate_limit
        wait = earliest - now
        _last_hit[host] = max(now, earliest)
    if wait > 0:
        time.sleep(wait)


def _verdict_cache(use_cache: bool) -> Optional[ResponseCache]:
    """Build an on-disk cache of link verdicts (status/code/detail), or None.

    Reuses the same ResponseCache machinery as the scraper's HTTP cache, in a
    dedicated sub-folder so link-check verdicts never collide with page bodies.
    """
    if not use_cache:
        return None
    try:
        return ResponseCache(Path(OUTPUT_DIR) / CACHE_DIRNAME / "linkcheck", ttl=CACHE_TTL)
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("Could not create link-check cache: %s", exc)
        return None


def _host_key(hoster: str, url: str) -> str:
    """Best-effort identification of the file host from the hoster label or URL."""
    h = (hoster or "").lower()
    u = (url or "").lower()
    for key in DEAD_MARKERS:
        if key in h:
            return key
    if "mediafire" in u:
        return "mediafire"
    if "1fichier" in u:
        return "1fichier"
    if "terabox" in u or "1024tera" in u or "teraboxapp" in u:
        return "terabox"
    if "buzzheavier" in u:
        return "buzzheavier"
    if "send.cm" in u or "send-cm" in u:
        return "send.cm"
    if "up-4ever" in u or "up-load" in u or "up4ever" in u:
        return "up-4ever"
    if "megaup" in u:
        return "megaup"
    if "mega.nz" in u or "mega.io" in u:
        return "mega"
    return ""


# ── Core single-link check ─────────────────────────────────────────────────

def check_link(
    url: str,
    hoster: str = "",
    session: Optional[requests.Session] = None,
    timeout: int = DEFAULT_TIMEOUT,
    rate_limit: float = 0.0,
) -> Tuple[str, str, str]:
    """
    Check a single link.

    Returns (status, http_code, detail) where status is ACTIVE / DEAD / UNKNOWN.

    - Hard 404/410 -> DEAD
    - 401/403/5xx -> UNKNOWN (blocked / anti-bot / server error, not necessarily dead)
    - 200 with a host-specific "deleted" marker in the HTML -> DEAD
    - 200 non-HTML body (direct file) or clean HTML -> ACTIVE
    """
    if not url or url.strip().upper() in ("", "N/A"):
        return STATUS_UNKNOWN, "-", "No link to check"

    sess = session or _session()
    try:
        _respect_rate_limit(url, rate_limit)
        resp = sess.get(
            url, timeout=timeout, allow_redirects=True, stream=True,
        )
        code = resp.status_code

        if code in (404, 410):
            return STATUS_DEAD, str(code), f"HTTP {code} not found"
        if code in (401, 403):
            return STATUS_UNKNOWN, str(code), f"HTTP {code} (blocked / anti-bot)"
        if code >= 500:
            return STATUS_UNKNOWN, str(code), f"HTTP {code} server error"

        content_type = resp.headers.get("Content-Type", "").lower()

        # A direct binary response means the file is being served -> alive.
        if content_type and "text/html" not in content_type:
            return STATUS_ACTIVE, str(code), f"HTTP {code}, {content_type.split(';')[0]}"

        # Read a bounded slice of the HTML body to scan for dead markers.
        body = ""
        try:
            raw = next(resp.iter_content(chunk_size=200_000), b"")
            if isinstance(raw, bytes):
                body = raw.decode("utf-8", errors="ignore")
            else:
                body = raw or ""
        except Exception:
            body = ""
        finally:
            resp.close()

        low = body.lower()
        key = _host_key(hoster, str(resp.url))
        markers = DEAD_MARKERS.get(key, ()) + GENERIC_DEAD_MARKERS
        for marker in markers:
            if marker in low:
                return STATUS_DEAD, str(code), f"HTTP {code}: matched '{marker}'"

        if code == 200:
            return STATUS_ACTIVE, "200", "HTTP 200, no dead markers found"
        return STATUS_UNKNOWN, str(code), f"HTTP {code}"

    except requests.Timeout:
        return STATUS_UNKNOWN, "TIMEOUT", "Request timed out"
    except requests.RequestException as exc:
        return STATUS_UNKNOWN, "ERROR", f"{type(exc).__name__}: {exc}"


# ── CSV IO helpers ─────────────────────────────────────────────────────────

def _detect_delimiter(header_line: str) -> str:
    """
    Pick the most likely delimiter from a CSV header line.

    Handles tab (our exporter), semicolon (Excel in ID/EU locales re-saves CSV
    with ';'), comma, and pipe. Chooses whichever appears most in the header.
    """
    candidates = ["\t", ";", ",", "|"]
    counts = {d: header_line.count(d) for d in candidates}
    best = max(candidates, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


def _read_rows(csv_path: Path) -> Tuple[List[str], List[dict], str]:
    """Read a scraped CSV, auto-detecting the delimiter (tab / ; / , / |)."""
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        first_line = sample.splitlines()[0] if sample else ""
        delimiter = _detect_delimiter(first_line)
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    return fieldnames, rows, delimiter


def _target_link(row: dict, link_col: str, fallback_col: str) -> str:
    """Pick the best URL to check for a row (final link, else redirect URL)."""
    val = (row.get(link_col) or "").strip()
    if val and val.upper() != "N/A":
        return val
    fb = (row.get(fallback_col) or "").strip()
    if fb and fb.upper() != "N/A":
        return fb
    return ""


def _write_csv(path: Path, headers: List[str], rows: List[dict], delimiter: str) -> None:
    """Write rows to a CSV using the given delimiter (utf-8-sig for Excel)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=headers, delimiter=delimiter, extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_recap(
    path: Path,
    counts: Dict[str, int],
    active_titles: List[str],
    total_rows: int,
    source: Path,
    now: str,
) -> None:
    """Write a plain-text recap: counts + list of games with an active link."""
    path.parent.mkdir(parents=True, exist_ok=True)
    active = counts.get(STATUS_ACTIVE, 0)
    dead = counts.get(STATUS_DEAD, 0)
    unknown = counts.get(STATUS_UNKNOWN, 0)

    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("         NESTFETCH LINK CHECK — RECAP")
    lines.append("=" * 60)
    lines.append(f"Source CSV               : {source}")
    lines.append(f"Generated                : {now}")
    lines.append("")
    lines.append(f"Total links checked      : {total_rows}")
    lines.append(f"ACTIVE links             : {active}")
    lines.append(f"DEAD links               : {dead}")
    lines.append(f"UNKNOWN links            : {unknown}")
    lines.append(f"Games with ACTIVE link   : {len(active_titles)} (unique titles)")
    lines.append("")
    lines.append("-" * 60)
    lines.append(f"GAMES WITH AN ACTIVE DOWNLOAD LINK ({len(active_titles)}):")
    lines.append("-" * 60)
    if active_titles:
        for i, title in enumerate(active_titles, 1):
            lines.append(f"{i:>4}. {title}")
    else:
        lines.append("(none)")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Public entry point ─────────────────────────────────────────────────────

def check_csv_links(
    csv_path: str | Path,
    output_path: Optional[str | Path] = None,
    workers: int = MAX_WORKERS,
    delay: float = 0.0,
    timeout: int = DEFAULT_TIMEOUT,
    link_column: str = DEFAULT_LINK_COLUMN,
    fallback_column: str = DEFAULT_FALLBACK_COLUMN,
    hoster_column: str = DEFAULT_HOSTER_COLUMN,
    resolve: bool = RESOLVE_LINKS_DEFAULT,
    rate_limit: float = 0.0,
    use_cache: bool = False,
) -> Optional[Path]:
    """
    Read a scraped CSV, check every link, and write an annotated report CSV.

    Returns the path to the written report, or None if the input was invalid.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        log.error("%sCSV not found:%s %s", Colours.RED, Colours.RESET, csv_path)
        return None

    fieldnames, rows, in_delimiter = _read_rows(csv_path)
    if not rows:
        log.warning("CSV has no data rows: %s", csv_path)
        return None

    if link_column not in fieldnames and fallback_column not in fieldnames:
        log.error(
            "%sCSV has neither '%s' nor '%s' column. Found columns: %s%s",
            Colours.RED, link_column, fallback_column, fieldnames, Colours.RESET,
        )
        return None

    log.info(
        "%s--- Starting LINK CHECK ---%s  (%d rows from %s)",
        Colours.CYAN, Colours.RESET, len(rows), csv_path,
    )
    log.info(
        "Shortener / ad-gate resolution: %s%s%s",
        Colours.GREEN if resolve else Colours.YELLOW,
        "ON" if resolve else "OFF",
        Colours.RESET,
    )

    # Collect unique URLs (many rows may share the same link) + a hoster hint.
    hoster_by_url: Dict[str, str] = {}
    for row in rows:
        u = _target_link(row, link_column, fallback_column)
        if u and u not in hoster_by_url:
            hoster_by_url[u] = row.get(hoster_column, "") if hoster_column in fieldnames else ""

    unique_urls = list(hoster_by_url.keys())
    total_unique = len(unique_urls)
    log.info("Checking %d unique links with %d workers…", total_unique, workers)
    if rate_limit and rate_limit > 0:
        log.info("Per-host rate limit: %s%.2fs between requests%s",
                 Colours.GREY, rate_limit, Colours.RESET)
    cache = _verdict_cache(use_cache)
    if cache is not None:
        log.info("Verdict cache: %sON%s (skips re-checking recently-seen links)",
                 Colours.GREEN, Colours.RESET)

    def _worker(u: str):
        # Reuse a recent ACTIVE/DEAD verdict if cached (avoids re-hitting hosts).
        if cache is not None:
            hit = cache.get(u)
            if hit is not None:
                parts = hit.split("\t", 2)
                if len(parts) == 3:
                    return u, None, (parts[0], parts[1], parts[2])
        if delay:
            time.sleep(delay)
        sess = _session()
        rr = resolve_url(u, session=sess, max_hops=RESOLVE_MAX_HOPS,
                         timeout=RESOLVE_TIMEOUT) if resolve else None
        target = rr.final_url if (rr and rr.final_url) else u
        chk = check_link(target, hoster_by_url.get(u, ""), session=sess,
                         timeout=timeout, rate_limit=rate_limit)
        # Only cache definitive verdicts; UNKNOWN (timeout/blocked) may be transient.
        if cache is not None and chk[0] in (STATUS_ACTIVE, STATUS_DEAD):
            cache.set(u, "\t".join(chk))
        return u, rr, chk

    results: Dict[str, Tuple[object, Tuple[str, str, str]]] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_worker, u): u for u in unique_urls}
        for future in as_completed(futures):
            u, rr, chk = future.result()
            results[u] = (rr, chk)
            done += 1
            if done % 25 == 0 or done == total_unique:
                log.info(
                    "%sProgress: %d/%d links checked…%s",
                    Colours.YELLOW, done, total_unique, Colours.RESET,
                )

    # ── Write annotated report ─────────────────────────────────────────
    if output_path is None:
        output_path = Path(OUTPUT_DIR) / LINK_CHECK_REPORT_FILENAME
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out_headers = fieldnames + [c for c in REPORT_COLUMNS if c not in fieldnames]
    title_col = "Game Title" if "Game Title" in fieldnames else (fieldnames[0] if fieldnames else "Game Title")

    counts = {STATUS_ACTIVE: 0, STATUS_DEAD: 0, STATUS_UNKNOWN: 0}
    dead_rows: List[Tuple[str, str, str]] = []  # (title, hoster, detail)
    annotated_rows: List[dict] = []             # every row + status columns
    active_rows: List[dict] = []                # only rows whose link is ACTIVE

    for row in rows:
        u = _target_link(row, link_column, fallback_column)
        if u:
            rr, (status, code, detail) = results.get(
                u, (None, (STATUS_UNKNOWN, "-", "not checked"))
            )
        else:
            rr, (status, code, detail) = (None, (STATUS_UNKNOWN, "-", "No link to check"))

        counts[status] = counts.get(status, 0) + 1
        if status == STATUS_DEAD:
            dead_rows.append((row.get(title_col, "?"), row.get(hoster_column, "?"), detail))

        out = dict(row)
        if rr is not None:
            out["Link Type"] = rr.link_type
            out["Resolved Link"] = rr.final_url if (rr.final_url and rr.final_url != u) else ""
        else:
            out["Link Type"] = classify_url(u) if u else "UNKNOWN"
            out["Resolved Link"] = ""
        out["Link Status"] = status
        out["HTTP Code"] = code
        out["Check Detail"] = detail
        out["Checked At"] = now
        annotated_rows.append(out)
        if status == STATUS_ACTIVE:
            active_rows.append(out)

    # 1) Full annotated report (all rows). Same delimiter as input so Excel opens
    #    it cleanly (';' for ID/EU locales, tab for our exporter, etc.).
    _write_csv(output_path, out_headers, annotated_rows, in_delimiter)

    # 2) Active-only report — just the rows whose link is still ACTIVE.
    active_path = output_path.parent / LINK_CHECK_ACTIVE_FILENAME
    _write_csv(active_path, out_headers, active_rows, in_delimiter)

    # 3) Unique game titles that have at least one ACTIVE link (order preserved).
    active_titles: List[str] = []
    seen: set = set()
    for r in active_rows:
        t = (r.get(title_col) or "").strip()
        if t and t not in seen:
            seen.add(t)
            active_titles.append(t)

    # 4) Human-readable recap (counts + list of games with an active link).
    recap_path = output_path.parent / LINK_CHECK_RECAP_FILENAME
    _write_recap(recap_path, counts, active_titles, len(rows), csv_path, now)

    _print_summary(
        counts, dead_rows, active_titles,
        output_path, active_path, recap_path, len(rows),
    )
    return output_path


def _print_summary(
    counts: Dict[str, int],
    dead_rows: List[Tuple[str, str, str]],
    active_titles: List[str],
    output_path: Path,
    active_path: Path,
    recap_path: Path,
    total_rows: int,
) -> None:
    """Print a coloured summary of the link-check run."""
    active = counts.get(STATUS_ACTIVE, 0)
    dead = counts.get(STATUS_DEAD, 0)
    unknown = counts.get(STATUS_UNKNOWN, 0)

    print(f"\n{Colours.GREEN}{Colours.BOLD}════════════════ LINK CHECK SUMMARY ════════════════{Colours.RESET}")
    print(f"  Total Links Checked      : {Colours.WHITE}{total_rows}{Colours.RESET}")
    print(f"  {Colours.GREEN}✔ ACTIVE links{Colours.RESET}           : {Colours.WHITE}{active}{Colours.RESET}")
    print(f"  {Colours.RED}✗ DEAD links{Colours.RESET}             : {Colours.WHITE}{dead}{Colours.RESET}")
    print(f"  {Colours.YELLOW}? UNKNOWN links{Colours.RESET}          : {Colours.WHITE}{unknown}{Colours.RESET}")
    print(f"  {Colours.GREEN}★ Games w/ active link{Colours.RESET}    : {Colours.WHITE}{len(active_titles)}{Colours.RESET} {Colours.GREY}(unique titles){Colours.RESET}")
    print(f"  Full report    : {Colours.WHITE}{output_path}{Colours.RESET}")
    print(f"  {Colours.GREEN}Active only{Colours.RESET}     : {Colours.WHITE}{active_path}{Colours.RESET}")
    print(f"  Recap (titles) : {Colours.WHITE}{recap_path}{Colours.RESET}")
    print(f"{Colours.GREEN}═════════════════════════════════════════════════════{Colours.RESET}")

    if active_titles:
        a_preview = active_titles[:20]
        print(f"\n{Colours.GREEN}{Colours.BOLD}Games with an ACTIVE download link ({len(active_titles)}):{Colours.RESET}")
        for i, title in enumerate(a_preview, 1):
            print(f"  {Colours.GREEN}✔{Colours.RESET} {i}. {title}")
        if len(active_titles) > len(a_preview):
            print(f"  {Colours.GREY}…and {len(active_titles) - len(a_preview)} more (see {recap_path.name}).{Colours.RESET}")

    if dead_rows:
        preview = dead_rows[:15]
        print(f"\n{Colours.RED}{Colours.BOLD}Dead / expired links ({len(dead_rows)}):{Colours.RESET}")
        for title, hoster, detail in preview:
            print(f"  {Colours.RED}✗{Colours.RESET} {title}  [{hoster}]  — {Colours.GREY}{detail}{Colours.RESET}")
        if len(dead_rows) > len(preview):
            print(f"  {Colours.GREY}…and {len(dead_rows) - len(preview)} more (see report CSV).{Colours.RESET}")
    print()


def default_csv_path() -> Path:
    """Convenience: the default scraped CSV location."""
    return Path(OUTPUT_DIR) / CSV_FILENAME
