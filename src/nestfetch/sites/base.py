#!/usr/bin/env python3
"""
SiteAdapter — the contract every supported download site must fulfil.

This is the heart of NESTfetch's multi-site architecture. The scraping engine
(`engine.py`) knows nothing about any specific website; it only talks to a
`SiteAdapter`. To support a new game-download site you simply create a new
subclass here (in its own module under `sites/`) and register it in
`sites/registry.py` — no changes to the engine are needed.

The pipeline the engine drives, per site:

    listing page(s)  -> parse_listing()      -> [Game stubs]
    (full site)      -> discover_all_urls()   -> [detail URLs]
    detail/download  -> parse_mirrors()       -> [Mirror stubs]
    redirect page    -> resolve_final_link()  -> final hoster URL

Parsing methods MUST be pure (HTML string in, data out — no network calls) so
they can be unit-tested offline. Only `discover_all_urls()` receives the HTTP
client, because full-site discovery is inherently network-driven.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict

from nestfetch.models import Game, Mirror


@dataclass(frozen=True)
class SiteMeta:
    """Static, declarative description of a supported site."""
    name: str                 # unique slug used on the CLI, e.g. "switchroms"
    base_url: str             # site root, e.g. "https://switchroms.io/"
    category: str             # "switch-rom" | "windows" | "emulator" | "linux" ...
    platform: str             # human label, e.g. "Nintendo Switch"
    description: str = ""      # one-line summary for --list-sites


class SiteAdapter(ABC):
    """Abstract base class for a single game-download site."""

    #: Subclasses MUST set this to a SiteMeta instance.
    meta: SiteMeta

    #: Whether this site supports a reliable "scrape the entire site" mode
    #: (e.g. via an XML sitemap). If False, only paginated/search scraping runs.
    supports_full_site: bool = False

    #: Whether the engine must fetch each mirror's redirect page and call
    #: resolve_final_link() to obtain the final URL. Set False when a site's
    #: mirror links are already final, or only resolvable via JS/captcha (the
    #: engine then keeps redirect_url as the mirror link, e.g. DODI Repacks).
    resolves_final_link: bool = True

    #: Two-step sites link from a detail page to a *separate* download-index
    #: page whose URL cannot be derived from the detail URL alone (it needs a
    #: value scraped from the detail page, e.g. a numeric post id). When True,
    #: the engine fetches the detail page and calls build_index_url_from_detail().
    needs_detail_page: bool = False

    # ── convenience passthroughs ───────────────────────────────────────
    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def base_url(self) -> str:
        return self.meta.base_url

    @property
    def category(self) -> str:
        return self.meta.category

    @property
    def platform(self) -> str:
        return self.meta.platform

    def stamp(self, game: Game) -> Game:
        """Tag a Game with this site's provenance (source/category/platform)."""
        game.source_site = self.name
        game.category = self.category
        game.platform = self.platform
        return game

    # ── REQUIRED: listing + mirror pipeline ────────────────────────────
    @abstractmethod
    def build_listing_url(self, page: int, query: Optional[str] = None) -> str:
        """Return the URL of listing/search page `page` (1-based)."""

    @abstractmethod
    def parse_listing(self, html: str) -> List[Game]:
        """Parse a listing/search page into Game stubs (title + detail_url + meta)."""

    @abstractmethod
    def build_download_index_url(self, detail_url: str) -> str:
        """Return the URL that lists a game's download mirrors."""

    @abstractmethod
    def parse_mirrors(
        self,
        html: str,
        detail_url: str,
        format_filter: str = "ALL",
        hoster_filter: str = "ALL",
    ) -> List[Mirror]:
        """Parse the mirror-index page into Mirror stubs (with redirect_url set)."""

    @abstractmethod
    def resolve_final_link(self, html: str) -> str:
        """Parse a redirect page and return the final direct hoster URL (or 'N/A')."""

    # ── OPTIONAL: full-site discovery + title recovery ─────────────────
    def discover_all_urls(self, client) -> List[str]:
        """Return every game detail URL on the site (full-site scrape).

        Default: not supported. Override when `supports_full_site` is True.
        `client` is the engine's HttpClient (has `.get(url) -> Optional[str]`).
        """
        return []

    def slug_to_title(self, url: str) -> str:
        """Best-effort human title from a URL slug (fallback for sitemap stubs)."""
        from urllib.parse import urlparse
        slug = urlparse(url).path.strip("/").split("/")[-1]
        words = slug.replace("-", " ").replace("_", " ").split()
        return " ".join(w.capitalize() for w in words) if words else "Unknown Title"

    def parse_detail_title(self, html: str) -> Optional[str]:
        """Recover a game's real title from its detail page (used for sitemap stubs)."""
        return None

    def build_index_url_from_detail(self, detail_html: str, detail_url: str) -> Optional[str]:
        """Given a fetched detail page, return the download-index URL to fetch
        next (for two-step sites). Default: None (single-step sites)."""
        return None

    # ── OPTIONAL: interactive filter menus (per-site) ──────────────────
    def format_choices(self) -> Dict[str, str]:
        """Menu options for the format filter: {menu_key: FILTER_VALUE}."""
        return {"1": "ALL"}

    def hoster_choices(self) -> Dict[str, str]:
        """Menu options for the hoster filter: {menu_key: FILTER_VALUE}."""
        return {"1": "ALL"}
