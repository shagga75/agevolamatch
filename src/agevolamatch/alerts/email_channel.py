from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

from agevolamatch.alerts.base import AlertChannel

_REQUIRED_ENV_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TO")


class EmailChannel(AlertChannel):
    name = "email"

    def send(self, subject: str, body: str) -> None:
        missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]
        if missing:
            raise RuntimeError(
                f"Email channel not configured: missing {', '.join(missing)} in the environment (.env)"
            )

        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = os.environ["SMTP_FROM"]
        message["To"] = os.environ["SMTP_TO"]

        use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() not in {"false", "0", "no"}
        host = os.environ["SMTP_HOST"]
        port = int(os.environ["SMTP_PORT"])

        with smtplib.SMTP(host, port, timeout=15) as client:
            if use_tls:
                client.starttls()
            client.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            client.sendmail(message["From"], [message["To"]], message.as_string())
