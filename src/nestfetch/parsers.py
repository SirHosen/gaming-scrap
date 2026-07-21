#!/usr/bin/env python3
"""
Pure parsing functions — no network calls here.
All BeautifulSoup logic is isolated so it can be unit-tested independently.
"""

from __future__ import annotations

import re
import warnings
from urllib.parse import urljoin, quote_plus, urlparse
from typing import List, Optional

from bs4 import BeautifulSoup

try:  # silence noisy warning when parsing XML sitemaps with the HTML parser
    from bs4 import XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:
    pass

from nestfetch.config import BASE_URL
from nestfetch.models import Game, Mirror


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


# Trailing slug tokens that are ROM-listing noise rather than part of a title.
_SLUG_NOISE = {"nsp", "xci", "nsz", "nsw", "rom", "roms", "switch", "eshop"}


def slug_to_title(url: str) -> str:
    """Derive a human-ish title from a detail URL slug (fallback only)."""
    slug = urlparse(url).path.strip("/").split("/")[-1]
    words = slug.replace("-", " ").split()
    # strip trailing noise tokens and standalone numbers (e.g. "...-switch-rom-5")
    while words and (words[-1].lower() in _SLUG_NOISE or words[-1].isdigit()):
        words.pop()
    return " ".join(w.capitalize() for w in words) if words else "Unknown Title"


def _strip_site_suffix(title: str) -> str:
    """Remove only a trailing ' - SwitchRoms'-style site-name suffix (safe for
    titles that legitimately contain dashes)."""
    return re.sub(
        r"\s*[|\-–—»]\s*Switch\s*Roms?\s*$", "", title, flags=re.IGNORECASE
    ).strip()


# Markers that indicate the start of ROM-listing noise appended to a page title,
# e.g. "Mario Kart 8 Deluxe NSP XCI Switch Rom V1.0 [UPDATE] Free Download".
_TITLE_CUT_RE = re.compile(
    r"\s+(?:NSP\b|XCI\b|NSZ\b|NSW\b|Switch\s+Rom\b|Free\s+Download\b|\[).*$",
    re.IGNORECASE,
)
_RELEASE_TAG_RE = re.compile(r"\[(UPDATE|DLC|BASE|DEMO)\]", re.IGNORECASE)


def _clean_game_title(raw: str) -> str:
    """
    Turn a noisy SEO page title into a clean game name, preserving a release
    tag when present.

    "The Legend of Zelda: Tears of the Kingdom NSP, XCI Switch Rom V1.2.1
    [UPDATE] Free Download"
        -> "The Legend of Zelda: Tears of the Kingdom [UPDATE]"
    """
    title = _strip_site_suffix(raw.strip())
    # Preserve a release-type tag (UPDATE / DLC / BASE / DEMO) if present.
    tag_match = _RELEASE_TAG_RE.search(title)
    tag = f" [{tag_match.group(1).upper()}]" if tag_match else ""
    # Cut everything from the first ROM-listing marker onward.
    cut = _TITLE_CUT_RE.search(title)
    if cut:
        title = title[: cut.start()]
    title = title.strip(" -–—|,").strip()
    return f"{title}{tag}" if title else title


# ── Sitemap parsers (full-site discovery) ──────────────────────────────

def parse_sitemap_locs(xml: str) -> List[str]:
    """Return every <loc> URL from a sitemap or sitemap index (order preserved)."""
    soup = BeautifulSoup(xml, "html.parser")
    return [
        loc.get_text(strip=True)
        for loc in soup.find_all("loc")
        if loc.get_text(strip=True)
    ]


def is_probable_game_url(url: str) -> bool:
    """
    Heuristic test for whether a sitemap URL is a game detail page.
    Game pages on switchroms.io are a single slug segment directly under the
    domain root, e.g. https://switchroms.io/super-mario-bros-wonder/.
    """
    path = urlparse(url).path.strip("/")
    if not path:
        return False
    lowered = path.lower()
    skip = (
        "category/", "tag/", "author/", "page/", "wp-content",
        "wp-json", "feed", "comments", "sitemap", ".xml",
    )
    if any(s in lowered for s in skip):
        return False
    # game detail URLs are a single slug segment (no nested path)
    return "/" not in path


def parse_detail_title(html: str) -> Optional[str]:
    """
    Best-effort extraction of a game's title from its detail/download page.

    IMPORTANT: switchroms.io detail pages contain a "latest games" sidebar
    widget that reuses the `.title-post` class from the listing page. Reading
    that class here would return the newest game on EVERY page (e.g. always
    "Atelier Yumia..."), which is exactly the duplicate-title bug we must avoid.
    So we rely only on per-page unique sources: og:title, the document <title>,
    then a scoped main-content <h1>.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. Open Graph title (set per-post by the SEO plugin) — most reliable
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content") and og["content"].strip():
        cleaned = _clean_game_title(og["content"])
        if cleaned:
            return cleaned

    # 2. Twitter title fallback
    tw = soup.find("meta", attrs={"name": "twitter:title"})
    if tw and tw.get("content") and tw["content"].strip():
        cleaned = _clean_game_title(tw["content"])
        if cleaned:
            return cleaned

    # 3. Document <title>
    if soup.title and soup.title.get_text(strip=True):
        cleaned = _clean_game_title(soup.title.get_text(strip=True))
        if cleaned:
            return cleaned

    # 4. Scoped main-content heading. switchroms.io uses <h1 class="h1-title">.
    #    NEVER read `.title-post` — that is the "Recommended for You" widget
    #    which repeats the same newest game on every detail page.
    for selector in ("h1.h1-title", "h1.entry-title", "h1.post-title", "h1.title-single"):
        tag = soup.select_one(selector)
        if tag and tag.get_text(strip=True):
            cleaned = _clean_game_title(tag.get_text(strip=True))
            if cleaned:
                return cleaned

    return None


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
