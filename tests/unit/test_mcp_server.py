from __future__ import annotations

import asyncio
import json

import pytest

from agevolamatch.sources.anac import ANACSource
from agevolamatch.sources.incentivi_gov_it import IncentiviGovItSource
from agevolamatch.storage import get_engine, get_session, init_db, upsert_opportunities


@pytest.fixture
def mcp_env(tmp_path, incentivi_gov_it_raw_docs, anac_cig_raw_rows, monkeypatch):
    db_path = tmp_path / "mcp_test.db"
    monkeypatch.setenv("AGEVOLAMATCH_DB_PATH", str(db_path))

    engine = get_engine(db_path)
    init_db(engine)
    incentive_source = IncentiviGovItSource()
    tender_source = ANACSource()
    opportunities = [incentive_source.normalize(doc) for doc in incentivi_gov_it_raw_docs] + [
        tender_source.normalize(row) for row in anac_cig_raw_rows
    ]
    with get_session(engine) as session:
        upsert_opportunities(session, opportunities)

    from agevolamatch.mcp.server import mcp

    return mcp


def _call(mcp, tool_name: str, arguments: dict):
    return asyncio.run(mcp.call_tool(tool_name, arguments))


def _json_items(result) -> list[dict]:
    return [json.loads(block.text) for block in result.content]


class TestListTools:
    def test_all_six_tools_are_registered(self, mcp_env):
        tools = asyncio.run(mcp_env.list_tools())
        assert {t.name for t in tools} == {
            "search_incentives",
            "get_incentive",
            "match_company_profile",
            "search_tenders",
            "get_tender",
            "match_tenders",
        }


class TestSearchIncentives:
    def test_returns_stored_incentives(self, mcp_env):
        result = _call(mcp_env, "search_incentives", {"limit": 5})
        items = _json_items(result)
        assert len(items) == 5
        assert "source_id" in items[0]

    def test_filters_by_status(self, mcp_env):
        result = _call(mcp_env, "search_incentives", {"status": "closed", "limit": 100})
        items = _json_items(result)
        assert items
        assert all(i["status"] == "closed" for i in items)

    def test_filters_by_region(self, mcp_env):
        result = _call(mcp_env, "search_incentives", {"region": "Estero", "limit": 100})
        items = _json_items(result)
        assert items
        assert all("Estero" in i["regions"] for i in items)


class TestGetIncentive:
    def test_returns_matching_incentive(self, mcp_env, incentivi_gov_it_raw_docs):
        known_id = str(incentivi_gov_it_raw_docs[0]["ID_Incentivo"])
        result = _call(mcp_env, "get_incentive", {"source_id": known_id})
        assert result.structured_content["result"]["source_id"] == known_id

    def test_returns_null_for_unknown_id(self, mcp_env):
        result = _call(mcp_env, "get_incentive", {"source_id": "does-not-exist"})
        assert result.structured_content["result"] is None
        assert result.content == []


class TestMatchCompanyProfile:
    VALID_PROFILE = {
        "name": "Test Srl",
        "region": "Lazio",
        "size": "Microimpresa",
        "ateco_codes": [{"code": "62.01", "version": "2025"}],
    }

    def test_returns_ranked_eligible_results(self, mcp_env):
        result = _call(mcp_env, "match_company_profile", {"profile": self.VALID_PROFILE, "top": 5})
        items = _json_items(result)
        assert items
        scores = [i["score"] for i in items]
        assert scores == sorted(scores, reverse=True)
        assert all(i["eligible"] for i in items)

    def test_respects_min_score(self, mcp_env):
        result = _call(
            mcp_env, "match_company_profile", {"profile": self.VALID_PROFILE, "top": 50, "min_score": 1000}
        )
        assert result.content == []

    def test_invalid_profile_raises_tool_error(self, mcp_env):
        """call_tool() (the in-process API used here and by these tests) raises
        on failure rather than returning is_error=True - the SDK's stdio/JSON-RPC
        transport layer is what translates a raised ToolError into the wire-level
        error result an actual MCP client sees; that translation isn't exercised
        by calling call_tool() directly."""
        from mcp.server.mcpserver.exceptions import ToolError

        with pytest.raises(ToolError, match="Invalid company profile"):
            _call(mcp_env, "match_company_profile", {"profile": {"name": "Missing required fields"}})


class TestSearchTenders:
    def test_returns_stored_tenders(self, mcp_env):
        result = _call(mcp_env, "search_tenders", {"limit": 5})
        items = _json_items(result)
        assert len(items) == 5
        assert "cpv_codes" in items[0]

    def test_filters_by_status(self, mcp_env):
        result = _call(mcp_env, "search_tenders", {"status": "open", "limit": 100})
        items = _json_items(result)
        assert items
        assert all(i["status"] == "open" for i in items)

    def test_filters_by_province(self, mcp_env, anac_cig_raw_rows):
        known_province = next(r["provincia"] for r in anac_cig_raw_rows if r.get("provincia"))
        result = _call(mcp_env, "search_tenders", {"province": known_province, "limit": 100})
        items = _json_items(result)
        assert items
        assert all(i["province"] == known_province for i in items)


class TestGetTender:
    def test_returns_matching_tender(self, mcp_env, anac_cig_raw_rows):
        known_id = anac_cig_raw_rows[0]["cig"]
        result = _call(mcp_env, "get_tender", {"source_id": known_id})
        assert result.structured_content["result"]["source_id"] == known_id

    def test_returns_null_for_unknown_id(self, mcp_env):
        result = _call(mcp_env, "get_tender", {"source_id": "does-not-exist"})
        assert result.structured_content["result"] is None
        assert result.content == []

    def test_does_not_leak_an_incentive_with_the_same_id(self, mcp_env, incentivi_gov_it_raw_docs):
        """Regression coverage for the source-filtering fix in
        get_tender_record - an incentive id must never surface here."""
        incentive_id = str(incentivi_gov_it_raw_docs[0]["ID_Incentivo"])
        result = _call(mcp_env, "get_tender", {"source_id": incentive_id})
        assert result.structured_content["result"] is None


class TestMatchTenders:
    VALID_PROFILE = {
        "name": "Test Srl",
        "region": "Lazio",
        "size": "Microimpresa",
        "cpv_codes": ["72200000", "72212000"],
    }

    def test_returns_ranked_eligible_results(self, mcp_env):
        result = _call(mcp_env, "match_tenders", {"profile": self.VALID_PROFILE, "top": 5})
        items = _json_items(result)
        assert items
        scores = [i["score"] for i in items]
        assert scores == sorted(scores, reverse=True)
        assert all(i["eligible"] for i in items)

    def test_respects_min_score(self, mcp_env):
        result = _call(mcp_env, "match_tenders", {"profile": self.VALID_PROFILE, "top": 50, "min_score": 1000})
        assert result.content == []

    def test_invalid_profile_raises_tool_error(self, mcp_env):
        from mcp.server.mcpserver.exceptions import ToolError

        with pytest.raises(ToolError, match="Invalid company profile"):
            _call(mcp_env, "match_tenders", {"profile": {"name": "Missing required fields"}})
