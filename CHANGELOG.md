# Changelog

All notable changes to **NESTfetch** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Phase 5 — web dashboard / desktop UI.
- More site adapters (Windows games, emulators, Linux, ...).

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

[Unreleased]: https://github.com/USERNAME/nestfetch/compare/v4.3.0...HEAD
[4.3.0]: https://github.com/USERNAME/nestfetch/compare/v4.2.0...v4.3.0
[4.2.0]: https://github.com/USERNAME/nestfetch/compare/v4.1.0...v4.2.0
[4.1.0]: https://github.com/USERNAME/nestfetch/releases/tag/v4.1.0
[4.0.0]: https://github.com/USERNAME/nestfetch/releases/tag/v4.0.0
[3.3.0]: https://github.com/USERNAME/nestfetch/releases/tag/v3.3.0
[3.2.0]: https://github.com/USERNAME/nestfetch/releases/tag/v3.2.0
[3.1.0]: https://github.com/USERNAME/nestfetch/releases/tag/v3.1.0
[3.0.0]: https://github.com/USERNAME/nestfetch/releases/tag/v3.0.0
