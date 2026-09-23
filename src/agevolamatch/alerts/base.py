from __future__ import annotations

from abc import ABC, abstractmethod


class AlertChannel(ABC):
    """A delivery channel. Config is read from the environment (.env) lazily,
    inside send(), so building the channel registry never fails just because
    a channel a subscription doesn't use isn't configured."""

    name: str

    @abstractmethod
    def send(self, subject: str, body: str) -> None: ...
