"""Estadísticas por jugador de la NBA: resumen, comparación y partidos de lo más reciente a lo más antiguo.

Reutiliza la descarga de datos de nba_h2h_jugadores (lista de jugadores y registro de partidos de ESPN).

Cómo usarlo desde otro archivo:
    import nba_jugadores
    nba_jugadores.render()
"""
import html
import json
import os
import re
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

import ficha_linea
import graficos
import nba_h2h_jugadores as h
import planes

COLORES = ["#6366f1", "#c9a227", "#14b8a6", "#ec4899"]   # un color por jugador (máximo 4)
VENTANA_PRINCIPAL = 10   # partidos que promedia la pantalla principal
VENTANAS = [5, 10, 15, 20, 25, 0]                         # 0 = todos los partidos

# (columna, etiqueta corta, ¿más alto es mejor?)
GRANDES = [("PTS", "PTS", True), ("REB", "REB", True), ("AST", "AST", True)]
PEQUENAS = [("STL", "ROB", True), ("BLK", "TAP", True), ("3PM", "3P", True), ("TO", "PER", False),
            ("MIN", "MIN", True), ("FG%", "FG%", True), ("3P%", "3P%", True), ("FT%", "FT%", True)]
NOMBRES = {"PTS": "Puntos", "REB": "Rebotes", "AST": "Asistencias", "STL": "Robos", "BLK": "Tapones",
           "3PM": "Triples", "TO": "Pérdidas", "MIN": "Minutos", "FG%": "% tiros de campo",
           "3P%": "% triples", "FT%": "% tiros libres", "REB+AST": "Rebotes + asistencias",
           "PTS+REB": "Puntos + rebotes",
           "PTS+AST": "Puntos + asistencias",
           "P+R+A": "Puntos + rebotes + asistencias"}

CSS = """
<style>
@keyframes jg-subir  { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
@keyframes jg-sube   { from { transform: scaleY(0); } to { transform: scaleY(1); } }
@keyframes jg-pop    { 0% { opacity: 0; transform: scale(.5); } 100% { opacity: 1; transform: scale(1); } }

.jg-lista { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin: .4rem 0 1rem; }
.jg-card { position: relative; overflow: hidden; border-radius: 18px; padding: 1.1rem 1.15rem 1rem;
  background: var(--card, rgba(127,127,127,.07)); border: 1px solid var(--borde, rgba(127,127,127,.22));
  animation: jg-subir .55s ease both; transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease; }
.jg-card::before { content: ""; position: absolute; inset: 0 0 auto 0; height: 5px; background: var(--c); }
.jg-card::after { content: ""; position: absolute; top: 0; left: -60%; width: 40%; height: 100%; pointer-events: none;
  background: linear-gradient(100deg, transparent, rgba(255,255,255,.18), transparent); transform: skewX(-20deg); transition: left .7s ease; }
.jg-card:hover { transform: translateY(-5px); box-shadow: 0 14px 30px rgba(79,70,229,.22); border-color: var(--c); }
.jg-card:hover::after { left: 120%; }

.jg-head { display: flex; align-items: center; gap: 8px; margin-top: .2rem; }
.jg-nom { font-family: 'Playfair Display', Georgia, serif; font-size: 1.25rem; font-weight: 700; color: var(--c);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jg-eq { padding: 0 .5rem; border-radius: 999px; border: 1px solid var(--c); color: var(--c); font-size: .68rem; font-weight: 700; letter-spacing: .1em; }
.jg-head { flex-wrap: wrap; row-gap: 4px; }
.jg-min { display: inline-flex; align-items: center; gap: 4px; padding: 0 .55rem; border-radius: 999px; font-size: .72rem; font-weight: 700;
  font-variant-numeric: tabular-nums; white-space: nowrap; background: rgba(127,127,127,.14); }
.jg-min small { font-weight: 600; opacity: .7; }
.jg-sub { font-size: .74rem; opacity: .7; margin: .15rem 0 .8rem; }

.jg-grandes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: .6rem; }
.jg-g { text-align: center; padding: .5rem .2rem; border-radius: 12px; background: rgba(127,127,127,.09); border: 1px solid transparent; position: relative; }
.jg-g b { display: block; font-size: 1.9rem; line-height: 1.05; font-weight: 800; color: var(--c); font-variant-numeric: tabular-nums;
  animation: jg-pop .6s cubic-bezier(.2, 1.4, .4, 1) both; }
.jg-g span, .jg-p span { font-size: .62rem; letter-spacing: .12em; font-weight: 700; opacity: .7; }
.jg-pequenas { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
.jg-p { text-align: center; padding: .3rem .1rem; border-radius: 10px; background: rgba(127,127,127,.06); border: 1px solid transparent; }
.jg-p b { display: block; font-size: .98rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.jg-g.lider, .jg-p.lider { border-color: #c9a227; background: rgba(201,162,39,.16); }
.jg-g.lider::after { content: "👑"; position: absolute; top: -7px; right: 4px; font-size: .8rem; }
.jg-p.lider b { color: #c9a227; }

.jg-spark-t { margin: .8rem 0 .25rem; font-size: .66rem; letter-spacing: .1em; font-weight: 700; opacity: .65; text-transform: uppercase; }
.jg-spark { display: flex; align-items: flex-end; gap: 3px; height: 52px; }
.jg-spark i { flex: 1; min-width: 4px; border-radius: 4px 4px 0 0; background: linear-gradient(180deg, var(--c), rgba(127,127,127,.25));
  transform-origin: bottom; animation: jg-sube .7s cubic-bezier(.2, .8, .2, 1) both; transition: filter .15s ease; }
.jg-spark i:hover { filter: brightness(1.3); }
.jg-spark-e { display: flex; justify-content: space-between; font-size: .62rem; opacity: .55; margin-top: 2px; }

@media (prefers-reduced-motion: reduce) { .jg-card, .jg-card *, .jg-g b { animation: none !important; transition: none !important; } }
</style>
"""


# ---------------------------------------------------------------------------
# Cálculos
# ---------------------------------------------------------------------------
def _hechos(texto):
    """'10-20' -> (10, 20). Si no se puede leer, (0, 0)."""
    try:
        hechos, intentos = str(texto).split("-")
        return int(hechos), int(intentos)
    except (ValueError, TypeError):
        return 0, 0


def _porcentaje(juegos, clave):
    """Porcentaje de tiro sumando todos los tiros (más justo que promediar porcentajes)."""
    hechos = intentos = 0
    for g in juegos:
        a, b = _hechos(g.get(clave))
        hechos += a
        intentos += b
    return round(100 * hechos / intentos, 1) if intentos else None


def promedios(juegos):
    """Promedios por partido de una lista de partidos."""
    p = {col: h._promedio([g[col] for g in juegos]) for _, col, _ in h.ESTADISTICAS}
    p["FG%"] = _porcentaje(juegos, "FG")
    p["3P%"] = _porcentaje(juegos, "3PT")
    p["FT%"] = _porcentaje(juegos, "FT")
    return p


def lideres(lista_promedios):
    """Para cada estadística, índice del jugador que lidera (None si hay empate o un solo jugador)."""
    res = {}
    if len(lista_promedios) < 2:
        return res
    for col, _, mas_es_mejor in GRANDES + PEQUENAS:
        valores = [p.get(col) for p in lista_promedios]
        validos = [v for v in valores if v is not None]
        if len(validos) < 2:
            continue
        mejor = max(validos) if mas_es_mejor else min(validos)
        if validos.count(mejor) == 1:
            res[col] = valores.index(mejor)
    return res


def _claves():
    """Estadísticas que se pueden elegir: las de la fuente de datos más la combinada Rebotes + asistencias."""
    return [c for _, c, _ in h.ESTADISTICAS] + ["REB+AST", "PTS+REB", "PTS+AST", "P+R+A"]


def _con_combinadas(juegos):
    """Copia de los partidos con la estadística combinada REB+AST (rebotes + asistencias del mismo partido)."""
    res = []
    for g in juegos:
        pts, reb, ast = g.get("PTS"), g.get("REB"), g.get("AST")
        total = None if reb is None and ast is None else (reb or 0) + (ast or 0)
        pra = None if pts is None and reb is None and ast is None else (pts or 0) + (reb or 0) + (ast or 0)
        pr = None if pts is None and reb is None else (pts or 0) + (reb or 0)
        pa = None if pts is None and ast is None else (pts or 0) + (ast or 0)
        res.append({**g, "REB+AST": total, "PTS+REB": pr, "PTS+AST": pa, "P+R+A": pra})
    return res


def _historial_ordenado(pid, temporadas, playoffs):
    """Partidos del más reciente al más antiguo (con la estadística combinada REB+AST incluida)."""
    ordenados = sorted(h._historial(pid, temporadas, playoffs), key=lambda g: g["fecha"], reverse=True)
    return _con_combinadas(ordenados)


def _solo_contra(historiales, rival):
    """Deja en cada historial solo los partidos jugados contra el equipo `rival` (sigla, p. ej. "TOR"). Sin rival, no cambia nada."""
    if not rival:
        return historiales
    return [[g for g in hist if str(g.get("rival", "")).upper() == rival.upper()] for hist in historiales]


def _solo_mismo_partido(historiales):
    """Deja en cada historial solo los partidos en que TODOS los jugadores elegidos jugaron el mismo partido (compañeros o rivales).

    Sirve para comparar quién rinde más dentro del mismo partido. Mantiene el orden del más reciente al más antiguo."""
    if len(historiales) < 2:
        return historiales
    comunes = set.intersection(*[{g["event"] for g in hist} for hist in historiales])
    return [[g for g in hist if g["event"] in comunes] for hist in historiales]


def _solo_companeros(historiales):
    """Deja en cada historial solo los partidos en que TODOS los jugadores elegidos jugaron y del mismo lado (compañeros).

    Dos jugadores del mismo partido son compañeros si tienen el mismo rival (así también se descartan los partidos en que
    uno ya había sido traspasado). Mantiene el orden del más reciente al más antiguo."""
    if len(historiales) < 2:
        return historiales
    por_evento = [{g["event"]: g for g in hist} for hist in historiales]
    comunes = set(por_evento[0])
    for d in por_evento[1:]:
        comunes &= set(d)
    comunes = {e for e in comunes if len({d[e]["rival_id"] for d in por_evento}) == 1}
    return [[g for g in hist if g["event"] in comunes] for hist in historiales]


def _solo_rivales(historiales):
    """Deja en cada historial solo los partidos en que TODOS los jugadores elegidos jugaron y NO todos del mismo lado.

    Con 2 jugadores son los partidos en que se enfrentaron (equipos distintos). Con 3 o 4, los partidos en que hubo
    al menos un jugador en cada bando. Mantiene el orden del más reciente al más antiguo."""
    if len(historiales) < 2:
        return historiales
    por_evento = [{g["event"]: g for g in hist} for hist in historiales]
    comunes = set(por_evento[0])
    for d in por_evento[1:]:
        comunes &= set(d)
    comunes = {e for e in comunes if len({d[e]["rival_id"] for d in por_evento}) > 1}
    return [[g for g in hist if g["event"] in comunes] for hist in historiales]


# ---------------------------------------------------------------------------
# Tarjetas de resumen
# ---------------------------------------------------------------------------
def _fmt(valor, clave):
    texto = h._fmt(valor)
    return texto + "%" if (valor is not None and clave.endswith("%")) else texto


def _tarjeta(i, nombre, equipo, juegos, etiqueta, total, prom, lider, maximo_pts):
    esc = html.escape
    grandes = "".join(
        f'<div class="jg-g{" lider" if lider.get(c) == i else ""}"><b style="animation-delay:{.1 + .08 * k:.2f}s">{_fmt(prom[c], c)}</b><span>{e}</span></div>'
        for k, (c, e, _) in enumerate(GRANDES))
    pequenas = "".join(
        f'<div class="jg-p{" lider" if lider.get(c) == i else ""}"><b>{_fmt(prom[c], c)}</b><span>{e}</span></div>'
        for c, e, _ in PEQUENAS)
    # Minutos por partido oficial (liga regular + playoffs, según lo que esté activado) de los partidos que se están promediando
    min_prom = prom.get("MIN")
    minutos = (f'<span class="jg-min" title="Minutos promedio por partido oficial · {esc(etiqueta)}">'
               f'⏱ {_fmt(min_prom, "MIN")} <small>min/partido</small></span>') if min_prom is not None else ""
    serie = juegos[:15]                      # de lo más reciente (izquierda) a lo más antiguo (derecha)
    barras = "".join(
        f'<i title="{esc(g["fecha"])} · {_fmt(g["PTS"], "PTS")} pts" style="height:{max(6, round(100 * (g["PTS"] or 0) / maximo_pts))}%;animation-delay:{.25 + .04 * k:.2f}s"></i>'
        for k, g in enumerate(serie))
    return (f'<div class="jg-card" style="--c:{COLORES[i]};animation-delay:{i * .08:.2f}s">'
            f'<div class="jg-head"><span class="jg-nom">{esc(nombre)}</span>'
            f'{f"<span class=jg-eq>{esc(equipo)}</span>" if equipo else ""}{minutos}</div>'
            f'<div class="jg-sub">{etiqueta} · {total} partidos disponibles</div>'
            f'<div class="jg-grandes">{grandes}</div><div class="jg-pequenas">{pequenas}</div>'
            f'<div class="jg-spark-t">Puntos por partido</div><div class="jg-spark">{barras}</div>'
            f'<div class="jg-spark-e"><span>← más reciente</span><span>más antiguo →</span></div></div>')


# ---------------------------------------------------------------------------
# Lista de últimos partidos (estilo marcador: equipos con escudo, resultado y estadísticas clave)
# ---------------------------------------------------------------------------
EQUIPOS_NBA = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets", "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons", "GS": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies", "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves", "NO": "New Orleans Pelicans", "NY": "New York Knicks",
    "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SA": "San Antonio Spurs", "TOR": "Toronto Raptors",
    "UTAH": "Utah Jazz", "WSH": "Washington Wizards",
}

def _css_partidos(p):
    """CSS de la tabla de últimos partidos con colores SÓLIDOS (sin transparencias), claro u oscuro."""
    return """
<style>
.up-caja { max-height: 680px; overflow: auto; border-radius: 22px; background: %(caja_bg)s; color: %(texto)s;
  border: 1px solid %(borde_t)s; box-shadow: 0 22px 50px -22px %(sombra)s, 0 2px 0 rgba(255,255,255,.5) inset; }
.up-tabla { width: 100%%; border-collapse: separate; border-spacing: 0; font-variant-numeric: tabular-nums; background: transparent; }
.up-tabla thead th { position: sticky; top: 0; z-index: 3; background: %(cab_bg)s; color: %(cab_txt)s; font-size: .68rem; letter-spacing: .12em;
  font-weight: 700; padding: .8rem .55rem; text-align: center; white-space: nowrap; border-bottom: 2px solid #6366f1; }
.up-tabla thead th.sep { border-left: 1px solid rgba(255,255,255,.12); }
.up-tabla td.sep { border-left: 1px solid %(borde_t)s; }
.up-tabla thead th.izq { text-align: left; padding-left: 1.1rem; }
.up-tabla td { padding: .5rem .55rem; text-align: center; border-bottom: 1px solid %(borde_t)s; font-size: .92rem; background: transparent;
  transition: background .18s ease; }
.up-tabla tbody tr:nth-child(even) td { background: %(zebra_t)s; }
.up-tabla tbody tr:hover td { background: %(hover_t)s; }
/* franja de color a la izquierda de cada fila: verde si ganó el equipo, rojo si perdió */
.up-tabla tbody tr:has(.up-res.g) td:first-child { box-shadow: inset 4px 0 0 #22c55e; }
.up-tabla tbody tr:has(.up-res.p) td:first-child { box-shadow: inset 4px 0 0 #ef4444; }
.up-tabla tbody tr:last-child td { border-bottom: none; }
.up-tabla .up-fecha { color: %(suave)s; font-size: .82rem; white-space: nowrap; }
.up-tabla .up-liga { font-weight: 700; font-size: .72rem; letter-spacing: .06em; color: %(suave)s; white-space: nowrap; }
.up-tabla .up-liga.po { color: #b7791f; }
.up-eq { display: grid; grid-template-columns: 1fr auto; align-items: center; column-gap: 18px; min-width: 260px; text-align: left; }
.up-eq > span { display: flex; align-items: center; gap: 8px; padding: 2px 0; white-space: nowrap; }
.up-eq img { width: 22px; height: 22px; object-fit: contain; }
.up-eq .gana { font-weight: 800; }
.up-eq .pierde { color: %(suave)s; }
.up-eq .pts { justify-self: end; font-weight: 800; }
.up-eq .pts.pierde { font-weight: 500; }
.up-tabla .up-pts { font-weight: 800; font-size: 1rem; }
.up-tabla .cero { color: %(suave)s; opacity: .55; }
.up-tabla .tiro { font-size: .86rem; white-space: nowrap; }
.up-res { display: inline-block; min-width: 28px; padding: 3px 0; border-radius: 6px; color: #fff; font-weight: 800; font-size: .78rem; }
.up-res.g { background: #16a34a; } .up-res.p { background: #dc2626; }
.up-tabla tfoot td { position: sticky; bottom: 0; z-index: 3; background: %(pie_bg)s; color: %(pie_txt)s; font-weight: 800;
  border-top: 2px solid #6366f1; border-bottom: none; font-size: .9rem; }
.up-tabla tfoot td.etq { color: %(pie_txt)s; opacity: .75; font-size: .7rem; letter-spacing: .12em; text-align: right; padding-right: 1rem; }
</style>
""" % p




def _marcador(g):
    """(puntos del equipo del jugador, puntos del rival) a partir del texto del marcador y de si ganó su equipo."""
    nums = re.findall(r"\d+", str(g.get("marcador", "")))
    if len(nums) < 2:
        return None, None
    a, b = int(nums[0]), int(nums[1])
    return (max(a, b), min(a, b)) if g.get("gano_equipo") else (min(a, b), max(a, b))


def _descanso_por_partido(hist):
    """{clave del partido: días de descanso antes de él} sobre el historial COMPLETO (más reciente primero).

    0 = back-to-back (jugó el día anterior). Se calcula con todo el historial, no con el recortado por rival o ventana,
    para que el partido previo sea siempre el real. Sin partido previo cargado, o con más de 10 días de pausa
    (inicio de temporada), no hay dato y el partido no se incluye."""
    res = {}
    for i, g in enumerate(hist[:-1]):
        a, b = _fecha_iso(g.get("fecha")), _fecha_iso(hist[i + 1].get("fecha"))
        if not a or not b:
            continue
        descanso = (a - b).days - 1
        if 0 <= descanso <= 10:
            res[g.get("event") or g.get("fecha")] = descanso
    return res


def _detalle_partido(g, descansos=None):
    """Lo que muestra el tooltip de cada barra: fecha, rival, resultado, minutos, fase y días de descanso."""
    mios, rival = _marcador(g)
    gano = g.get("gano_equipo")
    resultado = ""
    if mios is not None:
        resultado = f"{'Victoria' if gano else 'Derrota'} {mios}–{rival}"
    elif gano is not None:
        resultado = "Victoria" if gano else "Derrota"
    sigla = g.get("rival", "")
    return {"fecha": g.get("fecha"), "rival": g.get("rival_nombre") or EQUIPOS_NBA.get(sigla, sigla), "sede": g.get("sede"),
            "resultado": resultado, "gano": None if gano is None else bool(gano), "minutos": g.get("MIN"), "fase": g.get("fase"),
            "descanso": (descansos or {}).get(g.get("event") or g.get("fecha")),
            "anotacion": _anotacion(g)}


_POSICIONES = {"PG": "Base", "SG": "Escolta", "SF": "Alero", "PF": "Ala-pívot", "C": "Pívot",
               "G": "Guardia", "F": "Alero", "GF": "Escolta-alero", "FC": "Ala-pívot"}


@st.cache_data(ttl=3600, show_spinner=False)
def _biometria():
    """{id: (posición en español, altura en cm)} de la misma lista de jugadores que usa la vista; {} si no se pudo leer."""
    try:
        return {str(j["id"]): (_POSICIONES.get(str(j.get("pos") or "").upper().replace("-", ""), j.get("pos") or ""), j.get("cm"))
                for j in h._jugadores()}
    except Exception:  # noqa: BLE001
        return {}


def _bio_texto(pid, separador=" · "):
    """«Alero · 2.03 m» (o solo una de las dos partes, o «» si no hay datos)."""
    pos, cm = _biometria().get(str(pid), ("", None))
    return separador.join(x for x in (pos, f"{cm / 100:.2f} m" if cm else "") if x)


# --- Minutos por cuarto -----------------------------------------------------------------------------------------
# ESPN no da los minutos por cuarto, pero sí los cambios de cada partido (quién entra y quién sale, con cuarto y reloj).
# Con los titulares y esos cambios se reconstruye cuánto estuvo en cancha cada cuarto. Si lo reconstruido no suma los
# minutos oficiales del partido (± 1), el dato se descarta: mejor nada que minutos inventados.
_CAMBIOS = {}   # evento -> {"tit": {ids}, "cambios": [(cuarto, segundos que faltan, id1, id2)], "n": cuartos} | None (sin datos)


def _reloj_seg(txt):
    """'11:34' -> 694; '45.2' -> 45; None si no se entiende."""
    try:
        t = str(txt).strip()
        if ":" in t:
            m, s_ = t.split(":")
            return int(m) * 60 + int(float(s_))
        return int(float(t))
    except (ValueError, TypeError):
        return None


def _bajar_cambios(eid):
    """Titulares y cambios de un partido, o None si ESPN no los trae. Sin Streamlit: corre en hilos."""
    j = h._get_json(f"{h.BASE}/summary?event={eid}")
    tit = set()
    for eq in (j.get("boxscore") or {}).get("players") or []:
        for grupo in eq.get("statistics") or []:
            for a in grupo.get("athletes") or []:
                if a.get("starter"):
                    tit.add(str((a.get("athlete") or {}).get("id")))
    cambios, n = [], 4
    for p in j.get("plays") or []:
        per = (p.get("period") or {}).get("number")
        if isinstance(per, int):
            n = max(n, per)
        txt = p.get("text") or ""
        if "Substitution" not in str((p.get("type") or {}).get("text") or "") and " enters the game for " not in txt:
            continue
        ids = [str((x.get("athlete") or {}).get("id")) for x in p.get("participants") or []]
        seg = _reloj_seg((p.get("clock") or {}).get("displayValue"))
        if len(ids) >= 2 and isinstance(per, int) and seg is not None:
            cambios.append((per, seg, ids[0], ids[1]))
    return {"tit": tit, "cambios": cambios, "n": n} if tit and cambios else None


def _minutos_por_cuarto(datos, pid, total, entra_primero):
    """Segundos jugados en cada cuarto por `pid`, o None si no suman `total` minutos (± 1 min)."""
    largo = lambda per: 720 if per <= 4 else 300
    mins, periodo, desde = {}, 1, (720 if str(pid) in datos["tit"] else None)

    def avanzar_hasta(destino):
        nonlocal periodo, desde
        while periodo < destino:
            if desde is not None:
                mins[periodo] = mins.get(periodo, 0) + desde       # estaba en cancha hasta el final del cuarto
                desde = largo(periodo + 1)                         # y sigue en cancha al empezar el siguiente
            periodo += 1

    for per, seg, a, b in datos["cambios"]:
        avanzar_hasta(per)
        entra, sale = (a, b) if entra_primero else (b, a)
        if entra == str(pid) and desde is None:
            desde = seg
        elif sale == str(pid) and desde is not None:
            mins[per] = mins.get(per, 0) + desde - seg
            desde = None
    avanzar_hasta(datos["n"] + 1)
    segundos = [int(round(mins.get(k, 0))) for k in range(1, datos["n"] + 1)]
    if total is None or abs(sum(segundos) / 60 - float(total)) > 1.0:
        return None
    return segundos


def _cuartos_de_partidos(pid, juegos):
    """Una lista por partido (en el orden de `juegos`) con sus minutos por cuarto, o None donde no se pudo."""
    faltan = list({g.get("event") for g in juegos if g.get("event") and g.get("event") not in _CAMBIOS})
    if faltan:
        def bajar(e):
            try:
                return True, _bajar_cambios(e)
            except Exception:  # noqa: BLE001 - una falla de red no se guarda: se reintenta en la próxima carga
                return False, None
        with ThreadPoolExecutor(max_workers=8) as pool:
            for e, (ok, d) in zip(faltan, pool.map(bajar, faltan)):
                if ok:
                    _CAMBIOS[e] = d
    salida = []
    for g in juegos:
        d, total = _CAMBIOS.get(g.get("event")), g.get("MIN")
        r = None
        if d:
            for entra_primero in (True, False):   # no se sabe cuál de los dos participantes es el que entra: gana el orden que cuadra
                r = _minutos_por_cuarto(d, g.get("id_jugador") or pid, total, entra_primero)
                if r:
                    break
        salida.append(r)
    return salida


def _leer_tiros(texto):
    """'5-11' -> (5, 11); None si el dato no existe o no se entiende (a diferencia de _hechos, que devuelve (0, 0))."""
    try:
        hechos, intentos = str(texto).split("-")
        return int(hechos), int(intentos)
    except (ValueError, TypeError):
        return None


def _anotacion(g):
    """Cómo se hicieron los puntos de un partido: {"dobles": (canastas, pts), "triples": (...), "libres": (...)}.

    Dobles = tiros de campo anotados menos los triples. Si no hay datos de tiros, o si lo calculado no suma los
    puntos del partido (datos incompletos), devuelve None y el tooltip simplemente no muestra el desglose."""
    fg, tp, ft = _leer_tiros(g.get("FG")), _leer_tiros(g.get("3PT")), _leer_tiros(g.get("FT"))
    if fg is None or tp is None or ft is None or fg[0] < tp[0]:
        return None
    dobles, triples, libres = fg[0] - tp[0], tp[0], ft[0]
    total = dobles * 2 + triples * 3 + libres
    try:
        if g.get("PTS") is not None and abs(float(g["PTS"]) - total) > 1e-6:
            return None
    except (TypeError, ValueError):
        return None
    return {"dobles": (dobles, dobles * 2), "triples": (triples, triples * 3), "libres": (libres, libres)}


def _url_escudo_nba(abbr):
    """URL del escudo NBA de ESPN para una sigla (la misma fuente que usa la tabla de últimos partidos)."""
    abbr = str(abbr or "").strip().lower()
    return f"https://a.espncdn.com/i/teamlogos/nba/500/{abbr}.png" if re.fullmatch(r"[a-z]{2,5}", abbr) else ""


def _celda_equipo(abbr, nombre, pts, gana):
    clase = "gana" if gana else "pierde"
    logo = f"https://a.espncdn.com/i/teamlogos/nba/500/{html.escape(abbr.lower())}.png" if abbr else ""
    img = f'<img src="{logo}" alt="">' if logo else ""
    txt = "–" if pts is None else str(pts)
    return f'<span class="{clase}">{img}{html.escape(nombre)}</span><span class="pts {clase}">{txt}</span>'


def _num_celda(v, clase=""):
    if v is None:
        return f'<td class="{clase}">–</td>'
    cero = " cero" if float(v) == 0 else ""
    return f'<td class="{clase}{cero}">{int(round(float(v)))}</td>'


def _tiro_celda(v, clase=""):
    """Celda de tiros 'anotados-intentos' (p. ej. 9-18)."""
    txt = html.escape(str(v)) if v not in (None, "") else "–"
    return f'<td class="tiro {clase}">{txt}</td>'


# (clave, encabezado, descripción al pasar el cursor)
COLS_NUM = [("MIN", "MIN", "Minutos"), ("PTS", "PTS", "Puntos"), ("REB", "REB", "Rebotes"), ("AST", "AST", "Asistencias"),
            ("STL", "ROB", "Robos"), ("BLK", "TAP", "Tapones"), ("TO", "PER", "Pérdidas"), ("PF", "FAL", "Faltas")]
COLS_TIRO = [("FG", "TC", "Tiros de campo (anotados-intentos)"), ("3PT", "3P", "Triples (anotados-intentos)"),
             ("FT", "TL", "Tiros libres (anotados-intentos)")]


def _tabla_ultimos_partidos(juegos, equipo):
    """HTML con una fila por partido: fecha, fase, equipos con marcador, estadísticas, tiros, resultado y promedio al pie."""
    esc = html.escape
    # Solo muestra columnas que tienen datos (datos guardados de versiones anteriores pueden no traer faltas o tiros)
    nums = [c for c in COLS_NUM if any(g.get(c[0]) is not None for g in juegos)]
    tiros = [c for c in COLS_TIRO if any(g.get(c[0]) not in (None, "") for g in juegos)]
    filas = []
    for g in juegos:
        try:
            anio, mes, dia = str(g["fecha"]).split("-")
            fecha = f"{dia}.{mes}.{anio[2:]}"
        except (KeyError, ValueError):
            fecha = "—"
        mios, rival = _marcador(g)
        gano = bool(g.get("gano_equipo"))
        r_abbr = g.get("rival", "")
        mi_celda = _celda_equipo(equipo, EQUIPOS_NBA.get(equipo, equipo), mios, gano)
        r_celda = _celda_equipo(r_abbr, g.get("rival_nombre") or EQUIPOS_NBA.get(r_abbr, r_abbr), rival, not gano)
        celdas = (mi_celda + r_celda) if g.get("sede") == "Local" else (r_celda + mi_celda)   # el local va arriba
        po = g.get("fase") == "Playoffs"
        celdas_num = "".join(_num_celda(g.get(c), "up-pts" if c == "PTS" else ("sep" if k == 0 else ""))
                             for k, (c, _, _) in enumerate(nums))
        celdas_tiro = "".join(_tiro_celda(g.get(c), "sep" if k == 0 else "") for k, (c, _, _) in enumerate(tiros))
        filas.append(
            f'<tr><td class="up-fecha">{esc(fecha)}</td><td class="up-liga{" po" if po else ""}">{"PLAYOFFS" if po else "NBA"}</td>'
            f'<td class="sep"><div class="up-eq">{celdas}</div></td>'
            + celdas_num + celdas_tiro
            + f'<td class="sep"><span class="up-res {"g" if gano else "p"}">{"G" if gano else "P"}</span></td></tr>')

    cab = ('<th class="izq">FECHA</th><th>FASE</th><th class="izq sep">PARTIDO</th>'
           + "".join(f'<th title="{d}"{" class=sep" if k == 0 else ""}>{t}</th>' for k, (_, t, d) in enumerate(nums))
           + "".join(f'<th title="{d}"{" class=sep" if k == 0 else ""}>{t}</th>' for k, (_, t, d) in enumerate(tiros))
           + '<th class="sep" title="Resultado del equipo (G = ganó, P = perdió)">G/P</th>')

    # Pie: promedio por partido (y % de tiro sumando todos los tiros) de los partidos mostrados
    ganados = sum(1 for g in juegos if g.get("gano_equipo"))
    pie = f'<td class="etq" colspan="3">PROMEDIO · {len(juegos)} PARTIDOS</td>'
    for k, (c, _, _) in enumerate(nums):
        pie += f'<td class="{"sep" if k == 0 else ""}">{h._fmt(h._promedio([g[c] for g in juegos if g.get(c) is not None]))}</td>'
    for k, (c, _, _) in enumerate(tiros):
        pct = _porcentaje(juegos, c)
        pie += f'<td class="{"sep" if k == 0 else ""}">{"–" if pct is None else f"{pct}%"}</td>'
    pie += f'<td class="sep">{ganados}-{len(juegos) - ganados}</td>'
    return (f'<div class="up-caja"><table class="up-tabla"><thead><tr>{cab}</tr></thead>'
            f'<tbody>{"".join(filas)}</tbody><tfoot><tr>{pie}</tr></tfoot></table></div>')


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------
def _tabla_partidos(juegos):
    # Se usa .get() para que no falle si los datos guardados vienen de una versión anterior (sin faltas o tiros)
    filas = []
    for g in juegos:
        filas.append({
            "Fecha": g.get("fecha"),
            "Rival": f'{"vs" if g.get("sede") == "Local" else "@"} {g.get("rival", "?")}',
            "Resultado": ("✅ G " if g.get("gano_equipo") else "❌ P ") + str(g.get("marcador", "")),
            "Fase": "Playoffs" if g.get("fase") == "Playoffs" else "Regular",
            "MIN": g.get("MIN"), "PTS": g.get("PTS"), "REB": g.get("REB"), "AST": g.get("AST"),
            "ROB": g.get("STL"), "TAP": g.get("BLK"), "PER": g.get("TO"), "FALTAS": g.get("PF"),
            "TC": g.get("FG"), "3P": g.get("3PT"), "TL": g.get("FT"),
        })
    df = pd.DataFrame(filas)
    # Quita las columnas que no tienen ningún dato (p. ej. tiros, si los datos son de la versión anterior)
    return df.dropna(axis=1, how="all")


def _mostrar_tabla_partidos(juegos):
    if not juegos:
        st.info("Sin partidos en las temporadas elegidas.")
        return
    df = _tabla_partidos(juegos)
    topes = {c: max(float(df[c].max() or 1), 1) for c in ("PTS", "REB", "AST") if c in df.columns}
    config = {c: st.column_config.ProgressColumn(c, min_value=0, max_value=topes[c], format="%d") for c in topes}
    for c in ("MIN", "ROB", "TAP", "PER", "FALTAS"):
        if c in df.columns:
            config[c] = st.column_config.NumberColumn(c, format="%d")
    st.dataframe(df, hide_index=True, use_container_width=True, column_config=config, height=min(600, 38 + 35 * len(df)))


def _tabla_comparativa(nombres, lista_promedios):
    filas = []
    for col, etiqueta, mas_es_mejor in GRANDES + PEQUENAS:
        valores = [p.get(col) for p in lista_promedios]
        validos = [v for v in valores if v is not None]
        lider = "—"
        if len(validos) >= 2:
            mejor = max(validos) if mas_es_mejor else min(validos)
            lider = nombres[valores.index(mejor)] if validos.count(mejor) == 1 else "Empate"
        fila = {"Estadística": NOMBRES[col]}
        fila.update({n: _fmt(v, col) for n, v in zip(nombres, valores)})
        fila["Líder"] = lider
        filas.append(fila)
    return pd.DataFrame(filas)


COLOR_GANA = "font-weight:700;background-color:rgba(34,197,94,.38);"     # verde
COLOR_EMPATA = "font-weight:700;background-color:rgba(234,179,8,.45);"   # amarillo


def _colores_fila(fila, mas_es_mejor=True):
    """Verde = mejor valor de la fila; amarillo = empate en lo mejor (en pérdidas, menos es mejor). Los demás sin color."""
    valores = pd.to_numeric(fila, errors="coerce")
    validos = valores.dropna()
    if len(validos) < 2:
        return [""] * len(fila)
    mejor = validos.max() if mas_es_mejor else validos.min()
    empatados = int((validos == mejor).sum()) > 1
    color = COLOR_EMPATA if empatados else COLOR_GANA
    return [color if (pd.notna(v) and v == mejor) else "" for v in valores]


def _mostrar_comparacion(df, columnas, clave):
    """Muestra la tabla comparativa en un ancho acotado (columnas angostas) y resalta el mejor valor de cada fila."""
    estilo = df.style.format("{:.0f}", subset=columnas, na_rep="–")
    if len(columnas) > 1:
        estilo = estilo.apply(_colores_fila, axis=1, subset=columnas, mas_es_mejor=(clave != "TO"))
    # La tabla se estira al ancho de su contenedor; en una columna más estrecha cada columna queda más corta.
    # Con 6 o más columnas (3+ jugadores) usa todo el ancho para que no haga falta desplazarse de lado.
    ancho = 1.0 if len(df.columns) >= 6 else 0.11 * len(df.columns) + 0.05
    contenedor = st.columns([ancho, max(1 - ancho, 0.01)])[0] if ancho < 1 else st.container()
    with contenedor:
        st.dataframe(estilo, hide_index=True, use_container_width=True, height=min(600, 38 + 35 * len(df)))


def _es_oscuro():
    """True si la app usa el tema oscuro de Streamlit (si no se puede saber, tema claro)."""
    try:
        return st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001
        try:
            return st.get_option("theme.base") == "dark"
        except Exception:  # noqa: BLE001
            return False


# Paletas SÓLIDAS (sin transparencias) para que no se vea el fondo de la página a través de la tabla.
PALETA_CLARA = dict(fondo="#ffffff", cab="#f4f5fa", zebra="#f9fafc", hover="#eef0f8", borde="#dfe3ee",
                    texto="#1f2433", suave="#6b7287", pista="#e6e9f2", pie="#f4f5fa", sombra="rgba(30,41,90,.14)",
                    # tabla de partidos: degradados
                    caja_bg="linear-gradient(160deg,#ffffff 0%,#eef1ff 55%,#e2e8fb 100%)",
                    cab_bg="linear-gradient(180deg,#312e81 0%,#1e1b4b 100%)", cab_txt="#c7d2fe",
                    pie_bg="linear-gradient(180deg,#e0e7ff 0%,#c7d2fe 100%)", pie_txt="#1e1b4b",
                    zebra_t="rgba(99,102,241,.07)", hover_t="rgba(99,102,241,.16)", borde_t="rgba(99,102,241,.15)")
PALETA_OSCURA = dict(fondo="#161a26", cab="#1d2232", zebra="#1a1f2d", hover="#242a3d", borde="#2c3348",
                     texto="#e8eaf2", suave="#98a0b8", pista="#2a3045", pie="#1d2232", sombra="rgba(0,0,0,.45)",
                     # tabla de partidos: degradados
                     caja_bg="linear-gradient(160deg,#0f172a 0%,#1e1b4b 100%)",
                     cab_bg="linear-gradient(180deg,#3730a3 0%,#26236b 100%)", cab_txt="#c7d2fe",
                     pie_bg="linear-gradient(180deg,#26236b 0%,#1e1b4b 100%)", pie_txt="#e0e7ff",
                     zebra_t="rgba(255,255,255,.04)", hover_t="rgba(165,180,252,.14)", borde_t="rgba(255,255,255,.08)")


def _css_lado(p):
    return """
<style>
.ll-caja { max-height: 640px; overflow: auto; border-radius: 18px; background: %(fondo)s; color: %(texto)s;
  border: 1px solid %(borde)s; box-shadow: 0 10px 30px %(sombra)s; }
.ll-tabla { width: 100%%; border-collapse: separate; border-spacing: 0; font-variant-numeric: tabular-nums; font-size: .92rem; background: %(fondo)s; }

/* ---------- Cabecera con rostro ---------- */
.ll-tabla thead th { position: sticky; top: 0; z-index: 3; background: %(cab)s; padding: .85rem 1rem; text-align: left;
  border-bottom: 3px solid var(--c); white-space: nowrap; }
.ll-tabla thead th.ll-n { color: %(suave)s; text-align: center; font-size: .72rem; letter-spacing: .1em; border-bottom-color: %(borde)s; }
.ll-j { display: flex; align-items: center; gap: 14px; }
.ll-foto { position: relative; flex: none; width: 60px; height: 60px; border-radius: 50%%; overflow: hidden;
  background: color-mix(in srgb, var(--c) 22%%, %(fondo)s); border: 3px solid var(--c); box-shadow: 0 4px 12px %(sombra)s; }
.ll-foto img { position: absolute; left: 0; top: 4px; width: 100%%; height: 100%%; object-fit: cover; object-position: top center; }
.ll-nom { display: block; font-size: 1.08rem; font-weight: 800; color: var(--c); line-height: 1.15; }
.ll-min { display: inline-block; margin: 4px 0 0 6px; padding: 1px 9px; border-radius: 999px; font-size: .68rem; font-weight: 700;
  white-space: nowrap; color: var(--c); background: %(cab)s; border: 1px solid var(--c); }
.ll-eq { display: inline-block; margin-top: 4px; padding: 1px 9px; border-radius: 999px; font-size: .68rem; font-weight: 700;
  letter-spacing: .08em; color: #fff; background: var(--c); }

/* ---------- Filas ---------- */
.ll-tabla td { padding: .6rem 1rem; border-bottom: 1px solid %(borde)s; vertical-align: middle; background: %(fondo)s; }
.ll-tabla tbody tr:nth-child(even) td { background: %(zebra)s; }
.ll-tabla tbody tr:hover td { background: %(hover)s; }
.ll-tabla tbody tr:last-child td { border-bottom: 0; }
.ll-n { width: 46px; text-align: center; font-size: .76rem; font-weight: 700; color: %(suave)s; }
.ll-f { font-size: .8rem; color: %(suave)s; white-space: nowrap; border-left: 1px solid %(borde)s; }
.ll-v { min-width: 170px; }
.ll-b { display: grid; grid-template-columns: 1fr 2.4rem; align-items: center; gap: 12px; }
.ll-b span { height: 9px; border-radius: 99px; background: %(pista)s; overflow: hidden; }
.ll-b i { display: block; height: 100%%; border-radius: 99px; background: var(--c); opacity: .5; }
.ll-b b { text-align: right; font-weight: 600; font-size: 1rem; }

/* ---------- Mejor de la fila ---------- */
.ll-tabla tbody tr td.ll-v.w { background: color-mix(in srgb, var(--c) 14%%, %(fondo)s); }
.ll-v.w .ll-b i { opacity: 1; }
.ll-v.w .ll-b b { font-weight: 800; color: var(--c); }
.ll-v.w .ll-b b::before { content: "▲"; font-size: .55rem; margin-right: 3px; vertical-align: middle; }
.ll-tabla tbody tr td.ll-v.e { background: color-mix(in srgb, #94a3b8 18%%, %(fondo)s); }
.ll-v.e .ll-b i { background: #94a3b8; opacity: .9; }
.ll-v.e .ll-b b { font-weight: 800; }

/* ---------- Pie con promedios ---------- */
.ll-tabla tfoot td { position: sticky; bottom: 0; z-index: 3; padding: .8rem 1rem; font-weight: 800; background: %(pie)s;
  border-top: 3px solid %(borde)s; border-bottom: 0; }
.ll-tabla tfoot .ll-n { font-size: .68rem; letter-spacing: .06em; color: %(suave)s; }
.ll-tabla tfoot .ll-pr { text-align: right; color: var(--c); font-size: 1.25rem; }

/* ---------- Ganador de la fila: mucho más marcado ---------- */
.ll-tabla tbody tr td.ll-v.w { background: color-mix(in srgb, var(--c) 30%%, %(fondo)s); box-shadow: inset 5px 0 0 var(--c); }
.ll-v.w .ll-b b { font-size: 1.15rem; }
.ll-v.w .ll-b span { height: 11px; }
.ll-tabla tbody tr td.ll-v.p .ll-b { opacity: .5; }
.ll-tabla tbody tr td.ll-v.p .ll-b b { font-weight: 500; }

/* ---------- Chip de partidos ganados en la cabecera ---------- */
.ll-gan { display: block; margin-top: 6px; font-size: .74rem; font-weight: 800; color: var(--c); }
.ll-gan.top { display: inline-block; padding: 2px 10px; border-radius: 999px; background: var(--c); color: #fff; }

/* ---------- Marcador de líderes ---------- */
.mk-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; margin: .3rem 0 1.1rem; }
.mk-t { background: %(fondo)s; color: %(texto)s; border: 1px solid %(borde)s; border-radius: 16px; padding: .7rem .75rem .6rem;
  box-shadow: 0 6px 18px %(sombra)s; border-top: 5px solid var(--c, %(borde)s); }
.mk-t.sel { outline: 2px solid var(--c, %(suave)s); }
.mk-h { display: flex; justify-content: space-between; align-items: center; margin-bottom: .45rem; font-size: .72rem; font-weight: 800;
  letter-spacing: .1em; text-transform: uppercase; color: %(suave)s; }
.mk-h em { font-style: normal; color: var(--c); letter-spacing: 0; text-transform: none; }
.mk-r { display: grid; grid-template-columns: 34px 1fr auto; align-items: center; gap: 9px; padding: 5px 6px; border-radius: 12px; margin-top: 4px;
  background: %(zebra)s; }
.mk-r.dim { opacity: .55; }
.mk-r.lider { background: color-mix(in srgb, var(--c) 24%%, %(fondo)s); box-shadow: inset 4px 0 0 var(--c); }
.mk-r .ll-foto { width: 34px; height: 34px; border-width: 2px; box-shadow: none; }
.mk-r .ll-foto img { top: 2px; }
.mk-bar { height: 9px; border-radius: 99px; background: %(pista)s; overflow: hidden; }
.mk-bar i { display: block; height: 100%%; border-radius: 99px; background: var(--c); }
.mk-v { text-align: right; line-height: 1.1; }
.mk-v b { display: block; font-size: 1.3rem; font-weight: 800; font-variant-numeric: tabular-nums; }
.mk-r.lider .mk-v b { color: var(--c); }
.mk-v small { font-size: .62rem; font-weight: 700; color: %(suave)s; }
</style>
""" % p


STATS_MARCADOR = [("PTS", "Puntos", True), ("REB", "Rebotes", True), ("AST", "Asistencias", True),
                  ("REB+AST", "REB+AST", True), ("PTS+REB", "PTS+REB", True), ("PTS+AST", "PTS+AST", True), ("P+R+A", "P+R+A", True), ("STL", "Robos", True), ("BLK", "Tapones", True),
                  ("3PM", "Triples", True), ("TO", "Pérdidas", False)]


def _victorias(series, clave, mas_es_mejor):
    """Cuántas filas (partidos comparados) gana cada jugador en esa estadística. Los empates no cuentan."""
    ganadas = [0] * len(series)
    for k in range(max(len(s) for s in series)):
        valores = [s[k].get(clave) if k < len(s) and s[k] else None for s in series]
        validos = [v for v in valores if v is not None]
        if len(validos) < 2:
            continue
        mejor = max(validos) if mas_es_mejor else min(validos)
        if validos.count(mejor) == 1:
            ganadas[valores.index(mejor)] += 1
    return ganadas


def _marcador_html(nombres, series, colores, ids, clave_sel):
    """Una tarjeta por estadística: promedio de cada jugador, barra y corona para el que va ganando."""
    esc = html.escape
    tarjetas = []
    for col, titulo, mas_es_mejor in STATS_MARCADOR:
        medias = [h._promedio([g[col] for g in s if g and g.get(col) is not None]) for s in series]
        validos = [m for m in medias if m is not None]
        lider = None
        if len(validos) >= 2:
            mejor = max(validos) if mas_es_mejor else min(validos)
            if validos.count(mejor) == 1:
                lider = medias.index(mejor)
        ganadas = _victorias(series, col, mas_es_mejor)
        tope = max(validos + [1])
        filas = []
        for i, (n, m, c, pid) in enumerate(zip(nombres, medias, colores, ids)):
            clase = "lider" if lider == i else ("dim" if lider is not None else "")
            foto = f'<span class="ll-foto"><img src="{_foto(pid)}" alt=""></span>' if pid else "<span></span>"
            ancho = 0 if m is None else round(100 * m / tope)
            filas.append(
                f'<div class="mk-r {clase}" style="--c:{c}" title="{esc(n)}">{foto}'
                f'<div class="mk-bar"><i style="width:{ancho}%"></i></div>'
                f'<div class="mk-v"><b>{"👑 " if lider == i else ""}{h._fmt(m)}</b><small>{ganadas[i]} filas</small></div></div>')
        color = colores[lider] if lider is not None else None
        estilo = f' style="--c:{color}"' if color else ""
        quien = f'<em>{esc(nombres[lider].split()[-1])}</em>' if lider is not None else "<em>empate</em>"
        sel = " sel" if col == clave_sel else ""
        tarjetas.append(f'<div class="mk-t{sel}"{estilo}><div class="mk-h"><span>{titulo}</span>{quien}</div>{"".join(filas)}</div>')
    return f'<div class="mk-grid">{"".join(tarjetas)}</div>'


def _foto(pid):
    return f"https://a.espncdn.com/i/headshots/nba/players/full/{pid}.png"


def _lado_a_lado(nombres, series, clave, etiqueta, ids=None, equipos=None):
    """Resumen de quién va ganando en cada estadística. La tabla partido a partido se abre con el botón «Abrir tabla en grande»."""
    ids = ids or [None] * len(nombres)
    colores = [COLORES[i % len(COLORES)] for i in range(len(nombres))]
    paleta = PALETA_OSCURA if _es_oscuro() else PALETA_CLARA
    st.markdown(_css_lado(paleta), unsafe_allow_html=True)   # aparte del HTML: la app oculta los bloques que traen <style>
    st.markdown("#### 🏆 Quién va ganando")
    st.markdown(_marcador_html(nombres, series, colores, ids, clave), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tabla grande (diálogo a pantalla casi completa)
# ---------------------------------------------------------------------------
_PCT = ("FG%", "3P%", "FT%")


def _val(v, clave):
    """Valor entero de una celda (con % en las estadísticas de porcentaje)."""
    if v is None:
        return "–"
    return f"{int(round(v))}{'%' if clave in _PCT else ''}"


def _css_grande(p, n=2):
    css = """
<style>
/* El diálogo ocupa casi toda la pantalla */
div[data-testid="stDialog"] div[role="dialog"] { width: min(__ancho__px, 96vw) !important; max-width: 96vw !important; }
div[data-testid="stDialog"] div[role="dialog"] h2 { font-size: 1.2rem !important; padding: 0 !important; }
.tg-wrap { display: flex; flex-direction: column; gap: 10px; }

div[data-testid="stDialog"] [data-testid="stVerticalBlock"] { gap: .4rem !important; }
.tg-cab { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin: 0; }
.tg-cab h3 { margin: 0; padding: 0; font-size: 1.1rem; font-weight: 800; color: __texto__; }
.tg-cab p { margin: 0; font-size: .74rem; color: __suave__; }
.tg-pastilla { padding: .1rem .65rem; border-radius: 999px; font-size: .64rem; font-weight: 800; letter-spacing: .08em;
  text-transform: uppercase; color: __suave__; background: __cab__; border: 1px solid __borde__; }

/* ---------- Tarjetas de jugador ---------- */
.tg-heroes { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 10px; margin: 0; }
.tg-card { position: relative; overflow: hidden; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  border-radius: 16px; padding: .55rem .8rem .55rem 1rem; color: __texto__;
  background: linear-gradient(135deg, color-mix(in srgb, var(--c) 18%, __fondo__) 0%, __fondo__ 75%);
  border: 1px solid color-mix(in srgb, var(--c) 40%, __borde__); }
.tg-card::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 5px; background: var(--c); }
.tg-card.lider { box-shadow: 0 0 0 2px var(--c); }
.tg-cinta { display: inline-block; margin-left: 6px; padding: 0 8px; border-radius: 999px; background: var(--c); color: #fff;
  font-size: .58rem; font-weight: 800; letter-spacing: .1em; vertical-align: middle; }
.tg-top { display: flex; align-items: center; gap: 10px; min-width: 0; }
.tg-foto { position: relative; flex: none; width: 46px; height: 46px; border-radius: 50%; overflow: hidden;
  background: color-mix(in srgb, var(--c) 25%, __fondo__); border: 2px solid var(--c); }
.tg-foto img { position: absolute; left: 0; top: 3px; width: 100%; height: 100%; object-fit: cover; object-position: top center; }
.tg-nom { font-size: 1rem; font-weight: 800; line-height: 1.15; color: var(--c); }
.tg-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 3px; }
.tg-eq, .tg-chip { padding: 0 8px; border-radius: 999px; font-size: .62rem; font-weight: 700; white-space: nowrap; }
.tg-eq { background: var(--c); color: #fff; letter-spacing: .08em; }
.tg-chip { color: __texto__; background: __cab__; border: 1px solid __borde__; }
.tg-kpis { display: flex; gap: 6px; }
.tg-kpis div { text-align: center; padding: .15rem .5rem; min-width: 56px; border-radius: 10px; background: color-mix(in srgb, var(--c) 9%, __fondo__);
  border: 1px solid color-mix(in srgb, var(--c) 22%, __borde__); }
.tg-kpis small { display: block; font-size: .54rem; font-weight: 800; letter-spacing: .1em; color: __suave__; }
.tg-kpis b { display: block; font-size: 1.15rem; line-height: 1.2; font-weight: 800; color: var(--c); font-variant-numeric: tabular-nums; }
.tg-kpis b span { font-size: .68rem; font-weight: 700; color: __suave__; }

/* ---------- Tabla ---------- */
.tg-caja { overflow: hidden; border-radius: 14px; background: __fondo__; border: 1px solid __borde__; box-shadow: 0 6px 18px __sombra__; }
.tg-t { width: 100%; border-collapse: separate; border-spacing: 0; font-variant-numeric: tabular-nums; color: __texto__; background: __fondo__; }
.tg-t thead th { padding: .4rem .8rem; text-align: left; background: __cab__;
  border-bottom: 3px solid var(--c, __borde__); white-space: nowrap; }
.tg-t thead th.tg-n { text-align: center; font-size: .66rem; letter-spacing: .12em; color: __suave__; width: 44px; }
.tg-hp { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 10px; font-weight: 800; color: var(--c); font-size: .9rem; }
.tg-hp .tg-foto { width: 28px; height: 28px; border-width: 2px; }
.tg-hp .tg-foto img { top: 2px; }
.tg-hp .tg-bio { flex-basis: 100%; font-style: normal; font-size: .66rem; font-weight: 600; letter-spacing: .02em; opacity: .7; text-transform: none; }
.tg-hp em { font-style: normal; padding: 0 8px; border-radius: 999px; background: var(--c); color: #fff; font-size: .62rem; letter-spacing: .08em; }

.tg-t td { padding: .22rem .8rem; border-bottom: 1px solid __borde__; vertical-align: middle; }
.tg-t tbody tr:nth-child(even) td { background: __zebra__; }
.tg-t tbody tr:hover td { background: __hover__; }
.tg-t tbody tr:last-child td { border-bottom: 0; }
.tg-t td.tg-n { text-align: center; }
.tg-num { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; font-size: .7rem; font-weight: 800;
  color: __suave__; background: __cab__; border: 1px solid __borde__; }
.tg-fecha { font-size: .72rem; font-weight: 600; color: __suave__; white-space: nowrap; }
.tg-fila { display: grid; grid-template-columns: 96px 1fr auto; align-items: center; gap: 10px; }
.tg-pista { height: 8px; border-radius: 99px; background: __pista__; overflow: hidden; }
.tg-pista i { display: block; height: 100%; border-radius: 99px; background: var(--c); opacity: .45; }
.tg-fila b { min-width: 2.8rem; text-align: right; font-size: 1rem; font-weight: 600; }

/* Mejor de la fila */
.tg-t tbody tr td.tg-c.w { background: linear-gradient(90deg, color-mix(in srgb, var(--c) 32%, __fondo__), color-mix(in srgb, var(--c) 12%, __fondo__));
  box-shadow: inset 5px 0 0 var(--c); }
.tg-c.w .tg-pista { height: 10px; }
.tg-c.w .tg-pista i { opacity: 1; }
.tg-c.w .tg-fila b { font-size: 1.15rem; font-weight: 800; color: var(--c); }
.tg-c.w .tg-fila b::before { content: "▲"; font-size: .6rem; margin-right: 5px; vertical-align: middle; }
.tg-c.w .tg-fecha { color: __texto__; }
.tg-t tbody tr td.tg-c.e { background: color-mix(in srgb, #94a3b8 20%, __fondo__); }
.tg-c.e .tg-pista i { background: #94a3b8; opacity: .9; }
.tg-c.e .tg-fila b { font-weight: 800; }
.tg-c.p .tg-fila { opacity: .55; }
.tg-c .mx { margin-left: 4px; font-size: .7rem; color: #d4a017; }

/* Pie con promedios */
.tg-t tfoot td { padding: .35rem .8rem; background: __pie__; border-top: 3px solid __borde__; border-bottom: 0; }
.tg-t tfoot td.tg-n { font-size: .6rem; font-weight: 800; letter-spacing: .08em; color: __suave__; text-align: center; }
.tg-t tfoot td.tg-pr { font-size: 1.15rem; font-weight: 800; color: var(--c); text-align: right; }
.tg-t tfoot td.tg-pr small { display: block; font-size: .6rem; font-weight: 800; letter-spacing: .12em; color: __suave__; }
</style>
"""
    css = css.replace("__ancho__", "1040" if n <= 2 else "1260")
    for k, v in p.items():
        css = css.replace(f"__{k}__", v)
    return css


def _heroes_html(nombres, series, clave, colores, ids, equipos, mas_es_mejor):
    """Una tarjeta por jugador: rostro, equipo, minutos, promedio, mejor partido y filas ganadas."""
    esc = html.escape
    filas = max(len(s) for s in series)
    ganadas = _victorias(series, clave, mas_es_mejor)
    tope_g = max(ganadas)
    lider = ganadas.index(tope_g) if tope_g > 0 and ganadas.count(tope_g) == 1 else None
    sufijo = "%" if clave in _PCT else ""
    tarjetas = []
    for i, (n, s, c, pid, eq) in enumerate(zip(nombres, series, colores, ids, equipos)):
        vals = [g[clave] for g in s if g and g.get(clave) is not None]
        prom = h._promedio(vals)
        mejor = (max(vals) if mas_es_mejor else min(vals)) if vals else None
        mins = h._promedio([g["MIN"] for g in s if g and g.get("MIN") is not None])
        foto = f'<span class="tg-foto"><img src="{_foto(pid)}" alt=""></span>' if pid else ""
        chip_eq = f'<span class="tg-eq">{esc(eq)}</span>' if eq else ""
        chip_min = f'<span class="tg-chip">⏱ {h._fmt(mins)} min/partido</span>' if mins is not None else ""
        pos_b, cm_b = _biometria().get(str(pid), ("", None))
        chip_bio = (f'<span class="tg-chip">🧍 {esc(pos_b)}</span>' if pos_b else "") + \
                   (f'<span class="tg-chip">📏 {cm_b / 100:.2f} m</span>' if cm_b else "")
        cinta = '<span class="tg-cinta">👑 LÍDER</span>' if lider == i else ""
        tarjetas.append(
            f'<div class="tg-card{" lider" if lider == i else ""}" style="--c:{c}"><div class="tg-top">{foto}<div><div class="tg-nom">{esc(n)}{cinta}</div>'
            f'<div class="tg-chips">{chip_eq}{chip_bio}{chip_min}</div></div></div>'
            f'<div class="tg-kpis">'
            f'<div><small>PROMEDIO</small><b>{h._fmt(prom)}{sufijo}</b></div>'
            f'<div><small>MEJOR</small><b>{_val(mejor, clave)}</b></div>'
            f'<div><small>GANA</small><b>{ganadas[i]}<span>/{filas}</span></b></div></div></div>')
    return f'<div class="tg-heroes">{"".join(tarjetas)}</div>'


def _tabla_grande_html(nombres, series, clave, colores, ids, equipos, mas_es_mejor):
    esc = html.escape
    filas = max(len(s) for s in series)
    todos = [g[clave] for s in series for g in s if g and g.get(clave) is not None]
    tope = max(todos + [1])
    maximos = []
    for s in series:
        vals = [g[clave] for g in s if g and g.get(clave) is not None]
        maximos.append((max(vals) if mas_es_mejor else min(vals)) if vals else None)

    cab = '<th class="tg-n">#</th>'
    for n, c, pid, eq in zip(nombres, colores, ids, equipos):
        foto = f'<span class="tg-foto"><img src="{_foto(pid)}" alt=""></span>' if pid else ""
        chip = f'<em>{esc(eq)}</em>' if eq else ""
        bio = _bio_texto(pid)
        chip_bio = f'<i class="tg-bio">{esc(bio)}</i>' if bio else ""
        cab += f'<th style="--c:{c}"><div class="tg-hp">{foto}<span>{esc(n)}</span>{chip}{chip_bio}</div></th>'

    cuerpo = []
    for k in range(filas):
        partidos = [s[k] if k < len(s) else None for s in series]
        valores = [g.get(clave) if g else None for g in partidos]
        validos = [v for v in valores if v is not None]
        mejor = (max(validos) if mas_es_mejor else min(validos)) if len(validos) > 1 else None
        empate = mejor is not None and validos.count(mejor) > 1
        celdas = [f'<td class="tg-n"><span class="tg-num">{k + 1}</span></td>']
        for g, v, c, mx in zip(partidos, valores, colores, maximos):
            fecha = h._fecha_bonita(g["fecha"]) if g else "–"
            clase = "" if mejor is None or v is None else (" e" if (empate and v == mejor) else (" w" if v == mejor else " p"))
            if v is None:
                celdas.append(f'<td class="tg-c" style="--c:{c}"><div class="tg-fila"><span class="tg-fecha">{esc(fecha)}</span>'
                              f'<div class="tg-pista"></div><b>–</b></div></td>')
                continue
            marca = '<span class="mx" title="Su mejor partido">★</span>' if (mx is not None and v == mx and len(validos) > 0) else ""
            celdas.append(
                f'<td class="tg-c{clase}" style="--c:{c}"><div class="tg-fila"><span class="tg-fecha">{esc(fecha)}{marca}</span>'
                f'<div class="tg-pista"><i style="width:{round(100 * v / tope)}%"></i></div>'
                f'<b>{_val(v, clave)}</b></div></td>')
        cuerpo.append(f'<tr>{"".join(celdas)}</tr>')

    sufijo = "%" if clave in _PCT else ""
    pie = '<td class="tg-n">PROM.</td>' + "".join(
        f'<td class="tg-pr" style="--c:{c}">{h._fmt(h._promedio([g[clave] for g in s if g and g.get(clave) is not None]))}{sufijo}</td>'
        for s, c in zip(series, colores))
    return (f'<div class="tg-caja"><table class="tg-t"><thead><tr>{cab}</tr></thead>'
            f'<tbody>{"".join(cuerpo)}</tbody><tfoot><tr>{pie}</tr></tfoot></table></div>')


def _ganadores_partido_html(nombres, series, clave, colores, mas_es_mejor, paleta):
    """Resumen de quién se lleva cada partido: en el MISMO partido, el jugador con más (o menos, en pérdidas) de la estadística.

    Una tarjeta por jugador con cuántos partidos lideró y una tira de puntos (el más reciente a la izquierda) con el líder de cada
    uno. Los empates no cuentan para nadie. Devuelve "" si no hay al menos 2 jugadores con partidos en común."""
    if len(series) < 2:
        return ""
    esc = html.escape
    por_evento = [{g["event"]: g for g in s if g and g.get("event") is not None} for s in series]
    comunes = set.intersection(*[set(d) for d in por_evento])
    orden = [g["event"] for g in series[0] if g and g.get("event") in comunes]
    victorias, tira, total, empates = [0] * len(nombres), [], 0, 0
    for ev in orden:
        valores = [d[ev].get(clave) for d in por_evento]
        if any(v is None for v in valores):
            continue
        total += 1
        mejor = max(valores) if mas_es_mejor else min(valores)
        fecha = h._fecha_bonita(por_evento[0][ev]["fecha"])
        if valores.count(mejor) == 1:
            i = valores.index(mejor)
            victorias[i] += 1
            tira.append((i, f"{fecha} · {nombres[i]} ({_val(mejor, clave)})"))
        else:
            empates += 1
            tira.append((None, f"{fecha} · empate ({_val(mejor, clave)})"))
    if not total:
        return ""
    max_v = max(victorias)
    tarjetas = ""
    for n, c, v in zip(nombres, colores, victorias):
        pct = round(100 * v / total)
        top = v == max_v and victorias.count(max_v) == 1
        tarjetas += (
            f'<div style="--c:{c};flex:1 1 200px;min-width:200px;padding:.55rem .8rem;border-radius:14px;color:{paleta["texto"]};'
            f'background:{paleta["fondo"]};border:{"2px" if top else "1px"} solid {c if top else paleta["borde"]}">'
            f'<div style="font-weight:800;color:{c};font-size:.95rem">{"👑 " if top else ""}{esc(n)}</div>'
            f'<div style="font-size:1.45rem;font-weight:800;line-height:1.2">{v}<span style="font-size:.85rem;font-weight:600;color:{paleta["suave"]}"> de {total} partidos · {pct}%</span></div>'
            f'<div style="height:8px;border-radius:99px;background:{paleta["pista"]};overflow:hidden;margin-top:4px">'
            f'<i style="display:block;height:100%;width:{pct}%;background:{c}"></i></div></div>')
    puntos = "".join(
        f'<span title="{esc(t)}" style="width:14px;height:14px;border-radius:50%;display:inline-block;'
        f'background:{colores[i] if i is not None else "#94a3b8"}"></span>' for i, t in tira)
    nota_emp = f" · {empates} empate{'s' if empates != 1 else ''} (no cuentan)" if empates else ""
    return (f'<div style="border-radius:16px;padding:.7rem .8rem;background:{paleta["cab"]};border:1px solid {paleta["borde"]};color:{paleta["texto"]}">'
            f'<div style="font-weight:800;font-size:.95rem;margin-bottom:.45rem">🏆 Quién lidera {esc(NOMBRES[clave].lower())} en el mismo partido'
            f'<span style="font-weight:600;font-size:.74rem;color:{paleta["suave"]}"> · {total} partidos en que jugaron todos{nota_emp}</span></div>'
            f'<div style="display:flex;gap:10px;flex-wrap:wrap">{tarjetas}</div>'
            f'<div style="margin-top:.55rem;display:flex;align-items:center;gap:5px;flex-wrap:wrap">'
            f'<span style="font-size:.7rem;color:{paleta["suave"]};margin-right:4px">Partido a partido (más reciente → más antiguo):</span>{puntos}</div></div>')


def _apagar_rivales_modal():
    st.session_state["jug_rivales_modal"] = False


def _apagar_juntos_modal():
    st.session_state["jug_juntos_modal"] = False


def _filtrar_historiales(historiales, ventana, juntos, rivales):
    """Aplica «solo compañeros» / «solo rivales» y recorta a los últimos `ventana` partidos (0 = todos)."""
    if juntos:
        historiales = _solo_companeros(historiales)
    elif rivales:
        historiales = _solo_rivales(historiales)
    return [hist if ventana == 0 else hist[:ventana] for hist in historiales]


def _sincronizar_elegidos_modal():
    """Lo que se elige en el buscador del diálogo queda también elegido en la pantalla principal."""
    st.session_state["jug_elegidos"] = list(st.session_state.get("jug_elegidos_modal", []))


def _contenido_tabla_grande(por_id, temporadas, playoffs, clave_inicial):
    """Contenido del diálogo: buscador de jugadores, selector de estadística, filtros, tarjetas y la tabla grande.

    Como el diálogo es un fragmento, cambiar jugadores o filtros solo lo recalcula a él: la ventana no se cierra.
    Los jugadores se cargan aquí mismo, así se pueden cambiar sin salir y volver a entrar."""
    claves = _claves()

    # ---- Buscador de jugadores (el mismo de la pantalla principal; arranca con lo que ya estaba elegido) ----
    elegidos = st.multiselect("Jugadores (hasta 4)", _orden_favoritos(por_id), max_selections=4, key="jug_elegidos_modal",
                              format_func=_fmt_jugador(por_id),
                              placeholder="🔎 Escribe un nombre para agregar o cambiar jugadores...",
                              on_change=_sincronizar_elegidos_modal)
    if not elegidos:
        st.info("Elige al menos un jugador para ver su tabla.")
        return
    with st.spinner("Cargando partidos..."):
        historiales = [_historial_ordenado(i, temporadas, playoffs) for i in elegidos]
    nombres = [por_id[i]["nombre"] for i in elegidos]
    equipos = [por_id[i]["equipo"] for i in elegidos]
    ids = list(elegidos)
    st.markdown(_css_grande(PALETA_OSCURA if _es_oscuro() else PALETA_CLARA, len(nombres)), unsafe_allow_html=True)   # aparte del HTML: la app oculta los bloques que traen <style>

    if hasattr(st, "pills"):
        sel = st.pills("Estadística", claves, selection_mode="single", key="jug_lado_modal",
                       format_func=lambda c: NOMBRES[c], label_visibility="collapsed")
    else:
        sel = st.selectbox("Estadística", claves, key="jug_lado_modal", format_func=lambda c: NOMBRES[c])
    clave = sel or clave_inicial

    # ---- Filtros de partidos (los mismos de la pantalla principal; aquí arrancan con lo que ya estaba elegido) ----
    st.session_state.setdefault("jug_ventana_modal", 10)
    st.session_state.setdefault("jug_juntos_modal", False)
    st.session_state.setdefault("jug_rivales_modal", False)
    ventana = st.radio("Partidos a promediar", VENTANAS, horizontal=True, key="jug_ventana_modal",
                       format_func=lambda v: "Todos" if v == 0 else f"Últimos {v}")
    cj, cr = st.columns(2)
    juntos = cj.toggle("🤝 Solo jugando juntos", key="jug_juntos_modal", on_change=_apagar_rivales_modal,
                       help="Cuenta solo los partidos en que todos los jugadores elegidos jugaron y fueron compañeros de equipo.")
    rivales = cr.toggle("⚔️ Solo enfrentamientos entre rivales", key="jug_rivales_modal", on_change=_apagar_juntos_modal,
                        help="Cuenta solo los partidos en que los jugadores elegidos se enfrentaron (jugaron en equipos rivales). "
                             "No se combina con «Solo jugando juntos».")
    rivales = rivales and not juntos
    mismo = st.toggle("🏆 Quién se lleva cada partido (mismo partido)", key="jug_mismo_modal",
                      help="Usa solo los partidos oficiales (liga regular y playoffs) en que todos los jugadores elegidos jugaron el mismo "
                           "partido, y cuenta cuántas veces cada uno hizo más de la estadística elegida (por ejemplo, Puntos). "
                           "Elige «Todos» en «Partidos a promediar» para ver todo el historial.")
    if not any(historiales):
        st.warning("Sin partidos en las temporadas elegidas para: " + ", ".join(nombres) + ".")
        return

    # ---- Filtro por equipo rival: «¿quién rinde más contra Toronto?» (la lista incluye los 30 equipos) ----
    siglas = set(EQUIPOS_NBA) | {str(g.get("rival")).upper() for hist in historiales for g in hist if g.get("rival")}
    opciones_eq = [""] + sorted(siglas, key=lambda a: EQUIPOS_NBA.get(a, a))
    rival_eq = st.selectbox("🏀 Solo partidos contra el equipo...", opciones_eq, key="jug_vs_equipo_modal",
                            format_func=lambda a: "Todos los equipos" if not a else f"{EQUIPOS_NBA.get(a, a)} ({a})",
                            help="Compara a los jugadores usando solo sus partidos contra ese equipo (por ejemplo, el rival de hoy). "
                                 "Si salen pocos partidos, agrega más temporadas en la pantalla principal.")
    historiales_f = _solo_contra(historiales, rival_eq)
    if mismo:
        historiales_f = _solo_mismo_partido(historiales_f)
    if rival_eq and not any(historiales_f):
        st.warning(f"Ninguno de los jugadores elegidos jugó contra {EQUIPOS_NBA.get(rival_eq, rival_eq)} en las temporadas elegidas. "
                   "Prueba agregando más temporadas.")
        return
    series = _filtrar_historiales(historiales_f, ventana, juntos, rivales)
    if not any(series):
        st.warning("Con estos filtros no hay partidos en común. Prueba con otra combinación o desactiva un filtro.")
        return

    colores = [COLORES[i % len(COLORES)] for i in range(len(nombres))]
    mas_es_mejor = clave != "TO"
    cab = (f'<div class="tg-cab"><p>Fila 1 = último partido · ▲ mejor de la fila · gris = empate · ★ mejor partido del jugador</p>'
           f'<span class="tg-pastilla">{max(len(s) for s in series)} partidos{f" · vs {html.escape(rival_eq)}" if rival_eq else ""}</span></div>')
    ganadores = (_ganadores_partido_html(nombres, series, clave, colores, mas_es_mejor, PALETA_OSCURA if _es_oscuro() else PALETA_CLARA)
                 if mismo else "")
    heroes = _heroes_html(nombres, series, clave, colores, ids, equipos, mas_es_mejor)
    tabla = _tabla_grande_html(nombres, series, clave, colores, ids, equipos, mas_es_mejor)
    # todo en UN solo bloque: así nada se monta encima de otra cosa
    st.markdown(f'<div class="tg-wrap">{cab}{ganadores}{heroes}{tabla}</div>', unsafe_allow_html=True)


_dialogo = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
if _dialogo:
    _abrir_tabla_grande = _dialogo("📊 Tabla partido a partido", width="large")(_contenido_tabla_grande)
else:   # Streamlit antiguo sin diálogos: se muestra en un recuadro
    def _abrir_tabla_grande(*args):
        with st.container(border=True):
            _contenido_tabla_grande(*args)


# ---------------------------------------------------------------------------
# Pantalla
# ---------------------------------------------------------------------------
def _etiqueta_temporada(t):
    return f"{t - 1}-{str(t)[2:]}"


def _sincronizar_desde_pestana(clave):
    """Lo que se elige en el buscador de una pestaña queda elegido también arriba (y en las demás pestañas)."""
    st.session_state["jug_elegidos"] = list(st.session_state.get(clave, []))


def _cambiar_jugador_pestana(clave, idx):
    """Buscador de la tarjeta (máximo 1 jugador): cambia o quita SOLO al jugador de esa posición en la lista de arriba."""
    lista = list(st.session_state.get("jug_elegidos", []))
    valor = st.session_state.get(clave)
    nuevo = [valor] if valor else []
    if not nuevo:
        if idx < len(lista):
            del lista[idx]
    elif nuevo[-1] not in lista or (idx < len(lista) and lista[idx] == nuevo[-1]):
        if idx < len(lista):
            lista[idx] = nuevo[-1]
        else:
            lista.append(nuevo[-1])
    st.session_state["jug_elegidos"] = lista


def _buscador_rapido(por_id, elegidos, nombre, idx=None):
    """Buscador de jugadores DENTRO de una pestaña, para cambiar o agregar jugadores sin subir al inicio de la página.

    Es el mismo selector de arriba: siempre muestra los jugadores actuales y cualquier cambio se refleja en todos lados."""
    clave = f"jug_busca_{nombre}"
    if idx is not None:
        # Buscador de la tarjeta: UN solo jugador (el de esta posición); para agregar más se usa el selector de arriba
        # Es un selector simple (no de varios): escribes, eliges y reemplaza al jugador; no hay mensaje de límite
        st.session_state[clave] = elegidos[idx] if idx < len(elegidos) and elegidos[idx] in por_id else None
        try:
            st.selectbox("Buscar o cambiar jugador", _orden_favoritos(por_id), index=None, key=clave,
                         format_func=_fmt_jugador(por_id), placeholder="🔎 Escribe un nombre para buscar un jugador...",
                         label_visibility="collapsed", on_change=_cambiar_jugador_pestana, args=(clave, idx))
        except TypeError:   # Streamlit antiguo sin index=None / placeholder
            st.selectbox("Buscar o cambiar jugador", _orden_favoritos(por_id), key=clave,
                         format_func=_fmt_jugador(por_id), label_visibility="collapsed",
                         on_change=_cambiar_jugador_pestana, args=(clave, idx))
        return
    st.session_state[clave] = [i for i in elegidos if i in por_id]   # siempre alineado con el selector principal
    st.multiselect("Buscar o cambiar jugadores", _orden_favoritos(por_id), max_selections=4, key=clave,
                   format_func=_fmt_jugador(por_id),
                   placeholder="🔎 Escribe un nombre para buscar, agregar o cambiar jugadores...",
                   label_visibility="collapsed", on_change=_sincronizar_desde_pestana, args=(clave,))


# ---------------------------------------------------------------------------
# Favoritos: mini carpeta de jugadores guardados para ponerlos rápido en el buscador
# ---------------------------------------------------------------------------
ARCHIVO_FAVORITOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favoritos_jugadores.json")


def _leer_favoritos():
    """Ids (como texto) guardados en el archivo; lista vacía si no existe o no se puede leer."""
    try:
        with open(ARCHIVO_FAVORITOS, encoding="utf-8") as f:
            datos = json.load(f)
        return [str(i) for i in datos] if isinstance(datos, list) else []
    except (OSError, ValueError):
        return []


def _favoritos_actuales():
    if "jug_favoritos" not in st.session_state:
        st.session_state["jug_favoritos"] = _leer_favoritos()
    return list(st.session_state["jug_favoritos"])


def _guardar_favoritos(ids):
    """Guarda en la sesión y en el archivo (si el archivo no se puede escribir, igual quedan durante la sesión)."""
    st.session_state["jug_favoritos"] = list(ids)
    try:
        with open(ARCHIVO_FAVORITOS, "w", encoding="utf-8") as f:
            json.dump(list(ids), f, ensure_ascii=False)
        st.session_state.pop("jug_fav_error", None)
    except OSError:
        st.session_state["jug_fav_error"] = True


def _orden_favoritos(por_id):
    """Ids de todos los jugadores: primero los favoritos y luego el resto, cada grupo en orden alfabético (A→Z)."""
    favs = set(_favoritos_actuales())
    return sorted(h.ordenar_abc(por_id), key=lambda i: str(i) not in favs)   # el orden es estable: conserva el A→Z


def _fmt_jugador(por_id):
    """Nombre para los buscadores: los favoritos llevan una ⭐ delante."""
    favs = set(_favoritos_actuales())
    return lambda i: f"{'⭐ ' if str(i) in favs else ''}{por_id[i]['nombre']} ({por_id[i]['equipo']})"


def _fav_poner_en_buscador(pid):
    actuales = list(st.session_state.get("jug_elegidos", []))
    if pid in actuales:
        return
    if len(actuales) >= 4:
        st.session_state["jug_fav_aviso"] = "El buscador ya tiene 4 jugadores. Quita uno para poner otro."
        return
    st.session_state.pop("jug_fav_aviso", None)
    st.session_state["jug_elegidos"] = actuales + [pid]


def _fav_agregar(ids):
    favs = _favoritos_actuales()
    for i in ids:
        if str(i) not in favs:
            favs.append(str(i))
    _guardar_favoritos(favs)


def _fav_guardar_elegidos():
    _fav_agregar(st.session_state.get("jug_elegidos", []))


def _fav_guardar_nuevos():
    _fav_agregar(st.session_state.get("jug_fav_nuevos", []))
    st.session_state["jug_fav_nuevos"] = []


def _fav_quitar():
    quitar = {str(i) for i in st.session_state.get("jug_fav_quitar", [])}
    _guardar_favoritos([f for f in _favoritos_actuales() if f not in quitar])
    st.session_state["jug_fav_quitar"] = []


# Fondo del círculo del rostro: luz índigo claro arriba que baja a índigo vivo; contrasta con pieles claras y oscuras
_FONDO_ROSTRO = "radial-gradient(circle at 50% 28%,#e0e7ff 0%,#a5b4fc 42%,#6366f1 100%)"


def _css_rostros_favoritos(pids):
    """Una regla por favorito: su rostro (foto de ESPN) en un círculo, a la izquierda del botón. Un botón de Streamlit no
    admite imágenes, así que la foto va como ::before del botón, identificado por la clave del botón."""
    reglas = []
    for pid in pids:
        pid = str(pid)
        if not re.fullmatch(r"\d+", pid):
            continue
        reglas.append(
            f'.st-key-jug_fav_btn_{pid} button::before{{background-image:url("{_foto(pid)}"),{_FONDO_ROSTRO}}}')
    if not reglas:
        return ""
    return ("<style>"
            '[class*="st-key-jug_fav_btn_"] button{position:relative;min-height:58px !important;padding-left:66px !important;'
            'transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease}'
            '[class*="st-key-jug_fav_btn_"] button:hover:not(:disabled){transform:translateY(-2px);'
            'box-shadow:0 10px 22px -12px rgba(30,41,90,.4)}'
            '[class*="st-key-jug_fav_btn_"] button::before{content:"";position:absolute;left:9px;top:50%;width:46px;height:46px;'
            'margin-top:-23px;border-radius:50%;background-color:#6366f1;background-repeat:no-repeat;'
            'background-size:190% auto,100% 100%;background-position:50% 2%,center;'
            'box-shadow:0 0 0 2px rgba(255,255,255,.92),0 6px 14px rgba(15,23,42,.45)}'
            + "".join(reglas) + "</style>")


_CAJA_FAV = "jug_fav_caja"
_CSS_CAJA_FAV_EXTRA = """
<style>
/* El desplegable queda transparente: el fondo oscuro lo pone la caja (el mismo de la tarjeta de línea y tendencia) */
.st-key-__F__.st-key-__F__ [data-testid="stExpander"] details { background: transparent !important; border: 0 !important;
  border-radius: 0 !important; box-shadow: none !important; }
.st-key-__F__.st-key-__F__ [data-testid="stExpander"], .st-key-__F__.st-key-__F__ [data-testid="stExpander"] details > *,
.st-key-__F__.st-key-__F__ [data-testid="stExpander"] summary, .st-key-__F__.st-key-__F__ [data-testid="stExpander"] summary:hover,
.st-key-__F__.st-key-__F__ [data-testid="stExpander"] summary:focus, .st-key-__F__.st-key-__F__ [data-testid="stExpanderDetails"] {
  background: transparent !important; background-color: transparent !important; background-image: none !important;
  border: 0 !important; box-shadow: none !important; }
.st-key-__F__.st-key-__F__ [data-testid="stExpander"] summary { padding-left: 0 !important; border-bottom: 1px solid rgba(255,255,255,.10) !important; }
.st-key-__F__.st-key-__F__ [data-testid="stExpander"] summary,
.st-key-__F__.st-key-__F__ [data-testid="stExpander"] summary * { color: #eef0ff !important; font-weight: 700; }
.st-key-__F__.st-key-__F__ [data-testid="stExpander"] summary svg { fill: rgba(255,255,255,.75) !important; color: rgba(255,255,255,.75) !important; }
.st-key-__F__ [data-testid="stCaptionContainer"], .st-key-__F__ [data-testid="stCaptionContainer"] * { color: rgba(255,255,255,.6) !important; }
/* botones: cristal oscuro, como los controles de la tarjeta */
.st-key-__F__.st-key-__F__ button { background: linear-gradient(135deg, rgba(99,102,241,.20), rgba(255,255,255,.04)) !important;
  border: 1px solid rgba(165,180,252,.22) !important;
  color: #eef0ff !important; border-radius: 14px !important; }
.st-key-__F__.st-key-__F__ button * { color: #eef0ff !important; }
.st-key-__F__.st-key-__F__ button:hover:not(:disabled) { background: linear-gradient(135deg, rgba(99,102,241,.38), rgba(139,92,246,.18)) !important;
  border-color: rgba(165,180,252,.7) !important;
  box-shadow: 0 10px 22px -12px rgba(0,0,0,.6) !important; }
.st-key-__F__.st-key-__F__ button:disabled { opacity: .4 !important; }
</style>
"""


def _carpeta_favoritos(por_id, elegidos):
    """«Mis favoritos» dentro de una caja con el mismo fondo oscuro, controles y estilo que la tarjeta de línea y tendencia."""
    st.markdown(ficha_linea._CSS_CAJA.replace("__C__", f"st-key-{_CAJA_FAV}")
                + _CSS_CAJA_FAV_EXTRA.replace("__F__", _CAJA_FAV), unsafe_allow_html=True)
    try:
        caja = st.container(key=_CAJA_FAV)
    except TypeError:   # Streamlit antiguo sin key en container: queda sin fondo, pero funciona igual
        caja = st.container()
    with caja:
        _carpeta_favoritos_interna(por_id, elegidos)


def _carpeta_favoritos_interna(por_id, elegidos):
    """Expander «Mis favoritos»: toca un jugador para ponerlo en el buscador; también guarda y quita favoritos."""
    claves = {str(k): k for k in por_id}
    favs = [f for f in _favoritos_actuales() if f in claves]
    etiqueta = lambda i: f"{por_id[i]['nombre']} ({por_id[i]['equipo']})"
    with st.expander(f"⭐ Mis favoritos ({len(favs)})"):
        if favs:
            st.caption("Toca un jugador para ponerlo en el buscador (hasta 4).")
            st.markdown(_css_rostros_favoritos([claves[f] for f in favs]), unsafe_allow_html=True)
            cols = st.columns(4)
            for k, f in enumerate(favs):
                pid = claves[f]
                cols[k % 4].button(("✅ " if pid in elegidos else "") + etiqueta(pid), key=f"jug_fav_btn_{f}",
                                   on_click=_fav_poner_en_buscador, args=(pid,), use_container_width=True)
        else:
            st.caption("Todavía no tienes favoritos. Elige jugadores en el buscador y guárdalos aquí, o agrégalos desde la lista de abajo.")
        if st.session_state.get("jug_fav_aviso"):
            st.warning(st.session_state["jug_fav_aviso"])
        st.button("⭐ Guardar los jugadores elegidos en favoritos", key="jug_fav_guardar_elegidos", on_click=_fav_guardar_elegidos,
                  disabled=not elegidos)
        resto = [i for i in por_id if str(i) not in favs]
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        c1.multiselect("Agregar otros jugadores a favoritos", resto, key="jug_fav_nuevos", format_func=etiqueta,
                       placeholder="Escribe un nombre para buscar...")
        c2.button("⭐ Guardar", key="jug_fav_guardar_nuevos", on_click=_fav_guardar_nuevos, use_container_width=True)
        if favs:
            c3, c4 = st.columns([3, 1], vertical_alignment="bottom")
            c3.multiselect("Quitar de favoritos", [claves[f] for f in favs], key="jug_fav_quitar", format_func=etiqueta,
                           placeholder="Elige los que quieras quitar...")
            c4.button("🗑 Quitar", key="jug_fav_quitar_btn", on_click=_fav_quitar, use_container_width=True)
        if st.session_state.get("jug_fav_error"):
            st.caption("⚠️ No se pudo escribir el archivo de favoritos: durarán solo mientras esta sesión esté abierta.")


# ---------------------------------------------------------------------------
# Autoanálisis y simulación del próximo partido
# ---------------------------------------------------------------------------
SIM_STATS = [("PTS", "Puntos"), ("REB", "Rebotes"), ("AST", "Asistencias"), ("REB+AST", "REB+AST"), ("PTS+REB", "PTS+REB"), ("PTS+AST", "PTS+AST"), ("P+R+A", "P+R+A"),
             ("3PM", "Triples"), ("STL", "Robos"), ("BLK", "Tapones"), ("MIN", "Minutos")]
SIM_DRAWS = 10000      # partidos simulados por estadística
CLAVES_RIVAL_DIEZMADO = ("PTS", "REB", "AST", "REB+AST", "PTS+REB", "PTS+AST", "P+R+A", "3PM")   # donde un rival con bajas pesa (ajuste estimado)

CSS_SIM = """
<style>
.sm-wrap { border-radius: 24px; padding: 1.2rem 1.4rem 1.1rem; color: #fff; margin: .8rem 0 1rem;
  background: linear-gradient(160deg, #0f172a 0%, #1e1b4b 100%); border: 1px solid rgba(255,255,255,.10); box-shadow: 0 24px 60px rgba(15,23,42,.35); }
.sm-t { font-size: 1.3rem; font-weight: 800; letter-spacing: -.01em; }
.sm-s { margin-top: .15rem; font-size: .84rem; color: rgba(255,255,255,.62); }
.sm-banner { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin: .9rem 0 .8rem;
  padding: .7rem .95rem; border-radius: 16px; background: rgba(99,102,241,.16); border: 1px solid rgba(165,180,252,.38); }
.sm-banner b { font-size: 1rem; }
.sm-banner span { font-size: .78rem; color: rgba(255,255,255,.7); }
.sm-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 10px; }
.sm-c { padding: .75rem .85rem .7rem; border-radius: 16px; background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.10);
  transition: transform .2s ease, border-color .2s ease; }
.sm-c:hover { transform: translateY(-3px); border-color: rgba(165,180,252,.55); }
.sm-c.sel { border-color: #a5b4fc; box-shadow: 0 0 0 2px rgba(165,180,252,.25); }
.sm-c small { display: block; font-size: .62rem; font-weight: 700; letter-spacing: .13em; text-transform: uppercase; color: rgba(255,255,255,.55); }
.sm-c b { display: block; margin-top: .1rem; font-size: 2.1rem; font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums; }
.sm-rango { position: relative; height: 8px; margin: .55rem 0 .25rem; border-radius: 99px; background: rgba(255,255,255,.12); }
.sm-rango i { position: absolute; top: 0; bottom: 0; border-radius: 99px; background: linear-gradient(90deg, #6366f1, #a78bfa); }
.sm-rango em { position: absolute; top: -3px; width: 3px; height: 14px; border-radius: 2px; background: #fff; }
.sm-pie { display: flex; justify-content: space-between; font-size: .68rem; color: rgba(255,255,255,.55); }
.sm-chip { display: inline-block; margin-top: .45rem; padding: .08rem .55rem; border-radius: 999px; font-size: .7rem; font-weight: 700;
  background: rgba(148,163,184,.18); color: #cbd5e1; }
.sm-chip.v { background: rgba(34,197,94,.18); color: #86efac; } .sm-chip.r { background: rgba(239,68,68,.18); color: #fca5a5; }
.sm-ten { margin-top: .35rem; font-size: .72rem; color: rgba(255,255,255,.62); }
.sm-ten .sube { color: #86efac; } .sm-ten .baja { color: #fca5a5; }
.sm-nota { margin: .9rem 0 0; padding: 0; list-style: none; display: grid; gap: .35rem; }
.sm-nota li { font-size: .84rem; color: rgba(255,255,255,.82); padding-left: 1.2rem; position: relative; }
.sm-nota li::before { content: "▸"; position: absolute; left: 0; color: #a5b4fc; }
.sm-sec { margin-top: 1rem; font-size: .7rem; font-weight: 800; letter-spacing: .13em; text-transform: uppercase; color: rgba(255,255,255,.55); }
.sm-les { display: flex; flex-wrap: wrap; gap: 6px; margin-top: .4rem; }
.sm-les span { padding: .12rem .6rem; border-radius: 999px; font-size: .72rem; font-weight: 600; background: rgba(148,163,184,.16); color: #cbd5e1; }
.sm-les span.out { background: rgba(239,68,68,.18); color: #fca5a5; } .sm-les span.dud { background: rgba(234,179,8,.18); color: #fde68a; }
.sm-les span.rot { box-shadow: inset 0 0 0 1px rgba(165,180,252,.6); }
.sm-tag { display: inline-block; margin: .5rem .35rem 0 0; padding: .1rem .6rem; border-radius: 999px; font-size: .72rem; font-weight: 700;
  background: rgba(99,102,241,.2); color: #c7d2fe; }
.sm-tag.v { background: rgba(34,197,94,.18); color: #86efac; }
.sm-est { color: rgba(253,230,138,.9); }
.sm-aviso { margin-top: .8rem; font-size: .7rem; color: rgba(255,255,255,.5); }
</style>
"""


@st.cache_data(ttl=1800, show_spinner=False)
def _proximo_partido(equipo):
    """Próximo partido sin jugar del equipo según el calendario de ESPN: {rival, rival_nombre, sede, fecha, evento} o None."""
    try:
        equipos = h._get_json(h.BASE + "/teams")["sports"][0]["leagues"][0]["teams"]
        tid = next(str(t["team"]["id"]) for t in equipos if t["team"].get("abbreviation", "").upper() == str(equipo).upper())
        eventos = h._get_json(f"{h.BASE}/teams/{tid}/schedule").get("events", [])
    except Exception:  # noqa: BLE001 - sin calendario seguimos sin rival automático
        return None
    pendientes = []
    for ev in eventos:
        try:
            comp = ev["competitions"][0]
            if comp.get("status", {}).get("type", {}).get("completed"):
                continue
            mio = next(c for c in comp["competitors"] if str(c["team"]["id"]) == tid)
            rival = next(c for c in comp["competitors"] if str(c["team"]["id"]) != tid)
            pendientes.append((str(ev.get("date", "")), {
                "rival": str(rival["team"].get("abbreviation", "")).upper(),
                "rival_nombre": rival["team"].get("displayName", ""),
                "sede": "Local" if mio.get("homeAway") == "home" else "Visita",
                "fecha": str(ev.get("date", ""))[:10], "evento": str(ev.get("id", ""))}))
        except (KeyError, StopIteration, IndexError):
            continue
    return min(pendientes, key=lambda x: x[0])[1] if pendientes else None


def _contexto_rival(equipo, rival_elegido):
    """Rival y sede de la simulación: el equipo elegido en «Contra el equipo» o, si no hay, el próximo rival del calendario."""
    prox = _proximo_partido(equipo)
    if rival_elegido:
        coincide = prox is not None and prox["rival"] == rival_elegido.upper()
        return {"rival": rival_elegido.upper(), "sede": prox["sede"] if coincide else None,
                "fecha": prox["fecha"] if coincide else None, "evento": prox["evento"] if coincide else "", "origen": "elegido"}
    if prox:
        return {**prox, "origen": "calendario"}
    return {"rival": "", "sede": None, "fecha": None, "evento": "", "origen": None}


# ----- Lesiones, titulares y descanso -----
def _p_juega(estado, texto):
    """Probabilidad aproximada de que juegue según el estado del reporte de lesiones (Out = 0)."""
    e, t = str(estado or "").lower(), str(texto or "").lower()
    if e.startswith("out") or any(f in t for f in ("out for the season", "ruled out", "will not play", "will miss")):
        return 0.0
    if "doubtful" in e or "doubtful" in t:
        return 0.15
    if "probable" in e or "probable" in t:
        return 0.85
    return 0.5   # questionable / day-to-day / sin dato


@st.cache_data(ttl=1200, show_spinner=False)
def _lesiones():
    """Reporte de lesiones de ESPN: {sigla: [{id, nombre, estado, detalle, p_juega}]}; {} si no se puede descargar."""
    try:
        data = h._get_json(h.BASE + "/injuries")
        equipos = h._get_json(h.BASE + "/teams")["sports"][0]["leagues"][0]["teams"]
    except Exception:  # noqa: BLE001
        return {}
    por_id = {str(t["team"]["id"]): t["team"].get("abbreviation", "").upper() for t in equipos}
    por_nombre = {t["team"].get("displayName", ""): t["team"].get("abbreviation", "").upper() for t in equipos}
    res = {}
    for eq in data.get("injuries", []):
        sigla = por_id.get(str(eq.get("id"))) or por_nombre.get(eq.get("displayName", ""), "")
        for it in eq.get("injuries", []):
            a = it.get("athlete") or {}
            if not a.get("id") or not sigla:
                continue
            estado = it.get("status", "")
            texto = f"{it.get('shortComment') or ''} {it.get('longComment') or ''}"
            detalle = (it.get("details") or {}).get("type") or (it.get("type") or {}).get("description") or ""
            res.setdefault(sigla, []).append({"id": str(a["id"]), "nombre": a.get("displayName") or a.get("fullName", "?"),
                                              "estado": estado, "detalle": detalle, "p_juega": _p_juega(estado, texto)})
    return res


@st.cache_data(ttl=120, show_spinner=False)
def _titulares_confirmados(evento):
    """Ids de los titulares del partido si ESPN ya los publicó (suele ser solo al acercarse o empezar el partido); si no, vacío."""
    if not evento:
        return set()
    try:
        data = h._get_json(f"{h.BASE}/summary?event={evento}")
    except Exception:  # noqa: BLE001
        return set()
    ids = set()
    for r in data.get("rosters", []):
        for j in r.get("roster", []):
            if j.get("starter"):
                ids.add(str((j.get("athlete") or {}).get("id")))
    for t in (data.get("boxscore") or {}).get("players", []):
        for grupo in t.get("statistics", []):
            for a in grupo.get("athletes", []):
                if a.get("starter"):
                    ids.add(str((a.get("athlete") or {}).get("id")))
    return ids if len(ids) >= 5 else set()


def _flags_ausencia(hist, hist_tm):
    """Para cada uno de los últimos 80 partidos del jugador: True = su compañero NO jugó, False = jugó, None = no se sabe.

    Solo cuenta desde el primer partido que jugaron juntos (así no se confunde con partidos de antes de que llegara).
    Devuelve None si jugaron juntos menos de 5 veces."""
    por_ev = {g["event"]: g for g in hist_tm}
    juntos = [g["fecha"] for g in hist if g["event"] in por_ev and por_ev[g["event"]].get("rival_id") == g.get("rival_id")]
    if len(juntos) < 5:
        return None
    desde = min(juntos)
    flags = []
    for g in hist[:80]:
        if g["fecha"] < desde:
            flags.append(None)
        elif g["event"] in por_ev:
            flags.append(False if por_ev[g["event"]].get("rival_id") == g.get("rival_id") else None)
        else:
            flags.append(True)
    return flags


def _fecha_iso(texto):
    try:
        return date.fromisoformat(str(texto)[:10])
    except ValueError:
        return None


def _flags_b2b(hist):
    """True = ese partido fue en back-to-back (el día siguiente al anterior), False = con descanso, None = sin partido previo."""
    flags = []
    for i, g in enumerate(hist[:80]):
        a, b = _fecha_iso(g.get("fecha")), (_fecha_iso(hist[i + 1].get("fecha")) if i + 1 < len(hist) else None)
        flags.append(None if not a or not b else (a - b).days == 1)
    return flags


def _contexto_partido(pid, equipo, hist, ctx, temporadas, playoffs):
    """Todo lo que rodea al partido: lesiones propias y del rival, compañeros ausentes con su efecto, rival con bajas, descanso y rol."""
    les = _lesiones()
    mios = [x for x in les.get(equipo, []) if x["id"] != str(pid)][:8]
    del_rival = les.get(ctx["rival"], [])[:8] if ctx["rival"] else []
    companeros, peso_rival, filas_p, filas_r, explicaciones = [], 0.0, [], [], []
    for x in mios:
        hist_tm = _historial_ordenado(x["id"], temporadas, playoffs)
        mins = [g["MIN"] for g in hist_tm[:15] if g.get("MIN") is not None]
        prom = float(np.mean(mins)) if len(mins) >= 5 else 0.0
        fila = {**x, "min": prom, "rot": prom >= 12}
        filas_p.append(fila)
        if prom < 12:
            continue
        flags = _flags_ausencia(hist, hist_tm)
        if flags is None:
            continue
        companeros.append({"nombre": x["nombre"], "p_juega": x["p_juega"], "flags": flags})
        sin = [g for g, f in zip(hist, flags) if f is True]
        con = [g for g, f in zip(hist, flags) if f is False]
        if len(sin) >= 3 and len(con) >= 5:
            m = lambda lst, c: float(np.mean([g[c] for g in lst if g.get(c) is not None] or [0]))
            explicaciones.append(f"Sin {x['nombre']} ({x['estado'] or 'en el reporte'}) promedia {h._fmt(m(sin, 'PTS'))} pts y "
                                 f"{h._fmt(m(sin, 'MIN'))} min en {len(sin)} partidos; con él, {h._fmt(m(con, 'PTS'))} pts y {h._fmt(m(con, 'MIN'))} min.")
    for x in del_rival:
        hist_r = _historial_ordenado(x["id"], temporadas, playoffs)
        mins = [g["MIN"] for g in hist_r[:15] if g.get("MIN") is not None]
        prom = float(np.mean(mins)) if len(mins) >= 5 else 0.0
        filas_r.append({**x, "min": prom, "rot": prom >= 20})
        if prom >= 20:
            peso_rival += (1 - x["p_juega"]) * min(prom, 36.0) / 30.0
    factor_rival = 1.0 + min(0.06, 0.02 * peso_rival)

    b2b_hoy, fecha_prox = None, _fecha_iso(ctx.get("fecha"))
    if fecha_prox and hist and _fecha_iso(hist[0].get("fecha")):
        dias = (fecha_prox - _fecha_iso(hist[0]["fecha"])).days
        b2b_hoy = True if dias == 1 else (False if dias > 1 else None)
    fb = _flags_b2b(hist)
    b2b = [g for g, f in zip(hist, fb) if f is True]
    desc = [g for g, f in zip(hist, fb) if f is False]
    if b2b_hoy is not None and len(b2b) >= 4 and len(desc) >= 8:
        m = lambda lst, c: float(np.mean([g[c] for g in lst if g.get(c) is not None] or [0]))
        explicaciones.append(f"{'Juega en back-to-back' if b2b_hoy else 'Llega con descanso'}: en back-to-back promedia {h._fmt(m(b2b, 'PTS'))} pts y "
                             f"{h._fmt(m(b2b, 'MIN'))} min ({len(b2b)} partidos); con descanso, {h._fmt(m(desc, 'PTS'))} pts y {h._fmt(m(desc, 'MIN'))} min.")

    mins10 = [g["MIN"] for g in hist[:10] if g.get("MIN") is not None]
    prom_min = float(np.mean(mins10)) if mins10 else 0.0
    rol = "titular probable" if prom_min >= 28 else ("rotación" if prom_min >= 18 else "banca")
    conf = _titulares_confirmados(ctx.get("evento"))
    titular = (str(pid) in conf) if conf else None
    return {"propios": filas_p, "rival": filas_r, "companeros": companeros, "factor_rival": factor_rival, "b2b_hoy": b2b_hoy,
            "explicaciones": explicaciones, "rol": rol, "prom_min": prom_min, "titular": titular}


def simular_estadistica(hist, clave, rival="", sede=None, semilla=0, partidos=SIM_DRAWS, companeros=None, b2b_hoy=None, factor_rival=1.0):
    """Simula `partidos` veces el próximo partido de un jugador en una estadística.

    hist         partidos del más reciente al más antiguo (con REB+AST incluida).
    Proyección = 60 % forma reciente (últimos 10, los más nuevos pesan más) + 40 % media de hasta 40 partidos,
    más un ajuste por el rival y por la sede (local/visita) que pesa más cuantos más partidos haya de cada tipo.
    La dispersión sale de cómo varió el jugador (se remuestrean sus propios partidos).
    companeros   [{nombre, p_juega, flags}]: en cada partido simulado el compañero juega o no según su probabilidad, y se suma
                 cuánto cambia el jugador sin él (solo la parte que su forma reciente aún no refleja).
    b2b_hoy      True/False si el partido es (o no) en back-to-back; ajusta con lo que rinde el jugador en back-to-back.
    factor_rival multiplicador estimado (>1) si el rival tiene bajas importantes (solo en CLAVES_RIVAL_DIEZMADO).
    Devuelve None con menos de 5 partidos."""
    valores = [g[clave] for g in hist if g.get(clave) is not None]
    if len(valores) < 5:
        return None
    todos, recientes = valores[:40], valores[:10]
    media = float(np.mean(todos))
    forma = float(np.average(recientes, weights=[0.85 ** k for k in range(len(recientes))]))
    base = 0.6 * forma + 0.4 * media
    vs = [g[clave] for g in hist[:80] if rival and str(g.get("rival", "")).upper() == rival.upper() and g.get(clave) is not None]
    aj_rival = (len(vs) / (len(vs) + 3)) * 0.6 * (float(np.mean(vs)) - media) if vs else 0.0
    misma_sede = [g[clave] for g in hist[:40] if sede and g.get("sede") == sede and g.get(clave) is not None]
    aj_sede = (len(misma_sede) / (len(misma_sede) + 6)) * 0.5 * (float(np.mean(misma_sede)) - media) if len(misma_sede) >= 4 else 0.0
    proyeccion = max(base + aj_rival + aj_sede, 0.0)

    muestra = np.array(valores[:30], dtype=float)
    rng = np.random.default_rng(semilla)
    sim = proyeccion + rng.choice(muestra - muestra.mean(), partidos) + rng.normal(0, 0.12 * (muestra.std() or 1), partidos)

    # ---- contexto del partido: compañeros ausentes, descanso y rival con bajas ----
    vals80 = [g.get(clave) for g in hist[:80]]
    aj_comp = np.zeros(partidos)
    activos = 0
    for c in companeros or []:
        fl = c["flags"]
        sin = [v for v, f in zip(vals80, fl) if f is True and v is not None]
        con = [v for v, f in zip(vals80, fl) if f is False and v is not None]
        if len(sin) < 3 or len(con) < 5:
            continue
        delta = (float(np.mean(sin)) - float(np.mean(con))) * len(sin) / (len(sin) + 4)
        rec = [(f is True) for f in fl[:10] if f is not None]
        w = [0.85 ** k for k, f in enumerate(fl[:10]) if f is not None]
        frac_rec = float(np.average(rec, weights=w)) if rec else 0.0
        f40 = [(f is True) for f in fl[:40] if f is not None]
        frac_base = 0.6 * frac_rec + 0.4 * (float(np.mean(f40)) if f40 else 0.0)   # cuánto de su ausencia ya está en la proyección
        ausente = (rng.random(partidos) > c["p_juega"]).astype(float)
        aj_comp += delta * (ausente - frac_base)
        activos += 1
    if activos > 1:
        aj_comp *= 0.75      # varios ausentes se solapan: no se suman completos
    aj_b2b = 0.0
    if b2b_hoy is not None:
        fb = _flags_b2b(hist)
        con_b, sin_b = [v for v, f in zip(vals80, fb) if f is True and v is not None], [v for v, f in zip(vals80, fb) if f is False and v is not None]
        if len(con_b) >= 4 and len(sin_b) >= 8:
            delta = (float(np.mean(con_b)) - float(np.mean(sin_b))) * len(con_b) / (len(con_b) + 6)
            fb40 = [f for f in fb[:40] if f is not None]
            aj_b2b = delta * ((1.0 if b2b_hoy else 0.0) - (float(np.mean(fb40)) if fb40 else 0.0))
    aj_riv_les = proyeccion * (factor_rival - 1.0) if clave in CLAVES_RIVAL_DIEZMADO else 0.0
    tope = 0.45 * max(proyeccion, 1.0)
    sim = sim + np.clip(aj_comp + aj_b2b + aj_riv_les, -tope, tope)
    sim = np.clip(np.round(sim), 0, None)

    ultimos5, previos = valores[:5], valores[5:20]
    cambio = (float(np.mean(ultimos5)) - float(np.mean(previos))) if previos else 0.0
    umbral = max(0.1 * float(np.mean(previos)), 0.5) if previos else 0.5
    tendencia = 1 if cambio > umbral else (-1 if cambio < -umbral else 0)
    cv = float(muestra.std() / muestra.mean()) if muestra.mean() > 0 else 0.0
    return {"sim": sim, "esperado": float(sim.mean()), "p10": float(np.percentile(sim, 10)), "p50": float(np.percentile(sim, 50)),
            "p90": float(np.percentile(sim, 90)), "linea": min(max(float(np.floor(np.median(recientes))) + 0.5, 0.5), 399.5),
            "tendencia": tendencia, "cambio": cambio, "media": media, "vs_n": len(vs),
            "vs_media": float(np.mean(vs)) if vs else None, "cv": cv, "n": len(valores),
            "aj_comp": float(aj_comp.mean()), "aj_b2b": float(aj_b2b), "aj_riv_les": float(aj_riv_les)}


def _prob(res, linea, mas=True):
    """Porcentaje de partidos simulados que cumplen «más de / menos de» la línea."""
    sim = res["sim"]
    return round(100 * float(np.mean(sim > linea if mas else sim < linea)))


def _chips_lesiones(filas):
    """Chips con los lesionados: rojo = fuera, amarillo = dudoso; con borde = jugador de rotación."""
    if not filas:
        return '<span>Sin bajas en el reporte</span>'
    esc = html.escape
    chips = []
    for x in filas:
        clase = "out" if x["p_juega"] == 0 else ("dud" if x["p_juega"] < 1 else "")
        rot = " rot" if x.get("rot") else ""
        mins = f" · {x['min']:.0f} min" if x.get("min") else ""
        chips.append(f'<span class="{clase}{rot}" title="{esc(str(x.get("detalle", "")))}">{esc(x["nombre"])} · {esc(x["estado"] or "?")}{mins}</span>')
    return "".join(chips)


def _simulacion_html(nombre, ctx, res, sel, extra=None):
    """Tarjeta de simulación: una caja por estadística, contexto del partido, autoanálisis y, si hay, tu línea de la tarjeta de arriba."""
    esc = html.escape
    extra = extra or {}
    if ctx["rival"]:
        sede = {"Local": " (de local)", "Visita": " (de visita)"}.get(ctx["sede"], "")
        fecha = f" · {h._fecha_bonita(ctx['fecha'])}" if ctx["fecha"] else ""
        origen = "próximo partido" if ctx["origen"] == "calendario" else "rival elegido"
        sub = f"{origen}: vs {esc(EQUIPOS_NBA.get(ctx['rival'], ctx['rival']))} ({esc(ctx['rival'])}){sede}{fecha}"
    else:
        sub = "no se encontró el próximo rival: se usa solo su forma reciente (elige un equipo arriba para simular contra él)"

    etiquetas_rol = ""
    if extra.get("activo"):
        titular = extra.get("titular")
        if titular is True:
            etiquetas_rol += '<span class="sm-tag v">✅ Titular confirmado</span>'
        elif titular is False:
            etiquetas_rol += '<span class="sm-tag">Saldría desde la banca (quinteto publicado)</span>'
        else:
            etiquetas_rol += f'<span class="sm-tag">Rol estimado: {esc(extra.get("rol", ""))} (quinteto aún no publicado)</span>'
        if extra.get("b2b_hoy") is not None:
            etiquetas_rol += f'<span class="sm-tag">{"Back-to-back" if extra["b2b_hoy"] else "Con descanso"}</span>'

    banner = ""
    if sel:
        clave, lado, linea, pct_hist, pct_sim = sel
        etq = {"PTS": "puntos", "REB": "rebotes", "AST": "asistencias", "REB+AST": "reb + ast", "PTS+REB": "pts + reb", "PTS+AST": "pts + ast", "P+R+A": "pts + reb + ast", "3PM": "triples",
               "STL": "robos", "BLK": "tapones", "MIN": "minutos"}.get(clave, clave)
        lectura = "favorable" if pct_sim >= 60 else ("desfavorable" if pct_sim < 45 else "pareja")
        banner = (f'<div class="sm-banner"><div><b>Tu línea: {esc(lado)} {linea:g} {esc(etq)}</b><br>'
                  f'<span>Simulación {pct_sim}% · historial de la tarjeta {pct_hist}%</span></div>'
                  f'<span class="sm-chip {"v" if pct_sim >= 60 else ("r" if pct_sim < 45 else "")}">Lectura {lectura}</span></div>')

    cajas = []
    for clave, titulo in SIM_STATS:
        r = res.get(clave)
        if not r:
            continue
        escala = max(r["p90"] * 1.15, r["esperado"] * 1.15, 1.0)
        izq = 100 * r["p10"] / escala
        ancho = max(100 * (r["p90"] - r["p10"]) / escala, 2)
        pct = _prob(r, r["linea"])
        chip = "v" if pct >= 55 else ("r" if pct <= 45 else "")
        flecha = {1: '<span class="sube">▲ en alza</span>', -1: '<span class="baja">▼ en baja</span>', 0: "● estable"}[r["tendencia"]]
        rival_txt = ""
        if r["vs_media"] is not None:
            dif = r["vs_media"] - r["media"]
            rival_txt = f' · vs {esc(ctx["rival"])}: {h._fmt(r["vs_media"])} ({"+" if dif >= 0 else ""}{h._fmt(dif)})'
        ctx_aj = r["aj_comp"] + r["aj_b2b"] + r["aj_riv_les"]
        ajuste_txt = f' · contexto {"+" if ctx_aj >= 0 else ""}{h._fmt(ctx_aj)}' if extra.get("activo") and abs(ctx_aj) >= 0.05 else ""
        cajas.append(
            f'<div class="sm-c{" sel" if sel and sel[0] == clave else ""}"><small>{esc(titulo)}</small><b>{h._fmt(r["esperado"])}</b>'
            f'<div class="sm-rango"><i style="left:{izq:.1f}%;width:{ancho:.1f}%"></i><em style="left:{100 * r["esperado"] / escala:.1f}%"></em></div>'
            f'<div class="sm-pie"><span>{r["p10"]:g}</span><span>rango 80%</span><span>{r["p90"]:g}</span></div>'
            f'<span class="sm-chip {chip}">Más de {r["linea"]:g}: {pct}%</span>'
            f'<div class="sm-ten">{flecha}{rival_txt}{ajuste_txt}</div></div>')

    # ---- Lesiones y contexto ----
    bloque_ctx = ""
    if extra.get("activo"):
        rival_rotulo = f" ({esc(ctx['rival'])})" if ctx["rival"] else ""
        bloque_ctx = (f'<div class="sm-sec">Bajas de su equipo</div><div class="sm-les">{_chips_lesiones(extra.get("propios"))}</div>'
                      f'<div class="sm-sec">Bajas del rival{rival_rotulo}</div>'
                      f'<div class="sm-les">{_chips_lesiones(extra.get("rival")) if ctx["rival"] else "<span>Sin rival definido</span>"}</div>')

    # ---- Autoanálisis en palabras ----
    notas = []
    nombres_stat = dict(SIM_STATS)
    alza = [nombres_stat[c] for c, _ in SIM_STATS if res.get(c) and res[c]["tendencia"] == 1]
    baja = [nombres_stat[c] for c, _ in SIM_STATS if res.get(c) and res[c]["tendencia"] == -1]
    if alza:
        notas.append(f"En alza (últimos 5 partidos sobre sus 15 anteriores): {esc(', '.join(alza))}.")
    if baja:
        notas.append(f"En baja: {esc(', '.join(baja))}.")
    if not alza and not baja:
        notas.append("Su rendimiento reciente está estable en todas las estadísticas.")
    if extra.get("activo"):
        for t in extra.get("explicaciones", []):
            notas.append(esc(t))
        mp = res.get("MIN")
        if mp:
            notas.append(f"Minutos proyectados: {h._fmt(mp['esperado'])} (su promedio normal es {h._fmt(mp['media'])}).")
        if extra.get("factor_rival", 1.0) > 1.0:
            notas.append(f'<span class="sm-est">Estimado: el rival tiene bajas de rotación; se sube su producción esperada cerca de '
                         f'{(extra["factor_rival"] - 1) * 100:.0f}% en puntos, rebotes, asistencias y triples (ajuste aproximado, no sale de datos).</span>')
        if extra.get("sin_reporte"):
            notas.append("No se pudo leer el reporte de lesiones de ESPN: la simulación no incluye bajas.")
    if ctx["rival"]:
        mejores = [(c, res[c]["vs_media"] - res[c]["media"]) for c in ("PTS", "REB", "AST") if res.get(c) and res[c]["vs_n"] >= 2]
        for c, dif in mejores:
            base = max(res[c]["media"], 1)
            if abs(dif) >= 0.1 * base:
                notas.append(f"Contra {esc(ctx['rival'])} rinde {'más' if dif > 0 else 'menos'} en {esc(nombres_stat[c].lower())}: "
                             f"{h._fmt(res[c]['vs_media'])} de promedio en {res[c]['vs_n']} partidos frente a {h._fmt(res[c]['media'])} normal.")
        pocos = max((res[c]["vs_n"] for c in ("PTS", "REB", "AST") if res.get(c)), default=0)
        if pocos < 3:
            notas.append(f"Hay pocos partidos contra {esc(ctx['rival'])} ({pocos}); el ajuste por rival pesa poco. Agrega más temporadas arriba para mejorarlo.")
    regulares = sorted(((res[c]["cv"], c) for c in ("PTS", "REB", "AST") if res.get(c)))
    if regulares:
        notas.append(f"Es más regular en {esc(nombres_stat[regulares[0][1]].lower())} y más irregular en {esc(nombres_stat[regulares[-1][1]].lower())}.")
    n = max(r["n"] for r in res.values())
    notas.append(f"Base de cálculo: {n} partidos de las temporadas elegidas, {SIM_DRAWS:,} partidos simulados por estadística.".replace(",", "."))
    lista = "".join(f"<li>{t}</li>" for t in notas)

    aviso = ("Estimación estadística con su historial y el reporte de lesiones de ESPN; no es una predicción segura. "
             "Las bajas pueden cambiar hasta minutos antes del partido, y ESPN no publica los quintetos ni el plan de minutos del entrenador de antemano.")
    return (f'<div class="sm-wrap"><div class="sm-t">🔮 Simulación · {esc(nombre)}</div><div class="sm-s">{sub}</div>{etiquetas_rol}{banner}'
            f'<div class="sm-grid">{"".join(cajas)}</div>{bloque_ctx}<ul class="sm-nota">{lista}</ul>'
            f'<div class="sm-aviso">{aviso}</div></div>')


def _preparar_simulacion(idx, pid, equipo, hist, rival_elegido, temporadas, playoffs):
    """Calcula la simulación del próximo partido ANTES de dibujar la tarjeta, para que el encabezado de la tarjeta y el panel
    de debajo usen exactamente los mismos números. Devuelve {"ctx", "res", "extra", "fallo"}."""
    ctx = _contexto_rival(equipo, rival_elegido)
    usar = st.session_state.get(f"sim_ctx_{idx}", True)      # el interruptor se dibuja más abajo; su valor ya está en el estado
    extra = {"activo": False}
    parametros = {}
    fallo = False
    if usar:
        try:
            with st.spinner("Revisando lesiones y contexto del partido..."):
                cp = _contexto_partido(pid, equipo, hist, ctx, temporadas, playoffs)
            extra = {"activo": True, "propios": cp["propios"], "rival": cp["rival"], "explicaciones": cp["explicaciones"],
                     "rol": cp["rol"], "titular": cp["titular"], "b2b_hoy": cp["b2b_hoy"], "factor_rival": cp["factor_rival"],
                     "sin_reporte": not _lesiones()}
            parametros = {"companeros": cp["companeros"], "b2b_hoy": cp["b2b_hoy"], "factor_rival": cp["factor_rival"]}
        except Exception:  # noqa: BLE001 - si el contexto falla, la simulación sigue sin él
            extra = {"activo": False}
            fallo = True
    res = {}
    for clave, _ in SIM_STATS:
        semilla = zlib.crc32(f"{pid}|{clave}|{ctx['rival']}|{ctx['sede']}".encode())
        r = simular_estadistica(hist, clave, ctx["rival"], ctx["sede"], semilla, **parametros)
        if r:
            res[clave] = r
    return {"ctx": ctx, "res": res, "extra": extra, "fallo": fallo}


def _pct_simulacion(prep):
    """Función que la tarjeta llama con (estadística, línea, lado «Más de») y devuelve el % simulado, o None si no hay simulación."""
    res = prep["res"]

    def pct(stat, linea, mas):
        return _prob(res[stat], float(linea), bool(mas)) if stat in res else None
    return pct


def _mostrar_simulacion(idx, nombre, hist_tarjeta, prep):
    """Dibuja el autoanálisis del próximo partido (justo debajo de la tarjeta de línea) con lo ya calculado en _preparar_simulacion."""
    st.toggle("Considerar lesiones, quinteto, minutos y descanso", True, key=f"sim_ctx_{idx}",
              help="Suma al cálculo las bajas de su equipo y del rival, lo que rinde el jugador sin sus compañeros ausentes, "
                   "los minutos y si juega en back-to-back. Desactívalo para ver solo su historial.")
    ctx, res, extra = prep["ctx"], prep["res"], prep["extra"]
    if prep["fallo"]:
        st.caption("No se pudo cargar el contexto del partido (lesiones/descanso); se muestra la simulación solo con su historial.")
    if not res:
        st.caption("Todavía no hay suficientes partidos (mínimo 5) para simular el próximo partido.")
        return
    sel = None
    clave = st.session_state.get(f"fl_{idx}_stat")      # la estadística, el lado y la línea que tienes en la tarjeta
    if clave in res:
        lado = st.session_state.get(f"fl_{idx}_lado", "Más de")
        linea = st.session_state.get(f"fl_{idx}_linea_{clave}")
        if linea is not None:
            mas = lado == "Más de"
            valores = [g.get(clave) or 0 for g in hist_tarjeta[:10]]
            sel = (clave, lado, float(linea), ficha_linea.evaluar(valores, float(linea), mas)[3], _prob(res[clave], float(linea), mas))
    st.markdown(CSS_SIM, unsafe_allow_html=True)   # aparte del HTML: la app oculta los bloques que traen <style>
    st.markdown(_simulacion_html(nombre, ctx, res, sel, extra), unsafe_allow_html=True)


def _texto_equipo(a):
    return f"{EQUIPOS_NBA.get(a, a)} ({a})"


def _opciones_rival(hist):
    """Siglas de los 30 equipos (más cualquier otra que aparezca en el historial), ordenadas por nombre; \"\" = todos."""
    siglas = set(EQUIPOS_NBA) | {str(g.get("rival")).upper() for g in hist if g.get("rival")}
    return [""] + sorted(siglas, key=lambda a: EQUIPOS_NBA.get(a, a))


def _buscador_linea(por_id, elegidos, idx, opciones_rival):
    """Lo que va dentro de la tarjeta de línea: buscador de jugadores + selector de equipo rival, en una sola fila.

    Las claves usan la POSICIÓN (no el jugador): al quitar o cambiar al jugador, la estadística, el lado y la línea se mantienen."""
    c1, c2 = st.columns([3, 2])
    with c1:
        _buscador_rapido(por_id, elegidos, f"linea_{idx}", idx)
    with c2:
        st.selectbox("Contra el equipo", opciones_rival, key=f"jug_vs_{idx}", label_visibility="collapsed",
                     format_func=lambda a: "Todos los equipos" if not a else _texto_equipo(a))


# ----- Contexto del partido y próximo rival para la tarjeta de línea (ficha_linea.render) -----
_COMBINADAS_FR = {"REB+AST": ("REB", "AST"), "PTS+REB": ("PTS", "REB"), "PTS+AST": ("PTS", "AST"), "P+R+A": ("PTS", "REB", "AST")}


@st.cache_data(ttl=3600, show_spinner=False)
def _titulares_partidos(pid, eventos):
    """{evento: True/False} = si el jugador abrió ese partido, leído de los box scores (nba_extra; se guardan en disco, así que
    cada partido se descarga una sola vez). El registro de partidos de ESPN no trae este dato. Los partidos cuyo box score no se
    pueda leer simplemente no aparecen. {} si falla todo."""
    try:
        import nba_extra
        cajas, _ = nba_extra.cargar_cajas([str(e) for e in eventos])
    except Exception:  # noqa: BLE001 - el rol es un extra: sin él la tarjeta sale igual (sin ese filtro)
        return {}
    out = {}
    for ev, caja in cajas.items():
        for j in caja.get("jugadores", []):
            if str(j.get("id")) == str(pid):
                out[str(ev)] = bool(j.get("Titular"))
                break
    return out


def _titulares_con_aviso(pid, juegos):
    """Envoltorio de _titulares_partidos con aviso de carga (la primera vez baja varios box scores). {} si falla."""
    eventos = tuple(str(g.get("event")) for g in juegos if g.get("event"))
    if not eventos or pid is None:
        return {}
    try:
        with st.spinner("Leyendo titularidades de los últimos partidos…"):
            return _titulares_partidos(str(pid), eventos)
    except Exception:  # noqa: BLE001
        return {}


def _partidos_contexto(juegos, titulares=None):
    """Lo que `detalles` no trae y la tarjeta usa para sus filtros: diferencia final del equipo («paliza») y si fue titular.

    `juegos` va del más antiguo al más reciente; `titulares` = {evento: bool} (ver _titulares_partidos). Si un partido no está
    ahí, queda en None, y si ninguno lo está la tarjeta no ofrece el filtro de rol. Sede, descanso, resultado y minutos ya
    viajan en `detalles`, y la tarjeta los une con esto."""
    titulares = titulares or {}
    out = []
    for g in juegos:
        mios, rival = _marcador(g)
        tit = titulares.get(str(g.get("event")))
        out.append({"margen": None if mios is None else mios - rival, "titular": tit})
    return out


@st.cache_data(ttl=300, show_spinner=False)
def _datos_rival(equipo, rival, sede, fecha, jugador):
    """Del próximo rival: lo que concede (factor por estadística), su ritmo y las bajas de ambos equipos. None si no se puede.

    Reutiliza el pronóstico de «Próximos» (nba_hoy._pronostico, ya con caché) y las bajas de ficha_equipos. Con la sede
    desconocida (rival elegido a mano sin partido en el calendario) solo se muestran las bajas."""
    import ficha_equipos as fe
    import nba_hoy
    alias = nba_hoy._ALIAS_ABREV
    inverso = {v: k for k, v in alias.items()}
    equipos = fe._equipos()

    def buscar(ab):
        ab = str(ab).upper()
        cand = {ab, alias.get(ab, ab), inverso.get(ab, ab)}
        return next((e for e in equipos if str(e.get("abbr", "")).upper() in cand), None)

    e_riv, e_mio = buscar(rival), buscar(equipo)
    if not e_riv:
        return None
    pr = None
    if sede in ("Local", "Visita") and e_mio:
        loc, vis = (e_mio["id"], e_riv["id"]) if sede == "Local" else (e_riv["id"], e_mio["id"])
        try:
            pr = nba_hoy._pronostico(loc, vis, fecha or None)
        except Exception:  # noqa: BLE001 - sin pronóstico seguimos con las bajas
            pr = None
    if pr:
        local = sede == "Local"
        bajas_riv = pr.get("raw_bajas_v" if local else "raw_bajas_l")
        bajas_eq = pr.get("raw_bajas_l" if local else "raw_bajas_v")
        rit = pr.get("ritmo")
        fr = pr.get("fr_l" if local else "fr_v") or {}
        ritmo = {"valor": rit["pos"], "liga": nba_hoy._RITMO_LIGA, "nota": rit["cat"]} if rit else None
    else:
        fr, ritmo = {}, None
        bajas_riv = fe._bajas_hoy(e_riv["id"], e_riv["nombre"])
        bajas_eq = fe._bajas_hoy(e_mio["id"], e_mio["nombre"]) if e_mio else None
    propias = [b for b in (bajas_eq or []) if str(b.get("Jugador", "")).strip().lower() != str(jugador).strip().lower()]
    return {"fr": fr, "ritmo": ritmo, "bajas": list(bajas_riv or []), "bajas_equipo": propias}


def _factor_stat(fr, stat, series):
    """Factor de lo que el rival concede de `stat` (1.0 = en la media). Las combinadas se pesan por lo que aporta cada parte."""
    if stat in fr:
        return fr[stat]
    comp = _COMBINADAS_FR.get(stat)
    if comp and all(c in fr for c in comp):
        pesos = [sum(series.get(c) or [0]) / max(len(series.get(c) or [0]), 1) for c in comp]
        if sum(pesos) > 0:
            return sum(p * fr[c] for p, c in zip(pesos, comp)) / sum(pesos)
    return None


def _proximo_rival(nombre, equipo, ctx, series):
    """`proximo` para ficha_linea.render: rival, lo que concede de cada estadística, su ritmo y las bajas (Out y Day-To-Day)."""
    if not ctx.get("rival"):
        return None
    try:
        with st.spinner("Revisando al próximo rival..."):
            d = _datos_rival(equipo, ctx["rival"], ctx.get("sede"), ctx.get("fecha"), nombre)
    except Exception:  # noqa: BLE001 - el rival es un extra: si falla, la tarjeta sale igual
        return None
    if not d:
        return None
    concede = {}
    for stat in series:
        f = _factor_stat(d["fr"], stat, series)
        if f is not None:
            concede[stat] = {"valor": (f - 1) * 100, "rel": True}
    return {"rival": ctx["rival"], "sede": {"Local": "vs", "Visita": "@"}.get(ctx.get("sede"), ""),
            "concede": concede, "ritmo": d["ritmo"], "bajas": d["bajas"], "bajas_equipo": d["bajas_equipo"]}


def _ficha_vacia(por_id):
    """Tarjeta sin jugador: silueta desconocida y todo en 0. Mantiene el buscador y los controles para elegir otro."""
    opciones = [""] + sorted(EQUIPOS_NBA, key=lambda a: EQUIPOS_NBA[a])
    series = {c: [0.0] * 10 for c in ("PTS", "REB", "AST", "REB+AST", "PTS+REB", "PTS+AST", "P+R+A", "3PM", "STL", "BLK")}
    ficha_linea.render(nombre="Elige un jugador", foto_url=ficha_linea.SILUETA, contexto="sin partidos · todo en 0",
                       series=series, key="fl_0", buscador=lambda: _buscador_linea(por_id, [], 0, opciones))


def _autoanalisis_ventanas(nombre, hist_vs, pid, es_pro):
    """Botón de autoanálisis de stats en ventanas de 5, 10, 15 y 20 partidos + evaluador de cuota Pro."""
    c_auto, c_cuota = st.columns([1.6, 1.4], vertical_alignment="center")
    if c_auto.button("⚡ Autoanalizar (5, 10, 15 o 20 PJ)", key=f"btn_auto_{pid}", use_container_width=True):
        if not es_pro:
            planes.modal_pro("El autoanálisis de 5, 10, 15 y 20 partidos es exclusivo de ScoreLine Pro.")
        else:
            st.session_state[f"_show_auto_{pid}"] = not st.session_state.get(f"_show_auto_{pid}", False)

    if st.session_state.get(f"_show_auto_{pid}") and es_pro:
        filas = []
        for w in (5, 10, 15, 20):
            sub = hist_vs[:w]
            if not sub:
                continue
            fila = {"Ventana": f"Últimos {len(sub)} PJ"}
            for col in ("PTS", "REB", "AST", "3PM", "P+R+A"):
                vals = [float(g[col]) for g in sub if g.get(col) is not None]
                fila[col] = round(sum(vals) / len(vals), 1) if vals else None
            filas.append(fila)
        if filas:
            st.markdown(f"##### ⚡ Autoanálisis multi-ventana · {nombre}")
            st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

    with c_cuota:
        if es_pro:
            cuota_in = st.number_input("Cuota a evaluar (ej. 1.85)", min_value=1.01, max_value=20.0, value=1.85, step=0.05, key=f"cuota_ev_{pid}")
            if hist_vs:
                pts_vals = [float(g["PTS"]) for g in hist_vs[:10] if g.get("PTS") is not None]
                if pts_vals:
                    prom_10 = sum(pts_vals) / len(pts_vals)
                    linea_ref = max(0.5, round(prom_10 - 0.5) + 0.5)
                    prob_real = sum(1 for v in pts_vals if v > linea_ref) / len(pts_vals)
                    ev = (prob_real * cuota_in - 1.0) * 100.0
                    veredicto = "Rentable (+EV)" if ev > 0 else "Sin valor (-EV)"
                    st.caption(f"Línea ref. {linea_ref} PTS ({round(prob_real*100)}%) · EV: **{ev:+.1f}%** ({veredicto})")
        else:
            if st.button("🔒 Evaluar cuota rentable (Pro)", key=f"btn_cuota_lock_{pid}", use_container_width=True):
                planes.modal_pro("Evaluar si una cuota es rentable (EV%) es exclusivo de ScoreLine Pro.")


def render():
    st.title("📈 Jugadores")
    es_pro = planes.es_pro()
    st.caption(
        "Mira las estadísticas de un jugador y agrega más para compararlos. Los partidos van del más reciente al más antiguo."
        if es_pro else
        "Plan Gratuito: consulta PTS y últimos 5 partidos de un jugador. Comparar jugadores, métricas completas y simulación están disponibles en ScoreLine Pro."
    )

    try:
        jugadores = h._jugadores()
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo cargar la lista de jugadores ({type(e).__name__}). Revisa la sección Diagnóstico.")
        return
    if not jugadores:
        st.warning("No se encontraron jugadores.")
        return

    por_id = {j["id"]: j for j in jugadores}
    ids = _orden_favoritos(por_id)
    # rostros y resaltado en la lista de todos los buscadores de jugadores + escudos en el selector de equipo
    h.rostros_en_buscadores(por_id, extra={_texto_equipo(a): _url_escudo_nba(a) for a in EQUIPOS_NBA})

    hoy = date.today()
    actual = hoy.year + (1 if hoy.month >= 10 else 0)
    opciones = list(range(actual, actual - 6, -1))
    c1, c2 = st.columns([3, 1])
    temporadas = c1.multiselect("Temporadas", opciones, default=opciones[:2], format_func=_etiqueta_temporada,
                                key="jug_temporadas", help="Más temporadas = más partidos, pero tarda un poco más en cargar.")
    playoffs = c2.toggle("Incluir playoffs", True, key="jug_playoffs")
    ventana = VENTANA_PRINCIPAL if es_pro else 5

    # Espacio FIJO para avisos y carga, y pestañas SIEMPRE las mismas y en el mismo sitio: así, al activar un filtro o
    # quitar al jugador, no aparecen ni desaparecen elementos encima de las pestañas (si eso cambia, Streamlit las
    # reinicia y te devuelve a la primera). Las pestañas se crean ya; su contenido se llena más abajo.
    avisos = st.container()
    tab_linea, tab_part = st.tabs(["🎯 Línea y tendencia", "🗓️ Partidos (reciente → pasado)"])

    # El buscador de jugadores (hasta 4 en Pro, 1 en Gratis) vive en la pestaña de partidos
    with tab_part:
        elegidos = st.multiselect(
            "Jugadores (agrega hasta 4 para compararlos)" if es_pro else "Jugador (plan gratuito: 1 jugador a la vez)",
            ids,
            max_selections=4 if es_pro else 1,
            format_func=_fmt_jugador(por_id),
            placeholder="Escribe un nombre para buscar...",
            key="jug_elegidos",
        )
        if not es_pro:
            if st.button("🔒 Comparar jugadores en stats (ScoreLine Pro)", key="btn_lock_comp_jug"):
                planes.modal_pro("Comparar múltiples jugadores en estadísticas está disponible en ScoreLine Pro.")
        _carpeta_favoritos(por_id, elegidos)

    if not elegidos:
        with tab_linea:
            _ficha_vacia(por_id)
        with tab_part:
            st.info("Elige al menos un jugador para ver sus partidos.")
        return
    if not temporadas:
        avisos.warning("Elige al menos una temporada.")
        return

    with avisos:
        with st.spinner("Cargando partidos..."):
            historiales = [_historial_ordenado(i, temporadas, playoffs) for i in elegidos]
    nombres = [por_id[i]["nombre"] for i in elegidos]
    equipos = [por_id[i]["equipo"] for i in elegidos]
    recortados = [hist if ventana == 0 else hist[:ventana] for hist in historiales]

    sin_datos = [n for n, hist in zip(nombres, historiales) if not hist]
    if sin_datos:
        avisos.warning("Sin partidos en las temporadas elegidas para: " + ", ".join(sin_datos) + ".")
    if all(not hist for hist in historiales):
        return

    lista_prom = [promedios(r) if r else {c: None for c, _, _ in GRANDES + PEQUENAS} for r in recortados]
    lider = lideres(lista_prom)
    etiqueta = "Todos los partidos" if ventana == 0 else f"Últimos {ventana}"

    # ---- Línea y tendencia (tarjeta "más de / menos de" + historial completo de cada jugador) ----
    with tab_linea:
        pest_linea = st.tabs([f"👤 {n}" for n in nombres]) if len(nombres) > 1 else [st.container()]
        for idx, (pest, n, eq, hist, pid) in enumerate(zip(pest_linea, nombres, equipos, historiales, elegidos)):
            with pest:
                opciones_rival = _opciones_rival(hist)
                clave_vs = f"jug_vs_{idx}"
                if st.session_state.get(clave_vs, "") not in opciones_rival:
                    st.session_state[clave_vs] = ""
                rival_sel = st.session_state.get(clave_vs, "")
                hist_vs = _solo_contra([hist], rival_sel)[0]     # solo partidos contra ese equipo (o todos)
                buscador = lambda idx=idx, o=opciones_rival: _buscador_linea(por_id, elegidos, idx, o)
                max_hist = 20 if es_pro else 5
                ultimos = list(reversed(hist_vs[:max_hist]))       # del más antiguo al más reciente (izquierda → derecha)
                if not ultimos:
                    # Misma tarjeta (misma clave) con todo en 0: así no desaparece ni se reinicia al elegir un rival sin partidos
                    ficha_linea.render(
                        nombre=n,
                        foto_url=f"https://a.espncdn.com/i/headshots/nba/players/full/{pid}.png",
                        contexto=f"{eq} · sin partidos" + (f" contra {rival_sel}" if rival_sel else "") + " · todo en 0",
                        series={c: [0.0] * 5 for c in (("PTS", "REB", "AST", "REB+AST", "PTS+REB", "PTS+AST", "P+R+A", "3PM", "STL", "BLK") if es_pro else ("PTS",))},
                        rivales=None, key=f"fl_{idx}", buscador=buscador,
                        logo_equipo=_url_escudo_nba(eq))
                    if rival_sel:
                        st.info(f"{n} no jugó contra {EQUIPOS_NBA.get(rival_sel, rival_sel)} en las temporadas elegidas. "
                                "Prueba agregando más temporadas.")
                    else:
                        st.info("Sin partidos en las temporadas elegidas.")
                    continue
                cols_permitidas = ("PTS", "REB", "AST", "REB+AST", "PTS+REB", "PTS+AST", "P+R+A", "3PM", "STL", "BLK") if es_pro else ("PTS",)
                series = {c: [g.get(c) or 0 for g in ultimos] for c in cols_permitidas
                          if any(g.get(c) is not None for g in ultimos)}
                rivales = [f'{"vs" if g.get("sede") == "Local" else "@"} {g.get("rival", "?")}' for g in ultimos]
                contexto = eq + (f" · {_bio_texto(pid)}" if _bio_texto(pid) else "") + (f" · contra {rival_sel}" if rival_sel else "")
                descansos = _descanso_por_partido(hist)
                detalles_tt = [_detalle_partido(g, descansos) for g in ultimos]
                with st.spinner("Cargando minutos por cuarto..."):
                    for d_tt, c_tt in zip(detalles_tt, _cuartos_de_partidos(pid, ultimos)):
                        d_tt["cuartos"] = c_tt

                if es_pro:
                    prep_sim = _preparar_simulacion(idx, pid, eq, hist, rival_sel, temporadas, playoffs)
                    ficha_linea.render(
                        nombre=n,
                        foto_url=f"https://a.espncdn.com/i/headshots/nba/players/full/{pid}.png",
                        contexto=contexto,
                        series=series, rivales=rivales, key=f"fl_{idx}",
                        buscador=buscador, escudo=_url_escudo_nba, logo_equipo=_url_escudo_nba(eq),
                        ultimos=20, ventanas=(5, 10, 15, 20),
                        historico={c: [float(g.get(c) or 0) for g in reversed(hist_vs)] for c in series},
                        simulacion=_pct_simulacion(prep_sim),
                        detalles=detalles_tt,
                        partidos=_partidos_contexto(ultimos, _titulares_con_aviso(pid, ultimos)),
                        proximo=_proximo_rival(n, eq, prep_sim["ctx"], series))
                    _autoanalisis_ventanas(n, hist_vs, pid, True)
                    if rival_sel and len(ultimos) < 10:
                        st.caption(f"Solo hay {len(ultimos)} partido(s) de {n} contra {EQUIPOS_NBA.get(rival_sel, rival_sel)} "
                                   "en las temporadas elegidas; agrega más temporadas arriba para tener más muestra.")
                    _mostrar_simulacion(idx, n, hist_vs, prep_sim)
                    with st.expander("📏 Historial completo contra una línea (con medias móviles)"):
                        clave_h = st.selectbox("Estadística", _claves(), key=f"jug_hist_{pid}",
                                               format_func=lambda c: NOMBRES[c])
                        graficos.mostrar_jugador_vs_linea(hist_vs, clave_h, NOMBRES[clave_h], f"jug_{pid}_{clave_h}_{rival_sel}", nombre=n)
                else:
                    ficha_linea.render(
                        nombre=n,
                        foto_url=f"https://a.espncdn.com/i/headshots/nba/players/full/{pid}.png",
                        contexto=contexto,
                        series=series, rivales=rivales, key=f"fl_{idx}",
                        buscador=buscador, escudo=_url_escudo_nba, logo_equipo=_url_escudo_nba(eq),
                        ultimos=5, ventanas=(5,),
                        historico={"PTS": [float(g.get("PTS") or 0) for g in reversed(hist_vs[:5])]},
                        detalles=detalles_tt)
                    _autoanalisis_ventanas(n, hist_vs, pid, False)
                    planes.bloque_pro(
                        "Simulación de stats vs rival reciente y métricas completas",
                        "La simulación contra el próximo rival, ventanas de 10/15/20 partidos y estadísticas avanzadas están disponibles en ScoreLine Pro.",
                        "Simulación 10.000 corridas · REB · AST · 3PM · P+R+A",
                        key=f"lock_sim_{pid}_{idx}",
                    )

    # ---- Partidos ----
    with tab_part:
        etiquetas = [f"👤 {n}" for n in nombres] + (["⚖️ Lado a lado"] if len(elegidos) > 1 else [])
        pestanas = st.tabs(etiquetas)
        st.markdown(_css_partidos(PALETA_OSCURA if _es_oscuro() else PALETA_CLARA), unsafe_allow_html=True)   # aparte del HTML: la app oculta los bloques que traen <style>
        for pestana, hist, r, eq in zip(pestanas, historiales, recortados, equipos):
            with pestana:
                if r:
                    st.markdown(f"#### Últimos partidos · {etiqueta}")
                    st.markdown(_tabla_ultimos_partidos(r, eq), unsafe_allow_html=True)
                    with st.expander("Ver todas las estadísticas (tiros, faltas, fase…)"):
                        _mostrar_tabla_partidos(r)
                else:
                    _mostrar_tabla_partidos(r)
        if len(elegidos) > 1:
            with pestanas[-1]:
                try:   # selector angosto y, pegado a su lado, el botón (alineado abajo con el selector)
                    c_sel, c_btn, _ = st.columns([1.2, 1.2, 3], vertical_alignment="bottom")
                except TypeError:   # Streamlit antiguo sin vertical_alignment
                    c_sel, c_btn, _ = st.columns([1.2, 1.2, 3])
                with c_sel:
                    clave = st.selectbox("Estadística a comparar", _claves(), key="jug_lado",
                                         format_func=lambda c: NOMBRES[c])
                with c_btn:
                    abrir = st.button("🔍 Abrir tabla en grande", type="primary", key="jug_abrir_tabla",
                                      use_container_width=True, help="Abre esta comparación en una ventana grande, con otro diseño")
                st.caption("Cada fila es el mismo número de partido contando hacia atrás: la fila 1 es el último partido de cada uno. "
                           "El valor resaltado con el color del jugador es el mejor de la fila (gris = empate); al pie va el promedio. "
                           "Para cambiar cuántos partidos promediar o ver solo los que jugaron juntos o enfrentados, abre la tabla en grande.")
                if abrir:
                    st.session_state["jug_lado_modal"] = clave   # que el selector del diálogo arranque en la estadística elegida
                    st.session_state["jug_elegidos_modal"] = list(elegidos)   # y el buscador, con los jugadores actuales
                    _abrir_tabla_grande(por_id, temporadas, playoffs, clave)
                _lado_a_lado(nombres, [r for r in recortados], clave, NOMBRES[clave], ids=elegidos, equipos=equipos)
