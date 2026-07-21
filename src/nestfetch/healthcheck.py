#!/usr/bin/env python3
"""
Config health-check.

Websites change their HTML all the time, which silently breaks CSS-selector
based site configs. This module re-parses the saved reference pages in
``samples/`` with each site's adapter and reports how many listing items are
extracted — an early-warning signal that a config has drifted (0 items = broken).

It is intentionally offline and dependency-light: it never hits the network, so
it is safe to run in CI and as a pre-release gate.

Usage:
    python -m nestfetch.healthcheck                # auto-locate samples/
    python -m nestfetch.healthcheck path/to/samples
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import List, Optional

from nestfetch.logger import log
from nestfetch.sites.registry import get_adapter, site_names


@dataclass
class SiteHealth:
    name: str
    status: str          # "ok" | "empty" | "error" | "skipped"
    items: int = 0
    detail: str = ""

    @property
    def healthy(self) -> bool:
        # "skipped" (no reference sample) is not a failure — there is simply
        # nothing to verify offline for that site.
        return self.status in ("ok", "skipped")


def default_samples_dir() -> str:
    """Locate the repo's ``samples/`` folder relative to the installed package."""
    # src/nestfetch/healthcheck.py -> repo root is three levels up.
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(here))
    return os.path.join(repo_root, "samples")


def check_site(name: str, samples_dir: str) -> SiteHealth:
    """Re-parse the reference sample for one site and report extraction health."""
    sample_path = os.path.join(samples_dir, f"{name}.txt")
    if not os.path.exists(sample_path):
        return SiteHealth(name, "skipped", 0, "no reference sample")

    try:
        html = open(sample_path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return SiteHealth(name, "error", 0, f"cannot read sample: {exc}")

    try:
        adapter = get_adapter(name)
        games = adapter.parse_listing(html)
    except Exception as exc:  # a broken config must not crash the whole check
        return SiteHealth(name, "error", 0, repr(exc))

    count = len(games)
    if count == 0:
        return SiteHealth(name, "empty", 0, "parse_listing returned 0 items")
    return SiteHealth(name, "ok", count, "")


def run(samples_dir: Optional[str] = None) -> List[SiteHealth]:
    """Check every registered site; return a list of SiteHealth results."""
    samples_dir = samples_dir or default_samples_dir()
    return [check_site(name, samples_dir) for name in site_names()]


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    samples_dir = argv[0] if argv else None
    results = run(samples_dir)

    icons = {"ok": "\u2713", "empty": "\u2717", "error": "\u2717", "skipped": "\u2013"}
    for r in results:
        line = f"  {icons.get(r.status, '?')} {r.name:<18} {r.status:<8}"
        if r.items:
            line += f" ({r.items} items)"
        if r.detail:
            line += f"  {r.detail}"
        print(line)

    broken = [r for r in results if not r.healthy]
    checked = [r for r in results if r.status in ("ok", "empty", "error")]
    print(
        f"\nHealth-check: {len(checked) - len(broken)}/{len(checked)} verified sites OK "
        f"({len(results)} total, {len([r for r in results if r.status == 'skipped'])} skipped)."
    )
    if broken:
        log.error("Config health-check found %d broken site(s): %s",
                  len(broken), ", ".join(r.name for r in broken))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
