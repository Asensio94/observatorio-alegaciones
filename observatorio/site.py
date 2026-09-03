"""Estado acumulado y web estática (docs/): alegaciones abiertas, histórico e índice de informes."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import seguimiento
from .config import ESTADO_PATH
from .plazos import dias_restantes
from .report import (
    AVISO_METODO,
    badge,
    badge_estado,
    badge_estado_sentido,
    badge_fuente,
    esc,
    pagina,
    texto_plazo,
)


def cargar_estado() -> dict:
    if ESTADO_PATH.exists():
        estado = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
        estado.setdefault("resoluciones", {})
        return estado
    return {"anuncios": {}, "informes": [], "resoluciones": {}}


def guardar_estado(estado: dict) -> None:
    ESTADO_PATH.parent.mkdir(parents=True, exist_ok=True)
    ESTADO_PATH.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")


def actualizar_estado(resultados: list[dict], informe_rel: str, desde: date, hasta: date) -> dict:
    """Incorpora los resultados de una ejecución al estado acumulado (clave: identificador BOE)."""
    estado = cargar_estado()
    for r in resultados:
        a = dict(r["anuncio"])
        a.pop("texto", None)
        esp = r.get("especies") or {}
        estado["anuncios"][a["identificador"]] = {
            **a,
            "geolocalizado": r.get("geom") is not None,
            "municipios_no_resueltos": r.get("municipios_no_resueltos", []),
            "natura": [{"sitecode": s["sitecode"], "nombre": s["nombre"], "tipo": s["tipo"]} for s in r.get("natura", [])],
            "n_especies": esp.get("n_especies", 0),
            "n_aves": esp.get("n_aves", 0),
            "especies_top": [
                {"scientificName": e["scientificName"], "vernacular_es": e.get("vernacular_es", ""), "categoria_uicn": e["categoria_uicn"], "class": e.get("class", "")}
                for e in esp.get("especies", [])[:12]
            ],
            "informe": informe_rel,
            "actualizado": date.today().isoformat(),
        }
    estado["informes"] = [i for i in estado["informes"] if i["fichero"] != informe_rel]
    estado["informes"].append({"fichero": informe_rel, "desde": desde.isoformat(), "hasta": hasta.isoformat(), "generado": date.today().isoformat(), "n": len(resultados)})
    estado["informes"].sort(key=lambda i: i["hasta"], reverse=True)
    guardar_estado(estado)
    return estado


def _celda_estado(a: dict) -> str:
    """Estado de tramitación y, si se ha localizado, la resolución que cerró el expediente."""
    clave, etiqueta = seguimiento.estado_proyecto(a)
    out = badge_estado(clave, etiqueta)
    r = a.get("resolucion") or a.get("resolucion_posible")
    if r:
        aviso = "" if a.get("resolucion") else "<br><small class=warn>emparejamiento no confirmado</small>"
        out += (
            f"<br><small><a href='{esc(r['url_html'])}' target='_blank' rel='noopener'>"
            f"{esc(r['tipo_etiqueta'])} de {esc(r['fecha'])} en el {esc(r.get('fuente', 'BOE'))}</a></small>{aviso}"
        )
    return out


def _fila(a: dict) -> str:
    aves = ", ".join(
        f"<i>{esc(e['scientificName'])}</i>" + (f" ({esc(e['vernacular_es'])})" if e.get("vernacular_es") else "")
        for e in a.get("especies_top", []) if e.get("class") == "Aves"
    )[:400]
    natura = "; ".join(f"{esc(s['nombre'])} ({esc(s['tipo'])})" for s in a.get("natura", [])[:4])
    if len(a.get("natura", [])) > 4:
        natura += f" y {len(a['natura']) - 4} más"
    return (
        f"<tr><td>{texto_plazo(a)}</td>"
        f"<td>{_celda_estado(a)}</td>"
        f"<td>{badge(a['categoria'])}{'<br><small>EIA</small>' if a.get('tramite_ambiental') else ''}<br>{badge_fuente(a.get('fuente', 'BOE'))}</td>"
        f"<td><a href='{esc(a['informe'])}#{esc(a['identificador'])}'>{esc(a['identificador'])}</a><br><small>{esc(a['titulo'][:220])}…</small><br>"
        f"<small><a href='{esc(a['url_html'])}' target='_blank' rel='noopener'>Anuncio en el {esc(a.get('fuente', 'BOE'))}</a></small></td>"
        f"<td>{esc(', '.join(a.get('provincias', [])[:3]))}<br><small>{esc(', '.join(a.get('municipios', [])[:6]))}</small></td>"
        f"<td>{natura or '<i>ninguno</i>'}</td>"
        f"<td>{a.get('n_especies', 0)} esp. / {a.get('n_aves', 0)} aves<br><small>{aves}</small></td></tr>"
    )


def _tabla(filas: list[str]) -> str:
    if not filas:
        return "<p><i>Nada que mostrar.</i></p>"
    return (
        "<div class='wrap'><table class='datos'><thead><tr><th>Fecha límite (est.)</th><th>Estado</th><th>Tipo / fuente</th><th>Anuncio</th>"
        "<th>Provincias / municipios</th><th>Natura 2000 en el municipio</th><th>Especies amenazadas (UICN)</th></tr></thead>"
        f"<tbody>{''.join(filas)}</tbody></table></div>"
    )


def generar_web(estado: dict, docs_dir: Path) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)
    hoy = date.today()
    anuncios = list(estado["anuncios"].values())

    def _lim(a):
        return date.fromisoformat(a["fecha_limite"]) if a.get("fecha_limite") else hoy

    abiertos = sorted((a for a in anuncios if dias_restantes(_lim(a), hoy) >= 0), key=_lim)
    cerrados = sorted((a for a in anuncios if dias_restantes(_lim(a), hoy) < 0), key=_lim, reverse=True)
    urgentes = [a for a in abiertos if dias_restantes(_lim(a), hoy) <= 7]
    ultimo_mapa = estado["informes"][0]["fichero"].replace(".html", "_mapa.html") if estado["informes"] else ""

    nav = ('<nav><a href="index.html">Alegaciones abiertas</a><a href="seguimiento.html">Seguimiento</a>'
           '<a href="litoral.html">Litoral</a><a href="historico.html">Histórico</a>'
           '<a href="https://github.com/Asensio94/observatorio-alegaciones">Código y datos</a></nav>')
    cuerpo = f"""
<div class="kpis">
 <div class="kpi"><b>{len(abiertos)}</b>alegaciones abiertas</div>
 <div class="kpi"><b>{len(urgentes)}</b>vencen en 7 días o menos</div>
 <div class="kpi"><b>{sum(1 for a in abiertos if a.get('natura'))}</b>con Natura 2000 en el municipio</div>
 <div class="kpi"><b>{len(anuncios)}</b>proyectos seguidos en total</div>
 <div class="kpi"><b>{sum(1 for a in abiertos if a.get('fuente', 'BOE') == 'BOE')} / {sum(1 for a in abiertos if a.get('fuente') == 'BOC')}</b>abiertas BOE / BOC Cantabria</div>
 <div class="kpi"><b>{len(estado.get('resoluciones', {}))}</b><a href="seguimiento.html">resoluciones seguidas</a></div>
</div>
<div class="aviso">{AVISO_METODO}</div>
{f'<div class="mapa"><iframe src="{esc(ultimo_mapa)}" loading="lazy"></iframe></div>' if ultimo_mapa else ''}
<h2>Proyectos con plazo de alegaciones abierto</h2>
{_tabla([_fila(a) for a in abiertos])}
<h2>Informes diarios</h2>
<ul>{''.join(f"<li><a href='{esc(i['fichero'])}'>Anuncios del {esc(i['desde'])} al {esc(i['hasta'])}</a> · {i['n']} proyectos · generado {esc(i['generado'])}</li>" for i in estado['informes'][:30])}</ul>
<h2>Qué es esto</h2>
<p>Cada mañana laborable se leen los anuncios de información pública del <b>BOE</b> (sección V-B) y del <b>Boletín Oficial de Cantabria</b> (secciones 5 y 7), se detectan proyectos con posible afección ambiental
(eólica, fotovoltaica, líneas eléctricas, minería, infraestructuras, costas, hidráulica), se localizan sus municipios y se cruzan con la Red Natura 2000
y con los registros de especies animales amenazadas. El objetivo es que los grupos locales y las organizaciones de conservación conozcan los proyectos
<b>mientras aún se puede alegar</b>. Proyecto abierto: el código, los datos y las mejoras están en GitHub.</p>"""
    (docs_dir / "index.html").write_text(
        pagina("Observatorio de alegaciones ambientales", f"Alegaciones abiertas a {hoy:%d/%m/%Y} · fuentes: BOE y BOC (Cantabria)", cuerpo, nav),
        encoding="utf-8",
    )
    cuerpo_h = f"<h2>Plazos cerrados ({len(cerrados)})</h2>{_tabla([_fila(a) for a in cerrados])}"
    (docs_dir / "historico.html").write_text(
        pagina("Observatorio de alegaciones ambientales · histórico", f"Proyectos cuyo plazo estimado ya ha vencido · {hoy:%d/%m/%Y}", cuerpo_h, nav),
        encoding="utf-8",
    )
    (docs_dir / "seguimiento.html").write_text(_pagina_seguimiento(estado, cerrados, hoy, nav), encoding="utf-8")
    (docs_dir / ".nojekyll").write_text("", encoding="utf-8")


COMO_SEGUIR = """
<h2>Cómo se conoce el resultado de una alegación</h2>
<p>En el trámite de información pública <b>nadie contesta individualmente</b> a quien alega: no es un recurso.
Lo que sí es obligatorio es esto, y es lo que esta página rastrea:</p>
<ul>
 <li>El <b>artículo 41 de la Ley 21/2013</b> exige que la declaración de impacto ambiental incluya un resumen del
   resultado de la información pública y de las consultas, y <b>cómo se han tenido en consideración</b>. Ahí se
   comprueba si una alegación se leyó o se archivó.</li>
 <li>La declaración de impacto ambiental <b>se publica en el boletín oficial</b> correspondiente, y las
   autorizaciones administrativas de instalaciones eléctricas también (artículo 125 del Real Decreto 1955/2000).
   Por eso el resultado se detecta leyendo la misma fuente que abrió el plazo.</li>
 <li>La declaración de impacto ambiental <b>no se puede recurrir por sí sola</b>: el recurso se dirige contra el
   acto que autoriza el proyecto. Y ese acto abre plazos cortos, normalmente <b>un mes</b> para el recurso
   administrativo y <b>dos meses</b> para el contencioso, contados desde su publicación o notificación. Quien no
   vigila el boletín pierde el plazo sin enterarse.</li>
 <li>Para ver los papeles: la <b>Ley 27/2006</b> reconoce el derecho de acceso a la información ambiental sin
   necesidad de justificar el interés, con plazo de un mes. Es la vía para pedir el informe de contestación a
   las alegaciones.</li>
 <li>Referencia de tiempos: el artículo 33 de la Ley 21/2013 da al órgano ambiental <b>cuatro meses</b> para
   formular la declaración, prorrogables por dos más. Los expedientes marcados como demorados llevan más de seis
   meses cerrados sin resolución publicada.</li>
</ul>
<p class="aviso">El emparejamiento entre una resolución y su información pública es automático (expediente,
promotor, municipios, potencia y palabras distintivas del título). Los emparejamientos por debajo del umbral
de confianza se marcan como no confirmados, y hay resoluciones que corresponden a expedientes anteriores al
arranque del observatorio, por lo que aparecen sin asociar. Comprueba siempre el anuncio oficial.</p>
"""


def _pagina_seguimiento(estado: dict, cerrados: list[dict], hoy: date, nav: str) -> str:
    resoluciones = list(estado.get("resoluciones", {}).values())
    sueltas = sorted((r for r in resoluciones if not r.get("emparejado_con")), key=lambda r: r["fecha"], reverse=True)
    con_res = [a for a in cerrados if a.get("resolucion") or a.get("resolucion_posible")]
    pendientes = [a for a in cerrados if not (a.get("resolucion") or a.get("resolucion_posible"))]
    demorados = [a for a in pendientes if seguimiento.estado_proyecto(a, hoy)[0] == "demorado"]
    filas_sueltas = "".join(
        f"<tr><td>{esc(r['fecha'])}</td><td>{badge_fuente(r.get('fuente', 'BOE'))}</td>"
        f"<td>{esc(r['tipo_etiqueta'])}<br>{badge_estado_sentido(r['sentido'], r['sentido_etiqueta'])}</td>"
        f"<td>{esc(', '.join(r.get('municipios', [])[:5])) or '<i>sin municipio detectado</i>'}"
        f"{'<br><small>' + esc(r['expediente']) + '</small>' if r.get('expediente') else ''}</td>"
        f"<td><a href='{esc(r['url_html'])}' target='_blank' rel='noopener'>{esc(r['identificador'])}</a>"
        f"<br><small>{esc(r['titulo'][:230])}…</small></td></tr>"
        for r in sueltas[:80]
    )
    cuerpo = f"""
<div class="kpis">
 <div class="kpi"><b>{len(resoluciones)}</b>resoluciones detectadas</div>
 <div class="kpi"><b>{len(con_res)}</b>expedientes seguidos con resolución localizada</div>
 <div class="kpi"><b>{len(pendientes)}</b>con el plazo cerrado y sin resolución</div>
 <div class="kpi"><b>{len(demorados)}</b>sin resolución tras más de {seguimiento.MESES_DIA} meses</div>
</div>
{COMO_SEGUIR}
<h2>Expedientes seguidos cuyo plazo ya cerró ({len(cerrados)})</h2>
{_tabla([_fila(a) for a in sorted(con_res + pendientes, key=lambda a: a.get('fecha_limite', ''), reverse=True)])}
<h2>Resoluciones detectadas sin expediente asociado ({len(sueltas)})</h2>
<p>Casi todas resuelven trámites de información pública anteriores al arranque del observatorio, o de
comunidades autónomas cuyos boletines aún no se leen. Se publican igualmente porque son el resultado real de
proyectos en tramitación y porque dejan ver el ritmo y el sentido de lo que se está autorizando.</p>
<div class='wrap'><table class='datos'><thead><tr><th>Fecha</th><th>Fuente</th><th>Tipo y sentido</th>
<th>Municipios / expediente</th><th>Resolución</th></tr></thead><tbody>{filas_sueltas}</tbody></table></div>
"""
    return pagina(
        "Observatorio de alegaciones ambientales · seguimiento",
        f"Qué ha pasado con los proyectos: declaraciones de impacto ambiental y autorizaciones · {hoy:%d/%m/%Y}",
        cuerpo,
        nav,
    )
