"""Real project footprint from the list of affected land ("relación de bienes y derechos afectados").

Expropriation and right-of-way notices list every parcel a project occupies: cadastral
municipality, polygon and parcel, or the full cadastral reference. Joining that list with the
Catastro INSPIRE parcels gives the land the project actually touches, which is far tighter than
the whole municipality the rest of the observatory uses as a proxy.

Privacy: the same tables carry owners' names, addresses and ID numbers. Only the cadastral
columns and the declared areas are read; the rest is discarded in memory and never cached or
published. The raw XML is not stored.

Limits, stated wherever the footprint is shown:
- The footprint is the union of whole affected parcels, so it over-estimates the works: a line
  crossing a 30 ha field with a 400 m² easement still draws the 30 ha. `declared_m2` against
  `parcels_m2` measures that gap.
- Navarre and the Basque Country keep their own cadastres (not in the national INSPIRE
  service): their parcels stay unresolved.
- Rows without a municipality heading are only placed when the notice names one municipality.
"""
from __future__ import annotations

import io
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass, field
from functools import lru_cache

import numpy as np
import requests
import shapely
from lxml import etree
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import transform

from .config import BOE_XML_URL, CACHE_DIR, USER_AGENT

VERSION = 6  # bump when the parsing rules change, so cached results are recomputed

ATOM_ROOT = "https://www.catastro.hacienda.gob.es/INSPIRE/CadastralParcels/ES.SDGC.CP.atom.xml"
DIR = CACHE_DIR / "catastro"
RESULTS = CACHE_DIR / "footprint"
FORAL_OFFICES = {"01", "20", "31", "48"}  # Álava, Gipuzkoa, Navarra, Bizkaia
FORAL_PROVINCES = {"alava", "araba", "araba alava", "alava araba", "gipuzkoa", "guipuzcoa", "navarra", "nafarroa",
                   "bizkaia", "vizcaya"}
MAX_PARCELS = 3000  # a long line can list thousands; beyond this the notice is summarised only

_HEADERS = {"User-Agent": USER_AGENT}
_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
_CP = "{http://inspire.ec.europa.eu/schemas/cp/4.0}"
_GML = "{http://www.opengis.net/gml/3.2}"
_REFCAT = re.compile(r"\b(\d{5}[A-Z]\d{8}|\d{7}[A-Z]{2}\d{4}[A-Z])(\d{4}[A-Z]{2})?\b")
# «PROVINCIA: T-TARRAGONA MUNICIPIO: CA-CAMBRILS ABREVIATURAS ...» inside a banner row (Enagás).
_MUNI_INLINE = re.compile(r"\bMUNICIPIO\s*:\s*(?:[A-Z]{1,3}-)?(.+?)(?=\s+[A-ZÁÉÍÓÚÑ]{4,}\s*:|\s+ABREVIATURAS|$)", re.I)
_MUNI_ROW = re.compile(r"^(?:T\.?\s*M\.?|T[ÉE]RMINO\s+MUNICIPAL(?:\s+DE)?|MUNICIPIO(?:\s+DE)?)\s*:?\s*(.+)$", re.I)


@dataclass
class ParcelRef:
    municipality: str = ""          # name as written in the notice, when there is no refcat
    office_code: str = ""           # 5-digit cadastral municipality code, from the refcat
    polygon: int | None = None
    parcel: int | None = None
    refcat: str = ""                # 14-character parcel reference
    expropriation_m2: float = 0.0
    easement_m2: float = 0.0
    temporary_m2: float = 0.0


@dataclass
class Footprint:
    status: str                     # ok | partial | no_table | unresolved
    version: int = VERSION
    n_rows: int = 0
    n_parcels: int = 0
    n_matched: int = 0
    unmatched: list[str] = field(default_factory=list)
    foral: int = 0
    public_domain: int = 0          # unmatched parcels 9000-9999: public-domain strips
    declared_m2: dict = field(default_factory=dict)
    parcels_m2: float = 0.0
    catastro_date: str | None = None
    geometry: dict | None = None    # GeoJSON, WGS84

    def shape(self):
        return shapely.geometry.shape(self.geometry) if self.geometry else None


# ---------------------------------------------------------------------------- notice tables

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def _muni_key(s: str) -> str:
    """«Los Corrales de Buelna», «CORRALES DE BUELNA (LOS)» and «Corrales de Buelna» match."""
    s = _norm(re.sub(r"\(([^)]*)\)\s*$", lambda m: "" if len(m.group(1)) > 4 else m.group(1), s))
    s = re.sub(r"\b(el|la|los|las|l|les|o|a|os|as)\b", " ", s)
    return " ".join(s.split())


def _number(s: str) -> float:
    s = (s or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(re.findall(r"-?\d+(?:\.\d+)?", s)[0])
    except IndexError:
        return 0.0


def _cells(tr) -> list[str]:
    return [" ".join("".join(td.itertext()).split()) for td in tr if td.tag in ("td", "th")]


def _columns(header: list[str]) -> dict[str, int] | None:
    """Index of each useful column, or None if this row is not a parcel-table header."""
    cols: dict[str, int] = {}
    for i, h in enumerate(_norm(c) for c in header):
        if re.search(r"\bml\b", h):           # linear metres (Enagás «SP (ML)»): not an area
            continue
        if ("ref" in h and "catast" in h and "pol" not in h) or h == "rc":
            cols.setdefault("refcat", i)
        elif h.startswith("pol") or h == "pg":
            cols.setdefault("polygon", i)
            if "ref" in h:                      # «Polígono/Ref Catastral»
                cols.setdefault("refcat", i)
        elif h.startswith("par") and "parcial" not in h:
            cols.setdefault("parcel", i)
        elif h.startswith(("termino", "t m", "municipio")):
            cols.setdefault("municipality", i)
        elif h.startswith(("expropiac", "exp ", "pleno dominio")) or h == "exp":
            cols.setdefault("expropriation", i)
        elif h.startswith(("servidumbre", "ser ", "sp ")) or h in ("ser", "sp"):
            cols.setdefault("easement", i)
        elif h.startswith(("ocupacion temporal", "ot ")) or h == "ot":
            cols.setdefault("temporary", i)
    if "refcat" in cols or {"polygon", "parcel"} <= cols.keys():
        return cols
    return None


def parse_tables(xml: bytes, default_municipality: str = "") -> list[ParcelRef]:
    """Parcels listed in the notice tables. Owner columns are never read."""
    root = etree.fromstring(xml)
    out: list[ParcelRef] = []
    heading = default_municipality
    for el in root.iter("p", "table"):
        if el.tag == "p":
            # ADIF and others name the municipality in a paragraph before each table.
            if not any(a.tag == "table" for a in el.iterancestors()):
                m = _MUNI_ROW.match(" ".join("".join(el.itertext()).split()))
                if m:
                    heading = m.group(1).strip()
            continue
        table = el
        cols, muni = None, heading
        for tr in table.iter("tr"):
            cells = _cells(tr)
            nonempty = [c for c in cells if c]
            if len(nonempty) == 1:
                m = _MUNI_ROW.match(nonempty[0]) or _MUNI_INLINE.search(nonempty[0])
                if m:
                    muni = m.group(1).strip()
                continue
            if cols is None:
                cols = _columns(cells)
                continue
            if _columns(cells):                 # repeated header on a new page
                continue

            def get(k: str) -> str:
                i = cols.get(k)
                return cells[i] if i is not None and i < len(cells) else ""

            p = ParcelRef(
                municipality=get("municipality") or muni,
                expropriation_m2=_number(get("expropriation")),
                easement_m2=_number(get("easement")),
                temporary_m2=_number(get("temporary")),
            )
            ref = _REFCAT.search(get("refcat").replace(" ", "").upper())
            if ref:
                p.refcat = ref.group(1)
                if p.refcat[5].isalpha():       # rustic: office+municipality, sector, polygon, parcel
                    p.office_code, p.polygon, p.parcel = p.refcat[:5], int(p.refcat[6:9]), int(p.refcat[9:14])
            else:
                pol, par = get("polygon"), get("parcel")
                if not (pol.strip().isdigit() and par.strip().isdigit()):
                    continue
                p.polygon, p.parcel = int(pol), int(par)
            out.append(p)
    return out


def fetch_parcels(identifier: str, default_municipality: str = "") -> list[ParcelRef]:
    """Parcels of a BOE notice. Only the parsed cadastral columns are cached."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    cache = RESULTS / f"{identifier}.parcels.json"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("version") == VERSION:
            return [ParcelRef(**p) for p in d["parcels"]]
    r = requests.get(BOE_XML_URL.format(id=identifier), headers=_HEADERS, timeout=90)
    r.raise_for_status()
    parcels = parse_tables(r.content, default_municipality)
    cache.write_text(json.dumps({"version": VERSION, "parcels": [asdict(p) for p in parcels]},
                                ensure_ascii=False), encoding="utf-8")
    return parcels


# ---------------------------------------------------------------------------- Catastro

def _get(url: str) -> bytes:
    for attempt in range(4):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=180)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError


def _cached(url: str, name: str, max_age_days: float = 25) -> bytes:
    DIR.mkdir(parents=True, exist_ok=True)
    f = DIR / name
    if f.exists() and time.time() - f.stat().st_mtime < max_age_days * 86400:
        return f.read_bytes()
    try:
        f.write_bytes(_get(url))
    except requests.RequestException:
        if not f.exists():
            raise
    return f.read_bytes()


@lru_cache(maxsize=1)
def municipalities() -> list[dict]:
    """Every cadastral municipality of the national INSPIRE service: code, name, office, zip."""
    root = ET.fromstring(_cached(ATOM_ROOT, "atom_root.xml"))
    offices = sorted({m for m in re.findall(r"CadastralParcels/(\d{2})/", ET.tostring(root, encoding="unicode"))})
    out = []
    for office in offices:
        url = f"https://www.catastro.hacienda.gob.es/INSPIRE/CadastralParcels/{office}/ES.SDGC.CP.atom_{office}.xml"
        feed = ET.fromstring(_cached(url, f"atom_{office}.xml"))
        office_name = _norm((feed.findtext("a:title", "", _ATOM_NS) or "").split(" - ")[-1])
        for e in feed.findall("a:entry", _ATOM_NS):
            link = e.find("a:link[@rel='enclosure']", _ATOM_NS)
            m = re.search(r"/(\d{5})-([^/]+)/", link.get("href", "") if link is not None else "")
            if m:
                out.append({"code": m.group(1), "name": m.group(2).strip(), "key": _muni_key(m.group(2)),
                            "office": office, "office_name": office_name, "url": link.get("href"),
                            "updated": (e.findtext("a:updated", "", _ATOM_NS) or "")[:10]})
    return out


def resolve_municipality(name: str, provinces: list[str]) -> str | None:
    """Cadastral code for a municipality name, using the notice provinces to break ties."""
    name = re.sub(r"^(?:de|del)\s+", "", name.strip(), flags=re.I)  # «Término municipal: de Alcázar del Rey»
    name = re.sub(r"\s*\(([^)]{5,})\)\s*$", "", name)  # «ARNEDO (LA RIOJA)»
    key = _muni_key(name)
    hits = [m for m in municipalities() if m["key"] == key]
    if len(hits) > 1:
        prov = {_norm(p) for p in provinces}
        hits = [m for m in hits if any(p and p in m["office_name"] for p in prov)] or hits
    return hits[0]["code"] if len(hits) == 1 else None


def _ring(pos) -> np.ndarray | None:
    if pos is None or not pos.text:
        return None
    return np.array(pos.text.split(), dtype=float).reshape(-1, 2)


@lru_cache(maxsize=16)
def _parcels(code: str) -> tuple[dict, str, str]:
    """{refcat: geometry} for a municipality, its CRS and the Catastro date."""
    m = next(x for x in municipalities() if x["code"] == code)
    data = _cached(m["url"], f"{code}.zip")
    geoms, crs = {}, "EPSG:25830"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = next(n for n in z.namelist() if n.endswith("cadastralparcel.gml"))
        with z.open(name) as f:
            for _, el in ET.iterparse(f, events=("end",)):
                if el.tag != _CP + "CadastralParcel":
                    continue
                ref = el.findtext(_CP + "nationalCadastralReference")
                polys = []
                for patch in el.iter(_GML + "PolygonPatch"):
                    ext = _ring(patch.find(f"{_GML}exterior/{_GML}LinearRing/{_GML}posList"))
                    if ext is None or len(ext) < 4:
                        continue
                    holes = [h for h in (_ring(i.find(f"{_GML}LinearRing/{_GML}posList"))
                                         for i in patch.findall(_GML + "interior")) if h is not None and len(h) >= 4]
                    polys.append(Polygon(ext, holes))
                srs = next((s.get("srsName") for s in el.iter(_GML + "Surface") if s.get("srsName")), None)
                if srs:
                    crs = "EPSG:" + re.findall(r"\d+", srs)[-1]
                if ref and polys:
                    geoms[ref] = shapely.make_valid(MultiPolygon(polys) if len(polys) > 1 else polys[0])
                el.clear()
    return geoms, crs, m["updated"]


def build(parcels: list[ParcelRef], provinces: list[str]) -> Footprint:
    if not parcels:
        return Footprint(status="no_table")
    fp = Footprint(status="unresolved", n_rows=len(parcels), declared_m2={
        "expropriation": round(sum(p.expropriation_m2 for p in parcels)),
        "easement": round(sum(p.easement_m2 for p in parcels)),
        "temporary": round(sum(p.temporary_m2 for p in parcels)),
    })
    by_code: dict[str, set] = {}
    resolved: dict[str, str | None] = {}
    for p in parcels[:MAX_PARCELS]:
        code = p.office_code
        if not code and p.municipality:
            if p.municipality not in resolved:
                resolved[p.municipality] = resolve_municipality(p.municipality, provinces)
            code = resolved[p.municipality] or ""
        if code[:2] in FORAL_OFFICES or (not code and provinces
                                          and all(_norm(x) in FORAL_PROVINCES for x in provinces)):
            fp.foral += 1
            continue
        if not code:
            fp.unmatched.append(f"{p.municipality or '?'} {p.polygon}/{p.parcel}")
            continue
        by_code.setdefault(code, set()).add(p.refcat or (p.polygon, p.parcel))

    found, dates = [], set()
    keys = set()
    for code, wanted in by_code.items():
        geoms, crs, updated = _parcels(code)
        index = {(int(r[6:9]), int(r[9:14])): r for r in geoms if r[5].isalpha() and r[6:].isdigit()}
        to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
        for w in wanted:
            ref = w if isinstance(w, str) else index.get(w)
            if ref in geoms and ref not in keys:
                keys.add(ref)
                fp.parcels_m2 += geoms[ref].area
                found.append(transform(to_wgs84, geoms[ref]))
                dates.add(updated)
            elif ref not in keys and not isinstance(w, str) and 9000 <= w[1] < 10000:
                fp.public_domain += 1           # roads, streams: the Catastro does not always draw them
            elif ref not in keys:
                fp.unmatched.append(f"{code} {w if isinstance(w, str) else '%s/%s' % w}")
    fp.n_parcels = len(keys) + len(fp.unmatched) + fp.foral + fp.public_domain
    fp.n_matched = len(keys)
    fp.unmatched = fp.unmatched[:50]
    fp.parcels_m2 = round(fp.parcels_m2)
    fp.catastro_date = max(dates) if dates else None
    if found:
        union = shapely.union_all(found).simplify(0.00002, preserve_topology=True)
        fp.geometry = mapping(union)
        fp.status = "ok" if fp.n_matched + fp.public_domain == fp.n_parcels else "partial"
    elif fp.foral == fp.n_parcels:
        fp.status = "foral"
    return fp


def footprint(identifier: str, municipalities_hint: list[str], provinces: list[str]) -> Footprint:
    """Footprint of a BOE notice, cached by identifier and rules version."""
    cache = RESULTS / f"{identifier}.json"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("version") == VERSION:
            return Footprint(**d)
    default = municipalities_hint[0] if len(municipalities_hint) == 1 else ""
    fp = build(fetch_parcels(identifier, default), provinces)
    cache.write_text(json.dumps(asdict(fp), ensure_ascii=False), encoding="utf-8")
    return fp


_LISTS_LAND = re.compile(r"bienes y derechos|relaci[oó]n (?:concreta|de titulares|de propietarios)|expropiaci[oó]n|"
                         r"necesidad de (?:la )?ocupaci[oó]n|utilidad p[uú]blica", re.I)


def lists_affected_land(text: str) -> bool:
    """Notices that may carry a parcel table; the parser decides whether there really is one."""
    return bool(_LISTS_LAND.search(text or ""))


def publish(identifier: str, fp: Footprint, out_dir) -> None:
    """GeoJSON for other tools (centinela-natura reads it to look for works outside the footprint)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    props = {k: v for k, v in asdict(fp).items() if k not in ("geometry", "unmatched")}
    props["identifier"] = identifier
    doc = {"type": "FeatureCollection",
           "features": [{"type": "Feature", "properties": props, "geometry": fp.geometry}]}
    (out_dir / f"{identifier}.geojson").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
