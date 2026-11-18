"""The cause of a disruption as the customer names it in chat, in the 20 languages.

The chat check stays preliminary: a cause never changes the verdict. It adds one
sentence that sets expectations, since whether a cause excuses the airline
("extraordinary circumstances") depends on the cause:

- technical problem, strike by the airline's own staff: usually not extraordinary
  (CJEU C-549/07 Wallentin-Hermann; C-28/20 Airhelp v SAS), the claim stands
- weather: extraordinary only if it really affected this flight, checked later
- strike by air traffic control or airport staff: usually extraordinary
- a strike without saying whose: depends on whose staff it was
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

_RE = {k: re.compile(v) for k, v in
       {"strike": _STRIKE, "atc": _ATC, "staff": _STAFF, "tech": _TECH, "weather": _WEATHER}.items()}

CAUSES = ("strike_atc", "strike_staff", "strike", "technical", "weather")


def cause_in_text(text: str) -> str | None:
    """One of CAUSES, or None. Strikes first, since "pilot strike" also has no weather word."""
    low = text.lower()
    if _RE["strike"].search(low):
        if _RE["atc"].search(low):
            return "strike_atc"
        if _RE["staff"].search(low):
            return "strike_staff"
        return "strike"
    if _RE["tech"].search(low):
        return "technical"
    if _RE["weather"].search(low):
        return "weather"
    return None
