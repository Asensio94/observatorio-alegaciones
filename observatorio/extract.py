"""Clasificación de anuncios y extracción de datos (reglas + regex).

La extracción con LLM se añadirá como capa opcional; primero una base determinista
que funcione con el lenguaje muy formulario de los anuncios oficiales.
"""

from __future__ import annotations

import re
import unicodedata

from .boe import Anuncio

# --- Clasificación -----------------------------------------------------------

INFO_PUBLICA = re.compile(r"informaci[oó]n\s+p[uú]blica|tr[aá]mite\s+de\s+(?:IP|audiencia)", re.I)

TRAMITE_AMBIENTAL = re.compile(
    r"impacto\s+ambiental|evaluaci[oó]n\s+(?:de\s+impacto\s+)?ambiental|EsIA|estudio\s+ambiental|"
    r"declaraci[oó]n\s+de\s+impacto|autorizaci[oó]n\s+ambiental|Ley\s+21/2013",
    re.I,
)

CATEGORIAS: list[tuple[str, re.Pattern, int]] = [
    # (categoria, patrón, prioridad base 1-5)
    ("eolica", re.compile(r"e[oó]lic|aerogenerador", re.I), 5),
    ("fotovoltaica", re.compile(r"fotovoltaic|solar|placas?\s+solares|planta\s+FV", re.I), 5),
    ("hidrogeno_baterias", re.compile(r"hidr[oó]geno|electroliz|almacenamiento\s+(?:de\s+)?energ|bater[ií]as|BESS", re.I), 4),
    ("red_electrica", re.compile(r"l[ií]nea\s+(?:a[eé]rea|el[eé]ctrica|de\s+(?:alta|media)\s+tensi[oó]n)|subestaci[oó]n|\d+\s*kV|red\s+de\s+transporte", re.I), 4),
    ("hidrocarburos_gas", re.compile(r"gasoducto|oleoducto|hidrocarburo|gas\s+natural|regasificad", re.I), 4),
    ("mineria", re.compile(r"miner[ií]a|explotaci[oó]n\s+minera|concesi[oó]n\s+(?:de\s+explotaci[oó]n|minera)|cantera|permiso\s+de\s+investigaci[oó]n", re.I), 4),
    ("transporte", re.compile(r"autov[ií]a|autopista|carretera|ferrocarril|l[ií]nea\s+de\s+alta\s+velocidad|aeropuerto|variante\s+de", re.I), 4),
    ("puertos_costas", re.compile(r"autoridad\s+portuaria|puerto\s+de|dominio\s+p[uú]blico\s+mar[ií]timo|costas?\b|dragado", re.I), 3),
    ("hidraulica", re.compile(r"presa|embalse|trasvase|encauzamiento|central\s+hidroel[eé]ctrica|desaladora|regad[ií]o|regable", re.I), 3),
    ("agua_concesion", re.compile(r"confederaci[oó]n\s+hidrogr[aá]fica|aprovechamiento\s+de\s+aguas|concesi[oó]n\s+de\s+aguas|vertido", re.I), 1),
    ("urbanismo_industria", re.compile(r"urbaniz|pol[ií]gono\s+industrial|planta\s+(?:industrial|de\s+tratamiento)|incineradora|vertedero|residuos", re.I), 3),
]


def clasificar(a: Anuncio) -> Anuncio:
    """Rellena categoria, prioridad y tramite_ambiental a partir del título (y texto si existe)."""
    base = a.titulo + "\n" + a.texto[:4000]
    a.tramite_ambiental = bool(TRAMITE_AMBIENTAL.search(base))
    a.categoria = "otros"
    a.prioridad = 0
    for cat, pat, prio in CATEGORIAS:
        if pat.search(a.titulo):
            a.categoria = cat
            a.prioridad = prio
            break
    if a.tramite_ambiental:
        a.prioridad = max(a.prioridad, 3) + 1
    if not INFO_PUBLICA.search(a.titulo):
        a.prioridad = max(a.prioridad - 2, 0)
    return a


def es_candidato(a: Anuncio) -> bool:
    """Filtro grueso sobre el título: anuncios de información pública con posible afección ambiental."""
    if not INFO_PUBLICA.search(a.titulo):
        return False
    if TRAMITE_AMBIENTAL.search(a.titulo):
        return True
    for cat, pat, prio in CATEGORIAS:
        if prio >= 3 and pat.search(a.titulo):
            return True
    return False


# --- Extracción --------------------------------------------------------------

def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


PROVINCIAS = [
    "A Coruña", "Álava", "Araba", "Albacete", "Alicante", "Alacant", "Almería", "Asturias", "Ávila", "Badajoz",
    "Illes Balears", "Islas Baleares", "Barcelona", "Bizkaia", "Vizcaya", "Burgos", "Cáceres", "Cádiz", "Cantabria",
    "Castellón", "Castelló", "Ciudad Real", "Córdoba", "Cuenca", "Gipuzkoa", "Guipúzcoa", "Girona", "Granada",
    "Guadalajara", "Huelva", "Huesca", "Jaén", "La Rioja", "Las Palmas", "León", "Lleida", "Lugo", "Madrid", "Málaga",
    "Murcia", "Navarra", "Ourense", "Palencia", "Pontevedra", "Salamanca", "Santa Cruz de Tenerife", "Segovia",
    "Sevilla", "Soria", "Tarragona", "Teruel", "Toledo", "Valencia", "València", "Valladolid", "Zamora", "Zaragoza",
    "Ceuta", "Melilla",
]
_PROV_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in sorted(PROVINCIAS, key=len, reverse=True)) + r")\b", re.I)
_PROV_CANON = {_strip_accents(p.lower()): p for p in PROVINCIAS}

# Caracteres válidos en un nombre de municipio (incluye gallego, catalán, euskera)
_NOM = r"[A-Za-zÁÉÍÓÚÑÀÈÒÇÜÏáéíóúñàèòçüïl'’\-\.\s/,]"

# Fórmulas: "términos municipales de A, B y C", "T.M. de A", "T.M.: A", "T.M. ARNEDO (LA RIOJA)",
# "Término Municipal: EL BURGO DE EBRO", "Término Municipal y Provincia: A, B y C (Lugo); D (Ourense)"
_TM_RE = re.compile(
    r"(?:t[eé]rminos?\s+municipal(?:es)?(?:\s+y\s+provincia)?|\bt\.?\s*m\.?|\btt\.?\s*mm\.?|\bmunicipios?)"
    r"\s*(?::|\s+de\s+|\s+)"
    r"(?P<lista>" + _NOM + r"{3,220}?)"
    r"(?=\s*(?:\(|,?\s*(?:en\s+la\s+|de\s+la\s+)?provincia|\.\s|\.$|;|\n|$|,\s*pertenecientes|\s+pertenecientes|\s+y\s+(?:se|uno|en\s+la)\b|\s+con\s+un|\s+para\b|\s+en\s+la\s+(?:provincia|comarca|comunidad|isla)|\s+aprobado|\s+que\b|\s+conforme|\s+donde|\s+cuyo))",
    re.I,
)
_STOP_WORDS = {"la", "el", "los", "las", "de", "del", "provincia", "en", "y", "e", "i", "provincia y", "municipal"}
_BASURA = re.compile(
    r"^(?:y|e|i|de|del|en)\s+|^[a-záéíóúñ]+\s+de\s+(?=[A-ZÁÉÍÓÚÑ])|\s+(?:y|e|i)$|\s+pertenecientes.*$|\s+(?:en|de)\s+la\s+provincia.*$",
)
_PUERTO_RE = re.compile(r"(?:[Pp]uerto|Autoridad\s+Portuaria)\s+de\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de|del|la)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+|\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)")


def _titlecase(s: str) -> str:
    """Convierte 'EL BURGO DE EBRO' → 'El Burgo de Ebro' respetando partículas."""
    if s != s.upper():
        return s
    minus = {"de", "del", "la", "las", "los", "el", "y", "e", "i", "a", "o", "os", "as", "da", "do", "das", "dos", "d'", "l'"}
    out = []
    for i, w in enumerate(s.lower().split()):
        out.append(w if (w in minus and i > 0) else w[:1].upper() + w[1:])
    return " ".join(out)


def _split_lista(lista: str) -> list[str]:
    lista = re.sub(r"\s+", " ", lista).strip(" ,.;:")
    partes = re.split(r"\s*[,;]\s*|\s+(?:y|e|i)\s+(?:de\s+)?(?=[A-ZÁÉÍÓÚÑ])", lista)
    out: list[str] = []
    for p in partes:
        p = _BASURA.sub("", p.strip(" ,.;:"))
        p = _BASURA.sub("", p).strip(" ,.;:")
        if not p or len(p) < 3 or _strip_accents(p.lower()) in _STOP_WORDS:
            continue
        if len(p.split()) > 6 or not p[0].isupper():
            continue
        out.append(_titlecase(p))
    return out


def extraer_municipios(titulo: str, texto: str) -> tuple[list[str], list[str]]:
    """Devuelve (municipios, provincias). Las provincias se toman del título si aparecen ahí
    (evita capturar la dirección del promotor en Madrid); si no, del texto."""
    base = titulo + "\n" + texto
    munis: list[str] = []
    for m in _TM_RE.finditer(base):
        for x in _split_lista(m.group("lista")):
            if x not in munis and _strip_accents(x.lower()) not in {"provincia"}:
                munis.append(x)

    def _provs(s: str) -> list[str]:
        out: list[str] = []
        for m in _PROV_RE.finditer(s):
            p = _PROV_CANON.get(_strip_accents(m.group(1).lower()), m.group(1))
            if p not in out:
                out.append(p)
        return out

    if not munis:
        # Concesiones portuarias: "Puerto de Santander" → municipio Santander
        for m in _PUERTO_RE.finditer(base):
            x = m.group(1)
            if _strip_accents(x.lower()) in _PROV_CANON or x.lower() in {"baleares", "canarias", "interés", "titularidad", "refugio"}:
                continue  # autoridades portuarias de ámbito provincial/autonómico: no hay municipio
            if x not in munis:
                munis.append(x)
    provs = _provs(titulo)
    if not provs:
        # Zona de "Emplazamiento"/"Término municipal" del texto, no las direcciones postales
        zona = " ".join(m.group(0) for m in re.finditer(r".{0,40}(?:t[eé]rmino|municipi|emplazamiento|provincia de).{0,160}", texto, re.I))
        provs = _provs(zona) or _provs(texto[:3000])
    return munis[:40], provs[:6]


_NUM_PALABRA = {
    "un": 1, "uno": 1, "una": 1, "diez": 10, "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40,
    "cuarenta y cinco": 45, "dos": 2, "tres": 3,
}
_PLAZO_RE = re.compile(
    r"plazo\s+de\s+(?P<n>\d{1,3}|un|uno|una|dos|tres|diez|quince|veinte|treinta|cuarenta y cinco|cuarenta)"
    r"\s*(?:\(\s*(?P<n2>\d{1,3})\s*\))?\s*(?P<u>d[ií]as|mes(?:es)?)",
    re.I,
)
_MW_RE = re.compile(r"(\d{1,4}(?:[.,]\d{1,3})?)\s*MW\b", re.I)
_PROMOTOR_RE = re.compile(
    r"(?:promotor|peticionario|solicitante|titular)\s*[:\-]\s*(?P<p>[^\n;]{3,140}?)"
    r"(?=,?\s+con\s+(?:CIF|NIF|domicilio)|,\s+(?:CIF|NIF|con)\b|\s+y\s+CIF|\n|$|\.\s+[A-Z])",
    re.I,
)
_EXPEDIENTE_RE = re.compile(
    r"\b(?:referencia\s+del\s+expediente|n[úu]mero\s+de\s+expediente|expediente|expte\.?|exp\.)\s*"
    r"(?:n[úu]m(?:ero)?\.?|nº|n\.º|n°)?\s*[:\-]?\s*(?P<e>[A-Z0-9][A-Z0-9/\-\._]{3,40}\d[A-Z0-9/\-\._]*|[A-Z0-9/\-\._]*\d[A-Z0-9/\-\._]{3,40})",
    re.I,
)


def extraer_datos(a: Anuncio) -> Anuncio:
    munis, provs = extraer_municipios(a.titulo, a.texto)
    a.municipios = munis
    a.provincias = provs
    for m in _PLAZO_RE.finditer(a.texto):
        n_raw = (m.group("n2") or m.group("n")).lower()
        n = int(n_raw) if n_raw.isdigit() else _NUM_PALABRA.get(n_raw)
        if n is None:
            continue
        if m.group("u").lower().startswith("mes"):
            n *= 30
        # Ignora plazos de concesión (años) y plazos absurdos
        if 5 <= n <= 90:
            a.plazo_dias = n
            break
    mws = []
    for x in _MW_RE.findall(a.titulo + "\n" + a.texto):
        try:
            mws.append(float(x.replace(".", "").replace(",", ".")) if "," in x else float(x))
        except ValueError:
            pass
    if mws:
        a.potencia_mw = max(mws)
    m = _PROMOTOR_RE.search(a.texto)
    if m:
        a.promotor = m.group("p").strip(" ,.")
    m = _EXPEDIENTE_RE.search(a.titulo) or _EXPEDIENTE_RE.search(a.texto)
    if m:
        a.expediente = m.group("e").strip(" .,")
    return a
