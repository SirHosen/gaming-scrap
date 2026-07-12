#!/usr/bin/env python3
"""
CLI interface — argument parsing and interactive menu.
Supports both `--flags` for automation and interactive prompts for manual use.
"""

from __future__ import annotations

import argparse
import sys
from typing import Tuple

from config import FORMAT_MAP, HOSTER_MAP, OUTPUT_MAP
from logger import log, Colours


# ── Banner ─────────────────────────────────────────────────────────────────

BANNER = f"""{Colours.CYAN}{Colours.BOLD}
  ════════════════════════════════════════════════════════════════════════════
     ██████╗ ██╗    ██╗██╗████████╗ ██████╗██╗  ██╗██████╗  ██████╗ ███╗   ███╗███████╗
    ██╔════╝ ██║    ██║██║╚══██╔══╝██╔════╝██║  ██║██╔══██╗██╔═══██╗████╗ ████║██╔════╝
    ╚█████╗  ██║ █╗ ██║██║   ██║   ██║     ███████║██████╔╝██║   ██║██╔████╔██║███████╗
     ╚═══██╗ ██║███╗██║██║   ██║   ██║     ██╔══██║██╔══██╗██║   ██║██║╚██╔╝██║╚════██║
    ██████╔╝ ╚███╔███╔╝██║   ██║   ╚██████╗██║  ██║██║  ██║╚██████╔╝██║ ╚═╝ ██║███████║
    ╚═════╝   ╚══╝╚══╝ ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝
                      NINTENDO SWITCH ROMS SCRAPER v3.1
  ════════════════════════════════════════════════════════════════════════════{Colours.RESET}"""


def print_banner() -> None:
    print(BANNER)


# ── Interactive menu ───────────────────────────────────────────────────────

def _prompt(label: str, default: str = "") -> str:
    """Helper: prompt with default value, return user input or default."""
    suffix = f" (default: {default})" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    return val if val else default


def interactive_menu() -> Tuple[str | None, int, str, str, str, bool]:
    """
    Interactive CLI menu when no CLI args are provided.
    Returns: (search_query, max_pages, format_filter, hoster_filter, output_format, scrape_all)
    """
    print(f"\n{Colours.BOLD}1. Select Action Mode:{Colours.RESET}")
    print("  [1] Scrape latest games (Homepage)")
    print("  [2] Search specific games by keyword")
    print("  [3] Scrape ALL games on the entire website (auto-paginate)")
    mode = _prompt("Select option", "1")

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

    return search_q, max_p, format_filter, hoster_filter, output_fmt, scrape_all


# ── argparse CLI ───────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argparse-based CLI for non-interactive / automated usage."""
    parser = argparse.ArgumentParser(
        description="SwitchRoms Scraper v3.1 — Nintendo Switch ROM metadata scraper",
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
    return parser


def parse_args() -> Tuple[str | None, int, str, str, str, float, int, bool, bool]:
    """
    If CLI args are provided, use argparse. Otherwise, launch interactive menu.
    Returns: (search, pages, format, hoster, output, delay, workers, verbose, scrape_all)
    """
    parser = build_arg_parser()
    args = parser.parse_args()

    # If no meaningful args were passed, go interactive
    if len(sys.argv) == 1:
        search_q, max_p, fmt, hoster, out, scrape_all = interactive_menu()
        return search_q, max_p, fmt, hoster, out, 1.0, 5, False, scrape_all

    return (
        args.search,
        args.pages,
        args.format,
        args.hoster,
        args.output,
        args.delay,
        args.workers,
        args.verbose,
        args.all,
    )
