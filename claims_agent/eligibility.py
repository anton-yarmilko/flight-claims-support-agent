"""EU261 eligibility check, simplified for first-line support.

Pure functions, no I/O, so the rules can be tested directly. This is a support
aid that tells the agent what to say next; it is not legal advice and it skips
edge cases (re-routing reductions, denied-boarding nuances, UK261 differences).
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


@dataclass(frozen=True)
class Incident:
    kind: Disruption
    arrival_delay_hours: float = 0.0
    cancellation_notice_days: int | None = None
    extraordinary_circumstances: bool = False


@dataclass(frozen=True)
class Verdict:
    eligible: bool
    amount_eur: int
    reason: str


def covered_by_eu261(flight: Flight) -> bool:
    """Departing the EU on any airline, or arriving in the EU on an EU airline."""
    return flight.departs_eu or (flight.arrives_eu and flight.eu_carrier)


def compensation_band(flight: Flight) -> int:
    """Fixed amount by distance band (Article 7)."""
    if flight.distance_km <= 1500:
        return 250
    if flight.intra_eu or flight.distance_km <= 3500:
        return 400
    return 600


def check(flight: Flight, incident: Incident) -> Verdict:
    if not covered_by_eu261(flight):
        return Verdict(False, 0, "Route not covered by EU261 (non-EU departure on a non-EU airline).")

    if incident.extraordinary_circumstances:
        return Verdict(False, 0, "Airline cites extraordinary circumstances; needs a human review of the evidence.")

    if incident.kind is Disruption.DELAY and incident.arrival_delay_hours < 3:
        return Verdict(False, 0, "Arrival delay under 3 hours.")

    if (
        incident.kind is Disruption.CANCELLATION
        and incident.cancellation_notice_days is not None
        and incident.cancellation_notice_days >= 14
    ):
        return Verdict(False, 0, "Cancellation announced 14 or more days before departure.")

    amount = compensation_band(flight)
    return Verdict(True, amount, f"Likely eligible: EUR {amount} per passenger before the service fee.")
