"""Fact extraction on phrasings real customers use: accents, inflections, spelled-out numbers."""

import pytest

from claims_agent.facts import extract_facts_rules as extract


@pytest.mark.parametrize("text,origin,dest", [
    ("Рейс Київ - Варшава затримали на 4,5 години", "KBP", "WAW"),
    ("vuelo de Barcelona a Ámsterdam con retraso de tres horas", "BCN", "AMS"),
    ("Mein Flug von Köln nach Palma wurde 10 Tage vorher annulliert", "CGN", "PMI"),
    ("flight Thessaloniki to Bratislava delayed 5 hours", "SKG", "BTS"),
    ("Volo da Napoli a Siviglia in ritardo di 4 ore", "NAP", "SVQ"),
    ("Lot z Poznania do Edynburga opóźniony o 3 godziny", "POZ", "EDI"),
    ("Mon vol de Lyon à Tenerife a eu 4 heures de retard", "LYS", "TFS"),
])
def test_routes(text, origin, dest):
    f = extract(text)
    assert (f.origin, f.destination) == (origin, dest)


@pytest.mark.parametrize("text,hours", [
    ("vuelo con retraso de tres horas", 3.0),
    ("Our flight was delayed four hours", 4.0),
    ("Lot opóźniony o cztery godziny", 4.0),
    ("Рейс затримали на чотири години", 4.0),
    ("Il volo è arrivato con tre ore di ritardo", 3.0),
    ("Ich hatte drei Stunden Verspätung", 3.0),
    ("delayed 3h 20min", 3 + 20 / 60),
    ("one of the flights was delayed", None),
])
def test_delay_hours(text, hours):
    got = extract(text).delay_hours
    assert got == pytest.approx(hours) if hours is not None else got is None


@pytest.mark.parametrize("text", [
    "Have a nice day, thanks for the help",
    "I SAW HER FLIGHT AND THE MAN WAS LATE",
    "Can I get a barista job?",
])
def test_common_words_are_not_airports(text):
    f = extract(text)
    assert f.origin is None and f.destination is None
