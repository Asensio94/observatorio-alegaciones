"""France: the developer and the commune, read from the first pages of the environmental authority's avis.

projets-environnement stopped filling the developer field in 2025, and a developer's own filing (TPS) often
gives no place but the department. The avis of the environmental authority (MRAe or IGEDD) says both on
its first page: the MRAe's current form has a box («Nom du pétitionnaire», «Commune», «Département»);
older avis and the IGEDD's put it in the title («… à Saint-Cyr-les-Colons (Yonne)», «porté par la société
…»). Only those two facts are kept, in a small cache per record; the PDF is not stored, and the rest of
the avis (which names the authority's members) is not read here.

A developer that is a natural person is dropped by privacy.promoter, as in Spain. Their name may still
be in the project's title without an honorific («Élevage Dupont»), and the title is rebuilt from the
register on every run; so the cache keeps a fingerprint of each word of the name (a truncated hash, from
which the name cannot be read back) and `redact_title` takes out the words of the title that match it.
"""
from __future__ import annotations

import hashlib
import io
import json
import re

from . import privacy
from .config import CACHE_DIR

CACHE = CACHE_DIR / "avis_fr"
CACHE.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 40_000_000

_SP = r"[ \t  ]"
# The MRAe's box («Nom du pétitionnaire», «Commune») and Nouvelle-Aquitaine's («Maître d'ouvrage :»,
# «Localisation du projet : Commune de X (16)»), read line by line.
_BOX_PROMOTER = re.compile(rf"Nom{_SP}+du{_SP}+p[ée]titionnaire{_SP}+(.+?)\n(?=Commune|D[ée]partement|Objet)", re.S)
_OWNER_LINE = re.compile(rf"^Ma[îi]tre(?:\(s\))?{_SP}+d[’']ouvrage(?:\(s\))?{_SP}*:{_SP}*(?:(?:la{_SP}+)?soci[ée]t[ée]{_SP}+)?(.+?){_SP}*$", re.M | re.I)
_BOX_COMMUNE = re.compile(rf"^Communes?{_SP}+(?!de{_SP})(.+?){_SP}*$", re.M)
_PLACE_LINE = re.compile(rf"^Localisation{_SP}+du{_SP}+projet{_SP}*:{_SP}*(?:communes?{_SP}+d[e’']{_SP}*)?(.+?){_SP}*(?:\([^)]*\))?{_SP}*$", re.M | re.I)
# In running text, read with its lines joined.
_CARRIED_BY = re.compile(r"port[ée]e?\s+par\s+(?:la\s+soci[ée]t[ée]|le\s+groupe|l[’']entreprise)\s+([^,(.;]+)", re.I)
_COMPANY_QUOTED = re.compile(r"[Ll]a\s+[Ss]oci[ée]t[ée]\s+«\s*([^»]+?)\s*»")
# «… à Saint-Cyr-les-Colons (Yonne)», «… sur la commune de X (32)», «… sur les communes de A et de B (32)»
_TITLE_PLACE = re.compile(
    r"(?:\bà|\b[Cc]ommunes?\s+d[e’'])\s*([A-ZÀ-Ý][\w’'\- ]+?)\s*\(([^)]{1,40})\)")
# Where a company's name stops in running text: «ALTAREA LOGISTIQUE et développé par …».
_NAME_END = re.compile(r"\s+(?:et|qui|dont|pour|dans|au|aux|en|afin)\s+.*$")


def _clean(s: str) -> str:
    return re.sub(rf"{_SP}+|\s*\n\s*", " ", s).strip(" –-")


def _fingerprint(word: str) -> str:
    return hashlib.sha256(word.casefold().encode()).hexdigest()[:16]


def _name_words(name: str) -> list[str]:
    """The words of a person's name that could stand alone in a title: capitalised, not the honorific
    or the firm's form, not a particle."""
    words = re.findall(r"[A-ZÀ-Ý][\w’'-]+", name)
    return [w for w in words if not re.fullmatch(r"(?:M|MM|Mme|Mlle|Monsieur|Madame|Mademoiselle|EARL|GAEC|SCEA|EIRL|EURL)", w)]


def redact_title(title: str, fingerprints: list[str]) -> str:
    if not fingerprints:
        return title
    marks = set(fingerprints)
    words = title.split(" ")
    out: list[str] = []
    for w in words:
        core = w.strip(",;:.()«»\"")
        if core and _fingerprint(core) in marks:
            if not (out and out[-1].startswith(privacy.REDACTED_FR)):
                out.append(w.replace(core, privacy.REDACTED_FR))
            continue
        out.append(w)
    return " ".join(out)


def read_header(text: str) -> dict:
    """{"promoter": str|None, "person": [fingerprints], "communes": [names]} from the avis' first two pages.
    A name with «et» is left whole: it may be one commune («Chemaudin et Vaux») or two, which only the
    INSEE lookup can tell (fr_projets.locate)."""
    # Running text with its lines joined, and words cut at the end of a line mended («So-\nlaire»).
    flat = re.sub(r"\s+", " ", re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=[a-zà-ÿ])", "", text))
    promoter = None
    m = _BOX_PROMOTER.search(text) or _OWNER_LINE.search(text)
    if m:
        promoter = _clean(m.group(1))
    else:
        m = _COMPANY_QUOTED.search(flat) or _CARRIED_BY.search(flat)
        if m:
            promoter = _NAME_END.sub("", m.group(1).strip())
    if promoter:
        # «X SAS – filiale des sociétés Y et Z»: the developer is X.
        promoter = re.split(r"\s+[–—-]\s+", promoter)[0].strip() or None
    communes: list[str] = []
    box = _PLACE_LINE.search(text) or _BOX_COMMUNE.search(text)
    if box:
        communes = [c for c in re.split(r"\s*[,;]\s*", _clean(box.group(1))) if c]
    else:
        t = _TITLE_PLACE.search(flat[:1500])
        if t:
            communes = [_clean(t.group(1))]
    public = privacy.promoter(promoter, "FR") if promoter else None
    person = [_fingerprint(w) for w in _name_words(promoter)] if promoter and public is None else []
    return {"promoter": public, "person": person, "communes": communes[:6]}


def header(rid: str, url: str) -> dict | None:
    """The avis' header for record `rid`, cached; None when the PDF cannot be read (scanned, missing)."""
    cache = CACHE / f"{re.sub(r'[^A-Za-z0-9_-]', '_', rid)}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    from pypdf import PdfReader  # only here: the rest of the project reads no PDF

    from .fr_projets import _SESSION

    r = _SESSION.get(url, timeout=120)
    if r.status_code in (403, 404, 410):
        out = None
    else:
        r.raise_for_status()
        out = None
        if len(r.content) <= MAX_BYTES:
            try:
                pdf = PdfReader(io.BytesIO(r.content))
                text = "\n".join((p.extract_text() or "") for p in pdf.pages[:2])
            except Exception:  # noqa: BLE001 - a damaged PDF is a missing header, not a failed run
                text = ""
            out = read_header(text) if text.strip() else None
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out
