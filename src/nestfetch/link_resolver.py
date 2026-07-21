#!/usr/bin/env python3
"""
Link resolver — unwrap URL shorteners and ad-gate ("click, wait for the ad,
then continue") links to reveal the real download destination.

Many game-download sites hide the actual host link (Mediafire, 1fichier, ...)
behind:
  1. Pure redirect shorteners (bit.ly, tinyurl, cutt.ly, ...) — a single 30x
     redirect straight to the destination.
  2. Ad-gate shorteners (ouo.io, exe.io, gplinks, linkvertise, ...) — an
     interstitial page with an ad + countdown before a "Continue" button.

Strategy (all best-effort, generic — no service-specific exploits):
  * classify_url() : DIRECT / SHORTENER / AD_GATE / UNKNOWN, purely by domain.
  * resolve_url()  : up to RESOLVE_MAX_HOPS of
        - embedded target in the URL query (?url=, ?target=, base64, ...)
        - following HTTP redirects
        - reading a <meta refresh> or a link to a known direct host in the HTML
    until it lands on a direct host (or runs out of hops).

Legal / ToS note: unwrapping links can violate a shortener's Terms of Service
and a site's monetisation. Use responsibly and only on links you may access.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urljoin, parse_qs, unquote

import requests

from nestfetch.config import (
    SHORTENER_DOMAINS,
    AD_GATE_DOMAINS,
    DIRECT_HOST_DOMAINS,
    RESOLVE_MAX_HOPS,
    RESOLVE_TIMEOUT,
    RESOLVE_USE_BROWSER_FALLBACK,
    RESOLVE_BROWSER_TIMEOUT,
    DEFAULT_HEADERS,
)

log = logging.getLogger("nestfetch.link_resolver")
_BROWSER_UNAVAILABLE_LOGGED = False


# ── Link type constants ────────────────────────────────────────
DIRECT = "DIRECT"
SHORTENER = "SHORTENER"
AD_GATE = "AD_GATE"
UNKNOWN = "UNKNOWN"

# Common query-param keys that carry the wrapped destination URL.
_EMBED_KEYS = (
    "url", "target", "dest", "destination", "link", "u", "r", "to",
    "redirect", "out", "goto", "continue",
)

_META_REFRESH_RE = re.compile(
    r'http-equiv=["\']?refresh["\']?[^>]*content=["\'][^"\']*?url=([^"\'>\s]+)',
    re.I,
)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)


@dataclass
class ResolveResult:
    """Outcome of attempting to unwrap a link."""
    original_url: str
    final_url: str
    link_type: str      # classification of the ORIGINAL link
    resolved: bool      # True if we reached a real (non-gate) destination
    hops: int
    method: str         # last technique used
    note: str


# ── Domain helpers ────────────────────────────────────────
def _domain(url: str) -> str:
    try:
        net = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if net.startswith("www."):
        net = net[4:]
    if ":" in net:
        net = net.split(":", 1)[0]
    return net


def _matches(domain: str, patterns) -> bool:
    for p in patterns:
        p = p.lower()
        if domain == p or domain.endswith("." + p):
            return True
    return False


def classify_url(url: str) -> str:
    """Classify a URL as DIRECT / SHORTENER / AD_GATE / UNKNOWN by its domain."""
    if not url or url.strip().upper() in ("", "N/A"):
        return UNKNOWN
    d = _domain(url)
    if not d:
        return UNKNOWN
    if _matches(d, DIRECT_HOST_DOMAINS):
        return DIRECT
    if _matches(d, AD_GATE_DOMAINS):
        return AD_GATE
    if _matches(d, SHORTENER_DOMAINS):
        return SHORTENER
    return UNKNOWN


# ── Unwrap techniques ─────────────────────────────────────
def _looks_like_http(s: Optional[str]) -> bool:
    return isinstance(s, str) and s.lower().startswith(("http://", "https://"))


def _try_base64(value: str) -> Optional[str]:
    """If `value` is a base64-encoded http URL, decode and return it."""
    s = (value or "").strip()
    if len(s) < 12 or not re.fullmatch(r"[A-Za-z0-9+/=_-]+", s):
        return None
    for candidate in (s, s + "=" * (-len(s) % 4)):
        try:
            dec = base64.urlsafe_b64decode(candidate.encode()).decode("utf-8", "ignore")
        except Exception:
            continue
        if _looks_like_http(dec):
            return dec
    return None


def _extract_embedded_target(url: str) -> Optional[str]:
    """Pull a wrapped destination out of the URL's own query string."""
    try:
        q = parse_qs(urlparse(url).query)
    except Exception:
        return None
    for key in _EMBED_KEYS:
        for raw in q.get(key, []):
            val = unquote(raw)
            if _looks_like_http(val):
                return val
            decoded = _try_base64(val)
            if decoded:
                return decoded
    return None


def _read_body(resp, limit: int = 200_000) -> str:
    try:
        raw = next(resp.iter_content(chunk_size=limit), b"")
        if isinstance(raw, bytes):
            return raw.decode("utf-8", "ignore")
        return raw or ""
    except Exception:
        return ""


def _extract_from_html(html: str, base_url: str) -> Optional[str]:
    """Find a destination in the HTML: <meta refresh> or a known-host link."""
    if not html:
        return None
    m = _META_REFRESH_RE.search(html)
    if m:
        tgt = urljoin(base_url, unquote(m.group(1).strip().strip('"\'')))
        if _looks_like_http(tgt):
            return tgt
    for href in _HREF_RE.findall(html):
        full = urljoin(base_url, href.strip())
        if _looks_like_http(full) and _matches(_domain(full), DIRECT_HOST_DOMAINS):
            return full
    return None


def _default_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s


# ── Headless-browser fallback (optional, heavy) ──────────────
# Text on the "continue / get link" buttons ad-gates typically show.
_CONTINUE_TEXTS = (
    "get link", "get download link", "continue", "get download", "download now",
    "proceed", "skip ad", "skip", "go to link", "get url", "click here to continue",
    "generate link", "get link now",
)


def _browser_pick_direct(page) -> Optional[str]:
    """Scan the current page for an anchor pointing at a known direct host."""
    try:
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
    except Exception:
        hrefs = []
    for href in hrefs:
        if _looks_like_http(href) and _matches(_domain(href), DIRECT_HOST_DOMAINS):
            return href
    return None


def _resolve_with_browser(url: str, timeout: int = RESOLVE_BROWSER_TIMEOUT) -> Optional[str]:
    """
    Heavyweight fallback: drive a headless Chromium through an ad-gate (wait out
    the countdown, click the continue/get-link button) and return the first link
    to a known direct host that appears.

    Requires the optional 'playwright' package + its Chromium browser:
        pip install playwright && python -m playwright install chromium

    Returns None (never raises) if Playwright is unavailable or nothing is found.
    """
    global _BROWSER_UNAVAILABLE_LOGGED
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        if not _BROWSER_UNAVAILABLE_LOGGED:
            log.warning(
                "Browser fallback requested but Playwright is not installed. Run: "
                "pip install playwright && python -m playwright install chromium"
            )
            _BROWSER_UNAVAILABLE_LOGGED = True
        return None

    deadline_ms = max(5, timeout) * 1000
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(user_agent=DEFAULT_HEADERS.get("User-Agent"))
                page = ctx.new_page()
                page.set_default_timeout(deadline_ms)
                page.goto(url, wait_until="domcontentloaded", timeout=deadline_ms)

                # (a) destination may already be linked on the landing page
                found = _browser_pick_direct(page)
                if found:
                    return found

                # (b) wait out the countdown, click likely "continue" buttons,
                #     and re-scan until we find a direct host or run out of time.
                start = time.monotonic()
                while (time.monotonic() - start) < timeout:
                    for text in _CONTINUE_TEXTS:
                        try:
                            btn = page.get_by_text(text, exact=False).first
                            if btn and btn.is_visible():
                                btn.click(timeout=2000)
                                page.wait_for_load_state("domcontentloaded", timeout=5000)
                        except Exception:
                            pass
                    found = _browser_pick_direct(page)
                    if found:
                        return found
                    if _matches(_domain(page.url), DIRECT_HOST_DOMAINS):
                        return page.url
                    time.sleep(1.0)
                return None
            finally:
                browser.close()
    except Exception as exc:
        log.warning("Browser fallback failed: %s", type(exc).__name__)
        return None


# ── Public API ───────────────────────────────────────────
def resolve_url(
    url: str,
    session: Optional[requests.Session] = None,
    max_hops: int = RESOLVE_MAX_HOPS,
    timeout: int = RESOLVE_TIMEOUT,
    use_browser: Optional[bool] = None,
    browser_timeout: int = RESOLVE_BROWSER_TIMEOUT,
) -> ResolveResult:
    """
    Best-effort unwrap a shortener / ad-gate link to its real destination.

    Never raises on network errors — returns a ResolveResult describing how far
    it got. DIRECT and UNKNOWN links are returned unchanged (no network calls).
    """
    original = url or ""
    ltype = classify_url(original)
    if use_browser is None:
        use_browser = RESOLVE_USE_BROWSER_FALLBACK

    if not original or original.strip().upper() in ("", "N/A"):
        return ResolveResult(original, original, UNKNOWN, False, 0, "none", "empty link")
    if ltype == DIRECT:
        return ResolveResult(original, original, DIRECT, True, 0, "already-direct",
                             "already a direct host link")
    if ltype == UNKNOWN:
        return ResolveResult(original, original, UNKNOWN, True, 0, "assumed-direct",
                             "unknown domain, treated as final")

    sess = session or _default_session()
    current = original
    hops = 0
    method = "none"
    visited: set = set()

    while hops < max_hops:
        if current in visited:
            break
        visited.add(current)

        # A) destination embedded in the URL itself
        emb = _extract_embedded_target(current)
        if emb and emb != current:
            current = emb
            hops += 1
            method = "embedded-param"
            if classify_url(current) == DIRECT:
                return ResolveResult(original, current, ltype, True, hops, method,
                                     "resolved to direct host")
            continue

        # B) fetch and follow HTTP redirects
        try:
            resp = sess.get(current, timeout=timeout, allow_redirects=True, stream=True)
        except requests.RequestException as exc:
            return ResolveResult(original, current, ltype, current != original, hops,
                                 method, f"error: {type(exc).__name__}")
        landed = str(getattr(resp, "url", current) or current)
        body = _read_body(resp)
        try:
            resp.close()
        except Exception:
            pass

        if landed and landed != current:
            current = landed
            hops += 1
            method = "http-redirect"
            ct = classify_url(current)
            if ct == DIRECT:
                return ResolveResult(original, current, ltype, True, hops, method,
                                     "resolved to direct host")
            if ct == UNKNOWN:
                return ResolveResult(original, current, ltype, True, hops, method,
                                     "resolved (best-effort)")
            continue

        # C) look inside the HTML for the destination
        tgt = _extract_from_html(body, current)
        if tgt and tgt != current:
            current = tgt
            hops += 1
            method = "html-extract"
            if classify_url(current) == DIRECT:
                return ResolveResult(original, current, ltype, True, hops, method,
                                     "resolved to direct host")
            continue

        break  # nothing advanced this round

    final_type = classify_url(current)
    resolved = (current != original) and final_type not in (AD_GATE, SHORTENER)

    # D) heavyweight fallback: drive a real (headless) browser through the
    #    ad-gate timer/JS when the lightweight methods stalled on a gate.
    if not resolved and final_type in (AD_GATE, SHORTENER) and use_browser:
        browser_target = _resolve_with_browser(current, timeout=browser_timeout)
        if browser_target and browser_target != current:
            current = browser_target
            hops += 1
            method = "browser"
            final_type = classify_url(current)
            resolved = final_type not in (AD_GATE, SHORTENER)

    if final_type == DIRECT:
        note = "resolved to direct host"
    elif final_type in (AD_GATE, SHORTENER):
        note = ("ad-gate not solved automatically (manual step needed)"
                if use_browser
                else "still behind a shortener/ad-gate (enable browser fallback or open manually)")
    else:
        note = "resolved (best-effort)" if current != original else "could not unwrap"
    return ResolveResult(original, current, ltype, resolved, hops, method, note)
