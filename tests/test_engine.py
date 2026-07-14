"""Tests for the site-agnostic engine: dedup + mirror resolution, driven by a
fake in-memory adapter (no network)."""
from typing import List, Optional

from engine import ScraperEngine
from models import Game, Mirror
from sites.base import SiteAdapter, SiteMeta


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
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
