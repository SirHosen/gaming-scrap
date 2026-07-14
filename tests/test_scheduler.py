#!/usr/bin/env python3
"""Offline tests for scheduler.run_scheduler (Phase 4).

The clock is injected (sleep_fn / now_fn) so the loop runs instantly.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scheduler as sch


class _Clock:
    """Deterministic clock: records sleeps and advances a fake 'now'."""
    def __init__(self):
        self.sleeps = []
        self._now = datetime(2026, 1, 1, 0, 0, 0)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self._now += timedelta(seconds=seconds)

    def now(self):
        return self._now


def test_runs_exact_iterations():
    clock = _Clock()
    runs = []
    count = sch.run_scheduler(
        lambda i: runs.append(i),
        interval_minutes=5,
        iterations=3,
        sleep_fn=clock.sleep,
        now_fn=clock.now,
    )
    assert count == 3, count
    assert runs == [1, 2, 3], runs
    # sleeps happen BETWEEN runs only (not after the final run)
    assert len(clock.sleeps) == 2, clock.sleeps
    assert all(s == 300 for s in clock.sleeps), clock.sleeps
    print("\u2714 test_runs_exact_iterations")


def test_task_exception_does_not_stop_loop():
    clock = _Clock()
    runs = []
    def flaky(i):
        runs.append(i)
        if i == 2:
            raise RuntimeError("boom")
    count = sch.run_scheduler(
        flaky, interval_minutes=1, iterations=3,
        sleep_fn=clock.sleep, now_fn=clock.now,
    )
    assert count == 3, count
    assert runs == [1, 2, 3], runs
    print("\u2714 test_task_exception_does_not_stop_loop")


def test_non_positive_interval_coerced():
    clock = _Clock()
    sch.run_scheduler(
        lambda i: None, interval_minutes=0, iterations=2,
        sleep_fn=clock.sleep, now_fn=clock.now,
    )
    # coerced to 60 min -> 3600s between the two runs
    assert clock.sleeps == [3600.0], clock.sleeps
    print("\u2714 test_non_positive_interval_coerced")


def test_wait_before_first_run():
    clock = _Clock()
    runs = []
    sch.run_scheduler(
        lambda i: runs.append(i),
        interval_minutes=2, iterations=1, run_immediately=False,
        sleep_fn=clock.sleep, now_fn=clock.now,
    )
    assert runs == [1]
    # one initial wait, none after the single run
    assert clock.sleeps == [120.0], clock.sleeps
    print("\u2714 test_wait_before_first_run")


def run():
    test_runs_exact_iterations()
    test_task_exception_does_not_stop_loop()
    test_non_positive_interval_coerced()
    test_wait_before_first_run()
    print("\nAll scheduler tests passed.")


if __name__ == "__main__":
    run()
