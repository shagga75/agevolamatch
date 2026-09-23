"""Cross-source deduplication: many Invitalia measures are also published on
incentivi.gov.it under a longer, differently-worded title (e.g. Invitalia's
"Smart&Start Italia" vs. incentivi.gov.it's "Smart&Start Italia - Sostegno
alle startup innovative"). There's no shared external ID between the two
sources, so this compares normalized titles instead.
"""

from __future__ import annotations

import re
import unicodedata

from agevolamatch.models.opportunity import Incentive

DEFAULT_SIMILARITY_THRESHOLD = 0.6


def normalize_title(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    ascii_title = re.sub(r"[^a-z0-9\s]", " ", ascii_title.lower())
    return re.sub(r"\s+", " ", ascii_title).strip()


def _title_similarity(a: str, b: str) -> float:
    norm_a, norm_b = normalize_title(a), normalize_title(b)
    if not norm_a or not norm_b:
        return 0.0
    if norm_a in norm_b or norm_b in norm_a:
        return 1.0
    tokens_a, tokens_b = set(norm_a.split()), set(norm_b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def find_duplicate(
    candidate_title: str,
    existing_incentives: list[Incentive],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> Incentive | None:
    """Returns the best-matching existing incentive if its title similarity
    to candidate_title is at or above threshold, else None."""
    best_match: Incentive | None = None
    best_score = 0.0
    for existing in existing_incentives:
        score = _title_similarity(candidate_title, existing.title)
        if score > best_score:
            best_score = score
            best_match = existing
    return best_match if best_score >= threshold else None
