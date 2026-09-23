"""Después del sí: condiciones de las declaraciones de impacto ambiental y cómo pedir cuentas de ellas.

Cada declaración de impacto ambiental (DIA) del Estado termina con un condicionado: medidas que el
promotor debe cumplir y documentos que debe entregar (programa de vigilancia ambiental, informes de
seguimiento de mortalidad de fauna, proyectos de medidas compensatorias...). Casi nadie comprueba
después si esos documentos existen. Este módulo:

- localiza en el BOE las DIA, los informes de impacto ambiental (IIA) y las modificaciones de
  condiciones que formula la Dirección General de Calidad y Evaluación Ambiental;
- trocea el condicionado en condiciones numeradas y etiqueta cada una (cuándo se aplica, si obliga a
  entregar un documento, a quién, con qué periodicidad y sobre qué: mortalidad de aves, quirópteros...);
- calcula la fecha en que la DIA perdería vigencia si el proyecto no ha empezado a ejecutarse
  (art. 43.1 de la Ley 21/2013: cuatro años desde su publicación en el BOE; art. 47.4 para el IIA);
- redacta una solicitud de acceso a la información ambiental (Ley 27/2006) con lo que hay que pedir.

Los datos se publican tal cual como base abierta en docs/datos/condicionado/.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from . import boe, extract, seguimiento
from .boe import Anuncio
from .config import DOCS_DIR

DATOS_DIR = DOCS_DIR / "datos" / "condicionado"
INDICE_PATH = DATOS_DIR / "indice.json"
VIGENCIA_ANOS = 4  # art. 43.1 (DIA) y 47.4 (IIA) de la Ley 21/2013
PRORROGA_ANOS = 2  # art. 43.2: la prórroga, si se concede, es de hasta dos años más

# --- Selección en el sumario --------------------------------------------------

_ORGANO = re.compile(r"Direcci[oó]n\s+General\s+de\s+Calidad\s+y\s+Evaluaci[oó]n\s+Ambiental", re.I)
TIPOS = [
    ("modificacion", re.compile(r"modificaci[oó]n\s+de\s+(?:las\s+)?condiciones|modifica[n]?\s+(?:el\s+|los\s+|las\s+)?condiciona(?:dos?|ntes)|modifican?\s+las\s+condiciones|por\s+la\s+que\s+se\s+modifica\s+la\s+(?:de\s+\d|resoluci)", re.I)),
    ("dia", re.compile(r"formula\s+(?:la\s+)?declaraci[oó]n\s+(?:de\s+)?impacto\s+ambiental", re.I)),
    ("iia", re.compile(r"formula\s+(?:el\s+)?informe\s+de\s+impacto\s+ambiental", re.I)),
]


_CORRECCION = re.compile(r"^\s*Correcci[oó]n\s+de\s+err|por\s+la\s+que\s+se\s+corrigen\s+err", re.I)


_FAVORABLE_PARTE = re.compile(r"declaraci[oó]n\s+de\s+impacto\s+ambiental\s+favorable", re.I)


def tipo_de(titulo: str) -> str:
    # Las correcciones de errores se enlazan a su resolución por las referencias del BOE; no son fichas.
    if not _ORGANO.search(titulo) or _CORRECCION.search(titulo):
        return ""
    for clave, pat in TIPOS:
        if pat.search(titulo):
            return clave
    return ""


def candidatos(dias: list[date], aviso=lambda s: None) -> list[Anuncio]:
    out = []
    for d in dias:
        try:
            s = boe.fetch_sumario(d)
        except Exception as e:  # noqa: BLE001 - un día caído no para el resto
            aviso(f"BOE {d}: {e}")
            continue
        if not s:
            continue
        out += [a for a in boe.iter_items(s, d, ("3",)) if tipo_de(a.titulo)]
    return out


# --- Troceo del condicionado ------------------------------------------------------

# Dónde empieza: "Condiciones al proyecto", a veces numerado ("5. Condiciones al proyecto").
_INICIO = re.compile(r"^\s*(?:\d+\.\s*|[A-Z][.)]\s*)?Condiciones\s+(?:generales\s+|ambientales\s+)?al\s+proyecto\b(?:.{0,40}|\s+y\s+medidas\b.{0,120}|[^.]{0,120}:)$", re.I | re.M)
# Dónde acaba: la fórmula de publicación o la firma.
_FIN = re.compile(
    r"^\s*(?:Se\s+procede\s+a\s+la\s+publicaci[oó]n|De\s+conformidad\s+con\s+el\s+apartado\s+(?:cuarto|4)|"
    r"Madrid,\s+\d|ANEXO\b)",
    re.M,
)
_NUM = re.compile(r"^\(?((?:[A-Z]\.)?\d+(?:\.\d+)*)(?:\.|\))?\)?\s+(\S.*)$")  # 1. / 5.2.1 / 1) / (1) / D.3.3.1
_BLOQUE = re.compile(r"^(?:\(?[ivx]+[).]|\(?[a-dA-D][).]|\d+(?:\.\d+)?\.?)?\s*(Condiciones|Programa\s+de\s+(?:seguimiento\s+y\s+)?vigilancia)", re.I)
_GUION = re.compile(r"^[–—•-]\s*(\S.*)$")
_LETRA = re.compile(r"^\(?([a-hj-z])\)\s+(\S.*)$")  # a) b)… (la i) es de bloque)
_INICIO_ALT = re.compile(r"se\s+resuelven\s+las\s+condiciones|se\s+establecen\s+en\s+los\s+siguientes\s+t[eé]rminos", re.I)
_RESUELVE = re.compile(r"\bresuelve:\s*$", re.I | re.M)  # modificaciones de condiciones
_GENERALES = re.compile(r"^\s*[\divx.()]*\s*Condiciones\s+generales", re.I | re.M)
_VERBO = re.compile(r"\b(?:deber[aá]n?|ser[aá]n?|se\s+\w+|habr[aá]n?|podr[aá]n?|incluir[aá]n?|realizar[aá]n?|presentar[aá]n?)\b", re.I)


def _parrafos(bloque: str) -> list[str]:
    """Reúne las líneas partidas por la cursiva del XML del BOE (nombres de especies, subíndices)."""
    out: list[str] = []
    for linea in bloque.split("\n"):
        l = linea.strip()
        if not l:
            continue
        nuevo = (
            not out
            or _NUM.match(l)
            or _GUION.match(l)
            or _LETRA.match(l)
            or _BLOQUE.match(l)
            or (out[-1][-1:] in ".:;" and l[:1].isupper())
        )
        if nuevo:
            out.append(l)
        else:
            sep = "" if l[:1] in ".,;:)" or out[-1][-1:] in "(" else " "
            out[-1] += sep + l
    return out


def _bloque_de(texto: str) -> str:
    t = texto.lower()
    if "vigilancia" in t or "seguimiento" in t:
        return "pva"
    if "general" in t:
        return "generales"
    return "medidas"


@dataclass
class Condicion:
    num: str
    bloque: str  # generales / medidas / pva
    factor: str  # "Fauna", "Agua"...
    texto: str
    momento: list[str] = field(default_factory=list)
    entregable: bool = False
    destinatarios: list[str] = field(default_factory=list)
    periodicidad: str = ""
    duracion: str = ""
    temas: list[str] = field(default_factory=list)


def _cuerpo(texto: str) -> str:
    """El condicionado: de "Condiciones al proyecto" a la fórmula de publicación."""
    ini = list(_INICIO.finditer(texto))
    if ini:
        start = ini[-1].end()
    elif alt := list(_INICIO_ALT.finditer(texto)):
        start = texto.find("\n", alt[-1].end())
    else:
        # Sin frase de entrada: desde el primer epígrafe "Condiciones generales" de la parte resolutiva.
        gen = [m for m in _GENERALES.finditer(texto) if m.start() > len(texto) * 0.3]
        start = gen[0].start() if gen else -1
        if start < 0 and (res := list(_RESUELVE.finditer(texto))):
            start = res[-1].end()
    if start < 0:
        return ""
    cuerpo = texto[start:]
    fin = _FIN.search(cuerpo)
    return cuerpo[: fin.start()] if fin else cuerpo


def _es_epigrafe(p: str) -> bool:
    return len(p) < 110 and not _VERBO.search(p)


def _tipo_marca(p: str) -> str:
    return "num" if _NUM.match(p) else "letra" if _LETRA.match(p) else "guion" if _GUION.match(p) else "libre"


def _marcas(parrafos: list[str]) -> set[str]:
    """Con qué marca señala este documento cada condición (número, letra, guion); a veces mezcla."""
    n = Counter(
        _tipo_marca(p) for p in parrafos
        if not _es_epigrafe(p) and not (_BLOQUE.match(p) and len(p) < 160)
    )
    return {m for m in ("num", "letra", "guion") if n[m] >= 3} or {"libre"}


def trocear(texto: str) -> list[Condicion]:
    parrafos = _parrafos(_cuerpo(texto))
    marcas = _marcas(parrafos)
    conds: list[Condicion] = []
    bloque, factor, prof_factor = "generales", "", 99
    en_lista = False  # tras "…las siguientes modificaciones:", los guiones y letras son del mismo punto
    # Tras un epígrafe numerado ("3.2 Nueva condición a añadir al apartado E.3…"), un párrafo sin marca que
    # no introduce una lista es una condición propia, no la continuación de la anterior.
    tras_epigrafe, num_epigrafe = False, ""
    for i, p in enumerate(parrafos):
        if _BLOQUE.match(p) and len(p) < 160:
            bloque, factor, prof_factor, en_lista = _bloque_de(p), "", 99, False
            continue
        m, l, g = _NUM.match(p), _LETRA.match(p), _GUION.match(p)
        t = _tipo_marca(p)
        siguiente = parrafos[i + 1] if i + 1 < len(parrafos) else ""
        if _es_epigrafe(p) and not en_lista and not (g and _GUION.match(siguiente)):
            # "– Fauna.", "5.2.1 Contaminación acústica.", "Fase de construcción:". Un guion seguido de otro
            # guion es un elemento de lista, no un epígrafe.
            factor = (m.group(2) if m else g.group(1) if g else p).strip().rstrip(".:")
            prof_factor = m.group(1).count(".") if m else 99
            tras_epigrafe, num_epigrafe = True, (m.group(1) if m else num_epigrafe)
            continue
        if t in ("letra", "guion") and en_lista:
            nueva = False
        elif marcas == {"libre"}:
            nueva = t == "libre"
        else:
            nueva = t in marcas or (t == "libre" and tras_epigrafe and not p.endswith(":"))
        if nueva:
            # "5.3.8" ya no cuelga del epígrafe "5.3.7"; un "1." bajo "1.3.1 Agua:" sí.
            if m and "." in m.group(1) and m.group(1).count(".") <= prof_factor < 99:
                factor, prof_factor = "", 99  # 5.3.8 ya no cuelga del epígrafe 5.3.7
            num = m.group(1) if m else l.group(1) if l else (
                num_epigrafe if tras_epigrafe and num_epigrafe else f"[{len(conds) + 1}]")
            tras_epigrafe = False
            cuerpo = (m.group(2) if m else l.group(2) if l else g.group(1) if g else p).strip()
            bl = "pva" if re.search(r"seguimiento|vigilancia", factor, re.I) else bloque
            conds.append(Condicion(num=num, bloque=bl, factor=factor, texto=cuerpo))
            en_lista = cuerpo.endswith(":")
        elif conds:
            conds[-1].texto += "\n" + p
            if t == "libre":
                en_lista = p.endswith(":")
        # Un párrafo suelto antes de la primera condición es una introducción: se descarta.
    for c in conds:
        etiquetar(c)
    return conds


# --- Etiquetas ------------------------------------------------------------------

MOMENTOS = [
    ("proyecto", r"proyecto\s+(?:constructivo|de\s+ejecuci[oó]n|de\s+construcci[oó]n)|antes\s+de\s+(?:obtener\s+)?la\s+autorizaci[oó]n|"
                 r"para\s+solicitar\s+la\s+aprobaci[oó]n|previamente\s+a\s+(?:su\s+)?aprobaci[oó]n"),
    ("antes_obras", r"(?:antes|con\s+(?:car[aá]cter\s+previo|anterioridad)|previamente)\s+(?:al|a\s+la|del|de\s+la|de\s+las)\s+"
                    r"(?:inicio|comienzo|replanteo|ejecuci[oó]n|obras)"),
    ("obras", r"durante\s+(?:la\s+fase\s+de\s+)?(?:las\s+)?(?:obras|construcci[oó]n)|fase\s+de\s+(?:obras|construcci[oó]n)"),
    ("antes_explotacion", r"antes\s+de\s+la\s+puesta\s+en\s+(?:servicio|marcha|funcionamiento)|antes\s+del\s+inicio\s+de\s+la\s+explotaci[oó]n"),
    ("explotacion", r"explotaci[oó]n|funcionamiento\s+del\s+parque|vida\s+[uú]til"),
    ("cese", r"desmantelamiento|cese\s+(?:definitivo\s+)?de\s+la\s+actividad|final(?:izaci[oó]n)?\s+de\s+la\s+vida\s+[uú]til"),
]
MOMENTOS = [(k, re.compile(p, re.I)) for k, p in MOMENTOS]

_ENTREGA = re.compile(
    r"\b(?:presentar|remitir|enviar|entregar|elaborar|redactar|comunicar|trasladar|acreditar|emitir|someter|"
    r"aportar|facilitar|notificar)\w*\b|se\s+(?:emitir|remitir|presentar|enviar|elaborar|comunicar)\w*|"
    r"informes?\s+(?:anual|semestral|trimestral|peri[oó]dic|final|de\s+seguimiento)",
    re.I,
)
_DOCUMENTO = re.compile(
    r"\b(?:informe|programa|proyecto|plan|estudio|memoria|documento|protocolo|an[aá]lisis|resultados|registro|"
    r"cartograf[ií]a|inventario|censo|prospecci[oó]n|propuesta|certificado|acta)s?\b",
    re.I,
)
_DESTINO = re.compile(
    r"(?:al|a\s+la|a\s+los|ante\s+el|ante\s+la|ante\s+los|para\s+(?:su\s+)?(?:aprobaci[oó]n|validaci[oó]n|conformidad)\s+(?:del|de\s+la|por\s+el|por\s+la))\s+"
    r"((?:[oó]rgano|[oó]rganos|Confederaci[oó]n|Direcci[oó]n\s+General|Servicio|Subdirecci[oó]n|Consejer[ií]a|Delegaci[oó]n|"
    r"Agencia|Ayuntamiento|Instituto|Demarcaci[oó]n|Administraci[oó]n|Comunidad|Junta|Gobierno|Departamento)"
    r"[^,.;:()]{0,110})",
    re.I,
)
_PERIODO = re.compile(
    r"\b(anual(?:es|mente)?|semestral(?:es|mente)?|trimestral(?:es|mente)?|mensual(?:es|mente)?|quincenal(?:es|mente)?|"
    r"semanal(?:es|mente)?|cada\s+(?:dos|tres|cuatro|cinco|seis|\d+)\s+(?:a[nñ]os|meses|semanas|d[ií]as))\b",
    re.I,
)
_DURACION = re.compile(
    r"durante\s+(?:al\s+menos\s+|como\s+m[ií]nimo\s+)?(?:los|el)\s+(?:primer(?:os)?\s+)?"
    r"(?:(?:dos|tres|cuatro|cinco|seis|diez|\d+)\s+(?:\(\d+\)\s+)?)?a[nñ]os?\s+(?:de\s+(?:la\s+)?)?(?:explotaci[oó]n|funcionamiento)"
    r"|durante\s+toda\s+la\s+(?:vida\s+[uú]til|fase\s+de\s+explotaci[oó]n|explotaci[oó]n)",
    re.I,
)

TEMAS = {
    "mortalidad": r"cad[aá]ver|colisi[oó]n|mortalidad|siniestralidad|electrocuci|bajas?\s+de\s+(?:aves|fauna)",
    "avifauna": r"avifauna|\baves\b|rapaces|[aá]guila|milano|buitre|alimoche|cern[ií]calo|aguilucho|avutarda|"
                r"s[ií]s[oó]n|ganga|ortega|cig[uü]e[nñ]a|quebrantahuesos|urogallo|halc[oó]n|b[uú]ho|alondra",
    "quiropteros": r"quir[oó]pter|murci[eé]lag",
    "parada": r"parada|detenci[oó]n\s+(?:temporal\s+)?de\s+(?:los\s+)?aerogeneradores|sistemas?\s+de\s+(?:detecci[oó]n|disuasi[oó]n)|"
              r"velocidad\s+de\s+arranque|cut-?in|DTBird|curtailment",
    "compensatoria": r"compensatori",
    "vallado": r"vallad|cerramiento",
    "agua": r"dominio\s+p[uú]blico\s+hidr[aá]ulico|cauces?|Confederaci[oó]n\s+Hidrogr[aá]fica|aguas?\s+(?:superficiales|subterr[aá]neas)",
    "patrimonio": r"arqueol[oó]g|patrimonio\s+cultural|paleontol",
    "flora": r"\bflora\b|bot[aá]nic|h[aá]bitats?\s+de\s+inter[eé]s",
    "ruido": r"ruido|ac[uú]stic",
    "paisaje": r"paisaj",
    "incendios": r"incendio",
    "desmantelamiento": r"desmantelamiento",
}
TEMAS = {k: re.compile(p, re.I) for k, p in TEMAS.items()}
ETIQUETA_TEMA = {
    "mortalidad": "mortalidad de fauna", "avifauna": "aves", "quiropteros": "quirópteros",
    "parada": "parada de aerogeneradores", "compensatoria": "medidas compensatorias", "vallado": "vallado",
    "agua": "agua", "patrimonio": "patrimonio", "flora": "flora y hábitats", "ruido": "ruido",
    "paisaje": "paisaje", "incendios": "incendios", "desmantelamiento": "desmantelamiento",
}


_ORGANO_GENERICO = re.compile(
    r"[oó]rganos?\s+(?:sustantivo|ambiental(?:\s+auton[oó]mico)?|competentes?(?:\s+en\s+(?:materia\s+de\s+)?"
    r"[a-záéíóúñ]+(?:(?:,\s*|\s+y\s+|\s+de\s+)[a-záéíóúñ]+){0,4})?)",
    re.I,
)
_CONECTOR = {"de", "del", "la", "las", "los", "el", "y", "e", "para", "en"}


def _limpia_destino(s: str) -> str:
    """Nombre del organismo, sin el resto de la frase ("al órgano sustantivo haberlo elaborado")."""
    s = re.sub(r"\s+", " ", s).strip()
    g = _ORGANO_GENERICO.match(s)
    if g:
        out = g.group(0)
    else:
        # Nombre propio: palabras con mayúscula o conectores; para en la primera palabra corriente.
        palabras = []
        for w in s.split(" "):
            if w[:1].isupper() or w.lower() in _CONECTOR or not palabras:
                palabras.append(w)
            else:
                break
        while palabras and palabras[-1].lower() in _CONECTOR:
            palabras.pop()
        out = " ".join(palabras)
    return out[:1].upper() + out[1:]


def etiquetar(c: Condicion) -> None:
    t = c.texto
    c.momento = [k for k, p in MOMENTOS if p.search(t)]
    c.entregable = bool(_ENTREGA.search(t) and _DOCUMENTO.search(t))
    vistos = []
    for m in _DESTINO.finditer(t):
        d = _limpia_destino(m.group(1))
        if d and d.lower() not in (v.lower() for v in vistos):
            vistos.append(d)
    c.destinatarios = vistos[:4]
    p = _PERIODO.search(t)
    c.periodicidad = p.group(1).lower() if p else ""
    d = _DURACION.search(t)
    c.duracion = re.sub(r"\s+", " ", d.group(0)) if d else ""
    c.temas = [k for k, p in TEMAS.items() if p.search(c.factor + ". " + t)]
    if c.bloque == "pva" and ("avifauna" in c.temas or "quiropteros" in c.temas) and _PERIODO.search(t):
        c.entregable = True  # los informes periódicos del PVA son lo primero que hay que pedir


# --- Metadatos de la resolución ---------------------------------------------------

_MESES = {m: i for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}
_FECHA_RES = re.compile(r"Resoluci[oó]n\s+de\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", re.I)
_PROYECTO = re.compile(r"[«\"“]([^»\"”]{5,400})[»\"”]")
# "…como órgano sustantivo, y respecto del que Eólica Sierra de Ávila, SL, es promotor" (2026) o
# "…cuyo promotor es Green Capital Power, S.L., respecto de la que…" (2022). Las razones sociales llevan
# comas y puntos ("S.L."), así que el final se reconoce por lo que viene después.
_FIN_NOMBRE = r"(?=,?\s+(?:respecto|y\s+(?:cuyo|el|la|respecto)|siendo|como|que\s)|\.\s+(?:[A-ZÁÉÍÓÚ][a-záéíóú]{2,}|\d)|;|\n|$)"
_PROMOTOR = [
    re.compile(r"(?:remitid[ao]s?|presentad[ao]s?|promovid[ao]s?)\s+por\s+(?:la\s+|el\s+)?(?P<p>(?:(?!\bcomo\b)[^;\n]){3,160}?),?\s+(?:como|en\s+calidad\s+de)\s+promotor", re.I),
    re.compile(r"\bdel?\s+(?:que|cual)\s+(?P<p>[^;\n]{3,120}?),?\s+(?:es|son|act[uú]an?\s+como)\s+(?:el\s+|los\s+)?promotor", re.I),
    re.compile(r"respecto\s+del?\s+(?:que|cual)\s+(?P<p>[^;\n]{3,120}?),?\s+(?:es|act[uú]a\s+como)\s+(?:el\s+)?promotor", re.I),
    re.compile(r"(?:siendo|y\s+es|cuyo)\s+(?:el\s+)?promotor\s+(?:del\s+proyecto\s+)?(?:es\s+)?(?P<p>[^;\n]{3,120}?)" + _FIN_NOMBRE, re.I),
    re.compile(r"(?:El\s+)?promotor\s+(?:del\s+proyecto\s+)?es\s+(?P<p>[^;\n]{3,120}?)" + _FIN_NOMBRE, re.I),
    re.compile(r"a\s+solicitud\s+de\s+(?P<p>[^;\n]{3,120}?),?\s+(?:como|en\s+calidad\s+de)\s+promotor", re.I),
    re.compile(r"promovid[ao]s?\s+por\s+(?:la\s+|el\s+)?(?P<p>[^;\n]{3,120}?)" + _FIN_NOMBRE, re.I),
    # "…es remitida, con fecha 7 de noviembre de 2024, al promotor Biocantaber SL para conocimiento…"
    re.compile(r"\bal\s+promotor,?\s+(?P<p>[A-ZÁÉÍÓÚ][^;\n,]{2,100}?(?:,?\s+S\.?\s?[LA]\.?U?\.?)?)"
               r"(?=,?\s+(?:para|con|a\s+fin|y\s)|[,.;\n])"),
]
# Proyectos de la propia Administración: el mismo organismo es promotor y órgano sustantivo.
_AMBOS_DELANTE = re.compile(
    r"(?:El\s+)?promotor\s+y\s+[oó]rgano\s+sustantivo\s+(?:del\s+proyecto\s+)?(?:es|son)\s+(?:la\s+|el\s+)?(?P<p>[^;\n]{3,160}?)"
    + _FIN_NOMBRE, re.I)
_AMBOS_DETRAS = re.compile(r",?\s+(?:como\s+)?(?:el\s+)?[oó]rgano\s+sustantivo\s+y\s+promotor", re.I)
_COMO_SUSTANTIVO = re.compile(r",?\s+(?:como|es|act[uú]a\s+como|ostenta\s+la\s+condici[oó]n\s+de)\s+(?:el\s+)?(?:promotor(?:es)?\s+y\s+)?[oó]rgano\s+sustantivo", re.I)
_ORGANISMO = re.compile(
    r"(?:Direcci[oó]n\s+General|Subdirecci[oó]n|Secretar[ií]a|Ministerio|Confederaci[oó]n|Consejer[ií]a|"
    r"Delegaci[oó]n|Demarcaci[oó]n|Agencia|Autoridad\s+Portuaria|Entidad|Organismo|ADIF|Puertos\s+del\s+Estado|Instituto)"
)


def _fecha_resolucion(titulo: str) -> str:
    m = _FECHA_RES.search(titulo)
    if not m or m.group(2).lower() not in _MESES:
        return ""
    return date(int(m.group(3)), _MESES[m.group(2).lower()], int(m.group(1))).isoformat()


_PROMOTOR_SOCIEDAD = re.compile(
    r"\b(?:al|el)\s+promotor,?\s+(?:la\s+sociedad\s+)?(?P<p>[A-ZÁÉÍÓÚ][\w&.\- ]{1,80}?,?\s+S\.?\s?[LA]\.?(?:U\.?)?)(?=[\s,.;)])"
)


def _promotor(texto: str) -> str:
    # Primero la cabecera (antecedentes); si no aparece, el resto: en las modificaciones de condiciones el
    # promotor solo se nombra más abajo, al relatar la tramitación.
    # Ahí los patrones generales dan falsos positivos, así que solo vale un nombre con forma societaria.
    for patrones, cab in ((_PROMOTOR, texto[:6000]), ([_PROMOTOR_SOCIEDAD], texto[6000:30000])):
        for p in patrones:
            m = p.search(cab)
            if m:
                nombre = re.sub(r"\s+", " ", m.group("p")).strip(" «»\"")
                return re.sub(r"^(?:la|el|los|las)\s+", "", nombre)
    return ""


def _sustantivo(texto: str) -> str:
    m = _AMBOS_DELANTE.search(texto[:8000])
    if m:
        return re.sub(r"\s+", " ", m.group("p")).strip(" ,")
    m = _COMO_SUSTANTIVO.search(texto[:8000]) or _AMBOS_DETRAS.search(texto[:8000])
    if not m:
        return ""
    ventana = texto[max(0, m.start() - 260):m.start()]
    orgs = list(_ORGANISMO.finditer(ventana))
    if not orgs:
        return ""
    # El último organismo que se nombra antes de "como órgano sustantivo" es el órgano, pero su nombre
    # puede contener otro ("Dirección General de Política Energética y Minas del Ministerio…").
    k = orgs[-1].start()
    for o in reversed(orgs[:-1]):
        if re.fullmatch(r"[^.;«»]*?\s(?:del|de\s+la|de\s+los)\s+", ventana[o.end():k]):
            k = o.start()
    return re.sub(r"\s+", " ", ventana[k:]).strip(" ,")


# Una sola forma por provincia para poder filtrar: el BOE escribe "Alacant", "Alicante" o "Alicante/Alacant".
_PROV_SINONIMOS = {
    "Araba": "Álava", "Alacant": "Alicante", "Illes Balears": "Islas Baleares", "Vizcaya": "Bizkaia",
    "Guipúzcoa": "Gipuzkoa", "Castelló": "Castellón", "València": "Valencia", "La Coruña": "A Coruña",
    "Orense": "Ourense", "Gerona": "Girona", "Lérida": "Lleida",
}
_PROV_TITULO = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(p) for p in sorted(set(extract.PROVINCIAS) | set(_PROV_SINONIMOS), key=len, reverse=True))
    + r")(?!\w|\s+de\s+[A-ZÁÉÍÓÚ])", re.I)  # "Valencia de Alcántara" es un municipio de Cáceres


def _provincias(titulo: str) -> list[str]:
    canon = {extract._strip_accents(p.lower()): p for p in set(extract.PROVINCIAS) | set(_PROV_SINONIMOS)}
    provs = set()
    for m in _PROV_TITULO.finditer(titulo):
        p = canon[extract._strip_accents(m.group(1).lower())]
        provs.add(_PROV_SINONIMOS.get(p, p))
    return sorted(provs)


def _suma_anos(d: date, anos: int) -> date:
    try:
        return d.replace(year=d.year + anos)
    except ValueError:  # 29 de febrero
        return d.replace(year=d.year + anos, day=28)


def ficha(a: Anuncio) -> dict:
    """Todo lo que publicamos de una resolución: metadatos, vigencia y condicionado etiquetado."""
    texto = a.texto or boe.fetch_texto(a)
    tipo = tipo_de(a.titulo)
    a.texto = texto
    extract.clasificar(a)
    extract.extraer_datos(a)
    s_clave, s_etiqueta = seguimiento.sentido(a, "dia" if tipo == "modificacion" else tipo)
    if tipo == "dia" and s_clave == "sin_eia":
        tipo = "iia"  # titulada "declaración" pero resuelve una evaluación simplificada
    # Algunas resoluciones agrupan proyectos: desfavorable para el parque eólico y favorable, con
    # condiciones, para la batería o la línea que lo acompañan.
    if s_clave == "desfavorable" and _FAVORABLE_PARTE.search(seguimiento._fallo(texto)[:1500]):
        s_clave, s_etiqueta = "parcial", "desfavorable en parte; con condiciones para el resto"
    pub = date.fromisoformat(a.fecha)
    proyecto = _PROYECTO.search(a.titulo)
    conds = trocear(texto) if tipo in ("dia", "modificacion") else []
    sustantivo = _sustantivo(texto)
    promotor = _promotor(texto)
    if not promotor and (_AMBOS_DELANTE.search(texto[:8000]) or _AMBOS_DETRAS.search(texto[:8000])):
        promotor = sustantivo
    refs = boe.fetch_referencias(a)
    f = {
        "identificador": a.identificador,
        "tipo": tipo,
        "fecha_publicacion": a.fecha,
        "fecha_resolucion": _fecha_resolucion(a.titulo),
        "titulo": a.titulo,
        "proyecto": proyecto.group(1).strip() if proyecto else "",
        "promotor": promotor,
        "organo_sustantivo": sustantivo,
        "provincias": _provincias(a.titulo) or sorted({_PROV_SINONIMOS.get(p, p) for p in a.provincias}),
        "categoria": a.categoria,
        "sentido": s_clave,
        "sentido_etiqueta": s_etiqueta,
        "url_html": a.url_html,
        "url_pdf": a.url_pdf,
        "anulada": refs.get("anulada", False),
        "correcciones": [p["referencia"] for p in refs.get("posteriores", [])
                         if re.search(r"correc|corrig", p["relacion"], re.I)],
        "condiciones": [c.__dict__ for c in conds],
    }
    if tipo == "modificacion":
        f["modifica_a"] = {"fecha_resolucion": _fecha_original(a.titulo, texto), "identificador": ""}
    if tipo in ("dia", "iia") and (s_clave in seguimiento.SENTIDOS_VERDES or s_clave == "parcial"):
        f["vigencia_hasta"] = _suma_anos(pub, VIGENCIA_ANOS).isoformat()
        f["vigencia_max_con_prorroga"] = _suma_anos(pub, VIGENCIA_ANOS + PRORROGA_ANOS).isoformat()
    return f


def resumen(f: dict) -> dict:
    """Fila del índice: lo necesario para la tabla, sin el texto de las condiciones."""
    cs = f["condiciones"]
    temas = sorted({t for c in cs for t in c["temas"]})
    return {
        k: f.get(k) for k in (
            "identificador", "tipo", "fecha_publicacion", "fecha_resolucion", "proyecto", "promotor",
            "organo_sustantivo", "provincias", "categoria", "sentido", "sentido_etiqueta",
            "url_html", "vigencia_hasta", "vigencia_max_con_prorroga",
        )
    } | {
        "n_condiciones": len(cs),
        "n_entregables": sum(c["entregable"] for c in cs),
        "seguimiento_mortalidad": any("mortalidad" in c["temas"] and c["bloque"] == "pva" for c in cs),
        "temas": temas,
        "modificada_por": f.get("modificada_por", []),
        "modifica_a": f.get("modifica_a", ""),
    }


# --- Enlaces entre resoluciones -------------------------------------------------

# "…por la que se modifica la de 4 de noviembre de 2019, …" / "…de modificación de condiciones de la
# Resolución de 7 de noviembre de 2005, …". La primera fecha del título es la de la propia modificación.
_FECHA_ORIGINAL = re.compile(
    r"(?:modifica[n]?\s+(?:la|condicionados\s+de\s+la\s+Resoluci[oó]n)\s+de|condiciones\s+de\s+la\s+Resoluci[oó]n\s+de)"
    r"\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", re.I)


def _clave_proyecto(p: str) -> frozenset:
    """Palabras significativas del nombre del proyecto, para casar modificaciones con su DIA."""
    return frozenset(w for w in re.findall(r"[a-záéíóúñü0-9]{4,}", p.lower())
                     if w not in {"proyecto", "infraestructura", "infraestructuras", "evacuación", "provincia",
                                  "términos", "municipales", "potencia", "instalada"})


def _fecha_original(titulo: str, texto: str) -> str:
    """Fecha de la DIA que una modificación cambia: en el título o, si no, en el primer antecedente
    ("…se aprueba por Resolución de 14 de mayo de 2021…")."""
    m = _FECHA_ORIGINAL.search(titulo) or _FECHA_RES.search(texto[:2500])
    if not m or m.group(2).lower() not in _MESES:
        return ""
    return date(int(m.group(3)), _MESES[m.group(2).lower()], int(m.group(1))).isoformat()


def enlazar(fichas: list[dict]) -> None:
    """Rellena `modifica_a` en cada modificación y `modificada_por` en la DIA que modifica (si la tenemos)."""
    dias = [f for f in fichas if f["tipo"] == "dia"]
    for d in dias:
        d["modificada_por"] = []
    for f in fichas:
        if f["tipo"] != "modificacion":
            continue
        fecha = f.get("modifica_a", {}).get("fecha_resolucion", "")
        clave = _clave_proyecto(f["proyecto"])
        mejor, puntos = None, 0.0
        for d in dias:
            if fecha and d["fecha_resolucion"] != fecha:
                continue
            otra = _clave_proyecto(d["proyecto"])
            if not clave or not otra:
                continue
            p = len(clave & otra) / len(clave | otra)
            if p > puntos:
                mejor, puntos = d, p
        f["modifica_a"] = {"fecha_resolucion": fecha, "identificador": ""}
        if mejor and puntos >= 0.5:
            f["modifica_a"]["identificador"] = mejor["identificador"]
            mejor["modificada_por"].append(f["identificador"])


# --- Solicitud de acceso a la información ambiental ----------------------------------

ORGANO_AMBIENTAL = ("Dirección General de Calidad y Evaluación Ambiental, Ministerio para la Transición "
                    "Ecológica y el Reto Demográfico")
_FALTA_SUSTANTIVO = "[ÓRGANO SUSTANTIVO: figura en los antecedentes de la resolución]"


def _fecha_larga(iso: str) -> str:
    if not iso:
        return "[fecha]"
    d = date.fromisoformat(iso)
    return f"{d.day} de {list(_MESES)[d.month - 1]} de {d.year}"


def _extracto(texto: str, n: int = 260) -> str:
    t = re.sub(r"\s+", " ", texto).strip()
    if len(t) <= n:
        return t
    corte = t.rfind(" ", 0, n)
    return t[: corte if corte > 0 else n].rstrip(" ,;:") + "…"


def _cita(f: dict) -> str:
    que = {"iia": "se formula informe de impacto ambiental",
           "modificacion": "se modifican las condiciones de la declaración de impacto ambiental"}.get(
        f["tipo"], "se formula declaración de impacto ambiental")
    return (f"la Resolución de {_fecha_larga(f.get('fecha_resolucion'))} de la Dirección General de Calidad y "
            f"Evaluación Ambiental, publicada en el «Boletín Oficial del Estado» el "
            f"{_fecha_larga(f['fecha_publicacion'])} ({f['identificador']}), por la que {que} del proyecto "
            f"«{f.get('proyecto') or '[proyecto]'}»")


def solicitud(f: dict, destino: str = "sustantivo") -> str:
    """Texto de una solicitud de información ambiental (Ley 27/2006) sobre el cumplimiento de una DIA.

    `destino`: "sustantivo" (quien autoriza el proyecto y vigila el condicionado, art. 52 de la Ley 21/2013)
    o "ambiental" (la Dirección General que formuló la DIA: vigencia, prórrogas, modificaciones).
    Los datos del solicitante quedan entre corchetes: los pone quien firma.
    """
    promotor = f.get("promotor") or "[PROMOTOR]"
    sustantivo = f.get("organo_sustantivo") or _FALTA_SUSTANTIVO
    dirigido = sustantivo if destino == "sustantivo" else ORGANO_AMBIENTAL
    entregables = [c for c in f.get("condiciones", []) if c["entregable"]]
    L = [
        f"A la atención de: {dirigido}",
        "",
        "SOLICITUD DE ACCESO A INFORMACIÓN AMBIENTAL",
        "(Ley 27/2006, de 18 de julio, por la que se regulan los derechos de acceso a la información, de "
        "participación pública y de acceso a la justicia en materia de medio ambiente)",
        "",
        "[NOMBRE Y APELLIDOS], con [DNI/NIE] y correo electrónico a efectos de notificaciones [CORREO], "
        "comparece y",
        "",
        "EXPONE",
        "",
        f"1. Que mediante {_cita(f)}, promovido por {promotor}, se establecieron las condiciones ambientales "
        "a las que queda sujeto el proyecto, incluido su programa de vigilancia ambiental.",
    ]
    if destino == "sustantivo":
        L += [
            "",
            "2. Que, de acuerdo con el artículo 52 de la Ley 21/2013, de 9 de diciembre, de evaluación "
            "ambiental, corresponde al órgano sustantivo el seguimiento del cumplimiento de la declaración, y "
            "que el promotor debe remitirle informes de seguimiento con un listado de comprobación de las "
            "medidas del programa de vigilancia ambiental, programa y listado que han de hacerse públicos en "
            "su sede electrónica.",
        ]
        if entregables:
            L += ["", "3. Que el condicionado obliga al promotor a elaborar o remitir, entre otros, los siguientes "
                  "documentos:"]
            for c in entregables[:25]:
                cab = f"condición {c['num']}" + (f" ({c['factor']})" if c.get("factor") else "")
                L.append(f"   – {cab}: «{_extracto(c['texto'])}»")
            if len(entregables) > 25:
                L.append(f"   – y otras {len(entregables) - 25} condiciones con obligación documental.")
    else:
        L += [
            "",
            "2. Que, según el artículo 43 de la Ley 21/2013, la declaración pierde su vigencia si no se ha "
            "comenzado la ejecución del proyecto en el plazo de cuatro años desde su publicación, salvo "
            "prórroga acordada por el órgano ambiental.",
        ]
    L += ["", "SOLICITA", "",
          "Que, al amparo de los artículos 3.1 y 10 de la Ley 27/2006, se le facilite en formato electrónico "
          "la siguiente información ambiental relativa a dicho proyecto:", ""]
    if destino == "sustantivo":
        pide = [
            "Si se ha otorgado la autorización o aprobación del proyecto y, en su caso, la fecha y la "
            "referencia de la resolución.",
            "Si consta el inicio de la ejecución del proyecto y en qué fecha.",
            "Los informes de seguimiento del cumplimiento de la declaración remitidos por el promotor "
            "(artículo 52.2 de la Ley 21/2013), con sus listados de comprobación del programa de vigilancia "
            "ambiental.",
        ]
        if entregables:
            pide.append("Los documentos enumerados en el expositivo 3 que se hayan presentado, con su fecha de "
                        "entrada, o, en su defecto, indicación de que no constan.")
        if any("mortalidad" in c["temas"] for c in f.get("condiciones", [])):
            pide.append("Los datos del seguimiento de mortalidad de fauna (especie, fecha, localización y "
                        "elemento del proyecto de cada ejemplar hallado) y los informes periódicos en que se "
                        "hayan analizado.")
        pide.append("Las actuaciones de comprobación, requerimientos o procedimientos sancionadores "
                    "relacionados con el cumplimiento del condicionado.")
    else:
        pide = [
            "Si el promotor ha comunicado o consta de otro modo el comienzo de la ejecución del proyecto.",
            "Si se ha solicitado o acordado la prórroga de la vigencia de la declaración (artículo 43 de la "
            "Ley 21/2013) y, en su caso, la resolución correspondiente.",
            "Si se ha solicitado la modificación de las condiciones de la declaración (artículo 44) y en qué "
            "estado se encuentra.",
            "Las comunicaciones recibidas del órgano sustantivo o de terceros sobre el cumplimiento del "
            "condicionado.",
        ]
    L += [f"{i}. {p}" for i, p in enumerate(pide, 1)]
    L += ["",
          "Que la información se facilite en el plazo de un mes previsto en el artículo 10.2.c) de la Ley "
          "27/2006, o en el de dos meses si su volumen y complejidad lo justifican, notificándose en ese "
          "caso la ampliación y sus razones; y que cualquier denegación, total o parcial, sea motivada con "
          "indicación de los recursos procedentes (artículos 13 y 20).",
          "", "En [LUGAR], a [FECHA].", "", "Fdo.: [NOMBRE Y APELLIDOS]"]
    return "\n".join(L)


# --- Base abierta ------------------------------------------------------------

def _con_solicitudes(f: dict) -> dict:
    if (f["tipo"] in ("dia", "modificacion") and f["sentido"] in ("condicionada", "parcial")) \
            or (f["tipo"] == "iia" and f["sentido"] == "sin_eia"):
        f["solicitudes"] = {"sustantivo": solicitud(f, "sustantivo"), "ambiental": solicitud(f, "ambiental")}
    return f


def cargar() -> dict[str, dict]:
    if not DATOS_DIR.exists():
        return {}
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in DATOS_DIR.glob("BOE-*.json")}


def guardar(fichas: dict[str, dict]) -> None:
    DATOS_DIR.mkdir(parents=True, exist_ok=True)
    lista = sorted(fichas.values(), key=lambda f: f["fecha_publicacion"], reverse=True)
    enlazar(lista)
    for f in lista:
        _con_solicitudes(f)
        ruta = DATOS_DIR / f"{f['identificador']}.json"
        nuevo = json.dumps(f, ensure_ascii=False, separators=(",", ":"))
        if not ruta.exists() or ruta.read_text(encoding="utf-8") != nuevo:
            ruta.write_text(nuevo, encoding="utf-8")
    INDICE_PATH.write_text(
        json.dumps({"generado": date.today().isoformat(), "fichas": [resumen(f) for f in lista]},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def actualizar(dias: list[date], aviso=lambda s: None) -> tuple[dict[str, dict], int]:
    """Añade a la base las resoluciones publicadas en `dias`. Devuelve la base y cuántas eran nuevas."""
    fichas = cargar()
    nuevas = 0
    for a in candidatos(dias, aviso):
        if a.identificador in fichas:
            continue
        try:
            fichas[a.identificador] = ficha(a)
            nuevas += 1
        except Exception as e:  # noqa: BLE001 - una resolución mal formada no para las demás
            aviso(f"{a.identificador}: {e}")
    guardar(fichas)
    return fichas, nuevas
