"""French municipalities: INSEE codes and outlines from geo.api.gouv.fr (France's equivalent of the IGN layer).

projets-environnement gives a project either as a town name with its postcode or as a polygon, never both.
A name is resolved within its postcode first (a postcode spans a handful of communes) and then by the API's
own name search within the department, which forgives hyphens and spaces. A polygon is resolved by asking
which commune holds a point inside each of its parts. Codes are INSEE's: five characters, 2A/2B in Corsica.
"""
from __future__ import annotations

import json
import re
import unicodedata

import requests
from requests.adapters import HTTPAdapter
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from urllib3.util.retry import Retry

from .config import CACHE_DIR, USER_AGENT

GEO_API = "https://geo.api.gouv.fr"
CACHE = CACHE_DIR / "geo_fr"
CACHE.mkdir(parents=True, exist_ok=True)

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = USER_AGENT
_SESSION.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])))

# The API's own score for a name search; below it, the match is a different town.
MIN_SCORE = 0.8


def fold(name: str) -> str:
    """A town name reduced for comparison: «Val-d'Épy» and «Val d Epy» are the same; «St» is «Saint»."""
    s = "".join(c for c in unicodedata.normalize("NFD", name) if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"\bste\b", "sainte", s)
    return re.sub(r"\bst\b", "saint", s)


def department_of(value: str | None) -> str | None:
    """«13 - Bouches-du-Rhône», «2A» or «974» → the department code alone."""
    m = re.match(r"\s*(2[AB]|97\d|\d{2})\b", value or "", re.I)
    return m.group(1).upper() if m else None


def _department_of_postcode(postcode: str | None) -> str | None:
    """Overseas postcodes carry the three-digit department; Corsica's «20» stands for both 2A and 2B."""
    pc = (postcode or "").strip()
    if not re.fullmatch(r"\d{5}", pc) or pc.startswith("20"):
        return None
    return pc[:3] if pc.startswith("97") else pc[:2]


def _get(path: str, params: dict, cache_key: str):
    cache = CACHE / f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', cache_key)}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    r = _SESSION.get(GEO_API + path, params=params, timeout=60)
    if r.status_code == 404:
        data = None
    else:
        r.raise_for_status()
        data = r.json()
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def commune_by_name(name: str, postcode: str | None, department: str | None) -> dict | None:
    """{code, nom} of the commune called `name`, or None. The postcode is tried first, then the department."""
    want = fold(name)
    if not want:
        return None
    if postcode and re.fullmatch(r"\d{5}", postcode.strip()):
        found = _get("/communes", {"codePostal": postcode.strip(), "fields": "code,nom"}, f"cp_{postcode.strip()}") or []
        for c in found:
            if fold(c["nom"]) == want:
                return {"code": c["code"], "nom": c["nom"]}
        # The short form of a longer name («Moutiers» for «Moutiers-en-Beauce»), when only one fits.
        starts = [c for c in found if fold(c["nom"]).startswith(want + " ")]
        if len(starts) == 1:
            return {"code": starts[0]["code"], "nom": starts[0]["nom"]}
    department = department or _department_of_postcode(postcode)
    params = {"nom": name, "fields": "code,nom", "boost": "population", "limit": 3}
    if department:
        params["codeDepartement"] = department
    found = _get("/communes", params, f"nom_{department or 'fr'}_{want}") or []
    # The same name, whatever the score (the API scores some exact names low); else a close enough one.
    for c in found:
        if fold(c["nom"]) == want:
            return {"code": c["code"], "nom": c["nom"]}
    for c in found:
        if c.get("_score", 0) >= MIN_SCORE:
            return {"code": c["code"], "nom": c["nom"]}
    return None


def commune_at(lon: float, lat: float) -> dict | None:
    found = _get("/communes", {"lon": f"{lon:.5f}", "lat": f"{lat:.5f}", "fields": "code,nom"}, f"pt_{lon:.4f}_{lat:.4f}") or []
    return {"code": found[0]["code"], "nom": found[0]["nom"]} if found else None


def outline(code: str) -> BaseGeometry | None:
    """The commune's polygon (EPSG:4326), simplified to ~50 m: enough for crossing with Natura 2000 and
    GBIF, and the cache is kept in the repository, where full outlines would weigh tens of megabytes."""
    cache = CACHE / f"contour_{code}.json"
    if cache.exists():
        g = json.loads(cache.read_text(encoding="utf-8"))
        return shape(g) if g else None
    r = _SESSION.get(f"{GEO_API}/communes/{code}", params={"fields": "code", "format": "geojson", "geometry": "contour"}, timeout=60)
    if r.status_code == 404:
        geom = None
    else:
        r.raise_for_status()
        f = r.json()
        geom = shape(f["geometry"]).simplify(0.0005, preserve_topology=True) if f.get("geometry") else None
    cache.write_text(json.dumps(_rounded(mapping(geom)) if geom is not None else None), encoding="utf-8")
    return geom


def _rounded(gj: dict) -> dict:
    def r(c):
        return [round(c[0], 5), round(c[1], 5)] if isinstance(c[0], float) else [r(x) for x in c]
    return {"type": gj["type"], "coordinates": r(gj["coordinates"])}


def communes_in(geom: BaseGeometry, max_parts: int = 12) -> list[dict]:
    """Communes holding the polygon: one point inside each of its largest parts. A project that crosses
    a boundary inside a single part is given the commune of that point only."""
    parts = sorted(getattr(geom, "geoms", [geom]), key=lambda g: -g.area)[:max_parts]
    out: dict[str, dict] = {}
    for p in parts:
        pt = p.representative_point()
        c = commune_at(pt.x, pt.y)
        if c:
            out.setdefault(c["code"], c)
    return list(out.values())


def project_geometry(communes: list[dict]) -> BaseGeometry | None:
    geoms = [g for g in (outline(c["code"]) for c in communes) if g is not None]
    return unary_union(geoms) if geoms else None


def to_geojson(geom: BaseGeometry) -> dict:
    return mapping(geom)
