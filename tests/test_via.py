"""The connecting airport is kept for the letter and the handoff note, not for the distance."""

from claims_agent.agent import handoff_note
from claims_agent.claim_letter import draft_letter
from claims_agent.facts import FlightFacts, extract_facts_rules
from claims_agent.triage import Action, Decision


def test_extraction_keeps_via():
    f = extract_facts_rules("Warsaw via Frankfurt to Lisbon, 5 hours late")
    assert (f.origin, f.destination, f.via) == ("WAW", "LIS", "FRA")
    assert extract_facts_rules("Lisbon to Berlin, 4 hours late").via is None


def test_letter_mentions_connection():
    f = FlightFacts(origin="WAW", destination="LIS", via="FRA", disruption="delay", delay_hours=5,
                    flight_number="LO123", date="2026-10-01", passenger="Anna Nowak")
    letter = draft_letter(f)
    assert "connecting in Frankfurt (FRA)" in letter.text
    assert "EUR 400" in letter.text


def test_handoff_note_lists_via():
    f = FlightFacts(origin="WAW", destination="LIS", via="FRA")
    note = handoff_note(Decision("payment_issue", Action.HUMAN_HANDOFF), "where is my money", f)
    assert "via=FRA" in note


def test_api_accepts_via():
    from app.server import facts_from

    assert facts_from({"via": "fra, muc"}).via == "FRA,MUC"
    assert facts_from({"via": "12"}).via is None
