"""Vertical del litoral y del suelo turístico.

Por qué es un módulo aparte y no una categoría más del observatorio: los dos verticales buscan cosas
opuestas. El observatorio de energía busca proyectos grandes con evaluación de impacto ambiental, y para
no ahogarse en ruido descarta expresamente (`extract.EXCLUIR`) las viviendas unifamiliares, los cierres de
parcela, las reformas y los cambios de uso. En el litoral eso es precisamente el objeto: la costa no se
transforma con un proyecto de 300 MW, se transforma con cincuenta expedientes de quince días que
individualmente parecen menores. Este módulo lee el montón de descartes del otro.

Dos fuentes, dos regímenes:

- **BOE, sección V-B, Demarcaciones y Servicios Provinciales de Costas** (Ministerio para la Transición
  Ecológica): concesiones y autorizaciones de ocupación del dominio público marítimo-terrestre, deslindes y
  reservas demaniales, de toda la costa española. Ley 22/1988 de Costas y su Reglamento (RD 876/2014).
- **BOC, sección 7.1 Urbanismo** (Cantabria): autorizaciones en la zona de servidumbre de protección del
  dominio público marítimo-terrestre, que son competencia autonómica (artículo 229 de la Ley de Cantabria
  5/2022), planeamiento municipal y evaluación ambiental estratégica de los planes.

Lo que el módulo no hace: decidir si una obra es legal. Marca señales con su apoyo normativo para que quien
lea sepa dónde mirar. La prohibición del artículo 25.1.a) de la Ley de Costas tiene excepciones y regímenes
transitorios, y solo el expediente dice si aplican.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .boe import Anuncio
from .config import DATA_DIR
from .extract import INFO_PUBLICA, _strip_accents
from .plazos import dias_restantes
from .report import esc, pagina

SECCIONES_BOE = ("5B",)
ESTADO_PATH = DATA_DIR / "estado_litoral.json"

# --- Materia -----------------------------------------------------------------

# La servidumbre se nombra de dos maneras y en Cantabria se usa la segunda: "zona de servidumbre del
# dominio público marítimo terrestre". Exigir "de protección" dejaba fuera justo los expedientes que
# más importan, que son las obras en la franja de 100 metros.
_SERVIDUMBRE = re.compile(
    r"servidumbre\s+(?:de\s+(?:protecci[oó]n|tr[aá]nsito|acceso)|del\s+dominio\s+p[uú]blico|mar[ií]tim)",
    re.I,
)
# Órganos de Costas: es el único filtro de ámbito que se aplica al BOE. Lo demás que sale en la
# sección V-B (confederaciones hidrográficas, industria) es tierra adentro y no es de este vertical.
_ORGANO_COSTAS = re.compile(
    r"demarcaci[oó]n\s+de\s+costas|servicio\s+provincial\s+de\s+costas|servicio\s+de\s+costas\s+(?:en|de)|"
    r"direcci[oó]n\s+general\s+de\s+la\s+costa",
    re.I,
)
_DPMT = re.compile(
    r"dominio\s+p[uú]blico\s+mar[ií]timo|servidumbre\s+(?:de\s+(?:protecci[oó]n|tr[aá]nsito|acceso)|"
    r"del\s+dominio\s+p[uú]blico)|zona\s+de\s+influencia|demarcaci[oó]n\s+de\s+costas|"
    r"servicio\s+provincial\s+de\s+costas|direcci[oó]n\s+general\s+de\s+la\s+costa|deslinde|"
    r"reserva\s+demanial|DPMT",
    re.I,
)
_PLANEAMIENTO = re.compile(
    r"plan\s+general|plan\s+parcial|plan\s+especial|modificaci[oó]n\s+puntual|plan\s+de\s+sectorizaci[oó]n|"
    r"estudio\s+de\s+detalle|proyecto\s+de\s+urbanizaci[oó]n|unidad\s+de\s+actuaci[oó]n|reparcelaci[oó]n|"
    r"plan\s+de\s+ordenaci[oó]n\s+del\s+litoral|revisi[oó]n\s+del\s+plan|normas?\s+urban[ií]stica|"
    r"delimitaci[oó]n\s+de\s+(?:unidad|suelo)|convenio\s+urban[ií]stico",
    re.I,
)
_TURISTICO = re.compile(
    r"c[aá]mping|glamping|hotel|hostal|apartamentos?\s+tur[ií]stic|complejo\s+tur[ií]stic|resort|balneario|"
    r"parador|campo\s+de\s+golf|puerto\s+deportivo|marina\s+seca|club\s+n[aá]utico|estaci[oó]n\s+de\s+esqu[ií]|"
    r"telesilla|telecabina|parque\s+de\s+aventura|zona\s+de\s+acampada|aparcamiento\s+en\s+temporada",
    re.I,
)
_EAE = re.compile(
    r"ambiental\s+estrat[eé]gic|informe\s+ambiental\s+estrat[eé]gico|\bIAE\b|memoria\s+ambiental", re.I
)
_RESIDENCIAL = re.compile(
    r"viviendas?|residencial|unifamiliar|chal[eé]|adosad|edificio\s+de\s+\d+|apartamentos?\b|habitaci[oó]n", re.I
)
# Rasgos físicos del litoral: sirven tanto para detectar como para puntuar
_COSTA_FISICA = re.compile(
    r"playa|duna|acantilado|marisma|estuario|ensenada|paseo\s+mar[ií]timo|frente\s+mar[ií]timo|rasa\s+costera|"
    r"\br[ií]a\b|litoral|costa\b|senda\s+costera|arenal|puntal|manglar",
    re.I,
)

# Ruido administrativo de las secciones municipales: ordenanzas, ferias, personal, presupuestos.
_RUIDO = re.compile(
    r"ordenanza|reglamento\s+org[aá]nico|administraci[oó]n\s+electr[oó]nica|prestaciones?\s+econ[oó]mic|"
    r"teleasistencia|emergencia\s+social|venta\s+ambulante|ferias|barracas|puestos?\s+de\s+venta|fiestas\s+de|"
    r"padr[oó]n|plantilla|oferta\s+de\s+empleo|bolsa\s+de\s+trabajo|licitaci[oó]n|formalizaci[oó]n\s+de\s+contrat|"
    r"adjudicaci[oó]n\s+de\s+contrat|subvenci[oó]n|beca|cuenta\s+general|presupuesto|tasa\s+por|"
    r"junta\s+electoral|consulta\s+p[uú]blica\s+previa\s+un\s+proyecto\s+de\s+orden",
    re.I,
)

# Anuncios de Costas que abren plazo sin usar la fórmula "información pública" en el título.
_COSTAS_TRAMITE = re.compile(
    r"solicitud\s+de\s+(?:concesi[oó]n|autorizaci[oó]n|reserva)|otorgamiento\s+de\s+concesi[oó]n|"
    r"procedimiento\s+de\s+deslinde|pr[oó]rroga\s+de\s+(?:la\s+)?concesi[oó]n|"
    r"extinci[oó]n\s+de\s+(?:la\s+)?concesi[oó]n",
    re.I,
)

# (clave, etiqueta, patrón, prioridad base 1-5, plazo por defecto en días hábiles)
CATEGORIAS: list[tuple[str, str, re.Pattern, int, int | None]] = [
    # El deslinde fija dónde empieza la propiedad privada: es el trámite del que cuelga todo lo demás.
    ("deslinde", "Deslinde del dominio público", re.compile(r"deslinde|reserva\s+demanial", re.I), 5, 30),
    ("servidumbre", "Obra en la servidumbre de protección",
     re.compile(r"servidumbre\s+(?:de\s+(?:protecci[oó]n|tr[aá]nsito|acceso)|del\s+dominio\s+p[uú]blico)|"
                r"zona\s+de\s+influencia", re.I), 4, 15),
    ("regeneracion", "Movimiento de arena o regeneración de playa",
     re.compile(r"reubicaci[oó]n\s+de\s+arena|aportaci[oó]n\s+de\s+arena|trasvase\s+de\s+arena|"
                r"regeneraci[oó]n\s+de\s+(?:la\s+)?playa|borde\s+litoral", re.I), 4, 20),
    ("dpmt", "Ocupación del dominio público marítimo-terrestre",
     re.compile(r"dominio\s+p[uú]blico\s+mar[ií]timo|concesi[oó]n\s+de\s+ocupaci[oó]n|DPMT", re.I), 5, 20),
    ("eae", "Evaluación ambiental estratégica de un plan", _EAE, 4, None),
    ("planeamiento", "Planeamiento urbanístico", _PLANEAMIENTO, 4, 20),
    ("turistico", "Instalación turística o de ocio", _TURISTICO, 4, 15),
    ("portuario", "Obra portuaria", re.compile(r"autoridad\s+portuaria|puerto\s+de|dragado|espig[oó]n|dique", re.I), 3, 20),
    ("residencial", "Edificación residencial", _RESIDENCIAL, 3, 15),
]

# Cajones de sastre: (etiqueta, prioridad, plazo por defecto). El de Costas se separa porque un anuncio
# de una Demarcación siempre toca el dominio público aunque el título no lo nombre.
OTRAS_CATEGORIAS: dict[str, tuple[str, int, int | None]] = {
    "costas_otro": ("Otro trámite de Costas", 3, 20),
    "litoral_otro": ("Otro trámite del litoral", 2, 15),
}

# Municipios con línea de costa (o de ría) en Cantabria. Lista curada a mano: sirve para puntuar, no
# para filtrar, y corregirla es cambiar una línea. Los demás municipios cántabros entran igual en el
# vertical, porque la presión turística de Liébana, los valles pasiegos o Campoo es del mismo tipo.
COSTEROS_CANTABRIA = {
    "castro urdiales", "liendo", "laredo", "colindres", "barcena de cicero", "santona", "argonos",
    "noja", "arnuero", "bareyo", "ribamontan al mar", "marina de cudeyo", "el astillero", "astillero",
    "camargo", "santander", "santa cruz de bezana", "pielagos", "miengo", "suances",
    "santillana del mar", "alfoz de lloredo", "comillas", "ruiloba", "valdaliga",
    "san vicente de la barquera", "val de san vicente", "escalante", "limpias", "voto", "villaescusa",
}

# Señales de atención, con el precepto donde mirar. Los puntos son un orden de lectura, no un dictamen.
SENALES: list[tuple[str, str, re.Pattern, int, str]] = [
    ("residencial_servidumbre", "Uso residencial en la servidumbre de protección", re.compile(r"", re.I), 5,
     "El artículo 25.1.a) de la Ley 22/1988 de Costas prohíbe en la servidumbre de protección las "
     "edificaciones destinadas a residencia o habitación. Solo caben las excepciones del artículo 25.3 "
     "(autorización del Consejo de Ministros por razones de utilidad pública) y los regímenes transitorios "
     "de la propia ley. Conviene comprobar cuál se invoca y si está acreditado."),
    ("playa_duna", "Afecta a playa, duna o acantilado", _COSTA_FISICA, 3,
     "En la playa y la zona marítimo-terrestre solo se permiten las instalaciones que por su naturaleza no "
     "puedan ubicarse fuera (artículo 32 de la Ley 22/1988), y los paseos marítimos no pueden ocupar la playa "
     "(artículo 44.5). Los sistemas dunares y los acantilados suelen ser además hábitat de interés comunitario."),
    ("mas_edificabilidad", "Aumenta edificabilidad, altura o clasifica suelo",
     re.compile(r"incremento\s+de|aumento\s+de|mayor\s+(?:edificabilidad|aprovechamiento|altura)|edificabilidad|"
                r"aprovechamiento\s+urban[ií]stic|reclasificaci[oó]n|sectorizaci[oó]n|nuevo\s+sector|"
                r"cambio\s+de\s+clasificaci[oó]n|recalificaci[oó]n", re.I), 3,
     "En la zona de influencia (500 m desde el límite interior de la ribera del mar) la ordenación debe "
     "evitar la formación de pantallas arquitectónicas y no puede superar la densidad edificatoria media del "
     "suelo urbanizable del municipio (artículo 30.1.b de la Ley 22/1988). Es el argumento más directo contra "
     "un aumento de aprovechamiento en primera línea."),
    ("pol", "Suelo ordenado por el Plan de Ordenación del Litoral",
     re.compile(r"plan\s+de\s+ordenaci[oó]n\s+del\s+litoral|\bPOL\b|ley\s+2/2004", re.I), 3,
     "El Plan de Ordenación del Litoral de Cantabria (Ley de Cantabria 2/2004) clasifica la franja "
     "costera en categorías de protección y de ordenación. Cuando un plan o una autorización lo cita "
     "conviene comprobar en qué categoría del POL cae la parcela y si lo que se pide encaja en ella."),
    ("municipio_costero", "Frente costero", re.compile(r"", re.I), 2,
     "El municipio tiene frente marítimo, así que la actuación puede caer en la zona de influencia de "
     "los 500 metros del artículo 30 de la Ley 22/1988 y en el ámbito del Plan de Ordenación del Litoral. "
     "Merece localizar la parcela antes que nada: la distancia a la ribera del mar decide qué régimen se "
     "aplica."),
    ("parcelacion", "Divide la finca en parcelas",
     re.compile(r"parcelaci[oó]n|divisi[oó]n\s+horizontal|segregaci[oó]n\s+de\s+(?:finca|parcela)|"
                r"divisi[oó]n\s+de\s+(?:la\s+)?(?:finca|parcela)", re.I), 3,
     "Dividir una finca en lotes es el primer paso material de la urbanización: cada lote pide después su "
     "licencia por separado y ningún expediente parece grande. Conviene comprobar la clasificación del suelo "
     "y si la división encubre una parcelación urbanística, que fuera del suelo urbanizado no cabe."),
    ("estudio_detalle", "Se tramita por estudio de detalle",
     re.compile(r"estudio\s+de\s+detalle", re.I), 2,
     "El estudio de detalle es el instrumento más ligero del planeamiento: no puede aumentar el "
     "aprovechamiento ni alterar la ordenación estructural, solo reordenar volúmenes. Por eso conviene "
     "leer la memoria y comprobar si el reajuste sube en realidad altura, ocupación o edificabilidad, "
     "que es la forma habitual de saltarse una modificación del plan general."),
    ("suspension_licencias", "Suspende licencias en el ámbito",
     re.compile(r"suspensi[oó]n\s+(?:del\s+otorgamiento\s+)?de\s+licencia|suspensi[oó]n\s+de\s+la\s+tramitaci[oó]n",
                re.I), 2,
     "La aprobación inicial suspende el otorgamiento de licencias en el ámbito afectado (artículo 89 de "
     "la Ley de Cantabria 5/2022). Es la señal de que el expediente va en serio y de que el plazo de "
     "información pública es el momento útil para intervenir."),
    ("suelo_rustico", "En suelo rústico", re.compile(r"suelo\s+r[uú]stic|r[uú]stico\s+de\s+protecci[oó]n", re.I), 2,
     "La autorización en suelo rústico es excepcional y debe justificar la necesidad del emplazamiento "
     "concreto; el trámite es el del artículo 228 de la Ley de Cantabria 5/2022."),
    ("eae_simplificada", "Se resolvió por evaluación ambiental estratégica simplificada",
     re.compile(r"simplificad|informe\s+ambiental\s+estrat[eé]gico|IAE|"
                r"no\s+precisa\s+de\s+sometimiento|no\s+se\s+prev[eé]n\s+efectos", re.I), 3,
     "El informe ambiental estratégico es la salida de la evaluación simplificada (artículos 29 a 32 de la "
     "Ley 21/2013): concluye que el plan no necesita evaluación ordinaria. No se recurre solo, pero sí junto "
     "con la aprobación del plan, y el punto débil habitual es que no valora los efectos acumulativos con el "
     "resto de desarrollos previstos en el mismo municipio."),
    ("plazo_corto", "Plazo de quince días", re.compile(r"quince\s+d[ií]as|15\s+d[ií]as", re.I), 1,
     "Quince días es el mínimo. Si el expediente es voluminoso puede pedirse ampliación del plazo "
     "(artículo 32 de la Ley 39/2015) y, en todo caso, acceso al expediente (artículo 53.1.a)."),
    ("temporada", "Instalación de temporada que se repite cada año",
     re.compile(r"temporada\s+estival|periodo\s+estival|verano|temporal(?:es)?\s+de\s+playa|desmontable", re.I), 2,
     "Las instalaciones desmontables de temporada se autorizan año tras año sobre el mismo suelo. Conviene "
     "vigilar si lo desmontable se ha vuelto permanente, que es el modo habitual de consolidar la ocupación."),
    ("natura_texto", "El anuncio menciona espacio protegido",
     re.compile(r"red\s+natura|ZEPA|\bLIC\b|\bZEC\b|parque\s+natural|reserva\s+natural|h[aá]bitat\s+de\s+inter[eé]s|"
                r"espacio\s+natural\s+protegido", re.I), 2,
     "Si el anuncio ya cita el espacio protegido, la evaluación de repercusiones del artículo 6.3 de la "
     "Directiva Hábitats (artículo 46 de la Ley 42/2007) debería constar en el expediente."),
]


def _base(a: Anuncio) -> str:
    return _strip_accents(a.titulo + "\n" + (a.texto or "")[:6000])


def es_candidato(a: Anuncio) -> bool:
    """Filtro de entrada. Sobre el título salvo en Costas, donde el trámite se nombra sin la fórmula ritual."""
    t = a.titulo
    if _RUIDO.search(t):
        return False
    abre_plazo = bool(INFO_PUBLICA.search(t)) or bool(_COSTAS_TRAMITE.search(t)) or bool(_EAE.search(t))
    if not abre_plazo:
        return False
    if _DPMT.search(t) or _PLANEAMIENTO.search(t) or _TURISTICO.search(t) or _EAE.search(t):
        return True
    # Vivienda suelta: solo interesa si está en la costa
    return bool(_RESIDENCIAL.search(t) and _COSTA_FISICA.search(t))


def es_costas(a: Anuncio) -> bool:
    """Si lo firma una Demarcación o un Servicio Provincial de Costas, toca el dominio público."""
    return bool(_ORGANO_COSTAS.search(a.titulo + " " + (a.departamento or "")))


def clasificar(a: Anuncio) -> Anuncio:
    """Rellena categoria y prioridad. El título manda: el cuerpo suele citar toda la normativa del mundo."""
    a.categoria = "costas_otro" if es_costas(a) else "litoral_otro"
    a.prioridad = OTRAS_CATEGORIAS[a.categoria][1]
    for clave, _etiqueta, pat, prio, _plazo in CATEGORIAS:
        if pat.search(a.titulo):
            a.categoria, a.prioridad = clave, prio
            break
    a.tramite_ambiental = bool(_EAE.search(a.titulo + (a.texto or "")[:2000]))
    return a


def en_ambito(a: Anuncio) -> bool:
    """Segundo filtro, ya con la categoría puesta.

    Del BOE solo se queda lo de Costas: en la sección V-B comparten sitio las demarcaciones costeras y
    las confederaciones hidrográficas, y un deslinde del dominio público hidráulico en Jaén no es de este
    vertical. Del boletín autonómico se queda todo, porque Cantabria entera es costa o interior turístico
    y filtrar por municipio dejaría fuera Potes o Soba, que es exactamente donde también aprieta.
    """
    if a.fuente == "BOE":
        return es_costas(a)
    return True


def etiqueta_categoria(clave: str) -> str:
    for c, etiqueta, *_ in CATEGORIAS:
        if c == clave:
            return etiqueta
    if clave in OTRAS_CATEGORIAS:
        return OTRAS_CATEGORIAS[clave][0]
    return "Otro trámite del litoral"


def plazo_por_defecto(clave: str) -> int | None:
    for c, _e, _p, _prio, plazo in CATEGORIAS:
        if c == clave:
            return plazo
    if clave in OTRAS_CATEGORIAS:
        return OTRAS_CATEGORIAS[clave][2]
    return 15


def senales(a: Anuncio) -> list[dict]:
    """Señales detectadas, cada una con su apoyo normativo. Ordenadas por peso."""
    base = _base(a)
    munis = {_strip_accents(m).lower() for m in (a.municipios or [])}
    fuera = []
    for clave, etiqueta, pat, puntos, apoyo in SENALES:
        if clave == "residencial_servidumbre":
            # Combinación, no un patrón suelto: es la señal que más pesa y la que más falsos positivos daría.
            hay = bool(_RESIDENCIAL.search(base)) and bool(_SERVIDUMBRE.search(base))
        elif clave == "municipio_costero":
            # Un expediente de una Demarcación de Costas está en la costa por definición, sea de la
            # provincia que sea; la lista curada solo hace falta para lo que llega por el BOC.
            hay = bool(munis & COSTEROS_CANTABRIA) or es_costas(a)
        else:
            hay = bool(pat.search(base))
        if hay:
            fuera.append({"clave": clave, "etiqueta": etiqueta, "puntos": puntos, "apoyo": apoyo})
    return sorted(fuera, key=lambda s: -s["puntos"])


def puntos(sen: list[dict]) -> int:
    return sum(s["puntos"] for s in sen)


# --- Estado y web ------------------------------------------------------------

def cargar_estado() -> dict:
    if ESTADO_PATH.exists():
        e = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
        e.setdefault("anuncios", {})
        return e
    return {"anuncios": {}}


def guardar_estado(estado: dict) -> None:
    ESTADO_PATH.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")


def actualizar_estado(estado: dict, resultados: list[dict]) -> int:
    """Incorpora resultados nuevos. Devuelve cuántos no estaban. Los ya conocidos se refrescan."""
    nuevas = 0
    for r in resultados:
        a = dict(r["anuncio"])
        i = a["identificador"]
        if i not in estado["anuncios"]:
            nuevas += 1
        a["senales"] = r.get("senales", [])
        a["puntos"] = r.get("puntos", 0)
        a["natura"] = [s["sitecode"] for s in r.get("natura", [])]
        a["natura_nombres"] = [s["nombre"] for s in r.get("natura", [])][:6]
        esp = r.get("especies") or {}
        a["n_especies"] = esp.get("n_especies", 0)
        a["n_aves"] = esp.get("n_aves", 0)
        a.pop("texto", None)  # el texto completo no se versiona: pesa y está en el boletín
        estado["anuncios"][i] = a
    return nuevas


def _badge_senal(s: dict) -> str:
    color = "#00695c" if s["puntos"] >= 5 else ("#b26a00" if s["puntos"] >= 3 else "#546e7a")
    return f'<span class="badge" style="background:{color}" title="{esc(s["apoyo"])}">{esc(s["etiqueta"])}</span>'


def _fila(a: dict, hoy: date) -> str:
    lim = date.fromisoformat(a["fecha_limite"]) if a.get("fecha_limite") else None
    if lim is None:
        plazo = "<i>sin plazo</i>"
    else:
        d = dias_restantes(lim, hoy)
        est = " (est.)" if a.get("plazo_estimado") else ""
        if d < 0:
            plazo = f"<span class=cerrado>{lim:%d/%m/%Y} · cerrado</span>{est}"
        else:
            plazo = f"<span class='{'urgente' if d <= 7 else ''}'>{lim:%d/%m/%Y} · quedan {d} d</span>{est}"
    munis = esc(", ".join(a.get("municipios", []))) or "<i>no detectado</i>"
    sen = "".join(_badge_senal(s) for s in a.get("senales", [])) or "<i>ninguna</i>"
    nat = ", ".join(a.get("natura_nombres", [])[:2])
    return (
        f"<tr><td>{plazo}</td>"
        f"<td>{esc(etiqueta_categoria(a.get('categoria', '')))}</td>"
        f"<td><a href='{esc(a.get('url_html', ''))}' target='_blank' rel='noopener'>{esc(a['identificador'])}</a><br>"
        f"<small>{esc(a['titulo'][:190])}</small></td>"
        f"<td>{munis}<br><small>{esc(', '.join(a.get('provincias', [])))}</small></td>"
        f"<td>{esc(a.get('promotor', '') or '—')}</td>"
        f"<td>{sen}</td>"
        f"<td>{esc(nat) or '—'}{(' · ' + str(a['n_especies']) + ' esp.') if a.get('n_especies') else ''}</td></tr>"
    )


def _tabla(filas: list[str]) -> str:
    if not filas:
        return "<p><i>Nada que mostrar.</i></p>"
    return (
        "<div class='wrap'><table class='datos'><thead><tr><th>Plazo</th><th>Trámite</th><th>Anuncio</th>"
        "<th>Municipio</th><th>Promotor</th><th>Señales</th><th>Espacios protegidos</th></tr></thead>"
        f"<tbody>{''.join(filas)}</tbody></table></div>"
    )


COMO_ALEGAR = """
<h2>Cómo se pelea una obra en el litoral</h2>
<p>La costa no se pierde de golpe. Se pierde en expedientes de quince días que, por separado, parecen menores:
una reforma, un cierre de parcela, cinco viviendas, un aparcamiento de temporada. Este observatorio los junta.</p>
<ul>
 <li><b>Servidumbre de protección</b> (100 m desde la ribera del mar, 20 m en suelo ya urbanizado en 1988).
 El artículo 25.1.a) de la Ley 22/1988 de Costas <b>prohíbe las edificaciones destinadas a residencia o
 habitación</b>. Cuando el anuncio dice «vivienda» y «servidumbre de protección» en la misma línea, ahí hay
 que mirar: la obra solo cabe por las excepciones del artículo 25.3 o por un régimen transitorio, y eso hay
 que acreditarlo en el expediente. En Cantabria estas autorizaciones las da la Comunidad Autónoma y se
 publican con el trámite del artículo 229 de la Ley 5/2022.</li>
 <li><b>Zona de influencia</b> (500 m). El artículo 30.1.b) obliga a evitar pantallas arquitectónicas y a no
 superar la densidad media del suelo urbanizable del municipio. Es el precepto que sirve contra un aumento de
 edificabilidad en primera línea, que casi siempre llega disfrazado de «modificación puntual».</li>
 <li><b>Playa y zona marítimo-terrestre</b>. Solo lo que por su naturaleza no pueda estar en otro sitio
 (artículo 32), y los paseos marítimos no pueden ocupar la playa (artículo 44.5). Ojo a lo «desmontable» que
 se renueva cada verano durante quince años.</li>
 <li><b>Deslinde</b>. Fija dónde acaba el dominio público. Es el trámite más técnico y el más decisivo: de él
 depende que una parcela esté dentro o fuera. Se somete a información pública por un mes.</li>
 <li><b>Planeamiento y evaluación ambiental estratégica</b>. Una modificación puntual del plan general se
 aprueba inicialmente, se expone un mes (artículo 110.2.a de la Ley 5/2022 en Cantabria) y suele resolverse por
 evaluación estratégica <i>simplificada</i>: un informe ambiental estratégico que concluye que no hace falta
 evaluación ordinaria. Ese informe no se recurre solo, pero sí con la aprobación del plan, y el punto débil
 habitual es que no valora los efectos acumulativos con el resto de desarrollos del municipio.</li>
 <li><b>El expediente, siempre</b>. Ninguna cifra de una alegación debe salir de este panel: se pide el
 expediente (artículo 53.1.a de la Ley 39/2015, o la Ley 27/2006 si eres tercero) y se citan los documentos del
 propio promotor. Lo de aquí sirve para llegar a tiempo, no para argumentar.</li>
</ul>
<p class="sub">Los plazos son estimados, en días hábiles desde el día siguiente a la publicación, descontando
festivos nacionales y los dos autonómicos fijos de Cantabria. Cuando el anuncio no dice el plazo se asume el
habitual del trámite y se marca «(est.)». Comprueba siempre el anuncio original.</p>
"""


def generar_web(estado: dict, docs_dir: Path) -> None:
    hoy = date.today()
    anuncios = list(estado["anuncios"].values())

    def _lim(a):
        return date.fromisoformat(a["fecha_limite"]) if a.get("fecha_limite") else hoy

    abiertos = sorted((a for a in anuncios if a.get("fecha_limite") and dias_restantes(_lim(a), hoy) >= 0), key=_lim)
    cerrados = sorted((a for a in anuncios if not a.get("fecha_limite") or dias_restantes(_lim(a), hoy) < 0),
                      key=_lim, reverse=True)
    urgentes = [a for a in abiertos if dias_restantes(_lim(a), hoy) <= 7]
    graves = [a for a in anuncios if any(s["clave"] == "residencial_servidumbre" for s in a.get("senales", []))]
    nav = ('<nav><a href="index.html">Alegaciones abiertas</a><a href="seguimiento.html">Seguimiento</a>'
           '<a href="litoral.html">Litoral</a><a href="historico.html">Histórico</a>'
           '<a href="https://github.com/Asensio94/observatorio-alegaciones">Código y datos</a></nav>')
    cuerpo = f"""
<div class="kpis">
 <div class="kpi"><b>{len(abiertos)}</b>trámites con plazo abierto</div>
 <div class="kpi"><b>{len(urgentes)}</b>vencen en 7 días o menos</div>
 <div class="kpi"><b>{len(graves)}</b>uso residencial en servidumbre de protección</div>
 <div class="kpi"><b>{len(anuncios)}</b>expedientes seguidos en total</div>
</div>
{COMO_ALEGAR}
<h2>Con plazo abierto ({len(abiertos)})</h2>
{_tabla([_fila(a, hoy) for a in abiertos])}
<h2>Plazo cerrado o sin plazo ({len(cerrados)})</h2>
<p class="sub">Se mantienen a la vista porque el patrón importa más que el expediente suelto: el mismo tramo de
costa aparece una y otra vez, y porque la autorización, cuando llega, sí se puede recurrir.</p>
{_tabla([_fila(a, hoy) for a in cerrados[:150]])}"""
    (docs_dir / "litoral.html").write_text(
        pagina("Observatorio del litoral", f"Costa y suelo turístico · {hoy:%d/%m/%Y} · BOE (Costas) y BOC (Cantabria)",
               cuerpo, nav),
        encoding="utf-8",
    )
