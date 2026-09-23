from __future__ import annotations

import os

import httpx

from agevolamatch.alerts.base import AlertChannel

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramChannel(AlertChannel):
    name = "telegram"

    def send(self, subject: str, body: str) -> None:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise RuntimeError(
                "Telegram channel not configured: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the environment (.env)"
            )

        text = f"*{subject}*\n\n{body}"
        response = httpx.post(
            f"{TELEGRAM_API_BASE}/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        response.raise_for_status()
