"""Inbox view: run a batch of customer messages through triage and the EU261 check.

Shows what the agent would do with a day's mail: how much it can answer itself,
what goes to a person and why, which cases are urgent, and how much compensation
the eligible claims add up to. Rules only (no LLM), so it is instant, free and
gives the same answer every time.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .agent import respond

SAMPLE = Path(__file__).resolve().parent.parent / "evals" / "cases.jsonl"
MAX_MESSAGES = 200

# Why a message went to a person, from the triage reason text.
HANDOFF_REASONS = (
    ("legal action", "legal"),
    ("Data-protection", "gdpr"),
    ("Money or bank", "money"),
    ("upset", "anger"),
    ("No known intent", "unknown"),
)


def sample_messages() -> list[dict[str, str]]:
    rows = [json.loads(line) for line in SAMPLE.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Cases that simulate a low-confidence LLM classifier have no fixed label offline.
    return [{"message": r["message"]} if "confidence" in r else
            {"message": r["message"], "expected_action": r["action"], "expected_intent": r["intent"]} for r in rows]


def handoff_reasons(reasons: list[str]) -> list[str]:
    return [code for marker, code in HANDOFF_REASONS if any(marker in r for r in reasons)] or ["unknown"]


def process(items: list[dict[str, str]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in items[:MAX_MESSAGES]:
        text = str(item.get("message", "")).strip()
        if not text:
            continue
        r = respond(text)
        check = r.eligibility
        verdict = check.verdict if check else None
        row: dict[str, Any] = {
            "message": text,
            "language": r.language,
            "intent": r.decision.intent,
            "action": r.decision.action.value,
            "priority": r.decision.priority,
            "handoff": handoff_reasons(r.decision.reasons) if r.decision.action.value == "human_handoff" else [],
            "route": check.route if check else None,
            "eligible": verdict.eligible if verdict else None,
            "amount": check.total_eur if check else 0,
            "passengers": check.passengers if check else 1,
            "missing": bool(check and check.missing),
            "reply": r.text,
        }
        if item.get("expected_action"):
            row["agrees"] = row["action"] == item["expected_action"] and row["intent"] == item.get("expected_intent", row["intent"])
        rows.append(row)

    ai = [r for r in rows if r["action"] == "ai_answer"]
    labelled = [r for r in rows if "agrees" in r]
    stats = {
        "total": len(rows),
        "ai": len(ai),
        "human": len(rows) - len(ai),
        "urgent": sum(r["priority"] == "high" for r in rows),
        "eligible": sum(bool(r["eligible"]) for r in rows),
        "eur": sum(r["amount"] for r in rows),
        "languages": len({r["language"] for r in rows}),
        "handoff_reasons": dict(Counter(c for r in rows for c in r["handoff"]).most_common()),
        "intents": dict(Counter(r["intent"] for r in rows).most_common()),
        "labelled": len(labelled),
        "agrees": sum(r["agrees"] for r in labelled),
    }
    return {"rows": rows, "stats": stats}
