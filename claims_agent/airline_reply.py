"""Analyse an airline's rejection letter and suggest whether to contest it.

Airlines often refuse with "extraordinary circumstances". Whether that holds
depends on the actual cause. This module names the cause, maps it to the usual
position in EU case law and suggests the next step. The category comes from
keyword rules, or from the LLM when no rule matches; the recommendation for a
category is fixed here, never written by the model. Every result goes to a
person for the final decision. Not legal advice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .llm import LLM


@dataclass(frozen=True)
class Category:
    name: str
    label: str
    pattern: str
    recommendation: str  # contest | review | unlikely
    why: str


# Order matters: more specific causes first.
CATEGORIES: list[Category] = [
    Category("airline_staff_strike", "Strike by the airline's own staff",
             r"(our|own|company|cabin crew|pilots?'?|crew) (strike|industrial action)|strike (of|by) (our|the airline'?s?) (pilots|crew|staff)"
             r"|pilot strike|crew strike|sick[- ]?out|wildcat",
             "contest", "Strikes by the airline's own staff are usually not extraordinary "
             "(CJEU C-28/20 Airhelp v SAS; spontaneous 'wildcat' sick-outs: C-195/17 Krüsemann)."),
    Category("atc_strike", "Air-traffic-control or airport strike",
             r"(air traffic control|atc|controllers?'?|airport (staff|workers)|security staff|ground handling) (strike|industrial action)"
             r"|strike (of|by) (the )?(\w+ )?(air traffic|atc|controllers|airport)",
             "unlikely", "Strikes outside the airline (ATC, airport) are generally extraordinary. Worth a look only if "
             "the airline did not take reasonable measures, e.g. a very long delay or no re-routing offered."),
    Category("bird_strike", "Bird strike",
             r"bird ?strike|collision with (a )?bird",
             "unlikely", "A bird strike is extraordinary (CJEU C-315/15 Pešková), though delay beyond the "
             "necessary inspection may still be claimable."),
    Category("volcanic_ash", "Volcanic ash / airspace closure",
             r"volcan\w*|ash cloud|eruption",
             "unlikely", "A volcanic eruption that closes airspace is extraordinary (CJEU C-12/11 McDonagh), "
             "but the airline still owed care (meals, hotel) during the wait."),
    Category("airport_fuel", "Airport fuel supply failure",
             r"fuel (supply|system|shortage)|refuel(l)?ing (system|failure)|airport (systems?|infrastructure) (failure|outage)",
             "review", "A failure of the airport's own fuel supply system can be extraordinary (CJEU C-308/21 SATA), "
             "but the airline must show it took reasonable measures. Ask for the airport's notice."),
    Category("weather", "Weather",
             r"\b(weather|storms?|snow\w*|fog|thunder\w*|wind|ice|icing|de-?icing|visibility|hurricane)\b",
             "review", "Severe weather can be extraordinary, but it must have affected this flight. Check historic "
             "weather at the airports and whether other flights operated normally."),
    Category("atc_restrictions", "ATC restrictions / slots",
             r"air traffic (control )?restriction|atc restriction|slot|eurocontrol|airspace (closure|restriction)|flow control",
             "review", "ATC decisions can be extraordinary, but the airline must show they caused this delay. "
             "Ask for the ATC/slot evidence."),
    Category("knock_on", "Knock-on effect of an earlier flight",
             r"previous flight|earlier flight|late arrival of (the )?(incoming )?aircraft|\brotation\b|knock-?on|\binbound\b",
             "review", "The airline may rely on a cause from an earlier rotation only if that cause was itself "
             "extraordinary and directly linked (CJEU C-74/19 LE v TAP). Ask what happened on the earlier flight."),
    Category("security_medical", "Security, medical or political event",
             r"security (threat|alert|incident)|bomb|medical emergency|unruly|disruptive passenger|political|war|airspace closed",
             "unlikely", "Security threats, medical emergencies and unruly passengers are usually extraordinary."),
    Category("foreign_object", "Foreign object or third-party damage",
             r"foreign object|\bfod\b|debris|screw (on|found)|object on the runway|damaged by (a )?(ground|third)|ground (vehicle|equipment) (hit|struck|damaged)",
             "review", "Damage caused by a foreign object on the runway or by a third party can be extraordinary "
             "(CJEU C-501/17 Germanwings, screw in a tyre). Ask for the damage report and how long the repair took."),
    Category("crew_illness", "Sudden crew illness or absence",
             r"(crew|pilot|co-?pilot|captain|cabin crew) (member )?(fell|became|was|were) (ill|sick|unwell|unfit)|illness of (the |a )?(crew|pilot|co-?pilot|captain)"
             r"|(crew|pilot|co-?pilot|captain)'?s? (sudden )?(illness|death|absence)",
             "contest", "A crew member's sudden illness or death is part of the airline's normal activity and is not "
             "extraordinary (CJEU C-156/22 to C-158/22 TAP, 2023)."),
    Category("technical", "Technical problem",
             r"\b(technical|mechanical|maintenance|engines?|repairs?|fault|defects?|aircraft (problem|issue)|spare parts?|hydraulic)\b",
             "contest", "Technical problems are usually not extraordinary: maintenance is part of normal airline "
             "operations (CJEU C-549/07 Wallentin-Hermann; C-257/14 van der Lans). Exception: hidden manufacturing "
             "defects or damage by a third party, such as foreign objects on the runway (C-501/17 Germanwings)."),
    Category("operational", "Operational / crew shortage",
             r"operational reasons?|crew (shortage|availability)|staff shortage|crew rest|duty time|scheduling|aircraft availability",
             "contest", "Crew shortages and other operational reasons are part of the airline's normal activity "
             "and are generally not extraordinary."),
]

BY_NAME = {c.name: c for c in CATEGORIES}

NEXT_STEP = {
    "contest": "Reply to the airline contesting the refusal and asking for evidence.",
    "review": "Ask the airline for evidence of the cause; a claims handler decides after reviewing it.",
    "unlikely": "Tell the customer the refusal is probably valid; a claims handler confirms before closing.",
}


@dataclass
class Analysis:
    category: str
    label: str
    recommendation: str
    why: str
    next_step: str
    matched: str | None
    source: str  # rules | llm | none
    summary: str | None = None
    notes: list[str] = field(default_factory=list)
    human_review: bool = True
    draft: str | None = None  # reply to the airline, for "contest" and "review"; a person edits and sends it

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


EVIDENCE = {
    "contest": "Under Regulation (EC) No 261/2004 the burden of proving extraordinary circumstances lies with "
               "the carrier, and the cause you name is, in established case law, part of the normal exercise of "
               "an air carrier's activity. We therefore maintain the claim.",
    "review": "Under Regulation (EC) No 261/2004 the burden of proving extraordinary circumstances lies with "
              "the carrier. Before we can assess your position, please provide:",
}
REQUESTS = (
    "- documentary evidence of the cause and of when it occurred (for example technical log entries, "
    "ATC or airport notices, or weather reports for the airports concerned);\n"
    "- evidence that the cause directly affected this flight; and\n"
    "- the reasonable measures you took to avoid the disruption or limit the delay, including re-routing options."
)


def rebuttal(a: Analysis, letter: str) -> str | None:
    """A fixed-template reply to the airline. No model writes it, so it carries no invented facts."""
    if a.recommendation not in EVIDENCE:
        return None
    ref = re.search(r"\b(?:booking|reference|pnr|claim|case)\W{0,15}(?=[A-Z]*\d)([A-Z0-9]{6,10})\b", letter, re.I)
    subject = f"Your refusal of the compensation claim{f' (reference {ref.group(1).upper()})' if ref else ''}"
    body = [f"Subject: {subject}", "", "Dear Sir or Madam,", "",
            f"Thank you for your reply. You refused compensation, citing: {a.label.lower()}.", "",
            EVIDENCE[a.recommendation]]
    if a.recommendation == "contest":
        body += ["", a.why, "", "If you still consider the circumstances extraordinary, please provide:"]
    body += [REQUESTS, "",
             "Please pay the compensation or send this evidence within 14 days. Otherwise we will refer the case "
             "to the national enforcement body or to the court.", "", "Yours faithfully,", "[SERVICE] claims team"]
    return "\n".join(body)


LLM_PROMPT = """You read an airline's reply to an EU261 compensation claim.
Pick the cause the airline gives for the disruption, one of:
{names}, other.
Reply with JSON only:
{{"category": "<name>", "airline_claim": "<one sentence: what the airline says happened>"}}"""


def analyse(letter: str, llm: LLM | None = None) -> Analysis:
    low = letter.lower()
    for c in CATEGORIES:
        m = re.search(c.pattern, low)
        if m:
            a = Analysis(c.name, c.label, c.recommendation, c.why, NEXT_STEP[c.recommendation], m.group(0), "rules")
            break
    else:
        a = Analysis("other", "Unclear cause", "review",
                     "The letter does not name a cause the rules recognise. A claims handler should read it.",
                     NEXT_STEP["review"], None, "none")

    if llm is not None:
        from .llm import LLMError

        try:
            data = llm.chat_json(
                [{"role": "system", "content": LLM_PROMPT.format(names=", ".join(BY_NAME))},
                 {"role": "user", "content": letter[:6000]}],
                temperature=0.0, max_tokens=150,
            )
            a.summary = str(data.get("airline_claim") or "") or None
            cat = str(data.get("category", "")).strip()
            if a.source == "none" and cat in BY_NAME:
                c = BY_NAME[cat]
                a.category, a.label, a.recommendation, a.why = c.name, c.label, c.recommendation, c.why
                a.next_step, a.source = NEXT_STEP[c.recommendation], "llm"
            elif a.source == "rules" and cat in BY_NAME and cat != a.category:
                a.notes.append(f"The LLM read the cause as '{BY_NAME[cat].label}'; check which one applies.")
        except LLMError as e:
            a.notes.append(f"LLM analysis failed: {e}")
    a.draft = rebuttal(a, letter)
    return a
