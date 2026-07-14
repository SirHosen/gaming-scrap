#!/usr/bin/env python3
"""
Site registry — the single place that knows which sites NESTfetch supports.

To add a new site:
    1. Create `sites/<yoursite>.py` with a `SiteAdapter` subclass.
    2. Import it here and add it to `_ADAPTER_CLASSES`.
That's it — the engine, CLI, and exporters pick it up automatically.
"""

from __future__ import annotations

from typing import Dict, List, Type

from sites.base import SiteAdapter, SiteMeta
from sites.switchroms import SwitchRomsAdapter


# Register every available adapter class here.
_ADAPTER_CLASSES: List[Type[SiteAdapter]] = [
    SwitchRomsAdapter,
    # e.g. WindowsGamesAdapter, EmulatorZoneAdapter, LinuxGamesAdapter, ...
]

#: Default site used when the user doesn't pass --site.
DEFAULT_SITE: str = SwitchRomsAdapter.meta.name

_BY_NAME: Dict[str, Type[SiteAdapter]] = {
    cls.meta.name: cls for cls in _ADAPTER_CLASSES
}


def available_sites() -> List[SiteMeta]:
    """Return the SiteMeta for every registered adapter."""
    return [cls.meta for cls in _ADAPTER_CLASSES]


def site_names() -> List[str]:
    """Return the list of registered site slugs."""
    return list(_BY_NAME.keys())


def get_adapter(name: str) -> SiteAdapter:
    """Instantiate the adapter registered under `name` (case-insensitive)."""
    key = (name or "").strip().lower()
    cls = _BY_NAME.get(key)
    if cls is None:
        valid = ", ".join(_BY_NAME.keys())
        raise ValueError(f"Unknown site '{name}'. Available sites: {valid}")
    return cls()
