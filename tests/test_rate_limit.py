"""LLM calls on the public demo are capped per visitor and in total."""

from app import server
from app.server import RateLimiter


def test_per_visitor_cap_and_window():
    rl = RateLimiter(per_client=2, total=100, window=60)
    assert rl.allow("a", now=0) and rl.allow("a", now=1)
    assert not rl.allow("a", now=2)
    assert rl.allow("b", now=2)  # other visitors are not affected
    assert rl.allow("a", now=61)  # the window slides


def test_total_cap():
    rl = RateLimiter(per_client=10, total=3, window=60)
    assert all(rl.allow(c, now=0) for c in "abc")
    assert not rl.allow("d", now=1)


class _NoCallLLM:
    model = vision_model = "should-not-be-called"

    def chat(self, *a, **k):  # pragma: no cover - failing here is the point
        raise AssertionError("LLM called over the limit")


def test_over_limit_falls_back_to_templates(monkeypatch):
    monkeypatch.setattr(server, "LLM_CLIENT", _NoCallLLM())
    monkeypatch.setattr(server, "LIMITER", RateLimiter(per_client=0, total=0))
    out = server.api("/api/chat", {"message": "My flight FR1234 from WAW to BCN was cancelled"}, client="x")
    assert out["text"]
    assert out["mode"].endswith("(rate limit)")


def test_rules_only_endpoints_are_not_limited(monkeypatch):
    monkeypatch.setattr(server, "LLM_CLIENT", _NoCallLLM())
    monkeypatch.setattr(server, "LIMITER", RateLimiter(per_client=0, total=0))
    assert server.api("/api/inbox", {}, client="x")["stats"]["total"] > 0
