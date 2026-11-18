"""Article 5(1)(c)(ii)/(iii): notice plus a close replacement flight means no compensation."""

from claims_agent.agent import respond, template_reply
from claims_agent.eligibility import Disruption, Flight, Incident, check
from claims_agent.facts import FlightFacts, check_facts

SHORT = Flight(departs_eu=True, arrives_eu=True, eu_carrier=True, distance_km=900, intra_eu=True)
LONG = Flight(departs_eu=True, arrives_eu=False, eu_carrier=True, distance_km=7000)


def cancel(notice, late):
    return Incident(Disruption.CANCELLATION, cancellation_notice_days=notice, reroute_arrival_delay_hours=late)


def test_seven_to_thirteen_days_and_within_four_hours():
    for notice, late in [(7, 4), (13, 0.5), (10, 3)]:
        v = check(LONG, cancel(notice, late))
        assert not v.eligible and "5(1)(c)(ii)" in v.reason, (notice, late)


def test_seven_to_thirteen_days_but_later_than_four_hours_is_full():
    assert check(LONG, cancel(10, 4.5)).amount_eur == 600


def test_under_seven_days_and_under_two_hours():
    v = check(SHORT, cancel(3, 1.5))
    assert not v.eligible and "5(1)(c)(iii)" in v.reason


def test_under_seven_days_two_hours_or_more_uses_halving_or_full():
    assert check(LONG, cancel(3, 3)).amount_eur == 300  # within 4 h on long haul: Article 7(2) half
    assert check(SHORT, cancel(3, 2.5)).amount_eur == 250


def test_unknown_notice_or_arrival_keeps_old_rules():
    assert check(SHORT, cancel(None, 1.5)).amount_eur == 125
    assert check(SHORT, cancel(10, None)).amount_eur == 250


def test_reply_is_translated():
    r = check_facts(FlightFacts(origin="WAW", destination="LIS", disruption="cancellation",
                                notice_days=10, delay_hours=3))
    assert not r.verdict.eligible
    assert "7-13 days" in template_reply("eligibility", "en", r)
    assert "7-13 днів" in template_reply("eligibility", "uk", r)


def test_chat_end_to_end():
    r = respond("Our flight Warsaw to Lisbon was cancelled 10 days before departure, "
                "the new flight arrived 3 hours late. Can we claim?")
    assert r.eligibility.verdict is not None and not r.eligibility.verdict.eligible
    assert "7-13" in r.text
