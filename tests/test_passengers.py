"""Compensation is per passenger: the check, replies, letter and Inbox multiply by the party size."""

import pytest

from app.server import api
from claims_agent.agent import respond
from claims_agent.claim_letter import draft_letter
from claims_agent.facts import FlightFacts, check_facts, extract_facts_rules


@pytest.mark.parametrize("text,n", [
    ("We were three passengers", 3),
    ("Нас було троє", 3),
    ("family of 4", 4),
    ("my wife and I flew", 2),
    ("było nas czworo", 4),
    ("wir waren zu dritt", 3),
    ("éramos cinco", 5),
    ("eravamo in tre", 3),
    ("We are 4 hours late", None),
    ("I flew alone", None),
])
def test_passengers_from_text(text, n):
    assert extract_facts_rules(text).passengers == n


@pytest.mark.parametrize("text,hours", [
    ("delayed 3 and a half hours", 3.5),
    ("затримали на 3 і пів години", 3.5),
    ("opóźniony o 3 i pół godziny", 3.5),
    ("3½ hours late", 3.5),
])
def test_half_hours(text, hours):
    assert extract_facts_rules(text).delay_hours == hours


def test_total_in_check_reply_and_letter():
    msg = "We were 3 passengers. Flight from Lisbon to Berlin, delayed 4 hours. Am I entitled to compensation?"
    r = respond(msg)
    d = r.eligibility.to_dict()
    assert (d["amount_eur"], d["passengers"], d["total_eur"]) == (400, 3, 1200)
    assert "1200" in r.text
    f = FlightFacts(origin="LIS", destination="BER", disruption="delay", delay_hours=4, passengers=3)
    letter = draft_letter(f).text
    assert "each of the 3 passengers" in letter and "EUR 1200" in letter


def test_single_passenger_unchanged():
    d = check_facts(FlightFacts(origin="LIS", destination="BER", disruption="delay", delay_hours=4)).to_dict()
    assert (d["passengers"], d["total_eur"]) == (1, 400)


def test_inbox_counts_party_size():
    out = api("/api/inbox", {"messages": ["Family of 4, flight Lisbon to Berlin delayed 5 hours, compensation?"]})
    assert out["rows"][0]["amount"] == 1600 and out["stats"]["eur"] == 1600
