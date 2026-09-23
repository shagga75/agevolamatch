from __future__ import annotations

from agevolamatch.models.enums import OpportunitySourceName, OpportunityStatus
from agevolamatch.sources.incentivi_gov_it import IncentiviGovItSource


def test_normalize_all_fixture_records_without_raising(incentivi_gov_it_raw_docs):
    source = IncentiviGovItSource()
    incentives = [source.normalize(doc) for doc in incentivi_gov_it_raw_docs]
    assert len(incentives) == len(incentivi_gov_it_raw_docs)
    for incentive in incentives:
        assert incentive.source == OpportunitySourceName.INCENTIVI_GOV_IT
        assert incentive.source_id
        assert incentive.content_hash


def test_run_is_tolerant_of_one_malformed_record(incentivi_gov_it_raw_docs, monkeypatch):
    source = IncentiviGovItSource()
    broken = dict(incentivi_gov_it_raw_docs[0])
    del broken["Titolo"]  # required field missing -> normalize() should raise for this one
    docs = [broken, *incentivi_gov_it_raw_docs[1:]]

    monkeypatch.setattr(source, "fetch", lambda: docs)
    results = source.run()

    assert len(results) == len(docs) - 1


def test_ateco_all_sectors_prose_is_recognized(incentivi_gov_it_raw_docs):
    source = IncentiviGovItSource()
    doc = next(d for d in incentivi_gov_it_raw_docs if (d.get("Codici_ATECO") or "").startswith("Tutti"))
    incentive = source.normalize(doc)
    assert incentive.ateco_all_sectors is True
    assert incentive.ateco_codes is None


def test_ateco_real_codes_are_parsed(incentivi_gov_it_raw_docs):
    import re

    source = IncentiviGovItSource()
    doc = next(
        d for d in incentivi_gov_it_raw_docs if re.search(r"\d{2}\.\d{2}", d.get("Codici_ATECO") or "")
    )
    incentive = source.normalize(doc)
    assert incentive.ateco_all_sectors is False
    assert incentive.ateco_codes


def test_startup_or_pmi_innovativa_flag_set_when_ambiguous_value_present(incentivi_gov_it_raw_docs):
    source = IncentiviGovItSource()
    doc = next(
        d for d in incentivi_gov_it_raw_docs if "Impresa - SU/PMI innovativa" in d.get("Tipologia_Soggetto", [])
    )
    incentive = source.normalize(doc)
    assert incentive.startup_or_pmi_innovativa_ambiguous is True


def test_municipalities_split_into_list(incentivi_gov_it_raw_docs):
    source = IncentiviGovItSource()
    doc = next(d for d in incentivi_gov_it_raw_docs if d.get("Comuni"))
    incentive = source.normalize(doc)
    assert incentive.municipalities
    assert all(";" not in m for m in incentive.municipalities)


def test_missing_close_date_yields_open_or_unknown_status(incentivi_gov_it_raw_docs):
    source = IncentiviGovItSource()
    doc = next(d for d in incentivi_gov_it_raw_docs if "Data_chiusura" not in d)
    incentive = source.normalize(doc)
    assert incentive.status in {OpportunityStatus.OPEN, OpportunityStatus.UNKNOWN}


def test_estero_region_is_preserved(incentivi_gov_it_raw_docs):
    source = IncentiviGovItSource()
    doc = next(d for d in incentivi_gov_it_raw_docs if "Estero" in d.get("Regioni", []))
    incentive = source.normalize(doc)
    assert "Estero" in incentive.regions
