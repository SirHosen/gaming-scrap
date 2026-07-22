#!/usr/bin/env python3
"""
Exporters — write scraped data to JSON and/or CSV.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List, Optional, Dict

from nestfetch.config import OUTPUT_DIR
from nestfetch.logger import log, Colours
from nestfetch.models import Game


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


def ensure_output_dir(site_name: str = "default") -> Path:
    """Create the site-specific output directory if it doesn't exist."""
    out = Path(OUTPUT_DIR) / site_name
    out.mkdir(parents=True, exist_ok=True)
    return out


def _resolve_site_name(games: List[Game], site_name: Optional[str] = None) -> str:
    if site_name:
        return site_name
    if games and games[0].source_site:
        return games[0].source_site
    return "default"


def export_json(games: List[Game], site_name: Optional[str] = None) -> Path:
    """Write games to a nested JSON file under output/<site_name>/<site_name>.json."""
    resolved_site = _resolve_site_name(games, site_name)
    out_dir = ensure_output_dir(resolved_site)
    path = out_dir / f"{resolved_site}.json"

    data = [g.to_dict() for g in games]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    log.info("%s✔%s JSON saved: %s", Colours.GREEN, Colours.RESET, path)
    return path


def export_csv(games: List[Game], site_name: Optional[str] = None) -> Path:
    """
    Write games to a flat CSV under output/<site_name>/<site_name>.csv (one row per mirror).

    Uses UTF-8 BOM encoding so Excel correctly detects the encoding
    and renders special characters (é, —, etc.) without garbling.
    Uses tab as the delimiter so Excel auto-splits columns cleanly
    without needing the Text Import Wizard.
    """
    resolved_site = _resolve_site_name(games, site_name)
    out_dir = ensure_output_dir(resolved_site)
    path = out_dir / f"{resolved_site}.csv"

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


def export_data(
    games: List[Game],
    fmt: str = "both",
    site_name: Optional[str] = None,
) -> List[Path]:
    """
    Export data in the requested format.
    fmt: 'csv', 'json', or 'both'.
    site_name: optional explicit target website slug. If None, resolves from games.
    Returns list of paths written.
    """
    paths: List[Path] = []
    if not games:
        resolved_site = site_name or "default"
        if fmt in ("json", "both"):
            paths.append(export_json([], site_name=resolved_site))
        if fmt in ("csv", "both"):
            paths.append(export_csv([], site_name=resolved_site))
        return paths

    if site_name:
        groups: Dict[str, List[Game]] = {site_name: games}
    else:
        groups = {}
        for g in games:
            s_name = g.source_site or "default"
            groups.setdefault(s_name, []).append(g)

    for s_name, s_games in groups.items():
        if fmt in ("json", "both"):
            paths.append(export_json(s_games, site_name=s_name))
        if fmt in ("csv", "both"):
            paths.append(export_csv(s_games, site_name=s_name))

    return paths
