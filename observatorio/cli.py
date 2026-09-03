"""CLI: python -m observatorio.cli run --days 4"""

from __future__ import annotations

from datetime import date

import typer
from rich.console import Console
from rich.table import Table

from . import boc_cantabria, boe, extract, geo, litoral, natura, plazos, report, seguimiento, site, species
from .config import DATA_DIR, DOCS_DIR, FUENTES

app = typer.Typer(add_completion=False, help="Observatorio de alegaciones ambientales")
console = Console()


@app.callback()
def _main() -> None:
    """Observatorio de alegaciones ambientales."""


@app.command()
def run(
    days: int = typer.Option(4, help="Días hacia atrás desde --hasta (incluidos)"),
    hasta: str = typer.Option(None, help="Fecha final YYYY-MM-DD (por defecto hoy)"),
    min_prioridad: int = typer.Option(3, help="Prioridad mínima para cruzar con Natura/GBIF"),
    sin_gbif: bool = typer.Option(False, help="Omitir consulta de especies (más rápido)"),
    sin_web: bool = typer.Option(False, help="No actualizar estado ni web (solo informe)"),
    fuentes: str = typer.Option(",".join(FUENTES), help="Fuentes separadas por coma: " + ", ".join(FUENTES)),
):
    """Descarga el BOE de los últimos días, detecta proyectos, genera el informe y actualiza la web."""
    fin = date.fromisoformat(hasta) if hasta else date.today()
    dias = boe.business_days_back(fin, days)
    candidatos: list[boe.Anuncio] = []
    total_items = 0
    activas = {f.strip() for f in fuentes.split(",") if f.strip()}
    desconocidas = activas - set(FUENTES)
    if desconocidas:
        raise typer.BadParameter(f"Fuentes desconocidas: {', '.join(sorted(desconocidas))}")
    for d in dias:
        resumen = []
        if "boe" in activas:
            try:
                sumario = boe.fetch_sumario(d)
            except Exception as e:  # noqa: BLE001
                console.print(f"[red]{d}: error descargando sumario BOE: {e}[/red]")
                sumario = None
            n = 0
            if sumario:
                for a in boe.iter_items(sumario, d):
                    total_items += 1
                    if extract.es_candidato(a):
                        candidatos.append(a)
                        n += 1
            resumen.append(f"BOE {n if sumario else '-'}")
        if "boc_cantabria" in activas:
            try:
                anuncios_boc = boc_cantabria.anuncios_dia(d)
            except boc_cantabria.BOCInaccesible:
                console.print(f"[yellow]{d}: BOC sin volcado local y no accesible desde esta red (ver README, relevo local)[/yellow]")
                anuncios_boc = None
            except Exception as e:  # noqa: BLE001
                console.print(f"[red]{d}: error descargando BOC: {e}[/red]")
                anuncios_boc = None
            n = 0
            if anuncios_boc:
                for a in anuncios_boc:
                    total_items += 1
                    if extract.es_candidato(a):
                        candidatos.append(a)
                        n += 1
            resumen.append(f"BOC {n if anuncios_boc is not None else '-'}")
        console.print(f"{d}: candidatos " + " · ".join(resumen))
    console.print(f"[bold]{len(candidatos)} candidatos de {total_items} anuncios revisados[/bold]")

    resultados: list[dict] = []
    for a in candidatos:
        if a.fuente == "BOE" and not a.texto:
            try:
                a.texto = boe.fetch_texto(a)
            except Exception as e:  # noqa: BLE001
                console.print(f"  [red]{a.identificador}: error descargando texto: {e}[/red]")
        extract.clasificar(a)
        extract.extraer_datos(a)
        comunidad = None
        if a.fuente == boc_cantabria.FUENTE:
            boc_cantabria.completar_geo(a)
            comunidad = boc_cantabria.COMUNIDAD
        lim, est = plazos.fecha_limite(date.fromisoformat(a.fecha), a.plazo_dias, comunidad)
        a.fecha_limite, a.plazo_estimado = lim.isoformat(), est
        r = {"anuncio": a.to_dict(), "geom": None, "natura": [], "especies": {}, "municipios_no_resueltos": []}
        if a.prioridad >= min_prioridad and a.municipios:
            console.print(f"  [cyan]{a.identificador}[/cyan] {a.categoria} · {len(a.municipios)} municipios · {a.provincias[:2]} · límite {a.fecha_limite}")
            try:
                g, ok, ko = geo.geom_proyecto(a.municipios, a.provincias)
            except Exception as e:  # noqa: BLE001
                console.print(f"    [red]Geolocalización error: {e}[/red]")
                g, ok, ko = None, [], list(a.municipios)
            r["geom"] = g
            r["municipios_no_resueltos"] = ko
            if g is not None:
                try:
                    r["natura"] = natura.sitios_natura(g)
                except Exception as e:  # noqa: BLE001
                    console.print(f"    [red]Natura error: {e}[/red]")
                if not sin_gbif:
                    try:
                        r["especies"] = species.especies_amenazadas(g)
                    except Exception as e:  # noqa: BLE001
                        console.print(f"    [red]GBIF error: {e}[/red]")
                console.print(f"    Natura: {len(r['natura'])} · especies amenazadas: {r['especies'].get('n_especies', '-')}")
        else:
            console.print(f"  [dim]{a.identificador} {a.categoria} prio={a.prioridad} munis={len(a.municipios)} (sin cruce)[/dim]")
        resultados.append(r)

    nombre = f"informe_{dias[0]:%Y%m%d}_{fin:%Y%m%d}.html"
    out = report.generar_informe(resultados, dias[0], fin, DOCS_DIR / "informes", nombre)
    if not sin_web:
        estado = site.actualizar_estado(resultados, f"informes/{nombre}", dias[0], fin)
        res = seguimiento.recolectar(dias, activas, aviso=lambda s: console.print(f"[yellow]{s}[/yellow]"))
        nuevas, firmes = seguimiento.incorporar(estado, res)
        site.guardar_estado(estado)
        console.print(f"[cyan]Resoluciones:[/cyan] {len(res)} en estos días ({nuevas} nuevas) · {firmes} emparejadas con expedientes seguidos")
        site.generar_web(estado, DOCS_DIR)
        console.print(f"[green]Web:[/green] {DOCS_DIR / 'index.html'} · {len(estado['anuncios'])} proyectos en estado")

    t = Table(title="Resumen")
    for c in ("Anuncio", "Fuente", "Cat.", "EIA", "Prov.", "Natura", "Esp.", "Aves", "Límite"):
        t.add_column(c)
    for r in sorted(resultados, key=lambda r: -r["anuncio"]["prioridad"]):
        a = r["anuncio"]
        t.add_row(
            a["identificador"], a["fuente"], a["categoria"], "Sí" if a["tramite_ambiental"] else "",
            ", ".join(a["provincias"][:2]), str(len(r["natura"])),
            str(r["especies"].get("n_especies", "")), str(r["especies"].get("n_aves", "")),
            a["fecha_limite"] + ("*" if a["plazo_estimado"] else ""),
        )
    console.print(t)
    console.print(f"[green]Informe:[/green] {out}")


@app.command("litoral")
def cmd_litoral(
    days: int = typer.Option(20, help="Días hacia atrás desde --hasta (incluidos)"),
    hasta: str = typer.Option(None, help="Fecha final YYYY-MM-DD (por defecto hoy)"),
    min_puntos: int = typer.Option(3, help="Puntos de señal mínimos para cruzar con Natura/GBIF"),
    sin_gbif: bool = typer.Option(False, help="Omitir consulta de especies (más rápido)"),
    sin_web: bool = typer.Option(False, help="No actualizar el estado del litoral ni su página"),
    fuentes: str = typer.Option(",".join(FUENTES), help="Fuentes separadas por coma: " + ", ".join(FUENTES)),
):
    """Vertical del litoral: costas, servidumbre de protección, planeamiento y suelo turístico."""
    fin = date.fromisoformat(hasta) if hasta else date.today()
    activas = {f.strip() for f in fuentes.split(",") if f.strip()}
    desconocidas = activas - set(FUENTES)
    if desconocidas:
        raise typer.BadParameter(f"Fuentes desconocidas: {', '.join(sorted(desconocidas))}")
    dias = boe.business_days_back(fin, days)
    candidatos: list[boe.Anuncio] = []
    revisados = 0
    for d in dias:
        resumen = []
        if "boe" in activas:
            try:
                sumario = boe.fetch_sumario(d)
            except Exception as e:  # noqa: BLE001
                console.print(f"[red]{d}: error descargando sumario BOE: {e}[/red]")
                sumario = None
            n = 0
            if sumario:
                for a in boe.iter_items(sumario, d, secciones=litoral.SECCIONES_BOE):
                    revisados += 1
                    # El filtro de ámbito va antes de bajar el texto: en la V-B el BOE mezcla las
                    # demarcaciones de costas con las confederaciones hidrográficas.
                    if litoral.es_candidato(a) and litoral.en_ambito(a):
                        candidatos.append(a); n += 1
            resumen.append(f"BOE {n if sumario else '-'}")
        if "boc_cantabria" in activas:
            try:
                anuncios_boc = boc_cantabria.anuncios_dia(d)
            except boc_cantabria.BOCInaccesible:
                console.print(f"[yellow]{d}: BOC sin volcado local y no accesible desde esta red[/yellow]")
                anuncios_boc = None
            except Exception as e:  # noqa: BLE001
                console.print(f"[red]{d}: error descargando BOC: {e}[/red]")
                anuncios_boc = None
            n = 0
            for a in anuncios_boc or []:
                revisados += 1
                if litoral.es_candidato(a):
                    candidatos.append(a); n += 1
            resumen.append(f"BOC {n if anuncios_boc is not None else '-'}")
        console.print(f"{d}: " + " · ".join(resumen))
    console.print(f"[bold]{len(candidatos)} candidatos de {revisados} anuncios revisados[/bold]")

    resultados: list[dict] = []
    for a in candidatos:
        if a.fuente == "BOE" and not a.texto:
            try:
                a.texto = boe.fetch_texto(a)
            except Exception as e:  # noqa: BLE001
                console.print(f"  [red]{a.identificador}: error descargando texto: {e}[/red]")
        litoral.clasificar(a)
        extract.extraer_datos(a)
        comunidad = None
        if a.fuente == boc_cantabria.FUENTE:
            boc_cantabria.completar_geo(a)
            comunidad = boc_cantabria.COMUNIDAD
        sen = litoral.senales(a)
        pts = litoral.puntos(sen)
        plazo = (a.plazo_dias or litoral.plazo_por_defecto(a.categoria)) if litoral.abre_plazo(a) else None
        if plazo is None:  # la declaración o el informe ambiental estratégico es resolución, no trámite
            a.fecha_limite, a.plazo_estimado = "", True
        else:
            lim, _ = plazos.fecha_limite(date.fromisoformat(a.fecha), plazo, comunidad)
            a.fecha_limite, a.plazo_estimado = lim.isoformat(), a.plazo_dias is None
        r = {"anuncio": a.to_dict(), "senales": sen, "puntos": pts, "natura": [], "especies": {}}
        if pts >= min_puntos and a.municipios:
            console.print(f"  [cyan]{a.identificador}[/cyan] {a.categoria} · {pts} pts · {', '.join(a.municipios[:2])}")
            try:
                g, _ok, _ko = geo.geom_proyecto(a.municipios, a.provincias)
            except Exception as e:  # noqa: BLE001
                console.print(f"    [red]Geolocalización error: {e}[/red]")
                g = None
            if g is not None:
                try:
                    r["natura"] = natura.sitios_natura(g)
                except Exception as e:  # noqa: BLE001
                    console.print(f"    [red]Natura error: {e}[/red]")
                if not sin_gbif:
                    try:
                        r["especies"] = species.especies_amenazadas(g)
                    except Exception as e:  # noqa: BLE001
                        console.print(f"    [red]GBIF error: {e}[/red]")
        else:
            console.print(f"  [dim]{a.identificador} {a.categoria} {pts} pts (sin cruce)[/dim]")
        resultados.append(r)

    t = Table(title=f"Litoral · {dias[0]} a {fin}")
    for c in ("Anuncio", "Fuente", "Trámite", "Pts", "Municipio", "Señal principal", "Límite"):
        t.add_column(c)
    for r in sorted(resultados, key=lambda r: -r["puntos"])[:40]:
        a = r["anuncio"]
        t.add_row(
            a["identificador"], a["fuente"], a["categoria"], str(r["puntos"]),
            ", ".join(a["municipios"][:2]) or "-",
            r["senales"][0]["etiqueta"] if r["senales"] else "-",
            (a["fecha_limite"] or "-") + ("*" if a["plazo_estimado"] and a["fecha_limite"] else ""),
        )
    console.print(t)
    if not sin_web:
        estado = litoral.cargar_estado()
        nuevas = litoral.actualizar_estado(estado, resultados)
        litoral.guardar_estado(estado)
        litoral.generar_web(estado, DOCS_DIR)
        console.print(f"[green]Litoral:[/green] {len(estado['anuncios'])} expedientes en estado ({nuevas} nuevos) · {DOCS_DIR / 'litoral.html'}")


@app.command()
def fetch(
    days: int = typer.Option(10, help="Días hacia atrás desde --hasta (incluidos)"),
    hasta: str = typer.Option(None, help="Fecha final YYYY-MM-DD (por defecto hoy)"),
):
    """Descarga el BOC de Cantabria y guarda el volcado JSON en data/fuentes/ (ejecutar desde España y subir al repo)."""
    fin = date.fromisoformat(hasta) if hasta else date.today()
    nuevos = 0
    for d in boe.business_days_back(fin, days):
        store = boc_cantabria.STORE / f"{d:%Y%m%d}.json"
        existia = store.exists()
        try:
            lst = boc_cantabria.anuncios_dia(d)
        except boc_cantabria.BOCInaccesible as e:
            console.print(f"[red]{d}: {e}[/red]")
            raise typer.Exit(2)
        if not existia:
            nuevos += 1
        console.print(f"{d}: {'sin BOC' if lst is None else f'{len(lst)} anuncios (secc. 5 y 7)'}{'' if existia else ' · guardado'}")
    console.print(f"[green]{nuevos} días nuevos en {boc_cantabria.STORE}[/green]")


@app.command()
def resoluciones(
    days: int = typer.Option(60, help="Días hacia atrás desde --hasta (incluidos)"),
    hasta: str = typer.Option(None, help="Fecha final YYYY-MM-DD (por defecto hoy)"),
    fuentes: str = typer.Option(",".join(FUENTES), help="Fuentes separadas por coma: " + ", ".join(FUENTES)),
    sin_web: bool = typer.Option(False, help="No regenerar la web"),
):
    """Rastrea resoluciones (declaraciones e informes de impacto ambiental, autorizaciones) y las empareja
    con los expedientes ya seguidos. Sirve para rellenar hacia atrás sin repetir todo el análisis."""
    fin = date.fromisoformat(hasta) if hasta else date.today()
    activas = {f.strip() for f in fuentes.split(",") if f.strip()}
    desconocidas = activas - set(FUENTES)
    if desconocidas:
        raise typer.BadParameter(f"Fuentes desconocidas: {', '.join(sorted(desconocidas))}")
    dias = boe.business_days_back(fin, days)
    res = seguimiento.recolectar(dias, activas, aviso=lambda s: console.print(f"[yellow]{s}[/yellow]"))
    estado = site.cargar_estado()
    nuevas, firmes = seguimiento.incorporar(estado, res)
    site.guardar_estado(estado)
    t = Table(title=f"Resoluciones del {dias[0]} al {fin}")
    for c in ("Fecha", "Fuente", "Tipo", "Sentido", "Expediente", "Municipios", "Empareja con", "Pts"):
        t.add_column(c)
    for r in sorted(res, key=lambda r: r["fecha"], reverse=True)[:40]:
        g = estado["resoluciones"][r["identificador"]]
        t.add_row(
            r["fecha"], r.get("fuente", "BOE"), r["tipo"], r["sentido"] or "-", (r.get("expediente") or "-")[:20],
            ", ".join(r.get("municipios", [])[:2]) or "-",
            (g["emparejado_con"] or "-") + (" (firme)" if g["firme"] else ""), str(g["puntos"]),
        )
    console.print(t)
    console.print(f"[green]{len(res)} resoluciones ({nuevas} nuevas) · {firmes} emparejadas con expedientes seguidos[/green]")
    if not sin_web:
        site.generar_web(estado, DOCS_DIR)
        console.print(f"[green]Web:[/green] {DOCS_DIR / 'seguimiento.html'}")


# Registro privado de escritos propios. No se versiona (ver .gitignore): la web pública sigue todos los
# expedientes, y con qué proyectos se ha alegado uno mismo no tiene por qué estar publicado.
MIS_ALEGACIONES_PATH = DATA_DIR / "mis_alegaciones.json"


@app.command("mis-alegaciones")
def mis_alegaciones():
    """Estado de los escritos propios: plazo, si ya se presentó y qué se ha resuelto desde entonces."""
    import json

    if not MIS_ALEGACIONES_PATH.exists():
        console.print(f"[yellow]No hay registro en {MIS_ALEGACIONES_PATH}.[/yellow]")
        console.print('Crea una lista de objetos con: proyecto, expediente, identificador, plazo, presentada, escrito, notas.')
        raise typer.Exit(1)
    registro = json.loads(MIS_ALEGACIONES_PATH.read_text(encoding="utf-8"))
    estado = site.cargar_estado()
    hoy = date.today()
    t = Table(title="Mis alegaciones")
    for c in ("Proyecto", "Expediente", "Plazo", "Presentada", "Estado del expediente", "Resolución"):
        t.add_column(c)
    for m in registro:
        a = estado["anuncios"].get(m.get("identificador", ""))
        if a is None:  # el registro puede apuntar solo al expediente
            a = next((x for x in estado["anuncios"].values() if x.get("expediente") and x["expediente"] == m.get("expediente")), None)
        etiqueta = seguimiento.estado_proyecto(a, hoy)[1] if a else "no seguido por el observatorio"
        r = (a or {}).get("resolucion") or (a or {}).get("resolucion_posible") or {}
        plazo = m.get("plazo") or (a or {}).get("fecha_limite") or "-"
        aviso = ""
        if plazo != "-" and not m.get("presentada"):
            d = (date.fromisoformat(plazo) - hoy).days
            aviso = f" [red](quedan {d} días)[/red]" if 0 <= d <= 10 else (" [red](vencido)[/red]" if d < 0 else "")
        t.add_row(
            m.get("proyecto", "-"), m.get("expediente", "-"), plazo + aviso,
            m.get("presentada") or "[yellow]pendiente[/yellow]", etiqueta,
            f"{r.get('tipo_etiqueta', '')} {r.get('fecha', '')} {r.get('sentido_etiqueta', '')}".strip() or "-",
        )
    console.print(t)
    console.print(
        "\nRecuerda: la declaración de impacto ambiental no se recurre por sí sola, y contra la autorización\n"
        "del proyecto suele haber un mes para el recurso administrativo y dos para el contencioso."
    )


if __name__ == "__main__":
    app()
