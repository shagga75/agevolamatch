from __future__ import annotations

from agevolamatch.sources.dedup import find_duplicate, normalize_title


def test_normalize_title_strips_accents_case_and_punctuation():
    assert normalize_title("Smart&Start Italia!") == "smart start italia"
    assert normalize_title("Perché così è più forte") == normalize_title("perche cosi e piu forte")


def test_find_duplicate_matches_substring_containment(incentive_factory):
    existing = [incentive_factory(source_id="1", title="Smart&Start Italia - Sostegno alle startup innovative")]
    match = find_duplicate("Smart&Start Italia", existing)
    assert match is not None
    assert match.source_id == "1"


def test_find_duplicate_matches_high_token_overlap(incentive_factory):
    existing = [incentive_factory(source_id="1", title="Resto al Sud 2.0 per giovani imprenditori")]
    match = find_duplicate("Resto al Sud 2.0", existing)
    assert match is not None


def test_find_duplicate_returns_none_for_unrelated_titles(incentive_factory):
    existing = [incentive_factory(source_id="1", title="Bonus colonnine domestiche")]
    match = find_duplicate("Fondo di partecipazione MUR", existing)
    assert match is None


def test_find_duplicate_returns_none_when_no_existing_incentives():
    assert find_duplicate("Anything", []) is None


def test_find_duplicate_picks_the_best_match_among_several(incentive_factory):
    existing = [
        incentive_factory(source_id="1", title="Completely unrelated bando"),
        incentive_factory(source_id="2", title="Legge 181 - Autoimpiego e Autoimprenditorialità"),
    ]
    match = find_duplicate("Legge 181", existing)
    assert match is not None
    assert match.source_id == "2"
