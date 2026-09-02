"""Boletín Oficial de Cantabria (BOC).

El BOC no tiene API, pero sí dos cosas muy útiles:
- Un formulario de consulta por fecha (POST a boletines.do) cuya respuesta HTML enlaza el XML del día
  (verXmlAction.do?idBlob=N) y el PDF de cada anuncio (verAnuncioAction.do?idAnuBlob=N).
- Ese XML diario incluye el texto completo de cada anuncio, su CVE y el órgano emisor, así que basta
  una descarga por día y no hay que abrir PDFs.
"""

from __future__ import annotations

import json
import re
from datetime import date

import requests
from lxml import etree

from .boe import Anuncio
from .config import BOC_ANUNCIO_URL, BOC_CVE_URL, BOC_SUMARIO_URL, BOC_XML_URL, CACHE_DIR, USER_AGENT

FUENTE = "BOC"
COMUNIDAD = "Cantabria"
# Secciones del BOC que interesan: 5 Expropiación forzosa (líneas, carreteras) y 7 Otros anuncios
# (7.1 Urbanismo, 7.2 Medio Ambiente y Energía, 7.5 Varios).
SECCIONES_POR_DEFECTO = ("5", "7")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT})

_IDBLOB_RE = re.compile(r"verXmlAction\.do\?idBlob=(\d+)")
_ANUNCIO_RE = re.compile(r"verAnuncioAction\.do\?idAnuBlob=(\d+)[^>]*>\s*PDF\s*\(BOC-(\d{4}-\d+)")
_AYTO_RE = re.compile(r"^Ayuntamiento\s+de\s+(.+)$", re.I)


def fetch_sumario(day: date) -> dict | None:
    """Devuelve {"idblob": str, "anuncios": {cve: idAnuBlob}} o None si no hubo BOC ese día."""
    cache = CACHE_DIR / "boc_cantabria" / f"sumario_{day:%Y%m%d}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    r = _SESSION.post(
        BOC_SUMARIO_URL,
        data={"boletinBean.fecBolString": f"{day:%d/%m/%Y}", "boletinBean.tipoBol": "", "boton": "Buscar"},
        timeout=90,
    )
    r.raise_for_status()
    html = r.content.decode("latin-1")
    m = _IDBLOB_RE.search(html)
    if not m:
        cache.write_text("null", encoding="utf-8")
        return None
    data = {"idblob": m.group(1), "anuncios": {f"CVE-{cve}": idanu for idanu, cve in _ANUNCIO_RE.findall(html)}}
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def fetch_xml(idblob: str) -> bytes:
    cache = CACHE_DIR / "boc_cantabria" / f"boletin_{idblob}.xml"
    if cache.exists():
        return cache.read_bytes()
    r = _SESSION.get(BOC_XML_URL.format(id=idblob), timeout=180)
    r.raise_for_status()
    cache.write_bytes(r.content)
    return r.content


def _texto(el) -> str:
    if el is None:
        return ""
    partes = []
    for p in el.iter():
        if p.tag in ("p", "center") and "".join(p.itertext()).strip():
            partes.append(re.sub(r"\s+", " ", " ".join(p.itertext())).strip())
    if not partes:
        partes = [t.strip() for t in el.itertext() if t.strip()]
    return "\n".join(partes)


def anuncios_dia(day: date, secciones: tuple[str, ...] = SECCIONES_POR_DEFECTO) -> list[Anuncio] | None:
    """Anuncios del BOC de ese día en las secciones indicadas, con texto completo. None si no hubo BOC."""
    sumario = fetch_sumario(day)
    if not sumario:
        return None
    root = etree.fromstring(fetch_xml(sumario["idblob"]))
    detalle = root.find(".//detalle_texto")
    if detalle is None:
        return []
    out: list[Anuncio] = []
    for sec in detalle.findall("seccion"):
        cod = sec.get("codSeccion", "")
        num_sec = str(int(cod[:2]) // 10) if cod[:2].isdigit() else cod
        if num_sec not in secciones:
            continue
        subsec = ""
        emisor = ""
        for el in sec.iter():  # orden de documento: subsección → emisor → disposiciones
            if el.tag == "titulo_subsec":
                subsec = re.sub(r"\.(?=[A-Za-zÁÉÍÓÚ])", ". ", (el.text or "").strip())
            elif el.tag in ("emisor", "emisor_text", "emisor_text2"):
                emisor = re.sub(r"\s+", " ", " ".join(el.itertext())).strip() or emisor
            elif el.tag == "disposicion":
                cve = (el.findtext("numeroExp") or "").strip()
                if not cve:
                    continue
                idanu = sumario["anuncios"].get(cve)
                url = BOC_ANUNCIO_URL.format(id=idanu) if idanu else BOC_CVE_URL.format(cve=cve)
                out.append(
                    Anuncio(
                        identificador="BOC-" + cve.removeprefix("CVE-"),
                        fecha=day.isoformat(),
                        seccion=subsec or (sec.findtext("titulo_sec") or "").strip(),
                        departamento=emisor,
                        titulo=re.sub(r"\s+", " ", el.findtext("titulo_text") or "").strip(),
                        url_html=url,
                        url_xml=BOC_XML_URL.format(id=sumario["idblob"]),
                        url_pdf=url,
                        texto=_texto(el.find("texto")),
                        fuente=FUENTE,
                    )
                )
    return out


def completar_geo(a: Anuncio) -> Anuncio:
    """Tras extraer_datos: en el BOC la provincia es siempre Cantabria y, si el anuncio lo publica un
    ayuntamiento y no se detectó municipio en el texto, el municipio es el del emisor."""
    a.provincias = [COMUNIDAD]
    if not a.municipios:
        m = _AYTO_RE.match(a.departamento or "")
        if m:
            a.municipios = [m.group(1).strip()]
    return a
