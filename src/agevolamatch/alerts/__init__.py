from agevolamatch.alerts.base import AlertChannel
from agevolamatch.alerts.email_channel import EmailChannel
from agevolamatch.alerts.service import AlertEvent, AlertRunSummary, run_alerts, run_tender_alerts
from agevolamatch.alerts.subscriptions import AlertSubscription, load_subscriptions
from agevolamatch.alerts.telegram_channel import TelegramChannel


def default_channels() -> dict[str, AlertChannel]:
    return {"email": EmailChannel(), "telegram": TelegramChannel()}


__all__ = [
    "AlertChannel",
    "AlertEvent",
    "AlertRunSummary",
    "AlertSubscription",
    "EmailChannel",
    "TelegramChannel",
    "default_channels",
    "load_subscriptions",
    "run_alerts",
    "run_tender_alerts",
]
