#!/usr/bin/env python3
"""Offline tests for settings.load_settings (Phase 4).

Every call passes explicit `environ`, `env_file`, and `config_path` so the
loader never scans the real working directory.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from nestfetch import settings as st

# A path that is guaranteed not to exist -> loader treats it as "no file".
NOFILE_JSON = os.path.join(tempfile.gettempdir(), "nestfetch_nope_xyz.json")
NOFILE_ENV = os.path.join(tempfile.gettempdir(), "nestfetch_nope_xyz.env")


def test_env_precedence():
    environ = {
        "NESTFETCH_TELEGRAM_TOKEN": "abc123",
        "NESTFETCH_TELEGRAM_CHAT_ID": "999",
    }
    s = st.load_settings(NOFILE_JSON, environ=environ, env_file=NOFILE_ENV)
    assert s.telegram.token == "abc123", s.telegram.token
    assert s.telegram.chat_id == "999"
    assert s.telegram.ready is True
    assert s.telegram.active is True  # auto-enabled when creds present
    assert s.any_channel_configured() is True
    print("\u2714 test_env_precedence")


def test_env_overrides_config():
    fd, cfg = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(cfg, "w", encoding="utf-8") as fh:
        json.dump({"telegram": {"token": "from_config", "chat_id": "111"}}, fh)
    try:
        environ = {"NESTFETCH_TELEGRAM_TOKEN": "from_env"}
        s = st.load_settings(cfg, environ=environ, env_file=NOFILE_ENV)
        # env wins over the config file for token; chat_id falls back to config
        assert s.telegram.token == "from_env", s.telegram.token
        assert s.telegram.chat_id == "111", s.telegram.chat_id
    finally:
        os.remove(cfg)
    print("\u2714 test_env_overrides_config")


def test_env_file_parse():
    fd, envf = tempfile.mkstemp(suffix=".env")
    os.close(fd)
    with open(envf, "w", encoding="utf-8") as fh:
        fh.write("# a comment line\n")
        fh.write('export NESTFETCH_DISCORD_WEBHOOK_URL="https://example.com/hook"\n')
    try:
        s = st.load_settings(NOFILE_JSON, environ={}, env_file=envf)
        assert s.discord.webhook_url == "https://example.com/hook", s.discord.webhook_url
        assert s.discord.active is True
    finally:
        os.remove(envf)
    print("\u2714 test_env_file_parse")


def test_json_config_and_list():
    fd, cfg = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(cfg, "w", encoding="utf-8") as fh:
        json.dump({
            "email": {
                "smtp_host": "smtp.example.com",
                "from_addr": "me@example.com",
                "to": ["a@x.com", "b@x.com"],
            },
        }, fh)
    try:
        s = st.load_settings(cfg, environ={}, env_file=NOFILE_ENV)
        assert s.email.smtp_host == "smtp.example.com"
        assert s.email.to_addrs == ["a@x.com", "b@x.com"], s.email.to_addrs
        assert s.email.active is True
    finally:
        os.remove(cfg)
    print("\u2714 test_json_config_and_list")


def test_list_parsing_from_string():
    environ = {
        "NESTFETCH_EMAIL_SMTP_HOST": "smtp.example.com",
        "NESTFETCH_EMAIL_TO": "a@x.com, b@x.com; c@x.com",
    }
    s = st.load_settings(NOFILE_JSON, environ=environ, env_file=NOFILE_ENV)
    assert s.email.to_addrs == ["a@x.com", "b@x.com", "c@x.com"], s.email.to_addrs
    print("\u2714 test_list_parsing_from_string")


def test_defaults_disabled():
    s = st.load_settings(NOFILE_JSON, environ={}, env_file=NOFILE_ENV)
    assert s.any_channel_configured() is False
    assert s.notify.on_new_games is True
    assert s.notify.on_dead_links is True
    assert s.schedule.interval_minutes == 60.0
    print("\u2714 test_defaults_disabled")


def run():
    test_env_precedence()
    test_env_overrides_config()
    test_env_file_parse()
    test_json_config_and_list()
    test_list_parsing_from_string()
    test_defaults_disabled()
    print("\nAll settings tests passed.")


if __name__ == "__main__":
    run()
