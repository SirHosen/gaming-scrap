#!/usr/bin/env python3
"""
Central configuration for the SwitchRoms scraper.
All tunable parameters live here so the core engine stays clean.
"""

from __future__ import annotations

# ── Target site ────────────────────────────────────────────────────────────
BASE_URL: str = "https://switchroms.io/"

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
