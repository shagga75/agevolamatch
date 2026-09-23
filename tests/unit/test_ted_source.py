from __future__ import annotations

from agevolamatch.models.enums import OpportunitySourceName
from agevolamatch.sources.ted import TEDSource, _pick_language_value, _pick_url


class TestPickLanguageValue:
    def test_prefers_italian(self):
        assert _pick_language_value({"eng": "Hello", "ita": "Ciao"}) == "Ciao"

    def test_falls_back_to_english(self):
        assert _pick_language_value({"eng": "Hello", "fra": "Bonjour"}) == "Hello"

    def test_falls_back_to_any_available(self):
        assert _pick_language_value({"fra": "Bonjour"}) == "Bonjour"

    def test_unwraps_single_element_lists(self):
        assert _pick_language_value({"ita": ["Nome Azienda"]}) == "Nome Azienda"

    def test_none_input(self):
        assert _pick_language_value(None) is None

    def test_empty_dict(self):
        assert _pick_language_value({}) is None


class TestPickUrl:
    def test_prefers_italian_html_direct(self):
        links = {"htmlDirect": {"ITA": "https://ted.europa.eu/it/notice/1/html", "ENG": "https://.../en"}}
        assert _pick_url(links) == "https://ted.europa.eu/it/notice/1/html"

    def test_falls_back_to_english(self):
        links = {"htmlDirect": {"ENG": "https://ted.europa.eu/en/notice/1/html"}}
        assert _pick_url(links) == "https://ted.europa.eu/en/notice/1/html"

    def test_none_links(self):
        assert _pick_url(None) is None

    def test_empty_html_direct(self):
        assert _pick_url({"htmlDirect": {}}) is None


def test_normalize_all_fixture_notices_without_raising(ted_notices_raw):
    source = TEDSource()
    tenders = [source.normalize(n) for n in ted_notices_raw]
    assert len(tenders) == len(ted_notices_raw)
    for tender in tenders:
        assert tender.source == OpportunitySourceName.TED_EUROPA
        assert tender.source_id
        assert tender.buyer_country == "ITA"


def test_run_is_tolerant_of_one_malformed_record(ted_notices_raw, monkeypatch):
    source = TEDSource()
    broken = dict(ted_notices_raw[0])
    del broken["publication-number"]  # required -> normalize() should raise for this one
    docs = [broken, *ted_notices_raw[1:]]

    monkeypatch.setattr(source, "fetch", lambda: docs)
    results = source.run()

    assert len(results) == len(docs) - 1


def test_open_and_closed_statuses_both_present_in_fixture(ted_notices_raw):
    """The fixture was curated to include both - see how tests/fixtures/
    ted_notices_sample.json was built (docs/sources.md)."""
    source = TEDSource()
    tenders = [source.normalize(n) for n in ted_notices_raw]
    statuses = {t.status.value for t in tenders}
    assert "open" in statuses
    assert "closed" in statuses


def test_cpv_codes_are_deduplicated_and_sorted(ted_notices_raw):
    source = TEDSource()
    notice = next(n for n in ted_notices_raw if len(set(n.get("classification-cpv") or [])) > 1)
    tender = source.normalize(notice)
    assert tender.cpv_codes == sorted(set(tender.cpv_codes))


def test_missing_estimated_value_leaves_field_none(ted_notices_raw):
    source = TEDSource()
    notice = next(n for n in ted_notices_raw if not n.get("estimated-value-lot"))
    tender = source.normalize(notice)
    assert tender.estimated_value is None
