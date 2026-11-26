"""Cuadro de líneas para equipos de la NBA: over/under de puntos, puntos del equipo, triples y hándicap.

Se usa desde app.py con:  ficha_equipos.render()
Datos: ESPN (calendario de cada equipo + box score de cada partido, que se guarda en disco vía nba_extra).
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
import math
import os
import re
import unicodedata
from difflib import SequenceMatcher
from html import escape as _e
from statistics import mean, median, stdev

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import estilos
import nba
import nba_extra
from common import _session, normalizar

# Mercados agrupados por tipo. Cada mercado es UNA entrada (clase Mercado): de ella salen el tipo de tarjeta, el rango del
# hándicap y los textos, así que ni _tarjeta ni render() mantienen listas propias de claves.
# Datos que calcula _serie_equipo en cada partido, además de los de ESPN:
#   tq1..tq4 = total de puntos del cuarto (ambos equipos)   pq1..pq4 = puntos del equipo en el cuarto
#   gq1..gq4 = diferencia del equipo en el cuarto (>0 = ganó el cuarto)
#   th1/th2  = total de puntos del primer / segundo tiempo (cuartos 1+2 y 3+4, ambos equipos)
#   ph1/ph2  = puntos del equipo en el primer / segundo tiempo
#   gh1/gh2  = diferencia del equipo en el primer / segundo tiempo (>0 = ganó el tiempo)
#   ftm / fta / dos = tiros libres anotados / intentados / tiros de 2 anotados del equipo   oreb = rebotes ofensivos
#   gft / g2 = diferencia de tiros libres / de 2 anotados contra el rival (>0 = el equipo anotó más)
@dataclass(frozen=True)
class Mercado:
    clave: str            # identificador del mercado
    tipo: str = "over"    # "over" (más/menos de una línea) | "handicap" | "ganador" (verde = ganó o anotó más que el rival)
    dato: str = ""        # dato que se lee de cada partido cuando no es la propia clave (alias: el hándicap del 1.er cuarto lee gq1)
    rango: float = 0.0    # solo hándicap: límite (±) del selector de línea
    ayuda: str = ""       # solo ganador: texto que se muestra bajo el selector
    tag: str = "GANADOR"  # solo ganador: etiqueta y texto grande de la tarjeta
    grande: str = "Gana"
    verbo: str = "Ganó"   # solo ganador: inicio del resumen («Ganó 7 de 10»)

    @property
    def campo(self):
        """Clave del dato que se lee en cada partido."""
        return self.dato or self.clave


def _ganar_periodo(clave, periodo):
    return Mercado(clave, "ganador", ayuda=(
        f"Mide cuántas veces el equipo ganó ese {periodo} (verde = lo ganó; un empate en el {periodo} no cuenta como ganado). "
        f"El número de cada barra es la diferencia de puntos en el {periodo}."))


def _anotar_mas(clave, que):
    return Mercado(clave, "ganador", tag="MÁS ANOTADOS", grande="Más", verbo="Anotó más que el rival en", ayuda=(
        f"Mide cuántas veces el equipo anotó más {que} que su rival (verde = anotó más; un empate no cuenta). "
        "El número de cada barra es la diferencia contra el rival."))


_O = Mercado   # atajo: mercado de más/menos de una línea
_ORDINALES = {1: "1.er", 2: "2.º", 3: "3.er", 4: "4.º"}
_TIEMPOS = {1: "primer", 2: "segundo"}
_CUARTOS = {}
for _h, _n in _TIEMPOS.items():
    _CUARTOS[f"Total de puntos del {_n} tiempo (ambos equipos)"] = _O(f"th{_h}")
    _CUARTOS[f"Puntos del equipo en el {_n} tiempo"] = _O(f"ph{_h}")
    _CUARTOS[f"Ganador del {_n} tiempo"] = _ganar_periodo(f"gh{_h}", "tiempo")
    _CUARTOS[f"Hándicap del {_n} tiempo"] = Mercado(f"hh{_h}", "handicap", dato=f"gh{_h}", rango=25.0)
for _k, _o in _ORDINALES.items():
    _CUARTOS[f"Total de puntos del {_o} cuarto (ambos equipos)"] = _O(f"tq{_k}")
    _CUARTOS[f"Puntos del equipo en el {_o} cuarto"] = _O(f"pq{_k}")
    _CUARTOS[f"Ganador del {_o} cuarto"] = _ganar_periodo(f"gq{_k}", "cuarto")
    _CUARTOS[f"Hándicap del {_o} cuarto"] = Mercado(f"hq{_k}", "handicap", dato=f"gq{_k}", rango=15.0)

GRUPOS_MERCADO = {
    "🏀 Puntos": {
        "Total de puntos (over/under)": _O("total"), "Puntos del equipo": _O("pf"), "Puntos recibidos": _O("pc"),
        "Puntos en la pintura": _O("paint"), "Puntos de contraataque": _O("fast"),
    },
    "⏱️ Cuartos y tiempos": _CUARTOS,
    "🎯 Tiros": {
        "Triples": _O("tri"), "Tiros libres anotados": _O("ftm"), "Tiros libres intentados": _O("fta"),
        "Tiros de 2 puntos anotados": _O("dos"),
        "% de tiros de campo": _O("fgp"), "% de triples": _O("tpp"), "% de tiros libres": _O("ftp"),
        "Equipo con más tiros libres anotados": _anotar_mas("gft", "tiros libres"),
        "Equipo con más tiros de 2 puntos anotados": _anotar_mas("g2", "tiros de 2 puntos"),
    },
    "📊 Estadísticas": {
        "Rebotes": _O("reb"), "Rebotes ofensivos": _O("oreb"), "Asistencias": _O("ast"), "Robos": _O("stl"),
        "Tapones": _O("blk"), "Pérdidas": _O("to"), "Faltas": _O("fal"),
    },
    "⚡ Ritmo y eficiencia": {
        "Ritmo (posesiones por 48 min)": _O("ritmo"), "Rend. ofensivo (pts por 100 pos.)": _O("ortg"),
        "Rend. defensivo (pts recibidos por 100 pos.)": _O("drtg"),
    },
    "🆚 Resultado": {
        "Hándicap": Mercado("margen", "handicap", rango=40.0),
        # ganar = margen mayor que 0: usa los mismos datos del hándicap
        "Ganador (local o visita)": Mercado("ganador", "ganador", dato="margen", ayuda=(
            "Mide cuántas veces ganó el equipo (verde = victoria). «En casa» y «De visita» muestran su récord según la sede.")),
    },
}
MERCADOS = {nombre: m for grupo in GRUPOS_MERCADO.values() for nombre, m in grupo.items()}   # nombre -> Mercado
# Los estilos viven en css/equipos.css y css/escudos.css (cargados con estilos.py).


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
def _json(url):
    for _ in range(2):  # un reintento: un fallo momentáneo de ESPN no debe dejar partidos fuera
        try:
            r = _session.get(url, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            continue
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def _temporada_api():
    """Año de la temporada en curso según ESPN (2027 = temporada 2026-27); None si no se pudo leer."""
    datos = _json(nba.BASE + "/scoreboard") or {}
    try:
        return int(datos["leagues"][0]["season"]["year"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _temporada_actual():
    hoy = date.today()
    base = hoy.year + (1 if hoy.month >= 10 else 0)
    api = _temporada_api()
    return max(base, api) if api else base


def _color_equipo(t):
    """Color del equipo para el brillo de su tarjeta: el oficial de ESPN; si es casi negro, el alterno; si no hay, índigo."""
    def hex_ok(c):
        c = str(c or "")
        return len(c) == 6 and all(x in "0123456789abcdefABCDEF" for x in c)

    def brillo(c):
        r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255

    for clave in ("color", "alternateColor"):
        c = t.get(clave)
        if hex_ok(c) and brillo(c) >= 0.2:
            return "#" + c
    return "#4f46e5"


@st.cache_data(ttl=3600, show_spinner=False)
def _equipos():
    datos = _json(nba.BASE + "/teams") or {}
    out = []
    for liga in (datos.get("sports") or [{}])[0].get("leagues", []):
        for t in liga.get("teams", []):
            t = t.get("team", {})
            logos = t.get("logos") or [{}]
            out.append({"id": str(t.get("id")), "abbr": t.get("abbreviation", ""), "nombre": t.get("displayName", ""),
                        "logo": logos[0].get("href", ""), "color": _color_equipo(t)})
    return sorted(out, key=lambda e: e["nombre"])


def _pts(competidor):
    s = competidor.get("score")
    try:
        return int(float(s.get("value") if isinstance(s, dict) else s))
    except (TypeError, ValueError, AttributeError):
        return None


@st.cache_data(ttl=900, show_spinner=False)
def _eventos(team_id, temp, tipo):
    """Eventos crudos del calendario de un equipo (terminados y futuros) en una temporada y fase."""
    url = f"{nba.BASE}/teams/{team_id}/schedule" + (f"?season={temp}&seasontype={tipo}" if temp else "")
    datos = _json(url)
    if datos is None:   # una excepción no se guarda en caché: así un fallo no esconde partidos durante 15 min
        raise RuntimeError("ESPN no respondió")
    return datos.get("events", [])


def _ev(team_id, temp, tipo):
    try:
        return _eventos(team_id, temp, tipo)
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=900, show_spinner=False)
def _partidos(team_id, temporadas):
    """Partidos terminados del equipo, del más reciente al más antiguo."""
    juegos, vistos = [], set()
    fuentes = [(temp, tipo) for temp in temporadas for tipo in (2, 3)] + [(None, None)]  # 2 = regular, 3 = playoffs; al final, el calendario actual sin filtros
    for temp, tipo in fuentes:
        for ev in _ev(team_id, temp, tipo):
            if str(ev.get("id")) in vistos:
                continue
            comp = (ev.get("competitions") or [{}])[0]
            est = (comp.get("status") or ev.get("status") or {}).get("type") or {}
            if not (est.get("completed") or est.get("state") == "post"):
                continue
            vistos.add(str(ev.get("id")))
            mio = next((c for c in comp.get("competitors", []) if str((c.get("team") or {}).get("id")) == str(team_id)), None)
            rival = next((c for c in comp.get("competitors", []) if c is not mio), None)
            if not mio or not rival or _pts(mio) is None or _pts(rival) is None:
                continue
            juegos.append({"fecha": ev.get("date", ""), "evento": str(ev.get("id")), "sede": mio.get("homeAway"),
                           "rival": (rival.get("team") or {}).get("abbreviation", "?"), "rival_id": str((rival.get("team") or {}).get("id")),
                           "pf": _pts(mio), "pc": _pts(rival),
                           "per": int(((comp.get("status") or ev.get("status") or {}).get("period")) or 4)})
    juegos.sort(key=lambda g: g["fecha"], reverse=True)
    return juegos


def _limpio(x):
    """12.0 -> 12 (los enteros se muestran sin decimales); el resto queda igual."""
    return int(x) if isinstance(x, float) and x.is_integer() else x


def _porcentaje(hechos, intentos):
    return round(100 * hechos / intentos, 1) if hechos is not None and intentos else None


def _oreb(e):
    """Rebotes ofensivos del box score compacto (acepta los nombres de clave más comunes)."""
    for k in ("oreb", "orb", "oreb_", "reb_of", "rebo"):
        if e.get(k) is not None:
            return e.get(k)
    return None


def _stats_de_caja(caja):
    """{id de equipo: {clave: valor}} con las estadísticas que usan los mercados, sacadas del box score compacto
    (el mismo que usa nba_extra y que se guarda en disco: así cada partido se descarga una sola vez)."""
    res = {}
    cuartos = (caja or {}).get("cuartos") or {}
    for tid, e in ((caja or {}).get("equipos") or {}).items():
        d = {"tri": e.get("tpm"), "fgm": e.get("fgm"), "ftm": e.get("ftm"), "reb": e.get("reb"), "ast": e.get("ast"),
             "stl": e.get("stl"), "blk": e.get("blk"), "fta": e.get("fta"), "oreb": _oreb(e), "to": e.get("tov"), "fal": e.get("fal"),
             "paint": e.get("paint"), "fast": e.get("fb"),
             "fgp": _porcentaje(e.get("fgm"), e.get("fga")), "tpp": _porcentaje(e.get("tpm"), e.get("tpa")),
             "ftp": _porcentaje(e.get("ftm"), e.get("fta"))}
        for i, q in enumerate(cuartos.get(tid) or [], start=1):
            d[f"q{i}"] = q
        res[tid] = {k: _limpio(v) for k, v in d.items() if v is not None}
    return res


# ---------------------------------------------------------------------------
# Contexto del partido: local/visita, descanso, lesiones y ritmo
# ---------------------------------------------------------------------------
def _fecha_et(iso):
    """Fecha del partido en hora del este de EE. UU. (la fecha de calendario que usa la NBA); None si no se puede leer."""
    try:
        return pd.Timestamp(iso).tz_convert("America/New_York").date()
    except Exception:  # noqa: BLE001
        try:  # sin zona horaria: restar 6 h a UTC da la fecha correcta para cualquier horario de la NBA
            return (pd.Timestamp(iso) - pd.Timedelta(hours=6)).date()
        except Exception:  # noqa: BLE001
            return None


def _contexto_calendario(completos):
    """{evento: {"desc": días de descanso (0 = back-to-back) o None, "g7": partidos en los 7 días previos}}.

    Se calcula con el calendario completo del equipo, no solo con la ventana que se analiza.
    Si el partido anterior quedó a más de 10 días (receso o inicio de temporada), el descanso queda en None."""
    fechas = [(g["evento"], _fecha_et(g["fecha"])) for g in sorted(completos, key=lambda x: x["fecha"])]
    out = {}
    for i, (ev, d) in enumerate(fechas):
        if d is None:
            continue
        prev = fechas[i - 1][1] if i > 0 else None
        desc = (d - prev).days - 1 if prev else None
        if desc is not None and not 0 <= desc <= 10:
            desc = None
        out[ev] = {"desc": desc, "g7": sum(1 for _, x in fechas[:i] if x and 0 < (d - x).days <= 7)}
    return out


def _caja(evento):
    """Box score compacto (con caché en disco) o None si ESPN no lo entrega."""
    try:
        c = nba_extra.box_compacto(evento)
        return c if c and c.get("equipos") else None
    except Exception:  # noqa: BLE001
        return None


def _ritmo_y_eficiencia(caja, team_id, pf, pc, periodo):
    """(ritmo por 48 min, puntos por 100 posesiones, puntos recibidos por 100 posesiones) o None si faltan datos.

    Posesiones = tiros de campo intentados + 0.44 x tiros libres intentados - rebotes ofensivos + pérdidas;
    se promedian las del equipo y las del rival (misma fórmula de la sección de métricas avanzadas)."""
    if not caja:
        return None
    own = (caja.get("equipos") or {}).get(str(team_id))
    rivales = [v for k, v in (caja.get("equipos") or {}).items() if k != str(team_id)]
    if not own or not rivales:
        return None
    vals = [x for x in (nba_extra._posesiones(own), nba_extra._posesiones(rivales[0])) if not math.isnan(x)]
    if not vals:
        return None
    poss = sum(vals) / len(vals)
    if poss <= 0:
        return None
    minutos = 48 + 5 * max(0, (periodo or 4) - 4)  # con tiempo extra hay más posesiones: se lleva a 48 min
    return round(poss * 48 / minutos, 1), round(100 * pf / poss, 1), round(100 * pc / poss, 1)


def _marcar_estrellas(juegos, cajas, team_id):
    """Anota en cada partido qué estrellas faltaron (g['bajas']: None = sin datos, [] = nadie faltó).

    Estrella = los 2 máximos anotadores por partido de la ventana (con al menos un tercio de apariciones).
    Faltó = no aparece con minutos en el box score de ese partido. Si un jugador llegó por traspaso a mitad
    de la ventana, los partidos anteriores a su llegada cuentan como «falta»: es una aproximación."""
    tid, n = str(team_id), len(juegos)
    acum, presentes = {}, []
    for c in cajas:
        jug = [j for j in (c or {}).get("jugadores", []) if j.get("team_id") == tid and (j.get("MIN") or 0) > 0]
        if len(jug) < 5:  # box score incompleto: no se puede saber quién faltó
            presentes.append(None)
            continue
        presentes.append({j["id"] for j in jug})
        for j in jug:
            a = acum.setdefault(j["id"], {"nombre": j["Jugador"], "pts": 0.0, "pj": 0})
            a["pts"] += j.get("PTS") or 0
            a["pj"] += 1
    minimo = max(2, -(-n // 3))
    top = sorted(((a["pts"] / a["pj"], k) for k, a in acum.items() if a["pj"] >= minimo), reverse=True)[:2]
    estrellas = {k: acum[k]["nombre"] for _, k in top}
    for g, pres in zip(juegos, presentes):
        g["_estrellas"] = list(estrellas.values())
        g["bajas"] = None if pres is None else [nom for k, nom in estrellas.items() if k not in pres]


def _contexto_hoy(team_id, temporada, completos):
    """Próximo partido del equipo: rival, cuándo, días de descanso, partidos en los últimos 7 días y si es back-to-back."""
    prox = None
    for tipo in (2, 3):
        for ev in _ev(team_id, temporada, tipo):
            comp = (ev.get("competitions") or [{}])[0]
            if ((comp.get("status") or ev.get("status") or {}).get("type") or {}).get("state") not in ("pre", "in"):
                continue
            f = _fecha_et(ev.get("date", ""))
            if f is not None and (prox is None or f < prox[0]):
                prox = (f, ev, comp)
    if not prox:
        return None
    f, ev, comp = prox
    mio = next((c for c in comp.get("competitors", []) if str((c.get("team") or {}).get("id")) == str(team_id)), None)
    rival = next((c for c in comp.get("competitors", []) if c is not mio), None)
    if not mio or not rival:
        return None
    fechas = [x for x in (_fecha_et(g["fecha"]) for g in completos) if x and x < f]
    desc = (f - max(fechas)).days - 1 if fechas else None
    if desc is not None and desc > 10:
        desc = None
    hoy = pd.Timestamp.now(tz="America/New_York").date()
    dif = (f - hoy).days
    cuando = "hoy" if dif == 0 else "mañana" if dif == 1 else f.strftime("%d/%m")
    return {"etq": f'{"vs" if mio.get("homeAway") == "home" else "@"} {(rival.get("team") or {}).get("abbreviation", "?")}',
            "cuando": cuando, "desc": desc, "g7": sum(1 for x in fechas if 0 < (f - x).days <= 7),
            "b2b": desc == 0, "rival_id": str((rival.get("team") or {}).get("id")), "sede": mio.get("homeAway")}


@st.cache_data(ttl=60, show_spinner=False)
def _lesiones_espn(minuto):
    """Lesionados de TODOS los equipos directo de ESPN: {id_equipo: [{Jugador, Estado, Lesión}]}.

    Se vuelve a pedir como máximo cada 60 s (`minuto` cambia cada minuto y fuerza la renovación). Si ESPN falla se lanza
    una excepción, así que un fallo nunca queda guardado en memoria y la siguiente visita lo reintenta."""
    datos = _json(nba.BASE + "/injuries")
    if not datos or "injuries" not in datos:
        raise RuntimeError("ESPN no entregó lesiones")
    out = {}
    for eq in datos.get("injuries") or []:
        lista = []
        for it in eq.get("injuries") or []:
            atleta = it.get("athlete") or {}
            nombre = atleta.get("displayName") or atleta.get("fullName")
            if not nombre:
                continue
            det = it.get("details") or {}
            lesion = " ".join(x for x in (det.get("side"), det.get("type"), det.get("detail")) if x) or it.get("shortComment") or ""
            lista.append({"Jugador": nombre, "Estado": it.get("status") or (it.get("type") or {}).get("description") or "?",
                          "Lesión": lesion})
        out[str(eq.get("id"))] = lista
    return out


def _bajas_hoy(team_id, nombre):
    """Lesionados del equipo: lista de dicts, [] si no hay, None si no se pudo leer.

    Primero se pide la lista fresca a ESPN (renovada cada minuto); si falla, se usa la sección de lesiones de nba_extra."""
    try:
        todas = _lesiones_espn(int(pd.Timestamp.now().timestamp() // 60))
        return todas.get(str(team_id), [])
    except Exception:  # noqa: BLE001
        pass
    try:
        df = nba_extra.lesiones()
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty:
        return []
    return df[df["Equipo"] == nombre].to_dict("records")


def _html_hoy(ctx, estrellas):
    """Bloque «hoy» de la tarjeta: calendario del próximo partido y bajas."""
    if not ctx:
        return ""
    lineas = []
    h = ctx.get("hoy")
    if h:
        d = "sin dato" if h["desc"] is None else f'{h["desc"]} día{"s" if h["desc"] != 1 else ""} de descanso'
        tag = '<span class="tag">BACK-TO-BACK</span>' if h["b2b"] else ""
        lineas.append(f'📅 <b>Próximo ({_e(h["cuando"])}):</b> {_e(h["etq"])} · {d} · {h["g7"]} partido{"s" if h["g7"] != 1 else ""} en los últimos 7 días{tag}')
    bajas = ctx.get("bajas")
    if bajas is None:
        lineas.append("🩹 <b>Bajas:</b> no se pudieron leer las lesiones ahora.")
    elif not bajas:
        lineas.append("🩹 <b>Bajas:</b> ESPN no reporta lesionados.")
    else:
        est = {normalizar(x) for x in estrellas}
        bajas = sorted(bajas, key=lambda b: (str(b.get("Estado")).lower() != "out", str(b.get("Jugador"))))
        chips = "".join(
            f'<span class="chip{"" if str(b.get("Estado")).lower() == "out" else " dud"}" title="{_e(str(b.get("Lesión") or ""))}">'
            f'{"⭐ " if normalizar(b.get("Jugador", "")) in est else ""}{_e(str(b.get("Jugador")))} · {_e(str(b.get("Estado")))}</span>'
            for b in bajas[:10])
        mas = f" (+{len(bajas) - 10} más)" if len(bajas) > 10 else ""
        lineas.append(f'🩹 <b>Bajas ({len(bajas)}):</b> {chips}{mas}')
    return f'<div class="fl-hoy">{"<br>".join(lineas)}</div>' if lineas else ""


class _SerieIncompleta(Exception):
    """Falló alguna descarga: la serie no se guarda en memoria (así se reintenta en el siguiente cambio) pero se puede usar."""

    def __init__(self, serie):
        super().__init__("serie incompleta")
        self.serie = serie


def _calcular_serie(team_id, temporadas, n, rival_id, sin_ot=False):
    """Calcula la serie. Devuelve (partidos, completa); completa=False si algún box score no se pudo leer."""
    todos = _partidos(team_id, temporadas)
    calendario = _contexto_calendario(todos)  # descanso y carga de partidos con el calendario completo
    if rival_id:  # solo los partidos contra ese rival (enfrentamientos directos)
        todos = [g for g in todos if g["rival_id"] == str(rival_id)]
    if sin_ot:    # solo partidos que terminaron en los 4 cuartos; se siguen tomando n (los n más recientes sin tiempo extra)
        todos = [g for g in todos if (g.get("per") or 4) <= 4]
    ultimos = list(reversed(todos[:n]))
    with ThreadPoolExecutor(max_workers=8) as pool:
        cajas = list(pool.map(lambda g: _caja(g["evento"]), ultimos))
    tri = [_stats_de_caja(c) for c in cajas]
    _marcar_estrellas(ultimos, cajas, team_id)
    for g, t, caja in zip(ultimos, tri, cajas):
        g["total"] = g["pf"] + g["pc"]
        g["margen"] = g["pf"] - g["pc"]
        g["ot"] = (g.get("per") or 4) > 4       # fue a tiempo extra (los puntos del partido lo incluyen; los cuartos no)
        mio, riv = t.get(str(team_id)) or {}, t.get(g["rival_id"]) or {}
        for clave, valor in mio.items():
            g[clave] = valor
        for k in (1, 2, 3, 4):                     # cuartos: puntos del equipo, total y diferencia
            a, b = mio.get(f"q{k}"), riv.get(f"q{k}")
            if a is not None and b is not None:
                g[f"pq{k}"], g[f"tq{k}"], g[f"gq{k}"] = a, a + b, a - b
        for h, (qa, qb) in {1: (1, 2), 2: (3, 4)}.items():             # tiempos: cuartos 1+2 y 3+4 (no incluyen tiempo extra)
            if all(g.get(f"pq{q}") is not None and g.get(f"tq{q}") is not None for q in (qa, qb)):
                g[f"th{h}"] = g[f"tq{qa}"] + g[f"tq{qb}"]                # total, ambos equipos
                g[f"ph{h}"] = g[f"pq{qa}"] + g[f"pq{qb}"]                # puntos del equipo
                g[f"gh{h}"] = g[f"gq{qa}"] + g[f"gq{qb}"]                # diferencia del equipo
        dos_a = mio["fgm"] - mio["tri"] if mio.get("fgm") is not None and mio.get("tri") is not None else None
        dos_b = riv["fgm"] - riv["tri"] if riv.get("fgm") is not None and riv.get("tri") is not None else None
        if dos_a is not None:
            g["dos"] = dos_a
        if dos_a is not None and dos_b is not None:
            g["g2"] = dos_a - dos_b
        if mio.get("ftm") is not None and riv.get("ftm") is not None:
            g["gft"] = mio["ftm"] - riv["ftm"]
        for clave, valor in riv.items():           # lo que hizo el rival en ese partido (r_…): sirve para saber qué permite cada equipo
            g[f"r_{clave}"] = valor
        if dos_b is not None:
            g["r_dos"] = dos_b
        for h, (qa, qb) in {1: (1, 2), 2: (3, 4)}.items():
            if riv.get(f"q{qa}") is not None and riv.get(f"q{qb}") is not None:
                g[f"r_ph{h}"] = riv[f"q{qa}"] + riv[f"q{qb}"]
        g["etq"] = f'{"vs" if g["sede"] == "home" else "@"} {g["rival"]}'
        g["dia"] = _fecha_et(g["fecha"])
        r = _ritmo_y_eficiencia(caja, team_id, g["pf"], g["pc"], g.get("per"))
        if r:
            g["ritmo"], g["ortg"], g["drtg"] = r
        c = calendario.get(g["evento"]) or {}
        g["desc"], g["g7"] = c.get("desc"), c.get("g7")
    completa = all(t.get(str(team_id)) for t in tri) and all(c is not None for c in cajas)
    return ultimos, completa


@st.cache_data(ttl=900, show_spinner=False)
def _serie_guardada(team_id, temporadas, n, rival_id, sin_ot):
    serie, completa = _calcular_serie(team_id, temporadas, n, rival_id, sin_ot)
    if not completa:
        raise _SerieIncompleta(serie)   # las excepciones no se guardan en caché
    return serie


def _serie_equipo(team_id, temporadas, n=10, rival_id=None, sin_ot=False):
    """Últimos n partidos (del más antiguo al más reciente) con puntos, total, margen y estadísticas del boxscore.

    El resultado se guarda 15 min en memoria: cambiar la línea, el lado o el mercado no vuelve a calcular nada.
    Si alguna descarga falló, se devuelve igual pero sin guardarlo, para que el próximo cambio lo reintente."""
    try:
        return _serie_guardada(team_id, tuple(temporadas), n, rival_id, bool(sin_ot))
    except _SerieIncompleta as e:
        return e.serie


# ---------------------------------------------------------------------------
# Tarjeta
# ---------------------------------------------------------------------------
def _cuando(g):
    """' · 09/11/26 · 111-122' (fecha en hora del este y marcador pf-pc) para el texto que sale al pasar el mouse."""
    d = g.get("dia")
    return (f" · {d:%d/%m/%y}" if d else "") + f' · {g["pf"]}-{g["pc"]}'


def _medio(x):
    return round(x * 2) / 2


@dataclass
class Estadisticas:
    """Números de una tarjeta, sin HTML. Los calcula _estadisticas y los pinta _html_tarjeta."""
    n: int            # partidos con dato
    k: int            # cuántos cumplen la línea
    pct: int
    cumple: list      # un bool por partido
    margenes: list    # cuánto cumplió (+) o falló (−) cada partido respecto a la línea
    mm: float         # margen medio
    mu: float         # promedio
    mu_p: float       # promedio ponderado (los partidos recientes pesan más)
    sd: float
    escala: float
    lo: float         # límites del eje de las barras
    hi: float
    direc: int        # hacia qué lado se apuesta (+1 / −1)
    tendencia: tuple  # (flecha, diferencia) o None si hay menos de 6 partidos
    justa: float      # línea que deja el promedio ponderado en el centro
    prob: int         # probabilidad estimada (%) o None si no hay variación


def _estadisticas(vals, umbral, lado, modo):
    """Cuenta cuántos valores cumplen la línea y calcula promedio, variación, tendencia, línea justa y probabilidad."""
    n = len(vals)
    cumple = [v > umbral for v in vals] if modo == "handicap" or lado == "Más de" else [v < umbral for v in vals]
    k = sum(cumple)
    todos = vals + [umbral]
    lo = 0 if min(todos) >= 0 else min(todos) - 2
    hi = max(todos) * 1.08 + 0.5
    if hi <= lo:
        hi = lo + 1
    direc = -1 if (modo != "handicap" and lado == "Menos de") else 1       # hacia qué lado se apuesta
    margenes = [direc * (v - umbral) for v in vals]
    sd = stdev(vals) if n > 1 else 0.0
    pesos = [0.9 ** (n - 1 - i) for i in range(n)]                          # el partido más reciente pesa 1; cada anterior, 10 % menos
    mu, mu_p = mean(vals), sum(p * v for p, v in zip(pesos, vals)) / sum(pesos)
    tendencia = None                                                         # último tercio contra el resto
    if n >= 6:
        k3 = max(3, n // 3)
        delta = mean(vals[-k3:]) - mean(vals[:-k3])
        tendencia = ("↑" if delta > 0.25 * sd else "↓" if delta < -0.25 * sd else "→", delta)
    prob = None                                                              # distribución normal con el promedio ponderado
    if sd > 0:
        cdf = 0.5 * (1 + math.erf(((umbral - mu_p) / sd) / math.sqrt(2)))
        prob = round(100 * ((1 - cdf) if direc == 1 else cdf))
    return Estadisticas(n=n, k=k, pct=round(100 * k / n), cumple=cumple, margenes=margenes, mm=mean(margenes), mu=mu, mu_p=mu_p,
                        sd=sd, escala=1.5 * sd or 1.0, lo=lo, hi=hi, direc=direc, tendencia=tendencia,
                        justa=_medio(mu_p), prob=prob)


# ---------------------------------------------------------------------------
# HTML de la tarjeta (solo presentación: todos los números llegan ya calculados)
# ---------------------------------------------------------------------------
def _tile(rotulo, valor, clase="", ayuda=""):
    return f'<div class="fl-st" title="{_e(ayuda)}"><small>{rotulo}</small><b class="{clase}">{valor}</b></div>'


def _marcas_juego(g):
    """(HTML de los puntos, texto para el tooltip) de back-to-back y estrellas ausentes en ese partido."""
    a, r = g.get("desc") == 0, bool(g.get("bajas"))
    dos = " dos" if a and r else ""
    html = (f'<i class="mk a{dos}"></i>' if a else "") + (f'<i class="mk r{dos}"></i>' if r else "")
    texto = (" · back-to-back" if a else "") + (f' · sin {", ".join(g["bajas"])}' if r else "") + (" · tiempo extra" if g.get("ot") else "")
    return html, texto


def _nombre_rival(g):
    """Nombre completo del rival de un partido (p. ej. «Indiana Pacers»); si no se encuentra, su sigla."""
    try:
        nombres = {e["id"]: e["nombre"] for e in _equipos()}
    except Exception:
        nombres = {}
    return nombres.get(str(g.get("rival_id"))) or g.get("rival") or "?"


def _tip_barra(g, v, c, m, fmt, i, n):
    """Ficha que aparece al pasar el mouse por una barra (solo CSS): partido, valor, si cumplió y el contexto."""
    borde = max(1, n // 4)
    pos = " izq" if i < borde else " der" if i >= n - borde else ""   # en los extremos se ancla al borde para no salirse de la tarjeta
    chips = ["🏠 Local" if g.get("sede") == "home" else "✈️ Visita"]
    if g.get("desc") == 0:
        chips.append("⏱️ Back-to-back")
    if g.get("bajas"):
        chips.append("🩹 Sin " + ", ".join(_e(x) for x in g["bajas"]))
    if g.get("ot"):
        chips.append("⏳ Tiempo extra")
    return (f'<span class="fx-tip{pos}"><span class="fx-tip-t">{"vs" if g.get("sede") == "home" else "@"} {_e(_nombre_rival(g))}</span>'
            f'<span class="fx-tip-f">{_e(_cuando(g).lstrip(" ·"))}</span>'
            f'<span class="fx-tip-v">{fmt(v)}</span>'
            f'<span class="fx-tip-r {"ok" if c else "no"}">{"✅ Cumple" if c else "❌ No cumple"} · {m:+.1f} vs la línea</span>'
            f'<span class="fx-tip-c">{" · ".join(chips)}</span></span>')


def _html_barras(juegos, vals, est, umbral, signo):
    """Una barra por partido (verde = cumplió la línea), con sus marcas de back-to-back, estrella ausente y tiempo extra."""
    fmt = (lambda v: format(v, "+g")) if signo else (lambda v: format(v, "g"))
    marcas = [_marcas_juego(g) for g in juegos]
    n = len(juegos)
    return "".join(
        f'<div class="fl-b {"ok" if c else ""}{" ot" if g.get("ot") else ""}{" vis" if g.get("sede") == "away" else " loc" if g.get("sede") == "home" else ""}" '
        f'aria-label="{_e(g["etq"])}: {fmt(v)}" '
        f'style="height:{max((v - est.lo) / (est.hi - est.lo) * 100, 7):.0f}%;animation-delay:{min(i * .04, .6):.2f}s'
        f'{";opacity:%.2f" % (0.55 + 0.45 * min(1, m / est.escala)) if c else ""}">{fmt(v)}{mh}'
        f'{_tip_barra(g, v, c, m, fmt, i, n)}</div>'
        for i, (v, c, g, m, (mh, mt)) in enumerate(zip(vals, est.cumple, juegos, est.margenes, marcas)))


def _html_estadisticas(est, modo):
    tend = f"{est.tendencia[0]} {est.tendencia[1]:+.1f}" if est.tendencia else "—"
    justa_txt = f"{-est.justa + 0:+g}" if modo == "handicap" else f"{est.justa:g}"
    prob_txt = f"{est.prob}%" if est.prob is not None else "—"
    return "".join([
        _tile("Margen medio vs línea", f"{est.mm:+.1f}", "pos" if est.mm > 0 else "neg" if est.mm < 0 else "",
              "Promedio de cuánto se pasó (+) o se quedó corto (−) de la línea."),
        _tile("Promedio", f"{est.mu:.1f}"),
        _tile("Ponderado", f"{est.mu_p:.1f}", "", "Los partidos recientes pesan más (cada partido anterior vale 10 % menos)."),
        _tile("Variación (±)", f"{est.sd:.1f}", "", "Desviación estándar: qué tan irregulares son sus resultados."),
        _tile("Tendencia", tend, "", "Promedio del último tercio de partidos menos el del resto."),
        _tile("Línea justa", justa_txt, "", "Línea que dejaría el promedio ponderado en el centro."),
        _tile("Prob. estimada", prob_txt, "", "Probabilidad de cumplir la línea si los resultados siguen una distribución normal "
                                              "con su promedio ponderado y su variación. Es una estimación, no una garantía."),
    ])


def _html_contexto(juegos, ventana, cumple):
    """(bloque «Contexto del partido», estrellas de la ventana): cómo cumplió la línea según sede, descanso y estrellas, más ritmo."""
    def _frac(sel):
        idx = [i for i, x in enumerate(sel) if x]
        if not idx:
            return None
        kk = sum(cumple[i] for i in idx)
        p = round(100 * kk / len(idx))
        return f"{kk}/{len(idx)} · {p}%", "pos" if p >= 50 else "neg", len(idx)

    grupos = []
    if any(g.get("desc") == 0 for g in juegos):
        grupos += [("⏱️ Back-to-back", [g.get("desc") == 0 for g in juegos], "Partidos jugados sin día de descanso."),
                   ("😴 Con descanso", [(g.get("desc") or 0) > 0 for g in juegos], "Partidos con al menos un día de descanso.")]
    estrellas = (ventana[-1].get("_estrellas") or []) if ventana else []
    if any(g.get("bajas") for g in juegos):
        quienes = ", ".join(estrellas)
        grupos += [("🩹 Sin estrella", [bool(g.get("bajas")) for g in juegos],
                    f"Partidos en que faltó alguna de las 2 estrellas de la ventana ({quienes}). Se detecta porque no aparece en el box score."),
                   ("⭐ Con estrellas", [g.get("bajas") == [] for g in juegos], "Partidos con las 2 estrellas en cancha.")]
    tiles, chico = [], False
    for rot, sel, ayuda in grupos:
        f = _frac(sel)
        if f:
            tiles.append(_tile(rot, f[0], f[1], ayuda))
            chico = chico or f[2] < 3
    ritmo = {k: [g[k] for g in ventana if g.get(k) is not None] for k in ("ritmo", "ortg", "drtg")}
    if ritmo["ritmo"]:
        tiles += [
            _tile("Ritmo (pos/48)", f'{mean(ritmo["ritmo"]):.1f}', "", "Posesiones por 48 minutos (tiros de campo + 0.44 × tiros libres − rebotes ofensivos + pérdidas). "
                                                                      "Más posesiones = más oportunidades de anotar para los dos equipos."),
            _tile("Ataque (pts/100 pos)", f'{mean(ritmo["ortg"]):.1f}', "", "Puntos anotados por cada 100 posesiones: mide la eficiencia, sin importar el ritmo."),
            _tile("Defensa (pts rec./100)", f'{mean(ritmo["drtg"]):.1f}', "", "Puntos recibidos por cada 100 posesiones (menos es mejor).")]
    bloque = (f'<div class="fl-sub">Contexto del partido</div><div class="fl-stats">{"".join(tiles)}</div>' if tiles else "")
    if chico:
        bloque += '<div class="fl-aviso">⚠️ Algún grupo tiene menos de 3 partidos: su porcentaje no es confiable.</div>'
    return bloque, estrellas


def _html_leyenda(juegos):
    items = ([("a", "back-to-back")] if any(g.get("desc") == 0 for g in juegos) else []) \
        + ([("r", "faltó una estrella")] if any(g.get("bajas") for g in juegos) else []) \
        + ([("o", "tiempo extra")] if any(g.get("ot") for g in juegos) else [])
    return ('<div class="fl-leyenda">Marcas en las barras:' + "".join(f'<i class="{c}"></i>{t}' for c, t in items) + '</div>') if items else ""


def _por_sede(juegos, vals, cumple):
    """{sede: (veces que cumplió, partidos, promedio)} separando partidos de local («home») y de visita («away»)."""
    out = {}
    for sede in ("home", "away"):
        idx = [i for i, g in enumerate(juegos) if g.get("sede") == sede]
        if idx:
            out[sede] = (sum(cumple[i] for i in idx), len(idx), mean(vals[i] for i in idx))
    return out


def _pct_sede(d, sede):
    return round(100 * d[sede][0] / d[sede][1])


def _celda_sede(icono, nombre, dato, signo, top=False, marca=""):
    if not dato:
        return f'<div class="fx-sede vacio"><span class="fx-t">{icono} {nombre}</span><em>sin partidos</em></div>'
    k, n, m = dato
    p = round(100 * k / n)
    prom = f"{m:+.1f}" if signo else f"{m:.1f}"
    poco = '<small class="fx-poco">⚠️ pocos partidos</small>' if n < 3 else ""
    return (f'<div class="fx-sede {"si" if p >= 50 else "no"}{" top" if top else ""}">'
            f'<span class="fx-t">{icono} {nombre}{marca}</span><b>{k}/{n}</b>'
            f'<div class="fx-bar"><i style="width:{p}%"></i></div>'
            f'<small>{p}% · promedio {prom}</small>{poco}</div>')


def _html_fallos(juegos, vals, cumple, signo, titulo, ok_txt, maximo=10):
    """Lista de rivales contra los que NO se cumplió la línea (el más reciente primero), con el valor de ese partido."""
    fmt = (lambda v: format(v, "+g")) if signo else (lambda v: format(v, "g"))
    fallos = [(g, v) for g, v, c in zip(juegos, vals, cumple) if not c][::-1]
    if not fallos:
        return f'<div class="fx-fallos ok">✅ {ok_txt}</div>'
    chips = "".join(
        f'<span class="fx-chip no" title="{_e(_nombre_rival(g))}{_e(_cuando(g))}">'
        f'{"vs" if g.get("sede") == "home" else "@"} {_e(g.get("rival") or "?")} · {fmt(v)}</span>'
        for g, v in fallos[:maximo])
    mas = f'<span class="fx-chip">+{len(fallos) - maximo} más</span>' if len(fallos) > maximo else ""
    return (f'<div class="fx-fallos"><div class="fx-fallos-t">❌ {titulo} <em>({len(fallos)} de {len(vals)})</em></div>'
            f'<div class="fx-chips">{chips}{mas}</div></div>')


def _html_sede(juegos, vals, cumple, signo):
    """Bloque «Local vs visita»: cuántas veces se cumple la línea en cada sede y dónde rinde mejor."""
    d = _por_sede(juegos, vals, cumple)
    if not d:
        return ""
    mejor = None
    if len(d) == 2:
        ph, pa = _pct_sede(d, "home"), _pct_sede(d, "away")
        if abs(ph - pa) >= 15:
            mejor = "home" if ph > pa else "away"
            veredicto = (f'{"🏠 Se cumple más de local" if mejor == "home" else "✈️ Se cumple más de visita"} '
                         f'({max(ph, pa)}% vs {min(ph, pa)}%)')
        else:
            veredicto = f"Rinde parecido en casa y de visita ({ph}% · {pa}%)"
    else:
        veredicto = "Solo hay partidos de una sede en esta ventana"
    return (f'<div class="fx-titulo"><span>Local vs visita</span><em>{veredicto}</em></div>'
            f'<div class="fx-sedes">{_celda_sede("🏠", "Local", d.get("home"), signo, mejor == "home")}'
            f'{_celda_sede("✈️", "Visita", d.get("away"), signo, mejor == "away")}</div>'
            f'<div class="fx-nota">En las barras, <b>L</b> = partido de local y <b>V</b> = de visita.</div>')


# Qué dato del partido del RIVAL equivale a «lo que permite» frente a la estadística del equipo.
#   "permite": lo que el rival deja hacer a sus oponentes (su dato «r_…» = lo que hizo el contrario en sus partidos)
#   "ataca":   la estadística es algo que el equipo concede (puntos recibidos…): se compara con lo que el rival logra
#   "comun":   dato del partido entero (total, ritmo): se mira cómo salen los partidos del rival
def _campo_permitido(campo):
    """(campo que se lee en los partidos del rival, signo, tipo)."""
    if campo in ("total", "ritmo") or campo[:2] in ("tq", "th"):
        return campo, 1, "comun"
    if campo == "pf":
        return "pc", 1, "permite"
    if campo == "pc":
        return "pf", 1, "ataca"
    if campo == "ortg":
        return "drtg", 1, "permite"
    if campo == "drtg":
        return "ortg", 1, "ataca"
    if campo in ("margen", "gft", "g2") or campo[:2] in ("gq", "gh"):
        return campo, -1, "permite"     # una diferencia a favor del equipo es una diferencia en contra del rival
    if campo[:2] == "pq":
        return f"r_q{campo[2:]}", 1, "permite"
    if campo[:2] == "ph":
        return f"r_ph{campo[2:]}", 1, "permite"
    return f"r_{campo}", 1, "permite"


def _frase_rival(tipo, modo, mas, k, n, r, lin, etiqueta, hand):
    """Frase completa: qué condición se midió en los partidos del rival y cuántas veces se dio."""
    cuenta = f"en {k} de {n} partidos"
    sup = "superó" if mas else "quedó bajo"
    if modo == "handicap":
        return f"{cuenta} de {r}, su rival habría cubierto el hándicap de {hand:+g}"
    if modo == "ganador":
        return f"{cuenta} de {r}, su rival cumplió «{etiqueta}»"
    if tipo == "permite":
        return f"{cuenta} de {r}, su rival {sup} {lin} en «{etiqueta}»"
    if tipo == "ataca":
        return f"{cuenta}, {r} {sup} {lin} con su propio ataque"
    return f"{cuenta} de {r}, «{etiqueta}» {sup} {lin}"


_VEREDICTOS_RIVAL = ("A favor", "Parejo", "En contra")


def _html_permite(est, mercado, umbral, lado, rival, etiqueta="", hand=None):
    """Bloque del rival: repite la MISMA condición de la tarjeta sobre los últimos partidos del rival."""
    campo, signo, tipo = _campo_permitido(mercado.campo)
    r = rival["abbr"]
    jr = [g for g in rival["juegos"] if g.get(campo) is not None]
    titulo = f"🆚 Rival: {_e(r)} frente a esta línea"
    if len(jr) < 3:
        return (f'<div class="fx-permite medio"><div class="fx-p-cab"><span>{titulo}</span></div>'
                f'<div class="fx-p-nota">No hay datos suficientes de {_e(r)} para esta estadística.</div></div>')
    vr = [signo * g[campo] for g in jr]
    mas = mercado.tipo == "handicap" or lado == "Más de"
    cr = [v > umbral for v in vr] if mas else [v < umbral for v in vr]
    n, k = len(vr), sum(cr)
    pr = round(100 * k / n)
    nivel = "ok" if pr >= 60 else "no" if pr <= 40 else "medio"
    veredicto = _VEREDICTOS_RIVAL[("ok", "medio", "no").index(nivel)]
    cumple = est.pct >= 50
    if nivel == "medio":
        cruce = f"{_e(r)} queda en el medio: no confirma ni contradice la línea."
    elif cumple and nivel == "ok":
        cruce = f"✅ Coinciden: el equipo cumple la línea y los partidos de {_e(r)} van en la misma dirección."
    elif cumple:
        cruce = f"⚠️ Se contradicen: el equipo cumple la línea, pero los partidos de {_e(r)} van en contra."
    elif nivel == "ok":
        cruce = f"El equipo no la cumple seguido, pero los partidos de {_e(r)} sí van en esa dirección."
    else:
        cruce = f"❌ Coinciden en contra: ni el equipo ni los partidos de {_e(r)} cumplen la línea."
    mu = mean(vr)
    lin = f"{abs(umbral):g}"
    frase = _frase_rival(tipo, mercado.tipo, mas, k, n, _e(r), lin, _e(etiqueta), hand)
    if mercado.tipo == "over":
        detalle = f"Promedio de {_e(r)} en esto: {mu:.1f} (línea {lin})"
    else:
        detalle = f"Diferencia promedio: {mu:+.1f}"
    d = _por_sede(jr, vr, cr)
    chips = ""
    for sede, icono, nombre in (("home", "🏠", "en casa"), ("away", "✈️", "de visita")):
        if sede in d:
            kk, nn, _ = d[sede]
            hoy = " hoy" if rival.get("sede") == sede else ""
            marca = " · hoy juega así" if rival.get("sede") == sede else ""
            chips += f'<span class="fx-chip{hoy}">{icono} {_e(r)} {nombre}: {kk} de {nn}{marca}</span>'
    nota = f'<div class="fx-p-nota">{_e(rival["nota"])}</div>' if rival.get("nota") else ""
    return (f'<div class="fx-permite {nivel}"><div class="fx-p-cab"><span>{titulo}</span><em>{veredicto}</em></div>'
            f'<div class="fx-p-cuerpo"><b>{pr}%</b><span>Se dio {frase}.<br>{detalle}</span></div>'
            f'<div class="fx-chips">{chips}</div>'
            f'{_html_fallos(jr, vr, cr, mercado.tipo != "over", f"No se dio contra (partidos de {_e(r)})", f"Se dio contra todos los rivales de {_e(r)}.")}'
            f'<div class="fx-p-cruce">{cruce}</div>{nota}</div>')


def _html_tarjeta(eq, juegos, ventana, vals, est, mercado, umbral, lado, etiqueta, hand, h2h, ctx, rival=None):
    """Arma la tarjeta con los números de `est`. `juegos` y `vals` son los partidos que tienen dato de este mercado."""
    n, k, pct = est.n, est.k, est.pct
    modo, clave = mercado.tipo, mercado.campo
    barras = _html_barras(juegos, vals, est, umbral, signo=modo != "over")
    bloque_ctx, estrellas = _html_contexto(juegos, ventana, est.cumple)
    leyenda = _html_leyenda(juegos)
    aviso = f'<div class="fl-aviso">⚠️ Muestra pequeña ({n} partidos): tómalo con cautela.</div>' if n < 8 else ""
    denso = " denso" if n > 10 else ""
    # con muchos partidos las etiquetas de rival no caben: quedan en el texto que sale al pasar el mouse
    riv = ('<div class="fl-riv' + denso + '">' + "".join(f'<span>{_e(g["etq"])}</span>' for g in juegos) + "</div>") if n <= 15 else ""
    ventana_txt = f"{n} enfrentamientos directos" if h2h else f"últimos {n} partidos"
    if modo == "ganador":
        tag, grande = mercado.tag, mercado.grande
        resumen = f"{mercado.verbo} {k} de {n}"
    elif modo == "handicap":
        tag, grande = "HÁNDICAP", f"{hand:+g}"
        resumen = f"Cubrió el hándicap en {k} de {n}"
    else:
        tag, grande = lado.upper(), f"{abs(umbral):g}"   # puntos/triples nunca llevan signo
        resumen = f'{"Superó" if lado == "Más de" else "Quedó bajo"} la línea en {k} de {n}'
    clase = "si" if pct >= 50 else "no"
    sedes = _html_sede(juegos, vals, est.cumple, signo=modo != "over")
    sedes += _html_fallos(juegos, vals, est.cumple, signo=modo != "over", titulo="No se cumplió contra",
                          ok_txt="Se cumplió contra todos los rivales de esta ventana.")
    permite = _html_permite(est, mercado, umbral, lado, rival, etiqueta, hand) if rival else ""
    return f"""
<div class="fl eq" style="--tc:{_e(eq.get('color') or '#4f46e5')}">
  <img class="fl-logo" src="{_e(eq['logo'])}" alt="">
  <div class="fl-nombre">{_e(eq['nombre'])}</div>
  <div class="fl-ctx">{_e(etiqueta)} · {ventana_txt}</div>
  <div class="fl-fila fx-fila">
    <div><div class="fl-tag {clase}">{tag}</div><div class="fl-linea">{grande}</div></div>
    <div class="fx-anillo {clase}" style="--p:{pct};--n:{pct}" role="img" aria-label="{pct}% ({k} de {n})"><i></i><b><span class="fx-num"></span><small>{k} de {n}</small></b></div>
  </div>
  <div class="fx-resumen {'v' if pct >= 50 else 'r'}">{resumen}</div>
  <div class="fl-barras{denso}"><div class="corte" style="bottom:{(umbral - est.lo) / (est.hi - est.lo) * 100:.1f}%"></div>{barras}</div>
  {riv}{leyenda}{sedes}{permite}{_html_hoy(ctx, estrellas)}
  <div class="fl-stats">{_html_estadisticas(est, modo)}</div>{bloque_ctx}{aviso}
</div>""".replace("$", "&#36;")


def _tarjeta(eq, juegos, mercado, umbral, lado, etiqueta, hand=None, h2h=False, ctx=None, rival=None):
    """HTML de una tarjeta. `mercado` es un Mercado: su tipo decide si es 'over' (más/menos de umbral), 'handicap'
    (margen + hándicap > 0) o 'ganador'.

    ctx = {"hoy": próximo partido, "bajas": lesionados} (opcional, ver _contexto_hoy y _bajas_hoy).
    rival = {"nombre", "abbr", "juegos", "sede", "nota"} (opcional): sus partidos recientes, para ver si permite la línea."""
    ventana = juegos  # todos los partidos de la ventana, aunque alguno no tenga dato de este mercado
    clave = mercado.campo
    con_dato = [g for g in juegos if g.get(clave) is not None]
    if not con_dato:
        return f'<div class="fl eq"><div class="fl-nombre">{_e(eq["nombre"])}</div><div class="fl-ctx">Sin datos de {etiqueta.lower()}.</div></div>'
    vals = [g[clave] for g in con_dato]
    est = _estadisticas(vals, umbral, lado, mercado.tipo)
    return _html_tarjeta(eq, con_dato, ventana, vals, est, mercado, umbral, lado, etiqueta, hand, h2h, ctx, rival)


def _armar_rival(otro, serie_otro, ctx, por_id, temporadas, n, sin_ot):
    """Datos del rival para el bloque «¿lo permite?».

    `otro` es el otro equipo elegido (comparación o cruce directo); si no hay, se usa el rival del próximo partido."""
    prox = (ctx or {}).get("hoy")
    if otro:
        r, serie = otro, serie_otro
    elif prox and prox.get("rival_id") in por_id:
        r = por_id[prox["rival_id"]]
        serie = _serie_equipo(r["id"], temporadas, n, sin_ot=sin_ot)
    else:
        return None
    if not serie:
        return None
    sede = None
    if prox and prox.get("rival_id") == r["id"]:
        sede = "away" if prox.get("sede") == "home" else "home"   # el rival juega en la sede contraria
    return {"nombre": r["nombre"], "abbr": r["abbr"] or r["nombre"][:3], "juegos": serie, "sede": sede,
            "nota": f'Próximo partido ({prox["cuando"]}): {prox["etq"]}' if sede else ""}


_CSS_MEJORAS = """
.fl.eq{--fx-ok:#4ade80;--fx-no:#f87171;--fx-mid:#fbbf24;--fx-mute:rgba(226,232,240,.62)}
.fl.eq .fx-fila{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:14px 0 6px}
.fx-anillo{position:relative;width:104px;height:104px;flex:none;--fx-c:var(--fx-ok)}
.fx-anillo.no{--fx-c:var(--fx-no)}
.fx-anillo i{position:absolute;inset:0;border-radius:50%;--fx-p:var(--p);animation:fx-llenar 1.1s cubic-bezier(.22,.8,.3,1) .1s both;
  background:conic-gradient(var(--fx-c) calc(var(--fx-p) * 1%),rgba(255,255,255,.09) 0);
  -webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 10px),#000 calc(100% - 9px));
  mask:radial-gradient(farthest-side,transparent calc(100% - 10px),#000 calc(100% - 9px));
  filter:drop-shadow(0 0 8px color-mix(in srgb,var(--fx-c) 45%,transparent))}
.fx-anillo b{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
  font-size:1.75rem;line-height:1;color:var(--fx-c);font-variant-numeric:tabular-nums}
.fx-anillo b small{display:block;margin-top:4px;font-size:.62rem;font-weight:600;letter-spacing:.04em;color:var(--fx-mute)}
.fx-resumen{margin:8px 0 4px;padding:7px 12px;border-radius:10px;font-size:.76rem;font-weight:700;letter-spacing:.03em;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.07);color:var(--fx-mute)}
.fx-resumen.v{color:var(--fx-ok);background:rgba(74,222,128,.09);border-color:rgba(74,222,128,.25)}
.fx-resumen.r{color:var(--fx-no);background:rgba(248,113,113,.09);border-color:rgba(248,113,113,.25)}
.fl.eq .fl-b{transition:filter .15s}
.fl.eq .fl-b:hover{filter:brightness(1.2)}
.fl.eq .fl-b.vis,.fl.eq .fl-b.loc{position:relative}
.fl.eq .fl-b.vis::before,.fl.eq .fl-b.loc::before{position:absolute;top:4px;left:50%;transform:translateX(-50%);width:16px;height:16px;
  display:flex;align-items:center;justify-content:center;border-radius:50%;font-size:.6rem;font-weight:800;line-height:1;color:#fff;
  text-shadow:none;pointer-events:none;writing-mode:horizontal-tb !important;text-orientation:mixed !important;box-shadow:0 1px 4px rgba(0,0,0,.45)}
.fl.eq .fl-b.loc::before{content:"L";background:#0284c7}
.fl.eq .fl-b.vis::before{content:"V";background:#ea580c}
.fl.eq .fl-b.ot::after{top:24px !important}
.fl.eq .fl-b.ot{outline:2px solid #a78bfa !important;outline-offset:1px;box-shadow:0 0 14px rgba(167,139,250,.65) !important}
.fl.eq .fl-b.ot::after{content:"OT";position:absolute;top:4px;left:50%;transform:translateX(-50%);padding:1px 6px;border-radius:99px;
  font-size:.58rem;font-weight:800;letter-spacing:.06em;line-height:1.3;color:#fff;background:#7c3aed;text-shadow:none;pointer-events:none;
  writing-mode:horizontal-tb !important;text-orientation:mixed !important}
.fx-titulo{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:4px 12px;margin:16px 0 8px;
  font-size:.7rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:var(--fx-mute)}
.fx-titulo em{font-style:normal;font-weight:700;letter-spacing:.02em;text-transform:none;color:#e2e8f0;font-size:.76rem}
.fx-sedes{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.fx-sede{display:grid;grid-template-columns:1fr auto;align-items:baseline;gap:2px 8px;padding:10px 12px 11px;border-radius:14px;
  background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.08)}
.fx-sede.top{border-color:rgba(74,222,128,.5);background:rgba(74,222,128,.08)}
.fx-sede.top.no{border-color:rgba(248,113,113,.5);background:rgba(248,113,113,.07)}
.fx-sede .fx-t{font-size:.68rem;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:var(--fx-mute)}
.fx-sede b{font-size:1.15rem;font-variant-numeric:tabular-nums;color:#f8fafc}
.fx-sede .fx-bar{grid-column:1 / -1;height:5px;margin-top:6px;border-radius:99px;background:rgba(255,255,255,.09);overflow:hidden}
.fx-sede .fx-bar i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#22c55e,#4ade80)}
.fx-sede.no .fx-bar i{background:linear-gradient(90deg,#ef4444,#f87171)}
.fx-sede small{grid-column:1 / -1;font-size:.7rem;color:var(--fx-mute)}
.fx-sede small.fx-poco{color:var(--fx-mid)}
.fx-sede.vacio{opacity:.55}
.fx-sede.vacio em{grid-column:1 / -1;font-style:normal;font-size:.72rem;color:var(--fx-mute)}
.fx-nota{margin-top:6px;font-size:.68rem;color:var(--fx-mute)}
.fx-permite{margin:16px 0 4px;padding:12px 14px;border-radius:14px;background:rgba(255,255,255,.045);
  border:1px solid rgba(255,255,255,.08);border-left:4px solid var(--fx-mid)}
.fx-permite.ok{border-left-color:var(--fx-ok);background:rgba(74,222,128,.06)}
.fx-permite.no{border-left-color:var(--fx-no);background:rgba(248,113,113,.06)}
.fx-p-cab{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:4px 10px;
  font-size:.74rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#e2e8f0}
.fx-p-cab em{font-style:normal;padding:2px 10px;border-radius:99px;font-size:.68rem;background:rgba(251,191,36,.16);color:var(--fx-mid)}
.fx-permite.ok .fx-p-cab em{background:rgba(74,222,128,.16);color:var(--fx-ok)}
.fx-permite.no .fx-p-cab em{background:rgba(248,113,113,.16);color:var(--fx-no)}
.fx-p-cuerpo{display:flex;align-items:center;gap:12px;margin:8px 0 6px}
.fx-p-cuerpo b{font-size:1.9rem;line-height:1;font-variant-numeric:tabular-nums;color:var(--fx-mid)}
.fx-permite.ok .fx-p-cuerpo b{color:var(--fx-ok)}
.fx-permite.no .fx-p-cuerpo b{color:var(--fx-no)}
.fx-p-cuerpo span{font-size:.78rem;line-height:1.45;color:var(--fx-mute)}
.fx-chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}
.fx-chip{padding:3px 10px;border-radius:99px;font-size:.7rem;font-weight:600;background:rgba(255,255,255,.07);color:#cbd5e1}
.fx-chip.hoy{background:rgba(129,140,248,.22);color:#c7d2fe}
.fx-fallos{margin:12px 0 4px}
.fx-fallos-t{margin-bottom:6px;font-size:.7rem;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:var(--fx-mute)}
.fx-fallos-t em{font-style:normal;font-weight:600;letter-spacing:0;text-transform:none}
.fx-fallos.ok{font-size:.76rem;font-weight:700;color:var(--fx-ok)}
.fx-chip.no{background:rgba(248,113,113,.14);color:#fecaca;border:1px solid rgba(248,113,113,.28)}
.fx-permite .fx-fallos{margin:4px 0 8px}
.fx-p-cruce{font-size:.8rem;font-weight:700;color:#f1f5f9}
.fx-p-nota{margin-top:4px;font-size:.7rem;color:var(--fx-mute)}
.fl-hoy{margin-top:14px;padding:12px 14px;border-radius:14px;background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.08);
  font-size:.8rem;line-height:1.9;color:#cbd5e1}
.fl-hoy .tag{margin-left:8px;padding:2px 8px;border-radius:99px;font-size:.65rem;font-weight:700;background:rgba(251,191,36,.18);color:#fbbf24}
.fl-hoy .chip{display:inline-block;margin:2px 4px 2px 0;padding:2px 10px;border-radius:99px;font-size:.72rem;font-weight:600;
  background:rgba(248,113,113,.14);color:#fecaca;border:1px solid rgba(248,113,113,.28)}
.fl-hoy .chip.dud{background:rgba(251,191,36,.12);color:#fde68a;border-color:rgba(251,191,36,.3)}
.fl.eq .fl-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(104px,1fr));gap:8px}
.fl.eq .fl-st{background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.07);border-radius:12px;padding:9px 11px}
@property --fx-p{syntax:"<number>";inherits:false;initial-value:0}
@property --fx-n{syntax:"<integer>";inherits:false;initial-value:0}
@keyframes fx-llenar{from{--fx-p:0}}
@keyframes fx-cuenta{from{--fx-n:0}}
@keyframes fx-entra{from{opacity:0;transform:translateY(10px)}}
@keyframes fx-ancho{from{transform:scaleX(0)}}
@keyframes fx-pulso{0%,100%{box-shadow:0 0 0 0 color-mix(in srgb,var(--fx-c) 35%,transparent)}50%{box-shadow:0 0 0 7px transparent}}
.fx-num{--fx-n:var(--n);animation:fx-cuenta 1.1s cubic-bezier(.22,.8,.3,1) .1s both;counter-reset:fxn var(--fx-n)}
.fx-num::before{content:counter(fxn) "%"}
.fx-anillo{border-radius:50%;animation:fx-pulso 1.6s ease-out 1.2s 1}
.fx-resumen{animation:fx-entra .45s ease-out .15s both}
.fx-titulo,.fx-sedes,.fx-nota{animation:fx-entra .5s ease-out .35s both}
.fx-permite{animation:fx-entra .5s ease-out .5s both}
.fx-sede .fx-bar i{transform-origin:left;animation:fx-ancho .9s cubic-bezier(.22,.8,.3,1) .6s both}
.fx-sede,.fx-chip{transition:transform .15s,border-color .15s,background .15s}
.fx-sede:hover{transform:translateY(-2px);border-color:rgba(255,255,255,.22)}
.fx-chip:hover{transform:translateY(-1px);background:rgba(255,255,255,.13)}
.fl.eq .fl-b:hover{opacity:1 !important;box-shadow:0 0 14px rgba(74,222,128,.55)}
.fl.eq .fl-b:not(.ok):hover{box-shadow:0 0 14px rgba(248,113,113,.5)}
.fl.eq .fl-barras{overflow:visible}
.fl.eq .fl-b{position:relative;cursor:default}
.fl.eq .fl-b:hover{z-index:30;overflow:visible}
.fx-tip{position:absolute;bottom:calc(100% + 10px);left:50%;z-index:40;display:flex;flex-direction:column;gap:2px;
  min-width:158px;padding:10px 12px;border-radius:12px;background:rgba(12,17,36,.98);border:1px solid rgba(255,255,255,.16);
  box-shadow:0 12px 32px rgba(0,0,0,.55);color:#e2e8f0;font-size:.72rem;font-weight:600;line-height:1.35;text-align:left;
  letter-spacing:0;text-transform:none;white-space:nowrap;opacity:0;visibility:hidden;pointer-events:none;
  writing-mode:horizontal-tb !important;text-orientation:mixed !important;direction:ltr;rotate:none;width:max-content;
  align-items:flex-start;font-variant-numeric:tabular-nums;
  transform:translateX(-50%) translateY(6px);transition:opacity .15s,transform .15s,visibility .15s}
.fx-tip.izq{left:0;transform:translateY(6px)}
.fx-tip.der{left:auto;right:0;transform:translateY(6px)}
.fl.eq .fl-b:hover .fx-tip{opacity:1;visibility:visible;transform:translateX(-50%) translateY(0)}
.fl.eq .fl-b:hover .fx-tip.izq,.fl.eq .fl-b:hover .fx-tip.der{transform:translateY(0)}
.fx-tip-t{font-size:.82rem;font-weight:800;color:#f8fafc}
.fx-tip>span{writing-mode:horizontal-tb;display:block}
.fx-tip-f{font-size:.68rem;color:rgba(226,232,240,.6)}
.fx-tip-v{margin:2px 0 4px;font-size:1.6rem;line-height:1.1;font-weight:800;color:#f8fafc;font-variant-numeric:tabular-nums}
.fx-tip-r.ok{color:var(--fx-ok)}
.fx-tip-r.no{color:var(--fx-no)}
.fx-tip-c{margin-top:5px;padding-top:5px;border-top:1px solid rgba(255,255,255,.12);font-size:.68rem;color:rgba(226,232,240,.75)}
@media (prefers-reduced-motion:reduce){
  .fx-anillo,.fx-anillo i,.fx-num,.fx-resumen,.fx-titulo,.fx-sedes,.fx-nota,.fx-permite,.fx-sede .fx-bar i{animation:none}
  .fx-tip,.fx-sede,.fx-chip{transition:none}
}
"""


FILAS_COMPARATIVA = [  # (nombre, clave, ¿más es mejor? None = sin líder)
    ("Puntos a favor", "pf", True), ("Puntos en contra", "pc", False), ("Total de puntos del partido", "total", None),
    ("Margen promedio", "margen", True), ("Triples convertidos", "tri", True), ("% tiros de campo", "fgp", True),
    ("% triples", "tpp", True), ("% tiros libres", "ftp", True), ("Rebotes", "reb", True), ("Asistencias", "ast", True),
    ("Robos", "stl", True), ("Tapones", "blk", True), ("Pérdidas", "to", False), ("Faltas", "fal", False),
    ("Puntos en la pintura", "paint", True), ("Puntos de contraataque", "fast", True),
    ("Tiros libres anotados", "ftm", True), ("Tiros de 2 puntos anotados", "dos", True),
    ("Ritmo (posesiones por 48 min)", "ritmo", None), ("Rend. ofensivo (pts por 100 pos.)", "ortg", True),
    ("Rend. defensivo (pts rec. por 100 pos.)", "drtg", False),
]


def _comparativa(a, b, sa, sb, titulo="Promedio"):
    """Tabla de promedios de los dos equipos con quién lidera cada fila."""
    filas = []
    wa, wb = sum(g["margen"] > 0 for g in sa), sum(g["margen"] > 0 for g in sb)
    filas.append({titulo: "Victorias", a["nombre"]: wa, b["nombre"]: wb,
                  "Líder": a["nombre"] if wa > wb else b["nombre"] if wb > wa else "—"})
    for nombre, clave, mas_es_mejor in FILAS_COMPARATIVA:
        va = [g[clave] for g in sa if g.get(clave) is not None]
        vb = [g[clave] for g in sb if g.get(clave) is not None]
        ma, mb = (mean(va) if va else None), (mean(vb) if vb else None)
        if ma is None and mb is None:
            continue
        lider = "—"
        if mas_es_mejor is not None and ma is not None and mb is not None and ma != mb:
            lider = a["nombre"] if (ma > mb) == mas_es_mejor else b["nombre"]
        filas.append({titulo: nombre, a["nombre"]: None if ma is None else round(ma, 1),
                      b["nombre"]: None if mb is None else round(mb, 1), "Líder": lider})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Líneas con racha: busca, para el cruce A vs B, las líneas que ambos vienen cumpliendo de forma consistente
# ---------------------------------------------------------------------------
# (nombre, clave, ¿del partido entero? True = una sola línea para los dos equipos; False = una por equipo)
MERCADOS_RACHA = [("Total de puntos", "total", True), ("Puntos", "pf", False), ("Triples", "tri", False),
                  ("Rebotes", "reb", False), ("Asistencias", "ast", False)]


def _valores(serie, clave):
    return [g[clave] for g in serie if g.get(clave) is not None]


def _racha_final(vals, ok):
    """Cuántos partidos seguidos, contando desde el más reciente, cumplieron (la serie va del más antiguo al más nuevo)."""
    n = 0
    for v in reversed(vals):
        if not ok(v):
            break
        n += 1
    return n


def _mejor_linea(series_rec, vals_h2h, lado, minimo):
    """La línea más exigente (la más alta en Más de, la más baja en Menos de) que se cumplió al menos `minimo` (0-1)
    de las veces en los partidos recientes Y en los enfrentamientos directos. None si ninguna llega."""
    rec = [v for s in series_rec for v in s]
    if len(rec) < 5:
        return None
    todos = rec + vals_h2h
    grid = [x + 0.5 for x in range(int(min(todos)) - 2, int(max(todos)) + 2)]
    mas = lado == "Más de"
    min_h = minimo if len(vals_h2h) >= 5 else 0.6   # con pocos cruces directos se exige menos (el 80 % de 3 partidos no existe)
    cumple = (lambda v, L: v > L) if mas else (lambda v, L: v < L)
    mejor = None
    for L in grid:
        hr = sum(cumple(v, L) for v in rec) / len(rec)
        hh = (sum(cumple(v, L) for v in vals_h2h) / len(vals_h2h)) if len(vals_h2h) >= 2 else None
        if hr >= minimo and (hh is None or hh >= min_h):
            if mejor is None or (mas and L > mejor[0]) or (not mas and L < mejor[0]):
                mejor = (L, hr, hh)
    if not mejor:
        return None
    L, hr, hh = mejor
    racha = min(_racha_final(s, lambda v: cumple(v, L)) for s in series_rec)
    return {"L": L, "kr": round(hr * len(rec)), "nr": len(rec), "hr": hr, "kh": None if hh is None else round(hh * len(vals_h2h)),
            "nh": len(vals_h2h), "hh": hh, "racha": racha}


def _proyeccion(ra, rb, ha):
    """Puntos esperados de cada equipo = promedio entre lo que anota y lo que recibe el rival; más el total y su ritmo."""
    pf_a, pc_a, pf_b, pc_b = (_valores(x, k) for x, k in ((ra, "pf"), (ra, "pc"), (rb, "pf"), (rb, "pc")))
    if not (pf_a and pc_a and pf_b and pc_b):
        return None
    pa, pb = (mean(pf_a) + mean(pc_b)) / 2, (mean(pf_b) + mean(pc_a)) / 2
    return {"a": pa, "b": pb, "total": pa + pb, "h2h": mean(_valores(ha, "total")) if _valores(ha, "total") else None}


def _inclinacion(series_rec, vals_h2h, linea):
    """(% que fue Más de, % que fue Menos de) en esa línea, mezclando recientes y enfrentamientos directos."""
    rec = [v for s in series_rec for v in s]
    def pct(f):
        p = sum(f(v) for v in rec) / len(rec)
        if len(vals_h2h) >= 2:
            p = (p + sum(f(v) for v in vals_h2h) / len(vals_h2h)) / 2
        return round(100 * p)
    return pct(lambda v: v > linea), pct(lambda v: v < linea)


def _picks_racha(a, b, ra, rb, ha, hb, minimo):
    """(proyección, línea central del total, DataFrame de líneas con racha)."""
    filas = []
    for nombre, clave, partido in MERCADOS_RACHA:
        if partido:   # el total es el mismo partido para los dos: en h2h se usa la serie de A para no contar dos veces
            grupos = [(nombre, [_valores(ra, clave), _valores(rb, clave)], _valores(ha, clave))]
        else:
            grupos = [(f'{nombre} {x["abbr"] or x["nombre"]}', [_valores(r, clave)], _valores(h, clave))
                      for x, r, h in ((a, ra, ha), (b, rb, hb))]
        for etq, series, vh in grupos:
            series = [s for s in series if s]
            if not series:
                continue
            esperado = mean([v for s in series for v in s])
            if len(vh) >= 2:
                esperado = (esperado + mean(vh)) / 2
            for lado in ("Más de", "Menos de"):
                r = _mejor_linea(series, vh, lado, minimo)
                if not r:
                    continue
                filas.append({"Mercado": etq, "Apuesta": lado, "Línea": r["L"],
                              "Recientes": f'{r["kr"]}/{r["nr"]} · {round(100 * r["hr"])}%',
                              "Cara a cara": "sin cruces" if r["hh"] is None else f'{r["kh"]}/{r["nh"]} · {round(100 * r["hh"])}%',
                              "Racha actual": r["racha"], "Esperado": round(esperado, 1),
                              "Holgura": round(abs(esperado - r["L"]), 1),
                              "_score": (r["hr"] + (r["hh"] if r["hh"] is not None else r["hr"])) / 2})
    df = pd.DataFrame(filas)
    if not df.empty:
        df = df.sort_values(["_score", "Racha actual", "Holgura"], ascending=[False, False, True]).drop(columns="_score").reset_index(drop=True)
    proy = _proyeccion(ra, rb, ha)
    central = None
    tot = [_valores(ra, "total"), _valores(rb, "total")]
    if proy and all(tot):
        central = _medio(proy["total"] if proy["h2h"] is None else (proy["total"] + proy["h2h"]) / 2)
        central = (central, *_inclinacion(tot, _valores(ha, "total"), central))
    return proy, central, df


def _seccion_racha(eq_a, eq_b, ra, rb, ha, hb):
    st.markdown("#### 🔥 Líneas con racha del cruce")
    minimo = st.slider("Mínimo de cumplimiento", 60, 100, 80, 5, format="%d%%", key="fe_racha_min",
                       help="Busca la línea más exigente que cumplieron al menos este % de las veces, tanto en los partidos "
                            "recientes como en los enfrentamientos directos.") / 100
    proy, central, df = _picks_racha(eq_a, eq_b, ra, rb, ha, hb, minimo)
    if proy:
        c1, c2, c3 = st.columns(3)
        c1.metric(f"{eq_a['abbr']} esperado", f"{proy['a']:.0f} pts", help="Promedio entre lo que anota y lo que recibe el rival.")
        c2.metric(f"{eq_b['abbr']} esperado", f"{proy['b']:.0f} pts")
        c3.metric("Total esperado", f"{proy['total']:.0f} pts",
                  None if proy["h2h"] is None else f"cara a cara: {proy['h2h']:.0f}", delta_color="off")
    if central:
        linea, mas, menos = central
        lean = "Más de" if mas >= 60 and mas > menos else "Menos de" if menos >= 60 and menos > mas else None
        txt = f"**Línea central {linea:g}:** Más de {mas}% · Menos de {menos}% (recientes y cara a cara mezclados). "
        st.markdown(txt + (f"👉 Inclinación: **{lean}**." if lean else "Sin ventaja clara: está parejo."))
    if df.empty:
        st.info(f"Ninguna línea llega al {round(minimo * 100)}% en recientes y cara a cara a la vez. Baja el mínimo o cambia la ventana.")
        return
    st.dataframe(df, hide_index=True, use_container_width=True, column_config={
        "Línea": st.column_config.NumberColumn(format="%.1f"),
        "Racha actual": st.column_config.NumberColumn(help="Partidos seguidos cumpliéndola, desde el más reciente (el menor de los dos equipos en el total)."),
        "Esperado": st.column_config.NumberColumn(help="Promedio del mercado (recientes y cara a cara)."),
        "Holgura": st.column_config.NumberColumn(help="Distancia entre la línea y el promedio: más holgura = más margen de seguridad.")})
    st.caption("Son líneas históricas «seguras» (las más exigentes que se cumplieron con esa frecuencia). "
               "No es una predicción ni garantiza el resultado.")


# ---------------------------------------------------------------------------
# Selector con escudos (botones pequeños)
# ---------------------------------------------------------------------------


def _css_escudos(equipos):
    """CSS con el escudo de cada equipo como fondo de su botón (la clave del botón es fe_a_<id> / fe_b_<id>)."""
    reglas = []
    for e in equipos:
        url = str(e.get("logo", ""))
        if not url.startswith("https://") or any(c in url for c in "\"'()<> "):
            continue
        for lado in ("a", "b"):
            reglas.append(f'.st-key-fe_{lado}_{e["id"]} button[data-testid^="stBaseButton"] {{ background-image: url("{url}") !important; }}')
    return "<style>" + estilos.css("escudos") + "\n".join(reglas) + "</style>"


# ---------------------------------------------------------------------------
# Elegir equipos hablando (micrófono)
# ---------------------------------------------------------------------------
_HTML_VOZ = r'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
  :root { --txt: #31333f; --pri: #6366f1; --fondo2: #f0f2f6; }
  html, body { margin: 0; padding: 0; background: transparent; font-family: "Source Sans Pro", system-ui, sans-serif; color: var(--txt); }
  #raiz { padding: 2px 3px 4px; }
  .fila { display: flex; align-items: center; gap: 8px; height: 44px; }
  button, select { font: inherit; color: var(--txt); background: var(--fondo2); border: 1px solid rgba(127,127,127,.35); border-radius: 999px; }
  button { flex: 0 0 auto; padding: 0 16px; height: 40px; cursor: pointer; font-weight: 700; white-space: nowrap; transition: transform .15s ease, box-shadow .15s ease; }
  button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(99,102,241,.25); }
  button.on { background: #ef4444; border-color: #ef4444; color: #fff; animation: pulso 1.2s ease-in-out infinite; }
  select { flex: 0 0 auto; height: 40px; padding: 0 8px; cursor: pointer; }
  #estado { font-size: .85rem; line-height: 1.3; white-space: normal; word-break: break-word; margin-top: 2px; }
  #estado.tenue { opacity: .7; }
  #estado:empty { display: none; }
  @keyframes pulso { 0%,100% { box-shadow: 0 0 0 0 rgba(239,68,68,.5); } 50% { box-shadow: 0 0 0 8px rgba(239,68,68,0); } }
</style>
</head>
<body>
<div id="raiz">
  <div class="fila">
    <button id="mic" type="button" title="Di el equipo local y después el visitante">🎤 Decir equipos</button>
    <select id="idioma" title="Idioma del reconocimiento de voz">
      <option value="es-CL">ES</option>
      <option value="en-US">EN</option>
    </select>
  </div>
  <div id="estado"></div>
</div>
<script>
  // ---------- Protocolo mínimo de componentes de Streamlit ----------
  function enviar(tipo, extra) {
    window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: tipo }, extra || {}), "*");
  }
  function ajustarAlto() {
    var alto = document.getElementById("raiz").offsetHeight + 6;
    enviar("streamlit:setFrameHeight", { height: Math.max(alto, 48) });
  }
  enviar("streamlit:componentReady", { apiVersion: 1 });
  ajustarAlto();
  window.addEventListener("resize", ajustarAlto);

  window.addEventListener("message", function (e) {
    if (!e.data || e.data.type !== "streamlit:render") return;
    var t = e.data.theme || (e.data.args && e.data.args.theme);
    if (!t) return;
    var r = document.documentElement.style;
    if (t.textColor) r.setProperty("--txt", t.textColor);
    if (t.primaryColor) r.setProperty("--pri", t.primaryColor);
    if (t.secondaryBackgroundColor) r.setProperty("--fondo2", t.secondaryBackgroundColor);
  });

  // ---------- Elementos y estado ----------
  var btn = document.getElementById("mic");
  var sel = document.getElementById("idioma");
  var estado = document.getElementById("estado");
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var escuchando = false, parar = null;
  var usarVosk = !SR;            // Brave (o sin API de voz) => motor Vosk dentro del navegador
  var textoActual = "", ultimoEnviado = "", tEnvio = 0, contador = 0, timerSilencio = null;

  if (navigator.brave && navigator.brave.isBrave) {
    navigator.brave.isBrave().then(function (es) { if (es) usarVosk = true; });
  }

  function texto(t, tenue) {
    estado.textContent = t;
    estado.className = tenue ? "tenue" : "";
    ajustarAlto();
  }

  // Manda lo dicho a Python (en vivo, con un pequeño límite de frecuencia)
  function mandar(t, parcial) {
    if (!t) return;
    ultimoEnviado = t; tEnvio = Date.now();
    enviar("streamlit:setComponentValue", {
      value: { texto: t, id: Date.now() + "-" + (++contador), parcial: !!parcial },
      dataType: "json"
    });
  }

  // Se llama cada vez que cambia el texto reconocido (mientras hablas)
  function actualizar(t) {
    t = (t || "").replace(/\s+/g, " ").trim();
    if (t === textoActual) return;
    textoActual = t;
    texto(t ? "«" + t + "»" : "Escuchando… di el local y después el visitante", !t);
    if (t && t !== ultimoEnviado && Date.now() - tEnvio > 500) mandar(t, true);
    // si dejas de hablar ~2,5 s, termina solo
    clearTimeout(timerSilencio);
    if (t) timerSilencio = setTimeout(function () { if (escuchando && parar) parar(); }, 2500);
  }

  function ui(on) {
    escuchando = on;
    btn.classList.toggle("on", on);
    btn.textContent = on ? "⏹ Escuchando…" : "🎤 Decir equipos";
  }

  function terminar() {
    clearTimeout(timerSilencio);
    ui(false);
    parar = null;
    if (textoActual) {
      mandar(textoActual, false);   // resultado final
      texto("«" + textoActual + "»");
    }
  }

  function mensajeError(codigo) {
    if (codigo === "not-allowed" || codigo === "service-not-allowed")
      return "Sin permiso para el micrófono: actívalo con el candado de la barra de direcciones.";
    if (codigo === "no-speech") return "No te escuché. Prueba otra vez.";
    if (codigo === "audio-capture") return "No encuentro ningún micrófono.";
    return "No se pudo usar la voz (" + codigo + ").";
  }

  // ---------- Motor 1: voz del navegador (Chrome, Edge, Safari) ----------
  function iniciarNavegador() {
    var rec = new SR();
    rec.lang = sel.value;
    rec.interimResults = true;
    rec.continuous = true;
    rec.maxAlternatives = 1;
    var huboError = false, cayoAVosk = false;
    parar = function () { try { rec.stop(); } catch (e) {} };

    rec.onstart = function () { ui(true); texto("Escuchando… di el local y después el visitante", true); };
    rec.onresult = function (ev) {
      var t = "";
      for (var i = 0; i < ev.results.length; i++) t += ev.results[i][0].transcript + " ";
      actualizar(t);
    };
    rec.onerror = function (ev) {
      huboError = true;
      if (ev.error === "network") {          // el navegador bloquea el servicio de voz => motor propio
        cayoAVosk = true; usarVosk = true; ui(false); iniciarVosk(); return;
      }
      texto(mensajeError(ev.error));
    };
    rec.onend = function () {
      if (cayoAVosk) return;
      if (!textoActual && !huboError) texto("No te escuché. Prueba otra vez.");
      terminar();
    };
    try { rec.start(); } catch (err) { texto("No se pudo iniciar el micrófono."); }
  }

  // ---------- Motor 2: Vosk (reconocimiento dentro del navegador, sin Google) ----------
  var BASE = "https://ccoreilly.github.io/vosk-browser/models/";
  var MODELOS = {
    "es-CL": BASE + "vosk-model-small-es-0.42.tar.gz",
    "en-US": BASE + "vosk-model-small-en-us-0.15.tar.gz"
  };
  var cacheModelos = {}, promesaLib = null;

  function cargarLibVosk() {
    if (window.Vosk) return Promise.resolve();
    if (!promesaLib) promesaLib = new Promise(function (ok, mal) {
      var s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/vosk-browser@0.0.5/dist/vosk.js";
      s.onload = ok; s.onerror = function () { promesaLib = null; mal(new Error("no se pudo descargar la librería de voz")); };
      document.head.appendChild(s);
    });
    return promesaLib;
  }
  function cargarModelo(idioma) {
    if (!cacheModelos[idioma]) {
      cacheModelos[idioma] = cargarLibVosk().then(function () { return window.Vosk.createModel(MODELOS[idioma]); })
        .catch(function (e) { delete cacheModelos[idioma]; throw e; });
    }
    return cacheModelos[idioma];
  }

  function iniciarVosk() {
    var cancelado = false;
    var ac = new (window.AudioContext || window.webkitAudioContext)();   // se crea dentro del clic
    var stream = null, nodo = null, fuente = null, recog = null, finales = [];
    ui(true);
    parar = function () { cancelado = true; limpiar(); terminar(); };
    texto("Cargando el modelo de voz… (solo tarda la primera vez, ~40 MB)", true);

    function limpiar() {
      try { if (nodo) { nodo.onaudioprocess = null; nodo.disconnect(); } } catch (e) {}
      try { if (fuente) fuente.disconnect(); } catch (e) {}
      try { if (stream) stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
      try { if (recog) recog.remove(); } catch (e) {}
      try { ac.close(); } catch (e) {}
    }

    Promise.all([
      cargarModelo(sel.value),
      navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 }, video: false })
    ]).then(function (r) {
      if (cancelado) { r[1].getTracks().forEach(function (t) { t.stop(); }); return; }
      var modelo = r[0]; stream = r[1];
      if (ac.state === "suspended") ac.resume();
      recog = new modelo.KaldiRecognizer(ac.sampleRate);
      recog.on("result", function (m) {
        var t = m && m.result && m.result.text;
        if (t) { finales.push(t); actualizar(finales.join(" ")); }
      });
      recog.on("partialresult", function (m) {
        var p = (m && m.result && m.result.partial) || "";
        actualizar((finales.join(" ") + " " + p));
      });
      nodo = ac.createScriptProcessor(4096, 1, 1);
      nodo.onaudioprocess = function (e) { try { recog.acceptWaveform(e.inputBuffer); } catch (x) {} };
      fuente = ac.createMediaStreamSource(stream);
      fuente.connect(nodo); nodo.connect(ac.destination);
      texto("Escuchando… di el local y después el visitante", true);
    }).catch(function (err) {
      cancelado = true; limpiar(); ui(false); parar = null;
      if (err && (err.name === "NotAllowedError" || err.name === "SecurityError"))
        texto("Sin permiso para el micrófono: actívalo con el candado de la barra de direcciones.");
      else if (err && err.name === "NotFoundError") texto("No encuentro ningún micrófono.");
      else texto("No se pudo cargar el motor de voz: " + (err && err.message ? err.message : err));
    });
  }

  // ---------- Botón ----------
  btn.addEventListener("click", function () {
    if (escuchando) { if (parar) parar(); return; }
    textoActual = ""; ultimoEnviado = "";
    if (usarVosk) iniciarVosk(); else iniciarNavegador();
  });
</script>
</body>
</html>
'''


def _ruta_voz():
    """Escribe el componente de voz (embebido en este archivo) en voz_equipos/index.html y devuelve la carpeta.
    Así basta con este único archivo y siempre se usa la versión más reciente."""
    import tempfile
    base = os.path.dirname(os.path.abspath(__file__))
    for carpeta in (os.path.join(base, "voz_equipos"), os.path.join(tempfile.gettempdir(), "voz_equipos")):
        try:
            os.makedirs(carpeta, exist_ok=True)
            destino = os.path.join(carpeta, "index.html")
            try:
                with open(destino, encoding="utf-8") as f:
                    igual = f.read() == _HTML_VOZ
            except OSError:
                igual = False
            if not igual:
                with open(destino, "w", encoding="utf-8") as f:
                    f.write(_HTML_VOZ)
            return carpeta
        except OSError:
            continue
    return None


_RUTA_VOZ = _ruta_voz()
_VOZ_ERROR = None
try:
    _VOZ = components.declare_component("voz_equipos", path=_RUTA_VOZ) if _RUTA_VOZ else None
    if _VOZ is None:
        _VOZ_ERROR = "No encuentro index.html del micrófono. Ponlo en la carpeta voz_equipos/ junto a ficha_equipos.py."
except Exception as _e:  # noqa: BLE001
    _VOZ = None
    _VOZ_ERROR = f"No se pudo cargar el micrófono: {_e}"

_AMBIGUOS_VOZ = {"los angeles", "la", "new york city"}   # nombres de ciudad que valen para más de un equipo
_EXTRAS_VOZ = {   # cómo se dice o cómo suena cada equipo (clave = apodo sin acentos)
    "76ers": ["sixers", "setenta y seis", "filadelfia", "76"],
    "knicks": ["niks", "nicks", "nueva york"],
    "thunder": ["oklahoma", "okc", "zander", "sander"],
    "pelicans": ["nueva orleans", "pelicanos"],
    "trail blazers": ["blazers"],
    "cavaliers": ["cavs"], "mavericks": ["mavs"], "timberwolves": ["wolves", "timberwolf"],
    "celtics": ["seltics", "keltics"], "lakers": ["leikers", "laykers"],
    "clippers": ["los angeles clippers", "clipers"],
    "warriors": ["guerreros", "warrior", "golden"], "grizzlies": ["grizzly", "grizlis"],
    "raptors": ["raptores"], "bulls": ["toros"], "hornets": ["avispones"], "nuggets": ["naguets", "nugets"],
    "wizards": ["magos", "wizard"], "rockets": ["cohetes"], "pistons": ["piston"], "pacers": ["peisers"],
    "spurs": ["espurs"], "kings": ["reyes"],
}


def _sin_acentos(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _equipos_en_frase(texto, equipos):
    """Ids de los equipos nombrados en la frase, en el orden en que se dijeron (máximo 2)."""
    t = _sin_acentos(texto)
    if not t:
        return []
    alias = {}
    for e in equipos:
        n = _sin_acentos(e["nombre"])
        if not n:
            continue
        apodo = " ".join(n.split()[-2:]) if n.endswith("trail blazers") else n.split()[-1]
        ciudad = n[:len(n) - len(apodo)].strip()
        for a in (n, apodo, ciudad, *_EXTRAS_VOZ.get(apodo, ())):
            a = _sin_acentos(a)
            if len(a) >= 3 and a not in _AMBIGUOS_VOZ:
                alias.setdefault(a, set()).add(e["id"])
    alias = {a: next(iter(ids)) for a, ids in alias.items() if len(ids) == 1}   # un alias que sirve a dos equipos no se usa

    usados, hallados = [], []   # (inicio, fin) ya tomados y (posición, id) de cada mención

    def libre(s, f):
        return not any(s < u1 and f > u0 for u0, u1 in usados)

    candidatos = []
    for a, eid in alias.items():
        for m in re.finditer(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", t):
            candidatos.append((m.start(), m.end(), eid))
    for s, f, eid in sorted(candidatos, key=lambda c: (-(c[1] - c[0]), c[0])):   # primero lo más largo ("Los Angeles Lakers" antes que "Lakers")
        if libre(s, f):
            usados.append((s, f))
            hallados.append((s, eid))

    if len({eid for _, eid in hallados}) < 2:   # lo que no calzó exacto: nombres mal escuchados («leikers», «seltics»…)
        toks = [(m.start(), m.end()) for m in re.finditer(r"[a-z0-9]+", t)]
        for i in range(len(toks)):
            for k in (2, 1):
                if i + k > len(toks):
                    continue
                s, f = toks[i][0], toks[i + k - 1][1]
                frase = t[s:f]
                if len(frase) < 4 or not libre(s, f):
                    continue
                r, eid = max(((SequenceMatcher(None, frase, a).ratio(), eid) for a, eid in alias.items() if len(a) >= 4),
                             default=(0, None))
                if r >= 0.8:
                    usados.append((s, f))
                    hallados.append((s, eid))
                    break

    orden = []
    for _, eid in sorted(hallados):
        if eid not in orden:
            orden.append(eid)
    return orden[:2]


def _aplicar_voz(valor, equipos, por_id):
    """Primer equipo que se dice = Equipo A (local); el segundo = Equipo B (visita)."""
    if not isinstance(valor, dict) or valor.get("id") is None or valor["id"] == st.session_state.get("fe_voz_id"):
        return
    st.session_state["fe_voz_id"] = valor["id"]   # cada frase se procesa una sola vez, aunque la pantalla se vuelva a dibujar
    texto = re.sub(r"[*_`\[\]]", "", str(valor.get("texto", "")))
    ids = _equipos_en_frase(texto, equipos)
    if not ids:
        if not valor.get("parcial"):   # mientras aún hablas no molestamos con avisos
            st.session_state["fe_voz_msg"] = ("warning", f"Escuché «{texto}», pero no reconocí ningún equipo. Prueba otra vez.")
        return
    st.session_state["fe_a"] = ids[0]
    st.session_state["fe_b"] = ids[1] if len(ids) > 1 else None
    resumen = f"🏠 Local: **{por_id[ids[0]]['nombre']}**"
    resumen += f" · ✈️ Visita: **{por_id[ids[1]]['nombre']}**" if len(ids) > 1 else " (sin visita: di dos equipos para compararlos)"
    st.session_state["fe_voz_msg"] = ("success", f"Escuché «{texto}» → {resumen}")


def _transcribir(audio_bytes, idioma="es-CL"):
    """Pasa el audio grabado a texto desde el servidor (sirve en Brave, que bloquea la voz del navegador)."""
    import io
    try:
        import speech_recognition as sr
    except ImportError:
        try:   # se instala sola la primera vez
            import importlib
            import subprocess
            import sys
            subprocess.check_call([sys.executable, "-m", "pip", "install", "SpeechRecognition"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            importlib.invalidate_caches()
            import speech_recognition as sr
        except Exception:  # noqa: BLE001
            return None, "No pude instalar SpeechRecognition solo. Ejecuta: pip install SpeechRecognition"
    try:
        rec = sr.Recognizer()
        with sr.AudioFile(io.BytesIO(audio_bytes)) as fuente:
            audio = rec.record(fuente)
        return rec.recognize_google(audio, language=idioma), None
    except sr.UnknownValueError:
        return None, "No se entendió el audio. Prueba otra vez, más cerca del micrófono."
    except Exception as e:  # noqa: BLE001
        return None, f"No se pudo transcribir el audio ({e}). ¿El servidor tiene internet?"


def _grabar_audio(equipos, por_id):
    """Alternativa al botón del navegador: graba con el micrófono de Streamlit y transcribe en el servidor."""
    if not hasattr(st, "audio_input"):
        return
    with st.expander("🎙️ Grabar audio (alternativa si tu navegador bloquea la voz)"):
        st.caption("Usa esta opción si estás en Brave o si tu navegador bloquea el reconocimiento de voz directo.")
        audio = st.audio_input("Di el equipo local y después el visitante", key="fe_voz_audio")
        if audio is None:
            return
        datos = audio.getvalue()
        marca = hash(datos)
        if marca == st.session_state.get("fe_voz_audio_hash"):
            return   # esta grabación ya se procesó
        st.session_state["fe_voz_audio_hash"] = marca
        with st.spinner("Transcribiendo…"):
            texto, error = _transcribir(datos)
        if error:
            st.session_state["fe_voz_msg"] = ("warning", error)
        else:
            _aplicar_voz({"texto": texto, "id": f"audio-{marca}"}, equipos, por_id)
        st.rerun()


def _barra_voz(equipos, por_id):
    if _VOZ is None:
        if _VOZ_ERROR:
            st.caption("🎤 " + _VOZ_ERROR)
    else:
        try:
            c_mic, c_msg = st.columns([2, 5], vertical_alignment="center")
        except TypeError:   # Streamlit antiguo sin vertical_alignment
            c_mic, c_msg = st.columns([2, 5])
        with c_mic:
            valor = _VOZ(key="fe_voz", default=None)
        _aplicar_voz(valor, equipos, por_id)
        msg = st.session_state.get("fe_voz_msg")
        if msg:
            with c_msg:
                getattr(st, msg[0])(msg[1])
    _grabar_audio(equipos, por_id)


def _elegir(clave, valor):
    st.session_state[clave] = valor
    st.session_state.pop("fe_voz_msg", None)   # el aviso de la voz ya no describe lo que está elegido
    if clave == "fe_a" and st.session_state.get("fe_b") == valor:  # A y B no pueden ser el mismo equipo
        st.session_state["fe_b"] = None


def _fila_escudos(titulo, clave, equipos, por_id, bloqueado=None, con_ninguno=False):
    """Una fila de escudos pequeños: al apretar uno queda elegido (el nombre aparece al pasar el mouse)."""
    elegido = st.session_state.get(clave)
    nombre = por_id[elegido]["nombre"] if elegido in por_id else "ninguno"
    st.markdown(f"**{titulo}:** {_e(nombre)}")
    with st.container(key=f"{clave}_barra"):
        for e in equipos:
            st.button(e["abbr"] or e["nombre"][:3], key=f'{clave}_{e["id"]}', help=e["nombre"], on_click=_elegir,
                      args=(clave, e["id"]), type="primary" if e["id"] == elegido else "secondary",
                      disabled=e["id"] == bloqueado)
    if con_ninguno and elegido is not None:
        st.button("✕ Quitar Visita", key=f"{clave}_ninguno", on_click=_elegir, args=(clave, None),
                  help="Analizar solo el Local")


def selector_equipos(equipos, por_id, key_pref="fe", con_abbr=True):
    """Selector moderno de 1 o 2 equipos con botones de modo, escudos chicos y lista oscura."""
    import json as _json
    import streamlit.components.v1 as _comp

    ids_eq = [e["id"] for e in equipos]
    if not ids_eq:
        return
    if st.session_state.get("fe_a") not in por_id:
        st.session_state["fe_a"] = ids_eq[0]
    if st.session_state.get("fe_b") not in por_id:
        st.session_state["fe_b"] = None

    k_cmp = f"{key_pref}_modo_cmp"
    if k_cmp not in st.session_state:
        st.session_state[k_cmp] = st.session_state.get("fe_b") is not None
    modo_cmp = bool(st.session_state[k_cmp])

    b1, b2 = st.columns(2, gap="small")
    if b1.button("📊 Ver stats del equipo", key=f"{key_pref}_btn_uno",
                 type="primary" if not modo_cmp else "secondary", use_container_width=True):
        st.session_state[k_cmp] = False
        st.session_state["fe_b"] = None
        st.rerun()
    if b2.button("⚔️ Comparar stats de equipos", key=f"{key_pref}_btn_cmp",
                 type="primary" if modo_cmp else "secondary", use_container_width=True):
        st.session_state[k_cmp] = True
        if st.session_state.get("fe_b") is None:
            otros = [i for i in ids_eq if i != st.session_state["fe_a"]]
            st.session_state["fe_b"] = otros[0] if otros else None
        st.rerun()

    def _etq(i):
        eq = por_id[i]
        return eq["nombre"]

    def _pill(eq, rol="Local"):
        logo = eq.get("logo") or ""
        img = f'<img src="{_e(logo)}" alt="">' if logo else "<span>🛡️</span>"
        cls_rol = "visita" if rol == "Visita" else "local"
        st.markdown(
            f'<div class="sl-team-pill">{img}<span class="sl-team-name">{_e(_etq(eq["id"]))}</span>'
            f'<span class="sl-team-badge {cls_rol}">{_e(rol.upper())}</span></div>',
            unsafe_allow_html=True,
        )

    cols = st.columns(2, gap="medium") if modo_cmp else [st.container()]
    with cols[0]:
        _pill(por_id[st.session_state["fe_a"]], "Local")
        idx_a = ids_eq.index(st.session_state["fe_a"]) if st.session_state["fe_a"] in ids_eq else 0
        sel_a = st.selectbox(
            "Local",
            ids_eq,
            index=idx_a,
            format_func=_etq,
            key=f"{key_pref}_sel_a_txt",
        )
        if sel_a != st.session_state["fe_a"]:
            st.session_state["fe_a"] = sel_a
            if st.session_state["fe_b"] == sel_a:
                otros = [i for i in ids_eq if i != sel_a]
                st.session_state["fe_b"] = otros[0] if (modo_cmp and otros) else None
            st.rerun()

    if modo_cmp:
        ops_b = [i for i in ids_eq if i != st.session_state["fe_a"]]
        if ops_b:
            if st.session_state["fe_b"] not in ops_b:
                st.session_state["fe_b"] = ops_b[0]
            with cols[1]:
                _pill(por_id[st.session_state["fe_b"]], "Visita")
                idx_b = ops_b.index(st.session_state["fe_b"])
                sel_b = st.selectbox(
                    "Visita",
                    ops_b,
                    index=idx_b,
                    format_func=_etq,
                    key=f"{key_pref}_sel_b_txt",
                )
                if sel_b != st.session_state["fe_b"]:
                    st.session_state["fe_b"] = sel_b
                    st.rerun()

    logos_map = {_etq(e["id"]): e["logo"] for e in equipos if e.get("logo")}
    if logos_map:
        _comp.html(
            f"""<script>
(function() {{
  try {{
    var P = window.parent;
    if (!P || !P.document) return;
    P.__slLogos = Object.assign(P.__slLogos || {{}}, {_json.dumps(logos_map)});

    /* ---- resaltar opción activa con teclado ---- */
    function syncActive() {{
      var list = P.document.querySelector('div[data-baseweb="popover"] ul[role="listbox"]');
      if (!list) return;
      /* Intentar con aria-activedescendant */
      var activeId = '';
      P.document.querySelectorAll('[data-baseweb="select"] input').forEach(function(inp) {{
        var v = inp.getAttribute('aria-activedescendant');
        if (v) activeId = v;
      }});
      var opts = list.querySelectorAll('li[role="option"]');
      opts.forEach(function(li) {{
        /* Comparar por id O por aria-selected si no hay activeId */
        var byId  = activeId && li.id === activeId;
        var bySel = !activeId && li.getAttribute('aria-selected') === 'true';
        li.classList.toggle('sl-kb-active', !!(byId || bySel));
      }});
    }}

    /* ---- inyectar logos en el desplegable ---- */
    function paint() {{
      var opts = P.document.querySelectorAll('div[data-baseweb="popover"] ul[role="listbox"] li[role="option"]');
      opts.forEach(function(li) {{
        var txt = (li.textContent || '').replace('↵','').trim();
        var url = P.__slLogos[txt];
        if (!url) return;
        var cur = li.querySelector('img.sl-opt-logo');
        if (cur && cur.getAttribute('src') === url) return;
        if (cur) cur.remove();
        var img = P.document.createElement('img');
        img.className = 'sl-opt-logo';
        img.src = url;
        img.style.cssText = 'width:18px;height:18px;object-fit:contain;flex-shrink:0;margin-right:2px;';
        li.prepend(img);
      }});
      syncActive();
    }}

    /* ---- registrar observer y keydown (siempre actualizar la referencia) ---- */
    if (P.__slLogoObs) {{ P.__slLogoObs.disconnect(); }}
    P.__slLogoObs = new MutationObserver(paint);
    P.__slLogoObs.observe(P.document.body, {{
      childList: true, subtree: true,
      attributes: true,
      attributeFilter: ['aria-activedescendant', 'aria-selected']
    }});

    /* registrar keydown solo una vez por sesión de parent */
    if (!P.__slKbBound) {{
      P.__slKbBound = true;
      P.document.addEventListener('keydown', function(ev) {{
        if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {{
          setTimeout(syncActive, 15);
          setTimeout(syncActive, 60);
          setTimeout(syncActive, 150);
        }}
      }}, true);
    }}
    paint();
  }} catch(e) {{}}
}})();
</script>""",
            height=0,
            width=0,
        )


# ---------------------------------------------------------------------------
# Pantalla
# ---------------------------------------------------------------------------
def render():
    st.title("🎯 Líneas de equipos")
    st.caption("Elige un equipo (o dos para compararlos) y una línea: mira cuántas veces la cumplieron en sus últimos 5 a 25 partidos o en sus enfrentamientos directos.")
    equipos = _equipos()
    if not equipos:
        st.error("No se pudo cargar la lista de equipos. Revisa la sección Diagnóstico.")
        return
    por_id = {e["id"]: e for e in equipos}
    hoy = date.today()
    actual = _temporada_actual()
    temporadas = (actual, actual - 1)  # temporada actual y anterior, por si aún van pocos partidos

    selector_equipos(equipos, por_id, key_pref="fe", con_abbr=True)

    with st.expander("🛡️ Elegir desde cuadrícula de escudos", expanded=False):
        st.markdown(_css_escudos(equipos), unsafe_allow_html=True)
        _fila_escudos("Local", "fe_a", equipos, por_id)
        _fila_escudos("Visita (opcional, para comparar)", "fe_b", equipos, por_id, bloqueado=st.session_state["fe_a"], con_ninguno=True)
    import planes
    es_pro = planes.es_pro()
    ida, idb = st.session_state["fe_a"], st.session_state["fe_b"]
    if es_pro:
        grupo = st.radio("Tipo de mercado", list(GRUPOS_MERCADO), horizontal=True, key="fe_grupo_mercado", label_visibility="collapsed")
        opciones = sorted(GRUPOS_MERCADO[grupo], key=normalizar)   # orden alfabético (sin distinguir tildes ni mayúsculas)
        mercado = st.selectbox("Mercado", opciones, key=f"fe_mercado_{grupo}")
        ventanas = [5, 10, 15, 20, 25] + (["h2h"] if idb else [])
        ventana = st.radio("Partidos a analizar", ventanas, index=1, horizontal=True, key="fe_ventana",
                           format_func=lambda v: "⚔️ Enfrentamientos directos" if v == "h2h" else f"Últimos {v}")
    else:
        st.caption("Plan Gratuito en Equipos: solo estadísticas de **Puntos (PTS)** y **últimos 5 partidos**.")
        mercado = "Puntos del equipo"
        ventana = 5
        planes.bloque_pro(
            "Todos los mercados y ventanas de 10 a 25 partidos",
            "Cuartos, tiros, hándicaps, enfrentamientos directos y ventanas amplias están disponibles en ScoreLine Pro.",
            "Cuartos · Tiros · Hándicaps · Últimos 10/15/20/25 PJ",
            key="lock_fe_mercados",
        )
    h2h = ventana == "h2h"
    sin_ot = st.toggle("Excluir partidos con tiempo extra", key="fe_sin_ot",
                       help="Los puntos del partido y casi todas las estadísticas incluyen el tiempo extra; los mercados de cuartos y "
                            "del primer tiempo no. Al excluirlos se toman igualmente los últimos N partidos, pero de los que terminaron "
                            "en los 4 cuartos. Los partidos con tiempo extra se ven con borde violeta en las barras.")
    with st.spinner("Cargando partidos y estadísticas..."):
        if h2h:  # los cruces directos son pocos por temporada: se buscan en las últimas 4
            temps = (actual, actual - 1, actual - 2, actual - 3)
            sa = _serie_equipo(ida, temps, 25, rival_id=idb, sin_ot=sin_ot)
            sb = _serie_equipo(idb, temps, 25, rival_id=ida, sin_ot=sin_ot)
        else:
            sa = _serie_equipo(ida, temporadas, ventana, sin_ot=sin_ot)
            sb = _serie_equipo(idb, temporadas, ventana, sin_ot=sin_ot) if idb else []
    if not sa:
        if h2h:
            st.info("Estos equipos no se han enfrentado en las últimas 4 temporadas.")
        else:
            st.warning("No hay partidos terminados para el Equipo A en estas temporadas.")
        return

    if h2h:
        u = sa[-1]
        st.caption(f"⚔️ Último cruce: {u['dia']:%d/%m/%Y} · {por_id[ida]['abbr']} {u['pf']} – {u['rival']} {u['pc']}"
                   f" ({'ganó' if u['pf'] > u['pc'] else 'perdió'} {por_id[ida]['abbr']}, {'local' if u['sede'] == 'home' else 'visita'})."
                   if u.get("dia") else f"⚔️ Último cruce: {por_id[ida]['abbr']} {u['pf']} – {u['rival']} {u['pc']}.")
    m = MERCADOS[mercado]
    clave = m.campo   # el dato que se lee en cada partido (en "Ganador (local o visita)" es el margen)
    medianas = [median([g[clave] for g in s if g.get(clave) is not None]) for s in (sa, sb) if any(g.get(clave) is not None for g in s)]
    if not medianas:
        st.warning("ESPN no entregó datos de este mercado para estos partidos. Prueba otro mercado.")
        return
    if m.tipo == "handicap":
        sugerida = -_medio(medianas[0] if len(medianas) == 1 else (medianas[0] - medianas[1]) / 2)
    else:
        sugerida = _medio(mean(medianas))

    l1, l2 = st.columns(2)
    if m.tipo == "ganador":
        linea, lado = 0.0, "Más de"
        l1.caption(m.ayuda)
    elif m.tipo == "handicap":
        linea = l1.number_input(f"Hándicap de {por_id[ida]['nombre']}", -m.rango, m.rango, float(min(max(sugerida, -m.rango), m.rango)), 0.5, format="%+.1f",
                                key=f"fe_l_{m.clave}_{ida}_{idb}", help="Ej.: -5.5 = debe ganar por 6 o más. +3.5 = puede perder por hasta 3.")
        lado = "Más de"
    else:
        # La línea siempre termina en .5 (como las de las casas de apuestas): la sugerida se ajusta al .5 más cercano
        # y el paso es de 1, así «+» y «−» no sacan el valor del .5. Si alguien escribe un entero, se sube a .5.
        sugerida_5 = min(max(math.floor(sugerida) + 0.5, 0.5), 399.5)
        linea = l1.number_input("Línea", 0.5, 399.5, float(sugerida_5), 1.0, format="%.1f", key=f"fe_l5_{m.clave}_{ida}_{idb}")
        if linea % 1 == 0:
            linea += 0.5
        lado = l2.radio("Apuesta", ["Más de", "Menos de"], horizontal=True, key="fe_lado")

    estilos.cargar("ficha_linea", "equipos")   # primero la base (.fl), luego lo propio de equipos
    st.markdown(f"<style>{_CSS_MEJORAS}</style>", unsafe_allow_html=True)   # retoques visuales y bloques nuevos
    modo = m.tipo
    eq_a = por_id[ida]
    # Solo el hándicap se invierte para el Equipo B; en los demás mercados la línea es la misma para los dos
    linea_b = -linea if modo == "handicap" else linea
    cards = [(eq_a, sa, linea)] + ([(por_id[idb], sb, linea_b)] if idb else [])
    cols = st.columns(len(cards))
    # Partidos recientes de cada equipo para ver qué permite como rival. En un cruce directo los partidos entre ellos
    # no sirven (serían los mismos), así que se usan sus últimos 10 partidos.
    n_rival = ventana if isinstance(ventana, int) else 10
    rec_a = rec_b = None
    if idb and h2h:
        with st.spinner("Cargando los últimos partidos de cada equipo..."):
            rec_a = _serie_equipo(ida, temporadas, n_rival, sin_ot=sin_ot)
            rec_b = _serie_equipo(idb, temporadas, n_rival, sin_ot=sin_ot)
    for i, (col, (eq, serie, l)) in enumerate(zip(cols, cards)):
        umbral = -l if modo == "handicap" else abs(l)  # margen necesario para cubrir el hándicap
        ctx = {"hoy": _contexto_hoy(eq["id"], actual, _partidos(eq["id"], temporadas)), "bajas": _bajas_hoy(eq["id"], eq["nombre"])}
        otro = cards[1 - i][0] if idb else None
        serie_otro = (rec_b if i == 0 else rec_a) if (idb and h2h) else (cards[1 - i][1] if idb else None)
        rival = _armar_rival(otro, serie_otro, ctx, por_id, temporadas, n_rival, sin_ot)
        col.markdown(_tarjeta(eq, serie, m, umbral, lado, mercado, hand=l, h2h=h2h, ctx=ctx, rival=rival), unsafe_allow_html=True)

    if idb:
        st.markdown("#### Comparativa")
        st.dataframe(_comparativa(eq_a, por_id[idb], sa, sb, "Promedio (enfrentamientos directos)" if h2h else f"Promedio (últimos {ventana})"), hide_index=True, use_container_width=True)
    if idb:
        ra, rb = ([g["ritmo"] for g in x if g.get("ritmo") is not None] for x in (sa, sb))
        if ra and rb:
            st.caption(f"⏱️ Ritmo esperado del cruce: ≈ {(mean(ra) + mean(rb)) / 2:.0f} posesiones por 48 min "
                       f"({por_id[ida]['abbr']} {mean(ra):.1f} · {por_id[idb]['abbr']} {mean(rb):.1f}).")
    if idb and es_pro:
        with st.spinner("Calculando líneas con racha..."):
            n_rec = ventana if isinstance(ventana, int) else 10
            temps4 = (actual, actual - 1, actual - 2, actual - 3)
            ra = sa if not h2h else rec_a
            rb = sb if not h2h else rec_b
            ha = sa if h2h else _serie_equipo(ida, temps4, 25, rival_id=idb, sin_ot=sin_ot)
            hb = sb if h2h else _serie_equipo(idb, temps4, 25, rival_id=ida, sin_ot=sin_ot)
        if ra and rb:
            _seccion_racha(eq_a, por_id[idb], ra, rb, ha, hb)
    elif idb and not es_pro:
        planes.bloque_pro("Líneas con racha y análisis IA", "Disponible en ScoreLine Pro.", "Racha H2H + Análisis IA", key="lock_fe_racha")
    st.caption("Back-to-back y estrellas ausentes se marcan en las barras (punto amarillo y rojo). Las estrellas son los 2 máximos anotadores de la ventana; "
               "si alguien llegó por traspaso a mitad de ventana, sus partidos previos cuentan como ausencia. \n\n"
               "La frecuencia es histórica (cuántas veces cumplieron la línea), no una predicción del partido. "
               "El hándicap del Equipo B es el opuesto al del A. Verde más intenso = superó la línea por más margen.")
