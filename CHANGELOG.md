# Changelog

All notable changes to **NESTfetch** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [4.9.0] - 2026-07-21

### Changed
- **Restructured into a `src/` package layout.** All modules moved from the repo
  root into an importable `src/nestfetch/` package (with `__init__.py` and
  `__main__.py`). Run with `python -m nestfetch` or the installed `nestfetch`
  command. All internal imports rewritten to absolute `nestfetch.*` form; test
  path bootstraps, `conftest.py`, and packaging (`package-dir`, `packages.find`,
  `package-data`) updated accordingly. No behavioural changes.
- **Docs consolidated under `docs/`** (`ARCHITECTURE.md`, `AUDIT.md`,
  `ROADMAP.md`); repo root is now clean and scannable.
- **Dashboard/CLI/package version bumped to `4.9`** across `webapp.py`,
  `cli.py`, `__init__.py`, and `pyproject.toml`.

### Added
- **robots.txt politeness** (`nestfetch/robots.py`, on by default via
  `RESPECT_ROBOTS_TXT`). The engine consults each host's `robots.txt` before
  fetching and skips disallowed URLs; `robots.txt` itself is always fetched;
  unreachable robots fails open (allow) with a debug log. Wired into
  `HttpClient` (opt-in) and enabled by `ScraperEngine`.
- **Config health-check** (`nestfetch/healthcheck.py`,
  `python -m nestfetch.healthcheck`, `tools/healthcheck.py`): re-parses saved
  `samples/` pages with each adapter and flags configs that extract 0 items.
- **Continuous Integration** (`.github/workflows/ci.yml`): ruff + mypy +
  9-site load check + health-check + pytest on Python 3.9 / 3.11 / 3.12.
- **Dev tooling & scaffolding**: `[tool.ruff]` / `[tool.mypy]` config,
  `requirements-dev.txt` (pinned), `Makefile` (`make check`), `.editorconfig`,
  `CONTRIBUTING.md`, `SECURITY.md`, and `docs/ARCHITECTURE.md`.
- **New tests** (suite now 82, all offline): `tests/test_robots.py` (6) and
  `tests/test_healthcheck.py` (4).

### Fixed
- **`.gitignore` config-preserve path** updated for the new layout
  (`!src/nestfetch/sites/configs/`), so shipped JSON configs are still tracked.
- Added per-case `log.debug` diagnostics to previously silent `except` blocks
  (adapter introspection, browser auto-open); documented the error-handling
  policy that intentional best-effort cleanup (e.g. closing a connection) stays
  quiet by design.

---

## [4.8.1] - 2026-07-21

### Fixed
- **Shipped site configs were being excluded from the package.** The blanket
  `*.json` rule in `.gitignore` also swallowed `sites/configs/*.json`, so only the
  built-in `switchroms` Python adapter was registered (`--list-sites` showed 1
  site instead of 9) and all 8 `test_real_<site>_config` tests failed without the
  files present. Added explicit `!sites/configs/` and `!sites/configs/*.json`
  whitelist exceptions and restored the 8 configs + shared preset.
- **Dashboard version mismatch.** `webapp.py` reported `4.4`; bumped to `4.8` to
  match `pyproject.toml`, `scraper.py`, and `cli.py`.
- **Placeholder project URLs.** Replaced `github.com/USERNAME/nestfetch` with the
  real owner in `pyproject.toml` and `CHANGELOG.md`.
- **Leftover single-site branding.** Default logger name `switchroms` →
  `nestfetch`; `config.py` module docstring updated to "NESTfetch scraper".
- **Stale README "Project Structure".** Rewritten to reflect the current
  multi-site layout and to document the `sites/configs/` packaging exception.

### Added
- **Registry smoke tests** (`tests/test_registry_smoke.py`) that fail loudly if the
  registry ever drops below the full 9-site roster — guarding against the config
  packaging regression above.
- **`AUDIT.md`** — full audit report (findings, root causes, fixes, verification).
- **Strengthened Legal & Ethical Notice** in the README.

### Planned
- More site adapters (Windows games, emulators, Linux, ...) — now mostly JSON configs.
- Verify the best-effort search/full-site URLs for the newer sites against live pages.

---

## [4.8.0] - 2026-07-17

### Added
- **7 new site configs (pure JSON, no new code):** `freelinuxpcgames`,
  `skidrowcodex`, `ovagames`, `romsfun`, `coolrom`, `nxbrew`, `elamigos`.
  `--list-sites` now reports **9** sites. Each was onboarded from a live HTML
  sample and locked in with a dedicated
  `tests/test_config_adapter.py::test_real_<site>_config` regression test.
- **Reusable two-step download engine.** New optional `detail.index_from_detail`
  config block (`url_template`, `value` selector/attr, `slug`); `SiteAdapter`
  gained `needs_detail_page` + `build_index_url_from_detail()`. When set, the
  engine (`_scrape_single_game`) fetches the detail page first, builds the real
  download/index URL from a scraped value (e.g. `post_id`, numeric `id`), and only
  then parses mirrors. Used by `romsfun` (`/download/{slug}-{post_id}`) and
  `coolrom` (`/dlpop.php?id={id}`). Covered by
  `tests/test_engine.py::test_engine_two_step_fetches_detail_then_index`.
- **Extraction capabilities exercised by the new configs:** regex-filtered listing
  links (skip navbar/category anchors), gate URLs regex-extracted from
  `onclick="window.open('…')"` (nxbrew), hoster names cleaned of leading symbols
  (elamigos `★ ROOTZ` → `ROOTZ`), dual grid/list listing layouts + raw-byte sizes
  (coolrom), and scoped mirror blocks (`#notiene` to exclude "complements").

### Notes
- Several search-result and full-site URLs for the new sites are best-effort and
  flagged for live verification; browse + detail parsing is sample-verified.

---

## [4.7.0] - 2026-07-15

### Added
- **Per-site format/hoster filters.** `--format` / `--hoster` and the interactive
  menu now render the *selected site's own* choices (from each adapter's
  `format_choices()` / `hoster_choices()`) instead of a hard-coded Switch list.
  `--list-sites` now prints each site's valid `Formats` and `Hosters`. The
  argparse `choices=` allow-lists were removed so cross-site values are accepted;
  an unknown filter is passed through with a non-fatal warning
  (`scraper._validate_filter`).
- **DODI full-catalogue mode.** The WordPress-repack preset gained a `full_site`
  block (`sitemap_candidates`, `skip_keywords`, `game_url_pattern`), so DODI now
  supports `--all` (no query) to crawl the entire site via its XML sitemap, with
  automatic fallback to paginated discovery. Every future repack site inherits it.
- **Link-checker rate limiting + verdict cache.** `check_csv_links` /
  `check_link` accept `rate_limit` (polite per-host spacing, enforced under a lock
  so different hosts never block each other) and `use_cache` (an on-disk
  `ResponseCache` of `status/code/detail` verdicts under `.http_cache/linkcheck`,
  honouring `CACHE_TTL`; only ACTIVE/DEAD are cached). The `check` CLI action now
  forwards `--rate-limit` and `--cache`.
- **Tests.** `tests/test_engine.py` now covers `--all --search` using pagination
  (not sitemap) vs. `--all` alone using sitemap discovery;
  `tests/test_config_adapter.py` verifies the shipped DODI config inherits
  `full_site` + per-site hoster filters from the preset.

### Fixed
- **`--all --search "..."`** no longer triggers full-site sitemap discovery (which
  ignored the query); it now auto-paginates through all *search-result* pages.
- **`--list-sites` / `usage` no longer advertise Switch-only `--format`/`--hoster`
  values** regardless of the chosen `--site`.

---

## [4.6.0] - 2026-07-15

### Added
- **Config presets (`extends`).** A config can now inherit a shared preset via
  `"extends": "<preset>"`, deep-merged so the child overrides the preset. This
  lets a family of similar sites share one blueprint
  (`sites/configs/_preset_wordpress-repack.json`) while each real site is a tiny
  file. Presets are `_`-prefixed and never loaded as sites; a missing preset is
  skipped with a warning, and circular `extends` chains are detected.
- **`{base}` URL token** in listing templates, filled with the site's `base_url`
  at runtime so presets stay site-agnostic (e.g. `"{base}page/{page}/"`).
- **Labeled-group mirror mode** (`detail.mirror_mode: "labeled_group"`) for
  download blocks where the hoster name is plain text in front of one or more
  `<a>` links (`Torrent – Click Here – or – Click Here`). Each link becomes a
  mirror tagged with the leading hoster label; empty labels and
  `group_skip_hosters` entries are skipped. Supports `group_link_selector`,
  `group_skip_hosters`, and optional `group_label_pattern`.
- **`resolve.mode: "none"`** for sites whose mirror links only resolve through a
  JS/countdown/captcha gate. The engine skips final-link resolution and keeps
  the mirror URL as-is (new `SiteAdapter.resolves_final_link` flag).
- **DODI Repacks onboarded** as the first real Windows site (`--site dodi`),
  config-only via the new WordPress-repack preset: search, `/page/N/`
  pagination, size parsed from the title, and per-hoster mirrors.
- **Tests.** Extended `tests/test_config_adapter.py` with preset/`extends`
  merging, missing-preset handling, `{base}` token URLs, and labeled-group +
  resolve-none parsing.

---

## [4.5.0] - 2026-07-15

### Added
- **Config-driven site adapters.** Standard game-download sites can now be added
  by dropping a JSON file in `sites/configs/` — **no Python required**. A single
  `GenericConfigAdapter` reads the config and fulfils the whole SiteAdapter
  contract (listing, detail/mirrors, redirect resolution, optional sitemap
  full-site discovery). Configs are auto-loaded by the registry; invalid ones are
  skipped with a warning instead of crashing.
- **Flexible selector engine** to absorb per-site differences: fallback selector
  chains, text-or-attribute extraction, optional regex, and value transforms
  (`strip` / `lower` / `upper` / `title` / `collapse_ws` / `absolute_url` /
  `number`), plus `raw_text_split` for sites that pack format/size/hoster into
  one string.
- **Schema guide + template** — `sites/configs/README.md` documents every field;
  `sites/configs/_example.json` is a ready-to-copy starting point (files prefixed
  with `_` are treated as disabled templates and skipped by the loader).
- **Tests.** New offline suite `tests/test_config_adapter.py` covering the
  selector engine, listing/mirror/final-link parsing, URL builders, config
  validation errors, and sitemap discovery (with a fake client).

### Changed
- The site registry now serves two tiers — config-driven sites and hand-written
  Python adapters (the escape hatch for weird sites) — with Python adapters
  overriding configs of the same name.
- Packaging now ships `sites/configs/*.json` and `*.md` as package data.

---

## [4.4.0] - 2026-07-15

### Added
- **Web dashboard (Phase 5).** A new `--serve` command launches a local
  single-page dashboard built entirely on the standard-library `http.server`
  — **zero extra dependencies**, runs fully offline, no Flask/FastAPI needed.
  - Browse and **search** the scraped catalogue, filtered by site and category,
    with per-game mirror counts and live link-health badges (active / dead).
  - View summary **stat cards**, recent **scrape history**, and a **dead-links**
    table, all served from the SQLite database.
  - **Trigger a scrape or link-check from the browser** — jobs run in the
    background (one at a time), with status polled live and results auto-refreshed.
  - Configurable bind address via `--host` / `--port` (defaults
    `127.0.0.1:8787`, i.e. localhost-only); interactive menu gains **[9] launch
    web dashboard**.
- **Tests.** New offline suite `tests/test_webapp.py` covering the data-payload
  functions (against a temp DB), the request→params builders, and the
  `JobRunner` single-flight/error handling — no sockets or network required.
- **Packaging.** `webapp` added to the installed modules; new config keys
  `WEB_DEFAULT_HOST` / `WEB_DEFAULT_PORT`.

### Changed
- The dashboard's data functions are deliberately separated from the HTTP layer
  so they stay unit-testable offline.

---

## [4.3.0] - 2026-07-15

### Added
- **Automation & notifications (Phase 4).**
  - **Watch mode / scheduler** — new `--watch` runs a scrape and/or link-check
    on a fixed interval (`--interval <minutes>`, default 60), with
    `--task {scrape,check,both}` and `--iterations N` (default: forever). Pure
    standard library; the clock is injectable so it's fully unit-tested.
  - **Multi-channel notifications** — Telegram, Discord, and email alerts when a
    scrape finds **new games** or a link check finds **newly-dead links**.
    Add `--notify` to a one-off scrape/check, or rely on watch mode. Transports
    use only `urllib`/`smtplib` and are injectable for offline tests.
  - **Settings & secrets loader** — `settings.py` reads config from environment
    variables, a `.env` file, or `config.yaml`/`config.json` (precedence:
    env > .env > config file > defaults). Channels auto-enable when their creds
    are present. Added `.env.example` and `config.example.yaml`.
  - **`--notify-test`** sends a test message to every configured channel.
  - Interactive menu gains **[7] watch mode** and **[8] test notifications**.
- **Tests.** New offline suites for settings loading, the notifier (fake
  transports), and the scheduler (injected clock).
- **Packaging.** `settings`, `notifier`, `scheduler` added to the installed
  modules; new optional extra `[config]` (PyYAML) for YAML config files.

### Changed
- Link checks now also return `newly_dead_urls`, and the scrape/check flow is
  refactored into reusable `do_scrape()` / `run_link_check()` helpers so watch
  mode can drive them and raise notifications.
- `.gitignore` now ignores real `config.yaml`/`config.json`/`.env` files while
  keeping the `*.example` templates tracked.

---

## [4.2.0] - 2026-07-15

### Added
- **Optional async fetching (Phase 3).** New `--async` flag fetches detail pages
  concurrently via `aiohttp` (`pip install nestfetch[async]`); falls back to the
  threaded client automatically when `aiohttp` isn't installed.
- **On-disk HTTP caching.** New `--cache` flag reuses recent responses
  (TTL-based, sha256-keyed) so re-runs skip already-downloaded pages.
- **Polite per-host rate limiting.** New `--rate-limit <seconds>` enforces a
  minimum interval between requests to the same host.
- **Test suite (pytest).** Offline unit tests for the HTTP client, async
  fetcher, engine, exporters, database, and link resolver, under `tests/`.
- **Packaging.** `pyproject.toml` added — `pip install .` installs a `nestfetch`
  console command; optional extras `[async]`, `[browser]`, `[dev]`.

### Changed
- **Smarter retries** in the HTTP client: exponential backoff with jitter on
  `429/500/502/503/504`, honours the `Retry-After` header, and never retries
  `404`s.
- Engine can optionally pre-fetch detail pages concurrently before resolving
  mirrors when `--async` is enabled.

---

## [4.1.0] - 2026-07-15

### Added
- **SQLite persistence + scrape history (Phase 2).** Every scrape is now stored
  in a local SQLite database (`output/nestfetch.db`), on top of the CSV/JSON.
  - normalised schema: `scrape_runs`, `games`, `mirrors`, `link_checks`;
  - **run diffing** — after each scrape NESTfetch reports what's **new**,
    **changed**, or **removed** vs. the previous run (removed detection only on
    full-site scrapes, so a keyword search never wrongly marks games removed);
  - **link-health history** — link checks are recorded per URL and NESTfetch
    tracks when a link **first went dead** (`first_dead_at`), how long it has
    been dead (`consecutive_dead`), and when it was last alive; a recovered link
    resets its dead marker;
  - **export from the database** without re-scraping (`--db-export`).
- New CLI: `--history` (recent runs + dead-link snapshot), `--db-export`,
  `--no-db` (skip persistence), and `--db PATH` (custom database file). The
  interactive menu gains matching options [5] history and [6] export-from-DB.

### Changed
- Link-check results are now persisted to the database automatically after each
  run (unless `--no-db`).

---

## [4.0.0] - 2026-07-14

### Added
- **Multi-site adapter architecture (Phase 1).** The engine is now site-agnostic
  and driven by a `SiteAdapter` contract. Adding a new site = one file in `sites/`.
  - `sites/base.py` — `SiteAdapter` + `SiteMeta` contract.
  - `sites/registry.py` — registered sites, default, lookup.
  - `sites/switchroms.py` — switchroms.io adapter (migrated from the old code;
    owns XML-sitemap full-site discovery).
- **Link provenance** — every record now carries `Source Site`, `Platform`, and
  `Category`, added to both CSV and JSON output.
- **Site selection in the CLI** — interactive site picker plus `--site` and
  `--list-sites` flags.
- **Shortener / ad-gate link resolver** (`link_resolver.py`). Detects and
  unwraps URL shorteners and ad-gate pages that sit in front of the real
  download host:
  - classifies links as `DIRECT` / `SHORTENER` / `AD_GATE` / `UNKNOWN`;
  - best-effort unwrap via HTTP redirects, embedded `?url=`/base64 targets,
    `<meta refresh>`, and links to known direct hosts;
  - link checker now reports `Link Type` + `Resolved Link` and validates the
    resolved destination (so ACTIVE/DEAD reflects the real file host);
  - domain lists + toggle live in `config.py`;
  - optional headless-browser fallback (Playwright) for JS/timer ad-gates
    (linkvertise, modern ouo.io/gplinks) — off by default, degrades gracefully
    when Playwright isn't installed.

### Changed
- Renamed the project **SwitchRoms Scraper → NESTfetch** (banner, README, CLI,
  docstrings).
- `engine.py` no longer imports switchroms parsers directly; it works through
  the injected adapter.
- `exporters.py` CSV headers extended with the provenance columns.

### Notes
- Behaviour for existing switchroms.io scraping is unchanged — this release is a
  foundation for the remaining phases.

---

## [3.3.0] - 2026-07-14

### Added
- **Active-link split + recap** for the link checker: alongside the full report
  it now writes `link_check_active.csv` (only rows whose link is ACTIVE) and
  `link_check_recap.txt` (counts + unique game titles that have an active link).

## [3.2.0] - 2026-07-12

### Added
- **Link checker** — validates whether scraped links are still alive
  (ACTIVE / DEAD / UNKNOWN) using host-specific "deleted file" text markers, not
  just HTTP status codes. Runs concurrently and writes an annotated report CSV.

### Fixed
- CSV delimiter auto-detection (tab / `;` / `,` / `|`) so semicolon-delimited
  files (Excel in ID/EU locales) are read correctly instead of as one column.

## [3.1.0] - 2026-07-12

### Added
- **Option 3: scrape ALL games** on the site via XML-sitemap discovery
  (auto-paginate), a dedicated `output/` folder, and Excel-friendly CSV
  (UTF-8 BOM, tab dialect).

### Fixed
- Duplicate games (pages 1–3 repeating) caused by pagination looping back to the
  homepage — now de-duplicated by detail URL, with sitemap-driven full scrape.
- Corrupted / duplicated game titles when discovered via sitemap.

## [3.0.0] - 2026-07-12

### Changed
- Full rewrite from a single-file script into a **modular package**
  (config, logger, models, http_client, parsers, engine, exporters, cli).
- Added retries + exponential backoff, concurrency, coloured logging, and both
  JSON and CSV export.

[Unreleased]: https://github.com/CitraGivenchyA/nestfetch/compare/v4.8.0...HEAD
[4.8.0]: https://github.com/CitraGivenchyA/nestfetch/compare/v4.7.0...v4.8.0
[4.7.0]: https://github.com/CitraGivenchyA/nestfetch/compare/v4.6.0...v4.7.0
[4.6.0]: https://github.com/CitraGivenchyA/nestfetch/compare/v4.5.0...v4.6.0
[4.5.0]: https://github.com/CitraGivenchyA/nestfetch/compare/v4.4.0...v4.5.0
[4.4.0]: https://github.com/CitraGivenchyA/nestfetch/compare/v4.3.0...v4.4.0
[4.3.0]: https://github.com/CitraGivenchyA/nestfetch/compare/v4.2.0...v4.3.0
[4.2.0]: https://github.com/CitraGivenchyA/nestfetch/compare/v4.1.0...v4.2.0
[4.1.0]: https://github.com/CitraGivenchyA/nestfetch/releases/tag/v4.1.0
[4.0.0]: https://github.com/CitraGivenchyA/nestfetch/releases/tag/v4.0.0
[3.3.0]: https://github.com/CitraGivenchyA/nestfetch/releases/tag/v3.3.0
[3.2.0]: https://github.com/CitraGivenchyA/nestfetch/releases/tag/v3.2.0
[3.1.0]: https://github.com/CitraGivenchyA/nestfetch/releases/tag/v3.1.0
[3.0.0]: https://github.com/CitraGivenchyA/nestfetch/releases/tag/v3.0.0
