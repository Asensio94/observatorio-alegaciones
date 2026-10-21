"""Number formats and the labels a reader sees, one dictionary per language.

Each country's pages are written in that country's language: Spain's in Spanish, France's in French.
The data (data/estado*.json, docs/signals.json) stays in canonical, language-independent values; only
what a reader sees goes through here. Same pattern as humedales/i18n.py in vigilancia-humedales.
"""
from __future__ import annotations

from datetime import date

LANG_BY_COUNTRY = {"ES": "es", "FR": "fr"}

# French typography: a narrow no-break space as thousands separator and before «%».
_NNBSP = " "


def lang_of(country: str) -> str:
    return LANG_BY_COUNTRY.get(country, "es")


def n(v: float, lang: str) -> str:
    """Integer with the thousands separator of the language: 46.709 / 46 709."""
    s = f"{v:,.0f}"
    return s.replace(",", "." if lang == "es" else _NNBSP)


def d(v: float, lang: str, nd: int = 1) -> str:
    """Decimal with comma, in both languages: 2,7."""
    return f"{v:.{nd}f}".replace(".", ",")


def p(x: float, lang: str) -> str:
    """A fraction as a percentage without decimals: 15 % (no-break space) / 15 % (narrow)."""
    return f"{100 * x:.0f}{chr(0xA0) if lang == 'es' else _NNBSP}%"


_MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
              "septembre", "octobre", "novembre", "décembre")


def day(iso: str | None, lang: str) -> str:
    """«2026-10-01» → «01/10/2026» (es) or «1er octobre 2026» (fr)."""
    if not iso:
        return ""
    x = date.fromisoformat(iso)
    if lang == "fr":
        return f"{'1er' if x.day == 1 else x.day} {_MONTHS_FR[x.month - 1]} {x.year}"
    return f"{x:%d/%m/%Y}"


# The category keys are shared with Spain (data); their names are not.
CATEGORIES = {
    "fr": {
        "eolica": "éolien", "fotovoltaica": "photovoltaïque", "red_electrica": "réseau électrique",
        "hidrogeno_baterias": "hydrogène et stockage", "hidrocarburos_gas": "hydrocarbures et gaz",
        "mineria": "carrières et mines", "transporte": "transports", "puertos_costas": "ports et littoral",
        "hidraulica": "ouvrages hydrauliques", "agua_concesion": "eau et assainissement",
        "urbanismo_industria": "aménagement et industrie", "otros": "autres",
    },
}

# Natura 2000 site types as each country names them: LIC/ZEC and ZEPA are SIC/ZSC and ZPS in France.
NATURA_TYPES = {"fr": {"LIC/ZEC": "ZSC / SIC (directive Habitats)", "ZEPA": "ZPS (directive Oiseaux)",
                       "LIC/ZEC+ZEPA": "ZSC et ZPS"}}

IUCN = {"fr": {"CR": "en danger critique", "EN": "en danger", "VU": "vulnérable", "NT": "quasi menacée"}}

CLASSES = {"fr": {"Aves": "oiseaux", "Mammalia": "mammifères", "Amphibia": "amphibiens", "Reptilia": "reptiles",
                  "Insecta": "insectes", "Actinopterygii": "poissons", "Gastropoda": "gastéropodes",
                  "Bivalvia": "bivalves", "Malacostraca": "crustacés", "Arachnida": "arachnides"}}


def label(table: dict, lang: str, key: str) -> str:
    return table.get(lang, {}).get(key, key)
