"""Optional LLM enrichment: extracts eligibility requirements mentioned in an
incentive's free-text description that the structured fields don't capture
(e.g. "costituita da non più di 60 mesi", a specific comune). Purely
informational - appended to MatchExplanation.unverifiable, prefixed "[LLM]"
so it's never confused with a deterministic hard-filter finding. Never
changes eligibility or score. Any failure (network, malformed response) is
logged and skipped for that one result - one bad LLM call must not break the
match run, same principle as BaseSource.run()'s per-record tolerance.
"""

from __future__ import annotations

import logging
import re

from agevolamatch.matching.llm.base import LLMProvider
from agevolamatch.matching.models import MatchResult

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """Sei un assistente che analizza il testo di un incentivo pubblico italiano per le imprese.
Estrai SOLO i requisiti di ammissibilità espliciti menzionati nel testo (età dell'azienda, comune o provincia specifici, settore escluso, forma giuridica, altro requisito concreto).
Rispondi con un elenco puntato breve (massimo 6 punti), una riga per requisito, in italiano, senza premesse.
Se non ci sono requisiti espliciti oltre a quelli già evidenti dal titolo, rispondi esattamente con: Nessun requisito aggiuntivo rilevato

Testo dell'incentivo:
\"\"\"
{description}
\"\"\"
"""

_BULLET_PREFIX = re.compile(r"^[-*•]\s*|^\d+[.)]\s*")
_NO_REQUIREMENTS_MARKER = "nessun requisito"
_MAX_DESCRIPTION_CHARS = 4000


def _parse_bullet_list(text: str, max_items: int) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = _BULLET_PREFIX.sub("", line.strip()).strip()
        if not stripped:
            continue
        if stripped.lower().startswith(_NO_REQUIREMENTS_MARKER):
            return []
        items.append(stripped)
        if len(items) >= max_items:
            break
    return items


def extract_requirements(provider: LLMProvider, description: str, max_items: int = 6) -> list[str]:
    if not description or not description.strip():
        return []
    prompt = _PROMPT_TEMPLATE.format(description=description[:_MAX_DESCRIPTION_CHARS])
    response_text = provider.complete(prompt)
    return _parse_bullet_list(response_text, max_items=max_items)


def enrich_with_llm_requirements(
    results: list[MatchResult],
    provider: LLMProvider,
    top_n: int = 10,
) -> list[MatchResult]:
    enriched: list[MatchResult] = []
    for index, result in enumerate(results):
        if index >= top_n or not result.eligible:
            enriched.append(result)
            continue
        try:
            requirements = extract_requirements(provider, result.incentive.description or "")
        except Exception:
            logger.exception("LLM requirement extraction failed for %s", result.incentive.source_id)
            enriched.append(result)
            continue
        if not requirements:
            enriched.append(result)
            continue
        new_explanation = result.explanation.model_copy(
            update={"unverifiable": [*result.explanation.unverifiable, *(f"[LLM] {r}" for r in requirements)]}
        )
        enriched.append(result.model_copy(update={"explanation": new_explanation}))
    return enriched
