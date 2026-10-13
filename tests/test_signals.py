"""signals.json for Estado de las IBA, built from a small synthetic state."""
import json
from datetime import datetime, timezone

from observatorio import signals

SITE_A = {"sitecode": "ES0000001", "nombre": "Sierra A", "tipo": "ZEPA"}
SITE_B = {"sitecode": "ES0000002", "nombre": "Vega B", "tipo": "LIC/ZEC"}


def _notice(ident: str, fecha: str, **kw) -> dict:
    return {"identificador": ident, "fecha": fecha, "titulo": f"Anuncio {ident}", "url_html": f"https://www.boe.es/{ident}",
            "categoria": "eolica", "departamento": "MINISTERIO", "promotor": "", "expediente": "", "potencia_mw": None,
            "municipios": ["Villanueva"], "provincias": ["Granada"], "fecha_limite": "2026-10-20", "natura": [SITE_A, SITE_B],
            **kw}


def _resolution(ident: str, fecha: str, paired_with: str | None, **kw) -> dict:
    return {"identificador": ident, "fecha": fecha, "titulo": f"Resolución {ident}", "url_html": f"https://www.boe.es/{ident}",
            "categoria": "eolica", "promotor": "Eólica Uno, SL", "expediente": "PEol-1", "potencia_mw": 50.0,
            "municipios": ["Villanueva"], "provincias": ["Granada"], "fecha_limite": "2026-11-30",
            "sentido": "condicionada", "sentido_etiqueta": "favorable con condiciones", "emparejado_con": paired_with,
            **kw}


def _by_id(estado: dict) -> dict:
    return {s["id"]: s for s in signals.build(estado)["signals"]}


def test_notice_without_footprint_reaches_the_sites_of_its_municipalities():
    s = signals.notice(_notice("BOE-B-2026-1", "2026-10-01", promotor="Eólica Uno, SL", expediente="PEol-1"))
    assert (s["kind"], s["date"], s["url"]) == ("notice", "2026-10-01", "https://www.boe.es/BOE-B-2026-1")
    assert s["precision"] == "municipio"
    assert s["sites"] == [{"code": "ES0000001"}, {"code": "ES0000002"}]
    # The hub resolves names to INE codes; the provinces tell homonyms apart.
    assert (s["municipalities"], s["municipality_names"], s["provinces"]) == ([], ["Villanueva"], ["Granada"])
    assert s["details"] == {"category": "eolica", "promoter": "Eólica Uno, SL", "file": "PEol-1", "department": "MINISTERIO"}
    assert s["status"] is None and s["value"] is None


def test_notice_with_footprint_reaches_only_the_sites_in_its_parcels():
    s = signals.notice(_notice("BOE-B-2026-2", "2026-10-01", potencia_mw=49.5,
                               footprint={"status": "ok", "natura": [SITE_B]}))
    assert s["precision"] == "parcelas"
    assert s["sites"] == [{"code": "ES0000002"}]
    assert s["value"] == {"amount": 49.5, "unit": "MW"}


def test_footprint_without_sites_falls_back_to_the_municipalities():
    s = signals.notice(_notice("BOE-B-2026-3", "2026-10-01", footprint={"status": "ok", "natura": []}))
    assert s["precision"] == "municipio"
    assert len(s["sites"]) == 2


def test_empty_fields_are_null():
    s = signals.notice(_notice("BOE-B-2026-4", "2026-10-01", fecha_limite="", natura=[], municipios=[]))
    assert s["deadline"] is None and s["sites"] == [] and s["municipality_names"] == []
    assert s["details"]["promoter"] is None and s["details"]["file"] is None


def test_deadline_only_on_notices():
    by_id = _by_id({"anuncios": {"BOE-B-2026-5": _notice("BOE-B-2026-5", "2026-10-01")},
                    "resoluciones": {"BOE-A-2026-9": _resolution("BOE-A-2026-9", "2026-10-02", "BOE-B-2026-5")}})
    assert by_id["BOE-B-2026-5"]["deadline"] == "2026-10-20"
    # A resolution carries the deadline field of every bulletin act, but it opens no consultation.
    assert by_id["BOE-A-2026-9"]["deadline"] is None


def test_resolution_inherits_place_from_its_notice():
    notice = _notice("BOE-B-2026-6", "2026-10-01", footprint={"natura": [SITE_A]})
    by_id = _by_id({"anuncios": {"BOE-B-2026-6": notice},
                    "resoluciones": {"BOE-A-2026-10": _resolution("BOE-A-2026-10", "2026-10-05", "BOE-B-2026-6")}})
    r = by_id["BOE-A-2026-10"]
    assert (r["kind"], r["precision"], r["sites"]) == ("resolution", "parcelas", [{"code": "ES0000001"}])
    assert r["status"] == "favorable con condiciones"
    assert r["value"] == {"amount": 50.0, "unit": "MW"}
    assert r["details"] == {"category": "eolica", "promoter": "Eólica Uno, SL", "file": "PEol-1",
                            "paired_with": "BOE-B-2026-6"}


def test_unpaired_resolution_has_no_sites():
    by_id = _by_id({"anuncios": {}, "resoluciones": {
        "BOE-A-2026-11": _resolution("BOE-A-2026-11", "2026-10-05", None, sentido_etiqueta=""),
        "BOE-A-2026-12": _resolution("BOE-A-2026-12", "2026-10-05", "BOE-B-2025-1")}})  # paired with an unknown notice
    for r in by_id.values():
        assert (r["precision"], r["sites"], r["details"]["paired_with"]) == ("municipio", [], None)
    assert by_id["BOE-A-2026-11"]["status"] == "condicionada"


def test_document_is_sorted_and_stamped():
    estado = {"anuncios": {i: _notice(i, d) for i, d in (("BOE-B-2026-9", "2026-10-02"), ("BOE-B-2026-8", "2026-10-02"),
                                                         ("BOE-B-2026-7", "2026-10-03"))},
              "resoluciones": {"BOE-A-2026-1": _resolution("BOE-A-2026-1", "2026-10-01", None)}}
    doc = signals.build(estado, now=datetime(2026, 10, 13, 7, 2, 41, tzinfo=timezone.utc))
    assert (doc["source"], doc["version"], doc["generated"]) == ("observatorio-alegaciones", 1, "2026-10-13T07:02Z")
    assert doc["coverage"]["sites"] is None
    assert [s["id"] for s in doc["signals"]] == ["BOE-A-2026-1", "BOE-B-2026-8", "BOE-B-2026-9", "BOE-B-2026-7"]
    for s in doc["signals"]:
        assert "source" not in s and "regions" not in s


def test_written_file_is_utf8_with_lf(tmp_path):
    path = signals.write({"anuncios": {"BOE-B-2026-1": _notice("BOE-B-2026-1", "2026-10-01")}, "resoluciones": {}}, tmp_path)
    raw = path.read_bytes()
    assert b"\r\n" not in raw and "Toda España".encode() in raw
    assert json.loads(raw.decode("utf-8"))["signals"][0]["id"] == "BOE-B-2026-1"


def test_web_build_rewrites_it(tmp_path):
    from observatorio import site

    site.generar_web({"anuncios": {}, "informes": [], "resoluciones": {}}, tmp_path)
    assert json.loads((tmp_path / "signals.json").read_text(encoding="utf-8"))["signals"] == []
