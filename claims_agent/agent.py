"""The first-line support agent: triage, then an LLM reply or a handoff note.

Flow for every customer message:

1. `triage` decides AI answer vs human handoff (rules first, LLM only as a fallback).
2. For eligibility questions the rule-based EU261 check runs on the facts found in
   the conversation, and its result is handed to the model as a tool result.
3. The LLM writes the reply from the knowledge base. A number guard rejects any
   reply that quotes a number found neither in the knowledge base, the check
   result nor the customer's own messages, and falls back to a template.
4. On handoff the customer gets a holding message in their language and the
   support team gets a structured note.

Without an LLM every step still works, with template replies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .facts import EligibilityResult, FlightFacts, check_facts, extract_facts
from .language import SUPPORTED, detect_language
from .triage import Action, Decision, triage

if TYPE_CHECKING:
    from .llm import LLM

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def knowledge() -> str:
    parts = [p.read_text() for p in sorted((ROOT / "knowledge").glob("*.md"))]
    return "\n\n".join(parts)


HOLDING = {
    "en": "Thanks, I've passed this to a colleague who will reply personally within one business day. "
          "You don't need to send anything else for now.",
    "uk": "Дякую, я передав ваше звернення колезі, який особисто відповість протягом одного робочого дня. "
          "Поки що нічого додатково надсилати не потрібно.",
    "pl": "Dziękuję, przekazałem sprawę koledze, który odpowie osobiście w ciągu jednego dnia roboczego. "
          "Na razie nie trzeba niczego więcej wysyłać.",
    "de": "Danke, ich habe Ihr Anliegen an einen Kollegen weitergegeben, der sich innerhalb eines Werktags "
          "persönlich meldet. Sie müssen vorerst nichts weiter schicken.",
    "es": "Gracias, he pasado su consulta a un compañero que le responderá personalmente en un día hábil. "
          "Por ahora no necesita enviar nada más.",
}


@dataclass
class Reply:
    text: str
    decision: Decision
    language: str
    mode: str  # "llm" | "offline" | "offline-fallback"
    handoff_note: str | None = None
    facts: FlightFacts | None = None
    eligibility: EligibilityResult | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "intent": self.decision.intent,
            "action": self.decision.action.value,
            "priority": self.decision.priority,
            "reasons": self.decision.reasons,
            "intent_source": self.decision.source,
            "language": self.language,
            "mode": self.mode,
            "handoff_note": self.handoff_note,
            "facts": self.facts.to_dict() if self.facts else None,
            "eligibility": self.eligibility.to_dict() if self.eligibility else None,
            "notes": self.notes,
        }


# ---------- offline templates (English and Ukrainian; other languages get English) ----------

def _t(lang: str, en: str, uk: str) -> str:
    return uk if lang == "uk" else en


MISSING_UK = {
    "route (from and to)": "маршрут (звідки і куди)",
    "what happened (delay, cancellation or denied boarding)": "що сталося (затримка, скасування чи відмова в посадці)",
    "how late you arrived at the final destination": "на скільки годин ви запізнилися до кінцевого пункту",
    "a different departure and arrival airport": "різні аеропорти вильоту і прильоту",
    "the airline (flights into the EU are covered only on EU airlines)": "авіакомпанію (рейси в ЄС покриваються лише для авіакомпаній ЄС)",
}


def template_reply(intent: str, lang: str, result: EligibilityResult | None) -> str:
    if intent == "eligibility":
        if result is None or result.verdict is None:
            items = result.missing if result else ["route (from and to)", "what happened (delay, cancellation or denied boarding)"]
            if lang == "uk":
                items = [MISSING_UK.get(i, i) for i in items]
            need = ", ".join(items)
            return _t(lang,
                      f"I can run a quick EU261 check for you. Please tell me {need}.",
                      f"Я можу швидко перевірити ваш рейс за EU261. Напишіть, будь ласка: {need}.")
        v = result.verdict
        if v.eligible:
            return _t(lang,
                      f"Good news: your flight {result.route} ({result.distance_km} km) looks eligible. "
                      f"Compensation would be EUR {v.amount_eur} per passenger, before our service fee. "
                      "This is a preliminary check, not a guarantee. To start the claim, send your boarding pass or e-ticket.",
                      f"Схоже, ваш рейс {result.route} ({result.distance_km} км) має право на компенсацію: "
                      f"EUR {v.amount_eur} на пасажира до вирахування нашої комісії. "
                      "Це попередня перевірка, а не гарантія. Щоб подати заявку, надішліть посадковий або e-ticket.")
        return _t(lang,
                  f"From what you've told me, this flight is probably not eligible: {v.reason} "
                  "If any detail is different, tell me and I'll check again.",
                  f"За вашими даними цей рейс, найімовірніше, не підпадає під компенсацію: {v.reason} "
                  "Якщо якісь деталі інші, напишіть, і я перевірю ще раз.")
    if intent == "fee_question":
        return _t(lang,
                  "We work on a no win, no fee basis. If we get your compensation, our fee is 30% (VAT included). "
                  "If the airline refuses and the case has to go to court or an external lawyer, the fee is 50%. "
                  "Baggage and reimbursement claims are 40%.",
                  "Ми працюємо за принципом «немає виплати, немає комісії». Якщо ми отримаємо компенсацію, комісія 30% (з ПДВ). "
                  "Якщо авіакомпанія відмовить і справа піде до суду чи зовнішнього юриста, комісія 50%. "
                  "Для претензій щодо багажу та відшкодувань 40%.")
    if intent == "claim_status":
        return _t(lang,
                  "Every claim moves through these stages: submitted, sent to the airline (a reply usually takes 2-8 weeks), "
                  "negotiation, and if needed a national authority or court. I can't promise a date, but a colleague can tell "
                  "you the exact stage of your claim if you share your claim number.",
                  "Кожна заявка проходить етапи: подано, надіслано авіакомпанії (відповідь зазвичай 2-8 тижнів), "
                  "переговори і за потреби національний орган чи суд. Дату обіцяти не можу, але колега підкаже точний етап, "
                  "якщо ви надішлете номер заявки.")
    if intent == "documents":
        return _t(lang,
                  "To start a claim we need: the boarding pass or e-ticket for every passenger, an ID document for the lead "
                  "passenger, and a signed authorisation so we can act for you. You can upload them in your claim form.",
                  "Для заявки потрібні: посадковий або e-ticket для кожного пасажира, документ, що посвідчує особу головного "
                  "пасажира, і підписана довіреність, щоб ми могли діяти від вашого імені. Їх можна завантажити у формі заявки.")
    return HOLDING.get(lang, HOLDING["en"])


# ---------- LLM reply ----------

SYSTEM_PROMPT = """You are the first-line support agent of a flight-compensation claims service (EU261).
Rules:
- Answer the question in the first sentence. Short paragraphs, plain words, no legal jargon. Max 120 words.
- Use ONLY facts and numbers from the KNOWLEDGE BASE and the CHECK RESULT below. Never invent a number.
- Eligibility: give the amount per passenger BEFORE the service fee and say it is a preliminary check, not a guarantee.
  If the check result lists missing details, ask only for those.
- Fees: state the fee model exactly. Never apologise for the fee or offer discounts.
- Status: give the stages and the next step; never promise a payout date. You cannot see live claim data.
- Never ask for card numbers or passwords.
- Reply in {language}.

KNOWLEDGE BASE:
{knowledge}

CHECK RESULT:
{check}"""

_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _norm_num(n: str) -> str:
    n = n.replace(",", ".")
    return n.rstrip("0").rstrip(".") if "." in n else n


def number_guard(reply: str, allowed_sources: list[str]) -> list[str]:
    """Numbers in the reply that appear in none of the allowed sources."""
    allowed = {"1", "2", "3"}  # "step 1", "one of 2 options" and similar
    for src in allowed_sources:
        allowed |= {_norm_num(n) for n in _NUM.findall(src.replace("\u00a0", ""))}
    # "1,500 km" in the knowledge base is one number, not two.
    for src in allowed_sources:
        allowed |= {n.replace(",", "") for n in re.findall(r"\d{1,3}(?:,\d{3})+", src)}
    return [n for n in _NUM.findall(reply) if _norm_num(n) not in allowed and n.replace(",", "") not in allowed]


def _check_summary(result: EligibilityResult | None) -> str:
    if result is None:
        return "No eligibility check run for this message."
    d = result.to_dict()
    if result.verdict is None:
        return f"Check could not run yet. Missing: {', '.join(result.missing)}."
    return (f"Route {d['route']}, {d['distance_km']} km. Eligible: {d['eligible']}. "
            f"Amount per passenger before fee: EUR {d['amount_eur']}. Reason: {d['reason']}")


def handoff_note(decision: Decision, message: str, facts: FlightFacts | None, summary: str | None = None,
                 next_step: str | None = None) -> str:
    known = []
    if facts:
        for key in ("origin", "destination", "airline", "flight_number", "date", "disruption", "delay_hours", "booking_ref"):
            v = getattr(facts, key)
            if v is not None:
                known.append(f"{key}={v}")
    why = "\n".join(f"  - {r}" for r in decision.reasons) or "  - (none)"
    return (
        f"INTENT: {decision.intent}   PRIORITY: {decision.priority}\n"
        f"WHY:\n{why}\n"
        f"CUSTOMER WANTS: {summary or message.strip()[:200]}\n"
        f"FACTS SO FAR: {', '.join(known) or 'none yet'}\n"
        f"SUGGESTED NEXT STEP: {next_step or _default_next_step(decision.intent)}"
    )


def _default_next_step(intent: str) -> str:
    return {
        "payment_issue": "Check payout status in the payments system and confirm bank details via the secure form.",
        "legal_threat": "Senior agent reviews the case history and replies the same day.",
        "gdpr_request": "Log the request in the GDPR register and confirm identity before acting.",
        "fee_question": "Explain the fee calmly from the published price list; no discounts.",
    }.get(intent, "Read the conversation and reply personally.")


HANDOFF_PROMPT = """Summarise this support message for a human colleague.
Reply with JSON only: {"customer_wants": "<one sentence in English>", "next_step": "<one line in English>"}"""


def respond(
    message: str,
    history: list[dict[str, str]] | None = None,
    *,
    llm: "LLM | None" = None,
    previous_handoffs: int = 0,
) -> Reply:
    from .llm import LLMError

    history = history or []
    lang = detect_language(message)
    decision = triage(message, previous_handoffs=previous_handoffs, llm=llm)
    customer_text = "\n".join([m["content"] for m in history if m.get("role") == "user"] + [message])
    notes: list[str] = []

    if decision.action is Action.HUMAN_HANDOFF:
        facts = extract_facts(customer_text)
        summary = next_step = None
        if llm is not None:
            try:
                data = llm.chat_json([{"role": "system", "content": HANDOFF_PROMPT},
                                      {"role": "user", "content": message}], temperature=0.0, max_tokens=150)
                summary = str(data.get("customer_wants") or "") or None
                next_step = str(data.get("next_step") or "") or None
            except LLMError as e:
                notes.append(f"LLM summary failed: {e}")
        return Reply(HOLDING.get(lang, HOLDING["en"]), decision, lang, "llm" if llm and not notes else "offline",
                     handoff_note(decision, message, facts, summary, next_step), facts, None, notes)

    facts = result = None
    if decision.intent == "eligibility":
        facts = extract_facts(customer_text, llm)
        result = check_facts(facts)

    offline = template_reply(decision.intent, lang, result)
    if llm is None:
        if lang not in {"en", "uk"}:
            offline += f"\n\n(A colleague can help in {SUPPORTED[lang]} if you prefer.)"
        return Reply(offline, decision, lang, "offline", None, facts, result, notes)

    check = _check_summary(result)
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(
        language=SUPPORTED.get(lang, "English"), knowledge=knowledge(), check=check)}]
    messages += [m for m in history[-8:] if m.get("role") in {"user", "assistant"}]
    messages.append({"role": "user", "content": message})
    try:
        text = llm.chat(messages, temperature=0.3, max_tokens=400).strip()
    except LLMError as e:
        notes.append(f"LLM failed, used template: {e}")
        return Reply(offline, decision, lang, "offline-fallback", None, facts, result, notes)

    bad = number_guard(text, [knowledge(), check, customer_text])
    if bad or not text:
        notes.append(f"Number guard rejected the LLM reply (unsupported numbers: {', '.join(bad) or 'empty reply'}).")
        return Reply(offline, decision, lang, "offline-fallback", None, facts, result, notes)
    return Reply(text, decision, lang, "llm", None, facts, result, notes)
