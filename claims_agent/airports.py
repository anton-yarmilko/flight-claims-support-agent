"""Small airport and airline reference data for the demo.

Enough to compute EU261 distance bands for common routes. A real service would
use a full airport database. "EU" here means where EU261 applies: the EU plus
Iceland, Norway and Switzerland. The UK has its own UK261 and is marked non-EU.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache


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
    _A("LIS", "Lisbon", "PT", True, 38.7742, -9.1342, ("lisboa", "lissabon", "лісабон", "lizbona", "лиссабон", "lisbonne", "lisbona", "lizbon", "lisszabon", "lisabon", "λισαβόνα")),
    _A("OPO", "Porto", "PT", True, 41.2481, -8.6814, ("порту",)),
    _A("MAD", "Madrid", "ES", True, 40.4719, -3.5626, ("мадрид",)),
    _A("BCN", "Barcelona", "ES", True, 41.2971, 2.0785, ("барселона", "barcelone", "βαρκελώνη", "barselona")),
    _A("AGP", "Malaga", "ES", True, 36.6749, -4.4991, ("málaga", "малага")),
    _A("PMI", "Palma de Mallorca", "ES", True, 39.5517, 2.7388, ("palma", "mallorca", "майорка")),
    _A("CDG", "Paris", "FR", True, 49.0097, 2.5479, ("paryż", "париж", "parís", "parigi", "παρίσι", "párizs", "paříž", "pariz", "pariisi")),
    _A("NCE", "Nice", "FR", True, 43.6584, 7.2159, ("nizza", "ніцца")),
    _A("AMS", "Amsterdam", "NL", True, 52.3105, 4.7683, ("амстердам",)),
    _A("BRU", "Brussels", "BE", True, 50.9014, 4.4844, ("bruxelles", "brüssel", "брюссель", "bruksela")),
    _A("FRA", "Frankfurt", "DE", True, 50.0379, 8.5622, ("франкфурт",)),
    _A("MUC", "Munich", "DE", True, 48.3538, 11.7861, ("münchen", "мюнхен", "monachium", "monaco di baviera", "munique", "múnich", "μόναχο", "münih", "mnichov", "minhen")),
    _A("BER", "Berlin", "DE", True, 52.3667, 13.5033, ("берлін", "берлин", "berlino", "berlín", "berlijn", "βερολίνο")),
    _A("HAM", "Hamburg", "DE", True, 53.6304, 9.9882, ("гамбург",)),
    _A("DUS", "Dusseldorf", "DE", True, 51.2895, 6.7668, ("düsseldorf", "дюссельдорф")),
    _A("VIE", "Vienna", "AT", True, 48.1103, 16.5697, ("wien", "відень", "вена", "wiedeń", "viena", "vienna", "vienne", "wenen", "beč", "viyana", "bécs", "vídeň", "vídně", "βιέννη", "wenen")),
    _A("ZRH", "Zurich", "CH", True, 47.4647, 8.5492, ("zürich", "цюрих")),
    _A("GVA", "Geneva", "CH", True, 46.2381, 6.1090, ("genève", "genf", "женева")),
    _A("FCO", "Rome", "IT", True, 41.8003, 12.2389, ("roma", "rom", "рим", "rzym", "rome", "ρώμη", "róma", "řím", "rooma")),
    _A("MXP", "Milan", "IT", True, 45.6306, 8.7281, ("milano", "mailand", "мілан", "mediolan")),
    _A("VCE", "Venice", "IT", True, 45.5053, 12.3519, ("venezia", "венеція")),
    _A("ATH", "Athens", "GR", True, 37.9364, 23.9445, ("athen", "афіни", "ateny", "atenas", "афины", "athènes", "atene", "atena", "athene", "αθήνα", "atina", "atin", "athén", "atény", "ateena")),
    _A("WAW", "Warsaw", "PL", True, 52.1657, 20.9671, ("warszawa", "варшава", "warschau", "varsovia", "varsovie", "varsavia", "varșovia", "varsó", "varšava", "varşova", "βαρσοβία", "varsova")),
    _A("KRK", "Krakow", "PL", True, 50.0777, 19.7848, ("kraków", "краків", "krakau")),
    _A("GDN", "Gdansk", "PL", True, 54.3776, 18.4662, ("gdańsk", "гданськ")),
    _A("WRO", "Wroclaw", "PL", True, 51.1027, 16.8858, ("wrocław", "вроцлав")),
    _A("PRG", "Prague", "CZ", True, 50.1008, 14.2600, ("praha", "prah", "prag", "прага", "praga", "prague")),
    _A("BUD", "Budapest", "HU", True, 47.4369, 19.2556, ("будапешт",)),
    _A("OTP", "Bucharest", "RO", True, 44.5711, 26.0850, ("bucurești", "бухарест")),
    _A("SOF", "Sofia", "BG", True, 42.6967, 23.4114, ("софія",)),
    _A("VNO", "Vilnius", "LT", True, 54.6341, 25.2858, ("вільнюс", "wilno")),
    _A("KUN", "Kaunas", "LT", True, 54.9639, 24.0848, ("каунас",)),
    _A("RIX", "Riga", "LV", True, 56.9236, 23.9711, ("rīga", "рига")),
    _A("TLL", "Tallinn", "EE", True, 59.4133, 24.8328, ("таллінн",)),
    _A("HEL", "Helsinki", "FI", True, 60.3172, 24.9633, ("гельсінкі", "helsing", "хельсинки")),
    _A("ARN", "Stockholm", "SE", True, 59.6519, 17.9186, ("стокгольм", "sztokholm")),
    _A("CPH", "Copenhagen", "DK", True, 55.6180, 12.6560, ("københavn", "kopenhagen", "копенгаген", "kopenhaga")),
    _A("OSL", "Oslo", "NO", True, 60.1939, 11.1004, ("осло",)),
    _A("KEF", "Reykjavik", "IS", True, 63.9850, -22.6056, ("reykjavík", "рейк'явік")),
    _A("DUB", "Dublin", "IE", True, 53.4213, -6.2701, ("дублін",)),
    _A("LHR", "London", "GB", False, 51.4700, -0.4543, ("londyn", "лондон", "londres", "heathrow", "londra", "λονδίνο", "londýn", "lontoo")),
    _A("STN", "London Stansted", "GB", False, 51.8860, 0.2389, ("stansted",)),
    _A("IST", "Istanbul", "TR", False, 41.2753, 28.7519, ("стамбул", "stambuł", "estambul", "istanbul", "κωνσταντινούπολη")),
    _A("AYT", "Antalya", "TR", False, 36.8987, 30.8005, ("анталія",)),
    _A("DXB", "Dubai", "AE", False, 25.2532, 55.3657, ("дубай", "dubaj")),
    _A("DOH", "Doha", "QA", False, 25.2731, 51.6081, ("доха",)),
    _A("TLV", "Tel Aviv", "IL", False, 32.0055, 34.8854, ("тель-авів",)),
    _A("CAI", "Cairo", "EG", False, 30.1219, 31.4056, ("каїр", "kair")),
    _A("HRG", "Hurghada", "EG", False, 27.1783, 33.7994, ("хургада",)),
    _A("JFK", "New York", "US", False, 40.6413, -73.7781, ("нью-йорк", "nowy jork", "nueva york")),
    _A("ORD", "Chicago", "US", False, 41.9742, -87.9073, ("чикаго",)),
    _A("YYZ", "Toronto", "CA", False, 43.6777, -79.6248, ("торонто",)),
    # More European airports common in compensation claims.
    _A("KBP", "Kyiv", "UA", False, 50.3450, 30.8947, ("київ", "киев", "kijów", "kiew", "kiev", "kijev", "kyjev", "kiova", "κίεβο")),
    _A("LWO", "Lviv", "UA", False, 49.8125, 23.9561, ("львів", "львов", "lwów", "lemberg", "leopoli")),
    _A("ODS", "Odesa", "UA", False, 46.4268, 30.6765, ("одеса", "одесса", "odessa")),
    _A("CGN", "Cologne", "DE", True, 50.8659, 7.1427, ("köln", "кельн", "kolonia", "colonia", "keulen", "kolín")),
    _A("STR", "Stuttgart", "DE", True, 48.6899, 9.2220, ("штутгарт",)),
    _A("NUE", "Nuremberg", "DE", True, 49.4987, 11.0669, ("nürnberg", "нюрнберг", "norymberga", "norimberga", "nuremberga")),
    _A("HAJ", "Hanover", "DE", True, 52.4611, 9.6851, ("hannover", "ганновер", "hanower")),
    _A("KTW", "Katowice", "PL", True, 50.4743, 19.0800, ("катовіце", "катовице", "kattowitz")),
    _A("POZ", "Poznan", "PL", True, 52.4210, 16.8263, ("poznań", "познань", "posen")),
    _A("BLQ", "Bologna", "IT", True, 44.5354, 11.2887, ("болонья", "bolonia", "bologne", "bolonha")),
    _A("NAP", "Naples", "IT", True, 40.8860, 14.2908, ("napoli", "неаполь", "nápoles", "neapol", "neapel", "napels", "νάπολη")),
    _A("CTA", "Catania", "IT", True, 37.4668, 15.0664, ("катанія", "катания")),
    _A("PMO", "Palermo", "IT", True, 38.1760, 13.0910, ("палермо",)),
    _A("BRI", "Bari", "IT", True, 41.1389, 16.7606, ("барі", "бари")),
    _A("SVQ", "Seville", "ES", True, 37.4180, -5.8931, ("sevilla", "севілья", "севилья", "sewilla", "séville", "siviglia", "sevilha")),
    _A("VLC", "Valencia", "ES", True, 39.4893, -0.4816, ("валенсія", "валенсия", "walencja", "valence", "valência")),
    _A("ALC", "Alicante", "ES", True, 38.2822, -0.5582, ("аліканте", "аликанте")),
    _A("IBZ", "Ibiza", "ES", True, 38.8729, 1.3731, ("ібіца", "ибица", "eivissa")),
    _A("TFS", "Tenerife", "ES", True, 28.0445, -16.5725, ("тенеріфе", "тенерифе", "teneryfa", "teneriffa")),
    _A("LPA", "Gran Canaria", "ES", True, 27.9319, -15.3866, ("гран-канарія", "гран-канария", "las palmas")),
    _A("MRS", "Marseille", "FR", True, 43.4393, 5.2214, ("марсель", "marsylia", "marsella", "marsiglia", "marselha", "marseilles")),
    _A("LYS", "Lyon", "FR", True, 45.7256, 5.0811, ("ліон", "лион", "lione", "lyons")),
    _A("TLS", "Toulouse", "FR", True, 43.6291, 1.3638, ("тулуза", "tuluza", "tolosa")),
    _A("BOD", "Bordeaux", "FR", True, 44.8283, -0.7156, ("бордо", "burdeos")),
    _A("NTE", "Nantes", "FR", True, 47.1532, -1.6107, ("нант",)),
    _A("CRL", "Charleroi", "BE", True, 50.4592, 4.4538, ("шарлеруа",)),
    _A("EIN", "Eindhoven", "NL", True, 51.4500, 5.3745, ("ейндховен", "эйндховен")),
    _A("BSL", "Basel", "CH", True, 47.5896, 7.5299, ("базель", "bâle", "bazylea", "basilea", "bâle-mulhouse")),
    _A("CLJ", "Cluj-Napoca", "RO", True, 46.7852, 23.6862, ("cluj", "клуж")),
    _A("IAS", "Iasi", "RO", True, 47.1785, 27.6206, ("iași",)),
    _A("VAR", "Varna", "BG", True, 43.2321, 27.8251, ("варна", "warna")),
    _A("BEG", "Belgrade", "RS", False, 44.8184, 20.3091, ("beograd", "белград", "belgrad", "belgrado", "belgrád", "bělehrad", "βελιγράδι")),
    _A("ZAG", "Zagreb", "HR", True, 45.7429, 16.0688, ("загреб", "ζάγκρεμπ")),
    _A("DBV", "Dubrovnik", "HR", True, 42.5614, 18.2682, ("дубровник",)),
    _A("LJU", "Ljubljana", "SI", True, 46.2237, 14.4576, ("любляна", "lublana", "lubiana")),
    _A("SKG", "Thessaloniki", "GR", True, 40.5197, 22.9709, ("θεσσαλονίκη", "салоніки", "салоники", "saloniki", "thessalonique", "tesalónica", "selanik", "szaloniki", "soluň")),
    _A("HER", "Heraklion", "GR", True, 35.3397, 25.1803, ("ηράκλειο", "іракліон", "ираклион", "iraklio", "heraklion")),
    _A("RHO", "Rhodes", "GR", True, 36.4054, 28.0862, ("ρόδος", "родос", "rodos", "rhodos")),
    _A("CFU", "Corfu", "GR", True, 39.6019, 19.9117, ("κέρκυρα", "корфу", "korfu", "corfou")),
    _A("SAW", "Sabiha Gokcen", "TR", False, 40.8986, 29.3092, ("sabiha", "sabiha gökçen")),
    _A("ADB", "Izmir", "TR", False, 38.2924, 27.1570, ("i̇zmir", "ізмір", "измир", "smyrna", "esmirna")),
    _A("LTN", "Luton", "GB", False, 51.8747, -0.3683, ("лутон",)),
    _A("LGW", "Gatwick", "GB", False, 51.1537, -0.1821, ("гатвік", "гатвик")),
    _A("MAN", "Manchester", "GB", False, 53.3537, -2.2750, ("манчестер",)),
    _A("EDI", "Edinburgh", "GB", False, 55.9500, -3.3725, ("единбург", "эдинбург", "edynburg", "edimburgo", "édimbourg", "edimbourg")),
    _A("BHX", "Birmingham", "GB", False, 52.4539, -1.7480, ("бірмінгем", "бирмингем")),
    _A("LCA", "Larnaca", "CY", True, 34.8751, 33.6249, ("λάρνακα", "ларнака", "larnaka")),
    _A("MLA", "Malta", "MT", True, 35.8575, 14.4775, ("мальта", "valletta")),
    _A("FAO", "Faro", "PT", True, 37.0144, -7.9659, ("фару", "фаро")),
    _A("FNC", "Madeira", "PT", True, 32.6979, -16.7745, ("funchal", "мадейра")),
    _A("PDL", "Ponta Delgada", "PT", True, 37.7412, -25.6979, ("azores", "açores", "азори", "азоры")),
    _A("BTS", "Bratislava", "SK", True, 48.1702, 17.2127, ("братислава", "bratysława", "pozsony", "pressburg")),
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


def fold(text: str) -> str:
    """Lowercase and drop accents from Latin letters ("Ámsterdam" -> "amsterdam", "Köln" -> "koln").

    Cyrillic and Greek letters keep their marks: in Ukrainian "й" and "ї" are letters of their own.
    """
    out: list[str] = []
    for ch in unicodedata.normalize("NFD", text.lower()):
        if unicodedata.combining(ch) and out and "a" <= out[-1] <= "z":
            continue
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out)).translate(_LATIN_EXTRA)


_LATIN_EXTRA = str.maketrans({"ł": "l", "ø": "o", "ß": "ss", "æ": "ae", "đ": "d", "ı": "i"})
# English words that are also IATA codes or city names; they count only when written as a name.
_AMBIGUOUS_IATA = {"MAN", "SAW", "HER", "VAR", "BOD", "BER", "LIS", "NAP", "BRI", "EDI"}
_CASE_SENSITIVE_CITIES = {"nice", "malta", "faro", "bari"}


def airports_in_text(text: str) -> list[Airport]:
    """Airports mentioned in text, in order of appearance (IATA codes or city names)."""
    return [a for _, a in _airport_hits(text)]


# A connecting airport: "via Frankfurt", "через Франкфурт", "przez Frankfurt", "connection in Frankfurt".
_VIA = (r"(?:via|through|over|stopover in|lay-?over in|connection in|connecting in|change in|через|пересадк\w* в"
        r"|przez|przesiadk\w* w|über|uber|umstieg in|escala en|vía|par|avec escale à|correspondance à|scalo a"
        r"|tramite|prin|escala em|över|μέσω|přes|preko|kautta)")


def route_in_text(text: str) -> tuple[Airport | None, Airport | None, list[Airport]]:
    """Origin, final destination and connecting airports.

    EU261 distance runs from the first departure to the final destination, so a
    connection named in the middle ("Warsaw via Frankfurt to Lisbon") is skipped.
    Without a via-word the first and last airports named are taken.
    """
    hits = _airport_hits(text)
    low = fold(text)
    via, main = [], []
    for pos, a in hits:
        before = low[max(0, pos - 25):pos]
        (via if re.search(_VIA + r"\W{1,3}$", before) else main).append(a)
    if len(main) < 2:
        main = [a for _, a in hits]
        via = []
    if not main:
        return None, None, []
    if len(main) == 1:
        return main[0], None, via
    return main[0], main[-1], via + main[1:-1]


@dataclass(frozen=True)
class _Matcher:
    airport: Airport
    folded: re.Pattern[str] | None  # stems on the folded text
    cased: re.Pattern[str] | None  # names that only count when capitalised ("Nice", "Faro")
    iata: re.Pattern[str]


@lru_cache(maxsize=1)
def _matchers() -> tuple[_Matcher, ...]:
    """One compiled pattern per airport, built once. Compiling ~500 patterns per message used to
    overflow the re module's cache and took most of the time of a reply."""
    out = []
    for a in AIRPORTS.values():
        names = sorted({fold(n) for n in (a.city, *a.aliases)})
        # Ukrainian/Polish nouns inflect ("з Лісабона", "z Warszawy"); match the stem of longer names.
        stems = [re.escape(n[:-1]) if len(n) > 5 else re.escape(n) for n in names if n not in _CASE_SENSITIVE_CITIES]
        cased = [re.escape(n.capitalize()) for n in names if n in _CASE_SENSITIVE_CITIES]
        out.append(_Matcher(
            a,
            re.compile(r"(?<!\w)(?:" + "|".join(stems) + ")") if stems else None,
            re.compile(r"(?<!\w)(?:" + "|".join(cased) + r")(?!\w)") if cased else None,
            re.compile(r"\b" + a.iata + r"\b"),
        ))
    return tuple(out)


def _airport_hits(text: str) -> list[tuple[int, Airport]]:
    hits: list[tuple[int, Airport]] = []
    low = fold(text)
    upper = text.isupper()
    for mt in _matchers():
        starts = [m.start() for m in (
            mt.folded.search(low) if mt.folded else None,
            mt.cased.search(text) if mt.cased else None,
            None if upper and mt.airport.iata in _AMBIGUOUS_IATA else mt.iata.search(text),
        ) if m]
        if starts:
            hits.append((min(starts), mt.airport))
    hits.sort(key=lambda h: h[0])
    return hits


_AIRLINE_PATTERNS = [(re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)"), code)
                     for name, code in sorted(AIRLINE_NAMES.items(), key=lambda kv: -len(kv[0]))]


def airline_in_text(text: str) -> str | None:
    low = text.lower()
    for pattern, code in _AIRLINE_PATTERNS:
        if pattern.search(low):
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
