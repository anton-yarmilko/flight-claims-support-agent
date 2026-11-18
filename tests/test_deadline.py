"""Flights over 2 years old go to a person (claim deadlines differ by country)."""

import datetime as dt

from claims_agent.agent import TOO_OLD_REASON, respond
from claims_agent.claim_letter import draft_letter
from claims_agent.facts import FlightFacts, check_facts, parse_date
from claims_agent.inbox import process

TODAY = dt.date(2026, 11, 18)


def test_parse_date_formats():
    assert parse_date("2024-03-12") == dt.date(2024, 3, 12)
    assert parse_date("12.03.2024") == dt.date(2024, 3, 12)
    assert parse_date("12/03/24") == dt.date(2024, 3, 12)
    assert parse_date("12 mar 2024") == dt.date(2024, 3, 12)
    assert parse_date("3 September 2023") == dt.date(2023, 9, 3)
    assert parse_date("31.02.2024") is None
    assert parse_date("next tuesday") is None
    assert parse_date(None) is None


def facts(date):
    return FlightFacts(origin="WAW", destination="LIS", disruption="delay", delay_hours=4, date=date,
                       flight_number="LO123", passenger="Anna Nowak")


def test_check_flags_old_flight_only():
    old = check_facts(facts("2023-05-01"), today=TODAY)
    assert old.too_old and old.flight_date == "2023-05-01"
    assert old.verdict.eligible  # the check still runs; only the deadline needs a person
    recent = check_facts(facts("2026-05-01"), today=TODAY)
    assert not recent.too_old
    assert not check_facts(facts(None), today=TODAY).too_old
    assert check_facts(facts("2023-05-01"), today=TODAY).to_dict()["too_old"] is True


def test_chat_hands_off_old_flight():
    r = respond("My flight Warsaw to Lisbon on 2021-06-10 arrived 5 hours late. Can I claim compensation?")
    assert r.decision.action.value == "human_handoff"
    assert TOO_OLD_REASON in r.decision.reasons
    assert r.eligibility is not None and r.eligibility.too_old
    assert "claim deadline" in r.handoff_note


def test_chat_answers_recent_flight():
    when = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    r = respond(f"My flight Warsaw to Lisbon on {when} arrived 5 hours late. Can I claim compensation?")
    assert r.decision.action.value == "ai_answer"


def test_letter_not_ready_for_old_flight():
    letter = draft_letter(facts("2023-05-01"), today=TODAY)
    assert not letter.ready
    assert any("2 years" in n for n in letter.notes)
    assert draft_letter(facts("2026-05-01"), today=TODAY).ready


def test_inbox_reason_code():
    out = process([{"message": "Flight Warsaw to Lisbon on 01.02.2020 was 6 hours late, do I get compensation?"}])
    assert out["rows"][0]["handoff"] == ["old"]
    assert out["stats"]["handoff_reasons"] == {"old": 1}
