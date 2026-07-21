# Architecture

NESTfetch is a modular, multi-site game-download **metadata** scraper. This
document explains how the pieces fit together so you can navigate and extend the
codebase quickly.

## High-level flow

```
CLI / interactive menu  (cli.py, scraper.py, __main__.py)
        │
        ▼
  ScraperEngine  (engine.py)  ──uses──►  HttpClient (http_client.py)
        │                                    │
        │                                    ├─ RobotsPolicy (robots.py)  ← ethics gate
        │                                    ├─ retry / backoff / rate-limit
        │                                    └─ on-disk response cache
        │
        ├─ SiteAdapter (sites/*)  ── parse_listing / parse_mirrors / resolve_final_link
        │        └─ GenericConfigAdapter (config_adapter.py) driven by sites/configs/*.json
        │
        ▼
   models.py (Game, Mirror)  ──►  exporters.py (JSON/CSV)  +  database.py (SQLite history)
                                        │
                                        └─►  notifier.py / scheduler.py / webapp.py
```

## Package layout (`src/nestfetch/`)

| Module            | Responsibility                                              |
|-------------------|-------------------------------------------------------------|
| `__main__.py`     | Enables `python -m nestfetch`; delegates to `scraper.main`. |
| `cli.py`          | Argparse CLI + interactive menu.                            |
| `scraper.py`      | Entry point: wires CLI args to the engine and run modes.    |
| `config.py`       | Global constants (headers, rate-limit, robots toggles, …).  |
| `settings.py`     | Env / `.env` / JSON settings loader for secrets & options.  |
| `logger.py`       | Coloured console + file logging.                            |
| `models.py`       | `Game` / `Mirror` dataclasses — the shared data contract.   |
| `http_client.py`  | Sync HTTP with retry/backoff, cache, rate-limit, robots.    |
| `robots.py`       | `RobotsPolicy`: per-host robots.txt fetch + allow/deny.     |
| `async_client.py` | Optional aiohttp fetcher; threaded fallback if absent.      |
| `parsers.py`      | Pure BeautifulSoup helpers (no I/O).                        |
| `engine.py`       | Site-agnostic orchestration incl. the two-step download hop.|
| `exporters.py`    | JSON + Excel-friendly CSV writers.                          |
| `database.py`     | SQLite run history + diffing (new/removed games).           |
| `link_checker.py` | Dead / expired link validator.                              |
| `link_resolver.py`| Shortener / ad-gate resolver (optional browser fallback).   |
| `notifier.py`     | Telegram / Discord / email notifications.                   |
| `scheduler.py`    | Interval scheduler for automated runs.                      |
| `webapp.py`       | Local stdlib dashboard (no web framework dependency).       |
| `healthcheck.py`  | Re-parses `samples/` to detect config drift.                |
| `sites/`          | Adapters + the config-driven site engine (see below).       |

## The site layer (`sites/`)

- `base.py` defines the `SiteAdapter` interface: `parse_listing(html)`,
  `build_listing_url(...)`, `parse_mirrors(...)`, `resolve_final_link(...)`, plus
  a `SiteMeta` describing the site.
- `registry.py` is the **single source of truth** for supported sites
  (`site_names()`, `get_adapter(name)`, `available_sites()`, `DEFAULT_SITE`).
- `config_adapter.py` provides `GenericConfigAdapter`, which turns a JSON file in
  `configs/` into a full adapter — no per-site Python. This is how 8 of the 9
  sites are implemented.
- `switchroms.py` is the one reference hand-written adapter, kept as an example
  of what a code adapter looks like when a config isn't expressive enough.

Adding a site is therefore usually just: drop a `configs/<site>.json`, save a
`samples/<site>.txt`, and add a regression test. See `CONTRIBUTING.md`.

## The two-step download engine

Some sites hide the real download/index behind a second page. A config can
declare `detail.index_from_detail` — "the download page URL is built from a value
scraped off the detail page" (e.g. a hidden `post_id` or numeric `id`). The
engine fetches the detail page, builds the real URL, then parses mirrors from it,
all without site-specific code.

## Ethics gate: robots.txt

`RobotsPolicy` (in `robots.py`) is consulted by `HttpClient.get()` **before** the
rate-limiter, for every fetch:

- `robots.txt` itself is always allowed (otherwise we could never read it).
- Results are cached per host.
- An unreachable/unparseable `robots.txt` **fails open** (allow) with a debug
  log — a site outage shouldn't halt a run — while an explicit `Disallow`
  results in the URL being skipped (logged at info level).
- Fully disabled (`RESPECT_ROBOTS_TXT = False`) means zero robots I/O.

## Testing philosophy

The suite is 100% offline and deterministic. HTTP is replaced by fakes
(`tests/fakes.py`: `FakeResp`, `FakeSession`, `FakeClock`) and real site parsing
is validated against recorded `samples/`. The `healthcheck` reuses those same
samples so a config that silently stops matching a site's HTML is caught early.
