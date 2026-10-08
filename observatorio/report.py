"""Informe HTML diario con mapa (folium) y fichas por proyecto."""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

import folium
from shapely.geometry import mapping, shape

from .config import GBIF_THREAT_CATEGORIES, GBIF_YEAR_FROM
from .plazos import FESTIVOS_NACIONALES, PLAZO_POR_DEFECTO, dias_restantes

COLORES = {
    "eolica": "#d62728",
    "fotovoltaica": "#ff7f0e",
    "red_electrica": "#9467bd",
    "hidrogeno_baterias": "#8c564b",
    "hidrocarburos_gas": "#7f7f7f",
    "mineria": "#bcbd22",
    "transporte": "#1f77b4",
    "puertos_costas": "#17becf",
    "hidraulica": "#2ca02c",
    "urbanismo_industria": "#e377c2",
    "agua_concesion": "#aec7e8",
    "otros": "#444444",
}

# Shared look of the sibling projects: common.css is copied verbatim from the style guide and inlined
# before this repo's own rules, so every page stays a single self-contained file.
COMMON_CSS = (Path(__file__).resolve().parent / "common.css").read_text(encoding="utf-8")
ACCENT_CSS = ":root{--accent:#9f1d35;--accent-dark:#f0708a}"
FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700"
    "&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap"
)

# Colours with a meaning (deadlines, warnings) stay in this repo, with a lighter variant for dark mode.
_DARK_TOKENS = "--urgent:#f08a80;--warn:#e3a93c;--notice-bg:#2a2214;--notice-line:#b8862a;"
CSS = (
    ":root{--urgent:#b3261e;--warn:#9a5b00;--notice-bg:#fbf3dc;--notice-line:#c99a2e}"
    f"@media (prefers-color-scheme: dark){{:root:not([data-theme=\"light\"]){{{_DARK_TOKENS}}}}}"
    f":root[data-theme=\"dark\"]{{{_DARK_TOKENS}}}"
    """
 .site-nav{display:flex;flex-wrap:wrap;gap:4px 18px;font:600 14px/1.3 var(--font-title);text-transform:uppercase;letter-spacing:.08em}
 .site-nav a{color:var(--muted);text-decoration:none} .site-nav a:hover{color:var(--ink)} .site-nav a[aria-current]{color:var(--accent)}
 .figures a{text-decoration-color:var(--line)}
 main.content{max-width:1440px;margin:0 auto;padding:0 16px 8px}
 h2{font:700 26px/1.05 var(--font-title);text-transform:uppercase;letter-spacing:.03em;margin:28px 0 10px}
 h3{font:600 18px/1.2 var(--font-title);text-transform:uppercase;letter-spacing:.05em}
 .sub{color:var(--muted)}
 table{border-collapse:collapse;width:100%;font-size:15px} th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
 thead th{background:var(--paper);font:600 13px/1.25 var(--font-title);text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
 table.meta th{width:240px;color:var(--muted);font-weight:600}
 .wrap{overflow-x:auto;background:var(--paper);border:1px solid var(--line)}
 .ficha{background:var(--paper);border:1px solid var(--line);box-shadow:var(--shadow);padding:16px;margin:24px 0}
 .ficha h2{margin-top:0} .ficha .wrap{border:0}
 .badge{color:#fff;border:0;border-radius:2px;padding:4px 7px 3px;margin-right:.4rem;vertical-align:middle;white-space:nowrap}
 .warn{color:var(--warn)} .urgente{color:var(--urgent);font-weight:600} .cerrado{color:var(--muted)}
 .mapa iframe{display:block;width:100%;height:520px;border:1px solid var(--line);background:var(--paper)}
 .aviso{background:var(--notice-bg);border-left:4px solid var(--notice-line);padding:10px 16px;margin:16px 0;font-size:15px}
 .method ol li{margin:6px 0} .method table.params{margin:6px 0 4px}
 @media (max-width:640px){table.meta th{width:38%} table.params th{white-space:normal} .mapa iframe{height:420px}}
"""
)

_NAV_LINKS = [
    ("index.html", "Alegaciones abiertas"),
    ("seguimiento.html", "Seguimiento"),
    ("condicionado.html", "Después del sí"),
    ("litoral.html", "Litoral"),
    ("historico.html", "Histórico"),
]
REPO_URL = "https://github.com/Asensio94/observatorio-alegaciones"


def site_nav(current: str = "") -> str:
    """Section links; the page being rendered is marked with aria-current."""
    links = "".join(
        f'<a href="{href}"{" aria-current=page" if href == current else ""}>{label}</a>' for href, label in _NAV_LINKS
    )
    return f'<nav class="site-nav" aria-label="Secciones">{links}<a href="{REPO_URL}">Código y datos</a></nav>'


NAV = site_nav()

AVISO_METODO = (
    "El cruce con Red Natura 2000 y con especies amenazadas se hace sobre el <b>término municipal completo</b>, "
    "no sobre la huella de las obras. Indica que la zona merece atención, no que el proyecto afecte al espacio protegido. "
    "Las fechas límite se calculan en días hábiles descontando solo festivos nacionales y son orientativas: "
    "compruébalas siempre en el anuncio oficial."
)


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def badge(categoria: str) -> str:
    return f'<span class="badge" style="background:{COLORES.get(categoria, "#444")}">{esc(categoria)}</span>'



COLORES_FUENTE = {"BOE": "#37474f", "BOC": "#00695c"}


def badge_fuente(fuente: str) -> str:
    return f"<span class='badge' style='background:{COLORES_FUENTE.get(fuente, '#555')}'>{esc(fuente)}</span>"


# Estado de tramitación de un expediente. El color distingue el momento procesal, no si el resultado
# gusta o no: eso lo juzga quien lee.
COLORES_ESTADO = {
    "abierto": "#1565c0",
    "pendiente": "#78909c",
    "demorado": "#b26a00",
    "posible": "#7b1fa2",
    "resuelto_fav": "#8d6e63",
    "resuelto": "#455a64",
    "parado": "#00695c",
    "nueva_eia": "#f57c00",
    "sin_plazo": "#9e9e9e",
}

COLORES_SENTIDO = {
    "favorable": "#8d6e63", "condicionada": "#8d6e63", "sin_eia": "#8d6e63",
    "desfavorable": "#00695c", "denegada": "#00695c", "caducidad": "#00695c",
    "a_ordinaria": "#f57c00", "parcial": "#7b1fa2",
}


def badge_estado(clave: str, etiqueta: str) -> str:
    return f"<span class='badge' style='background:{COLORES_ESTADO.get(clave, '#555')}'>{esc(etiqueta)}</span>"


def badge_estado_sentido(clave: str, etiqueta: str) -> str:
    return f"<span class='badge' style='background:{COLORES_SENTIDO.get(clave, '#9e9e9e')}'>{esc(etiqueta)}</span>"


def enlace_pdf(a: dict) -> str:
    """Enlace al PDF solo si es distinto del enlace principal (en el BOC ambos son el mismo PDF)."""
    if a.get("url_pdf") and a["url_pdf"] != a.get("url_html"):
        return f" · <a href=\"{esc(a['url_pdf'])}\" target=\"_blank\" rel=\"noopener\">PDF</a>"
    return ""

def construir_mapa(resultados: list[dict]) -> folium.Map:
    m = folium.Map(location=[40.2, -3.7], zoom_start=6, tiles="OpenStreetMap")
    natura_layer = folium.FeatureGroup(name="Red Natura 2000 en los municipios", show=True)
    proy_layer = folium.FeatureGroup(name="Municipios del proyecto", show=True)
    marcadores = folium.FeatureGroup(name="Proyectos", show=True)
    vistos: set[str] = set()
    for r in resultados:
        a = r["anuncio"]
        geom = r.get("geom")
        if geom is None:
            continue
        color = COLORES.get(a["categoria"], "#444")
        popup = folium.Popup(
            f"<b>{esc(a['identificador'])}</b><br>{esc(a['titulo'][:300])}…<br>"
            f"<b>Categoría:</b> {esc(a['categoria'])} · <b>Natura 2000 en el municipio:</b> {len(r['natura'])} · "
            f"<b>Especies amenazadas:</b> {r['especies'].get('n_especies', 0)}<br>"
            f"<b>Fecha límite (est.):</b> {esc(a.get('fecha_limite'))}<br>"
            f"<a href='{esc(a['url_html'])}' target='_blank' rel='noopener'>Ver anuncio oficial ({esc(a.get('fuente', 'BOE'))})</a>",
            max_width=420,
        )
        folium.GeoJson(
            mapping(geom.simplify(0.0008, preserve_topology=True)),
            style_function=lambda _f, c=color: {"color": c, "weight": 2, "fillColor": c, "fillOpacity": 0.25},
            tooltip=f"{a['identificador']} · {a['categoria']}",
        ).add_child(popup).add_to(proy_layer)
        c = geom.centroid
        folium.CircleMarker(
            [c.y, c.x], radius=9, color=color, fill=True, fill_opacity=0.9,
            tooltip=f"{a['identificador']} · {a['categoria']} · límite {a.get('fecha_limite', '')}",
        ).add_to(marcadores)
        for s in r["natura"]:
            if not s.get("geometry") or s["sitecode"] in vistos:
                continue
            vistos.add(s["sitecode"])
            folium.GeoJson(
                mapping(shape(s["geometry"]).simplify(0.002, preserve_topology=True)),
                style_function=lambda _f: {"color": "#2e7d32", "weight": 1, "fillColor": "#66bb6a", "fillOpacity": 0.2},
                tooltip=f"{s['sitecode']} {s['nombre']} ({s['tipo']})",
            ).add_to(natura_layer)
    natura_layer.add_to(m)
    proy_layer.add_to(m)
    marcadores.add_to(m)
    folium.LayerControl().add_to(m)
    return m


def texto_plazo(a: dict) -> str:
    if not a.get("fecha_limite"):
        return "no determinado"
    lim = date.fromisoformat(a["fecha_limite"])
    d = dias_restantes(lim)
    est = " (plazo no detectado; se asume 30 días hábiles)" if a.get("plazo_estimado") else f" ({a.get('plazo_dias')} días hábiles)"
    if d < 0:
        return f"<span class=cerrado>{lim:%d/%m/%Y} · cerrado</span>{est}"
    cls = "urgente" if d <= 7 else ""
    return f"<span class='{cls}'>{lim:%d/%m/%Y} · quedan {d} días</span>{est}"


def ficha(r: dict) -> str:
    a = r["anuncio"]
    esp = r["especies"]
    munis = ", ".join(a["municipios"]) or "<i>no detectados</i>"
    no_res = r.get("municipios_no_resueltos") or []
    filas_natura = "".join(
        f"<tr><td>{esc(s['sitecode'])}</td><td>{esc(s['nombre'])}</td><td>{esc(s['tipo'])}</td></tr>"
        for s in r["natura"]
    ) or "<tr><td colspan=3><i>Ningún espacio Natura 2000 en los municipios detectados</i></td></tr>"
    filas_esp = "".join(
        f"<tr><td><i>{esc(e['scientificName'])}</i></td><td>{esc(e.get('vernacular_es', ''))}</td>"
        f"<td>{esc(e.get('class', ''))}</td><td>{esc(e['categoria_es'])}</td>"
        f"<td style='text-align:right'>{e['registros']}</td></tr>"
        for e in esp.get("especies", [])[:25]
    ) or "<tr><td colspan=5><i>Sin registros de especies amenazadas (o zona sin geolocalizar)</i></td></tr>"
    mw = f"{a['potencia_mw']:g} MW" if a.get("potencia_mw") else ""
    amb = "Sí" if a.get("tramite_ambiental") else "No detectado en el título"
    return f"""
<section class="ficha" id="{esc(a['identificador'])}">
  <h2>{badge(a['categoria'])}{badge_fuente(a.get('fuente', 'BOE'))} {esc(a['identificador'])} <small>(publicado {esc(a['fecha'])}, prioridad {a['prioridad']})</small></h2>
  <p class="titulo">{esc(a['titulo'])}</p>
  <table class="meta">
    <tr><th>Fecha límite de alegaciones (estimada)</th><td>{texto_plazo(a)}</td></tr>
    <tr><th>Órgano</th><td>{esc(a['departamento'])}</td></tr>
    <tr><th>Trámite ambiental (EsIA/EIA)</th><td>{amb}</td></tr>
    <tr><th>Municipios</th><td>{esc(munis)}{(' · <span class=warn>no geolocalizados: ' + esc(', '.join(no_res)) + '</span>') if no_res else ''}</td></tr>
    <tr><th>Provincias</th><td>{esc(', '.join(a['provincias']))}</td></tr>
    <tr><th>Promotor</th><td>{esc(a.get('promotor', ''))}</td></tr>
    <tr><th>Potencia</th><td>{esc(mw)}</td></tr>
    <tr><th>Expediente</th><td>{esc(a.get('expediente', ''))}</td></tr>
    <tr><th>Anuncio oficial</th><td><a href="{esc(a['url_html'])}" target="_blank" rel="noopener">{esc(a.get('fuente', 'BOE'))}: anuncio</a>{enlace_pdf(a)}</td></tr>
  </table>
  <h3>Red Natura 2000 en los municipios afectados: {len(r['natura'])} <small>(zona de atención, no solape de obras)</small></h3>
  <div class="wrap"><table class="datos"><thead><tr><th>Código</th><th>Espacio</th><th>Tipo</th></tr></thead><tbody>{filas_natura}</tbody></table></div>
  <h3>Especies animales amenazadas (UICN) con registros desde 2005 en los municipios: {esp.get('n_especies', 0)} especies, {esp.get('n_aves', 0)} aves, {esp.get('total_registros_amenazadas', 0)} registros</h3>
  <div class="wrap"><table class="datos"><thead><tr><th>Especie</th><th>Nombre común</th><th>Clase</th><th>Categoría UICN</th><th>Registros</th></tr></thead><tbody>{filas_esp}</tbody></table></div>
</section>"""


SIBLINGS = [
    ("observatorio-alegaciones", "Observatorio de alegaciones"),
    ("vigia-incendios", "Vigía de incendios"),
    ("centinela-natura", "Centinela Natura"),
    ("vigilancia-humedales", "Vigilancia de humedales"),
    ("sub-nocte", "Sub Nocte"),
    ("riesgo-tendidos-aves", "Riesgo de tendidos para aves"),
    ("grafo-promotores", "Grafo de promotores"),
    ("cartera-cotizadas", "Cartera de las cotizadas"),
    ("cuaderno-campo", "Cuaderno de campo"),
]
THIS_PROJECT = "observatorio-alegaciones"


def _sibling_items() -> str:
    current = ' aria-current="page"'
    return "".join(
        f'    <li{current if slug == THIS_PROJECT else ""}><a href="https://asensio94.github.io/{slug}/">{name}</a></li>\n'
        for slug, name in SIBLINGS
    )


SITE_FOOTER = f"""<footer class="site-footer">
  <p class="principle">Datos públicos, reglas a la vista y cada cifra enlazada a su fuente. Indicios, no veredictos.</p>
  <p>Fuentes: BOE (datos abiertos), BOC Boletín Oficial de Cantabria (XML diario), Agencia Europea de Medio Ambiente (Natura 2000, versión 2024), GBIF (registros de animales con coordenadas desde 2005, categorías UICN), OpenStreetMap/Nominatim (límites municipales), Catastro (parcelas INSPIRE).
  Código abierto con licencia MIT: <a href="{REPO_URL}">github.com/Asensio94/observatorio-alegaciones</a>. Datos propios con licencia CC BY 4.0; los de terceros conservan la suya.</p>
  <nav aria-label="Proyectos hermanos"><ul class="siblings">
{_sibling_items()}  </ul></nav>
</footer>"""


def _years(years) -> str:
    ys = sorted(years)
    return f"{ys[0]}-{ys[-1]}" if len(ys) > 1 else str(ys[0])


# «Cómo se calcula» for the pages built from data/estado.json (open, closed and the dated reports).
# Every statement comes from the README or from the code constants interpolated here.
MAIN_METHOD = f"""
<p>Cada mañana laborable se leen los anuncios de información pública del <b>BOE</b> (sección V-B) y del
<b>Boletín Oficial de Cantabria</b> (secciones 5 y 7), se detectan proyectos con posible afección ambiental
(eólica, fotovoltaica, líneas eléctricas, minería, infraestructuras, costas, hidráulica), se localizan sus
municipios y se cruzan con la Red Natura 2000 y con los registros de especies animales amenazadas. El objetivo
es que los grupos locales y las organizaciones de conservación conozcan los proyectos <b>mientras aún se puede
alegar</b>. Proyecto abierto: el código, los datos y las mejoras están en GitHub.</p>
<ol>
 <li><b>Lectura.</b> A las 07:30 UTC, de lunes a sábado, se leen los anuncios de los últimos cuatro días del BOE
  (sección V-B, «Otros anuncios oficiales») y del BOC (secciones 5 y 7). Los servidores del BOC no responden
  desde GitHub, así que un equipo en España descarga sus anuncios y los sube al repositorio.</li>
 <li><b>Selección.</b> Reglas escritas (expresiones regulares) separan los proyectos con posible afección
  ambiental, les dan categoría y prioridad, y extraen municipios, provincias, plazo, promotor, potencia y
  expediente.</li>
 <li><b>Fecha límite.</b> Se cuentan los días hábiles del plazo desde el día siguiente a la publicación, sin
  sábados ni domingos y descontando los festivos nacionales y, en el BOC, los dos autonómicos fijos de
  Cantabria. Si el anuncio no dice el plazo se asumen {PLAZO_POR_DEFECTO} días hábiles y se marca como estimado.</li>
 <li><b>Localización.</b> Cada municipio se convierte en su polígono de OpenStreetMap (Nominatim).</li>
 <li><b>Cruces.</b> Los proyectos de prioridad 3 o más con municipios detectados se cruzan con los espacios Red
  Natura 2000 (LIC/ZEC y ZEPA) que tocan el término municipal y con los registros GBIF de especies animales en
  categoría UICN {", ".join(GBIF_THREAT_CATEGORIES)} desde {GBIF_YEAR_FROM}.</li>
 <li><b>Huella catastral.</b> Si el anuncio del BOE trae la relación de bienes y derechos afectados, cada
  parcela se localiza en el servicio INSPIRE del Catastro, se unen sus geometrías y se repite el cruce con Red
  Natura 2000 sobre esa huella («En las parcelas afectadas»). De esas tablas solo se leen las columnas
  catastrales y las superficies; los datos personales se descartan sin guardarse.</li>
 <li><b>Publicación.</b> Todo se acumula en <code>data/estado.json</code> y se regeneran estas páginas. Un
  proyecto pasa al histórico cuando su fecha límite estimada ya ha pasado.</li>
</ol>
<h3>Parámetros</h3>
<table class="params">
 <tr><th>Ventana de lectura diaria</th><td class="num">4 días</td></tr>
 <tr><th>Plazo si el anuncio no lo dice</th><td class="num">{PLAZO_POR_DEFECTO} días hábiles</td></tr>
 <tr><th>Festivos nacionales cargados</th><td class="num">{_years(FESTIVOS_NACIONALES)}</td></tr>
 <tr><th>Aviso de plazo urgente</th><td class="num">7 días o menos</td></tr>
 <tr><th>Prioridad mínima para cruzar</th><td class="num">3</td></tr>
 <tr><th>Especies (GBIF)</th><td class="num">UICN {"/".join(GBIF_THREAT_CATEGORIES)} · desde {GBIF_YEAR_FROM}</td></tr>
 <tr><th>Red Natura 2000</th><td class="num">versión 2024</td></tr>
</table>
<h3>Validación</h3>
<p>Pendiente: no hay todavía un contraste sistemático de la detección ni de las fechas límite contra una
lista de referencia. Sí está medida la localización de la huella catastral: en la primera versión, sobre los
35 anuncios con relación de bienes del estado, 6.666 parcelas, de las que 650 son forales; de las de catastro
común se localizó el 98,7 %.</p>
<h3>Límites</h3>
<ul>
 <li>El cruce se hace sobre el <b>término municipal completo</b>, no sobre la huella de las obras: es un filtro
  de atención, no una evaluación de afección.</li>
 <li>La huella catastral es la parcela entera, así que sobreestima: por eso se dan la superficie declarada y la
  de las parcelas. Navarra y el País Vasco tienen catastro propio y sus parcelas quedan como forales, sin huella.</li>
 <li>Las fechas límite son orientativas: no descuentan festivos locales ni autonómicos móviles.</li>
 <li>La extracción por reglas puede fallar en municipios, provincias o plazos. Cada fila enlaza al anuncio
  oficial: compruébalo allí.</li>
 <li>Solo se leen el BOE y el BOC de Cantabria; el resto de boletines autonómicos está pendiente.</li>
</ul>
"""


def figures_html(figures) -> str:
    """Key figures for the header: an iterable of (value_html, label_html)."""
    items = "".join(f"<div><b>{value}</b><span>{label}</span></div>" for value, label in figures)
    return f'<div class="figures">{items}</div>' if items else ""


def pagina(titulo: str, sub: str, cuerpo: str, nav: str = "", *, heading: str | None = None,
           figures=(), method: str = "") -> str:
    """Whole page: header (nav, h1, lede, figures), content, «Cómo se calcula» and the shared footer.

    `heading` is trusted HTML for the h1 (key word wrapped in <span>); it defaults to the escaped title.
    """
    method_html = (
        f'<section class="method" aria-labelledby="como-se-calcula"><h2 id="como-se-calcula">Cómo se calcula</h2>'
        f"{method}</section>"
        if method else ""
    )
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(titulo)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{esc(FONTS_URL)}">
<style>
{COMMON_CSS}
{ACCENT_CSS}
{CSS}</style></head><body>
<header class="site-header">
{nav}
<h1>{heading if heading is not None else esc(titulo)}</h1>
<p class="lede">{sub}</p>
{figures_html(figures)}
</header>
<main class="content">
{cuerpo}
</main>
{method_html}
{SITE_FOOTER}
</body></html>"""


def generar_informe(resultados: list[dict], desde: date, hasta: date, out_dir: Path, nombre: str) -> Path:
    """Escribe out_dir/nombre (HTML) y out_dir/nombre_mapa.html. Devuelve la ruta del informe."""
    out_dir.mkdir(parents=True, exist_ok=True)
    resultados = sorted(
        resultados,
        key=lambda r: (-r["anuncio"]["prioridad"], -len(r["natura"]), -r["especies"].get("n_especies", 0)),
    )
    mapa_file = nombre.replace(".html", "_mapa.html")
    construir_mapa(resultados).save(str(out_dir / mapa_file))
    n_geo = sum(1 for r in resultados if r.get("geom") is not None)
    n_natura = sum(1 for r in resultados if r["natura"])
    indice = "".join(
        f"<tr><td><a href='#{esc(r['anuncio']['identificador'])}'>{esc(r['anuncio']['identificador'])}</a></td>"
        f"<td>{badge_fuente(r['anuncio'].get('fuente', 'BOE'))}</td><td>{esc(r['anuncio']['fecha'])}</td><td>{badge(r['anuncio']['categoria'])}</td>"
        f"<td>{'Sí' if r['anuncio']['tramite_ambiental'] else ''}</td>"
        f"<td>{esc(', '.join(r['anuncio']['provincias'][:3]))}</td>"
        f"<td style='text-align:right'>{len(r['natura'])}</td>"
        f"<td style='text-align:right'>{r['especies'].get('n_especies', 0)}</td>"
        f"<td style='text-align:right'>{r['especies'].get('n_aves', 0)}</td>"
        f"<td>{texto_plazo(r['anuncio'])}</td></tr>"
        for r in resultados
    )
    figures = [
        (len(resultados), "proyectos en información pública"),
        (n_geo, "geolocalizados"),
        (n_natura, "con Natura 2000 en el municipio"),
        (sum(1 for r in resultados if r['anuncio']['tramite_ambiental']), "con trámite ambiental explícito"),
    ]
    cuerpo = f"""
<div class="aviso">{AVISO_METODO}</div>
<div class="mapa"><iframe src="{esc(mapa_file)}" loading="lazy" title="Mapa de los proyectos del informe"></iframe></div>
<h2>Índice</h2>
<div class="wrap"><table class="datos"><thead><tr><th>Anuncio</th><th>Fuente</th><th>Publicado</th><th>Categoría</th><th>EIA</th><th>Provincias</th><th>Natura (municipio)</th><th>Esp. amen.</th><th>Aves</th><th>Fecha límite (est.)</th></tr></thead><tbody>{indice}</tbody></table></div>
{''.join(ficha(r) for r in resultados)}"""
    nav = ('<nav class="site-nav" aria-label="Secciones"><a href="../index.html">← Alegaciones abiertas</a>'
           '<a href="../historico.html">Histórico</a></nav>')
    doc = pagina(
        "Observatorio de alegaciones ambientales",
        f"Informe de los anuncios de información pública publicados entre el {desde:%d/%m/%Y} y el {hasta:%d/%m/%Y} "
        f"en el BOE (sección V-B) y el BOC de Cantabria, con mapa y ficha de cada proyecto. Generado el {date.today():%d/%m/%Y}.",
        cuerpo,
        nav,
        heading="Observatorio de <span>alegaciones</span> ambientales",
        figures=figures,
        method=MAIN_METHOD,
    )
    out = out_dir / nombre
    out.write_text(doc, encoding="utf-8")
    (out_dir / nombre.replace(".html", ".json")).write_text(
        json.dumps(
            [{**r, "geom": None, "natura": [{k: v for k, v in s.items() if k != "geometry"} for s in r["natura"]]} for r in resultados],
            ensure_ascii=False, indent=1, default=str,
        ),
        encoding="utf-8",
    )
    return out
