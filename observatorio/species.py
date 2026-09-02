"""Especies amenazadas presentes en la zona del proyecto (GBIF)."""

from __future__ import annotations

import hashlib
import json

import requests
from shapely.geometry.base import BaseGeometry

from .config import (
    AVES_TAXON_KEY,
    CACHE_DIR,
    GBIF_OCC_URL,
    GBIF_SPECIES_URL,
    GBIF_THREAT_CATEGORIES,
    GBIF_YEAR_FROM,
    USER_AGENT,
)
from .geo import to_wkt_simplificado

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT})
_SESSION.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])))

_ESP_CAT = {"CR": "En peligro crítico", "EN": "En peligro", "VU": "Vulnerable", "NT": "Casi amenazada"}


def _species_info(key: int) -> dict:
    cache = CACHE_DIR / "gbif" / f"species_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    r = _SESSION.get(GBIF_SPECIES_URL.format(key=key), timeout=60)
    r.raise_for_status()
    d = r.json()
    r2 = _SESSION.get(GBIF_SPECIES_URL.format(key=key) + "/vernacularNames", params={"limit": 50}, timeout=60)
    vern = ""
    if r2.ok:
        names = [v for v in r2.json().get("results", []) if v.get("language") == "spa"]
        if names:
            vern = names[0].get("vernacularName", "")
    info = {
        "key": key,
        "scientificName": d.get("canonicalName") or d.get("scientificName"),
        "class": d.get("class"),
        "order": d.get("order"),
        "vernacular_es": vern,
    }
    cache.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return info


def especies_amenazadas(geom: BaseGeometry, max_species: int = 40) -> dict:
    """Devuelve resumen de especies amenazadas (UICN CR/EN/VU/NT) con registros en la geometría."""
    wkt = to_wkt_simplificado(geom)
    key = hashlib.md5(wkt.encode()).hexdigest()[:16]
    cache = CACHE_DIR / "gbif" / f"occ_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    resumen: dict = {"total_registros_amenazadas": 0, "aves_amenazadas_registros": 0, "especies": []}
    params = [
        ("geometry", wkt),
        ("year", f"{GBIF_YEAR_FROM},2030"),
        ("hasCoordinate", "true"),
        ("hasGeospatialIssue", "false"),
        ("kingdomKey", "1"),  # Animalia: descarta plantas ornamentales y cultivadas
        ("limit", "0"),
        ("facet", "speciesKey"),
        ("facetLimit", str(max_species)),
    ] + [("iucnRedListCategory", c) for c in GBIF_THREAT_CATEGORIES]
    r = _SESSION.get(GBIF_OCC_URL, params=params, timeout=120)
    if r.status_code == 400:
        # Geometría rechazada (autointersección tras simplificar): usamos la envolvente convexa
        wkt = to_wkt_simplificado(geom.buffer(0).convex_hull)
        params = [(k, wkt) if k == "geometry" else (k, v) for k, v in params]
        r = _SESSION.get(GBIF_OCC_URL, params=params, timeout=120)
    r.raise_for_status()
    d = r.json()
    resumen["total_registros_amenazadas"] = d.get("count", 0)
    counts = {}
    for f in d.get("facets", []):
        if f["field"] == "SPECIES_KEY":
            counts = {int(c["name"]): c["count"] for c in f["counts"]}

    # Categoría UICN por especie: una consulta por categoría para asignar (facet por categoría)
    cat_por_especie: dict[int, str] = {}
    for cat in GBIF_THREAT_CATEGORIES:
        p2 = [x for x in params if x[0] != "iucnRedListCategory"] + [("iucnRedListCategory", cat)]
        r2 = _SESSION.get(GBIF_OCC_URL, params=p2, timeout=120)
        if not r2.ok:
            continue
        for f in r2.json().get("facets", []):
            if f["field"] == "SPECIES_KEY":
                for c in f["counts"]:
                    cat_por_especie.setdefault(int(c["name"]), cat)

    especies = []
    for sk, n in counts.items():
        info = _species_info(sk)
        cat = cat_por_especie.get(sk, "")
        especies.append(
            {
                **info,
                "registros": n,
                "categoria_uicn": cat,
                "categoria_es": _ESP_CAT.get(cat, cat),
            }
        )
    orden_cat = {"CR": 0, "EN": 1, "VU": 2, "NT": 3, "": 4}
    especies.sort(key=lambda e: (orden_cat.get(e["categoria_uicn"], 4), -e["registros"]))
    resumen["especies"] = especies
    resumen["aves_amenazadas_registros"] = sum(e["registros"] for e in especies if e.get("class") == "Aves")
    resumen["n_especies"] = len(especies)
    resumen["n_aves"] = sum(1 for e in especies if e.get("class") == "Aves")
    cache.write_text(json.dumps(resumen, ensure_ascii=False), encoding="utf-8")
    return resumen
