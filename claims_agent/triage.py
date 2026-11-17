"""Decide whether the AI agent may answer a message or must hand it to a human.

The rules are deliberately explicit and conservative: anything legal, financial
or emotionally charged goes to a person. The AI layer drafts; this layer decides.

Keywords cover English, Ukrainian, Polish, German and Spanish. When no rule
matches, an optional LLM classifier may name the intent, but it can only pick
from the fixed list below, it never overrides a rule match, and its own
confidence goes through the same 0.70 threshold.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm import LLM


class Action(str, Enum):
    AI_ANSWER = "ai_answer"
    HUMAN_HANDOFF = "human_handoff"


@dataclass(frozen=True)
class Decision:
    intent: str
    action: Action
    reasons: list[str] = field(default_factory=list)
    priority: str = "normal"
    source: str = "rules"  # "rules" or "llm"


# Checked in order. The first matching intent names the message.
# Non-English stems are left open at the end so inflected forms still match.
INTENTS: list[tuple[str, str]] = [
    ("gdpr_request",
     r"\b(gdpr|delete my (data|account)|erase my data|personal data)\b"
     r"|видаліть мої дані|персональн\w* дан|rodo\b|usu[ńn] moje dane|dane osobow"
     r"|dsgvo|daten l[öo]sch|meine daten|rgpd|borr(ar|en) mis datos|datos personales"),
    ("legal_threat",
     r"\b(lawyer|attorney|sue|court|legal action|ombudsman|regulator)\b"
     r"|юрист|адвокат|(?<!\w)суд|позов|омбудсмен"
     r"|prawnik|adwokat|(?<!\w)s[ąa]d(?!\w)|pozew|rzecznik praw"
     r"|anwalt|gericht|klage|schlichtungsstelle|abogad|demanda|tribunal"),
    ("payment_issue",
     r"\b(not received|haven'?t received|where is my (money|payment)|wrong amount|bank details|iban|refund me)\b"
     r"|не отрима|гроші не|де мої гроші|реквізит|рахун\w* для виплат"
     r"|nie otrzyma|gdzie (są )?moje pieni|numer konta|z[łl]a kwota"
     r"|nicht erhalten|wo ist mein geld|bankverbindung|kontodaten|falscher betrag"
     r"|no he recibido|dónde está mi dinero|cuenta bancaria|importe incorrecto"),
    ("fee_question",
     r"\b(fee|commission|charge|how much do you (take|keep)|percent)\b|%"
     r"|комісі|скільки ви (берете|забираєте)|відсот"
     r"|prowizj|op[łl]at|ile (bierzecie|pobieracie)|procent"
     r"|geb[üu]hr|provision|wie viel (nehmen|behalten) sie|prozent"
     r"|comisi[óo]n|tarifa|cu[áa]nto (cobr|se qued)|porcentaje"),
    ("claim_status",
     r"\b(status|update on my claim|any news|claim number|case number|how long)\b"
     r"|статус|які новини|номер (заявки|справи)|скільки чекати"
     r"|status|jakie[ś]? wie[śs]ci|numer (sprawy|wniosku)|jak d[łl]ugo"
     r"|stand meine|neuigkeiten|fallnummer|wie lange"
     r"|estado de mi|alguna novedad|n[úu]mero de (caso|reclamaci)|cu[áa]nto tiempo"),
    ("documents",
     r"\b(boarding pass|e-?ticket|document|upload|power of attorney|passport)\b"
     r"|посадков|квиток|документ|завантаж|довіреніст|паспорт"
     r"|karta pok[łl]adowa|bilet|dokument|pe[łl]nomocnictw|paszport|prze[śs]l"
     r"|bordkarte|ticket|dokument|hochladen|vollmacht|reisepass"
     r"|tarjeta de embarque|billete|documento|subir|poder notarial|pasaporte"),
    ("eligibility",
     r"\b(eligible|entitled|compensation|delayed|delay|cancel+ed|cancellation|overbooked|denied boarding)\b"
     r"|затрим|скасува|компенсац|відмовили в посадці|овербукінг|маю право"
     r"|op[óo][źz]ni|odwo[łl]a|odszkodow|odm[óo]wiono wej[śs]cia|nadrezerwac"
     r"|versp[äa]t|annull|gestrichen|entsch[äa]digung|[üu]berbuch|nicht mitgenommen"
     r"|retras|cancela|indemnizaci|compensaci|overbooking|denegaron el embarque"),
]

INTENT_NAMES = [name for name, _ in INTENTS] + ["other"]

ESCALATE_INTENTS = {
    "gdpr_request": "Data-protection request must be logged and handled by a person.",
    "legal_threat": "Mentions legal action or a regulator.",
    "payment_issue": "Money or bank details involved.",
}

ANGER = re.compile(
    r"\b(scam|fraud|thie(f|ves)|disgusting|unacceptable|worst|ridiculous|furious|angry)\b|!!!"
    r"|шахра|обман|злоді|ганьба|жахлив|оборзіл"
    r"|oszu|z[łl]odzie|skandal|ha[ńn]ba|okropn"
    r"|betrug|betr[üu]ger|abzocke|frechheit|unversch[äa]mt"
    r"|estafa|fraude|ladrones|verg[üu]enza|indignante",
    re.I,
)


def classify(message: str) -> str:
    text = message.lower()
    for name, pattern in INTENTS:
        if re.search(pattern, text, re.I):
            return name
    return "other"


LLM_CLASSIFIER_PROMPT = """You classify customer messages for a flight-compensation claims service.
Pick exactly one intent:
- eligibility: asks whether a delay, cancellation or denied boarding gives compensation
- claim_status: asks about the progress of an existing claim
- fee_question: asks about the service fee or commission
- documents: asks which documents are needed or how to send them
- payment_issue: payout not received, wrong amount, bank details
- legal_threat: mentions lawyers, courts, regulators
- gdpr_request: asks to see or delete personal data
- other: anything else
The message can be in any language. Reply with JSON only:
{"intent": "<one of the names above>", "confidence": <0.0-1.0>}"""


def classify_with_llm(message: str, llm: "LLM") -> tuple[str, float]:
    data = llm.chat_json(
        [{"role": "system", "content": LLM_CLASSIFIER_PROMPT}, {"role": "user", "content": message}],
        temperature=0.0,
        max_tokens=60,
    )
    intent = str(data.get("intent", "other")).strip().lower()
    if intent not in INTENT_NAMES:
        return "other", 0.0
    try:
        conf = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
    except (TypeError, ValueError):
        conf = 0.0
    return intent, conf


def triage(
    message: str,
    *,
    ai_confidence: float = 1.0,
    previous_handoffs: int = 0,
    llm: "LLM | None" = None,
) -> Decision:
    intent = classify(message)
    source = "rules"
    reasons: list[str] = []

    if intent == "other" and llm is not None:
        from .llm import LLMError

        try:
            llm_intent, llm_conf = classify_with_llm(message, llm)
        except LLMError:
            llm_intent, llm_conf = "other", 0.0
        if llm_intent != "other":
            intent, source = llm_intent, "llm"
            ai_confidence = min(ai_confidence, llm_conf)

    if intent in ESCALATE_INTENTS:
        reasons.append(ESCALATE_INTENTS[intent])
    if ANGER.search(message):
        reasons.append("Customer is upset; a person should reply.")
    if ai_confidence < 0.7:
        what = "LLM intent confidence" if source == "llm" else "Knowledge-base match"
        reasons.append(f"{what} too weak ({ai_confidence:.2f} < 0.70).")
    if previous_handoffs > 0:
        reasons.append("Customer was already handed to a person; keep the same owner.")
    if intent == "other":
        reasons.append("No known intent; do not guess.")

    if reasons:
        urgent = intent in {"legal_threat", "gdpr_request"} or bool(ANGER.search(message))
        return Decision(intent, Action.HUMAN_HANDOFF, reasons, "high" if urgent else "normal", source)
    return Decision(intent, Action.AI_ANSWER, source=source)
