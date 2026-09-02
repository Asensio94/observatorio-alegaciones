"""Informe HTML con mapa (folium) y fichas por proyecto."""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

import folium
from shapely.geometry import mapping, shape

from .config import OUTPUT_DIR

_COLORES = {
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


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def construir_mapa(resultados: list[dict]) -> folium.Map:
    m = folium.Map(location=[40.2, -3.7], zoom_start=6, tiles="OpenStreetMap")
    marcadores = folium.FeatureGroup(name="Proyectos (marcador)", show=True)
    natura_layer = folium.FeatureGroup(name="Red Natura 2000 afectada", show=True)
    proy_layer = folium.FeatureGroup(name="Proyectos (municipios)", show=True)
    vistos_natura: set[str] = set()
    for r in resultados:
        a = r["anuncio"]
        geom = r.get("geom")
        if geom is None:
            continue
        color = _COLORES.get(a["categoria"], "#444")
        popup = folium.Popup(
            f"<b>{_esc(a['identificador'])}</b><br>{_esc(a['titulo'][:300])}…<br>"
            f"<b>Categoría:</b> {_esc(a['categoria'])} · <b>Natura 2000:</b> {len(r['natura'])} espacios · "
            f"<b>Especies amenazadas:</b> {r['especies'].get('n_especies', 0)}<br>"
            f"<a href='{_esc(a['url_html'])}' target='_blank'>Ver anuncio en el BOE</a>",
            max_width=420,
        )
        folium.GeoJson(
            mapping(geom.simplify(0.0008, preserve_topology=True)),
            style_function=lambda _f, c=color: {"color": c, "weight": 2, "fillColor": c, "fillOpacity": 0.25},
            tooltip=f"{a['identificador']} · {a['categoria']}",
        ).add_child(popup).add_to(proy_layer)
        c = geom.centroid
        folium.CircleMarker([c.y, c.x], radius=9, color=color, fill=True, fill_opacity=0.9,
                            tooltip=f"{a['identificador']} · {a['categoria']} · Natura {len(r['natura'])} · esp. {r['especies'].get('n_especies', 0)}").add_to(marcadores)
        for s in r["natura"]:
            if not s.get("geometry") or s["sitecode"] in vistos_natura:
                continue
            vistos_natura.add(s["sitecode"])
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


def _ficha(r: dict) -> str:
    a = r["anuncio"]
    esp = r["especies"]
    munis = ", ".join(a["municipios"]) or "<i>no detectados</i>"
    no_res = r.get("municipios_no_resueltos") or []
    filas_natura = "".join(
        f"<tr><td>{_esc(s['sitecode'])}</td><td>{_esc(s['nombre'])}</td><td>{_esc(s['tipo'])}</td>"
        f"<td style='text-align:right'>{_esc(s['solape_km2'])}</td></tr>"
        for s in r["natura"]
    ) or "<tr><td colspan=4><i>Sin solape con Red Natura 2000 en los municipios detectados</i></td></tr>"
    filas_esp = "".join(
        f"<tr><td><i>{_esc(e['scientificName'])}</i></td><td>{_esc(e.get('vernacular_es',''))}</td>"
        f"<td>{_esc(e.get('class',''))}</td><td>{_esc(e['categoria_es'])}</td>"
        f"<td style='text-align:right'>{e['registros']}</td></tr>"
        for e in esp.get("especies", [])[:25]
    ) or "<tr><td colspan=5><i>Sin registros de especies amenazadas (o zona sin geolocalizar)</i></td></tr>"
    plazo = f"{a['plazo_dias']} días" if a.get("plazo_dias") else "no detectado"
    mw = f"{a['potencia_mw']:g} MW" if a.get("potencia_mw") else ""
    amb = "Sí" if a.get("tramite_ambiental") else "No"
    return f"""
<section class="ficha" id="{_esc(a['identificador'])}">
  <h2><span class="badge" style="background:{_COLORES.get(a['categoria'],'#444')}">{_esc(a['categoria'])}</span>
      {_esc(a['identificador'])} <small>({_esc(a['fecha'])}, prioridad {a['prioridad']})</small></h2>
  <p class="titulo">{_esc(a['titulo'])}</p>
  <table class="meta">
    <tr><th>Órgano</th><td>{_esc(a['departamento'])}</td></tr>
    <tr><th>Trámite ambiental (EsIA/EIA)</th><td>{amb}</td></tr>
    <tr><th>Plazo de alegaciones</th><td>{plazo}</td></tr>
    <tr><th>Municipios</th><td>{_esc(munis)}{(' · <span class=warn>no geolocalizados: ' + _esc(', '.join(no_res)) + '</span>') if no_res else ''}</td></tr>
    <tr><th>Provincias</th><td>{_esc(', '.join(a['provincias']))}</td></tr>
    <tr><th>Promotor</th><td>{_esc(a.get('promotor',''))}</td></tr>
    <tr><th>Potencia</th><td>{_esc(mw)}</td></tr>
    <tr><th>Expediente</th><td>{_esc(a.get('expediente',''))}</td></tr>
    <tr><th>Enlaces</th><td><a href="{_esc(a['url_html'])}" target="_blank">BOE (HTML)</a> · <a href="{_esc(a['url_pdf'])}" target="_blank">PDF</a></td></tr>
  </table>
  <h3>Red Natura 2000 en los municipios afectados ({len(r['natura'])})</h3>
  <table class="datos"><thead><tr><th>Código</th><th>Espacio</th><th>Tipo</th><th>Solape aprox. (km²)</th></tr></thead><tbody>{filas_natura}</tbody></table>
  <h3>Especies amenazadas (UICN) con registros desde 2005 en la zona: {esp.get('n_especies',0)} especies, {esp.get('n_aves',0)} aves, {esp.get('total_registros_amenazadas',0)} registros</h3>
  <table class="datos"><thead><tr><th>Especie</th><th>Nombre común</th><th>Clase</th><th>Categoría UICN</th><th>Registros</th></tr></thead><tbody>{filas_esp}</tbody></table>
</section>"""


def generar_informe(resultados: list[dict], desde: date, hasta: date, nombre: str = "informe.html") -> Path:
    resultados = sorted(
        resultados,
        key=lambda r: (-r["anuncio"]["prioridad"], -len(r["natura"]), -r["especies"].get("n_especies", 0)),
    )
    mapa = construir_mapa(resultados)
    mapa_file = nombre.replace(".html", "_mapa.html")
    mapa.save(str(OUTPUT_DIR / mapa_file))
    mapa_html = f'<iframe src="{mapa_file}" style="width:100%;height:520px;border:0" loading="lazy"></iframe>'
    n_geo = sum(1 for r in resultados if r.get("geom") is not None)
    n_natura = sum(1 for r in resultados if r["natura"])
    fichas = "\n".join(_ficha(r) for r in resultados)
    indice = "".join(
        f"<tr><td><a href='#{_esc(r['anuncio']['identificador'])}'>{_esc(r['anuncio']['identificador'])}</a></td>"
        f"<td>{_esc(r['anuncio']['fecha'])}</td><td>{_esc(r['anuncio']['categoria'])}</td>"
        f"<td>{'Sí' if r['anuncio']['tramite_ambiental'] else ''}</td>"
        f"<td>{_esc(', '.join(r['anuncio']['provincias'][:3]))}</td>"
        f"<td style='text-align:right'>{len(r['natura'])}</td>"
        f"<td style='text-align:right'>{r['especies'].get('n_especies',0)}</td>"
        f"<td style='text-align:right'>{r['especies'].get('n_aves',0)}</td>"
        f"<td>{_esc(r['anuncio']['plazo_dias'] or '')}</td></tr>"
        for r in resultados
    )
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Observatorio de alegaciones ambientales · {desde} a {hasta}</title>
<style>
 html,body{{background:#fff}} body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;padding:1.5rem;max-width:1200px;margin:auto;color:#222;color-scheme:light}}
 h1{{margin-bottom:.2rem}} .sub{{color:#666;margin-top:0}}
 .kpis{{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}} .kpi{{background:#f4f6f8;border-radius:8px;padding:.8rem 1.2rem;min-width:150px}}
 .kpi b{{font-size:1.6rem;display:block}}
 table{{border-collapse:collapse;width:100%;font-size:.92rem}} th,td{{border-bottom:1px solid #e5e5e5;padding:.35rem .5rem;text-align:left;vertical-align:top}}
 table.meta th{{width:220px;color:#555;font-weight:600}} thead th{{background:#f4f6f8}}
 .ficha{{border:1px solid #ddd;border-radius:10px;padding:1rem 1.2rem;margin:1.5rem 0}}
 .badge{{color:#fff;border-radius:6px;padding:.1rem .5rem;font-size:.8rem;vertical-align:middle;margin-right:.4rem}}
 .titulo{{color:#333}} .warn{{color:#b26a00}} .mapa{{height:520px;margin:1rem 0}} .mapa iframe{{height:520px!important}}
</style></head><body>
<h1>Observatorio de alegaciones ambientales</h1>
<p class="sub">Prototipo · BOE sección V-B · anuncios publicados entre {desde} y {hasta} · generado {date.today()}</p>
<div class="kpis">
 <div class="kpi"><b>{len(resultados)}</b>proyectos en información pública</div>
 <div class="kpi"><b>{n_geo}</b>geolocalizados</div>
 <div class="kpi"><b>{n_natura}</b>con solape Natura 2000</div>
 <div class="kpi"><b>{sum(1 for r in resultados if r['anuncio']['tramite_ambiental'])}</b>con trámite ambiental explícito</div>
</div>
<div class="mapa">{mapa_html}</div>
<h2>Índice</h2>
<table class="datos"><thead><tr><th>Anuncio</th><th>Fecha</th><th>Categoría</th><th>EIA</th><th>Provincias</th><th>Natura</th><th>Esp. amen.</th><th>Aves</th><th>Plazo</th></tr></thead><tbody>{indice}</tbody></table>
{fichas}
<footer><p style="color:#777;font-size:.85rem">Fuentes: BOE (datos abiertos), Agencia Europea de Medio Ambiente (Natura 2000, versión 2024), GBIF (registros con coordenadas desde 2005, categorías UICN), OpenStreetMap/Nominatim (límites municipales). El solape se calcula sobre el término municipal completo, no sobre la huella exacta del proyecto: es un filtro de atención, no una evaluación.</p></footer>
</body></html>"""
    out = OUTPUT_DIR / nombre
    out.write_text(doc, encoding="utf-8")
    (OUTPUT_DIR / nombre.replace(".html", ".json")).write_text(
        json.dumps(
            [{**r, "geom": mapping(r["geom"]) if r.get("geom") is not None else None,
              "natura": [{k: v for k, v in s.items() if k != "geometry"} for s in r["natura"]]} for r in resultados],
            ensure_ascii=False, indent=1, default=str,
        ),
        encoding="utf-8",
    )
    return out
