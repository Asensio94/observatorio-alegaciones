from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
DOCS_DIR = ROOT / "docs"  # web estática publicada con GitHub Pages
ESTADO_PATH = DATA_DIR / "estado.json"  # estado acumulado de anuncios detectados
# Volcados versionados de fuentes que no son accesibles desde GitHub Actions (se descargan desde España y se suben al repo)
FUENTES_DIR = DATA_DIR / "fuentes"

for d in (CACHE_DIR / "boe", CACHE_DIR / "geo", CACHE_DIR / "natura", CACHE_DIR / "gbif", CACHE_DIR / "boc_cantabria", FUENTES_DIR / "boc_cantabria", DOCS_DIR / "informes"):
    d.mkdir(parents=True, exist_ok=True)

USER_AGENT = "observatorio-alegaciones/0.1 (proyecto abierto de conservacion)"

# BOE
BOE_SUMARIO_URL = "https://www.boe.es/datosabiertos/api/boe/sumario/{yyyymmdd}"
BOE_XML_URL = "https://www.boe.es/diario_boe/xml.php?id={id}"

# BOC (Boletín Oficial de Cantabria): sin API; sumario por fecha (POST) → XML diario con texto completo
BOC_SUMARIO_URL = "https://boc.cantabria.es/boces/boletines.do"
BOC_XML_URL = "https://boc.cantabria.es/boces/verXmlAction.do?idBlob={id}"
BOC_ANUNCIO_URL = "https://boc.cantabria.es/boces/verAnuncioAction.do?idAnuBlob={id}"
BOC_CVE_URL = "https://boc.cantabria.es/boces/boletines.do?cve={cve}&boton=Buscar"

# Fuentes disponibles (clave de la CLI → etiqueta)
FUENTES = {"boe": "BOE", "boc_cantabria": "BOC (Cantabria)"}

# EEA Natura 2000 (ArcGIS REST). Capas: 0 Habitats (LIC/ZEC), 1 Aves (ZEPA), 2 ambas.
EEA_NATURA_URL = (
    "https://bio.discomap.eea.europa.eu/arcgis/rest/services/ProtectedSites/Natura2000Sites/MapServer/{layer}/query"
)
EEA_LAYERS = {0: "LIC/ZEC", 1: "ZEPA", 2: "LIC/ZEC+ZEPA"}

# GBIF
GBIF_OCC_URL = "https://api.gbif.org/v1/occurrence/search"
GBIF_SPECIES_URL = "https://api.gbif.org/v1/species/{key}"
GBIF_THREAT_CATEGORIES = ["CR", "EN", "VU", "NT"]
GBIF_YEAR_FROM = 2005
AVES_TAXON_KEY = 212

# Nominatim
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_MIN_INTERVAL = 1.1  # segundos entre peticiones (política de uso)

# Buffer alrededor del municipio para el cruce con Natura/GBIF (grados; ~0.02 = 2 km)
GEO_BUFFER_DEG = 0.0
