# SwitchRoms Scraper v3.0

A professional, modular Nintendo Switch ROM metadata scraper for `switchroms.io`.

## What's New in v3.0 (Upgrade from v2.0)

| Area | v2.0 (Original) | v3.0 (Upgraded) |
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
├── engine.py           # Scraper orchestration + concurrency
├── exporters.py        # JSON / CSV export
├── requirements.txt    # Python dependencies
└── output/             # Generated output files
    ├── switch_games.json
    ├── switch_games.csv
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

### CLI Mode (for automation / scripting)
```bash
# Scrape homepage, 1 page, all formats, all hosters, both outputs
python scraper.py

# Search for "Mario", 3 pages, NSP only, Mediafire only, JSON only
python scraper.py --search Mario --pages 3 --format "NSP ROM" --hoster MEDIAFIRE --output json

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
| `--format` | `-f` | ALL | ROM format filter (NSP ROM, XCI ROM, UPDATE, DLC, ALL) |
| `--hoster` | `-H` | ALL | File hoster filter |
| `--output` | `-o` | both | Output format (csv, json, both) |
| `--delay` | `-d` | 1.0 | Delay between requests (seconds) |
| `--workers` | `-w` | 5 | Concurrent thread pool size |
| `--verbose` | `-v` | False | Enable debug logging |

## Output Format

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

### CSV (flat, one row per mirror)
Columns: Game Title, Front Page Info (Size/Version), Front Page Info (Genre/Publisher), Detail URL, ROM Format, File Size, Mirror Hoster, Redirect URL, Final Direct Link

## Legal & Ethical Notice

This tool is for educational and research purposes only. Scraping websites may violate their Terms of Service. Always:
- Respect `robots.txt`
- Use reasonable delays between requests
- Do not redistribute copyrighted content
- Check local laws regarding ROM downloads
