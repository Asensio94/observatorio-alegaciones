"""Estado acumulado y web estática (docs/): alegaciones abiertas, histórico e índice de informes."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .config import ESTADO_PATH
from .plazos import dias_restantes
from .report import AVISO_METODO, badge, esc, pagina, texto_plazo


def cargar_estado() -> dict:
    if ESTADO_PATH.exists():
        return json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
    return {"anuncios": {}, "informes": []}


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
    ESTADO_PATH.parent.mkdir(parents=True, exist_ok=True)
    ESTADO_PATH.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    return estado


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
        f"<td>{badge(a['categoria'])}{'<br><small>EIA</small>' if a.get('tramite_ambiental') else ''}</td>"
        f"<td><a href='{esc(a['informe'])}#{esc(a['identificador'])}'>{esc(a['identificador'])}</a><br><small>{esc(a['titulo'][:220])}…</small><br>"
        f"<small><a href='{esc(a['url_html'])}' target='_blank' rel='noopener'>Anuncio en el BOE</a></small></td>"
        f"<td>{esc(', '.join(a.get('provincias', [])[:3]))}<br><small>{esc(', '.join(a.get('municipios', [])[:6]))}</small></td>"
        f"<td>{natura or '<i>ninguno</i>'}</td>"
        f"<td>{a.get('n_especies', 0)} esp. / {a.get('n_aves', 0)} aves<br><small>{aves}</small></td></tr>"
    )


def _tabla(filas: list[str]) -> str:
    if not filas:
        return "<p><i>Nada que mostrar.</i></p>"
    return (
        "<div class='wrap'><table class='datos'><thead><tr><th>Fecha límite (est.)</th><th>Tipo</th><th>Anuncio</th>"
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

    nav = '<nav><a href="index.html">Alegaciones abiertas</a><a href="historico.html">Histórico</a><a href="https://github.com/Asensio94/observatorio-alegaciones">Código y datos</a></nav>'
    cuerpo = f"""
<div class="kpis">
 <div class="kpi"><b>{len(abiertos)}</b>alegaciones abiertas</div>
 <div class="kpi"><b>{len(urgentes)}</b>vencen en 7 días o menos</div>
 <div class="kpi"><b>{sum(1 for a in abiertos if a.get('natura'))}</b>con Natura 2000 en el municipio</div>
 <div class="kpi"><b>{len(anuncios)}</b>proyectos seguidos en total</div>
</div>
<div class="aviso">{AVISO_METODO}</div>
{f'<div class="mapa"><iframe src="{esc(ultimo_mapa)}" loading="lazy"></iframe></div>' if ultimo_mapa else ''}
<h2>Proyectos con plazo de alegaciones abierto</h2>
{_tabla([_fila(a) for a in abiertos])}
<h2>Informes diarios</h2>
<ul>{''.join(f"<li><a href='{esc(i['fichero'])}'>Anuncios del {esc(i['desde'])} al {esc(i['hasta'])}</a> · {i['n']} proyectos · generado {esc(i['generado'])}</li>" for i in estado['informes'][:30])}</ul>
<h2>Qué es esto</h2>
<p>Cada mañana laborable se leen los anuncios de información pública del BOE (sección V-B), se detectan proyectos con posible afección ambiental
(eólica, fotovoltaica, líneas eléctricas, minería, infraestructuras, costas, hidráulica), se localizan sus municipios y se cruzan con la Red Natura 2000
y con los registros de especies animales amenazadas. El objetivo es que los grupos locales y las organizaciones de conservación conozcan los proyectos
<b>mientras aún se puede alegar</b>. Proyecto abierto: el código, los datos y las mejoras están en GitHub.</p>"""
    (docs_dir / "index.html").write_text(
        pagina("Observatorio de alegaciones ambientales", f"Alegaciones abiertas a {hoy:%d/%m/%Y} · fuente: BOE", cuerpo, nav),
        encoding="utf-8",
    )
    cuerpo_h = f"<h2>Plazos cerrados ({len(cerrados)})</h2>{_tabla([_fila(a) for a in cerrados])}"
    (docs_dir / "historico.html").write_text(
        pagina("Observatorio de alegaciones ambientales · histórico", f"Proyectos cuyo plazo estimado ya ha vencido · {hoy:%d/%m/%Y}", cuerpo_h, nav),
        encoding="utf-8",
    )
    (docs_dir / ".nojekyll").write_text("", encoding="utf-8")
