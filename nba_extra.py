"""NBA (datos extra): posiciones, lesiones, métricas avanzadas por equipo y estadísticas por jugador.

Fuente: API pública (no oficial) de ESPN. Los box scores de partidos terminados se guardan en la carpeta
`.cache_box` (un archivo JSON pequeño por partido), así que cada partido se descarga una sola vez.
"""
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import graficos
import nba
from common import COLOR_A, COLOR_B, COLOR_NEG, COLOR_NEUTRO, COLOR_POS, get_json, num

V2 = "https://site.api.espn.com/apis/v2/sports/basketball/nba"
CACHE = Path(__file__).parent / ".cache_box"

# nombre de estadística de ESPN -> título en español (el resto se muestra al final tal cual)
COLUMNAS_POSICIONES = {
    "wins": "G", "losses": "P", "winPercent": "%G", "gamesBehind": "Dif. líder", "streak": "Racha",
    "avgPointsFor": "PF", "avgPointsAgainst": "PC", "differential": "Dif. pts", "playoffSeed": "Cabeza",
    "pointsFor": "Pts a favor (total)", "pointsAgainst": "Pts en contra (total)",
}


# ================================================================ utilidades de lectura
def _clave(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _flt(v):
    """'12' -> 12.0, '34:12' -> 34.2 (minutos), '--' -> None."""
    if v is None:
        return None
    s = str(v).strip()
    if ":" in s:
        try:
            m, seg = s.split(":")
            return int(m) + int(seg) / 60
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _par(v):
    """'41-88' -> (41.0, 88.0)."""
    p = str(v).split("-") if v is not None else []
    if len(p) == 2:
        try:
            return float(p[0]), float(p[1])
        except ValueError:
            pass
    return None, None


def _stats_equipo(lista) -> dict:
    d = {}
    for x in lista or []:
        for k in (x.get("name"), x.get("label"), x.get("abbreviation")):
            if k:
                d.setdefault(_clave(k), x.get("displayValue"))

    def g(*ks):
        for k in ks:
            if _clave(k) in d:
                return d[_clave(k)]
        return None

    fgm, fga = _par(g("fieldGoalsMade-fieldGoalsAttempted", "FG"))
    tpm, tpa = _par(g("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "3PT"))
    ftm, fta = _par(g("freeThrowsMade-freeThrowsAttempted", "FT"))
    return {"fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa, "ftm": ftm, "fta": fta,
            "oreb": _flt(g("offensiveRebounds", "Offensive Rebounds")), "dreb": _flt(g("defensiveRebounds", "Defensive Rebounds")),
            "reb": _flt(g("totalRebounds", "Rebounds")), "ast": _flt(g("assists", "Assists")),
            "stl": _flt(g("steals", "Steals")), "blk": _flt(g("blocks", "Blocks")),
            "tov": _flt(g("totalTurnovers", "turnovers", "Total Turnovers", "Turnovers")),
            "fb": _flt(g("fastBreakPoints", "Fast Break Points")), "paint": _flt(g("pointsInPaint", "Points in Paint")),
            "pto": _flt(g("turnoverPoints", "pointsOffTurnovers", "Points Off Turnovers")),
            "fal": _flt(g("fouls", "personalFouls", "totalFouls", "Fouls"))}


def _jugadores(s: dict) -> list[dict]:
    out = []
    for blk in (s.get("boxscore") or {}).get("players", []):
        tid = str((blk.get("team") or {}).get("id"))
        for bloque in (blk.get("statistics") or [])[:1]:
            etiquetas = bloque.get("labels") or bloque.get("names") or []
            for a in bloque.get("athletes", []):
                vals = a.get("stats") or []
                if a.get("didNotPlay") or not vals:
                    continue
                v = dict(zip(etiquetas, vals))
                ath = a.get("athlete") or {}
                fgm, fga = _par(v.get("FG"))
                tpm, tpa = _par(v.get("3PT"))
                ftm, fta = _par(v.get("FT"))
                out.append({"team_id": tid, "id": str(ath.get("id", "")), "Jugador": ath.get("displayName", "?"),
                            "Titular": bool(a.get("starter")), "MIN": _flt(v.get("MIN")), "PTS": _flt(v.get("PTS")),
                            "REB": _flt(v.get("REB")), "AST": _flt(v.get("AST")), "TO": _flt(v.get("TO")),
                            "STL": _flt(v.get("STL")), "BLK": _flt(v.get("BLK")), "OREB": _flt(v.get("OREB")),
                            "DREB": _flt(v.get("DREB")), "PF": _flt(v.get("PF")), "FGM": fgm, "FGA": fga,
                            "3PM": tpm, "3PA": tpa, "FTM": ftm, "FTA": fta, "+/-": _flt(v.get("+/-"))})
    return out


# Versión del formato guardado en disco. Súbela cuando compactar() guarde datos nuevos: los archivos viejos
# se vuelven a descargar una vez (si ESPN no responde, se sigue usando el viejo).
VERSION_CAJA = 2


def _cuartos(cs: list) -> dict:
    """{id de equipo: [pts 1.er, 2.º, 3.er, 4.º cuarto]} desde el encabezado del partido (el tiempo extra no se incluye).
    Si algún cuarto no se puede leer, el equipo no se incluye (mejor sin dato que un dato corrido)."""
    out = {}
    for c in cs:
        tid = str((c.get("team") or {}).get("id", c.get("id", "")))
        q = [num(x) for x in (c.get("linescores") or [])[:4]]
        if tid and len(q) == 4 and all(v is not None for v in q):
            out[tid] = [int(v) for v in q]
    return out


def compactar(s: dict) -> dict:
    """Reduce la respuesta de `summary` de ESPN a lo que usa la app (unos pocos KB por partido)."""
    equipos = {}
    for e in (s.get("boxscore") or {}).get("teams", []):
        tid = str((e.get("team") or {}).get("id"))
        equipos[tid] = _stats_equipo(e.get("statistics"))
    comp = ((s.get("header") or {}).get("competitions") or [{}])[0]
    cs = comp.get("competitors") or []
    loc = next((c for c in cs if c.get("homeAway") == "home"), {})
    vis = next((c for c in cs if c.get("homeAway") == "away"), {})
    ab_l, ab_v = (loc.get("team") or {}).get("abbreviation", ""), (vis.get("team") or {}).get("abbreviation", "")
    spread, total = None, None
    pc = s.get("pickcenter") or []
    if pc:
        total = num(pc[0].get("overUnder"))
        spread = nba.margen_esperado_local({"details": pc[0].get("details")}, ab_l, ab_v)
    return {"equipos": equipos, "jugadores": _jugadores(s), "cuartos": _cuartos(cs), "v": VERSION_CAJA,
            "home_id": str((loc.get("team") or {}).get("id", loc.get("id", ""))),
            "away_id": str((vis.get("team") or {}).get("id", vis.get("id", ""))),
            "spread_local": spread, "total": total}


def box_compacto(event_id: str) -> dict:
    """Box score compacto de un partido terminado; se guarda en disco la primera vez."""
    ruta = CACHE / f"{event_id}.json"
    viejo = None
    try:
        if ruta.exists():
            guardado = json.loads(ruta.read_text(encoding="utf-8"))
            if guardado.get("v") == VERSION_CAJA:
                return guardado
            viejo = guardado   # formato anterior (sin cuartos): se vuelve a descargar una vez
    except Exception:  # noqa: BLE001
        pass
    try:
        c = compactar(get_json(f"{nba.BASE}/summary", params={"event": event_id}, retries=2))
    except Exception:  # noqa: BLE001
        if viejo:
            return viejo   # ESPN no respondió: se usa lo que había
        raise
    if not c["equipos"] and viejo:
        return viejo
    if c["equipos"]:
        try:
            CACHE.mkdir(exist_ok=True)
            ruta.write_text(json.dumps(c), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return c


def cargar_cajas(ids: list[str], al_avanzar=None):
    """Descarga en paralelo los box scores; devuelve ({id: caja}, cantidad_de_fallos).

    `al_avanzar(hechos, total)` es opcional y se llama desde el hilo principal (los hilos no pueden tocar st.*).
    """
    def uno(i):
        try:
            return i, box_compacto(i)
        except Exception:  # noqa: BLE001
            return i, None

    out, fallos = {}, 0
    with ThreadPoolExecutor(8) as ex:
        futuros = [ex.submit(uno, i) for i in ids]
        for hechos, f in enumerate(as_completed(futuros), 1):
            i, c = f.result()
            if c and c.get("equipos"):
                out[i] = c
            else:
                fallos += 1
            if al_avanzar:
                al_avanzar(hechos, len(ids))
    return out, fallos


# ================================================================ métricas avanzadas
def _f(d: dict, k: str) -> float:
    v = d.get(k)
    return np.nan if v is None else float(v)


def _posesiones(d: dict) -> float:
    return _f(d, "fga") + 0.44 * _f(d, "fta") - _f(d, "oreb") + _f(d, "tov")


def metricas_partido(own: dict, opp: dict, pf: float, pc: float) -> dict:
    vals = [x for x in (_posesiones(own), _posesiones(opp)) if not np.isnan(x)]
    poss = sum(vals) / len(vals) if vals else np.nan
    fga, fta = _f(own, "fga"), _f(own, "fta")
    ofga, ofta = _f(opp, "fga"), _f(opp, "fta")
    return {
        "Posesiones": poss, "ORtg": 100 * pf / poss if poss else np.nan, "DRtg": 100 * pc / poss if poss else np.nan,
        "eFG %": (_f(own, "fgm") + 0.5 * _f(own, "tpm")) / fga * 100 if fga else np.nan,
        "TS %": pf / (2 * (fga + 0.44 * fta)) * 100 if (fga + 0.44 * fta) else np.nan,
        "TOV %": _f(own, "tov") / (fga + 0.44 * fta + _f(own, "tov")) * 100,
        "ORB %": _f(own, "oreb") / (_f(own, "oreb") + _f(opp, "dreb")) * 100,
        "FT rate": fta / fga * 100 if fga else np.nan,
        "3P rate": _f(own, "tpa") / fga * 100 if fga else np.nan,
        "3P %": _f(own, "tpm") / _f(own, "tpa") * 100 if _f(own, "tpa") else np.nan,
        "Rival eFG %": (_f(opp, "fgm") + 0.5 * _f(opp, "tpm")) / ofga * 100 if ofga else np.nan,
        "Rival TOV %": _f(opp, "tov") / (ofga + 0.44 * ofta + _f(opp, "tov")) * 100,
        "Rival ORB %": _f(opp, "oreb") / (_f(opp, "oreb") + _f(own, "dreb")) * 100,
        "Rival FT rate": ofta / ofga * 100 if ofga else np.nan,
        "Contraataque": _f(own, "fb"), "Pts en pintura": _f(own, "paint"), "Pts tras pérdidas": _f(own, "pto"),
        "Rebotes": _f(own, "reb"), "Asistencias": _f(own, "ast"), "Pérdidas": _f(own, "tov"),
        "Robos": _f(own, "stl"), "Tapones": _f(own, "blk")}


def veredicto_linea(margen: float, esperado, pf: float, pc: float, total):
    """ATS (contra el spread) y over/under de un partido; None si no hay línea."""
    ats = ou = None
    if esperado is not None and not np.isnan(esperado):
        d = margen - esperado
        ats = "Cubre" if d > 0 else "No cubre" if d < 0 else "Push"
    if total is not None and not np.isnan(total):
        t = pf + pc
        ou = "Over" if t > total else "Under" if t < total else "Push"
    return ats, ou


def armar_partidos(te: pd.DataFrame, cajas: dict, tid: str):
    """Une los partidos del equipo (de `t`) con sus box scores. Devuelve (partidos_df, jugadores_df)."""
    filas, jug = [], []
    for r in te.itertuples(index=False):
        c = cajas.get(r.event_id)
        if not c or tid not in c["equipos"]:
            continue
        rivales = [k for k in c["equipos"] if k != tid]
        if not rivales:
            continue
        own, opp = c["equipos"][tid], c["equipos"][rivales[0]]
        es_local = c.get("home_id") == tid if c.get("home_id") else r.Condicion == "Local"
        esp = c.get("spread_local")
        esp_eq = None if esp is None else (esp if es_local else -esp)
        ats, ou = veredicto_linea(r.PF - r.PC, esp_eq, r.PF, r.PC, c.get("total"))
        fila = {"Fecha": r.Date, "Condición": r.Condicion, "Rival": r.Rival, "PF": r.PF, "PC": r.PC,
                "Resultado": "G" if r.PF > r.PC else "P", "event_id": r.event_id,
                "Margen esp.": esp_eq, "Total línea": c.get("total"), "vs spread": ats, "Over/Under": ou}
        fila.update(metricas_partido(own, opp, r.PF, r.PC))
        filas.append(fila)
        for j in c["jugadores"]:
            if j["team_id"] == tid:
                jug.append({**j, "Fecha": r.Date, "Rival": r.Rival, "Condición": r.Condicion, "event_id": r.event_id})
    return pd.DataFrame(filas), pd.DataFrame(jug)


# ================================================================ vistas: posiciones y lesiones
@st.cache_data(ttl=600, show_spinner=False)
def posiciones() -> pd.DataFrame:
    j = get_json(f"{V2}/standings")
    grupos = j.get("children") or ([{"name": "Liga", "standings": j.get("standings")}] if j.get("standings") else [])
    filas = []
    for conf in grupos:
        for e in (conf.get("standings") or {}).get("entries", []):
            t = e.get("team") or {}
            fila = {"Conferencia": conf.get("name") or conf.get("abbreviation") or "", "Equipo": t.get("displayName") or t.get("name")}
            for s in e.get("stats", []):
                k = s.get("name") or s.get("displayName")
                if k:
                    fila[k] = s.get("displayValue", s.get("value"))
            filas.append(fila)
    return pd.DataFrame(filas)


def vista_posiciones():
    try:
        p = posiciones()
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudieron leer las posiciones de ESPN: {e}")
        return
    if p.empty:
        st.info("ESPN no devolvió posiciones en este momento.")
        return
    confs = ["Ambas"] + sorted(p["Conferencia"].dropna().unique())
    sel = st.radio("Conferencia", confs, horizontal=True, key="nx_conf")
    v = p if sel == "Ambas" else p[p.Conferencia == sel]
    conocidas = [c for c in COLUMNAS_POSICIONES if c in v.columns]
    tabla = v[["Conferencia", "Equipo"] + conocidas].rename(columns=COLUMNAS_POSICIONES)
    for c in ("G", "P", "Cabeza"):
        if c in tabla.columns:
            tabla[c] = pd.to_numeric(tabla[c], errors="coerce")
    orden = "%G" if "%G" in tabla.columns else "G" if "G" in tabla.columns else None
    if orden:
        tabla["_o"] = pd.to_numeric(tabla[orden], errors="coerce")
        tabla = tabla.sort_values("_o", ascending=False).drop(columns="_o")
    st.dataframe(tabla.reset_index(drop=True), hide_index=True, use_container_width=True)
    resto = [c for c in v.columns if c not in ("Conferencia", "Equipo") and c not in conocidas]
    if resto:
        with st.expander("Todas las columnas que entrega ESPN (local, visita, división, últimos 10, etc.)"):
            st.dataframe(v[["Equipo"] + resto].reset_index(drop=True), hide_index=True, use_container_width=True)


@st.cache_data(ttl=600, show_spinner=False)
def lesiones() -> pd.DataFrame:
    j = get_json(f"{nba.BASE}/injuries")
    filas = []
    for tm in j.get("injuries", []):
        equipo = tm.get("displayName") or (tm.get("team") or {}).get("displayName")
        for i in tm.get("injuries", []):
            a = i.get("athlete") or {}
            det = i.get("details") or {}
            filas.append({"Equipo": equipo, "Jugador": a.get("displayName"),
                          "Pos": (a.get("position") or {}).get("abbreviation"), "Estado": i.get("status"),
                          "Lesión": " ".join(str(x) for x in (det.get("side"), det.get("type"), det.get("location")) if x) or
                                    ((i.get("type") or {}).get("description") if isinstance(i.get("type"), dict) else None),
                          "Regreso estimado": det.get("returnDate"), "Fecha": i.get("date"),
                          "Nota": i.get("shortComment") or i.get("longComment")})
    return pd.DataFrame(filas)


def mostrar_lesiones_partido(*equipos: str):
    """Bloque compacto para el detalle de un partido: lesionados de los dos equipos."""
    df = lesiones()
    if df.empty:
        return
    v = df[df.Equipo.isin(equipos)]
    if not v.empty:
        with st.expander(f"🩹 Lesionados ({len(v)})"):
            st.dataframe(v[["Equipo", "Jugador", "Pos", "Estado", "Lesión", "Regreso estimado"]].reset_index(drop=True),
                         hide_index=True, use_container_width=True)


def vista_lesiones():
    try:
        df = lesiones()
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudieron leer las lesiones de ESPN: {e}")
        return
    if df.empty:
        st.info("ESPN no informa lesiones en este momento.")
        return
    c1, c2 = st.columns(2)
    eqs = c1.multiselect("Equipos", sorted(df.Equipo.dropna().unique()), key="nx_les_eq")
    est = c2.multiselect("Estado", sorted(df.Estado.dropna().unique()), key="nx_les_est")
    v = df
    if eqs:
        v = v[v.Equipo.isin(eqs)]
    if est:
        v = v[v.Estado.isin(est)]
    cuenta = df.groupby("Equipo").size().sort_values(ascending=False).head(10).reset_index()
    cuenta.columns = ["Equipo", "Lesionados"]
    k = st.columns(3)
    k[0].metric("Jugadores en el reporte", len(df))
    k[1].metric("Marcados «Out»", int((df.Estado.astype(str).str.lower() == "out").sum()))
    k[2].metric("Equipos con más bajas", f"{cuenta.iloc[0]['Equipo']} ({cuenta.iloc[0]['Lesionados']})")
    st.dataframe(v.reset_index(drop=True), hide_index=True, use_container_width=True)


# ================================================================ vista: avanzadas y jugadores
_ESTILO_TIRA = """<style>
@keyframes nx-crecer { from { height: 0; } }
@keyframes nx-aparece { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.nx-tit { font-weight: 700; font-size: 1.05rem; margin: .6rem 0 .1rem; animation: nx-aparece .5s ease both; }
.nx-ley { display: flex; flex-wrap: wrap; gap: 14px; font-size: .82rem; opacity: .85; margin: .2rem 0 .5rem; animation: nx-aparece .6s ease both; }
.nx-ley i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
.nx-ley i.ov { background: #009E73; } .nx-ley i.un { background: #D55E00; } .nx-ley i.pu { background: #8A8F98; }
.nx-ley i.nj { background: repeating-linear-gradient(135deg, rgba(127,127,127,.55) 0 3px, transparent 3px 6px); }
.nx-ley i.li { width: 16px; height: 0; border-top: 2px dashed #E69F00; border-radius: 0; vertical-align: 3px; }
.nx-tira { display: flex; gap: 8px; overflow-x: auto; padding: 14px 8px 12px; border: 1px solid rgba(127,127,127,.22);
  border-radius: 16px; background: rgba(127,127,127,.05); }
.nx-j { flex: 1 0 64px; text-align: center; transition: transform .2s ease; }
.nx-j:hover { transform: translateY(-4px); }
.nx-pista { position: relative; height: 190px; display: flex; align-items: flex-end; justify-content: center;
  border-bottom: 2px solid rgba(127,127,127,.35); }
.nx-pista::after { content: ""; position: absolute; left: -5px; right: -5px; bottom: var(--linea); border-top: 2px dashed #E69F00;
  pointer-events: none; animation: nx-aparece 1s ease both; }
.nx-barra { width: 64%; height: var(--h); border-radius: 9px 9px 0 0; animation: nx-crecer .8s cubic-bezier(.2,.8,.2,1) both;
  animation-delay: var(--d); transition: filter .2s ease, box-shadow .2s ease; }
.nx-j:hover .nx-barra { filter: brightness(1.12); box-shadow: 0 0 18px rgba(79,70,229,.35); }
.nx-val { position: absolute; left: 0; right: 0; bottom: calc(var(--h) + 5px); z-index: 2; font-weight: 700; font-size: 1rem;
  animation: nx-aparece .6s ease both; animation-delay: calc(var(--d) + .35s); }
.ov .nx-barra { background: linear-gradient(180deg, #2fd6aa, #009E73); } .ov .nx-val { color: #009E73; }
.un .nx-barra { background: linear-gradient(180deg, #f6a36f, #D55E00); } .un .nx-val { color: #D55E00; }
.pu .nx-barra { background: linear-gradient(180deg, #b4b8c0, #8A8F98); } .pu .nx-val { color: #8A8F98; }
.nj .nx-barra { height: 100%; opacity: .5; background: repeating-linear-gradient(135deg, rgba(127,127,127,.35) 0 6px, transparent 6px 12px); }
.nj .nx-val { bottom: 46%; font-size: .68rem; font-weight: 500; opacity: .75; }
.nx-logo { width: 32px; height: 32px; margin: 9px auto 3px; background-size: contain; background-repeat: no-repeat; background-position: center; }
.nx-rival { font-weight: 600; font-size: .78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nx-meta { font-size: .72rem; opacity: .65; }
@media (prefers-reduced-motion: reduce) { .nx-tira *, .nx-tit, .nx-ley { animation: none !important; } }
</style>"""


STATS_JUGADOR = {"Puntos": "PTS", "Rebotes": "REB", "Asistencias": "AST", "Triples convertidos": "3PM",
                 "Puntos + rebotes + asist.": "PRA", "Puntos + rebotes": "PR", "Puntos + asist.": "PA",
                 "Rebotes + asist.": "RA", "Robos": "STL", "Tapones": "BLK", "Pérdidas": "TO", "Minutos": "MIN"}


def _derivadas(j: pd.DataFrame) -> pd.DataFrame:
    j = j.copy()
    j["PRA"], j["PR"], j["PA"], j["RA"] = j.PTS + j.REB + j.AST, j.PTS + j.REB, j.PTS + j.AST, j.REB + j.AST
    return j


def datos_avanzados(t: pd.DataFrame, nombre: str, n: int):
    """Descarga los box scores de los últimos `n` partidos de `nombre`. Devuelve (pa, ju) o None si no hay datos."""
    tid = str(t.loc[t.Equipo == nombre, "EquipoId"].iloc[0])
    te = t[t.EquipoId == tid].sort_values("Date").tail(n)
    ids = [str(i) for i in te.event_id]
    clave = ("nba_cajas", tuple(ids))
    if clave not in st.session_state:
        barra = st.progress(0.0, text=f"Descargando {len(ids)} box scores...")
        st.session_state[clave] = cargar_cajas(
            ids, lambda h, t: barra.progress(h / t, text=f"Descargando box scores... {h}/{t}"))
        barra.empty()
    cajas, fallos = st.session_state[clave]
    if fallos:
        st.warning(f"{fallos} de {len(ids)} box scores no se pudieron leer; el análisis usa los {len(cajas)} restantes.")
    pa, ju = armar_partidos(te, cajas, tid)
    if pa.empty:
        st.error("No se pudo leer ningún box score. Revisa tu conexión o la página de Diagnóstico.")
        return None
    if "Descanso" in te.columns:  # días de descanso antes de cada partido (0 = back-to-back)
        pa = pa.merge(te[["event_id", "Descanso"]].drop_duplicates("event_id"), on="event_id", how="left")
    return pa, ju


def tab_equipo(nombre: str, pa: pd.DataFrame):
    k = st.columns(6)
    k[0].metric("Ofensiva (pts/100 pos.)", f"{pa.ORtg.mean():.1f}")
    k[1].metric("Defensiva (pts/100 pos.)", f"{pa.DRtg.mean():.1f}")
    k[2].metric("Neto", f"{(pa.ORtg - pa.DRtg).mean():+.1f}")
    k[3].metric("Posesiones por partido", f"{pa.Posesiones.mean():.1f}")
    k[4].metric("eFG %", f"{pa['eFG %'].mean():.1f}")
    k[5].metric("TS %", f"{pa['TS %'].mean():.1f}")
    st.caption(f"Promedio de los últimos {len(pa)} partidos con box score. Posesiones estimadas: TL + 0.44·TLib − Reb. of. + Pérdidas.")

    st.markdown("**Cuatro factores** (equipo vs rivales)")
    ff = pd.DataFrame({
        "Factor": ["Tiro efectivo (eFG %)", "Pérdidas (TOV %)", "Rebote ofensivo (ORB %)", "Tiros libres por tiro de campo"],
        nombre: [pa["eFG %"].mean(), pa["TOV %"].mean(), pa["ORB %"].mean(), pa["FT rate"].mean()],
        "Rivales": [pa["Rival eFG %"].mean(), pa["Rival TOV %"].mean(), pa["Rival ORB %"].mean(), pa["Rival FT rate"].mean()]}).round(1)
    st.dataframe(ff, hide_index=True, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Ofensiva y defensiva por partido**")
        d = pa.melt("Fecha", ["ORtg", "DRtg"], "Métrica", "Pts/100 pos.")
        st.altair_chart(alt.Chart(d).mark_line(strokeWidth=2, point=True).encode(
            x=alt.X("Fecha:T", title=None), y=alt.Y("Pts/100 pos.:Q", scale=alt.Scale(zero=False)),
            color=alt.Color("Métrica:N", scale=alt.Scale(domain=["ORtg", "DRtg"], range=[COLOR_A, COLOR_B])),
            tooltip=["Fecha:T", "Métrica", alt.Tooltip("Pts/100 pos.:Q", format=".1f")]).properties(height=240),
            use_container_width=True)
    with c2:
        st.markdown("**Contra la línea de apuestas**")
        con_l = pa.dropna(subset=["vs spread"])
        con_t = pa.dropna(subset=["Over/Under"])
        if con_l.empty and con_t.empty:
            st.caption("ESPN no guardó la línea de estos partidos.")
        else:
            filas = []
            if not con_l.empty:
                dec = con_l[con_l["vs spread"] != "Push"]
                filas.append({"Mercado": "Spread", "Partidos": len(con_l), "Resultado": f"{(dec['vs spread'] == 'Cubre').sum()}-{(dec['vs spread'] == 'No cubre').sum()}",
                              "%": round((dec["vs spread"] == "Cubre").mean() * 100, 1) if len(dec) else None})
            if not con_t.empty:
                dec = con_t[con_t["Over/Under"] != "Push"]
                filas.append({"Mercado": "Over/Under", "Partidos": len(con_t), "Resultado": f"{(dec['Over/Under'] == 'Over').sum()}-{(dec['Over/Under'] == 'Under').sum()}",
                              "%": round((dec["Over/Under"] == "Over").mean() * 100, 1) if len(dec) else None})
            st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
            st.caption("Spread: cubrir-no cubrir, y % de veces que cubre. Over/Under: over-under, y % de overs.")

    st.markdown("**Estilo de juego**")
    est = pd.DataFrame({"Métrica": ["Triples intentados por tiro de campo %", "Triples %", "Contraataque (pts)", "Pts en pintura",
                                    "Pts tras pérdidas", "Rebotes", "Asistencias", "Pérdidas", "Robos", "Tapones"],
                        "Promedio": [pa["3P rate"].mean(), pa["3P %"].mean(), pa["Contraataque"].mean(), pa["Pts en pintura"].mean(),
                                     pa["Pts tras pérdidas"].mean(), pa["Rebotes"].mean(), pa["Asistencias"].mean(),
                                     pa["Pérdidas"].mean(), pa["Robos"].mean(), pa["Tapones"].mean()]}).round(1)
    st.dataframe(est.dropna(), hide_index=True, use_container_width=True)

    st.markdown("**Partido a partido**")
    v = pa.iloc[::-1].copy()
    v["Fecha"] = v.Fecha.dt.strftime("%d/%m")
    v["Marcador"] = v.apply(lambda r: f"{r.PF:.0f}-{r.PC:.0f}", axis=1)
    cols = ["Fecha", "Condición", "Rival", "Marcador", "Resultado", "Posesiones", "ORtg", "DRtg", "eFG %", "TOV %", "ORB %",
            "Margen esp.", "vs spread", "Total línea", "Over/Under"]
    st.dataframe(v[cols].round(1), hide_index=True, use_container_width=True)
    st.caption("Margen esp. = ventaja que daba la línea a este equipo (positivo = favorito). «vs spread» dice si cubrió esa línea.")


# ================================================================ contexto del partido (por jugador)
ORDEN_DESCANSO = ["Back-to-back (0 días)", "1 día", "2+ días"]


def _cat_descanso(d):
    if pd.isna(d):
        return None
    return ORDEN_DESCANSO[0] if d == 0 else (ORDEN_DESCANSO[1] if d == 1 else ORDEN_DESCANSO[2])


def _agrupar_contexto(h: pd.DataFrame, col: str, linea: float, por: str) -> pd.DataFrame:
    """PJ, minutos, promedio, mediana y % over de `col`, agrupado por la columna `por`."""
    g = h.dropna(subset=[por]).groupby(por, observed=True)
    out = g.agg(PJ=(col, "size"), MIN=("MIN", "mean"), Promedio=(col, "mean"), Mediana=(col, "median"),
                over=(col, lambda s: (s > linea).sum() / max((s != linea).sum(), 1) * 100))
    return out.rename(columns={"over": "% over"}).round(1)


def _tabla_sin_titular(h: pd.DataFrame, ju: pd.DataFrame, jug: str, col: str, linea: float, estados: dict) -> pd.DataFrame:
    """Rendimiento de `jug` en los partidos que se perdió cada compañero titular habitual.

    `h` = partidos que jug jugó. Un compañero «falta» si no aparece en el box score de ese partido.
    `estados` = {jugador: estado de lesión hoy} (de la sección de lesiones)."""
    comp = ju[ju.Jugador != jug]
    if comp.empty or h.empty:
        return pd.DataFrame()
    g = comp.groupby("Jugador").agg(PJ=("event_id", "nunique"), Tit=("Titular", "sum"))
    habituales = g[(g.Tit >= 3) & (g.Tit >= 0.5 * g.PJ)].index
    filas = []
    for t in habituales:
        jugo = set(comp.loc[comp.Jugador == t, "event_id"])
        sin, con = h[~h.event_id.isin(jugo)], h[h.event_id.isin(jugo)]
        estado = estados.get(t)
        if sin.empty and not estado:
            continue
        dec = sin[sin[col] != linea]
        filas.append({"Compañero titular": t, "Estado hoy": estado or "–", "Partidos sin él": len(sin),
                      "Promedio sin él": sin[col].mean(), "Promedio con él": con[col].mean(),
                      "Dif.": sin[col].mean() - con[col].mean(),
                      "% over sin él": (dec[col] > linea).mean() * 100 if len(dec) else np.nan,
                      "MIN sin él": sin["MIN"].mean()})
    if not filas:
        return pd.DataFrame()
    return pd.DataFrame(filas).sort_values("Partidos sin él", ascending=False).round(1).reset_index(drop=True)


def _estados_lesion(equipo) -> dict:
    """{jugador: estado} tomado de la sección de lesiones (ESPN). Si falla, el resto sigue funcionando."""
    try:
        les = lesiones()
        if les.empty:
            return {}
        if equipo:
            les = les[les.Equipo == equipo]
        return dict(zip(les.Jugador, les.Estado))
    except Exception:  # noqa: BLE001
        return {}


def _contexto_partido(jug: str, est_n: str, col: str, linea: float, historial: pd.DataFrame,
                      pa: pd.DataFrame, ju: pd.DataFrame, equipo):
    h = historial.dropna(subset=[col]).copy()
    if "Descanso" in pa.columns:
        h = h.merge(pa[["event_id", "Descanso"]].drop_duplicates("event_id"), on="event_id", how="left")
    else:
        h["Descanso"] = np.nan
    h["Descanso (cat)"] = pd.Categorical(h["Descanso"].map(_cat_descanso), categories=ORDEN_DESCANSO, ordered=True)

    st.markdown("**Contexto del partido**")
    st.caption(f"{est_n} de {jug} en los {len(h)} partidos de la ventana cargada · línea {linea:g}.")
    if len(h) < 3:
        st.info("Muy pocos partidos para analizar el contexto. Sube «Últimos partidos» arriba.")
        return

    t_loc, t_desc, t_riv, t_min, t_baja = st.tabs(
        ["Local / visitante", "Descanso", "Contra el rival", "Minutos", "Sin un titular"])

    with t_loc:
        st.dataframe(_agrupar_contexto(h, col, linea, "Condición"), use_container_width=True)

    with t_desc:
        tab = _agrupar_contexto(h, col, linea, "Descanso (cat)")
        if tab.empty:
            st.info("No hay datos de descanso en estos partidos.")
        else:
            st.dataframe(tab, use_container_width=True)
            st.caption("Descanso = días sin jugar el equipo antes del partido. 0 días = back-to-back.")

    with t_riv:
        tab = _agrupar_contexto(h, col, linea, "Rival").sort_values(["PJ", "Promedio"], ascending=False)
        st.dataframe(tab, use_container_width=True)

    with t_min:
        m = h.dropna(subset=["MIN"])
        k = st.columns(3)
        k[0].metric("Minutos promedio", f"{m['MIN'].mean():.1f}")
        k[1].metric("Mínimo", f"{m['MIN'].min():.0f}")
        k[2].metric("Máximo", f"{m['MIN'].max():.0f}")
        v = m.sort_values("Fecha", ascending=False)
        v = v.assign(Fecha=v["Fecha"].dt.strftime("%d/%m/%Y"))
        cols = ["Fecha", "Rival", "MIN"] + ([col] if col != "MIN" else [])
        st.dataframe(v[cols].rename(columns={col: est_n}), hide_index=True, use_container_width=True)

    with t_baja:
        estados = _estados_lesion(equipo)
        tab = _tabla_sin_titular(h, ju, jug, col, linea, estados)
        if tab.empty:
            st.info("Ningún titular habitual del equipo se perdió partidos en esta ventana.")
        else:
            st.dataframe(tab, hide_index=True, use_container_width=True)
            st.caption("«Estado hoy» viene de la sección de lesiones. Con 1 o 2 partidos sin el titular, no concluyas nada.")


def tab_jugadores(ju: pd.DataFrame, pa: pd.DataFrame, equipo=None):
    if ju.empty:
        st.info("Sin datos de jugadores en estos box scores.")
        return
    ju = _derivadas(ju)
    g = ju.groupby("Jugador").agg(PJ=("PTS", "size"), MIN=("MIN", "mean"), PTS=("PTS", "mean"), REB=("REB", "mean"),
                                  AST=("AST", "mean"), TO=("TO", "mean"), STL=("STL", "mean"), BLK=("BLK", "mean"),
                                  T3=("3PM", "mean"), FGM=("FGM", "sum"), FGA=("FGA", "sum"), M3=("3PM", "sum"),
                                  A3=("3PA", "sum"), FTM=("FTM", "sum"), FTA=("FTA", "sum"), PM=("+/-", "mean"))
    g["FG %"] = g.FGM / g.FGA.replace(0, np.nan) * 100
    g["3P %"] = g.M3 / g.A3.replace(0, np.nan) * 100
    g["TL %"] = g.FTM / g.FTA.replace(0, np.nan) * 100
    g = g.rename(columns={"T3": "3PM", "PM": "+/-"}).drop(columns=["FGM", "FGA", "M3", "A3", "FTM", "FTA"])
    g = g.sort_values("MIN", ascending=False).round(1).reset_index()
    st.markdown("**Promedios por jugador**")
    st.dataframe(g, hide_index=True, use_container_width=True)

    st.markdown("**Analizar a un jugador contra una línea**")
    c1, c2, c3 = st.columns([2, 2, 1])
    jug = c1.selectbox("Jugador", list(g.Jugador), key="nx_jug")
    est_n = c2.selectbox("Estadística", list(STATS_JUGADOR), key="nx_stat")
    col = STATS_JUGADOR[est_n]
    historial = ju[ju.Jugador == jug]
    media_hist = float(historial[col].mean())
    linea = c3.number_input("Línea", value=float(round(media_hist * 2) / 2), step=0.5, key=f"nx_linea_{jug}_{col}")

    # Ventana de partidos: se muestran los últimos N partidos del EQUIPO (también aquellos en que el jugador no jugó).
    total_eq = len(pa)
    n_ver = st.slider("Partidos a mostrar", min(5, total_eq), total_eq, min(15, total_eq), key="nx_n_ver",
                      help="Son los últimos partidos del equipo. Para ver más, sube «Últimos partidos» arriba.") \
        if total_eq > 5 else total_eq
    juegos = pa[["event_id", "Fecha", "Rival", "Condición"]].sort_values("Fecha").tail(n_ver)
    d = juegos.merge(historial[["event_id", col, "MIN"]], on="event_id", how="left").reset_index(drop=True)
    d["Jugó"] = d[col].notna()
    dp = d[d["Jugó"]]
    if dp.empty:
        st.info(f"{jug} no jugó en los últimos {n_ver} partidos del equipo.")
        return

    d["Resultado"] = np.where(~d["Jugó"], "No jugó",
                              np.where(d[col] > linea, "Over", np.where(d[col] < linea, "Under", "Push")))
    nover, nunder = int((d.Resultado == "Over").sum()), int((d.Resultado == "Under").sum())
    k = st.columns(5)
    k[0].metric("Promedio", f"{dp[col].mean():.1f}")
    k[1].metric("Mediana", f"{dp[col].median():.1f}")
    k[2].metric("Últimos 5", f"{dp[col].tail(5).mean():.1f}")
    k[3].metric("Over / Under", f"{nover} / {nunder}")
    k[4].metric("% over", f"{nover / max(nover + nunder, 1):.0%}")
    st.caption(f"Jugó {len(dp)} de los últimos {n_ver} partidos del equipo. Los partidos en que no jugó no cuentan en las métricas.")

    # ---- Tira de partidos: una columna por partido, con logo y nombre del rival siempre visibles ----
    try:
        abrevs = nba.equipos().set_index("Equipo")["Abrev"].to_dict()
    except Exception:  # noqa: BLE001
        abrevs = {}
    entero = bool((dp[col] % 1 == 0).all())
    fmt = (lambda v: f"{v:.0f}") if entero else (lambda v: f"{v:.1f}")
    tope = max(float(dp[col].max()), float(linea), 1.0) * 1.15          # aire arriba para el número
    pct_linea = min(float(linea) / tope * 100, 100)
    clase = {"Over": "ov", "Under": "un", "Push": "pu", "No jugó": "nj"}
    cols_html = []
    for i, (fecha, rival, cond, valor, res) in enumerate(zip(d["Fecha"], d["Rival"], d["Condición"], d[col], d["Resultado"])):
        abrev = abrevs.get(rival, "")
        logo = f"https://a.espncdn.com/i/teamlogos/nba/500/{abrev.lower()}.png" if abrev else ""
        corto = str(rival).split()[-1]
        vs = "vs" if cond == "Local" else "@"
        juega = res != "No jugó"
        alto = valor / tope * 100 if juega else 100
        texto = fmt(valor) if juega else "No jugó"
        tip = f"{fecha:%d/%m/%Y} · {vs} {rival} · " + (f"{fmt(valor)} {est_n} · {res}" if juega else "No jugó")
        cols_html.append(
            f'<div class="nx-j {clase[res]}" style="--h:{alto:.1f}%;--d:{0.05 * i:.2f}s" title="{html.escape(tip)}">'
            f'<div class="nx-pista"><span class="nx-val">{texto}</span><div class="nx-barra"></div></div>'
            f'<div class="nx-logo" style="background-image:url(\'{logo}\')"></div>'
            f'<div class="nx-rival">{html.escape(corto)}</div>'
            f'<div class="nx-meta">{vs} · {fecha:%d/%m}</div></div>')
    leyenda = ('<div class="nx-ley"><span><i class="ov"></i>Over</span><span><i class="un"></i>Under</span>'
               '<span><i class="pu"></i>Push</span><span><i class="nj"></i>No jugó</span>'
               f'<span><i class="li"></i>Línea {linea:g}</span></div>')
    titulo = f'<div class="nx-tit">{html.escape(jug)} · {html.escape(est_n)} · últimos {n_ver} partidos</div>'
    # Los estilos van en su propio bloque: así la tira nunca queda oculta por reglas que esconden bloques con <style>.
    st.markdown(_ESTILO_TIRA, unsafe_allow_html=True)
    st.markdown(titulo + leyenda + f'<div class="nx-tira" style="--linea:{pct_linea:.1f}%">{"".join(cols_html)}</div>',
                unsafe_allow_html=True)

    # ---- Tendencia: valor de cada partido + medias móviles de 5 y 10 contra la línea ----
    tend = graficos.preparar_partidos(
        dp[["Fecha", "Rival", col]].assign(Fecha=dp["Fecha"].dt.strftime("%Y-%m-%d")), col, linea,
        mas_reciente_primero=False)
    if len(tend) >= 3:
        st.markdown("**Tendencia: medias móviles de 5 y 10 partidos**")
        graficos.mostrar_grafico(graficos.grafico_partidos(
            tend, linea, titulo=f"{jug} · {est_n}", etiqueta_y=est_n, alto=280, solo_tendencia=True))
        ult = tend.iloc[-1]
        dif = ult["mm5"] - ult["mm10"]
        if abs(dif) >= 0.05:
            st.caption(("📈 En alza" if dif > 0 else "📉 A la baja")
                       + f": media de los últimos 5 = {ult['mm5']:.1f} vs. últimos 10 = {ult['mm10']:.1f} "
                       f"(la línea está en {linea:g}). Solo cuenta los partidos que jugó.")

    _contexto_partido(jug, est_n, col, linea, historial, pa, ju, equipo)

    st.caption("La línea no viene de ninguna casa: la pones tú. Con pocos partidos, el % over varía mucho.")
