#!/usr/bin/env python3
"""
notifier.py — multi-channel notifications for NESTfetch (Phase 4).

Sends alerts to Telegram, Discord, and/or email when a scrape finds NEW games
or a link check finds NEWLY-DEAD links. Pure standard library:

  * Telegram / Discord → urllib.request (HTTPS POST to bot API / webhook)
  * Email              → smtplib + email.message

Every channel is optional and configured through settings.py (env / .env / yaml).
The network transports are module-level functions so tests can inject fakes and
run completely offline.
"""
from __future__ import annotations

import json
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import List, Optional, Tuple

from nestfetch.logger import log, Colours
from nestfetch.settings import Settings, load_settings


@dataclass
class NotifyResult:
    channel: str
    ok: bool
    detail: str = ""


# ── Injectable transports (tests replace these) ─────────
def _http_post(url: str, data: Optional[bytes] = None,
               headers: Optional[dict] = None, timeout: int = 15) -> Tuple[int, str]:
    """HTTPS POST helper returning (status_code, body_text). Uses stdlib urllib."""
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted URLs)
            return getattr(resp, "status", 200), resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "ignore")
    except Exception as exc:  # network errors, DNS, timeouts
        return 0, str(exc)


def _smtp_factory(host: str, port: int, use_tls: bool, timeout: int = 20):
    """Return a connected SMTP client. Overridable in tests."""
    client = smtplib.SMTP(host, port, timeout=timeout)
    if use_tls:
        client.ehlo()
        client.starttls(context=ssl.create_default_context())
        client.ehlo()
    return client


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Notifier:
    """Fan-out notifier across every configured channel."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings if settings is not None else load_settings()

    # ── Introspection ──
    def enabled_channels(self) -> List[str]:
        s = self.settings
        out = []
        if s.telegram.active:
            out.append("telegram")
        if s.discord.active:
            out.append("discord")
        if s.email.active:
            out.append("email")
        return out

    # ── Core send ──
    def send(self, subject: str, body: str) -> List[NotifyResult]:
        results: List[NotifyResult] = []
        if self.settings.telegram.active:
            results.append(self._send_telegram(subject, body))
        if self.settings.discord.active:
            results.append(self._send_discord(subject, body))
        if self.settings.email.active:
            results.append(self._send_email(subject, body))

        for r in results:
            if r.ok:
                log.info("%s✔ Notification sent via %s%s (%s)",
                         Colours.GREEN, r.channel, Colours.RESET, r.detail)
            else:
                log.warning("%s✖ Notification via %s failed:%s %s",
                            Colours.YELLOW, r.channel, Colours.RESET, r.detail)
        return results

    # ── Event helpers ──
    def notify_new_games(self, summary, site: Optional[str] = None) -> List[NotifyResult]:
        """Notify about newly-discovered games from a scrape RunSummary."""
        if not self.settings.notify.on_new_games:
            return []
        if not summary or not getattr(summary, "new", 0):
            return []
        site_name = site or getattr(summary, "site", "") or "the site"
        titles = list(getattr(summary, "new_titles", []))[:25]
        lines = [f"• {t}" for t in titles if t]
        remaining = summary.new - len(titles)
        if remaining > 0:
            lines.append(f"…and {remaining} more")
        body = f"{summary.new} new game(s) found on {site_name}.\n\n" + "\n".join(lines)
        return self.send(f"{summary.new} new game(s) on {site_name}", body)

    def notify_dead_links(self, stats, site: Optional[str] = None) -> List[NotifyResult]:
        """Notify about links that just went dead in a link check."""
        if not self.settings.notify.on_dead_links:
            return []
        if not stats:
            return []
        newly = stats.get("newly_dead", 0)
        if not newly:
            return []
        urls = list(stats.get("newly_dead_urls", []))[:25]
        lines = [f"• {u}" for u in urls if u]
        dead_total = stats.get("dead", 0)
        extra = f" ({dead_total} dead in total)" if dead_total else ""
        header = f"{newly} link(s) just went dead{extra}."
        body = header + ("\n\n" + "\n".join(lines) if lines else "")
        where = f" — {site}" if site else ""
        return self.send(f"{newly} newly-dead link(s){where}", body)

    def test(self) -> List[NotifyResult]:
        """Send a test message to every configured channel."""
        return self.send(
            "Test notification",
            "If you can read this, NESTfetch notifications are configured correctly. 🎉",
        )

    # ── Channel implementations ──
    def _send_telegram(self, subject: str, body: str) -> NotifyResult:
        t = self.settings.telegram
        url = "https://api.telegram.org/bot" + t.token + "/sendMessage"
        text = _truncate(f"*{subject}*\n\n{body}", 4000)
        data = urllib.parse.urlencode({
            "chat_id": t.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        code, resp = _http_post(
            url, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        ok = 200 <= code < 300
        return NotifyResult("telegram", ok, f"HTTP {code}" + ("" if ok else f": {_truncate(resp, 160)}"))

    def _send_discord(self, subject: str, body: str) -> NotifyResult:
        d = self.settings.discord
        content = _truncate(f"**{subject}**\n{body}", 1900)
        payload = json.dumps({"content": content}).encode("utf-8")
        code, resp = _http_post(
            d.webhook_url, data=payload,
            headers={"Content-Type": "application/json"},
        )
        ok = code in (200, 204) or 200 <= code < 300
        return NotifyResult("discord", ok, f"HTTP {code}" + ("" if ok else f": {_truncate(resp, 160)}"))

    def _send_email(self, subject: str, body: str) -> NotifyResult:
        e = self.settings.email
        msg = EmailMessage()
        msg["Subject"] = f"[NESTfetch] {subject}"
        msg["From"] = e.from_addr or e.username or "nestfetch@localhost"
        msg["To"] = ", ".join(e.to_addrs)
        msg.set_content(body)
        try:
            client = _smtp_factory(e.smtp_host, e.smtp_port, e.use_tls)
            try:
                if e.username:
                    client.login(e.username, e.password)
                client.send_message(msg)
            finally:
                try:
                    client.quit()
                except Exception:
                    pass
            return NotifyResult("email", True, f"sent to {len(e.to_addrs)} recipient(s)")
        except Exception as exc:
            return NotifyResult("email", False, str(exc))
