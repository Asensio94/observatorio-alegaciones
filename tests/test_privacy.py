"""No natural person is stored or published: the rule, the extraction and the data stored before it."""
import json
from datetime import date

from observatorio import condicionado, extract, litoral, privacy, seguimiento, site
from observatorio.boe import Anuncio

PERSON = "D. Juan Pérez García"


def _anuncio(texto: str, titulo: str = "Anuncio de la Confederación Hidrográfica de información pública") -> Anuncio:
    return Anuncio(identificador="BOE-B-2026-1", fecha="2026-10-05", seccion="5B", departamento="MINISTERIO",
                   titulo=titulo, url_html="https://www.boe.es/x", url_xml="https://www.boe.es/x.xml", texto=texto)


def test_the_test_is_the_honorific():
    for person in (PERSON, "Dña. Ana López", "Doña Ana López", "D.ª Ana López", "Don Juan Pérez", "don Juan Pérez Gil",
                   "Sra. López"):
        assert privacy.promoter(person) is None
    # Companies without a legal form stay. A company named after a place such as Don Benito would
    # lose its name: the rule fails on the side of naming no one.
    for company in ("Esteyco", "Eólica Uno, SL", "Donana Solar", "DGUOT"):
        assert privacy.promoter(company) == company
    assert privacy.promoter("") is None and privacy.promoter(None) is None


def test_redact_takes_out_the_name_with_or_without_honorific():
    text = f"Peticionario: {PERSON}. Consulte con Juan Pérez García en San Juan."
    assert privacy.redact(text, [PERSON]) == "Peticionario: [persona física]. Consulte con [persona física] en San Juan."
    # A first name alone is not taken out of everything: San Juan stays.
    assert privacy.redact("Embalse de San Juan", ["D. Juan"]) == "Embalse de San Juan"


def test_extraction_drops_a_person():
    a = extract.extraer_datos(_anuncio(
        f"Se somete a información pública el Expediente: D-0101/2026.\nPeticionario: {PERSON}.\n"
        "Solicita la instalación de una boya de amarre en el T.M. de Navalvillar de Pela (Badajoz)."))
    assert a.promotor == ""
    # The reports publish the text: the name leaves it too, and nothing else changes.
    assert "Pérez García" not in a.texto and "Peticionario: [persona física]." in a.texto
    assert a.expediente == "D-0101/2026" and a.municipios == ["Navalvillar de Pela"]


def test_extraction_keeps_companies():
    for company in ("Esteyco", "Jade Sostenible", "Eólica Uno"):
        a = extract.extraer_datos(_anuncio(f"Peticionario: {company}, con CIF B00000000.\nSolicita la instalación."))
        assert a.promotor == company


def test_resolution_promoter_found_in_the_ruling(monkeypatch):
    resolutions = [
        _anuncio("Texto sin fórmula de promotor.", titulo=(
            f"Resolución de la Dirección General de Política Energética y Minas por la que se otorga a {who} "
            "autorización administrativa previa para la instalación fotovoltaica Solar Uno."))
        for who in (PERSON, "Solar Uno Energía, SL")
    ]
    monkeypatch.setattr(seguimiento.boe, "fetch_sumario", lambda d: {"sumario": "stub"})
    monkeypatch.setattr(seguimiento.boe, "iter_items", lambda sumario, d, secciones: iter(resolutions))
    person, company = seguimiento.recolectar([date(2026, 10, 5)], {"boe"})
    assert person["promotor"] == "" and "Pérez García" not in json.dumps(person, ensure_ascii=False)
    assert company["promotor"] == "Solar Uno Energía"


def _dirty_state() -> dict:
    return {
        "anuncios": {
            "BOE-B-2026-1": {"identificador": "BOE-B-2026-1", "titulo": f"Concesión solicitada por {PERSON}",
                             "promotor": PERSON},
            "BOE-B-2026-2": {"identificador": "BOE-B-2026-2", "titulo": "Parque eólico", "promotor": "Eólica Uno, SL"},
        },
        "informes": [],
        "resoluciones": {
            "BOE-A-2026-3": {"identificador": "BOE-A-2026-3", "promotor": "Dña. Ana López Ruiz",
                             "motivos": [f"mismo promotor ({PERSON})"]},
        },
    }


def test_loading_the_state_scrubs_it(tmp_path, monkeypatch):
    path = tmp_path / "estado.json"
    path.write_text(json.dumps(_dirty_state(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(site, "ESTADO_PATH", path)
    estado = site.cargar_estado()
    assert estado["anuncios"]["BOE-B-2026-1"]["promotor"] == "" and estado["resoluciones"]["BOE-A-2026-3"]["promotor"] == ""
    assert estado["anuncios"]["BOE-B-2026-1"]["titulo"] == "Concesión solicitada por [persona física]"
    assert estado["anuncios"]["BOE-B-2026-2"]["promotor"] == "Eólica Uno, SL"
    raw = json.dumps(estado, ensure_ascii=False)
    assert "Pérez García" not in raw and "López Ruiz" not in raw


def test_the_daily_run_saves_the_state_clean(tmp_path, monkeypatch):
    path = tmp_path / "estado.json"
    path.write_text(json.dumps(_dirty_state(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(site, "ESTADO_PATH", path)
    # `run` goes through actualizar_estado even on a day without new notices.
    site.actualizar_estado([], "informes/informe_20261010_20261013.html", date(2026, 10, 10), date(2026, 10, 13))
    raw = path.read_text(encoding="utf-8")
    assert "Pérez García" not in raw and "López Ruiz" not in raw and "Eólica Uno, SL" in raw


def test_litoral_and_condicionado_scrub_on_load(tmp_path, monkeypatch):
    path = tmp_path / "estado_litoral.json"
    path.write_text(json.dumps({"anuncios": {"BOC-1": {"promotor": PERSON}}}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(litoral, "ESTADO_PATH", path)
    assert litoral.cargar_estado()["anuncios"]["BOC-1"]["promotor"] == ""

    monkeypatch.setattr(condicionado, "DATOS_DIR", tmp_path)
    sheet = {"identificador": "BOE-A-2023-1", "promotor": "don Juan Pérez García",
             "solicitudes": {"sustantivo": "…promovido por don Juan Pérez García, se establecieron…"}}
    (tmp_path / "BOE-A-2023-1.json").write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")
    loaded = condicionado.cargar()["BOE-A-2023-1"]
    assert loaded["promotor"] == "" and "Pérez García" not in json.dumps(loaded, ensure_ascii=False)


def test_scrub_reaches_every_text_of_a_report():
    report = [{"anuncio": {"promotor": PERSON, "titulo": "Boya de amarre",
                           "texto": f"Peticionario: {PERSON}.\nSolicita la instalación."}}]
    privacy.scrub(report)
    assert report[0]["anuncio"] == {"promotor": "", "titulo": "Boya de amarre",
                                    "texto": "Peticionario: [persona física].\nSolicita la instalación."}
