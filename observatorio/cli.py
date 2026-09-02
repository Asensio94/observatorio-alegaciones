"""CLI: python -m observatorio.cli run --days 8"""

from __future__ import annotations

import json
from datetime import date, datetime

import typer
from rich.console import Console
from rich.table import Table

from . import boe, extract, geo, natura, species, report
from .config import OUTPUT_DIR

app = typer.Typer(add_completion=False, help="Observatorio de alegaciones ambientales")
console = Console()


@app.callback()
def _main() -> None:
    """Observatorio de alegaciones ambientales."""


@app.command()
def run(
    days: int = typer.Option(8, help="Días hacia atrás desde --hasta"),
    hasta: str = typer.Option(None, help="Fecha final YYYY-MM-DD (por defecto hoy)"),
    min_prioridad: int = typer.Option(3, help="Prioridad mínima para cruzar con Natura/GBIF"),
    sin_gbif: bool = typer.Option(False, help="Omitir consulta de especies (más rápido)"),
    nombre: str = typer.Option(None, help="Nombre del fichero HTML de salida"),
):
    """Descarga el BOE de los últimos días, detecta proyectos y genera el informe."""
    fin = date.fromisoformat(hasta) if hasta else date.today()
    dias = boe.business_days_back(fin, days)
    candidatos: list[boe.Anuncio] = []
    total_items = 0
    for d in dias:
        sumario = boe.fetch_sumario(d)
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
        a.texto = boe.fetch_texto(a)
        extract.clasificar(a)
        extract.extraer_datos(a)
        r = {"anuncio": a.to_dict(), "geom": None, "natura": [], "especies": {}, "municipios_no_resueltos": []}
        if a.prioridad >= min_prioridad and a.municipios:
            console.print(f"  [cyan]{a.identificador}[/cyan] {a.categoria} · {len(a.municipios)} municipios · {a.provincias[:2]}")
            g, ok, ko = geo.geom_proyecto(a.municipios, a.provincias)
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

    nombre = nombre or f"informe_{dias[0]:%Y%m%d}_{fin:%Y%m%d}.html"
    out = report.generar_informe(resultados, dias[0], fin, nombre)

    t = Table(title="Resumen")
    for c in ("Anuncio", "Cat.", "EIA", "Prov.", "Natura", "Esp.", "Aves", "Plazo"):
        t.add_column(c)
    for r in sorted(resultados, key=lambda r: -r["anuncio"]["prioridad"]):
        a = r["anuncio"]
        t.add_row(
            a["identificador"], a["categoria"], "Sí" if a["tramite_ambiental"] else "",
            ", ".join(a["provincias"][:2]), str(len(r["natura"])),
            str(r["especies"].get("n_especies", "")), str(r["especies"].get("n_aves", "")), str(a["plazo_dias"] or ""),
        )
    console.print(t)
    console.print(f"[green]Informe:[/green] {out}")


if __name__ == "__main__":
    app()
