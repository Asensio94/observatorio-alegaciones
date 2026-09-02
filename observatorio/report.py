"""Informe HTML diario con mapa (folium) y fichas por proyecto."""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

import folium
from shapely.geometry import mapping, shape

from .plazos import dias_restantes

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

CSS = """
 html,body{background:#fff} body{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;padding:1.5rem;max-width:1200px;margin:auto;color:#222;color-scheme:light}
 h1{margin-bottom:.2rem} .sub{color:#666;margin-top:0} nav a{margin-right:1rem}
 .kpis{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0} .kpi{background:#f4f6f8;border-radius:8px;padding:.8rem 1.2rem;min-width:150px}
 .kpi b{font-size:1.6rem;display:block}
 table{border-collapse:collapse;width:100%;font-size:.92rem} th,td{border-bottom:1px solid #e5e5e5;padding:.35rem .5rem;text-align:left;vertical-align:top}
 table.meta th{width:240px;color:#555;font-weight:600} thead th{background:#f4f6f8}
 .ficha{border:1px solid #ddd;border-radius:10px;padding:1rem 1.2rem;margin:1.5rem 0}
 .badge{color:#fff;border-radius:6px;padding:.1rem .5rem;font-size:.8rem;vertical-align:middle;margin-right:.4rem;white-space:nowrap}
 .titulo{color:#333} .warn{color:#b26a00} .urgente{color:#c62828;font-weight:600} .cerrado{color:#888}
 .mapa iframe{width:100%;height:520px;border:0}
 .aviso{background:#fff8e1;border-left:4px solid #f9a825;padding:.6rem 1rem;margin:1rem 0;font-size:.9rem}
 footer{color:#777;font-size:.85rem;margin-top:2rem}
 .wrap{overflow-x:auto}
"""

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


def pagina(titulo: str, sub: str, cuerpo: str, nav: str = "") -> str:
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(titulo)}</title><style>{CSS}</style></head><body>
<h1>{esc(titulo)}</h1><p class="sub">{sub}</p>{nav}
{cuerpo}
<footer><p>Fuentes: BOE (datos abiertos), BOC Boletín Oficial de Cantabria (XML diario), Agencia Europea de Medio Ambiente (Natura 2000, versión 2024), GBIF (registros de animales con coordenadas desde 2005, categorías UICN), OpenStreetMap/Nominatim (límites municipales).
Código abierto: <a href="https://github.com/Asensio94/observatorio-alegaciones">github.com/Asensio94/observatorio-alegaciones</a>.</p></footer>
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
    cuerpo = f"""
<div class="kpis">
 <div class="kpi"><b>{len(resultados)}</b>proyectos en información pública</div>
 <div class="kpi"><b>{n_geo}</b>geolocalizados</div>
 <div class="kpi"><b>{n_natura}</b>con Natura 2000 en el municipio</div>
 <div class="kpi"><b>{sum(1 for r in resultados if r['anuncio']['tramite_ambiental'])}</b>con trámite ambiental explícito</div>
</div>
<div class="aviso">{AVISO_METODO}</div>
<div class="mapa"><iframe src="{esc(mapa_file)}" loading="lazy"></iframe></div>
<h2>Índice</h2>
<div class="wrap"><table class="datos"><thead><tr><th>Anuncio</th><th>Fuente</th><th>Publicado</th><th>Categoría</th><th>EIA</th><th>Provincias</th><th>Natura (municipio)</th><th>Esp. amen.</th><th>Aves</th><th>Fecha límite (est.)</th></tr></thead><tbody>{indice}</tbody></table></div>
{''.join(ficha(r) for r in resultados)}"""
    nav = '<nav><a href="../index.html">← Alegaciones abiertas</a><a href="../historico.html">Histórico</a></nav>'
    doc = pagina(
        "Observatorio de alegaciones ambientales",
        f"Informe · BOE sección V-B · anuncios publicados entre {desde} y {hasta} · generado {date.today()}",
        cuerpo,
        nav,
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
