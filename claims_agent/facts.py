"""Pull flight facts out of a message or ticket and run the EU261 check on them.

The rule-based extractor works offline and covers the common phrasings. With an
LLM configured, `extract_facts` asks it first and then fills any gaps with the
rules, so a number the model invents for a field the text does not mention is
not accepted silently: every field records where it came from.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from .airports import AIRLINES, AIRPORTS, airline_in_text, airports_in_text, distance_km
from .eligibility import Disruption, Flight, Incident, Verdict, check

if TYPE_CHECKING:
    from .llm import LLM


@dataclass
class FlightFacts:
    origin: str | None = None  # IATA
    destination: str | None = None  # IATA
    airline: str | None = None  # IATA airline code
    flight_number: str | None = None
    date: str | None = None  # as written / ISO
    passenger: str | None = None
    booking_ref: str | None = None
    disruption: str | None = None  # delay | cancellation | denied_boarding
    delay_hours: float | None = None
    notice_days: int | None = None
    passengers: int | None = None  # people on the booking; compensation is per passenger
    sources: dict[str, str] = field(default_factory=dict)

    def missing_for_check(self) -> list[str]:
        missing = []
        if not self.origin or not self.destination:
            missing.append("route (from and to)")
        if not self.disruption:
            missing.append("what happened (delay, cancellation or denied boarding)")
        if self.disruption == "delay" and self.delay_hours is None:
            missing.append("how late you arrived at the final destination")
        return missing

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_HOUR_UNIT = (r"(?:hours?|hrs?|h\b|годин\w*|год\b|час\w*|godzin\w*|godz\b|stunden?|std\b|horas?"
              r"|heures?|ore\b|ora\b|uur|ώρ\w*|saat|[óo]r[áa]\w*|hodin\w*|sat[ai]?\b|timer|timmar|tunti\w*|tunnin)")
_MINUTE_UNIT = r"(?:minutes?|mins?|хвилин\w*|хв\b|минут\w*|minut\w*|min\b|minuten|minuti|minutos|λεπτ\w*|dakika|perc\w*|minuuttia)"
_HOURS = r"(\d+(?:[.,]\d+)?)\s*" + _HOUR_UNIT
_MINUTES = r"(\d+)\s*" + _MINUTE_UNIT
_CANCEL = (r"cancel|скасува|отмен|odwo[łl]a|annul|gestrichen|anulat|geannuleerd|annulering|ακυρ|iptal|t[öo]r[öo]lt"
           r"|zru[šs]en|otkaz|aflys|kansell|innstilt|inst[äa]lld|peruttu|peruutettiin")
_DENIED = (r"denied boarding|overbook|відмовили в посадці|овербук|отказали в посадке|odm[óo]wiono wej|nadrezerwac"
           r"|[üu]berbuch|nicht mitgenommen|denegaron el embarque|refus d.embarquement|surr[ée]servation|negato l.imbarco"
           r"|recusa de embarque|refuz la [îi]mbarcare|instapweigering|άρνηση επιβίβασης|u[çc]a[ğg]a al[ıi]nmad|nepustili"
           r"|nisu me pustili|n[æa]gtet boarding|nektet ombordstigning|nekad ombordstigning|ei p[äa][äa]ssyt koneeseen")
_DELAY = (r"delay|late|затрим|запізн|задерж|опозда|op[óo][źz]ni|versp[äa]t|retras|retard|ritard|atras|[îi]nt[âa]rzi"
          r"|vertraag|vertraging|καθυστ|r[öo]tar|gecik|k[ée]s|zpo[žz]d|kasn|forsink|f[öo]rsen|my[öo]h[äa]|viiv[äa]s")
_DATE = r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\s?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s?\d{2,4})\b"


# Spelled-out durations ("three hours", "tres horas", "чотири години"), 1 to 12, in the main languages.
_NUMBER_WORDS: dict[str, int] = {}
for _n, _words in enumerate([
    "one un una uno ein eine eins один одна одну jeden jedna jedną um uma één en ett yksi egy jeden jedna μία μια bir",
    "two dos deux due zwei два дві dwa dwie dois duas twee to två kaksi kettő két dva dvě δύο iki",
    "three tres trois tre drei три trzy três drie tre tre kolme három tři τρεις τρία üç",
    "four cuatro quatre quattro vier чотири четыре cztery quatro vier fire fyra neljä négy čtyři τέσσερις τέσσερα dört",
    "five cinco cinq cinque fünf п'ять пять pięć cinco vijf fem fem viisi öt pět πέντε beş",
    "six seis six sei sechs шість шесть sześć seis zes seks sex kuusi hat šest έξι altı",
    "seven siete sept sette sieben сім семь siedem sete zeven syv sju seitsemän hét sedm επτά yedi",
    "eight ocho huit otto acht вісім восемь osiem oito acht otte åtta kahdeksan nyolc osm οκτώ sekiz",
    "nine nueve neuf nove neun дев'ять девять dziewięć nove negen ni nio yhdeksän kilenc devět εννέα dokuz",
    "ten diez dix dieci zehn десять dziesięć dez tien ti tio kymmenen tíz deset δέκα on",
    "eleven once onze undici elf одинадцять одиннадцать jedenaście onze elf elleve elva tizenegy jedenáct έντεκα",
    "twelve doce douze dodici zwölf дванадцять двенадцать dwanaście doze twaalf tolv tolv tizenkét dvanáct δώδεκα",
], start=1):
    for _w in _words.split():
        _NUMBER_WORDS.setdefault(_w, _n)
_UNIT_AFTER = re.compile(r"\s+(?:" + _HOUR_UNIT + "|" + _MINUTE_UNIT + ")")
_NUMBER_WORD_RE = re.compile(r"(?<!\w)(" + "|".join(sorted(map(re.escape, _NUMBER_WORDS), key=len, reverse=True)) + r")(?=\s+)")


_HALF_AFTER = re.compile(r"(\d+)\s*(?:½|and a half|і пів|с половиной|i pół|und ein halb|y media|et demie|e mezza|e meia|en een half)\s+")
_ONE_AND_HALF = re.compile(r"(?<!\w)(?:one and a half|півтори|полтора|półtorej|anderthalb|eineinhalb|uno y medio|une heure et demie)(?=\s)")


def spell_numbers(low: str) -> str:
    """Turn a spelled-out number into digits when an hour or minute word follows it.

    Also "3 and a half hours" -> "3.5 hours" and "півтори години" -> "1.5 години".
    """
    low = _HALF_AFTER.sub(lambda m: f"{m.group(1)}.5 ", low)
    low = _ONE_AND_HALF.sub("1.5", low)
    def repl(m: re.Match[str]) -> str:
        unit = _UNIT_AFTER.match(low, m.end())
        return str(_NUMBER_WORDS[m.group(1)]) if unit else m.group(1)
    return _NUMBER_WORD_RE.sub(repl, low)


# "we were three", "family of 4", "нас було троє", "było nas czworo", "wir waren zu dritt"...
_COLLECTIVE = {"двоє": 2, "троє": 3, "четверо": 4, "п'ятеро": 5, "шестеро": 6, "двое": 2, "трое": 3,
               "пятеро": 5, "dwoje": 2, "troje": 3, "czworo": 4, "pięcioro": 5, "zu zweit": 2, "zu dritt": 3,
               "zu viert": 4, "zu fünft": 5, "both of us": 2, "the two of us": 2, "my wife and i": 2,
               "my husband and i": 2, "my partner and i": 2}
_PAX_NUM = r"(\d{1,2}|[a-zа-яіїєґąćęłńóśźżäöüßéèêàçíñ']+)"
_PAX_PATTERNS = [
    _PAX_NUM + r"\s+(?:passengers?|people|persons|adults|of us|пасажир\w*|пассажир\w*|людей|осіб|человек"
    r"|pasa[żz]er\w*|os[óo]b\w*|passagiere|personen|pasajeros|personas|passagers|personnes|passeggeri|persone"
    r"|passageiros|pessoas|passagiers|matkustaja\w*|utas\w*|cestuj[íi]c\w*|yolcu|επιβάτ\w*)",
    r"(?:family of|we were|we are|there were|нас було|нас было|нас|было нас|było nas|wir waren|éramos|somos"
    r"|nous étions|nous sommes|eravamo|siamo|we waren|vi var|olimme)\s+(?:in |zu )?" + _PAX_NUM
    + r"(?!\s*(?:" + _HOUR_UNIT + "|" + _MINUTE_UNIT + "))",  # "we were 4 hours late" is not 4 people
]


def passengers_in(low: str) -> int | None:
    for phrase, n in _COLLECTIVE.items():
        if re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", low):
            return n
    for pat in _PAX_PATTERNS:
        for m in re.finditer(pat, low):
            word = m.group(1)
            n = int(word) if word.isdigit() else _NUMBER_WORDS.get(word) or _COLLECTIVE.get(word)
            if n and 1 <= n <= 20:
                return n
    return None


def extract_facts_rules(text: str) -> FlightFacts:
    f = FlightFacts()
    low = text.lower()

    ports = airports_in_text(text)
    # "from X to Y" order is the usual one; IATA pairs like "LIS-BER" keep their order too.
    if len(ports) >= 2:
        f.origin, f.destination = ports[0].iata, ports[1].iata
    elif len(ports) == 1:
        f.origin = ports[0].iata

    f.airline = airline_in_text(text)
    m = re.search(r"\b([A-Z0-9]{2})\s?(\d{2,4})\b", text)
    if m and m.group(1) in AIRLINES:
        f.flight_number = f"{m.group(1)}{m.group(2)}"
        f.airline = f.airline or m.group(1)

    if re.search(_CANCEL, low):
        f.disruption = "cancellation"
    elif re.search(_DENIED, low):
        f.disruption = "denied_boarding"
    elif re.search(_DELAY, low):
        f.disruption = "delay"

    spelled = spell_numbers(low)
    h = re.search(_HOURS, spelled)
    mins = re.search(_MINUTES, spelled)
    if h:
        f.delay_hours = float(h.group(1).replace(",", "."))
        if mins and mins.start() > h.start():
            f.delay_hours += int(mins.group(1)) / 60
    elif mins:
        f.delay_hours = int(mins.group(1)) / 60
    if f.delay_hours is not None and f.disruption is None:
        f.disruption = "delay"

    n = re.search(r"(\d+)\s*(?:days?|днів|дні|дней|дня|dni|tage?n?|d[íi]as|jours?|giorni|zile|dagen|dage|dager|dagar|ημέρες|g[üu]n|nap\w*|dn[íi]|dana|p[äa]iv[äa][äa])\s*(?:before|in advance|до|przed|vorher|vor|antes|avant|prima|înainte|voor|før|före|πριν|önce|előtt|předem|pre|ennen)", low)
    if n:
        f.notice_days = int(n.group(1))

    f.passengers = passengers_in(low)

    d = re.search(_DATE, low)
    if d:
        f.date = d.group(1)
    b = re.search(r"\b(?:booking|pnr|reservation|confirmation|бронювання|rezerwac\w*|buchung\w*|reserva)\W{0,15}([A-Z0-9]{6})\b", text, re.I)
    if b and not b.group(1).isdigit():
        f.booking_ref = b.group(1).upper()

    p = re.search(r"(?:passenger(?: name)?|name|пасажир|pasa[żz]er|passagier|pasajero)\s*[:\-]\s*"
                  r"([A-ZА-ЯІЇЄ][\w'\-]+(?:[ /][A-ZА-ЯІЇЄ][\w'\-]+)+)", text, re.I)
    if p:
        f.passenger = p.group(1).strip()

    f.sources = {k: "rules" for k, v in f.to_dict().items() if v not in (None, {}) and k != "sources"}
    return f


EXTRACT_PROMPT = """Extract flight details from the customer's text or ticket. Use only what is written.
If a field is not stated, use null. Never guess.
Reply with JSON only:
{"origin": "<IATA airport code or city>", "destination": "<IATA code or city>",
 "airline": "<airline name or 2-letter code>", "flight_number": "<e.g. FR1234>",
 "date": "<YYYY-MM-DD if known>", "passenger": "<name>", "booking_ref": "<6 chars>",
 "disruption": "delay|cancellation|denied_boarding|null",
 "delay_hours": <number or null>, "notice_days": <number or null>,
 "passengers": <number of people travelling on the booking, or null>}"""


def _norm_airport(value: Any) -> str | None:
    if not value or not isinstance(value, str):
        return None
    from .airports import find_airport

    a = find_airport(value)
    if a:
        return a.iata
    hits = airports_in_text(value)
    return hits[0].iata if hits else None


def _norm_airline(value: Any) -> str | None:
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    if v.upper() in AIRLINES:
        return v.upper()
    return airline_in_text(v)


def merge_llm_facts(base: FlightFacts, data: dict[str, Any]) -> FlightFacts:
    """Fill fields the rules missed with the LLM's answer, normalised and type-checked."""
    cleaners = {
        "origin": _norm_airport,
        "destination": _norm_airport,
        "airline": _norm_airline,
        "flight_number": lambda v: re.sub(r"\s", "", v).upper() if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9]{2}\s?\d{1,4}", v.strip()) else None,
        "date": lambda v: v.strip() if isinstance(v, str) and v.strip() and v.lower() != "null" else None,
        "passenger": lambda v: v.strip() if isinstance(v, str) and v.strip() and v.lower() != "null" else None,
        "booking_ref": lambda v: v.strip().upper() if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9]{6}", v.strip()) else None,
        "disruption": lambda v: v if v in {"delay", "cancellation", "denied_boarding"} else None,
        "delay_hours": lambda v: float(v) if isinstance(v, (int, float)) and 0 <= v < 100 else None,
        "notice_days": lambda v: int(v) if isinstance(v, (int, float)) and 0 <= v < 400 else None,
        "passengers": lambda v: int(v) if isinstance(v, (int, float)) and 1 <= v <= 20 else None,
    }
    for key, clean in cleaners.items():
        if getattr(base, key) is not None:
            continue
        try:
            value = clean(data.get(key))
        except (TypeError, ValueError):
            value = None
        if value is not None:
            setattr(base, key, value)
            base.sources[key] = "llm"
    if base.flight_number and not base.airline and base.flight_number[:2] in AIRLINES:
        base.airline = base.flight_number[:2]
        base.sources["airline"] = base.sources.get("flight_number", "rules")
    return base


def extract_facts(text: str, llm: LLM | None = None) -> FlightFacts:
    facts = extract_facts_rules(text)
    if llm is not None:
        from .llm import LLMError

        try:
            data = llm.chat_json(
                [{"role": "system", "content": EXTRACT_PROMPT}, {"role": "user", "content": text[:6000]}],
                temperature=0.0,
                max_tokens=300,
            )
            facts = merge_llm_facts(facts, data)
        except LLMError:
            pass
    return facts


def prefer_latest(facts: FlightFacts, latest: FlightFacts) -> FlightFacts:
    """Let what the customer said last win over earlier turns.

    The conversation is read as one text, so an older route would otherwise beat
    a new one. The route only switches when the new message names both ends.
    """
    for k, v in vars(latest).items():
        if v in (None, "", [], {}) or k in ("origin", "destination", "sources"):
            continue
        setattr(facts, k, v)
    if latest.origin and latest.destination:
        facts.origin, facts.destination = latest.origin, latest.destination
    facts.sources = {**facts.sources, **latest.sources}
    return facts


@dataclass
class EligibilityResult:
    verdict: Verdict | None
    distance_km: int | None
    missing: list[str]
    route: str | None = None
    passengers: int = 1

    @property
    def total_eur(self) -> int:
        return self.verdict.amount_eur * self.passengers if self.verdict and self.verdict.eligible else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.verdict.eligible if self.verdict else None,
            "amount_eur": self.verdict.amount_eur if self.verdict else None,
            "passengers": self.passengers,
            "total_eur": self.total_eur,
            "reason": self.verdict.reason if self.verdict else None,
            "distance_km": self.distance_km,
            "route": self.route,
            "missing": self.missing,
        }


def check_facts(facts: FlightFacts, *, extraordinary: bool = False) -> EligibilityResult:
    missing = facts.missing_for_check()
    if facts.origin and facts.destination and facts.origin == facts.destination:
        missing.append("a different departure and arrival airport")
    if missing:
        return EligibilityResult(None, None, missing)

    o, d = AIRPORTS[facts.origin], AIRPORTS[facts.destination]  # type: ignore[index]
    km = distance_km(o, d)
    if not o.eu and d.eu and not facts.airline:
        return EligibilityResult(None, km, ["the airline (flights into the EU are covered only on EU airlines)"],
                                 f"{o.city} - {d.city}")
    eu_carrier = AIRLINES.get(facts.airline or "", ("", False))[1]
    flight = Flight(departs_eu=o.eu, arrives_eu=d.eu, eu_carrier=eu_carrier, distance_km=km, intra_eu=o.eu and d.eu)
    incident = Incident(
        kind=Disruption(facts.disruption),
        arrival_delay_hours=facts.delay_hours or 0.0,
        cancellation_notice_days=facts.notice_days,
        extraordinary_circumstances=extraordinary,
    )
    return EligibilityResult(check(flight, incident), km, [], f"{o.city} - {d.city}", facts.passengers or 1)
