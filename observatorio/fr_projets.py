"""France: public consultations from projets-environnement.gouv.fr, kept in data/estado_fr.json.

projets-environnement is the national register of projects that need an environmental assessment
(Opendatasoft dataset `sico_to_ods`, Licence Ouverte). It is fed from two systems: GUNenv, the
prefectures' one-stop shop, gives a town and its postcode; TPS, the developers' own filings, gives a
polygon or a point, or only the department. A record counts as a notice when it carries the dates of a
public consultation (enquête publique, participation par voie électronique…); a record without them is a
filed impact study with nothing yet to comment on, and is left out.

A notice is dated by the opening of its consultation, not by its publication in the register: the
register publishes a record again whenever a document is added (the decision, months later).

Each notice keeps the field names of the Spanish state (identificador, fecha, titulo, url_html…), so the
signals and the follow-up pages read both countries alike, plus `country: "FR"` and the INSEE codes.
Nothing personal is kept: the register no longer fills the developer field, titles are cleaned by
pattern (privacy.redact_fr) and the free-text description is not stored.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

import requests
from requests.adapters import HTTPAdapter
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from urllib3.util.retry import Retry

from . import fr_geo, privacy
from .config import DATA_DIR, USER_AGENT

COUNTRY = "FR"
ESTADO_PATH = DATA_DIR / "estado_fr.json"
SINCE = date(2026, 1, 1)

API = "https://www.projets-environnement.gouv.fr/api/explore/v2.1/catalog/datasets/sico_to_ods"
EXPORT_URL = API + "/exports/json"
# The register has no page per project; its own search, keyed by the record id, is the stable link.
RECORD_URL = "https://www.projets-environnement.gouv.fr/explore/dataset/sico_to_ods/table/?q=%22{rid}%22"

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = USER_AGENT
_SESSION.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])))

# The register's own nature and the title, read against the Spanish categories (extract.CATEGORIAS) so
# both countries count alike. First match wins: a solar plant filed as ICPE is still solar.
CATEGORIES_FR: list[tuple[str, re.Pattern]] = [
    ("eolica", re.compile(r"[ée]olien|a[ée]rog[ée]n[ée]rat|rubrique ICPE 2980", re.I)),
    ("fotovoltaica", re.compile(r"photovolta|solaire|agrivolta", re.I)),
    ("hidrogeno_baterias", re.compile(r"hydrog[èe]ne|[ée]lectroly|stockage d.[ée]nergie|batteries", re.I)),
    ("red_electrica", re.compile(r"ligne (?:a[ée]rienne|[ée]lectrique|souterraine)|poste (?:[ée]lectrique|source)|\d+\s*kV|RTE\b", re.I)),
    ("hidrocarburos_gas", re.compile(r"gazoduc|ol[ée]oduc|hydrocarbure|m[ée]thanier|stockage de gaz", re.I)),
    ("mineria", re.compile(r"carri[èe]re|rubrique ICPE 2510|mine\b|minier|granulats|sabli[èe]re", re.I)),
    ("transporte", re.compile(r"autoroute|route|d[ée]viation|contournement|ferroviaire|voie ferr[ée]e|a[ée]roport|LGV|rocade|[ée]changeur", re.I)),
    ("puertos_costas", re.compile(r"\bport\b|portuaire|littoral|dragage|digue", re.I)),
    ("hidraulica", re.compile(r"barrage|retenue|r[ée]servoir|irrigation|hydro[ée]lectri|micro-?centrale|seuil", re.I)),
    ("agua_concesion", re.compile(r"forage|pr[ée]l[èe]vement d.eau|captage|rejet|assainissement|station d.[ée]puration|STEP\b", re.I)),
    ("urbanismo_industria", re.compile(r"ZAC\b|lotissement|am[ée]nagement|logistique|entrep[ôo]t|industri|usine|"
                                       r"d[ée]chets|m[ée]thanis|incin[ée]r|installations? class[ée]es|ICPE|[ée]levage|"
                                       r"porcin|avicole|volailles|bovin|poulailler", re.I)),
]

# Phrases of the register, kept for the page (in French) and for the signals' details.
PROCEDURES = {"AENV": "Autorisation environnementale"}


def fetch(since: date = SINCE) -> list[dict]:
    """Every record published since `since` (one request: the export holds the whole selection)."""
    r = _SESSION.get(EXPORT_URL, params={"where": f"date_de_diffusion >= date'{since.isoformat()}'"}, timeout=180)
    r.raise_for_status()
    return r.json()


def category(record: dict) -> str:
    base = f"{record.get('titre') or ''}\n{record.get('nature') or ''}"
    for cat, pat in CATEGORIES_FR:
        if pat.search(base):
            return cat
    return "otros"


def _day(value: str | None) -> str | None:
    """«2026-04-23» or «2026-02-10T16:01:42+00:00» → «2026-04-23»; anything else → None."""
    m = re.match(r"\d{4}-\d{2}-\d{2}", value or "")
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(0)).isoformat()
    except ValueError:
        return None


def is_notice(record: dict, since: date = SINCE) -> bool:
    """A public consultation that opened on or after `since`. The register publishes a record again when a
    decision is added, so an old consultation can come back with a recent publication date: it is not a
    notice here (its decision is what matters about it)."""
    opens, closes = _day(record.get("dateouverture")), _day(record.get("datefermeture"))
    return bool(opens and closes and opens >= since.isoformat())


def _geometry(record: dict) -> BaseGeometry | None:
    loc = record.get("localisation")
    if isinstance(loc, dict) and loc.get("geometry"):
        loc = loc["geometry"]
    if isinstance(loc, dict) and loc.get("type"):
        try:
            g = shape(loc)
            return g if not g.is_empty else None
        except (ValueError, TypeError, AttributeError):
            pass
    pt = record.get("geo_point_2d")
    if isinstance(pt, dict) and pt.get("lon") is not None:
        return Point(pt["lon"], pt["lat"])
    return None


def communes_named(names: list[str], department: str | None) -> list[dict]:
    """Communes from names read in an avis; «A et B» is tried whole first, then as two communes."""
    out: dict[str, dict] = {}
    for name in names:
        c = fr_geo.commune_by_name(name, None, department)
        found = [c] if c else [fr_geo.commune_by_name(p, None, department)
                               for p in re.split(r"\s+et\s+(?:de\s+|d['’]\s*)?", name) if p != name]
        for c in found:
            if c:
                out.setdefault(c["code"], c)
    return list(out.values())


def locate(record: dict, avis_communes: list[str] | None = None) -> tuple[list[dict], BaseGeometry | None, str]:
    """(communes, geometry for the Natura and GBIF cross, precision). A polygon is crossed as drawn
    («perimetro»); a town or a point is crossed through its commune's outline («municipio»)."""
    department = fr_geo.department_of(record.get("departement_de_la_prefecture"))
    g = _geometry(record)
    if g is not None and g.geom_type in ("Polygon", "MultiPolygon"):
        return fr_geo.communes_in(g), g, "perimetro"
    if g is not None:
        c = fr_geo.commune_at(g.x, g.y)
        communes = [c] if c else []
    elif record.get("location_ville"):
        c = fr_geo.commune_by_name(record["location_ville"], record.get("code_postal"), department)
        communes = [c] if c else []
    else:
        communes = []
    if not communes and avis_communes:  # a filing with only its department: the avis names the place
        communes = communes_named(avis_communes, department)
    return communes, fr_geo.project_geometry(communes) if communes else None, "municipio"


def _documents(record: dict) -> dict:
    keys = {"registre": "dc_relation_websitedebate", "avis_ae": "dc_relation_expertise_avisae",
            "reponse_avis_ae": "dc_relation_expertise_reponseavisae", "etude_impact": "dc_relation_expertise_etudeimpact",
            "resume_non_technique": "dc_relation_synthesis", "arrete_ouverture": "dc_relation_informationnote",
            "decision": "dc_relation_decision"}
    return {k: record[f] for k, f in keys.items() if isinstance(record.get(f), str) and record[f].startswith("http")}


def notice(record: dict) -> dict:
    """The record as a notice, without geography (see `locate`)."""
    rid = str(record["recordsid"])
    department = fr_geo.department_of(record.get("departement_de_la_prefecture"))
    procedure = record.get("type_de_procedure") or ""
    return {
        "country": COUNTRY, "identificador": f"FR-PE-{rid}", "fuente": "projets-environnement", "sistema": record.get("source"),
        "fecha": _day(record.get("dateouverture")), "publie": _day(record.get("date_de_diffusion")), "titulo": privacy.redact_fr((record.get("titre") or "").strip()),
        "url_html": RECORD_URL.format(rid=rid), "categoria": category(record),
        "nature": record.get("nature") or "", "procedure": PROCEDURES.get(procedure, procedure),
        "departamento": None, "departement": department, "promotor": "", "expediente": rid, "potencia_mw": None,
        "consultation": {"ouverture": _day(record.get("dateouverture")), "fermeture": _day(record.get("datefermeture")),
                         "etat": record.get("etat_de_la_consultation_publique")},
        "fecha_limite": _day(record.get("datefermeture")) or "",
        "documents": _documents(record),
        "municipios": [], "municipios_insee": [], "provincias": [department] if department else [],
    }


def cargar_estado() -> dict:
    if ESTADO_PATH.exists():
        e = privacy.scrub(json.loads(ESTADO_PATH.read_text(encoding="utf-8")), COUNTRY)
        e.setdefault("anuncios", {})
        return e
    return {"anuncios": {}}


def guardar_estado(estado: dict) -> None:
    ESTADO_PATH.parent.mkdir(parents=True, exist_ok=True)
    ESTADO_PATH.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


def species_summary(esp: dict, vernacular=None) -> dict:
    """What the state keeps of the GBIF cross: counts and the dozen most threatened species, never a record
    or a point. `vernacular(key)` gives the French common name (species.vernacular_fr)."""
    top = esp.get("especies", [])[:12]
    return {"n_especies": esp.get("n_especies", 0), "n_aves": esp.get("n_aves", 0),
            "especies_top": [{"key": e.get("key"), "scientificName": e["scientificName"],
                              "vernacular_fr": (vernacular(e["key"]) if vernacular and e.get("key") else ""),
                              "categoria_uicn": e["categoria_uicn"], "class": e.get("class", "")} for e in top]}


def _located(prev: dict | None) -> bool:
    return bool(prev and prev.get("cruce"))


def process(record: dict, prev: dict | None, with_gbif: bool = True) -> tuple[dict, bool]:
    """The notice for `record`, crossed with Natura 2000 and GBIF unless `prev` already was. Returns
    (notice, crossed now). Dates, state and documents always come fresh from the register."""
    from . import fr_avis, natura, species  # heavy clients, only when crossing

    a = notice(record)
    head = None
    if a["documents"].get("avis_ae"):
        try:
            head = fr_avis.header(str(record["recordsid"]), a["documents"]["avis_ae"])
        except requests.RequestException:
            head = None  # tried again on the next run: nothing is cached
    if head:
        a["promotor"] = head.get("promoter") or ""
        a["titulo"] = fr_avis.redact_title(a["titulo"], head.get("person") or [])
    if _located(prev):
        keep = ("municipios", "municipios_insee", "precision", "natura", "n_especies", "n_aves", "especies_top", "cruce")
        a.update({k: prev[k] for k in keep if k in prev})
        for e in a.get("especies_top") or []:  # crossed before the French names were kept
            if "vernacular_fr" not in e and with_gbif:
                e["vernacular_fr"] = species.vernacular_fr(e["key"]) if e.get("key") else ""
        return stamp(a), False
    communes, g, precision = locate(record, (head or {}).get("communes"))
    a["municipios"] = [c["nom"] for c in communes]
    a["municipios_insee"] = [c["code"] for c in communes]
    a["precision"] = precision
    a["natura"], a["n_especies"], a["n_aves"], a["especies_top"] = [], 0, 0, []
    if g is not None:
        a["natura"] = [{"sitecode": s["sitecode"], "nombre": s["nombre"], "tipo": s["tipo"]} for s in natura.sitios_natura(g)]
        if with_gbif:
            a.update(species_summary(species.especies_amenazadas(g), species.vernacular_fr))
    # A record with no place found is crossed again on the next run: the avis may name the commune.
    a["cruce"] = "ok" if g is not None and (with_gbif or a["natura"]) else ""
    return stamp(a), True


def stamp(a: dict, now: datetime | None = None) -> dict:
    a["actualizado"] = (now or datetime.now()).strftime("%Y-%m-%d")
    return a
