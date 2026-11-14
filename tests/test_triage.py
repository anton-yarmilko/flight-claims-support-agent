import json
from pathlib import Path

import pytest

from claims_agent.triage import Action, triage

CASES = [json.loads(l) for l in (Path(__file__).parent.parent / "evals" / "cases.jsonl").read_text().splitlines() if l.strip()]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_eval_cases(case):
    d = triage(case["message"], ai_confidence=case.get("confidence", 1.0))
    assert d.intent == case["intent"], d
    assert d.action.value == case["action"], d


def test_low_confidence_goes_to_human():
    d = triage("Am I entitled to compensation for a delay?", ai_confidence=0.4)
    assert d.action is Action.HUMAN_HANDOFF
    assert any("too weak" in r for r in d.reasons)


def test_previous_handoff_keeps_human_owner():
    d = triage("What is the status of my claim?", previous_handoffs=1)
    assert d.action is Action.HUMAN_HANDOFF


def test_legal_threat_is_high_priority():
    assert triage("I will contact my lawyer").priority == "high"
