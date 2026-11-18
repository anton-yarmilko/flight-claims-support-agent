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

from .causes import EXCUSING_CAUSES
from .facts import (
    FUTURE_FLIGHT,
    EligibilityResult,
    FlightFacts,
    check_facts,
    extract_facts,
    extract_facts_rules,
    prefer_latest,
)
from .i18n import t
from .language import SUPPORTED, detect_language
from .triage import Action, Decision, triage

if TYPE_CHECKING:
    from .llm import LLM

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def knowledge() -> str:
    parts = [p.read_text() for p in sorted((ROOT / "knowledge").glob("*.md"))]
    return "\n\n".join(parts)


def holding(lang: str) -> str:
    return t(lang, "holding")


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


# ---------- offline templates (every AirAdvisor language, see locales/) ----------

MISSING_KEYS = {
    "route (from and to)": "m_route",
    "what happened (delay, cancellation or denied boarding)": "m_what",
    "how late you arrived at the final destination": "m_delay",
    "a different departure and arrival airport": "m_airports",
    "the airline (flights into the EU are covered only on EU airlines)": "m_airline",
    FUTURE_FLIGHT: "m_future",
}

REASON_KEYS = {
    "Route not covered": "rs_not_covered",
    "extraordinary circumstances": "rs_extraordinary",
    "under 3 hours": "rs_under_3h",
    "14 or more days": "rs_notice_14d",
    "announced 7-13 days ahead": "rs_reroute_7d",
    "announced under 7 days ahead": "rs_reroute_lt7",
    "voluntarily": "rs_voluntary",
}


def _reason(lang: str, reason: str) -> str:
    m = re.match(r"Likely eligible: ([A-Z]{3}) (\d+) .*within (\d) hours", reason)
    if m:
        return t(lang, "rs_halved", cur=m.group(1), amount=m.group(2), h=m.group(3))
    m = re.match(r"Likely eligible: ([A-Z]{3}) (\d+)", reason)
    if m:
        return t(lang, "rs_likely", cur=m.group(1), amount=m.group(2))
    for marker, key in REASON_KEYS.items():
        if marker in reason:
            return t(lang, key)
    return reason


def template_reply(intent: str, lang: str, result: EligibilityResult | None) -> str:
    if intent == "eligibility":
        if result is None or result.verdict is None:
            items = result.missing if result else list(MISSING_KEYS)[:2]
            need = ", ".join(t(lang, MISSING_KEYS[i]) if i in MISSING_KEYS else i for i in items)
            return t(lang, "elig_ask", need=need)
        v = result.verdict
        if v.eligible:
            # A cause that usually excuses the airline: no "good news" opening.
            key = "elig_maybe" if result.cause in EXCUSING_CAUSES else "elig_yes"
            text = t(lang, key, route=result.route, km=result.distance_km, amount=v.amount_eur, cur=v.currency)
            if v.regulation == "UK261":
                text += " " + t(lang, "uk261_note")
            half = re.search(r"within (\d) hours", v.reason)
            if half:
                text += " " + t(lang, "elig_half", h=half.group(1))
            if result.passengers > 1:
                text += " " + t(lang, "elig_total", n=result.passengers, total=result.total_eur, cur=v.currency)
            if result.departure_only:
                text += " " + t(lang, "dep_only")
            if result.cause:
                text += " " + t(lang, "cause_" + result.cause)
            if result.operated_by:
                text += " " + t(lang, "codeshare", airline=result.operated_by)
            return text
        text = t(lang, "elig_no", reason=_reason(lang, v.reason))
        if result.operated_by:
            text += " " + t(lang, "codeshare", airline=result.operated_by)
        return text
    if intent == "fee_question":
        return t(lang, "fee")
    if intent == "claim_status":
        return t(lang, "status")
    if intent == "documents":
        return t(lang, "documents")
    return holding(lang)


# ---------- LLM reply ----------

SYSTEM_PROMPT = """You are the first-line support agent of a flight-compensation claims service (EU261).
Rules:
- Answer the question in the first sentence. Short paragraphs, plain words, no legal jargon. Max 120 words.
- Answer only what the customer asked; do not add fee, status or document details they did not ask about.
- Plain text only: no Markdown, no asterisks, no headings.
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


_CURRENCY_WORDS = {
    # Currency names in the 20 reply languages, not only the codes ("Europe" must not match).
    "EUR": re.compile(r"\bEUR\b|€|\beur(?:o|os|ó|ót|óban|ów|ach|a|y|t|ssa|ja|oa)?\b|євро|евро|ευρώ|\bavro\b",
                      re.IGNORECASE),
    "GBP": re.compile(r"\bGBP\b|£|\bpounds?\b|фунт|\bfunt|pfund|sterlin|στερλ|λίρ|\bpund\b|\bpond(?:en)?\b"
                      r"|\blibr(?:a|as|y|ách|e)\b|\blire\b|\blivres?\b|\bpun(?:ta|taa|nissa|tia)\b|\bfont\b|\bfontban\b",
                      re.IGNORECASE),
}


def currency_guard(reply: str, result: EligibilityResult | None) -> list[str]:
    """Currency words in the reply that are not the currency of the check (EUR vs GBP for UK261).
    The number guard cannot see a wrong currency: "EUR 520" uses a grounded number."""
    v = result.verdict if result else None
    if v is None or not v.eligible:
        return []
    other = "GBP" if v.currency == "EUR" else "EUR"
    return sorted({m.group(0) for m in _CURRENCY_WORDS[other].finditer(reply)})


def _check_summary(result: EligibilityResult | None) -> str:
    if result is None:
        return "No eligibility check run for this message."
    d = result.to_dict()
    if result.verdict is None:
        return f"Check could not run yet. Missing: {', '.join(result.missing)}."
    cur = d["currency"]
    return (f"Route {d['route']}, {d['distance_km']} km. Regulation: {d['regulation']}. Eligible: {d['eligible']}. "
            f"Amount per passenger before fee: {cur} {d['amount_eur']}. Reason: {d['reason']}"
            + (f" Passengers: {d['passengers']}, total before fee: {cur} {d['total_eur']}." if d["passengers"] > 1 and d["eligible"] else "")
            + (f" The customer names the cause; tell them: {t('en', 'cause_' + d['cause'])}" if d["cause"] and d["eligible"] else "")
            + (f" The customer gave the departure delay only; tell them: {t('en', 'dep_only')}" if d["departure_only"] and d["eligible"] else "")
            + (f" Codeshare; tell them: {t('en', 'codeshare', airline=d['operated_by'])}" if d.get("operated_by") else ""))


def handoff_note(decision: Decision, message: str, facts: FlightFacts | None, summary: str | None = None,
                 next_step: str | None = None, result: EligibilityResult | None = None) -> str:
    known = []
    if facts:
        for key in ("origin", "destination", "via", "airline", "flight_number", "date", "disruption", "delay_hours", "booking_ref", "cause"):
            v = getattr(facts, key)
            if v is not None:
                known.append(f"{key}={v}")
    why = "\n".join(f"  - {r}" for r in decision.reasons) or "  - (none)"
    return (
        f"INTENT: {decision.intent}   PRIORITY: {decision.priority}\n"
        f"WHY:\n{why}\n"
        f"CUSTOMER WANTS: {summary or message.strip()[:200]}\n"
        f"FACTS SO FAR: {', '.join(known) or 'none yet'}\n"
        + (f"EU261 CHECK: {_check_summary(result)}\n" if result is not None and result.verdict is not None else "")
        + f"SUGGESTED NEXT STEP: {next_step or _default_next_step(decision.intent)}"
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


TOO_OLD_REASON = "Flight is over 2 years old: the claim deadline depends on the country, a person checks it."


def _handoff(decision: Decision, message: str, lang: str, facts: FlightFacts | None, llm: LLM | None,
             result: EligibilityResult | None = None) -> Reply:
    from .llm import LLMError

    notes: list[str] = []
    summary = next_step = None
    if llm is not None:
        try:
            data = llm.chat_json([{"role": "system", "content": HANDOFF_PROMPT},
                                  {"role": "user", "content": message}], temperature=0.0, max_tokens=150)
            summary = str(data.get("customer_wants") or "") or None
            next_step = str(data.get("next_step") or "") or None
        except LLMError as e:
            notes.append(f"LLM summary failed: {e}")
    if TOO_OLD_REASON in decision.reasons and not next_step:
        next_step = "Check the claim deadline for the departure country and airline before accepting the case."
    return Reply(holding(lang), decision, lang, "llm" if llm and not notes else "offline",
                 handoff_note(decision, message, facts, summary, next_step, result), facts, result, notes)


def respond(
    message: str,
    history: list[dict[str, str]] | None = None,
    *,
    llm: LLM | None = None,
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
        # Give the colleague the EU261 numbers too when the message already has them.
        result = None if facts.missing_for_check() else check_facts(facts)
        return _handoff(decision, message, lang, facts, llm, result)

    facts = result = None
    if decision.intent == "eligibility":
        facts = extract_facts(customer_text, llm)
        if history:
            facts = prefer_latest(facts, extract_facts_rules(message))
        result = check_facts(facts)
        if result.too_old:
            decision = Decision(decision.intent, Action.HUMAN_HANDOFF, [*decision.reasons, TOO_OLD_REASON],
                                decision.priority, decision.source)
            return _handoff(decision, message, lang, facts, llm, result)

    offline = template_reply(decision.intent, lang, result)
    if llm is None:
        return Reply(offline, decision, lang, "offline", None, facts, result, notes)

    check = _check_summary(result)
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(
        language=SUPPORTED.get(lang, "English"), knowledge=knowledge(), check=check)}]
    messages += [m for m in history[-8:] if m.get("role") in {"user", "assistant"}]
    messages.append({"role": "user", "content": message})
    sources = [knowledge(), check, customer_text]
    try:
        text = llm.chat(messages, temperature=0.3, max_tokens=400).strip()
        bad, wrong_cur = number_guard(text, sources), currency_guard(text, result)
        if bad or wrong_cur:
            # One retry: tell the model what it may not use. The guards still decide.
            fix = []
            if bad:
                notes.append(f"Number guard rejected the first LLM reply (unsupported numbers: {', '.join(bad)}); retried.")
                fix.append(f"Your reply used numbers that are not in the KNOWLEDGE BASE or CHECK RESULT: {', '.join(bad)}. "
                           "Rewrite it without them, using only numbers given above.")
            if wrong_cur:
                notes.append(f"Currency guard rejected the first LLM reply (wrong currency: {', '.join(wrong_cur)}); retried.")
                fix.append(f"The amount is in {result.verdict.currency}, as the CHECK RESULT says; "  # type: ignore[union-attr]
                           f"do not write {', '.join(wrong_cur)}.")
            retry = [*messages, {"role": "assistant", "content": text}, {"role": "system", "content": " ".join(fix)}]
            text = llm.chat(retry, temperature=0.0, max_tokens=400).strip()
    except LLMError as e:
        notes.append(f"LLM failed, used template: {e}")
        return Reply(offline, decision, lang, "offline-fallback", None, facts, result, notes)

    bad = number_guard(text, sources)
    if bad or not text:
        notes.append(f"Number guard rejected the LLM reply (unsupported numbers: {', '.join(bad) or 'empty reply'}).")
        return Reply(offline, decision, lang, "offline-fallback", None, facts, result, notes)
    wrong_cur = currency_guard(text, result)
    if wrong_cur:
        notes.append(f"Currency guard rejected the LLM reply (wrong currency: {', '.join(wrong_cur)}).")
        return Reply(offline, decision, lang, "offline-fallback", None, facts, result, notes)
    return Reply(text, decision, lang, "llm", None, facts, result, notes)
