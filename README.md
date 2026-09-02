# Observatorio de alegaciones ambientales

Detecta automáticamente proyectos sometidos a **información pública** (parques eólicos, fotovoltaicas,
líneas eléctricas, minería, infraestructuras…) publicados en el BOE, los geolocaliza por término municipal
y los cruza con la **Red Natura 2000** y con los registros de **especies amenazadas** (GBIF).
El objetivo es avisar a tiempo, dentro del plazo de alegaciones, a grupos locales y organizaciones
de conservación.

## Estado

Prototipo v0.1 (septiembre 2026). Solo BOE, sección V-B. Extracción por reglas (sin LLM).

## Uso

```bash
python -m observatorio.cli run --days 8
```

Genera `output/informe_<desde>_<hasta>.html` (mapa + fichas) y un JSON con los mismos datos.

Opciones: `--hasta 2026-09-01`, `--min-prioridad 3`, `--sin-gbif`.

## Fuentes

| Fuente | Uso | Acceso |
|---|---|---|
| BOE datos abiertos (`/datosabiertos/api/boe/sumario/AAAAMMDD`) | sumarios diarios y XML de cada anuncio | público, sin clave |
| EEA Natura 2000 (ArcGIS REST) | espacios LIC/ZEC/ZEPA que intersectan el municipio | público |
| GBIF occurrence API | especies con categoría UICN CR/EN/VU/NT en la zona | público |
| Nominatim (OSM) | polígonos municipales | público, 1 petición/s |

## Pipeline

1. `boe.py`: descarga sumarios, filtra sección V-B, obtiene texto de cada anuncio.
2. `extract.py`: filtra candidatos (información pública + tipología), clasifica, extrae municipios,
   provincias, plazo, promotor, potencia y expediente.
3. `geo.py`: resuelve municipios a polígonos y los une.
4. `natura.py` / `species.py`: cruces espaciales.
5. `report.py`: informe HTML con mapa folium y fichas.

Todo se cachea en `data/cache/` para poder iterar sin repetir descargas.

## Próximos pasos

- Boletines autonómicos (DOG, BOCM, BOJA, DOGC…): la mayoría de proyectos < 50 MW se tramitan ahí.
- Extracción con LLM de la huella real (coordenadas UTM, parcelas) en lugar del municipio completo.
- IBAs (SEO/BirdLife), Catálogo Español de Especies Amenazadas, hábitats de interés comunitario.
- Alertas por correo/Telegram con el plazo restante y borrador de alegación.
- Servicio web con suscripción por provincia o comarca.
