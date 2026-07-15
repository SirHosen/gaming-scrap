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
`listing.fields.title`, `listing.fields.detail_url`, `detail.mirror_item`, and
`resolve.final_link` **unless** you set `resolve.mode: "none"` (see below).
Everything else is optional. With `extends` (below), a required key may come from
the preset instead of the site file.

## Sharing config across many sites (presets + `extends`)

Most sites are not unique — whole *families* share the same engine (lots of game
repack sites are WordPress blogs with an identical layout). Instead of copying
selectors into every file, put the shared "blueprint" in a **preset** and let each
real site inherit it.

- A **preset** is just a normal config file whose name starts with `_` (e.g.
  `_preset_wordpress-repack.json`). Because it starts with `_` it is **never**
  loaded as a site on its own — it only exists to be inherited.
- A **site** inherits a preset with `"extends": "<preset-name>"`. The loader looks
  for `_preset_<name>.json` (or `_<name>.json`) in this folder and **deep-merges**
  the preset underneath the site, so anything in the site file overrides the
  preset. Presets may themselves `extends` another preset.

That means a real site can be tiny. The entire `dodi.json` is:

```jsonc
{
  "extends": "wordpress-repack",
  "name": "dodi",
  "base_url": "https://dodi-repacks.site/",
  "description": "DODI Repacks — compressed Windows PC game repacks"
}
```

Adding the next WordPress-style repack site is another ~4-line file pointing at
the same preset. Only sites that genuinely differ need their own selectors.

### `{base}` URL token

So a preset can stay site-agnostic, listing URL templates may use `{base}`, which
is replaced with that site's `base_url` at runtime (alongside `{page}` /
`{query}`):

```jsonc
"first_page_url":   "{base}",
"page_url":         "{base}page/{page}/",
"search_first_url": "{base}?s={query}",
"search_url":       "{base}page/{page}/?s={query}"
```

### `detail.mirror_mode: "labeled_group"`

Some sites don't give each mirror its own row — instead the **hoster name is plain
text in front of one or more links**, e.g.
`Torrent – Click Here – or – Click Here – or – Click Here`. Set this mode and each
`<a>` becomes its own mirror tagged with the leading label:

```jsonc
"detail": {
  "mirror_mode": "labeled_group",
  "mirror_item": ".entry-content p",     // each block that starts with a hoster label
  "group_link_selector": "a[href]",       // which links inside count (default a[href])
  "group_skip_hosters": ["youtube", "subscribe"], // ignore these labels
  "group_label_pattern": null              // optional regex; only keep labels that match
}
```

Blocks whose label comes out empty (e.g. a bare YouTube link with no leading
text) are skipped automatically.

### `resolve.mode: "none"`

When a site's mirror links go through a shortener / countdown / captcha gate that
can only be passed in a real browser (e.g. DODI's `zovo.ink` → `go.zovo.ink` →
`tii.la`), there is no reliable final URL to fetch server-side. Set:

```jsonc
"resolve": { "mode": "none" }
```

and the engine keeps the mirror link **as-is** instead of trying (and failing) to
resolve a final link. `resolve.final_link` is then not required.

## Adding a site in 3 steps

1. Grab HTML samples of (a) the listing page, (b) one detail/download page, and
   (c) a redirect page if the site uses one.
2. Copy `_example.json` to `mysite.json` and fill in the selectors.
3. Run `python scraper.py --site mysite --search "test"` and iterate.

When a site can't be expressed here (JS-rendered content, timer ad-gates), write
a Python adapter instead — see `sites/switchroms.py` for the reference.
