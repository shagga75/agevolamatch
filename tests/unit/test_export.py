from __future__ import annotations

import csv
import json
from datetime import date

import pytest

from agevolamatch.export import match_results_to_rows, write_rows
from agevolamatch.matching.engine import match_incentive
from agevolamatch.models.company_profile import AtecoCode, CompanyProfile
from agevolamatch.models.enums import CompanySize, Region


def make_profile(**overrides) -> CompanyProfile:
    defaults = {
        "name": "Test Srl",
        "region": Region.LAZIO,
        "size": CompanySize.MICRO,
        "ateco_codes": [AtecoCode(code="62.01")],
    }
    defaults.update(overrides)
    return CompanyProfile(**defaults)


def test_match_results_to_rows_shape(incentive_factory):
    incentive = incentive_factory(ateco_all_sectors=True)
    result = match_incentive(incentive, make_profile(), as_of=date(2024, 6, 1))
    rows = match_results_to_rows([result])
    assert rows[0]["source_id"] == incentive.source_id
    assert rows[0]["score"] == result.score


def test_write_rows_json_roundtrip(tmp_path):
    rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    path = tmp_path / "out.json"
    write_rows(rows, path, "json")
    assert json.loads(path.read_text(encoding="utf-8")) == rows


def test_write_rows_csv_roundtrip(tmp_path):
    rows = [{"a": "1", "b": "x"}, {"a": "2", "b": "y"}]
    path = tmp_path / "out.csv"
    write_rows(rows, path, "csv")
    with path.open(encoding="utf-8") as f:
        read_rows = list(csv.DictReader(f))
    assert read_rows == rows


def test_write_rows_empty_list(tmp_path):
    path = tmp_path / "empty.csv"
    write_rows([], path, "csv")
    assert path.read_text(encoding="utf-8") == ""


def test_write_rows_rejects_unknown_format(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        write_rows([{"a": 1}], tmp_path / "out.xml", "xml")
