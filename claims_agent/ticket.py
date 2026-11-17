"""Read a boarding pass or e-ticket and turn it into flight facts.

Three inputs are accepted:

- the text under a boarding-pass barcode (IATA BCBP), parsed offline and exactly;
- pasted e-ticket or booking-confirmation text, rules first, LLM for the gaps;
- a photo or screenshot, read by a vision model when one is configured.
"""

from __future__ import annotations

import base64
import datetime as dt
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .airports import AIRLINES, AIRPORTS
from .facts import EXTRACT_PROMPT, FlightFacts, extract_facts, merge_llm_facts

if TYPE_CHECKING:
    from .llm import LLM

# M1DOE/JOHN            EABC123 LISBERFR 1234 123Y014C0001 100
# Real barcodes are fixed-width; the pattern also accepts hand-typed text with uneven spaces.
BCBP = re.compile(
    r"M[1-4](?P<name>[A-Z][A-Z/ \-]{1,19}?)\s*E?(?P<pnr>[A-Z0-9]{5,7})\s+(?P<from>[A-Z]{3})(?P<to>[A-Z]{3})"
    r"(?P<carrier>[A-Z0-9]{2}[A-Z]?)\s*(?P<flight>\d{1,4}[A-Z]?)\s+(?P<julian>\d{3})"
)


@dataclass
class TicketResult:
    facts: FlightFacts
    method: str  # "barcode" | "text" | "image" | "none"
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"facts": self.facts.to_dict(), "method": self.method, "notes": self.notes}


def parse_bcbp(text: str, today: dt.date | None = None) -> FlightFacts | None:
    m = BCBP.search(text.upper())
    if not m:
        return None
    today = today or dt.date.today()
    name = m.group("name").strip()
    last, _, first = name.partition("/")
    carrier = m.group("carrier").strip()
    number = m.group("flight").strip().lstrip("0")
    day_of_year = int(m.group("julian"))
    date = None
    if 1 <= day_of_year <= 366:
        # BCBP has no year: take the most recent date with that day number.
        for year in (today.year, today.year - 1):
            try:
                d = dt.date(year, 1, 1) + dt.timedelta(days=day_of_year - 1)
            except ValueError:
                continue
            if d <= today + dt.timedelta(days=1) and d.year == year:
                date = d.isoformat()
                break
    f = FlightFacts(
        origin=m.group("from") if m.group("from") in AIRPORTS else None,
        destination=m.group("to") if m.group("to") in AIRPORTS else None,
        airline=carrier if carrier in AIRLINES else None,
        flight_number=f"{carrier}{number}" if carrier and number else None,
        date=date,
        passenger=" ".join(p.title() for p in (first, last) if p) or None,
        booking_ref=m.group("pnr").strip() or None,
    )
    f.sources = {k: "barcode" for k, v in f.to_dict().items() if v not in (None, {}) and k != "sources"}
    unknown = [code for code in (m.group("from"), m.group("to")) if code not in AIRPORTS]
    if unknown:
        f.sources["unknown_airports"] = ",".join(unknown)
    return f


def read_ticket_text(text: str, llm: "LLM | None" = None) -> TicketResult:
    bcbp = parse_bcbp(text)
    if bcbp:
        notes = []
        if "unknown_airports" in bcbp.sources:
            notes.append(f"Airport codes not in the demo table: {bcbp.sources.pop('unknown_airports')}.")
        return TicketResult(bcbp, "barcode", notes)
    facts = extract_facts(text, llm)
    notes = [] if llm else ["Offline mode: rule-based extraction. Configure an LLM for messier tickets."]
    return TicketResult(facts, "text", notes)


IMAGE_PROMPT = EXTRACT_PROMPT + "\nThe input is a photo or screenshot of a boarding pass, e-ticket or booking confirmation."


def read_ticket_image(image: bytes, mime: str, llm: "LLM | None") -> TicketResult:
    if llm is None or not llm.vision_model:
        return TicketResult(FlightFacts(), "none", [
            "Reading photos needs a vision model. Set LLM_PROVIDER (and LLM_VISION_MODEL if needed), "
            "or paste the ticket text or the barcode text instead."])
    from .llm import LLMError

    data_uri = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    try:
        data = llm.chat_json(
            [{"role": "system", "content": IMAGE_PROMPT},
             {"role": "user", "content": [
                 {"type": "text", "text": "Extract the flight details from this document."},
                 {"type": "image_url", "image_url": {"url": data_uri}}]}],
            model=llm.vision_model, temperature=0.0, max_tokens=300,
        )
    except LLMError as e:
        return TicketResult(FlightFacts(), "none", [f"Vision model failed: {e}"])
    facts = merge_llm_facts(FlightFacts(), data)
    return TicketResult(facts, "image", ["Read by a vision model: check the fields before filing the claim."])
