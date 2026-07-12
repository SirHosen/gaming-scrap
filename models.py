#!/usr/bin/env python3
"""
Pydantic-style data models (using dataclasses for zero external deps).
These models enforce a consistent shape for every scraped record.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class Mirror:
    """A single download mirror for a game."""
    raw_text: str = ""
    format: str = "N/A"          # NSP ROM, XCI ROM, [UPDATE] NSP ROM, etc.
    size: str = "N/A"             # e.g. "2.78 GB"
    hoster: str = "Unknown"       # e.g. Mediafire, 1fichier
    redirect_url: str = ""        # intermediate ?download=X page
    final_link: str = "N/A"       # resolved direct link to file hoster

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Game:
    """A game entry with its metadata and list of mirrors."""
    title: str = "No Title"
    meta_size: str = "N/A"        # front-page size/version string
    meta_genre: str = "N/A"       # front-page genre/publisher string
    detail_url: str = ""          # game detail page URL
    mirrors: List[Mirror] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "front_page_info": {
                "size_version": self.meta_size,
                "publisher_genre": self.meta_genre,
            },
            "detail_url": self.detail_url,
            "mirrors": [m.to_dict() for m in self.mirrors],
        }
