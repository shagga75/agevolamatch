from __future__ import annotations

from agevolamatch.tenders.cpv import CpvMatchLevel, match_cpv


def test_exact_match():
    level, detail = match_cpv(["72200000"], ["72200000", "72212000"])
    assert level == CpvMatchLevel.EXACT
    assert "72200000" in detail


def test_prefix_match_at_shorter_shared_prefix():
    """Regression: a naive fixed-length-6 check would miss this - '722010'
    vs '724700' only share the first 2 digits, not 6."""
    level, _ = match_cpv(["72201000"], ["72470000"])
    assert level == CpvMatchLevel.PREFIX


def test_no_match():
    level, _ = match_cpv(["72200000"], ["45232410"])
    assert level == CpvMatchLevel.NO_MATCH


def test_unverifiable_when_tender_has_no_codes():
    level, _ = match_cpv(["72200000"], [])
    assert level == CpvMatchLevel.UNVERIFIABLE


def test_unverifiable_when_profile_has_no_codes():
    level, _ = match_cpv([], ["72200000"])
    assert level == CpvMatchLevel.UNVERIFIABLE


def test_check_digit_suffix_is_ignored():
    level, _ = match_cpv(["45232410"], ["45232410-9"])
    assert level == CpvMatchLevel.EXACT
