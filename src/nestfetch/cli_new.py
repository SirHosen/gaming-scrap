#!/usr/bin/env python3
"""
CLI interface — argument parsing and interactive menu.
Supports both `--flags` for automation and interactive prompts for manual use.
"""

from __future__ import annotations

import argparse
from typing import Dict, Tuple

from nestfetch.config import (
    OUTPUT_MAP,
    CACHE_ENABLED_DEFAULT, ASYNC_ENABLED_DEFAULT, PER_HOST_RATE_LIMIT,
    WEB_DEFAULT_HOST, WEB_DEFAULT_PORT,
)
from nestfetch.logger import Colours
from nestfetch.sites.registry import available_sites, site_names, DEFAULT_SITE, get_adapter


# ── Banner ─────────────────────────────────────────────────────────────────

BANNER = f"""{Colours.CYAN}{Colours.BOLD}
  ════════════════════════════════════════════════════════════════════════════
   ███╗   ██╗███████╗███████╗████████╗███████╗███████╗████████╗ ██████╗██╗  ██╗
   ████╗  ██║██╔════╝██╔════╝╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝██╔════╝██║  ██║
   ██╔██╗ ██║█████╗  ███████╗   ██║   █████╗  █████╗     ██║   ██║     ███████║
   ██║╚██╗██║██╔══╝  ╚════██║   ██║   ██╔══╝  ██╔══╝     ██║   ██║     ██╔══██║
   ██║ ╚████║███████╗███████║   ██║   ██║     ███████╗   ██║   ╚██████╗██║  ██║
   ╚═╝  ╚═══╝╚══════╝╚══════╝   ╚═╝   ╚═╝     ╚══════╝   ╚═╝    ╚═════╝╚═╝  ╚═╝
              NESTfetch v4.9 — Multi-Site Game Download Scraper
  ════════════════════════════════════════════════════════════════════════════{Colours.RESET}"""


def print_banner() -> None:
    print(BANNER)


# ── Interactive menu ───────────────────────────────────────────────────────

def _prompt(label: str, default: str = "") -> str:
    """Helper: prompt with default value, return user input or default."""
    suffix = f" (default: {default})" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    return val if val else default


def _prompt_choice(title: str, choices: Dict[str, str], default_value: str = "ALL") -> str:
    """Render a {menu-number: value} choice dict and return the picked value.
    Dynamically generated per-site so each site presents its actual
    valid formats / hosters instead of a hard-coded switchroms list.
    """
    print(f"\n{Colours.BOLD}{title}:{Colours.RESET}")
    default_key = next((k for k, v in choices.items() if v == default_value), None)
    if default_key is None:
        default_key = next(iter(choices), "1")
    for key, value in choices.items():
        marker = f"  {Colours.GREY}(default){Colours.RESET}" if key == default_key else ""
        print(f"  [{key}] {value}{marker}")
    picked = _prompt("Select", default_key)
    return choices.get(picked, choices.get(default_key, default_value))


def interactive_menu() -> Tuple[str, dict]:
    """Interactively ask the user for scraping parameters.

    Returns (action, kwargs).
    """
    print_banner()

    # ── Step 0: choose which site to scrape ───────────────────────────
    sites = available_sites()
    site = DEFAULT_SITE
    if len(sites) > 1:
        site_choices = {str(i + 1): s for i, s in enumerate(site_names())}
        site = _prompt_choice("Choose Site to Scrape", site_choices, DEFAULT_SITE)

    adapter = get_adapter(site)

    # ── Step 1: choose operation mode ────────────────────────────────
    print(f"\n{Colours.BOLD}1. Select operation for [{site}]:{Colours.RESET}")
    print("  [1] Scrape homepage (page 1 only)")
    print("  [2] Search for games by keyword")
    print("  [3] Scrape multiple pages")
    print("  [4] Verify download links (Link Checker)")
    print("  [5] View scrape history (from database)")
    print("  [6] Export database to CSV / JSON")
    print("  [7] Watch mode (scheduler + notifications)")
    print("  [8] Test notification dispatch")
    print("  [9] Web dashboard")

    mode = _prompt("Select mode [1-9]", "1")

    # ── Mode 4: link checker (works on an existing CSV, no scraping) ─────
    if mode == "4":
        from nestfetch.link_checker import default_csv_path
        default_csv = str(default_csv_path(site))
        print(f"\n{Colours.BOLD}Link Checker — verify scraped download links{Colours.RESET}")
        print(f"  {Colours.GREY}Reads a scraped CSV and flags each link ACTIVE / DEAD / UNKNOWN.{Colours.RESET}")
        csv_path = _prompt("Path to scraped CSV", default_csv)
        workers_in = _prompt("Concurrent workers", "10")
        try:
            workers = int(workers_in)
        except ValueError:
            workers = 10
        return "check", {
            "csv_path": csv_path,
            "workers": workers,
            "site": site,
        }

    # ── Mode 5: show scrape history from the database ────────────────────
    if mode == "5":
        return "history", {
            "site": site,
        }

    # ── Mode 6: export previously scraped data from the database ─────────
    if mode == "6":
        print(f"\n{Colours.BOLD}Export from database — choose output format:{Colours.RESET}")
        print("  [1] Excel Spreadsheet (CSV)")
        print("  [2] Database File (JSON)")
        print("  [3] Both formats")
        exp_opt = _prompt("Select output format", "3")
        return "db-export", {
            "site": site,
            "output": OUTPUT_MAP.get(exp_opt, "both"),
        }

    # ── Mode 7: watch mode (scheduler + notifications) ───────────────────
    if mode == "7":
        from nestfetch.link_checker import default_csv_path
        print(f"\n{Colours.BOLD}Watch mode — periodic scrape/check with notifications{Colours.RESET}")
        print(f"  {Colours.GREY}Tip: configure channels in .env or config.yaml (see the *.example files).{Colours.RESET}")
        print("  [1] Scrape only")
        print("  [2] Check links only")
        print("  [3] Both scrape + check")
        task_opt = _prompt("Select task", "3")
        task = {"1": "scrape", "2": "check", "3": "both"}.get(task_opt, "both")
        interval_in = _prompt("Interval in minutes", "60")
        try:
            interval = float(interval_in)
        except ValueError:
            interval = 60.0
        return "watch", {
            "mode": mode,
            "task": task,
            "interval": interval,
            "site": site,
            "max_pages": 1,
            "pages": 1,
            "format": "ALL",
            "hoster": "ALL",
            "output": "both",
            "delay": 1.0,
            "workers": 5,
            "verbose": False,
            "csv_path": str(default_csv_path(site)),
            "scrape_all": False,
        }

    # ── Mode 8: test notification setup ─────────────────────────────────
    if mode == "8":
        return "notify-test", {
            "site": site,
        }

    # ── Mode 9: launch the web dashboard ────────────────────────────────
    if mode == "9":
        print(f"\n{Colours.BOLD}Web dashboard — browse the catalogue in your browser{Colours.RESET}")
        print(f"  {Colours.GREY}Serves a local page to view games, history & dead links, and trigger scrapes.{Colours.RESET}")
        host_in = _prompt("Host to bind", WEB_DEFAULT_HOST)
        port_in = _prompt("Port", str(WEB_DEFAULT_PORT))
        try:
            port = int(port_in)
        except ValueError:
            port = WEB_DEFAULT_PORT
        return "serve", {
            "host": host_in or WEB_DEFAULT_HOST,
            "port": port,
            "site": site,
        }

    search_q: str | None = None
    scrape_all = False

    if mode == "2":
        search_q = _prompt("Enter game search keywords (e.g. Zelda, Mario)")
        while not search_q:
            search_q = _prompt("Search query cannot be empty")
    elif mode == "3":
        if getattr(adapter, "supports_full_site", False):
            all_in = _prompt("Scrape ALL pages dynamically via sitemap/pagination? (y/N)", "N")
            scrape_all = all_in.lower().startswith("y")
        else:
            print(f"  {Colours.YELLOW}ℹ Full-site sweep (sitemap) is not supported by site '{site}'. Falling back to page count.{Colours.RESET}")

    if not scrape_all:
        print(f"\n{Colours.BOLD}2. How many pages to sweep?{Colours.RESET}")
        pages_input = _prompt("Enter number of pages", "1")
        max_p = int(pages_input) if pages_input.isdigit() and int(pages_input) > 0 else 1
    else:
        max_p = 9999

    # ── Per-site format & hoster filters ─────────────────────────────
    _fmt_choices = adapter.format_choices()
    _hoster_choices = adapter.hoster_choices()

    format_filter = _prompt_choice("3. Filter File Format", _fmt_choices, "ALL")
    hoster_filter = _prompt_choice("4. Filter File Hosting Provider", _hoster_choices, "ALL")

    # ── Output format choice ──────────────────────────────────────────
    print(f"\n{Colours.BOLD}5. How should results be saved?{Colours.RESET}")
    print("  [1] Excel Spreadsheet (CSV)")
    print("  [2] Database File (JSON)")
    print("  [3] Both formats")
    save_opt = _prompt("Select output format", "3")
    output_fmt = OUTPUT_MAP.get(save_opt, "both")

    return "scrape", {
        "search": search_q,
        "max_pages": max_p,
        "pages": max_p,
        "format": format_filter,
        "hoster": hoster_filter,
        "output": output_fmt,
        "delay": 1.0,
        "workers": 5,
        "verbose": False,
        "site": site,
        "scrape_all": scrape_all,
    }


# ── argparse CLI ───────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NESTfetch v4.9 — Multi-Site Game Download Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape homepage, page 1, all formats, all hosters, output both
  python -m nestfetch

  # Search for "Mario", 3 pages, NSP only, Mediafire only, JSON only
  python -m nestfetch -s Mario -p 3 -f NSP -H Mediafire -o json

  # Non-interactive full scrape
  python -m nestfetch -p 5 -f XCI -H 1Fichier -o both -d 0.5 -w 10

  # Scrape ALL games on the entire website (auto-paginate)
  python -m nestfetch --all -d 0.5

  # Check whether links in the default scraped CSV are still alive
  python -m nestfetch --check-links

  # Check links in a specific CSV, faster with 20 workers
  python -m nestfetch --check-links output/switch_games.csv -w 20
""",
    )

    # ── Phase 1: scrape target & depth ─────────────────────────────
    parser.add_argument("--search", "-s", type=str, default=None,
                        help="Search query for games (scrapes search results instead of homepage)")
    parser.add_argument("--pages", "-p", type=int, default=1,
                        help="Number of listing pages to scrape (default: 1)")
    parser.add_argument("--all", "-a", action="store_true",
                        help="Scrape all available pages dynamically (auto-pagination / sitemap)")

    # ── Phase 2: filtering & output ────────────────────────────────
    parser.add_argument("--format", "-f", type=str, default="ALL",
                        help="Filter links by format, e.g. NSP, XCI, PC, Update, DLC (default: ALL)")
    parser.add_argument("--hoster", "-H", type=str, default="ALL",
                        help="Filter links by hoster, e.g. Mega, 1Fichier, Torrent, Mediafire (default: ALL)")
    parser.add_argument("--output", "-o", type=str, default="both",
                        choices=["csv", "json", "both"],
                        help="Output format: csv, json, or both (default: both)")

    # ── Phase 3: performance & resilience ────────────────────
    parser.add_argument("--delay", "-d", type=float, default=1.0,
                        help="Delay between requests in seconds (default: 1.0)")
    parser.add_argument("--workers", "-w", type=int, default=5,
                        help="Number of concurrent workers (default: 5)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug-level logging")
    parser.add_argument("--check-links", "-c", nargs="?", const="__DEFAULT__", default=None,
                        metavar="CSV_PATH",
                        help="Run the link checker to verify download links in a scraped CSV file. "
                             "Optionally pass a CSV path (default: output/switch_games.csv).")
    parser.add_argument("--check-output", type=str, default=None,
                        help="Path for the link checker report CSV "
                             "(default: output/link_check_report.csv)")
    parser.add_argument("--site", type=str, default=DEFAULT_SITE,
                        help=f"Which site to scrape (default: {DEFAULT_SITE})")
    parser.add_argument("--list-sites", action="store_true",
                        help="List available sites and exit")
    parser.add_argument("--no-db", action="store_true",
                        help="Disable SQLite persistence for this run")
    parser.add_argument("--db", type=str, default=None,
                        help="Path to the SQLite database file (default: output/nestfetch.db)")
    parser.add_argument("--history", action="store_true",
                        help="Show scrape history from the database and exit")
    parser.add_argument("--db-export", action="store_true",
                        help="Export database records to CSV/JSON and exit")
    parser.add_argument("--async", dest="use_async", action="store_true",
                        default=ASYNC_ENABLED_DEFAULT,
                        help="Enable async HTML fetching (aiohttp)")
    parser.add_argument("--no-async", dest="use_async", action="store_false",
                        help="Disable async fetching; force sync requests")
    parser.add_argument("--cache", dest="use_cache", action="store_true",
                        default=CACHE_ENABLED_DEFAULT,
                        help="Enable HTML caching (default)")
    parser.add_argument("--no-cache", dest="use_cache", action="store_false",
                        help="Disable HTML caching; force fresh HTTP requests")
    parser.add_argument("--rate-limit", dest="rate_limit", type=float,
                        default=PER_HOST_RATE_LIMIT,
                        help="Per-host rate limit delay in seconds")

    # ── Phase 4: automation & notifications ──────────────────
    parser.add_argument("--watch", action="store_true",
                        help="Run in Watch Mode (schedule periodic scrape/check)")
    parser.add_argument("--interval", type=float, default=60.0,
                        help="Watch interval in minutes (default: 60)")
    parser.add_argument("--task", type=str, default="both",
                        choices=["scrape", "check", "both"],
                        help="Watch task to run: scrape, check, or both (default: both)")
    parser.add_argument("--iterations", type=int, default=None,
                        help="Limit watch loop iterations (default: unlimited)")
    parser.add_argument("--notify", action="store_true",
                        help="Enable notification dispatch (Discord/Telegram)")
    parser.add_argument("--notify-test", dest="notify_test", action="store_true",
                        help="Send a test notification and exit")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.yaml (default: config.yaml if present)")

    # -- Phase 5: web dashboard --
    parser.add_argument("--serve", action="store_true",
                        help="Launch local web dashboard UI")
    parser.add_argument("--host", type=str, default=WEB_DEFAULT_HOST,
                        help=f"Web server host (default: {WEB_DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=WEB_DEFAULT_PORT,
                        help=f"Web server port (default: {WEB_DEFAULT_PORT})")

    return parser


def parse_args() -> Tuple[str, dict]:
    """Parse command line arguments.

    Returns (action, kwargs).
    """
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.list_sites:
        return "list-sites", {}

    if args.history:
        return "history", {
            "site": args.site,
            "db_path": args.db,
        }

    if args.db_export:
        return "db-export", {
            "site": args.site,
            "db_path": args.db,
            "output": args.output,
        }

    if args.notify_test:
        return "notify-test", {
            "site": args.site,
            "config": args.config,
        }

    if args.serve:
        return "serve", {
            "host": args.host,
            "port": args.port,
            "site": args.site,
            "db_path": args.db,
        }

    if args.watch:
        from nestfetch.link_checker import default_csv_path
        return "watch", {
            "mode": "7",
            "task": args.task,
            "interval": args.interval,
            "iterations": args.iterations,
            "notify": args.notify,
            "config": args.config,
            "site": args.site,
            "max_pages": args.pages,
            "pages": args.pages,
            "search": args.search,
            "format": args.format,
            "hoster": args.hoster,
            "output": args.output,
            "delay": args.delay,
            "workers": args.workers,
            "verbose": args.verbose,
            "use_async": args.use_async,
            "use_cache": args.use_cache,
            "rate_limit": args.rate_limit,
            "db_path": args.db,
            "no_db": args.no_db,
            "csv_path": str(default_csv_path(args.site)),
            "scrape_all": args.all,
        }

    if args.check_links is not None:
        from nestfetch.link_checker import default_csv_path
        csv_path = args.check_links
        if csv_path == "__DEFAULT__":
            csv_path = str(default_csv_path(args.site))
        return "check", {
            "csv_path": csv_path,
            "output_path": args.check_output,
            "workers": args.workers,
            "delay": args.delay,
            "verbose": args.verbose,
            "site": args.site,
            "db_path": args.db,
            "no_db": args.no_db,
        }

    if not any([
        args.search, args.all, args.pages > 1,
        args.format != "ALL", args.hoster != "ALL",
        args.output != "both", args.delay != 1.0,
        args.workers != 5, args.verbose,
        args.use_async != ASYNC_ENABLED_DEFAULT,
        args.use_cache != CACHE_ENABLED_DEFAULT,
        args.rate_limit != PER_HOST_RATE_LIMIT,
        args.no_db, args.db is not None, args.site != DEFAULT_SITE,
    ]):
        return interactive_menu()

    return "scrape", {
        "search": args.search,
        "max_pages": args.pages,
        "pages": args.pages,
        "format": args.format,
        "hoster": args.hoster,
        "output": args.output,
        "delay": args.delay,
        "workers": args.workers,
        "verbose": args.verbose,
        "use_async": args.use_async,
        "use_cache": args.use_cache,
        "rate_limit": args.rate_limit,
        "site": args.site,
        "db_path": args.db,
        "no_db": args.no_db,
        "scrape_all": args.all,
    }
