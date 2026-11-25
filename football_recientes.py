"""Fútbol · últimos partidos de un equipo en TODAS las competiciones (liga, Champions, Europa League, copas, amistosos).

football-data.co.uk solo trae partidos de liga y con retraso, así que los «Últimos 5/10/...» salían incompletos
(faltaban Champions y los partidos más nuevos). Aquí se leen los marcadores de ESPN (scoreboard por rango de fechas) y,
para cada partido terminado, sus estadísticas (tiros, tiros a puerta, córners, faltas, tarjetas).

Devuelve un DataFrame con las MISMAS columnas que football.partidos_por_equipo, así que el resto de la app no cambia.
Si ESPN falla, football_lineas usa los datos de liga como antes.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from common import get_json

ESPN_SCORE = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"
ESPN_RESUMEN = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary"

DIAS_ATRAS = 150      # ventana de búsqueda (alcanza de sobra para 25 partidos)
TROZO_DIAS = 50       # el scoreboard se pide en trozos para que ESPN no recorte la lista
EUROPA = ["uefa.champions", "uefa.europa", "uefa.europa.conf", "uefa.super_cup"]
COPAS = {
    "eng.1": ["eng.fa", "eng.league_cup"], "esp.1": ["esp.copa_del_rey", "esp.super_cup"], "ger.1": ["ger.dfb_pokal"],
    "ita.1": ["ita.coppa_italia", "ita.super_cup"], "fra.1": ["fra.coupe_de_france"],
    "eng.2": ["eng.fa", "eng.league_cup"], "esp.2": ["esp.copa_del_rey"], "ger.2": ["ger.dfb_pokal"],
    "ita.2": ["ita.coppa_italia"], "fra.2": ["fra.coupe_de_france"],
    "arg.1": [], "bra.1": [], "mex.1": [], "usa.1": [],
}
EXTRA_AMERICA = {"arg.1": ["conmebol.libertadores", "conmebol.sudamericana"], "bra.1": ["conmebol.libertadores", "conmebol.sudamericana"],
                 "mex.1": ["concacaf.champions"], "usa.1": ["concacaf.champions"]}
AMISTOSOS = ["club.friendly"]

_lock = threading.Lock()
_cache: dict = {}


def limpiar_cache():
    with _lock:
        _cache.clear()


def _cacheado(clave, ttl, fn):
    """fn() devuelve el valor, o None si falló. Los aciertos se guardan `ttl` segundos; los fallos solo 2 minutos
    (así no se reintenta en cada clic, pero tampoco se esconde un fallo pasajero mucho rato). Los fallos dan None."""
    ahora = time.time()
    with _lock:
        hit = _cache.get(clave)
    if hit and ahora < hit[0]:
        return hit[1]
    valor = fn()
    with _lock:
        _cache[clave] = (ahora + (ttl if valor is not None else 120), valor)
    return valor


def competiciones(liga_espn):
    """Códigos de ESPN donde puede haber jugado un equipo de esta liga."""
    europeo = liga_espn not in EXTRA_AMERICA
    out = [liga_espn] + COPAS.get(liga_espn, []) + (EUROPA if europeo else []) + EXTRA_AMERICA.get(liga_espn, []) + AMISTOSOS
    return list(dict.fromkeys(out))


def _num(v):
    if isinstance(v, dict):
        v = v.get("value", v.get("displayValue"))
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


# ---------------------------------------------------------------- marcadores
def _eventos(slug, d1, d2):
    """Partidos terminados de una competición entre dos fechas (YYYYMMDD). Si falla devuelve [] sin romper nada."""
    def pedir():
        try:
            js = get_json(ESPN_SCORE.format(slug=slug), params={"dates": f"{d1}-{d2}", "limit": 400}, retries=1)
        except Exception:  # noqa: BLE001
            return None
        out = []
        for e in js.get("events", []):
            comp = (e.get("competitions") or [{}])[0]
            est = (comp.get("status") or e.get("status") or {}).get("type") or {}
            if not (est.get("completed") or est.get("state") == "post"):
                continue
            cs = comp.get("competitors") or []
            loc = next((c for c in cs if c.get("homeAway") == "home"), None)
            vis = next((c for c in cs if c.get("homeAway") == "away"), None)
            if not loc or not vis:
                continue
            gl, gv = _num(loc.get("score")), _num(vis.get("score"))
            if np.isnan(gl) or np.isnan(gv):
                continue
            eq = lambda c: {"id": str((c.get("team") or {}).get("id")), "nombre": (c.get("team") or {}).get("displayName") or "?",  # noqa: E731
                           "abbr": (c.get("team") or {}).get("abbreviation") or ""}
            out.append({"id": str(e.get("id")), "slug": slug, "fecha": e.get("date"), "neutral": bool(comp.get("neutralSite")),
                        "local": eq(loc), "visita": eq(vis), "gl": gl, "gv": gv})
        return out
    # un fallo no se guarda mucho rato en caché (para reintentar pronto); un acierto, 15 min
    return _cacheado(("ev", slug, d1, d2), 900, pedir) or []


def _partidos_equipo(espn_id, liga_espn):
    hoy = pd.Timestamp.today().normalize()
    ini = hoy - pd.Timedelta(days=DIAS_ATRAS)
    trozos, a = [], ini
    while a <= hoy:
        b = min(a + pd.Timedelta(days=TROZO_DIAS - 1), hoy)
        trozos.append((a.strftime("%Y%m%d"), b.strftime("%Y%m%d")))
        a = b + pd.Timedelta(days=1)
    tareas = [(s, d1, d2) for s in competiciones(liga_espn) for d1, d2 in trozos]
    with ThreadPoolExecutor(8) as ex:
        resultados = list(ex.map(lambda x: _eventos(*x), tareas))
    vistos, mios = set(), []
    for lista in resultados:
        for e in lista:
            if e["id"] in vistos:
                continue
            if str(espn_id) in (e["local"]["id"], e["visita"]["id"]):
                vistos.add(e["id"])
                mios.append(e)
    mios.sort(key=lambda e: e["fecha"] or "")
    return mios


# ---------------------------------------------------------------- estadísticas del partido
_STATS = {"totalShots": "Tiros", "shotsOnTarget": "TP", "wonCorners": "Corners", "foulsCommitted": "Faltas",
          "yellowCards": "Amarillas", "redCards": "Rojas"}


def _stats_partido(slug, evento_id):
    """{id de equipo ESPN: {Tiros, TP, Corners, Faltas, Amarillas, Rojas}}. Un partido terminado no cambia: caché de 7 días."""
    def pedir():
        try:
            js = get_json(ESPN_RESUMEN.format(slug=slug), params={"event": evento_id})
        except Exception:  # noqa: BLE001
            return None
        out = {}
        for t in (js.get("boxscore") or {}).get("teams", []):
            d = {}
            for s in t.get("statistics") or []:
                k = _STATS.get(s.get("name"))
                if k:
                    d[k] = _num(s.get("value", s.get("displayValue")))
            out[str((t.get("team") or {}).get("id"))] = d
        return out
    return _cacheado(("st", slug, evento_id), 7 * 86400, pedir) or {}


# ---------------------------------------------------------------- tabla del equipo
def ultimos(espn_id, nombre_equipo, n, liga_espn, sede=None):
    """Últimos `n` partidos terminados del equipo en todas las competiciones, del más antiguo al más reciente.
    Mismas columnas que football.partidos_por_equipo (+ RivalAbbr). DataFrame vacío si ESPN no responde."""
    if not espn_id or not liga_espn:
        return pd.DataFrame()
    eventos = _partidos_equipo(espn_id, liga_espn)
    if sede:   # «Local» / «Visita»: se filtra ANTES de tomar los últimos n (los n últimos de esa sede, no de todos)
        eventos = [e for e in eventos if (e["local"]["id"] == str(espn_id)) == (sede == "Local") and not e["neutral"]]
    eventos = eventos[-n:]
    if not eventos:
        return pd.DataFrame()
    with ThreadPoolExecutor(8) as ex:
        stats = list(ex.map(lambda e: _stats_partido(e["slug"], e["id"]), eventos))
    eid, filas = str(espn_id), []
    for e, st_ in zip(eventos, stats):
        es_local = e["local"]["id"] == eid
        yo, rv = (e["local"], e["visita"]) if es_local else (e["visita"], e["local"])
        gf, gc = (e["gl"], e["gv"]) if es_local else (e["gv"], e["gl"])
        a, b = st_.get(eid, {}), st_.get(rv["id"], {})
        fecha = pd.to_datetime(e["fecha"], utc=True, errors="coerce")
        filas.append({"Date": fecha.tz_localize(None) if pd.notna(fecha) else pd.NaT, "Temporada": "ESPN", "Equipo": nombre_equipo,
                      "Rival": rv["nombre"], "RivalAbbr": rv["abbr"], "Condicion": "Local" if es_local else "Visita",
                      "Neutral": e["neutral"], "GF": gf, "GC": gc, "GF1T": np.nan, "GC1T": np.nan,
                      "Tiros": a.get("Tiros", np.nan), "TirosRival": b.get("Tiros", np.nan),
                      "TP": a.get("TP", np.nan), "TPRival": b.get("TP", np.nan),
                      "Corners": a.get("Corners", np.nan), "CornersRival": b.get("Corners", np.nan),
                      "Faltas": a.get("Faltas", np.nan), "Amarillas": a.get("Amarillas", np.nan), "Rojas": a.get("Rojas", np.nan),
                      "FaltasRival": b.get("Faltas", np.nan), "AmarillasRival": b.get("Amarillas", np.nan), "RojasRival": b.get("Rojas", np.nan)})
    t = pd.DataFrame(filas).dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    t["Resultado"] = np.where(t.GF > t.GC, "G", np.where(t.GF < t.GC, "P", "E"))
    t["Puntos"] = t["Resultado"].map({"G": 3, "E": 1, "P": 0})
    t["Gana"], t["Pierde"] = t.Resultado == "G", t.Resultado == "P"
    t["SinPerder"], t["SinGanar"] = t.Resultado != "P", t.Resultado != "G"
    t["ArcoEnCero"], t["Anota"], t["Concede"] = t.GC == 0, t.GF > 0, t.GC > 0
    t["Total"], t["Margen"] = t.GF + t.GC, t.GF - t.GC
    t["Over25"], t["BTTS"] = t.Total > 2.5, (t.GF > 0) & (t.GC > 0)
    t["BTTSn"] = t["BTTS"].astype(float)
    t["Goles1T"], t["Goles2T"] = np.nan, np.nan   # ESPN no da el marcador del descanso de forma fiable
    t["CornersTotal"] = t.Corners + t.CornersRival
    dia = t["Date"].dt.normalize()
    desc = (dia - dia.shift()).dt.days - 1
    t["Descanso"] = desc.where(desc <= 14).clip(lower=0)
    return t
