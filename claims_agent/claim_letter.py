"""Draft an EU261 claim letter to the airline from the case facts.

The letter body is a fixed template, so every amount, date and article number
comes from the facts and the eligibility check. An LLM, when configured, may
only rewrite the short "what happened" paragraph, and that paragraph passes the
same number guard as chat replies. A person sends the letter, never the bot.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .agent import number_guard
from .airports import AIRLINES, AIRPORTS
from .facts import EligibilityResult, FlightFacts, check_facts

if TYPE_CHECKING:
    from .llm import LLM

ARTICLE = {"delay": "Articles 5, 6 and 7 (as interpreted in CJEU C-402/07 Sturgeon)",
           "cancellation": "Articles 5 and 7", "denied_boarding": "Articles 4 and 7"}


@dataclass
class Letter:
    text: str
    ready: bool
    missing: list[str]
    eligibility: EligibilityResult
    mode: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "ready": self.ready, "missing": self.missing,
                "eligibility": self.eligibility.to_dict(), "mode": self.mode, "notes": self.notes}


def _what_happened(f: FlightFacts) -> str:
    if f.disruption == "delay":
        return f"The flight arrived at its final destination {f.delay_hours:g} hours late."
    if f.disruption == "cancellation":
        when = f" The cancellation was announced {f.notice_days} days before departure." if f.notice_days is not None else ""
        late = f" The passenger reached the final destination {f.delay_hours:g} hours late on a replacement flight." \
            if f.delay_hours is not None else ""
        return "The flight was cancelled." + when + late
    return "The passenger was denied boarding against their will despite presenting for check-in on time."


def _connection(f: FlightFacts) -> str:
    codes = [c for c in (f.via or "").split(",") if c in AIRPORTS]
    if not codes:
        return ""
    names = " and ".join(f"{AIRPORTS[c].city} ({c})" for c in codes)
    return f", connecting in {names} under one booking"


PARAGRAPH_PROMPT = """Rewrite this paragraph for a formal EU261 claim letter in English. Keep every fact and
number exactly; add nothing new. One to three sentences. Reply with the paragraph only.

Paragraph: {p}"""


def draft_letter(facts: FlightFacts, *, service_name: str = "FlyClaim", llm: LLM | None = None,
                 today: dt.date | None = None) -> Letter:
    result = check_facts(facts, today=today)
    missing = list(result.missing)
    for key, label in (("flight_number", "flight number"), ("date", "flight date"), ("passenger", "passenger name")):
        if not getattr(facts, key):
            missing.append(label)

    if result.verdict is not None and not result.verdict.eligible:
        return Letter(f"No letter drafted: {result.verdict.reason}", False, missing, result, "template")
    if result.verdict is None:
        return Letter("No letter drafted yet. Missing: " + ", ".join(missing) + ".", False, missing, result, "template")

    o, d = AIRPORTS[facts.origin], AIRPORTS[facts.destination]  # type: ignore[index]
    airline = AIRLINES.get(facts.airline or "", (facts.airline or "[AIRLINE]", False))[0]
    amount = result.verdict.amount_eur
    pax = result.passengers
    total = result.total_eur
    paragraph = _what_happened(facts)
    mode, notes = "template", []
    if llm is not None:
        from .llm import LLMError

        try:
            new = llm.chat([{"role": "user", "content": PARAGRAPH_PROMPT.format(p=paragraph)}],
                           temperature=0.3, max_tokens=150).strip()
            bad = number_guard(new, [paragraph])
            if new and not bad:
                paragraph, mode = new, "llm"
            else:
                notes.append(f"LLM paragraph rejected by the number guard ({', '.join(bad) or 'empty'}).")
        except LLMError as e:
            notes.append(f"LLM failed, used template: {e}")

    passenger = facts.passenger or "[PASSENGER NAME]"
    letter = f"""To: {airline}, Customer Relations / Claims
Date: {(today or dt.date.today()).isoformat()}
Subject: Compensation claim under Regulation (EC) No 261/2004 - flight {facts.flight_number or '[FLIGHT]'} on {facts.date or '[DATE]'}

Dear Sir or Madam,

{service_name} acts on behalf of {passenger}{f' (booking reference {facts.booking_ref})' if facts.booking_ref else ''}, under the attached authorisation.

The passenger held a confirmed reservation on flight {facts.flight_number or '[FLIGHT]'} from {o.city} ({o.iata}) to {d.city} ({d.iata}){_connection(facts)} on {facts.date or '[DATE]'}. {paragraph}

Under {ARTICLE[facts.disruption or 'delay']} of Regulation (EC) No 261/2004, and given a flight distance of {result.distance_km} km, {"the passenger is" if pax == 1 else f"each of the {pax} passengers is"} entitled to compensation of EUR {amount}{"" if pax == 1 else f", EUR {total} in total"}.

If you consider that extraordinary circumstances apply, please provide the specific evidence (cause, time and why it could not have been avoided by all reasonable measures).

Please pay EUR {total} within 14 days to the account given in the attached authorisation, or reply to this letter with your position.

Yours faithfully,
{service_name} claims team

Attachments: boarding pass / e-ticket, authorisation (power of attorney), passenger ID"""
    ready = not missing and not result.too_old
    if missing:
        notes.append("Fill the [PLACEHOLDERS] before sending.")
    if result.too_old:
        notes.append("The flight is over 2 years old: check the claim deadline for this country before sending.")
    return Letter(letter, ready, missing, result, mode, notes)
