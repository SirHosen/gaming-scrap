#!/usr/bin/env python3
"""
Offline tests for the config-driven site engine (sites/config_adapter.py).

No network / no sockets: we feed synthetic HTML straight into the pure parsing
methods, and use a tiny fake HTTP client for sitemap discovery.

Run standalone:  PYTHONPATH=.:tests python3 tests/test_config_adapter.py
"""

from __future__ import annotations

import json
import os
import tempfile

from bs4 import BeautifulSoup

from sites.config_adapter import (
    ConfigError,
    GenericConfigAdapter,
    discover_configs,
    extract_value,
    validate_config,
)

BASE = "https://ex.com/"
# Build templates by concatenation so no full-URL-then-{token} literal appears.
_PAGE = "page/" + "{page}" + "/"
_QUERY_TOKEN = "{query}"
_DETAIL_TOKEN = "{detail_url}"


def make_config(full_site=True):
    cfg = {
        "name": "TestSite",
        "base_url": BASE,
        "category": "windows",
        "platform": "Windows PC",
        "description": "test fixture",
        "listing": {
            "first_page_url": BASE,
            "page_url": BASE + _PAGE,
            "search_url": BASE + _PAGE + "?s=" + _QUERY_TOKEN,
            "item": "article.game",
            "fields": {
                "title": "a.title",
                "detail_url": {"selector": "a.title", "attr": "href", "transform": ["absolute_url"]},
                "meta_size": {"selector": "span.size", "transform": ["strip", "number"]},
                "meta_genre": "span.genre",
            },
        },
        "detail": {
            "download_index_url": _DETAIL_TOKEN + "/?download",
            "mirror_item": "a.dl",
            "mirror_fields": {
                "redirect_url": {"attr": "href", "transform": ["absolute_url"]},
                "raw_text": "span.lt",
            },
            "raw_text_split": {"delimiter": "|", "format_index": 0, "size_index": 1, "hoster_index": 2},
            "title": [{"selector": "meta[property='og:title']", "attr": "content"}, "h1.title"],
        },
        "resolve": {
            "final_link": [
                {"selector": "#nope a", "attr": "href"},
                {"selector": "#dl a", "attr": "href"},
            ],
            "default": "N/A",
        },
    }
    if full_site:
        cfg["full_site"] = {
            "sitemap_candidates": ["sitemap.xml"],
            "skip_keywords": ["category", "tag"],
            "game_url_pattern": r"^https?://[^/]+/game/[^/]+/?$",
        }
    return cfg


LISTING_HTML = """
<div class="games">
  <article class="game">
    <a class="title" href="/game/cool-game/">Cool Game</a>
    <span class="size">Size: 4.2 GB</span>
    <span class="genre">Action</span>
  </article>
  <article class="game">
    <a class="title" href="https://ex.com/game/another/">Another Game</a>
    <span class="size">1 GB</span>
  </article>
  <article class="game"><span>no link here</span></article>
</div>
"""

MIRROR_HTML = """
<div class="downloads">
  <a class="dl" href="/go/1"><span class="lt">NSP | 4 GB | MediaFire</span></a>
  <a class="dl" href="/go/2"><span class="lt">XCI | 8 GB | MEGA</span></a>
</div>
"""

FINAL_HTML = '<div id="dl"><a href="https://host.com/file.nsp">Download</a></div>'
DETAIL_HTML = (
    '<html><head><meta property="og:title" content="Cool Game Deluxe">'
    '</head><body><h1 class="title">ignored heading</h1></body></html>'
)


class FakeClient:
    """Minimal stand-in for engine.HttpClient (only .get is used)."""
    def __init__(self, pages):
        self.pages = pages

    def get(self, url):
        return self.pages.get(url)


# ── tests ───────────────────────────────────────────
def test_build_listing_url():
    a = GenericConfigAdapter(make_config())
    assert a.build_listing_url(1) == BASE, a.build_listing_url(1)
    assert a.build_listing_url(2) == BASE + "page/2/", a.build_listing_url(2)
    assert a.build_listing_url(2, "mario") == BASE + "page/2/?s=mario", a.build_listing_url(2, "mario")
    # spaces get url-encoded
    assert a.build_listing_url(1, "mario kart") == BASE + "page/1/?s=mario+kart"
    print("  [ok] build_listing_url")


def test_parse_listing():
    a = GenericConfigAdapter(make_config())
    games = a.parse_listing(LISTING_HTML)
    assert len(games) == 2, len(games)          # third card has no link -> skipped
    assert games[0].title == "Cool Game", games[0].title
    assert games[0].detail_url == "https://ex.com/game/cool-game/", games[0].detail_url
    assert games[0].meta_size == "4.2", games[0].meta_size   # strip + number
    assert games[0].meta_genre == "Action", games[0].meta_genre
    assert games[1].detail_url == "https://ex.com/game/another/", games[1].detail_url
    assert games[1].meta_genre == "N/A", games[1].meta_genre  # missing -> default
    print("  [ok] parse_listing")


def test_build_download_index_url():
    a = GenericConfigAdapter(make_config())
    got = a.build_download_index_url("https://ex.com/game/cool-game/")
    assert got == "https://ex.com/game/cool-game/?download", got
    print("  [ok] build_download_index_url")


def test_parse_mirrors():
    a = GenericConfigAdapter(make_config())
    mirrors = a.parse_mirrors(MIRROR_HTML, "https://ex.com/game/cool-game/")
    assert len(mirrors) == 2, len(mirrors)
    m0 = mirrors[0]
    assert m0.format == "NSP", m0.format
    assert m0.size == "4 GB", m0.size
    assert m0.hoster == "MediaFire", m0.hoster
    assert m0.redirect_url == "https://ex.com/go/1", m0.redirect_url
    # hoster filter
    only_mega = a.parse_mirrors(MIRROR_HTML, "x", hoster_filter="MEGA")
    assert len(only_mega) == 1 and only_mega[0].format == "XCI", only_mega
    # format filter
    only_nsp = a.parse_mirrors(MIRROR_HTML, "x", format_filter="NSP")
    assert len(only_nsp) == 1 and only_nsp[0].hoster == "MediaFire", only_nsp
    print("  [ok] parse_mirrors")


def test_resolve_final_link():
    a = GenericConfigAdapter(make_config())
    assert a.resolve_final_link(FINAL_HTML) == "https://host.com/file.nsp"
    assert a.resolve_final_link("<html></html>") == "N/A"    # fallback default
    print("  [ok] resolve_final_link")


def test_parse_detail_title():
    a = GenericConfigAdapter(make_config())
    assert a.parse_detail_title(DETAIL_HTML) == "Cool Game Deluxe"
    # config without a detail.title spec -> None
    cfg = make_config()
    cfg["detail"].pop("title")
    assert GenericConfigAdapter(cfg).parse_detail_title(DETAIL_HTML) is None
    print("  [ok] parse_detail_title")


def test_extract_value_helpers():
    soup = BeautifulSoup(LISTING_HTML, "html.parser")
    item = soup.select_one("article.game")
    # attribute + absolute_url
    v = extract_value(item, {"selector": "a.title", "attr": "href", "transform": ["absolute_url"]}, BASE)
    assert v == "https://ex.com/game/cool-game/", v
    # regex extraction
    v = extract_value(item, {"selector": "span.size", "regex": r"([0-9.]+)", "regex_group": 1}, BASE)
    assert v == "4.2", v
    # list-of-specs fallback (first misses, second hits)
    v = extract_value(item, ["span.nope", "span.genre"], BASE)
    assert v == "Action", v
    # default when nothing matches
    v = extract_value(item, {"selector": "span.nope", "default": "D"}, BASE)
    assert v == "D", v
    print("  [ok] extract_value helpers")


def test_validate_config_errors():
    ok = 0
    for mutate in (
        lambda c: c.pop("resolve"),
        lambda c: c["listing"]["fields"].pop("detail_url"),
        lambda c: c["detail"].pop("mirror_item"),
        lambda c: c.pop("name"),
    ):
        cfg = make_config()
        mutate(cfg)
        try:
            validate_config(cfg, "test")
        except ConfigError:
            ok += 1
    assert ok == 4, ok
    print("  [ok] validate_config errors")


def test_supports_full_site_and_discovery():
    a = GenericConfigAdapter(make_config(full_site=True))
    assert a.supports_full_site is True
    assert GenericConfigAdapter(make_config(full_site=False)).supports_full_site is False

    sitemap = (
        "<urlset>"
        "<url><loc>https://ex.com/game/aaa/</loc></url>"
        "<url><loc>https://ex.com/game/bbb/</loc></url>"
        "<url><loc>https://ex.com/category/x/</loc></url>"
        "<url><loc>https://ex.com/</loc></url>"
        "</urlset>"
    )
    client = FakeClient({"https://ex.com/sitemap.xml": sitemap})
    urls = a.discover_all_urls(client)
    assert urls == ["https://ex.com/game/aaa/", "https://ex.com/game/bbb/"], urls
    print("  [ok] supports_full_site + discover_all_urls")


def test_discover_configs_skips_underscore_and_invalid():
    tmp = tempfile.mkdtemp()
    # valid, should load
    with open(os.path.join(tmp, "good.json"), "w", encoding="utf-8") as f:
        json.dump(make_config(), f)
    # underscore-prefixed template, should be skipped
    with open(os.path.join(tmp, "_tpl.json"), "w", encoding="utf-8") as f:
        json.dump(make_config(), f)
    # invalid, should be skipped with a warning (not raise)
    with open(os.path.join(tmp, "broken.json"), "w", encoding="utf-8") as f:
        f.write("{ not valid json ")
    loaded = discover_configs(tmp)
    names = [c["name"] for c in loaded]
    assert names == ["testsite"], names   # only good.json, name lowercased
    print("  [ok] discover_configs skips _/invalid")


def test_extends_preset_merge():
    tmp = tempfile.mkdtemp()
    preset = {
        "category": "windows", "platform": "Windows PC", "description": "preset",
        "listing": {
            "first_page_url": "{base}", "page_url": "{base}page/{page}/",
            "search_first_url": "{base}?s={query}", "search_url": "{base}page/{page}/?s={query}",
            "item": "article.post",
            "fields": {"title": "h2 a", "detail_url": {"selector": "h2 a", "attr": "href"}},
        },
        "detail": {"mirror_mode": "labeled_group", "mirror_item": ".entry-content p"},
        "resolve": {"mode": "none"},
    }
    with open(os.path.join(tmp, "_preset_wp.json"), "w", encoding="utf-8") as f:
        json.dump(preset, f)
    child = {"extends": "wp", "name": "MySite", "base_url": "https://c.com/",
             "description": "child override"}
    with open(os.path.join(tmp, "child.json"), "w", encoding="utf-8") as f:
        json.dump(child, f)
    loaded = discover_configs(tmp)
    assert [c["name"] for c in loaded] == ["mysite"], loaded   # preset (underscore) skipped
    cfg = loaded[0]
    assert cfg["category"] == "windows"                 # inherited from preset
    assert cfg["platform"] == "Windows PC"              # inherited from preset
    assert cfg["listing"]["item"] == "article.post"     # inherited from preset
    assert cfg["base_url"] == "https://c.com/"          # from child
    assert cfg["description"] == "child override"       # child overrides preset
    assert "extends" not in cfg
    a = GenericConfigAdapter(cfg)
    assert a.resolves_final_link is False
    print("  [ok] extends/preset merge")


def test_missing_preset_skipped():
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, "orphan.json"), "w", encoding="utf-8") as f:
        json.dump({"extends": "nope", "name": "x", "base_url": "https://x.com/"}, f)
    assert discover_configs(tmp) == []   # skipped with a warning, not a crash
    print("  [ok] missing preset skipped gracefully")


def test_base_token_urls():
    cfg = make_config()
    cfg["base_url"] = "https://b.com/"
    cfg["listing"]["first_page_url"] = "{base}"
    cfg["listing"]["page_url"] = "{base}page/{page}/"
    cfg["listing"]["search_first_url"] = "{base}?s={query}"
    cfg["listing"]["search_url"] = "{base}page/{page}/?s={query}"
    a = GenericConfigAdapter(cfg)
    assert a.build_listing_url(1) == "https://b.com/"
    assert a.build_listing_url(3) == "https://b.com/page/3/"
    assert a.build_listing_url(1, "mario") == "https://b.com/?s=mario"
    assert a.build_listing_url(2, "mario") == "https://b.com/page/2/?s=mario"
    print("  [ok] {base} token URLs")


def test_labeled_group_and_resolve_none():
    cfg = make_config(full_site=False)
    cfg["detail"] = {
        "mirror_mode": "labeled_group",
        "mirror_item": ".entry-content p",
        "group_link_selector": "a[href]",
        "group_skip_hosters": ["youtube", "subscribe"],
    }
    cfg["resolve"] = {"mode": "none"}
    a = GenericConfigAdapter(cfg)
    assert a.resolves_final_link is False
    html = '''
    <div class="entry-content">
      <h1><strong>Download Mirrors</strong></h1>
      <p><strong>Torrent <span>– <a href="https://zovo.ink/a">Click Here</a> – or – <a href="/rel/b">Click Here</a></span></strong></p>
      <p><strong>OneDrive – <a href="https://zovo.ink/d">Click Here</a></strong></p>
      <p>Just a description, no links.</p>
      <p><a href="https://youtube.com/x">Youtube – Subscribe</a></p>
    </div>'''
    mirrors = a.parse_mirrors(html, "https://ex.com/game/x/")
    assert len(mirrors) == 3, [(m.hoster, m.redirect_url) for m in mirrors]
    assert mirrors[0].hoster == "Torrent"
    assert mirrors[0].redirect_url == "https://zovo.ink/a"
    assert mirrors[1].redirect_url == "https://ex.com/rel/b"   # relative -> absolute
    assert mirrors[2].hoster == "OneDrive"
    tor = a.parse_mirrors(html, "x", hoster_filter="TORRENT")
    assert len(tor) == 2 and all(m.hoster == "Torrent" for m in tor)
    print("  [ok] labeled_group + resolve mode none")


def test_real_dodi_preset_full_site_and_filters():
    # The shipped DODI config inherits full_site + per-site hoster filters from
    # _preset_wordpress-repack.json (real files, not a synthetic fixture).
    import re
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    configs_dir = os.path.join(here, "sites", "configs")
    loaded = {c["name"]: c for c in discover_configs(configs_dir)}
    assert "dodi" in loaded, list(loaded)
    dodi = loaded["dodi"]
    a = GenericConfigAdapter(dodi)
    assert a.supports_full_site is True
    assert a.resolves_final_link is False               # inherited resolve.mode=none
    hosters = list(a.hoster_choices().values())
    assert "TORRENT" in hosters and "ONEDRIVE" in hosters, hosters
    fs = dodi["full_site"]
    assert "wp-sitemap.xml" in fs["sitemap_candidates"]
    rx = re.compile(fs["game_url_pattern"])
    assert rx.search("https://dodi-repacks.site/some-game/")
    assert not rx.search("https://dodi-repacks.site/page/2/")
    print("  [ok] real DODI preset full_site + filters")


TESTS = [
    test_build_listing_url,
    test_parse_listing,
    test_build_download_index_url,
    test_parse_mirrors,
    test_resolve_final_link,
    test_parse_detail_title,
    test_extract_value_helpers,
    test_validate_config_errors,
    test_supports_full_site_and_discovery,
    test_discover_configs_skips_underscore_and_invalid,
    test_extends_preset_merge,
    test_missing_preset_skipped,
    test_base_token_urls,
    test_labeled_group_and_resolve_none,
    test_real_dodi_preset_full_site_and_filters,
]


def run():
    print("Running config_adapter tests...")
    for t in TESTS:
        t()
    print("All config_adapter tests passed.")


if __name__ == "__main__":
    run()
