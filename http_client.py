#!/usr/bin/env python3
"""
HTTP client with retry, backoff, rate-limiting, and session reuse.
All network calls go through this module.
"""

from __future__ import annotations

import time
import requests
from typing import Optional

from config import (
    DEFAULT_DELAY, DEFAULT_TIMEOUT, DEFAULT_RETRIES,
    BACKOFF_BASE, BACKOFF_CAP, DEFAULT_HEADERS,
)
from logger import log


class HttpClient:
    """A reusable, polite HTTP client wrapping requests.Session."""

    def __init__(
        self,
        headers: Optional[dict] = None,
        delay: float = DEFAULT_DELAY,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ):
        self.session = requests.Session()
        self.session.headers.update(headers or DEFAULT_HEADERS)
        self.delay = delay
        self.timeout = timeout
        self.retries = retries

    # ── public ─────────────────────────────────────────────────────────

    def get(self, url: str) -> Optional[str]:
        """
        Perform a GET request with polite delay, retries, and backoff.
        Returns the response text on success, or None on failure.
        """
        time.sleep(self.delay)
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout)

                if resp.status_code == 200:
                    return resp.text

                if resp.status_code == 403:
                    log.warning("HTTP 403 Forbidden on %s (attempt %d/%d)", url, attempt, self.retries)
                elif resp.status_code == 404:
                    log.error("HTTP 404 Not Found: %s", url)
                    return None          # don't retry 404s
                else:
                    log.warning("HTTP %d on %s (attempt %d/%d)", resp.status_code, url, attempt, self.retries)

            except requests.RequestException as exc:
                last_exc = exc
                log.warning("Request error on %s (attempt %d/%d): %s", url, attempt, self.retries, exc)

            # Exponential backoff (capped)
            if attempt < self.retries:
                sleep_time = min(BACKOFF_BASE ** attempt, BACKOFF_CAP)
                log.debug("Backing off %.1fs before retry…", sleep_time)
                time.sleep(sleep_time)

        if last_exc:
            log.error("All %d attempts exhausted for %s: %s", self.retries, url, last_exc)
        return None

    # ── context manager support ────────────────────────────────────────

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
