#!/usr/bin/env python3
"""
Core scraping engine — site-agnostic orchestration of HTTP + parsing + concurrency.

The engine knows NOTHING about any specific website. It is driven entirely by a
`SiteAdapter` (see `sites/base.py`), so the exact same orchestration logic works
for every supported site (ROM, Windows, emulator, Linux, ...). To add a site you
write an adapter, not new engine code.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

from config import MAX_WORKERS
from logger import log, Colours
from http_client import HttpClient
from models import Game
from sites.base import SiteAdapter


class ScraperEngine:
    """High-level orchestrator that sweeps listing pages and resolves mirrors
    for a single selected site (via its SiteAdapter)."""

    def __init__(
        self,
        adapter: SiteAdapter,
        delay: float = 1.0,
        max_workers: int = MAX_WORKERS,
        format_filter: str = "ALL",
        hoster_filter: str = "ALL",
    ):
        self.adapter = adapter
        self.client = HttpClient(delay=delay)
        self.max_workers = max_workers
        self.format_filter = format_filter
        self.hoster_filter = hoster_filter

    # ── public API ─────────────────────────────────────────────

    def run(
        self,
        search_query: Optional[str] = None,
        max_pages: int = 1,
        scrape_all: bool = False,
    ) -> Tuple[List[Game], float]:
        """
        Execute a full scrape run for the configured site.

        Args:
            search_query: Optional keyword to search for.
            max_pages: Number of listing pages to scrape (ignored if scrape_all).
            scrape_all: If True, scrape every game on the site (full-site mode).

        Returns (list_of_games, elapsed_seconds).
        """
        start = time.time()
        all_games: List[Game] = []
        site_label = f"{self.adapter.name} ({self.adapter.platform})"

        if scrape_all:
            log.info("%s--- Starting FULL SITE scrape: %s ---%s", Colours.CYAN, site_label, Colours.RESET)
            if self.adapter.supports_full_site:
                # Preferred path: discover every game via the adapter's own
                # full-site discovery (e.g. XML sitemap crawl).
                game_urls = self.adapter.discover_all_urls(self.client)
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
                    "Full-site discovery returned nothing — falling back to "
                    "paginated sweep with de-duplication."
                )
            else:
                log.warning(
                    "Site '%s' does not support full-site discovery — falling back "
                    "to paginated sweep with de-duplication.", self.adapter.name,
                )
        else:
            log.info("%s--- Starting scraping session: %s ---%s", Colours.CYAN, site_label, Colours.RESET)

        page = 1
        seen_urls: set = set()
        while True:
            # Determine if we should stop
            if not scrape_all and page > max_pages:
                break

            target_url = self.adapter.build_listing_url(page, search_query)
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

            page_games = self.adapter.parse_listing(html)
            if not page_games:
                log.info("No games found on page %d — ending page sweep.", page)
                break

            # ── Deduplicate: some sites serve the SAME listing on every /page/N/
            #    URL (pagination loops back to the homepage). Keep only games
            #    whose detail_url has not been seen before. ──
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

    # ── internal ───────────────────────────────────────────

    def _resolve_from_urls(self, game_urls: List[str]) -> List[Game]:
        """Resolve a large list of game detail URLs in progress-logged batches."""
        stubs = [
            self.adapter.stamp(Game(
                title=self.adapter.slug_to_title(u),
                meta_size="N/A",
                meta_genre="N/A",
                detail_url=u,
            ))
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
        # Ensure provenance is stamped even for listing-sourced games.
        self.adapter.stamp(game)

        download_index_url = self.adapter.build_download_index_url(game.detail_url)
        log.debug("Scraping mirror index: %s", download_index_url)

        html = self.client.get(download_index_url)
        if not html:
            return None

        # If this game was discovered via full-site mode (title is a slug
        # fallback), upgrade it with the real title parsed from the page.
        if game.title == self.adapter.slug_to_title(game.detail_url):
            real_title = self.adapter.parse_detail_title(html)
            if real_title:
                game.title = real_title

        mirrors = self.adapter.parse_mirrors(
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
                mirror.final_link = self.adapter.resolve_final_link(redirect_html)
            else:
                mirror.final_link = "N/A"

        game.mirrors = mirrors
        return game
