#!/usr/bin/env python3
"""
NESTfetch v4.8 — Main entry point.

A professional, modular, MULTI-SITE game-download metadata scraper.
(Originally a single-site Nintendo Switch ROM scraper.)

Architecture:
  config.py      → All tunable parameters
  logger.py      → Coloured console + file logging
  models.py      → Dataclass-based data models (with source_site/category/platform)
  http_client.py → Retry, backoff, caching, rate-limiting, session reuse
  async_client.py→ Optional aiohttp concurrent fetching (threaded fallback)
  sites/         → Pluggable per-site adapters (base + registry + one file per site)
  parsers.py     → switchroms.io BeautifulSoup parsing (used by its adapter)
  engine.py      → Site-agnostic concurrency orchestration + auto-paginate
  exporters.py   → JSON / CSV output (Excel-friendly CSV with UTF-8 BOM)
  database.py    → SQLite scrape history + link-health tracking
  settings.py    → User settings/secrets loader (.env / config.yaml / env vars)
  notifier.py    → Telegram / Discord / email notifications
  scheduler.py   → Periodic "watch" runner
  webapp.py      → Zero-dependency web dashboard (Phase 5)
  cli.py         → Argparse + interactive menu
  scraper.py     → This file (entry point)

Usage:
  python scraper.py                           # interactive mode
  python scraper.py --search Mario --pages 3  # CLI mode
  python scraper.py --all                     # scrape entire site
  python scraper.py --watch --interval 60     # scheduler + notifications
  python scraper.py --notify-test             # test your notification setup
  python scraper.py --serve                   # launch the local web dashboard
  python scraper.py --help                    # full help
"""

from __future__ import annotations

import logging

import database as db
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
    print(f"{Colours.GREEN}════════════════════════════════════════════════════{Colours.RESET}\n")


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
        try:
            a = get_adapter(m.name)
            print(f"      Formats  : {', '.join(a.format_choices().values())}")
            print(f"      Hosters  : {', '.join(a.hoster_choices().values())}")
        except Exception:
            pass
    print()


def run_link_check(params: dict) -> dict:
    """Check whether links in a previously scraped CSV are still alive.

    Returns the link-health stats dict (active / dead / unknown / newly_dead /
    newly_dead_urls) so callers (e.g. watch mode) can raise notifications.
    """
    from link_checker import check_csv_links

    stats: dict = {}
    csv_path = params["csv_path"]
    log.info("%sLink check target:%s %s", Colours.CYAN, Colours.RESET, csv_path)
    report = check_csv_links(
        csv_path,
        output_path=params.get("output"),
        workers=params.get("workers", 5),
        delay=params.get("delay", 0.0),
        rate_limit=params.get("rate_limit", 0.0),
        use_cache=params.get("use_cache", False),
    )
    if report:
        # Persist link health to the database (first_dead_at tracking).
        if not params.get("no_db"):
            try:
                conn = db.connect(params.get("db_path"))
                stats = db.record_link_checks_from_report(conn, report) or {}
                conn.close()
                if stats:
                    log.info(
                        "%sSaved link health to database%s (active=%d, dead=%d, unknown=%d, newly dead=%d)",
                        Colours.CYAN, Colours.RESET,
                        stats.get("active", 0), stats.get("dead", 0),
                        stats.get("unknown", 0), stats.get("newly_dead", 0),
                    )
            except Exception as exc:
                log.warning("Could not record link checks to database: %s", exc)
        log.info("%s[FINISHED]%s Link check complete.", Colours.BOLD + Colours.GREEN, Colours.RESET)
    else:
        log.warning("Link check did not produce a report (see errors above).")
    return stats


def _validate_filter(value: str, choices: dict, kind: str, site_name: str) -> str:
    """Validate a format/hoster filter against the chosen site's own choices.

    Non-fatal: an unknown value is passed through with a warning (hoster/format
    matching is substring-based, so a custom value may still be intentional).
    """
    if not value or str(value).upper() == "ALL":
        return "ALL"
    allowed = {str(v).upper() for v in choices.values()}
    if str(value).upper() in allowed:
        return value
    log.warning(
        "%s'%s' is not a listed %s filter for site '%s' (valid: %s). "
        "Proceeding anyway — results may be empty.%s",
        Colours.YELLOW, value, kind, site_name,
        ", ".join(sorted(allowed)) or "ALL", Colours.RESET,
    )
    return value


def do_scrape(params: dict):
    """Run a single scrape from params; export + persist to the DB.

    Returns (games, summary, elapsed) where `summary` is the DB RunSummary
    (or None if nothing was scraped / the DB was skipped).
    """
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

    # Resolve the selected site adapter.
    site = params.get("site") or "switchroms"
    adapter = get_adapter(site)
    log.info("%sTarget site:%s %s (%s)", Colours.CYAN, Colours.RESET, adapter.name, adapter.platform)

    # Filters are per-site: validate the requested format/hoster against this
    # site's own advertised choices (see --list-sites).
    fmt_filter = _validate_filter(fmt_filter, adapter.format_choices(), "format", adapter.name)
    hoster_filter = _validate_filter(hoster_filter, adapter.hoster_choices(), "hoster", adapter.name)

    # Run scraper.
    engine = ScraperEngine(
        adapter,
        delay=delay,
        max_workers=workers,
        format_filter=fmt_filter,
        hoster_filter=hoster_filter,
        use_async=params.get("use_async", False),
        use_cache=params.get("use_cache", False),
        rate_limit=params.get("rate_limit", 0.0),
    )

    games, elapsed = engine.run(
        search_query=search_q,
        max_pages=max_p,
        scrape_all=scrape_all,
    )

    summary = None
    if games:
        log.info("%s--- Exporting results ---%s", Colours.CYAN, Colours.RESET)
        export_data(games, out_fmt)

        # Persist to the SQLite history database + report the diff.
        if not params.get("no_db"):
            try:
                run_mode = "all" if scrape_all else ("search" if search_q else "latest")
                conn = db.connect(params.get("db_path"))
                summary = db.save_scrape(conn, games, site, mode=run_mode)
                conn.close()
                db.log_run_summary(summary)
            except Exception as exc:
                log.warning("Could not save scrape to database: %s", exc)

        print_summary(games, elapsed)
    else:
        log.warning("Scraping completed but no links matched your filters/search.")

    return games, summary, elapsed


# ── Notifications & scheduling (Phase 4) ─────────────
def _build_notifier(params: dict):
    """Construct a Notifier from settings (config file / .env / env vars)."""
    from notifier import Notifier
    from settings import load_settings
    return Notifier(load_settings(params.get("config")))


def _notify_new_games(params: dict, summary) -> None:
    if not summary or not getattr(summary, "new", 0):
        return
    try:
        notifier = _build_notifier(params)
        if not notifier.enabled_channels():
            log.info("%sNotifications: no channels configured — skipping.%s", Colours.GREY, Colours.RESET)
            return
        notifier.notify_new_games(summary)
    except Exception as exc:
        log.warning("Could not send new-games notification: %s", exc)


def _notify_dead_links(params: dict, stats) -> None:
    if not stats or not stats.get("newly_dead"):
        return
    try:
        notifier = _build_notifier(params)
        if not notifier.enabled_channels():
            log.info("%sNotifications: no channels configured — skipping.%s", Colours.GREY, Colours.RESET)
            return
        notifier.notify_dead_links(stats, site=params.get("site"))
    except Exception as exc:
        log.warning("Could not send dead-links notification: %s", exc)


def _run_notify_test(params: dict) -> None:
    """Send a test notification to every configured channel."""
    from notifier import Notifier
    from settings import load_settings
    settings = load_settings(params.get("config"))
    if settings.source_files:
        log.info("%sLoaded settings from:%s %s",
                 Colours.CYAN, Colours.RESET, ", ".join(settings.source_files))
    notifier = Notifier(settings)
    channels = notifier.enabled_channels()
    if not channels:
        log.warning(
            "No notification channels are configured. Create a .env or config.yaml "
            "(see .env.example / config.example.yaml) with Telegram, Discord, or email settings."
        )
        return
    log.info("%sSending a test notification via:%s %s", Colours.CYAN, Colours.RESET, ", ".join(channels))
    notifier.test()


def _run_watch(params: dict) -> None:
    """Run scrape and/or link-check repeatedly on a schedule, with notifications."""
    from scheduler import run_scheduler
    task = (params.get("task") or "both").lower()
    interval = params.get("interval") or 60.0
    iterations = params.get("iterations")

    notifier = None
    try:
        notifier = _build_notifier(params)
        channels = notifier.enabled_channels()
        if channels:
            log.info("%sNotifications active:%s %s", Colours.GREEN, Colours.RESET, ", ".join(channels))
        else:
            log.warning("Watch mode running WITHOUT notifications (no channels configured).")
    except Exception as exc:
        log.warning("Could not initialise notifier: %s", exc)

    def task_fn(iteration: int) -> None:
        if task in ("scrape", "both"):
            _games, summary, _elapsed = do_scrape(params)
            if notifier and summary:
                try:
                    notifier.notify_new_games(summary)
                except Exception as exc:
                    log.warning("new-games notification failed: %s", exc)
        if task in ("check", "both"):
            stats = run_link_check(params)
            if notifier and stats:
                try:
                    notifier.notify_dead_links(stats, site=params.get("site"))
                except Exception as exc:
                    log.warning("dead-links notification failed: %s", exc)

    run_scheduler(task_fn, interval, iterations=iterations)


def main() -> None:
    """Entry point: parse config, then dispatch to the requested action."""
    print_banner()

    action, params = parse_args()

    if params.get("verbose"):
        log.setLevel(logging.DEBUG)

    # List-sites mode: show supported sites, then exit.
    if action == "list-sites":
        print_sites()
        return

    # History mode: show recent scrape runs from the database.
    if action == "history":
        db.print_history(
            db.connect(params.get("db_path")),
            site=params.get("site"),
            limit=params.get("limit", 10),
        )
        return

    # DB-export mode: export previously scraped data from the DB.
    if action == "db-export":
        conn = db.connect(params.get("db_path"))
        games = db.export_from_db(
            conn,
            site=params.get("site"),
            active_only=params.get("active_only", True),
        )
        conn.close()
        if games:
            log.info("%s--- Exporting %d games from database ---%s", Colours.CYAN, len(games), Colours.RESET)
            export_data(games, params.get("output", "both"))
        else:
            log.warning("No games in the database to export (run a scrape first).")
        return

    # Notify-test mode: send a test notification, then exit.
    if action == "notify-test":
        _run_notify_test(params)
        return

    # Watch mode: run scrape/check on a schedule with notifications.
    if action == "watch":
        _run_watch(params)
        return

    # Web dashboard mode: launch the local dashboard server (blocks until Ctrl-C).
    if action == "serve":
        import webapp
        webapp.serve(
            host=params.get("host") or webapp.WEB_DEFAULT_HOST,
            port=params.get("port") or webapp.WEB_DEFAULT_PORT,
            db_path=params.get("db_path"),
            open_browser=params.get("open_browser", False),
        )
        return

    # Link-check mode: validate an existing CSV, then exit.
    if action == "check":
        stats = run_link_check(params)
        if params.get("notify"):
            _notify_dead_links(params, stats)
        log.info("%s[FINISHED]%s System terminated successfully.", Colours.BOLD + Colours.GREEN, Colours.RESET)
        return

    # Scrape mode.
    _games, summary, _elapsed = do_scrape(params)

    if params.get("notify"):
        _notify_new_games(params, summary)

    log.info("%s[FINISHED]%s System terminated successfully.", Colours.BOLD + Colours.GREEN, Colours.RESET)


if __name__ == "__main__":
    main()
