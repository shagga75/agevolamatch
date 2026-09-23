from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agevolamatch.sources.anac import ANACSource
from agevolamatch.sources.incentivi_gov_it import IncentiviGovItSource
from agevolamatch.storage import get_engine, get_session, init_db, upsert_opportunities


@pytest.fixture
def api_client(tmp_path, incentivi_gov_it_raw_docs, anac_cig_raw_rows, monkeypatch):
    db_path = tmp_path / "api_test.db"
    monkeypatch.setenv("AGEVOLAMATCH_DB_PATH", str(db_path))

    # Import after setting the env var so app module-level state (none, but
    # keeps the pattern consistent) and the lru_cache key reflect this test's DB.
    from agevolamatch.api.app import _engine_for
    from agevolamatch.api.app import app as fastapi_app

    _engine_for.cache_clear()

    engine = get_engine(db_path)
    init_db(engine)
    incentive_source = IncentiviGovItSource()
    tender_source = ANACSource()
    opportunities = [incentive_source.normalize(doc) for doc in incentivi_gov_it_raw_docs] + [
        tender_source.normalize(row) for row in anac_cig_raw_rows
    ]
    with get_session(engine) as session:
        upsert_opportunities(session, opportunities)

    with TestClient(fastapi_app) as client:
        yield client

    _engine_for.cache_clear()


def test_health(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_incentives_returns_stored_data(api_client):
    response = api_client.get("/incentives", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert "source_id" in body[0]


def test_list_incentives_filters_by_status(api_client):
    response = api_client.get("/incentives", params={"status": "closed", "limit": 100})
    assert response.status_code == 200
    assert all(item["status"] == "closed" for item in response.json())


def test_list_incentives_filters_by_region(api_client):
    response = api_client.get("/incentives", params={"region": "Estero", "limit": 100})
    assert response.status_code == 200
    assert all("Estero" in item["regions"] for item in response.json())


def test_get_incentive_by_id(api_client, incentivi_gov_it_raw_docs):
    known_id = str(incentivi_gov_it_raw_docs[0]["ID_Incentivo"])
    response = api_client.get(f"/incentives/{known_id}")
    assert response.status_code == 200
    assert response.json()["source_id"] == known_id


def test_get_incentive_not_found(api_client):
    response = api_client.get("/incentives/does-not-exist")
    assert response.status_code == 404


def test_match_endpoint_returns_ranked_results(api_client):
    profile = {
        "name": "Test Srl",
        "region": "Lazio",
        "size": "Microimpresa",
        "ateco_codes": [{"code": "62.01", "version": "2025"}],
    }
    response = api_client.post("/match", json=profile, params={"top": 5})
    assert response.status_code == 200
    results = response.json()
    assert results
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert all(r["eligible"] for r in results)


def test_match_endpoint_rejects_invalid_profile(api_client):
    response = api_client.post("/match", json={"name": "Missing required fields"})
    assert response.status_code == 422


def test_list_tenders_returns_stored_data(api_client):
    response = api_client.get("/tenders", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert "cpv_codes" in body[0]


def test_list_tenders_filters_by_status(api_client):
    response = api_client.get("/tenders", params={"status": "open", "limit": 100})
    assert response.status_code == 200
    assert response.json()
    assert all(item["status"] == "open" for item in response.json())


def test_list_tenders_filters_by_province(api_client, anac_cig_raw_rows):
    known_province = next(r["provincia"] for r in anac_cig_raw_rows if r.get("provincia"))
    response = api_client.get("/tenders", params={"province": known_province, "limit": 100})
    assert response.status_code == 200
    assert response.json()
    assert all(item["province"] == known_province for item in response.json())


def test_get_tender_by_id(api_client, anac_cig_raw_rows):
    known_id = anac_cig_raw_rows[0]["cig"]
    response = api_client.get(f"/tenders/{known_id}")
    assert response.status_code == 200
    assert response.json()["source_id"] == known_id


def test_get_tender_not_found(api_client):
    response = api_client.get("/tenders/does-not-exist")
    assert response.status_code == 404


def test_get_incentive_does_not_leak_a_tender_with_the_same_id(api_client, anac_cig_raw_rows):
    """A CIG that happens to exist must never be returned by /incentives/{id}
    - regression coverage for the source-filtering fix in get_incentive_record."""
    tender_id = anac_cig_raw_rows[0]["cig"]
    response = api_client.get(f"/incentives/{tender_id}")
    assert response.status_code == 404


def test_match_tenders_endpoint_returns_ranked_results(api_client):
    profile = {
        "name": "Test Srl",
        "region": "Lazio",
        "size": "Microimpresa",
        "cpv_codes": ["72200000", "72212000"],
    }
    response = api_client.post("/tenders/match", json=profile, params={"top": 5})
    assert response.status_code == 200
    results = response.json()
    assert results
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert all(r["eligible"] for r in results)


def test_match_tenders_endpoint_rejects_invalid_profile(api_client):
    response = api_client.post("/tenders/match", json={"name": "Missing required fields"})
    assert response.status_code == 422
