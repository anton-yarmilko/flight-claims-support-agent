"""Connecting flights: EU261 distance runs from first departure to final destination."""

import pytest

from claims_agent.airports import route_in_text
from claims_agent.facts import check_facts, extract_facts_rules
from claims_agent.triage import triage


@pytest.mark.parametrize("text", [
    "My flight from Warsaw via Frankfurt to Lisbon arrived 5 hours late",
    "Рейс з Варшави через Франкфурт до Лісабона затримали на 5 годин",
    "Lot z Warszawy przez Frankfurt do Lizbony opóźniony 5 godzin",
    "Warsaw to Lisbon with a connection in Frankfurt, 5 hours late",
    "WAW-FRA-LIS delayed 5 hours",
])
def test_connection_skipped(text):
    f = extract_facts_rules(text)
    assert (f.origin, f.destination) == ("WAW", "LIS")


def test_route_reports_connection():
    origin, destination, via = route_in_text("Flug von Berlin über München nach Rom")
    assert (origin.iata, destination.iata, [a.iata for a in via]) == ("BER", "FCO", ["MUC"])


def test_direct_route_unchanged():
    origin, destination, via = route_in_text("Lisbon to Berlin delayed 4 hours")
    assert (origin.iata, destination.iata, via) == ("LIS", "BER", [])


def test_connection_changes_amount():
    r = check_facts(extract_facts_rules("Warsaw via Frankfurt to Lisbon, arrived 5 hours late"))
    assert r.verdict.amount_eur == 400  # Warsaw-Lisbon, not Warsaw-Frankfurt (250)


def test_arrived_late_is_an_eligibility_question():
    assert triage("We arrived 5 hours late in Lisbon, can I claim?").intent == "eligibility"


def test_llm_city_names_are_normalised():
    from claims_agent.facts import FlightFacts, merge_llm_facts

    f = merge_llm_facts(FlightFacts(), {"origin": "the Warsaw airport", "destination": "Lisboa"})
    assert (f.origin, f.destination) == ("WAW", "LIS")
