#!/usr/bin/env python3
"""
GenericConfigAdapter — a declarative, config-driven SiteAdapter.

This is the "config-first" tier of NESTfetch's multi-site strategy. Instead of
writing a Python adapter for every site, most standard game-download sites can
be supported by dropping a JSON file into `sites/configs/`. A single generic
adapter reads that config and fulfils the full SiteAdapter contract:

    listing page(s)  -> parse_listing()      (config: listing.item + fields)
    detail/download  -> parse_mirrors()      (config: detail.mirror_item ...)
    redirect page    -> resolve_final_link() (config: resolve.final_link)
    full site        -> discover_all_urls()  (config: full_site.*, optional)

The selector engine is intentionally flexible so that differences between sites
are absorbed by DATA, not code:
  * a field may list several fallback selectors (first match wins);
  * a value may come from element text or any attribute ("attr": "href");
  * an optional regex + transforms (strip / absolute_url / number / ...) clean it;
  * missing optional fields fall back to a default instead of crashing.

When a site is too weird for config (heavy JS, exotic ad-gates), write a real
Python SiteAdapter instead — both kinds live side-by-side in the registry.

All parsing here is pure (HTML string in, data out) so it is unit-tested offline.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup

from logger import log
from models import Game, Mirror
from sites.base import SiteAdapter, SiteMeta


class ConfigError(ValueError):
    """Raised when a site config file is missing required keys or is malformed."""


# ══ Selector engine (pure) ═════════════════════════
def _first_element(scope, selector):
    """Return the first element matching `selector` (str or list of str)."""
    if isinstance(selector, (list, tuple)):
        for sel in selector:
            el = scope.select_one(sel)
            if el is not None:
                return el
        return None
    return scope.select_one(selector)


def _apply_transform(value: Optional[str], transform: str, base_url: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        # e.g. a multi-valued attribute like class -> join it
        value = " ".join(value) if isinstance(value, (list, tuple)) else str(value)
    if transform == "strip":
        return value.strip()
    if transform == "lower":
        return value.lower()
    if transform == "upper":
        return value.upper()
    if transform == "title":
        return value.title()
    if transform == "collapse_ws":
        return re.sub(r"\s+", " ", value).strip()
    if transform == "absolute_url":
        return urljoin(base_url, value)
    if transform == "number":
        m = re.search(r"[\d.]+", value)
        return m.group(0) if m else value
    log.debug("Unknown transform '%s' ignored", transform)
    return value


def extract_value(scope, spec: Any, base_url: str) -> Optional[str]:
    """Extract a single string value from `scope` using a field spec.

    A spec can be:
      * None                          -> None
      * "a.title"                     -> text of first match
      * [spec, spec, ...]             -> try each in order, first non-empty wins
      * {"selector": ..., "attr": ..., "regex": ..., "regex_group": ...,
         "transform": [...], "fallback": spec, "default": ...}
    When "selector" is omitted, the value is read from `scope` itself (handy for
    reading an attribute off the container element, e.g. a mirror <a>'s href).
    """
    if spec is None:
        return None

    # list of specs: first that yields a non-empty value wins
    if isinstance(spec, (list, tuple)):
        for sub in spec:
            val = extract_value(scope, sub, base_url)
            if val not in (None, ""):
                return val
        return None

    if isinstance(spec, str):
        spec = {"selector": spec}

    if not isinstance(spec, dict):
        return None

    def _fallback_or_default():
        if spec.get("fallback") is not None:
            return extract_value(scope, spec["fallback"], base_url)
        return spec.get("default")

    selector = spec.get("selector")
    el = _first_element(scope, selector) if selector else scope
    if el is None:
        return _fallback_or_default()

    attr = spec.get("attr")
    value = el.get(attr) if attr else el.get_text(strip=True)
    if value in (None, ""):
        return _fallback_or_default()

    regex = spec.get("regex")
    if regex:
        if not isinstance(value, str):
            value = str(value)
        m = re.search(regex, value)
        if m:
            group = spec.get("regex_group", 1 if m.groups() else 0)
            value = m.group(group)
        else:
            return _fallback_or_default()

    for transform in (spec.get("transform") or []):
        value = _apply_transform(value, transform, base_url)

    if value in (None, ""):
        return _fallback_or_default()
    return value


def _leading_text(el) -> str:
    """Return the text of `el` that appears BEFORE its first <a> descendant,
    cleaned up. Used for 'labeled group' download blocks where the hoster name is
    plain text in front of one or more <a> 'Click Here' links, e.g.:
        <p><strong>Torrent – <a>Click Here</a> – or – <a>Click Here</a></strong></p>
    -> "Torrent".
    """
    parts: List[str] = []
    for node in el.descendants:
        if getattr(node, "name", None) == "a":
            break
        if isinstance(node, str):
            parts.append(str(node))
    text = re.sub(r"\s+", " ", "".join(parts)).strip()
    # drop trailing separators/dashes left dangling before the first link
    text = re.sub(r"[\s|:•·\-\u2013\u2014]+$", "", text).strip()
    return text


def _parse_locs(xml: str) -> List[str]:
    """Return every <loc> URL from a sitemap / sitemap index."""
    soup = BeautifulSoup(xml, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if loc.get_text(strip=True)]


# ══ Config validation + loading ═════════════════════
REQUIRED_TOP = ("name", "base_url", "category", "platform")


def validate_config(cfg: Dict[str, Any], source: str = "<config>") -> Dict[str, Any]:
    """Validate a site config dict, raising ConfigError with a clear message."""
    if not isinstance(cfg, dict):
        raise ConfigError(f"{source}: config must be a JSON object.")

    for key in REQUIRED_TOP:
        if not cfg.get(key):
            raise ConfigError(f"{source}: missing required key '{key}'.")

    listing = cfg.get("listing")
    if not isinstance(listing, dict):
        raise ConfigError(f"{source}: missing 'listing' section.")
    if not listing.get("item"):
        raise ConfigError(f"{source}: 'listing.item' selector is required.")
    fields = listing.get("fields")
    if not isinstance(fields, dict) or not fields.get("title") or not fields.get("detail_url"):
        raise ConfigError(
            f"{source}: 'listing.fields' must define at least 'title' and 'detail_url'."
        )

    detail = cfg.get("detail")
    if not isinstance(detail, dict) or not detail.get("mirror_item"):
        raise ConfigError(f"{source}: 'detail.mirror_item' selector is required.")

    resolve = cfg.get("resolve") or {}
    if resolve.get("mode") != "none" and not resolve.get("final_link"):
        raise ConfigError(
            f"{source}: 'resolve.final_link' is required "
            f"(or set 'resolve.mode' to \"none\" when mirror links are already final)."
        )

    return cfg


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge `over` onto `base` (values in `over` win). Nested dicts
    are merged; everything else is replaced. Used for config presets."""
    result = dict(base)
    for key, val in over.items():
        if isinstance(result.get(key), dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _preset_path(name: str, configs_dir: str) -> Optional[str]:
    for fname in (f"_preset_{name}.json", f"_{name}.json"):
        p = os.path.join(configs_dir, fname)
        if os.path.isfile(p):
            return p
    return None


def _resolve_extends(
    cfg: Dict[str, Any], configs_dir: str, source: str = "<config>",
    _seen: Optional[set] = None,
) -> Dict[str, Any]:
    """If `cfg` has an "extends": "<preset>" key, deep-merge the preset
    (`_preset_<preset>.json` in `configs_dir`) UNDER it so the child overrides the
    preset. Presets may themselves extend other presets."""
    parent = cfg.get("extends")
    if not parent:
        return cfg
    _seen = _seen or set()
    if parent in _seen:
        raise ConfigError(f"{source}: circular 'extends' chain via '{parent}'.")
    _seen.add(parent)
    path = _preset_path(parent, configs_dir)
    if not path:
        raise ConfigError(
            f"{source}: preset '{parent}' not found "
            f"(expected _preset_{parent}.json in {configs_dir})."
        )
    try:
        with open(path, "r", encoding="utf-8") as fh:
            preset_raw = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON — {exc}") from exc
    preset = _resolve_extends(preset_raw, configs_dir, os.path.basename(path), _seen)
    merged = _deep_merge(preset, cfg)
    merged.pop("extends", None)
    return merged


def load_config(path: str, configs_dir: Optional[str] = None) -> Dict[str, Any]:
    """Read + validate a single JSON config file (resolving `extends` presets)."""
    if configs_dir is None:
        configs_dir = os.path.dirname(os.path.abspath(path))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON — {exc}") from exc
    cfg = _resolve_extends(raw, configs_dir, source=os.path.basename(path))
    validate_config(cfg, source=os.path.basename(path))
    cfg["name"] = str(cfg["name"]).strip().lower()
    cfg["__source__"] = path
    return cfg


def default_configs_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")


def discover_configs(configs_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load every `*.json` config in `configs_dir` (files starting with '_' are
    treated as disabled examples and skipped)."""
    if configs_dir is None:
        configs_dir = default_configs_dir()
    results: List[Dict[str, Any]] = []
    if not os.path.isdir(configs_dir):
        return results
    for fname in sorted(os.listdir(configs_dir)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        path = os.path.join(configs_dir, fname)
        try:
            results.append(load_config(path))
        except ConfigError as exc:
            log.warning("Skipping invalid site config %s: %s", fname, exc)
    return results


def config_meta(cfg: Dict[str, Any]) -> SiteMeta:
    return SiteMeta(
        name=str(cfg["name"]).strip().lower(),
        base_url=cfg["base_url"],
        category=cfg["category"],
        platform=cfg["platform"],
        description=cfg.get("description", ""),
    )


def _fill(template: str, page: int, query: str, base: str = "") -> str:
    """Fill a URL template. Uses str.replace (not .format) so real braces in a
    URL never break, and only the {base} / {page} / {query} tokens are
    substituted. {base} lets a shared preset stay site-agnostic."""
    return (
        template.replace("{base}", base)
        .replace("{page}", str(page))
        .replace("{query}", query)
    )


# ══ The adapter ══════════════════════════════
class GenericConfigAdapter(SiteAdapter):
    """A SiteAdapter whose behaviour is entirely driven by a config dict."""

    def __init__(self, config: Dict[str, Any]):
        validate_config(config, source=config.get("name", "<config>"))
        self.config = config
        self.meta = config_meta(config)
        self.supports_full_site = bool(config.get("full_site"))
        # When resolve.mode == "none", the mirror's own link is already the final
        # link (or only resolvable via JS/captcha), so the engine must NOT fetch
        # and resolve each redirect page.
        self.resolves_final_link = (config.get("resolve") or {}).get("mode") != "none"

    # ── listing ────────────────────────────────────────────────────
    def build_listing_url(self, page: int, query: Optional[str] = None) -> str:
        listing = self.config["listing"]
        base = self.base_url
        if query:
            q = quote_plus(query)
            if page == 1 and listing.get("search_first_url"):
                return _fill(listing["search_first_url"], page, q, base)
            tpl = listing.get("search_url") or listing.get("page_url")
            if tpl:
                return _fill(tpl, page, q, base)
            return base.rstrip("/") + "/?s=" + q
        if page == 1 and listing.get("first_page_url"):
            return _fill(listing["first_page_url"], page, "", base)
        tpl = listing.get("page_url")
        if not tpl:
            return base
        return _fill(tpl, page, "", base)

    def parse_listing(self, html: str) -> List[Game]:
        soup = BeautifulSoup(html, "html.parser")
        listing = self.config["listing"]
        fields = listing.get("fields", {})
        games: List[Game] = []
        for item in soup.select(listing["item"]):
            detail_url = extract_value(item, fields.get("detail_url"), self.base_url)
            if not detail_url:
                continue
            games.append(Game(
                title=extract_value(item, fields.get("title"), self.base_url) or "No Title",
                meta_size=extract_value(item, fields.get("meta_size"), self.base_url) or "N/A",
                meta_genre=extract_value(item, fields.get("meta_genre"), self.base_url) or "N/A",
                detail_url=detail_url,
            ))
        return games

    # ── detail / mirrors ───────────────────────────────────────────
    def build_download_index_url(self, detail_url: str) -> str:
        tpl = self.config["detail"].get("download_index_url")
        if tpl:
            return tpl.replace("{detail_url}", detail_url.rstrip("/"))
        return detail_url

    def parse_mirrors(
        self,
        html: str,
        detail_url: str,
        format_filter: str = "ALL",
        hoster_filter: str = "ALL",
    ) -> List[Mirror]:
        soup = BeautifulSoup(html, "html.parser")
        detail = self.config["detail"]
        if detail.get("mirror_mode") == "labeled_group":
            return self._parse_mirrors_labeled_group(soup, detail, format_filter, hoster_filter)
        mfields = detail.get("mirror_fields", {})
        split = detail.get("raw_text_split")
        default_redirect = {"attr": "href", "transform": ["absolute_url"]}
        mirrors: List[Mirror] = []

        for el in soup.select(detail["mirror_item"]):
            redirect_url = extract_value(
                el, mfields.get("redirect_url", default_redirect), self.base_url
            )
            if not redirect_url:
                continue
            raw_text = extract_value(el, mfields.get("raw_text"), self.base_url) or ""
            rom_format = extract_value(el, mfields.get("format"), self.base_url)
            size = extract_value(el, mfields.get("size"), self.base_url)
            hoster = extract_value(el, mfields.get("hoster"), self.base_url)

            if split and raw_text:
                parts = [p.strip() for p in raw_text.split(split.get("delimiter", "|"))]

                def pick(idx):
                    if idx is None or idx < 0 or idx >= len(parts):
                        return None
                    return parts[idx]

                rom_format = rom_format or pick(split.get("format_index"))
                size = size or pick(split.get("size_index"))
                hoster = hoster or pick(split.get("hoster_index"))

            rom_format = rom_format or "N/A"
            size = size or "N/A"
            hoster = hoster or "Unknown"

            if format_filter != "ALL" and format_filter not in rom_format.upper():
                continue
            if hoster_filter != "ALL" and hoster_filter not in hoster.upper():
                continue

            mirrors.append(Mirror(
                raw_text=raw_text or hoster,
                format=rom_format,
                size=size,
                hoster=hoster,
                redirect_url=redirect_url,
            ))
        return mirrors

    def _parse_mirrors_labeled_group(
        self, soup, detail, format_filter: str, hoster_filter: str,
    ) -> List[Mirror]:
        """Parse download blocks where the hoster name is plain text in front of
        one or more <a> links (e.g. "Torrent – Click Here – or – Click Here").
        Each <a> becomes its own Mirror tagged with the group's hoster label.
        Groups with an empty label (e.g. a bare YouTube link) are skipped.
        """
        link_sel = detail.get("group_link_selector", "a[href]")
        label_pattern = detail.get("group_label_pattern")
        lrx = re.compile(label_pattern, re.I) if label_pattern else None
        skip = {h.lower() for h in detail.get("group_skip_hosters", [])}
        mirrors: List[Mirror] = []
        for group in soup.select(detail["mirror_item"]):
            hoster = _leading_text(group)
            if not hoster or hoster.lower() in skip:
                continue
            if lrx and not lrx.search(hoster):
                continue
            if hoster_filter != "ALL" and hoster_filter not in hoster.upper():
                continue
            for a in group.select(link_sel):
                href = a.get("href")
                if not href:
                    continue
                mirrors.append(Mirror(
                    raw_text=hoster,
                    format="N/A",
                    size="N/A",
                    hoster=hoster,
                    redirect_url=urljoin(self.base_url, href),
                ))
        return mirrors

    def resolve_final_link(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        resolve = self.config.get("resolve", {})
        value = extract_value(soup, resolve.get("final_link"), self.base_url)
        return value or resolve.get("default", "N/A")

    # ── optional: detail-page title recovery ───────────────────────
    def parse_detail_title(self, html: str) -> Optional[str]:
        spec = self.config.get("detail", {}).get("title")
        if not spec:
            return None
        soup = BeautifulSoup(html, "html.parser")
        return extract_value(soup, spec, self.base_url)

    # ── optional: per-site filter menus ────────────────────────────
    def format_choices(self) -> Dict[str, str]:
        return dict(self.config.get("filters", {}).get("format", {"1": "ALL"}))

    def hoster_choices(self) -> Dict[str, str]:
        return dict(self.config.get("filters", {}).get("hoster", {"1": "ALL"}))

    # ── optional: full-site discovery via sitemap ──────────────────
    def discover_all_urls(self, client) -> List[str]:
        fs = self.config.get("full_site")
        if not fs:
            return []
        candidates = fs.get("sitemap_candidates") or ["sitemap.xml", "sitemap_index.xml"]
        skip = [k.lower() for k in fs.get("skip_keywords", [])]
        pattern = fs.get("game_url_pattern")
        rx = re.compile(pattern) if pattern else None

        root_xml: Optional[str] = None
        for cand in candidates:
            url = self.base_url.rstrip("/") + "/" + str(cand).lstrip("/")
            log.info("Looking for sitemap: %s", url)
            xml = client.get(url)
            if xml and "<loc" in xml.lower():
                root_xml = xml
                log.info("Using sitemap: %s", url)
                break
        if not root_xml:
            return []

        locs = _parse_locs(root_xml)
        sub_sitemaps = [u for u in locs if u.lower().endswith(".xml")]
        seen: set = set()
        urls: List[str] = []

        def _collect(cands: List[str]) -> None:
            for u in cands:
                lu = u.lower()
                if lu.endswith(".xml"):
                    continue
                if any(k in lu for k in skip):
                    continue
                if rx and not rx.search(u):
                    continue
                if u not in seen:
                    seen.add(u)
                    urls.append(u)

        if sub_sitemaps:
            for sm in sub_sitemaps:
                if any(k in sm.lower() for k in skip):
                    continue
                log.info("Reading sub-sitemap: %s", sm)
                xml = client.get(sm)
                if xml:
                    _collect(_parse_locs(xml))
        else:
            _collect(locs)

        log.info("Sitemap discovery found %d candidate game pages.", len(urls))
        return urls


def build_config_adapters(configs_dir: Optional[str] = None) -> List[GenericConfigAdapter]:
    """Convenience: load all configs and return ready adapter instances."""
    return [GenericConfigAdapter(cfg) for cfg in discover_configs(configs_dir)]
