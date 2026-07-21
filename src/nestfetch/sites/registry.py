#!/usr/bin/env python3
"""
Site registry — the single place that knows which sites NESTfetch supports.

NESTfetch supports two tiers of sites, both surfaced through this registry:

  1. **Config-driven sites (preferred)** — drop a JSON file in `sites/configs/`.
     It is auto-loaded and served by `GenericConfigAdapter`, no code needed.
     See `sites/configs/README.md` for the schema.

  2. **Python adapter sites (escape hatch)** — for sites too weird for config
     (heavy JS, exotic ad-gates, bespoke title cleaning). Create
     `sites/<yoursite>.py` with a `SiteAdapter` subclass and add it to
     `_PY_ADAPTER_CLASSES` below. `switchroms` is the reference example.

If a Python adapter and a JSON config share the same name, the Python adapter
wins (it is the deliberate override).

The engine, CLI, and exporters pick up every registered site automatically.
"""

from __future__ import annotations

from typing import Dict, List, Type

from nestfetch.logger import log
from nestfetch.sites.base import SiteAdapter, SiteMeta
from nestfetch.sites.switchroms import SwitchRomsAdapter
from nestfetch.sites.config_adapter import (
    GenericConfigAdapter,
    config_meta,
    discover_configs,
)


# ── Tier 2: hand-written Python adapters ───────────────────────────
_PY_ADAPTER_CLASSES: List[Type[SiteAdapter]] = [
    SwitchRomsAdapter,
    # e.g. add bespoke adapters here when config isn't enough.
]

#: Default site used when the user doesn't pass --site.
DEFAULT_SITE: str = SwitchRomsAdapter.meta.name

_PY_BY_NAME: Dict[str, Type[SiteAdapter]] = {
    cls.meta.name.lower(): cls for cls in _PY_ADAPTER_CLASSES
}


# ── Tier 1: config-driven sites (auto-loaded from sites/configs/*.json) ──
def _load_configs() -> List[dict]:
    try:
        return discover_configs()
    except Exception as exc:  # never let a bad config break the whole CLI
        log.warning("Failed to load site configs: %s", exc)
        return []


_CONFIGS: List[dict] = _load_configs()
# Python adapters override configs of the same name.
_CONFIG_BY_NAME: Dict[str, dict] = {
    c["name"]: c for c in _CONFIGS if c["name"] not in _PY_BY_NAME
}


def available_sites() -> List[SiteMeta]:
    """Return the SiteMeta for every registered adapter (Python + config)."""
    metas: List[SiteMeta] = [cls.meta for cls in _PY_ADAPTER_CLASSES]
    metas += [config_meta(c) for c in _CONFIG_BY_NAME.values()]
    return metas


def site_names() -> List[str]:
    """Return the list of registered site slugs."""
    return [m.name for m in available_sites()]


def get_adapter(name: str) -> SiteAdapter:
    """Instantiate the adapter registered under `name` (case-insensitive)."""
    key = (name or "").strip().lower()
    if key in _PY_BY_NAME:
        return _PY_BY_NAME[key]()
    if key in _CONFIG_BY_NAME:
        return GenericConfigAdapter(_CONFIG_BY_NAME[key])
    valid = ", ".join(site_names())
    raise ValueError(f"Unknown site '{name}'. Available sites: {valid}")
