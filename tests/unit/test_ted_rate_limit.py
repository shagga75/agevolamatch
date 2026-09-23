"""Regression coverage for the 429 handling added after hitting a real rate
limit from the live (unauthenticated) TED API during manual testing."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from agevolamatch.sources.ted import SEARCH_URL, TEDSource


@respx.mock
def test_retries_on_429_and_succeeds():
    route = respx.post(SEARCH_URL)
    route.side_effect = [
        Response(429, headers={"Retry-After": "0"}, json={"message": "rate limited"}),
        Response(200, json={"notices": [], "totalNoticeCount": 0}),
    ]

    source = TEDSource(min_request_interval_seconds=0.0, max_pages=1)
    notices = source.fetch()

    assert notices == []
    assert route.call_count == 2


@respx.mock
def test_gives_up_after_max_retries():
    respx.post(SEARCH_URL).mock(return_value=Response(429, headers={"Retry-After": "0"}))

    source = TEDSource(min_request_interval_seconds=0.0, max_pages=1, max_retries_on_rate_limit=2)

    with pytest.raises(Exception, match="429"):
        source.fetch()


@respx.mock
def test_stops_paginating_when_a_page_is_short():
    respx.post(SEARCH_URL).mock(
        return_value=Response(200, json={"notices": [{"publication-number": "1-2026"}], "totalNoticeCount": 1})
    )

    source = TEDSource(min_request_interval_seconds=0.0, page_size=50, max_pages=10)
    notices = source.fetch()

    assert len(notices) == 1
