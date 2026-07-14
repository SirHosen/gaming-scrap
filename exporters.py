#!/usr/bin/env python3
"""
Exporters — write scraped data to JSON and/or CSV.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List

from config import OUTPUT_DIR, JSON_FILENAME, CSV_FILENAME
from logger import log, Colours
from models import Game


CSV_HEADERS = [
    "Game Title",
    "Source Site",
    "Platform",
    "Category",
    "Front Page Info (Size/Version)",
    "Front Page Info (Genre/Publisher)",
    "Detail URL",
    "ROM Format",
    "File Size",
    "Mirror Hoster",
    "Redirect URL",
    "Final Direct Link",
]


def ensure_output_dir() -> Path:
    """Create the output directory if it doesn't exist."""
    out = Path(OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    return out


def export_json(games: List[Game]) -> Path:
    """Write games to a nested JSON file (preserving mirror structure)."""
    out_dir = ensure_output_dir()
    path = out_dir / JSON_FILENAME

    data = [g.to_dict() for g in games]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    log.info("%s✔%s JSON saved: %s", Colours.GREEN, Colours.RESET, path)
    return path


def export_csv(games: List[Game]) -> Path:
    """
    Write games to a flat CSV (one row per mirror).

    Uses UTF-8 BOM encoding so Excel correctly detects the encoding
    and renders special characters (é, —, etc.) without garbling.
    Uses tab as the delimiter so Excel auto-splits columns cleanly
    without needing the Text Import Wizard.
    """
    out_dir = ensure_output_dir()
    path = out_dir / CSV_FILENAME

    # Write with UTF-8 BOM (utf-8-sig) for Excel compatibility
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, dialect="excel-tab")
        writer.writerow(CSV_HEADERS)

        for game in games:
            for mirror in game.mirrors:
                writer.writerow([
                    game.title,
                    game.source_site,
                    game.platform,
                    game.category,
                    game.meta_size,
                    game.meta_genre,
                    game.detail_url,
                    mirror.format,
                    mirror.size,
                    mirror.hoster,
                    mirror.redirect_url,
                    mirror.final_link,
                ])

    log.info("%s✔%s CSV saved: %s", Colours.GREEN, Colours.RESET, path)
    return path


def export_data(games: List[Game], fmt: str = "both") -> List[Path]:
    """
    Export data in the requested format.
    fmt: 'csv', 'json', or 'both'.
    Returns list of paths written.
    """
    paths: List[Path] = []

    if fmt in ("json", "both"):
        paths.append(export_json(games))
    if fmt in ("csv", "both"):
        paths.append(export_csv(games))

    return paths
