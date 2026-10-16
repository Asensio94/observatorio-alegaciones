"""The French pages (docs/fr/): open public consultations and the archive, in French.

Built from data/estado_fr.json only. The look is the Spanish pages' (same CSS, logo and footer siblings);
the words go through i18n. The method section says where every column comes from, what is left out and
why, and the limits, as the Spanish one does: the README alone is not enough.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import i18n
from .config import GBIF_THREAT_CATEGORIES, GBIF_YEAR_FROM
from .i18n import CATEGORIES, CLASSES, IUCN, NATURA_TYPES, label
from .logo import LOGO_SVG
from .report import (ACCENT_CSS, COLORES, COMMON_CSS, CSS, FAVICON, FONTS_URL, REPO_URL, SIBLINGS, THIS_PROJECT,
                     esc, figures_html)

LANG = "fr"
URGENT_DAYS = 7
MAX_CROSSES = 80  # per daily run; the rest wait for the next one (cli.france --max-cruces)
SOURCE_URL = "https://www.projets-environnement.gouv.fr/explore/dataset/sico_to_ods/"

_NAV_LINKS = [("index.html", "Consultations ouvertes"), ("archives.html", "Archives")]

DOCUMENTS = {"registre": "registre", "avis_ae": "avis de l’autorité environnementale",
             "reponse_avis_ae": "réponse du maître d’ouvrage", "etude_impact": "étude d’impact",
             "resume_non_technique": "résumé non technique", "arrete_ouverture": "arrêté d’ouverture",
             "decision": "décision"}


def site_nav(current: str = "") -> str:
    links = "".join(f'<a href="{href}"{" aria-current=page" if href == current else ""}>{text}</a>'
                    for href, text in _NAV_LINKS)
    return (f'<nav class="site-nav" aria-label="Sections">{links}'
            f'<a href="../index.html" hreflang="es" lang="es">España</a><a href="{REPO_URL}">Code et données</a></nav>')


def _siblings() -> str:
    current = ' aria-current="page"'
    return "".join(
        f'    <li{current if slug == THIS_PROJECT else ""}><a href="https://asensio94.github.io/{slug}/" lang="es">{name}</a></li>\n'
        for slug, name in SIBLINGS)


FOOTER = f"""<footer class="site-footer">
  <p class="principle">Données publiques, règles visibles et chaque chiffre relié à sa source. Des indices, pas des verdicts.</p>
  <p>Sources : projets-environnement.gouv.fr (ministère de la Transition écologique, jeu de données
  <a href="{SOURCE_URL}">sico_to_ods</a>), avis des autorités environnementales (MRAe et Ae de l’IGEDD), API Découpage
  administratif (geo.api.gouv.fr, codes INSEE et contours des communes), Agence européenne pour l’environnement
  (Natura 2000, version 2024), GBIF (observations d’animaux géolocalisées depuis {GBIF_YEAR_FROM}, catégories UICN).
  Code sous licence MIT : <a href="{REPO_URL}">github.com/Asensio94/observatorio-alegaciones</a>. Données propres sous
  licence CC BY 4.0 ; celles des tiers gardent la leur.</p>
  <nav aria-label="Projets associés"><ul class="siblings">
{_siblings()}  </ul></nav>
</footer>"""


def page(title: str, lede: str, body: str, nav: str, *, heading: str, figures=(), method: str = "") -> str:
    method_html = (f'<section class="method" aria-labelledby="comment"><h2 id="comment">Comment c’est calculé</h2>'
                   f"{method}</section>") if method else ""
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
{FAVICON}
<link rel="alternate" hreflang="es" href="../index.html">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{esc(FONTS_URL)}">
<style>
{COMMON_CSS}
{ACCENT_CSS}
{CSS}
 .fr-list td.when{{white-space:nowrap}} .fr-list small{{color:var(--muted)}} .fr-list ul{{margin:4px 0 0;padding-left:18px}}
</style></head><body>
<header class="site-header">
{nav}
<h1>{LOGO_SVG}{heading}</h1>
<p class="lede">{lede}</p>
{figures_html(figures)}
</header>
<main class="content">
{body}
</main>
{method_html}
{FOOTER}
</body></html>"""


def badge(category: str) -> str:
    return (f'<span class="badge" style="background:{COLORES.get(category, "#444")}">'
            f'{esc(label(CATEGORIES, LANG, category))}</span>')


def days_left(a: dict, today: date) -> int | None:
    closes = (a.get("consultation") or {}).get("fermeture") or a.get("fecha_limite")
    return (date.fromisoformat(closes) - today).days if closes else None


def closing(a: dict, today: date) -> str:
    closes = (a.get("consultation") or {}).get("fermeture") or a.get("fecha_limite")
    if not closes:
        return "non indiquée"
    left = days_left(a, today)
    when = i18n.day(closes, LANG)
    if left < 0:
        return f'<span class="cerrado">{when} · close</span>'
    rest = "dernier jour" if left == 0 else f"encore {left} jour{'s' if left > 1 else ''}"
    return f'<span class="{"urgente" if left <= URGENT_DAYS else ""}">{when}<br><small>{rest}</small></span>'


def _place(a: dict) -> str:
    dept = a.get("departement") or ""
    names = [f"{esc(nom)} <small>({esc(code)})</small>"
             for nom, code in zip(a.get("municipios") or [], a.get("municipios_insee") or [])]
    if names:
        where = ", ".join(names[:6]) + (f" <small>et {len(names) - 6} autres</small>" if len(names) > 6 else "")
    elif a.get("cruce") == "" and a.get("precision") is not None:
        where = '<span class="warn">commune non trouvée</span>'
    else:
        where = '<span class="warn">pas encore localisé</span>'
    perimeter = " <small>· périmètre dessiné</small>" if a.get("precision") == "perimetro" else ""
    return f"{where}{perimeter}<br><small>Département {esc(dept)}</small>" if dept else where + perimeter


def _natura(a: dict) -> str:
    if not a.get("cruce"):
        return "<small>—</small>"
    sites = a.get("natura") or []
    if not sites:
        return "aucun"
    items = "".join(f'<li>{esc(s["nombre"])} <small>{esc(s["sitecode"])} · {esc(label(NATURA_TYPES, LANG, s["tipo"]))}</small></li>'
                    for s in sites[:5])
    more = f"<li><small>et {len(sites) - 5} autres</small></li>" if len(sites) > 5 else ""
    return f"{len(sites)}<ul>{items}{more}</ul>"


def _species(a: dict) -> str:
    if not a.get("cruce"):
        return "<small>—</small>"
    n = a.get("n_especies", 0)
    if not n:
        return "aucune"
    top = a.get("especies_top") or []
    items = "".join(
        f'<li>{esc(e.get("vernacular_fr") or "")} <i>{esc(e["scientificName"])}</i> '
        f'<small>{esc(label(IUCN, LANG, e["categoria_uicn"]))}</small></li>' for e in top[:5])
    birds = a.get("n_aves", 0)
    return (f"{i18n.n(n, LANG)} espèce{'s' if n > 1 else ''}"
            f"{f', dont {i18n.n(birds, LANG)} oiseau' + ('x' if birds > 1 else '') if birds else ''}<ul>{items}</ul>")


def _documents(a: dict) -> str:
    docs = a.get("documents") or {}
    links = [f'<a href="{esc(docs[k])}" target="_blank" rel="noopener">{esc(text)}</a>'
             for k, text in DOCUMENTS.items() if docs.get(k)]
    links.append(f'<a href="{esc(a["url_html"])}" target="_blank" rel="noopener">fiche du projet</a>')
    return "<br>".join(links)


def _project(a: dict) -> str:
    who = f"<br><small>Maître d’ouvrage : {esc(a['promotor'])}</small>" if a.get("promotor") else ""
    proc = f"<br><small>{esc(a['procedure'])}</small>" if a.get("procedure") else ""
    return f"{badge(a['categoria'])} {esc(a['titulo'])}{who}{proc}"


def _table(rows: list[dict], today: date, *, open_: bool) -> str:
    if not rows:
        return "<p><i>Aucune consultation.</i></p>"
    head = ("<th>Clôture</th><th>Projet</th><th>Commune (code INSEE)</th><th>Natura 2000 sur la commune</th>"
            "<th>Animaux menacés observés</th><th>Documents</th>")
    body = "".join(
        f'<tr id="{esc(a["identificador"])}"><td class="when">{closing(a, today)}</td><td>{_project(a)}</td>'
        f"<td>{_place(a)}</td><td>{_natura(a)}</td><td>{_species(a)}</td><td>{_documents(a)}</td></tr>"
        for a in rows)
    caption = "Consultations publiques ouvertes" if open_ else "Consultations publiques closes"
    return (f'<div class="wrap"><table class="datos fr-list" aria-label="{caption}">'
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def split(estado: dict, today: date) -> tuple[list[dict], list[dict]]:
    """(open, closed): open ones by closing date, soonest first; closed ones most recent first."""
    notices = list(estado.get("anuncios", {}).values())
    open_ = [a for a in notices if (days_left(a, today) is not None and days_left(a, today) >= 0)]
    closed = [a for a in notices if a not in open_]
    open_.sort(key=lambda a: (a.get("fecha_limite") or "", a["identificador"]))
    closed.sort(key=lambda a: (a.get("fecha_limite") or "", a["identificador"]), reverse=True)
    return open_, closed


def _method(since: date) -> str:
    return f"""
<p>Chaque jour, le robot lit le registre national des projets soumis à évaluation environnementale,
<a href="https://www.projets-environnement.gouv.fr/">projets-environnement.gouv.fr</a>, garde les consultations du public
et les situe sur leurs communes, puis les croise avec le réseau Natura 2000 et les observations d’animaux menacés.
Le but : que les associations et les riverains connaissent un projet <b>tant qu’il est encore possible de donner
son avis</b>. Il ne remplace pas le registre officiel : chaque ligne y renvoie.</p>
<ol>
 <li><b>Lecture.</b> Les fiches publiées depuis le {i18n.day(since.isoformat(), LANG)} sont lues dans le jeu de
  données <code>sico_to_ods</code> (API Opendatasoft). Il réunit deux systèmes : GUNenv, où l’administration saisit
  la commune et le code postal, et la téléprocédure du maître d’ouvrage (TPS), qui donne un périmètre, un point ou
  seulement le département.</li>
 <li><b>Sélection.</b> Seules comptent les fiches avec des dates d’ouverture et de clôture de consultation, et dont
  la consultation s’est ouverte après le début de la série. Une fiche republiée parce qu’une décision s’y ajoute
  garde la date de sa consultation, pas celle de sa republication.</li>
 <li><b>Catégorie.</b> Des règles écrites (expressions régulières) sur le titre et la nature du projet lui donnent
  l’une des catégories de la version espagnole : éolien, photovoltaïque, carrières et mines, eau et assainissement…</li>
 <li><b>Localisation.</b> Un périmètre dessiné est croisé tel quel ; on cherche la commune d’un point de chacune de
  ses parties. Une commune nommée est retrouvée par son nom dans son code postal, puis dans son département, avec
  l’API Découpage administratif, qui donne son code INSEE (cinq caractères, 2A et 2B en Corse) et son contour,
  simplifié à environ 50 m. Si la fiche ne donne que le département, on lit la commune sur la première page de
  l’avis de l’autorité environnementale (MRAe ou Ae de l’IGEDD).</li>
 <li><b>Maître d’ouvrage.</b> Il est lu sur la même première page de l’avis : l’encadré de la MRAe («&#8239;Nom du
  pétitionnaire&#8239;»), la ligne «&#8239;Maître d’ouvrage&#8239;» ou la phrase «&#8239;porté par la société…&#8239;».</li>
 <li><b>Croisements.</b> Le contour de la commune (ou le périmètre) est croisé avec les sites Natura 2000 qui le
  touchent et avec les observations GBIF d’animaux en catégorie UICN {", ".join(GBIF_THREAT_CATEGORIES)} depuis
  {GBIF_YEAR_FROM}. Chaque passage croise au plus {MAX_CROSSES} nouvelles fiches, les plus récentes d’abord ; les
  autres attendent le passage suivant («&#8239;pas encore localisé&#8239;»).</li>
 <li><b>Publication.</b> Tout s’accumule dans <code>data/estado_fr.json</code>, ces pages sont régénérées et chaque
  consultation passe dans <code>docs/signals.json</code> avec <code>"country": "FR"</code> et ses codes INSEE, pour
  les projets associés. Une consultation passe aux archives le lendemain de sa clôture.</li>
</ol>
<h3>Paramètres</h3>
<table class="params">
 <tr><th>Début de la série</th><td class="num">consultations ouvertes depuis le {i18n.day(since.isoformat(), LANG)}</td></tr>
 <tr><th>Nouveaux croisements par passage</th><td class="num">{MAX_CROSSES}</td></tr>
 <tr><th>Clôture signalée comme proche</th><td class="num">{URGENT_DAYS} jours ou moins</td></tr>
 <tr><th>Espèces (GBIF)</th><td class="num">UICN {"/".join(GBIF_THREAT_CATEGORIES)} · depuis {GBIF_YEAR_FROM}</td></tr>
 <tr><th>Natura 2000</th><td class="num">version 2024 (ZSC/SIC et ZPS)</td></tr>
 <tr><th>Contours des communes</th><td class="num">simplifiés à ~50 m</td></tr>
</table>
<h3>Ce qui est laissé de côté, et pourquoi</h3>
<ul>
 <li><b>Les fiches sans dates de consultation</b> (projets enregistrés sans participation du public ouverte) : il
  n’y a pas encore d’avis à donner.</li>
 <li><b>Les consultations ouvertes avant le début de la série</b>, même si leur fiche a été republiée depuis.</li>
 <li><b>Les décisions d’examen au cas par cas</b> et le contenu des avis (recommandations de l’autorité
  environnementale) : ils seront lus dans une étape suivante. Pour l’instant, seule la première page de l’avis
  est lue, pour la commune et le maître d’ouvrage.</li>
 <li><b>Les arrêtés d’autorisation et leurs prescriptions</b>, publiés dans les recueils des actes administratifs
  de chaque préfecture : prévus pour une seconde phase, d’abord dans deux ou trois départements pilotes, car il faut
  les lire préfecture par préfecture et beaucoup sont des images à passer par la reconnaissance de caractères.</li>
 <li><b>Les enquêtes publiques et registres dématérialisés</b> ne sont pas lus : on donne le lien vers le registre
  que la fiche indique, où se déposent les observations.</li>
 <li><b>Les plans et programmes</b> (PLU, SCoT…) : ils ne figurent pas dans ce registre de projets.</li>
 <li><b>La description libre du projet</b> n’est pas conservée : elle peut nommer des particuliers.</li>
</ul>
<h3>Limites</h3>
<ul>
 <li>Le croisement porte sur la <b>commune entière</b> (ou le périmètre déclaré), pas sur l’emprise des travaux :
  c’est un filtre d’attention, pas une évaluation d’incidences.</li>
 <li>Une fiche TPS sans lieu et dont l’avis ne se lit pas (scan, avis absent) reste sans commune ni croisement.</li>
 <li>Un périmètre à cheval sur deux communes dans une même partie n’est attribué qu’à la commune de son point
  intérieur.</li>
 <li>Les catégories et le maître d’ouvrage sont lus par des règles qui peuvent se tromper. Les dates viennent du
  registre ; vérifiez-les toujours sur le registre de la consultation.</li>
 <li>Le registre ne couvre que les projets que l’administration ou le maître d’ouvrage y saisissent.</li>
</ul>
<h3>Données personnelles</h3>
<p>Aucun nom de personne physique n’est conservé ni publié. Un maître d’ouvrage introduit par une civilité (M., Mme…)
ou qui est une entreprise individuelle ou agricole (EARL, GAEC, SCEA, EIRL, EURL) est écarté, et son nom est remplacé
par «&#8239;[personne physique]&#8239;» dans le titre du projet. Seules les sociétés, les collectivités et les
établissements publics sont nommés. Les observations d’espèces ne sont publiées qu’en totaux par commune, jamais
avec leurs coordonnées.</p>
"""


def build(estado: dict, docs_dir: Path, today: date | None = None, since: date | None = None) -> list[Path]:
    """Write docs/fr/index.html and docs/fr/archives.html; returns their paths."""
    from .fr_projets import SINCE

    today = today or date.today()
    since = since or SINCE
    open_, closed = split(estado, today)
    out = docs_dir / "fr"
    out.mkdir(parents=True, exist_ok=True)
    method = _method(since)
    soon = sum(1 for a in open_ if days_left(a, today) <= URGENT_DAYS)
    with_natura = sum(1 for a in open_ if a.get("natura"))
    depts = {a.get("departement") for a in open_ if a.get("departement")}
    heading = "Observatoire des <span>consultations</span> environnementales"
    title = "Observatoire des consultations environnementales"
    figures = [
        (i18n.n(len(open_), LANG), "consultations ouvertes"),
        (i18n.n(soon, LANG), f"closent dans {URGENT_DAYS} jours ou moins"),
        (i18n.n(with_natura, LANG), "touchent une commune Natura 2000"),
        (i18n.n(len(depts), LANG), "départements"),
    ]
    lede = ("Les projets soumis à évaluation environnementale en France dont la consultation du public est ouverte, "
            "situés sur leurs communes et croisés avec Natura 2000 et les observations d’animaux menacés. "
            f"Mis à jour le {i18n.day(today.isoformat(), LANG)}.")
    notice = ('<p class="aviso">Le croisement avec Natura 2000 et les espèces menacées porte sur la <b>commune entière</b>, '
              "pas sur l’emprise du projet : il signale une zone à regarder, pas une atteinte. La date de clôture vient du "
              "registre : vérifiez-la sur le registre de la consultation avant de déposer une observation.</p>")
    paths = [out / "index.html", out / "archives.html"]
    paths[0].write_text(page(title, lede, notice + _table(open_, today, open_=True), site_nav("index.html"),
                             heading=heading, figures=figures, method=method), encoding="utf-8")
    lede_closed = (f"Les consultations closes depuis le début de la série ({i18n.day(since.isoformat(), LANG)}), "
                   "la plus récente d’abord. Les documents restent sur le registre.")
    paths[1].write_text(page(f"Archives · {title}", lede_closed, _table(closed, today, open_=False), site_nav("archives.html"),
                             heading="Consultations <span>closes</span>",
                             figures=[(i18n.n(len(closed), LANG), "consultations closes")], method=method), encoding="utf-8")
    return paths
