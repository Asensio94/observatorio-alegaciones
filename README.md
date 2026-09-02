# Observatorio de alegaciones ambientales

**Web:** https://asensio94.github.io/observatorio-alegaciones/

Detecta automáticamente proyectos sometidos a **información pública** (parques eólicos, fotovoltaicas,
líneas eléctricas, minería, infraestructuras, costas, hidráulica…) publicados en el **BOE** y en el
**Boletín Oficial de Cantabria (BOC)**, calcula la
**fecha límite estimada de alegaciones**, los geolocaliza por término municipal y los cruza con la
**Red Natura 2000** y con los registros de **especies animales amenazadas** (GBIF).

El objetivo es que grupos locales y organizaciones de conservación conozcan los proyectos
**mientras aún se puede alegar**. Es un proyecto abierto y sin ánimo de lucro.

## Cómo funciona en producción

- Un flujo de **GitHub Actions** (`.github/workflows/diario.yml`) se ejecuta cada mañana laborable
  (07:30 UTC, lunes a sábado) y también se puede lanzar a mano desde la pestaña *Actions*.
- Lee los últimos 4 días del BOE (sección V-B, *Otros anuncios oficiales*) y del BOC (secciones 5 y 7),
  procesa los candidatos y
  actualiza `data/estado.json` (estado acumulado) y la web estática en `docs/`.
- El propio flujo hace *commit* de los cambios y **GitHub Pages** sirve `docs/` como web pública.
- Coste: cero. Sin servidores, sin base de datos, sin claves de API.

La web tiene tres partes: **alegaciones abiertas** (ordenadas por fecha límite), **histórico** de
plazos vencidos e **informes** por rango de fechas con mapa y ficha de cada proyecto.

## Aviso metodológico

- El cruce con Natura 2000 y especies se hace con el **término municipal completo**, no con la huella
  real de las obras. Es un **filtro de atención**, no una evaluación de afección: un proyecto puede tener
  espacios protegidos en su municipio y no tocarlos, o al revés.
- La **fecha límite es estimada**: se cuentan días hábiles descontando festivos nacionales y, en el BOC, los
  dos autonómicos fijos de Cantabria (los locales no). Cuando
  el anuncio no indica plazo se asumen 30 días hábiles y se marca como estimado.
- La extracción es por reglas (expresiones regulares), sin LLM. Puede fallar en municipios,
  provincias o plazos. Siempre hay enlace al anuncio original del BOE: **comprueba allí**.

## Uso local

```bash
pip install -r requirements.txt
python -m observatorio.cli run --days 8 --hasta 2026-09-01
python -m http.server 8765 --directory docs
```

Opciones: `--days N`, `--hasta AAAA-MM-DD`, `--min-prioridad 3`, `--sin-gbif` (más rápido), `--sin-web`
(solo genera el informe, no toca el estado ni la web), `--fuentes boe,boc_cantabria` (por defecto todas).

## Fuentes

| Fuente | Uso | Acceso |
|---|---|---|
| BOE datos abiertos (`/datosabiertos/api/boe/sumario/AAAAMMDD`) | sumarios diarios y XML de cada anuncio | público, sin clave |
| BOC Cantabria (`boletines.do` por fecha → `verXmlAction.do?idBlob=N`) | XML diario con el texto completo de cada anuncio, CVE y órgano | público, sin clave |
| EEA Natura 2000 (ArcGIS REST) | espacios LIC/ZEC/ZEPA que intersectan el municipio | público |
| GBIF occurrence API | especies animales con categoría UICN CR/EN/VU/NT en la zona (desde 2005) | público |
| Nominatim (OSM) | polígonos municipales | público, 1 petición/s |

## Estructura

```
observatorio/
  boe.py       descarga sumarios, filtra sección V-B, obtiene el texto de cada anuncio
  boc_cantabria.py  BOC: sumario por fecha, XML diario, anuncios de las secciones 5 y 7 con texto
  extract.py   filtra candidatos, clasifica y extrae municipios, provincias, plazo, promotor, MW, expediente
  plazos.py    fecha límite en días hábiles (festivos nacionales 2026-2028)
  geo.py       resuelve municipios a polígonos (Nominatim) y los une
  natura.py    cruce con Red Natura 2000
  species.py   especies amenazadas (GBIF)
  report.py    informe HTML por rango de fechas: mapa folium + fichas
  site.py      estado acumulado (data/estado.json) y web estática (docs/)
  cli.py       punto de entrada
data/
  estado.json  todos los anuncios detectados, con su fecha límite y cruces
  cache/       geo, natura y gbif se versionan (aceleran Actions); boe/ y boc_cantabria/ se ignoran
docs/          web publicada con GitHub Pages
```

## Contribuir

Pull requests bienvenidos: nuevos patrones de detección, correcciones en la extracción, festivos
autonómicos, boletines autonómicos, mejoras de la web. Flujo habitual: *fork* → rama → PR.
Los cambios los revisa y acepta el mantenedor antes de integrarse en `main`.

Si detectas un falso positivo o un proyecto que se ha escapado, abre un *issue* con el identificador
del anuncio del BOE (por ejemplo `BOE-B-2026-12345`).

## Hoja de ruta

- **Más boletines autonómicos** (DOG, BOCM, BOJA, DOGC, BOA…): la mayoría de proyectos de menos de 50 MW
  se tramitan ahí. Cantabria ya está; cada boletín es un módulo `observatorio/<boletin>.py` que devuelve
  objetos `Anuncio` con texto, y el resto del pipeline es común.
- Huella real del proyecto (coordenadas UTM, parcelas catastrales) en lugar del municipio completo. En espera.
- IBAs (SEO/BirdLife), Catálogo Español de Especies Amenazadas, hábitats de interés comunitario.
- Alertas por correo o Telegram y suscripción por provincia o comarca.

## Licencia

MIT. Ver `LICENSE`. Los datos proceden de fuentes públicas citadas arriba y conservan sus condiciones de uso.
