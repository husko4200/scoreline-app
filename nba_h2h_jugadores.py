"""H2H entre jugadores de la NBA: cómo rinde cada uno cuando se enfrentan o cuando son compañeros.

Se analizan los partidos en los que AMBOS jugaron: en equipos contrarios (enfrentados) o en el mismo
equipo (compañeros). Los datos salen del registro de partidos de cada jugador en ESPN.

Cómo usarlo desde otro archivo:
    import nba_h2h_jugadores
    nba_h2h_jugadores.render()
"""
import html
import json
import os
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import graficos

import nba
from common import _session

BASE = getattr(nba, "BASE", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba")
GAMELOG = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{pid}/gamelog?season={season}"

# (nombre en la tabla, columna de ESPN, ¿más alto es mejor?)
ESTADISTICAS = [
    ("Puntos", "PTS", True),
    ("Rebotes", "REB", True),
    ("Asistencias", "AST", True),
    ("Robos", "STL", True),
    ("Tapones", "BLK", True),
    ("Triples", "3PM", True),
    ("Pérdidas", "TO", False),
    ("Minutos", "MIN", True),
]


# ---------------------------------------------------------------------------
# Descarga de datos
# ---------------------------------------------------------------------------
def _get_json(url):
    r = _session.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


def _num(valor):
    """Convierte '27' o '27.5' en número; devuelve None si no se puede."""
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


_TTL_LISTA = 6 * 3600                                                      # la lista se renueva cada 6 horas
_RUTA_LISTA = Path(__file__).parent / ".cache_jugadores" / "jugadores.json"   # copia en disco: sobrevive a reiniciar la app
_HILOS_LISTA = 10                                                          # planteles que se piden a la vez


def _leer_lista_disco(max_edad=None):
    """Lista guardada en disco; None si no existe, está dañada o es más vieja que `max_edad` segundos (None = cualquier edad)."""
    try:
        d = json.loads(_RUTA_LISTA.read_text(encoding="utf-8"))
        if d.get("jugadores") and (max_edad is None or time.time() - d.get("ts", 0) < max_edad):
            return d["jugadores"]
    except Exception:  # noqa: BLE001
        pass
    return None


def _guardar_lista_disco(filas):
    try:
        _RUTA_LISTA.parent.mkdir(exist_ok=True)
        tmp = _RUTA_LISTA.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ts": time.time(), "jugadores": filas}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _RUTA_LISTA)          # reemplazo atómico: nunca queda un archivo a medias
    except Exception:  # noqa: BLE001
        pass


def _plantel(t):
    """Jugadores de un equipo [{id, nombre, equipo}]; None si ESPN falla (se reintenta una vez). Sin llamadas a Streamlit: corre en hilos."""
    for _ in range(2):
        try:
            plantilla = _get_json(f"{BASE}/teams/{t['id']}/roster").get("athletes", [])
        except Exception:  # noqa: BLE001
            continue
        filas = []
        for a in plantilla:
            for j in (a.get("items", []) if "items" in a else [a]):
                if j.get("id"):
                    alt = j.get("height")
                    filas.append({"id": str(j["id"]), "nombre": j.get("displayName") or j.get("fullName", "?"),
                                  "equipo": t.get("abbreviation", ""),
                                  "pos": (j.get("position") or {}).get("abbreviation", ""),
                                  "cm": round(alt * 2.54) if isinstance(alt, (int, float)) and alt > 0 else None})
        return filas
    return None


@st.cache_data(ttl=_TTL_LISTA, show_spinner="Cargando lista de jugadores...")
# ---------------------------------------------------------------------------
# Buscadores de jugadores: orden alfabético, rostros y resaltado al bajar con las flechas
# ---------------------------------------------------------------------------
def clave_abc(texto):
    """Clave para ordenar como en un abecedario: sin tildes ni mayúsculas (Dončić queda junto a Doncic)."""
    t = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in t if not unicodedata.combining(c)).casefold()


def ordenar_abc(por_id):
    """Ids de los jugadores ordenados A→Z por el nombre que se ve en el buscador."""
    return sorted(por_id, key=lambda i: (clave_abc(por_id[i]["nombre"]), str(i)))


# Script que se instala UNA vez en la página (no en el iframe, que se destruye en cada ejecución). Revisa las opciones de la
# lista desplegable de los buscadores: a cada jugador le pone su rostro (un <img> delante del nombre) y marca la opción activa
# (la que recorres con las flechas del teclado o la que tiene el ratón encima). Todos los estilos van EN LÍNEA con !important,
# así no dependen de la estructura interna de Streamlit ni los pisa el CSS de la app. Las listas largas reutilizan los mismos
# elementos al hacer scroll, por eso se revisa en cada cambio.
_JS_PAGINA = r"""
(function(){
  if (window.__nbaRostros5) return; window.__nbaRostros5 = true;
  var crudo = null, mapa = {}, FOTO = 'https://a.espncdn.com/i/headshots/nba/players/full/';

  /* ---- Estilo del campo selector (dentro de las tarjetas oscuras) y de la lista desplegable ---- */
  var css = [
    /* campo: un único borde fino y limpio; sin líneas internas ni el rojo de Streamlit */
    '[class*="_caja"] [data-baseweb="select"] > div{border:1px solid rgba(165,180,252,.30) !important;border-radius:12px !important;',
    ' box-shadow:none !important;outline:0 !important;transition:border-color .18s ease,box-shadow .18s ease !important;}',
    '[class*="_caja"] [data-baseweb="select"] > div:hover{border-color:rgba(165,180,252,.60) !important;}',
    '[class*="_caja"] [data-baseweb="select"] > div:focus-within,[class*="_caja"] [data-baseweb="select"][aria-expanded="true"] > div{',
    ' border-color:#a5b4fc !important;box-shadow:0 0 0 3px rgba(129,140,248,.22) !important;}',
    '[class*="_caja"] [data-baseweb="select"] > div *{border:0 !important;border-color:transparent !important;outline:0 !important;box-shadow:none !important;}',
    '[class*="_caja"] [data-baseweb="select"] > div::before,[class*="_caja"] [data-baseweb="select"] > div::after,',
    '[class*="_caja"] [data-baseweb="select"] > div *::before,[class*="_caja"] [data-baseweb="select"] > div *::after{display:none !important;content:none !important;}',
    /* lista: panel más limpio, filas más aireadas y separadores casi invisibles */
    'body [data-baseweb="popover"]{border:1px solid rgba(99,102,241,.28) !important;border-radius:14px !important;',
    ' box-shadow:0 18px 44px rgba(15,23,60,.34),0 2px 8px rgba(15,23,60,.12) !important;overflow:hidden !important;}',
    'body [data-baseweb="popover"] [role="option"]{border-bottom:1px solid rgba(99,102,241,.07) !important;padding-top:7px !important;',
    ' padding-bottom:7px !important;padding-left:14px !important;font-size:.92rem !important;letter-spacing:.005em;transition:background-color .12s ease;}',
    'body [data-baseweb="popover"] [role="option"]:last-child{border-bottom:0 !important;}',
    '[data-nba-pseudo]::before,[data-nba-pseudo]::after{display:none !important;content:none !important;}',
    /* zoom suave del logo al pasar el ratón (o al recorrer con las flechas) */
    'body [data-baseweb="popover"] [role="option"]:hover .nba-rostro,body [data-baseweb="popover"] [data-nba-act] .nba-rostro{',
    ' transform:scale(1.14) !important;box-shadow:0 0 0 1px rgba(99,102,241,.30),0 4px 10px rgba(30,41,90,.28) !important;}',
    '@media (prefers-reduced-motion:reduce){.nba-rostro{transition:none !important;}}'
  ].join('');
  var viejo = document.getElementById('nba-sel-css-4'); if (viejo) viejo.remove();
  var st = document.createElement('style'); st.id = 'nba-sel-css-5'; st.textContent = css; document.head.appendChild(st);

  function leer(){ if (crudo !== window.__nbaMapaJSON){ crudo = window.__nbaMapaJSON;
      try { mapa = JSON.parse(crudo) || {}; } catch(e){ mapa = {}; } } return mapa; }
  function fijar(el, css){ for (var k in css) el.style.setProperty(k, css[k], 'important'); }
  function quitar(el, props){ props.forEach(function(k){ el.style.removeProperty(k); }); }
  var P_ACT = ['background-color','font-weight','color'];

  /* Dos tipos de adorno delante del texto: rostro (jugador, círculo), equipo (escudo entero sobre placa blanca) («Todos los equipos» va sin adorno) */
  var BASE = {width:'34px', height:'34px', 'min-width':'34px', 'margin-right':'12px', flex:'none', 'pointer-events':'none', 'box-sizing':'border-box',
              transition:'transform .22s cubic-bezier(.34,1.56,.64,1), box-shadow .22s ease'};
  var ESTILO = {
    rostro: {'border-radius':'10px', 'object-fit':'cover', 'object-position':'center top',
             background:'radial-gradient(circle at 50% 30%,#8f98f7 0%,#5b61d8 58%,#3b3fa8 100%)',
             'box-shadow':'0 0 0 1px rgba(79,70,229,.45), 0 2px 6px rgba(30,41,90,.25)'},
    equipo: {'border-radius':'10px', 'object-fit':'contain', padding:'4px', background:'#ffffff',
             'box-shadow':'0 0 0 1px rgba(99,102,241,.18), 0 1px 3px rgba(30,41,90,.14)'}
  };
  function crear(tipo){
    var el = document.createElement('img');
    el.className = 'nba-rostro'; el.setAttribute('data-k', tipo); el.setAttribute('data-v', '5');
    el.alt = ''; el.onerror = function(){ this.style.visibility = 'hidden'; };
    fijar(el, BASE); fijar(el, ESTILO[tipo]);
    return el;
  }

  /* El rojo por defecto de Streamlit puede venir de cualquier regla (borde, divisoria junto a la flecha, sombra o contorno);
     en vez de adivinar cuál, se mira el color REAL de cada pieza del selector y, si es rojizo, se cambia en línea. */
  function rojo(c){ var q = /rgba?\(\s*(\d+)[ ,]+(\d+)[ ,]+(\d+)/.exec(c || ''); return !!q && +q[1] >= 190 && +q[2] <= 130 && +q[3] <= 130; }
  var LADOS = ['top','right','bottom','left'];
  function sanar(sel){
    var ctrl = sel.firstElementChild, nodos = [sel].concat([].slice.call(sel.querySelectorAll('*')));
    for (var up = sel.parentElement, n = 0; up && n < 3; up = up.parentElement, n++) nodos.push(up);
    nodos.forEach(function(el){
      var cs = getComputedStyle(el), malo = false, esCtrl = el === ctrl;
      for (var i = 0; i < 4; i++){ if (parseFloat(cs.getPropertyValue('border-' + LADOS[i] + '-width')) > 0 && rojo(cs.getPropertyValue('border-' + LADOS[i] + '-color'))) malo = true; }
      if (malo){
        if (esCtrl){ var f = el.matches(':focus-within') || sel.getAttribute('aria-expanded') === 'true';
          fijar(el, {'border-color': f ? '#a5b4fc' : 'rgba(165,180,252,.30)'}); }
        else if (el === sel || el.contains(sel)){ fijar(el, {'border-color':'transparent'}); }
        else { fijar(el, {'border-color':'transparent', 'border-width':'0'}); }
      }
      if (rojo(cs.outlineColor) && parseFloat(cs.outlineWidth) > 0) fijar(el, {outline:'0'});
      if (rojo(cs.boxShadow) && cs.boxShadow !== 'none') fijar(el, {'box-shadow': esCtrl ? '0 0 0 3px rgba(129,140,248,.22)' : 'none'});
      /* divisoria dibujada como una tira fina de fondo rojo */
      if (rojo(cs.backgroundColor) && (parseFloat(cs.width) <= 3 || parseFloat(cs.height) <= 3)) fijar(el, {'background-color':'transparent'});
      /* divisoria dibujada con ::before / ::after: no se puede pintar en línea, se marca el elemento y una regla la oculta */
      ['::before','::after'].forEach(function(ps){
        var q = getComputedStyle(el, ps);
        if (q.content !== 'none' && (rojo(q.backgroundColor) || rojo(q.borderLeftColor) || rojo(q.borderTopColor) || rojo(q.borderRightColor) || rojo(q.borderBottomColor)))
          el.setAttribute('data-nba-pseudo', '1');
      });
    });
  }

  function pintar(){
    document.querySelectorAll('[data-baseweb="select"]').forEach(sanar);
    var m = leer(), ae = document.activeElement, ad = ae && ae.getAttribute ? ae.getAttribute('aria-activedescendant') : null;
    document.querySelectorAll('[role="option"]').forEach(function(li){
      var t = (li.textContent || '').replace(/^[\s⭐️]+/, '').trim();
      var id = m[t], tipo = id ? (/^https:/.test(id) ? 'equipo' : 'rostro') : null, img = null;
      for (var c = li.firstChild; c; c = c.nextSibling){ if (c.className === 'nba-rostro'){ img = c; break; } }
      if (img && (!tipo || img.getAttribute('data-k') !== tipo || img.getAttribute('data-v') !== '5')){ img.remove(); img = null; }
      if (tipo){
        if (!img){ img = crear(tipo); li.insertBefore(img, li.firstChild); }
        var src = tipo === 'equipo' ? id : FOTO + id + '.png';
        if (img.getAttribute('src') !== src){ img.style.visibility = 'visible'; img.setAttribute('src', src); }
        fijar(li, {display:'flex', 'align-items':'center'});
      }
      var activo = li.getAttribute('aria-selected') === 'true' || li.hasAttribute('data-highlighted')
                   || (ad && li.id === ad) || li.matches(':hover');
      if (activo){
        if (!li.hasAttribute('data-nba-act')){
          li.setAttribute('data-nba-act', '1');
          fijar(li, {'background-color':'#dde3ff', 'font-weight':'600', color:'#1e1b4b'});
        }
      } else if (li.hasAttribute('data-nba-act')){ li.removeAttribute('data-nba-act'); quitar(li, P_ACT); }
    });
  }
  var pendiente = false;
  function programar(){ if (pendiente) return; pendiente = true;
    setTimeout(function(){ pendiente = false; pintar(); }, 16); }
  new MutationObserver(programar).observe(document.body, {childList:true, subtree:true, characterData:true,
      attributes:true, attributeFilter:['aria-selected','aria-activedescendant','data-highlighted']});
  ['keydown','keyup','mousemove','mouseover','input','focusin'].forEach(function(ev){
    document.addEventListener(ev, programar, true); });
  setInterval(pintar, 250);
  pintar();
})();
"""


def rostros_en_buscadores(por_id, extra=None):
    """Pone el rostro de cada jugador en la lista desplegable de los buscadores y resalta la opción marcada con las flechas.

    Streamlit no deja poner imágenes dentro de las opciones, así que se hace con un pequeño script que corre en la página.
    Basta llamarla una vez por ejecución, con el diccionario {id: {nombre, equipo}} de los jugadores.
    extra: {texto de la opción: URL https de la imagen} para listas que no son de jugadores (p. ej. escudos de equipos)."""
    import json as _json
    mapa = {f"{j['nombre']} ({j['equipo']})": str(i) for i, j in por_id.items() if str(i).isdigit()}
    mapa.update(extra or {})
    codigo = (
        "<script>(function(){try{var P=window.parent,D=P.document;"
        f"P.__nbaMapaJSON={_json.dumps(_json.dumps(mapa, ensure_ascii=False))};"
        "if(!D.getElementById('nba-rostros-js-5')){var s=D.createElement('script');s.id='nba-rostros-js-5';"
        f"s.textContent={_json.dumps(_JS_PAGINA)};D.head.appendChild(s);"
        "}}catch(e){}"
        # el iframe no debe ocupar espacio en la página
        "try{var f=window.frameElement;f.style.display='none';var c=f.closest('[data-testid=\"stElementContainer\"]');"
        "if(c)c.style.display='none';}catch(e){}})();</script>")
    components.html(codigo, height=0)


def _jugadores():
    """Todos los jugadores de las plantillas actuales: [{id, nombre, equipo}].

    Los 30 planteles se piden a la vez (antes, uno tras otro) y la lista se guarda en disco: al reiniciar la app o
    al volver a abrirla se lee de ahí al instante. Si ESPN falla, se usa la última lista guardada aunque sea vieja."""
    reciente = _leer_lista_disco(_TTL_LISTA)
    if reciente and "pos" in reciente[0]:      # una lista guardada antes de añadir posición y altura se vuelve a bajar una vez
        return reciente
    try:
        equipos = _get_json(BASE + "/teams")["sports"][0]["leagues"][0]["teams"]
        with ThreadPoolExecutor(max_workers=_HILOS_LISTA) as pool:
            planteles = list(pool.map(lambda t: _plantel(t["team"]), equipos))
    except Exception:  # noqa: BLE001
        planteles = []
    filas = sorted((f for p in planteles if p for f in p), key=lambda f: f["nombre"])
    if not filas:                             # sin datos: usa la copia vieja o falla (una lista vacía NO se debe guardar en caché)
        vieja = _leer_lista_disco()
        if vieja:
            return vieja
        raise RuntimeError("ESPN no entregó los planteles")
    if all(p is not None for p in planteles):  # solo se guarda si bajaron los 30 equipos
        _guardar_lista_disco(filas)
    return filas


def _partidos(pid, temporada):
    """Partidos de un jugador en una temporada (el año en que termina, p. ej. 2026 = 2025-26).

    Si ESPN falla devuelve [] SIN guardarlo en caché (antes un fallo puntual dejaba la lista vacía durante 1 hora)."""
    try:
        return _partidos_cache(pid, temporada)
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=300, show_spinner=False)   # 5 min: así los partidos nuevos aparecen rápido
def _partidos_cache(pid, temporada):
    data = _get_json(GAMELOG.format(pid=pid, season=temporada))
    etiquetas = data.get("labels", [])
    eventos = data.get("events", {})
    partidos = {}
    for tipo in data.get("seasonTypes", []):
        fase = tipo.get("displayName", "")
        if "preseason" in fase.lower():
            continue
        es_playoffs = "post" in fase.lower()
        for cat in tipo.get("categories", []):
            for ev in cat.get("events", []):
                eid = str(ev.get("eventId"))
                info = eventos.get(eid)
                if not info:
                    continue
                stats = dict(zip(etiquetas, ev.get("stats", [])))
                triples = str(stats.get("3PT", "")).split("-")[0]
                fila = {
                    "event": eid,
                    "fecha": str(info.get("gameDate", ""))[:10],
                    "rival_id": str(info.get("opponent", {}).get("id", "")),
                    "rival": info.get("opponent", {}).get("abbreviation", "?"),
                    "rival_nombre": info.get("opponent", {}).get("displayName", ""),
                    "sede": "Local" if info.get("atVs") == "vs" else "Visita",
                    "gano_equipo": info.get("gameResult") == "W",
                    "marcador": info.get("score", ""),
                    "fase": "Playoffs" if es_playoffs else "Temporada regular",
                    "3PM": _num(triples),
                    # Tiros como texto "hechos-intentados" (p. ej. "10-20") y faltas; los usa la sección de jugadores
                    "FG": stats.get("FG"), "3PT": stats.get("3PT"), "FT": stats.get("FT"),
                    "PF": _num(stats.get("PF")),
                }
                for _, col, _ in ESTADISTICAS:
                    if col != "3PM":
                        fila[col] = _num(stats.get(col))
                partidos[eid] = fila
    return list(partidos.values())


def _historial(pid, temporadas, incluir_playoffs):
    filas = []
    for t in temporadas:
        filas.extend(_partidos(pid, t))
    if not incluir_playoffs:
        filas = [f for f in filas if f["fase"] == "Temporada regular"]
    return filas


# ---------------------------------------------------------------------------
# Lógica del H2H
# ---------------------------------------------------------------------------
def calcular_partidos_juntos(partidos_a, partidos_b):
    """Partidos donde ambos jugaron: lista de (partido_a, partido_b, son_companeros).

    En el mismo partido, si tienen el MISMO rival son compañeros; si tienen rivales
    distintos, jugaron uno contra el otro.
    """
    por_evento_b = {p["event"]: p for p in partidos_b}
    juntos = []
    for pa in partidos_a:
        pb = por_evento_b.get(pa["event"])
        if pb:
            juntos.append((pa, pb, pa["rival_id"] == pb["rival_id"]))
    juntos.sort(key=lambda d: d[0]["fecha"], reverse=True)
    return juntos


def calcular_duelos(partidos_a, partidos_b):
    """Solo los partidos en los que jugaron en equipos contrarios."""
    return [(pa, pb) for pa, pb, comp in calcular_partidos_juntos(partidos_a, partidos_b) if not comp]


def _promedio(valores):
    valores = [v for v in valores if v is not None]
    return round(sum(valores) / len(valores), 1) if valores else None


def tabla_comparativa(duelos, nombre_a, nombre_b):
    filas = []
    for etiqueta, col, mas_es_mejor in ESTADISTICAS:
        pa = _promedio([a[col] for a, _ in duelos])
        pb = _promedio([b[col] for _, b in duelos])
        if pa is None or pb is None or pa == pb:
            mejor = "Empate" if pa == pb else "—"
        else:
            mejor = nombre_a if (pa > pb) == mas_es_mejor else nombre_b
        filas.append({"Estadística": etiqueta, nombre_a: pa, nombre_b: pb, "Mejor": mejor})
    return pd.DataFrame(filas)


def _quien_anota_mas(duelos):
    """Cuenta en cuántos duelos anotó más cada uno."""
    a = sum(1 for x, y in duelos if (x["PTS"] or 0) > (y["PTS"] or 0))
    b = sum(1 for x, y in duelos if (y["PTS"] or 0) > (x["PTS"] or 0))
    return a, b, len(duelos) - a - b


# ---------------------------------------------------------------------------
# Tarjetas "cara a cara" (HTML + CSS con animaciones)
# ---------------------------------------------------------------------------
CSS_H2H = """
<style>
@keyframes h2h-subir   { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
@keyframes h2h-aparece { from { opacity: 0; } to { opacity: 1; } }
@keyframes h2h-crece   { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes h2h-pop     { 0% { opacity: 0; transform: scale(.4); } 100% { opacity: 1; transform: scale(1); } }
@keyframes h2h-pulso   { 0% { box-shadow: 0 0 0 0 rgba(124, 58, 237, .55); } 70% { box-shadow: 0 0 0 12px rgba(124, 58, 237, 0); } 100% { box-shadow: 0 0 0 0 rgba(124, 58, 237, 0); } }

/* Cabecera con los dos jugadores */
.h2h-banner { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 12px; margin: .2rem 0 1rem;
  padding: .9rem 1.2rem; border-radius: 16px; border: 1px solid var(--borde, rgba(127,127,127,.22));
  background: linear-gradient(110deg, rgba(99,102,241,.22), rgba(127,127,127,.06) 50%, rgba(201,162,39,.22));
  animation: h2h-aparece .5s ease both; }
.h2h-b { font-family: 'Playfair Display', Georgia, serif; font-size: 1.25rem; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.h2h-b.a { color: #6366f1; text-align: left; }
.h2h-b.b { color: #c9a227; text-align: right; }
.h2h-vsb { font-weight: 800; letter-spacing: .15em; padding: .3rem .85rem; border-radius: 999px; color: #fff;
  background: linear-gradient(135deg, #4f46e5, #7c3aed); animation: h2h-pulso 2.2s infinite; }

/* Tarjetas */
.h2h-lista { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }
.h2h-card { --ca: #6366f1; --cb: #c9a227; position: relative; overflow: hidden; border-radius: 16px; padding: 1.05rem 1.1rem .9rem; display: flex; flex-direction: column;
  background: var(--card, rgba(127,127,127,.07)); border: 1px solid var(--borde, rgba(127,127,127,.22));
  animation: h2h-subir .55s ease both; transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease; }
.h2h-card::before { content: ""; position: absolute; inset: 0 0 auto 0; height: 4px; background: linear-gradient(90deg, var(--ca), var(--cb)); }
.h2h-card::after { content: ""; position: absolute; top: 0; left: -60%; width: 40%; height: 100%; pointer-events: none;
  background: linear-gradient(100deg, transparent, rgba(255,255,255,.20), transparent); transform: skewX(-20deg); transition: left .7s ease; }
.h2h-card:hover { transform: translateY(-5px); box-shadow: 0 14px 30px rgba(79,70,229,.25); border-color: var(--cb); }
.h2h-card:hover::after { left: 120%; }

.h2h-top { display: flex; gap: 8px; align-items: center; min-height: 1.7rem; margin: .25rem 0 .45rem; }
.h2h-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: .85rem; min-height: 1.35rem; }
.h2h-fecha { font-weight: 600; font-size: .82rem; opacity: .85; }
.h2h-chip { padding: .1rem .55rem; border-radius: 999px; font-size: .7rem; border: 1px solid var(--borde, rgba(127,127,127,.22)); background: var(--card, rgba(127,127,127,.07)); }
.h2h-chip.riv { background: rgba(239,68,68,.12); border-color: rgba(239,68,68,.35); }
.h2h-chip.com { background: rgba(34,197,94,.14); border-color: rgba(34,197,94,.40); }
.h2h-chip.po  { background: rgba(201,162,39,.16); border-color: rgba(201,162,39,.45); }
.h2h-marc { margin-left: auto; white-space: nowrap; font-weight: 700; font-size: .85rem; font-variant-numeric: tabular-nums; }

/* Puntos grandes */
.h2h-jug { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 8px; margin-bottom: .75rem; }
.h2h-lado { text-align: center; opacity: .72; min-width: 0; }
.h2h-lado.win { opacity: 1; }
.h2h-lado .nom { font-size: .8rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.h2h-lado .pts { font-size: 2.4rem; font-weight: 800; line-height: 1.05; font-variant-numeric: tabular-nums;
  animation: h2h-pop .6s cubic-bezier(.2, 1.4, .4, 1) both; animation-delay: var(--d, .2s); }
.h2h-lado .u { font-size: .62rem; letter-spacing: .14em; opacity: .7; }
.h2h-lado .eq { display: inline-block; margin: 3px 0 2px; padding: 0 .5rem; border-radius: 999px; border: 1px solid currentColor; font-size: .66rem; font-weight: 700; letter-spacing: .1em; }
.h2h-lado .eq.oculto { visibility: hidden; }
.h2h-chip.vs { font-weight: 600; letter-spacing: .02em; }
.h2h-lado.a .nom, .h2h-lado.a .eq, .h2h-lado.a .pts { color: var(--ca); }
.h2h-lado.b .nom, .h2h-lado.b .eq, .h2h-lado.b .pts { color: var(--cb); }
.h2h-lado.a.win .pts { text-shadow: 0 0 18px rgba(99,102,241,.45); }
.h2h-lado.b.win .pts { text-shadow: 0 0 18px rgba(201,162,39,.55); }
.h2h-lado.win .pts::after { content: "👑"; font-size: .4em; margin-left: .2em; vertical-align: super; }
.h2h-centro { text-align: center; }
.h2h-vs { font-weight: 800; font-size: .8rem; letter-spacing: .14em; opacity: .55; }
.h2h-dif { margin-top: 4px; font-size: .72rem; font-weight: 700; padding: .05rem .5rem; border-radius: 999px; color: #fff; display: inline-block; }
.h2h-dif.a { background: var(--ca); } .h2h-dif.b { background: var(--cb); } .h2h-dif.e { background: rgba(127,127,127,.55); }

/* Barras espejo */
.h2h-fila { display: grid; grid-template-columns: 34px 1fr 38px 1fr 34px; align-items: center; gap: 6px; margin: .3rem 0; font-size: .82rem; }
.h2h-fila .v { text-align: center; font-variant-numeric: tabular-nums; font-weight: 600; opacity: .6; }
.h2h-fila .v.win { opacity: 1; font-weight: 800; }
.h2h-fila .v.a.win { color: var(--ca); } .h2h-fila .v.b.win { color: var(--cb); }
.h2h-fila .lbl { text-align: center; font-size: .64rem; letter-spacing: .08em; font-weight: 700; opacity: .65; }
.h2h-fila .bar { height: 8px; border-radius: 99px; background: rgba(127,127,127,.16); display: flex; overflow: hidden; }
.h2h-fila .bar.izq { justify-content: flex-end; }
.h2h-fila .bar i { display: block; height: 100%; border-radius: 99px; animation: h2h-crece .8s cubic-bezier(.2, .8, .2, 1) both; animation-delay: var(--d, .2s); }
.h2h-fila .bar.izq i { background: linear-gradient(270deg, var(--ca), rgba(99,102,241,.45)); transform-origin: right; }
.h2h-fila .bar.der i { background: linear-gradient(90deg, var(--cb), rgba(201,162,39,.45)); transform-origin: left; }
.h2h-fila .bar i.lose { opacity: .4; }

/* Tarjetas de partido compactas (solo dentro de .h2h-lista; el resumen final no cambia) */
.h2h-lista { grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 10px; }
.h2h-lista .h2h-card { padding: .6rem .8rem .55rem; border-radius: 12px; }
.h2h-lista .h2h-card::before { height: 3px; }
.h2h-lista .h2h-card::after { display: none; }
.h2h-lista .h2h-card:hover { transform: none; box-shadow: 0 6px 16px rgba(79,70,229,.18); }
.h2h-lista .h2h-fila { margin: .12rem 0; font-size: .76rem; gap: 5px; grid-template-columns: 28px 1fr 34px 1fr 28px; }
.h2h-lista .h2h-fila .bar { height: 6px; }
.h2h-cab { display: flex; align-items: center; gap: 6px; margin: .15rem 0 .45rem; font-size: .74rem; min-width: 0; }
.h2h-cab .f { font-weight: 600; opacity: .8; white-space: nowrap; }
.h2h-cab .h2h-chip { font-size: .66rem; padding: 0 .45rem; white-space: nowrap; }
.h2h-cab .m { margin-left: auto; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
.h2h-duelo { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 6px; margin-bottom: .35rem; }
.h2h-duelo .p { display: flex; align-items: baseline; gap: 6px; min-width: 0; opacity: .65; }
.h2h-duelo .p.b { justify-content: flex-end; }
.h2h-duelo .p.win { opacity: 1; }
.h2h-duelo .n { font-size: .74rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.h2h-duelo .x { font-size: 1.55rem; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.h2h-duelo .p.a .n, .h2h-duelo .p.a .x { color: var(--ca); }
.h2h-duelo .p.b .n, .h2h-duelo .p.b .x { color: var(--cb); }
.h2h-duelo .h2h-dif { margin: 0; }
.h2h-res1 { margin-top: .3rem; text-align: center; font-size: .72rem; font-weight: 700; }

/* Pie con el resultado */

.h2h-pie { margin-top: auto; padding-top: .6rem; border-top: 1px dashed var(--borde, rgba(127,127,127,.3)); text-align: center; font-size: .82rem; font-weight: 700; }
.h2h-res.a { color: var(--ca); } .h2h-res.b { color: var(--cb); } .h2h-res.ok { color: #22c55e; } .h2h-res.mal { color: #ef4444; }

/* Tarjeta final: resumen por ventanas de partidos */
.h2h-resumen { margin-top: 18px; border-color: rgba(201,162,39,.55);
  background: linear-gradient(135deg, rgba(99,102,241,.12), rgba(127,127,127,.05) 50%, rgba(201,162,39,.14)); }
.h2h-cuerpo { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; align-items: start; }
.h2h-resumen .h2h-fila { grid-template-columns: 46px 1fr 40px 1fr 46px; }
.h2h-subt { font-size: .7rem; letter-spacing: .1em; font-weight: 700; opacity: .7; margin: .2rem 0 .6rem; text-transform: uppercase; }
.h2h-nota { margin-top: .7rem; font-size: .72rem; opacity: .65; line-height: 1.4; }
.h2h-mat { display: grid; grid-template-columns: 38px repeat(5, 1fr); gap: 6px; align-items: center; }
.h2h-mat .mh { text-align: center; font-size: .72rem; font-weight: 800; opacity: .6; }
.h2h-mat .mh.sel { opacity: 1; color: #7c3aed; }
.h2h-mat .ml { font-size: .64rem; letter-spacing: .08em; font-weight: 700; opacity: .65; }
.h2h-mat .c { text-align: center; font-size: .72rem; font-weight: 700; padding: .2rem 0; border-radius: 8px; color: #fff;
  font-variant-numeric: tabular-nums; animation: h2h-pop .5s cubic-bezier(.2, 1.4, .4, 1) both; transition: transform .15s ease; }
.h2h-mat .c:hover { transform: scale(1.12); }
.h2h-mat .c.a { background: var(--ca); } .h2h-mat .c.b { background: var(--cb); } .h2h-mat .c.e { background: rgba(127,127,127,.55); }
.h2h-mat .c.n { background: rgba(127,127,127,.15); color: inherit; opacity: .6; }
.h2h-mat .c.sel { box-shadow: 0 0 0 2px #7c3aed; }
@media (max-width: 760px) { .h2h-cuerpo { grid-template-columns: 1fr; gap: 14px; } }
@media (max-width: 480px) { .h2h-lista { grid-template-columns: 1fr; } .h2h-b { font-size: 1rem; } }
@media (prefers-reduced-motion: reduce) { .h2h-card, .h2h-card *, .h2h-banner, .h2h-vsb { animation: none !important; transition: none !important; } }
</style>
"""

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

# (columna de ESPN, etiqueta corta, ¿más alto es mejor?)
FILAS_TARJETA = [("REB", "REB", True), ("AST", "AST", True), ("3PM", "3P", True)]   # las demás están en la tabla y el resumen


def _fecha_bonita(texto):
    try:
        anio, mes, dia = texto.split("-")
        return f"{int(dia)} {MESES[int(mes) - 1]} {anio}"
    except (ValueError, IndexError):
        return texto or "—"


def _fmt(v):
    if v is None:
        return "–"
    v = round(float(v), 1)
    return str(int(v)) if v.is_integer() else f"{v:.1f}"


def _ganador(va, vb, mas_es_mejor=True):
    """'a', 'b' o None (empate o dato faltante)."""
    if va is None or vb is None or va == vb:
        return None
    return "a" if (va > vb) == mas_es_mejor else "b"


def _fila_html(etiqueta, va, vb, mas_es_mejor, retraso):
    g = _ganador(va, vb, mas_es_mejor)
    mx = max(va or 0, vb or 0)
    wa = round(100 * (va or 0) / mx) if mx else 0
    wb = round(100 * (vb or 0) / mx) if mx else 0
    return (f'<div class="h2h-fila">'
            f'<b class="v a{" win" if g == "a" else ""}">{_fmt(va)}</b>'
            f'<div class="bar izq"><i class="{"lose" if g == "b" else ""}" style="width:{wa}%;--d:{retraso:.2f}s"></i></div>'
            f'<span class="lbl">{etiqueta}</span>'
            f'<div class="bar der"><i class="{"lose" if g == "a" else ""}" style="width:{wb}%;--d:{retraso:.2f}s"></i></div>'
            f'<b class="v b{" win" if g == "b" else ""}">{_fmt(vb)}</b></div>')


def _corto(nombre):
    """Apellido para que quepa en la tarjeta compacta (el nombre completo va en el tooltip)."""
    partes = nombre.split()
    return partes[-1] if len(partes) > 1 else nombre


def _tarjeta_html(a, b, companeros, nombre_a, nombre_b, indice):
    """Tarjeta compacta de un partido (todo en una línea para que Markdown no lo rompa)."""
    esc = html.escape
    base = min(indice, 10) * 0.04          # las tarjetas aparecen una tras otra
    g = _ganador(a["PTS"], b["PTS"])
    dif = abs((a["PTS"] or 0) - (b["PTS"] or 0))
    chip_dif = (f'<span class="h2h-dif {g}">+{_fmt(dif)}</span>' if g else '<span class="h2h-dif e">=</span>')

    if companeros:
        cruce = ("🏠 vs " if a["sede"] == "Local" else "✈️ @ ") + esc(a["rival"])
        res = ('<span class="h2h-res ok">✅ Victoria juntos</span>' if a["gano_equipo"]
               else '<span class="h2h-res mal">❌ Derrota juntos</span>')
    else:
        eq_a, eq_b = b["rival"], a["rival"]      # el equipo de A es el rival de B, y al revés
        local, visita = (eq_a, eq_b) if a["sede"] == "Local" else (eq_b, eq_a)
        cruce = f"{esc(visita)} @ {esc(local)}"
        quien, clase = (nombre_a, "a") if a["gano_equipo"] else (nombre_b, "b")
        res = f'<span class="h2h-res {clase}">🏆 Ganó {esc(_corto(quien))}</span>'
    chip_comp = '<span class="h2h-chip com">🤝</span>' if companeros else ""
    chip_fase = '<span class="h2h-chip po">PO</span>' if a["fase"] == "Playoffs" else ""

    filas = "".join(_fila_html(etq, a[col], b[col], mejor, base + 0.15 + 0.05 * i)
                    for i, (col, etq, mejor) in enumerate(FILAS_TARJETA))
    return (f'<div class="h2h-card" style="animation-delay:{base:.2f}s">'
            f'<div class="h2h-cab"><span class="f">📅 {_fecha_bonita(a["fecha"])}</span>{chip_comp}{chip_fase}'
            f'<span class="h2h-chip vs">{cruce}</span><span class="m">{esc(str(a["marcador"]))}</span></div>'
            f'<div class="h2h-duelo">'
            f'<div class="p a{" win" if g == "a" else ""}" title="{esc(nombre_a)}"><span class="n">{esc(_corto(nombre_a))}</span>'
            f'<span class="x">{_fmt(a["PTS"])}</span></div>{chip_dif}'
            f'<div class="p b{" win" if g == "b" else ""}" title="{esc(nombre_b)}"><span class="x">{_fmt(b["PTS"])}</span>'
            f'<span class="n">{esc(_corto(nombre_b))}</span></div></div>'
            f'{filas}<div class="h2h-res1">{res}</div></div>')


def _banner_html(nombre_a, nombre_b):
    esc = html.escape
    return (f'<div class="h2h-banner"><div class="h2h-b a">{esc(nombre_a)}</div>'
            f'<div class="h2h-vsb">VS</div><div class="h2h-b b">{esc(nombre_b)}</div></div>')


VENTANAS = (5, 10, 15, 20, 25)
ETIQ_RESUMEN = {"PTS": "PTS", "REB": "REB", "AST": "AST", "STL": "ROB", "BLK": "TAP", "3PM": "3P", "TO": "PER", "MIN": "MIN"}


def _celda_ventana(duelos, n, col, mas_es_mejor, nombre_a, nombre_b, seleccionada):
    """Una celda de la matriz: quién lidera esa estadística en los últimos n partidos y por cuánto."""
    sel = " sel" if seleccionada else ""
    if len(duelos) < n:
        return f'<span class="c n{sel}" title="Solo hay {len(duelos)} partidos">–</span>'
    sub = duelos[:n]
    pa = _promedio([a[col] for a, _ in sub])
    pb = _promedio([b[col] for _, b in sub])
    if pa is None or pb is None:
        return f'<span class="c n{sel}">–</span>'
    titulo = html.escape(f"{nombre_a} {_fmt(pa)} · {nombre_b} {_fmt(pb)}")
    g = _ganador(pa, pb, mas_es_mejor)
    if g is None:
        return f'<span class="c e{sel}" title="{titulo}">=</span>'
    return f'<span class="c {g}{sel}" title="{titulo}">+{_fmt(abs(pa - pb))}</span>'


def _resumen_html(duelos, n, nombre_a, nombre_b):
    """Tarjeta final: promedios de los últimos n partidos y quién lidera cada estadística."""
    esc = html.escape
    sub = duelos[:n]
    ganadas_a = ganadas_b = 0
    filas = []
    for i, (_, col, mejor) in enumerate(ESTADISTICAS):
        pa = _promedio([a[col] for a, _ in sub])
        pb = _promedio([b[col] for _, b in sub])
        g = _ganador(pa, pb, mejor)
        ganadas_a += g == "a"
        ganadas_b += g == "b"
        filas.append(_fila_html(ETIQ_RESUMEN[col], pa, pb, mejor, 0.15 + 0.07 * i))

    lider = "a" if ganadas_a > ganadas_b else "b" if ganadas_b > ganadas_a else None
    if lider:
        nombre_lider = nombre_a if lider == "a" else nombre_b
        pie = (f'<span class="h2h-res {lider}">👑 {esc(nombre_lider)} domina: '
               f'{max(ganadas_a, ganadas_b)} de {len(ESTADISTICAS)} categorías</span>')
    else:
        pie = '<span class="h2h-res">⚖️ Cara a cara parejo</span>'

    cabecera = '<span></span>' + "".join(
        f'<span class="mh{" sel" if v == n else ""}">{v}</span>' for v in VENTANAS)
    matriz = "".join(
        f'<span class="ml">{ETIQ_RESUMEN[col]}</span>'
        + "".join(_celda_ventana(duelos, v, col, mejor, nombre_a, nombre_b, v == n) for v in VENTANAS)
        for _, col, mejor in ESTADISTICAS)

    etiqueta = f"Todos los partidos ({len(sub)})" if n >= len(duelos) else f"Últimos {len(sub)} partidos"
    return (f'<div class="h2h-card h2h-resumen">'
            f'<div class="h2h-top"><span class="h2h-fecha">📊 Resumen final</span><span class="h2h-marc">{etiqueta}</span></div>'
            f'<div class="h2h-cuerpo"><div>'
            f'<div class="h2h-jug">'
            f'<div class="h2h-lado a{" win" if lider == "a" else ""}"><div class="nom">{esc(nombre_a)}</div>'
            f'<div class="pts">{ganadas_a}</div><div class="u">CATEGORÍAS</div></div>'
            f'<div class="h2h-centro"><div class="h2h-vs">VS</div></div>'
            f'<div class="h2h-lado b{" win" if lider == "b" else ""}"><div class="nom">{esc(nombre_b)}</div>'
            f'<div class="pts">{ganadas_b}</div><div class="u">CATEGORÍAS</div></div></div>'
            f'{"".join(filas)}</div>'
            f'<div><div class="h2h-subt">Líder por ventana · últimos partidos</div>'
            f'<div class="h2h-mat">{cabecera}{matriz}</div>'
            f'<div class="h2h-nota">Cada casilla muestra quién lidera y por cuánto en promedio. '
            f'Pasa el mouse para ver ambos promedios. «–» = no hay suficientes partidos.</div></div></div>'
            f'<div style="height:.75rem"></div><div class="h2h-pie">{pie}</div></div>')


def _tabla_clasica(duelos, son_companeros, nombre_a, nombre_b):
    filas = []
    for (a, b), comp in zip(duelos, son_companeros):
        if comp:
            resultado = "Victoria juntos" if a["gano_equipo"] else "Derrota juntos"
        else:
            resultado = f"Ganó {nombre_a if a['gano_equipo'] else nombre_b}"
        equipos = f"Juntos vs {a['rival']}" if comp else f"{b['rival']} vs {a['rival']}"
        filas.append({
            "Fecha": a["fecha"], "Tipo": "Compañeros" if comp else "Enfrentados", "Equipos": equipos, "Fase": a["fase"],
            "Marcador": a["marcador"], "Resultado": resultado,
            f"{nombre_a} PTS": a["PTS"], f"{nombre_a} REB": a["REB"], f"{nombre_a} AST": a["AST"],
            f"{nombre_b} PTS": b["PTS"], f"{nombre_b} REB": b["REB"], f"{nombre_b} AST": b["AST"],
        })
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)


def _detalle_partidos(duelos, son_companeros, nombre_a, nombre_b):
    """Detalle partido a partido: tarjetas cara a cara o tabla clásica."""
    vista = st.radio("Vista", ["🃏 Tarjetas", "📋 Tabla"], horizontal=True, label_visibility="collapsed",
                     key="h2h_vista")
    if vista.startswith("📋"):
        _tabla_clasica(duelos, son_companeros, nombre_a, nombre_b)
        return

    limite = 6
    ver_todos = True
    if len(duelos) > limite:
        ver_todos = st.toggle(f"Mostrar los {len(duelos)} partidos", False, key="h2h_ver_todos",
                              help=f"Por defecto se muestran los {limite} más recientes.")
    mostrar = list(zip(duelos, son_companeros))[: None if ver_todos else limite]

    st.markdown(CSS_H2H, unsafe_allow_html=True)   # aparte del HTML: la app oculta los bloques que traen <style>
    tarjetas = "".join(_tarjeta_html(a, b, comp, nombre_a, nombre_b, i) for i, ((a, b), comp) in enumerate(mostrar))
    st.markdown(_banner_html(nombre_a, nombre_b) + f'<div class="h2h-lista">{tarjetas}</div>', unsafe_allow_html=True)

    # Tarjeta final: resumen de los últimos 5, 10, 15, 20 o 25 partidos (usa todos los duelos, no solo los visibles)
    total = len(duelos)
    opciones = [v for v in VENTANAS if v <= total]
    if total not in opciones:
        opciones.append(total)
    st.markdown("##### 📊 Resumen final: ¿quién domina?")
    n = st.radio("Ventana de partidos", opciones, index=len(opciones) - 1, horizontal=True,
                 format_func=lambda v: f"Todos ({v})" if v == total and v not in VENTANAS else f"Últimos {v}",
                 label_visibility="collapsed", key="h2h_ventana")
    st.markdown(_resumen_html(duelos, n, nombre_a, nombre_b), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Pantalla
# ---------------------------------------------------------------------------
def _etiqueta_temporada(t):
    return f"{t - 1}-{str(t)[2:]}"


def render():
    st.subheader("⚔️ H2H entre jugadores")
    st.caption("Compara cómo rinde cada jugador en los partidos que jugaron juntos: enfrentados o como compañeros.")

    try:
        jugadores = _jugadores()
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo cargar la lista de jugadores ({type(e).__name__}). "
                 "Revisa la sección Diagnóstico.")
        return
    if not jugadores:
        st.warning("No se encontraron jugadores.")
        return

    por_id = {j["id"]: j for j in jugadores}
    ids = ordenar_abc(por_id)
    rostros_en_buscadores(por_id)
    formato = lambda i: f"{por_id[i]['nombre']} ({por_id[i]['equipo']})"  # noqa: E731

    c1, c2 = st.columns(2)
    id_a = c1.selectbox("Jugador A", ids, index=None, format_func=formato,
                        placeholder="Escribe para buscar...", key="h2h_jug_a")
    id_b = c2.selectbox("Jugador B", ids, index=None, format_func=formato,
                        placeholder="Escribe para buscar...", key="h2h_jug_b")

    hoy = date.today()
    actual = hoy.year + (1 if hoy.month >= 10 else 0)
    opciones = list(range(actual, actual - 6, -1))
    c3, c4 = st.columns([3, 1])
    temporadas = c3.multiselect("Temporadas", opciones, default=opciones[:3], format_func=_etiqueta_temporada,
                                help="Más temporadas = más duelos, pero tarda un poco más en cargar.")
    playoffs = c4.toggle("Incluir playoffs", True)

    modo = st.radio("Partidos a analizar", ["⚔️ Enfrentados", "🤝 Compañeros", "Todos"], horizontal=True,
                    help="Enfrentados: equipos contrarios. Compañeros: mismo equipo. Todos: ambos casos.")

    if not id_a or not id_b:
        st.info("Elige dos jugadores para ver su cara a cara.")
        return
    if id_a == id_b:
        st.warning("Elige dos jugadores distintos.")
        return
    if not temporadas:
        st.warning("Elige al menos una temporada.")
        return

    nombre_a, nombre_b = por_id[id_a]["nombre"], por_id[id_b]["nombre"]
    with st.spinner("Buscando partidos en común..."):
        hist_a = _historial(id_a, temporadas, playoffs)
        hist_b = _historial(id_b, temporadas, playoffs)
    juntos = calcular_partidos_juntos(hist_a, hist_b)
    if modo.startswith("⚔️"):
        juntos = [j for j in juntos if not j[2]]
    elif modo.startswith("🤝"):
        juntos = [j for j in juntos if j[2]]

    if not juntos:
        st.info(f"No hay partidos ({modo.split(' ', 1)[-1].lower()}) entre {nombre_a} y {nombre_b} "
                "en las temporadas elegidas. Prueba otro tipo de partido o agrega más temporadas.")
        return

    duelos = [(a, b) for a, b, _ in juntos]
    son_companeros = [c for _, _, c in juntos]
    n_comp = sum(son_companeros)
    solo_companeros = n_comp == len(juntos)
    solo_rivales = n_comp == 0

    # ---- Resumen principal: ¿quién anota más? ----
    gana_a, gana_b, empates = _quien_anota_mas(duelos)
    prom_a = _promedio([a["PTS"] for a, _ in duelos])
    prom_b = _promedio([b["PTS"] for _, b in duelos])

    if solo_companeros:
        titulo = f"🤝 {len(duelos)} partidos como compañeros"
    elif solo_rivales:
        titulo = f"⚔️ {len(duelos)} duelos analizados"
    else:
        titulo = f"📊 {len(duelos)} partidos ({len(duelos) - n_comp} enfrentados, {n_comp} como compañeros)"
    st.markdown(f"### {titulo}")

    m1, m2, m3 = st.columns(3)
    m1.metric(f"Pts por partido · {nombre_a}", prom_a)
    m2.metric(f"Pts por partido · {nombre_b}", prom_b)
    if gana_a != gana_b:
        lider = nombre_a if gana_a > gana_b else nombre_b
        m3.metric("Anota más veces", lider, f"{max(gana_a, gana_b)} de {len(duelos)} partidos")
    else:
        m3.metric("Anota más veces", "Parejo", f"{gana_a}-{gana_b}")
    st.caption(f"Partidos con más puntos: {nombre_a} {gana_a} · {nombre_b} {gana_b} · empates {empates}.")

    if solo_companeros:
        victorias = sum(1 for a, _ in duelos if a["gano_equipo"])
        c1, c2 = st.columns(2)
        c1.metric("Récord juntos", f"{victorias}-{len(duelos) - victorias}",
                  f"{round(100 * victorias / len(duelos))}% de victorias", delta_color="off")
        c2.metric("Puntos combinados por partido", _promedio([(a["PTS"] or 0) + (b["PTS"] or 0) for a, b in duelos]))
    elif solo_rivales:
        victorias_a = sum(1 for a, _ in duelos if a["gano_equipo"])
        st.caption(f"El equipo de {nombre_a} ganó {victorias_a} y el de {nombre_b} ganó {len(duelos) - victorias_a}.")

    # ---- Promedios completos ----
    st.markdown("#### Promedios en estos partidos")
    st.dataframe(tabla_comparativa(duelos, nombre_a, nombre_b), hide_index=True, use_container_width=True)
    medias = {n: {e: _promedio([(a if i == 0 else b)[c] for a, b in duelos]) for e, c, _ in ESTADISTICAS}
              for i, n in enumerate((nombre_a, nombre_b))}
    graficos.mostrar_comparacion(medias, titulo="Promedios en estos partidos", clave="h2h_cmp")

    # ---- Gráfico de puntos por partido ----
    cronologico = list(reversed(duelos))
    grafico = pd.DataFrame({
        nombre_a: [a["PTS"] for a, _ in cronologico],
        nombre_b: [b["PTS"] for _, b in cronologico],
    }, index=[a["fecha"] for a, _ in cronologico])
    st.markdown("#### Puntos en cada partido")
    st.bar_chart(grafico)

    # ---- Cada jugador contra una línea, con medias móviles ----
    with st.expander("📏 Barras por partido contra una línea (con medias móviles)"):
        etiqueta_stat = st.selectbox("Estadística", [e for e, _, _ in ESTADISTICAS], key="h2h_graf_stat")
        col_stat = next(c for e, c, _ in ESTADISTICAS if e == etiqueta_stat)
        ta, tb = st.tabs([f"👤 {nombre_a}", f"👤 {nombre_b}"])
        with ta:
            graficos.mostrar_jugador_vs_linea([a for a, _ in duelos], col_stat, etiqueta_stat,
                                              f"h2h_a_{col_stat}", nombre=nombre_a)
        with tb:
            graficos.mostrar_jugador_vs_linea([b for _, b in duelos], col_stat, etiqueta_stat,
                                              f"h2h_b_{col_stat}", nombre=nombre_b)

    # ---- Detalle partido a partido ----
    with st.expander("Ver partido a partido", expanded=True):
        _detalle_partidos(duelos, son_companeros, nombre_a, nombre_b)
