"""ATECO matching: exact code, hierarchical prefix, or the source's "all
sectors eligible" free-text pattern (see docs/sources.md - 71% of incentives
use that pattern instead of real codes).

NOTE: the official ISTAT ATECO 2007<->2025 correspondence table is not yet
integrated (documented TODO in CLAUDE.md). Until then, codes from either
version are compared as plain digit strings, which is safe for exact/prefix
matching within the same version but may under-match across a 2007/2025
boundary where a code was renumbered.
"""

from __future__ import annotations

from enum import StrEnum


class AtecoMatchLevel(StrEnum):
    ALL_SECTORS = "all_sectors"
    EXACT = "exact"
    PREFIX = "prefix"
    NO_MATCH = "no_match"
    UNVERIFIABLE = "unverifiable"


def _normalize(code: str) -> str:
    return code.replace(".", "").strip()


def match_ateco(
    profile_codes: list[str],
    incentive_codes: list[str] | None,
    all_sectors: bool,
) -> tuple[AtecoMatchLevel, str]:
    if all_sectors:
        return AtecoMatchLevel.ALL_SECTORS, "Incentivo abierto a todos los sectores (ATECO no restringido)"

    if not incentive_codes:
        return AtecoMatchLevel.UNVERIFIABLE, "El incentivo no especifica códigos ATECO parseables"

    if not profile_codes:
        return AtecoMatchLevel.UNVERIFIABLE, "El perfil no tiene códigos ATECO configurados"

    norm_incentive = {_normalize(c) for c in incentive_codes}
    norm_profile = {_normalize(c) for c in profile_codes}

    if norm_profile & norm_incentive:
        matched = next(iter(norm_profile & norm_incentive))
        return AtecoMatchLevel.EXACT, f"Coincidencia exacta de código ATECO ({matched})"

    for p in norm_profile:
        for i in norm_incentive:
            max_len = min(len(p), len(i), 4)
            for prefix_len in range(max_len, 1, -1):
                if p[:prefix_len] == i[:prefix_len]:
                    return AtecoMatchLevel.PREFIX, f"Coincidencia por prefijo ATECO ({p[:prefix_len]}...)"

    return AtecoMatchLevel.NO_MATCH, "Ningún código ATECO del perfil coincide con los del incentivo"
