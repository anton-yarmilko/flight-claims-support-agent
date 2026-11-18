"""Tests for the LLM layer and the demo features.

The LLM path runs against a tiny fake OpenAI-compatible server, so no key or
network is needed and the replies are scripted.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from claims_agent import airline_reply
from claims_agent.agent import number_guard, respond
from claims_agent.claim_letter import draft_letter
from claims_agent.facts import FlightFacts, check_facts, extract_facts_rules
from claims_agent.language import detect_language
from claims_agent.llm import LLM, LLMError, get_llm, parse_json
from claims_agent.ticket import parse_bcbp, read_ticket_image
from claims_agent.triage import Action, triage

# ---------- fake LLM server ----------

class FakeLLM:
    def __init__(self):
        self.replies: list[str] = []
        self.requests: list[dict] = []
        handler = self._handler()
        self.httpd = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.client = LLM(base_url=f"http://127.0.0.1:{self.httpd.server_port}/v1", model="fake-8b",
                          api_key="test", vision_model="fake-vision")

    def _handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                content = fake.replies.pop(0) if fake.replies else "{}"
                data = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        return H


@pytest.fixture
def fake():
    f = FakeLLM()
    yield f
    f.httpd.shutdown()


# ---------- llm config ----------

def test_no_key_means_offline():
    assert get_llm({}) is None
    assert get_llm({"LLM_PROVIDER": "off", "LLM_API_KEY": "x"}) is None


def test_key_alone_uses_groq_default():
    llm = get_llm({"LLM_API_KEY": "k"})
    assert llm and "groq" in llm.base_url and llm.model == "openai/gpt-oss-20b"


def test_ollama_needs_no_key_and_model_override():
    llm = get_llm({"LLM_PROVIDER": "ollama", "LLM_MODEL": "qwen2.5:3b"})
    assert llm and llm.model == "qwen2.5:3b" and llm.api_key == ""


def test_bad_config_raises():
    with pytest.raises(LLMError):
        get_llm({"LLM_PROVIDER": "groq"})
    with pytest.raises(LLMError):
        get_llm({"LLM_PROVIDER": "nope", "LLM_API_KEY": "k"})


def test_parse_json_tolerates_fences():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"a": 2} hope it helps') == {"a": 2}


# ---------- language + multilingual triage ----------

@pytest.mark.parametrize("text,lang", [
    ("Мій рейс затримали", "uk"), ("Mój lot był opóźniony", "pl"),
    ("Mein Flug wurde annulliert", "de"), ("Mi vuelo fue cancelado", "es"), ("My flight was late", "en"),
])
def test_detect_language(text, lang):
    assert detect_language(text) == lang


def test_llm_classifies_unknown_message(fake):
    fake.replies = ['{"intent": "claim_status", "confidence": 0.9}']
    d = triage("Hola, ¿qué pasa con lo mío? Escribí hace un mes", llm=fake.client)
    assert d.intent == "claim_status" and d.source == "llm" and d.action is Action.AI_ANSWER


def test_llm_low_confidence_goes_to_human(fake):
    fake.replies = ['{"intent": "eligibility", "confidence": 0.4}']
    d = triage("hmm what about that thing", llm=fake.client)
    assert d.action is Action.HUMAN_HANDOFF and d.source == "llm"


def test_llm_cannot_override_rule_escalation(fake):
    d = triage("I will call my lawyer", llm=fake.client)
    assert d.intent == "legal_threat" and d.action is Action.HUMAN_HANDOFF
    assert fake.requests == []  # rules matched, the LLM was never asked


def test_llm_invalid_intent_is_ignored(fake):
    fake.replies = ['{"intent": "give_discount", "confidence": 0.99}']
    d = triage("blah blah", llm=fake.client)
    assert d.intent == "other" and d.action is Action.HUMAN_HANDOFF


# ---------- facts + eligibility ----------

def test_facts_from_ukrainian_message():
    f = extract_facts_rules("Мій рейс з Лісабона до Берліна затримали на 5 годин")
    assert (f.origin, f.destination, f.disruption, f.delay_hours) == ("LIS", "BER", "delay", 5.0)
    r = check_facts(f)
    assert r.verdict and r.verdict.eligible and r.verdict.amount_eur == 400


def test_facts_inflected_polish_cities():
    f = extract_facts_rules("Lot z Warszawy do Barcelony opóźniony 3,5 godziny")
    assert (f.origin, f.destination, f.delay_hours) == ("WAW", "BCN", 3.5)


def test_flight_into_eu_needs_airline():
    r = check_facts(FlightFacts(origin="IST", destination="VIE", disruption="delay", delay_hours=5))
    assert r.verdict is None and "airline" in r.missing[0]
    r = check_facts(FlightFacts(origin="IST", destination="VIE", airline="TK", disruption="delay", delay_hours=5))
    assert r.verdict and not r.verdict.eligible


# ---------- chat agent ----------

def test_offline_eligibility_reply_has_amount():
    r = respond("My flight from Lisbon to Berlin was delayed 4 hours. Am I entitled?")
    assert r.mode == "offline" and "EUR 400" in r.text and r.eligibility.verdict.eligible


def test_offline_asks_for_missing_details_in_ukrainian():
    r = respond("Мій рейс скасували, чи можу я отримати компенсацію?")
    assert r.language == "uk" and "маршрут" in r.text


def test_handoff_has_note_and_localised_holding_message():
    r = respond("Ви шахраї! Гроші не прийшли")
    assert r.decision.action is Action.HUMAN_HANDOFF and r.decision.priority == "high"
    assert r.text.startswith("Дякую") and "INTENT: payment_issue" in r.handoff_note


def test_llm_reply_used_when_numbers_are_grounded(fake):
    fake.replies = ["Our fee is 30% only if we win; if the case goes to court it is 50%."]
    r = respond("How much commission do you take?", llm=fake.client)
    assert r.mode == "llm" and r.text.startswith("Our fee is 30%")
    assert "KNOWLEDGE BASE" in fake.requests[0]["messages"][0]["content"]


def test_number_guard_blocks_invented_numbers(fake):
    fake.replies = ["Our fee is only 15% and you will be paid in 7 days.", "Still 15%."]
    r = respond("How much commission do you take?", llm=fake.client)
    assert r.mode == "offline-fallback" and "30%" in r.text
    assert any("Number guard" in n for n in r.notes)


def test_number_guard_retry_can_fix_the_reply(fake):
    fake.replies = ["Our fee is only 15%.", "Our fee is 30% of the compensation, only if you win."]
    r = respond("How much commission do you take?", llm=fake.client)
    assert r.mode == "llm" and "30%" in r.text
    assert "15" in fake.requests[-1]["messages"][-1]["content"]


def test_llm_failure_falls_back_to_template():
    dead = LLM(base_url="http://127.0.0.1:9/v1", model="x", timeout=0.5)
    r = respond("How much commission do you take?", llm=dead)
    assert r.mode == "offline-fallback" and "30%" in r.text


def test_number_guard_accepts_thousand_separators():
    assert number_guard("Flights up to 1,500 km get EUR 250.", ["Up to 1,500 km | EUR 250"]) == []
    assert number_guard("You get EUR 900.", ["EUR 250"]) == ["900"]


# ---------- ticket reader ----------

def test_bcbp_barcode():
    import datetime as dt

    f = parse_bcbp("M1DOE/JOHN            EABC123 LISBERFR 1234 123Y014C0001 100", today=dt.date(2026, 11, 17))
    assert (f.origin, f.destination, f.airline, f.flight_number, f.booking_ref, f.passenger, f.date) == (
        "LIS", "BER", "FR", "FR1234", "ABC123", "John Doe", "2026-05-03")


def test_image_without_vision_model_explains():
    r = read_ticket_image(b"x", "image/png", None)
    assert r.method == "none" and "vision model" in r.notes[0]


def test_image_with_vision_model_validates_fields(fake):
    fake.replies = ['{"origin": "Warsaw", "destination": "BCN", "flight_number": "FR 1234", '
                    '"date": "2026-10-27", "delay_hours": 500, "booking_ref": "TOO-LONG-REF"}']
    r = read_ticket_image(b"\x89PNG", "image/png", fake.client)
    f = r.facts
    assert (f.origin, f.destination, f.flight_number, f.airline) == ("WAW", "BCN", "FR1234", "FR")
    assert f.delay_hours is None and f.booking_ref is None  # implausible values are dropped
    assert fake.requests[0]["model"] == "fake-vision"


# ---------- airline reply ----------

@pytest.mark.parametrize("letter,category,rec", [
    ("The delay was due to a technical problem with the aircraft.", "technical", "contest"),
    ("Cancelled because of a strike by French air traffic controllers.", "atc_strike", "unlikely"),
    ("Our pilots' strike forced the cancellation.", "airline_staff_strike", "contest"),
    ("Heavy snow and de-icing at the airport.", "weather", "review"),
    ("A bird strike on the previous landing required inspection.", "bird_strike", "unlikely"),
    ("Late arrival of the incoming aircraft.", "knock_on", "review"),
    ("Airspace closed because of the volcanic ash cloud.", "volcanic_ash", "unlikely"),
    ("A screw found on the runway damaged the tyre.", "foreign_object", "review"),
    ("The captain fell ill shortly before departure.", "crew_illness", "contest"),
    ("A failure of the airport fuel supply system prevented refuelling.", "airport_fuel", "review"),
    ("Crew shortage due to operational reasons.", "operational", "contest"),
])
def test_airline_reply_rules(letter, category, rec):
    a = airline_reply.analyse(letter)
    assert (a.category, a.recommendation, a.human_review) == (category, rec, True)


def test_airline_reply_llm_fills_unknown_cause(fake):
    fake.replies = ['{"category": "operational", "airline_claim": "Not enough crew was available."}']
    a = airline_reply.analyse("Unfortunately we were unable to operate the service as planned.", fake.client)
    assert a.category == "operational" and a.source == "llm" and a.recommendation == "contest"


# ---------- claim letter ----------

def _facts(**kw):
    base = dict(origin="WAW", destination="BCN", airline="FR", flight_number="FR1234", date="2026-10-27",
                passenger="Anna Kowalska", booking_ref="XYZ789", disruption="delay", delay_hours=4.5)
    base.update(kw)
    return FlightFacts(**base)


def test_letter_complete():
    L = draft_letter(_facts())
    assert L.ready and "EUR 400" in L.text and "Ryanair" in L.text and "1870 km" in L.text


def test_no_letter_when_not_eligible():
    L = draft_letter(_facts(delay_hours=2))
    assert not L.ready and "under 3 hours" in L.text


def test_letter_llm_paragraph_cannot_change_numbers(fake):
    fake.replies = ["The flight landed 9 hours late, causing great distress."]
    L = draft_letter(_facts(), llm=fake.client)
    assert L.mode == "template" and "4.5 hours" in L.text


# ---------- response cache ----------

def test_same_request_is_served_from_cache(fake):
    fake.replies = ["first", "second"]
    msgs = [{"role": "user", "content": "hi"}]
    assert fake.client.chat(msgs) == "first"
    assert fake.client.chat(msgs) == "first"
    assert len(fake.requests) == 1 and fake.client.hits == 1
    assert fake.client.chat(msgs, temperature=0) == "second"  # different request, new call


def test_cache_is_bounded_and_can_be_off(fake):
    fake.client.cache_size = 2
    fake.replies = ["a", "b", "c", "a2"]
    for q in ("1", "2", "3"):
        fake.client.chat([{"role": "user", "content": q}])
    assert len(fake.client._cache) == 2
    assert fake.client.chat([{"role": "user", "content": "1"}]) == "a2"  # evicted, asked again
    fake.client.cache_size = 0
    fake.replies = ["x", "y"]
    m = [{"role": "user", "content": "z"}]
    assert fake.client.chat(m) == "x" and fake.client.chat(m) == "y"


UK_MSG = "My BA flight from London to New York landed 6 hours late. Can I claim?"


def test_currency_guard_rejects_euros_for_uk261(fake):
    fake.replies = ["{}", "Good news, you can get EUR 520.", "You can get 520 euros."]
    r = respond(UK_MSG, llm=fake.client)
    assert r.mode == "offline-fallback" and "GBP 520" in r.text
    assert any("Currency guard" in n for n in r.notes)
    assert "GBP" in fake.requests[-1]["messages"][-1]["content"]


def test_currency_guard_retry_can_fix_the_reply(fake):
    fake.replies = ["{}", "You can get €520.", "You can get GBP 520 per passenger under UK261."]
    r = respond(UK_MSG, llm=fake.client)
    assert r.mode == "llm" and "GBP 520" in r.text


def test_currency_guard_only_for_eligible_checks():
    from claims_agent.agent import currency_guard
    from claims_agent.facts import FlightFacts
    eu = check_facts(FlightFacts(origin="WAW", destination="BCN", disruption="delay", delay_hours=5))
    assert currency_guard("EUR 400 per passenger", eu) == []
    assert currency_guard("£400 per passenger", eu) == ["£"]
    assert currency_guard("400 фунтів", eu) == ["фунт"]
    assert currency_guard("anything", None) == []


@pytest.mark.parametrize("reply", ["Du får 520 pund.", "Získáte 520 librách.", "Θα λάβετε 520 λίρες.",
                                   "Saat 520 punnissa.", "Vous recevrez 520 livres.", "U krijgt 520 pond.",
                                   "Receberá 520 libras.", "520 font jár."])
def test_currency_guard_knows_local_pound_names(reply):
    from claims_agent.agent import currency_guard
    from claims_agent.facts import FlightFacts
    eu = check_facts(FlightFacts(origin="WAW", destination="BCN", disruption="delay", delay_hours=5))
    assert currency_guard(reply, eu), reply


def test_currency_guard_knows_local_euro_names_but_not_europe():
    from claims_agent.agent import currency_guard
    from claims_agent.facts import FlightFacts
    uk = check_facts(FlightFacts(origin="LHR", destination="JFK", airline="BA", disruption="delay", delay_hours=6))
    assert currency_guard("520 eurót kap.", uk) and currency_guard("520 eurów", uk)
    assert currency_guard("GBP 520 under UK261, the UK copy of the European rules.", uk) == []
