"""Common interface every ingestion source implements.

A malformed individual record must never abort a whole ingestion run: normalize()
is called per-record from run(), failures are logged and skipped.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from agevolamatch.models.opportunity import Opportunity

logger = logging.getLogger(__name__)


class BaseSource(ABC):
    """Interface for a single ingestion source (one dataset / one website)."""

    name: str

    @abstractmethod
    def fetch(self) -> Any:
        """Retrieve the raw payload(s) from the origin (network I/O happens here only)."""

    @abstractmethod
    def parse(self, raw: Any) -> list[dict[str, Any]]:
        """Turn the raw payload into a list of source-native record dicts."""

    @abstractmethod
    def normalize(self, record: dict[str, Any]) -> Opportunity:
        """Map one source-native record to the canonical Opportunity/Incentive model.

        Raise on bad input; run() is responsible for catching and logging so one
        broken record doesn't break the whole ingestion.
        """

    def run(self) -> list[Opportunity]:
        raw = self.fetch()
        records = self.parse(raw)
        results: list[Opportunity] = []
        for record in records:
            try:
                results.append(self.normalize(record))
            except Exception:
                record_id = record.get("ID_Incentivo") or record.get("id") or "<unknown>"
                logger.exception("Failed to normalize record %s from source %s", record_id, self.name)
        logger.info("Source %s: %d/%d records normalized", self.name, len(results), len(records))
        return results
