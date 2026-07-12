#!/usr/bin/env python3
"""
Pure parsing functions — no network calls here.
All BeautifulSoup logic is isolated so it can be unit-tested independently.
"""

from __future__ import annotations

from urllib.parse import urljoin, quote_plus
from typing import List, Optional

from bs4 import BeautifulSoup

from config import BASE_URL
from models import Game, Mirror


# ── URL builders ───────────────────────────────────────────────────────────

def build_page_url(page_num: int, search_query: Optional[str] = None) -> str:
    """Generate a paginated listing/search URL in WordPress style."""
    if search_query:
        encoded = quote_plus(search_query)
        if page_num == 1:
            return f"{BASE_URL}?s={encoded}"
        return f"{BASE_URL}page/{page_num}/?s={encoded}"
    else:
        if page_num == 1:
            return BASE_URL
        return f"{BASE_URL}page/{page_num}/"


def build_download_index_url(detail_url: str) -> str:
    """Append /?download to a detail URL to get the mirror index page."""
    return detail_url.rstrip("/") + "/?download"


# ── Listing page parser ────────────────────────────────────────────────────

def parse_listing_page(html: str) -> List[Game]:
    """
    Parse a listing/search page and return a list of Game objects
    (with title, meta_size, meta_genre, detail_url populated).
    """
    soup = BeautifulSoup(html, "html.parser")
    post_items = soup.select(".list-post .post-item")
    games: List[Game] = []

    for item in post_items:
        link_tag = item.select_one("a.wrapper-item-title")
        if not link_tag or not link_tag.get("href"):
            continue

        detail_url = link_tag["href"]

        title_tag = item.select_one(".title-post")
        title = title_tag.get_text(strip=True) if title_tag else "No Title"

        meta_spans = item.select(".text-cat.version")
        meta_size = meta_spans[0].get_text(strip=True) if len(meta_spans) > 0 else "N/A"
        meta_genre = meta_spans[1].get_text(strip=True) if len(meta_spans) > 1 else "N/A"

        games.append(Game(
            title=title,
            meta_size=meta_size,
            meta_genre=meta_genre,
            detail_url=detail_url,
        ))

    return games


# ── Mirror index parser ────────────────────────────────────────────────────

def parse_mirror_index(
    html: str,
    detail_url: str,
    format_filter: str = "ALL",
    hoster_filter: str = "ALL",
) -> List[Mirror]:
    """
    Parse the /?download mirror index page.
    Pre-filters mirrors by format and hoster before the caller
    resolves each redirect URL.
    """
    soup = BeautifulSoup(html, "html.parser")
    mirrors: List[Mirror] = []

    for link in soup.select("a.a-link-button"):
        href = link.get("href")
        if not href:
            continue

        redirect_url = urljoin(BASE_URL, href)

        title_span = link.select_one(".link-title")
        raw_text = title_span.get_text(strip=True) if title_span else "Unknown Mirror"

        parts = [p.strip() for p in raw_text.split("|")]
        rom_format = parts[0] if len(parts) > 0 else "N/A"
        size       = parts[1] if len(parts) > 1 else "N/A"
        hoster     = parts[2] if len(parts) > 2 else "Unknown"

        # ── Pre-filter optimisation ─────────────────────────────────
        if format_filter != "ALL" and format_filter not in rom_format.upper():
            continue
        if hoster_filter != "ALL" and hoster_filter not in hoster.upper():
            continue

        mirrors.append(Mirror(
            raw_text=raw_text,
            format=rom_format,
            size=size,
            hoster=hoster,
            redirect_url=redirect_url,
        ))

    return mirrors


# ── Redirect page parser ───────────────────────────────────────────────────

def parse_final_download_link(html: str) -> str:
    """
    Parse a ?download=X redirect page and return the final file-hoster URL.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Strategy A: active download button
    link = soup.select_one("#download-active a")
    if not link:
        # Strategy B: fallback paragraph link
        link = soup.select_one(".aligncenter.mt-2 a")

    if link and link.get("href"):
        return link["href"]

    return "N/A"
