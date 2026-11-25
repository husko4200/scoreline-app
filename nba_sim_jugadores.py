"""Simulación de jugadores y rotaciones para cada partido de «Próximos».

Para cada partido simula miles de veces el marcador cuarto a cuarto (con los cuartos y el pronóstico ya anclado al
mercado) y, dentro de cada simulación, reparte los minutos de cada jugador por tramos de 6 minutos: titulares
probables, rotación, banco y «partido decidido» (los titulares se sientan cuando la ventaja es grande). Con esos
minutos se simulan puntos, rebotes, asistencias, triples, robos y tapones.

Qué tiene en cuenta:
  · rendimiento por minuto de cada jugador en los últimos partidos (los más recientes pesan más);
  · quiénes abren los partidos (quinteto probable) y cuántos minutos juega cada uno;
  · bajas y dudas (según su estado): quien no juega libera minutos y tiros que absorben los compañeros;
  · lo que concede el rival, el ritmo esperado y el cansancio (los mismos factores que usan los picks);
  · los puntos de cada equipo suman el pronóstico del partido.

Se conecta desde nba_hoy.py: `plantel()` guarda los datos por jugador, `simular()` corre la simulación y `html()`
dibuja el bloque dentro de la tarjeta (el CSS está en `CSS`).
"""
import math
import zlib
from html import escape as _e

import numpy as np

from common import normalizar

N_SIM = 4000                 # partidos simulados por cruce
_DECAY = 0.92                # cada partido anterior pesa un 8 % menos que el siguiente
_MAX_JUG = 13                # jugadores que se muestran por equipo
ESTADS = ("PTS", "REB", "AST", "3PM", "STL", "BLK")
_OTRAS = ("REB", "AST", "3PM", "STL", "BLK")
ETQ = {"PTS": "PTS", "REB": "REB", "AST": "AST", "3PM": "3P", "STL": "ROB", "BLK": "TAP"}
# Dispersión extra (gamma-Poisson) de cada estadística: más alto = más parecido a Poisson puro
_K_DISP = {"REB": 60.0, "AST": 35.0, "3PM": 40.0, "STL": 25.0, "BLK": 12.0}
# Cuánto del total de equipo se conserva cuando falta un compañero (los rebotes casi no se pierden; los triples sí)
_ABSORBE = {"REB": 0.9, "AST": 0.6, "3PM": 0.5, "STL": 0.7, "BLK": 0.8}


def _hoy():
    """El módulo de Próximos (import tardío: él importa a este)."""
    import nba_hoy
    return nba_hoy


def _num(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(x) else x


# --- Datos por jugador (se guardan junto al pronóstico) ------------------------------------------------------------
def plantel(serie, team_id, cajas) -> dict:
    """{nombre normalizado: {nombre, id, n, juegos: [...]}} con lo que hizo cada jugador del equipo en la ventana.

    `serie` y `cajas` van en orden cronológico (el último es el más reciente). Un partido cuyo box score trae menos de
    5 jugadores con minutos no se cuenta. `ev` es el número de partido válido; `tit` = abrió el partido.
    """
    tid, out, validas = str(team_id), {}, 0
    for c in cajas:
        jug = [x for x in (c or {}).get("jugadores", []) if x.get("team_id") == tid and _num(x.get("MIN")) > 0]
        if len(jug) < 5:
            continue
        idx, validas = validas, validas + 1
        for x in jug:
            a = out.setdefault(normalizar(x.get("Jugador", "")),
                               {"nombre": x.get("Jugador", ""), "id": str(x.get("id") or ""), "juegos": []})
            a["juegos"].append({"ev": idx, "MIN": _num(x.get("MIN")), "PTS": _num(x.get("PTS")),
                                "REB": _num(x.get("REB")), "AST": _num(x.get("AST")), "3PM": _num(x.get("3PM")),
                                "STL": _num(x.get("STL")), "BLK": _num(x.get("BLK")), "tit": bool(x.get("Titular"))})
    for a in out.values():
        a["n"] = validas
    return out


def _resumen(a) -> dict | None:
    """Minutos, tasa por minuto y frecuencia de titular de un jugador, con los partidos recientes pesando más.

    Forma actual: los últimos 5 partidos corrigen (con tope) la tasa por minuto y los minutos; `forma` = (puntos de los
    últimos 5, puntos ponderados) cuando el jugador va claramente en alza o a la baja."""
    js, n = a.get("juegos") or [], a.get("n") or 0
    if not js or not n:
        return None
    w = np.array([_DECAY ** (n - 1 - g["ev"]) for g in js])
    mins = np.array([g["MIN"] for g in js])
    sw, wm = w.sum(), max(float((w * mins).sum()), 1e-9)
    mpg = float((w * mins).sum() / sw)
    tasa = {s: float((w * np.array([g[s] for g in js])).sum() / wm) for s in ESTADS}
    forma = None
    rec = [g for g in js if g["ev"] >= n - 5]
    if len(rec) >= 3 and sum(g["MIN"] for g in rec) > 0:
        mr = sum(g["MIN"] for g in rec)
        mpg = 0.65 * mpg + 0.35 * mr / len(rec)                      # los minutos de ahora mandan más que los de hace 3 semanas
        for s in ESTADS:
            if tasa[s] > 0:
                k, lim = (0.4, 0.12) if s in ("PTS", "REB", "AST", "3PM") else (0.2, 0.10)   # robos y tapones son muy ruidosos
                tasa[s] *= float(np.clip(1 + k * ((sum(g[s] for g in rec) / mr) / tasa[s] - 1), 1 - lim, 1 + lim))
        p5, pw = sum(g["PTS"] for g in rec) / len(rec), float((w * np.array([g["PTS"] for g in js])).sum() / sw)
        if pw >= 5 and abs(p5 - pw) >= 2 and abs(p5 / pw - 1) >= 0.15:
            forma = (p5, pw)
    return {"mpg": mpg, "id": str(a.get("id") or ""), "forma": forma,
            "tit": float((w * np.array([1.0 if g["tit"] else 0.0 for g in js])).sum() / sw),
            "pres": len(js) / n,
            "reciente": any(g["ev"] >= n - 5 for g in js),
            "tasa": tasa}


def _total_equipo(det) -> dict:
    """Promedio ponderado de lo que suma el equipo por partido en cada estadística (para no perder lo de un ausente)."""
    n = max((a.get("n") or 0 for a in det.values()), default=0)
    if not n:
        return {}
    por_ev = {s: np.zeros(n) for s in ESTADS}
    for a in det.values():
        for g in a.get("juegos") or []:
            for s in ESTADS:
                por_ev[s][g["ev"]] += g[s]
    w = np.array([_DECAY ** (n - 1 - i) for i in range(n)])
    return {s: float((w * por_ev[s]).sum() / w.sum()) for s in ESTADS}


# --- Simulación ---------------------------------------------------------------------------------------------------
def _marcadores(pr, rng, H):
    """(ventaja del local al empezar cada tramo de 6 min (N, 8), puntos del local (N,), puntos de la visita (N,))."""
    m, tot = float(pr["margen"]), float(pr["total"])
    cq = pr.get("cuartos")
    if cq:
        T, D = np.array(cq["ql"]) + np.array(cq["qv"]), np.array(cq["ql"]) - np.array(cq["qv"])
    else:
        T, D = np.full(4, tot / 4), np.full(4, m / 4)
    T = T * tot / T.sum()
    D = D + (m - D.sum()) / 4                                         # los cuartos suman el margen proyectado
    d = D[None, :] + rng.normal(0, H._SD_MARGEN / 2, (N_SIM, 4))      # margen (local − visita) de cada cuarto
    t = T[None, :] + rng.normal(0, H._SD_TOTAL / 2, (N_SIM, 4))       # puntos de cada cuarto entre ambos
    M, TOT = d.sum(axis=1), t.sum(axis=1)
    C = np.cumsum(d, axis=1)
    ini = np.concatenate([np.zeros((N_SIM, 1)), C[:, :3]], axis=1)
    lead = np.empty((N_SIM, 8))
    lead[:, 0::2], lead[:, 1::2] = ini, ini + 0.5 * d
    return lead, np.clip((TOT + M) / 2, 60, None), np.clip((TOT - M) / 2, 60, None)


def _minutos(mpg, tit, juega, ventaja, H):
    """Minutos de cada jugador en cada tramo: (N, jugadores, 8).

    Igual que la simulación de paliza, pero con el quinteto probable en vez de «26+ minutos». Los 5 en cancha suman
    30 min por tramo; si la ventaja es grande para el tiempo que queda, salen los titulares y entra el fondo del banco."""
    base = np.where(tit[:, None], H._FRAC_TIT[None, :], H._FRAC_BAN[None, :]) * mpg[:, None]          # (P, 8)
    arriba = ventaja > 0
    desp = np.where(arriba[:, None, :], np.where(mpg >= 34, -2.0, 0.0)[None, :, None], 3.0)
    g = 1 / (1 + np.exp(-(np.abs(ventaja)[:, None, :] - (H._UMBRAL_PULL[None, None, :] + desp)) / 3.0))
    f_tit = 1 - np.where(arriba[:, None, :], 0.93, 0.85) * g
    f_med = 1 - 0.55 * g
    f_fon = 1 + 2.2 * g
    f = np.where(tit[None, :, None], f_tit, np.where((mpg >= 18)[None, :, None], f_med, f_fon))
    m = base[None, :, :] * f * juega[:, :, None]
    for _ in range(4):
        m = np.minimum(m * (30.0 / np.maximum(m.sum(axis=1, keepdims=True), 1e-9)), H._MIN_TRAMO)
    return m


def _ape(nombre) -> str:
    return nombre.split()[-1] if nombre else ""


def _efecto_ausencias(det, k, ausentes, n):
    """Cómo rinde el jugador `k` (por minuto) cuando falta cada compañero ausente, con los partidos que ya jugaron juntos.

    Devuelve ({stat: factor}, motivo o None). Solo cuenta desde la primera vez que el ausente aparece en la ventana
    (así no se confunde con partidos de antes de que llegara) y exige 3+ partidos con y sin él. Se pondera por la
    probabilidad de que falte y por cuántos partidos hay sin él."""
    js = det[k]["juegos"]
    fx, mejor = {s: 1.0 for s in ESTADS}, None
    for ka, p, nom in ausentes:
        if ka == k:
            continue
        ja = (det.get(ka) or {}).get("juegos") or []
        if not ja:
            continue
        evs = {g["ev"] for g in ja}
        ini = min(evs)
        sin = {e for e in range(ini, n) if e not in evs}
        gs = [g for g in js if g["ev"] in sin]
        gc = [g for g in js if g["ev"] >= ini and g["ev"] not in sin]
        ms, mc = sum(g["MIN"] for g in gs), sum(g["MIN"] for g in gc)
        if len(gs) < 3 or len(gc) < 3 or ms <= 0 or mc <= 0:
            continue
        w = min(1.0, (len(gs) - 1) / 5)
        for s in ESTADS:
            rs, rc = sum(g[s] for g in gs) / ms, sum(g[s] for g in gc) / mc
            if rc <= 0:
                continue
            ratio = min(1.3, max(0.75, rs / rc))
            ratio = 1 + (ratio - 1) * len(gs) / (len(gs) + 6)       # pocos partidos sin él = mucho ruido: se encoge hacia 1
            fx[s] *= 1 + p * w * (0.8 if s == "PTS" else 0.5) * (ratio - 1)
            if s in ("PTS", "REB", "AST") and (mejor is None or p * w * abs(ratio - 1) > mejor[0]):
                mejor = (p * w * abs(ratio - 1), s, ratio, nom, len(gs))
    fx = {s: float(np.clip(v, 0.85, 1.2)) for s, v in fx.items()}
    if mejor and mejor[0] >= 0.04:
        _, s, ratio, nom, ng = mejor
        return fx, f"sin {_ape(nom)}: {ratio - 1:+.0%} {ETQ[s]} por minuto (comprobado en {ng} partidos sin él)".replace("-", "−")
    return fx, None


def _factor_reb_rival(det_r, bajas_r, H):
    """(factor de rebotes, nota): si al rival le faltan rebotedores, los jugadores de este equipo cogen algo más."""
    tot = _total_equipo(det_r).get("REB", 0.0)
    if tot <= 0:
        return 1.0, None
    perdido, quien = 0.0, []
    for k, p in H._prob_no_juega(bajas_r).items():
        a = det_r.get(k)
        r = _resumen(a) if a else None
        if not r or p < 0.3:
            continue
        v = p * r["pres"] * sum(g["REB"] for g in a["juegos"]) / len(a["juegos"])
        perdido += v
        quien.append((v, a["nombre"]))
    f = 1 + min(0.06, 0.35 * perdido / tot)
    if f - 1 < 0.01:
        return 1.0, None
    return f, f"rival sin {_ape(max(quien)[1])}: se espera +{f - 1:.0%} de rebotes para este equipo"


def _confirmados(evento) -> set:
    """Ids de los titulares si ESPN ya publicó el quinteto de este partido; vacío si todavía no."""
    if not evento:
        return set()
    try:
        import nba_jugadores
        return set(nba_jugadores._titulares_confirmados(str(evento)) or [])
    except Exception:  # noqa: BLE001
        return set()


def _equipo(det, bajas, fr, f_rit, f_fat, ventaja, pts_eq, rng, H, picks=None, conf=None, riv=None, objetivo_pts=None):
    """Simula a un equipo: filas por jugador, totales, quinteto, bajas y líderes. None si faltan datos.

    picks = picks de jugadores de este equipo (se compara cada uno con la simulación) · conf = ids de titulares
    confirmados por ESPN · riv = (plantel del rival, bajas del rival)."""
    p_no = H._prob_no_juega(bajas)
    n_ev = max((a.get("n") or 0 for a in det.values()), default=0)
    info, fuera, ausentes = {}, [], []
    for k, a in det.items():
        r = _resumen(a)
        if not r:
            continue
        pn = p_no.get(k, 0.0)
        if pn >= 0.3 and r["mpg"] >= 15:
            ausentes.append((k, pn, a["nombre"]))
        if pn >= 0.999:
            if r["mpg"] >= 8:                        # baja confirmada con peso en la rotación (aunque lleve semanas fuera)
                est = next((str(b.get("Estado") or "") for b in bajas or []
                            if normalizar(str(b.get("Jugador", ""))) == k), "")
                fuera.append((a["nombre"], est, r["mpg"]))
            continue
        # entra quien jugó hace poco, o quien es duda y suele jugar; el que se fue del equipo no aparece
        if not (r["reciente"] or (pn > 0 and r["pres"] >= 0.3)) or r["mpg"] < 3:
            continue
        info[k] = {**r, "nombre": a["nombre"], "p_no": pn}
    if len(info) < 8:
        return None
    # rival sin rebotedores → algo más de rebotes aquí
    nota_riv = None
    if riv and riv[0]:
        f_rr, nota_riv = _factor_reb_rival(riv[0], riv[1], H)
        fr = {**fr, "REB": fr.get("REB", 1.0) * f_rr}
    # quinteto: el confirmado por ESPN si ya está publicado; si no, quienes más abren los partidos
    ini_c = [k for k in info if conf and info[k]["id"] in conf]
    confirmado = len(ini_c) == 5
    ks = sorted(info, key=lambda x: -info[x]["mpg"])[:_MAX_JUG]
    if confirmado:
        ks += [k for k in ini_c if k not in ks]
        ini = ini_c
    else:
        disp_ini = [k for k in ks if info[k]["p_no"] < 0.5]
        ini = sorted((k for k in disp_ini if info[k]["tit"] >= 0.5), key=lambda x: (-info[x]["tit"], -info[x]["mpg"]))[:5]
        if len(ini) < 5:                               # faltan titulares claros: completa con quienes más juegan
            ini += [k for k in sorted(disp_ini, key=lambda x: -info[x]["mpg"]) if k not in ini][:5 - len(ini)]
    # efecto comprobado de las ausencias de compañeros sobre el rendimiento por minuto de cada uno
    for k in ks:
        info[k]["fx"], info[k]["why_aus"] = _efecto_ausencias(det, k, ausentes, n_ev) if ausentes else ({}, None)
    P, n = len(ks), N_SIM
    mpg = np.array([info[k]["mpg"] for k in ks])
    tit = np.array([k in ini for k in ks])
    pno = np.array([info[k]["p_no"] for k in ks])
    juega = (rng.random((n, P)) >= pno[None, :]).astype(float)
    mins = _minutos(mpg, tit, juega, ventaja, H)       # (n, P, 8)
    tot = mins.sum(axis=2)                             # (n, P)

    def tasa_de(s):
        return np.array([info[k]["tasa"][s] * info[k]["fx"].get(s, 1.0) for k in ks])

    # puntos: el pronóstico del equipo se reparte según ritmo de anotación × minutos (el que tiene la noche buena, más)
    w = tasa_de("PTS")[None, :] * tot * rng.lognormal(-0.045, 0.30, (n, P))
    est = {"PTS": pts_eq[:, None] * w / np.maximum(w.sum(axis=1, keepdims=True), 1e-9)}
    # el resto: tasa por minuto × minutos × rival × ritmo × cansancio, ajustado al total habitual del equipo
    objetivo = _total_equipo(det)
    juego_rel = np.clip(pts_eq / pts_eq.mean(), 0.8, 1.2)[:, None]       # más puntos del equipo → más asistencias y triples
    for s in _OTRAS:
        f = fr.get(s, 1.0) * f_rit * f_fat
        lam = tasa_de(s)[None, :] * tot * f * (juego_rel ** 0.9 if s in ("AST", "3PM") else 1.0)
        base = float(lam.sum(axis=1).mean())
        meta = objetivo.get(s, 0.0) * f
        if base > 0 and meta > 0:
            a = _ABSORBE[s]
            lam = lam * float(np.clip((1 - a) + a * meta / base, 0.8, 1.25))
        lam = lam * rng.gamma(_K_DISP[s], 1 / _K_DISP[s], (n, P))
        est[s] = rng.poisson(lam).astype(float)

    # Partido «típico»: la simulación cuyas cifras se parecen más a lo esperado de todos los jugadores a la vez.
    # Así cada número es un resultado entero y posible (no un promedio con decimales) y el equipo suma bien.
    base_j = juega * (pno < 0.5)[None, :]                       # (n, P) solo cuentan los que se espera que jueguen
    mask = (juega == (pno < 0.5)[None, :].astype(float)).all(axis=1)
    cnt = np.maximum(base_j.sum(axis=0), 1.0)
    dist = np.zeros(n)
    for s_ in ESTADS + ("MIN",):
        x = tot if s_ == "MIN" else est[s_]
        mu_ = (x * base_j).sum(axis=0) / cnt
        sd_ = np.sqrt((((x - mu_) ** 2) * base_j).sum(axis=0) / cnt)
        dist += (((x - mu_) / (sd_ + 0.75)) ** 2 * base_j).sum(axis=1)
    meta_pts = int(round(objetivo_pts if objetivo_pts is not None else float(pts_eq.mean())))
    dist += P * ((pts_eq - meta_pts) / (float(pts_eq.std()) + 1.0)) ** 2     # que el marcador del equipo ya sea parecido
    dist = np.where(mask, dist, np.inf) if mask.any() else dist
    r = int(np.argmin(dist))
    # puntos enteros: reparte EXACTAMENTE el marcador pronosticado entre los jugadores que se muestran
    vis = (juega[:, :].sum(axis=0) >= 30) & (juega[r] > 0)
    pr_ = np.where(vis, est["PTS"][r], 0.0)
    cuota = pr_ / max(float(pr_.sum()), 1e-9) * meta_pts
    pts_int = np.floor(cuota)
    for j_ in np.argsort(-(cuota - pts_int))[:meta_pts - int(pts_int.sum())]:
        pts_int[j_] += 1

    # minutos enteros: cada cuarto suma exactamente 60 (5 jugadores × 12 min) y el partido 240
    Qm = mins[r].reshape(P, 4, 2).sum(axis=2) * vis[:, None]
    Qint = np.zeros((P, 4), dtype=int)
    for c_ in range(4):
        cu = Qm[:, c_] / max(float(Qm[:, c_].sum()), 1e-9) * 60.0
        fl = np.floor(cu)
        for j_ in np.argsort(-(cu - fl))[:60 - int(fl.sum())]:
            fl[j_] += 1
        Qint[:, c_] = fl.astype(int)

    picks_k = {}
    for c in picks or []:
        picks_k.setdefault(c.get("k"), []).append(c)
    filas = []
    for i, k in enumerate(ks):
        disp = juega[:, i] > 0
        if disp.sum() < 30:
            continue
        mi = mins[disp, i, :]
        q = mi.reshape(-1, 4, 2).sum(axis=2).mean(axis=0)
        mu_min = float(tot[disp, i].mean())
        pts, reb, ast = np.round(est["PTS"][disp, i]), est["REB"][disp, i], est["AST"][disp, i]
        dd = float((((pts >= 10).astype(int) + (reb >= 10) + (ast >= 10)) >= 2).mean())
        qi = Qint[i]                                                            # minutos enteros por cuarto
        stats = {}
        for s in ESTADS:
            v = int(pts_int[i]) if s == "PTS" else int(round(float(est[s][r, i])))
            if juega[r, i] == 0:
                v = 0
            lo_, hi_ = float(np.percentile(est[s][disp, i], 10)), float(np.percentile(est[s][disp, i], 90))
            stats[s] = (v, min(lo_, v), max(hi_, v))
        if k in ini:
            rol = "Titular"
        elif mu_min >= 18:
            rol = "Rotación"
        elif mu_min >= 9:
            rol = "Banco"
        else:
            rol = "Fondo"
        pj = 1 - info[k]["p_no"]
        pk = [{"stat": c["stat"], "linea": c["linea"], "conf": c["conf"],
               "p": float((est[c["stat"]][disp, i] > c["linea"]).mean()) * pj} for c in picks_k.get(k, [])]
        fm = info[k]["forma"]
        why = [x for x in (info[k]["why_aus"],
                           f"va {'en alza' if fm[0] > fm[1] else 'a la baja'}: {fm[0]:.1f} pts en sus últimos 5 "
                           f"(promedio {fm[1]:.1f})" if fm else None) if x]
        filas.append({"nombre": info[k]["nombre"], "k": k, "tit": k in ini, "rol": rol, "p_juega": pj,
                      "min": mu_min, "min_t": int(qi.sum()), "q": [int(x) for x in qi], "est": stats, "dd": dd, "picks": pk, "why": why,
                      "forma": None if not fm else ("alza" if fm[0] > fm[1] else "baja")})
    if len(filas) < 8:
        return None
    filas.sort(key=lambda f: (not f["tit"], -f["min"]))
    activos = [f for f in filas if f["p_juega"] >= 0.5]
    lid = {s: max(activos, key=lambda f: f["est"][s][0]) for s in ESTADS} if activos else {}
    return {"filas": filas, "ini": [info[k]["nombre"] for k in ini], "confirmado": confirmado, "nota_riv": nota_riv,
            "tot": {**{s: float(sum(f["est"][s][0] for f in filas)) for s in ESTADS},
                    "MIN": float(sum(f["min_t"] for f in filas))},
            "rot": sum(1 for f in activos if f["min"] >= 10),
            "fuera": sorted(fuera, key=lambda x: -x[2])[:4],
            "lid": {s: (f["nombre"], f["est"][s][0]) for s, f in lid.items()}}


def simular(pr, rl, rv, semilla="", evento=None) -> dict | None:
    """Simulación de jugadores del partido; `pr` es el pronóstico ya anclado al mercado. None si faltan datos.

    `evento` = id del partido en ESPN (sirve para leer el quinteto confirmado cuando ya está publicado)."""
    sl, sv = pr.get("sj_l"), pr.get("sj_v")
    if not sl or not sv:
        return None
    H = _hoy()
    rng = np.random.default_rng(zlib.crc32(f"sj|{rl}|{rv}|{semilla}".encode()))
    lead, pts_l, pts_v = _marcadores(pr, rng, H)
    rit = pr.get("ritmo") or {}
    conf = _confirmados(evento)
    eq_l = _equipo(sl, pr.get("raw_bajas_l"), pr.get("fr_l") or {}, rit.get("f_l", 1.0), pr.get("ff_l", 1.0),
                   lead, pts_l, rng, H, pr.get("picks_l"), conf, (sv, pr.get("raw_bajas_v")), pr.get("pts_l"))
    eq_v = _equipo(sv, pr.get("raw_bajas_v"), pr.get("fr_v") or {}, rit.get("f_v", 1.0), pr.get("ff_v", 1.0),
                   -lead, pts_v, rng, H, pr.get("picks_v"), conf, (sl, pr.get("raw_bajas_l")), pr.get("pts_v"))
    if not eq_l or not eq_v:
        return None
    eq_l["pts"], eq_v["pts"] = eq_l["tot"]["PTS"], eq_v["tot"]["PTS"]
    return {"equipos": {rl: eq_l, rv: eq_v}, "n": N_SIM}


# --- Dibujo -------------------------------------------------------------------------------------------------------
def _celda(e, top, linea=None) -> str:
    mu, lo, hi = e
    rango = f"{lo:.0f}–{hi:.0f}" if round(lo) != round(hi) else f"{lo:.0f}"
    ln = f'<i class="sj-ln">línea {linea:.1f}</i>' if linea is not None else ""
    return f'<td class="sj-v{" top" if top else ""}{" pk" if linea is not None else ""}"><b>{mu:.0f}</b><small>{rango}</small>{ln}</td>'


def _celda_q(m) -> str:
    a = min(m / 12.0, 1.0) * 0.5 + 0.04            # más minutos en el cuarto, más intenso
    return f'<td class="sj-qc"><span style="background:rgba(79,70,229,{a:.2f})">{m:.0f}</span></td>'


def _fila(f, fotos, tops, H) -> str:
    cara = H._cara(f["nombre"], fotos.get(f["k"]))
    pill = f'<span class="sj-r {f["rol"][:3].lower()}">{f["rol"]}</span>'
    forma = ""
    if f.get("forma"):
        forma = ('<span class="sj-r alza">▲ en alza</span>' if f["forma"] == "alza" else '<span class="sj-r baja">▼ a la baja</span>')
    duda = (f'<span class="sj-r duda" title="Probabilidad de jugar según su estado">⚠ juega {f["p_juega"]:.0%}</span>'
            if f["p_juega"] < 0.995 else "")
    dd = f'<span class="sj-r dd" title="Probabilidad de doble-doble">DD {f["dd"]:.0%}</span>' if f["dd"] >= 0.25 else ""
    pks = ""
    for c in f.get("picks") or []:
        cl = "ok" if c["p"] >= c["conf"] - 0.07 else "med" if c["p"] >= c["conf"] - 0.15 else "no"
        pks += (f'<span class="sj-pk {cl}" title="Pick: {c["conf"]:.0%} · simulación: {c["p"]:.0%}">🎯 Más de {c["linea"]:.1f} '
                f'{ETQ[c["stat"]]} · sim {c["p"]:.0%} <em>(pick {c["conf"]:.0%})</em></span>')
    lineas = {c["stat"]: c["linea"] for c in f.get("picks") or []}
    why = "".join(f'<span class="sj-why">{_e(x)}</span>' for x in f.get("why") or [])
    celdas = "".join(_celda(f["est"][s], tops.get(s) == f["nombre"], lineas.get(s)) for s in ESTADS)
    return (f'<tr class="{"tit" if f["tit"] else "ban"}"><td class="n"><div class="sj-j">{cara}'
            f'<span class="sj-nm"><b>{_e(f["nombre"])}</b><span class="sj-tags">{pill}{forma}{duda}{dd}</span>{pks}{why}</span></div></td>'
            f'<td class="sj-m"><b>{f["min_t"]}</b><div class="sj-bar"><i style="width:{min(f["min_t"] / 40, 1) * 100:.0f}%"></i></div></td>'
            f'{celdas}{"".join(_celda_q(x) for x in f["q"])}</tr>')


def _bloque_equipo(ab, eq, tid, logos, H) -> str:
    try:
        fotos = H._fotos_plantel(tid) if tid else {}
    except Exception:  # noqa: BLE001
        fotos = {}
    color = H._colores_equipo({"abrev": ab, "nombre": ab})[0]
    tops = {s: v[0] for s, v in eq["lid"].items()}
    ini = ", ".join(_e(x.split()[-1]) for x in eq["ini"])
    tot = eq["tot"]
    chips_tot = "".join(f'<span class="sj-ct"><small>{ETQ[s]}</small><b>{tot[s]:.0f}</b></span>' for s in ESTADS[1:])
    lid = "".join(f'<span class="sj-ld"><small>{ETQ[s]}</small>{_e(nom.split()[-1])} <b>{v:.0f}</b></span>'
                  for s, (nom, v) in eq["lid"].items())
    esc = H._escudo_hist(ab, tid, logos) if logos else ""
    filas, sep = [], None
    for f in eq["filas"]:
        grupo = "Titulares" + (" (confirmados por ESPN)" if eq.get("confirmado") else " (quinteto probable)") if f["tit"] else "Banco y rotación"
        if grupo != sep:
            filas.append(f'<tr class="sep"><td colspan="12">{grupo}</td></tr>')
            sep = grupo
        filas.append(_fila(f, fotos, tops, H))
    pie = "".join(f'<td class="sj-v"><b>{tot[s]:.0f}</b></td>' if s != "PTS" else f'<td class="sj-v"><b>{eq["pts"]:.0f}</b></td>'
                  for s in ESTADS)
    avisos = ""
    if eq["fuera"]:
        avisos += ('<div class="sj-fu"><b>Fuera:</b> ' + " · ".join(
            f'{_e(n)}{f" <em>({_e(e)})</em>" if e else ""}' for n, e, _ in eq["fuera"]) +
            ' — sus minutos y tiros ya se repartieron entre los que juegan.</div>')
    if eq.get("nota_riv"):
        avisos += f'<div class="sj-fu sj-ok">{_e(eq["nota_riv"])}</div>'
    return (f'<div class="sj-eq" style="--c:{color}"><div class="sj-h">{esc}<div class="sj-ht"><b>{_e(ab)}</b>'
            f'<span>{"Quinteto confirmado" if eq.get("confirmado") else "Quinteto probable"}: {ini}</span>'
            f'<span>Rotación de {eq["rot"]} jugadores (10+ min)</span></div>'
            f'<div class="sj-tt">{chips_tot}</div></div><div class="sj-lds">{lid}</div>{avisos}'
            f'<div class="sj-w"><table class="sj-t"><thead><tr><th rowspan="2" class="n">Jugador</th><th rowspan="2">MIN</th>'
            + "".join(f'<th rowspan="2">{ETQ[s]}</th>' for s in ESTADS) +
            '<th colspan="4" class="g">Rotación · min por cuarto</th></tr><tr><th class="g">1.º</th><th class="g">2.º</th>'
            '<th class="g">3.º</th><th class="g">4.º</th></tr></thead><tbody>' + "".join(filas) +
            f'<tr class="tot"><td class="n">Total proyectado del equipo</td><td class="sj-m"><b>{tot["MIN"]:.0f}</b></td>{pie}'
            '<td colspan="4"></td></tr></tbody></table></div></div>')


def html(rl, rv, pr, ids=None, logos=None, abierto=True) -> str:
    """Bloque «Simulación de jugadores y rotaciones» de la tarjeta; '' si no hay simulación."""
    sim = pr.get("sim_jug")
    if not sim:
        return ""
    H = _hoy()
    ids, logos = ids or {}, logos or {}
    cuerpo = "".join(_bloque_equipo(ab, sim["equipos"][ab], ids.get(ab), logos, H) for ab in (rl, rv) if ab in sim["equipos"])
    nota = (f'Simulación de {sim["n"]:,} partidos. Cada cifra es el resultado de un partido típico simulado (el que más se parece a lo esperado de todos), '
            f'en números enteros; debajo, el rango central (80 % de los casos). Parte de su rendimiento por minuto y sus minutos recientes (los últimos 5 partidos '
            f'corrigen la media), del quinteto (confirmado por ESPN cuando ya se publicó), de las bajas según su estado (con lo que '
            f'cada compañero rindió de verdad sin ellos), del rival (defensa y lesionados), el ritmo y el cansancio, y de que una '
            f'ventaja grande manda a los titulares al banco. Los puntos suman el pronóstico de cada equipo. 🎯 = tu pick: la '
            f'simulación recalcula su probabilidad y la compara con la del pick. ROB = robos, TAP = tapones, DD = doble-doble. '
            f'Es una estimación, no una certeza.')
    return (f'<details class="sj"{" open" if abierto else ""}><summary><span>🎲 Simulación de jugadores y rotaciones</span>'
            f'<em>{sim["n"]:,} simulaciones</em></summary><div class="sj-body">{cuerpo}<div class="sj-f">{nota}</div></div></details>')


CSS = """
.sj{margin-top:14px;border-radius:16px;background:#eaeff6;border:1px solid #d3dbe8}
.sj>summary{display:flex;align-items:center;justify-content:space-between;gap:10px;cursor:pointer;list-style:none;padding:11px 14px;
  font-size:.7rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#1e293b}
.sj>summary::-webkit-details-marker{display:none}
.sj>summary em{margin-left:auto;font-style:normal;font-weight:600;letter-spacing:.02em;text-transform:none;color:#64748b;font-size:.68rem}
.sj>summary::after{content:'▾';color:#64748b;font-size:.8rem;transition:transform .2s}
.sj[open]>summary::after{transform:rotate(180deg)}
.sj-body{display:flex;flex-direction:column;gap:12px;padding:0 14px 14px}
.sj-eq{background:#fff;border:1px solid #cbd5e1;border-top:3px solid var(--c,#6366f1);border-radius:12px;overflow:hidden;
  box-shadow:0 1px 2px rgba(15,23,42,.06),0 6px 14px -8px rgba(15,23,42,.22)}
.sj-h{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:11px 14px 8px}
.sj-ht{display:flex;flex-direction:column;line-height:1.3;min-width:0}
.sj-ht b{font-size:1rem;font-weight:800;letter-spacing:.04em;color:#0f172a}
.sj-ht span{font-size:.7rem;color:#64748b}
.sj-tt{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}
.sj-ct{display:flex;flex-direction:column;align-items:center;min-width:44px;padding:3px 8px;border-radius:10px;background:#f1f5f9;border:1px solid #e2e8f0}
.sj-ct small{font-size:.54rem;font-weight:800;letter-spacing:.08em;color:#64748b}
.sj-ct b{font-size:.84rem;color:#0f172a;font-variant-numeric:tabular-nums}
.sj-lds{display:flex;flex-wrap:wrap;gap:6px;padding:0 14px 10px}
.sj-ld{display:inline-flex;align-items:center;gap:5px;padding:2px 10px 2px 3px;border-radius:99px;font-size:.68rem;color:#334155;background:#eef2ff;border:1px solid #c7d2fe}
.sj-ld small{padding:1px 6px;border-radius:99px;background:#4f46e5;color:#fff;font-size:.54rem;font-weight:800;letter-spacing:.06em}
.sj-ld b{color:#3730a3;font-variant-numeric:tabular-nums}
.sj-fu{margin:0 14px 10px;padding:5px 10px;border-radius:10px;font-size:.7rem;line-height:1.45;color:#991b1b;background:#fef2f2;border:1px solid #fecaca}
.sj-fu em{font-style:normal;opacity:.8}
.sj-w{overflow-x:auto;border-top:1px solid #e2e8f0}
.sj-t{width:100%;min-width:760px;border-collapse:collapse;font-size:.74rem;font-variant-numeric:tabular-nums;color:#334155}
.sj-t th{padding:7px 6px;background:#f1f5f9;border-bottom:1px solid #cbd5e1;font-size:.6rem;font-weight:800;letter-spacing:.07em;
  text-transform:uppercase;color:#475569;text-align:center;white-space:nowrap}
.sj-t th.n,.sj-t td.n{text-align:left;padding-left:14px}
.sj-t th.g{background:#e0e7ff;color:#3730a3;border-bottom:1px solid #c7d2fe}
.sj-t td{padding:6px;border-top:1px solid #eef2f7;text-align:center;vertical-align:middle}
.sj-t tr.ban td{background:#fbfcfe}
.sj-t tr.sep td{padding:4px 14px;background:#f8fafc;border-top:1px solid #e2e8f0;font-size:.58rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#94a3b8;text-align:left}
.sj-t tr.tot td{background:#f1f5f9;border-top:2px solid #cbd5e1;font-weight:700}
.sj-t tr.tot td.n{font-size:.66rem;letter-spacing:.04em;text-transform:uppercase;color:#475569}
.sj-j{display:flex;align-items:center;gap:9px;min-width:0}
.sj-nm{display:flex;flex-direction:column;gap:2px;min-width:0}
.sj-nm b{font-size:.78rem;color:#0f172a;white-space:nowrap}
.sj-tags{display:flex;flex-wrap:wrap;gap:4px}
.sj-r{padding:0 7px;border-radius:99px;font-size:.58rem;font-weight:700;letter-spacing:.03em;border:1px solid #cbd5e1;background:#f1f5f9;color:#475569;white-space:nowrap}
.sj-r.tit{background:#e0e7ff;border-color:#c7d2fe;color:#3730a3}
.sj-r.rot{background:#ecfdf5;border-color:#a7f3d0;color:#047857}
.sj-r.duda{background:#fffbeb;border-color:#fde68a;color:#b45309}
.sj-r.dd{background:#fdf4ff;border-color:#f0abfc;color:#a21caf}
.sj-m b{font-size:.84rem;color:#0f172a}
.sj-bar{height:4px;margin:3px auto 0;width:44px;border-radius:99px;background:#e2e8f0;overflow:hidden}
.sj-bar i{display:block;height:100%;background:linear-gradient(90deg,#6366f1,#818cf8)}
.sj-v b{display:block;font-size:.86rem;color:#0f172a}
.sj-v small{display:block;font-size:.58rem;color:#94a3b8}
.sj-t td.sj-v.top{background:#eef2ff}.sj-t td.sj-v.top b{color:#3730a3}
.sj-qc span{display:inline-block;min-width:28px;padding:3px 0;border-radius:6px;font-size:.68rem;font-weight:700;color:#1e1b4b}
.sj-r.alza{background:#ecfdf5;border-color:#a7f3d0;color:#047857}
.sj-r.baja{background:#fef2f2;border-color:#fecaca;color:#b91c1c}
.sj-pk{align-self:flex-start;padding:1px 8px;border-radius:8px;font-size:.62rem;font-weight:700;border:1px solid #cbd5e1;background:#f8fafc;color:#334155;white-space:nowrap}
.sj-pk em{font-style:normal;font-weight:600;opacity:.75}
.sj-pk.ok{background:#ecfdf5;border-color:#86efac;color:#047857}
.sj-pk.med{background:#fffbeb;border-color:#fde68a;color:#b45309}
.sj-pk.no{background:#fef2f2;border-color:#fca5a5;color:#b91c1c}
.sj-why{font-size:.6rem;line-height:1.3;color:#64748b;font-style:italic}
.sj-fu.sj-ok{color:#1e3a8a;background:#eff6ff;border-color:#bfdbfe}
.sj-t td.sj-v.pk{box-shadow:inset 0 0 0 2px #fbbf24;background:#fffbeb}
.sj-ln{display:block;font-style:normal;font-size:.54rem;font-weight:800;color:#b45309}
.sj-f{font-size:.66rem;line-height:1.5;color:#64748b}
"""
