"""EU261 counts the arrival delay; a departure-only delay gets a one-line reminder."""

import pytest

from claims_agent.agent import respond
from claims_agent.causes import departure_only
from claims_agent.i18n import LANGUAGES, strings


@pytest.mark.parametrize("text,expected", [
    ("Our flight from Warsaw to Barcelona departed 4 hours late", True),
    ("Рейс з Варшави до Барселони вилетів на 4 години пізніше", True),
    ("Lot z Warszawy wyleciał 4 godziny później", True),
    ("Der Abflug war 4 Stunden verspätet", True),
    ("Le vol a décollé avec 4 heures de retard", True),
    ("departed 4 hours late and arrived 3 hours late", False),
    ("рейс прибув на 5 годин пізніше", False),
    ("My flight from Lisbon to Berlin was delayed 5 hours", False),
    ("We landed 5 hours late", False),
])
def test_departure_only(text, expected):
    assert departure_only(text) is expected


def test_every_language_has_the_note():
    assert all(strings(lang).get("dep_only") for lang in LANGUAGES)


def test_reply_adds_arrival_reminder():
    r = respond("Our Ryanair flight from Warsaw to Barcelona departed 4 hours late. Can I claim?")
    assert r.eligibility.verdict.eligible and r.eligibility.departure_only
    assert "how late you arrived" in r.text


def test_no_reminder_when_arrival_given():
    r = respond("Our Ryanair flight from Warsaw to Barcelona arrived 4 hours late. Can I claim?")
    assert not r.eligibility.departure_only and "how late you arrived" not in r.text


def test_ukrainian_reminder():
    r = respond("Рейс з Варшави до Барселони вилетів на 4 години пізніше. Чи є компенсація?")
    assert r.eligibility.departure_only and "прибули" in r.text
