#!/usr/bin/env python3
"""
scheduler.py — lightweight periodic runner for NESTfetch (Phase 4).

Runs a task (scrape / link-check / both) repeatedly on a fixed interval so you
can leave NESTfetch watching a site for new games or dying links and get pinged
via notifier.py. Pure standard library — no cron / APScheduler / celery needed.

The clock (`sleep_fn`, `now_fn`) is injectable so the loop is unit-testable and
runs instantly in tests.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from nestfetch.logger import log, Colours


def run_scheduler(
    task_fn: Callable[[int], None],
    interval_minutes: float,
    iterations: Optional[int] = None,
    *,
    run_immediately: bool = True,
    sleep_fn: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], datetime] = datetime.now,
) -> int:
    """Call ``task_fn(iteration)`` every ``interval_minutes``.

    Args:
        task_fn: callback receiving the 1-based run number. Exceptions raised
            inside are logged and swallowed so one bad run never kills the loop.
        interval_minutes: gap between runs (values <= 0 are coerced to 60).
        iterations: total runs to perform; ``None`` runs forever (until Ctrl-C).
        run_immediately: run once right away; if False, wait one interval first.
        sleep_fn / now_fn: injectable clock (defaults to real time).

    Returns:
        The number of iterations actually executed.
    """
    if interval_minutes <= 0:
        interval_minutes = 60.0
    interval_s = interval_minutes * 60.0

    scope = "forever" if iterations is None else f"{iterations} run(s)"
    log.info("%sScheduler started%s — every %.0f min (%s)",
             Colours.CYAN + Colours.BOLD, Colours.RESET, interval_minutes, scope)

    count = 0
    try:
        if not run_immediately:
            sleep_fn(interval_s)
        while iterations is None or count < iterations:
            count += 1
            start = now_fn()
            log.info("%s[Scheduler] Run #%d — %s%s", Colours.CYAN, count,
                     start.strftime("%Y-%m-%d %H:%M:%S"), Colours.RESET)
            try:
                task_fn(count)
            except Exception as exc:  # never let one failed run stop the schedule
                log.error("%s[Scheduler] Run #%d failed: %s%s",
                          Colours.RED, count, exc, Colours.RESET)

            if iterations is not None and count >= iterations:
                break

            nxt = now_fn() + timedelta(seconds=interval_s)
            log.info("%s[Scheduler] Next run ~%s (sleeping %.0f min)…%s",
                     Colours.GREY, nxt.strftime("%H:%M:%S"), interval_minutes, Colours.RESET)
            sleep_fn(interval_s)
    except KeyboardInterrupt:
        log.info("%sScheduler stopped by user (Ctrl-C).%s", Colours.YELLOW, Colours.RESET)

    return count
