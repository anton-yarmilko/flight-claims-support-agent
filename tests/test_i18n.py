"""Tests for the 20-language support: locales, detection, triage and the API."""

import json
import re
from pathlib import Path

import pytest

from app.server import api, localize_check
from claims_agent.agent import respond
from claims_agent.i18n import LANGUAGES, native_names, strings, t
from claims_agent.language import detect_language
from claims_agent.triage import Action, triage

LOCALES = Path(__file__).resolve().parent.parent / "claims_agent" / "locales"
INDEX = Path(__file__).resolve().parent.parent / "app" / "static" / "index.html"
EN = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))


def test_twenty_languages_have_a_locale_file():
    assert len(LANGUAGES) == 20
    assert sorted(p.stem for p in LOCALES.glob("*.json")) == sorted(LANGUAGES)


@pytest.mark.parametrize("lang", sorted(LANGUAGES))
def test_locale_has_every_key_and_same_placeholders(lang):
    data = json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    assert set(data) == set(EN), set(data) ^ set(EN)
    for key, text in EN.items():
        assert set(re.findall(r"{(\w+)}", data[key])) == set(re.findall(r"{(\w+)}", text)), key


@pytest.mark.parametrize("lang", sorted(LANGUAGES))
def test_bot_templates_detect_as_their_own_language(lang):
    for key in ("holding", "fee", "status", "documents"):
        assert detect_language(t(lang, key)) == lang, (key, t(lang, key))


def _ui_samples() -> dict[str, str]:
    js = INDEX.read_text(encoding="utf-8")
    block = js[js.index("SAMPLE_BY_LANG"):]
    block = block[block.index("{"):block.index("};") + 1]
    return dict(re.findall(r'(\w{2}):\s*"((?:[^"\\]|\\.)*)"', block))


def test_every_language_has_a_ui_sample():
    assert set(_ui_samples()) == set(LANGUAGES)


@pytest.mark.parametrize("lang,text", sorted(_ui_samples().items()))
def test_ui_sample_is_detected_and_answered_in_its_language(lang, text):
    assert detect_language(text) == lang
    reply = respond(text)
    assert reply.language == lang
    assert reply.decision.intent == "eligibility"
    assert reply.eligibility is not None and not reply.eligibility.missing


@pytest.mark.parametrize("text", [
    "Je vais saisir le tribunal si vous ne payez pas",          # fr
    "Ich werde Sie verklagen",                                   # de
    "Złożę pozew do sądu",                                       # pl
    "Подам в суд на вашу компанию",                              # ru
])
def test_legal_threats_go_to_a_human_in_any_language(text):
    assert triage(text).action is Action.HUMAN_HANDOFF


def test_russian_risk_is_not_a_lawsuit():
    assert triage("Какой риск, если я подам заявку?").intent != "legal_threat"


def test_localized_eligibility_check():
    out = localize_check({"eligible": None, "missing": ["how late you arrived at the final destination"], "reason": ""}, "uk")
    assert out["missing"] and out["missing"][0] == t("uk", "m_delay")
    assert localize_check({"missing": ["x"]}, "en") == {"missing": ["x"]}


def test_i18n_endpoints_data():
    names = native_names()
    assert names["uk"] == strings("uk")["_name"] and names["en"]
    assert strings("de")["tab_chat"] != strings("en")["tab_chat"]
    out = api("/api/eligibility", {"origin": "LIS", "destination": "WAW", "airline": "FR",
                                    "disruption": "cancellation", "notice_days": 2, "lang": "pl"})
    assert out["eligible"] is True


def test_positive_reason_is_translated():
    out = localize_check({"eligible": True, "missing": [],
                          "reason": "Likely eligible: EUR 400 per passenger before the service fee."}, "uk")
    assert out["reason"] == t("uk", "rs_likely", amount="400")


def test_new_route_in_a_later_message_wins_over_history():
    history = [{"role": "user", "content": "Мій рейс з Варшави до Барселони затримали на 5 годин."},
               {"role": "assistant", "content": "..."}]
    reply = respond("Η πτήση μου από Αθήνα προς Βερολίνο καθυστέρησε 5 ώρες, δικαιούμαι αποζημίωση;", history)
    assert reply.facts.origin == "ATH" and reply.facts.destination == "BER"


def test_earlier_facts_still_fill_gaps():
    history = [{"role": "user", "content": "My flight from Lisbon to Berlin was delayed"},
               {"role": "assistant", "content": "..."}]
    reply = respond("It was 4 hours late", history)
    assert reply.facts.origin == "LIS" and reply.facts.delay_hours == 4
