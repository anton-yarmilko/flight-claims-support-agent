"""EU261 eligibility check, simplified for first-line support.

Pure functions, no I/O, so the rules can be tested directly. This is a support
aid that tells the agent what to say next; it is not legal advice and it skips
edge cases (denied-boarding nuances). Flights EU261 does not cover but the UK's
own UK261 does (departing the UK, or arriving in the UK on a UK or EU airline)
get the UK261 amounts in pounds: GBP 220, 350 or 520. It applies the Article
7(2)(c) halving for long-haul delays of 3 to 4 hours, and the Article 7(2) halving
when a cancelled or denied passenger was re-routed and arrived within 2, 3 or 4
hours, depending on the distance band. A cancellation announced 7-13 days ahead
with a replacement arriving within 4 hours, or under 7 days ahead with one arriving
less than 2 hours late, is not compensated (Article 5(1)(c)(ii) and (iii)).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Disruption(str, Enum):
    DELAY = "delay"
    CANCELLATION = "cancellation"
    DENIED_BOARDING = "denied_boarding"


@dataclass(frozen=True)
class Flight:
    departs_eu: bool
    arrives_eu: bool
    eu_carrier: bool
    distance_km: int
    intra_eu: bool = False
    departs_uk: bool = False
    arrives_uk: bool = False
    uk_carrier: bool = False


@dataclass(frozen=True)
class Incident:
    kind: Disruption
    arrival_delay_hours: float = 0.0
    cancellation_notice_days: int | None = None
    extraordinary_circumstances: bool = False
    # Cancellation / denied boarding: how late the replacement flight reached the final destination.
    reroute_arrival_delay_hours: float | None = None
    # Denied boarding: the passenger gave up the seat in exchange for benefits (Article 4(1)).
    voluntary: bool = False


@dataclass(frozen=True)
class Verdict:
    eligible: bool
    amount_eur: int  # the amount in `currency`; the name predates UK261 support
    reason: str
    currency: str = "EUR"
    regulation: str = "EU261"


def covered_by_eu261(flight: Flight) -> bool:
    """Departing the EU on any airline, or arriving in the EU on an EU airline."""
    return flight.departs_eu or (flight.arrives_eu and flight.eu_carrier)


def covered_by_uk261(flight: Flight) -> bool:
    """UK261: departing the UK on any airline, or arriving in the UK on a UK or EU airline."""
    return flight.departs_uk or (flight.arrives_uk and (flight.uk_carrier or flight.eu_carrier))


# UK261 Article 7 amounts in pounds, keyed by the EU261 band they replace.
UK_AMOUNTS = {250: 220, 400: 350, 600: 520}


def compensation_band(flight: Flight) -> int:
    """Fixed amount by distance band (Article 7)."""
    if flight.distance_km <= 1500:
        return 250
    if flight.intra_eu or flight.distance_km <= 3500:
        return 400
    return 600


# Article 7(2): re-routed arrival within this many hours halves the amount, by distance band.
REROUTE_LIMIT_HOURS = {250: 2, 400: 3, 600: 4}


def check(flight: Flight, incident: Incident) -> Verdict:
    if covered_by_eu261(flight):
        currency, regulation = "EUR", "EU261"
    elif covered_by_uk261(flight):
        currency, regulation = "GBP", "UK261"
    else:
        return Verdict(False, 0, "Route not covered by EU261 or UK261 (departure outside the EU and the UK "
                                 "on an airline from outside the EU and the UK).")

    def no(reason: str) -> Verdict:
        return Verdict(False, 0, reason, currency, regulation)

    if incident.extraordinary_circumstances:
        return no("Airline cites extraordinary circumstances; needs a human review of the evidence.")

    if incident.kind is Disruption.DENIED_BOARDING and incident.voluntary:
        return no("Passenger gave up the seat voluntarily; volunteers get the benefits agreed "
                  "with the airline, not EU261 compensation.")

    if incident.kind is Disruption.DELAY and incident.arrival_delay_hours < 3:
        return no("Arrival delay under 3 hours.")

    if (
        incident.kind is Disruption.CANCELLATION
        and incident.cancellation_notice_days is not None
        and incident.cancellation_notice_days >= 14
    ):
        return no("Cancellation announced 14 or more days before departure.")

    if incident.kind is Disruption.CANCELLATION:
        notice, late = incident.cancellation_notice_days, incident.reroute_arrival_delay_hours
        if notice is not None and late is not None:
            # Article 5(1)(c)(ii) and (iii): early enough notice plus a close replacement flight.
            if 7 <= notice < 14 and late <= 4:
                return no("Cancellation announced 7-13 days ahead and the replacement flight arrived within 4 hours "
                          "(Article 5(1)(c)(ii)); this holds if it left no more than 2 hours before the original time.")
            if notice < 7 and late < 2:
                return no("Cancellation announced under 7 days ahead and the replacement flight arrived less than "
                          "2 hours late (Article 5(1)(c)(iii)); this holds if it left no more than 1 hour before "
                          "the original time.")

    band = compensation_band(flight)
    full = UK_AMOUNTS[band] if regulation == "UK261" else band
    amount = full
    if band == 600 and incident.kind is Disruption.DELAY and incident.arrival_delay_hours < 4:
        amount = full // 2  # Article 7(2)(c): long-haul arriving 3-4 hours late gets half
    tag = " under UK261" if regulation == "UK261" else ""
    late = incident.reroute_arrival_delay_hours
    if incident.kind is not Disruption.DELAY and late is not None:
        limit = REROUTE_LIMIT_HOURS[band]
        if late <= limit:
            amount //= 2
            return Verdict(True, amount, f"Likely eligible: {currency} {amount} per passenger before the service fee "
                                         f"(halved: the replacement flight arrived within {limit} hours, Article 7(2)){tag}.",
                                         currency, regulation)
    return Verdict(True, amount, f"Likely eligible: {currency} {amount} per passenger before the service fee{tag}.",
                   currency, regulation)
