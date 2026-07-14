"""Tests for the Phase 3 HTTP client: caching, priming, smart retries,
Retry-After, and per-host rate limiting — all fully offline."""
import contextlib
import tempfile

import http_client
from http_client import HttpClient, ResponseCache
from fakes import FakeResp, FakeSession, FakeClock


@contextlib.contextmanager
def patched_time(clock):
    """Temporarily swap http_client's time module for a deterministic clock."""
    orig = http_client.time
    http_client.time = clock
    try:
        yield
    finally:
        http_client.time = orig


def _client(session, **kw):
    kw.setdefault("delay", 0.0)
    c = HttpClient(**kw)
    c.session = session
    return c


def test_prime_is_one_shot():
    # Priming returns the stored body first, then falls through to the network.
    sess = FakeSession(default=FakeResp(status_code=200, text="NET"))
    c = _client(sess)
    c.prime("https://x/a", "PRIMED")
    assert c.get("https://x/a") == "PRIMED"   # served from memory, no call
    assert sess.calls == []
    assert c.get("https://x/a") == "NET"      # one-shot consumed → hits network
    assert sess.calls == ["https://x/a"]


def test_disk_cache_skips_network():
    with tempfile.TemporaryDirectory() as d:
        cache = ResponseCache(d, ttl=0)
        sess = FakeSession(default=FakeResp(status_code=200, text="BODY"))
        c = _client(sess, cache=cache)
        assert c.get("https://x/a") == "BODY"
        assert len(sess.calls) == 1
        # Second fetch is served from disk cache — no new network call.
        assert c.get("https://x/a") == "BODY"
        assert len(sess.calls) == 1


def test_404_is_not_retried():
    sess = FakeSession(default=FakeResp(status_code=404, text="nope"))
    c = _client(sess, retries=3)
    assert c.get("https://x/missing") is None
    assert len(sess.calls) == 1          # no retries on 404


def test_retry_then_success():
    sess = FakeSession(responses=[
        FakeResp(status_code=500, text="err"),
        FakeResp(status_code=200, text="OK"),
    ])
    c = _client(sess, retries=3)
    clock = FakeClock()
    with patched_time(clock):
        assert c.get("https://x/a") == "OK"
    assert len(sess.calls) == 2
    assert len(clock.slept) >= 1         # backed off once between attempts


def test_retry_after_header_is_honoured():
    sess = FakeSession(responses=[
        FakeResp(status_code=503, text="busy", headers={"Retry-After": "7"}),
        FakeResp(status_code=200, text="OK"),
    ])
    c = _client(sess, retries=3)
    clock = FakeClock()
    with patched_time(clock):
        assert c.get("https://x/a") == "OK"
    assert 7 in clock.slept              # honoured the server's Retry-After


def test_per_host_rate_limit():
    sess = FakeSession(default=FakeResp(status_code=200, text="OK"))
    c = _client(sess, rate_limit=2.0)
    clock = FakeClock()
    with patched_time(clock):
        c.get("https://host.test/1")     # first call: no wait
        c.get("https://host.test/2")     # same host: must wait rate_limit
    assert 2.0 in clock.slept


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
