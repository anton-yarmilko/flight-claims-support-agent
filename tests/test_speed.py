"""Regression guard: the rule path must stay fast (it used to recompile ~500 regexes per message)."""

import time

from claims_agent.inbox import process, sample_messages


def test_inbox_of_200_messages_is_fast():
    items = (sample_messages() * 6)[:200]
    process(items[:1])  # warm-up builds the compiled patterns once
    started = time.perf_counter()
    out = process(items)
    assert out["stats"]["total"] == 200
    assert time.perf_counter() - started < 2.0  # about 0.1 s on a laptop; was about 4 s
