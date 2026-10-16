"""docs/signals.json: this project's facts in the common format of Estado de las IBA (estado-iba, CONTRATO.md).

Every notice and every resolution in data/estado.json becomes one signal, keyed by its bulletin
identifier. A notice reaches a Natura 2000 site through its cadastral footprint when the footprint
has sites in it («parcelas»), and otherwise through the sites of its municipalities («municipio»).
Resolutions carry no geometry: they inherit the sites and precision of the notice they were paired
with. Municipalities go by name, with their provinces to tell homonyms apart; the hub resolves them
to INE codes. The hub also adds the source and the regions, and applies its own time windows.

France (data/estado_fr.json, see fr_projets) goes in the same list. Every signal says its country
(«ES» or «FR»); a French notice already carries its municipalities as INSEE codes (five characters,
2A/2B in Corsica), its departments in `provinces`, and its precision: «municipio» when it is placed by
its commune, «perimetro» when the register gives the project's own polygon. The `country` field and the
INSEE codes need version 2 of the contract; until estado-iba publishes it, the document says version 1.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# The state is already scrubbed when it is loaded; applied again here, since this file is the contract.
from .privacy import promoter

SOURCE = "observatorio-alegaciones"
VERSION = 1
COVERAGE = {
    "label": "Toda España, desde el 27 de julio de 2026",
    "sites": None,
    "note": "Anuncios del BOE con trámite ambiental, leídos cada mañana.",
}
COVERAGE_WITH_FRANCE = {
    "label": "Toda España, desde el 27 de julio de 2026; Francia, consultas públicas desde el 1 de enero de 2026",
    "sites": None,
    "note": "Anuncios del BOE con trámite ambiental y consultas de projets-environnement.gouv.fr, leídos cada mañana.",
}


def _signal(x: dict, kind: str, precision: str, sites: list[dict], deadline: str | None, status: str | None,
            details: dict) -> dict:
    country = x.get("country") or "ES"
    return {
        "id": x["identificador"], "country": country, "kind": kind, "date": x["fecha"], "title": x["titulo"], "url": x["url_html"],
        "sites": sites, "municipalities": list(x.get("municipios_insee") or []) if country == "FR" else [],
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
                   details={"category": a.get("categoria"), "promoter": promoter(a.get("promotor")),
                            "file": a.get("expediente") or None, "department": a.get("departamento")})


def notice_fr(a: dict) -> dict:
    """A French consultation: placed by its commune or by its own polygon, never by a footprint."""
    c = a.get("consultation") or {}
    return _signal(a, "notice", a.get("precision") or "municipio", [{"code": s["sitecode"]} for s in a.get("natura") or []],
                   deadline=a.get("fecha_limite") or None, status=None,
                   details={"category": a.get("categoria"), "promoter": promoter(a.get("promotor"), "FR"),
                            "file": a.get("expediente") or None, "procedure": a.get("procedure") or None,
                            "consultation": {"opens": c.get("ouverture"), "closes": c.get("fermeture")}})


def resolution(r: dict, paired: dict | None) -> dict:
    """`paired` is the notice's signal; a resolution opens no deadline, whatever its own text says."""
    return _signal(r, "resolution", paired["precision"] if paired else "municipio",
                   list(paired["sites"]) if paired else [], deadline=None,
                   status=r.get("sentido_etiqueta") or r.get("sentido"),
                   details={"category": r.get("categoria"), "promoter": promoter(r.get("promotor")),
                            "file": r.get("expediente") or None, "paired_with": paired["id"] if paired else None})


def build(estado: dict, now: datetime | None = None, france: dict | None = None) -> dict:
    notices = {a["identificador"]: notice(a) for a in estado["anuncios"].values()}
    french = [notice_fr(a) for a in (france or {}).get("anuncios", {}).values()]
    # Suggested pairings («emparejamiento no confirmado») count too, as on the follow-up page.
    resolutions = [resolution(r, notices.get(r.get("emparejado_con") or ""))
                   for r in estado.get("resoluciones", {}).values()]
    now = now or datetime.now(timezone.utc)
    return {
        "source": SOURCE, "version": VERSION, "generated": now.strftime("%Y-%m-%dT%H:%MZ"),
        "coverage": COVERAGE_WITH_FRANCE if french else COVERAGE,
        "signals": sorted([*notices.values(), *resolutions, *french], key=lambda s: (s["date"] or "", s["id"])),
    }


def write(estado: dict, docs_dir: Path, france: dict | None = None) -> Path:
    path = docs_dir / "signals.json"
    path.write_text(json.dumps(build(estado, france=france), ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return path
