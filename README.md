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

### Boletines que bloquean IPs extranjeras (BOC Cantabria)

Los servidores del Gobierno de Cantabria no responden a los runners de GitHub (timeout de conexión), así
que el BOC no se puede leer desde Actions. Solución: un equipo en España ejecuta

```bash
python -m observatorio.cli fetch --days 10
```

que guarda un JSON por día en `data/fuentes/boc_cantabria/` (solo secciones 5 y 7, con el texto de cada
anuncio) y lo sube al repositorio. Un *push* en esa carpeta dispara el workflow, que procesa esos días sin
tocar la red del BOC. `scripts/boc_local.ps1` hace todo el ciclo (pull, fetch, commit, push) y está pensado
para el Programador de tareas de Windows. Si el volcado no llega, Actions sigue publicando el BOE con normalidad.

## Aviso metodológico

- El cruce con Natura 2000 y especies se hace con el **término municipal completo**, no con la huella
  real de las obras. Es un **filtro de atención**, no una evaluación de afección: un proyecto puede tener
  espacios protegidos en su municipio y no tocarlos, o al revés.
- La **fecha límite es estimada**: se cuentan días hábiles descontando festivos nacionales y, en el BOC, los
  dos autonómicos fijos de Cantabria (los locales no). Cuando
  el anuncio no indica plazo se asumen 30 días hábiles y se marca como estimado.
- La extracción es por reglas (expresiones regulares), sin LLM. Puede fallar en municipios,
  provincias o plazos. Siempre hay enlace al anuncio original del BOE: **comprueba allí**.

## Seguimiento de expedientes

Alegar es la mitad del trabajo; la otra es enterarse de en qué acaba. El mismo boletín que publica el
trámite de información pública publica después la resolución que lo cierra: la declaración o el informe
de impacto ambiental (art. 41 de la Ley 21/2013) y la autorización administrativa del proyecto
(art. 125 del RD 1955/2000). El módulo `seguimiento.py` detecta esas resoluciones, las clasifica por tipo
y por sentido, e intenta emparejarlas con los expedientes que el observatorio ya venía siguiendo.

El emparejamiento exige coincidencia estructural: mismo expediente, mismo promotor o municipios en común.
Sin eso no empareja, aunque compartan vocabulario. Con 6 puntos o más se considera firme y se enlaza; por
debajo se muestra como *emparejamiento no confirmado*. Se recalcula en cada ejecución, así que una mejora
del algoritmo corrige el pasado. Un plazo de alegaciones abierto manda sobre cualquier resolución
emparejada: un proyecto ya autorizado puede tener otro trámite vivo (el urbanístico, por ejemplo).

La página [Seguimiento](https://asensio94.github.io/observatorio-alegaciones/seguimiento.html) muestra los
expedientes cerrados, las resoluciones sin emparejar y cómo pedir el expediente completo al órgano
sustantivo (Ley 27/2006, un mes para contestar).

```bash
python -m observatorio.cli resoluciones --days 60          # rellena hacia atrás sin repetir el análisis
python -m observatorio.cli mis-alegaciones                 # estado de los escritos propios (registro local)
```

`mis-alegaciones` lee `data/mis_alegaciones.json`, que **no se versiona**: es una lista de objetos con
`proyecto`, `expediente`, `identificador`, `plazo`, `presentada`, `escrito`, `organo` y `notas`, y cruza
cada uno con el estado del observatorio para avisar de plazos a menos de diez días y de resoluciones
nuevas. Con qué proyectos alega cada cual no tiene por qué estar publicado.

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
  mis_alegaciones.json  registro privado de escritos propios (no se versiona)
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
- Seguimiento: enlazar la resolución con el expediente cuando el boletín no repite el número, y
  detectar los recursos contencioso-administrativos que se publican en el propio boletín.

## Licencia

MIT. Ver `LICENSE`. Los datos proceden de fuentes públicas citadas arriba y conservan sus condiciones de uso.
