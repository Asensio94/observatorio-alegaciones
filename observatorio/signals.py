"""docs/signals.json: this project's facts in the common format of Estado de las IBA (estado-iba, CONTRATO.md).

Every notice and every resolution in data/estado.json becomes one signal, keyed by its bulletin
identifier. A notice reaches a Natura 2000 site through its cadastral footprint when the footprint
has sites in it («parcelas»), and otherwise through the sites of its municipalities («municipio»).
Resolutions carry no geometry: they inherit the sites and precision of the notice they were paired
with. Municipalities go by name, with their provinces to tell homonyms apart; the hub resolves them
to INE codes. The hub also adds the source and the regions, and applies its own time windows.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SOURCE = "observatorio-alegaciones"
COVERAGE = {
    "label": "Toda España, desde el 27 de julio de 2026",
    "sites": None,
    "note": "Anuncios del BOE con trámite ambiental, leídos cada mañana.",
}


def _signal(x: dict, kind: str, precision: str, sites: list[dict], deadline: str | None, status: str | None,
            details: dict) -> dict:
    return {
        "id": x["identificador"], "kind": kind, "date": x["fecha"], "title": x["titulo"], "url": x["url_html"],
        "sites": sites, "municipalities": [],
        "municipality_names": x.get("municipios") or [], "provinces": x.get("provincias") or [],
        "precision": precision, "deadline": deadline, "status": status,
        "value": {"amount": x["potencia_mw"], "unit": "MW"} if x.get("potencia_mw") else None,
        "details": details,
    }


def notice(a: dict) -> dict:
    in_footprint = (a.get("footprint") or {}).get("natura") or []
    natura, precision = (in_footprint, "parcelas") if in_footprint else (a.get("natura") or [], "municipio")
    return _signal(a, "notice", precision, [{"code": s["sitecode"]} for s in natura],
                   deadline=a.get("fecha_limite") or None, status=None,
                   details={"category": a.get("categoria"), "promoter": a.get("promotor") or None,
                            "file": a.get("expediente") or None, "department": a.get("departamento")})


def resolution(r: dict, paired: dict | None) -> dict:
    """`paired` is the notice's signal; a resolution opens no deadline, whatever its own text says."""
    return _signal(r, "resolution", paired["precision"] if paired else "municipio",
                   list(paired["sites"]) if paired else [], deadline=None,
                   status=r.get("sentido_etiqueta") or r.get("sentido"),
                   details={"category": r.get("categoria"), "promoter": r.get("promotor") or None,
                            "file": r.get("expediente") or None, "paired_with": paired["id"] if paired else None})


def build(estado: dict, now: datetime | None = None) -> dict:
    notices = {a["identificador"]: notice(a) for a in estado["anuncios"].values()}
    # Suggested pairings («emparejamiento no confirmado») count too, as on the follow-up page.
    resolutions = [resolution(r, notices.get(r.get("emparejado_con") or ""))
                   for r in estado.get("resoluciones", {}).values()]
    now = now or datetime.now(timezone.utc)
    return {
        "source": SOURCE, "version": 1, "generated": now.strftime("%Y-%m-%dT%H:%MZ"), "coverage": COVERAGE,
        "signals": sorted([*notices.values(), *resolutions], key=lambda s: (s["date"], s["id"])),
    }


def write(estado: dict, docs_dir: Path) -> Path:
    path = docs_dir / "signals.json"
    path.write_text(json.dumps(build(estado), ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return path
