"""Denied boarding: volunteers get agreed benefits, not EU261 compensation (Article 4(1))."""

import pytest

from claims_agent.agent import respond, template_reply
from claims_agent.facts import check_facts, extract_facts_rules


@pytest.mark.parametrize("text", [
    "Flight Warsaw to Lisbon was overbooked and I volunteered to take a later flight for a voucher",
    "Рейс Варшава Лісабон овербукінг, я добровільно відмовився від місця",
    "Lot z Warszawy do Lizbony, nadrezerwacja, dobrowolnie oddałem miejsce",
    "Flug Warschau Lissabon überbucht, ich habe freiwillig verzichtet",
])
def test_volunteer_not_eligible(text):
    r = check_facts(extract_facts_rules(text))
    assert r.verdict is not None and not r.verdict.eligible
    assert "voluntarily" in r.verdict.reason


@pytest.mark.parametrize("text", [
    "Overbooked flight Warsaw to Lisbon, I was denied boarding against my will",
    "Рейс Варшава Лісабон овербукінг, мене недобровільно не пустили",
    "Lot Warszawa Lizbona nadrezerwacja, nie dobrowolnie",
    "Flight Warsaw to Lisbon was overbooked, involuntary denied boarding",
])
def test_involuntary_still_eligible(text):
    r = check_facts(extract_facts_rules(text))
    assert r.verdict.eligible and r.verdict.amount_eur == 400


def test_reply_explains_in_customer_language():
    r = check_facts(extract_facts_rules("Рейс Варшава Лісабон овербукінг, я добровільно відмовився від місця"))
    assert "добровільно" in template_reply("eligibility", "uk", r)


def test_chat_end_to_end():
    r = respond("Flight Warsaw to Lisbon was overbooked and I volunteered for a voucher. Can I still claim compensation?")
    assert r.eligibility.verdict.eligible is False
