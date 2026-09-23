from __future__ import annotations

from agevolamatch.matching.ateco import AtecoMatchLevel, match_ateco


def test_all_sectors_wins_regardless_of_profile_codes():
    level, _ = match_ateco(["62.01"], None, all_sectors=True)
    assert level == AtecoMatchLevel.ALL_SECTORS


def test_exact_match():
    level, detail = match_ateco(["62.01"], ["62.01", "62.02"], all_sectors=False)
    assert level == AtecoMatchLevel.EXACT
    assert "6201" in detail


def test_prefix_match():
    level, _ = match_ateco(["62.01"], ["62.09"], all_sectors=False)
    assert level == AtecoMatchLevel.PREFIX


def test_no_match():
    level, _ = match_ateco(["62.01"], ["10.01"], all_sectors=False)
    assert level == AtecoMatchLevel.NO_MATCH


def test_unverifiable_when_incentive_has_no_codes():
    level, _ = match_ateco(["62.01"], None, all_sectors=False)
    assert level == AtecoMatchLevel.UNVERIFIABLE


def test_unverifiable_when_profile_has_no_codes():
    level, _ = match_ateco([], ["62.01"], all_sectors=False)
    assert level == AtecoMatchLevel.UNVERIFIABLE
