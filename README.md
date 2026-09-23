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

## Vertical del litoral y del suelo turístico

La costa no se transforma con un proyecto de 300 MW: se transforma con cincuenta expedientes de quince
días que por separado parecen menores. Una reforma, un cierre de parcela, cinco viviendas, un aparcamiento
«de temporada». El observatorio principal descarta a propósito ese material (`extract.EXCLUIR` tira las
viviendas unifamiliares, los cambios de uso y las reformas) para no ahogarse en ruido. El módulo
`litoral.py` lee justo ese montón de descartes, y por eso es un vertical aparte con su estado
(`data/estado_litoral.json`) y su página propios.

Dos fuentes y dos regímenes:

- **BOE, sección V-B, órganos de Costas** (demarcaciones y servicios provinciales, de toda España):
  concesiones y autorizaciones de ocupación del dominio público marítimo-terrestre, prórrogas, deslindes,
  reservas demaniales y movimientos de arena. Ley 22/1988 de Costas y RD 876/2014. Del BOE **solo** entra
  lo que firma un órgano de Costas: en esa misma sección conviven las confederaciones hidrográficas, y un
  deslinde del dominio público hidráulico en Jaén no es de este vertical.
- **BOC de Cantabria, sección 7 (Urbanismo)**: las autorizaciones en la zona de servidumbre de protección
  del dominio público marítimo-terrestre, que son competencia autonómica (art. 229 de la Ley de Cantabria
  5/2022), más el planeamiento municipal (estudios de detalle por el art. 101, modificaciones puntuales del
  plan general por el art. 110) y la evaluación ambiental estratégica de esos planes. Del boletín autonómico
  entra todo el territorio: filtrar por municipio costero dejaría fuera Potes o Soba, que es donde también
  aprieta la presión turística.

Cada expediente se clasifica por trámite y se le marcan **señales** con su apoyo normativo: uso residencial
en la servidumbre (art. 25.1.a de la Ley de Costas, la señal que más pesa), afección a playa o duna
(arts. 32 y 44.5), aumento de edificabilidad en la zona de influencia de los 500 metros (art. 30.1.b),
suelo ordenado por el Plan de Ordenación del Litoral (Ley de Cantabria 2/2004), tramitación por estudio de
detalle, parcelación de la finca, informe ambiental estratégico simplificado (arts. 29-32 de la Ley
21/2013), suspensión de licencias (art. 89 de la Ley 5/2022) y frente costero. Los puntos ordenan la
lectura; **no son un dictamen**: la prohibición del art. 25.1.a tiene excepciones y regímenes transitorios,
y solo el expediente dice si aplican. A partir del umbral de puntos se cruza con Red Natura 2000 y GBIF.

```bash
python -m observatorio.cli litoral --days 20                  # BOE (Costas) + BOC, web incluida
python -m observatorio.cli litoral --days 55 --min-puntos 5    # solo cruza los expedientes más señalados
```

La página [Litoral](https://asensio94.github.io/observatorio-alegaciones/litoral.html) separa lo que tiene
plazo abierto de lo cerrado, y mantiene lo cerrado a la vista porque el patrón importa más que el
expediente suelto: el mismo tramo de costa aparece una y otra vez, y la autorización, cuando llega, sí se
puede recurrir.

## Después del sí: qué se cumple de cada declaración

Una declaración de impacto ambiental favorable no es el final del expediente: es una lista de obligaciones.
El módulo `condicionado.py` lee las resoluciones de la Dirección General de Calidad y Evaluación Ambiental
en la sección III del BOE (desde 2022) y, de cada una, extrae:

- **tipo y sentido**: declaración, informe de impacto ambiental (evaluación simplificada) o modificación de
  condiciones; favorable con condiciones, desfavorable, favorable en parte o sin efectos significativos. Las
  correcciones de errores no son fichas: se anotan en la resolución a la que corrigen.
- **promotor, órgano sustantivo y provincias**, desde los antecedentes y el título.
- **el condicionado troceado**: cada condición con su número, el factor ambiental al que se refiere, el
  bloque (condiciones generales, medidas, programa de vigilancia), unos temas (avifauna, quirópteros,
  seguimiento de mortalidad, agua, suelo, paisaje…) y si obliga a **entregar** algo: informes, planes,
  estudios o comunicaciones que alguien debería poder pedir después.
- **la vigencia**: cuatro años desde la publicación para empezar la ejecución (art. 43.1 de la Ley 21/2013;
  art. 47.4 para los informes de impacto ambiental), prorrogables otros dos. La base no sabe si la obra ha
  empezado: la fecha es la de caducidad **si no ha empezado**, y es justo lo que hay que preguntar.
- **las modificaciones**, enlazadas con la declaración original cuando esta es de 2022 o posterior.

Con eso genera, para cada declaración con condiciones, una **solicitud de acceso a la información
ambiental** (Ley 27/2006) lista para firmar, en dos versiones: al órgano sustantivo, que es quien vigila el
cumplimiento (art. 52 de la Ley 21/2013), pidiendo la autorización, el inicio de obras, los informes de
seguimiento con su listado de comprobación, los documentos que el condicionado exige y, si lo hay, el
seguimiento de mortalidad de fauna; y al órgano ambiental, por la vigencia, las prórrogas y las
modificaciones. El plazo de respuesta es de un mes (art. 10.2.c), ampliable a dos si se justifica.

```bash
python -m observatorio.cli condicionado --days 8                     # lo que entra cada día (Actions)
python -m observatorio.cli condicionado --desde 2022-01-01 --sin-web # relleno histórico
python -m observatorio.cli solicitud BOE-A-2025-19771 --a sustantivo --salida escudo.txt
python -m observatorio.cli solicitud BOE-A-2025-19771 --presentada 2026-09-24 --registro REGAGE…
python -m observatorio.cli mis-solicitudes                           # cuándo vence el mes de cada una
```

La página [Después del sí](https://asensio94.github.io/observatorio-alegaciones/condicionado.html) filtra
por tipo, sentido, categoría, provincia y tema, marca lo que caduca en los próximos doce meses y abre cada
declaración con su condicionado y sus dos solicitudes. La base completa está en `docs/datos/condicionado/`
(un JSON por resolución más `indice.json`), para quien quiera usarla sin la página.

**Límites.** Solo el BOE, que recoge lo que evalúa el Ministerio. Lo autonómico va en cada boletín: el del
BOC de Cantabria y el BOCYL están pendientes. El troceado sigue la numeración de cada resolución, que no
es uniforme; en unas pocas el texto no trae epígrafe de condiciones reconocible y salen sin condiciones.
Los registros de solicitudes presentadas (`data/mis_solicitudes.json`) no se versionan.

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
  litoral.py   vertical del litoral: costas, servidumbre, planeamiento y suelo turístico
  condicionado.py  «Después del sí»: DIA del BOE, condicionado troceado, vigencia y solicitudes Ley 27/2006
  condicionado_web.py  página docs/condicionado.html (tabla, filtros y ficha de cada declaración)
  site.py      estado acumulado (data/estado.json) y web estática (docs/)
  cli.py       punto de entrada
data/
  estado.json  todos los anuncios detectados, con su fecha límite y cruces
  estado_litoral.json  lo mismo para el vertical del litoral (fuentes y señales distintas)
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
- Litoral: distancia real a la ribera del mar (hoy la señal de frente costero es una lista de municipios),
  ámbito del Plan de Ordenación del Litoral como capa, y acumulación por tramo de costa: contar cuántos
  expedientes caen en el mismo kilómetro es el argumento de efectos acumulativos que hoy falta.
- Litoral en otras comunidades: la parte del BOE ya cubre toda la costa española; lo que falta es el
  boletín autonómico de cada una (Galicia, Asturias, País Vasco, Andalucía, Levante, Baleares, Canarias).

## Licencia

MIT. Ver `LICENSE`. Los datos proceden de fuentes públicas citadas arriba y conservan sus condiciones de uso.
