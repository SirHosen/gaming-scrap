#!/usr/bin/env python3
"""
Core scraping engine — orchestrates HTTP + parsing + concurrency.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

from config import MAX_WORKERS
from logger import log, Colours
from http_client import HttpClient
from models import Game, Mirror
from parsers import (
    build_page_url,
    build_download_index_url,
    parse_listing_page,
    parse_mirror_index,
    parse_final_download_link,
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
            log.info("%s--- Starting FULL SITE scrape (auto-paginate) ---%s", Colours.CYAN, Colours.RESET)
        else:
            log.info("%s--- Starting scraping session ---%s", Colours.CYAN, Colours.RESET)

        page = 1
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

            log.info("Found %d games on page %d.", len(page_games), page)

            # Resolve mirrors concurrently for this page's games
            resolved = self._resolve_games_concurrent(page_games)
            all_games.extend(resolved)

            if scrape_all:
                log.info("%sProgress: %d games scraped so far…%s", Colours.YELLOW, len(all_games), Colours.RESET)

            page += 1

        elapsed = time.time() - start
        self.client.close()
        return all_games, elapsed

    # ── internal ──────────────────────────────────────────────────────

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
