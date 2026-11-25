"""Análisis profundo de un partido: forma actual, jugadores en foco, bajas con su impacto, regresos de lesión y emparejamientos.

Funciones puras: reciben datos ya cargados (series de partidos y box scores de `nba_hoy`) y devuelven diccionarios simples
(serializables, aptos para `st.cache_data`). No hay Streamlit, HTML ni red aquí, así que se prueban con datos sintéticos
(ver test_nba_profundo.py).

Qué NO hace, a propósito: ESPN no publica quién defiende a quién. Los emparejamientos se arman por posición y altura del
quinteto probable, y se rotulan como orientativos. Cada cifra sale de box scores reales; si no hay muestra suficiente, el dato
se omite (None) en vez de rellenarse.

Formato de entrada
  serie   lista (más antiguo → más reciente) de {pf, pc, sede, ...}; cajas = lista paralela de box scores (o None).
  caja    {"jugadores": [{team_id, id, Jugador, Titular, MIN, PTS, REB, AST, FGA, FTA, ...}]}
  bajas   lista de {Jugador, Estado, [Lesión], [Regreso estimado]} (o None si ESPN no respondió).
  posiciones  {id de jugador: {"pos": "PG", "alt": 188}} (puede faltar: entonces no hay emparejamientos).
"""
from __future__ import annotations

import unicodedata

# --- Umbrales (un solo lugar para ajustarlos) -------------------------------------------------------------------
MIN_JUEGOS = 5            # partidos con box score completo para analizar a un equipo
MIN_ROTACION = 12.0       # minutos por partido desde los que alguien cuenta como de rotación
MIN_FOCO = 18.0           # minutos por partido para entrar en «jugadores en foco»
VENTANA_FORMA = 5         # «últimos N» frente a toda la ventana
UMBRAL_TENDENCIA = 3.0    # puntos de diferencial por partido para hablar de alza o baja
UMBRAL_CALIENTE = 3.0     # puntos por partido sobre su promedio (y al menos un 20 %) para «caliente» / «frío»
MIN_AUSENCIA_REGRESO = 3  # partidos seguidos fuera para que su vuelta se considere un regreso
MAX_PARTIDOS_REGRESO = 5  # un regreso es «reciente» si volvió hace tantos partidos o menos
FRAC_MINUTOS_LIMITADOS = 0.80
MIN_MUESTRA = 2           # partidos mínimos con y sin un jugador para MOSTRAR la comparación del equipo
MIN_MUESTRA_VEREDICTO = 3 # partidos sin el jugador para sacar una conclusión (y para decir quién absorbe su juego)
COBERTURA_POSICIONES = 0.85   # fracción de los puntos rivales cuya posición debe conocerse para publicar «concede por posición»

_GRUPO = {"PG": "Guardias", "SG": "Guardias", "G": "Guardias", "SF": "Aleros", "GF": "Aleros", "F": "Aleros",
          "PF": "Interiores", "FC": "Interiores", "C": "Interiores"}
_RANGO = {"PG": 1.0, "G": 1.5, "SG": 2.0, "GF": 2.5, "SF": 3.0, "F": 3.5, "PF": 4.0, "FC": 4.5, "C": 5.0}
_ORDEN_ESTADO = (("out", 0), ("doubtful", 1), ("questionable", 2), ("day-to-day", 3), ("probable", 4))


# --- Utilidades --------------------------------------------------------------------------------------------------
def norm(texto) -> str:
    """Nombre en minúsculas, sin tildes ni puntuación: clave estable para cruzar box scores con la lista de lesiones."""
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    for c in ".'-":
        s = s.replace(c, " " if c == "-" else "")
    return " ".join(s.split())


def _v(x) -> float:
    """Número seguro: None, texto o NaN valen 0."""
    return float(x) if isinstance(x, (int, float)) and x == x else 0.0


def _prom(valores):
    valores = list(valores)
    return sum(valores) / len(valores) if valores else None


def _ts(filas):
    """True shooting % (0-1) de un conjunto de filas de box score; None si no tiró."""
    filas = list(filas)
    pts = sum(_v(f.get("PTS")) for f in filas)
    den = 2 * (sum(_v(f.get("FGA")) for f in filas) + 0.44 * sum(_v(f.get("FTA")) for f in filas))
    return pts / den if den > 0 else None


def _nivel_estado(estado) -> int:
    e = str(estado or "").lower()
    return next((n for k, n in _ORDEN_ESTADO if k in e), 5)


def _bloque(juegos):
    """Récord y diferencial de puntos de una lista de partidos {pf, pc}; None si no hay ninguno con marcador."""
    v = [g for g in juegos if g.get("pf") is not None and g.get("pc") is not None]
    if not v:
        return None
    ganados = sum(1 for g in v if g["pf"] > g["pc"])
    # eficiencia por 100 posesiones: solo si TODOS los partidos la traen (mezclar con y sin dato sesgaría el promedio)
    eff = all(g.get("ortg") is not None and g.get("drtg") is not None for g in v)
    return {"g": ganados, "p": len(v) - ganados, "n": len(v), "dif": sum(g["pf"] - g["pc"] for g in v) / len(v),
            "pf": sum(g["pf"] for g in v) / len(v), "pc": sum(g["pc"] for g in v) / len(v),
            "ortg": sum(g["ortg"] for g in v) / len(v) if eff else None, "drtg": sum(g["drtg"] for g in v) / len(v) if eff else None}


# --- Datos por partido y por jugador -----------------------------------------------------------------------------
def partidos_jugados(serie, cajas, tid):
    """Partidos con box score completo del equipo, del más antiguo al más reciente.

    Cada uno: {pf, pc, jug: {clave: fila}} con quienes jugaron (MIN > 0). Un box score con menos de 5 jugadores se descarta:
    contarlo haría parecer que medio plantel «faltó»."""
    out = []
    for g, c in zip(serie, cajas):
        filas = [x for x in ((c or {}).get("jugadores") or []) if str(x.get("team_id")) == str(tid) and _v(x.get("MIN")) > 0]
        if len(filas) >= 5:
            out.append({"pf": g.get("pf"), "pc": g.get("pc"), "jug": {norm(x.get("Jugador")): x for x in filas}})
    return out


def fichas(vg):
    """{clave: ficha} con lo que hizo cada jugador en la ventana y en los últimos 5 partidos."""
    n = len(vg)
    acum = {}
    for i, p in enumerate(vg):
        for k, x in p["jug"].items():
            acum.setdefault(k, {})[i] = x
    out = {}
    for k, filas in acum.items():
        idx = sorted(filas)
        u5 = [i for i in idx if i >= n - 5]
        x0 = filas[idx[-1]]
        out[k] = {
            "nombre": x0.get("Jugador", "?"), "id": str(x0.get("id", "")), "gp": len(idx), "pres": len(idx) / n, "idx": idx, "filas": filas,
            "mpg": _prom(_v(filas[i].get("MIN")) for i in idx), "ppg": _prom(_v(filas[i].get("PTS")) for i in idx),
            "g5": len(u5), "mpg5": _prom(_v(filas[i].get("MIN")) for i in u5), "ppg5": _prom(_v(filas[i].get("PTS")) for i in u5),
            "ts": _ts(filas[i] for i in idx), "ts5": _ts(filas[i] for i in u5),
            "tit5": sum(1 for i in u5 if filas[i].get("Titular")),
            "ult": [(_v(filas[i].get("PTS")), _v(filas[i].get("MIN"))) for i in u5],
        }
    return out


def _presencia(ficha, n):
    s = set(ficha["idx"])
    return [i in s for i in range(n)]


def _fuera_actual(pres) -> int:
    """Partidos seguidos sin jugar hasta hoy."""
    a = 0
    while a < len(pres) and not pres[len(pres) - 1 - a]:
        a += 1
    return a


def _ultimo_regreso(pres):
    """(partidos jugados desde que volvió, partidos seguidos que se perdió antes, ¿la ausencia empieza antes de la ventana?) o None."""
    n = len(pres)
    m = 0
    while m < n and pres[n - 1 - m]:
        m += 1
    if m == 0 or m == n:
        return None
    k = 0
    while m + k < n and not pres[n - 1 - m - k]:
        k += 1
    return m, k, (m + k == n)


# --- Bloques de análisis -----------------------------------------------------------------------------------------
def forma(serie, es_local):
    """Récord y diferencial de los últimos 5 y de toda la ventana, racha, tendencia y rendimiento en la sede de hoy."""
    if len(serie) < MIN_JUEGOS:
        return None
    reciente, total = _bloque(serie[-VENTANA_FORMA:]), _bloque(serie)
    if not reciente or not total:
        return None
    racha, tipo = 0, None
    for g in reversed(serie):
        if g.get("pf") is None or g.get("pc") is None:
            break
        gano = g["pf"] > g["pc"]
        if tipo is None:
            tipo = gano
        if gano != tipo:
            break
        racha += 1
    sede = _bloque([g for g in serie if (g.get("sede") == "home") == es_local])
    if sede and sede["n"] < 3:
        sede = None
    d = reciente["dif"] - total["dif"]
    return {"u5": reciente, "total": total, "sede": sede, "es_local": es_local,
            "racha": {"gano": bool(tipo), "n": racha} if racha else None,
            "tendencia": "alza" if d >= UMBRAL_TENDENCIA else "baja" if d <= -UMBRAL_TENDENCIA else None}


def foco(fs, estados):
    """Hasta 5 jugadores más usados con su forma de los últimos 5 partidos frente a su promedio de la ventana.

    estados = {clave: estado de lesión}. «caliente» / «frío» exige al menos 5 partidos jugados y 2 en los últimos 5."""
    cand = sorted((f for f in fs.values() if (f["mpg"] or 0) >= MIN_FOCO and f["pres"] >= 0.4), key=lambda f: -(f["mpg"] or 0))[:5]
    out = []
    for f in cand:
        d_pts = f["ppg5"] - f["ppg"] if f["g5"] >= 2 and f["gp"] >= 5 else None
        d_min = f["mpg5"] - f["mpg"] if f["g5"] >= 2 and f["gp"] >= 5 else None
        margen = max(UMBRAL_CALIENTE, 0.2 * (f["ppg"] or 0))
        d_ts = f["ts5"] - f["ts"] if f["ts5"] is not None and f["ts"] is not None and f["g5"] >= 3 else None
        out.append({"nombre": f["nombre"], "ppg": f["ppg"], "ppg5": f["ppg5"], "mpg": f["mpg"], "mpg5": f["mpg5"],
                    "d_pts": d_pts, "d_min": d_min, "d_ts": d_ts, "ult": f["ult"], "gp": f["gp"], "g5": f["g5"],
                    "estado": estados.get(norm(f["nombre"]), ""),
                    "etiqueta": "caliente" if d_pts is not None and d_pts >= margen else "frio" if d_pts is not None and d_pts <= -margen else None})
    return out


def _con_sin(vg, clave):
    """(bloque con él, bloque sin él) del equipo; None si falta muestra en alguno de los dos."""
    con = [p for p in vg if clave in p["jug"]]
    sin = [p for p in vg if clave not in p["jug"]]
    if len(con) < MIN_MUESTRA or len(sin) < MIN_MUESTRA:
        return None, None
    return _bloque(con), _bloque(sin)


def _absorben(vg, clave, fs):
    """Compañeros que suben puntos y minutos cuando falta `clave`: [{nombre, d_pts, d_min}] (hasta 2)."""
    out = []
    for k, f in fs.items():
        if k == clave or f["gp"] < 4:
            continue
        con = [p["jug"][k] for p in vg if k in p["jug"] and clave in p["jug"]]
        sin = [p["jug"][k] for p in vg if k in p["jug"] and clave not in p["jug"]]
        if len(con) < MIN_MUESTRA or len(sin) < MIN_MUESTRA_VEREDICTO:
            continue
        d_pts = _prom(_v(x.get("PTS")) for x in sin) - _prom(_v(x.get("PTS")) for x in con)
        d_min = _prom(_v(x.get("MIN")) for x in sin) - _prom(_v(x.get("MIN")) for x in con)
        if d_pts >= 2.0 and d_min >= 3.0:
            out.append({"nombre": f["nombre"], "d_pts": d_pts, "d_min": d_min})
    out.sort(key=lambda x: -x["d_pts"])
    return out[:2]


def bajas_con_impacto(vg, fs, bajas):
    """Cada baja con su rol, cuánto lleva fuera y cómo le va al equipo sin él (récord y diferencial) y quién absorbe su juego."""
    n = len(vg)
    out = []
    for b in bajas or []:
        nombre = str(b.get("Jugador") or b.get("nombre") or "")
        if not nombre:
            continue
        clave = norm(nombre)
        f = fs.get(clave)
        item = {"nombre": nombre, "estado": str(b.get("Estado") or b.get("estado") or ""),
                "lesion": str(b.get("Lesión") or b.get("lesion") or ""),
                "regreso": str(b.get("Regreso estimado") or b.get("regreso") or ""),
                "mpg": None, "ppg": None, "fuera_n": None, "larga": f is None, "con": None, "sin": None, "absorben": [],
                "puede_volver": False}
        if f:
            pres = _presencia(f, n)
            item.update(mpg=f["mpg"], ppg=f["ppg"], fuera_n=_fuera_actual(pres))
            item["con"], item["sin"] = _con_sin(vg, clave)
            if item["sin"]:
                item["absorben"] = _absorben(vg, clave, fs)
            item["puede_volver"] = _nivel_estado(item["estado"]) >= 2 and item["fuera_n"] >= 1
        out.append(item)
    out.sort(key=lambda x: (_nivel_estado(x["estado"]), -(x["mpg"] or 0)))
    return out[:5]


def regresos(vg, fs, estados):
    """Jugadores de rotación que volvieron hace poco tras perderse varios partidos, con sus minutos antes y después."""
    n = len(vg)
    out = []
    for k, f in fs.items():
        if _nivel_estado(estados.get(k, "")) == 0:      # figura como baja segura: no ha vuelto
            continue
        r = _ultimo_regreso(_presencia(f, n))
        if not r:
            continue
        m, perdidos, desde_antes = r
        if perdidos < MIN_AUSENCIA_REGRESO or m > MAX_PARTIDOS_REGRESO:
            continue
        antes = [i for i in f["idx"] if i < n - m - perdidos][-5:]
        min_antes = _prom(_v(f["filas"][i].get("MIN")) for i in antes)
        min_desde = _prom(_v(f["filas"][i].get("MIN")) for i in f["idx"] if i >= n - m)
        if max(min_antes or 0, min_desde or 0) < MIN_ROTACION:
            continue
        out.append({"nombre": f["nombre"], "desde": m, "perdidos": perdidos, "desde_antes_ventana": desde_antes,
                    "min_antes": min_antes, "min_desde": min_desde,
                    "limitado": bool(min_antes and m <= 3 and min_desde <= FRAC_MINUTOS_LIMITADOS * min_antes),
                    "ppg_desde": _prom(_v(f["filas"][i].get("PTS")) for i in f["idx"] if i >= n - m),
                    "equipo_sin": _bloque(vg[n - m - perdidos:n - m]), "equipo_desde": _bloque(vg[n - m:])})
    out.sort(key=lambda x: -(x["min_antes"] or x["min_desde"] or 0))
    return out[:3]


# --- Emparejamientos por posición ---------------------------------------------------------------------------------
def concede_por_posicion(serie, cajas, tid, posiciones):
    """Puntos por partido que el equipo `tid` permite a cada grupo de posición rival ({'Guardias': 22.4, ...}).

    None si no se conoce la posición de al menos el 85 % de los puntos rivales (planteles cambiados: mejor sin dato que uno sesgado)."""
    if not posiciones:
        return None
    por_juego, conocido, total = [], 0.0, 0.0
    for g, c in zip(serie, cajas):
        rivales = [x for x in ((c or {}).get("jugadores") or []) if str(x.get("team_id")) != str(tid) and _v(x.get("MIN")) > 0]
        if len(rivales) < 5:
            continue
        acum = {}
        for x in rivales:
            pts = _v(x.get("PTS"))
            total += pts
            grupo = _GRUPO.get((posiciones.get(str(x.get("id"))) or {}).get("pos"))
            if grupo:
                conocido += pts
                acum[grupo] = acum.get(grupo, 0.0) + pts
        por_juego.append(acum)
    if len(por_juego) < MIN_JUEGOS or total <= 0 or conocido / total < COBERTURA_POSICIONES:
        return None
    return {g: _prom(j.get(g, 0.0) for j in por_juego) for g in ("Guardias", "Aleros", "Interiores")}


def quinteto_probable(fs, estados):
    """Los 5 que más veces fueron titulares en los últimos 5 partidos (desempate: minutos), sin los que figuran como baja segura."""
    cand = [f for k, f in fs.items() if _nivel_estado(estados.get(k, "")) != 0 and f["g5"] >= 2]
    cand.sort(key=lambda f: (-f["tit5"], -(f["mpg"] or 0)))
    return cand[:5]


def emparejar(q_l, q_v, posiciones):
    """Une los quintetos por posición (de guardia a pívot) y compara altura y producción. None si faltan datos de posición."""
    def entradas(q):
        e = []
        for f in q:
            info = (posiciones or {}).get(f["id"]) or {}
            rango = _RANGO.get(info.get("pos"))
            if rango is not None:
                e.append((rango, {"nombre": f["nombre"], "pos": info["pos"], "alt": info.get("alt"), "ppg5": f["ppg5"], "ppg": f["ppg"],
                                  "grupo": _GRUPO[info["pos"]]}))
        e.sort(key=lambda x: x[0])
        return [x[1] for x in e]
    el, ev = entradas(q_l), entradas(q_v)
    pares = [{"l": a, "v": b, "dalt": (a["alt"] - b["alt"]) if a.get("alt") and b.get("alt") else None} for a, b in zip(el, ev)]
    return pares if len(pares) >= 3 else None


# --- Punto de entrada --------------------------------------------------------------------------------------------
def analizar(serie_l, serie_v, cajas_l, cajas_v, bajas_l, bajas_v, id_l, id_v, posiciones=None):
    """Análisis profundo de los dos equipos; cada bloque es None si no hay muestra suficiente. Nunca lanza por datos incompletos."""
    res = {"emparejamientos": None, "concede": None}
    fichas_eq = {}
    for lado, serie, cajas, bajas, tid, local in (("l", serie_l, cajas_l, bajas_l, id_l, True), ("v", serie_v, cajas_v, bajas_v, id_v, False)):
        vg = partidos_jugados(serie, cajas, tid)
        estados = {norm(b.get("Jugador") or b.get("nombre")): str(b.get("Estado") or b.get("estado") or "") for b in bajas or []}
        info = {"forma": forma(serie, local), "foco": None, "bajas": [], "regresos": [], "n_cajas": len(vg), "bajas_conocidas": bajas is not None}
        if len(vg) >= MIN_JUEGOS:
            fs = fichas(vg)
            fichas_eq[lado] = (fs, estados)
            info.update(foco=foco(fs, estados), bajas=bajas_con_impacto(vg, fs, bajas), regresos=regresos(vg, fs, estados))
        res[lado] = info
    if posiciones and "l" in fichas_eq and "v" in fichas_eq:
        res["emparejamientos"] = emparejar(quinteto_probable(*fichas_eq["l"]), quinteto_probable(*fichas_eq["v"]), posiciones)
        res["concede"] = {"l": concede_por_posicion(serie_l, cajas_l, id_l, posiciones),     # lo que permite el local
                          "v": concede_por_posicion(serie_v, cajas_v, id_v, posiciones)}     # lo que permite la visita
    return res
