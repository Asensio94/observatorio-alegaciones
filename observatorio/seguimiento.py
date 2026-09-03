"""Seguimiento de expedientes: detecta en los boletines las resoluciones que cierran un trámite y las
empareja con los anuncios de información pública ya fichados.

Por qué funciona: la información pública y su resolución se publican en el mismo boletín. El artículo 41
de la Ley 21/2013 obliga a publicar la declaración de impacto ambiental en el boletín oficial
correspondiente, y las autorizaciones administrativas de instalaciones eléctricas se publican por el
artículo 125 del Real Decreto 1955/2000. Así que basta seguir leyendo lo que ya se lee:

- BOE, sección III (Otras disposiciones): resoluciones de la Dirección General de Política Energética y
  Minas y de la Dirección General de Calidad y Evaluación Ambiental.
- BOC de Cantabria, sección 7.2 (Medio Ambiente y Energía): resoluciones que formulan la declaración o el
  informe de impacto ambiental y las autorizaciones administrativas previas y de construcción.

El emparejamiento es por puntos (expediente, promotor, municipios, categoría y palabras distintivas del
título). Solo se da por firme a partir de UMBRAL_FIRME; por debajo se publica como sugerencia, porque un
emparejamiento falso sería peor que ninguno.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from . import boc_cantabria, boe, extract
from .boe import Anuncio

# --- Detección ---------------------------------------------------------------

# Verbo resolutorio: distingue "Resolución ... por la que se formula la DIA" de "Información pública del
# expediente ... y declaración de impacto ambiental", que es la apertura del plazo y ya la detecta extract.
_RESUELVE = re.compile(
    r"resoluci[oó]n|acuerdo\s+de\s+la\s+comisi[oó]n|se\s+(?:formula|otorga|concede|deniega|desestima|estima|"
    r"aprueba|declara|autoriza|archiva|acuerda|hace\s+p[uú]blic|resuelve)",
    re.I,
)

# Materia: sin esto entraría media sección III del BOE (subvenciones, convenios, homologaciones).
_MATERIA = re.compile(
    r"impacto\s+ambiental|evaluaci[oó]n\s+ambiental|autorizaci[oó]n\s+ambiental|"
    r"autorizaci[oó]n\s+administrativa(?:\s+(?:previa|de\s+construcci[oó]n))?|"
    r"utilidad\s+p[uú]blica|declaraci[oó]n\s+responsable\s+ambiental|Ley\s+21/2013",
    re.I,
)

# Tipos, en orden de especificidad: manda el primero que casa.
TIPOS: list[tuple[str, str, re.Pattern]] = [
    ("dia", "Declaración de impacto ambiental", re.compile(r"declaraci[oó]n\s+de\s+impacto\s+ambiental|\bDIA\b")),
    ("iia", "Informe de impacto ambiental", re.compile(r"informe\s+de\s+impacto\s+ambiental|\bIIA\b", re.I)),
    ("ambiental_otro", "Resolución ambiental", re.compile(r"evaluaci[oó]n\s+ambiental|autorizaci[oó]n\s+ambiental\s+integrada", re.I)),
    ("autorizacion", "Autorización administrativa", re.compile(r"autorizaci[oó]n\s+administrativa|aprobaci[oó]n\s+del\s+proyecto|utilidad\s+p[uú]blica", re.I)),
]

# Sentido del fallo. Se lee primero en el título, porque el cuerpo de estas resoluciones cita las
# declaraciones de impacto ambiental de otros proyectos y repite el vocabulario de todas las
# alternativas evaluadas: buscar "favorable" o "desfavorable" a secas en el texto clasifica mal.
_NEGATIVO = re.compile(r"se\s+deniega|se\s+desestima|denegar\b|desestimar\b|desfavorable", re.I)
_POSITIVO = re.compile(
    r"se\s+otorga|otorgar\b|se\s+concede|conceder\b|se\s+autoriza|autorizar\b|favorable|"
    r"se\s+declara(?:n)?\s+(?:en\s+concreto\s+)?la\s+utilidad\s+p[uú]blica|"
    r"declaraci[oó]n\s+(?:en\s+concreto\s+)?de\s+utilidad\s+p[uú]blica",
    re.I,
)
_ARCHIVO = re.compile(
    r"desistimiento|caducidad\s+d[eo]l?\s+(?:expediente|procedimiento|solicitud)|se\s+archiva|archivo\s+d[eo]l?\s+expediente",
    re.I,
)
# Fallos propios de la evaluación ambiental. Una declaración de impacto ambiental del Estado
# normalmente no dice "favorable": se formula con condiciones, y solo se califica cuando es negativa.
_AMB_DESFAVORABLE = re.compile(
    r"(?:declaraci[oó]n|informe)\s+de\s+impacto\s+ambiental\s+desfavorable|(?:formula|formular|emitir)[^.]{0,70}desfavorable",
    re.I,
)
_AMB_A_ORDINARIA = re.compile(
    r"deb(?:e|er[aá])\s+someterse\s+a\s+(?:una\s+)?evaluaci[oó]n\s+de\s+impacto\s+ambiental\s+ordinaria|"
    r"someterse\s+al\s+procedimiento\s+de\s+evaluaci[oó]n\s+de\s+impacto\s+ambiental\s+ordinaria",
    re.I,
)
_AMB_SIN_EFECTOS = re.compile(
    r"no\s+(?:se\s+prev[eé]n|es\s+previsible|resulta\s+previsible|se\s+espera[n]?)[^.]{0,90}efectos\s+"
    r"(?:adversos\s+)?significativos|no\s+tiene\s+efectos\s+(?:adversos\s+)?significativos",
    re.I,
)
# Sentidos que dejan al proyecto en condiciones de seguir adelante, y los que lo frenan.
SENTIDOS_VERDES = ("favorable", "condicionada", "sin_eia")
SENTIDOS_ROJOS = ("desfavorable", "denegada", "caducidad")

# El promotor de una resolución no viene con la fórmula "Promotor:" que busca extract, sino en el propio
# fallo ("por la que se otorga a X autorización administrativa previa").
_PROMOTOR_RES = re.compile(
    r"(?:se\s+(?:otorga|concede|deniega|autoriza)\s+a|otorgar\s+a|conceder\s+a)\s+"
    r"(?P<p>[A-ZÁÉÍÓÚÑ][^,;\n]{2,80}?)(?=,|\s+(?:la\s+|el\s+)?autorizaci[oó]n|\s+para\b)",
    re.I,
)

# Vocabulario administrativo: no distingue un proyecto de otro.
_VACIAS = {
    "resolucion", "resoluciones", "anuncio", "acuerdo", "direccion", "general", "politica", "energetica",
    "minas", "ministerio", "gobierno", "consejeria", "servicio", "subdireccion", "delegacion",
    "subdelegacion", "area", "industria", "energia", "medio", "ambiente", "cambio", "climatico",
    "informacion", "publica", "publico", "expediente", "expte", "proyecto", "instalacion", "instalaciones",
    "declaracion", "impacto", "ambiental", "informe", "evaluacion", "autorizacion", "administrativa",
    "previa", "construccion", "utilidad", "concreto", "efectos", "correspondiente", "relativa", "relativo",
    "denominado", "denominada", "termino", "terminos", "municipal", "municipales", "municipio", "provincia",
    "cantabria", "espana", "parque", "planta", "central", "linea", "aerea", "subestacion", "electrica",
    "eolico", "eolica", "fotovoltaico", "fotovoltaica", "solar", "solares", "kilovoltios", "tension",
    "sociedad", "limitada", "anonima", "unipersonal", "energias", "renovables", "sus", "las", "los", "del",
    "por", "que", "para", "con", "una", "uno", "sobre", "entre", "desde", "hasta", "otros", "otras",
    # Vocabulario técnico compartido por casi todos los proyectos energéticos: no distingue nada, y si se
    # cuenta como coincidencia empareja cualquier resolución con cualquier anuncio.
    "evacuacion", "almacenamiento", "solicitud", "infraestructura", "infraestructuras", "potencia",
    "instalada", "mediante", "baterias", "bess", "hibridacion", "nudo", "conexion", "aerogeneradores",
    "tramo", "tramos", "ampliacion", "modificacion", "nueva", "nuevo", "nuevas", "nuevos", "denominacion",
    "transformadora", "subestaciones", "existente", "existentes", "asociada", "asociadas", "situado",
    "situada", "ubicado", "ubicada", "afectados", "afectadas", "bienes", "derechos", "relacion",
    "concreta", "individualizada", "expropiacion", "forzosa", "urgente", "ocupacion", "ejecucion",
    "obras", "tratamiento", "produccion", "energetico", "electrico", "electricas", "electricos",
    "transporte", "distribucion", "generacion", "megavatios", "circuito", "aereo", "subterraneo",
    "apoyo", "apoyos", "somete", "sometimiento", "tramite", "periodo", "plazo", "dias", "meses",
    "boletin", "oficial", "estado", "comunidad", "autonoma", "consejero", "director", "fotovoltaicas",
    "fotovoltaicos", "eolicos", "eolicas", "parques", "plantas", "lineas", "proyectos",
}
_FORMAS = re.compile(r"\b(?:s\.?\s*l\.?\s*u?\.?|s\.?\s*a\.?\s*u?\.?|s\.?\s*coop\.?|sociedad\s+(?:limitada|an[oó]nima)|unipersonal|slu|sau)\b", re.I)

UMBRAL_FIRME = 6  # a partir de aquí se considera el mismo expediente
UMBRAL_SUGERENCIA = 3  # entre este umbral y el anterior se publica como posible


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", extract._strip_accents(str(s or "").lower()))


def _tokens(s: str) -> set[str]:
    """Palabras distintivas de un título: topónimos y nombres propios de proyecto o de promotor."""
    out = set()
    for w in re.findall(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñüÀÈÒÇàèòç]{4,}", str(s or "")):
        n = extract._strip_accents(w.lower())
        if n not in _VACIAS:
            out.add(n)
    return out


def es_resolucion(a: Anuncio) -> bool:
    """True si el título parece la resolución de un expediente ambiental o energético (y no su apertura)."""
    t = a.titulo
    if extract.INFO_PUBLICA.search(t):
        return False
    if not (_RESUELVE.search(t) and _MATERIA.search(t)):
        return False
    # "Orden por la que se declaran de utilidad pública diversas asociaciones" no es un proyecto.
    return not re.search(r"padr[oó]n|subvenci[oó]n|beca|convenio\s+colectivo|nombramiento|oposici|asociaci", t, re.I)


def tipo_resolucion(a: Anuncio) -> tuple[str, str]:
    """El título manda: el cuerpo de una autorización administrativa cita la declaración de impacto
    ambiental que la precedió, y buscar en el texto la clasificaría como si fuera esa declaración."""
    for base in (a.titulo, a.texto[:2000]):
        for clave, etiqueta, pat in TIPOS:
            if pat.search(base):
                return clave, etiqueta
    return "otro", "Resolución"


def sentido(a: Anuncio, tipo: str = "") -> tuple[str, str]:
    """Sentido de la resolución: (clave, etiqueta)."""
    t = a.titulo
    if _ARCHIVO.search(t):
        return "caducidad", "desistida o archivada"
    neg, pos = _NEGATIVO.search(t), _POSITIVO.search(t)
    if neg and pos:
        return "parcial", "otorgada en parte"  # "se otorga a X ... y se deniega a Y"
    if neg:
        return ("desfavorable", "desfavorable") if "desfavorable" in t.lower() else ("denegada", "denegada")
    if pos:
        return "favorable", "favorable"
    cuerpo = a.texto
    if not cuerpo:
        return "", "sentido no determinado"
    if _ARCHIVO.search(cuerpo[:3000]):
        return "caducidad", "desistida o archivada"
    if tipo in ("dia", "iia", "ambiental_otro"):
        if _AMB_DESFAVORABLE.search(cuerpo):
            return "desfavorable", "desfavorable"
        if _AMB_A_ORDINARIA.search(cuerpo):
            return "a_ordinaria", "obligado a evaluación de impacto ambiental ordinaria"
        if _AMB_SIN_EFECTOS.search(cuerpo):
            return "sin_eia", "sin efectos significativos, no se somete a evaluación ordinaria"
        return "condicionada", "formulada con condiciones"
    if _NEGATIVO.search(cuerpo[:2500]):
        return "denegada", "denegada"
    if _POSITIVO.search(cuerpo[:2500]):
        return "favorable", "favorable"
    return "", "sentido no determinado"


# --- Emparejamiento ----------------------------------------------------------

@dataclass
class Emparejamiento:
    identificador: str = ""  # anuncio de información pública al que corresponde
    puntos: int = 0
    motivos: list[str] = field(default_factory=list)

    @property
    def firme(self) -> bool:
        return bool(self.identificador) and self.puntos >= UMBRAL_FIRME


def _puntua(res: dict, anu: dict) -> tuple[int, list[str]]:
    p, motivos = 0, []
    if res.get("fecha", "") <= anu.get("fecha", ""):
        return 0, []  # una resolución nunca precede a la información pública de su propio expediente
    e_r, e_a = _norm(res.get("expediente", "")), _norm(anu.get("expediente", ""))
    if e_r and e_a:
        if e_r == e_a:
            p += 6
            motivos.append(f"mismo expediente ({anu['expediente']})")
        elif len(min(e_r, e_a, key=len)) >= 6 and (e_r in e_a or e_a in e_r):
            p += 4
            motivos.append(f"expediente contenido ({res['expediente']} / {anu['expediente']})")
        else:
            # Dos expedientes distintos del mismo proyecto (p. ej. la autorización energética y la
            # autorización urbanística) son trámites distintos y no deben darse por el mismo.
            p -= 2
            motivos.append(f"expedientes distintos ({res['expediente']} / {anu['expediente']})")
    pr_r = _norm(_FORMAS.sub("", res.get("promotor", "")))
    pr_a = _norm(_FORMAS.sub("", anu.get("promotor", "")))
    if pr_r and pr_a and len(min(pr_r, pr_a, key=len)) >= 5 and (pr_r in pr_a or pr_a in pr_r):
        p += 3
        motivos.append(f"mismo promotor ({anu['promotor']})")
    comunes = {_norm(m) for m in res.get("municipios", [])} & {_norm(m) for m in anu.get("municipios", [])}
    comunes.discard("")
    if comunes:
        p += 2 if len(comunes) == 1 else 3
        motivos.append(f"{len(comunes)} municipio(s) en común")
    if p == 0:
        # Sin ninguna coincidencia estructural (expediente, promotor o municipio) no hay emparejamiento:
        # las palabras del título y la categoría por sí solas emparejan cualquier cosa con cualquier cosa.
        return 0, []
    if res.get("categoria") and res["categoria"] == anu.get("categoria") and res["categoria"] != "otros":
        p += 1
        motivos.append(f"misma categoría ({res['categoria']})")
    pot_r, pot_a = res.get("potencia_mw"), anu.get("potencia_mw")
    if pot_r and pot_a and abs(pot_r - pot_a) <= 0.05 * max(pot_r, pot_a):
        p += 2
        motivos.append(f"misma potencia ({pot_a} MW)")
    tk = _tokens(res.get("titulo", "")) & _tokens(anu.get("titulo", ""))
    if tk:
        p += 1 if len(tk) == 1 else 2  # aporta, pero nunca decide por sí solo
        motivos.append("coinciden: " + ", ".join(sorted(tk)[:4]))
    return p, motivos


def emparejar(res: dict, anuncios: dict[str, dict]) -> Emparejamiento:
    """Mejor candidato entre los anuncios de información pública ya fichados."""
    mejor = Emparejamiento()
    for ident, anu in anuncios.items():
        p, motivos = _puntua(res, anu)
        if p > mejor.puntos:
            mejor = Emparejamiento(ident, p, motivos)
    if mejor.puntos < UMBRAL_SUGERENCIA:
        return Emparejamiento()
    return mejor


# --- Recolección -------------------------------------------------------------

# Secciones del BOE donde aparecen las resoluciones (III, Otras disposiciones) además de la V-B habitual.
SECCIONES_BOE = ("3", "5B")


def recolectar(dias: list[date], activas: set[str], aviso=lambda s: None) -> list[dict]:
    """Recorre los días indicados y devuelve las resoluciones detectadas, ya clasificadas.

    No toca la red para el BOC (lee los volcados versionados) y para el BOE reutiliza la caché de sumarios.
    """
    out: list[dict] = []
    for d in dias:
        candidatas: list[Anuncio] = []
        if "boe" in activas:
            try:
                sumario = boe.fetch_sumario(d)
            except Exception as e:  # noqa: BLE001
                aviso(f"{d}: error descargando sumario BOE: {e}")
                sumario = None
            if sumario:
                candidatas += [a for a in boe.iter_items(sumario, d, secciones=SECCIONES_BOE) if es_resolucion(a)]
        if "boc_cantabria" in activas:
            try:
                lst = boc_cantabria.anuncios_dia(d)
            except boc_cantabria.BOCInaccesible:
                lst = None
            except Exception as e:  # noqa: BLE001
                aviso(f"{d}: error leyendo BOC: {e}")
                lst = None
            if lst:
                candidatas += [a for a in lst if es_resolucion(a)]
        for a in candidatas:
            if a.fuente == "BOE" and not a.texto:
                try:
                    a.texto = boe.fetch_texto(a)
                except Exception as e:  # noqa: BLE001
                    aviso(f"  {a.identificador}: error descargando texto: {e}")
            extract.clasificar(a)
            extract.extraer_datos(a)
            if not a.promotor:
                m = _PROMOTOR_RES.search(a.titulo) or _PROMOTOR_RES.search(a.texto[:4000])
                if m:
                    a.promotor = m.group("p").strip(" ,.")
            if a.fuente == boc_cantabria.FUENTE:
                boc_cantabria.completar_geo(a)
            clave, etiqueta = tipo_resolucion(a)
            s_clave, s_etiqueta = sentido(a, clave)
            r = a.to_dict()
            r.pop("texto", None)
            r.update({"tipo": clave, "tipo_etiqueta": etiqueta, "sentido": s_clave, "sentido_etiqueta": s_etiqueta})
            out.append(r)
    return out


def incorporar(estado: dict, resoluciones: list[dict]) -> tuple[int, int]:
    """Guarda las resoluciones en el estado y anota en cada anuncio la que le corresponde.

    Devuelve (nuevas, emparejadas firmes). El emparejamiento se recalcula siempre, porque un anuncio
    detectado después puede resultar mejor candidato que el que ya había.
    """
    estado.setdefault("resoluciones", {})
    nuevas = 0
    for r in resoluciones:
        if r["identificador"] not in estado["resoluciones"]:
            nuevas += 1
        estado["resoluciones"][r["identificador"]] = {**estado["resoluciones"].get(r["identificador"], {}), **r}
    for a in estado["anuncios"].values():
        a.pop("resolucion", None)
        a.pop("resolucion_posible", None)
    firmes = 0
    for ident, r in estado["resoluciones"].items():
        m = emparejar(r, estado["anuncios"])
        r["emparejado_con"] = m.identificador
        r["puntos"] = m.puntos
        r["motivos"] = m.motivos
        r["firme"] = m.firme
        if not m.identificador:
            continue
        destino = estado["anuncios"][m.identificador]
        campo = "resolucion" if m.firme else "resolucion_posible"
        previo = destino.get(campo)
        if previo and previo.get("puntos", 0) >= m.puntos:
            continue  # ya tenía emparejada una resolución mejor (p. ej. la DIA frente a una corrección de errores)
        destino[campo] = {
            "identificador": ident,
            "fecha": r["fecha"],
            "tipo": r["tipo"],
            "tipo_etiqueta": r["tipo_etiqueta"],
            "sentido": r["sentido"],
            "sentido_etiqueta": r["sentido_etiqueta"],
            "titulo": r["titulo"],
            "url_html": r["url_html"],
            "fuente": r.get("fuente", "BOE"),
            "puntos": m.puntos,
            "motivos": m.motivos,
        }
        if m.firme:
            firmes += 1
    return nuevas, firmes


# --- Estado de cada expediente ----------------------------------------------

# El artículo 33 de la Ley 21/2013 da al órgano ambiental cuatro meses para formular la declaración de
# impacto ambiental, prorrogables por dos más. Pasado ese plazo sin publicación, conviene preguntar.
MESES_DIA = 6


def estado_proyecto(a: dict, hoy: date | None = None) -> tuple[str, str]:
    """(clave, etiqueta) del estado de tramitación de un proyecto ya detectado."""
    hoy = hoy or date.today()
    lim = a.get("fecha_limite")
    dias = (date.fromisoformat(lim) - hoy).days if lim else None
    # El plazo abierto manda sobre cualquier resolución emparejada: si aún se puede alegar, el trámite
    # está vivo, y lo emparejado será una resolución de otro expediente del mismo proyecto.
    if dias is not None and dias >= 0:
        return "abierto", f"en plazo, quedan {dias} días"
    r = a.get("resolucion")
    if r:
        if r["sentido"] in SENTIDOS_ROJOS:
            return "parado", f"{r['tipo_etiqueta']}: {r['sentido_etiqueta']}"
        if r["sentido"] == "a_ordinaria":
            return "nueva_eia", "obligado a evaluación ordinaria: habrá nueva información pública"
        if r["sentido"] in SENTIDOS_VERDES:
            return "resuelto_fav", f"{r['tipo_etiqueta']}: {r['sentido_etiqueta']}"
        return "resuelto", f"{r['tipo_etiqueta']} publicada"
    if dias is None:
        return "sin_plazo", "plazo no determinado"
    if a.get("resolucion_posible"):
        return "posible", "posible resolución sin confirmar"
    meses = -dias / 30.44
    if meses >= MESES_DIA:
        return "demorado", f"sin resolución publicada tras {int(meses)} meses"
    return "pendiente", "pendiente de resolución"
