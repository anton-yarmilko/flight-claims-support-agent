"""Inbox batch view and the long-haul delay rule."""

from app.server import api
from claims_agent.eligibility import Disruption, Flight, Incident, check
from claims_agent.inbox import process, sample_messages

LONG_HAUL = Flight(departs_eu=True, arrives_eu=False, eu_carrier=True, distance_km=5800)


def test_sample_inbox_stats_add_up():
    out = process(sample_messages())
    s = out["stats"]
    assert s["total"] == len(out["rows"]) == len(sample_messages())
    assert s["ai"] + s["human"] == s["total"]
    assert s["languages"] == 20
    assert s["agrees"] == s["labelled"] > 0
    assert sum(s["handoff_reasons"].values()) >= s["human"]
    assert s["eur"] == sum(r["amount"] for r in out["rows"]) > 0


def test_inbox_endpoint_takes_own_messages():
    out = api("/api/inbox", {"messages": ["I will sue you", "", "What is your fee?"]})
    rows = out["rows"]
    assert [r["action"] for r in rows] == ["human_handoff", "ai_answer"]
    assert rows[0]["handoff"] == ["legal"] and rows[0]["priority"] == "high"


def test_inbox_endpoint_defaults_to_sample():
    assert api("/api/inbox", {})["stats"]["total"] == len(sample_messages())


def test_long_haul_delay_between_3_and_4_hours_is_halved():
    assert check(LONG_HAUL, Incident(Disruption.DELAY, arrival_delay_hours=3.5)).amount_eur == 300
    assert check(LONG_HAUL, Incident(Disruption.DELAY, arrival_delay_hours=4)).amount_eur == 600
    assert check(LONG_HAUL, Incident(Disruption.CANCELLATION, cancellation_notice_days=2)).amount_eur == 600
