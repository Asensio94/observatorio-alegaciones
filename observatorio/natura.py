"""Cruce con Red Natura 2000 (servicio ArcGIS REST de la Agencia Europea de Medio Ambiente)."""

from __future__ import annotations

import hashlib
import json

import requests
from shapely.geometry import shape, mapping
from shapely.geometry.base import BaseGeometry

from .config import CACHE_DIR, EEA_LAYERS, EEA_NATURA_URL, USER_AGENT

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT})
_SESSION.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])))


def _esri_polygon(geom: BaseGeometry) -> dict:
    """Convierte Polygon/MultiPolygon shapely en geometría Esri JSON (solo anillos exteriores + agujeros)."""
    gj = mapping(geom.simplify(0.002, preserve_topology=True))
    rings: list[list[list[float]]] = []
    if gj["type"] == "Polygon":
        polys = [gj["coordinates"]]
    else:
        polys = gj["coordinates"]
    for poly in polys:
        for ring in poly:
            rings.append([[round(x, 5), round(y, 5)] for x, y in ring])
    return {"rings": rings, "spatialReference": {"wkid": 4326}}


def sitios_natura(geom: BaseGeometry) -> list[dict]:
    """Espacios Natura 2000 que intersectan la geometría. Devuelve lista de dicts con geometría GeoJSON."""
    esri = _esri_polygon(geom)
    key = hashlib.md5(json.dumps(esri, sort_keys=True).encode()).hexdigest()[:16]
    cache = CACHE_DIR / "natura" / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    sitios: list[dict] = []
    vistos: set[str] = set()
    for layer, tipo in EEA_LAYERS.items():
        r = _SESSION.post(
            EEA_NATURA_URL.format(layer=layer),
            data={
                "geometry": json.dumps(esri),
                "geometryType": "esriGeometryPolygon",
                "inSR": 4326,
                "outSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "SITECODE,SITENAME,SITETYPE,MS",
                "returnGeometry": "true",
                "geometryPrecision": 4,
                "f": "geojson",
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"EEA error: {data['error']}")
        for f in data.get("features", []):
            code = f["properties"].get("SITECODE")
            if code in vistos:
                continue
            vistos.add(code)
            g = shape(f["geometry"]) if f.get("geometry") else None
            inter_km2 = None
            if g is not None:
                try:
                    inter = g.intersection(geom)
                    inter_km2 = round(inter.area * 111.32 * 111.32 * 0.75, 1)  # aprox. grados² → km² (lat ~41º)
                except Exception:
                    inter_km2 = None
            sitios.append(
                {
                    "sitecode": code,
                    "nombre": f["properties"].get("SITENAME"),
                    "tipo": tipo,
                    "sitetype": f["properties"].get("SITETYPE"),
                    "solape_km2": inter_km2,
                    # Geometría simplificada: basta para el mapa y mantiene la caché ligera en el repositorio
                    "geometry": mapping(g.simplify(0.002, preserve_topology=True)) if g is not None else None,
                }
            )
    sitios.sort(key=lambda s: -(s["solape_km2"] or 0))
    cache.write_text(json.dumps(sitios), encoding="utf-8")
    return sitios
