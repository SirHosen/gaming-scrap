"""Tests for the site-agnostic engine: dedup + mirror resolution, driven by a
fake in-memory adapter (no network)."""
from typing import List, Optional

from nestfetch.engine import ScraperEngine
from nestfetch.models import Game, Mirror
from nestfetch.sites.base import SiteAdapter, SiteMeta


class FakeAdapter(SiteAdapter):
    meta = SiteMeta(name="fake", base_url="https://fake.test/",
                    category="test", platform="Test Platform")
    supports_full_site = False

    def build_listing_url(self, page: int, query: Optional[str] = None) -> str:
        return f"https://fake.test/list/{page}"

    def parse_listing(self, html: str) -> List[Game]:
        # Always returns the SAME two games — exercises the dedup / loop guard.
        return [
            Game(title="Game One", detail_url="https://fake.test/g1"),
            Game(title="Game Two", detail_url="https://fake.test/g2"),
        ]

    def build_download_index_url(self, detail_url: str) -> str:
        return detail_url + "/dl"

    def parse_mirrors(self, html, detail_url, format_filter="ALL", hoster_filter="ALL"):
        return [Mirror(format="NSP ROM", hoster="Mediafire",
                       redirect_url=detail_url + "/r")]

    def resolve_final_link(self, html: str) -> str:
        return "https://mediafire.com/final"


class FullSiteFakeAdapter(FakeAdapter):
    """Full-site-capable adapter that records whether sitemap discovery ran."""
    supports_full_site = True

    def __init__(self):
        super().__init__()
        self.discover_called = False

    def discover_all_urls(self, client) -> List[str]:
        self.discover_called = True
        return ["https://fake.test/g1", "https://fake.test/g2"]


class TwoStepFakeAdapter(FakeAdapter):
    """Two-step adapter: the engine must fetch the detail page first, then use
    build_index_url_from_detail() to derive the real download-index URL."""
    needs_detail_page = True

    def __init__(self):
        super().__init__()
        self.index_built_from = []

    def build_index_url_from_detail(self, detail_html, detail_url):
        self.index_built_from.append((detail_url, detail_html))
        return detail_url + "/index-from-detail"


def test_engine_two_step_fetches_detail_then_index():
    a = TwoStepFakeAdapter()
    engine = ScraperEngine(a, delay=0.0)
    fetched = []

    def rec(url, use_cache=True):
        fetched.append(url)
        return f"<html>{url}</html>"

    engine.client.get = rec
    games, _ = engine.run(search_query=None, max_pages=1, scrape_all=False)

    assert len(games) == 2
    # The detail page itself was fetched for each game...
    assert "https://fake.test/g1" in fetched
    assert "https://fake.test/g2" in fetched
    # ...and the index URL derived from that detail page was fetched next.
    assert "https://fake.test/g1/index-from-detail" in fetched
    # build_index_url_from_detail received the fetched detail HTML + detail URL.
    assert ("https://fake.test/g1", "<html>https://fake.test/g1</html>") in a.index_built_from
    for g in games:
        assert len(g.mirrors) == 1
        assert g.mirrors[0].final_link == "https://mediafire.com/final"


def test_scrape_all_with_search_uses_pagination_not_sitemap():
    # --all + a search query must auto-paginate the SEARCH results, never invoke
    # full-site sitemap discovery (which would ignore the query).
    a = FullSiteFakeAdapter()
    engine = ScraperEngine(a, delay=0.0)
    engine.client.get = lambda url, use_cache=True: "<html>stub</html>"
    games, _ = engine.run(search_query="mario", max_pages=1, scrape_all=True)
    assert a.discover_called is False
    assert len(games) == 2


def test_scrape_all_without_search_uses_sitemap():
    # --all with no query on a full-site adapter => sitemap discovery path.
    a = FullSiteFakeAdapter()
    engine = ScraperEngine(a, delay=0.0)
    engine.client.get = lambda url, use_cache=True: "<html>stub</html>"
    games, _ = engine.run(search_query=None, max_pages=1, scrape_all=True)
    assert a.discover_called is True
    assert len(games) == 2


def test_engine_dedup_and_resolution():
    engine = ScraperEngine(FakeAdapter(), delay=0.0)
    # Replace the network entirely with a constant HTML stub.
    engine.client.get = lambda url, use_cache=True: "<html>stub</html>"

    games, elapsed = engine.run(search_query=None, max_pages=3, scrape_all=False)

    # Even across 3 pages the same 2 games are returned → dedup keeps only 2.
    assert len(games) == 2
    titles = sorted(g.title for g in games)
    assert titles == ["Game One", "Game Two"]
    for g in games:
        assert len(g.mirrors) == 1
        assert g.mirrors[0].final_link == "https://mediafire.com/final"
        assert g.source_site == "fake"          # provenance stamped
        assert g.platform == "Test Platform"
    assert elapsed >= 0


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
