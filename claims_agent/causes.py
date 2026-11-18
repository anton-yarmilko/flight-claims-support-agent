"""The cause of a disruption as the customer names it in chat, in the 20 languages.

The chat check stays preliminary: a cause never changes the verdict. It adds one
sentence that sets expectations, since whether a cause excuses the airline
("extraordinary circumstances") depends on the cause:

- technical problem, strike by the airline's own staff: usually not extraordinary
  (CJEU C-549/07 Wallentin-Hermann; C-28/20 Airhelp v SAS), the claim stands
- weather: extraordinary only if it really affected this flight, checked later
- strike by air traffic control or airport staff: usually extraordinary
- a strike without saying whose: depends on whose staff it was
- bird strike: extraordinary (CJEU C-315/15 Pešková), unless reasonable measures could have avoided the delay
- shortage of crew or staff: the airline's own responsibility, the claim stands
- medical emergency or disruptive passenger on board: usually extraordinary for that flight (C-74/19 LE v TAP)
"""

from __future__ import annotations

import re

_STRIKE = (r"strike|industrial action|страйк|забастов|strajk|streik|gr[èe]ve|huelga|sciopero|staking|grev[ăa]"
           r"|απεργ|\bgrev\b|sztr[áa]jk|st[áa]vk|strejk|lakko|[šs]trajk")
_ATC = (r"air[- ]traffic|\batc\b|controllers?|диспетчер|kontroler\w* (ruchu|lot)|fluglots|flugsicherung"
        r"|contr[ôo]leurs? a[ée]rien|controlador\w* a[ée]re|controllori di volo|controlador\w* de tr[áa]fego"
        r"|luchtverkeersleid|controlori de trafic|ελεγκτ\w* εναέρι|hava trafik|l[ée]giforgalmi|ř[íi]d[íi]c\w* letov"
        r"|flygledar|flyveleder|flygeleder|lennonjohta|kontrolor\w* leta"
        r"|airport (staff|workers)|security staff|ground handling|персонал\w* аеропорт|персонал\w* аэропорт")
_STAFF = (r"pilot|crew|cabin|own staff|airline staff|екіпаж|пілот|экипаж|пилот|załog|personel linii|besatzung|kabinen"
          r"|personnel navigant|équipage|equipage|tripulaci|equipaggio|tripula[çc]|bemanning|echipaj|πλήρωμα|πιλότ"
          r"|m[üu]rettebat|pilot\w*|szem[ée]lyzet|pos[áa]dk|besättning|besætning|mannskap|miehist[öo]|lent[äa]j|posad")
_TECH = (r"technical|mechanical|engine (problem|failure|issue)|aircraft (problem|issue|fault)|maintenance|техн[іи]ч|поломк"
         r"|несправн|неисправн|techniczn|awari|technisch|defekt|technique|panne|t[ée]cnic|aver[íi]a|tecnic|guasto"
         r"|avaria|tehnic|defec[țt]iune|τεχνικ|βλάβη|teknik|ar[ıi]za|m[űu]szaki|technick|porucha|teknisk"
         r"|tekninen|tekniikka|vika\b|tehni[čc]k")
_WEATHER = (r"weather|storm|snow|\bfog\b|thunder|hurricane|blizzard|icing|погод|шторм|\bгроз(?:а|и|у|ою|ой)\b|снігопад|снегопад|туман|ураган"
            r"|pogod|burz|śnieg|sniez|mgł|wetter|sturm|gewitter|schnee|nebel|m[ée]t[ée]o|temp[êe]te|orage|neige|brouillard"
            r"|tormenta|nieve|niebla|maltempo|tempesta|neve\b|nebbia|tempestade|nevoeiro|slecht weer|sneeuw|onweer"
            r"|furtun|ninsoare|cea[țt][ăa]|vreme rea|καιρ|καταιγ|χιον|ομίχλ|f[ıi]rt[ıi]na|kar ya[ğg]|\bsis\b|hava ko[şs]ul"
            r"|id[őo]j[áa]r[áa]s|vihar|havaz|\bköd\b|po[čc]as[íi]|bouř|sn[íi]h|mlh|v[äa]der|sn[öo]storm|dimma|vejr"
            r"|tåge|\bsnø|tåke|uvær|myrsky|\blumi(?:sate\w*|myrsk\w*)?\b|\blumen\b|\blunta\b|\bsumu|nevreme|oluj|\bsneg|magl")

_BIRD = (r"\bbirds?\b|птах|птиц|\bpta(?:k|ki|ka|kiem)\b|\bvogel|vögel|oiseau|p[áa]jaro|uccell|p[áa]ssaro|\bp[ăa]s[ăa]r"
         r"|πουλ|πτην|ku[şs] [çc]arp|mad[áa]r|\bpt[áa]k|\bpt[áa]c|f[åa]gel|f[åa]glar|\bfugl|\blintu|\bptic|\baves\b|volatil|aviaire")
_SHORTAGE = (r"(?:crew|staff|pilot)s? shortage|shortage of (?:crew|staff|pilots)|lack of (?:crew|staff|pilots)|no (?:crew|pilots?) (?:was )?available"
             r"|нестач\w* (?:екіпаж|персонал|пілот)|брак\w* (?:екіпаж|персонал|пілот)|нехват\w* (?:экипаж|персонал|пилот)"
             r"|brak\w* (?:za[łl]og|personel|pilot)|personalmangel|crewmangel|manque (?:de |d')(?:personnel|pilotes|[ée]quipage)|mangel an (?:crew|personal|piloten)"
             r"|falta de (?:personal|tripula|pilotos|pessoal)|carenza di (?:personale|equipaggio|piloti)|personeelstekort"
             r"|personalbrist|brist på (?:besättning|personal|piloter)|tekort aan (?:bemanning|personeel|piloten)|szem[ée]lyzethi[áa]ny|lipsa de (?:echipaj|personal)|personalemangel|mangel på (?:personale|personell|besætning|mannskap)|lips[ăa] de personal"
             r"|έλλειψη (?:προσωπικού|πληρώματος)|personel eksikli|m[üu]rettebat eksikli|munkaer[őo]hi[áa]ny"
             r"|nedostat\w* (?:person[áa]l|pos[áa]dk|osoblja|posade)|henkil[öo]st[öo]pula|miehist[öo]pula|(?:miehist[öo]n|henkil[öo]st[öo]n)\w* (?:\w+ )?puut")
_PASSENGER = (r"medical emergency|passenger (?:was |fell |got |became )?(?:ill|sick|unwell)|sick passenger|unruly|disruptive passenger"
              r"|медичн\w* (?:допомог|невідклад|надзвичай|ситуац)|невідкладн\w* медичн|экстренн\w* медицин|медицинск\w* ситуац|пасажир\w* (?:стало погано|захвор)|медицинск\w* (?:помощ|экстрен|чрезвычай)"
              r"|пассажир\w* (?:стало плохо|заболел)|nag[łl]\w* wypad\w* medyczn|medizinische[rn]? notfall|urgence m[ée]dicale"
              r"|passager malade|emergencia m[ée]dica|pasajero enfermo|emergenza medica|passeggero (?:malato|si [èe] sentito male)"
              r"|emerg[êe]ncia m[ée]dica|medisch noodgeval|urgen[țt][ăa] medical[ăa]|ιατρικ\w* (?:έκτακτ|περιστατικ)"
              r"|t[ıi]bbi acil|orvosi v[ée]szhelyzet|zdravotn\w* (?:n[áa]hl|pohotov)|medicinsk(?:t)? n[öø]d|medisinsk n[øo]d|h[äa]t[äa]tilan|medicinsk akut"
              r"|l[äa][äa]ketieteellinen h[äa]t[äa]|hitn[ae] medicinsk|agresivn\w* putnik")

_RE = {k: re.compile(v) for k, v in
       {"strike": _STRIKE, "atc": _ATC, "staff": _STAFF, "tech": _TECH, "weather": _WEATHER,
        "bird": _BIRD, "shortage": _SHORTAGE, "passenger": _PASSENGER}.items()}

# Causes that usually count as extraordinary circumstances.
EXCUSING_CAUSES = frozenset({"strike_atc", "bird", "passenger"})

CAUSES = ("bird", "strike_atc", "strike_staff", "strike", "crew_shortage", "technical", "passenger", "weather")


def cause_in_text(text: str) -> str | None:
    """One of CAUSES, or None. A bird strike before strikes; strikes before the rest ("pilot strike")."""
    low = text.lower()
    if _RE["bird"].search(low):
        return "bird"
    if _RE["strike"].search(low):
        if _RE["atc"].search(low):
            return "strike_atc"
        if _RE["staff"].search(low):
            return "strike_staff"
        return "strike"
    if _RE["shortage"].search(low):
        return "crew_shortage"
    if _RE["tech"].search(low):
        return "technical"
    if _RE["passenger"].search(low):
        return "passenger"
    if _RE["weather"].search(low):
        return "weather"
    return None


# EU261 counts the delay at arrival (CJEU C-402/07 Sturgeon; C-452/13 Germanwings).
_DEPARTED = re.compile(
    r"depart|took off|take-?off|вилет|вылет|wylot|wylecia|wystartowa|abflug|abgeflogen|gestartet|d[ée]coll|d[ée]part"
    r"|despeg|salida|sali[óo]|partenza|partit|decoll|partida|partiu|descol|vertrek|vertrokken|plecare|decolat"
    r"|αναχ[ώω]ρ|απογει|kalk[ıi][şs]|kalkt[ıi]|indul|odlet|odlét|avg[åa]ng|lyfte|afgang|lettede|avgang|l[äa]ht[öo]|l[äa]hti"
    r"|poleta|polaz|poleteo")
_ARRIVED = re.compile(
    r"arriv|land|reached|прибу|приземл|прилет|приліт|прилетіл|przylot|przylecia|wyl[ąa]dow|dotar|ankunft|angekommen"
    r"|atterr|lleg|aterriz|arriv|chegad|cheg[aá]|aterr|aankomst|aangekomen|sosi|aterizat|[άα]φιξ|φτάσ|προσγει"
    r"|vard[ıi]k?|var[ıi][şs]|indik|[ée]rkez|p[řr][íi]let|p[řr]ist[áa]l|dorazil|ankomst|kom fram|ankom|saapu|perill[äa]"
    r"|laskeutu|stig|sleteo|slet|dola[zs]")


def departure_only(text: str) -> bool:
    """The customer talks about the departure delay and never about the arrival."""
    low = text.lower()
    return bool(_DEPARTED.search(low)) and not _ARRIVED.search(low)
