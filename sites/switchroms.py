#!/usr/bin/env python3
"""
SwitchRoms adapter — switchroms.io (Nintendo Switch ROMs: NSP / XCI / NSZ).

This is the reference SiteAdapter implementation and a straight migration of
NESTfetch's original single-site logic. All the actual HTML parsing still lives
in the site-specific `parsers.py`; this adapter simply wires those pure
functions into the generic `SiteAdapter` contract, and owns full-site
discovery via the XML sitemap (which used to live inside the engine).
"""

from __future__ import annotations

from typing import List, Optional, Dict

import parsers
from config import (
    BASE_URL, SITEMAP_CANDIDATES, SITEMAP_SKIP_KEYWORDS,
    FORMAT_MAP, HOSTER_MAP,
)
from logger import log, Colours
from models import Game, Mirror
from sites.base import SiteAdapter, SiteMeta


class SwitchRomsAdapter(SiteAdapter):
    """Adapter for https://switchroms.io/."""

    meta = SiteMeta(
        name="switchroms",
        base_url=BASE_URL,
        category="switch-rom",
        platform="Nintendo Switch",
        description="Nintendo Switch ROMs (NSP/XCI/NSZ) — switchroms.io",
    )
    supports_full_site = True

    # ── listing + mirror pipeline (delegates to parsers.py) ────────────
    def build_listing_url(self, page: int, query: Optional[str] = None) -> str:
        return parsers.build_page_url(page, query)

    def parse_listing(self, html: str) -> List[Game]:
        return parsers.parse_listing_page(html)

    def build_download_index_url(self, detail_url: str) -> str:
        return parsers.build_download_index_url(detail_url)

    def parse_mirrors(
        self,
        html: str,
        detail_url: str,
        format_filter: str = "ALL",
        hoster_filter: str = "ALL",
    ) -> List[Mirror]:
        return parsers.parse_mirror_index(html, detail_url, format_filter, hoster_filter)

    def resolve_final_link(self, html: str) -> str:
        return parsers.parse_final_download_link(html)

    # ── title recovery for sitemap-discovered stubs ───────────────────
    def slug_to_title(self, url: str) -> str:
        return parsers.slug_to_title(url)

    def parse_detail_title(self, html: str) -> Optional[str]:
        return parsers.parse_detail_title(html)

    # ── per-site interactive filter menus ───────────────────────────
    def format_choices(self) -> Dict[str, str]:
        return dict(FORMAT_MAP)

    def hoster_choices(self) -> Dict[str, str]:
        return dict(HOSTER_MAP)

    # ── full-site discovery via XML sitemap ─────────────────────────
    def discover_all_urls(self, client) -> List[str]:
        """Crawl the site's XML sitemap(s) to collect every game detail URL.

        switchroms.io ignores /page/N/ pagination (every page loops back to the
        homepage listing), so a full scrape is driven by the XML sitemap, which
        reliably lists every individual game page.
        """
        # 1. Locate a working root sitemap
        root_xml: Optional[str] = None
        for candidate in SITEMAP_CANDIDATES:
            url = self.base_url.rstrip("/") + "/" + candidate
            log.info("Looking for sitemap: %s", url)
            xml = client.get(url)
            if xml and "<loc" in xml.lower():
                root_xml = xml
                log.info("Using sitemap: %s", url)
                break
        if not root_xml:
            return []

        locs = parsers.parse_sitemap_locs(root_xml)
        sub_sitemaps = [u for u in locs if u.lower().endswith(".xml")]
        game_urls: List[str] = []
        seen: set = set()

        def _collect(candidate_urls: List[str]) -> None:
            for u in candidate_urls:
                if u.lower().endswith(".xml"):
                    continue
                if parsers.is_probable_game_url(u) and u not in seen:
                    seen.add(u)
                    game_urls.append(u)

        if sub_sitemaps:
            # This is a sitemap index — fetch each relevant sub-sitemap
            for sm in sub_sitemaps:
                if any(k in sm.lower() for k in SITEMAP_SKIP_KEYWORDS):
                    log.debug("Skipping non-content sitemap: %s", sm)
                    continue
                log.info("Reading sub-sitemap: %s", sm)
                xml = client.get(sm)
                if xml:
                    _collect(parsers.parse_sitemap_locs(xml))
        else:
            # Single flat sitemap
            _collect(locs)

        log.info(
            "%sSitemap discovery found %d candidate game pages.%s",
            Colours.CYAN, len(game_urls), Colours.RESET,
        )
        return game_urls
