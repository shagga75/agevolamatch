from __future__ import annotations

from agevolamatch.models.enums import OpportunitySourceName, OpportunityStatus
from agevolamatch.sources.invitalia import InvitaliaSource, parse_listing_page


def test_parse_listing_page_extracts_all_real_cards(invitalia_listing_page0_html):
    cards = parse_listing_page(invitalia_listing_page0_html)
    assert len(cards) == 12
    titles = {c["title"] for c in cards}
    assert "Smart&Start Italia" in titles
    assert "Imprenditoria femminile" in titles


def test_parse_listing_page_extracts_status_and_description(invitalia_listing_page0_html):
    cards = parse_listing_page(invitalia_listing_page0_html)
    smart_start = next(c for c in cards if c["title"] == "Smart&Start Italia")
    assert smart_start["status_label"] == "attivo"
    assert smart_start["description"]
    assert smart_start["url"] == "/incentivi-e-strumenti/smartstart-italia"


def test_parse_listing_page_extracts_closed_and_upcoming_statuses(
    invitalia_listing_page0_html, invitalia_listing_page_chiuso_html
):
    cards_p0 = parse_listing_page(invitalia_listing_page0_html)
    assert any(c["status_label"] == "in apertura" for c in cards_p0)

    cards_p2 = parse_listing_page(invitalia_listing_page_chiuso_html)
    assert any(c["status_label"] == "chiuso" for c in cards_p2)


def test_parse_listing_page_empty_html_returns_no_cards():
    assert parse_listing_page("<html><body>no cards here</body></html>") == []


def test_normalize_maps_status_labels_correctly(invitalia_listing_page0_html, invitalia_listing_page_chiuso_html):
    source = InvitaliaSource()
    open_card = next(c for c in parse_listing_page(invitalia_listing_page0_html) if c["status_label"] == "attivo")
    upcoming_card = next(
        c for c in parse_listing_page(invitalia_listing_page0_html) if c["status_label"] == "in apertura"
    )
    closed_card = next(
        c for c in parse_listing_page(invitalia_listing_page_chiuso_html) if c["status_label"] == "chiuso"
    )

    assert source.normalize(open_card).status == OpportunityStatus.OPEN
    assert source.normalize(upcoming_card).status == OpportunityStatus.UPCOMING
    assert source.normalize(closed_card).status == OpportunityStatus.CLOSED


def test_normalize_produces_absolute_url_and_slug_id(invitalia_listing_page0_html):
    source = InvitaliaSource()
    card = next(c for c in parse_listing_page(invitalia_listing_page0_html) if c["title"] == "Smart&Start Italia")
    incentive = source.normalize(card)
    assert incentive.source == OpportunitySourceName.INVITALIA
    assert incentive.source_id == "smartstart-italia"
    assert incentive.url == "https://www.invitalia.it/incentivi-e-strumenti/smartstart-italia"


def test_normalize_leaves_unmodeled_fields_empty(invitalia_listing_page0_html):
    """Detail pages have no structured region/ATECO/size data (see module
    docstring) - this source never fabricates those, leaving them for the
    matching engine's existing "unverifiable" handling."""
    source = InvitaliaSource()
    card = parse_listing_page(invitalia_listing_page0_html)[0]
    incentive = source.normalize(card)
    assert incentive.regions == []
    assert incentive.ateco_codes is None
    assert incentive.ateco_all_sectors is False
    assert incentive.company_sizes == []


def test_parse_deduplicates_by_url_across_pages(invitalia_listing_page0_html):
    source = InvitaliaSource()
    records = source.parse([invitalia_listing_page0_html, invitalia_listing_page0_html])
    assert len(records) == 12


def test_run_normalizes_every_record_from_a_pre_fetched_page(invitalia_listing_page0_html, monkeypatch):
    source = InvitaliaSource()
    monkeypatch.setattr(source, "fetch", lambda: [invitalia_listing_page0_html])
    results = source.run()
    assert len(results) == 12
    assert all(r.source == OpportunitySourceName.INVITALIA for r in results)
