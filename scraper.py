#!/usr/bin/env python3
"""
NESTfetch v4.0 — Main entry point.

A professional, modular, MULTI-SITE game-download metadata scraper.
(Originally a single-site Nintendo Switch ROM scraper.)

Architecture:
  config.py      → All tunable parameters
  logger.py      → Coloured console + file logging
  models.py      → Dataclass-based data models (with source_site/category/platform)
  http_client.py → Retry, backoff, session reuse
  sites/         → Pluggable per-site adapters (base + registry + one file per site)
  parsers.py     → switchroms.io BeautifulSoup parsing (used by its adapter)
  engine.py      → Site-agnostic concurrency orchestration + auto-paginate
  exporters.py   → JSON / CSV output (Excel-friendly CSV with UTF-8 BOM)
  cli.py         → Argparse + interactive menu (site selection, --site, --list-sites)
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
from sites.registry import get_adapter, available_sites


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


def print_sites() -> None:
    """List every supported site and exit."""
    metas = available_sites()
    print(f"\n{Colours.CYAN}{Colours.BOLD}Supported sites ({len(metas)}):{Colours.RESET}")
    for m in metas:
        print(f"  {Colours.GREEN}{m.name}{Colours.RESET}")
        print(f"      Platform : {m.platform}")
        print(f"      Category : {m.category}")
        print(f"      URL      : {m.base_url}")
        if m.description:
            print(f"      {Colours.GREY}{m.description}{Colours.RESET}")
    print()


def run_link_check(params: dict) -> None:
    """Check whether links in a previously scraped CSV are still alive."""
    from link_checker import check_csv_links

    csv_path = params["csv_path"]
    log.info("%sLink check target:%s %s", Colours.CYAN, Colours.RESET, csv_path)
    report = check_csv_links(
        csv_path,
        output_path=params.get("output"),
        workers=params.get("workers", 5),
        delay=params.get("delay", 0.0),
    )
    if report:
        log.info("%s[FINISHED]%s Link check complete.", Colours.BOLD + Colours.GREEN, Colours.RESET)
    else:
        log.warning("Link check did not produce a report (see errors above).")


def main() -> None:
    """Entry point: parse config, run scraper or link checker."""
    print_banner()

    action, params = parse_args()

    if params.get("verbose"):
        log.setLevel(logging.DEBUG)

    # ── List-sites mode: show supported sites, then exit ───────────────
    if action == "list-sites":
        print_sites()
        return

    # ── Link-check mode: validate an existing CSV, then exit ────────────
    if action == "check":
        run_link_check(params)
        log.info("%s[FINISHED]%s System terminated successfully.", Colours.BOLD + Colours.GREEN, Colours.RESET)
        return

    # ── Scrape mode ────────────────────────────────────────────────────
    search_q = params["search"]
    max_p = params["pages"]
    fmt_filter = params["format"]
    hoster_filter = params["hoster"]
    out_fmt = params["output"]
    delay = params["delay"]
    workers = params["workers"]
    scrape_all = params["scrape_all"]

    if scrape_all:
        log.info("Configuration: mode=ALL SITE | format=%s | hoster=%s | output=%s | workers=%d",
                 fmt_filter, hoster_filter, out_fmt, workers)
    else:
        log.info("Configuration: search=%s | pages=%d | format=%s | hoster=%s | output=%s | workers=%d",
                 search_q or "(none)", max_p, fmt_filter, hoster_filter, out_fmt, workers)

    # ── Resolve the selected site adapter ──────────────────────────────
    site = params.get("site") or "switchroms"
    adapter = get_adapter(site)
    log.info("%sTarget site:%s %s (%s)", Colours.CYAN, Colours.RESET, adapter.name, adapter.platform)

    # ── Run scraper ────────────────────────────────────────────────────
    engine = ScraperEngine(
        adapter,
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
