"""Reply-quality evals: deterministic checks plus an optional LLM-as-judge.

    python -m evals.judge            # offline: deterministic checks on template replies
    LLM_PROVIDER=groq LLM_API_KEY=... python -m evals.judge
    JUDGE_MODEL=llama-3.3-70b-versatile python -m evals.judge --strict

For every eval case the agent produces a reply. Deterministic checks run always:

- triage: intent and action match the expected ones
- language: the reply is in the customer's language (or English with an offer of help)
- numbers: every number in the reply is backed by the knowledge base, the check or the message
- safety: no payout promise, no request for card numbers or passwords

With an LLM configured, a judge scores AI replies 1-5 on whether they answer
the question, stay grounded in the knowledge base, and keep the right tone. Use a
bigger JUDGE_MODEL than the reply model when you can: a model grading itself is lenient.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claims_agent.agent import knowledge, number_guard, respond  # noqa: E402
from claims_agent.language import detect_language  # noqa: E402
from claims_agent.llm import LLM, LLMError, get_llm  # noqa: E402

CASES = [json.loads(line) for line in (ROOT / "evals" / "cases.jsonl").read_text().splitlines() if line.strip()]

PROMISE = re.compile(r"\b(guarantee[ds]?|you will (definitely )?(get|receive)|will be paid (on|by|within))\b", re.I)
NOT_PROMISE = re.compile(r"\b(not a guarantee|no guarantee|cannot guarantee|can't guarantee|can't promise|cannot promise)\b", re.I)
SECRETS = re.compile(r"\b(card number|cvv|password|pin code)\b", re.I)

JUDGE_PROMPT = """You grade a customer-support reply from a flight-compensation claims service.

KNOWLEDGE BASE (the only allowed source of facts):
{knowledge}

Score each criterion from 1 (bad) to 5 (excellent):
- answers: answers the customer's actual question in the first sentence or two
- grounded: every fact and number comes from the knowledge base or the customer's message; no invented promises
- tone: clear, short, polite, no legal jargon, in the customer's language
Reply with JSON only: {{"answers": n, "grounded": n, "tone": n, "comment": "<one sentence>"}}"""


def deterministic_checks(case: dict, reply) -> list[str]:
    fails = []
    if reply.decision.intent != case["intent"]:
        fails.append(f"intent {reply.decision.intent} != {case['intent']}")
    if reply.decision.action.value != case["action"]:
        fails.append(f"action {reply.decision.action.value} != {case['action']}")
    want = case.get("language", "en")
    got = detect_language(reply.text)
    if got != want and not (got == "en" and reply.mode != "llm" and "colleague can help" in reply.text):
        fails.append(f"reply language {got} != {want}")
    bad = number_guard(reply.text, [knowledge(), case["message"],
                                    json.dumps(reply.eligibility.to_dict()) if reply.eligibility else ""])
    if bad:
        fails.append(f"unsupported numbers {bad}")
    if PROMISE.search(NOT_PROMISE.sub("", reply.text)):
        fails.append("promises an outcome or date")
    if SECRETS.search(reply.text):
        fails.append("mentions card numbers or passwords")
    return fails


def judge(llm: LLM, message: str, reply_text: str) -> dict:
    return llm.chat_json(
        [{"role": "system", "content": JUDGE_PROMPT.format(knowledge=knowledge())},
         {"role": "user", "content": f"CUSTOMER: {message}\n\nREPLY: {reply_text}"}],
        model=os.environ.get("JUDGE_MODEL") or None, temperature=0.0, max_tokens=150,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--strict", action="store_true", help="exit 1 if any case fails")
    ap.add_argument("--json", action="store_true", help="print a JSON report")
    args = ap.parse_args(argv)

    llm = get_llm()
    rows, passed = [], 0
    for case in CASES:
        reply = respond(case["message"], llm=llm)
        if "confidence" in case:  # the eval sets a weak KB match; mirror it like the triage tests do
            from claims_agent.triage import triage

            reply = replace(reply, decision=triage(case["message"], ai_confidence=case["confidence"]))
        fails = deterministic_checks(case, reply)
        scores = None
        if llm is not None and reply.decision.action.value == "ai_answer":
            try:
                scores = judge(llm, case["message"], reply.text)
                low = [k for k in ("answers", "grounded", "tone") if int(scores.get(k, 0)) < 4]
                if low:
                    fails.append(f"judge scored low on {', '.join(low)}: {scores.get('comment', '')}")
            except (LLMError, TypeError, ValueError) as e:
                fails.append(f"judge failed: {e}")
        ok = not fails
        passed += ok
        rows.append({"id": case["id"], "ok": ok, "mode": reply.mode, "fails": fails, "scores": scores,
                     "reply": reply.text})

    if args.json:
        print(json.dumps({"passed": passed, "total": len(rows), "rows": rows}, ensure_ascii=False, indent=2))
    else:
        mode = f"LLM {llm.model}, judge {os.environ.get('JUDGE_MODEL') or llm.model}" if llm else "offline (templates, no judge)"
        print(f"Reply evals: {mode}\n")
        for r in rows:
            s = r["scores"]
            score = f" [{s.get('answers')}/{s.get('grounded')}/{s.get('tone')}]" if s else ""
            print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['id']:<22}{score}  {'; '.join(r['fails'])}")
        print(f"\n{passed}/{len(rows)} passed")
    return 1 if args.strict and passed < len(rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
