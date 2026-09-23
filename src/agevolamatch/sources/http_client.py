"""Shared cached + rate-limited GET client, used by every HTTP-based source
so each one only needs to say what URL to fetch, not how to fetch politely."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from agevolamatch.sources.http_cache import CachedHttpClient


@dataclass
class RateLimitedHttpClient:
    user_agent: str
    min_request_interval_seconds: float = 1.0
    timeout_seconds: float = 30.0
    http_cache: CachedHttpClient = field(default_factory=CachedHttpClient)
    client: httpx.Client | None = None
    _last_request_at: float = field(default=0.0, init=False, repr=False)

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self.min_request_interval_seconds - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def get(self, url: str) -> str:
        cached = self.http_cache.get_cached(url)
        if cached is not None:
            return cached
        self._rate_limit()
        client = self.client or httpx.Client(timeout=self.timeout_seconds)
        try:
            response = client.get(url, headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            body = response.text
        finally:
            if self.client is None:
                client.close()
        self.http_cache.store(url, body)
        return body
