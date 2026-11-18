"""Fixed-template reply to an airline's refusal."""

from claims_agent.airline_reply import analyse


def test_contest_draft_cites_case_law_and_reference():
    a = analyse("Booking reference ABC123. Your flight was delayed due to a technical fault with the aircraft.")
    assert a.recommendation == "contest"
    assert "reference ABC123" in a.draft
    assert "C-549/07" in a.draft  # the category's case law
    assert "burden of proving extraordinary circumstances" in a.draft
    assert "14 days" in a.draft


def test_review_draft_asks_for_evidence_only():
    a = analyse("The delay was caused by severe weather at the departure airport.")
    assert a.recommendation == "review"
    assert "please provide" in a.draft and "C-549/07" not in a.draft


def test_no_draft_when_refusal_is_probably_valid():
    a = analyse("The flight was diverted after a bird strike on approach.")
    assert a.recommendation == "unlikely" and a.draft is None
    assert analyse("Due to a bird strike").to_dict()["draft"] is None
