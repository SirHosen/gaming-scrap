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


def test_real_freelinuxpcgames_config():
    # Standalone (non-preset) WordPress config: single magnet/torrent download,
    # genre derived from the article's category-* class, resolve.mode=none.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    configs_dir = os.path.join(here, "sites", "configs")
    loaded = {c["name"]: c for c in discover_configs(configs_dir)}
    assert "freelinuxpcgames" in loaded, list(loaded)
    a = GenericConfigAdapter(loaded["freelinuxpcgames"])
    assert a.build_listing_url(2) == "https://freelinuxpcgames.com/page/2/"
    assert a.build_listing_url(1, "terraria") == "https://freelinuxpcgames.com/?s=terraria"
    article = ('<article class="post-1 post type-post category-action layout-grid">'
               '<h2 class="blog-entry-title entry-title">'
               '<a href="https://freelinuxpcgames.com/hearthlands/" rel="bookmark">Hearthlands (1.3.1)</a>'
               '</h2></article>')
    games = a.parse_listing(article)
    assert len(games) == 1 and games[0].title == "Hearthlands (1.3.1)"
    assert games[0].detail_url == "https://freelinuxpcgames.com/hearthlands/"
    assert games[0].meta_genre == "Action", games[0].meta_genre
    dl = ('<div class="entry-content"><h2>Terraria Linux Free Download</h2>'
          '<p><em>File Size: 622 MB</em></p>'
          '<p><a href="magnet:?xt=urn:btih:ABC&dn=Terraria"><strong>Terraria v1.4.5.6</strong></a></p></div>')
    mirrors = a.parse_mirrors(dl, "https://freelinuxpcgames.com/terraria/")
    assert len(mirrors) == 1, mirrors
    assert mirrors[0].hoster == "TORRENT"
    assert mirrors[0].redirect_url.startswith("magnet:")
    assert a.parse_detail_title('<h1 class="title entry-title">Terraria (1.4.5.6)</h1>') == "Terraria (1.4.5.6)"
    assert a.resolves_final_link is False
    assert list(a.hoster_choices().values()) == ["ALL", "TORRENT"]
    print("  [ok] real freelinuxpcgames config")


def test_real_skidrowcodex_config():
    # Standalone config: cracked-scene WordPress theme where the real download
    # links are hidden behind a single gate (<links> custom tag). resolve=none;
    # hoster is labelled from the gate domain; per-host filtering is impossible.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    configs_dir = os.path.join(here, "sites", "configs")
    loaded = {c["name"]: c for c in discover_configs(configs_dir)}
    assert "skidrowcodex" in loaded, list(loaded)
    a = GenericConfigAdapter(loaded["skidrowcodex"])
    assert a.build_listing_url(3) == "https://www.skidrowcodex.net/page/3/"
    assert a.build_listing_url(1, "palworld") == "https://www.skidrowcodex.net/?s=palworld"
    listing = ('<div class="blog-post "><div class="blog-content "><h2>'
               '<a href="https://www.skidrowcodex.net/worldwide-rush-update-v1324-tenoke/">'
               ' Worldwide Rush Update v1.3.24-TENOKE </a></h2></div></div>')
    games = a.parse_listing(listing)
    assert len(games) == 1, games
    assert games[0].title == "Worldwide Rush Update v1.3.24-TENOKE"
    assert games[0].detail_url == "https://www.skidrowcodex.net/worldwide-rush-update-v1324-tenoke/"
    dl = ('<div>1fichier.com, gofile.io, megaup.net</div>'
          '<links><a href="https://fileguard.cc/0b52e85cfb">https://fileguard.cc/0b52e85cfb</a></links>')
    mirrors = a.parse_mirrors(dl, "https://www.skidrowcodex.net/palworld-rune/")
    assert len(mirrors) == 1, mirrors
    assert mirrors[0].redirect_url == "https://fileguard.cc/0b52e85cfb"
    assert mirrors[0].hoster == "FILEGUARD.CC", mirrors[0].hoster
    assert a.parse_detail_title("<h1>Palworld-RUNE            </h1>") == "Palworld-RUNE"
    assert a.resolves_final_link is False
    assert list(a.hoster_choices().values()) == ["ALL"]
    print("  [ok] real skidrowcodex config")


def test_real_ovagames_config():
    # Standalone eGamer-theme config: title comes from the anchor's title attr
    # (visible text is truncated); each hoster is a labelled <a> to a filecrypt
    # container, so per-host filtering works even though resolve=none.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    configs_dir = os.path.join(here, "sites", "configs")
    loaded = {c["name"]: c for c in discover_configs(configs_dir)}
    assert "ovagames" in loaded, list(loaded)
    a = GenericConfigAdapter(loaded["ovagames"])
    assert a.build_listing_url(3) == "https://www.ovagames.com/page/3"
    assert a.build_listing_url(1, "aoe") == "https://www.ovagames.com/?s=aoe"
    listing = ('<div class="home-post-wrap"><div class="home-post-titles"><h2>'
               '<a href="https://www.ovagames.com/age-of-empires-iv-anniversary-edition-multi24-elamigos.html" '
               'title="Permanent Link to Age of Empires IV Anniversary Edition MULTi24-ElAmigos">'
               'Age of Empires IV Anniversary Editio...</a></h2></div></div>')
    games = a.parse_listing(listing)
    assert len(games) == 1, games
    assert games[0].title == "Age of Empires IV Anniversary Edition MULTi24-ElAmigos", games[0].title
    assert games[0].detail_url == "https://www.ovagames.com/age-of-empires-iv-anniversary-edition-multi24-elamigos.html"
    dl = ('<div class="dl-wraps-dl cl"><div class="dl-wraps-item"><b>AOE4</b></p><p>'
          '<a href="https://www.filecrypt.cc/Container/AAA.html">DATANODES</a><br />'
          '<a href="https://www.filecrypt.cc/Container/BBB.html">GOOGLE DRIVE</a><br />'
          '<a href="https://www.filecrypt.cc/Container/CCC.html">MEDIAFIRE</a></p></div></div>')
    mirrors = a.parse_mirrors(dl, "https://www.ovagames.com/aoe.html")
    assert len(mirrors) == 3, mirrors
    assert mirrors[0].hoster == "DATANODES"
    assert mirrors[0].redirect_url == "https://www.filecrypt.cc/Container/AAA.html"
    assert mirrors[1].hoster == "GOOGLE DRIVE", mirrors[1].hoster
    only_mf = a.parse_mirrors(dl, "x", hoster_filter="MEDIAFIRE")
    assert len(only_mf) == 1 and only_mf[0].hoster == "MEDIAFIRE"
    assert a.parse_detail_title('<h1 class="post-title"><a>Age of Empires IV Anniversary Edition MULTi24-ElAmigos   </a></h1>') == "Age of Empires IV Anniversary Edition MULTi24-ElAmigos"
    assert a.resolves_final_link is False
    assert "TORRENT" in a.hoster_choices().values()
    print("  [ok] real ovagames config")


def test_real_romsfun_config():
    # Standalone two-step ROM catalogue: the detail page carries data-post_id,
    # and the real download-index URL is /download/{slug}-{post_id} whose table
    # lists per-region/version links (resolve=none, so those links are final).
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    configs_dir = os.path.join(here, "sites", "configs")
    loaded = {c["name"]: c for c in discover_configs(configs_dir)}
    assert "romsfun" in loaded, list(loaded)
    a = GenericConfigAdapter(loaded["romsfun"])
    assert a.needs_detail_page is True
    assert a.resolves_final_link is False
    assert a.build_listing_url(1) == "https://romsfun.com/browse-all-roms/"
    assert a.build_listing_url(2) == "https://romsfun.com/browse-all-roms/page/2/"

    listing = ('<div class="bg-white rounded-lg shadow-md"><div class="p-4">'
               '<h3 class="font-bold"><a href="https://romsfun.com/roms/playstation-2/god-of-war-ii.html">God of War II</a></h3>'
               '<span class="text-xs inline-flex items-center">6.65 G</span>'
               '</div></div>')
    games = a.parse_listing(listing)
    assert len(games) == 1, games
    assert games[0].title == "God of War II", games[0].title
    assert games[0].detail_url == "https://romsfun.com/roms/playstation-2/god-of-war-ii.html"
    assert games[0].meta_size == "6.65 G", games[0].meta_size

    detail_url = "https://romsfun.com/roms/playstation-2/god-of-war-ii.html"
    meta = '<div class="rating" data-post_id="12928"></div>'
    idx = a.build_index_url_from_detail(meta, detail_url)
    assert idx == "https://romsfun.com/download/god-of-war-ii-12928", idx
    assert a.build_index_url_from_detail("<div>no id</div>", detail_url) is None

    table = ('<table class="table-auto"><thead><tr><th>Filename</th><th>Type</th><th>Size</th></tr></thead><tbody>'
             '<tr><td><a href="https://romsfun.com/download/god-of-war-ii-12928/1">God of War II (Asia)</a></td><td>Redump</td><td>6.65 G</td></tr>'
             '<tr><td><a href="https://romsfun.com/download/god-of-war-ii-12928/9">Action Replay</a></td><td>CHD Format</td><td>9.08 M</td></tr>'
             '</tbody></table>')
    mirrors = a.parse_mirrors(table, idx)
    assert len(mirrors) == 2, mirrors
    assert mirrors[0].redirect_url == "https://romsfun.com/download/god-of-war-ii-12928/1"
    assert mirrors[0].raw_text == "God of War II (Asia)", mirrors[0].raw_text
    assert mirrors[0].format == "Redump", mirrors[0].format
    assert mirrors[0].size == "6.65 G", mirrors[0].size
    assert mirrors[0].hoster == "ROMSFUN", mirrors[0].hoster
    chd = a.parse_mirrors(table, idx, format_filter="CHD")
    assert len(chd) == 1 and chd[0].format == "CHD Format", chd
    assert a.parse_detail_title('<h1 class="text-xl text-romfun-pink">God of War II</h1>') == "God of War II"
    print("  [ok] real romsfun config")


def test_real_coolrom_config():
    # Standalone two-step ROM catalogue (Cloudflare/Rocket-Loader). Detail page
    # /roms/{console}/{id}/{Name}.php carries input[name=id]; the real download
    # page is /dlpop.php?id={id} whose "Continue to download" link is the CDN
    # file (resolve=none). Listing links are filtered to game URLs by regex so
    # navbar/console links are ignored.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    configs_dir = os.path.join(here, "sites", "configs")
    loaded = {c["name"]: c for c in discover_configs(configs_dir)}
    assert "coolrom" in loaded, list(loaded)
    a = GenericConfigAdapter(loaded["coolrom"])
    assert a.needs_detail_page is True
    assert a.resolves_final_link is False
    assert a.build_listing_url(1) == "https://coolrom.com/roms/psx/"
    assert a.build_listing_url(1, "mario") == "https://coolrom.com/search?q=mario"

    grid = ('<td><a href="/roms/psx/39843/Yu-Gi-Oh!_Forbidden_Memories.php">'
            '<img src="/screenshots/psx/x.jpg"><br><font size="1">Yu-Gi-Oh! Forbidden Memories</font></a></td>')
    g = a.parse_listing(grid)
    assert len(g) == 1, g
    assert g[0].title == "Yu-Gi-Oh! Forbidden Memories", g[0].title
    assert g[0].detail_url == "https://coolrom.com/roms/psx/39843/Yu-Gi-Oh!_Forbidden_Memories.php"
    table = ('<tr><td><a href="/roms/psx/39136/Jackie_Chan_Stuntmaster.php">Jackie Chan Stuntmaster</a></td>'
             '<td align="right">23,944,030</td></tr>')
    g2 = a.parse_listing(table)
    assert len(g2) == 1 and g2[0].detail_url.endswith("/39136/Jackie_Chan_Stuntmaster.php"), g2
    # Navbar/console index links (no numeric id) must NOT be treated as games.
    navbar = '<div><a href="/roms/atari2600/">Atari 2600</a><a href="/faq.php">FAQ</a></div>'
    assert a.parse_listing(navbar) == []

    detail_url = "https://coolrom.com/roms/genesis/1205/Aladdin.php"
    info = ('<span class="fn">Aladdin</span>'
            '<form action="/rate.php"><input type="hidden" name="id" value="1205">'
            '<input type="hidden" name="host" value="coolrom.com"></form>')
    idx = a.build_index_url_from_detail(info, detail_url)
    assert idx == "https://coolrom.com/dlpop.php?id=1205", idx
    assert a.build_index_url_from_detail("<div>no id</div>", detail_url) is None

    dlpop = ('<a class="linkdownload" href="javascript:void(0)"><div>DOWNLOAD FILE</div></a>'
             '<a onclick="redirect()" href="https://dl.coolrom.com/roms/genesis/Aladdin.zip/HASH/1784207192/">'
             'Continue to download in my current browser</a>')
    mirrors = a.parse_mirrors(dlpop, idx)
    assert len(mirrors) == 1, mirrors
    assert mirrors[0].redirect_url == "https://dl.coolrom.com/roms/genesis/Aladdin.zip/HASH/1784207192/"
    assert mirrors[0].hoster == "COOLROM", mirrors[0].hoster
    assert a.parse_detail_title(info) == "Aladdin"
    print("  [ok] real coolrom config")


def test_real_nxbrew_config():
    # Single-step WordPress (HitMag) Switch ROM site. The download button is a
    # <button class=nsp-download> whose gate URL is embedded in the onclick
    # window.open('...') call, so redirect_url/hoster are regex-extracted from
    # the onclick attribute (resolve=none; secureclouds gate is not resolvable).
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    configs_dir = os.path.join(here, "sites", "configs")
    loaded = {c["name"]: c for c in discover_configs(configs_dir)}
    assert "nxbrew" in loaded, list(loaded)
    a = GenericConfigAdapter(loaded["nxbrew"])
    assert a.needs_detail_page is False
    assert a.resolves_final_link is False
    assert a.build_listing_url(1) == "https://nxbrew.me/"
    assert a.build_listing_url(2) == "https://nxbrew.me/page/2/"
    assert a.build_listing_url(2, "mario") == "https://nxbrew.me/page/2/?s=mario"

    art = ('<article id="post-21883" class="hitmag-post post-21883 post type-post status-publish '
           'category-switch-nsps"><a href="https://nxbrew.me/inferno-2/"><div class="archive-thumb">'
           '<img src="x.png"/></div></a><div class="archive-content"><header class="entry-header">'
           '<h3 class="entry-title"><a href="https://nxbrew.me/inferno-2/" rel="bookmark">'
           'Inferno 2 Switch NSP [Update] (eShop)</a></h3></header></div></article>')
    g = a.parse_listing(art)
    assert len(g) == 1, g
    assert g[0].title == "Inferno 2 Switch NSP [Update] (eShop)", g[0].title
    assert g[0].detail_url == "https://nxbrew.me/inferno-2/", g[0].detail_url

    dlbtn = ('<center><button type="button" class="nsp-download" rel="nofollow noopener noreferrer" '
             'onclick="window.open(\'https://secureclouds.org/?h=f6e20e656eb477ecb20f13a236ae4125&z=382\','
             '\'_blank\',\'noopener,noreferrer\');"><span>&#8595;</span> Download NSP</button></center>')
    mirrors = a.parse_mirrors(dlbtn, g[0].detail_url)
    assert len(mirrors) == 1, mirrors
    assert mirrors[0].redirect_url == "https://secureclouds.org/?h=f6e20e656eb477ecb20f13a236ae4125&z=382", mirrors[0].redirect_url
    assert mirrors[0].hoster == "SECURECLOUDS.ORG", mirrors[0].hoster

    h1 = '<h1 class="entry-title">Inferno 2 Switch NSP [Update] (eShop)</h1>'
    assert a.parse_detail_title(h1) == "Inferno 2 Switch NSP [Update] (eShop)"
    assert a.parse_detail_title('<meta property="og:title" content="Inferno 2">' + h1) == "Inferno 2"
    print("  [ok] real nxbrew config")


def test_real_elamigos_config():
    # Single-step multi-mirror PC repack site (Laravel/Bootstrap). Detail page
    # exposes a "Download servers" block (#notiene #dw) of hoster <a> buttons,
    # each linking to a zpaste.net gate (resolve=none). Hoster name is the link
    # text with any leading star/symbol stripped. The separate "Game complements"
    # block (a bare #dw without #notiene) must be excluded.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    configs_dir = os.path.join(here, "sites", "configs")
    loaded = {c["name"]: c for c in discover_configs(configs_dir)}
    assert "elamigos" in loaded, list(loaded)
    a = GenericConfigAdapter(loaded["elamigos"])
    assert a.needs_detail_page is False
    assert a.resolves_final_link is False
    assert a.build_listing_url(1) == "https://www.elamigosgames.net/"
    assert a.build_listing_url(2) == "https://www.elamigosgames.net?page=2", a.build_listing_url(2)
    assert a.build_listing_url(1, "palworld") == "https://www.elamigosgames.net?s=palworld"

    card = ('<div class="col-lg-2 portfolio-item"><div class="card h-1">'
            '<a href="https://www.elamigosgames.net/games/age-of-empires-iv-anniversary-edition-p">'
            '<img class="card-img-top" src="/storage/x.jpg"></a><div class="card-body">'
            '<h6 class="card-title"><a href="https://www.elamigosgames.net/games/age-of-empires-iv-anniversary-edition-p">'
            'Age of Empires IV Anniversary Edition</a></h6><small>[Update 16.1.9737]</small>'
            '<small class="text-body-secondary">39.30GB</small></div></div></div>')
    g = a.parse_listing(card)
    assert len(g) == 1, g
    assert g[0].title == "Age of Empires IV Anniversary Edition", g[0].title
    assert g[0].detail_url == "https://www.elamigosgames.net/games/age-of-empires-iv-anniversary-edition-p"
    assert g[0].meta_size == "39.30GB", g[0].meta_size

    servers = ('<div id="notiene"><div id="dw">'
               '<a href="https://zpaste.net/p/apjeh" class="btn btn-danger btn-xs" target="_blank">\u2605 ROOTZ</a>'
               '<a href="https://zpaste.net/p/dvod2" class="btn btn-info btn-xs" target="_blank">DATANODES</a>'
               '<a href="https://zpaste.net/p/tm3y9" class="btn btn-danger btn-xs" target="_blank">MEGA</a>'
               '<a href="https://zpaste.net/p/da6je" class="btn btn-success btn-xs" target="_blank">TORRENT</a>'
               '</div></div>')
    complements = ('<div id="dw">Palworld update, 26MB<br />'
                   '<a href="https://zpaste.net/p/53ktq" class="btn btn-danger btn-xs">\u2605 ROOTZ</a></div>')
    mirrors = a.parse_mirrors(servers + complements, "https://www.elamigosgames.net/games/palworld-p")
    assert len(mirrors) == 4, [m.hoster for m in mirrors]  # complements excluded
    hosters = [m.hoster for m in mirrors]
    assert hosters == ["ROOTZ", "DATANODES", "MEGA", "TORRENT"], hosters  # leading star stripped
    assert mirrors[0].redirect_url == "https://zpaste.net/p/apjeh", mirrors[0].redirect_url

    h2 = '<h2 class="my-4">Palworld PC (<a href="?year=2026">2026</a>) MULTi17-ElAmigos,  29.25GB<hr></h2>'
    assert a.parse_detail_title(h2).startswith("Palworld PC"), a.parse_detail_title(h2)
    print("  [ok] real elamigos config")


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
    test_real_freelinuxpcgames_config,
    test_real_skidrowcodex_config,
    test_real_ovagames_config,
    test_real_romsfun_config,
    test_real_coolrom_config,
    test_real_nxbrew_config,
    test_real_elamigos_config,
]


def run():
    print("Running config_adapter tests...")
    for t in TESTS:
        t()
    print("All config_adapter tests passed.")


if __name__ == "__main__":
    run()
