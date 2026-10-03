"""UI translation.

Each language is a JSON file in web/locales/ (fr.json, en.json…).
To add a language, copy en.json under a new name, translate the values,
then run `python -m web.i18n` to find anything missing.

Conventions in the files:
  - "_name"       : the language's name in that language (shown in the switcher)
  - "_thousands"  : thousands separator (narrow space in French, comma in English)
  - "key.one" / "key.other" : singular and plural forms, picked from {n}
  - {param}       : value inserted into the sentence
"""
import json
import re
import sys
from pathlib import Path

from sdvsave.errors import SaveError, T

LOCALES_DIR = Path(__file__).parent / "locales"
FALLBACK = "en"

# French uses the singular for 0 and 1 ("0 partie trouvée"), English only for 1
_PLURAL_RULES = {"fr": lambda n: n < 2}

_catalogs = {
    path.stem: json.loads(path.read_text(encoding="utf-8"))
    for path in sorted(LOCALES_DIR.glob("*.json"))
}

#: Keys that were requested but exist in no language (used by tests)
missing = set()


def languages():
    """{code: display name}, in alphabetical order of codes."""
    return {code: cat.get("_name", code) for code, cat in _catalogs.items()}


def best_match(accept_languages):
    """The browser's language if we have it, otherwise the fallback."""
    return accept_languages.best_match(list(_catalogs)) or FALLBACK


def _lookup(lang, key):
    for code in (lang, FALLBACK):
        value = _catalogs.get(code, {}).get(key)
        if value is not None:
            return value
    return None


def translate(lang, key, default=None, **params):
    if "n" in params and _lookup(lang, key + ".one") is not None:
        singular = _PLURAL_RULES.get(lang, lambda n: n == 1)(params["n"])
        key += ".one" if singular else ".other"
    text = _lookup(lang, key)
    if text is None:
        if default is not None:
            return default
        missing.add(key)
        return key
    # A key parameter (a field name) can itself use the other parameters:
    # "Friendship with {npc}" inside "{field} must be between…"
    plain = {k: v for k, v in params.items() if not isinstance(v, T)}
    params = {k: translate(lang, v, **plain) if isinstance(v, T) else v
              for k, v in params.items()}
    text = _elide(lang, text, params)
    try:
        return text.format(**params)
    except (KeyError, IndexError, ValueError):
        return text  # a badly written translation must not crash the page


_VOWEL_START = re.compile(r"[aeiouyhàâäéèêëîïôöûüœ]", re.IGNORECASE)


def _elide(lang, text, params):
    """French elides "de" before a vowel: "Maison de {name}" with Aboobakar → "Maison d'Aboobakar"."""
    if lang != "fr":
        return text
    for name, value in params.items():
        if isinstance(value, str) and not isinstance(value, T) and _VOWEL_START.match(value):
            text = re.sub(r"\b([dD])e \{" + re.escape(name) + r"\}", r"\1'{" + name + "}", text)
    return text


def translate_error(lang, exc):
    if isinstance(exc, SaveError):
        return translate(lang, exc.key, **exc.params)
    return str(exc)


def format_number(lang, n):
    sep = _lookup(lang, "_thousands") or ","
    return f"{int(n):,}".replace(",", sep)


# ------------------------------------------------------------------ checking
def check():
    """Lists keys present in one language and missing from another."""
    all_keys = set().union(*(cat.keys() for cat in _catalogs.values()))
    problems = 0
    for code, cat in _catalogs.items():
        absent = sorted(all_keys - cat.keys())
        for key in absent:
            print(f"[{code}] missing key: {key}")
        problems += len(absent)
    print("Everything is translated." if not problems else f"{problems} key(s) to add.")
    return problems


if __name__ == "__main__":
    sys.exit(1 if check() else 0)