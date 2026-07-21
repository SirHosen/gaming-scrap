#!/usr/bin/env python3
"""
HTTP client with smart retries, backoff+jitter, per-host rate-limiting,
optional on-disk response caching, and session reuse.

All network calls go through this module. Phase 3 additions:
  * retry on a configurable set of status codes (429 / 5xx) — not just exceptions
  * exponential backoff WITH jitter (avoids thundering-herd retries)
  * honours the server's `Retry-After` header on 429 / 503
  * per-host rate limiting shared across worker threads
  * optional on-disk response cache (skip re-downloading unchanged pages)
  * in-memory "priming" so an async prefetch can feed the sync flow
"""

from __future__ import annotations

import hashlib
import random
import threading
import time
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

from nestfetch.config import (
    DEFAULT_DELAY, DEFAULT_TIMEOUT, DEFAULT_RETRIES,
    BACKOFF_BASE, BACKOFF_CAP, BACKOFF_JITTER,
    RETRY_STATUS_CODES, RESPECT_RETRY_AFTER,
    PER_HOST_RATE_LIMIT, CACHE_TTL, DEFAULT_HEADERS,
)
from nestfetch.logger import log


class ResponseCache:
    """Tiny thread-safe on-disk cache of GET response bodies keyed by URL."""

    def __init__(self, directory, ttl: int = CACHE_TTL):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self._lock = threading.Lock()

    def _path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.dir / f"{key}.html"

    def get(self, url: str) -> Optional[str]:
        p = self._path(url)
        with self._lock:
            if not p.exists():
                return None
            if self.ttl and (time.time() - p.stat().st_mtime) > self.ttl:
                return None            # stale
            try:
                return p.read_text(encoding="utf-8")
            except OSError:
                return None

    def set(self, url: str, text: str) -> None:
        p = self._path(url)
        with self._lock:
            try:
                p.write_text(text, encoding="utf-8")
            except OSError as exc:
                log.debug("Cache write failed for %s: %s", url, exc)

    def clear(self) -> int:
        """Delete every cached entry; return how many were removed."""
        removed = 0
        with self._lock:
            for f in self.dir.glob("*.html"):
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed


class HttpClient:
    """A reusable, polite HTTP client wrapping requests.Session."""

    def __init__(
        self,
        headers: Optional[dict] = None,
        delay: float = DEFAULT_DELAY,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        rate_limit: float = PER_HOST_RATE_LIMIT,
        cache: Optional[ResponseCache] = None,
        robots: Optional["RobotsPolicy"] = None,
    ):
        self.session = requests.Session()
        self.session.headers.update(headers or DEFAULT_HEADERS)
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.rate_limit = rate_limit
        self.cache = cache
        # Optional robots.txt politeness policy. When None, no robots checks are
        # performed (keeps the low-level client dependency-free for unit tests);
        # the engine wires in a real policy for production scrapes.
        self.robots = robots

        # per-host rate-limit bookkeeping (thread-safe)
        self._state_lock = threading.Lock()
        self._host_locks: Dict[str, threading.Lock] = {}
        self._host_last: Dict[str, float] = {}

        # in-memory one-shot primed responses (e.g. from an async prefetch)
        self._primed: Dict[str, str] = {}

    # ── priming (async prefetch → sync flow) ─────────────────────────

    def prime(self, url: str, text: Optional[str]) -> None:
        """Store a pre-fetched body so the next get(url) returns it instantly."""
        if text is not None:
            self._primed[url] = text

    # ── public ───────────────────────────────────────────

    def get(self, url: str, use_cache: bool = True) -> Optional[str]:
        """
        Perform a GET request with polite delay, retries, and backoff.
        Returns the response text on success, or None on failure.

        Lookup order: primed in-memory → on-disk cache → network.
        """
        # 1) primed (one-shot, from an async prefetch)
        if use_cache:
            primed = self._primed.pop(url, None)
            if primed is not None:
                return primed

        # 2) on-disk cache
        if self.cache and use_cache:
            cached = self.cache.get(url)
            if cached is not None:
                log.debug("Cache hit: %s", url)
                return cached

        # 3) robots.txt politeness — skip anything the site disallows.
        if self.robots is not None and not self.robots.allowed(url):
            log.info("Skipping %s (disallowed by robots.txt)", url)
            return None

        # 4) network
        self._respect_rate_limit(url)
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.retries + 1):
            retry_after: Optional[float] = None
            try:
                resp = self.session.get(url, timeout=self.timeout)

                if resp.status_code == 200:
                    if self.cache and use_cache:
                        self.cache.set(url, resp.text)
                    return resp.text

                if resp.status_code == 404:
                    log.error("HTTP 404 Not Found: %s", url)
                    return None          # don't retry 404s

                retry_after = self._parse_retry_after(resp)
                if resp.status_code in RETRY_STATUS_CODES:
                    log.warning(
                        "HTTP %d on %s (attempt %d/%d)%s",
                        resp.status_code, url, attempt, self.retries,
                        f" — Retry-After {retry_after:.0f}s" if retry_after else "",
                    )
                elif resp.status_code == 403:
                    log.warning("HTTP 403 Forbidden on %s (attempt %d/%d)", url, attempt, self.retries)
                else:
                    log.warning("HTTP %d on %s (attempt %d/%d)", resp.status_code, url, attempt, self.retries)

            except requests.RequestException as exc:
                last_exc = exc
                log.warning("Request error on %s (attempt %d/%d): %s", url, attempt, self.retries, exc)

            # Exponential backoff (capped) with jitter, honouring Retry-After.
            if attempt < self.retries:
                self._backoff_sleep(attempt, retry_after)

        if last_exc:
            log.error("All %d attempts exhausted for %s: %s", self.retries, url, last_exc)
        return None

    # ── internal ─────────────────────────────────────────

    def _respect_rate_limit(self, url: str) -> None:
        """Global polite delay + optional per-host minimum interval."""
        if self.delay:
            time.sleep(self.delay)

        if not self.rate_limit:
            return

        host = urlparse(url).netloc
        with self._state_lock:
            lock = self._host_locks.setdefault(host, threading.Lock())
        with lock:
            elapsed = time.time() - self._host_last.get(host, 0.0)
            wait = self.rate_limit - elapsed
            if wait > 0:
                time.sleep(wait)
            self._host_last[host] = time.time()

    def _backoff_sleep(self, attempt: int, retry_after: Optional[float]) -> None:
        if retry_after is not None:
            sleep_time = min(retry_after, BACKOFF_CAP)
        else:
            sleep_time = min(BACKOFF_BASE ** attempt, BACKOFF_CAP)
            if BACKOFF_JITTER:
                sleep_time += random.uniform(0, BACKOFF_JITTER)
        log.debug("Backing off %.1fs before retry…", sleep_time)
        time.sleep(sleep_time)

    @staticmethod
    def _parse_retry_after(resp) -> Optional[float]:
        if not RESPECT_RETRY_AFTER:
            return None
        raw = resp.headers.get("Retry-After")
        if not raw:
            return None
        try:
            return float(raw)          # delta-seconds form
        except (TypeError, ValueError):
            return None                # HTTP-date form: ignore (rare here)

    # ── context manager support ───────────────────────────────

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
