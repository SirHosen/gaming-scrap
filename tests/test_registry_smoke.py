#!/usr/bin/env python3
"""Smoke tests for the site registry.

These guard against the class of regression where the shipped JSON site
configs are accidentally excluded from the package (e.g. a blanket `*.json`
.gitignore rule), which silently collapses the registry down to the single
built-in Python adapter (`switchroms`).

Run standalone:      PYTHONPATH=.:tests python3 tests/test_registry_smoke.py
Or via pytest:       pytest tests/test_registry_smoke.py
"""
from __future__ import annotations

import os
import sys

# Make the project root importable when run standalone.
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from nestfetch.sites.registry import (  # noqa: E402
    DEFAULT_SITE,
    available_sites,
    get_adapter,
    site_names,
)

# The full roster NESTfetch is expected to ship with: 1 Python adapter
# (switchroms) + 8 config-driven sites.
EXPECTED_SITES = {
    "switchroms",
    "dodi",
    "freelinuxpcgames",
    "skidrowcodex",
    "ovagames",
    "romsfun",
    "coolrom",
    "nxbrew",
    "elamigos",
}


def test_all_expected_sites_registered():
    names = set(site_names())
    missing = EXPECTED_SITES - names
    assert not missing, (
        f"Missing site adapters: {sorted(missing)}. "
        "The shipped sites/configs/*.json files are probably not packaged "
        "(check the .gitignore *.json rule and the !sites/configs/ exception)."
    )
    assert len(names) >= len(EXPECTED_SITES)


def test_no_duplicate_site_names():
    names = site_names()
    assert len(names) == len(set(names)), f"duplicate site slugs: {names}"


def test_default_site_is_registered():
    assert DEFAULT_SITE in site_names()


def test_every_site_meta_is_well_formed():
    for meta in available_sites():
        assert meta.name and isinstance(meta.name, str)
        assert getattr(meta, "base_url", None), f"{meta.name} missing base_url"
        assert str(meta.base_url).startswith("http"), meta.base_url


def test_every_site_can_be_instantiated():
    for name in site_names():
        adapter = get_adapter(name)
        assert adapter is not None
        # build_listing_url is the common entrypoint every adapter implements.
        url = adapter.build_listing_url(1)
        assert isinstance(url, str) and url.startswith("http"), (name, url)


def test_unknown_site_raises():
    raised = False
    try:
        get_adapter("definitely-not-a-real-site")
    except ValueError:
        raised = True
    assert raised, "get_adapter should raise ValueError for unknown sites"


_TESTS = [
    test_all_expected_sites_registered,
    test_no_duplicate_site_names,
    test_default_site_is_registered,
    test_every_site_meta_is_well_formed,
    test_every_site_can_be_instantiated,
    test_unknown_site_raises,
]


def run() -> int:
    print("Running registry smoke tests...")
    failed = 0
    for t in _TESTS:
        try:
            t()
            print(f"  [ok] {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  [FAIL] {t.__name__}: {exc}")
    if failed:
        print(f"{failed} smoke test(s) failed.")
    else:
        print("All registry smoke tests passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run())
