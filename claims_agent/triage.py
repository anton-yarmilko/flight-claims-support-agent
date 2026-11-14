"""Decide whether the AI agent may answer a message or must hand it to a human.

The rules are deliberately explicit and conservative: anything legal, financial
or emotionally charged goes to a person. The AI layer drafts; this layer decides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Action(str, Enum):
    AI_ANSWER = "ai_answer"
    HUMAN_HANDOFF = "human_handoff"


@dataclass(frozen=True)
class Decision:
    intent: str
    action: Action
    reasons: list[str] = field(default_factory=list)
    priority: str = "normal"


# Checked in order. The first matching intent names the message.
INTENTS: list[tuple[str, str]] = [
    ("gdpr_request", r"\b(gdpr|delete my (data|account)|erase my data|personal data)\b"),
    ("legal_threat", r"\b(lawyer|attorney|sue|court|legal action|ombudsman|regulator)\b"),
    ("payment_issue", r"\b(not received|haven'?t received|where is my (money|payment)|wrong amount|bank details|iban|refund me)\b"),
    ("fee_question", r"\b(fee|commission|charge|how much do you (take|keep)|percent|%)\b"),
    ("claim_status", r"\b(status|update on my claim|any news|claim number|case number|how long)\b"),
    ("documents", r"\b(boarding pass|e-?ticket|document|upload|power of attorney|passport)\b"),
    ("eligibility", r"\b(eligible|entitled|compensation|delayed|delay|cancel+ed|cancellation|overbooked|denied boarding)\b"),
]

ESCALATE_INTENTS = {
    "gdpr_request": "Data-protection request must be logged and handled by a person.",
    "legal_threat": "Mentions legal action or a regulator.",
    "payment_issue": "Money or bank details involved.",
}

ANGER = re.compile(
    r"\b(scam|fraud|thie(f|ves)|disgusting|unacceptable|worst|ridiculous|furious|angry)\b|!!!",
    re.I,
)


def classify(message: str) -> str:
    text = message.lower()
    for name, pattern in INTENTS:
        if re.search(pattern, text, re.I):
            return name
    return "other"


def triage(message: str, *, ai_confidence: float = 1.0, previous_handoffs: int = 0) -> Decision:
    intent = classify(message)
    reasons: list[str] = []

    if intent in ESCALATE_INTENTS:
        reasons.append(ESCALATE_INTENTS[intent])
    if ANGER.search(message):
        reasons.append("Customer is upset; a person should reply.")
    if ai_confidence < 0.7:
        reasons.append(f"Knowledge-base match too weak ({ai_confidence:.2f} < 0.70).")
    if previous_handoffs > 0:
        reasons.append("Customer was already handed to a person; keep the same owner.")
    if intent == "other":
        reasons.append("No known intent; do not guess.")

    if reasons:
        urgent = intent in {"legal_threat", "gdpr_request"} or bool(ANGER.search(message))
        return Decision(intent, Action.HUMAN_HANDOFF, reasons, "high" if urgent else "normal")
    return Decision(intent, Action.AI_ANSWER)
