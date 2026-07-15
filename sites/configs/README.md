# Site configs (config-driven adapters)

Drop a `.json` file in this folder to add a new game-download site to NESTfetch
**without writing any Python**. On startup the registry auto-loads every
`*.json` here and serves it through `GenericConfigAdapter`.

- Files starting with `_` (like `_example.json`) are treated as disabled
  templates and are **skipped** by the loader.
- If a JSON config and a hand-written Python adapter share the same `name`, the
  **Python adapter wins** (deliberate override / escape hatch).
- An invalid config is skipped with a warning — it never crashes the CLI.

## The shape every site shares

HTML differs per site, but the *flow* is almost always the same:

```
listing page(s)  ->  detail / download page  ->  (optional) redirect page  ->  final link
```

A config just tells the engine **where** each piece lives in that site's HTML.

## Field specs (how a value is extracted)

Anywhere the schema below expects a value, you can use one of:

| Form | Meaning |
|------|---------|
| `"a.title"` | text of the first element matching this CSS selector |
| `["a.title", "h2 a"]` | try each selector in order, first non-empty wins |
| `{ "selector": "a.title", "attr": "href" }` | read an attribute instead of text |
| `{ "attr": "href" }` | read from the container element itself (no selector) |
| `{ "selector": "...", "regex": "([0-9.]+) GB", "regex_group": 1 }` | pull a substring out |
| `{ "selector": "...", "transform": ["strip", "absolute_url"] }` | clean the value |
| `{ "selector": "...", "fallback": {...}, "default": "N/A" }` | fallbacks when nothing matches |

**Transforms:** `strip`, `lower`, `upper`, `title`, `collapse_ws`,
`absolute_url` (join relative URLs onto `base_url`), `number` (keep the first
`[0-9.]` run, e.g. `"Size: 4.2 GB"` -> `"4.2"`).

## Schema

```jsonc
{
  "name": "mysite",              // unique slug (lowercased); used as --site mysite
  "base_url": "https://mysite.com/",
  "category": "windows",         // windows | emulator | linux | switch-rom | ...
  "platform": "Windows PC",      // human label
  "description": "one-liner for --list-sites",

  "listing": {
    // URL templates. {page} and {query} are substituted; real braces are safe.
    "first_page_url": "https://mysite.com/",             // optional page-1 override (no search)
    "page_url": "https://mysite.com/page/{page}/",       // page N (no search)
    "search_url": "https://mysite.com/page/{page}/?s={query}", // optional search template
    "item": "article.game",      // selector for each game card in the listing
    "fields": {
      "title":     "a.title",                             // REQUIRED
      "detail_url": { "selector": "a.title", "attr": "href", "transform": ["absolute_url"] }, // REQUIRED
      "meta_size":  { "selector": "span.size", "transform": ["strip"] },   // optional
      "meta_genre": "span.genre"                          // optional
    }
  },

  "detail": {
    "download_index_url": "{detail_url}/?download",       // optional; {detail_url} substituted
    "mirror_item": "a.download-button",  // selector for each mirror row/link
    "mirror_fields": {
      "redirect_url": { "attr": "href", "transform": ["absolute_url"] }, // default if omitted
      "raw_text": "span.link-title",
      "format": "span.format",           // OR derive via raw_text_split below
      "size": "span.size",
      "hoster": "span.host"
    },
    // If a site packs "NSP | 4 GB | MediaFire" into one string, split it:
    "raw_text_split": { "delimiter": "|", "format_index": 0, "size_index": 1, "hoster_index": 2 },
    "title": [{ "selector": "meta[property='og:title']", "attr": "content" }, "h1.entry-title"]  // optional detail-page title recovery (meta tags need attr:content)
  },

  "resolve": {
    // Where the FINAL hoster link lives on the redirect/ad-gate page.
    // A list = fallback chain (first match wins).
    "final_link": [
      { "selector": "#download-active a", "attr": "href" },
      { "selector": ".download a", "attr": "href" }
    ],
    "default": "N/A"
  },

  "filters": {                    // optional interactive-menu filters
    "format": { "1": "ALL", "2": "NSP", "3": "XCI" },
    "hoster": { "1": "ALL", "2": "MEDIAFIRE", "3": "MEGA" }
  },

  "full_site": {                  // optional: enables --all via XML sitemap
    "sitemap_candidates": ["sitemap.xml", "sitemap_index.xml"],
    "skip_keywords": ["category", "tag", "author", "page"],
    "game_url_pattern": "^https?://[^/]+/[^/]+/?$"   // regex marking a game detail URL
  }
}
```

**Required keys:** `name`, `base_url`, `category`, `platform`, `listing.item`,
`listing.fields.title`, `listing.fields.detail_url`, `detail.mirror_item`,
`resolve.final_link`. Everything else is optional.

## Adding a site in 3 steps

1. Grab HTML samples of (a) the listing page, (b) one detail/download page, and
   (c) a redirect page if the site uses one.
2. Copy `_example.json` to `mysite.json` and fill in the selectors.
3. Run `python scraper.py --site mysite --search "test"` and iterate.

When a site can't be expressed here (JS-rendered content, timer ad-gates), write
a Python adapter instead — see `sites/switchroms.py` for the reference.
