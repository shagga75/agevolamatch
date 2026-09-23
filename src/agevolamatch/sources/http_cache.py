"""Minimal file-based HTTP response cache, used to avoid hammering origin
servers on repeated ingest runs during development and testing."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CACHE_DIR = Path("data/cache/http")


@dataclass
class CachedHttpClient:
    """Wraps a GET call with a TTL file cache, keyed by the full URL."""

    cache_dir: Path = DEFAULT_CACHE_DIR
    ttl_seconds: int = 3600

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def get_cached(self, url: str) -> str | None:
        path = self._cache_path(url)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - payload["cached_at"] > self.ttl_seconds:
            return None
        return payload["body"]

    def store(self, url: str, body: str) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_path(url)
        path.write_text(
            json.dumps({"url": url, "cached_at": time.time(), "body": body}),
            encoding="utf-8",
        )
