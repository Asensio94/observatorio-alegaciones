"""Geolocalización de municipios mediante Nominatim (OSM), con caché en disco."""

from __future__ import annotations

import json
import re
import time
import unicodedata

import requests
from shapely.geometry import shape, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .config import CACHE_DIR, NOMINATIM_MIN_INTERVAL, NOMINATIM_URL, USER_AGENT

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT})
_last_call = 0.0


def _slug(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _throttle() -> None:
    global _last_call
    wait = NOMINATIM_MIN_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def municipio_geom(municipio: str, provincia: str | None = None) -> BaseGeometry | None:
    """Polígono administrativo del municipio (EPSG:4326) o None si no se resuelve."""
    key = _slug(f"{municipio}_{provincia or ''}")
    cache = CACHE_DIR / "geo" / f"{key}.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        return shape(data) if data else None

    q = ", ".join(x for x in (municipio, provincia, "España") if x)
    _throttle()
    r = _SESSION.get(
        NOMINATIM_URL,
        params={"q": q, "format": "json", "polygon_geojson": 1, "limit": 5, "countrycodes": "es"},
        timeout=60,
    )
    r.raise_for_status()
    geom = None
    for res in r.json():
        if res.get("class") == "boundary" and res.get("type") == "administrative":
            gj = res.get("geojson")
            if gj and gj.get("type") in ("Polygon", "MultiPolygon"):
                geom = shape(gj)
                break
    if geom is None and provincia:
        # Reintento sin provincia (nombres en gallego/catalán/euskera a veces no casan)
        return municipio_geom(municipio, None)
    cache.write_text(json.dumps(mapping(geom)) if geom is not None else "null", encoding="utf-8")
    return geom


def geom_proyecto(municipios: list[str], provincias: list[str]) -> tuple[BaseGeometry | None, list[str], list[str]]:
    """Unión de los polígonos de los municipios. Devuelve (geom, resueltos, no_resueltos)."""
    geoms: list[BaseGeometry] = []
    ok: list[str] = []
    ko: list[str] = []
    prov = provincias[0] if provincias else None
    for m in municipios:
        g = municipio_geom(m, prov)
        if g is None and len(provincias) > 1:
            for p in provincias[1:]:
                g = municipio_geom(m, p)
                if g is not None:
                    break
        if g is None:
            ko.append(m)
        else:
            ok.append(m)
            geoms.append(g)
    if not geoms:
        return None, ok, ko
    return unary_union(geoms), ok, ko


def to_wkt_simplificado(geom: BaseGeometry, max_len: int = 1500) -> str:
    """WKT compacto para GBIF (límite práctico de longitud de URL)."""
    tol = 0.001
    g = geom
    while True:
        wkt = g.wkt
        if len(wkt) <= max_len or tol > 0.2:
            break
        tol *= 2
        g = geom.simplify(tol, preserve_topology=True)
    if len(wkt) > max_len:
        wkt = geom.convex_hull.wkt
    # GBIF exige orientación antihoraria en polígonos
    from shapely.geometry.polygon import orient
    from shapely.geometry import Polygon, MultiPolygon
    def _orient(gg):
        if isinstance(gg, Polygon):
            return orient(gg, sign=1.0)
        if isinstance(gg, MultiPolygon):
            return MultiPolygon([orient(p, sign=1.0) for p in gg.geoms])
        return gg
    from shapely import wkt as _wkt
    g2 = _orient(_wkt.loads(wkt))
    return re.sub(r"(\d+\.\d{5})\d+", r"\1", g2.wkt)
