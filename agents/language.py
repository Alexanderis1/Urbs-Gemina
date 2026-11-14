"""Italian first (Alessandro, 14 Nov 2026): answer in Italian unless the officer writes in English.

The client sends a language, but the text the officer typed or spoke wins when it is clearly one language.
A short text with no signal (a place name, "municipio:5") keeps the client's choice, Italian by default.
"""
from __future__ import annotations

import re

from agents.contract import Language, TwinQuestion

_WORD = re.compile(r"[a-zàèéìòù']+")
_EN = frozenset("the a an is are was what which where when how many much of in on for to and with this that "
                "there do does can could should would please show me tell give near my our".split())
_IT = frozenset("il lo la i gli le un una è sono che chi cosa dove quando come quanti quante quanto di del della "
                "dei delle nel nella nei sul sulla per con questo questa c'è ci mi dammi mostra vicino mio "
                "nostro stamattina oggi domani".split())
_ELISION = re.compile(r"\b(?:l|d|dell|dall|all|nell|sull|com|un|c|quest|qual)['’](?=[a-zàèéìòù])")
MIN_HITS = 2


def detect_language(text: str) -> Language | None:
    """'en' or 'it' when the text clearly reads as one of them, else None."""
    words = [w.strip("'") for w in _WORD.findall(text.lower())]
    en = sum(w in _EN for w in words)
    it = sum(w in _IT for w in words) + len(_ELISION.findall(text.lower()))  # dell'aria, com'è, l'ospedale
    if en >= MIN_HITS and en > 2 * it:
        return "en"
    if it >= MIN_HITS and it > en:
        return "it"
    return None


def answer_language(question: TwinQuestion) -> Language:
    return detect_language(question.question) or question.language or "it"
