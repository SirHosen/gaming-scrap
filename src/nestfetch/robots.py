#!/usr/bin/env python3
"""
robots.txt politeness policy.

NESTfetch is a *polite* scraper: before fetching a page it can consult the
target site's ``robots.txt`` and skip anything the site asks bots not to crawl.

This module is intentionally self-contained and dependency-light (stdlib
``urllib.robotparser`` + ``requests``). It is thread-safe and caches one parsed
``robots.txt`` per host.

Behaviour notes:
  * ``robots.txt`` itself is always allowed (you must fetch it to obey it).
  * If ``robots.txt`` cannot be fetched/parsed, we **fail open** (allow) but log
    at debug level — an unreachable robots file should not silently kill a run.
  * Disabling the policy (``enabled=False``) makes ``allowed()`` always return
    ``True`` and performs no network I/O.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from nestfetch.config import (
    DEFAULT_HEADERS,
    RESPECT_ROBOTS_TXT,
    ROBOTS_TIMEOUT,
    ROBOTS_USER_AGENT,
)
from nestfetch.logger import log


class RobotsPolicy:
    """Decide whether a URL may be fetched, according to each host's robots.txt."""

    def __init__(
        self,
        enabled: bool = RESPECT_ROBOTS_TXT,
        user_agent: str = ROBOTS_USER_AGENT,
        timeout: int = ROBOTS_TIMEOUT,
        session: Optional[requests.Session] = None,
    ):
        self.enabled = enabled
        self.user_agent = user_agent or "*"
        self.timeout = timeout
        self._session = session
        self._lock = threading.Lock()
        # host -> RobotFileParser (or None when robots.txt was unreachable)
        self._cache: Dict[str, Optional[RobotFileParser]] = {}

    # ── public ────────────────────────────────────────────────

    def allowed(self, url: str) -> bool:
        """Return True if ``url`` may be fetched under the host's robots rules."""
        if not self.enabled:
            return True

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True  # relative/blank URLs: nothing to check

        # Fetching robots.txt itself must always be permitted.
        if parsed.path in ("/robots.txt", "robots.txt"):
            return True

        parser = self._parser_for(parsed)
        if parser is None:
            return True  # fail open (already logged)
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception as exc:  # extremely defensive: never crash a scrape
            log.debug("robots can_fetch error for %s: %s", url, exc)
            return True

    def crawl_delay(self, url: str) -> Optional[float]:
        """Return the host's Crawl-delay (seconds) if it declares one."""
        if not self.enabled:
            return None
        parsed = urlparse(url)
        parser = self._parser_for(parsed)
        if parser is None:
            return None
        try:
            delay = parser.crawl_delay(self.user_agent)
            return float(delay) if delay is not None else None
        except Exception:
            return None

    # ── internal ──────────────────────────────────────────────

    def _parser_for(self, parsed) -> Optional[RobotFileParser]:
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        with self._lock:
            if host_key in self._cache:
                return self._cache[host_key]

        parser = self._load(host_key)
        with self._lock:
            self._cache[host_key] = parser
        return parser

    def _load(self, host_key: str) -> Optional[RobotFileParser]:
        robots_url = urljoin(host_key + "/", "robots.txt")
        try:
            session = self._session or requests
            resp = session.get(
                robots_url,
                timeout=self.timeout,
                headers={"User-Agent": DEFAULT_HEADERS.get("User-Agent", "*")},
            )
        except Exception as exc:
            log.debug("Could not fetch %s (%s) — allowing by default.", robots_url, exc)
            return None

        if resp.status_code >= 400:
            # No robots.txt (404) or blocked: nothing to enforce — allow.
            log.debug("robots.txt %s returned HTTP %d — allowing.", robots_url, resp.status_code)
            return None

        parser = RobotFileParser()
        try:
            parser.parse(resp.text.splitlines())
        except Exception as exc:
            log.debug("Failed to parse %s: %s — allowing.", robots_url, exc)
            return None
        log.debug("Loaded robots.txt for %s", host_key)
        return parser
