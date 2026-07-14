# Changelog

All notable changes to **NESTfetch** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Phase 2 — SQLite persistence + scrape history (new / changed / removed games,
  when a link first went dead).
- Phase 3 — async HTTP, smarter retries, pytest suite, packaging.
- Phase 4 — scheduler + notifications (Telegram / Discord / email).
- Phase 5 — web dashboard / desktop UI.
- More site adapters (Windows games, emulators, Linux, ...).

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

[Unreleased]: https://github.com/USERNAME/nestfetch/compare/v4.0.0...HEAD
[4.0.0]: https://github.com/USERNAME/nestfetch/releases/tag/v4.0.0
[3.3.0]: https://github.com/USERNAME/nestfetch/releases/tag/v3.3.0
[3.2.0]: https://github.com/USERNAME/nestfetch/releases/tag/v3.2.0
[3.1.0]: https://github.com/USERNAME/nestfetch/releases/tag/v3.1.0
[3.0.0]: https://github.com/USERNAME/nestfetch/releases/tag/v3.0.0
