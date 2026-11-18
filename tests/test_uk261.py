"""UK261: flights from the UK, or into the UK on a UK or EU airline, get the pound amounts."""

from claims_agent.agent import template_reply
from claims_agent.claim_letter import draft_letter
from claims_agent.eligibility import Disruption, Flight, Incident, check
from claims_agent.facts import FlightFacts, check_facts
from claims_agent.inbox import process

DELAY5 = Incident(Disruption.DELAY, arrival_delay_hours=5)


def facts(o, d, airline=None, **kw):
    base = dict(origin=o, destination=d, airline=airline, disruption="delay", delay_hours=5)
    base.update(kw)
    return FlightFacts(**base)


def test_uk_departure_long_haul_is_gbp_520():
    v = check(Flight(False, False, False, 5540, departs_uk=True), DELAY5)
    assert v.eligible and (v.amount_eur, v.currency, v.regulation) == (520, "GBP", "UK261")
    assert "GBP 520" in v.reason and "UK261" in v.reason


def test_uk_bands_and_halving():
    assert check(Flight(False, False, False, 900, departs_uk=True), DELAY5).amount_eur == 220
    assert check(Flight(False, False, False, 2500, departs_uk=True), DELAY5).amount_eur == 350
    long_3h = Incident(Disruption.DELAY, arrival_delay_hours=3.5)
    assert check(Flight(False, False, False, 5540, departs_uk=True), long_3h).amount_eur == 260
    rerouted = Incident(Disruption.CANCELLATION, reroute_arrival_delay_hours=1.5)
    v = check(Flight(False, False, False, 900, departs_uk=True), rerouted)
    assert v.amount_eur == 110 and "halved" in v.reason


def test_into_uk_needs_uk_or_eu_airline():
    assert check(Flight(False, False, True, 5540, arrives_uk=True), DELAY5).currency == "GBP"
    assert check(Flight(False, False, False, 5540, arrives_uk=True, uk_carrier=True), DELAY5).eligible
    v = check(Flight(False, False, False, 5540, arrives_uk=True), DELAY5)
    assert not v.eligible and "not covered" in v.reason


def test_eu_departure_to_uk_stays_eu261():
    v = check(Flight(True, False, True, 1500, arrives_uk=True), DELAY5)
    assert (v.currency, v.regulation, v.amount_eur) == ("EUR", "EU261", 250)


def test_uk_to_eu_on_eu_airline_uses_eu261():
    v = check(Flight(False, True, True, 1000, departs_uk=True), DELAY5)
    assert (v.currency, v.amount_eur) == ("EUR", 250)


def test_london_new_york_from_facts():
    r = check_facts(facts("LHR", "JFK", "BA"))
    assert r.verdict.eligible and r.verdict.currency == "GBP" and r.verdict.amount_eur == 520
    d = r.to_dict()
    assert d["currency"] == "GBP" and d["regulation"] == "UK261"


def test_new_york_london_on_us_airline_not_covered_and_on_ba_covered():
    assert not check_facts(facts("JFK", "LHR", "UA")).verdict.eligible
    assert check_facts(facts("JFK", "LHR", "BA")).verdict.amount_eur == 520
    assert check_facts(facts("JFK", "LHR")).missing  # airline needed for flights into the UK


def test_reply_shows_pounds_and_note_in_any_language():
    r = check_facts(facts("LHR", "JFK", "BA", passengers=2))
    en = template_reply("eligibility", "en", r)
    assert "GBP 520" in en and "GBP 1040" in en and "UK261" in en and "EUR" not in en
    uk = template_reply("eligibility", "uk", r)
    assert "GBP 520" in uk and "UK261" in uk


def test_eu_reply_unchanged():
    en = template_reply("eligibility", "en", check_facts(facts("WAW", "BCN")))
    assert "EUR 400" in en and "UK261" not in en


def test_letter_uses_pounds_and_uk_regulation():
    letter = draft_letter(facts("LHR", "JFK", "BA", flight_number="BA117", date="2026-03-01",
                                passenger="Jane Doe", booking_ref="ABC123"))
    assert "GBP 520" in letter.text and "UK261" in letter.text and "EUR" not in letter.text


def test_inbox_sums_currencies_separately():
    out = process([{"message": "My BA flight from London to New York was 5 hours late, can I claim?"},
                     {"message": "Wizz Air flight from Warsaw to Barcelona arrived 4 hours late, can I claim?"}])
    s = out["stats"]
    assert s["gbp"] == 520 and s["eur"] == 400
