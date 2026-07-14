#!/usr/bin/env python3
"""
Central configuration for the SwitchRoms scraper.
All tunable parameters live here so the core engine stays clean.
"""

from __future__ import annotations

# ── Target site ────────────────────────────────────────────────────────────
BASE_URL: str = "https://switchroms.io/"

# ── Full-site discovery via XML sitemap (used by "scrape all") ───────────
# switchroms.io ignores /page/N/ pagination on the homepage (every page loops
# back to the same latest listing), so a full scrape is driven by the XML
# sitemap, which reliably lists every individual game page.
SITEMAP_CANDIDATES: tuple = (
    "sitemap_index.xml",
    "sitemap.xml",
    "wp-sitemap.xml",
)
# Sub-sitemaps / URL fragments to skip during discovery (non-game content).
SITEMAP_SKIP_KEYWORDS: tuple = (
    "category", "tag", "author", "page-sitemap",
    "taxonomies", "wp-sitemap-users",
)

# ── Network behaviour ──────────────────────────────────────────────────────
DEFAULT_DELAY: float = 1.0          # polite delay between requests (seconds)
DEFAULT_TIMEOUT: int = 20           # per-request timeout (seconds)
DEFAULT_RETRIES: int = 3           # retry attempts on transient failures
BACKOFF_BASE: float = 2.0          # exponential backoff base
BACKOFF_CAP: float = 30.0           # maximum backoff sleep

# ── Concurrency ───────────────────────────────────────────────────────────
MAX_WORKERS: int = 5               # thread-pool size for parallel detail pages

# ── Output ────────────────────────────────────────────────────────────────
OUTPUT_DIR: str = "output"
JSON_FILENAME: str = "switch_games.json"
CSV_FILENAME: str = "switch_games.csv"
LOG_FILENAME: str = "scraper.log"
LINK_CHECK_REPORT_FILENAME: str = "link_check_report.csv"
LINK_CHECK_ACTIVE_FILENAME: str = "link_check_active.csv"
LINK_CHECK_RECAP_FILENAME: str = "link_check_recap.txt"

# ── Database (SQLite scrape history) ─────────────────
# Every scrape is recorded here so NESTfetch can diff runs (new/changed/removed)
# and track when a link first went dead. Lives inside OUTPUT_DIR (git-ignored).
DB_FILENAME: str = "nestfetch.db"

# ── Browser-like headers ──────────────────────────────────────────────────
DEFAULT_HEADERS: dict = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE_URL,
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ── Known file hosters (for validation / display) ─────────────────────────
KNOWN_HOSTERS: tuple = (
    "Mediafire", "Megaup", "1fichier", "Buzzheavier",
    "Terabox", "Send.cm", "Up-4ever", "Qiwi.gg",
    "Filefactory", "Mega", "Unknown",
)

# ── Format filter mapping ─────────────────────────────────────────────────
FORMAT_MAP: dict = {
    "1": "NSP ROM",
    "2": "XCI ROM",
    "3": "UPDATE",
    "4": "DLC",
    "5": "ALL",
}

HOSTER_MAP: dict = {
    "1": "MEDIAFIRE",
    "2": "MEGAUP",
    "3": "1FICHIER",
    "4": "BUZZHEAVIER",
    "5": "TERABOX",
    "6": "SEND.CM",
    "7": "UP-4EVER",
    "8": "ALL",
}

OUTPUT_MAP: dict = {
    "1": "csv",
    "2": "json",
    "3": "both",
}

# ── Link shortener / ad-gate resolution ──────────────────────────
# Some download links are wrapped in URL shorteners or "wait for the ad, then
# continue" ad-gate pages. The link checker can unwrap these to reveal (and
# validate) the real host link. Extend these lists anytime — no code changes.
RESOLVE_LINKS_DEFAULT: bool = True   # unwrap shorteners/ad-gates during link check
RESOLVE_MAX_HOPS: int = 5            # max unwrap steps per link (avoid loops)
RESOLVE_TIMEOUT: int = 15           # per-hop timeout (seconds)

# Optional headless-browser fallback for ad-gates that build the real link with
# JavaScript / a countdown timer (linkvertise, modern ouo.io/gplinks, ...).
# Off by default: it needs the extra 'playwright' package + a Chromium download
# and is much slower. Enable after:
#   pip install playwright && python -m playwright install chromium
RESOLVE_USE_BROWSER_FALLBACK: bool = False
RESOLVE_BROWSER_TIMEOUT: int = 45   # max seconds to drive the browser per link

# Pure redirect shorteners — resolved simply by following HTTP redirects.
SHORTENER_DOMAINS: tuple = (
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "v.gd", "rb.gy",
    "cutt.ly", "shorturl.at", "rebrand.ly", "ow.ly", "buff.ly", "t.ly",
    "s.id", "shrtco.de", "clck.ru", "tiny.cc", "soo.gd", "tny.im",
)

# Ad-gate / interstitial shorteners — show an ad + countdown before the link.
# Unwrapped best-effort (redirects, meta-refresh, embedded target, continue link).
AD_GATE_DOMAINS: tuple = (
    "ouo.io", "ouo.press", "exe.io", "exey.io", "adf.ly", "sh.st",
    "adfoc.us", "shrinkme.io", "shrinkearn.com", "gplinks.co", "gplinks.in",
    "droplink.co", "linkvertise.com", "link-to.net", "za.gl", "oke.io",
    "clk.sh", "cpmlink.net", "short.pe", "mboost.me", "fc.lc",
    "try2link.com", "adshrink.it", "linkpays.in", "earn4link.in", "gyanilinks.com",
)

# Domains treated as FINAL download destinations (never a shortener/ad-gate).
DIRECT_HOST_DOMAINS: tuple = (
    "mediafire.com", "1fichier.com", "terabox.com", "teraboxapp.com",
    "1024terabox.com", "1024tera.com", "mega.nz", "mega.io", "megaup.net",
    "send.cm", "up-4ever.net", "up-4ever.com", "buzzheavier.com", "qiwi.gg",
    "filefactory.com", "pixeldrain.com", "gofile.io", "krakenfiles.com",
    "drive.google.com", "dropbox.com",
)

# ── HTTP resilience & performance (Phase 3) ──────────────────
# Status codes worth retrying (transient server / rate-limit responses).
RETRY_STATUS_CODES: tuple = (429, 500, 502, 503, 504)
# Random jitter (0..N seconds) added to each backoff sleep so many concurrent
# workers don't all retry at the same instant ("thundering herd").
BACKOFF_JITTER: float = 0.5
# Honour a server's `Retry-After` header on 429 / 503 (capped at BACKOFF_CAP).
RESPECT_RETRY_AFTER: bool = True
# Per-host polite rate limit: minimum seconds between requests to the SAME host,
# enforced across ALL worker threads. 0 disables it (rely on DEFAULT_DELAY only).
PER_HOST_RATE_LIMIT: float = 0.0

# ── Response cache (skip re-downloading unchanged pages) ────────
# Optional on-disk cache of GET bodies keyed by URL — great for re-runs and
# link checks. Stored in OUTPUT_DIR/CACHE_DIRNAME (git-ignored).
CACHE_ENABLED_DEFAULT: bool = False
CACHE_DIRNAME: str = ".http_cache"
CACHE_TTL: int = 86400              # cache entry lifetime in seconds (0 = forever)

# ── Async HTTP (optional, experimental) ─────────────────────
# Fetch many pages concurrently with aiohttp — faster than the thread pool for
# hundreds of pages. OFF by default; needs the optional 'aiohttp' package and
# falls back to the threaded client automatically when it's missing.
ASYNC_ENABLED_DEFAULT: bool = False
ASYNC_CONCURRENCY: int = 10        # max simultaneous async requests
