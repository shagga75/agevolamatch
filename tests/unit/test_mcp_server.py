from __future__ import annotations

import asyncio
import json

import pytest

from agevolamatch.sources.incentivi_gov_it import IncentiviGovItSource
from agevolamatch.storage import get_engine, get_session, init_db, upsert_opportunities


@pytest.fixture
def mcp_env(tmp_path, incentivi_gov_it_raw_docs, monkeypatch):
    db_path = tmp_path / "mcp_test.db"
    monkeypatch.setenv("AGEVOLAMATCH_DB_PATH", str(db_path))

    engine = get_engine(db_path)
    init_db(engine)
    source = IncentiviGovItSource()
    incentives = [source.normalize(doc) for doc in incentivi_gov_it_raw_docs]
    with get_session(engine) as session:
        upsert_opportunities(session, incentives)

    from agevolamatch.mcp.server import mcp

    return mcp


def _call(mcp, tool_name: str, arguments: dict):
    return asyncio.run(mcp.call_tool(tool_name, arguments))


def _json_items(result) -> list[dict]:
    return [json.loads(block.text) for block in result.content]


class TestListTools:
    def test_all_three_tools_are_registered(self, mcp_env):
        tools = asyncio.run(mcp_env.list_tools())
        assert {t.name for t in tools} == {"search_incentives", "get_incentive", "match_company_profile"}


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
