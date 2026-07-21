"""Offline tests for the robots.txt politeness policy (nestfetch.robots).

No real network is used: a FakeSession serves a canned robots.txt.

Run directly:
    PYTHONPATH=src:tests python3 tests/test_robots.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
for _p in (_SRC, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from nestfetch.robots import RobotsPolicy
from nestfetch.http_client import HttpClient
from fakes import FakeResp, FakeSession

ROBOTS = "User-agent: *\nDisallow: /private/\nAllow: /\n"


def _robots_session(text=ROBOTS, status=200):
    return FakeSession(responses={
        "https://ex.test/robots.txt": FakeResp(
            url="https://ex.test/robots.txt", status_code=status, text=text
        ),
    }, default=FakeResp(status_code=200, text=""))


def test_disabled_allows_everything():
    pol = RobotsPolicy(enabled=False, session=_robots_session())
    assert pol.allowed("https://ex.test/private/secret") is True
    # Disabled => no network call at all.
    assert pol._session.calls == []
    print("  [ok] disabled policy allows everything, no I/O")


def test_disallowed_path_is_blocked():
    pol = RobotsPolicy(enabled=True, session=_robots_session())
    assert pol.allowed("https://ex.test/private/secret") is False
    assert pol.allowed("https://ex.test/public/page") is True
    print("  [ok] Disallow rule blocks /private/, allows others")


def test_robots_txt_itself_always_allowed():
    pol = RobotsPolicy(enabled=True, session=_robots_session())
    assert pol.allowed("https://ex.test/robots.txt") is True
    print("  [ok] robots.txt itself is always fetchable")


def test_missing_robots_fails_open():
    # 404 robots.txt => nothing to enforce => allow everything.
    pol = RobotsPolicy(enabled=True, session=_robots_session(status=404))
    assert pol.allowed("https://ex.test/private/secret") is True
    print("  [ok] missing robots.txt fails open (allow)")


def test_result_is_cached_per_host():
    sess = _robots_session()
    pol = RobotsPolicy(enabled=True, session=sess)
    pol.allowed("https://ex.test/a")
    pol.allowed("https://ex.test/b")
    pol.allowed("https://ex.test/private/c")
    # robots.txt fetched exactly once for the host despite 3 checks.
    assert sess.calls.count("https://ex.test/robots.txt") == 1
    print("  [ok] robots.txt cached once per host")


def test_http_client_skips_disallowed_url():
    # Integration: HttpClient with a robots policy must not fetch a page the
    # site disallows, and must return None for it.
    page_sess = FakeSession(default=FakeResp(status_code=200, text="PAGE"))
    pol = RobotsPolicy(enabled=True, session=_robots_session())
    c = HttpClient(delay=0.0, robots=pol)
    c.session = page_sess
    assert c.get("https://ex.test/private/x") is None
    assert page_sess.calls == []            # page was never fetched
    assert c.get("https://ex.test/ok") == "PAGE"
    assert page_sess.calls == ["https://ex.test/ok"]
    print("  [ok] HttpClient skips robots-disallowed URLs")


if __name__ == "__main__":
    for name in sorted(n for n in dir() if n.startswith("test_")):
        globals()[name]()
    print("ALL robots tests passed")
