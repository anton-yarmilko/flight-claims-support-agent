"""A cause the customer names adds one expectation-setting sentence; the verdict stays."""

import pytest

from claims_agent.agent import respond, template_reply
from claims_agent.causes import cause_in_text
from claims_agent.facts import extract_facts_rules
from claims_agent.i18n import LANGUAGES, strings


@pytest.mark.parametrize("text,cause", [
    ("delayed 5 hours because of a technical problem", "technical"),
    ("рейс затримали через технічну несправність", "technical"),
    ("Il volo è stato cancellato per un guasto", "technical"),
    ("the pilots were on strike", "strike_staff"),
    ("Streik der Piloten", "strike_staff"),
    ("air traffic control strike in France", "strike_atc"),
    ("страйк диспетчерів", "strike_atc"),
    ("strajk kontrolerów ruchu lotniczego", "strike_atc"),
    ("huelga de controladores aéreos", "strike_atc"),
    ("grève", "strike"),
    ("because of the snow storm", "weather"),
    ("через туман", "weather"),
    ("wegen Nebel", "weather"),
    ("kvůli bouřce", "weather"),
    ("myrskyn takia", "weather"),
])
def test_cause_in_text(text, cause):
    assert cause_in_text(text) == cause


@pytest.mark.parametrize("text", [
    "My flight Warsaw to Lisbon was 5 hours late", "crisis", "14 Tage vorher annulliert",
    "kod rezerwacji ABC123", "vi var kvar i 5 timmar", "take off was late", "угроза", "luminous",
])
def test_no_false_causes(text):
    assert cause_in_text(text) is None


def test_every_language_has_every_cause_note():
    for lang in LANGUAGES:
        for cause in ("technical", "strike_staff", "strike_atc", "strike", "weather"):
            assert strings(lang).get("cause_" + cause), (lang, cause)


def test_reply_adds_note_but_keeps_amount():
    r = respond("My Ryanair flight from Warsaw to Barcelona was 5 hours late because of a technical problem. Can I claim?")
    assert r.eligibility.verdict.eligible and r.eligibility.verdict.amount_eur == 400
    assert r.eligibility.cause == "technical"
    assert "not an extraordinary circumstance" in r.text


def test_atc_strike_note_in_ukrainian():
    r = respond("Рейс з Варшави до Барселони затримали на 5 годин через страйк диспетчерів. Чи є компенсація?")
    assert r.eligibility.cause == "strike_atc" and r.eligibility.verdict.eligible
    assert "диспетчерів" in r.text and "Колега перевірить" in r.text


def test_no_note_when_not_eligible():
    f = extract_facts_rules("Flight Warsaw to Barcelona 2 hours late because of fog")
    assert f.cause == "weather"
    from claims_agent.facts import check_facts
    res = check_facts(f)
    assert not res.verdict.eligible
    assert "weather" not in template_reply("eligibility", "en", res)


def test_cause_in_dict_and_handoff_note():
    r = respond("My flight from Warsaw to Barcelona was 5 hours late due to a pilot strike. I want my money now or I sue!")
    assert r.eligibility is not None and r.eligibility.to_dict()["cause"] == "strike_staff"
    assert "strike_staff" in (r.handoff_note or "")


@pytest.mark.parametrize("text,expected", [
    ("Flight Warsaw to Barcelona 5 hours late because of fog", ["WAW", "BCN"]),  # "because" is not Beč (Vienna)
    ("roman holiday", []),
    ("poznámka k letu", []),
    ("z Rzymu do Paryża", ["FCO", "CDG"]),
    ("з Риму до Парижа", ["FCO", "CDG"]),
    ("Flug nach Rom", ["FCO"]),
    ("do Pragi", ["PRG"]),
    ("z Poznania do Warszawy", ["POZ", "WAW"]),
])
def test_short_city_names_need_a_word_end(text, expected):
    from claims_agent.airports import _airport_hits
    assert [a.iata for _, a in _airport_hits(text)] == expected
