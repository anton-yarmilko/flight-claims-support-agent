"""Small airport and airline reference data for the demo.

Enough to compute EU261 distance bands for common routes. A real service would
use a full airport database. "EU" here means where EU261 applies: the EU plus
Iceland, Norway and Switzerland. The UK has its own UK261 and is marked non-EU.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Airport:
    iata: str
    city: str
    country: str
    eu: bool
    lat: float
    lon: float
    aliases: tuple[str, ...] = ()


_A = Airport
AIRPORTS: dict[str, Airport] = {a.iata: a for a in [
    _A("LIS", "Lisbon", "PT", True, 38.7742, -9.1342, ("lisboa", "lissabon", "лісабон", "lizbona")),
    _A("OPO", "Porto", "PT", True, 41.2481, -8.6814, ("порту",)),
    _A("MAD", "Madrid", "ES", True, 40.4719, -3.5626, ("мадрид",)),
    _A("BCN", "Barcelona", "ES", True, 41.2971, 2.0785, ("барселона",)),
    _A("AGP", "Malaga", "ES", True, 36.6749, -4.4991, ("málaga", "малага")),
    _A("PMI", "Palma de Mallorca", "ES", True, 39.5517, 2.7388, ("palma", "mallorca", "майорка")),
    _A("CDG", "Paris", "FR", True, 49.0097, 2.5479, ("paryż", "париж", "parís")),
    _A("NCE", "Nice", "FR", True, 43.6584, 7.2159, ("nizza", "ніцца")),
    _A("AMS", "Amsterdam", "NL", True, 52.3105, 4.7683, ("амстердам",)),
    _A("BRU", "Brussels", "BE", True, 50.9014, 4.4844, ("bruxelles", "brüssel", "брюссель", "bruksela")),
    _A("FRA", "Frankfurt", "DE", True, 50.0379, 8.5622, ("франкфурт",)),
    _A("MUC", "Munich", "DE", True, 48.3538, 11.7861, ("münchen", "мюнхен", "monachium")),
    _A("BER", "Berlin", "DE", True, 52.3667, 13.5033, ("берлін", "берлин")),
    _A("HAM", "Hamburg", "DE", True, 53.6304, 9.9882, ("гамбург",)),
    _A("DUS", "Dusseldorf", "DE", True, 51.2895, 6.7668, ("düsseldorf", "дюссельдорф")),
    _A("VIE", "Vienna", "AT", True, 48.1103, 16.5697, ("wien", "відень", "вена", "wiedeń", "viena")),
    _A("ZRH", "Zurich", "CH", True, 47.4647, 8.5492, ("zürich", "цюрих")),
    _A("GVA", "Geneva", "CH", True, 46.2381, 6.1090, ("genève", "genf", "женева")),
    _A("FCO", "Rome", "IT", True, 41.8003, 12.2389, ("roma", "rom", "рим", "rzym")),
    _A("MXP", "Milan", "IT", True, 45.6306, 8.7281, ("milano", "mailand", "мілан", "mediolan")),
    _A("VCE", "Venice", "IT", True, 45.5053, 12.3519, ("venezia", "венеція")),
    _A("ATH", "Athens", "GR", True, 37.9364, 23.9445, ("athen", "афіни", "ateny", "atenas")),
    _A("WAW", "Warsaw", "PL", True, 52.1657, 20.9671, ("warszawa", "варшава", "warschau", "varsovia")),
    _A("KRK", "Krakow", "PL", True, 50.0777, 19.7848, ("kraków", "краків", "krakau")),
    _A("GDN", "Gdansk", "PL", True, 54.3776, 18.4662, ("gdańsk", "гданськ")),
    _A("WRO", "Wroclaw", "PL", True, 51.1027, 16.8858, ("wrocław", "вроцлав")),
    _A("PRG", "Prague", "CZ", True, 50.1008, 14.2600, ("praha", "prag", "прага", "praga")),
    _A("BUD", "Budapest", "HU", True, 47.4369, 19.2556, ("будапешт",)),
    _A("OTP", "Bucharest", "RO", True, 44.5711, 26.0850, ("bucurești", "бухарест")),
    _A("SOF", "Sofia", "BG", True, 42.6967, 23.4114, ("софія",)),
    _A("VNO", "Vilnius", "LT", True, 54.6341, 25.2858, ("вільнюс", "wilno")),
    _A("KUN", "Kaunas", "LT", True, 54.9639, 24.0848, ("каунас",)),
    _A("RIX", "Riga", "LV", True, 56.9236, 23.9711, ("rīga", "рига")),
    _A("TLL", "Tallinn", "EE", True, 59.4133, 24.8328, ("таллінн",)),
    _A("HEL", "Helsinki", "FI", True, 60.3172, 24.9633, ("гельсінкі",)),
    _A("ARN", "Stockholm", "SE", True, 59.6519, 17.9186, ("стокгольм", "sztokholm")),
    _A("CPH", "Copenhagen", "DK", True, 55.6180, 12.6560, ("københavn", "kopenhagen", "копенгаген", "kopenhaga")),
    _A("OSL", "Oslo", "NO", True, 60.1939, 11.1004, ("осло",)),
    _A("KEF", "Reykjavik", "IS", True, 63.9850, -22.6056, ("reykjavík", "рейк'явік")),
    _A("DUB", "Dublin", "IE", True, 53.4213, -6.2701, ("дублін",)),
    _A("LHR", "London", "GB", False, 51.4700, -0.4543, ("londyn", "лондон", "londres", "heathrow")),
    _A("STN", "London Stansted", "GB", False, 51.8860, 0.2389, ("stansted",)),
    _A("IST", "Istanbul", "TR", False, 41.2753, 28.7519, ("стамбул", "stambuł", "estambul")),
    _A("AYT", "Antalya", "TR", False, 36.8987, 30.8005, ("анталія",)),
    _A("DXB", "Dubai", "AE", False, 25.2532, 55.3657, ("дубай", "dubaj")),
    _A("DOH", "Doha", "QA", False, 25.2731, 51.6081, ("доха",)),
    _A("TLV", "Tel Aviv", "IL", False, 32.0055, 34.8854, ("тель-авів",)),
    _A("CAI", "Cairo", "EG", False, 30.1219, 31.4056, ("каїр", "kair")),
    _A("HRG", "Hurghada", "EG", False, 27.1783, 33.7994, ("хургада",)),
    _A("JFK", "New York", "US", False, 40.6413, -73.7781, ("нью-йорк", "nowy jork", "nueva york")),
    _A("ORD", "Chicago", "US", False, 41.9742, -87.9073, ("чикаго",)),
    _A("YYZ", "Toronto", "CA", False, 43.6777, -79.6248, ("торонто",)),
    _A("BKK", "Bangkok", "TH", False, 13.6900, 100.7501, ("бангкок",)),
]}

# IATA airline code -> (name, EU carrier for EU261)
AIRLINES: dict[str, tuple[str, bool]] = {
    "FR": ("Ryanair", True), "U2": ("easyJet", False), "EJU": ("easyJet Europe", True),
    "W6": ("Wizz Air Hungary", True), "LH": ("Lufthansa", True), "AF": ("Air France", True),
    "KL": ("KLM", True), "BA": ("British Airways", False), "IB": ("Iberia", True),
    "VY": ("Vueling", True), "TP": ("TAP Air Portugal", True), "LO": ("LOT Polish Airlines", True),
    "SK": ("SAS", True), "AY": ("Finnair", True), "OS": ("Austrian Airlines", True),
    "LX": ("SWISS", True), "SN": ("Brussels Airlines", True), "AZ": ("ITA Airways", True),
    "EW": ("Eurowings", True), "DY": ("Norwegian", True), "BT": ("airBaltic", True),
    "A3": ("Aegean Airlines", True), "EI": ("Aer Lingus", True), "TK": ("Turkish Airlines", False),
    "EK": ("Emirates", False), "QR": ("Qatar Airways", False), "PS": ("Ukraine International", False),
    "UA": ("United Airlines", False), "DL": ("Delta Air Lines", False), "AA": ("American Airlines", False),
}

AIRLINE_NAMES = {name.lower(): code for code, (name, _) in AIRLINES.items()}
AIRLINE_NAMES.update({"wizz": "W6", "wizzair": "W6", "wizz air": "W6", "easyjet": "U2", "lot": "LO",
                      "райанейр": "FR", "візейр": "W6", "люфтганза": "LH", "мау": "PS"})


def find_airport(token: str) -> Airport | None:
    t = token.strip().lower()
    if len(t) == 3 and t.upper() in AIRPORTS:
        return AIRPORTS[t.upper()]
    for a in AIRPORTS.values():
        if t == a.city.lower() or t in a.aliases:
            return a
    return None


def airports_in_text(text: str) -> list[Airport]:
    """Airports mentioned in text, in order of appearance (IATA codes or city names)."""
    hits: list[tuple[int, Airport]] = []
    low = text.lower()
    for a in AIRPORTS.values():
        names = [a.city.lower(), *a.aliases]
        best = None
        for n in names:
            # Ukrainian/Polish nouns inflect ("з Лісабона", "z Warszawy"); match the stem of longer names.
            stem = n[:-1] if len(n) > 5 else n
            m = re.search(r"(?<!\w)" + re.escape(stem), low)
            if m and (best is None or m.start() < best):
                best = m.start()
        m = re.search(r"\b" + a.iata + r"\b", text)
        if m and (best is None or m.start() < best):
            best = m.start()
        if best is not None:
            hits.append((best, a))
    hits.sort(key=lambda h: h[0])
    seen: list[Airport] = []
    for _, a in hits:
        if a not in seen:
            seen.append(a)
    return seen


def airline_in_text(text: str) -> str | None:
    low = text.lower()
    for name, code in sorted(AIRLINE_NAMES.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", low):
            return code
    m = re.search(r"\b([A-Z0-9]{2})\s?(\d{2,4})\b", text)
    if m and m.group(1) in AIRLINES:
        return m.group(1)
    return None


def distance_km(a: Airport, b: Airport) -> int:
    """Great-circle distance, as EU261 Article 7 uses."""
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)))
