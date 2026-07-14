"""Tests for the optional async fetcher — exercises the threaded fallback
(aiohttp is not installed in CI, so fetch_many must still work)."""
import http_client
import async_client


def test_aiohttp_available_returns_bool():
    assert isinstance(async_client.aiohttp_available(), bool)


def test_fetch_many_empty():
    assert async_client.fetch_many([]) == {}


def test_fetch_many_threaded_fallback_and_dedup():
    # Force a deterministic, network-free HttpClient.get.
    orig_get = http_client.HttpClient.get
    http_client.HttpClient.get = lambda self, url, use_cache=True: f"BODY:{url}"
    try:
        results = async_client.fetch_many(["https://x/a", "https://x/b", "https://x/a"])
    finally:
        http_client.HttpClient.get = orig_get

    assert set(results) == {"https://x/a", "https://x/b"}   # de-duplicated
    assert results["https://x/a"] == "BODY:https://x/a"
    assert results["https://x/b"] == "BODY:https://x/b"


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
