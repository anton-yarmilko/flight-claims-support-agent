"""Cheap language detection for the languages the demo supports.

Good enough to pick the reply language and the triage keywords. Unknown
languages fall back to English.
"""

from __future__ import annotations

import re

SUPPORTED = {"en": "English", "uk": "Ukrainian", "pl": "Polish", "de": "German", "es": "Spanish"}

_MARKERS = {
    "uk": r"[іїєґ]|\b(мій|моя|рейс|що|як|чи|будь ласка|дякую)\b",
    "pl": r"[ąęłńśźż]|\b(mój|moja|lot|czy|jest|nie|proszę|dziękuję|się)\b",
    "de": r"[äöüß]|\b(mein|meine|flug|ist|und|nicht|bitte|danke|ich)\b",
    "es": r"[ñ¿¡]|\b(mi|vuelo|es|y|no|por favor|gracias|cuánto|está)\b",
    "en": r"\b(my|flight|is|and|not|please|thanks|the|what|how)\b",
}


def detect_language(text: str) -> str:
    low = text.lower()
    if re.search(r"[а-яіїєґ]", low) and not re.search(r"[іїєґ]", low):
        # Cyrillic without Ukrainian-only letters: still answer in Ukrainian for this demo.
        return "uk"
    scores = {lang: len(re.findall(p, low)) for lang, p in _MARKERS.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "en"
