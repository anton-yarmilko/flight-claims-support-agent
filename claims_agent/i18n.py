"""Translations for the demo UI and the agent's template replies.

The language list follows the switcher on airadvisor.com: 23 entries, which are
20 languages once regional variants (English UK/US, French/Canadian French,
German/Austrian German) share one translation. One JSON file per language lives
in `locales/`; English is the fallback for any missing key.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LOCALES = Path(__file__).parent / "locales"

# Order as on the site's switcher; value = English name (used in LLM prompts).
LANGUAGES: dict[str, str] = {
    "en": "English", "es": "Spanish", "de": "German", "fr": "French", "ro": "Romanian",
    "pt": "Portuguese", "pl": "Polish", "sr": "Serbian", "el": "Greek", "tr": "Turkish",
    "hu": "Hungarian", "da": "Danish", "no": "Norwegian", "fi": "Finnish", "nl": "Dutch",
    "sv": "Swedish", "cs": "Czech", "it": "Italian", "uk": "Ukrainian", "ru": "Russian",
}


@lru_cache(maxsize=None)
def strings(lang: str) -> dict[str, str]:
    path = LOCALES / f"{lang}.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if lang == "en":
        return data
    return {**strings("en"), **data}


def t(lang: str, key: str, **kw: object) -> str:
    text = strings(lang if lang in LANGUAGES else "en").get(key, key)
    return text.format(**kw) if kw else text


def native_names() -> dict[str, str]:
    return {code: strings(code).get("_name", name) for code, name in LANGUAGES.items()}
