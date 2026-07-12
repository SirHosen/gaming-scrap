# SwitchRoms Scraper v3.1

A professional, modular Nintendo Switch ROM metadata scraper for `switchroms.io`.

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

## Output Format

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
