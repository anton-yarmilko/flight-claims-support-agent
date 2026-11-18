"""Decide whether the AI agent may answer a message or must hand it to a human.

The rules are deliberately explicit and conservative: anything legal, financial
or emotionally charged goes to a person. The AI layer drafts; this layer decides.

Keywords cover English, Ukrainian, Polish, German and Spanish. When no rule
matches, an optional LLM classifier may name the intent, but it can only pick
from the fixed list below, it never overrides a rule match, and its own
confidence goes through the same 0.70 threshold.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm import LLM


class Action(str, Enum):
    AI_ANSWER = "ai_answer"
    HUMAN_HANDOFF = "human_handoff"


@dataclass(frozen=True)
class Decision:
    intent: str
    action: Action
    reasons: list[str] = field(default_factory=list)
    priority: str = "normal"
    source: str = "rules"  # "rules" or "llm"


# Keywords per intent and language. Non-English stems are left open at the end so
# inflected forms still match. Intents are checked in this order; the first match
# names the message.
KEYWORDS: dict[str, dict[str, str]] = {
    "gdpr_request": {
        "en": r"\b(gdpr|delete my (data|account)|erase my data|personal data)\b",
        "uk": r"видаліть мої дані|персональн\w* дан", "ru": r"удалите мои данные",
        "pl": r"rodo\b|usu[ńn] moje dane|dane osobow",
        "de": r"dsgvo|daten l[öo]sch|meine daten", "es": r"rgpd|borr(ar|en) mis datos|datos personales",
        "fr": r"supprim\w* mes donn[ée]es|donn[ée]es personnelles", "it": r"cancell\w* i miei dati|dati personali",
        "pt": r"apag\w* os meus dados|dados pessoais", "ro": r"[șs]terge\w* datele|date personale|date cu caracter personal",
        "nl": r"\bavg\b|verwijder mijn gegevens|persoonsgegevens", "el": r"διαγρ\w* τα δεδομένα|προσωπικά δεδομένα",
        "tr": r"kvkk|verilerimi sil|ki[şs]isel veri", "hu": r"t[öo]r[öo]lj\w* az adataimat|szem[ée]lyes adat",
        "cs": r"sma[žz]te moje [úu]daje|osobn[íi] [úu]daje", "sr": r"obri[šs]ite moje podatke|li[čc]n\w* podat",
        "da": r"slet mine data|personoplysninger", "no": r"slett mine data|personopplysninger",
        "sv": r"radera mina uppgifter|personuppgifter", "fi": r"poista tietoni|henkil[öo]tied",
    },
    "legal_threat": {
        "en": r"\b(lawyer|attorney|sue|court|legal action|ombudsman|regulator)\b",
        "uk": r"юрист|адвокат|(?<!\w)суд|позов|омбудсмен", "ru": r"(?<!\w)иск(?!\w)|подам в суд",
        "pl": r"prawnik|adwokat|(?<!\w)s[ąa]d(?!\w)|pozew|rzecznik praw",
        "de": r"anwalt|gericht|klage|schlichtungsstelle", "es": r"abogad|demanda|tribunal",
        "fr": r"avocat|tribunal|en justice|m[ée]diateur", "it": r"avvocat|tribunale|causa legale|denunc",
        "pt": r"advogad|tribunal|processo judicial|provedor", "ro": r"avocat|instan[țt]|tribunal|[îi]n judecat",
        "nl": r"advocaat|rechter|rechtbank|rechtszaak|juridische stappen", "el": r"δικηγόρ|δικαστήρι|μήνυση",
        "tr": r"avukat|mahkeme|dava a[çc]", "hu": r"[üu]gyv[ée]d|b[íi]r[óo]s[áa]g|beperel",
        "cs": r"advok[áa]t|pr[áa]vn[íi]k|(?<!\w)soud|[žz]alob", "sr": r"advokat|(?<!\w)sud(?!\w)|tu[žz]b|tu[žz]i[ćc]u",
        "da": r"advokat|retten|sags[øo]ge|domstol", "no": r"advokat|retten|saks[øo]ke|domstol",
        "sv": r"advokat|jurist|domstol|st[äa]mma|tingsr[äa]tt", "fi": r"asianajaja|lakimies|oikeuteen|haaste",
    },
    "payment_issue": {
        "en": r"\b(not received|haven'?t received|where is my (money|payment)|wrong amount|bank details|iban|refund me)\b",
        "uk": r"не отрима|гроші не|де мої гроші|реквізит|рахун\w* для виплат",
        "ru": r"не получил|где мои деньги|деньги не",
        "pl": r"nie otrzyma|gdzie (s[ąa] )?moje pieni|numer konta|z[łl]a kwota",
        "de": r"nicht erhalten|wo ist mein geld|bankverbindung|kontodaten|falscher betrag",
        "es": r"no he recibido|d[óo]nde est[áa] mi dinero|cuenta bancaria|importe incorrecto",
        "fr": r"pas re[çc]u|o[ùu] est mon argent|coordonn[ée]es bancaires|mauvais montant",
        "it": r"non ho ricevuto|dove sono i miei soldi|coordinate bancarie|importo sbagliato",
        "pt": r"n[ãa]o recebi|onde est[áa] o meu dinheiro|dados banc[áa]rios|valor errado",
        "ro": r"nu am primit|unde sunt banii|cont bancar|suma gre[șs]it",
        "nl": r"niet ontvangen|waar is mijn geld|bankgegevens|verkeerd bedrag",
        "el": r"δεν έλαβα|δεν πήρα|πού είναι τα χρήματα|τραπεζικ",
        "tr": r"almad[ıi]m|param nerede|banka bilgi|yanl[ıi][şs] tutar|[öo]deme gelmedi",
        "hu": r"nem kaptam meg|hol van a p[ée]nzem|banksz[áa]mla|rossz [öo]sszeg",
        "cs": r"nedostal|kde jsou moje pen[íi]ze|bankovn[íi] [úu][čc]et|[šs]patn[áa] [čc][áa]stka",
        "sr": r"nisam dobi|gde je moj novac|bankovni ra[čc]un|pogre[šs]an iznos",
        "da": r"ikke modtaget|hvor er mine penge|bankoplysninger|forkert bel[øo]b",
        "no": r"ikke mottatt|hvor er pengene|bankopplysninger|feil bel[øo]p",
        "sv": r"inte f[åa]tt|var [äa]r mina pengar|bankuppgifter|fel belopp",
        "fi": r"en ole saanut|miss[äa] rahani|tilitied|v[äa][äa]r[äa] summa",
    },
    "fee_question": {
        "en": r"\b(fee|commission|charge|how much do you (take|keep)|percent)\b|%",
        "uk": r"комісі|скільки ви (берете|забираєте)|відсот", "ru": r"комисси|сколько вы берете|процент",
        "pl": r"prowizj|op[łl]at|ile (bierzecie|pobieracie)|procent",
        "de": r"geb[üu]hr|provision|wie viel (nehmen|behalten) sie|prozent",
        "es": r"comisi[óo]n|tarifa|cu[áa]nto (cobr|se qued)|porcentaje",
        "fr": r"frais|commission|combien (prenez|gardez)|pourcentage", "it": r"commission|tariff|quanto prendete|percentuale",
        "pt": r"comiss|(?<!\w)taxa|quanto cobram|percentagem", "ro": r"comision|tax[ăa]|c[âa]t lua[țt]i|procent",
        "nl": r"kosten|commissie|hoeveel (rekenen|houden)|percentage", "el": r"προμήθει|χρέωση|πόσο κρατάτε|ποσοστό",
        "tr": r"komisyon|[üu]cret|ne kadar al[ıi]yorsunuz|y[üu]zde", "hu": r"(?<!\w)d[íi]j|jutal[ée]k|mennyit (k[ée]r|vesz|tart)|sz[áa]zal[ée]k",
        "cs": r"poplat|provize|kolik si (berete|[úu][čc]tujete)|procent", "sr": r"provizij|naknad|koliko uzimate|procen",
        "da": r"gebyr|provision|hvor meget tager", "no": r"gebyr|provisjon|hvor mye tar|prosent",
        "sv": r"avgift|provision|hur mycket tar", "fi": r"palkkio|(?<!\w)maksu|kuinka paljon otatte|prosent",
    },
    "claim_status": {
        "en": r"\b(status|update on my claim|any news|claim number|case number|how long)\b",
        "uk": r"статус|які новини|номер (заявки|справи)|скільки чекати", "ru": r"какие новости|номер (заявки|дела)|сколько ждать",
        "pl": r"status|jakie[śs]? wie[śs]ci|numer (sprawy|wniosku)|jak d[łl]ugo",
        "de": r"stand meine|neuigkeiten|fallnummer|wie lange",
        "es": r"estado de mi|alguna novedad|n[úu]mero de (caso|reclamaci)|cu[áa]nto tiempo",
        "fr": r"statut|[ée]tat de mon|des nouvelles|num[ée]ro de dossier|combien de temps",
        "it": r"stato della|novit[àa]|numero di pratica|quanto tempo", "pt": r"estado do|novidades|n[úu]mero do processo|quanto tempo",
        "ro": r"stadiul|nout[ăa][țt]i|num[ăa]r\w* de dosar|c[âa]t dureaz", "nl": r"stand van zaken|nieuws over|dossiernummer|hoe lang",
        "el": r"κατάσταση|νέα για|αριθμός υπόθεσης|πόσο καιρό", "tr": r"durum|haber var m|dosya numara|ne kadar s[üu]rer",
        "hu": r"[áa]llapot|h[íi]r(e|ek)|[üu]gysz[áa]m|mennyi ideig", "cs": r"stav (m[ée]|m[ée]ho)|novinky|[čc][íi]slo p[řr][íi]padu|jak dlouho",
        "sr": r"ima li vesti|broj predmeta|koliko dugo", "da": r"nyt om|sagsnummer|hvor l[æa]nge",
        "no": r"nytt om|saksnummer|hvor lenge", "sv": r"nytt om|[äa]rendenummer|hur l[äa]nge",
        "fi": r"(?<!\w)tila(?!\w)|uutisia|tapausnumero|kuinka kauan",
    },
    "documents": {
        "en": r"\b(boarding pass|e-?ticket|document|upload|power of attorney|passport)\b",
        "uk": r"посадков|квиток|документ|завантаж|довіреніст|паспорт",
        "ru": r"посадочн|билет|загруз|доверенност",
        "pl": r"karta pok[łl]adowa|bilet|dokument|pe[łl]nomocnictw|paszport|prze[śs]l",
        "de": r"bordkarte|ticket|dokument|hochladen|vollmacht|reisepass",
        "es": r"tarjeta de embarque|billete|documento|subir|poder notarial|pasaporte",
        "fr": r"carte d.embarquement|billet|document|t[ée]l[ée]charg|procuration|passeport",
        "it": r"carta d.imbarco|biglietto|document|caric|delega|passaporto",
        "pt": r"cart[ãa]o de embarque|bilhete|document|carregar|procura[çc][ãa]o|passaporte",
        "ro": r"card de [îi]mbarcare|bilet|document|[îi]ncarc|[îi]mputernicire|pa[șs]aport",
        "nl": r"instapkaart|ticket|document|uploaden|machtiging|paspoort",
        "el": r"κάρτα επιβίβασης|εισιτήρι|έγγραφ|ανέβασ|εξουσιοδότηση|διαβατήρι",
        "tr": r"bini[şs] kart|bilet|belge|y[üu]kle|vekaletname|pasaport",
        "hu": r"besz[áa]ll[óo]k[áa]rty|(?<!\w)jegy|dokumentum|felt[öo]lt|meghatalmaz[áa]s|[úu]tlev[ée]l",
        "cs": r"palubn[íi] vstupenk|letenk|dokument|nahr[áa]t|pln[áa] moc|(?<!\w)pas(?!\w)",
        "sr": r"ukrcn|avionsk\w* kart|dokument|otprem|ovla[šs][ćc]enj|paso[šs]",
        "da": r"boardingkort|billet|dokument|upload|fuldmagt", "no": r"boardingkort|billett|dokument|last opp|fullmakt",
        "sv": r"boardingkort|biljett|dokument|ladda upp|fullmakt", "fi": r"tarkastuskort|(?<!\w)lippu|asiakirj|lataa|valtakirj|passi",
    },
    "eligibility": {
        "en": r"\b(eligible|entitled|compensation|delayed|delay|cancel+ed|cancellation|overbooked|denied boarding)\b",
        "uk": r"затрим|скасува|компенсац|відмовили в посадці|овербукінг|маю право",
        "ru": r"задерж|отмен|овербукинг|отказали в посадке|имею право",
        "pl": r"op[óo][źz]ni|odwo[łl]a|odszkodow|odm[óo]wiono wej[śs]cia|nadrezerwac",
        "de": r"versp[äa]t|annull|gestrichen|entsch[äa]digung|[üu]berbuch|nicht mitgenommen",
        "es": r"retras|cancela|indemnizaci|compensaci|overbooking|denegaron el embarque",
        "fr": r"retard|annul|indemnis|surr[ée]servation|refus d.embarquement|ai-je droit",
        "it": r"ritard|cancellat|risarciment|negato l.imbarco|ho diritto",
        "pt": r"atras|cancelad|indemniza|compensa[çc][ãa]o|recusa de embarque|tenho direito",
        "ro": r"[îi]nt[âa]rzi|anulat|compensa[țt]i|desp[ăa]gubir|refuz la [îi]mbarcare|am dreptul",
        "nl": r"vertraag|vertraging|geannuleerd|annulering|compensatie|vergoeding|overboek|instapweigering|recht op",
        "el": r"καθυστέρ|ακυρώθ|ακύρωση|αποζημίωσ|υπερκράτηση|άρνηση επιβίβασης|δικαιούμαι",
        "tr": r"r[öo]tar|gecik|iptal|tazminat|u[çc]a[ğg]a al[ıi]nmad|hakk[ıi]m var",
        "hu": r"k[ée]sett|k[ée]s[ée]s|t[öo]r[öo]lt|k[áa]rt[ée]r[íi]t[ée]s|k[áa]rtalan[íi]t|t[úu]lfoglal|jogosult",
        "cs": r"zpo[žz]d|zru[šs]en|od[šs]kodn|kompenzac|nepustili|m[áa]m n[áa]rok",
        "sr": r"kasn|otkaz|od[šs]tet|kompenzacij|overbuking|nisu me pustili|imam pravo",
        "da": r"forsink|aflys|kompensation|erstatning|overbook|n[æa]gtet boarding|har jeg ret",
        "no": r"forsink|kansell|innstilt|kompensasjon|erstatning|overbook|nektet ombordstigning|har jeg rett",
        "sv": r"f[öo]rsen|inst[äa]ll|ers[äa]ttning|kompensation|[öo]verbok|nekad ombordstigning|har jag r[äa]tt",
        "fi": r"my[öo]h[äa]s|viiv[äa]s|(?<!\w)peru|korvau|ylivaraus|ei p[äa][äa]ssyt koneeseen|onko minulla oikeus",
    },
}

INTENTS: list[tuple[str, str]] = [(name, "|".join(by_lang.values())) for name, by_lang in KEYWORDS.items()]

INTENT_NAMES = [name for name, _ in INTENTS] + ["other"]

ESCALATE_INTENTS = {
    "gdpr_request": "Data-protection request must be logged and handled by a person.",
    "legal_threat": "Mentions legal action or a regulator.",
    "payment_issue": "Money or bank details involved.",
}

ANGER = re.compile(
    r"\b(scam|fraud|thie(f|ves)|disgusting|unacceptable|worst|ridiculous|furious|angry)\b|!!!"
    r"|шахра|обман|злоді|ганьба|жахлив|мошенни|воры|позор|безобрази"
    r"|oszu|z[łl]odzie|skandal|ha[ńn]ba|okropn"
    r"|betrug|betr[üu]ger|abzocke|frechheit|unversch[äa]mt"
    r"|estafa|fraude|ladrones|verg[üu]enza|indignante"
    r"|arnaque|escroc|voleurs|scandaleu|honteu"
    r"|truffa|truffatori|ladri|vergogna|schifo"
    r"|burla|ladr[õo]es|vergonha"
    r"|[țt]eap[ăa]|ho[țt]i|ru[șs]ine|bat[ăa]ie de joc"
    r"|oplicht|schandalig|dieven"
    r"|απάτ|απατεών|κλέφτ|ντροπή"
    r"|doland[ıi]r|rezalet|h[ıi]rs[ıi]z"
    r"|csal[óo]|[áa]tver[ée]s|tolvaj|botr[áa]ny"
    r"|podvod|zlod[ěe]j|ostuda"
    r"|prevar|lopov|sramot"
    r"|svindl?|bedr[äa]geri|bedragare|tjuvar|tyve|skandal[øo]s"
    r"|huijau|huijari|varkaat|skandaali",
    re.I,
)


def classify(message: str) -> str:
    text = message.lower()
    for name, pattern in INTENTS:
        if re.search(pattern, text, re.I):
            return name
    return "other"


LLM_CLASSIFIER_PROMPT = """You classify customer messages for a flight-compensation claims service.
Pick exactly one intent:
- eligibility: asks whether a delay, cancellation or denied boarding gives compensation
- claim_status: asks about the progress of an existing claim
- fee_question: asks about the service fee or commission
- documents: asks which documents are needed or how to send them
- payment_issue: payout not received, wrong amount, bank details
- legal_threat: mentions lawyers, courts, regulators
- gdpr_request: asks to see or delete personal data
- other: anything else
The message can be in any language. Reply with JSON only:
{"intent": "<one of the names above>", "confidence": <0.0-1.0>}"""


def classify_with_llm(message: str, llm: LLM) -> tuple[str, float]:
    data = llm.chat_json(
        [{"role": "system", "content": LLM_CLASSIFIER_PROMPT}, {"role": "user", "content": message}],
        temperature=0.0,
        max_tokens=60,
    )
    intent = str(data.get("intent", "other")).strip().lower()
    if intent not in INTENT_NAMES:
        return "other", 0.0
    try:
        conf = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
    except (TypeError, ValueError):
        conf = 0.0
    return intent, conf


def triage(
    message: str,
    *,
    ai_confidence: float = 1.0,
    previous_handoffs: int = 0,
    llm: LLM | None = None,
) -> Decision:
    intent = classify(message)
    source = "rules"
    reasons: list[str] = []

    if intent == "other" and llm is not None:
        from .llm import LLMError

        try:
            llm_intent, llm_conf = classify_with_llm(message, llm)
        except LLMError:
            llm_intent, llm_conf = "other", 0.0
        if llm_intent != "other":
            intent, source = llm_intent, "llm"
            ai_confidence = min(ai_confidence, llm_conf)

    if intent in ESCALATE_INTENTS:
        reasons.append(ESCALATE_INTENTS[intent])
    if ANGER.search(message):
        reasons.append("Customer is upset; a person should reply.")
    if ai_confidence < 0.7:
        what = "LLM intent confidence" if source == "llm" else "Knowledge-base match"
        reasons.append(f"{what} too weak ({ai_confidence:.2f} < 0.70).")
    if previous_handoffs > 0:
        reasons.append("Customer was already handed to a person; keep the same owner.")
    if intent == "other":
        reasons.append("No known intent; do not guess.")

    if reasons:
        urgent = intent in {"legal_threat", "gdpr_request"} or bool(ANGER.search(message))
        return Decision(intent, Action.HUMAN_HANDOFF, reasons, "high" if urgent else "normal", source)
    return Decision(intent, Action.AI_ANSWER, source=source)
