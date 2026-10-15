"""France: projets-environnement records as notices, INSEE helpers, the French privacy rule, the signals."""
from datetime import date

from observatorio import fr_geo, fr_projets, privacy, signals


def _record(**kw) -> dict:
    return {"recordsid": "2026D001402174", "source": "GUNenv", "titre": "Exploitation de carrière",
            "nature": "Carrières soumises à autorisation mentionnées par la rubrique ICPE 2510 et leurs extensions",
            "type_de_procedure": "AENV", "etat_de_la_consultation_publique": "ouvert",
            "date_de_diffusion": "2026-10-10T08:00:00+00:00", "dateouverture": "2026-10-01", "datefermeture": "2026-11-02",
            "departement_de_la_prefecture": "39 - Jura", "location_ville": "Val-d'Épy", "code_postal": "39160",
            "descriptif_du_projet": "M. Jean Dupont exploite…", "dc_relation_websitedebate": "https://registre.example/carriere",
            "dc_relation_expertise_avisae": "None", **kw}


# --- privacy ---------------------------------------------------------------

def test_french_honorifics_and_one_person_firms_are_people():
    for name in ("M. Jean Dupont", "Mme Durand", "Monsieur Petit", "EARL Martin", "GAEC du Bois Joli", "SCEA de la Grange"):
        assert privacy.promoter(name, "FR") is None
    for name in ("Soulanges Énergies SAS", "Carrières du Jura", "Commune de Plouay"):
        assert privacy.promoter(name, "FR") == name


def test_spanish_rule_is_unchanged_by_the_french_one():
    assert privacy.promoter("M. Jean Dupont") == "M. Jean Dupont"
    assert privacy.promoter("D. Juan Pérez") is None


def test_french_titles_lose_the_names_and_keep_the_rest():
    assert privacy.redact_fr("Extension de l'élevage porcin de l'EARL Martin à Plouay") == \
        "Extension de l'élevage porcin de l'[personne physique] à Plouay"
    assert privacy.redact_fr("Carrière de M. Martin et Mme Petit") == "Carrière de [personne physique] et [personne physique]"
    assert privacy.redact_fr("Parc éolien de Soulanges") == "Parc éolien de Soulanges"
    # A title, not a person: «le maire» is lower case.
    assert privacy.redact_fr("Centrale de Saint-Martin (M. le maire)") == "Centrale de Saint-Martin (M. le maire)"


def test_french_state_is_scrubbed_by_pattern():
    assert privacy.scrub({"titulo": "Forage de M. Dupont"}, "FR") == {"titulo": "Forage de [personne physique]"}


# --- INSEE helpers ---------------------------------------------------------

def test_names_fold_accents_hyphens_and_saint():
    assert fr_geo.fold("Val-d'Épy") == fr_geo.fold("Val d Epy")
    assert fr_geo.fold("St-Jean-de-Luz") == fr_geo.fold("Saint Jean de Luz")


def test_departments_from_the_register_and_from_postcodes():
    assert fr_geo.department_of("13 - Bouches-du-Rhône") == "13"
    assert fr_geo.department_of("2a") == "2A"
    assert fr_geo.department_of("974 - La Réunion") == "974"
    assert fr_geo.department_of("") is None
    assert fr_geo._department_of_postcode("39160") == "39"
    assert fr_geo._department_of_postcode("97400") == "974"
    assert fr_geo._department_of_postcode("20000") is None  # 2A or 2B: the name search decides


# --- records → notices -----------------------------------------------------

def test_a_record_with_consultation_dates_is_a_notice():
    assert fr_projets.is_notice(_record())
    assert not fr_projets.is_notice(_record(dateouverture=None))
    # Published again in 2026 because a decision was added; its consultation was in 2024.
    assert not fr_projets.is_notice(_record(dateouverture="2024-04-22", datefermeture="2024-05-24"))
    assert fr_projets.is_notice(_record(dateouverture="2024-04-22", datefermeture="2024-05-24"), since=date(2024, 1, 1))


def test_notice_fields():
    a = fr_projets.notice(_record())
    assert (a["country"], a["identificador"], a["fecha"], a["fecha_limite"]) == ("FR", "FR-PE-2026D001402174", "2026-10-01", "2026-11-02")
    assert (a["categoria"], a["procedure"], a["departement"], a["provincias"]) == ("mineria", "Autorisation environnementale", "39", ["39"])
    assert a["documents"] == {"registre": "https://registre.example/carriere"}
    # The free-text description may name people: it is not kept.
    assert "M. Jean Dupont" not in str(a)


def test_notice_title_is_redacted():
    assert fr_projets.notice(_record(titre="Création site volailles SCEA Martin"))["titulo"] == "Création site volailles [personne physique]"


def test_categories_follow_the_spanish_ones():
    assert fr_projets.category({"titre": "Parc éolien du Moulin", "nature": "Installations classées"}) == "eolica"
    assert fr_projets.category({"titre": "Centrale agrivoltaïque", "nature": "ICPE"}) == "fotovoltaica"
    assert fr_projets.category({"titre": "Système d'assainissement", "nature": ""}) == "agua_concesion"
    assert fr_projets.category({"titre": "Divers", "nature": ""}) == "otros"


# --- signals ---------------------------------------------------------------

def _french_notice(**kw) -> dict:
    a = fr_projets.notice(_record())
    a.update({"municipios": ["Val-d'Épy"], "municipios_insee": ["39209"], "precision": "municipio",
              "natura": [{"sitecode": "FR4301334", "nombre": "Petite montagne du Jura", "tipo": "LIC/ZEC"}], **kw})
    return a


def test_french_signal_carries_country_and_insee_codes():
    s = signals.notice_fr(_french_notice())
    assert (s["country"], s["kind"], s["precision"]) == ("FR", "notice", "municipio")
    assert (s["municipalities"], s["municipality_names"], s["provinces"]) == (["39209"], ["Val-d'Épy"], ["39"])
    assert s["sites"] == [{"code": "FR4301334"}]
    assert s["deadline"] == "2026-11-02"
    assert s["details"]["consultation"] == {"opens": "2026-10-01", "closes": "2026-11-02"}


def test_polygon_notice_is_perimetro_and_corsica_keeps_its_letters():
    s = signals.notice_fr(_french_notice(precision="perimetro", municipios_insee=["2A004"]))
    assert (s["precision"], s["municipalities"]) == ("perimetro", ["2A004"])


def test_both_countries_in_one_document():
    estado = {"anuncios": {}, "resoluciones": {}}
    doc = signals.build(estado, france={"anuncios": {"FR-PE-1": _french_notice(identificador="FR-PE-1")}})
    assert [s["country"] for s in doc["signals"]] == ["FR"]
    assert "Francia" in doc["coverage"]["label"]
    assert "Francia" not in signals.build(estado)["coverage"]["label"]


# --- avis header -----------------------------------------------------------

from observatorio import fr_avis  # noqa: E402

MRAE_BOX = ("Mission Régionale d’ Autorité Environnementale Grand Est\nNom du pétitionnaire Soulanges Énergies SAS – filiale des "
            "sociétés BayWa r.e France  \net C4B Finances\nCommune Soulanges\nDépartement Marne (51)\nObjet de la demande …\n")
NOUVELLE_AQUITAINE = ("Région Nouvelle-Aquitaine\nLocalisation du projet : Commune de SAINT-MARTIAL (16)\n"
                      "Maître(s) d’ouvrage(s) : Société PHOTOSOL Développement\nAvis émis à la demande …\n")
RUNNING_TEXT = ("Avis sur la création d’une centrale photovoltaïque au sol -\nCommune de Laveraët (Gers)\nPar courrier … sur la "
                "commune de Laveraët porté par la société CORFU So-\nlaire.\n")


def test_avis_headers_in_their_three_forms():
    assert fr_avis.read_header(MRAE_BOX) == {"promoter": "Soulanges Énergies SAS", "person": [], "communes": ["Soulanges"]}
    assert fr_avis.read_header(NOUVELLE_AQUITAINE) == {"promoter": "PHOTOSOL Développement", "person": [], "communes": ["SAINT-MARTIAL"]}
    assert fr_avis.read_header(RUNNING_TEXT) == {"promoter": "CORFU Solaire", "person": [], "communes": ["Laveraët"]}


def test_a_person_as_developer_leaves_only_a_fingerprint():
    h = fr_avis.read_header("Nom du pétitionnaire EARL Dupont\nCommune Plouay\nDépartement Morbihan (56)\n")
    assert h["promoter"] is None and "Dupont" not in str(h)
    assert fr_avis.redact_title("Extension élevage porcin Dupont à Plouay", h["person"]) == \
        "Extension élevage porcin [personne physique] à Plouay"
    assert fr_avis.redact_title("Parc éolien de Plouay", h["person"]) == "Parc éolien de Plouay"


def test_a_commune_with_et_is_kept_whole_for_the_lookup():
    h = fr_avis.read_header("Nom du pétitionnaire X SAS\nCommune Chemaudin et Vaux, Dannemarie\nDépartement Doubs (25)\n")
    assert h["communes"] == ["Chemaudin et Vaux", "Dannemarie"]


# --- French pages ----------------------------------------------------------

from observatorio import fr_site, i18n  # noqa: E402


def test_french_typography():
    assert i18n.n(46709, "fr") == "46 709" and i18n.n(46709, "es") == "46.709"
    assert i18n.p(0.15, "fr") == "15 %"
    assert i18n.day("2026-10-01", "fr") == "1er octobre 2026" and i18n.day("2026-11-02", "fr") == "2 novembre 2026"


def test_open_and_closed_split_on_the_closing_day():
    today = date(2026, 11, 2)
    last_day = _french_notice(identificador="FR-PE-1", cruce="ok")
    closed = _french_notice(identificador="FR-PE-2", fecha_limite="2026-10-30",
                            consultation={"ouverture": "2026-10-01", "fermeture": "2026-10-30", "etat": "clos"})
    open_, past = fr_site.split({"anuncios": {"1": last_day, "2": closed}}, today)
    assert [a["identificador"] for a in open_] == ["FR-PE-1"] and [a["identificador"] for a in past] == ["FR-PE-2"]
    assert "dernier jour" in fr_site.closing(last_day, today)


def test_french_pages_are_in_french_and_explain_the_method(tmp_path):
    notice = _french_notice(cruce="ok", promotor="Carrières du Jura", n_especies=3, n_aves=2,
                            especies_top=[{"scientificName": "Milvus milvus", "vernacular_fr": "Milan royal",
                                           "categoria_uicn": "NT", "class": "Aves"}])
    index, archives = fr_site.build({"anuncios": {"FR-PE-1": notice}}, tmp_path, today=date(2026, 10, 15))
    html = index.read_text(encoding="utf-8")
    assert '<html lang="fr">' in html and "Comment c’est calculé" in html
    assert "Ce qui est laissé de côté" in html and "Limites" in html and "Données personnelles" in html
    assert "carrières et mines" in html and "Val-d&#x27;Épy <small>(39209)</small>" in html
    assert "ZSC / SIC" in html and "Milan royal" in html and "quasi menacée" in html
    assert "encore 18 jours" in html and "Cómo se calcula" not in html
    assert "Aucune consultation" in archives.read_text(encoding="utf-8")
