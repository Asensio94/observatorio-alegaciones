"""Reader-facing wording: deadlines, uncrossed projects, category labels and non-native species."""

from datetime import date, timedelta

from observatorio import litoral, report, species


def _anuncio(**kw):
    a = {"identificador": "BOE-B-2026-1", "url_html": "https://www.boe.es/x", "municipios": ["X"], "prioridad": 3,
         "departamento": "MINISTERIO", "expediente": "EXP-1"}
    a.update(kw)
    return a


def test_deadline_wording():
    hoy = date.today()
    assert "último día hoy" in report.texto_plazo(_anuncio(fecha_limite=hoy.isoformat(), plazo_dias=20))
    assert "quedan 5 días naturales" in report.texto_plazo(
        _anuncio(fecha_limite=(hoy + timedelta(days=5)).isoformat(), plazo_dias=20))
    cerrado = report.texto_plazo(_anuncio(fecha_limite=(hoy - timedelta(days=1)).isoformat(), plazo_dias=20))
    assert "plazo cerrado" in cerrado and "quedan" not in cerrado


def test_uncrossed_is_not_none_found():
    assert report.sin_cruce(_anuncio(geolocalizado=True)) == ""
    assert report.sin_cruce(_anuncio(geolocalizado=False, municipios=[])) == "sin cruce: municipios no detectados"
    assert report.sin_cruce(_anuncio(geolocalizado=False, prioridad=1)) == "sin cruce: prioridad baja"
    assert report.sin_cruce(_anuncio(geolocalizado=False)) == "sin cruce: municipios no localizados"


def test_category_labels():
    assert "Hidrógeno y baterías" in report.badge("hidrogeno_baterias")
    assert all("_" not in v for v in report.ETIQUETAS_CATEGORIA.values())
    assert set(report.ETIQUETAS_CATEGORIA) == set(report.COLORES)


def test_how_to_file_cites_reference():
    texto = report.como_alegar(_anuncio(fecha_limite=date.today().isoformat()))
    assert "EXP-1" in texto and "https://www.boe.es/x" in texto


def test_non_native_species_dropped():
    resumen = {"total_registros_amenazadas": 10, "aves_amenazadas_registros": 10, "n_especies": 2, "n_aves": 2,
               "especies": [{"scientificName": "Anser cygnoides", "class": "Aves", "registros": 4},
                            {"scientificName": "Otis tarda", "class": "Aves", "registros": 6}]}
    out = species.nativas(resumen)
    assert [e["scientificName"] for e in out["especies"]] == ["Otis tarda"]
    assert (out["n_especies"], out["n_aves"], out["total_registros_amenazadas"]) == (1, 1, 6)


def test_litoral_uncrossed_is_not_none_found(tmp_path):
    hoy = date.today()
    base = {"titulo": "Concesión en el DPMT", "url_html": "https://www.boe.es/x", "categoria": "dpmt",
            "fecha_limite": (hoy + timedelta(days=5)).isoformat(), "municipios": ["X"], "provincias": [],
            "senales": [], "natura_nombres": [], "n_especies": 0}
    anuncios = {
        "CRUZADO": {**base, "identificador": "CRUZADO", "puntos": 5, "geolocalizado": True},
        "POCOS": {**base, "identificador": "POCOS", "puntos": 2, "geolocalizado": False},
        "SIN-MUNI": {**base, "identificador": "SIN-MUNI", "puntos": 5, "municipios": [], "geolocalizado": False},
    }
    assert litoral.motivo_sin_cruce(anuncios["CRUZADO"]) == ""
    assert litoral.motivo_sin_cruce(anuncios["POCOS"]) == "sin cruce: menos de 3 puntos de señal"
    assert litoral.motivo_sin_cruce(anuncios["SIN-MUNI"]) == "sin cruce: municipios no detectados"
    # States saved before the flag: what the run was meant to cross counts as crossed.
    legado = {k: v for k, v in anuncios["CRUZADO"].items() if k != "geolocalizado"}
    assert litoral.motivo_sin_cruce(legado) == ""
    litoral.generar_web({"anuncios": anuncios}, tmp_path)
    html = (tmp_path / "litoral.html").read_text(encoding="utf-8")
    assert html.count("ninguno encontrado") == 1 and "sin cruce: menos de 3 puntos" in html
    assert "quedan 5 días naturales" in html and "Ocupación del dominio público marítimo-terrestre" in html
