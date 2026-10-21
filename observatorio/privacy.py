"""No natural person is stored or published: the rule, and where it is applied.

The bulletins name a natural person with an honorific («D. Nombre Apellidos», «Dña. …»); companies and
public bodies carry none. Many companies carry no legal form either («Esteyco»), so the test is the
honorific, not a missing «S.L.». A company named after a place such as Don Benito would lose its name:
the rule fails on the side of naming no one.

New data goes through `set_promoter` when the promoter is extracted; data stored before the rule goes
through `scrub` when it is loaded, so the next daily run rewrites it clean.

France has its own honorifics («M.», «Mme», «Monsieur»…) and its own one-person firms: a farm run as an
EARL, GAEC or SCEA, or a business as an EIRL or EURL, is usually named after its holder («EARL Martin»), so
those forms count as a person too. A French title is cleaned by pattern, not by a known name, because the
French records carry no promoter field to learn the name from. The Spanish rule is left as it was.
"""
from __future__ import annotations

import re
from typing import Iterable

_PERSON = re.compile(r"^\s*(D\.ª|Dª|Dña\.?|D\.|Don|Doña|Sr\.|Sra\.)\s", re.IGNORECASE)
# What a title or a text says instead of the name taken out of it.
REDACTED = "[persona física]"
REDACTED_FR = "[personne physique]"

_HONORIFIC_FR = r"M\.|MM\.|Mme\.?|Mmes|Mlle\.?|Monsieur|Madame|Mademoiselle"
_ONE_PERSON_FIRM_FR = r"EARL|GAEC|SCEA|EIRL|EURL"
_PERSON_FR = re.compile(rf"^\s*(?:{_HONORIFIC_FR}|{_ONE_PERSON_FIRM_FR})(?=[\s.]|$)", re.IGNORECASE)
# The honorific or the firm, its particles («de la», «du»), and up to four capitalised words of name.
_NAMED_FR = re.compile(
    rf"\b(?:{_HONORIFIC_FR}|(?-i:{_ONE_PERSON_FIRM_FR}))(?=[\s.])\s*"
    r"(?:(?:de|du|des|la|le|les|l['’]|d['’])\s*)*"
    r"(?:[A-ZÀ-ÖØ-Þ][\w'’-]*\.?(?:\s+|$|(?=[,;:)]))){1,4}",
    re.UNICODE)


def promoter(name: str | None, country: str = "ES") -> str | None:
    """The promoter as published, or None when it is a natural person: no person is named here."""
    if not name:
        return None
    return None if (_PERSON_FR if country == "FR" else _PERSON).match(name) else name


def redact_fr(text: str) -> str:
    """A French text without anyone named by honorific or by a one-person firm."""
    return _NAMED_FR.sub(lambda m: REDACTED_FR + (" " if m.group(0)[-1:].isspace() else ""), text or "")


def redact(text: str, names: Iterable[str]) -> str:
    """`text` without any of `names`, with or without the honorific."""
    for name in sorted(names, key=len, reverse=True):
        bare = _PERSON.sub("", name, count=1).strip()
        # A first name alone would also blank out places such as San Juan: only full names go.
        for s in (name, bare) if len(bare.split()) >= 2 else (name,):
            text = text.replace(s, REDACTED)
    return text


def set_promoter(a, name: str) -> None:
    """Gives a bulletin act (boe.Anuncio) its promoter. A natural person is left out, and the name is
    taken out of the title and the text too, since the reports publish both."""
    if promoter(name):
        a.promotor = name
    else:
        a.promotor = ""
        a.titulo, a.texto = redact(a.titulo, [name]), redact(a.texto or "", [name])


def scrub(data, country: str = "ES"):
    """Applies the rule to stored data (a state, a report, a resolution sheet): every `promotor` who is
    a natural person is emptied, and the name is taken out of every other text in `data` (titles,
    pairing reasons). Changes `data` in place and returns it."""
    names: set[str] = set()

    def find(x) -> None:
        if isinstance(x, dict):
            p = x.get("promotor")
            if isinstance(p, str) and p and promoter(p, country) is None:
                names.add(p)
                x["promotor"] = ""
            for v in x.values():
                find(v)
        elif isinstance(x, list):
            for v in x:
                find(v)

    def clean(x):
        if isinstance(x, str):
            x = redact(x, names)
            return redact_fr(x) if country == "FR" else x
        if isinstance(x, dict):
            for k, v in x.items():
                x[k] = clean(v)
        elif isinstance(x, list):
            x[:] = [clean(v) for v in x]
        return x

    find(data)
    return clean(data) if names or country == "FR" else data
