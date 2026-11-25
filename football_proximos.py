"""Fútbol · Próximos partidos: la misma tabla que la NBA (hora, escudos, línea, pronóstico, bajas y picks de jugadores).

Funciona con la liga que ya está cargada en football.py (`liga.t`, la tabla de partidos por equipo de football-data.co.uk)
y con el calendario de ESPN. Reutiliza de football_lineas: el cruce de nombres football-data <-> ESPN, la lista de ligas,
la descarga de estadísticas por jugador y la lista de equipos con sus ids.

Uso desde football.py (como una pestaña propia, igual que en la NBA: «📅 Próximos»):

    import football_proximos
    football_proximos.proximos(liga)

El botón «🎯 Analizar» te lleva a «Líneas» y deja elegidos el local (Equipo A), la visita (Equipo B), el mercado
«Total de goles del partido» y la línea de ESPN (o la estándar 2.5).

Pronóstico (modelo de Poisson, el estándar para goles de fútbol):
  · Ataque y defensa de cada equipo = goles anotados/recibidos en sus últimos 15 partidos de liga, corregidos por sede
    (local o visita), con más peso a los recientes (cada partido anterior pesa un 10 % menos) y suavizados hacia el promedio.
  · Goles esperados: local = media de goles de local × ataque local × defensa visita; la visita, al revés.
  · De ahí salen: 1X2, marcador más probable, hándicap, más/menos de una línea y ambos anotan.
  · Bajas: leídas de la plantilla de ESPN. Con «Picks de jugadores» activo también se descuenta lo que el ausente aportaba.
"""
import math
import re
from datetime import timedelta
from html import escape as _e

import pandas as pd
import streamlit as st

import football_lineas as fl
from common import ZONA, get_json

ESPN_MARCADOR = "https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/scoreboard"
ESPN_PLANTILLA = "https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/teams/{id}/roster"

# --- Ajustes del modelo -------------------------------------------------------------------------------------------
_VENTANA = 15            # últimos partidos de liga de cada equipo
_PESO = 0.9              # el partido más reciente pesa 1 y cada anterior un 10 % menos
_PRIOR = 3.0             # peso del «equipo promedio» con el que se suaviza (evita extremos con pocos partidos)
_MIN_PARTIDOS = 5        # menos que esto: no se proyecta
_MAX_GOLES = 10          # tamaño de la tabla de marcadores
_LINEA_STD = 2.5         # total de goles de referencia cuando ESPN no trae línea
_MAX_BAJA = 0.25         # las bajas nunca quitan más de este % de los goles esperados
_ABSORBEN = 0.5          # de lo que aportaba un ausente, los compañeros cubren este %
_MAX_BAJAS_CHIP = 4

# --- Ajustes de los picks de jugadores ------------------------------------------------------------------------------
_N_PARTIDOS_J = 12       # partidos del equipo que se miran
_MIN_TITULAR = 5         # mínimo de partidos de titular en la ventana
_FRAC_TITULAR = 0.5      # y haber sido titular en al menos esta fracción de los partidos del equipo
_ACIERTO_LINEA = 0.8     # la línea elegida es la más alta que el jugador superó al menos esta fracción de las veces
_CONF_MIN = 0.70         # confianza mínima para mostrar un pick
_PICKS_EQUIPO = 5

# (clave en fl._cargar_jugadores, texto, líneas posibles de menor a mayor, para quién)
_STATS_PICK = [
    ("tiros", "tiros", (0.5, 1.5, 2.5, 3.5), "campo"),
    ("tp", "tiros a puerta", (0.5, 1.5, 2.5), "campo"),
    ("goles", "goles", (0.5,), "campo"),
    ("asist", "asistencias", (0.5,), "campo"),
    ("faltas", "faltas", (0.5, 1.5, 2.5, 3.5), "todos"),
    ("faltas_rec", "faltas recibidas", (0.5, 1.5, 2.5), "campo"),
    ("amarillas", "tarjetas amarillas", (0.5,), "todos"),
    ("paradas", "paradas", (1.5, 2.5, 3.5, 4.5), "portero"),
]
# estadística del jugador -> (dato del equipo que la mueve, «ag» = lo que el rival concede / «for» = lo que el rival produce)
_DRIVER = {"tiros": ("tiros", "ag"), "tp": ("tp", "ag"), "goles": ("goles", "ag"), "asist": ("asist", "ag"),
           "paradas": ("tp", "for"), "faltas_rec": ("faltas", "for")}

_ESTADO_ES = {"out": "Baja", "doubtful": "Duda", "questionable": "Duda", "day-to-day": "Día a día", "suspen": "Suspendido"}
_GRAVEDAD = {"out": 0, "suspen": 0, "doubtful": 1, "questionable": 2, "day": 3}
_PROB_BAJA = {"out": 1.0, "suspen": 1.0, "doubtful": 0.85, "questionable": 0.5, "day": 0.3}


# ---------------------------------------------------------------------------
# Calendario (ESPN)
# ---------------------------------------------------------------------------
def _hoy():
    return pd.Timestamp.now(tz=ZONA).date()


def _num(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _equipo_espn(c):
    t = c.get("team") or {}
    logos = t.get("logos") or []
    return {"espn_id": str(t.get("id", "")), "abbr": t.get("abbreviation") or "", "logo": t.get("logo") or (logos[0].get("href", "") if logos else ""),
            "nombres": [t.get(k) for k in ("displayName", "shortDisplayName", "name", "location")]}


@st.cache_data(ttl=300, show_spinner=False)
def _calendario(liga_espn, dias):
    """Partidos de ESPN de los días dados (tupla de 'YYYYMMDD'), una consulta por día (ESPN rechaza los rangos con 400).

    Si falla un día se ignora; solo LANZA error si fallan todos, así no se guarda un resultado vacío en caché."""
    eventos, vistos, ultimo_error, ok = [], set(), None, 0
    for d in dias:
        try:
            js = get_json(ESPN_MARCADOR.format(liga=liga_espn), params={"dates": d})
            ok += 1
        except Exception as e:  # noqa: BLE001
            ultimo_error = e
            continue
        eventos += [ev for ev in js.get("events") or [] if ev.get("id") not in vistos and not vistos.add(ev.get("id"))]
    if not ok:
        raise ultimo_error
    out = []
    for ev in eventos:
        comp = (ev.get("competitions") or [{}])[0]
        tipo = (comp.get("status") or ev.get("status") or {}).get("type") or {}
        comps = comp.get("competitors") or []
        loc = next((c for c in comps if c.get("homeAway") == "home"), None)
        vis = next((c for c in comps if c.get("homeAway") == "away"), None)
        if not loc or not vis:
            continue
        odds = (comp.get("odds") or [{}])[0] or {}
        out.append({"id": str(ev.get("id")), "fecha": ev.get("date"), "estado": tipo.get("state"), "local": _equipo_espn(loc),
                    "visita": _equipo_espn(vis), "linea_total": _num(odds.get("overUnder")), "linea_txt": str(odds.get("details") or "")})
    return out


def _asignar(partidos, nombres, liga_espn):
    """Añade a cada equipo del calendario su nombre en football-data (`fd`) y su id en la lista de Líneas (`id`)."""
    espn, vistos = [], set()
    for p in partidos:
        for lado in ("local", "visita"):
            e = p[lado]
            if e["espn_id"] not in vistos:
                vistos.add(e["espn_id"])
                espn.append(e)
    casado = fl._emparejar(nombres, espn)                      # {nombre football-data: equipo ESPN}
    inv = {e["espn_id"]: nombre for nombre, e in casado.items()}
    ids = {e["nombre"]: e for e in fl._equipos_liga(nombres, liga_espn)}
    for p in partidos:
        for lado in ("local", "visita"):
            e = p[lado]
            fd = inv.get(e["espn_id"])
            e["fd"] = fd
            e["id"] = ids[fd]["id"] if fd in ids else None
            e["color"] = ids[fd]["color"] if fd in ids else None
            e["nombre"] = fd or next((n for n in e["nombres"] if n), "?")
            e["abbr"] = e["abbr"] or e["nombre"][:3].upper()
    return partidos


# ---------------------------------------------------------------------------
# Modelo de goles (Poisson)
# ---------------------------------------------------------------------------
def _sin_neutral(t):
    if "Neutral" not in t.columns:
        return pd.Series(True, index=t.index)
    return ~t["Neutral"].fillna(False).astype(bool)


def _bases(t):
    """(goles medios del local, goles medios de la visita) de toda la tabla; None si hay muy pocos partidos."""
    ok = _sin_neutral(t)
    loc, vis = t[(t.Condicion == "Local") & ok].GF.dropna(), t[(t.Condicion == "Visita") & ok].GF.dropna()
    if len(loc) < 30 or len(vis) < 30:
        return None
    return float(loc.mean()), float(vis.mean())


def _fuerza(t, nombre, base_l, base_v):
    """(ataque, defensa, partidos): 1.0 = como el equipo promedio de su sede. Defensa > 1 = recibe más de lo normal."""
    d = t[t.Equipo == nombre].dropna(subset=["GF", "GC"]).sort_values("Date").tail(_VENTANA)
    if len(d) < _MIN_PARTIDOS:
        return None
    n, sa, sd, sw, mu = len(d), 0.0, 0.0, 0.0, (base_l + base_v) / 2
    for i, r in enumerate(d.to_dict("records")):
        w = _PESO ** (n - 1 - i)
        neu = r.get("Neutral")
        neu = bool(neu) if neu is not None and not pd.isna(neu) else False
        if neu:
            rf = rc = mu
        elif r["Condicion"] == "Local":
            rf, rc = base_l, base_v
        else:
            rf, rc = base_v, base_l
        sa += w * r["GF"] / rf
        sd += w * r["GC"] / rc
        sw += w
    return (sa + _PRIOR) / (sw + _PRIOR), (sd + _PRIOR) / (sw + _PRIOR), n


def _pmf(lam):
    p = [math.exp(-lam)]
    for i in range(1, _MAX_GOLES + 1):
        p.append(p[-1] * lam / i)
    return p


def _matriz(ll, lv):
    """m[i][j] = probabilidad de que el local marque i y la visita j."""
    pl, pv = _pmf(ll), _pmf(lv)
    m = [[a * b for b in pv] for a in pl]
    s = sum(map(sum, m))
    return [[x / s for x in fila] for fila in m]


def _p_hand(m, h, local=True):
    """Probabilidad de cubrir un hándicap h (sin contar el empate «push»). Las líneas de cuarto (±0.25, ±0.75) se parten en dos."""
    if abs(h * 2 - round(h * 2)) > 1e-9:
        return (_p_hand(m, h - 0.25, local) + _p_hand(m, h + 0.25, local)) / 2
    ok = no = 0.0
    for i, fila in enumerate(m):
        for j, p in enumerate(fila):
            v = ((i - j) if local else (j - i)) + h
            if v > 1e-9:
                ok += p
            elif v < -1e-9:
                no += p
    return ok / (ok + no) if ok + no else 0.5


def _p_total(m, linea):
    """(P(más de la línea), P(menos de la línea)) sin contar el «push» de las líneas enteras."""
    mas = menos = 0.0
    for i, fila in enumerate(m):
        for j, p in enumerate(fila):
            if i + j > linea + 1e-9:
                mas += p
            elif i + j < linea - 1e-9:
                menos += p
    s = mas + menos
    return (mas / s, menos / s) if s else (0.5, 0.5)


def _pronostico_base(t, nom_l, nom_v):
    """Goles esperados y probabilidades del partido; None si falta información de alguno de los dos equipos."""
    if not nom_l or not nom_v:
        return None
    b = _bases(t)
    if not b:
        return None
    fl_, fv_ = _fuerza(t, nom_l, *b), _fuerza(t, nom_v, *b)
    if not fl_ or not fv_:
        return None
    return {"base_l": b[0], "base_v": b[1], "att_l": fl_[0], "def_l": fl_[1], "att_v": fv_[0], "def_v": fv_[1],
            "lam_l": b[0] * fl_[0] * fv_[1], "lam_v": b[1] * fv_[0] * fl_[1]}


def _completar(pr, loss_l=0.0, loss_v=0.0):
    """Aplica las bajas (fracción de goles que pierde cada equipo) y calcula todas las probabilidades."""
    ll, lv = pr["lam_l"] * (1 - loss_l), pr["lam_v"] * (1 - loss_v)
    m = _matriz(ll, lv)
    n = len(m)
    p_l = sum(m[i][j] for i in range(n) for j in range(n) if i > j)
    p_v = sum(m[i][j] for i in range(n) for j in range(n) if i < j)
    (mi, mj) = max(((i, j) for i in range(n) for j in range(n)), key=lambda ij: m[ij[0]][ij[1]])
    btts = sum(m[i][j] for i in range(1, n) for j in range(1, n))
    return {**pr, "ll": ll, "lv": lv, "m": m, "p_l": p_l, "p_x": 1 - p_l - p_v, "p_v": p_v, "total": ll + lv, "margen": ll - lv,
            "marcador": (mi, mj, m[mi][mj]), "btts": btts, "loss_l": loss_l, "loss_v": loss_v}


# ---------------------------------------------------------------------------
# Bajas (ESPN) y su efecto
# ---------------------------------------------------------------------------
def _clave_estado(estado):
    e = str(estado or "").lower()
    return next((k for k in _GRAVEDAD if k in e), None)


@st.cache_data(ttl=1800, show_spinner=False)
def _bajas_espn(liga_espn, team_id):
    """Jugadores con lesión o sanción en la plantilla de ESPN: [{jid, Jugador, Estado, Lesión}]. Lanza error si ESPN no responde."""
    js = get_json(ESPN_PLANTILLA.format(liga=liga_espn, id=team_id))
    out = []
    for a in fl._atletas(js):
        for inj in a.get("injuries") or []:
            estado = inj.get("status") or (inj.get("type") or {}).get("description") or ""
            det = inj.get("details") or {}
            out.append({"jid": str(a.get("id")), "Jugador": a.get("displayName") or a.get("fullName") or "?", "Estado": str(estado),
                        "Lesión": str(inj.get("shortComment") or det.get("type") or "")})
            break
    return out


def _estado_es(estado):
    e = str(estado or "").lower()
    return next((v for k, v in _ESTADO_ES.items() if k in e), str(estado or ""))


def _prob_no_juega(b):
    k = _clave_estado(b.get("Estado"))
    return _PROB_BAJA.get(k, 0.5)


def _aporte(df, jid):
    """Parte de los goles del equipo en que participó ese jugador (gol = 1, asistencia = 0.5; el total del equipo suma 1.5 por gol)."""
    if df is None or not len(df):
        return 0.0
    d = df[df.propio]
    goles_eq = d.goles.sum()
    if goles_eq <= 0:
        return 0.0
    j = d[d.jid == str(jid)]
    return float((j.goles.sum() + 0.5 * j.asist.sum()) / (1.5 * goles_eq))


def _impacto_bajas(bajas, df):
    """(fracción de goles que pierde el equipo, detalle [(jugador, estado, goles que pierde, aporte)]) sobre los ausentes con peso."""
    perdido, detalle = 0.0, []
    for b in bajas or []:
        p = _prob_no_juega(b)
        ap = _aporte(df, b["jid"])
        perdido += _ABSORBEN * ap * p
        detalle.append({"nombre": b["Jugador"], "estado": b["Estado"], "p": p, "aporte": ap, "frac": _ABSORBEN * ap * p,
                        "grav": _GRAVEDAD.get(_clave_estado(b["Estado"]), 9)})
    if perdido > _MAX_BAJA:   # tope: se reparte entre los ausentes para que el detalle sume lo mismo que se descuenta
        for d in detalle:
            d["frac"] *= _MAX_BAJA / perdido
    detalle.sort(key=lambda x: (x["grav"], -x["aporte"], x["nombre"]))
    return min(perdido, _MAX_BAJA), detalle


# ---------------------------------------------------------------------------
# Picks de jugadores
# ---------------------------------------------------------------------------
def _factores_rival(df_a, df_r):
    """{estadística: factor} para los jugadores de A frente al rival R. 1.05 = el rival permite un 5 % más.

    Igual que en la NBA: se compara lo que R concede (o produce) con el promedio de los partidos de ambos, se toma el 60 % de la
    desviación y se limita a ±12 %, porque con ~12 partidos hay mucho ruido."""
    res = {}
    for stat, (col, lado) in _DRIVER.items():
        todos = [v for d in (df_a, df_r) for v in d.groupby(["evento", "propio"])[col].sum().tolist()]
        sel = df_r[~df_r.propio] if lado == "ag" else df_r[df_r.propio]
        x = sel.groupby("evento")[col].sum().tolist()
        if len(x) < 5 or not todos or sum(todos) <= 0:
            res[stat] = 1.0
            continue
        raw = (sum(x) / len(x)) / (sum(todos) / len(todos))
        res[stat] = max(0.88, min(1.12, 1 + 0.6 * (raw - 1)))
    return res


def _picks_equipo(df, bajas, fr):
    """(picks, notas). Para cada jugador habitual de titular y cada estadística busca la línea «Más de X.5» más alta que superó en al
    menos el 80 % de sus últimos partidos de titular. Confianza = acierto suavizado × probabilidad de jugar × ajuste por rival."""
    d = df[df.propio]
    eventos = sorted(d.evento.unique(), key=lambda e: d[d.evento == e].fecha.max())[-_N_PARTIDOS_J:]
    d = d[d.evento.isin(eventos)]
    ne = len(eventos)
    if ne < _MIN_PARTIDOS:
        return [], []
    prob_no = {str(b["jid"]): _prob_no_juega(b) for b in bajas or []}
    con_dato = {c for c, *_ in _STATS_PICK if d[c].sum() > 0}   # si ESPN no trae esa estadística, no se inventan picks
    cand = []
    for jid, g in d.groupby("jid"):
        tit = g[g.titular]
        if len(tit) < _MIN_TITULAR or len(tit) / ne < _FRAC_TITULAR or prob_no.get(jid, 0) >= 0.85:
            continue
        grupos = g.grupo.dropna()
        grupo = grupos.mode().iat[0] if len(grupos) else None
        p_juega = (1 - prob_no.get(jid, 0)) * (0.5 + 0.5 * len(tit) / ne)
        for clave, texto, lineas, quien in _STATS_PICK:
            if clave not in con_dato:
                continue
            if (quien == "portero" and grupo != "Portero") or (quien == "campo" and grupo == "Portero"):
                continue
            v = tit[clave].tolist()
            mejor = None
            for L in lineas:
                if sum(x > L for x in v) / len(v) >= _ACIERTO_LINEA:
                    mejor = L
            if mejor is None:
                continue
            k = sum(x > mejor for x in v)
            f = fr.get(clave, 1.0)
            conf = min(0.99, (k + 1) / (len(v) + 2) * p_juega * (1 + 0.5 * (f - 1)))
            if conf >= _CONF_MIN:
                cand.append({"nombre": tit.jugador.iloc[-1], "k": jid, "stat": clave, "texto": texto, "linea": mejor, "conf": conf,
                             "riesgo": jid in prob_no, "fr": f, "hit": f"{k}/{len(v)}"})
    cand.sort(key=lambda c: (-round(c["conf"], 2), -c["linea"]))
    picks, por_jugador = [], {}
    for c in cand:
        if por_jugador.get(c["k"], 0) >= 2:
            continue
        por_jugador[c["k"]] = por_jugador.get(c["k"], 0) + 1
        picks.append(c)
        if len(picks) == _PICKS_EQUIPO:
            break
    notas = []
    for b in bajas or []:
        ap, p = _aporte(df, b["jid"]), _prob_no_juega(b)
        if ap >= 0.12 and p >= 0.85:
            notas.append(f"⭐ Sin <b>{_e(b['Jugador'])}</b>: el equipo pierde parte de su gol (aportaba el {ap:.0%} de los goles y asistencias)")
        elif ap >= 0.12 and p >= 0.3:
            notas.append(f"⚠ <b>{_e(b['Jugador'])}</b> es duda: sus compañeros y el equipo bajan de confianza")
    return picks, notas[:2]


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
_CSS = """
.st-key-fut_prox_panel{background:#f1f5f9;border:1px solid #cfe3d3;border-radius:18px;padding:18px 18px 12px;
  box-shadow:0 8px 24px -12px rgba(15,23,42,.18)}
[class*="st-key-fut_prox_fila_"]{box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;gap:0 !important;
  height:auto !important;min-height:68px;overflow:visible;background:#fff;border:1px solid #e2e8f0;border-left:4px solid #16a34a;
  border-radius:18px;padding:16px 22px !important;box-shadow:0 1px 2px rgba(15,23,42,.04),0 12px 28px -16px rgba(15,23,42,.28);
  transition:box-shadow .2s,transform .2s}
[class*="st-key-fut_prox_fila_"] > div,[class*="st-key-fut_prox_fila_"] [data-testid="stElementContainer"]{height:auto !important;min-height:0}
[class*="st-key-fut_prox_fila_"]:hover{box-shadow:0 6px 16px -6px rgba(22,163,74,.30);transform:translateY(-1px)}
[class*="st-key-fut_prox_fila_"] [data-testid="stHorizontalBlock"]{gap:.5rem;align-items:center}
[class*="st-key-fut_prox_fila_"] [data-testid="stMarkdownContainer"] p{margin:0}
[class*="st-key-fut_prox_fila_"] [data-testid="stMarkdownContainer"],[class*="st-key-fut_prox_fila_"] [data-testid="stMarkdown"]{margin:0 !important;padding:0 !important}
[class*="st-key-fut_prox_fila_"] [data-testid="stElementContainer"],[class*="st-key-fut_prox_fila_"] [data-testid="stHorizontalBlock"]{margin:0 !important}
[class*="st-key-fut_prox_fila_"] [data-testid="stVerticalBlock"]{gap:0 !important}
[class*="st-key-fut_prox_fila_"] button{min-height:1.9rem !important;padding:0 .5rem !important;font-size:.78rem !important;border-radius:9px !important;box-shadow:none !important}
.fx{display:flex;align-items:center;gap:14px;min-height:58px;color:#14231a}
.fx-hora{flex:none;text-align:center;padding:7px 13px;margin-right:6px;border-radius:12px;background:linear-gradient(180deg,#f2fbf4,#e0f3e5);
  border:1px solid #cfe3d3;color:#166534;font-weight:800;font-size:.9rem;letter-spacing:.02em;font-variant-numeric:tabular-nums;box-shadow:0 1px 2px rgba(22,101,52,.10)}
.fx-eq{display:flex;align-items:center;gap:12px;flex:none;min-width:0}
.fx-lg,.fx-ab{flex:none;width:52px;height:52px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 0 1px rgba(15,23,42,.06),0 6px 14px -6px rgba(15,23,42,.30)}
.fx-lg{background:radial-gradient(circle at 30% 25%,#fff,#f1f4f9)}
.fx-lg img{width:34px !important;height:34px !important;object-fit:contain;border-radius:0 !important;margin:0 !important}
.fx-ab{background:#dcfce7;font-size:.68rem;font-weight:800;color:#166534}
.fx-eq span{display:flex;flex-direction:column;line-height:1.2;min-width:0}
.fx-eq b{font-size:1.08rem;font-weight:800;letter-spacing:.03em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fx-eq small{font-size:.6rem;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:#7c8798}
.fx-eq.loc b{color:#14532d}
.fx-at{flex:none;margin:0 -4px;padding:2px 9px;border-radius:99px;border:1px solid #e2e8f0;background:rgba(255,255,255,.85);
  color:#94a3b8;font-weight:700;font-size:.66rem;letter-spacing:.12em;text-transform:uppercase}
.fx-lin{flex:none;margin-left:auto;display:flex;flex-direction:column;gap:3px;padding-left:18px;border-left:1px solid #e2e8f0;font-size:.74rem;line-height:1.3;color:#4b5563;text-align:right}
.fx-lin b{color:#111827}.fx-lin em{font-style:normal;color:#6b7280}
.fx-lin b.fx-mas{color:#047857}.fx-lin b.fx-menos{color:#b91c1c}
.fr{margin-top:12px;padding:12px 0 2px;border-top:1px dashed #dbe2ee}
.fr-marc{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:14px}
.fr-eq{display:flex;align-items:baseline;gap:10px;color:#64748b}
.fr-eq.der{justify-content:flex-end}
.fr-eq b{font-size:.78rem;letter-spacing:.06em}
.fr-pts{font-size:1.7rem;font-weight:800;line-height:1;color:#64748b;font-variant-numeric:tabular-nums}
.fr-eq.gana,.fr-eq.gana b,.fr-eq.gana .fr-pts{color:#14532d}
.fr-mid{text-align:center;font-size:.68rem;letter-spacing:.05em;text-transform:uppercase;color:#64748b;line-height:1.35}
.fr-mid strong{display:block;font-size:.84rem;letter-spacing:0;text-transform:none;color:#111827}
.fr-bar{display:flex;height:6px;margin:9px 0 3px;border-radius:99px;overflow:hidden;background:#e2e8f0}
.fr-bar i{display:block;height:100%;background:linear-gradient(90deg,#16a34a,#4ade80)}
.fr-bar i.x{background:#cbd5e1}.fr-bar i.v{background:#94a3b8}
.fr-leg{display:flex;justify-content:space-between;font-size:.64rem;color:#94a3b8;margin-bottom:8px;font-variant-numeric:tabular-nums}
.fr-chips{display:flex;flex-wrap:wrap;gap:6px}
.fr-chip{padding:3px 10px;border-radius:99px;font-size:.7rem;font-weight:600;background:#f1f5f9;color:#334155;border:1px solid #e2e8f0}
.fr-chip.ok{background:#ecfdf5;color:#047857;border-color:#a7f3d0}
.fr-chip.no{background:#fef2f2;color:#b91c1c;border-color:#fecaca}
.fr-chip.med{background:#fffbeb;color:#b45309;border-color:#fde68a}
.fr-bajas{margin-top:8px;padding-bottom:2px;font-size:.7rem;line-height:1.5;color:#64748b}
.fr-bajas b{color:#334155}.fr-bajas em{font-style:normal;color:#94a3b8}
.fk{margin-top:12px;padding-top:10px;border-top:1px dashed #dbe2ee}
.fk-cols{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media (max-width:900px){.fk-cols{grid-template-columns:1fr}}
.fk-tit{font-size:.66rem;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:#475569;margin-bottom:6px}
.fk-lista{display:flex;flex-direction:column;gap:5px}
.fk-it{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:5px 10px;border-radius:10px;font-size:.74rem;background:#f8fafc;border:1px solid #e2e8f0;color:#334155}
.fk-it b{color:#111827}.fk-it .fk-p{flex:none;font-weight:800;font-variant-numeric:tabular-nums}
.fk-it.alto{background:#ecfdf5;border-color:#a7f3d0}.fk-it.alto .fk-p{color:#047857}
.fk-it.med{background:#fffbeb;border-color:#fde68a}.fk-it.med .fk-p{color:#b45309}
.fk-it.riesgo{background:#fef2f2;border-color:#fecaca}.fk-it.riesgo .fk-p{color:#b91c1c}
.fk-it em{font-style:normal;color:#64748b;font-size:.68rem}
.fk-nota{margin-top:6px;font-size:.7rem;line-height:1.45;color:#92400e;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:5px 10px}
.fk-nota b{color:#78350f}
.fk-vacio{font-size:.7rem;color:#94a3b8}
"""

_RE_HANDICAP = re.compile(r"^(\S+)\s+([+-]?\d+(?:\.\d+)?)$")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _color(eq):
    c = eq.get("color")
    return c if isinstance(c, str) and _HEX.match(c) else fl._color_eq(eq["nombre"])


def _rgba(hexa, alfa):
    r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alfa})"


def _logo_ok(url):
    url = str(url or "")
    return url if (url.startswith("https://") or url.startswith("data:image/svg+xml;base64,")) and not any(c in url for c in "\"'()<> \\") else ""


def _eq_html(eq, rol, clase=""):
    url = _logo_ok(eq.get("logo"))
    img = f'<div class="fx-lg"><img src="{_e(url)}" alt=""></div>' if url else f'<div class="fx-ab">{_e(eq["abbr"])}</div>'
    return f'<div class="fx-eq {clase}">{img}<span><b title="{_e(eq["nombre"])}">{_e(eq["abbr"])}</b><small>{rol}</small></span></div>'


def _css_fondos(partidos):
    """Una regla por partido: franja con los colores de ambos equipos, velo suave en cada esquina y escudos translúcidos de fondo."""
    reglas = []
    for p in partidos:
        sel = f".st-key-fut_prox_fila_{p['id']}"
        cl, cv = _color(p["local"]), _color(p["visita"])
        fondo = (f"linear-gradient(90deg,{cl} 0%,{cl} 45%,{cv} 55%,{cv} 100%) top/100% 5px no-repeat,"
                 f"radial-gradient(560px 300px at 0% 0%,{_rgba(cl, .13)},transparent 70%),"
                 f"radial-gradient(560px 300px at 100% 0%,{_rgba(cv, .13)},transparent 70%)")
        reglas.append(f"{sel}{{position:relative;isolation:isolate;overflow:hidden !important;background:{fondo},#fff !important;"
                      f"border:1px solid #d9e0ec !important;border-left:1px solid #d9e0ec !important;"
                      f"box-shadow:0 1px 2px rgba(15,23,42,.05),0 16px 34px -18px rgba(15,23,42,.38) !important}}")
        for pseudo, lado, eq in (("before", "left", p["local"]), ("after", "right", p["visita"])):
            url = _logo_ok(eq.get("logo"))
            if url:
                reglas.append(f"{sel}::{pseudo}{{content:'';position:absolute;{lado}:-46px;top:-24px;width:230px;height:230px;"
                              f"background:url('{url}') center/contain no-repeat;opacity:.09;pointer-events:none;z-index:-1}}")
    return "".join(reglas)


def _hand_espn(p):
    """(abreviatura, valor) del hándicap de ESPN si viene como «MCI -1.5»; None si no."""
    m = _RE_HANDICAP.match(str(p.get("linea_txt") or "").strip())
    if not m:
        return None
    ab, v = m.group(1), float(m.group(2))
    ab_l, ab_v = p["local"]["abbr"], p["visita"]["abbr"]
    if ab not in (ab_l, ab_v) or v == 0:
        return None
    return ab, v


def _linea_total(p, pr):
    """(línea usada, ¿es de ESPN?)."""
    if p.get("linea_total"):
        return float(p["linea_total"]), True
    return _LINEA_STD, False


def _lineas_prox(p, pr):
    filas = []
    h = _hand_espn(p)
    if h:
        ab, v = h
        filas.append(f"🎯 Hándicap <b>{_e(ab)} {v:+g}</b> <em>({'favorito' if v < 0 else 'underdog'})</em>")
    elif p.get("linea_txt") and not _RE_HANDICAP.match(p["linea_txt"].strip()):
        filas.append(f"🎯 <b>{_e(p['linea_txt'])}</b>")
    t, de_espn = _linea_total(p, pr)
    if pr:
        mas = _p_total(pr["m"], t)[0] >= 0.5
        lado = f'<b class="fx-mas">▲ Más +{t:g} goles</b>' if mas else f'<b class="fx-menos">▼ Menos −{t:g} goles</b>'
        filas.append("Total de goles <em>(ambos)</em> " + lado + ("" if de_espn else " <em>(línea estándar)</em>"))
    elif de_espn:
        filas.append(f"Total de goles <em>(ambos)</em> <b>{t:g}</b>")
    return "".join(f"<span>{f}</span>" for f in filas) or "<span><em>sin línea aún</em></span>"


def _html_picks(ab_l, ab_v, pr):
    def col(ab, picks, notas):
        if picks:
            items = []
            for c in picks:
                clase = "riesgo" if c["riesgo"] else "alto" if c["conf"] >= 0.9 else "med"
                extra = []
                if abs(c["fr"] - 1) >= 0.03:
                    extra.append(f'rival {"permite más" if c["fr"] > 1 else "permite menos"} ({c["fr"] - 1:+.0%})')
                extra.append(f'{c["hit"]} partidos')
                aviso = " ⚠" if c["riesgo"] else ""
                items.append(f'<div class="fk-it {clase}"><span><b>{_e(c["nombre"])}</b>{aviso} · Más de {c["linea"]:.1f} {_e(c["texto"])} '
                             f'<em>({_e(" · ".join(extra))})</em></span><span class="fk-p">{c["conf"]:.0%}</span></div>')
            cuerpo = f'<div class="fk-lista">{"".join(items)}</div>'
        else:
            cuerpo = '<div class="fk-vacio">Sin picks con suficiente confianza.</div>'
        cuerpo += "".join(f'<div class="fk-nota">{n}</div>' for n in notas)
        return f'<div><div class="fk-tit">🎯 {_e(ab)} · picks más seguros</div>{cuerpo}</div>'

    return (f'<div class="fk"><div class="fk-cols">{col(ab_l, pr.get("picks_l"), pr.get("notas_l", []))}'
            f'{col(ab_v, pr.get("picks_v"), pr.get("notas_v", []))}</div></div>')


def _html_bajas(ab, det, lam):
    """Chips de bajas. Con datos de jugadores muestra, además, los goles esperados que pierde el equipo por cada ausente."""
    if det is None:
        return f"<b>{_e(ab)}</b> <em>sin datos de lesiones</em>"
    if not det:
        return f"<b>{_e(ab)}</b> <em>sin bajas reportadas por ESPN</em>"
    partes = []
    for d in det[:_MAX_BAJAS_CHIP]:
        partes.append(f"{_e(d['nombre'])} <em>({_e(_estado_es(d['estado']))})</em>" + (f" −{d['frac'] * lam:.2f}" if lam and d["frac"] * lam >= 0.02 else ""))
    if len(det) > _MAX_BAJAS_CHIP:
        partes.append(f"+{len(det) - _MAX_BAJAS_CHIP} más")
    return f"<b>{_e(ab)}</b> " + ", ".join(partes)


def _html_pron(p, pr):
    """Bloque del pronóstico dentro de la tarjeta: goles esperados, 1X2, marcador más probable, líneas y bajas."""
    ab_l, ab_v = p["local"]["abbr"], p["visita"]["abbr"]
    pl, px, pv = pr["p_l"], pr["p_x"], pr["p_v"]
    gana_l = pl >= pv
    top = max(pl, pv)
    if px > top:
        centro, gana_l = f"Empate · {px:.0%}", None
    else:
        centro = f"Gana {_e(ab_l if gana_l else ab_v)} · {top:.0%}"
    m = abs(pr["margen"])
    fuerza = "Muy parejo" if m < 0.3 else "Ligera ventaja" if m < 0.7 else "Ventaja clara" if m < 1.2 else "Amplia ventaja"
    mi, mj, mp = pr["marcador"]
    chips = [f'<span class="fr-chip">Empate <b>{px:.0%}</b></span>',
             f'<span class="fr-chip">Marcador más probable <b>{mi}-{mj}</b> ({mp:.0%})</span>']

    h = _hand_espn(p)
    if h:
        ab, v = h
        pc = _p_hand(pr["m"], v, local=(ab == ab_l))
        clase = "med" if abs(pc - 0.5) < 0.05 else "ok" if pc > 0.5 else "no"
        chips.append(f'<span class="fr-chip {clase}">Hándicap {_e(ab)} {v:+g}: {"cubre" if pc > 0.5 else "no cubre"} · {max(pc, 1 - pc):.0%}</span>')
    t, de_espn = _linea_total(p, pr)
    pm, pme = _p_total(pr["m"], t)
    mas = pm >= pme
    lado = f"▲ Más +{t:g}" if mas else f"▼ Menos −{t:g}"
    ps = max(pm, pme)
    chips.append(f'<span class="fr-chip {"med" if ps < 0.55 else "ok"}">Total: <b>{lado} goles</b> · proyectado <b>{pr["total"]:.1f}</b> '
                 f'({pr["total"] - t:+.1f}) · {ps:.0%}{" · ajustado" if ps < 0.55 else ""}{"" if de_espn else " · línea estándar"}</span>')
    si = pr["btts"] >= 0.5
    chips.append(f'<span class="fr-chip {"med" if abs(pr["btts"] - 0.5) < 0.05 else "ok"}">Ambos anotan: <b>{"Sí" if si else "No"}</b> · '
                 f'{pr["btts"] if si else 1 - pr["btts"]:.0%}</span>')

    hay = pr.get("con_jugadores", False)
    lam_l, lam_v = (pr["lam_l"], pr["lam_v"]) if hay else (None, None)   # sin datos de jugadores no hay efecto que mostrar
    cls_l = " gana" if gana_l else ""
    cls_v = " gana" if gana_l is False else ""
    return (f'<div class="fr"><div class="fr-marc">'
            f'<div class="fr-eq{cls_l}"><b>{_e(ab_l)}</b><span class="fr-pts">{pr["ll"]:.1f}</span></div>'
            f'<div class="fr-mid">Pronóstico · goles esperados<strong>{centro}</strong>{fuerza}</div>'
            f'<div class="fr-eq der{cls_v}"><span class="fr-pts">{pr["lv"]:.1f}</span><b>{_e(ab_v)}</b></div></div>'
            f'<div class="fr-bar"><i style="width:{pl * 100:.1f}%"></i><i class="x" style="width:{px * 100:.1f}%"></i><i class="v" style="flex:1"></i></div>'
            f'<div class="fr-leg"><span>{_e(ab_l)} {pl:.0%}</span><span>Empate {px:.0%}</span><span>{pv:.0%} {_e(ab_v)}</span></div>'
            f'<div class="fr-chips">{"".join(chips)}</div>'
            f'<div class="fr-bajas">🩹 {_html_bajas(ab_l, pr["bajas_l"], lam_l)} &nbsp;·&nbsp; {_html_bajas(ab_v, pr["bajas_v"], lam_v)}</div>'
            f'{_html_picks(ab_l, ab_v, pr) if pr.get("con_picks") else ""}</div>')


# ---------------------------------------------------------------------------
# Botón «Analizar» y pantalla
# ---------------------------------------------------------------------------
def _a_lineas(id_local, id_visita, linea):
    """Callback de «Analizar»: deja elegidos en «Líneas» el local (A), la visita (B), el mercado Total de goles y su línea.

    Corre antes de dibujar los widgets, por eso puede fijar sus valores. Las claves son las de football_lineas.render()."""
    ss = st.session_state
    ss["f_ir_a_lineas"] = True   # football.render() cambia a la pestaña «Líneas»
    ss["fe_a"], ss["fe_b"] = id_local, id_visita
    ss["ff_grupo_mercado"] = "⚽ Goles"
    ss["ff_mercado_⚽ Goles"] = "Total de goles del partido (más/menos)"
    if linea:
        ss[f"ff_l5_total_{id_local}_{id_visita}"] = min(max(math.floor(float(linea)) + 0.5, 0.5), 99.5)


def _calcular(t, p, liga_espn, con_picks):
    """Pronóstico completo de un partido (o None si no hay datos suficientes de alguno de los equipos)."""
    base = _pronostico_base(t, p["local"]["fd"], p["visita"]["fd"])
    if not base:
        return None
    bajas, dfs = {}, {}
    for lado in ("local", "visita"):
        try:
            bajas[lado] = _bajas_espn(liga_espn, p[lado]["espn_id"])
        except Exception:  # noqa: BLE001
            bajas[lado] = None
        dfs[lado] = None
        if con_picks:
            try:
                dfs[lado] = fl._cargar_jugadores(liga_espn, p[lado]["espn_id"])[0]
            except Exception:  # noqa: BLE001
                dfs[lado] = None
    loss_l, det_l = _impacto_bajas(bajas["local"], dfs["local"])
    loss_v, det_v = _impacto_bajas(bajas["visita"], dfs["visita"])
    pr = _completar(base, loss_l, loss_v)
    pr["bajas_l"] = None if bajas["local"] is None else det_l
    pr["bajas_v"] = None if bajas["visita"] is None else det_v
    pr["con_jugadores"] = dfs["local"] is not None and dfs["visita"] is not None
    pr["con_picks"] = False
    if con_picks and pr["con_jugadores"]:
        fr_l = _factores_rival(dfs["local"], dfs["visita"])
        fr_v = _factores_rival(dfs["visita"], dfs["local"])
        pr["picks_l"], pr["notas_l"] = _picks_equipo(dfs["local"], bajas["local"], fr_l)
        pr["picks_v"], pr["notas_v"] = _picks_equipo(dfs["visita"], bajas["visita"], fr_v)
        pr["con_picks"] = True
    return pr


def _cuerpo(liga):
    st.subheader("📅 Próximos partidos")
    if liga.codigo == "INT":
        st.info("Los próximos partidos están disponibles para las ligas de clubes (no para selecciones).")
        return
    liga_espn = fl.ESPN_LIGA.get(st.session_state.get("f_liga"))
    if not liga_espn:
        st.info("Esta liga no tiene calendario en ESPN, así que no se pueden mostrar sus próximos partidos.")
        return
    cuando = st.radio("Día", ["Hoy", "Mañana"], horizontal=True, key="fut_prox_dia", label_visibility="collapsed")
    dia = _hoy() + (timedelta(days=1) if cuando == "Mañana" else timedelta(0))
    c1, c2 = st.columns(2)
    mostrar = c1.toggle("📊 Pronóstico por equipo (rendimiento reciente y bajas)", value=True, key="fut_prox_pron",
                        help="Proyecta los goles de cada equipo con sus últimos 15 partidos de liga (ataque y defensa por sede, con más peso a los "
                             "recientes) y los pasa a probabilidades de 1X2, marcador, más/menos goles y ambos anotan.")
    picks = c2.toggle("🧍 Picks de jugadores (tiros, faltas, paradas…)", value=False, key="fut_prox_picks", disabled=not mostrar,
                      help="Descarga las alineaciones de los últimos partidos de cada equipo (ESPN). La primera vez tarda; después queda guardado "
                           "una hora. También permite descontar lo que aportaban los jugadores ausentes.")

    try:
        crudo = _calendario(liga_espn, tuple(f"{dia + timedelta(days=k):%Y%m%d}" for k in (-1, 0, 1)))
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo leer el calendario de ESPN: {e}")
        return
    partidos = [p for p in crudo if p["estado"] == "pre" and p["fecha"]
                and pd.to_datetime(p["fecha"], utc=True).tz_convert(ZONA).date() == dia]
    if not partidos:
        st.info("No hay partidos por jugar ese día en esta liga.")
        return

    t = liga.t
    ultima = t.loc[t.Date.idxmax(), "Temporada"]
    actuales = set(t.loc[t.Temporada == ultima, "Equipo"])
    nombres = tuple(sorted(actuales if len(actuales) >= 4 else t.Equipo.unique()))
    partidos = _asignar(partidos, nombres, liga_espn)
    st.markdown(f"<style>{_css_fondos(partidos)}</style>", unsafe_allow_html=True)

    pron = {}
    if mostrar:
        with st.spinner("Calculando pronósticos…" + (" (la primera vez descarga alineaciones y tarda)" if picks else "")):
            for p in partidos:
                try:
                    pron[p["id"]] = _calcular(t, p, liga_espn, picks)
                except Exception:  # noqa: BLE001
                    pron[p["id"]] = None

    for p in sorted(partidos, key=lambda x: x["fecha"]):
        L, V = p["local"], p["visita"]
        hora = pd.to_datetime(p["fecha"], utc=True).tz_convert(ZONA).strftime("%H:%M")
        pr = pron.get(p["id"])
        with st.container(key=f"fut_prox_fila_{p['id']}"):
            a, b = st.columns([9, 1.6], vertical_alignment="center")
            a.markdown(f'<div class="fx"><span class="fx-hora">{hora}</span>{_eq_html(L, "Local", "loc")}<span class="fx-at">vs</span>'
                       f'{_eq_html(V, "Visita")}<div class="fx-lin">{_lineas_prox(p, pr)}</div></div>', unsafe_allow_html=True)
            analizable = bool(L["id"] and V["id"])
            b.button("🎯 Analizar", key=f"fut_prox_lin_{p['id']}", use_container_width=True, type="primary", disabled=not analizable,
                     on_click=_a_lineas, args=(L["id"], V["id"], _linea_total(p, pr)[0]),
                     help="Carga estos dos equipos (A = local, B = visita) y la línea de total de goles en el análisis de abajo."
                          if analizable else "Este equipo no está en los datos de la liga cargada (por ejemplo, recién ascendido).")
            if mostrar:
                st.markdown(_html_pron(p, pr) if pr else
                            '<div class="fr"><div class="fr-bajas">Sin datos suficientes para proyectar este partido '
                            '(falta historial de alguno de los equipos en la liga cargada).</div></div>', unsafe_allow_html=True)
    st.caption("Son probabilidades de un modelo con los últimos partidos de liga, no una garantía. Los lesionados vienen de ESPN "
               "(si ESPN no reporta bajas de esta liga, aparecerá «sin bajas reportadas»).")


def proximos(liga):
    """Panel «Próximos partidos» (hoy o mañana) de la liga cargada. Va en la pestaña «Líneas», antes de football_lineas.render()."""
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
    with st.container(key="fut_prox_panel"):
        try:
            _cuerpo(liga)
        except Exception as e:  # noqa: BLE001  (un fallo aquí no debe tumbar el resto de la página)
            st.error(f"No se pudieron mostrar los próximos partidos: {e}")
