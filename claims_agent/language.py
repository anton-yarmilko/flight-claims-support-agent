"""Cheap language detection for the 20 languages AirAdvisor serves.

Scores each language by its distinctive letters (weight 2) and common short
words (weight 1). Good enough to pick the reply language and works offline.
Unknown text falls back to English.
"""

from __future__ import annotations

import re

from .i18n import LANGUAGES, strings

SUPPORTED = LANGUAGES

_CHARS = {
    "uk": "[іїєґ]", "ru": "[ыэъё]", "sr": "[đćђћџљњј]", "el": "[α-ωάέήίόύώ]",
    "de": "[ß]|[äöü]", "es": "[ñ¿¡]", "fr": "[àâçèêëîïôœùû]", "pt": "[ãõ]",
    "ro": "[ăîșțşţâ]", "pl": "[ąęłńśźż]", "cs": "[ěřů]", "hu": "[őű]", "tr": "[ğış]",
    "da": "[æø]", "no": "[æø]", "sv": "[åäö]", "fi": "[äö]", "it": "[ìò]|(?<!\\w)è(?!\\w)",
}

_WORDS = {
    "en": "my|flight|the|is|was|and|not|how|what|you|delayed|please|do",
    "uk": "мій|моя|рейс|що|як|чи|будь|дякую|мене|затримали|скільки",
    "ru": "мой|моя|что|как|мне|пожалуйста|спасибо|меня|задержали|сколько|был|это",
    "sr": "moj|moja|let|je|nije|sam|koliko|kasnio|otkazan|hvala|molim",
    "el": "η|το|μου|και|δεν|πτήση|είναι",
    "de": "ich|mein|meine|flug|ist|und|nicht|wurde|bitte|danke|wie",
    "es": "mi|vuelo|el|la|que|por|gracias|cuánto|está|fue|tengo",
    "fr": "mon|ma|vol|est|le|les|je|une|pour|été|ai|combien|mes|votre|vous|nous|des|pas|avec|sur|dans|cette|il|au",
    "it": "il|mio|volo|che|per|sono|stato|grazie|quanto|ho|della|di|un|non|suo|sua|gli|questo|è",
    "pt": "meu|voo|não|foi|com|obrigado|quanto|tenho|os|minha",
    "ro": "meu|zborul|este|nu|și|cu|am|fost|cât|mea|vă",
    "pl": "mój|moja|lot|czy|jest|nie|się|proszę|dziękuję|był",
    "cs": "můj|let|je|není|se|byl|jak|mám|děkuji|prosím",
    "hu": "a|az|és|nem|járat|járatom|késett|vagyok|mennyi|kérem|hogy|jár|nekem|órát|kártérítés|egy|van|ha|vagy|mekkora|díjuk|díjunk|ügyet|ügy",
    "tr": "bir|ve|benim|uçuş|uçuşum|için|mi|ne|kadar|teşekkür",
    "nl": "ik|mijn|vlucht|niet|het|een|van|werd|hoeveel|heb|de|uw|u|wij|dat|op|binnen|niets|heeft|geen|jullie|maar",
    "da": "jeg|min|mit|fly|ikke|og|er|af|blev|hvad|hvor|meget|dig|jer|noget|venligst|inden|tjekker|bliver|være",
    "no": "jeg|min|mitt|fly|ikke|og|er|ble|hva|hvor|mye|flyet|deg|dere|noe|gjerne|innen|sjekker|ikkje|være|fram",
    "sv": "jag|min|mitt|flyg|inte|och|är|blev|hur|mycket|flyget|mina|tack|uppgifter|enligt|mig|vill|du|ditt|som|inom|något",
    "fi": "minun|lento|lentoni|on|ei|ja|oli|kuinka|paljon|myöhässä",
}

_CHAR_RE = {k: re.compile(v) for k, v in _CHARS.items()}
_TOKEN = re.compile(r"[^\W\d_]{2,}")


def _distinctive_words() -> dict[str, str]:
    """Words that occur in exactly one language's translations: a free vocabulary
    of a few hundred words per language, taken from locales/."""
    seen: dict[str, set[str]] = {}
    for lang in LANGUAGES:
        for key, text in strings(lang).items():
            if key.startswith("_") or (lang != "en" and text == strings("en").get(key)):
                continue
            for w in _TOKEN.findall(text.lower()):
                seen.setdefault(w, set()).add(lang)
    return {w: next(iter(langs)) for w, langs in seen.items() if len(langs) == 1}


_VOCAB = _distinctive_words()
_WORD_RE = {k: re.compile(r"(?<!\w)(?:" + v + r")(?!\w)") for k, v in _WORDS.items()}


def detect_language(text: str) -> str:
    low = text.lower()
    scores = {lang: 0 for lang in LANGUAGES}
    for lang, rx in _CHAR_RE.items():
        scores[lang] += 2 * len(rx.findall(low))
    for lang, rx in _WORD_RE.items():
        scores[lang] += len(rx.findall(low))
    for w in _TOKEN.findall(low):
        lang = _VOCAB.get(w)
        if lang:
            scores[lang] += 1
    cyrillic = re.search(r"[а-яёіїєґ]", low)
    if cyrillic:
        # Cyrillic script: only uk, ru (or Serbian Cyrillic) are candidates.
        cands = {k: scores[k] for k in ("uk", "ru", "sr")}
        best = max(cands, key=lambda k: cands[k])
        return best if cands[best] > 0 else "ru"
    if re.search(r"[α-ω]", low):
        return "el"
    scores["uk"] = scores["ru"] = scores["el"] = 0
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "en"
