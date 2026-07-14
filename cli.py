#!/usr/bin/env python3
"""
CLI interface — argument parsing and interactive menu.
Supports both `--flags` for automation and interactive prompts for manual use.
"""

from __future__ import annotations

import argparse
import sys
from typing import Tuple

from config import (
    FORMAT_MAP, HOSTER_MAP, OUTPUT_MAP,
    CACHE_ENABLED_DEFAULT, ASYNC_ENABLED_DEFAULT, PER_HOST_RATE_LIMIT,
)
from logger import log, Colours
from sites.registry import available_sites, site_names, DEFAULT_SITE


# ── Banner ─────────────────────────────────────────────────────────────────

BANNER = f"""{Colours.CYAN}{Colours.BOLD}
  ════════════════════════════════════════════════════════════════════════════
   ███╗   ██╗███████╗███████╗████████╗███████╗███████╗████████╗ ██████╗██╗  ██╗
   ████╗  ██║██╔════╝██╔════╝╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝██╔════╝██║  ██║
   ██╔██╗ ██║█████╗  ███████╗   ██║   █████╗  █████╗     ██║   ██║     ███████║
   ██║╚██╗██║██╔══╝  ╚════██║   ██║   ██╔══╝  ██╔══╝     ██║   ██║     ██╔══██║
   ██║ ╚████║███████╗███████║   ██║   ██║     ███████╗   ██║   ╚██████╗██║  ██║
   ╚═╝  ╚═══╝╚══════╝╚══════╝   ╚═╝   ╚═╝     ╚══════╝   ╚═╝    ╚═════╝╚═╝  ╚═╝
              NESTfetch v4.3 — Multi-Site Game Download Scraper
  ════════════════════════════════════════════════════════════════════════════{Colours.RESET}"""


def print_banner() -> None:
    print(BANNER)


# ── Interactive menu ───────────────────────────────────────────────────────

def _prompt(label: str, default: str = "") -> str:
    """Helper: prompt with default value, return user input or default."""
    suffix = f" (default: {default})" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    return val if val else default


def interactive_menu() -> Tuple[str, dict]:
    """
    Interactive CLI menu when no CLI args are provided.
    Returns an (action, params) tuple where action is "scrape" or "check".
    """
    # ── Step 0: choose which site to scrape ────────────────────────
    metas = available_sites()
    print(f"\n{Colours.BOLD}Select Target Site:{Colours.RESET}")
    for i, m in enumerate(metas, 1):
        print(f"  [{i}] {m.name} — {m.platform} ({m.category})")
    site_in = _prompt("Select site", "1")
    if site_in.isdigit() and 1 <= int(site_in) <= len(metas):
        site = metas[int(site_in) - 1].name
    elif site_in in site_names():
        site = site_in
    else:
        site = DEFAULT_SITE
    print(f"  {Colours.GREEN}→ Using site: {site}{Colours.RESET}")

    print(f"\n{Colours.BOLD}1. Select Action Mode:{Colours.RESET}")
    print("  [1] Scrape latest games (Homepage)")
    print("  [2] Search specific games by keyword")
    print("  [3] Scrape ALL games on the entire website (auto-paginate)")
    print("  [4] Check scraped links from a CSV (dead / expired link validator)")
    print("  [5] Show scrape history (from the local database)")
    print("  [6] Export previously scraped data from the database")
    print("  [7] Watch mode — run scrape/check on a schedule with notifications")
    print("  [8] Test notification setup (Telegram / Discord / email)")
    mode = _prompt("Select option", "1")

    # ── Mode 4: link checker (works on an existing CSV, no scraping) ─────
    if mode == "4":
        import os
        from config import OUTPUT_DIR, CSV_FILENAME
        default_csv = os.path.join(OUTPUT_DIR, CSV_FILENAME)
        print(f"\n{Colours.BOLD}Link Checker — verify scraped download links{Colours.RESET}")
        print(f"  {Colours.GREY}Reads a scraped CSV and flags each link ACTIVE / DEAD / UNKNOWN.{Colours.RESET}")
        csv_path = _prompt("Path to scraped CSV", default_csv)
        workers_in = _prompt("Concurrent workers", "10")
        workers = int(workers_in) if workers_in.isdigit() and int(workers_in) > 0 else 10
        return "check", {
            "site": site,
            "csv_path": csv_path,
            "workers": workers,
            "delay": 0.0,
            "output": None,
            "verbose": False,
            "no_db": False,
            "db_path": None,
        }

    # ── Mode 5: show scrape history from the database ────────────────────
    if mode == "5":
        return "history", {
            "site": None,
            "db_path": None,
            "limit": 20,
            "verbose": False,
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
            "db_path": None,
            "active_only": True,
            "verbose": False,
        }

    # ── Mode 7: watch mode (scheduler + notifications) ──────────────────
    if mode == "7":
        import os
        from config import OUTPUT_DIR, CSV_FILENAME
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
            "site": site,
            "task": task,
            "interval": interval,
            "iterations": None,
            "notify": True,
            "config": None,
            "search": None,
            "pages": 1,
            "format": "ALL",
            "hoster": "ALL",
            "output": "both",
            "delay": 1.0,
            "workers": 5,
            "scrape_all": False,
            "no_db": False,
            "db_path": None,
            "use_async": False,
            "use_cache": CACHE_ENABLED_DEFAULT,
            "rate_limit": PER_HOST_RATE_LIMIT,
            "verbose": False,
            "check_output": None,
            "csv_path": os.path.join(OUTPUT_DIR, CSV_FILENAME),
        }

    # ── Mode 8: test notification setup ─────────────────────────────────
    if mode == "8":
        return "notify-test", {
            "config": None,
            "verbose": False,
        }

    search_q: str | None = None
    scrape_all = False

    if mode == "2":
        search_q = _prompt("Enter game search keywords (e.g. Zelda, Mario)")
        while not search_q:
            search_q = _prompt("Search query cannot be empty")
    elif mode == "3":
        scrape_all = True
        print(f"  {Colours.YELLOW}ℹ This will scrape every page until no more games are found.{Colours.RESET}")
        print(f"  {Colours.YELLOW}  This may take a while depending on the site size.{Colours.RESET}")

    max_p = 1
    if not scrape_all:
        print(f"\n{Colours.BOLD}2. How many pages to sweep?{Colours.RESET}")
        pages_input = _prompt("Enter number of pages", "1")
        max_p = int(pages_input) if pages_input.isdigit() and int(pages_input) > 0 else 1
    else:
        print(f"\n{Colours.BOLD}2. Pages to sweep:{Colours.RESET}")
        print(f"  {Colours.GREY}(Auto-paginate — will sweep all pages automatically){Colours.RESET}")

    print(f"\n{Colours.BOLD}3. Filter File Format:{Colours.RESET}")
    print("  [1] NSP (Standard Base Games)")
    print("  [2] XCI (Cartridge Dumps)")
    print("  [3] UPDATE (NSP Game Patches)")
    print("  [4] DLC (Add-on Contents)")
    print("  [5] ALL Formats")
    format_opt = _prompt("Select format filter", "5")
    format_filter = FORMAT_MAP.get(format_opt, "ALL")

    print(f"\n{Colours.BOLD}4. Filter File Hosting Provider:{Colours.RESET}")
    print("  [1] Mediafire   [2] MegaUp     [3] 1fichier")
    print("  [4] Buzzheavier  [5] Terabox   [6] Send.cm")
    print("  [7] Up-4ever     [8] ALL Providers")
    hoster_opt = _prompt("Select hoster filter", "8")
    hoster_filter = HOSTER_MAP.get(hoster_opt, "ALL")

    print(f"\n{Colours.BOLD}5. Choose Output Format:{Colours.RESET}")
    print("  [1] Excel Spreadsheet (CSV)")
    print("  [2] Database File (JSON)")
    print("  [3] Both formats")
    save_opt = _prompt("Select output format", "3")
    output_fmt = OUTPUT_MAP.get(save_opt, "both")

    return "scrape", {
        "site": site,
        "search": search_q,
        "pages": max_p,
        "format": format_filter,
        "hoster": hoster_filter,
        "output": output_fmt,
        "delay": 1.0,
        "workers": 5,
        "verbose": False,
        "scrape_all": scrape_all,
        "no_db": False,
        "db_path": None,
        "use_async": False,
        "use_cache": CACHE_ENABLED_DEFAULT,
        "rate_limit": PER_HOST_RATE_LIMIT,
    }


# ── argparse CLI ───────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argparse-based CLI for non-interactive / automated usage."""
    parser = argparse.ArgumentParser(
        description="NESTfetch v4.3 — Multi-Site Game Download Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape homepage, page 1, all formats, all hosters, output both
  python scraper.py

  # Search for "Mario", 3 pages, NSP only, Mediafire only, JSON only
  python scraper.py --search Mario --pages 3 --format NSP --hoster MEDIAFIRE --output json

  # Non-interactive full scrape
  python scraper.py --pages 5 --output both

  # Scrape ALL games on the entire website (auto-paginate)
  python scraper.py --all --output csv

  # Check whether links in the default scraped CSV are still alive
  python scraper.py --check-links

  # Check links in a specific CSV, faster with 20 workers
  python scraper.py --check-links output/switch_games.csv --workers 20
""",
    )
    parser.add_argument("--search", "-s", type=str, default=None,
                        help="Search keyword (e.g. 'Mario', 'Zelda')")
    parser.add_argument("--pages", "-p", type=int, default=1,
                        help="Number of listing pages to scrape (default: 1)")
    parser.add_argument("--all", "-a", action="store_true",
                        help="Scrape ALL games on the entire website (auto-paginate until empty)")
    parser.add_argument("--format", "-f", type=str, default="ALL",
                        choices=["NSP ROM", "XCI ROM", "UPDATE", "DLC", "ALL"],
                        help="Filter by ROM format")
    parser.add_argument("--hoster", "-H", type=str, default="ALL",
                        choices=["MEDIAFIRE", "MEGAUP", "1FICHIER", "BUZZHEAVIER",
                                 "TERABOX", "SEND.CM", "UP-4EVER", "ALL"],
                        help="Filter by file hosting provider")
    parser.add_argument("--output", "-o", type=str, default="both",
                        choices=["csv", "json", "both"],
                        help="Output format")
    parser.add_argument("--delay", "-d", type=float, default=1.0,
                        help="Delay between requests in seconds (default: 1.0)")
    parser.add_argument("--workers", "-w", type=int, default=5,
                        help="Number of concurrent workers (default: 5)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")
    parser.add_argument("--check-links", "-c", nargs="?", const="__DEFAULT__", default=None,
                        help="Check whether links in a scraped CSV are still active. "
                             "Optionally pass a CSV path (default: output/switch_games.csv).")
    parser.add_argument("--check-output", type=str, default=None,
                        help="Path to write the link-check report CSV "
                             "(default: output/link_check_report.csv)")
    parser.add_argument("--site", type=str, default=DEFAULT_SITE,
                        choices=site_names(),
                        help=f"Which site to scrape (default: {DEFAULT_SITE})")
    parser.add_argument("--list-sites", action="store_true",
                        help="List all supported sites and exit")
    parser.add_argument("--no-db", action="store_true",
                        help="Do not save this run to the local SQLite history database")
    parser.add_argument("--db", type=str, default=None,
                        help="Path to the SQLite database file (default: output/nestfetch.db)")
    parser.add_argument("--history", action="store_true",
                        help="Show recent scrape runs from the database and exit")
    parser.add_argument("--db-export", action="store_true",
                        help="Export previously scraped data straight from the database and exit")

    # ── Phase 3: performance & resilience ────────────────────
    parser.add_argument("--async", dest="use_async", action="store_true",
                        help="Prefetch pages concurrently with aiohttp "
                             "(falls back to threads if aiohttp isn't installed)")
    parser.add_argument("--cache", dest="use_cache", action="store_true",
                        default=CACHE_ENABLED_DEFAULT,
                        help="Cache HTTP responses on disk to skip re-downloading pages")
    parser.add_argument("--rate-limit", dest="rate_limit", type=float,
                        default=PER_HOST_RATE_LIMIT,
                        help="Minimum seconds between requests to the same host (0 = off)")

    # ── Phase 4: automation & notifications ──────────────────
    parser.add_argument("--watch", action="store_true",
                        help="Run scrape/check repeatedly on a schedule with notifications")
    parser.add_argument("--interval", type=float, default=60.0,
                        help="Minutes between watch-mode runs (default: 60)")
    parser.add_argument("--task", type=str, default="both",
                        choices=["scrape", "check", "both"],
                        help="Which task watch mode runs each cycle (default: both)")
    parser.add_argument("--iterations", type=int, default=None,
                        help="Stop watch mode after N cycles (default: run forever)")
    parser.add_argument("--notify", action="store_true",
                        help="Send notifications after a one-off scrape/check run")
    parser.add_argument("--notify-test", dest="notify_test", action="store_true",
                        help="Send a test notification to every configured channel and exit")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to a config.yaml / config.json settings file")
    return parser


def parse_args() -> Tuple[str, dict]:
    """
    If CLI args are provided, use argparse. Otherwise, launch interactive menu.
    Returns an (action, params) tuple where action is "scrape" or "check".
    """
    parser = build_arg_parser()
    args = parser.parse_args()

    # List supported sites and exit.
    if getattr(args, "list_sites", False):
        return "list-sites", {}

    # Show scrape history and exit.
    if getattr(args, "history", False):
        return "history", {
            "site": None,
            "db_path": args.db,
            "limit": 20,
            "verbose": args.verbose,
        }

    # Export previously scraped data from the database and exit.
    if getattr(args, "db_export", False):
        return "db-export", {
            "site": args.site,
            "output": args.output,
            "db_path": args.db,
            "active_only": True,
            "verbose": args.verbose,
        }

    # Send a test notification and exit.
    if getattr(args, "notify_test", False):
        return "notify-test", {
            "config": args.config,
            "verbose": args.verbose,
        }

    # Watch mode: run scrape/check on a schedule with notifications.
    if getattr(args, "watch", False):
        from link_checker import default_csv_path
        return "watch", {
            "site": args.site,
            "task": args.task,
            "interval": args.interval,
            "iterations": args.iterations,
            "notify": True,
            "config": args.config,
            "search": args.search,
            "pages": args.pages,
            "format": args.format,
            "hoster": args.hoster,
            "output": args.output,
            "delay": args.delay,
            "workers": args.workers,
            "scrape_all": args.all,
            "no_db": args.no_db,
            "db_path": args.db,
            "use_async": args.use_async,
            "use_cache": args.use_cache,
            "rate_limit": args.rate_limit,
            "verbose": args.verbose,
            "check_output": args.check_output,
            "csv_path": str(default_csv_path()),
        }

    # If no meaningful args were passed, go interactive
    if len(sys.argv) == 1:
        return interactive_menu()

    # Link-check mode takes precedence when --check-links is supplied.
    if args.check_links is not None:
        from link_checker import default_csv_path
        csv_path = args.check_links
        if csv_path == "__DEFAULT__":
            csv_path = str(default_csv_path())
        return "check", {
            "site": args.site,
            "csv_path": csv_path,
            "workers": args.workers,
            "delay": args.delay,
            "output": args.check_output,
            "verbose": args.verbose,
            "no_db": args.no_db,
            "db_path": args.db,
            "notify": args.notify,
            "config": args.config,
        }

    return "scrape", {
        "site": args.site,
        "search": args.search,
        "pages": args.pages,
        "format": args.format,
        "hoster": args.hoster,
        "output": args.output,
        "delay": args.delay,
        "workers": args.workers,
        "verbose": args.verbose,
        "scrape_all": args.all,
        "no_db": args.no_db,
        "db_path": args.db,
        "use_async": args.use_async,
        "use_cache": args.use_cache,
        "rate_limit": args.rate_limit,
        "notify": args.notify,
        "config": args.config,
    }
