#!/usr/bin/env python3
"""
Core scraping engine — orchestrates HTTP + parsing + concurrency.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

from config import (
    MAX_WORKERS, BASE_URL, SITEMAP_CANDIDATES, SITEMAP_SKIP_KEYWORDS,
)
from logger import log, Colours
from http_client import HttpClient
from models import Game, Mirror
from parsers import (
    build_page_url,
    build_download_index_url,
    parse_listing_page,
    parse_mirror_index,
    parse_final_download_link,
    parse_sitemap_locs,
    is_probable_game_url,
    parse_detail_title,
    slug_to_title,
)


class ScraperEngine:
    """High-level orchestrator that sweeps listing pages and resolves mirrors."""

    def __init__(
        self,
        delay: float = 1.0,
        max_workers: int = MAX_WORKERS,
        format_filter: str = "ALL",
        hoster_filter: str = "ALL",
    ):
        self.client = HttpClient(delay=delay)
        self.max_workers = max_workers
        self.format_filter = format_filter
        self.hoster_filter = hoster_filter

    # ── public API ─────────────────────────────────────────────────────

    def run(
        self,
        search_query: Optional[str] = None,
        max_pages: int = 1,
        scrape_all: bool = False,
    ) -> Tuple[List[Game], float]:
        """
        Execute a full scrape run.

        Args:
            search_query: Optional keyword to search for.
            max_pages: Number of listing pages to scrape (ignored if scrape_all).
            scrape_all: If True, auto-paginate through every page until empty.

        Returns (list_of_games, elapsed_seconds).
        """
        start = time.time()
        all_games: List[Game] = []

        if scrape_all:
            log.info("%s--- Starting FULL SITE scrape ---%s", Colours.CYAN, Colours.RESET)
            # Preferred path: discover every game via the XML sitemap, because
            # switchroms.io's /page/N/ pagination loops back to page 1.
            game_urls = self._discover_all_game_urls_via_sitemap()
            if game_urls:
                all_games = self._resolve_from_urls(game_urls)
                elapsed = time.time() - start
                self.client.close()
                log.info(
                    "%sFull-site scrape complete: %d games with mirrors from %d pages.%s",
                    Colours.CYAN, len(all_games), len(game_urls), Colours.RESET,
                )
                return all_games, elapsed
            log.warning(
                "Sitemap discovery unavailable — falling back to /page/N/ "
                "pagination with de-duplication (likely limited to the latest games)."
            )
        else:
            log.info("%s--- Starting scraping session ---%s", Colours.CYAN, Colours.RESET)

        page = 1
        seen_urls: set = set()
        while True:
            # Determine if we should stop
            if not scrape_all and page > max_pages:
                break

            target_url = build_page_url(page, search_query)
            if scrape_all:
                log.info("[PAGE %d] Fetching: %s", page, target_url)
            else:
                log.info("[PAGE %d/%d] Fetching: %s", page, max_pages, target_url)

            html = self.client.get(target_url)
            if not html:
                log.warning("Could not retrieve page %d — skipping.", page)
                if scrape_all:
                    log.info("Stopping auto-paginate (page %d unreachable).", page)
                    break
                page += 1
                continue

            page_games = parse_listing_page(html)
            if not page_games:
                log.info("No games found on page %d — ending page sweep.", page)
                break

            # ── Deduplicate: switchroms.io sometimes serves the SAME listing
            #    on every /page/N/ URL (pagination loops back to the homepage).
            #    Keep only games whose detail_url has not been seen before. ──
            new_games = [g for g in page_games if g.detail_url not in seen_urls]
            duplicate_count = len(page_games) - len(new_games)

            if not new_games:
                log.warning(
                    "Page %d returned %d games but ALL are duplicates already "
                    "scraped — the site is not serving new content for this page "
                    "(pagination likely loops back to page 1). Ending scrape.",
                    page, len(page_games),
                )
                break

            for g in new_games:
                seen_urls.add(g.detail_url)

            if duplicate_count:
                log.info(
                    "Found %d games on page %d (%d new, %d duplicates skipped).",
                    len(page_games), page, len(new_games), duplicate_count,
                )
            else:
                log.info("Found %d games on page %d.", len(page_games), page)

            # Resolve mirrors concurrently for this page's NEW games only
            resolved = self._resolve_games_concurrent(new_games)
            all_games.extend(resolved)

            if scrape_all:
                log.info("%sProgress: %d unique games scraped so far…%s", Colours.YELLOW, len(all_games), Colours.RESET)

            page += 1

        elapsed = time.time() - start
        self.client.close()
        return all_games, elapsed

    # ── internal ──────────────────────────────────────────────────────

    def _discover_all_game_urls_via_sitemap(self) -> List[str]:
        """Crawl the site's XML sitemap(s) to collect every game detail URL."""
        # 1. Locate a working root sitemap
        root_xml: Optional[str] = None
        for candidate in SITEMAP_CANDIDATES:
            url = BASE_URL.rstrip("/") + "/" + candidate
            log.info("Looking for sitemap: %s", url)
            xml = self.client.get(url)
            if xml and "<loc" in xml.lower():
                root_xml = xml
                log.info("Using sitemap: %s", url)
                break
        if not root_xml:
            return []

        locs = parse_sitemap_locs(root_xml)
        sub_sitemaps = [u for u in locs if u.lower().endswith(".xml")]
        game_urls: List[str] = []
        seen: set = set()

        def _collect(candidate_urls: List[str]) -> None:
            for u in candidate_urls:
                if u.lower().endswith(".xml"):
                    continue
                if is_probable_game_url(u) and u not in seen:
                    seen.add(u)
                    game_urls.append(u)

        if sub_sitemaps:
            # This is a sitemap index — fetch each relevant sub-sitemap
            for sm in sub_sitemaps:
                if any(k in sm.lower() for k in SITEMAP_SKIP_KEYWORDS):
                    log.debug("Skipping non-content sitemap: %s", sm)
                    continue
                log.info("Reading sub-sitemap: %s", sm)
                xml = self.client.get(sm)
                if xml:
                    _collect(parse_sitemap_locs(xml))
        else:
            # Single flat sitemap
            _collect(locs)

        log.info(
            "%sSitemap discovery found %d candidate game pages.%s",
            Colours.CYAN, len(game_urls), Colours.RESET,
        )
        return game_urls

    def _resolve_from_urls(self, game_urls: List[str]) -> List[Game]:
        """Resolve a large list of game detail URLs in progress-logged batches."""
        stubs = [
            Game(
                title=slug_to_title(u),
                meta_size="N/A",
                meta_genre="N/A",
                detail_url=u,
            )
            for u in game_urls
        ]
        collected: List[Game] = []
        batch_size = 40
        total = len(stubs)
        for i in range(0, total, batch_size):
            batch = stubs[i:i + batch_size]
            collected.extend(self._resolve_games_concurrent(batch))
            done = min(i + batch_size, total)
            log.info(
                "%sProgress: %d/%d pages processed, %d games with mirrors so far…%s",
                Colours.YELLOW, done, total, len(collected), Colours.RESET,
            )
        return collected

    def _resolve_games_concurrent(self, games: List[Game]) -> List[Game]:
        """Resolve mirrors for a batch of games using a thread pool."""
        results: List[Game] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_map = {
                pool.submit(self._scrape_single_game, game): game
                for game in games
            }

            for idx, future in enumerate(as_completed(future_map), 1):
                game = future_map[future]
                try:
                    resolved = future.result()
                    if resolved and resolved.mirrors:
                        results.append(resolved)
                        log.info(
                            "  [%d] %s%s%s — %d mirrors",
                            idx,
                            Colours.BOLD,
                            resolved.title,
                            Colours.RESET,
                            len(resolved.mirrors),
                        )
                    else:
                        log.info("  [%d] %s — no mirrors matched filters.", idx, game.title)
                except Exception as exc:
                    log.error("  Error scraping '%s': %s", game.title, exc)

        return results

    def _scrape_single_game(self, game: Game) -> Optional[Game]:
        """Fetch and parse the mirror index for one game, then resolve final links."""
        download_index_url = build_download_index_url(game.detail_url)
        log.debug("Scraping mirror index: %s", download_index_url)

        html = self.client.get(download_index_url)
        if not html:
            return None

        # If this game was discovered via sitemap (title is a slug fallback),
        # upgrade it with the real title parsed from the page (no extra request).
        if game.title == slug_to_title(game.detail_url):
            real_title = parse_detail_title(html)
            if real_title:
                game.title = real_title

        mirrors = parse_mirror_index(
            html,
            game.detail_url,
            self.format_filter,
            self.hoster_filter,
        )

        # Resolve each mirror's final link
        for mirror in mirrors:
            log.debug("  Fetching final link: %s (%s)", mirror.hoster, mirror.format)
            redirect_html = self.client.get(mirror.redirect_url)
            if redirect_html:
                mirror.final_link = parse_final_download_link(redirect_html)
            else:
                mirror.final_link = "N/A"

        game.mirrors = mirrors
        return game
