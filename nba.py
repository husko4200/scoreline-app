"""NBA: en vivo, H2H histórico, rachas, análisis por equipo y Elo.

Datos: API pública (no oficial) de ESPN. Las temporadas cerradas se guardan en disco
(persist="disk"), así que la primera carga es lenta y las siguientes son instantáneas.
"""
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import altair as alt
import graficos
import numpy as np
import pandas as pd
import requests
import streamlit as st

from common import (COLOR_A, COLOR_B, COLOR_NEG, COLOR_NEUTRO, COLOR_POS, PALETA, ZONA, buscar_rachas,
                    get_json, mostrar_rachas, num, racha_actual, racha_maxima, racha_resultado)

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"


# ================================================================ datos
def temporada_actual() -> int:
    """ESPN nombra la temporada por el año en que termina (2027 = 2026-27)."""
    hoy = date.today()
    return hoy.year + 1 if hoy.month >= 10 else hoy.year


def etiqueta(s: int) -> str:
    return f"{s - 1}-{str(s)[2:]}"


# Respaldo con los 30 equipos (id de ESPN, abreviatura, nombre) por si la API de ESPN no responde.
_RESPALDO = [
    ("1", "ATL", "Atlanta Hawks"), ("2", "BOS", "Boston Celtics"), ("17", "BKN", "Brooklyn Nets"),
    ("30", "CHA", "Charlotte Hornets"), ("4", "CHI", "Chicago Bulls"), ("5", "CLE", "Cleveland Cavaliers"),
    ("6", "DAL", "Dallas Mavericks"), ("7", "DEN", "Denver Nuggets"), ("8", "DET", "Detroit Pistons"),
    ("9", "GS", "Golden State Warriors"), ("10", "HOU", "Houston Rockets"), ("11", "IND", "Indiana Pacers"),
    ("12", "LAC", "LA Clippers"), ("13", "LAL", "Los Angeles Lakers"), ("29", "MEM", "Memphis Grizzlies"),
    ("14", "MIA", "Miami Heat"), ("15", "MIL", "Milwaukee Bucks"), ("16", "MIN", "Minnesota Timberwolves"),
    ("3", "NO", "New Orleans Pelicans"), ("18", "NY", "New York Knicks"), ("25", "OKC", "Oklahoma City Thunder"),
    ("19", "ORL", "Orlando Magic"), ("20", "PHI", "Philadelphia 76ers"), ("21", "PHX", "Phoenix Suns"),
    ("22", "POR", "Portland Trail Blazers"), ("23", "SAC", "Sacramento Kings"), ("24", "SA", "San Antonio Spurs"),
    ("28", "TOR", "Toronto Raptors"), ("26", "UTAH", "Utah Jazz"), ("27", "WSH", "Washington Wizards"),
]


@st.cache_data(ttl=86400, show_spinner=False)
def _equipos_api() -> pd.DataFrame:
    """Equipos desde ESPN. Si falla LANZA error, así Streamlit no guarda un resultado malo en caché."""
    j = get_json(f"{BASE}/teams", params={"limit": 40})
    ts = j["sports"][0]["leagues"][0]["teams"]
    filas = [{"id": str(t["team"]["id"]), "Equipo": t["team"]["displayName"],
              "Abrev": t["team"].get("abbreviation", "")} for t in ts]
    if len(filas) < 20:
        raise RuntimeError("lista de equipos incompleta")
    return pd.DataFrame(filas).sort_values("Equipo").reset_index(drop=True)


def equipos() -> pd.DataFrame:
    """Equipos de la NBA: ESPN si responde; si no, la lista de respaldo (nunca queda vacía)."""
    try:
        return _equipos_api()
    except Exception:  # noqa: BLE001
        filas = [{"id": i, "Equipo": n, "Abrev": a} for i, a, n in _RESPALDO]
        return pd.DataFrame(filas).sort_values("Equipo").reset_index(drop=True)


def _calendario(team_id: str, season: int, tipo: int):
    """Partidos terminados de un equipo. None = error de red; [] = sin partidos."""
    try:
        j = get_json(f"{BASE}/teams/{team_id}/schedule",
                     params={"season": season, "seasontype": tipo}, retries=1)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (400, 404):
            return []
        return None
    except Exception:  # noqa: BLE001
        return None
    filas = []
    for e in j.get("events", []):
        comp = (e.get("competitions") or [{}])[0]
        estado = ((comp.get("status") or e.get("status") or {}).get("type") or {})
        if not estado.get("completed"):
            continue
        cs = comp.get("competitors") or []
        loc = next((c for c in cs if c.get("homeAway") == "home"), None)
        vis = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not loc or not vis:
            continue
        pl, pv = num(loc.get("score")), num(vis.get("score"))
        if pl is None or pv is None:
            continue

        def info(c):
            t = c.get("team") or {}
            return str(t.get("id", c.get("id"))), t.get("displayName") or t.get("name")

        (hid, hn), (aid, an) = info(loc), info(vis)
        filas.append({"event_id": str(e.get("id")), "Date": e.get("date") or comp.get("date"),
                      "season": season, "tipo": "Playoffs" if tipo == 3 else "Regular",
                      "home_id": hid, "home_name": hn, "home_pts": pl,
                      "away_id": aid, "away_name": an, "away_pts": pv})
    return filas


def _descargar_temporada(season: int, playoffs: bool) -> pd.DataFrame:
    eq = equipos()
    tipos = [2, 3] if playoffs else [2]
    trabajos = [(tid, season, tp) for tid in eq["id"] for tp in tipos]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda a: _calendario(*a), trabajos))
    errores = sum(r is None for r in res)
    filas = [f for r in res if r for f in r]
    if errores:
        # No se cachea: así un fallo de red no queda guardado en disco.
        raise RuntimeError(f"datos incompletos ({errores} de {len(trabajos)} consultas fallaron)")
    if not filas:
        raise RuntimeError("sin partidos terminados")
    df = pd.DataFrame(filas).drop_duplicates("event_id")
    df["Date"] = (pd.to_datetime(df["Date"], utc=True).dt.tz_convert("America/New_York")
                  .dt.tz_localize(None))
    return df.sort_values("Date").reset_index(drop=True)


@st.cache_data(show_spinner=False, persist="disk")
def _temporada_cerrada(season: int, playoffs: bool) -> pd.DataFrame:
    return _descargar_temporada(season, playoffs)


@st.cache_data(ttl=1800, show_spinner=False)
def _temporada_en_curso(season: int, playoffs: bool) -> pd.DataFrame:
    return _descargar_temporada(season, playoffs)


def temporada(season: int, playoffs: bool) -> pd.DataFrame:
    f = _temporada_en_curso if season >= temporada_actual() else _temporada_cerrada
    return f(season, playoffs)


def a_largo(g: pd.DataFrame) -> pd.DataFrame:
    """Una fila por equipo y partido, con descanso, margen y banderas para rachas."""
    comunes = ["event_id", "Date", "season", "Temporada", "tipo"]
    h = g[comunes].copy()
    h["Equipo"], h["EquipoId"], h["Rival"] = g["Local"], g["home_id"], g["Visita"]
    h["Condicion"], h["PF"], h["PC"] = "Local", g["home_pts"], g["away_pts"]
    a = g[comunes].copy()
    a["Equipo"], a["EquipoId"], a["Rival"] = g["Visita"], g["away_id"], g["Local"]
    a["Condicion"], a["PF"], a["PC"] = "Visita", g["away_pts"], g["home_pts"]
    t = pd.concat([h, a], ignore_index=True).sort_values(["Equipo", "Date"]).reset_index(drop=True)
    t["Gana"] = t["PF"] > t["PC"]
    t["Pierde"] = ~t["Gana"]
    t["Margen"] = t["PF"] - t["PC"]
    t["Total"] = t["PF"] + t["PC"]
    t["Resultado"] = np.where(t["Gana"], "G", "P")
    dia = t["Date"].dt.normalize()
    prev = dia.groupby(t["Equipo"]).shift()
    desc = (dia - prev).dt.days - 1
    t["Descanso"] = desc.where(desc <= 10).clip(lower=0)  # >10 días = inicio de temporada
    return t


def calcular_elo(g: pd.DataFrame, k: float = 20.0, ventaja: float = 100.0):
    """Elo estilo FiveThirtyEight: multiplicador por margen y regresión entre temporadas."""
    rat, ult_temp, hist = {}, {}, []
    for r in g.sort_values("Date").itertuples(index=False):
        h, a = r.home_id, r.away_id
        for tm in (h, a):
            if tm not in rat:
                rat[tm] = 1500.0
            elif ult_temp.get(tm) != r.season:
                rat[tm] = 0.75 * rat[tm] + 0.25 * 1505.0
            ult_temp[tm] = r.season
        rh, ra = rat[h], rat[a]
        dif = rh + ventaja - ra
        esp_h = 1 / (1 + 10 ** (-dif / 400))
        gana_h = r.home_pts > r.away_pts
        mov = abs(r.home_pts - r.away_pts)
        dif_gan = dif if gana_h else -dif
        mult = (mov + 3) ** 0.8 / (7.5 + 0.006 * dif_gan)
        delta = k * mult * ((1.0 if gana_h else 0.0) - esp_h)
        rat[h], rat[a] = rh + delta, ra - delta
        hist.append((r.Date, h, rat[h]))
        hist.append((r.Date, a, rat[a]))
    return rat, pd.DataFrame(hist, columns=["Date", "id", "Elo"])


def prob_elo(rat: dict, a: str, b: str, a_local: bool, ventaja: float = 100.0):
    dif = rat[a] - rat[b] + (ventaja if a_local else -ventaja)
    return 1 / (1 + 10 ** (-dif / 400)), dif / 28.0  # 1 punto de margen ≈ 28 Elo


def calcular_srs(ts: pd.DataFrame) -> pd.Series:
    """Simple Rating System: margen medio ajustado por la fuerza de los rivales."""
    mm = ts.groupby("Equipo")["Margen"].mean()
    r = mm.copy()
    for _ in range(100):
        opp = ts.assign(rr=ts["Rival"].map(r)).groupby("Equipo")["rr"].mean()
        r = mm + opp
        r = r - r.mean()
    return r


def cargar_liga(temporadas: list[int], playoffs: bool):
    clave = ("nba", tuple(temporadas), playoffs)
    if clave in st.session_state:
        return st.session_state[clave]
    barra = st.progress(0.0, text="Cargando temporadas de la NBA...")
    frames, fallos = [], []
    for i, s in enumerate(temporadas):
        barra.progress(i / len(temporadas), text=f"Temporada {etiqueta(s)} ({i + 1}/{len(temporadas)})...")
        try:
            frames.append(temporada(s, playoffs))
        except Exception as e:  # noqa: BLE001
            fallos.append((s, str(e)))
    barra.empty()
    if not frames:
        return None, None, None, None, fallos
    g = pd.concat(frames, ignore_index=True).drop_duplicates("event_id")
    mapa = equipos().set_index("id")["Equipo"]
    g["Local"] = g["home_id"].map(mapa).fillna(g["home_name"])
    g["Visita"] = g["away_id"].map(mapa).fillna(g["away_name"])
    g["Temporada"] = g["season"].map(etiqueta)
    g = g.sort_values("Date").reset_index(drop=True)
    t = a_largo(g)
    rat, hist = calcular_elo(g)
    hist["Equipo"] = hist["id"].map(mapa)
    res = (g, t, rat, hist, fallos)
    st.session_state[clave] = res
    return res


# ================================================================ EN VIVO
def _reloj_seg(est: dict):
    c = num(est.get("clock"))
    if c is not None:
        return c
    d = str(est.get("displayClock") or "")
    try:
        if ":" in d:
            m, s = d.split(":")
            return int(m) * 60 + float(s)
        return float(d)
    except ValueError:
        return None


def minutos_jugados(periodo: int, reloj_seg) -> float:
    resto = (reloj_seg or 0) / 60
    if periodo <= 4:
        return (periodo - 1) * 12 + (12 - resto)
    return 48 + (periodo - 5) * 5 + (5 - resto)


def margen_esperado_local(odds, abrev_local: str, abrev_visita: str):
    """Margen esperado del local según la línea de ESPN ('BOS -4.5'); None si no hay."""
    if not odds:
        return None
    d = str(odds.get("details") or "").strip()
    if d.upper().startswith("EVEN") or d.upper() == "PK":
        return 0.0
    partes = d.split()
    if len(partes) >= 2:
        try:
            v = float(partes[-1])
        except ValueError:
            return None
        ab = partes[0].upper()
        if ab == (abrev_local or "").upper():
            return -v
        if ab == (abrev_visita or "").upper():
            return v
    return None


def prob_victoria_local(dif_local: float, frac_restante: float, margen_esp: float) -> float:
    """Normal con σ≈12 pts por partido; la ventaja pre-partido se diluye con el tiempo."""
    if frac_restante <= 0:
        return 1.0 if dif_local > 0 else 0.0 if dif_local < 0 else 0.5
    mu = dif_local + margen_esp * frac_restante
    sd = 12.0 * math.sqrt(frac_restante)
    return 0.5 * (1 + math.erf(mu / (sd * math.sqrt(2))))


def proyectar_total(total_pts: float, jugados: float, periodo: int, linea):
    """Proyección del total final mezclando ritmo observado y línea pre-partido."""
    if jugados <= 0:
        return linea, None
    dur = 48 if periodo <= 4 else 48 + 5 * (periodo - 4)
    resto = max(dur - jugados, 0)
    obs = total_pts / jugados
    if linea:
        w = jugados / (jugados + 12.0)
        ritmo = w * obs + (1 - w) * linea / 48
    else:
        ritmo = obs
    return total_pts + ritmo * resto, obs * 48


def _parse_juego(e: dict):
    comp = (e.get("competitions") or [{}])[0]
    est = e.get("status") or comp.get("status") or {}
    tipo = est.get("type") or {}
    cs = comp.get("competitors") or []
    loc = next((c for c in cs if c.get("homeAway") == "home"), None)
    vis = next((c for c in cs if c.get("homeAway") == "away"), None)
    if not loc or not vis:
        return None

    def lado(c):
        t = c.get("team") or {}
        p = num(c.get("score"))
        return {"id": str(t.get("id", c.get("id"))), "nombre": t.get("displayName") or t.get("name") or "?",
                "abrev": t.get("abbreviation") or "", "puntos": 0.0 if p is None else p,
                "record": ((c.get("records") or [{}])[0]).get("summary"),
                "q": [int(v) for v in (num(l) for l in c.get("linescores", [])) if v is not None]}

    odds = (comp.get("odds") or [None])[0]
    L, V = lado(loc), lado(vis)
    periodo = int(est.get("period") or 0)
    return {"id": str(e.get("id")), "estado": tipo.get("state", "pre"),
            "detalle": tipo.get("shortDetail") or tipo.get("detail") or "",
            "fecha": e.get("date"), "periodo": periodo, "reloj": _reloj_seg(est),
            "local": L, "visita": V,
            "margen_esp": margen_esperado_local(odds, L["abrev"], V["abrev"]),
            "linea_txt": (odds or {}).get("details"), "linea_total": num((odds or {}).get("overUnder"))}


@st.cache_data(ttl=15, show_spinner=False)
def scoreboard(fecha: str) -> list[dict]:
    j = get_json(f"{BASE}/scoreboard", params={"dates": fecha})
    return [x for x in (_parse_juego(e) for e in j.get("events", [])) if x]


@st.cache_data(ttl=15, show_spinner=False)
def resumen(event_id: str) -> dict:
    return get_json(f"{BASE}/summary", params={"event": event_id})


def analisis_vivo(j: dict) -> dict:
    """Métricas calculadas a partir del marcador (sin llamadas extra)."""
    L, V = j["local"], j["visita"]
    total = L["puntos"] + V["puntos"]
    dif = L["puntos"] - V["puntos"]
    out = {"total": total, "dif": dif}
    if j["estado"] == "in" and j["periodo"] > 0:
        jug = minutos_jugados(j["periodo"], j["reloj"])
        dur = 48 if j["periodo"] <= 4 else 48 + 5 * (j["periodo"] - 4)
        frac = max(dur - jug, 0) / 48
        me = j["margen_esp"] if j["margen_esp"] is not None else 2.5
        out.update(jugados=jug, prob_local=prob_victoria_local(dif, frac, me),
                   usa_linea=j["margen_esp"] is not None)
        proy, ritmo = proyectar_total(total, jug, j["periodo"], j["linea_total"])
        out.update(proy_total=proy, ritmo48=ritmo)
    elif j["estado"] == "post":
        out["prob_local"] = 1.0 if dif > 0 else 0.0
    return out


def _tabla_box(s: dict) -> dict:
    out = {}
    for blk in (s.get("boxscore") or {}).get("players", []):
        nombre = (blk.get("team") or {}).get("displayName", "Equipo")
        stats = (blk.get("statistics") or [{}])[0]
        etiquetas = stats.get("labels") or stats.get("names") or []
        filas = []
        for a in stats.get("athletes", []):
            if a.get("didNotPlay"):
                continue
            fila = {"Jugador": (a.get("athlete") or {}).get("displayName", "?")}
            fila.update(dict(zip(etiquetas, a.get("stats", []))))
            filas.append(fila)
        out[nombre] = pd.DataFrame(filas)
    return out


def _tabla_equipos(s: dict) -> pd.DataFrame:
    eqs = (s.get("boxscore") or {}).get("teams", [])
    if len(eqs) < 2:
        return pd.DataFrame()
    cols = {}
    for e in eqs:
        nombre = (e.get("team") or {}).get("displayName", "Equipo")
        cols[nombre] = {x.get("label") or x.get("name"): x.get("displayValue") for x in e.get("statistics", [])}
    return pd.DataFrame(cols).dropna(how="all")


def _racha_anotacion(plays: list, nombre_por_id: dict):
    """Parcial actual: puntos seguidos del mismo equipo en las últimas jugadas de anotación."""
    equipo, corrida = None, 0
    for p in reversed(plays):
        if not p.get("scoringPlay"):
            continue
        tid = str((p.get("team") or {}).get("id"))
        if equipo is None:
            equipo = tid
        if tid != equipo:
            break
        corrida += int(num(p.get("scoreValue")) or 0)
    return nombre_por_id.get(equipo, equipo), corrida


def _box_rico(s: dict) -> list[dict]:
    """Extrae box score por equipo con id, foto, posición, titularidad y stats."""
    import favoritos_datos as _fd
    equipos = []
    for blk in (s.get("boxscore") or {}).get("players", []):
        tm = blk.get("team") or {}
        nombre = tm.get("displayName", "Equipo")
        abrev = (tm.get("abbreviation") or "").upper()
        stats_blk = (blk.get("statistics") or [{}])[0]
        etiquetas = stats_blk.get("labels") or stats_blk.get("names") or []
        jugadores = []
        for a in stats_blk.get("athletes", []):
            if a.get("didNotPlay"):
                continue
            ath = a.get("athlete") or {}
            pid = str(ath.get("id") or "")
            nom = ath.get("shortName") or ath.get("displayName") or "?"
            pos = (ath.get("position") or {}).get("abbreviation") or ""
            dorsal = str(ath.get("jersey") or "")
            st_map = dict(zip(etiquetas, a.get("stats", [])))
            jugadores.append({
                "id": pid,
                "nom": nom,
                "pos": pos,
                "dorsal": dorsal,
                "starter": bool(a.get("starter")),
                "foto": _fd.foto(pid),
                "stats": st_map,
            })
        equipos.append({
            "id": str(tm.get("id") or ""),
            "nombre": nombre,
            "abrev": abrev,
            "logo": _fd.escudo(abrev),
            "etiquetas": etiquetas,
            "jugadores": jugadores,
        })
    return equipos


_ES_STATS_NBA = {
    "FG": "Tiros de campo", "Field Goals Made-Attempted": "Tiros de campo",
    "Field Goal %": "% Tiros de campo", "FG%": "% Tiros de campo",
    "3PT": "Triples", "Three Point %": "% Triples", "3P%": "% Triples",
    "FT": "Tiros libres", "Free Throw %": "% Tiros libres", "FT%": "% Tiros libres",
    "Rebounds": "Rebotes totales", "Offensive Rebounds": "Rebotes ofensivos",
    "Defensive Rebounds": "Rebotes defensivos", "Assists": "Asistencias",
    "Steals": "Robos", "Blocks": "Tapones", "Turnovers": "Pérdidas",
    "Total Turnovers": "Pérdidas", "Points in Paint": "Puntos en pintura",
    "Fast Break Points": "Contraataque", "Team Turnovers": "Pérdidas de equipo",
    "Technical Fouls": "Faltas técnicas", "Flagrant Fouls": "Faltas flagrantes",
}


def _num_stat(val):
    try:
        return float(str(val).replace("%", "").strip())
    except Exception:  # noqa: BLE001
        return None


def _detalle(j: dict):
    from html import escape as _e
    import favoritos_datos as _fd

    L, V = j["local"], j["visita"]
    a = analisis_vivo(j)
    v_ab = (V.get("abrev") or V["nombre"][:3]).upper()
    l_ab = (L.get("abrev") or L["nombre"][:3]).upper()
    v_logo = _fd.escudo(v_ab)
    l_logo = _fd.escudo(l_ab)

    if j["estado"] == "pre":
        hora, _ = _fd.cuando(j["fecha"])
        hora_lbl = hora.capitalize() if hora else pd.to_datetime(j["fecha"], utc=True).tz_convert(ZONA).strftime("%d/%m %H:%M")
        linea_txt = f"{j['linea_txt'] or 'Sin línea'}" + (f" · Total {j['linea_total']}" if j.get("linea_total") else "")
        st.markdown(
            f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:16px;padding:18px 20px;margin:6px 0 12px;'
            f'box-shadow:0 4px 18px -6px rgba(15,23,42,.07);">'
            f'<div style="display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:14px;">'
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<img src="{_e(v_logo)}" style="width:48px;height:48px;object-fit:contain;">'
            f'<div><div style="font-weight:800;font-size:1.08rem;color:#0F172A;">{_e(V["nombre"])}</div>'
            f'<div style="font-size:.78rem;color:#64748B;">Récord {_e(V["record"] or "-")}</div></div></div>'
            f'<div style="text-align:center;">'
            f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;background:#EEF2FF;color:#4338CA;border:1px solid #C7D2FE;font-size:.72rem;font-weight:700;">{_e(hora_lbl)}</span>'
            f'<div style="font-size:.75rem;color:#64748B;margin-top:5px;">{_e(linea_txt)}</div></div>'
            f'<div style="display:flex;align-items:center;justify-content:flex-end;gap:12px;text-align:right;">'
            f'<div><div style="font-weight:800;font-size:1.08rem;color:#0F172A;">{_e(L["nombre"])}</div>'
            f'<div style="font-size:.78rem;color:#64748B;">Récord {_e(L["record"] or "-")}</div></div>'
            f'<img src="{_e(l_logo)}" style="width:48px;height:48px;object-fit:contain;"></div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        st.caption("El panel en vivo, box score y gráfico de probabilidad se activan al iniciar el partido.")
        try:
            import nba_extra

            nba_extra.mostrar_lesiones_partido(L["nombre"], V["nombre"])
        except Exception:  # noqa: BLE001
            pass
        return

    # ── Tarjeta Hero del partido en vivo / finalizado ────────────────────────
    es_vivo = j["estado"] == "in"
    v_pts = f"{V['puntos']:.0f}"
    l_pts = f"{L['puntos']:.0f}"
    p_loc = round((a.get("prob_local") or 0.5) * 100)
    p_vis = 100 - p_loc

    badge_html = (
        f'<span style="display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;'
        f'background:#FFF1F2;color:#E11D48;border:1px solid #FECDD3;font-size:.72rem;font-weight:800;">'
        f'<span style="width:6px;height:6px;border-radius:50%;background:#E11D48;"></span>EN VIVO · {_e(j["detalle"])}</span>'
        if es_vivo else
        f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
        f'background:#F1F5F9;color:#475569;border:1px solid #E2E8F0;font-size:.72rem;font-weight:700;">FINAL</span>'
    )

    extra_kpis = ""
    if es_vivo:
        proy = f"{a.get('proy_total', 0):.0f}"
        ritmo = f"{a.get('ritmo48', 0):.0f}"
        dif_l = (f" ({a['proy_total'] - j['linea_total']:+.1f} vs línea)" if j.get("linea_total") else "")
        extra_kpis = (
            f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px;padding-top:12px;border-top:1px solid #F1F5F9;">'
            f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:8px 12px;">'
            f'<div style="font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748B;">Proyección total</div>'
            f'<div style="font-family:var(--pl-font-mono);font-size:1.15rem;font-weight:800;color:#0F172A;">{proy}<span style="font-size:.74rem;font-weight:600;color:#4F46E5;">{_e(dif_l)}</span></div></div>'
            f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:8px 12px;">'
            f'<div style="font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748B;">Ritmo (pts/48\')</div>'
            f'<div style="font-family:var(--pl-font-mono);font-size:1.15rem;font-weight:800;color:#0F172A;">{ritmo}</div></div>'
            f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:8px 12px;">'
            f'<div style="font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748B;">Prob. modelo</div>'
            f'<div style="font-size:.86rem;font-weight:800;color:#0F172A;margin:2px 0 4px;">{_e(v_ab)} {p_vis}% · {p_loc}% {_e(l_ab)}</div>'
            f'<div style="display:flex;height:5px;border-radius:999px;overflow:hidden;background:#E2E8F0;">'
            f'<div style="width:{p_vis}%;background:#94A3B8;"></div><div style="flex:1;background:#4F46E5;"></div></div></div>'
            f'</div>'
        )
    else:
        extra_kpis = (
            f'<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:14px;padding-top:12px;border-top:1px solid #F1F5F9;">'
            f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:8px 12px;">'
            f'<div style="font-size:.7rem;font-weight:700;text-transform:uppercase;color:#64748B;">Total del partido</div>'
            f'<div style="font-family:var(--pl-font-mono);font-size:1.15rem;font-weight:800;color:#0F172A;">{a["total"]:.0f} pts</div></div>'
            f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:8px 12px;">'
            f'<div style="font-size:.7rem;font-weight:700;text-transform:uppercase;color:#64748B;">Diferencia local</div>'
            f'<div style="font-family:var(--pl-font-mono);font-size:1.15rem;font-weight:800;color:#0F172A;">{a["dif"]:+.0f}</div></div>'
            f'</div>'
        )

    st.markdown(
        f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:16px;padding:18px 22px;margin:4px 0 12px;'
        f'box-shadow:0 6px 22px -8px rgba(15,23,42,.08);">'
        f'<div style="display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:16px;">'
        f'<div style="display:flex;align-items:center;gap:12px;min-width:0;">'
        f'<img src="{_e(v_logo)}" style="width:52px;height:52px;object-fit:contain;flex-shrink:0;">'
        f'<div style="min-width:0;"><div style="font-weight:800;font-size:1.1rem;color:#0F172A;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_e(V["nombre"])}</div>'
        f'<div style="font-size:.76rem;color:#64748B;">Visita · {_e(V["record"] or "-")}</div></div>'
        f'<div style="margin-left:auto;font-family:var(--pl-font-mono);font-size:2rem;font-weight:800;color:#0F172A;">{v_pts}</div>'
        f'</div>'
        f'<div style="text-align:center;">{badge_html}</div>'
        f'<div style="display:flex;align-items:center;gap:12px;min-width:0;">'
        f'<div style="margin-right:auto;font-family:var(--pl-font-mono);font-size:2rem;font-weight:800;color:#4F46E5;">{l_pts}</div>'
        f'<div style="min-width:0;text-align:right;"><div style="font-weight:800;font-size:1.1rem;color:#0F172A;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_e(L["nombre"])}</div>'
        f'<div style="font-size:.76rem;color:#64748B;">Local · {_e(L["record"] or "-")}</div></div>'
        f'<img src="{_e(l_logo)}" style="width:52px;height:52px;object-fit:contain;flex-shrink:0;">'
        f'</div>'
        f'</div>'
        f'{extra_kpis}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Tabla de cuartos en blanco elegante con escudos ──────────────────────
    n_q = max(len(L["q"]), len(V["q"]))
    if n_q:
        nom_cols = [f"Q{i + 1}" if i < 4 else f"OT{i - 3}" for i in range(n_q)]
        vq = [str(int(x)) for x in V["q"]] + ["–"] * (n_q - len(V["q"]))
        lq = [str(int(x)) for x in L["q"]] + ["–"] * (n_q - len(L["q"]))
        ths = "".join(f"<th style='padding:8px 12px;font-weight:700;'>{c}</th>" for c in nom_cols)
        v_tds = "".join(f"<td style='padding:9px 12px;font-family:var(--pl-font-mono);color:#334155;'>{x}</td>" for x in vq)
        l_tds = "".join(f"<td style='padding:9px 12px;font-family:var(--pl-font-mono);color:#334155;'>{x}</td>" for x in lq)
        st.markdown(
            f'<div style="overflow-x:auto;margin-bottom:12px;">'
            f'<table style="width:100%;border-collapse:collapse;background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;overflow:hidden;font-size:.84rem;text-align:center;box-shadow:0 2px 10px -4px rgba(15,23,42,.05);">'
            f'<thead><tr style="background:#F8FAFC;color:#64748B;font-size:.73rem;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #E2E8F0;">'
            f'<th style="text-align:left;padding:8px 14px;">Parciales por cuarto</th>{ths}<th style="padding:8px 14px;">Total</th></tr></thead>'
            f'<tbody>'
            f'<tr style="border-bottom:1px solid #F1F5F9;">'
            f'<td style="text-align:left;padding:9px 14px;font-weight:700;color:#0F172A;display:flex;align-items:center;gap:8px;">'
            f'<img src="{_e(v_logo)}" style="width:20px;height:20px;object-fit:contain;">{_e(V["nombre"])}</td>'
            f'{v_tds}<td style="padding:9px 14px;font-family:var(--pl-font-mono);font-weight:800;color:#0F172A;">{v_pts}</td></tr>'
            f'<tr>'
            f'<td style="text-align:left;padding:9px 14px;font-weight:700;color:#0F172A;display:flex;align-items:center;gap:8px;">'
            f'<img src="{_e(l_logo)}" style="width:20px;height:20px;object-fit:contain;">{_e(L["nombre"])}</td>'
            f'{l_tds}<td style="padding:9px 14px;font-family:var(--pl-font-mono);font-weight:800;color:#4F46E5;">{l_pts}</td></tr>'
            f'</tbody></table></div>',
            unsafe_allow_html=True,
        )

    try:
        s = resumen(j["id"])
    except Exception as e:  # noqa: BLE001
        st.warning(f"No se pudo cargar el detalle del partido ({e}).")
        return

    wp = s.get("winprobability") or []
    if wp:
        d = pd.DataFrame({"Jugada": range(len(wp)),
                          "Prob": [num(x.get("homeWinPercentage")) for x in wp]}).dropna()
        d["Prob"] = d["Prob"] * (100 if d["Prob"].max() <= 1 else 1)
        st.markdown(f"**📈 Probabilidad de victoria en vivo · {L['nombre']}**")
        area = alt.Chart(d).mark_area(
            color="#4F46E5", opacity=0.12, interpolate="monotone"
        ).encode(x="Jugada:Q", y=alt.Y("Prob:Q", scale=alt.Scale(domain=[0, 100])))
        linea = alt.Chart(d).mark_line(color="#4F46E5", strokeWidth=2.5, interpolate="monotone").encode(
            x=alt.X("Jugada:Q", title="Jugada"), y=alt.Y("Prob:Q", title="Probabilidad %", scale=alt.Scale(domain=[0, 100])),
            tooltip=[alt.Tooltip("Jugada", title="Jugada"), alt.Tooltip("Prob", title="Prob. %", format=".1f")])
        mitad = alt.Chart(pd.DataFrame({"y": [50]})).mark_rule(color="#94A3B8", strokeDash=[4, 4]).encode(y="y:Q")
        st.altair_chart((area + linea + mitad).properties(height=210), use_container_width=True)

    plays = s.get("plays") or []
    if plays and j["estado"] == "in":
        quien, pts = _racha_anotacion(plays, {L["id"]: L["nombre"], V["id"]: V["nombre"]})
        if quien and pts >= 6:
            st.info(f"🔥 Parcial en curso: **{quien}** suma **{pts}** puntos seguidos.")

    t_box, t_eq, t_jug = st.tabs(["📊 Box score y líderes", "⚖️ Comparativa de equipos", "⚡ Últimas jugadas"])

    with t_box:
        equipos_box = _box_rico(s)
        if not equipos_box:
            st.caption("Sin estadísticas de jugadores todavía.")
        else:
            # Líderes del partido con foto real
            todos_j = []
            for eb in equipos_box:
                for p in eb["jugadores"]:
                    todos_j.append((eb["abrev"], p))
            if todos_j:
                def _top_stat(claves):
                    mejor, mv = None, -1.0
                    for ab, p in todos_j:
                        for ck in claves:
                            val = _num_stat(p["stats"].get(ck))
                            if val is not None and val > mv:
                                mv = val
                                mejor = (ab, p, int(val))
                    return mejor

                top_pts = _top_stat(("PTS", "pts"))
                top_reb = _top_stat(("REB", "reb"))
                top_ast = _top_stat(("AST", "ast"))
                tarjetas_lid = []
                for titulo_l, item_l, uni in (("Máximo anotador", top_pts, "PTS"), ("Líder en rebotes", top_reb, "REB"), ("Líder en asistencias", top_ast, "AST")):
                    if not item_l:
                        continue
                    ab_l, pl_l, val_l = item_l
                    ini = "".join(w[0] for w in pl_l["nom"].split()[:2]).upper()
                    img_h = (
                        f'<img src="{_e(pl_l["foto"])}" style="width:44px;height:44px;border-radius:50%;object-fit:cover;object-position:50% 10%;'
                        f'background:radial-gradient(circle at 50% 25%,#F8FAFC,#E0E7FF);border:1.5px solid #C7D2FE;" '
                        f'onerror="this.style.display=\'none\';">'
                        if pl_l["foto"] else
                        f'<div style="width:44px;height:44px;border-radius:50%;background:#EEF2FF;color:#4338CA;display:grid;place-items:center;font-weight:800;">{_e(ini)}</div>'
                    )
                    tarjetas_lid.append(
                        f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:10px 12px;display:flex;align-items:center;gap:10px;">'
                        f'{img_h}'
                        f'<div style="min-width:0;flex:1;"><div style="font-size:.68rem;font-weight:700;text-transform:uppercase;color:#64748B;">{titulo_l}</div>'
                        f'<div style="font-weight:800;font-size:.88rem;color:#0F172A;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_e(pl_l["nom"])}</div>'
                        f'<div style="font-size:.72rem;color:#64748B;">{_e(ab_l)} · {_e(pl_l["pos"])}</div></div>'
                        f'<div style="text-align:right;"><div style="font-family:var(--pl-font-mono);font-size:1.25rem;font-weight:800;color:#4F46E5;">{val_l}</div>'
                        f'<div style="font-size:.65rem;font-weight:700;color:#64748B;">{uni}</div></div>'
                        f'</div>'
                    )
                if tarjetas_lid:
                    st.markdown(
                        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin-bottom:14px;">'
                        f'{"".join(tarjetas_lid)}</div>',
                        unsafe_allow_html=True,
                    )

            # Filtro interactivo por equipo
            nombres_eq = [eb["nombre"] for eb in equipos_box]
            opciones_f = ["Ambos equipos"] + nombres_eq
            sel_eq = (
                st.pills("Equipo box", opciones_f, default="Ambos equipos", key=f"box_flt_{j['id']}", label_visibility="collapsed")
                if hasattr(st, "pills") else
                st.radio("Equipo box", opciones_f, horizontal=True, key=f"box_flt_{j['id']}", label_visibility="collapsed")
            ) or "Ambos equipos"

            cols_mostrar = ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "STL", "BLK", "TO", "+/-"]
            for eb in equipos_box:
                if sel_eq != "Ambos equipos" and eb["nombre"] != sel_eq:
                    continue
                cols_eq = [c for c in cols_mostrar if c in eb["etiquetas"]]
                if not cols_eq:
                    cols_eq = eb["etiquetas"][:10]
                ths_b = "".join(f"<th style='padding:8px 8px;text-align:center;'>{_e(c)}</th>" for c in cols_eq)
                filas_html = []
                for p in eb["jugadores"]:
                    ini = "".join(w[0] for w in p["nom"].split()[:2]).upper()
                    av = (
                        f'<img src="{_e(p["foto"])}" style="width:32px;height:32px;border-radius:50%;object-fit:cover;object-position:50% 10%;'
                        f'background:radial-gradient(circle at 50% 25%,#F8FAFC,#E0E7FF);border:1.5px solid #C7D2FE;flex-shrink:0;" '
                        f'onerror="this.style.display=\'none\';">'
                        if p["foto"] else
                        f'<div style="width:32px;height:32px;border-radius:50%;background:#EEF2FF;color:#4338CA;display:grid;place-items:center;font-size:.7rem;font-weight:800;flex-shrink:0;">{_e(ini)}</div>'
                    )
                    tit_badge = (
                        '<span style="font-size:.62rem;font-weight:700;padding:1px 6px;border-radius:999px;background:#EEF2FF;color:#4338CA;border:1px solid #C7D2FE;margin-left:5px;">Titular</span>'
                        if p["starter"] else ""
                    )
                    celdas = []
                    for c in cols_eq:
                        val = str(p["stats"].get(c, "–"))
                        if c == "PTS":
                            celdas.append(f"<td style='padding:7px 8px;text-align:center;font-family:var(--pl-font-mono);font-weight:800;color:#4338CA;background:#F5F7FF;'>{_e(val)}</td>")
                        elif c == "+/-":
                            clr = "#059669" if val.startswith("+") and val != "+0" else ("#DC2626" if val.startswith("-") else "#475569")
                            celdas.append(f"<td style='padding:7px 8px;text-align:center;font-family:var(--pl-font-mono);font-weight:700;color:{clr};'>{_e(val)}</td>")
                        else:
                            celdas.append(f"<td style='padding:7px 8px;text-align:center;font-family:var(--pl-font-mono);color:#334155;'>{_e(val)}</td>")
                    filas_html.append(
                        f"<tr style='border-bottom:1px solid #F1F5F9;'>"
                        f"<td style='padding:7px 12px;text-align:left;'>"
                        f"<div style='display:flex;align-items:center;gap:9px;'>{av}"
                        f"<div><div style='font-weight:700;color:#0F172A;white-space:nowrap;'>{_e(p['nom'])}{tit_badge}</div>"
                        f"<div style='font-size:.7rem;color:#64748B;'>{_e(p['pos'])}{' · #' + _e(p['dorsal']) if p['dorsal'] else ''}</div></div></div></td>"
                        f"{''.join(celdas)}</tr>"
                    )
                st.markdown(
                    f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;overflow:hidden;margin-bottom:14px;box-shadow:0 3px 14px -6px rgba(15,23,42,.06);">'
                    f'<div style="display:flex;align-items:center;gap:9px;padding:10px 14px;background:#F8FAFC;border-bottom:1px solid #E2E8F0;">'
                    f'<img src="{_e(eb["logo"])}" style="width:24px;height:24px;object-fit:contain;">'
                    f'<span style="font-weight:800;font-size:.95rem;color:#0F172A;">{_e(eb["nombre"])}</span></div>'
                    f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:.8rem;">'
                    f'<thead><tr style="background:#FFFFFF;color:#64748B;font-size:.7rem;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #E2E8F0;">'
                    f'<th style="padding:8px 12px;text-align:left;">Jugador</th>{ths_b}</tr></thead>'
                    f'<tbody>{"".join(filas_html)}</tbody></table></div></div>',
                    unsafe_allow_html=True,
                )

    with t_eq:
        te = _tabla_equipos(s)
        if te.empty or len(te.columns) < 2:
            st.caption("Sin estadísticas de equipo todavía.")
        else:
            col_a, col_b = te.columns[0], te.columns[1]
            ab_a = v_ab if V["nombre"] in col_a else l_ab
            ab_b = l_ab if ab_a == v_ab else v_ab
            logo_a, logo_b = _fd.escudo(ab_a), _fd.escudo(ab_b)
            barras_eq = []
            for stat_k, row_s in te.iterrows():
                va, vb = str(row_s[col_a]), str(row_s[col_b])
                lbl_es = _ES_STATS_NBA.get(str(stat_k), str(stat_k))
                na, nb = _num_stat(va), _num_stat(vb)
                if na is not None and nb is not None and (na + nb) > 0:
                    pa = round(100 * na / (na + nb), 1)
                else:
                    pa = 50.0
                barras_eq.append(
                    f'<div style="margin-bottom:11px;">'
                    f'<div style="display:flex;justify-content:space-between;font-size:.82rem;font-weight:700;color:#0F172A;margin-bottom:4px;">'
                    f'<span>{_e(va)}</span><span style="font-weight:600;color:#64748B;">{_e(lbl_es)}</span><span>{_e(vb)}</span></div>'
                    f'<div style="display:flex;height:6px;border-radius:999px;overflow:hidden;background:#F1F5F9;">'
                    f'<div style="width:{pa}%;background:#94A3B8;"></div><div style="flex:1;background:#4F46E5;"></div></div></div>'
                )
            st.markdown(
                f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;padding:14px 18px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid #F1F5F9;">'
                f'<div style="display:flex;align-items:center;gap:8px;font-weight:800;color:#0F172A;"><img src="{_e(logo_a)}" style="width:24px;height:24px;object-fit:contain;">{_e(col_a)}</div>'
                f'<div style="display:flex;align-items:center;gap:8px;font-weight:800;color:#4F46E5;">{_e(col_b)}<img src="{_e(logo_b)}" style="width:24px;height:24px;object-fit:contain;"></div>'
                f'</div>{"".join(barras_eq)}</div>',
                unsafe_allow_html=True,
            )

    with t_jug:
        if not plays:
            st.caption("Sin jugadas registradas todavía.")
        else:
            feed = []
            for p in plays[-12:][::-1]:
                per = (p.get("period") or {}).get("displayValue", "")
                reloj = (p.get("clock") or {}).get("displayValue", "")
                tid_p = str((p.get("team") or {}).get("id") or "")
                lg_p = v_logo if tid_p == str(V["id"]) else (l_logo if tid_p == str(L["id"]) else "")
                img_p = f'<img src="{_e(lg_p)}" style="width:20px;height:20px;object-fit:contain;flex-shrink:0;">' if lg_p else ""
                feed.append(
                    f'<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;border-bottom:1px solid #F1F5F9;font-size:.82rem;">'
                    f'<span style="font-family:var(--pl-font-mono);font-size:.72rem;font-weight:700;color:#4338CA;background:#EEF2FF;padding:2px 7px;border-radius:6px;white-space:nowrap;">{_e(per)} {_e(reloj)}</span>'
                    f'{img_p}'
                    f'<span style="flex:1;color:#1E293B;">{_e(p.get("text", ""))}</span>'
                    f'<span style="font-family:var(--pl-font-mono);font-weight:700;color:#0F172A;white-space:nowrap;">{_e(str(p.get("awayScore", "")))}–{_e(str(p.get("homeScore", "")))}</span>'
                    f'</div>'
                )
            st.markdown(
                f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;overflow:hidden;">{"".join(feed)}</div>',
                unsafe_allow_html=True,
            )


def _avisar_marcadores(juegos):
    """Marca (invisible) el marcador de cada partido en vivo; movimiento.py detecta el cambio y celebra con sonido y confeti."""
    from html import escape
    marcas = []
    for j in juegos:
        if j["estado"] != "in":
            continue
        nombre = escape(f"{j['visita']['nombre']} @ {j['local']['nombre']}", quote=True)
        marca = escape(f"{int(j['visita']['puntos'])} - {int(j['local']['puntos'])}")
        marcas.append(f'<span class="pl-hook" data-pl-score data-pl-id="nba:{escape(j["id"], quote=True)}" data-pl-nombre="{nombre}">{marca}</span>')
    if marcas:
        st.markdown("".join(marcas), unsafe_allow_html=True)


def live_panel():
    hoy = pd.Timestamp.now(tz="America/New_York").date()
    try:
        juegos = scoreboard(hoy.strftime("%Y%m%d"))
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo leer el marcador de ESPN: {e}")
        return
    if not juegos:
        st.info("No hay partidos de la NBA programados para hoy.")
        return
    filas = []
    for j in juegos:
        a = analisis_vivo(j)
        filas.append({"Estado": {"in": "🔴 En vivo", "post": "Final", "pre": "Por jugar"}.get(j["estado"], j["estado"]),
                      "Detalle": j["detalle"], "Visita": j["visita"]["nombre"], "Pts V": j["visita"]["puntos"],
                      "Local": j["local"]["nombre"], "Pts L": j["local"]["puntos"],
                      "Línea": j["linea_txt"] or "", "Total línea": j["linea_total"],
                      "Proy. total": a.get("proy_total") if j["estado"] == "in" else None,
                      "Gana local %": round(a["prob_local"] * 100) if j["estado"] == "in" else None})
    vivo = sum(j["estado"] == "in" for j in juegos)
    fin = sum(j["estado"] == "post" for j in juegos)
    por_jugar = len(juegos) - vivo - fin
    hora_act = pd.Timestamp.now(tz=ZONA).strftime("%H:%M:%S")
    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;'
        f'background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:8px 14px;margin:4px 0 10px;">'
        f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:.8rem;font-weight:700;">'
        f'<span style="background:#FFF1F2;color:#E11D48;border:1px solid #FECDD3;padding:2px 9px;border-radius:999px;">🔴 {vivo} en vivo</span>'
        f'<span style="background:#EEF2FF;color:#4338CA;border:1px solid #C7D2FE;padding:2px 9px;border-radius:999px;">⏳ {por_jugar} por jugar</span>'
        f'<span style="background:#F1F5F9;color:#475569;border:1px solid #E2E8F0;padding:2px 9px;border-radius:999px;">✅ {fin} finalizados</span>'
        f'</div>'
        f'<span style="font-size:.76rem;color:#64748B;font-family:var(--pl-font-mono);">Actualizado {hora_act}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Tarjetas visuales con escudos de los equipos (dashboard más atractivo)
    from html import escape as _esc
    import favoritos_datos as _fd
    for i in range(0, len(juegos), 3):
        fila_j = juegos[i:i + 3]
        cols_j = st.columns(len(fila_j) if len(fila_j) < 3 else 3, gap="small")
        for col, j in zip(cols_j, fila_j):
            st_cls = j["estado"] if j["estado"] in ("in", "pre", "post") else "pre"
            v_ab = (j["visita"].get("abrev") or "").upper()
            l_ab = (j["local"].get("abrev") or "").upper()
            v_logo = _fd.escudo(v_ab)
            l_logo = _fd.escudo(l_ab)
            v_sc = f"{j['visita']['puntos']:.0f}" if st_cls in ("in", "post") else "-"
            l_sc = f"{j['local']['puntos']:.0f}" if st_cls in ("in", "post") else "-"
            sc_cls = "sl-mscore-big" if st_cls in ("in", "post") else "sl-mscore-big muted"
            if st_cls == "in":
                est_lbl = f"EN VIVO · {j['detalle']}"
            elif st_cls == "post":
                est_lbl = "FINALIZADO"
            else:
                hora_loc, _ = _fd.cuando(j.get("fecha"))
                est_lbl = hora_loc.capitalize() if hora_loc else j["detalle"]
            linea_info = j.get("linea_txt") or "Sin línea"
            if j.get("linea_total"):
                linea_info += f" · Total {j['linea_total']}"
            col.markdown(
                f'<div class="sl-mcard is-{st_cls}">'
                f'<div>'
                f'<div class="sl-mtop"><span>NBA</span><span class="sl-mstate {st_cls}">{_esc(est_lbl)}</span></div>'
                f'<div class="sl-mrow"><div class="sl-mteam"><img class="sl-mlogo" src="{_esc(v_logo)}" alt=""><span class="sl-mname">{_esc(j["visita"]["nombre"])}</span></div><span class="{sc_cls}">{_esc(v_sc)}</span></div>'
                f'<div class="sl-mrow"><div class="sl-mteam"><img class="sl-mlogo" src="{_esc(l_logo)}" alt=""><span class="sl-mname">{_esc(j["local"]["nombre"])}</span></div><span class="{sc_cls}">{_esc(l_sc)}</span></div>'
                f'</div>'
                f'<div class="sl-pre-info"><span>{_esc(linea_info)}</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    df_vivo = pd.DataFrame(filas).dropna(axis=1, how="all")
    if "Línea" in df_vivo.columns:
        df_vivo["Línea"] = df_vivo["Línea"].replace("", "Sin línea")
    with st.expander("📋 Ver tabla completa de marcadores y líneas", expanded=False):
        st.dataframe(df_vivo, hide_index=True, use_container_width=True)
    _avisar_marcadores(juegos)   # movimiento.py: fanfarria, confeti y aviso cuando cambia un marcador

    # Selector visual de partido para análisis detallado
    st.markdown(
        '<div style="margin:14px 0 6px;"><span style="font-size:.72rem;font-weight:700;text-transform:uppercase;'
        'letter-spacing:.08em;color:#64748B;">📋 Seleccionar partido para análisis detallado</span></div>',
        unsafe_allow_html=True,
    )
    idx = st.selectbox(
        "Partido",
        range(len(juegos)),
        key="nba_live_sel",
        index=next((i for i, j in enumerate(juegos) if j["estado"] == "in"), 0),
        format_func=lambda i: (
            f"🔴 {juegos[i]['visita']['nombre']} @ {juegos[i]['local']['nombre']}  ·  EN VIVO {filas[i].get('Detalle', '')}"
            if juegos[i]["estado"] == "in"
            else f"{'✅' if juegos[i]['estado'] == 'post' else '⏳'} {juegos[i]['visita']['nombre']} @ {juegos[i]['local']['nombre']}  ·  {filas[i]['Estado']}"
        ),
        label_visibility="collapsed",
    )
    _detalle(juegos[idx])


# ================================================================ H2H
def vista_h2h(g, t, rat):
    nombres = sorted(t["Equipo"].unique())
    c1, c2, c3 = st.columns([2, 2, 1])
    a = c1.selectbox("Equipo A", nombres, index=0, key="h2h_a")
    b = c2.selectbox("Equipo B", nombres, index=min(1, len(nombres) - 1), key="h2h_b")
    linea = c3.number_input("Línea total", value=225.0, step=0.5, key="h2h_linea")
    if a == b:
        st.warning("Elige dos equipos distintos.")
        return
    h = g[((g.Local == a) & (g.Visita == b)) | ((g.Local == b) & (g.Visita == a))].sort_values("Date").copy()
    if h.empty:
        st.info("No hay enfrentamientos en las temporadas cargadas. Amplía el rango en la barra lateral.")
        return
    h["PF_A"] = np.where(h.Local == a, h.home_pts, h.away_pts)
    h["PF_B"] = np.where(h.Local == a, h.away_pts, h.home_pts)
    h["Margen_A"] = h.PF_A - h.PF_B
    h["Gana_A"] = h.Margen_A > 0
    h["Total"] = h.PF_A + h.PF_B
    n = len(h)

    k = st.columns(5)
    k[0].metric(f"Victorias {a.split()[-1]}", int(h.Gana_A.sum()))
    k[1].metric(f"Victorias {b.split()[-1]}", int((~h.Gana_A).sum()))
    k[2].metric(f"Margen medio ({a.split()[-1]})", f"{h.Margen_A.mean():+.1f}")
    k[3].metric("Total medio", f"{h.Total.mean():.1f}", delta=f"{(h.Total > linea).mean():.0%} over {linea:g}")
    rr = racha_resultado(h.Gana_A)
    k[4].metric("Racha H2H actual", f"{a.split()[-1]} {rr}" if rr.startswith("G") else f"{b.split()[-1]} G{rr[1:]}")

    h["Partido"] = range(1, n + 1)
    h["Ganador"] = np.where(h.Gana_A, a, b)
    h["Fecha"] = h.Date.dt.strftime("%d/%m/%Y")
    h["Marcador"] = h.apply(lambda r: f"{r.home_pts:.0f}-{r.away_pts:.0f}", axis=1)
    st.markdown(f"**Total de puntos en cada partido contra la línea de {linea:g}**")
    st.caption("Verde = over, rojo = under. Las medias móviles de 5 y 10 muestran si los duelos se están "
               "poniendo más anotadores o más cerrados.")
    graficos.mostrar_partidos(h, "Total", linea=linea, jugador=f"{a.split()[-1]} vs {b.split()[-1]}",
                              etiqueta="Total de puntos", clave="h2h_total", columna_fecha="Fecha",
                              columna_rival="Marcador", mas_reciente_primero=False)

    _h2h_lineas(h, a, b, linea)

    cA, cB = st.columns(2)
    with cA:
        st.markdown("**Local vs visita**")
        ra_ = h[h.Local == a]
        rb_ = h[h.Local == b]
        df = pd.DataFrame({"Contexto": [f"{a} de local", f"{b} de local"],
                           "PJ": [len(ra_), len(rb_)],
                           f"Gana {a.split()[-1]}": [int(ra_.Gana_A.sum()), int(rb_.Gana_A.sum())],
                           f"Gana {b.split()[-1]}": [int((~ra_.Gana_A).sum()), int((~rb_.Gana_A).sum())],
                           "Margen medio A": [ra_.Margen_A.mean(), rb_.Margen_A.mean()]}).round(1)
        st.dataframe(df, hide_index=True, use_container_width=True)
    with cB:
        st.markdown("**Por temporada**")
        ps = h.groupby("Temporada").agg(PJ=("Gana_A", "size"), Gana_A=("Gana_A", "sum"),
                                        Margen=("Margen_A", "mean"), Total=("Total", "mean")).round(1)
        ps["Gana_B"] = ps["PJ"] - ps["Gana_A"]
        st.dataframe(ps.sort_index(ascending=False), use_container_width=True)

    if a in set(g.Local) | set(g.Visita) and b in set(g.Local) | set(g.Visita):
        ida = g.loc[g.Local == a, "home_id"].iloc[0] if (g.Local == a).any() else g.loc[g.Visita == a, "away_id"].iloc[0]
        idb = g.loc[g.Local == b, "home_id"].iloc[0] if (g.Local == b).any() else g.loc[g.Visita == b, "away_id"].iloc[0]
        if ida in rat and idb in rat:
            pa_h, ma_h = prob_elo(rat, ida, idb, True)
            pa_v, ma_v = prob_elo(rat, ida, idb, False)
            st.markdown("**Próximo duelo según Elo**")
            e = st.columns(4)
            e[0].metric(f"Elo {a.split()[-1]}", f"{rat[ida]:.0f}")
            e[1].metric(f"Elo {b.split()[-1]}", f"{rat[idb]:.0f}")
            e[2].metric(f"Gana {a.split()[-1]} de local", f"{pa_h:.0%}", delta=f"{ma_h:+.1f} pts")
            e[3].metric(f"Gana {a.split()[-1]} de visita", f"{pa_v:.0%}", delta=f"{ma_v:+.1f} pts")

    _h2h_estadisticas(h, a, b)

    st.markdown("**Todos los partidos**")
    vista = h[["Fecha", "Temporada", "tipo", "Local", "Marcador", "Visita", "Ganador"]].iloc[::-1]
    st.dataframe(vista.rename(columns={"tipo": "Fase"}), hide_index=True, use_container_width=True)


# ---------------------------------------------------------------- H2H: análisis de la línea
MAX_H2H_LINEA = 25  # tope de enfrentamientos anteriores que se pueden analizar


def _pct_over(serie: pd.Series, linea: float):
    """(overs, unders, % over) de una serie contra una línea; los push no cuentan."""
    s = serie.dropna()
    o, u = int((s > linea).sum()), int((s < linea).sum())
    return o, u, (o / (o + u) * 100 if o + u else np.nan)


def _datos_lineas(hh: pd.DataFrame, cajas: dict, ida: str, idb: str) -> pd.DataFrame:
    """Una fila por enfrentamiento: puntos, total y triples de cada equipo (NaN si falta el box score)."""
    filas = []
    for r in hh.itertuples():
        eq = (cajas.get(str(r.event_id)) or {}).get("equipos") or {}
        ta = (eq.get(ida) or {}).get("tpm")
        tb = (eq.get(idb) or {}).get("tpm")
        ta = np.nan if ta is None else float(ta)
        tb = np.nan if tb is None else float(tb)
        filas.append({"Fecha": r.Date, "Marcador": f"{r.home_pts:.0f}-{r.away_pts:.0f}",
                      "PF_A": r.PF_A, "PF_B": r.PF_B, "Total": r.PF_A + r.PF_B,
                      "3P_A": ta, "3P_B": tb, "3P_T": ta + tb})
    return pd.DataFrame(filas)


def _h2h_lineas(h, a, b, linea):
    """Estadísticas de los últimos N enfrentamientos (hasta 25) y qué tan efectiva fue la línea."""
    import nba_extra as nx

    ca, cb = a.split()[-1], b.split()[-1]
    total = len(h)
    st.markdown("### 🎯 Análisis de la línea en enfrentamientos")
    tope = min(MAX_H2H_LINEA, total)
    n = st.slider("Enfrentamientos anteriores a analizar", 1, tope, min(10, tope), key="h2h_n_linea",
                  help="Hasta 25. Los puntos salen de los resultados; los triples, de los box scores "
                       "(la primera vez se descargan, luego quedan en disco).") if tope > 1 else 1
    if total < MAX_H2H_LINEA:
        st.caption(f"Solo hay {total} enfrentamientos en las temporadas cargadas. "
                   "Sube «Temporadas a cargar» en la barra lateral para llegar a 25.")
    hh = h.tail(n)

    # Box scores (para los triples). Si fallan, el análisis de puntos sigue funcionando.
    ids = [str(i) for i in hh.event_id]
    clave = ("nba_cajas", tuple(ids))
    if clave not in st.session_state:
        with st.spinner(f"Descargando {len(ids)} box scores..."):
            st.session_state[clave] = nx.cargar_cajas(ids)
    cajas, fallos = st.session_state[clave]
    if fallos:
        st.warning(f"{fallos} de {len(ids)} box scores no se pudieron leer: los triples usan solo los que sí cargaron.")
    primero = hh.iloc[0]
    ida = str(primero.home_id if primero.Local == a else primero.away_id)
    idb = str(primero.home_id if primero.Local == b else primero.away_id)
    d = _datos_lineas(hh, cajas, ida, idb).reset_index(drop=True)

    # ---- Puntos
    mas_a, mas_b = int((d.PF_A > d.PF_B).sum()), int((d.PF_B > d.PF_A).sum())
    o, u, po = _pct_over(d.Total, linea)
    st.markdown(f"**Puntos** · últimos {len(d)} enfrentamientos")
    k = st.columns(6)
    k[0].metric(f"{ca} anotó más", f"{mas_a} de {len(d)}", delta=f"{mas_a / len(d):.0%}", delta_color="off")
    k[1].metric(f"{cb} anotó más", f"{mas_b} de {len(d)}", delta=f"{mas_b / len(d):.0%}", delta_color="off")
    k[2].metric(f"Pts promedio {ca}", f"{d.PF_A.mean():.1f}")
    k[3].metric(f"Pts promedio {cb}", f"{d.PF_B.mean():.1f}")
    k[4].metric("Total promedio", f"{d.Total.mean():.1f}", delta=f"{d.Total.mean() - linea:+.1f} vs línea")
    k[5].metric(f"Over {linea:g}", f"{o}-{u}", delta=f"{po:.0f}% over" if not np.isnan(po) else None, delta_color="off")

    # ---- Triples
    st.markdown("**Triples convertidos**")
    con_3p = d.dropna(subset=["3P_T"])
    if con_3p.empty:
        st.caption("Los box scores no trajeron triples para estos partidos.")
    else:
        k = st.columns(4)
        k[0].metric(f"Triples promedio {ca}", f"{con_3p['3P_A'].mean():.1f}")
        k[1].metric(f"Triples promedio {cb}", f"{con_3p['3P_B'].mean():.1f}")
        k[2].metric("Triples combinados por partido", f"{con_3p['3P_T'].mean():.1f}")
        k[3].metric(f"Más triples {ca} / {cb}",
                    f"{int((con_3p['3P_A'] > con_3p['3P_B']).sum())} / {int((con_3p['3P_B'] > con_3p['3P_A']).sum())}")
        if len(con_3p) < len(d):
            st.caption(f"Triples calculados con {len(con_3p)} de {len(d)} partidos (los demás no tienen box score).")

    # ---- Gráfico por partido
    opciones = {"Total de puntos": ("Total", True), f"Puntos de {ca}": ("PF_A", True),
                f"Puntos de {cb}": ("PF_B", True), "Triples combinados": ("3P_T", False),
                f"Triples de {ca}": ("3P_A", False), f"Triples de {cb}": ("3P_B", False)}
    c1, c2 = st.columns([2, 1])
    nombre = c1.selectbox("Estadística a graficar", list(opciones), key="h2h_lin_stat")
    col, escala_cero = opciones[nombre][0], not opciones[nombre][1]
    dd = d.dropna(subset=[col]).copy()
    if dd.empty:
        st.info("No hay datos de esa estadística en los partidos elegidos.")
        return
    if col == "Total":
        lin = linea
        c2.metric("Línea (la de arriba)", f"{linea:g}")
    else:
        lin = c2.number_input(f"Línea de {nombre.lower()}", value=float(round(dd[col].mean() * 2) / 2), step=0.5,
                              key=f"h2h_lin_{col}_{ca}_{cb}")
    dd["Resultado"] = np.where(dd[col] > lin, "Over", np.where(dd[col] < lin, "Under", "Push"))
    dd["Partido"] = dd.Fecha.dt.strftime("%d/%m/%y")
    dd["Dato"] = dd[col]
    orden = list(dd["Partido"])
    o, u, po = _pct_over(dd[col], lin)

    base = alt.Chart(dd).encode(
        x=alt.X("Partido:N", sort=orden, title=None, axis=alt.Axis(labelAngle=-45)),
        tooltip=["Partido", "Marcador", alt.Tooltip("Dato:Q", title=nombre, format=".0f"), "Resultado"])
    barras = base.mark_bar().encode(
        y=alt.Y("Dato:Q", title=nombre, scale=alt.Scale(zero=escala_cero)),
        color=alt.Color("Resultado:N", legend=alt.Legend(orient="top", title=None),
                        scale=alt.Scale(domain=["Over", "Under", "Push"], range=[COLOR_POS, COLOR_NEG, COLOR_NEUTRO])))
    textos = base.mark_text(dy=-6, fontSize=11).encode(y="Dato:Q", text=alt.Text("Dato:Q", format=".0f"))
    regla = alt.Chart(pd.DataFrame({"y": [lin]})).mark_rule(color="#E69F00", strokeDash=[6, 4], strokeWidth=2).encode(y="y:Q")
    media = alt.Chart(pd.DataFrame({"y": [dd[col].mean()]})).mark_rule(color=COLOR_NEUTRO, strokeDash=[2, 3]).encode(y="y:Q")
    st.markdown(f"**{nombre} en cada enfrentamiento contra la línea de {lin:g}**")
    st.altair_chart((barras + textos + regla + media).properties(height=320), use_container_width=True)
    st.caption(f"Línea naranja = {lin:g}; línea gris punteada = promedio ({dd[col].mean():.1f}). "
               f"Resultado: {o} over, {u} under"
               + (f" → {po:.0f}% over en {len(dd)} partidos." if not np.isnan(po) else "."))

    # ---- Efectividad de la línea según cuántos partidos mire
    filas = []
    for w in [x for x in (5, 10, 15, 20, 25) if x <= total] + ([total] if total < MAX_H2H_LINEA and total not in (5, 10, 15, 20) else []):
        s = h.tail(w)["Total"]
        o_, u_, p_ = _pct_over(s, linea)
        filas.append({"Últimos": w, "Over": o_, "Under": u_, "% over": round(p_, 1) if not np.isnan(p_) else None,
                      "% under": round(100 - p_, 1) if not np.isnan(p_) else None, "Total medio": round(float(s.mean()), 1)})
    if filas:
        st.markdown(f"**Efectividad de la línea {linea:g} según la muestra (total de puntos)**")
        st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
        st.caption("Si el % over se mantiene parecido en muestras chicas y grandes, la señal es más estable. "
                   "Con pocos partidos, los porcentajes saltan mucho.")


# ---------------------------------------------------------------- H2H: estadísticas completas
# (título, clave, mejor): mejor=True -> más es mejor; False -> menos es mejor; None -> solo informativa.
ESTADISTICAS_H2H = [
    ("Puntos", "pts", True),
    ("Rebotes", "reb", True),
    ("Rebotes ofensivos", "oreb", True),
    ("Rebotes defensivos", "dreb", True),
    ("Asistencias", "ast", True),
    ("Robos", "stl", True),
    ("Tapones", "blk", True),
    ("Pérdidas", "tov", False),
    ("% tiros de campo", "FG %", True),
    ("% triples", "3P %", True),
    ("% tiros libres", "TL %", True),
    ("Tiro efectivo (eFG %)", "eFG %", True),
    ("Eficiencia de tiro total (TS %)", "TS %", True),
    ("Tiros de campo convertidos", "fgm", None),
    ("Tiros de campo intentados", "fga", None),
    ("Triples convertidos", "tpm", None),
    ("Triples intentados", "tpa", None),
    ("Tiros libres convertidos", "ftm", None),
    ("Tiros libres intentados", "fta", None),
    ("Puntos de contraataque", "fb", True),
    ("Puntos en la pintura", "paint", True),
    ("Puntos tras pérdidas", "pto", True),
    ("Posesiones", "Posesiones", None),
    ("Ofensiva (pts/100 pos.)", "ORtg", True),
    ("Defensiva (pts/100 pos., menos es mejor)", "DRtg", False),
]


def _pct(numerador, denominador):
    return numerador / denominador * 100 if denominador else np.nan


def _promedios_equipo(df: pd.DataFrame) -> dict:
    """Promedios por partido. Los porcentajes se calculan con el total de tiros, no promediando porcentajes."""
    d = {k: df[k].mean() for k in ("pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov", "fgm", "fga", "tpm",
                                    "tpa", "ftm", "fta", "fb", "paint", "pto", "Posesiones", "ORtg", "DRtg")
         if k in df}
    fgm, fga, tpm, tpa = df.fgm.sum(), df.fga.sum(), df.tpm.sum(), df.tpa.sum()
    ftm, fta = df.ftm.sum(), df.fta.sum()
    d["FG %"] = _pct(fgm, fga)
    d["3P %"] = _pct(tpm, tpa)
    d["TL %"] = _pct(ftm, fta)
    d["eFG %"] = _pct(fgm + 0.5 * tpm, fga)
    d["TS %"] = _pct(df.pts.sum(), 2 * (fga + 0.44 * fta))
    return d


def _h2h_equipos(h, a, b, cajas, ida, idb):
    """Tabla comparativa de todas las estadísticas de equipo + resumen de quién lidera más categorías."""
    import nba_extra as nx

    fa, fb = [], []
    for r in h.itertuples():
        eq = (cajas.get(str(r.event_id)) or {}).get("equipos") or {}
        if ida not in eq or idb not in eq:
            continue
        ea, eb = eq[ida], eq[idb]
        fa.append({**ea, "pts": r.PF_A, **nx.metricas_partido(ea, eb, r.PF_A, r.PF_B)})
        fb.append({**eb, "pts": r.PF_B, **nx.metricas_partido(eb, ea, r.PF_B, r.PF_A)})
    if not fa:
        st.info("No se pudo leer el box score de estos partidos.")
        return len(fa)
    pa, pb = _promedios_equipo(pd.DataFrame(fa)), _promedios_equipo(pd.DataFrame(fb))
    ca, cb = a.split()[-1], b.split()[-1]

    filas, gana_a, gana_b, empates = [], 0, 0, 0
    for titulo, clave, mejor in ESTADISTICAS_H2H:
        va, vb = pa.get(clave, np.nan), pb.get(clave, np.nan)
        if pd.isna(va) and pd.isna(vb):
            continue
        va_r, vb_r = round(va, 1), round(vb, 1)
        sa, sb = f"{va_r:.1f}", f"{vb_r:.1f}"
        if mejor is None:
            lider = "—"
        elif va_r == vb_r:
            lider, empates = "Empate", empates + 1
        elif (va_r > vb_r) == mejor:
            lider, gana_a, sa = ca, gana_a + 1, "✅ " + sa
        else:
            lider, gana_b, sb = cb, gana_b + 1, "✅ " + sb
        filas.append({"Estadística": titulo, a: sa, b: sb, "Líder": lider})

    k = st.columns(3)
    k[0].metric(f"Categorías que lidera {ca}", gana_a)
    k[1].metric(f"Categorías que lidera {cb}", gana_b)
    k[2].metric("Empates", empates)
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    st.caption(f"Promedios por partido de {len(fa)} enfrentamientos con box score. ✅ marca al que lidera. "
               "Los porcentajes usan el total de tiros. Las filas sin ✅ (tiros intentados, posesiones) son informativas.")

    # Gráfico: estadísticas principales (cada una con su propia escala).
    principales = [("pts", "PTS"), ("reb", "REB"), ("ast", "AST"), ("stl", "ROB"), ("blk", "TAP"), ("tov", "PER")]
    medias = {n: {t: p.get(c) for c, t in principales} for n, p in ((a, pa), (b, pb))}
    st.markdown("**Estadísticas principales**")
    graficos.mostrar_comparacion(medias, titulo="Promedios por partido en estos enfrentamientos",
                                 clave="h2h_eq_cmp", colores=[COLOR_A, COLOR_B])

    # Gráfico: todas las eficiencias de tiro en la misma escala (0-100 %).
    pct = [("FG %", "% campo"), ("3P %", "% triples"), ("TL %", "% libres"), ("eFG %", "eFG %"), ("TS %", "TS %")]
    d = pd.DataFrame([{"Estadística": t, "Equipo": nombre, "Valor": p.get(c)}
                      for c, t in pct for nombre, p in ((a, pa), (b, pb))]).dropna()
    if not d.empty:
        st.markdown("**Eficiencia de tiro**")
        ch = alt.Chart(d).mark_bar().encode(
            x=alt.X("Equipo:N", axis=None, sort=[a, b]),
            y=alt.Y("Valor:Q", title="%"),
            color=alt.Color("Equipo:N", scale=alt.Scale(domain=[a, b], range=[COLOR_A, COLOR_B]),
                            legend=alt.Legend(orient="top")),
            column=alt.Column("Estadística:N", title=None, sort=[t for _, t in pct]),
            tooltip=["Equipo", "Estadística", alt.Tooltip("Valor:Q", format=".1f")])
        st.altair_chart(ch.properties(width=95, height=200))
    return len(fa)


def _h2h_jugadores(h, a, b, cajas, ida, idb, n_ok):
    """Líderes individuales del H2H (quién anota más, rebotea más, etc.) y tabla completa de jugadores."""
    filas = []
    for r in h.itertuples():
        c = cajas.get(str(r.event_id)) or {}
        for j in c.get("jugadores", []):
            if j["team_id"] in (ida, idb):
                filas.append({**j, "Equipo": a if j["team_id"] == ida else b})
    if not filas:
        st.info("Los box scores no traen estadísticas de jugadores.")
        return
    ju = pd.DataFrame(filas)
    g = ju.groupby(["Equipo", "Jugador"]).agg(
        PJ=("PTS", "size"), MIN=("MIN", "mean"), PTS=("PTS", "mean"), REB=("REB", "mean"), OREB=("OREB", "mean"),
        DREB=("DREB", "mean"), AST=("AST", "mean"), STL=("STL", "mean"), BLK=("BLK", "mean"), TO=("TO", "mean"),
        T3=("3PM", "mean"), PM=("+/-", "mean"), PTS_T=("PTS", "sum"), FGM=("FGM", "sum"), FGA=("FGA", "sum"),
        M3=("3PM", "sum"), A3=("3PA", "sum"), FTM=("FTM", "sum"), FTA=("FTA", "sum")).reset_index()
    cero = lambda s: s.replace(0, np.nan)  # noqa: E731
    g["FG %"] = g.FGM / cero(g.FGA) * 100
    g["3P %"] = g.M3 / cero(g.A3) * 100
    g["TL %"] = g.FTM / cero(g.FTA) * 100
    g["eFG %"] = (g.FGM + 0.5 * g.M3) / cero(g.FGA) * 100
    g["TS %"] = g.PTS_T / cero(2 * (g.FGA + 0.44 * g.FTA)) * 100
    g = g.rename(columns={"T3": "3PM", "PM": "+/-"})

    # Para no premiar a quien jugó un solo partido, se pide un mínimo de partidos (y de tiros en los porcentajes).
    min_pj = max(1, round(n_ok * 0.4))
    elegibles = g[g.PJ >= min_pj]
    if elegibles.empty:
        elegibles = g
    cats = [("Más puntos", "PTS", None, 0), ("Más rebotes", "REB", None, 0),
            ("Más rebotes ofensivos", "OREB", None, 0), ("Más rebotes defensivos", "DREB", None, 0),
            ("Más asistencias", "AST", None, 0), ("Más robos", "STL", None, 0), ("Más tapones", "BLK", None, 0),
            ("Más triples convertidos", "3PM", None, 0), ("Más pérdidas", "TO", None, 0),
            ("Más minutos", "MIN", None, 0), ("Mejor +/-", "+/-", None, 0),
            ("Mejor % de campo", "FG %", "FGA", 10), ("Mejor % de triples", "3P %", "A3", 5),
            ("Mejor % de tiros libres", "TL %", "FTA", 5), ("Mejor eficiencia total (TS %)", "TS %", "FGA", 10)]
    lid = []
    for titulo, col, fcol, fmin in cats:
        base = elegibles if fcol is None else elegibles[elegibles[fcol] >= fmin]
        base = base.dropna(subset=[col])
        if base.empty:
            continue
        r = base.loc[base[col].idxmax()]
        lid.append({"Categoría": titulo, "Jugador": r.Jugador, "Equipo": r.Equipo, "Valor": round(float(r[col]), 1)})
    st.markdown("**Líderes individuales**")
    st.dataframe(pd.DataFrame(lid), hide_index=True, use_container_width=True)
    st.caption(f"Promedios por partido en estos enfrentamientos. Se exige haber jugado al menos {min_pj} partido(s); "
               "los porcentajes piden además un mínimo de tiros (10 de campo, 5 de triples o libres).")

    with st.expander("Ver todos los jugadores"):
        cols = ["Equipo", "Jugador", "PJ", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TO", "3PM",
                "FG %", "3P %", "TL %", "eFG %", "TS %", "+/-"]
        st.dataframe(g.sort_values("PTS", ascending=False)[cols].round(1), hide_index=True, use_container_width=True)


def _h2h_estadisticas(h, a, b):
    """Sección 'Estadísticas cara a cara' del H2H: descarga los box scores y compara equipos y jugadores."""
    import nba_extra as nx

    st.markdown("### 📊 Estadísticas cara a cara")
    total = len(h)
    n = st.slider("Últimos enfrentamientos a analizar", 1, total, min(total, 10), key="h2h_n_stats",
                  help="La primera vez descarga un box score por partido; después queda guardado en disco.") \
        if total > 1 else 1
    hh = h.tail(n)
    ids = [str(i) for i in hh.event_id]
    clave = ("nba_cajas", tuple(ids))
    if clave not in st.session_state:
        with st.spinner(f"Descargando {len(ids)} box scores..."):
            st.session_state[clave] = nx.cargar_cajas(ids)
    cajas, fallos = st.session_state[clave]
    if fallos:
        st.warning(f"{fallos} de {len(ids)} box scores no se pudieron leer; se usan los {len(cajas)} restantes.")
    if not cajas:
        st.error("No se pudo leer ningún box score. Revisa tu conexión o la página de Diagnóstico.")
        return

    primero = hh.iloc[0]
    ida = str(primero.home_id if primero.Local == a else primero.away_id)
    idb = str(primero.home_id if primero.Local == b else primero.away_id)

    tab_eq, tab_ju = st.tabs(["Equipos", "Jugadores"])
    with tab_eq:
        n_ok = _h2h_equipos(hh, a, b, cajas, ida, idb)
    with tab_ju:
        _h2h_jugadores(hh, a, b, cajas, ida, idb, n_ok or len(cajas))


# ================================================================ RACHAS
def vista_rachas(t):
    c1, c2, c3 = st.columns(3)
    tipo = c1.selectbox("Tipo de racha", [
        "Victorias consecutivas", "Derrotas consecutivas", "Victorias de local seguidas",
        "Victorias de visita seguidas", "Victorias por margen grande", "Anotando muchos puntos",
        "Limitando al rival", "Over del total"])
    min_largo = c2.slider("Largo mínimo de la racha", 3, 40, 15)
    cruzar = c3.checkbox("Contar rachas que cruzan temporadas", True)

    d = t.copy()
    param = None
    if tipo == "Victorias por margen grande":
        param = st.slider("Margen mínimo de victoria (puntos)", 5, 30, 15)
        d["f"] = d["Margen"] >= param
    elif tipo == "Anotando muchos puntos":
        param = st.slider("Puntos anotados mínimos", 90, 140, 110)
        d["f"] = d["PF"] >= param
    elif tipo == "Limitando al rival":
        param = st.slider("El rival anota como máximo", 80, 120, 100)
        d["f"] = d["PC"] <= param
    elif tipo == "Over del total":
        param = st.slider("Línea del total", 200.0, 250.0, 225.0, 0.5)
        d["f"] = d["Total"] > param
    elif tipo == "Victorias de local seguidas":
        d = d[d.Condicion == "Local"].copy()
        d["f"] = d["Gana"]
    elif tipo == "Victorias de visita seguidas":
        d = d[d.Condicion == "Visita"].copy()
        d["f"] = d["Gana"]
    elif tipo == "Derrotas consecutivas":
        d["f"] = d["Pierde"]
    else:
        d["f"] = d["Gana"]

    part = None if cruzar else ["Temporada"]
    st.markdown(f"**Rachas históricas de {min_largo} o más** · {tipo.lower()}"
                + (f" ({param:g})" if param is not None else ""))
    r = mostrar_rachas(st, d, "Equipo", "Date", "f", min_largo, part, "rachas")
    if not r.empty:
        top = r.head(15).copy()
        top["Etiqueta"] = top["Equipo"] + " · " + pd.to_datetime(top["Inicio"]).dt.strftime("%m/%Y")
        ch = alt.Chart(top).mark_bar(color=COLOR_A).encode(
            x=alt.X("Largo:Q"), y=alt.Y("Etiqueta:N", sort="-x", title=None),
            tooltip=["Equipo", "Largo", "Inicio", "Fin"])
        st.altair_chart(ch.properties(height=max(120, 22 * len(top))), use_container_width=True)

    st.markdown("**Rachas activas ahora**")
    act = racha_actual(d, "Equipo", "Date", "f")
    act = act[act["Racha actual"] > 0].head(15)
    st.dataframe(act, hide_index=True, use_container_width=True)


# ================================================================ EQUIPO
def vista_equipo(t, eq=None):
    if eq is None:
        eq = st.selectbox("Equipo", sorted(t["Equipo"].unique()), key="nba_eq")
    te = t[t.Equipo == eq].sort_values("Date").reset_index(drop=True)
    opciones = ["Todas"] + sorted(te["Temporada"].unique(), reverse=True)
    sel = st.selectbox("Temporada", opciones, key="nba_eq_temp")
    if sel != "Todas":
        te = te[te["Temporada"] == sel].reset_index(drop=True)
    if te.empty:
        st.info("Sin partidos.")
        return
    g_, p_ = int(te.Gana.sum()), int((~te.Gana).sum())
    k = st.columns(6)
    k[0].metric("Récord", f"{g_}-{p_}", delta=f"{g_ / len(te):.0%}")
    k[1].metric("Puntos a favor", f"{te.PF.mean():.1f}")
    k[2].metric("Puntos en contra", f"{te.PC.mean():.1f}")
    k[3].metric("Margen medio", f"{te.Margen.mean():+.1f}")
    k[4].metric("Racha actual", racha_resultado(te.Gana))
    k[5].metric("Últimos 10", f"{int(te.tail(10).Gana.sum())}-{10 - int(te.tail(10).Gana.sum())}")

    l1, l2 = st.columns(2)
    with l1:
        st.markdown("**Margen (media móvil de 10 partidos)**")
        d = te.assign(Movil=te.Margen.rolling(10, min_periods=3).mean())
        ln = alt.Chart(d).mark_line(color=COLOR_A, strokeWidth=2).encode(
            x=alt.X("Date:T", title=None), y=alt.Y("Movil:Q", title="Margen"),
            tooltip=["Date:T", "Rival", alt.Tooltip("Movil", format=".1f")])
        z = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=COLOR_NEUTRO, strokeDash=[4, 4]).encode(y="y:Q")
        st.altair_chart(ln + z, use_container_width=True)
    with l2:
        st.markdown("**Distribución de márgenes**")
        hs = alt.Chart(te).mark_bar(color=COLOR_A).encode(
            x=alt.X("Margen:Q", bin=alt.Bin(step=5), title="Margen (pts)"), y=alt.Y("count()", title="Partidos"))
        st.altair_chart(hs, use_container_width=True)

    l3, l4 = st.columns(2)
    with l3:
        st.markdown("**Efecto del descanso**")
        dd = te.dropna(subset=["Descanso"]).copy()
        dd["Cat"] = pd.cut(dd["Descanso"], [-1, 0, 1, 2, 99], labels=["0 (back-to-back)", "1", "2", "3 o más"])
        rd = dd.groupby("Cat", observed=True).agg(PJ=("Gana", "size"), Pct=("Gana", "mean"), Margen=("Margen", "mean")).reset_index()
        rd["Pct"] = rd["Pct"] * 100
        bar = alt.Chart(rd).mark_bar(color=COLOR_A).encode(
            x=alt.X("Cat:N", title="Días de descanso", sort=None), y=alt.Y("Pct:Q", title="% victorias"),
            tooltip=["Cat", "PJ", alt.Tooltip("Pct", format=".0f"), alt.Tooltip("Margen", format=".1f")])
        st.altair_chart(bar, use_container_width=True)
    with l4:
        st.markdown("**Contexto**")
        prev = te.Gana.shift()
        filas = {
            "Tras victoria": te.Gana[prev == True].mean(),  # noqa: E712
            "Tras derrota": te.Gana[prev == False].mean(),  # noqa: E712
            "De local": te.Gana[te.Condicion == "Local"].mean(),
            "De visita": te.Gana[te.Condicion == "Visita"].mean(),
            "Partidos ≤5 pts": te.Gana[te.Margen.abs() <= 5].mean(),
            "Partidos ≥15 pts de margen": (te.Margen.abs() >= 15).mean(),
        }
        df = pd.DataFrame({"Situación": filas.keys(), "% victorias": [round(v * 100, 1) if pd.notna(v) else None for v in filas.values()]})
        df.loc[df.Situación == "Partidos ≥15 pts de margen", "Situación"] = "% de partidos con margen ≥15"
        st.dataframe(df, hide_index=True, use_container_width=True)

    st.markdown("**Por temporada**")
    ps = te.groupby("Temporada").agg(PJ=("Gana", "size"), G=("Gana", "sum"), PF=("PF", "mean"),
                                    PC=("PC", "mean"), Margen=("Margen", "mean")).round(1)
    ps["P"] = ps["PJ"] - ps["G"]
    ps["%"] = (ps["G"] / ps["PJ"] * 100).round(1)
    st.dataframe(ps.sort_index(ascending=False), use_container_width=True)

    st.markdown("**Últimos 15 partidos**")
    u = te.tail(15).iloc[::-1].copy()
    u["Fecha"] = u.Date.dt.strftime("%d/%m/%Y")
    u["Marcador"] = u.apply(lambda r: f"{r.PF:.0f}-{r.PC:.0f}", axis=1)
    st.dataframe(u[["Fecha", "Condicion", "Rival", "Marcador", "Resultado", "Margen", "Descanso"]],
                 hide_index=True, use_container_width=True)


# ================================================================ RANKING
def vista_ranking(g, t, rat, hist):
    temps = sorted(t["season"].unique(), reverse=True)
    s = st.selectbox("Temporada", temps, format_func=etiqueta, key="nba_rank_temp")
    ts = t[t.season == s]
    mapa_id = ts.drop_duplicates("Equipo").set_index("Equipo")["EquipoId"]
    srs = calcular_srs(ts)
    tab = ts.groupby("Equipo").agg(PJ=("Gana", "size"), G=("Gana", "sum"), PF=("PF", "mean"),
                                  PC=("PC", "mean"), Margen=("Margen", "mean"))
    tab["P"] = tab["PJ"] - tab["G"]
    tab["%G"] = (tab["G"] / tab["PJ"] * 100).round(1)
    tab["SRS"] = srs
    tab["Elo"] = [rat.get(mapa_id[e]) for e in tab.index]
    tab["L10"] = [f"{int(ts[ts.Equipo == e].tail(10).Gana.sum())}-{10 - int(ts[ts.Equipo == e].tail(10).Gana.sum())}" for e in tab.index]
    tab["Racha"] = [racha_resultado(ts[ts.Equipo == e].sort_values("Date").Gana) for e in tab.index]
    tab = tab.sort_values("SRS", ascending=False).round(1).reset_index()
    tab.insert(0, "#", range(1, len(tab) + 1))
    st.markdown("**Ranking de poder** (ordenado por SRS: margen ajustado por rivales)")
    st.dataframe(tab[["#", "Equipo", "PJ", "G", "P", "%G", "PF", "PC", "Margen", "SRS", "Elo", "L10", "Racha"]],
                 hide_index=True, use_container_width=True)

    st.markdown("**Evolución del Elo**")
    elegidos = st.multiselect("Equipos (máx. 5)", sorted(hist["Equipo"].dropna().unique()),
                              default=list(tab["Equipo"].head(3)), max_selections=5)
    if elegidos:
        d = hist[hist.Equipo.isin(elegidos)]
        ln = alt.Chart(d).mark_line(strokeWidth=2).encode(
            x=alt.X("Date:T", title=None), y=alt.Y("Elo:Q", scale=alt.Scale(zero=False)),
            color=alt.Color("Equipo:N", scale=alt.Scale(domain=elegidos, range=PALETA[:len(elegidos)])),
            tooltip=["Equipo", "Date:T", alt.Tooltip("Elo", format=".0f")])
        st.altair_chart(ln.properties(height=320), use_container_width=True)


# ================================================================ carga de la liga
def cargar_datos_liga():
    """Controles de temporadas en el menú lateral + carga de la liga. Devuelve (g, t, rat, hist) o None si falla."""
    hasta = temporada_actual()
    with st.sidebar:
        st.subheader("Datos NBA")
        n = st.slider("Temporadas a cargar", 1, 20, 3,
                      help="La primera carga baja ~60 consultas por temporada; después queda en disco.")
        playoffs = st.checkbox("Incluir playoffs", True)
    temporadas = list(range(hasta - n + 1, hasta + 1))
    try:
        g, t, rat, hist, fallos = cargar_liga(temporadas, playoffs)
    except Exception as e:  # noqa: BLE001
        st.error(f"Error cargando datos: {e}")
        return None
    for s, msg in fallos:
        st.warning(f"Temporada {etiqueta(s)} no se pudo cargar: {msg}. Recarga la página para reintentar.")
    if g is None:
        st.error("No se pudo cargar ninguna temporada. Revisa tu conexión o la página de Diagnóstico.")
        return None
    st.caption(f"{len(g):,} partidos · {g.Temporada.nunique()} temporadas · último partido: {g.Date.max():%d/%m/%Y}")
    return g, t, rat, hist
