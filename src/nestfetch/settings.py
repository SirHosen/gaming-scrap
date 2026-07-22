#!/usr/bin/env python3
"""
settings.py — user settings & secrets loader (Phase 4).

Keeps tokens / webhooks / SMTP credentials OUT of the source code and out of
git. Values are resolved in this order of precedence (first match wins):

  1. Environment variables   (NESTFETCH_TELEGRAM_TOKEN, ...)
  2. A .env file             (KEY=VALUE lines, same NESTFETCH_* keys)
  3. A config.yaml / .yml / config.json file (nested structure)
  4. Built-in defaults       (every channel disabled)

No third-party dependency is required:
  * .env  → parsed by hand
  * .json → stdlib json
  * .yaml → only read if PyYAML happens to be installed (optional)

A channel auto-enables when its required credentials are present, unless you
explicitly set its `enabled` flag.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # structural defaults live in config.py, but settings.py must not hard-depend
    from nestfetch.config import (
        CONFIG_FILE_CANDIDATES, ENV_FILENAME,
        SCHEDULE_DEFAULT_INTERVAL_MIN, SCHEDULE_DEFAULT_TASK,
    )
except Exception:  # pragma: no cover - fallback if config import order changes
    CONFIG_FILE_CANDIDATES = ("config.yaml", "config.yml", "config.json")
    ENV_FILENAME = ".env"
    SCHEDULE_DEFAULT_INTERVAL_MIN = 60.0
    SCHEDULE_DEFAULT_TASK = "both"


# ── Casting helpers ───────────────────────
def _as_bool(val: Any, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("1", "true", "yes", "on", "y")


def _as_int(val: Any, default: int) -> int:
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return default


def _as_float(val: Any, default: float) -> float:
    try:
        return float(str(val).strip())
    except (TypeError, ValueError):
        return default


def _as_list(val: Any) -> List[str]:
    if not val:
        return []
    if isinstance(val, (list, tuple)):
        return [str(x).strip() for x in val if str(x).strip()]
    return [p.strip() for p in str(val).replace(";", ",").split(",") if p.strip()]


# ── File readers ────────────────────
def _read_env_file(path: Optional[str]) -> Dict[str, str]:
    """Parse a simple KEY=VALUE .env file (comments with #, optional quotes)."""
    out: Dict[str, str] = {}
    if not path:
        return out
    p = Path(path)
    if not p.exists():
        return out
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def _read_config_file(path: Optional[str]) -> Dict[str, Any]:
    """Read a nested config from .json (always) or .yaml/.yml (if PyYAML present)."""
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8", errors="ignore")
    suffix = p.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # optional dependency
        except Exception:
            return {}
        try:
            data = yaml.safe_load(text)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _find_in_cwd(candidates) -> Optional[str]:
    for name in candidates:
        p = Path(name)
        if p.exists():
            return str(p)
    return None


class _Source:
    """Layered lookup: environment > .env flat file > nested config file."""

    def __init__(self, env: Dict[str, str], flat: Dict[str, str], nested: Dict[str, Any]):
        self.env = env
        self.flat = flat
        self.nested = nested

    def get(self, env_key: str, path: List[str]) -> Any:
        if env_key in self.env:
            return self.env[env_key]
        if env_key in self.flat:
            return self.flat[env_key]
        node: Any = self.nested
        for part in path:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return None
        return None if isinstance(node, dict) else node


# ── Settings dataclasses ─────────────────
@dataclass
class TelegramSettings:
    enabled: bool = False
    token: str = ""
    chat_id: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.token and self.chat_id)

    @property
    def active(self) -> bool:
        return self.enabled and self.ready


@dataclass
class DiscordSettings:
    enabled: bool = False
    webhook_url: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.webhook_url)

    @property
    def active(self) -> bool:
        return self.enabled and self.ready


@dataclass
class EmailSettings:
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = ""
    to_addrs: List[str] = field(default_factory=list)
    use_tls: bool = True

    @property
    def ready(self) -> bool:
        return bool(self.smtp_host and self.to_addrs)

    @property
    def active(self) -> bool:
        return self.enabled and self.ready


@dataclass
class NotifySettings:
    on_new_games: bool = True
    on_dead_links: bool = True


@dataclass
class ScheduleSettings:
    task: str = "both"                # scrape | check | both
    interval_minutes: float = 60.0


@dataclass
class Settings:
    telegram: TelegramSettings = field(default_factory=TelegramSettings)
    discord: DiscordSettings = field(default_factory=DiscordSettings)
    email: EmailSettings = field(default_factory=EmailSettings)
    notify: NotifySettings = field(default_factory=NotifySettings)
    schedule: ScheduleSettings = field(default_factory=ScheduleSettings)
    source_files: List[str] = field(default_factory=list)

    def any_channel_configured(self) -> bool:
        return self.telegram.active or self.discord.active or self.email.active


# ── Loader ──────────────────────
def load_settings(
    config_path: Optional[str] = None,
    *,
    environ: Optional[Dict[str, str]] = None,
    env_file: Optional[str] = None,
) -> Settings:
    """Build a Settings object from env vars, a .env file, and a config file.

    Pass `config_path` / `env_file` explicitly (e.g. in tests) to avoid scanning
    the current working directory.
    """
    environ = dict(os.environ if environ is None else environ)
    env_path = env_file if env_file is not None else _find_in_cwd((ENV_FILENAME,))
    cfg_path = config_path if config_path is not None else _find_in_cwd(CONFIG_FILE_CANDIDATES)

    flat = _read_env_file(env_path)
    nested = _read_config_file(cfg_path)
    src = _Source(environ, flat, nested)

    # ── Telegram ──
    tg_token = str(src.get("NESTFETCH_TELEGRAM_TOKEN", ["telegram", "token"]) or "").strip()
    tg_chat = str(src.get("NESTFETCH_TELEGRAM_CHAT_ID", ["telegram", "chat_id"]) or "").strip()
    telegram = TelegramSettings(
        enabled=_as_bool(src.get("NESTFETCH_TELEGRAM_ENABLED", ["telegram", "enabled"]),
                         default=bool(tg_token and tg_chat)),
        token=tg_token, chat_id=tg_chat,
    )

    # ── Discord ──
    dc_hook = str(src.get("NESTFETCH_DISCORD_WEBHOOK_URL", ["discord", "webhook_url"]) or "").strip()
    discord = DiscordSettings(
        enabled=_as_bool(src.get("NESTFETCH_DISCORD_ENABLED", ["discord", "enabled"]),
                         default=bool(dc_hook)),
        webhook_url=dc_hook,
    )

    # ── Email ──
    em_host = str(src.get("NESTFETCH_EMAIL_SMTP_HOST", ["email", "smtp_host"]) or "").strip()
    em_to = _as_list(src.get("NESTFETCH_EMAIL_TO", ["email", "to"]))
    email = EmailSettings(
        enabled=_as_bool(src.get("NESTFETCH_EMAIL_ENABLED", ["email", "enabled"]),
                         default=bool(em_host and em_to)),
        smtp_host=em_host,
        smtp_port=_as_int(src.get("NESTFETCH_EMAIL_SMTP_PORT", ["email", "smtp_port"]), 587),
        username=str(src.get("NESTFETCH_EMAIL_USERNAME", ["email", "username"]) or "").strip(),
        password=str(src.get("NESTFETCH_EMAIL_PASSWORD", ["email", "password"]) or ""),
        from_addr=str(src.get("NESTFETCH_EMAIL_FROM", ["email", "from_addr"]) or "").strip(),
        to_addrs=em_to,
        use_tls=_as_bool(src.get("NESTFETCH_EMAIL_USE_TLS", ["email", "use_tls"]), default=True),
    )

    # ── Notify toggles ──
    notify = NotifySettings(
        on_new_games=_as_bool(src.get("NESTFETCH_NOTIFY_ON_NEW_GAMES", ["notify", "on_new_games"]),
                              default=True),
        on_dead_links=_as_bool(src.get("NESTFETCH_NOTIFY_ON_DEAD_LINKS", ["notify", "on_dead_links"]),
                               default=True),
    )

    # ── Schedule ──
    schedule = ScheduleSettings(
        task=str(src.get("NESTFETCH_SCHEDULE_TASK", ["schedule", "task"]) or SCHEDULE_DEFAULT_TASK).strip().lower(),
        interval_minutes=_as_float(
            src.get("NESTFETCH_SCHEDULE_INTERVAL_MINUTES", ["schedule", "interval_minutes"]),
            SCHEDULE_DEFAULT_INTERVAL_MIN),
    )

    return Settings(
        telegram=telegram, discord=discord, email=email,
        notify=notify, schedule=schedule,
        source_files=[str(p) for p in (env_path, cfg_path) if p],
    )
