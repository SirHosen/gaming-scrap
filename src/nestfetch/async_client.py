#!/usr/bin/env python3
"""
Optional async HTTP fetching (Phase 3).

Uses aiohttp to fetch many URLs concurrently — much faster than the thread pool
for hundreds of listing / detail pages. This is OPTIONAL and OFF by default:

  * if the 'aiohttp' package is installed, fetch_many() runs a real async event
    loop with a bounded-concurrency semaphore;
  * if aiohttp is NOT installed, it transparently falls back to the threaded
    HttpClient so nothing breaks.

Install the extra with:  pip install aiohttp   (or: pip install nestfetch[async])
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, Optional

from nestfetch.config import ASYNC_CONCURRENCY, DEFAULT_TIMEOUT, DEFAULT_HEADERS, MAX_WORKERS
from nestfetch.logger import log


def aiohttp_available() -> bool:
    """True if the optional aiohttp package can be imported."""
    try:
        import aiohttp  # noqa: F401
        return True
    except ImportError:
        return False


def fetch_many(
    urls: Iterable[str],
    headers: Optional[dict] = None,
    concurrency: int = ASYNC_CONCURRENCY,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Optional[str]]:
    """
    Fetch many URLs and return {url: body-or-None}.

    Uses aiohttp when available; otherwise falls back to the threaded client.
    Ordering is not guaranteed — use the returned dict keyed by URL.
    """
    url_list = list(dict.fromkeys(urls))   # de-dup, preserve order
    if not url_list:
        return {}

    if aiohttp_available():
        try:
            import asyncio
            return asyncio.run(
                _async_fetch_many(url_list, headers, concurrency, timeout)
            )
        except Exception as exc:            # pragma: no cover - safety net
            log.warning("Async fetch failed (%s) — falling back to threads.", exc)

    return _threaded_fetch_many(url_list, headers, concurrency, timeout)


# ── aiohttp implementation ───────────────────────────────────

async def _async_fetch_many(urls, headers, concurrency, timeout):   # pragma: no cover - needs aiohttp
    import asyncio
    import aiohttp

    results: Dict[str, Optional[str]] = {}
    sem = asyncio.Semaphore(max(1, concurrency))
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    async def _one(session, url):
        async with sem:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        results[url] = await resp.text()
                    else:
                        log.warning("Async HTTP %d on %s", resp.status, url)
                        results[url] = None
            except Exception as exc:
                log.warning("Async request error on %s: %s", url, exc)
                results[url] = None

    async with aiohttp.ClientSession(
        headers=headers or DEFAULT_HEADERS, timeout=client_timeout
    ) as session:
        await asyncio.gather(*(_one(session, u) for u in urls))
    return results


# ── threaded fallback (always available) ──────────────────────────

def _threaded_fetch_many(urls, headers, concurrency, timeout):
    from nestfetch.http_client import HttpClient

    results: Dict[str, Optional[str]] = {}
    workers = max(1, min(concurrency or MAX_WORKERS, len(urls)))
    client = HttpClient(headers=headers, delay=0.0, timeout=timeout)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {pool.submit(client.get, u): u for u in urls}
            for fut in future_map:
                u = future_map[fut]
                try:
                    results[u] = fut.result()
                except Exception as exc:
                    log.warning("Fallback fetch error on %s: %s", u, exc)
                    results[u] = None
    finally:
        client.close()
    return results
