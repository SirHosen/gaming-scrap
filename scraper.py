#!/usr/bin/env python3
"""
SwitchRoms Scraper v3.1 — Main entry point.

A professional, modular Nintendo Switch ROM metadata scraper.

Architecture:
  config.py      → All tunable parameters
  logger.py      → Coloured console + file logging
  models.py      → Dataclass-based data models
  http_client.py → Retry, backoff, session reuse
  parsers.py     → Pure BeautifulSoup parsing (no network)
  engine.py      → Concurrency orchestration + auto-paginate
  exporters.py   → JSON / CSV output (Excel-friendly CSV with UTF-8 BOM)
  cli.py         → Argparse + interactive menu
  scraper.py     → This file (entry point)

Usage:
  python scraper.py                          # interactive mode
  python scraper.py --search Mario --pages 3  # CLI mode
  python scraper.py --all                     # scrape entire site
  python scraper.py --help                    # full help
"""

from __future__ import annotations

import logging

from cli import parse_args, print_banner
from engine import ScraperEngine
from exporters import export_data
from logger import log, Colours


def print_summary(games, elapsed: float) -> None:
    """Print a coloured summary of the scraping run."""
    total_mirrors = sum(len(g.mirrors) for g in games)
    print(f"\n{Colours.GREEN}{Colours.BOLD}══════════════════ SCRAPING SUMMARY ══════════════════{Colours.RESET}")
    print(f"  Total Games Extracted  : {Colours.WHITE}{len(games)}{Colours.RESET}")
    print(f"  Total Mirror Links     : {Colours.WHITE}{total_mirrors}{Colours.RESET}")
    print(f"  Execution Duration     : {Colours.WHITE}{elapsed:.2f} seconds{Colours.RESET}")
    if games:
        print(f"  Average Speed          : {Colours.WHITE}{elapsed / len(games):.2f} sec/game{Colours.RESET}")
    print(f"{Colours.GREEN}══════════════════════════════════════════════════════{Colours.RESET}\n")


def main() -> None:
    """Entry point: parse config, run scraper, export results."""
    print_banner()

    search_q, max_p, fmt_filter, hoster_filter, out_fmt, delay, workers, verbose, scrape_all = parse_args()

    if verbose:
        log.setLevel(logging.DEBUG)

    if scrape_all:
        log.info("Configuration: mode=ALL SITE | format=%s | hoster=%s | output=%s | workers=%d",
                 fmt_filter, hoster_filter, out_fmt, workers)
    else:
        log.info("Configuration: search=%s | pages=%d | format=%s | hoster=%s | output=%s | workers=%d",
                 search_q or "(none)", max_p, fmt_filter, hoster_filter, out_fmt, workers)

    # ── Run scraper ────────────────────────────────────────────────────
    engine = ScraperEngine(
        delay=delay,
        max_workers=workers,
        format_filter=fmt_filter,
        hoster_filter=hoster_filter,
    )

    games, elapsed = engine.run(
        search_query=search_q,
        max_pages=max_p,
        scrape_all=scrape_all,
    )

    # ── Export results ────────────────────────────────────────────────
    if games:
        log.info("%s--- Exporting results ---%s", Colours.CYAN, Colours.RESET)
        export_data(games, out_fmt)
        print_summary(games, elapsed)
    else:
        log.warning("Scraping completed but no links matched your filters/search.")

    log.info("%s[FINISHED]%s System terminated successfully.", Colours.BOLD + Colours.GREEN, Colours.RESET)


if __name__ == "__main__":
    main()
