"""Offline tests for the config health-check (nestfetch.healthcheck).

Parses the checked-in samples/ reference pages with each site's adapter and
asserts every site with a sample still extracts >= 1 listing item.

Run directly:
    PYTHONPATH=src:tests python3 tests/test_healthcheck.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
for _p in (_SRC, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from nestfetch import healthcheck


def test_default_samples_dir_exists():
    d = healthcheck.default_samples_dir()
    assert os.path.isdir(d), d
    print("  [ok] default samples dir resolves")


def test_all_sampled_sites_extract_items():
    results = healthcheck.run()
    # At least a few sites must actually be verified (guards against a broken
    # samples path silently skipping everything).
    verified = [r for r in results if r.status in ("ok", "empty", "error")]
    assert len(verified) >= 5, [r.__dict__ for r in results]
    broken = [r for r in results if not r.healthy]
    assert not broken, [(r.name, r.status, r.detail) for r in broken]
    print(f"  [ok] {len(verified)} sampled sites all healthy")


def test_missing_sample_is_skipped_not_failed():
    r = healthcheck.check_site("switchroms", healthcheck.default_samples_dir())
    assert r.status == "skipped"
    assert r.healthy is True
    print("  [ok] missing sample => skipped (not a failure)")


def test_main_returns_zero_when_healthy():
    assert healthcheck.main([]) == 0
    print("  [ok] main() exit code 0 when healthy")


if __name__ == "__main__":
    for name in sorted(n for n in dir() if n.startswith("test_")):
        globals()[name]()
    print("ALL healthcheck tests passed")
