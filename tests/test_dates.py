"""Relative flight dates, future dates and the EU261 numbers in the handoff note."""

import datetime as dt

from claims_agent.agent import respond
from claims_agent.facts import (
    FUTURE_FLIGHT,
    FlightFacts,
    check_facts,
    extract_facts,
    extract_facts_rules,
    relative_date,
)
from claims_agent.llm import LLM

TODAY = dt.date(2026, 11, 18)


def test_relative_dates_many_languages():
    assert relative_date("my flight yesterday was 4 hours late", TODAY) == "2026-11-17"
    assert relative_date("рейс позавчора затримали", TODAY) == "2026-11-16"
    assert relative_date("lot wczoraj był opóźniony", TODAY) == "2026-11-17"
    assert relative_date("der flug gestern", TODAY) == "2026-11-17"
    assert relative_date("ich bin hier", TODAY) is None  # German "here", not French "yesterday"
    assert relative_date("flying today", TODAY) is None


def test_explicit_date_wins_over_relative():
    f = extract_facts_rules("Yesterday I remembered my flight on 2026-10-01 was cancelled", TODAY)
    assert f.date == "2026-10-01"


def test_future_date_asks_for_a_past_flight():
    f = FlightFacts(origin="WAW", destination="LIS", disruption="delay", delay_hours=4, date="2026-12-24")
    r = check_facts(f, today=TODAY)
    assert r.verdict is None and r.missing == [FUTURE_FLIGHT]
    assert r.flight_date == "2026-12-24"


def test_chat_future_date_localised():
    when = (dt.date.today() + dt.timedelta(days=40)).isoformat()
    r = respond(f"Mój lot z Warszawy do Lizbony {when} będzie opóźniony o 5 godzin, czy dostanę odszkodowanie?")
    assert r.eligibility is not None and r.eligibility.missing == [FUTURE_FLIGHT]
    assert "przyszłości" in r.text


def test_handoff_note_carries_check():
    r = respond("I want my money now! Flight Warsaw to Lisbon was 5 hours late and you still have not paid")
    assert r.decision.action.value == "human_handoff"
    assert "EU261 CHECK" in r.handoff_note and "EUR 400" in r.handoff_note


class FakeLLM(LLM):
    def __init__(self, data):
        super().__init__(base_url="http://x", api_key="k", model="m")
        self._data = data

    def chat_json(self, messages, **kw):
        return self._data


def test_llm_invented_year_is_dropped():
    text = "My flight Warsaw to Lisbon on 12 March was 5 hours late"
    f = extract_facts(text, FakeLLM({"date": "2023-03-12"}))
    assert f.date is None
    f = extract_facts("Flight Warsaw to Lisbon, 12 March 2023, 5 hours late", FakeLLM({"date": "2023-03-12"}))
    assert f.date  # the year is in the text, so a date is kept
