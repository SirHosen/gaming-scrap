"""Tests for the link classifier + resolver (offline techniques only)."""
from urllib.parse import quote

import link_resolver as lr


def test_classify_url():
    assert lr.classify_url("https://www.mediafire.com/file/x") == lr.DIRECT
    assert lr.classify_url("https://bit.ly/abc") == lr.SHORTENER
    assert lr.classify_url("https://ouo.io/abc") == lr.AD_GATE
    assert lr.classify_url("https://some-unknown-host-xyz.com/f") == lr.UNKNOWN
    assert lr.classify_url("N/A") == lr.UNKNOWN
    assert lr.classify_url("") == lr.UNKNOWN


def test_resolve_direct_passthrough():
    url = "https://mediafire.com/file/real"
    r = lr.resolve_url(url)
    assert r.link_type == lr.DIRECT
    assert r.final_url == url
    assert r.resolved is True


def test_extract_embedded_target():
    inner = "https://mediafire.com/file/real"
    url = "https://exe.io/out?url=" + quote(inner, safe="")
    got = lr._extract_embedded_target(url)
    assert got is not None
    assert "mediafire.com" in got


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
