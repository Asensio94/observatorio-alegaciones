"""Descarga de sumarios y anuncios del BOE (API de datos abiertos)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Iterator

import requests
from lxml import etree

from .config import BOE_SUMARIO_URL, BOE_XML_URL, CACHE_DIR, USER_AGENT

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


@dataclass
class Anuncio:
    identificador: str
    fecha: str
    seccion: str
    departamento: str
    titulo: str
    url_html: str
    url_xml: str
    url_pdf: str = ""
    texto: str = ""
    fuente: str = "BOE"  # BOE, BOC…
    # Campos derivados (clasificación y extracción)
    categoria: str = ""
    prioridad: int = 0
    tramite_ambiental: bool = False
    municipios: list[str] = field(default_factory=list)
    provincias: list[str] = field(default_factory=list)
    plazo_dias: int | None = None
    promotor: str = ""
    potencia_mw: float | None = None
    expediente: str = ""
    fecha_limite: str = ""  # ISO, calculada en plazos.py
    plazo_estimado: bool = False  # True si el plazo no se detectó y se asumió el valor por defecto

    def to_dict(self) -> dict:
        return asdict(self)


def _as_list(x) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def fetch_sumario(day: date) -> dict | None:
    """Devuelve el sumario JSON de un día, o None si no hubo BOE (fin de semana, festivo)."""
    cache = CACHE_DIR / "boe" / f"sumario_{day:%Y%m%d}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    r = SESSION.get(BOE_SUMARIO_URL.format(yyyymmdd=f"{day:%Y%m%d}"), timeout=60)
    if r.status_code == 404:
        cache.write_text("null", encoding="utf-8")
        return None
    r.raise_for_status()
    data = r.json()
    if data.get("status", {}).get("code") not in (None, "200", 200):
        cache.write_text("null", encoding="utf-8")
        return None
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def iter_items(sumario: dict, day: date, secciones: tuple[str, ...] = ("5B",)) -> Iterator[Anuncio]:
    """Recorre los items de las secciones indicadas (por defecto V-B, Otros anuncios oficiales)."""
    for diario in _as_list(sumario["data"]["sumario"]["diario"]):
        for sec in _as_list(diario.get("seccion")):
            codigo = sec.get("codigo", "")
            if codigo not in secciones:
                continue
            for dep in _as_list(sec.get("departamento")):
                items = _as_list(dep.get("item"))
                for ep in _as_list(dep.get("epigrafe")):
                    items += _as_list(ep.get("item"))
                for it in items:
                    pdf = it.get("url_pdf")
                    if isinstance(pdf, dict):
                        pdf = pdf.get("texto", "")
                    yield Anuncio(
                        identificador=it.get("identificador", ""),
                        fecha=day.isoformat(),
                        seccion=codigo,
                        departamento=dep.get("nombre", ""),
                        titulo=it.get("titulo", ""),
                        url_html=it.get("url_html", ""),
                        url_xml=it.get("url_xml", BOE_XML_URL.format(id=it.get("identificador", ""))),
                        url_pdf=pdf or "",
                    )


def _descargar(anuncio: Anuncio) -> tuple[str, dict]:
    """Descarga el XML y guarda en caché el texto y las referencias posteriores."""
    r = SESSION.get(anuncio.url_xml, timeout=90, headers={"Accept": "application/xml"})
    r.raise_for_status()
    root = etree.fromstring(r.content)
    # El <texto> del documento es hijo directo de la raíz. Buscarlo con ".//texto" devuelve el primero
    # que aparezca, y en documentos con referencias posteriores ese es la nota de <analisis>
    # (", por Resolución de 15 de junio de 2023"), no la resolución.
    texto_el = root.find("texto")
    if texto_el is None:
        texto = ""
    else:
        parts = [t for t in texto_el.itertext()]
        texto = re.sub(r"[ \t]+", " ", "\n".join(p.strip() for p in parts if p.strip()))
    refs = {
        "anulada": (root.findtext("metadatos/judicialmente_anulada") or "").strip() == "S",
        "posteriores": [
            {
                "referencia": p.get("referencia", ""),
                "relacion": (p.findtext("palabra") or "").strip(),
                "texto": re.sub(r"\s+", " ", p.findtext("texto") or "").strip(" ,"),
            }
            for p in root.findall("analisis/referencias/posteriores/posterior")
        ],
    }
    (CACHE_DIR / "boe" / f"{anuncio.identificador}.txt").write_text(texto, encoding="utf-8")
    (CACHE_DIR / "boe" / f"{anuncio.identificador}.ref.json").write_text(
        json.dumps(refs, ensure_ascii=False), encoding="utf-8"
    )
    return texto, refs


def fetch_texto(anuncio: Anuncio) -> str:
    """Descarga el XML del anuncio y devuelve el texto plano (cacheado)."""
    cache = CACHE_DIR / "boe" / f"{anuncio.identificador}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    return _descargar(anuncio)[0]


def fetch_referencias(anuncio: Anuncio, refrescar: bool = False) -> dict:
    """Referencias posteriores que el BOE anota en el documento (correcciones, modificaciones,
    anulaciones judiciales). Cambian con el tiempo: `refrescar` vuelve a pedirlas."""
    cache = CACHE_DIR / "boe" / f"{anuncio.identificador}.ref.json"
    if cache.exists() and not refrescar:
        return json.loads(cache.read_text(encoding="utf-8"))
    return _descargar(anuncio)[1]


def business_days_back(end: date, n_days: int) -> list[date]:
    """Lista de fechas (todas, incluidos fines de semana; el API devuelve 404 si no hubo BOE)."""
    return [end - timedelta(days=i) for i in range(n_days)][::-1]
