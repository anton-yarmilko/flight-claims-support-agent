import pytest

from claims_agent.eligibility import Disruption, Flight, Incident, check, compensation_band

SHORT = Flight(departs_eu=True, arrives_eu=True, eu_carrier=True, distance_km=1200, intra_eu=True)
INTRA_LONG = Flight(departs_eu=True, arrives_eu=True, eu_carrier=True, distance_km=3900, intra_eu=True)
MEDIUM = Flight(departs_eu=True, arrives_eu=False, eu_carrier=False, distance_km=2800)
LONG = Flight(departs_eu=True, arrives_eu=False, eu_carrier=False, distance_km=7000)


@pytest.mark.parametrize(
    "flight, amount",
    [(SHORT, 250), (MEDIUM, 400), (INTRA_LONG, 400), (LONG, 600)],
)
def test_distance_bands(flight, amount):
    assert compensation_band(flight) == amount


def test_delay_of_three_hours_is_eligible():
    v = check(SHORT, Incident(Disruption.DELAY, arrival_delay_hours=3.0))
    assert v.eligible and v.amount_eur == 250


def test_delay_under_three_hours_is_not():
    assert not check(LONG, Incident(Disruption.DELAY, arrival_delay_hours=2.9)).eligible


def test_inbound_on_non_eu_airline_not_covered():
    flight = Flight(departs_eu=False, arrives_eu=True, eu_carrier=False, distance_km=5000)
    v = check(flight, Incident(Disruption.DELAY, arrival_delay_hours=6))
    assert not v.eligible and "not covered" in v.reason


def test_inbound_on_eu_airline_covered():
    flight = Flight(departs_eu=False, arrives_eu=True, eu_carrier=True, distance_km=5000)
    assert check(flight, Incident(Disruption.DELAY, arrival_delay_hours=6)).amount_eur == 600


def test_extraordinary_circumstances_need_human():
    v = check(MEDIUM, Incident(Disruption.CANCELLATION, extraordinary_circumstances=True))
    assert not v.eligible and "human" in v.reason


def test_cancellation_with_two_weeks_notice():
    assert not check(MEDIUM, Incident(Disruption.CANCELLATION, cancellation_notice_days=14)).eligible
    assert check(MEDIUM, Incident(Disruption.CANCELLATION, cancellation_notice_days=3)).eligible


def test_denied_boarding_eligible():
    assert check(LONG, Incident(Disruption.DENIED_BOARDING)).amount_eur == 600
