# NESTfetch v4.6

A professional, modular, **multi-site game-download metadata scraper**.
Started life as a single-site Nintendo Switch ROM scraper (`switchroms.io`) and is
now being rebuilt into a platform that can scrape many game-download sites
(Switch ROMs, Windows games, emulators, Linux, and more).

## What's New in v4.6 — Config presets + first real Windows site (DODI Repacks)

The config engine grew up so that families of similar sites share one reusable
"blueprint" instead of copy-pasting selectors into every file.

- **Config presets (`extends`)** — a shared preset holds all the common logic for
  a family of sites (e.g. WordPress-based repack sites live in
  `sites/configs/_preset_wordpress-repack.json`). A real site then only needs a
  tiny file: `dodi.json` is literally 4 lines (`extends` + `name` + `base_url` +
  `description`). Adding the next repack site is another 4-line file. Presets are
  `_`-prefixed so they are never loaded as sites themselves.
- **`{base}` URL token** — presets stay site-agnostic: `"page_url": "{base}page/{page}/"`
  is filled with each site's own `base_url` at runtime.
- **Labeled-group mirrors (`mirror_mode: "labeled_group"`)** — handles download
  blocks where the hoster name is plain text in front of one or more links, e.g.
  `Torrent – Click Here – or – Click Here – or – Click Here`. Each link becomes
  its own mirror tagged with that hoster; empty/blacklisted labels are skipped.
- **`resolve.mode: "none"`** — for sites whose mirror links go through a
  shortener/countdown/captcha gate (like DODI's `zovo.ink`) that can't be
  resolved without a browser, the scraper stores the mirror link as-is instead
  of trying (and failing) to fetch a final URL.
- **First real Windows site onboarded: DODI Repacks** (`--site dodi`) — search,
  pagination (`/page/N/`), size pulled from the title (`From 27.7 GB`), and
  per-hoster mirrors, all config-only.

```bash
python scraper.py --site dodi --search "spider-man" --all-pages
```

## What's New in v4.5 — Config-driven sites (add a site without code)

NESTfetch's multi-site foundation just got a huge upgrade: most standard
game-download sites can now be added by **dropping a JSON file** into
`sites/configs/` — no Python required.

- **Config-first** — a single `GenericConfigAdapter` reads a declarative config
  (CSS selectors for the listing, detail/mirror, and redirect pages) and does
  the scraping. Auto-loaded on startup; a bad config is skipped with a warning,
  never a crash.
- **Flexible selector engine** — handles the fact that every site is different:
  fallback selector chains, text-or-attribute extraction (`"attr": "href"`),
  optional regex, and transforms (`strip`, `absolute_url`, `number`, ...).
  Sites that pack `NSP | 4 GB | MediaFire` into one string can split it.
- **Escape hatch preserved** — sites too weird for config (JS-rendered content,
  timer ad-gates) can still ship a hand-written Python adapter
  (`sites/switchroms.py` is the reference). Both tiers live in one registry;
  a Python adapter overrides a config of the same name.
- **Optional full-site mode** — a config can enable `--all` via XML-sitemap
  discovery with a URL pattern, no code.

```bash
cp sites/configs/_example.json sites/configs/mysite.json   # then edit selectors
python scraper.py --site mysite --search "test"            # try it
python scraper.py --list-sites                             # your site shows up
```

The full schema (with every field and transform) lives in
`sites/configs/README.md`. Adding a site now takes HTML samples + a JSON file
instead of a code change. New offline suite: `tests/test_config_adapter.py`.

## What's New in v4.4 — Web dashboard (Phase 5)

NESTfetch now has a browser UI — no more terminal-only. It's built on Python's
standard-library `http.server`, so it's **zero-dependency** and runs offline:

- **Launch it** — `python scraper.py --serve` then open http://127.0.0.1:8787
  (change with `--host` / `--port`, or pick **[9]** in the interactive menu).
- **Browse & search the catalogue** — filter by site and category, with per-game
  mirror counts and live **link-health badges** (active / dead).
- **See stats, history & dead links** — summary cards, recent scrape runs, and a
  dedicated dead-links table, all read from the local SQLite database.
- **Run scrapes & link-checks from the browser** — click *Run scrape* or
  *Check links*; the job runs in the background (one at a time) and the page
  refreshes automatically when it finishes.

```bash
python scraper.py --serve                 # dashboard at http://127.0.0.1:8787
python scraper.py --serve --port 9000     # custom port
python scraper.py --serve --host 0.0.0.0  # expose on your LAN (use with care)
```

No Flask/FastAPI, no build step — the whole UI ships in `webapp.py` and is
unit-tested offline (`tests/test_webapp.py`).

## What's New in v4.3 — Automation & notifications (Phase 4)

NESTfetch can now run itself and tell you when something changes — no more manual
re-runs to spot new games or freshly-dead links:

- **Watch mode (scheduler)** — `--watch` runs a scrape and/or link-check on a
  fixed interval (`--interval <minutes>`, default 60). Choose what each cycle
  does with `--task {scrape,check,both}` and stop after N cycles with
  `--iterations N` (default: run forever until Ctrl-C).
- **Notifications** — get pinged on **Telegram**, **Discord**, and/or **email**
  when a scrape finds **new games** or a link check finds **newly-dead links**.
  Add `--notify` to a one-off `scrape`/`--check-links` run, or let watch mode
  notify automatically.
- **Config & secrets, out of the code** — tokens/webhooks/SMTP creds are read
  from environment variables, a `.env` file, or a `config.yaml`/`config.json`
  (precedence: env > .env > config file > defaults). A channel auto-enables when
  its credentials are present. Copy `.env.example` or `config.example.yaml` to
  get started. JSON config needs **no** extra dependencies; YAML needs PyYAML
  (`pip install nestfetch[config]`).
- **Test your setup** — `--notify-test` sends a test message to every configured
  channel so you can confirm it works before leaving it running.

```bash
cp .env.example .env                 # then fill in your tokens/webhook/SMTP
python scraper.py --notify-test      # confirm channels are wired up
python scraper.py --watch --interval 60 --task both   # scrape+check hourly, notify
python scraper.py --all --notify     # one-off full scrape + notify on new games
python scraper.py --check-links --notify              # notify on newly-dead links
```

Pure standard library for Telegram/Discord/email/JSON — the only optional add-on
is PyYAML if you prefer YAML config. New offline tests cover settings loading,
the notifier (with fake transports), and the scheduler.

## What's New in v4.2 — Performance & quality (Phase 3)

Under-the-hood upgrades that make big scrapes faster, gentler, and safer to ship:

- **Optional async fetching** — pass `--async` to fetch game detail pages
  concurrently (needs `aiohttp`; install with `pip install nestfetch[async]`).
  If `aiohttp` isn't installed, NESTfetch transparently falls back to its
  threaded client, so nothing breaks.
- **Smart retries** — automatic exponential backoff with jitter on transient
  errors (`429/500/502/503/504`), and it honours the server's `Retry-After`
  header. `404`s are never retried.
- **Polite per-host rate limiting** — `--rate-limit <seconds>` enforces a minimum
  gap between requests to the *same* host, so you don't hammer a mirror.
- **On-disk HTTP caching** — `--cache` reuses recent responses (TTL-based) so
  re-runs and interrupted scrapes don't re-download everything.
- **Test suite (pytest)** — offline unit tests for the HTTP client, async
  fetcher, engine, exporters, database, and link resolver. Run with `pytest`
  (`pip install nestfetch[dev]`).
- **Packaging** — `pip install .` now installs a `nestfetch` command
  (see `pyproject.toml`).

```bash
python scraper.py --all --async --cache --rate-limit 1.0   # fast + polite + cached
pip install .            # then just:  nestfetch --all
pip install nestfetch[async,dev]                            # extras
pytest                                                     # run the test suite
```

## What's New in v4.1 — Database & history (Phase 2)

Every scrape is now saved to a local **SQLite database** (`output/nestfetch.db`)
alongside the usual CSV/JSON, unlocking history and change tracking:

- **Run diffing** — after each scrape NESTfetch tells you what's **new**,
  **changed**, or **removed** since last time. (Removed detection only kicks in
  on a full-site scrape, so a keyword search never wrongly flags games as gone.)
- **Link-health history** — link-check results are stored per URL, and NESTfetch
  tracks **when a link first went dead**, how long it's been dead, and when it
  was last alive. A recovered link resets its dead marker.
- **Export from the database** anytime, no re-scrape needed.

```bash
python scraper.py --history            # recent runs + dead-link snapshot
python scraper.py --db-export -o csv   # rebuild CSV/JSON from the database
python scraper.py --all --no-db        # scrape without touching the database
python scraper.py --db mydata.db ...   # use a custom database file
```

Schema: `scrape_runs`, `games`, `mirrors`, `link_checks`. Pure standard-library
`sqlite3` — no new dependencies. The database lives in `output/` (git-ignored).

## What's New in v4.0 — Multi-site foundation (Phase 1)

The core has been refactored from a single-site scraper into a **pluggable
multi-site architecture**. The scraping engine no longer knows anything about
any specific website — it is driven entirely by a **`SiteAdapter`**.

```
sites/
  base.py        # SiteAdapter — the contract every site must implement
  registry.py    # the list of supported sites (+ default)
  switchroms.py  # switchroms.io adapter (migrated from the old code)
```

**Adding a new site = writing one file** in `sites/` and registering it — no
engine changes needed. Each scraped record now also carries its provenance:
`Source Site`, `Platform`, and `Category` columns (in both CSV and JSON).

New CLI:
```bash
python scraper.py --list-sites                 # show all supported sites
python scraper.py --site switchroms --all      # scrape a specific site
```
Interactive mode now asks which site to target first. Everything else
(scraping, filters, Excel-friendly CSV/JSON, the link checker) works exactly as
before — this phase is a foundation, not a behaviour change.

### 🔗 Shortener & ad-gate link resolver

Some download links on these sites are wrapped in URL shorteners or ad-gate
pages (ouo.io, exe.io, gplinks, linkvertise, bit.ly, ...) that show an ad
before reaching the real host. The link checker now **detects and unwraps** them:

- classifies every link as `DIRECT`, `SHORTENER`, `AD_GATE`, or `UNKNOWN`;
- best-effort unwrap by following redirects + embedded `?url=`/base64 targets +
  `<meta refresh>` + links to known direct hosts, to reveal the true destination;
- adds two columns to the report — **Link Type** and **Resolved Link** — and
  validates the *resolved* URL so ACTIVE/DEAD reflects the real file host.

Domain lists live in `config.py` (`SHORTENER_DOMAINS`, `AD_GATE_DOMAINS`,
`DIRECT_HOST_DOMAINS`) — extend them anytime. Toggle with `RESOLVE_LINKS_DEFAULT`.

**Tough ad-gates (timer + JavaScript).** Gates like linkvertise or modern
ouo.io/gplinks build the real link with JS after a countdown, so the lightweight
methods above can't see it. For these there's an optional **headless-browser
fallback** (Playwright) that waits out the timer and clicks through:

    pip install playwright && python -m playwright install chromium

Then set `RESOLVE_USE_BROWSER_FALLBACK = True` in `config.py`. It's off by
default because it needs the extra browser download and is slower; when off (or
if Playwright isn't installed) those links are simply flagged as unresolved so
you can open them manually.

> ⚠️ Unwrapping links may conflict with a shortener's Terms of Service. Use
> responsibly and only on links you're allowed to access.

> Roadmap for the remaining phases (database & history, performance/async, tests,
> automation & notifications, UI, and more sites) lives in `ROADMAP.md`.

## What's New in v3.3

### 📋 Rekap link aktif (active-only split + recap)

Selain report lengkap, link checker sekarang otomatis **memisahkan hasilnya** biar gampang direkap. Sekali jalan menghasilkan 3 file di folder `output/`:

| File | Isi |
|------|-----|
| `link_check_report.csv` | Semua baris + status (ACTIVE / DEAD / UNKNOWN). |
| `link_check_active.csv` | **Hanya baris dengan link ACTIVE** — tinggal pakai, sudah bersih dari link mati/unknown. |
| `link_check_recap.txt` | Ringkasan: jumlah link aktif/mati/unknown, jumlah judul game yang punya link aktif, plus **daftar judulnya**. |

Catatan: satu judul game bisa punya beberapa mirror. Di hitungan "judul game dengan link aktif", judul yang sama **dihitung sekali** (unik). Di akhir run, ringkasan + daftar judul game aktif juga langsung tampil di terminal.

## What's New in v3.2

### 🔗 Link Checker (dead / expired link validator)

Setelah scraping, banyak link download bisa kadaluarsa atau filenya sudah dihapus dari hoster. Fitur baru ini membaca CSV hasil scraping dan memeriksa setiap link, lalu menandai statusnya:

| Status | Arti |
|--------|------|
| **ACTIVE** | Link hidup — file masih tersedia. |
| **DEAD** | Link mati / kadaluarsa — HTTP 404/410, atau halaman host menampilkan pesan "Invalid or Deleted File", "file has been deleted", dll. |
| **UNKNOWN** | Tidak bisa dipastikan — diblokir anti-bot (403), timeout, error jaringan, atau tidak ada link untuk dicek. |

**Kenapa tidak cukup cek HTTP status saja?** Sebagian besar hoster (Mediafire, 1fichier, Terabox, dsb.) tetap mengembalikan HTTP 200 untuk file yang sudah dihapus, tapi menampilkan pesan "deleted" di HTML-nya. Jadi checker memeriksa **status code + penanda teks khusus per-host**.

Hasilnya ditulis ke folder `output/` — report lengkap (`link_check_report.csv`) berisi salinan CSV asli plus 4 kolom baru: `Link Status`, `HTTP Code`, `Check Detail`, `Checked At`. Selain itu otomatis dibuat `link_check_active.csv` (khusus link aktif) dan `link_check_recap.txt` (rekap + daftar judul game aktif). Buka di Excel lalu filter kolom `Link Status = DEAD` untuk melihat semua link kadaluarsa.

**Cara pakai:**
```bash
# Interaktif: pilih menu opsi [4]
python scraper.py

# CLI: cek CSV default (output/switch_games.csv)
python scraper.py --check-links

# CLI: cek CSV tertentu, 20 worker, simpan report ke lokasi custom
python scraper.py --check-links path/ke/data.csv --workers 20 --check-output report.csv
```

## What's New in v3.1

### ✨ New Features (from v3.0)

| Feature | Description |
|---------|-------------|
| **Opsi 3: Scrape ALL games** | Mode baru yang auto-paginate melalui seluruh halaman website sampai tidak ada game lagi. Tidak perlu input jumlah halaman manual. |
| **CSV Excel-friendly** | CSV ditulis dengan UTF-8 BOM (`utf-8-sig`) + tab delimiter (`excel-tab` dialect). Saat dibuka di Excel, kolom langsung terpisah rapi dan karakter khusus (é, —, ’) terbaca benar tanpa garbling. |
| **Folder output terpisah** | Semua hasil scraping (CSV, JSON, log) masuk ke folder `output/` yang dibuat otomatis. |

### Full Upgrade History (v2.0 → v3.1)

| Area | v2.0 (Original) | v3.1 (Upgraded) |
|------|-----------------|-----------------|
| **Architecture** | Single 350-line file | 8 modular files with clear separation of concerns |
| **Concurrency** | Sequential (1 game at a time) | Thread pool (configurable workers, default 5) |
| **Logging** | `print()` statements | Python `logging` module → coloured console + file log |
| **CLI** | Interactive menu only | Full `argparse` CLI + interactive fallback |
| **Error handling** | Basic retry, silent on parse errors | Structured retry + backoff, 404 short-circuit, exception logging |
| **Data models** | Raw dicts | Typed dataclasses (`Game`, `Mirror`) |
| **Config** | Hardcoded constants | Central `config.py` file |
| **Testing** | Untestable (network in parsers) | Pure parser functions (no network calls) → unit-testable |
| **Output** | Flat files in CWD | Organized `output/` directory |
| **CSV encoding** | Plain UTF-8 (garbled in Excel) | UTF-8 BOM + tab delimiter → rapi di Excel |
| **Scrape mode** | Homepage / Search only | Homepage / Search / **Scrape ALL** (auto-paginate) |
| **Documentation** | None | Full README + inline docstrings |

## Project Structure

```
switchroms-scraper/
├── scraper.py          # Main entry point
├── cli.py              # Argparse CLI + interactive menu
├── config.py           # All configuration constants
├── logger.py           # Logging setup (console + file)
├── models.py           # Dataclass models (Game, Mirror)
├── http_client.py      # HTTP client with retry/backoff
├── parsers.py          # Pure BeautifulSoup parsing functions
├── engine.py           # Scraper orchestration + concurrency + auto-paginate
├── exporters.py        # JSON / Excel-friendly CSV export
├── link_checker.py     # Dead / expired link validator (reads CSV → report CSV)
├── requirements.txt    # Python dependencies
├── README.md           # This file
└── output/             # Generated output files (auto-created)
    ├── switch_games.json
    ├── switch_games.csv   ← Buka di Excel, langsung rapi!
    └── scraper.log
```

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Interactive Mode (default)
```bash
python scraper.py
```

Menu yang muncul:
```
1. Select Action Mode:
  [1] Scrape latest games (Homepage)
  [2] Search specific games by keyword
  [3] Scrape ALL games on the entire website (auto-paginate)
```

### CLI Mode (for automation / scripting)

```bash
# Scrape homepage, 1 page, all formats, all hosters, both outputs
python scraper.py

# Search for "Mario", 3 pages, NSP only, Mediafire only, JSON only
python scraper.py --search Mario --pages 3 --format "NSP ROM" --hoster MEDIAFIRE --output json

# Scrape ALL games on the entire website, output CSV only
python scraper.py --all --output csv

# Full scrape with 5 pages and 10 concurrent workers
python scraper.py --pages 5 --workers 10 --output both

# Enable debug logging
python scraper.py --verbose
```

### CLI Flags

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--search` | `-s` | None | Search keyword |
| `--pages` | `-p` | 1 | Number of listing pages |
| `--all` | `-a` | False | Scrape ALL games (auto-paginate until empty) |
| `--format` | `-f` | ALL | ROM format filter (NSP ROM, XCI ROM, UPDATE, DLC, ALL) |
| `--hoster` | `-H` | ALL | File hoster filter |
| `--output` | `-o` | both | Output format (csv, json, both) |
| `--delay` | `-d` | 1.0 | Delay between requests (seconds) |
| `--workers` | `-w` | 5 | Concurrent thread pool size |
| `--verbose` | `-v` | False | Enable debug logging |
| `--check-links` | `-c` | None | Check links in a scraped CSV (optional path; default `output/switch_games.csv`) |
| `--check-output` | | None | Where to save the link-check report (default `output/link_check_report.csv`) |

## Output Format

### Link Check Report (`output/link_check_report.csv`)
Salinan CSV hasil scraping + 4 kolom tambahan: `Link Status` (ACTIVE/DEAD/UNKNOWN), `HTTP Code`, `Check Detail`, `Checked At`. Filter `Link Status = DEAD` di Excel untuk melihat link kadaluarsa.

### CSV (Excel-friendly)
- **Encoding**: UTF-8 with BOM (`utf-8-sig`) → Excel auto-detects encoding
- **Delimiter**: Tab (`excel-tab` dialect) → Excel auto-splits columns without Text Import Wizard
- **Columns**: Game Title, Front Page Info (Size/Version), Front Page Info (Genre/Publisher), Detail URL, ROM Format, File Size, Mirror Hoster, Redirect URL, Final Direct Link
- **Location**: `output/switch_games.csv`

### JSON (nested structure)
```json
[
  {
    "title": "Super Mario Party",
    "front_page_info": {
      "size_version": "1.1.1 + 2.78 GB",
      "publisher_genre": "Nintendo + Nintendo Switch Games"
    },
    "detail_url": "https://switchroms.io/...",
    "mirrors": [
      {
        "format": "NSP ROM",
        "size": "2.78 GB",
        "hoster": "Mediafire",
        "redirect_url": "https://switchroms.io/...?download=0",
        "final_link": "https://www.mediafire.com/..."
      }
    ]
  }
]
```

## Legal & Ethical Notice

This tool is for educational and research purposes only. Scraping websites may violate their Terms of Service. Always:
- Respect `robots.txt`
- Use reasonable delays between requests
- Do not redistribute copyrighted content
- Check local laws regarding ROM downloads
