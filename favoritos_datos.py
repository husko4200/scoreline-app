"""Datos para la portada y las alertas: próximo partido, forma reciente, línea del día, lesiones y jugadores.

Todo viene de las mismas fuentes que ya usa la app (ESPN vía nba.py y nba_h2h_jugadores.py) y se guarda en caché con
tiempos cortos. Ninguna función lanza excepciones hacia afuera: si algo falla devuelve None / {} y la interfaz lo muestra
como «sin datos», nunca como un error.
"""
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st

import nba
from common import ZONA, get_json, num

try:                      # fuente de jugadores e historiales de la vista Jugadores
    import nba_h2h_jugadores as h
except Exception:  # noqa: BLE001
    h = None

try:                      # para que los hilos puedan usar la caché de Streamlit sin avisos
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
except Exception:  # noqa: BLE001
    add_script_run_ctx = get_script_run_ctx = None

ET = "America/New_York"   # ESPN agrupa el marcador por día en hora del este
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


# ---------------------------------------------------------------- en paralelo
def _paralelo(tareas, hilos=8):
    """Ejecuta funciones sin argumentos a la vez; devuelve sus resultados en orden (None donde una falle)."""
    tareas = list(tareas)
    if not tareas:
        return []
    ctx = get_script_run_ctx() if get_script_run_ctx else None

    def _corre(f):
        if ctx is not None:
            try:
                add_script_run_ctx(threading.current_thread(), ctx)
            except Exception:  # noqa: BLE001
                pass
        try:
            return f()
        except Exception:  # noqa: BLE001
            return None

    with ThreadPoolExecutor(min(hilos, len(tareas))) as pool:
        return list(pool.map(_corre, tareas))


# ---------------------------------------------------------------- imágenes
def escudo(abrev) -> str:
    a = str(abrev or "").strip().lower()
    return f"https://a.espncdn.com/i/teamlogos/nba/500/{a}.png" if re.fullmatch(r"[a-z]{2,5}", a) else ""


def foto(pid) -> str:
    return f"https://a.espncdn.com/i/headshots/nba/players/full/{pid}.png" if re.fullmatch(r"\d+", str(pid)) else ""


# ---------------------------------------------------------------- equipos y jugadores
@st.cache_data(ttl=86400, show_spinner=False)
def mapa_equipos() -> dict:
    """{id: {id, nombre, abrev}} de los 30 equipos (nba.equipos() ya trae un respaldo si ESPN falla)."""
    df = nba.equipos()
    return {str(r["id"]): {"id": str(r["id"]), "nombre": r["Equipo"], "abrev": r["Abrev"]} for _, r in df.iterrows()}


def equipo_por_abrev(abrev):
    a = str(abrev or "").upper()
    return next((e for e in mapa_equipos().values() if e["abrev"].upper() == a), None)


@st.cache_data(ttl=3600, show_spinner=False)
def jugadores_info() -> dict:
    """{id: {id, nombre, equipo (sigla)}} con la misma lista que usa la vista Jugadores."""
    if h is None:
        return {}
    try:
        return {str(j["id"]): {"id": str(j["id"]), "nombre": j.get("nombre") or "?", "equipo": str(j.get("equipo") or "")}
                for j in h._jugadores()}
    except Exception:  # noqa: BLE001
        return {}


def equipo_de_jugador(pid):
    inf = jugadores_info().get(str(pid))
    return equipo_por_abrev(inf["equipo"]) if inf else None


# ---------------------------------------------------------------- tiempo
def cuando(iso):
    """(texto, minutos que faltan) en la zona horaria de la app. Ej.: ('hoy 20:30', 135)."""
    try:
        t = pd.to_datetime(iso, utc=True).tz_convert(ZONA)
    except Exception:  # noqa: BLE001
        return "", None
    ahora = pd.Timestamp.now(tz=ZONA)
    mins = int((t - ahora).total_seconds() // 60)
    dif = (t.date() - ahora.date()).days
    dia = "hoy" if dif == 0 else "mañana" if dif == 1 else f"{DIAS[t.weekday()]} {t:%d/%m}"
    return f"{dia} {t:%H:%M}", mins


def cuenta_regresiva(mins) -> str:
    if mins is None:
        return ""
    if mins <= 0:
        return "ahora"
    if mins < 60:
        return f"en {mins} min"
    if mins < 1440:
        return f"en {mins // 60} h {mins % 60:02d} min"
    return f"en {mins // 1440} d"


# ---------------------------------------------------------------- calendario y forma
def _eventos_equipo(team_id) -> list:
    def pedir(params):
        try:
            return get_json(f"{nba.BASE}/teams/{team_id}/schedule", params=params, retries=1)
        except Exception:  # noqa: BLE001
            return None

    por_id = {}
    # temporada regular (o la fase actual) + playoffs, las dos consultas a la vez
    for j in _paralelo([lambda: pedir(None), lambda: pedir({"seasontype": 3})], 2):
        for e in (j or {}).get("events", []):
            por_id[str(e.get("id"))] = e
    return list(por_id.values())


@st.cache_data(ttl=300, show_spinner=False)
def calendario(team_id) -> dict:
    """{'proximo': {...} | None, 'forma': [{res, pf, pc, rival, local, fecha}] (del más reciente al más antiguo)}."""
    pend, hechos = [], []
    for ev in _eventos_equipo(team_id):
        comp = (ev.get("competitions") or [{}])[0]
        est = (comp.get("status") or ev.get("status") or {}).get("type") or {}
        cs = comp.get("competitors") or []
        mio = next((c for c in cs if str((c.get("team") or {}).get("id")) == str(team_id)), None)
        riv = next((c for c in cs if c is not mio), None)
        if not mio or not riv:
            continue
        rt = riv.get("team") or {}
        base = {"evento": str(ev.get("id")), "fecha": ev.get("date") or comp.get("date") or "",
                "rival_id": str(rt.get("id", "")), "rival": rt.get("abbreviation", ""),
                "rival_nombre": rt.get("displayName", ""), "local": mio.get("homeAway") == "home"}
        if est.get("completed"):
            a, b = num(mio.get("score")), num(riv.get("score"))
            if a is not None and b is not None:
                hechos.append({**base, "res": "G" if a > b else "P", "pf": int(a), "pc": int(b)})
        elif est.get("state") in ("pre", "in"):
            pend.append({**base, "estado": est.get("state")})
    pend.sort(key=lambda x: x["fecha"])
    hechos.sort(key=lambda x: x["fecha"])
    forma = hechos[-5:][::-1]
    racha = 0
    for g in hechos[::-1]:
        if racha and g["res"] != hechos[-1]["res"]:
            break
        racha += 1
    return {"proximo": pend[0] if pend else None, "forma": forma,
            "racha": f"{hechos[-1]['res']}{racha}" if hechos else ""}


def calendario_seguro(team_id) -> dict:
    try:
        return calendario(str(team_id))
    except Exception:  # noqa: BLE001
        return {"proximo": None, "forma": [], "racha": ""}


# ---------------------------------------------------------------- línea del día
def spread_local(txt, abrev_local):
    """Handicap del LOCAL a partir de un texto como «BOS -3.5» (negativo = el local es favorito)."""
    t = str(txt or "").strip()
    if t.upper() in ("EVEN", "PK", "PICK", "PICK'EM"):
        return 0.0
    m = re.match(r"([A-Za-z]{2,5})\s*([+-]?\d+(?:\.\d+)?)", t)
    if not m:
        return None
    v = float(m.group(2))
    return v if m.group(1).upper() == str(abrev_local or "").upper() else -v


def linea(evento, fecha_iso):
    """{txt, total, spread_local, local, visita} del partido, o None si ESPN aún no publica línea."""
    try:
        dia = pd.to_datetime(fecha_iso, utc=True).tz_convert(ET).strftime("%Y%m%d")
        juegos = nba.scoreboard(dia)
    except Exception:  # noqa: BLE001
        return None
    j = next((g for g in juegos if str(g.get("id")) == str(evento)), None)
    if not j or (not j.get("linea_txt") and j.get("linea_total") is None):
        return None
    return {"txt": j.get("linea_txt"), "total": j.get("linea_total"),
            "spread_local": spread_local(j.get("linea_txt"), j["local"]["abrev"]),
            "local": j["local"]["abrev"], "visita": j["visita"]["abrev"]}


# ---------------------------------------------------------------- lesiones
def fecha_corta(iso) -> str:
    """'2026-11-28T...' -> '28/11'; '' si no hay fecha válida (ESPN no siempre da el regreso estimado)."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{m.group(3)}/{m.group(2)}" if m else ""


@st.cache_data(ttl=120, show_spinner=False)
def _lesiones_espn() -> dict:
    j = get_json(nba.BASE + "/injuries")          # si falla lanza: así un error no queda guardado en caché
    out = {}
    for eq in j.get("injuries") or []:
        tid = str(eq.get("id"))
        for it in eq.get("injuries") or []:
            a = it.get("athlete") or {}
            pid = str(a.get("id") or "")
            if not pid:
                continue
            det = it.get("details") or {}
            les = " ".join(str(x) for x in (det.get("side"), det.get("type"), det.get("location") or det.get("detail")) if x) \
                or it.get("shortComment") or ""
            out[pid] = {"id": pid, "nombre": a.get("displayName") or a.get("fullName") or "?", "equipo_id": tid,
                        "estado": it.get("status") or (it.get("type") or {}).get("description") or "?", "lesion": les,
                        "regreso": fecha_corta(det.get("returnDate"))}
    return out


def lesiones():
    """{id_jugador: {...}} o None si no se pudo leer (distinto de {} = «nadie lesionado»)."""
    try:
        return _lesiones_espn()
    except Exception:  # noqa: BLE001
        return None


def nivel_lesion(estado) -> str:
    """'out' | 'dudoso' | 'duda' | 'probable' (para el color del chip)."""
    e = str(estado or "").lower()
    if e.startswith("out") or "suspen" in e:
        return "out"
    if "doubtful" in e:
        return "dudoso"
    if "probable" in e:
        return "probable"
    return "duda"                                 # questionable / day-to-day / sin dato


# ---------------------------------------------------------------- forma de un jugador
@st.cache_data(ttl=900, show_spinner=False)
def forma_jugador(pid, n=5):
    """Promedios de sus últimos n partidos + serie de puntos (antiguo → reciente). None si no hay datos."""
    if h is None:
        return None
    act = nba.temporada_actual()
    hist = []
    for temps in ([act], [act, act - 1]):
        try:
            hist = h._historial(str(pid), temps, True)
        except Exception:  # noqa: BLE001
            hist = []
        if hist:
            break
    hist = sorted(hist, key=lambda g: g.get("fecha", ""), reverse=True)[:n]
    if not hist:
        return None

    def prom(c):
        v = []
        for g in hist:
            try:
                if g.get(c) is not None:
                    v.append(float(g[c]))
            except (TypeError, ValueError):
                pass
        return round(sum(v) / len(v), 1) if v else None

    def pts(g):
        try:
            return float(g.get("PTS") or 0)
        except (TypeError, ValueError):
            return 0.0

    return {"pts": prom("PTS"), "reb": prom("REB"), "ast": prom("AST"), "n": len(hist),
            "serie": [pts(g) for g in hist][::-1]}


def forma_jugador_segura(pid):
    try:
        return forma_jugador(str(pid))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- precarga
def precargar(equipos_ids, jugadores_ids):
    """Calienta la caché con TODO lo que necesitan la portada y las alertas, pidiendo las cosas a la vez
    (antes se pedía un equipo o jugador tras otro). Después, las funciones de arriba responden al instante."""
    ids_eq = {str(t) for t in equipos_ids}
    for pid in jugadores_ids:
        eq = equipo_de_jugador(pid)
        if eq:
            ids_eq.add(eq["id"])
    _paralelo([lesiones] + [lambda t=t: calendario_seguro(t) for t in ids_eq]
              + [lambda p=p: forma_jugador_segura(p) for p in jugadores_ids])
    proximos = {}
    for t in ids_eq:
        prox = calendario_seguro(t).get("proximo")
        if prox:
            proximos[prox["evento"]] = prox
    _paralelo([lambda pr=pr: linea(pr["evento"], pr["fecha"]) for pr in proximos.values()])
