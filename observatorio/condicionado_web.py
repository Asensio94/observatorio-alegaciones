"""Página «Después del sí»: tabla de DIA con su condicionado y solicitud de información para cada una.

La tabla se pinta en el navegador a partir de docs/datos/condicionado/indice.json y el detalle de cada
resolución se pide al abrirla (su JSON trae las condiciones y las dos solicitudes ya redactadas), así la
página pesa poco aunque la base tenga decenas de miles de condiciones.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .condicionado import ETIQUETA_TEMA, INDICE_PATH, PRORROGA_ANOS, VIGENCIA_ANOS
from .report import COLORES, esc, pagina, site_nav

# Result chips keep their meaning colours; the dark variants are lighter so they stay readable.
_DARK_CHIPS = "--s-cond:#7cc184;--s-parc:#e3b450;--s-desf:#f08a80;--s-sin:#7fb6e6;--s-ord:#c39be0;--doc:#7fb6e6;"
CSS_EXTRA = (
    ":root{--s-cond:#2f6b34;--s-parc:#8a6100;--s-desf:#b3261e;--s-sin:#1d5a8a;--s-ord:#6a2d8f;--doc:#1d5a8a}"
    f"@media (prefers-color-scheme: dark){{:root:not([data-theme=\"light\"]){{{_DARK_CHIPS}}}}}"
    f":root[data-theme=\"dark\"]{{{_DARK_CHIPS}}}"
    """
 .filtros{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:16px 0;padding:12px 16px;background:var(--paper);border:1px solid var(--line)}
 .filtros input[type=search]{min-width:260px;padding:6px 8px} .filtros select{padding:5px}
 .filtros input,.filtros select{font:15px/1.3 var(--font-text);color:var(--ink);background:var(--ground);border:1px solid var(--line)}
 .filtros label{font-size:15px;white-space:nowrap}
 #cuenta{color:var(--muted);font:14px/1.4 var(--font-data);margin:6px 0}
 tr.fila{cursor:pointer} tr.fila:hover td{background:var(--ground)} tr.fila:focus-visible td{outline:2px solid var(--accent)}
 td.num{text-align:right;font-family:var(--font-data);font-variant-numeric:tabular-nums;white-space:nowrap}
 .sent{padding:1px 7px;font:600 12px/1.4 var(--font-title);text-transform:uppercase;letter-spacing:.06em;white-space:nowrap;border:1px solid;background:color-mix(in srgb,currentColor 9%,transparent)}
 .s-condicionada{color:var(--s-cond)} .s-parcial{color:var(--s-parc)} .s-desfavorable{color:var(--s-desf)}
 .s-sin_eia{color:var(--s-sin)} .s-a_ordinaria{color:var(--s-ord)} .s-{color:var(--muted)}
 .vence{color:var(--urgent);font-weight:600}
 #detalle{background:var(--paper);border:1px solid var(--line);box-shadow:var(--shadow);padding:16px;margin:20px 0}
 #detalle h2{margin-top:0;padding-right:7rem}
 .cerrar{float:right;padding:6px 12px;cursor:pointer;font:600 14px/1.2 var(--font-title);text-transform:uppercase;letter-spacing:.06em;color:var(--ink);background:var(--paper);border:1px solid var(--line)}
 .tag{display:inline-block;font:500 12px/1.5 var(--font-data);background:var(--ground);color:var(--ink);border:1px solid var(--line);padding:0 6px;margin:0 4px 3px 0}
 .tag.doc{color:var(--doc);border-color:currentColor}
 .vista{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px 32px;margin:12px 0 4px}
 .vista .grupo{margin-top:0}
 .fases{list-style:none;padding:0;margin:10px 0 0;display:flex;position:relative}
 .fases::before{content:"";position:absolute;left:10%;right:10%;top:16px;border-top:2px solid var(--line)}
 .fases li{flex:1;position:relative}
 .fases button,.factores button{all:unset;box-sizing:border-box;cursor:pointer;width:100%;color:var(--ink)}
 .fases button{display:flex;flex-direction:column;align-items:center;gap:5px;text-align:center;font:13px/1.25 var(--font-text)}
 .fases .n{display:grid;place-items:center;min-width:34px;height:34px;padding:0 4px;background:var(--paper);border:2px solid var(--accent);font:600 14px/1 var(--font-data);color:var(--accent)}
 .fases button[aria-pressed=true] .n{background:var(--accent);color:var(--paper)}
 .fases button:disabled{cursor:default;opacity:.4}
 .factores{list-style:none;padding:0;margin:8px 0 0}
 .factores button{display:grid;grid-template-columns:minmax(7rem,11rem) 1fr 2.4rem;gap:10px;align-items:center;padding:3px 0;font:14px/1.3 var(--font-text)}
 .factores .barra{height:10px;background:var(--ground);border:1px solid var(--line)} .factores .barra i{display:block;height:100%;background:var(--accent)}
 .factores .n{text-align:right;font:13px/1 var(--font-data);color:var(--muted)}
 .factores:has([aria-pressed=true]) button:not([aria-pressed=true]),.fases:has([aria-pressed=true]) button:not([aria-pressed=true]){opacity:.45}
 .fases button:not(:disabled):hover .t,.factores button:hover .t{text-decoration:underline}
 .fases button[aria-pressed=true] .t,.factores button[aria-pressed=true] .t{font-weight:600;color:var(--accent)}
 .vista .nota{margin:8px 0 0;font-size:13px;color:var(--muted)}
 .barra-cond{position:sticky;top:0;z-index:1;display:flex;gap:8px 10px;flex-wrap:wrap;align-items:center;margin:12px -16px 0;padding:10px 16px;background:var(--paper);border-bottom:1px solid var(--line)}
 .barra-cond button{padding:6px 12px;cursor:pointer;font:600 14px/1.2 var(--font-title);text-transform:uppercase;letter-spacing:.06em;color:var(--ink);background:var(--paper);border:1px solid var(--line)}
 .barra-cond button[aria-pressed=true],.barra-cond #todas{border-color:var(--accent);color:var(--accent)}
 #cuenta-cond{font:14px/1.4 var(--font-data);color:var(--muted)}
 details.bloque{margin:18px 0 0}
 details.bloque>summary{cursor:pointer;list-style:none;padding:6px 0;border-bottom:2px solid var(--line);font:600 15px/1.2 var(--font-title);color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
 details.bloque>summary::before{content:"▸ "} details.bloque[open]>summary::before{content:"▾ "}
 details.bloque>summary .n,li.cond .num{font-family:var(--font-data)}
 summary::-webkit-details-marker{display:none}
 .conds{list-style:none;padding:0;margin:0}
 li.cond{border-bottom:1px solid var(--line);font-size:15px;line-height:1.5}
 li.cond.entrega{border-left:3px solid var(--accent)}
 li.cond>details>summary{cursor:pointer;list-style:none;display:grid;grid-template-columns:3.2rem minmax(0,1fr);gap:10px;padding:8px 8px 8px 0}
 li.cond>details>summary:hover{background:var(--ground)}
 li.cond .num{font-weight:600;font-size:13px;line-height:1.7;color:var(--muted);text-align:right;white-space:nowrap}
 li.cond .num::before{content:"▸ "} li.cond>details[open] .num::before{content:"▾ "}
 li.cond .cab{font-weight:600} li.cond .cab .tag{font-weight:500}
 li.cond .extracto{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;color:var(--muted)}
 li.cond>details[open] .extracto{display:none}
 li.cond .cuerpo{padding:0 8px 12px calc(3.2rem + 10px)} li.cond .cuerpo p{margin:0 0 8px}
 li.cond dl{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px;margin:0;font-size:14px}
 li.cond dt{color:var(--muted)} li.cond dd{margin:0}
 textarea.sol{width:100%;min-height:22rem;font:13px/1.45 var(--font-data);padding:10px;color:var(--ink);background:var(--ground);border:1px solid var(--line)}
 .botones{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}
 .botones button{padding:6px 12px;cursor:pointer;font:600 14px/1.2 var(--font-title);text-transform:uppercase;letter-spacing:.06em;color:var(--ink);background:var(--paper);border:1px solid var(--line)}
 .botones button[aria-pressed=true]{border-color:var(--accent);color:var(--accent)}
 .grupo{margin:16px 0 4px;font:600 15px/1.2 var(--font-title);color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
 @media (max-width:700px){.filtros input[type=search]{min-width:0;width:100%} .vista{grid-template-columns:1fr} .fases .t{font-size:12px} .factores button{grid-template-columns:7.5rem 1fr 2rem} li.cond>details>summary{grid-template-columns:2.6rem minmax(0,1fr)} li.cond .cuerpo{padding-left:8px}}
"""
)

SENTIDOS = {
    "condicionada": "con condiciones",
    "parcial": "desfavorable en parte",
    "desfavorable": "desfavorable",
    "sin_eia": "sin evaluación ordinaria",
    "a_ordinaria": "a evaluación ordinaria",
    "": "sin determinar",
}
TIPOS = {"dia": "Declaración de impacto ambiental", "iia": "Informe de impacto ambiental",
         "modificacion": "Modificación de condiciones"}

COMO_USAR = f"""
<div class="aviso"><b>Qué es esto.</b> Cada declaración de impacto ambiental (DIA) que formula el Ministerio acaba
con un condicionado: medidas que el promotor está obligado a cumplir y documentos que debe entregar (programa de
vigilancia ambiental, informes de seguimiento de mortalidad de aves y murciélagos, proyectos de medidas
compensatorias…). Aquí están todas las publicadas en el BOE desde 2022, troceadas condición a condición.
Pulsa en una fila para ver su condicionado y una <b>solicitud de información ambiental</b> ya redactada
(Ley 27/2006: un mes para responder) con lo que hay que pedir al órgano que la vigila.</div>
<div class="aviso"><b>Sobre la vigencia.</b> La fecha que se muestra es la que resultaría si el proyecto
<b>no</b> hubiera empezado a ejecutarse: la DIA caduca a los {VIGENCIA_ANOS} años de su publicación en el BOE
(art. 43 de la Ley 21/2013), prorrogables hasta {PRORROGA_ANOS} más si el órgano ambiental lo acuerda. No sabemos si
las obras han empezado; averiguarlo es precisamente lo que pide la solicitud. Una suspensión judicial o una norma
posterior pueden alterar el cómputo. El troceo y las etiquetas son automáticos: compruébalos siempre en el BOE
antes de citar una condición.</div>
"""

JS = r"""
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const HOY = new Date().toISOString().slice(0, 10);
const LIMITE = new Date(Date.now() + 365 * 864e5).toISOString().slice(0, 10);
let FICHAS = [];

function fmt(iso) { return iso ? iso.split('-').reverse().join('/') : ''; }
function sentido(f) { return `<span class="sent s-${esc(f.sentido)}">${esc(SENTIDOS[f.sentido] ?? f.sentido)}</span>`; }
function cat(c) { return c ? `<span class="badge" style="background:${COLORES[c] || '#444'}">${esc(c)}</span>` : ''; }
function vence(f) { return f.vigencia_hasta && f.vigencia_hasta >= HOY && f.vigencia_hasta <= LIMITE; }

function opciones(sel, valores, etiqueta = v => v) {
  for (const v of valores) sel.insertAdjacentHTML('beforeend', `<option value="${esc(v)}">${esc(etiqueta(v))}</option>`);
}

function filtrar() {
  const q = $('#q').value.trim().toLowerCase();
  const tipo = $('#tipo').value, sen = $('#sentido').value, c = $('#cat').value, prov = $('#prov').value, tema = $('#tema').value;
  const soloVence = $('#vence').checked, soloMort = $('#mort').checked;
  const out = FICHAS.filter(f =>
    (!tipo || f.tipo === tipo) && (!sen || f.sentido === sen) && (!c || f.categoria === c) &&
    (!prov || (f.provincias || []).includes(prov)) && (!tema || (f.temas || []).includes(tema)) &&
    (!soloVence || vence(f)) && (!soloMort || f.seguimiento_mortalidad) &&
    (!q || [f.proyecto, f.promotor, f.organo_sustantivo, f.identificador, (f.provincias || []).join(' ')]
      .join(' ').toLowerCase().includes(q)));
  pintar(out);
  try { history.replaceState(null, '', '#' + new URLSearchParams({q, tipo, sen, c, prov, tema, v: soloVence ? 1 : '', m: soloMort ? 1 : ''}).toString().replace(/[^&]+=(&|$)/g, '')); } catch (e) {}
}

function pintar(lista) {
  $('#cuenta').textContent = `${lista.length} de ${FICHAS.length} resoluciones`;
  $('#filas').innerHTML = lista.slice(0, 600).map(f => `
    <tr class="fila" tabindex="0" data-id="${esc(f.identificador)}">
      <td class="num">${fmt(f.fecha_publicacion)}</td>
      <td><b>${esc(f.proyecto || f.identificador)}</b><br><small>${esc(f.promotor || '')}</small></td>
      <td>${cat(f.categoria)}<br><small>${esc(TIPOS[f.tipo] || f.tipo)}</small></td>
      <td>${esc((f.provincias || []).join(', '))}</td>
      <td>${sentido(f)}${(f.modificada_por || []).length ? '<br><small>modificada</small>' : ''}</td>
      <td class="num">${f.n_condiciones || ''}${f.n_entregables ? `<br><small>${f.n_entregables} con entrega</small>` : ''}</td>
      <td class="num ${vence(f) ? 'vence' : ''}">${fmt(f.vigencia_hasta)}</td>
    </tr>`).join('') || '<tr><td colspan="7">Ninguna resolución cumple esos filtros.</td></tr>';
  if (lista.length > 600) $('#cuenta').textContent += ' (se muestran las 600 más recientes; afina los filtros)';
}

const FASES = [['proyecto', 'Proyecto'], ['antes_obras', 'Antes de las obras'], ['obras', 'Obras'],
  ['antes_explotacion', 'Antes de explotar'], ['explotacion', 'Explotación'], ['cese', 'Cese']];
// Each resolution names the environmental factors its own way ("Flora, vegetación e HICs", "Vegetación…"); group them.
const FACTORES = [
  ['Fauna', /fauna|avifauna|quir[oó]pt|lince|pesquer|marisq/i], ['Flora y hábitats', /flora|vegeta|h[aá]bitat|\bhics?\b|montes/i],
  ['Agua', /agua|hidrol|h[ií]dric|riego/i], ['Suelo y geología', /suelo|geol|geomorf|geodiv/i],
  ['Paisaje', /paisaj/i], ['Patrimonio y vías pecuarias', /patrimon|pecuari|arqueol/i],
  ['Población y salud', /poblaci|salud|socioecon/i], ['Aire, ruido y clima', /atm[oó]sf|\baire\b|ruido|ac[uú]st|clim|lum[ií]n/i],
  ['Red Natura y biodiversidad', /natura 2000|biodivers|espacios|\bzepa\b|\blic\b|\bzec\b/i],
  ['Riesgos y accidentes', /vulnerab|accident|cat[aá]strof|riesgo/i],
  ['Medidas compensatorias', /compensator/i],
  ['Residuos y bienes materiales', /residu|bienes materiales|material/i],
  ['Efectos acumulativos', /sinergi|acumulativ|transfronteriz/i],
];
const GRUPOS = {generales: 'Condiciones generales', medidas: 'Medidas y condiciones específicas', pva: 'Programa de vigilancia ambiental'};

function factorDe(c) {
  if (!c.factor) return 'Sin factor';
  for (const [nombre, re] of FACTORES) if (re.test(c.factor)) return nombre;
  return 'Otros';
}

function condLi(c, i) {
  const fases = (c.momento || []).map(m => (FASES.find(f => f[0] === m) || [m, m])[1]);
  const datos = [['Cuándo', fases.join(' · ')], ['Periodicidad', c.periodicidad], ['Duración', c.duracion],
    ['Destinatario', (c.destinatarios || []).join('; ')]].filter(x => x[1]);
  return `<li class="cond${c.entregable ? ' entrega' : ''}" data-i="${i}"><details><summary>
    <span class="num">${esc(c.num)}</span>
    <span><span class="cab">${esc(c.factor)} ${c.entregable ? '<span class="tag doc">entrega de documento</span>' : ''}${(c.temas || []).map(t => `<span class="tag">${esc(TEMAS[t] || t)}</span>`).join('')}</span>
    <span class="extracto">${esc(c.texto)}</span></span></summary>
    <div class="cuerpo"><p>${esc(c.texto).replace(/\n/g, '<br>')}</p>
    ${datos.length ? `<dl>${datos.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}</div></details></li>`;
}

function condicionado(conds) {
  const ent = conds.filter(c => c.entregable).length;
  const porFase = Object.fromEntries(FASES.map(([k]) => [k, conds.filter(c => (c.momento || []).includes(k)).length]));
  const sinFase = conds.filter(c => !(c.momento || []).length).length;
  const porFactor = {};
  conds.forEach(c => { const f = factorDe(c); porFactor[f] = (porFactor[f] || 0) + 1; });
  const ultimo = f => f === 'Sin factor' ? 2 : f === 'Otros' ? 1 : 0;
  const factores = Object.entries(porFactor).sort((a, b) => ultimo(a[0]) - ultimo(b[0]) || b[1] - a[1]);
  const max = Math.max(...factores.map(x => x[1]));
  let h = `<section aria-labelledby="cond-h"><h3 id="cond-h">Condicionado</h3>
    <p class="sub">${conds.length} condiciones, ${ent} con entrega de documentos. Pulsa una fase o un factor para quedarte solo con sus condiciones.</p>
    <div class="vista">
     <div><div class="grupo">Cuándo obliga</div>
      <ol class="fases">${FASES.filter(([k]) => k !== 'antes_explotacion' || porFase[k]).map(([k, t]) =>
        `<li><button type="button" data-fase="${k}" aria-pressed="false"${porFase[k] ? '' : ' disabled'}><span class="n">${porFase[k]}</span><span class="t">${t}</span></button></li>`).join('')}</ol>
      ${sinFase ? `<p class="nota">${sinFase} de ${conds.length} no dicen en qué fase: rigen durante toda la vida del proyecto o el texto no lo precisa.</p>` : ''}</div>
     <div><div class="grupo">Qué protege</div>
      <ul class="factores">${factores.map(([f, v]) =>
        `<li><button type="button" data-factor="${esc(f)}" aria-pressed="false"><span class="t">${esc(f)}</span><span class="barra"><i style="width:${(100 * v / max).toFixed(1)}%"></i></span><span class="n">${v}</span></button></li>`).join('')}</ul></div>
    </div>
    <div class="barra-cond">
     <button type="button" id="todas" aria-expanded="false">Desplegar todas</button>
     <button type="button" id="solo-ent" aria-pressed="false">Solo con entrega (${ent})</button>
     <button type="button" id="limpiar" hidden>Quitar filtro</button>
     <span id="cuenta-cond" aria-live="polite"></span>
    </div>`;
  for (const [clave, titulo] of Object.entries(GRUPOS)) {
    const gs = conds.map((c, i) => [c, i]).filter(([c]) => c.bloque === clave);
    if (!gs.length) continue;
    h += `<details class="bloque" open><summary>${titulo} · <span class="n">${gs.length}</span></summary>
      <ol class="conds">${gs.map(([c, i]) => condLi(c, i)).join('')}</ol></details>`;
  }
  return h + '</section>';
}

function activarCondicionado(d, conds) {
  const st = {fase: '', factor: '', ent: false};
  const items = [...d.querySelectorAll('li.cond')];
  const aplicar = () => {
    let vis = 0;
    for (const li of items) {
      const c = conds[li.dataset.i];
      const ok = (!st.fase || (c.momento || []).includes(st.fase)) && (!st.factor || factorDe(c) === st.factor) && (!st.ent || c.entregable);
      li.hidden = !ok; vis += ok;
    }
    d.querySelectorAll('details.bloque').forEach(b => {
      const n = b.querySelectorAll('li.cond:not([hidden])').length;
      b.hidden = !n; b.querySelector('summary .n').textContent = n;
    });
    d.querySelectorAll('[data-fase]').forEach(b => b.setAttribute('aria-pressed', b.dataset.fase === st.fase));
    d.querySelectorAll('[data-factor]').forEach(b => b.setAttribute('aria-pressed', b.dataset.factor === st.factor));
    d.querySelector('#solo-ent').setAttribute('aria-pressed', st.ent);
    const filtrado = st.fase || st.factor || st.ent;
    d.querySelector('#limpiar').hidden = !filtrado;
    d.querySelector('#cuenta-cond').textContent = filtrado ? `${vis} de ${conds.length} condiciones` : '';
  };
  d.querySelectorAll('[data-fase]').forEach(b => b.onclick = () => { st.fase = st.fase === b.dataset.fase ? '' : b.dataset.fase; aplicar(); });
  d.querySelectorAll('[data-factor]').forEach(b => b.onclick = () => { st.factor = st.factor === b.dataset.factor ? '' : b.dataset.factor; aplicar(); });
  d.querySelector('#solo-ent').onclick = () => { st.ent = !st.ent; aplicar(); };
  d.querySelector('#limpiar').onclick = () => { st.fase = st.factor = ''; st.ent = false; aplicar(); };
  const todas = d.querySelector('#todas');
  todas.onclick = () => {
    const desplegar = todas.getAttribute('aria-expanded') !== 'true';
    d.querySelectorAll('details.bloque').forEach(b => { b.open = true; });
    items.forEach(li => { li.firstElementChild.open = desplegar; });
    todas.setAttribute('aria-expanded', desplegar);
    todas.textContent = desplegar ? 'Replegar todas' : 'Desplegar todas';
  };
  aplicar();
}

async function abrir(id) {
  const d = $('#detalle');
  d.hidden = false;
  d.innerHTML = '<p>Cargando…</p>';
  let f;
  try { f = await (await fetch(`datos/condicionado/${id}.json`)).json(); }
  catch (e) { d.innerHTML = `<p>No se pudo cargar ${esc(id)}. Recarga la página e inténtalo de nuevo.</p>`; return; }
  const conds = f.condiciones || [];
  let html = `<button type="button" class="cerrar" id="cerrar">Cerrar ✕</button><h2>${esc(f.proyecto || f.identificador)}</h2>
    <table class="meta">
      <tr><th>Resolución</th><td>${esc(TIPOS[f.tipo] || f.tipo)} · ${sentido(f)} · resuelta el ${fmt(f.fecha_resolucion)}, publicada el ${fmt(f.fecha_publicacion)}
        · <a href="${esc(f.url_html)}" target="_blank" rel="noopener">${esc(f.identificador)} en el BOE</a>${f.url_pdf ? ` · <a href="${esc(f.url_pdf)}" target="_blank" rel="noopener">PDF</a>` : ''}</td></tr>
      <tr><th>Promotor</th><td>${esc(f.promotor) || '<i>no detectado: ver antecedentes</i>'}</td></tr>
      <tr><th>Órgano sustantivo</th><td>${esc(f.organo_sustantivo) || '<i>no detectado: ver antecedentes</i>'}</td></tr>
      ${f.vigencia_hasta ? `<tr><th>Vigencia si no se ha empezado</th><td>hasta el ${fmt(f.vigencia_hasta)} · con prórroga, como máximo hasta el ${fmt(f.vigencia_max_con_prorroga)}</td></tr>` : ''}
      ${(f.modificada_por || []).length ? `<tr><th>Modificada por</th><td>${f.modificada_por.map(m => `<a href="#" data-abrir="${esc(m)}">${esc(m)}</a>`).join(', ')}</td></tr>` : ''}
      ${f.modifica_a ? `<tr><th>Modifica la DIA</th><td>${f.modifica_a.identificador ? `<a href="#" data-abrir="${esc(f.modifica_a.identificador)}">${esc(f.modifica_a.identificador)}</a>` : 'anterior a 2022, fuera de esta base'}${f.modifica_a.fecha_resolucion ? ' · resolución de ' + fmt(f.modifica_a.fecha_resolucion) : ''}</td></tr>` : ''}
      ${(f.correcciones || []).length ? `<tr><th>Corrección de errores</th><td>${f.correcciones.map(c => `<a href="https://www.boe.es/buscar/doc.php?id=${esc(c)}" target="_blank" rel="noopener">${esc(c)}</a>`).join(', ')}</td></tr>` : ''}
    </table>`;
  if (f.solicitudes) {
    html += `<h3>Solicitud de información ambiental</h3>
      <p class="sub">Dirígela por el Registro Electrónico General (rec.redsara.es) al órgano indicado, rellenando tus datos entre corchetes.
      Al <b>órgano sustantivo</b> le corresponde vigilar el condicionado; al <b>órgano ambiental</b>, la vigencia y las prórrogas.</p>
      <div class="botones"><button data-sol="sustantivo">Al órgano sustantivo</button><button data-sol="ambiental">Al órgano ambiental</button>
      <button id="copiar">Copiar texto</button><button id="bajar">Descargar .txt</button></div>
      <textarea class="sol" id="sol" spellcheck="false" aria-label="Texto de la solicitud"></textarea>`;
  }
  if (conds.length) html += condicionado(conds);
  d.innerHTML = html;
  if (conds.length) activarCondicionado(d, conds);
  $('#cerrar').onclick = () => {
    d.hidden = true;
    const tr = document.querySelector(`tr.fila[data-id="${CSS.escape(f.identificador)}"]`);
    if (tr) { tr.scrollIntoView({block: 'center'}); tr.focus({preventScroll: true}); }
  };
  if (f.solicitudes) {
    const ver = k => { $('#sol').value = f.solicitudes[k]; d.querySelectorAll('[data-sol]').forEach(b => b.setAttribute('aria-pressed', b.dataset.sol === k)); };
    d.querySelectorAll('[data-sol]').forEach(b => b.onclick = () => ver(b.dataset.sol));
    ver('sustantivo');
    $('#copiar').onclick = async () => {
      try { await navigator.clipboard.writeText($('#sol').value); $('#copiar').textContent = 'Copiado'; }
      catch (e) { $('#sol').select(); document.execCommand('copy'); $('#copiar').textContent = 'Copiado'; }
      setTimeout(() => $('#copiar').textContent = 'Copiar texto', 2000);
    };
    $('#bajar').onclick = () => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([$('#sol').value], {type: 'text/plain;charset=utf-8'}));
      a.download = `solicitud_${f.identificador}.txt`; a.click();
    };
  }
  d.querySelectorAll('[data-abrir]').forEach(a => a.onclick = e => { e.preventDefault(); abrir(a.dataset.abrir); });
  d.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}

async function iniciar() {
  try { FICHAS = (await (await fetch('datos/condicionado/indice.json')).json()).fichas; }
  catch (e) { $('#cuenta').textContent = 'No se pudo cargar el índice.'; return; }
  const uniq = xs => [...new Set(xs.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es'));
  opciones($('#cat'), uniq(FICHAS.map(f => f.categoria)));
  opciones($('#prov'), uniq(FICHAS.flatMap(f => f.provincias || [])));
  opciones($('#tema'), Object.keys(TEMAS), t => TEMAS[t]);
  const p = new URLSearchParams(location.hash.slice(1));
  $('#q').value = p.get('q') || ''; $('#tipo').value = p.get('tipo') || ''; $('#sentido').value = p.get('sen') || '';
  $('#cat').value = p.get('c') || ''; $('#prov').value = p.get('prov') || ''; $('#tema').value = p.get('tema') || '';
  $('#vence').checked = !!p.get('v'); $('#mort').checked = !!p.get('m');
  document.querySelectorAll('.filtros input, .filtros select').forEach(el => el.addEventListener('input', filtrar));
  $('#filas').addEventListener('click', e => { const tr = e.target.closest('tr.fila'); if (tr) abrir(tr.dataset.id); });
  $('#filas').addEventListener('keydown', e => { const tr = e.target.closest('tr.fila'); if (tr && e.key === 'Enter') abrir(tr.dataset.id); });
  filtrar();
}
iniciar();
"""


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# «Cómo se calcula» for this page; the years come from observatorio/condicionado.py.
METHOD = f"""
<ol>
 <li><b>Lectura.</b> Se leen las resoluciones de la Dirección General de Calidad y Evaluación Ambiental en la
  sección III del BOE desde 2022; cada mañana entran las de los últimos ocho días.</li>
 <li><b>Tipo y sentido.</b> Cada resolución se clasifica como declaración, informe de impacto ambiental
  (evaluación simplificada) o modificación de condiciones, y por su sentido. Las correcciones de errores no son
  fichas: se anotan en la resolución a la que corrigen.</li>
 <li><b>Datos del expediente.</b> El promotor, el órgano sustantivo y las provincias salen de los antecedentes y
  del título.</li>
 <li><b>Condicionado.</b> El texto se trocea condición a condición, con su número, el factor ambiental, el bloque
  (condiciones generales, medidas, programa de vigilancia), unos temas y si obliga a entregar algún documento.</li>
 <li><b>Vigencia.</b> {VIGENCIA_ANOS} años desde la publicación para empezar la ejecución (art. 43.1 de la Ley
  21/2013; art. 47.4 para los informes de impacto ambiental), prorrogables {PRORROGA_ANOS} más. «Caducan en 12
  meses» marca las que llegan a esa fecha dentro del próximo año.</li>
 <li><b>Modificaciones.</b> Se enlazan con la declaración original cuando esta es de 2022 o posterior.</li>
 <li><b>Solicitud.</b> Para cada declaración con condiciones se redacta una solicitud de información ambiental
  (Ley 27/2006) en dos versiones: al órgano sustantivo, que vigila el cumplimiento (art. 52 de la Ley 21/2013), y
  al órgano ambiental, por la vigencia, las prórrogas y las modificaciones.</li>
</ol>
<h3>Parámetros</h3>
<table class="params">
 <tr><th>Vigencia sin empezar la obra</th><td class="num">{VIGENCIA_ANOS} años</td></tr>
 <tr><th>Prórroga máxima</th><td class="num">{PRORROGA_ANOS} años</td></tr>
 <tr><th>Aviso «caducan en 12 meses»</th><td class="num">365 días</td></tr>
 <tr><th>Filas que muestra la tabla</th><td class="num">600 más recientes</td></tr>
 <tr><th>Plazo de respuesta a la solicitud</th><td class="num">1 mes (art. 10.2.c)</td></tr>
</table>
<h3>Validación</h3>
<p>Pendiente: el troceo y las etiquetas no se han contrastado todavía contra una muestra revisada a mano.</p>
<h3>Límites</h3>
<ul>
 <li>Solo el BOE, que recoge lo que evalúa el Ministerio. Lo autonómico va en cada boletín: el del BOC de
  Cantabria y el BOCYL están pendientes.</li>
 <li>El troceado sigue la numeración de cada resolución, que no es uniforme; en unas pocas el texto no trae
  epígrafe de condiciones reconocible y salen sin condiciones.</li>
 <li>La base no sabe si la obra ha empezado: la vigencia es la de caducidad si no ha empezado.</li>
</ul>
"""


def generar_web(docs_dir: Path, hoy: date | None = None) -> Path:
    hoy = hoy or date.today()
    fichas = json.loads(INDICE_PATH.read_text(encoding="utf-8"))["fichas"]
    limite = (hoy + timedelta(days=365)).isoformat()
    dias = [f for f in fichas if f["tipo"] == "dia"]
    con_cond = [f for f in dias if f["sentido"] in ("condicionada", "parcial")]
    vencen = [f for f in con_cond if f.get("vigencia_hasta") and hoy.isoformat() <= f["vigencia_hasta"] <= limite]
    mort = [f for f in con_cond if f["seguimiento_mortalidad"]]
    n_cond = sum(f["n_condiciones"] for f in fichas)
    n_ent = sum(f["n_entregables"] for f in fichas)
    desde = min(f["fecha_publicacion"] for f in fichas)
    figures = [
        (len(con_cond), "declaraciones con condicionado"),
        (_miles(n_cond), f"condiciones extraídas, {_miles(n_ent)} con entrega de documentos"),
        (len(mort), "exigen seguimiento de mortalidad de fauna"),
        (len(vencen), "caducarían en los próximos 12 meses si no han empezado"),
    ]
    cuerpo = f"""
<style>{CSS_EXTRA}</style>
{COMO_USAR}
<div class="filtros" role="search">
 <input type="search" id="q" placeholder="Proyecto, promotor, provincia…" aria-label="Buscar">
 <select id="tipo" aria-label="Tipo"><option value="">Todos los tipos</option>{''.join(f'<option value="{k}">{esc(v)}</option>' for k, v in TIPOS.items())}</select>
 <select id="sentido" aria-label="Resultado"><option value="">Cualquier resultado</option>{''.join(f'<option value="{k}">{esc(v)}</option>' for k, v in SENTIDOS.items() if k)}</select>
 <select id="cat" aria-label="Categoría"><option value="">Todas las categorías</option></select>
 <select id="prov" aria-label="Provincia"><option value="">Todas las provincias</option></select>
 <select id="tema" aria-label="Tema de las condiciones"><option value="">Cualquier tema</option></select>
 <label><input type="checkbox" id="vence"> caducan en 12 meses</label>
 <label><input type="checkbox" id="mort"> con seguimiento de mortalidad</label>
</div>
<p id="cuenta" aria-live="polite">Cargando…</p>
<div id="detalle" hidden></div>
<div class="wrap"><table class="datos"><thead><tr><th>Publicada</th><th>Proyecto y promotor</th><th>Categoría</th>
<th>Provincias</th><th>Resultado</th><th>Condiciones</th><th>Vigencia hasta</th></tr></thead><tbody id="filas"></tbody></table></div>
<script>
const SENTIDOS = {json.dumps(SENTIDOS, ensure_ascii=False)};
const TIPOS = {json.dumps(TIPOS, ensure_ascii=False)};
const TEMAS = {json.dumps(ETIQUETA_TEMA, ensure_ascii=False)};
const COLORES = {json.dumps(COLORES)};
{JS}
</script>"""
    ruta = docs_dir / "condicionado.html"
    ruta.write_text(
        pagina("Después del sí",
               "Qué se cumple de cada declaración de impacto ambiental: el condicionado de las resoluciones "
               f"publicadas en el BOE desde {desde[:4]}, troceado condición a condición. Actualizado el {hoy:%d/%m/%Y}.",
               cuerpo, site_nav("condicionado.html"),
               heading="Después del <span>sí</span>", figures=figures, method=METHOD),
        encoding="utf-8",
    )
    return ruta
