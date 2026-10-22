"""No natural person is stored or published: the rule, and where it is applied.

The bulletins name a natural person with an honorific («D. Nombre Apellidos», «Dña. …»); companies and
public bodies carry none. Many companies carry no legal form either («Esteyco»), so the test is the
honorific, not a missing «S.L.». A company named after a place such as Don Benito would lose its name:
the rule fails on the side of naming no one.

New data goes through `set_promoter` when the promoter is extracted; data stored before the rule goes
through `scrub` when it is loaded, so the next daily run rewrites it clean.
"""
from __future__ import annotations

import re
from typing import Iterable

_PERSON = re.compile(r"^\s*(D\.ª|Dª|Dña\.?|D\.|Don|Doña|Sr\.|Sra\.)\s", re.IGNORECASE)
# What a title or a text says instead of the name taken out of it.
REDACTED = "[persona física]"


def promoter(name: str | None) -> str | None:
    """The promoter as published, or None when it is a natural person: no person is named here."""
    return None if not name or _PERSON.match(name) else name


# What a company or a public body carries and a person does not: a legal form, a kind of body or a sector
# word. Not an acronym: a name written in capitals would pass for one. Used where most applicants are people (the coast: a house in the protection strip),
# so a name is published only when it is recognisably not a person. The BOC names people without «D.».
_ENTITY = re.compile(
    r"\b(?:S\.?\s?L\.?(?:U|L)?|S\.?\s?A\.?U?|S\.?\s?C\.?(?:P|L)?|C\.?\s?B\.?|S\.?\s?Coop|A\.?\s?I\.?\s?E|U\.?\s?T\.?\s?E|"
    r"Sociedad|Compañía|Empresa|Grupo|Holding|Inversiones|Promociones|Inmobiliaria|Construcciones|Hoteles?|"
    r"Ayuntamiento|Concello|Junta|Gobierno|Consejería|Ministerio|Diputación|Cabildo|Consell|Mancomunidad|"
    r"Consorcio|Confederación|Demarcación|Dirección|Servicio|Agencia|Instituto|Organismo|Autoridad|Puertos?|"
    r"Comunidad|Asociación|Fundación|Cofradía|Club|Federación|Universidad|Parroquia|Obispado|Hermandad|"
    r"Energ\w*|Solar|Renovables?|Hidro\w*|Eólica|Ltd|GmbH|Inc|SAU|SLU)\b",
)


def entity(name: str | None) -> str | None:
    """The name when it is recognisably a company or a public body, else None (it may be a person)."""
    return name if name and promoter(name) and _ENTITY.search(name) else None


def redact(text: str, names: Iterable[str]) -> str:
    """`text` without any of `names`, with or without the honorific."""
    for name in sorted(names, key=len, reverse=True):
        bare = _PERSON.sub("", name, count=1).strip()
        # A first name alone would also blank out places such as San Juan: only full names go.
        for s in (name, bare) if len(bare.split()) >= 2 else (name,):
            text = text.replace(s, REDACTED)
    return text


# The list of affected owners of an expropriation goes whole: names and addresses, never needed here.
# A pattern for «Apellido Apellido, Nombre» was tried and dropped: in these texts it mostly matches bodies
# («Dirección General de Medio Ambiente, …») and places, which the municipalities are read from.
_OWNERS = re.compile(
    r"relaci[oó]n\s+(?:concreta\s+e\s+individualizada\s+)?de\s+(?:los\s+)?(?:bienes|propietarios|titulares)",
    re.IGNORECASE,
)
OWNERS_CUT = "[Relación de bienes y titulares: no se guarda aquí; está en el boletín]"


def strip_people(text: str, names: Iterable[str] = ()) -> str:
    """A bulletin text that can be stored: without the list of affected owners and without `names`
    (applicants found to be people)."""
    m = None if text.endswith(OWNERS_CUT) else _OWNERS.search(text)  # the cut itself names the list
    if m:
        text = text[: m.start()] + OWNERS_CUT
    return redact(text, names)


def set_promoter(a, name: str) -> None:
    """Gives a bulletin act (boe.Anuncio) its promoter. A natural person is left out, and the name is
    taken out of the title and the text too, since the reports publish both."""
    if promoter(name):
        a.promotor = name
    else:
        a.promotor = ""
        a.titulo, a.texto = redact(a.titulo, [name]), redact(a.texto or "", [name])


def scrub(data, strict: bool = False):
    """Applies the rule to stored data (a state, a report, a resolution sheet): every `promotor` who is
    a natural person is emptied, and the name is taken out of every other text in `data` (titles,
    pairing reasons). With `strict`, every promoter that is not recognisably an `entity` counts as a
    person. Changes `data` in place and returns it."""
    names: set[str] = set()
    keep = entity if strict else promoter

    def find(x) -> None:
        if isinstance(x, dict):
            p = x.get("promotor")
            if isinstance(p, str) and p and keep(p) is None:
                names.add(p)
                x["promotor"] = ""
            for v in x.values():
                find(v)
        elif isinstance(x, list):
            for v in x:
                find(v)

    def clean(x):
        if isinstance(x, str):
            return redact(x, names)
        if isinstance(x, dict):
            for k, v in x.items():
                x[k] = clean(v)
        elif isinstance(x, list):
            x[:] = [clean(v) for v in x]
        return x

    find(data)
    return clean(data) if names else data
