"""CLI: python -m observatorio.cli run --days 4"""

from __future__ import annotations

from datetime import date

import typer
from rich.console import Console
from rich.table import Table

from . import boe, extract, geo, natura, plazos, report, site, species
from .config import DOCS_DIR

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
):
    """Descarga el BOE de los últimos días, detecta proyectos, genera el informe y actualiza la web."""
    fin = date.fromisoformat(hasta) if hasta else date.today()
    dias = boe.business_days_back(fin, days)
    candidatos: list[boe.Anuncio] = []
    total_items = 0
    for d in dias:
        try:
            sumario = boe.fetch_sumario(d)
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]{d}: error descargando sumario: {e}[/red]")
            continue
        if not sumario:
            console.print(f"[dim]{d}: sin BOE[/dim]")
            continue
        n = 0
        for a in boe.iter_items(sumario, d):
            total_items += 1
            if extract.es_candidato(a):
                candidatos.append(a)
                n += 1
        console.print(f"{d}: {n} candidatos")
    console.print(f"[bold]{len(candidatos)} candidatos de {total_items} anuncios V-B[/bold]")

    resultados: list[dict] = []
    for a in candidatos:
        try:
            a.texto = boe.fetch_texto(a)
        except Exception as e:  # noqa: BLE001
            console.print(f"  [red]{a.identificador}: error descargando texto: {e}[/red]")
        extract.clasificar(a)
        extract.extraer_datos(a)
        lim, est = plazos.fecha_limite(date.fromisoformat(a.fecha), a.plazo_dias)
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
        site.generar_web(estado, DOCS_DIR)
        console.print(f"[green]Web:[/green] {DOCS_DIR / 'index.html'} · {len(estado['anuncios'])} proyectos en estado")

    t = Table(title="Resumen")
    for c in ("Anuncio", "Cat.", "EIA", "Prov.", "Natura", "Esp.", "Aves", "Límite"):
        t.add_column(c)
    for r in sorted(resultados, key=lambda r: -r["anuncio"]["prioridad"]):
        a = r["anuncio"]
        t.add_row(
            a["identificador"], a["categoria"], "Sí" if a["tramite_ambiental"] else "",
            ", ".join(a["provincias"][:2]), str(len(r["natura"])),
            str(r["especies"].get("n_especies", "")), str(r["especies"].get("n_aves", "")),
            a["fecha_limite"] + ("*" if a["plazo_estimado"] else ""),
        )
    console.print(t)
    console.print(f"[green]Informe:[/green] {out}")


if __name__ == "__main__":
    app()
