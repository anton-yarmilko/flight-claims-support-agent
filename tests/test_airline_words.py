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


def test_country_is_not_the_airline_emirates():
    assert airline_in_text("Dubai, United Arab Emirates to Paris") is None
    assert airline_in_text("Emirates flight from Dubai") == "EK"


def test_first_named_airline_wins():
    assert airline_in_text("My Emirates flight was cancelled; next time I fly Lufthansa") == "EK"
    assert airline_in_text("Flew Lufthansa, never Emirates again") == "LH"
    assert airline_in_text("easyJet Europe from Berlin") == "EJU"


def test_abu_dhabi_and_etihad():
    r = respond("Flew from Abu Dhabi to Rome with Etihad, delay 5 hours")
    assert r.eligibility.to_dict()["route"] == "Abu Dhabi - Rome"
    assert not r.eligibility.verdict.eligible
    r = respond("Flew Abu Dhabi to Rome with Lufthansa, delay 5 hours")
    assert r.eligibility.verdict.amount_eur == 600


@pytest.mark.parametrize("text,code", [
    ("Booked with Lufthansa, operated by United Airlines", "UA"),
    ("United Airlines flight operated by Lufthansa", "LH"),
    ("Квиток Lufthansa, рейс виконувала United Airlines", "UA"),
    ("Gebucht bei Lufthansa, durchgeführt von United Airlines", "UA"),
    ("Vol Air France opéré par Delta Air Lines", "DL"),
    ("Lufthansa bileti, United Airlines tarafından işletilen uçuş", "UA"),
    ("Flew Ryanair. The airline operated by its own rules", "FR"),
])
def test_operating_airline_counts(text, code):
    assert airline_in_text(text) == code


def test_codeshare_into_eu_follows_operating_airline():
    r = respond("My Lufthansa flight, operated by United Airlines, from New York to Frankfurt was delayed 5 hours")
    assert not r.eligibility.verdict.eligible
    r = respond("My United flight, operated by Lufthansa, from New York to Frankfurt was delayed 5 hours")
    assert r.eligibility.verdict.amount_eur == 600
