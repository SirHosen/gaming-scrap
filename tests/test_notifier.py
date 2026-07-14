#!/usr/bin/env python3
"""Offline tests for notifier.Notifier (Phase 4).

Network transports (_http_post / _smtp_factory) are monkeypatched with fakes so
nothing ever touches the network. Settings are built directly (no files/env).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import notifier as nf
from settings import (
    Settings, TelegramSettings, DiscordSettings, EmailSettings, NotifySettings,
)


class _Summary:
    """Stand-in for database.RunSummary (only the fields notifier reads)."""
    def __init__(self, new, site, new_titles):
        self.new = new
        self.site = site
        self.new_titles = new_titles


def _telegram_settings():
    return Settings(telegram=TelegramSettings(enabled=True, token="T", chat_id="C"))


def _discord_settings():
    return Settings(discord=DiscordSettings(enabled=True, webhook_url="https://d/hook"))


def _email_settings():
    return Settings(email=EmailSettings(
        enabled=True, smtp_host="smtp.local", smtp_port=25,
        from_addr="me@x.com", to_addrs=["a@x.com"], use_tls=False,
    ))


class _FakeSMTP:
    instances = []

    def __init__(self):
        self.logged_in = False
        self.sent = []
        self.quit_called = False
        _FakeSMTP.instances.append(self)

    def login(self, user, pw):
        self.logged_in = (user, pw)

    def send_message(self, msg):
        self.sent.append(msg)

    def quit(self):
        self.quit_called = True


def _patch(**kw):
    """Save originals, apply patches; return a restore() callable."""
    saved = {k: getattr(nf, k) for k in kw}
    for k, v in kw.items():
        setattr(nf, k, v)
    def restore():
        for k, v in saved.items():
            setattr(nf, k, v)
    return restore


def test_enabled_channels():
    n = nf.Notifier(Settings(
        telegram=TelegramSettings(enabled=True, token="T", chat_id="C"),
        discord=DiscordSettings(enabled=True, webhook_url="https://d/h"),
    ))
    assert n.enabled_channels() == ["telegram", "discord"], n.enabled_channels()
    # not-ready channel (missing chat_id) must not count
    n2 = nf.Notifier(Settings(telegram=TelegramSettings(enabled=True, token="T")))
    assert n2.enabled_channels() == [], n2.enabled_channels()
    print("\u2714 test_enabled_channels")


def test_telegram_send():
    calls = []
    def fake_post(url, data=None, headers=None, timeout=15):
        calls.append((url, data, headers))
        return 200, "ok"
    restore = _patch(_http_post=fake_post)
    try:
        results = nf.Notifier(_telegram_settings()).send("Subj", "Body")
        assert len(results) == 1 and results[0].ok, results
        assert results[0].channel == "telegram"
        url = calls[0][0]
        assert url == "https://api.telegram.org/botT/sendMessage", url
        assert b"chat_id=C" in calls[0][1]
    finally:
        restore()
    print("\u2714 test_telegram_send")


def test_discord_send():
    calls = []
    def fake_post(url, data=None, headers=None, timeout=15):
        calls.append((url, data, headers))
        return 204, ""
    restore = _patch(_http_post=fake_post)
    try:
        results = nf.Notifier(_discord_settings()).send("Subj", "Body")
        assert len(results) == 1 and results[0].ok, results
        assert results[0].channel == "discord"
        assert calls[0][0] == "https://d/hook"
        assert b"content" in calls[0][1]
    finally:
        restore()
    print("\u2714 test_discord_send")


def test_email_send():
    _FakeSMTP.instances.clear()
    def fake_factory(host, port, use_tls, timeout=20):
        assert host == "smtp.local" and port == 25 and use_tls is False
        return _FakeSMTP()
    restore = _patch(_smtp_factory=fake_factory)
    try:
        results = nf.Notifier(_email_settings()).send("Subj", "Body")
        assert len(results) == 1 and results[0].ok, results
        assert results[0].channel == "email"
        smtp = _FakeSMTP.instances[-1]
        assert len(smtp.sent) == 1
        assert smtp.quit_called is True
    finally:
        restore()
    print("\u2714 test_email_send")


def test_notify_new_games():
    posted = []
    def fake_post(url, data=None, headers=None, timeout=15):
        posted.append(data)
        return 200, "ok"
    restore = _patch(_http_post=fake_post)
    try:
        summary = _Summary(new=2, site="switchroms", new_titles=["Game A", "Game B"])
        results = nf.Notifier(_telegram_settings()).notify_new_games(summary)
        assert len(results) == 1 and results[0].ok
        assert len(posted) == 1
        # respects the on_new_games toggle
        off = Settings(telegram=TelegramSettings(enabled=True, token="T", chat_id="C"),
                       notify=NotifySettings(on_new_games=False))
        assert nf.Notifier(off).notify_new_games(summary) == []
        # zero new games -> nothing sent
        assert nf.Notifier(_telegram_settings()).notify_new_games(_Summary(0, "s", [])) == []
    finally:
        restore()
    print("\u2714 test_notify_new_games")


def test_notify_dead_links():
    posted = []
    def fake_post(url, data=None, headers=None, timeout=15):
        posted.append(data)
        return 200, "ok"
    restore = _patch(_http_post=fake_post)
    try:
        stats = {"active": 5, "dead": 3, "newly_dead": 2,
                 "newly_dead_urls": ["http://x/1", "http://x/2"]}
        results = nf.Notifier(_discord_settings()).notify_dead_links(stats, site="switchroms")
        assert len(results) == 1 and results[0].ok
        assert len(posted) == 1
        # no newly-dead links -> nothing sent
        assert nf.Notifier(_discord_settings()).notify_dead_links(
            {"newly_dead": 0}) == []
        # respects the on_dead_links toggle
        off = Settings(discord=DiscordSettings(enabled=True, webhook_url="https://d/h"),
                       notify=NotifySettings(on_dead_links=False))
        assert nf.Notifier(off).notify_dead_links(stats) == []
    finally:
        restore()
    print("\u2714 test_notify_dead_links")


def test_send_failure_reported():
    def fake_post(url, data=None, headers=None, timeout=15):
        return 500, "server error"
    restore = _patch(_http_post=fake_post)
    try:
        results = nf.Notifier(_telegram_settings()).send("S", "B")
        assert len(results) == 1 and results[0].ok is False
    finally:
        restore()
    print("\u2714 test_send_failure_reported")


def run():
    test_enabled_channels()
    test_telegram_send()
    test_discord_send()
    test_email_send()
    test_notify_new_games()
    test_notify_dead_links()
    test_send_failure_reported()
    print("\nAll notifier tests passed.")


if __name__ == "__main__":
    run()
