"""Airline names that are everyday words must not be read as airlines."""

import pytest

from claims_agent.agent import respond
from claims_agent.airports import airline_in_text


@pytest.mark.parametrize("text,code", [
    ("Mój lot z Warszawy do Barcelony opóźniony 5 godzin", None),  # "lot" = "flight" in Polish
    ("tap water", None),
    ("MÓJ LOT Z WARSZAWY", None),  # all caps: cannot tell
    ("Leciałem LOT-em z Warszawy", "LO"),
    ("liniami PLL LOT", "LO"),
    ("LOT Polish Airlines", "LO"),
    ("TAP flight from Lisbon", "TP"),
    ("Ryanair z Krakowa", "FR"),
])
def test_airline_in_text(text, code):
    assert airline_in_text(text) == code


def test_polish_flight_into_eu_asks_for_the_airline():
    # Used to read "lot" as LOT (an EU airline) and promise compensation for New York - Warsaw.
    r = respond("Mój lot z Nowego Jorku do Warszawy był opóźniony 5 godzin. Czy należy mi się odszkodowanie?")
    assert r.facts.airline is None
    assert r.eligibility.verdict is None and r.eligibility.missing
