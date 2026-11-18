"""The show-case chips in the chat must keep showing what they were added for."""

import json
import re
from pathlib import Path

from claims_agent.agent import respond

HTML = (Path(__file__).resolve().parent.parent / "app" / "static" / "index.html").read_text(encoding="utf-8")


def feature_samples() -> list[str]:
    block = re.search(r"const FEATURE_SAMPLES = (\[.*?\]);", HTML, re.S).group(1)
    return json.loads(re.sub(r",\s*\]", "]", block))


def test_three_feature_chips():
    uk261, cause, exemption = feature_samples()
    r = respond(uk261)
    assert r.eligibility.verdict.currency == "GBP" and r.eligibility.verdict.amount_eur == 520
    r = respond(cause)
    assert r.eligibility.cause == "technical" and r.eligibility.verdict.amount_eur == 400
    r = respond(exemption)
    assert not r.eligibility.verdict.eligible and "5(1)(c)(ii)" in r.eligibility.verdict.reason
