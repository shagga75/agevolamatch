from __future__ import annotations

import pytest
import respx
from httpx import Response

from agevolamatch.alerts.email_channel import EmailChannel
from agevolamatch.alerts.telegram_channel import TELEGRAM_API_BASE, TelegramChannel


def test_email_channel_raises_clear_error_when_unconfigured(monkeypatch):
    for var in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TO"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        EmailChannel().send("subject", "body")


def test_telegram_channel_raises_clear_error_when_unconfigured(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        TelegramChannel().send("subject", "body")


@respx.mock
def test_telegram_channel_sends_via_bot_api(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    route = respx.post(f"{TELEGRAM_API_BASE}/botfake-token/sendMessage").mock(
        return_value=Response(200, json={"ok": True})
    )

    TelegramChannel().send("Test subject", "Test body")

    assert route.called
    sent_data = route.calls[0].request.content.decode()
    assert "12345" in sent_data


@respx.mock
def test_telegram_channel_sends_plain_text_without_parse_mode(monkeypatch):
    """Regression test: parse_mode=Markdown was confirmed against the real
    Telegram API to 400 on real incentive titles/URLs containing unmatched
    markdown special characters. Plain text (no parse_mode) needs no escaping."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    route = respx.post(f"{TELEGRAM_API_BASE}/botfake-token/sendMessage").mock(
        return_value=Response(200, json={"ok": True})
    )

    subject_with_markdown_chars = "[AgevolaMatch] Bando *Test* (score 90) - a/b_c"
    TelegramChannel().send(subject_with_markdown_chars, "https://example.com/a_b-(c)")

    sent_form = route.calls[0].request.content.decode()
    assert "parse_mode" not in sent_form


@respx.mock
def test_telegram_channel_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    respx.post(f"{TELEGRAM_API_BASE}/botfake-token/sendMessage").mock(
        return_value=Response(400, json={"ok": False, "description": "bad request"})
    )

    with pytest.raises(Exception, match="400"):
        TelegramChannel().send("Test subject", "Test body")
