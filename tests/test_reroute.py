"""Article 7(2): re-routed passengers who arrive soon after the original time get half."""

from claims_agent.agent import respond, template_reply
from claims_agent.claim_letter import draft_letter
from claims_agent.eligibility import Disruption, Flight, Incident, check
from claims_agent.facts import FlightFacts, check_facts, extract_facts_rules

SHORT = Flight(departs_eu=True, arrives_eu=True, eu_carrier=True, distance_km=900, intra_eu=True)
MEDIUM = Flight(departs_eu=True, arrives_eu=True, eu_carrier=True, distance_km=2800, intra_eu=True)
LONG = Flight(departs_eu=True, arrives_eu=False, eu_carrier=True, distance_km=7000)


def cancel(late):
    return Incident(Disruption.CANCELLATION, reroute_arrival_delay_hours=late)  # notice unknown


def test_halving_by_band():
    assert check(SHORT, cancel(1.5)).amount_eur == 125
    assert check(SHORT, cancel(2.5)).amount_eur == 250
    assert check(MEDIUM, cancel(3)).amount_eur == 200
    assert check(MEDIUM, cancel(3.5)).amount_eur == 400
    assert check(LONG, cancel(4)).amount_eur == 300
    assert check(LONG, cancel(None)).amount_eur == 600  # unknown arrival: full amount
    denied = Incident(Disruption.DENIED_BOARDING, reroute_arrival_delay_hours=1)
    assert check(SHORT, denied).amount_eur == 125


def test_delay_is_unchanged():
    assert check(SHORT, Incident(Disruption.DELAY, arrival_delay_hours=3)).amount_eur == 250


def test_extraction_reads_replacement_arrival_but_not_notice():
    f = extract_facts_rules("Flight Warsaw to Lisbon was cancelled, we arrived 2 hours late on another flight")
    assert f.disruption == "cancellation" and f.delay_hours == 2
    f = extract_facts_rules("Flight Warsaw to Lisbon was cancelled 2 hours before departure")
    assert f.disruption == "cancellation" and f.delay_hours is None


def test_reply_and_letter_use_half():
    facts = FlightFacts(origin="WAW", destination="BER", disruption="cancellation", delay_hours=1.5,
                        flight_number="LO123", date="2026-10-01", passenger="Anna Nowak")
    result = check_facts(facts)
    assert result.verdict.amount_eur == 125
    assert "125" in template_reply("eligibility", "en", result)
    uk = template_reply("eligibility", "uk", result)
    assert "125" in uk and "половина" in uk
    letter = draft_letter(facts)
    assert "EUR 125" in letter.text and "replacement flight" in letter.text


def test_chat_end_to_end():
    r = respond("My flight Warsaw to Berlin was cancelled and the new flight arrived 1 hour late. Compensation?")
    assert r.eligibility.verdict.amount_eur == 125
