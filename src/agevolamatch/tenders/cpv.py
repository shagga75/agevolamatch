"""CPV (Common Procurement Vocabulary) matching - the tenders/gare analog of
matching/ateco.py's ATECO matching. CPV codes are 8-digit hierarchical codes
(e.g. '45232410' - division 45xxxxxx = construction works); unlike ATECO,
there is no "all sectors" free-text pattern in this domain's real data, every
tender we've seen carries real CPV codes (confirmed: 150/150 in a live TED
sample, and ANAC's cod_cpv is populated whenever present in the source row).
"""

from __future__ import annotations

from enum import StrEnum


class CpvMatchLevel(StrEnum):
    EXACT = "exact"
    PREFIX = "prefix"
    NO_MATCH = "no_match"
    UNVERIFIABLE = "unverifiable"


def _normalize(code: str) -> str:
    return code.strip().split("-")[0]  # CPV codes are sometimes suffixed '-9' (a check digit)


def match_cpv(profile_codes: list[str], tender_codes: list[str]) -> tuple[CpvMatchLevel, str]:
    if not tender_codes:
        return CpvMatchLevel.UNVERIFIABLE, "El bando no especifica códigos CPV"
    if not profile_codes:
        return CpvMatchLevel.UNVERIFIABLE, "El perfil no tiene códigos CPV configurados"

    norm_profile = {_normalize(c) for c in profile_codes}
    norm_tender = {_normalize(c) for c in tender_codes}

    if norm_profile & norm_tender:
        matched = next(iter(norm_profile & norm_tender))
        return CpvMatchLevel.EXACT, f"Coincidencia exacta de código CPV ({matched})"

    # Try the longest common prefix first, same approach as matching/ateco.py:
    # a single fixed-length check (e.g. always exactly 6 digits) would miss a
    # real match at a shorter shared prefix, like "45232410" vs "45247000"
    # (both division 45, but only agreeing on the first 2 digits).
    for p in norm_profile:
        for t in norm_tender:
            max_len = min(len(p), len(t), 6)
            for prefix_len in range(max_len, 1, -1):
                if p[:prefix_len] == t[:prefix_len]:
                    return CpvMatchLevel.PREFIX, f"Coincidencia por prefijo CPV ({p[:prefix_len]}...)"

    return CpvMatchLevel.NO_MATCH, "Ningún código CPV del perfil coincide con los del bando"
