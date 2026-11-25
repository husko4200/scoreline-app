"""Tarjeta de jugador con línea (over/under) y gráfico de sus últimos 10 partidos.

Uso (dentro de la ficha del jugador, en nba_jugadores.py o donde la dibujes):

    import ficha_linea
    ficha_linea.render(
        nombre="Kevin Durant",
        foto_url="https://a.espncdn.com/i/headshots/nba/players/full/3202.png",
        contexto="HOU vs GSW · 21:30",
        series={"PTS": [...10 valores...], "REB": [...], "AST": [...]},   # del más antiguo al más reciente
        rivales=["LAL", "DEN", ...],   # opcional, mismo largo; se muestra al pasar el mouse
        key="durant",                  # único por jugador
    )
"""
import math
import re
from contextlib import contextmanager
from html import escape as _e
from statistics import median
from urllib.parse import quote

import streamlit as st

import estilos

# Texto que se ve en el selector de estadística (la clave interna no cambia: sigue siendo la del box score)
ETIQ_RADIO = {"STL": "ROB"}

NOMBRES = {"PTS": "Puntos", "REB": "Rebotes", "AST": "Asistencias", "3PM": "Triples", "STL": "Robos", "BLK": "Tapones"}



def _redondea_medio(x):
    return round(x * 2) / 2


def _a_medio(x):
    """Lleva cualquier valor a x.5 (8 u 8.0 -> 8.5) dentro de 0.5–399.5."""
    x = float(x)
    if x % 1 != 0.5:
        x = math.floor(x) + 0.5
    return min(max(x, 0.5), 399.5)


def _ajusta_medio(wk):
    """Al escribir a mano un valor terminado en .0, el campo se corrige al instante."""
    st.session_state[wk] = _a_medio(st.session_state[wk])


def evaluar(valores, linea, mas=True):
    """Lógica pura de la tarjeta (sin Streamlit ni HTML), fácil de probar.

    Devuelve (estados, k, n, pct):
      estados  una etiqueta por partido: "ok" (cumple), "no" (no cumple) o "push" (empate exacto con la línea)
      k        partidos que cumplen
      n        partidos que cuentan (los empates se excluyen, como en las casas de apuestas)
      pct      porcentaje entero k/n (0 si no hay partidos que cuenten)
    """
    estados = ["push" if v == linea else "ok" if ((v > linea) if mas else (v < linea)) else "no" for v in valores]
    k, n = estados.count("ok"), len(estados) - estados.count("push")
    return estados, k, n, (round(100 * k / n) if n else 0)


_DECAY = 0.85            # el partido más reciente pesa 1, el anterior 0.85, el anterior 0.85², etc. (como la simulación)


def pct_ponderado(valores, linea, mas=True, decay=_DECAY):
    """% de partidos que cumplen la línea dando más peso a los recientes (peso decay**k, k = partidos atrás).

    `valores` va del más antiguo al más reciente. Los empates exactos no cuentan. None si no hay partidos que cuenten."""
    m = len(valores)
    num = den = 0.0
    for i, v in enumerate(valores):
        if v == linea:
            continue
        w = decay ** (m - 1 - i)
        den += w
        if (v > linea) if mas else (v < linea):
            num += w
    return round(100 * num / den) if den else None


def resumen_stats(valores):
    """(promedio, mediana, mínimo, máximo, desviación típica muestral); None si no hay datos."""
    if not valores:
        return None
    m = len(valores)
    mu = sum(valores) / m
    sd = math.sqrt(sum((v - mu) ** 2 for v in valores) / (m - 1)) if m > 1 else 0.0
    return mu, median(valores), min(valores), max(valores), sd


_EDGE_MIN = 3.0          # ventaja (en puntos porcentuales) a partir de la cual se marca «valor» o «sin valor»


def parse_cuota(texto):
    """Convierte lo escrito en el campo de cuota a cuota decimal (>1), o None si está vacío o no es válido.

    Solo cuota decimal: «1.91» o «1,91». Lo demás (por ejemplo «-110») no es válido."""
    t = str(texto or "").strip().replace(",", ".").replace(" ", "")
    if not t:
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return v if 1.01 <= v < 100 else None


def valor_vs_cuota(cuota, estimaciones, umbral=_EDGE_MIN):
    """Compara cada estimación con la probabilidad implícita de la cuota.

    estimaciones: [(nombre, % estimado)]. Devuelve [(nombre, %, ventaja_pts, ev_pct, cuota_justa, clase)] con
      · ventaja_pts: estimado − implícito (puntos porcentuales),
      · ev_pct: valor esperado por unidad apostada, p·cuota − 1, en %,
      · cuota_justa: 1/p, la cuota a partir de la cual la apuesta tiene valor (None si p = 0),
      · clase: «v» (ventaja ≥ umbral), «r» (≤ −umbral) o «n» (sin ventaja clara)."""
    implicita = 100 / cuota
    filas = []
    for nombre, pct in estimaciones:
        if pct is None:
            continue
        ventaja = pct - implicita
        ev = (pct / 100 * cuota - 1) * 100
        justa = 100 / pct if pct > 0 else None
        clase = "v" if ventaja >= umbral else ("r" if ventaja <= -umbral else "n")
        filas.append((nombre, pct, ventaja, ev, justa, clase))
    return filas


_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def fmt_dif(d):
    """Diferencia respecto a la línea con signo y un decimal: «+4.5», «−2.5» (menos tipográfico) o «0» si es exacta."""
    return "0" if abs(d) < 1e-9 else f"{d:+.1f}".replace("-", "−")


def fecha_corta(iso):
    """«2026-03-12» -> «12 mar 2026»; si no se entiende la fecha, devuelve \"\" (el tooltip simplemente no la muestra)."""
    try:
        anio, mes, dia = str(iso).split("-")[:3]
        return f"{int(dia)} {_MESES[int(mes) - 1]} {anio}"
    except (ValueError, IndexError):
        return ""


# Estadísticas combinadas y sus componentes, de abajo hacia arriba en la barra apilada
_COMPONENTES = {"REB+AST": ("REB", "AST"), "PTS+REB": ("PTS", "REB"), "PTS+AST": ("PTS", "AST"), "P+R+A": ("PTS", "REB", "AST")}
_UNIDAD = {"PTS": ("pt", "pts"), "REB": ("reb", "reb"), "AST": ("ast", "ast"), "3PM": ("triple", "triples"),
           "STL": ("robo", "robos"), "BLK": ("tapón", "tapones")}   # para «Hizo 10 pts» en el tooltip
_SEG_MIN = 0.22          # un segmento escribe su número dentro solo si ocupa al menos esta parte de la barra


def desglose_combinada(stat, series, n):
    """Para una estadística combinada: [[(componente, valor), ...] por partido] con los últimos n partidos, o None.

    Devuelve None si `stat` no es combinada o si faltan sus componentes en `series`. Un partido concreto queda en None
    (barra lisa) si sus componentes no suman exactamente el total."""
    comp = _COMPONENTES.get(stat)
    if not comp or stat not in series or any(c not in series or len(series[c]) < n for c in comp):
        return None
    partes = [series[c][-n:] for c in comp]
    total = series[stat][-n:]
    res = []
    for i in range(n):
        vals = [p[i] for p in partes]
        ok = all(v >= 0 for v in vals) and abs(sum(vals) - total[i]) < 1e-6
        res.append(list(zip(comp, vals)) if ok else None)
    return res if any(r is not None for r in res) else None


_PALIZA = 15             # diferencia final (pts) desde la que un partido cuenta como «paliza»: los titulares juegan menos
_FRAC_POCOS_MIN = 0.7    # «pocos minutos»: menos del 70 % de los minutos medianos del jugador en la muestra
_ESTADOS_OUT = {"out"}   # el resto de estados (Day-To-Day, Questionable...) se muestra como dudoso

# Filtros de contexto: clave -> (rótulo, [(opción, función(partido) -> bool|None)]).  None = dato desconocido (no entra al filtrar)
_FILTROS = {
    "sede": ("Sede", [("Local", lambda p: p.get("local")), ("Visita", lambda p: None if p.get("local") is None else not p["local"])]),
    "descanso": ("Descanso", [("Con descanso", lambda p: None if p.get("descanso") is None else p["descanso"] >= 1),
                              ("Sin descanso", lambda p: None if p.get("descanso") is None else p["descanso"] < 1)]),
    "rol": ("Rol", [("Titular", lambda p: p.get("titular")), ("Banca", lambda p: None if p.get("titular") is None else not p["titular"])]),
    "resultado": ("Resultado", [("Ganados", lambda p: p.get("gano")), ("Perdidos", lambda p: None if p.get("gano") is None else not p["gano"])]),
    "paliza": ("Paliza", [("Con paliza", lambda p: es_paliza(p)), ("Sin paliza", lambda p: None if es_paliza(p) is None else not es_paliza(p))]),
}


def es_paliza(p):
    """True si el partido fue una paliza (diferencia final >= _PALIZA o marcado a mano con "paliza"); None si no hay dato."""
    if p.get("paliza") is not None:
        return bool(p["paliza"])
    m = p.get("margen")
    return None if m is None else abs(m) >= _PALIZA


def filtrar_partidos(partidos, filtros):
    """Máscara (una casilla por partido) con los que cumplen TODOS los filtros activos. `filtros` = {clave: opción}; "Todos" no filtra.
    Un partido sin el dato necesario para un filtro activo no entra (no se puede clasificar)."""
    mascara = []
    for p in partidos:
        ok = True
        for clave, opcion in (filtros or {}).items():
            if not opcion or opcion == "Todos" or clave not in _FILTROS:
                continue
            f = dict(_FILTROS[clave][1]).get(opcion)
            if f is None or f(p) is not True:
                ok = False
                break
        mascara.append(ok)
    return mascara


def pocos_minutos(partidos, frac=_FRAC_POCOS_MIN):
    """(marcas, umbral): marcas[i] es True si jugó muy pocos minutos (< frac × la mediana de minutos de la muestra).
    Evita leer como mala racha un partido de 20 minutos. Sin minutos conocidos: todo False y umbral None."""
    mins = [p.get("min") for p in partidos if p.get("min") is not None]
    if len(mins) < 3:
        return [False] * len(partidos), None
    umbral = frac * median(mins)
    return [p.get("min") is not None and p["min"] < umbral for p in partidos], umbral


def armar_partidos(historial, pa=None):
    """Adaptador desde los DataFrames de nba_extra a la lista `partidos` que espera render().

    historial  partidos del jugador (event_id, Fecha, Condición, MIN, Titular); pa  partidos del equipo (event_id, Resultado,
    PF, PC, Descanso, Condición). Devuelve una lista del más antiguo al más reciente. Cada elemento:
    {"local", "descanso", "titular", "gano", "margen", "min"}; lo que falte queda en None."""
    import pandas as pd
    h = historial.copy()
    if "Fecha" in h.columns:
        h = h.sort_values("Fecha")
    if pa is not None and "event_id" in h.columns and "event_id" in pa.columns:
        extra = [c for c in ("event_id", "Descanso", "PF", "PC", "Condición") if c in pa.columns and (c == "event_id" or c not in h.columns)]
        h = h.merge(pa[extra].drop_duplicates("event_id"), on="event_id", how="left")
    def _num(x):
        return None if x is None or pd.isna(x) else float(x)
    def _local(r):
        c = str(r.get("Condición") or "").strip().lower()
        if c.startswith(("l", "vs", "casa", "home")):
            return True
        return False if c.startswith(("v", "@", "fuera", "away")) else None
    out = []
    for _, r in h.iterrows():
        pf, pc = _num(r.get("PF")), _num(r.get("PC"))
        tit = r.get("Titular")
        out.append({"local": _local(r), "descanso": _num(r.get("Descanso")),
                    "titular": None if tit is None or (not isinstance(tit, (bool, int)) and pd.isna(tit)) else bool(tit),
                    "gano": None if pf is None or pc is None else pf > pc,
                    "margen": None if pf is None or pc is None else pf - pc,
                    "min": _num(r.get("MIN"))})
    return out


def unificar_contexto(partidos, detalles, riv, n):
    """Une `partidos` (filtros) y `detalles` (tooltips y marcas) en dos listas de n elementos, una por barra: (ctx, det).

    ctx  {"local", "descanso", "titular", "gano", "margen", "min", "paliza"} para filtrar y marcar pocos minutos.
    det  el detalle del tooltip, completado con la sede, el descanso y los minutos que solo venían en `partidos`.
    Cada fuente se alinea con el final de la serie; si su largo no calza con n se descarta (mejor nada que datos de otro partido)."""
    def _alinea(fuente):
        lst = [d if isinstance(d, dict) else {} for d in (fuente or [])][-n:]
        return lst if len(lst) == n else [{}] * n
    pa, de = _alinea(partidos), _alinea(detalles)
    ctxs, dets = [], []
    for i in range(n):
        p, d = pa[i], dict(de[i])
        sede = d.get("sede") if d.get("sede") in ("Local", "Visita") else None
        if sede is None and riv:
            m = _RIVAL.match(riv[i][0].strip())
            sede = None if not m else ("Local" if m.group(1) == "vs" else "Visita")
        local = p.get("local") if p.get("local") is not None else (None if sede is None else sede == "Local")
        desc = p.get("descanso") if p.get("descanso") is not None else d.get("descanso")
        mins = p.get("min") if p.get("min") is not None else d.get("minutos")
        gano = p.get("gano") if p.get("gano") is not None else d.get("gano")
        ctxs.append({"local": local, "descanso": desc, "titular": p.get("titular"), "gano": gano,
                     "margen": p.get("margen"), "min": mins, "paliza": p.get("paliza")})
        if sede is None and local is not None:
            d["sede"] = "Local" if local else "Visita"
        elif sede is not None:
            d["sede"] = sede
        if d.get("descanso") is None and desc is not None:
            d["descanso"] = int(desc) if float(desc).is_integer() else desc
        elif isinstance(d.get("descanso"), float) and d["descanso"].is_integer():
            d["descanso"] = int(d["descanso"])
        if d.get("minutos") is None and mins is not None:
            d["minutos"] = mins
        dets.append(d)
    return ctxs, dets


_Z95 = 1.96              # intervalo de confianza del 95 %
_MIN_FIABLE = 5          # con menos partidos válidos que estos, el % se marca como poco fiable
_UMBRAL_SEGURA = 70      # una línea se considera «segura» si se cumplió en al menos este % de los partidos
_PASOS_ESCALERA = 4      # la escalera muestra la línea actual ± este número de pasos de 1.0 (9 líneas en total)


def intervalo_wilson(k, n, z=_Z95):
    """Rango probable (intervalo de Wilson al 95 %) del porcentaje real, en enteros (bajo, alto); None si n == 0.

    Con pocos partidos un 47 % no es un dato exacto: con 15 partidos el verdadero porcentaje puede estar entre ~25 % y ~70 %.
    Wilson se comporta bien con muestras pequeñas y con porcentajes cercanos a 0 % o 100 %."""
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    medio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, round(100 * (centro - medio))), min(100, round(100 * (centro + medio)))


def _clase_pct(pct):
    return "v" if pct >= 65 else ("r" if pct <= 35 else "n")


def tendencia_ventanas(valores, linea, mas, ventanas, historico=None):
    """[(etiqueta, partidos, k, n, pct, es_temporada)] para cada ventana (los últimos 5, 10...) y, si se da, toda la temporada.

    Las ventanas que no tienen más partidos que otra más corta no se repiten (con 12 partidos, «últimos 15» y «últimos 20» serían iguales)."""
    filas, vistos = [], set()
    for w in sorted(ventanas):
        tramo = valores[-w:]
        if not tramo or len(tramo) in vistos:
            continue
        vistos.add(len(tramo))
        _, k, n, pct = evaluar(tramo, linea, mas)
        filas.append((f"Últ. {len(tramo)}", len(tramo), k, n, pct, False))
    if historico and len(historico) not in vistos:
        _, k, n, pct = evaluar(historico, linea, mas)
        filas.append(("Temporada", len(historico), k, n, pct, True))
    return filas


def escalera_lineas(valores, linea, mas, pasos=_PASOS_ESCALERA):
    """[(línea, k, n, pct)] de la línea actual ±pasos (de 1.0 en 1.0, siempre en x.5 y dentro de 0.5–399.5)."""
    res = []
    for d in range(-pasos, pasos + 1):
        ln = linea + d
        if ln < 0.5 or ln > 399.5:
            continue
        _, k, n, pct = evaluar(valores, ln, mas)
        if n:
            res.append((ln, k, n, pct))
    return res


def linea_segura(valores, mas, umbral=_UMBRAL_SEGURA):
    """La línea más exigente que se cumplió en al menos `umbral` % de los partidos: (línea, pct) o None.

    «Más de»: la línea más alta que aún cumple el umbral. «Menos de»: la más baja."""
    if not valores:
        return None
    tope = math.floor(max(valores)) + 1.5
    mejor, ln = None, 0.5
    while ln <= min(tope, 399.5):
        _, k, n, pct = evaluar(valores, ln, mas)
        if n and pct >= umbral:
            if mas:
                mejor = (ln, pct)          # va subiendo: se queda con la última que cumple
            elif mejor is None:
                mejor = (ln, pct)          # «Menos de»: la primera (la más baja) que cumple
        ln += 1.0
    return mejor


_SILUETA_SVG = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 160 190'><defs><linearGradient id='g' x1='0' y1='0' x2='0' y2='1'>"
                "<stop offset='0' stop-color='#a5b4fc' stop-opacity='.55'/><stop offset='1' stop-color='#6366f1' stop-opacity='.18'/>"
                "</linearGradient></defs><circle cx='80' cy='62' r='34' fill='url(#g)'/>"
                "<path d='M12 190c0-52 30-80 68-80s68 28 68 80z' fill='url(#g)'/></svg>")
SILUETA = "data:image/svg+xml;utf8," + quote(_SILUETA_SVG)   # foto_url=ficha_linea.SILUETA dibuja una silueta desconocida


def _url_segura(url):
    """Solo se admiten imágenes por https (y la silueta propia); cualquier otra cosa se descarta."""
    url = str(url or "").strip()
    if url == SILUETA:
        return url
    return url if url.lower().startswith("https://") else ""


def _riv_stat(rivales, stat):
    """`rivales` puede ser una lista (igual para todas las estadísticas) o un dict {estadística: lista}."""
    return (rivales.get(stat) if isinstance(rivales, dict) else rivales) or []


def _corto_largo(r):
    """Cada rival es un texto o una pareja (etiqueta corta, nombre completo para el mouse)."""
    return (str(r[0]), str(r[1])) if isinstance(r, (tuple, list)) and len(r) == 2 else (str(r), str(r))


def render(nombre, foto_url, contexto, series, rivales=None, key="ficha", nombres=None, ultimos=10, medios=False, buscador=None, escudo=None, logo_equipo=None, ventanas=None, historico=None, simulacion=None, detalles=None, partidos=None, proximo=None):
    """Dibuja la tarjeta. `series` = {"PTS": [valores], ...}, del partido más antiguo al más reciente.

    nombres   {sigla: nombre largo}; por defecto los de la NBA. Si el nombre largo es igual a la sigla, se muestra una vez.
    ultimos   cuántos partidos se dibujan (10 por defecto).
    medios    (sin efecto) la línea siempre termina en .5: la sugerida es floor(mediana)+.5 y el paso es 1.
    buscador  función opcional sin argumentos que dibuja un buscador (p. ej. de jugadores) DENTRO de la tarjeta, arriba del todo.
    escudo    función opcional sigla -> URL https del escudo. Si se da y el rival viene como «vs MIA» o «@ MIA», bajo cada
              barra se dibuja el escudo con la sigla y la sede; sin ella (o sin escudo) queda el texto de siempre.
    logo_equipo  URL https opcional del escudo del equipo del jugador; se dibuja junto al texto de contexto, bajo el nombre.
    ventanas  opcional, p. ej. (5, 10, 15, 20): agrega el selector «Últimos partidos» y la tarjeta muestra solo esa cantidad.
              Hay que pasar series (y rivales) con al menos max(ventanas) partidos; `contexto` va SIN «últimos N partidos»
              (la tarjeta lo añade según la ventana elegida). Si hay menos partidos que la ventana, se muestran todos.
    rivales   lista (o dict por estadística) alineada con el final de cada serie; cada elemento es un texto
              o (etiqueta_corta, nombre_completo).
    historico opcional, {estadística: [valores]} del más antiguo al más reciente con TODOS los partidos disponibles (no solo
              los dibujados). Habilita la celda «Temporada» de la fila de tendencia; sin él, esa celda no aparece.

    detalles  opcional, lista alineada con el final de las series (un dict por partido) con lo que aparece en el tooltip de cada
              barra: {"fecha": "2026-03-12", "rival": "Orlando Magic", "sede": "Local"/"Visita", "resultado": "Victoria 112–105",
              "gano": True/False, "minutos": 34.5, "fase": "Playoffs", "descanso": 0}. Todas las claves son opcionales.
              «sede» y «descanso» (días de descanso; 0 = back-to-back) alimentan las marcas discretas bajo cada barra: punto
              lleno = local, anillo = visita, «BTB» = back-to-back. Sin «sede» se deduce de «vs» / «@» en el rival. Sin ella, el tooltip muestra
              solo el rival, el valor y la diferencia con la línea.
    partidos  opcional, lista alineada con el final de las series (un dict por partido) para el CONTEXTO DEL PARTIDO:
              {"local": bool, "descanso": días, "titular": bool, "gano": bool, "margen": pts del equipo, "min": minutos,
              "paliza": bool opcional}. Todo puede faltar (None). Activa los filtros (sede, descanso, rol, resultado, paliza: se
              aplican a barras, promedio, %, ponderado y escalera) y la marca ● bajo cada barra de un partido con pocos minutos.
              Se combina con `detalles` (la sede, el descanso y los minutos se toman de donde estén). `armar_partidos(historial, pa)`
              la construye desde los DataFrames de nba_extra.
    proximo   opcional, {"rival": "MIA", "sede": "vs"|"@", "concede": {estadística: {"valor", "liga", "rank"}},
              "ritmo": {"valor", "liga", "rank"}, "bajas": [{"Jugador", "Estado", "Lesión"}], "bajas_equipo": [...]}.
              Panel «Próximo rival»: cuánto concede de la estadística elegida, su ritmo y las bajas (Out y Day-To-Day).
    simulacion opcional, función (estadística, línea, mas) -> % simulado del próximo partido (o None). Con ella, el encabezado
              muestra «Historial 47 % · Simulación 52 %» y se ve de un vistazo si el historial y la proyección coinciden.

    Además de las barras, la tarjeta muestra: el rango probable del porcentaje (Wilson 95 %), la tendencia en todas las
    ventanas a la vez y la escalera de líneas (qué % habría con la línea ±4).
    """
    nom = {**NOMBRES, **(nombres or {})}
    ventanas = tuple(sorted({int(v) for v in ventanas if int(v) > 0})) if ventanas else ()
    if ventanas:
        ultimos = max(ultimos, ventanas[-1])
    series = {k: [float(v) for v in vals][-ultimos:] for k, vals in series.items() if vals}
    historico = {k: [float(v) for v in vals] for k, vals in (historico or {}).items() if vals}
    if not series:
        st.info("Todavía no hay partidos para mostrar.")
        return
    estilos.cargar("ficha_linea")

    # Contenedor con aspecto de tarjeta oscura: el buscador y los controles quedan DENTRO de ella
    # (un widget de Streamlit no puede ir dentro de un bloque HTML, así que la tarjeta se pinta en el contenedor).
    cls = "st-key-" + "".join(ch if ch.isalnum() else "_" for ch in f"{key}_caja")
    st.markdown(_CSS_CAJA.replace("__C__", cls), unsafe_allow_html=True)
    try:
        caja = st.container(key=f"{key}_caja")
    except TypeError:   # Streamlit antiguo sin key en container: queda sin fondo, pero funciona igual
        caja = st.container()
    with caja:
        _dibujar(nom, series, rivales, nombre, foto_url, contexto, key, ultimos, buscador, escudo, logo_equipo, ventanas, historico, simulacion, detalles, partidos, proximo)
    st.caption("La frecuencia es histórica (cuántas veces cumplió la línea), no una predicción del partido de hoy.")


_CSS_ESQUELETO = """
<style>
@keyframes fl-sk-brilla { from { background-position: 100% 0; } to { background-position: 0 0; } }
.fl-sk { position: relative; border-radius: 26px; padding: 1.4rem 1.6rem 1.2rem; margin: .4rem 0 .6rem; overflow: hidden;
  background: radial-gradient(760px 320px at 0% 0%, rgba(99,102,241,.40), transparent 62%),
              radial-gradient(700px 360px at 100% 100%, rgba(139,92,246,.32), transparent 62%),
              linear-gradient(160deg, #0f172a 0%, #1e1b4b 55%, #2b1d66 100%);
  border: 1px solid rgba(165,180,252,.24); box-shadow: 0 26px 60px -20px rgba(30,27,75,.65), 0 2px 0 rgba(255,255,255,.07) inset; }
.fl-sk .b { display: block; border-radius: 12px; background: linear-gradient(100deg, rgba(255,255,255,.06) 30%, rgba(255,255,255,.2) 50%, rgba(255,255,255,.06) 70%);
  background-size: 250% 100%; animation: fl-sk-brilla 1.5s ease-in-out infinite; }
.fl-sk .fila { display: flex; gap: 14px; align-items: flex-end; margin-bottom: 1.1rem; }
.fl-sk .barras { display: flex; align-items: flex-end; gap: 8px; height: 150px; margin-top: 1.4rem; }
.fl-sk .barras .b { flex: 1; border-radius: 9px; }
@media (prefers-reduced-motion: reduce) { .fl-sk .b { animation: none; } }
</style>
"""


def _html_esqueleto():
    alturas = (82, 78, 55, 60, 50, 66, 80, 72, 68, 80)
    barras = "".join(f'<i class="b" style="height:{h}%;animation-delay:{i * .08:.2f}s"></i>' for i, h in enumerate(alturas))
    return (_CSS_ESQUELETO + '<div class="fl-sk" role="status" aria-live="polite" aria-busy="true" aria-label="Cargando los partidos">'
            '<div class="fila"><i class="b" style="flex:3.6;height:96px"></i><i class="b" style="flex:3.9;height:96px"></i><i class="b" style="flex:2;height:96px"></i></div>'
            '<div class="fila"><i class="b" style="width:170px;height:42px"></i><i class="b" style="width:120px;height:42px"></i><i class="b" style="width:120px;height:42px"></i></div>'
            '<i class="b" style="width:min(60%,420px);height:44px;margin-bottom:.7rem"></i>'
            '<i class="b" style="width:min(30%,220px);height:20px;margin-bottom:1.6rem"></i>'
            '<div class="fila" style="justify-content:space-between"><i class="b" style="width:150px;height:70px"></i><i class="b" style="width:190px;height:70px"></i></div>'
            f'<div class="barras">{barras}</div></div>')


def esqueleto():
    """Dibuja una tarjeta «fantasma» con brillo (mismas proporciones que la real). Para usar con un st.empty(); mejor, con cargando()."""
    st.markdown(_html_esqueleto(), unsafe_allow_html=True)


@contextmanager
def cargando():
    """Mientras dura el bloque, muestra el esqueleto en el lugar donde luego irá la tarjeta; al terminar (o fallar) lo quita.

        with ficha_linea.cargando():
            historial = pedir_partidos(...)     # lo lento
        ficha_linea.render(...)
    """
    hueco = st.empty()
    hueco.markdown(_html_esqueleto(), unsafe_allow_html=True)
    try:
        yield
    finally:
        hueco.empty()


_CSS_CAJA = """
<style>
.__C__ { position: relative; border-radius: 26px; padding: 1.4rem 1.6rem 1.2rem; overflow: hidden; margin: .4rem 0 .6rem;
  background: radial-gradient(760px 320px at 0% 0%, rgba(99,102,241,.40), transparent 62%),
              radial-gradient(700px 360px at 100% 100%, rgba(139,92,246,.32), transparent 62%),
              radial-gradient(520px 260px at 100% 0%, rgba(56,189,248,.12), transparent 65%),
              linear-gradient(160deg, #0f172a 0%, #1e1b4b 55%, #2b1d66 100%);
  border: 1px solid rgba(165,180,252,.24);
  box-shadow: 0 26px 60px -20px rgba(30,27,75,.65), 0 2px 0 rgba(255,255,255,.07) inset; }
/* filete de color en el borde superior, el mismo índigo de la tabla de partidos */
.__C__::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; z-index: 1; pointer-events: none;
  background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 55%, #38bdf8 100%); }
.__C__ .fl { background: transparent !important; box-shadow: none !important; border: 0 !important; border-radius: 0 !important;
  margin: 0 !important; padding: .4rem 0 0 !important; overflow: visible !important; }

/* etiquetas pequeñas y discretas */
.__C__ [data-testid="stWidgetLabel"] p, .__C__ label > div > p { font-size: .66rem !important; font-weight: 700 !important;
  letter-spacing: .14em !important; text-transform: uppercase !important; color: rgba(255,255,255,.5) !important; }

/* buscador, selector de equipo y número: SIN fondo, solo un borde de cristal.
   Todo lo que hay dentro del selector se deja transparente (el color crema venía de capas internas). */
.__C__.__C__.__C__ [data-testid="stMultiSelect"] *, .__C__.__C__.__C__ [data-testid="stSelectbox"] *,
.__C__.__C__.__C__ [data-baseweb="select"], .__C__.__C__.__C__ [data-baseweb="select"] *, .__C__.__C__.__C__ [data-baseweb="input"],
.__C__.__C__.__C__ [data-baseweb="base-input"], .__C__.__C__.__C__ [data-testid="stNumberInput"] * {
  background: transparent !important; background-color: transparent !important; background-image: none !important; }
.__C__.__C__.__C__ [data-testid="stMultiSelect"], .__C__.__C__.__C__ [data-testid="stSelectbox"] { background: transparent !important; }
.__C__.__C__.__C__ [data-baseweb="select"] > div, .__C__.__C__.__C__ [data-baseweb="input"], .__C__.__C__.__C__ [data-testid="stNumberInput"] > div > div {
  border: 1px solid rgba(255,255,255,.22) !important; border-radius: 14px !important;
  transition: border-color .2s ease, box-shadow .2s ease; }
.__C__.__C__.__C__ [data-baseweb="select"] > div:hover, .__C__.__C__.__C__ [data-baseweb="input"]:hover { border-color: rgba(165,180,252,.65) !important; }
.__C__ [data-baseweb="select"] *, .__C__ input { color: #eef0ff !important; -webkit-text-fill-color: #eef0ff !important; }
.__C__ input { background: transparent !important; caret-color: #a5b4fc !important; }
.__C__ input::placeholder { color: rgba(255,255,255,.5) !important; -webkit-text-fill-color: rgba(255,255,255,.5) !important; opacity: 1 !important; }
.__C__ [data-baseweb="select"] svg, .__C__ [data-testid="stNumberInput"] svg { fill: rgba(255,255,255,.7) !important; color: rgba(255,255,255,.7) !important; }
.__C__.__C__.__C__ span[data-baseweb="tag"] { background: linear-gradient(135deg, #6366f1, #8b5cf6) !important; border-radius: 999px !important; }
.__C__ span[data-baseweb="tag"] * { color: #fff !important; -webkit-text-fill-color: #fff !important; }
.__C__.__C__.__C__ [data-testid="stNumberInput"] button { border: 0 !important; border-left: 1px solid rgba(255,255,255,.16) !important; color: #eef0ff !important; }
.__C__ [data-testid="stNumberInput"] button:hover { background: rgba(165,180,252,.18) !important; color: #fff !important; }
.__C__.__C__.__C__ [data-testid="stNumberInputContainer"],
.__C__.__C__.__C__ [data-testid="stNumberInput"] [data-baseweb="input"],
.__C__.__C__.__C__ [data-testid="stNumberInput"] > div > div { border-color: rgba(255,255,255,.22) !important; }
.__C__.__C__.__C__ [data-testid="stNumberInputContainer"]:focus-within,
.__C__.__C__.__C__ [data-testid="stNumberInput"] > div > div:focus-within { border-color: #a5b4fc !important; box-shadow: 0 0 0 3px rgba(165,180,252,.28) !important; }
.__C__.__C__ [data-testid="InputInstructions"] { color: rgba(224,231,255,.82) !important; -webkit-text-fill-color: rgba(224,231,255,.82) !important; }

/* sin contornos ni rayas internas (la línea naranja era el contorno de foco del campo de texto) */
.__C__.__C__.__C__ [data-baseweb="select"] > div *, .__C__.__C__.__C__ [data-baseweb="select"] input,
.__C__.__C__.__C__ [data-baseweb="select"] input:focus, .__C__.__C__.__C__ [data-baseweb="select"] input:focus-visible,
.__C__.__C__.__C__ [data-baseweb="input"] input:focus, .__C__.__C__.__C__ [data-baseweb="input"] input:focus-visible {
  outline: none !important; outline-width: 0 !important; border: 0 !important; box-shadow: none !important; }
.__C__.__C__.__C__ [data-baseweb="select"] > div::before, .__C__.__C__.__C__ [data-baseweb="select"] > div::after,
.__C__.__C__.__C__ [data-baseweb="select"] > div *::before, .__C__.__C__.__C__ [data-baseweb="select"] > div *::after { content: none !important; display: none !important; }
.__C__.__C__.__C__ [data-baseweb="select"] > div:focus, .__C__.__C__.__C__ [data-baseweb="select"] > div:focus-visible { outline: none !important; }

/* al enfocar (cuando vas a escribir): brillo fijo */
.__C__.__C__.__C__ [data-baseweb="select"] > div:focus-within, .__C__.__C__.__C__ [data-baseweb="input"]:focus-within {
  border-color: #a5b4fc !important; box-shadow: 0 0 0 3px rgba(165,180,252,.28), 0 0 18px rgba(139,92,246,.35); animation: none !important; }

/* buscador de jugadores vacío: parpadea suave para pedirte que escribas */
@keyframes fl-parpadeo {
  0%, 100% { box-shadow: 0 0 0 0 rgba(165,180,252,0), 0 0 0 0 rgba(139,92,246,0); }
  50%      { box-shadow: 0 0 0 4px rgba(165,180,252,.30), 0 0 22px rgba(139,92,246,.55); }
}
@keyframes fl-placeholder { 0%, 100% { opacity: .35; } 50% { opacity: 1; } }
.__C__.__C__.__C__ [data-testid="stMultiSelect"] [data-baseweb="select"]:not(:has([data-baseweb="tag"])) > div { animation: fl-parpadeo 1.4s ease-in-out infinite; }
.__C__ [data-testid="stMultiSelect"] [data-baseweb="select"]:not(:has([data-baseweb="tag"])) input::placeholder { animation: fl-placeholder 1.4s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce) { .__C__ [data-baseweb="select"] > div, .__C__ input::placeholder { animation: none !important; } }

/* Controles compactos: chips sin circulito, cada grupo en UNA fila y con la misma altura (42 px) que los campos de al lado,
   así las etiquetas de «Últimos partidos», «Lado», «Línea» y «Cuota» quedan a la misma altura. El elegido va en degradado. */
.__C__ [data-testid="stWidgetLabel"] { min-height: 1.15rem; align-items: center; margin-bottom: .3rem; }
.__C__.__C__ [data-testid="stRadio"] [role="radiogroup"] { background: rgba(255,255,255,.04) !important; border: 1px solid rgba(255,255,255,.14) !important;
  box-shadow: none !important; border-radius: 14px !important; padding: 3px !important; gap: 2px !important; min-height: 42px; box-sizing: border-box; align-items: center; }
.__C__.__C__ [data-testid="stRadio"] [role="radiogroup"] label { background: transparent !important; box-shadow: none !important; border-radius: 11px !important;
  margin: 0 !important; padding: 0 .72rem !important; min-height: 34px; display: flex !important; align-items: center; transition: background .2s ease; }
.__C__.__C__ [data-testid="stRadio"] [role="radiogroup"] label > *:not(input):not(:has([data-testid="stMarkdownContainer"])) { display: none !important; }
.__C__.__C__ [data-testid="stRadio"] [role="radiogroup"] label:hover { background: rgba(255,255,255,.08) !important; }
.__C__.__C__ [data-testid="stRadio"] [role="radiogroup"] label p { color: rgba(255,255,255,.72) !important; font-weight: 700 !important; font-size: .8rem !important;
  letter-spacing: 0 !important; text-transform: none !important; margin: 0 !important; white-space: nowrap; }
.__C__.__C__ [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) { background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
  box-shadow: 0 5px 14px rgba(99,102,241,.45) !important; }
.__C__.__C__ [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) p { color: #fff !important; }
/* Línea y Cuota: misma altura que los chips y números en negrita */
.__C__.__C__ [data-testid="stNumberInput"] [data-baseweb="input"], .__C__.__C__ [data-testid="stNumberInput"] > div > div:has([data-baseweb="input"]),
  .__C__.__C__ [data-testid="stTextInputRootElement"] { min-height: 42px; box-sizing: border-box; }
.__C__ [data-testid="stNumberInput"] input, .__C__ [data-testid="stTextInput"] input { font-weight: 700 !important; }
/* El campo de texto de la cuota también va sin relleno (la capa raíz de Streamlit lo pintaba de claro) */
.__C__.__C__.__C__ [data-testid="stTextInput"] *, .__C__.__C__.__C__ [data-testid="stTextInputRootElement"] { background: transparent !important; background-color: transparent !important; background-image: none !important; }
.__C__.__C__.__C__ [data-testid="stTextInputRootElement"] { border: 1px solid rgba(255,255,255,.22) !important; border-radius: 14px !important; transition: border-color .2s ease, box-shadow .2s ease; }
.__C__.__C__.__C__ [data-testid="stTextInputRootElement"] [data-baseweb="input"], .__C__.__C__.__C__ [data-testid="stTextInputRootElement"] [data-baseweb="base-input"] { border: 0 !important; box-shadow: none !important; }
.__C__.__C__.__C__ [data-testid="stTextInputRootElement"]:hover { border-color: rgba(165,180,252,.65) !important; }
.__C__.__C__.__C__ [data-testid="stTextInputRootElement"]:focus-within { border-color: #a5b4fc !important; box-shadow: 0 0 0 3px rgba(165,180,252,.28), 0 0 18px rgba(139,92,246,.35); }

/* Lista desplegable de los selectores (se dibuja fuera de la tarjeta, por eso no lleva __C__): más baja, para que quepa
   debajo del campo y no salte hacia arriba cuando la tarjeta queda cerca del borde inferior de la pantalla. */
div[data-baseweb="popover"] ul[role="listbox"] { max-height: 232px !important; }

/* selector de «Últimos partidos» y barras más finas cuando hay muchos partidos */
/* Al subir o bajar la línea: la línea punteada se desliza hasta su nueva altura y las barras se reajustan si cambia la escala.
   Hay dos animaciones gemelas (a y b) que se alternan en cada cambio: así el movimiento se reinicia aunque el navegador reutilice el elemento. */
@keyframes fl-mueve-a { from { bottom: var(--de); } to { bottom: var(--a); } }
@keyframes fl-mueve-b { from { bottom: var(--de); } to { bottom: var(--a); } }
@keyframes fl-alt-a { from { height: var(--de); } to { height: var(--a); } }
@keyframes fl-alt-b { from { height: var(--de); } to { height: var(--a); } }
.__C__ .fl-barras.sigue-a .corte { animation: fl-mueve-a .6s cubic-bezier(.22, 1, .36, 1) both; }
.__C__ .fl-barras.sigue-b .corte { animation: fl-mueve-b .6s cubic-bezier(.22, 1, .36, 1) both; }
.__C__ .fl-barras.sigue-a .fl-b { animation: fl-alt-a .6s cubic-bezier(.22, 1, .36, 1) both; }
.__C__ .fl-barras.sigue-b .fl-b { animation: fl-alt-b .6s cubic-bezier(.22, 1, .36, 1) both; }
/* Entrada de las barras: crecen desde la base, de izquierda a derecha (el retraso de cada una ya va en su style: i * .04 s).
   Solo cuando NO hay sigue-a/b (primera pintura o cambio de estadística/ventana); al mover la línea mandan fl-alt-a/b.
   fill-mode «backwards»: al terminar no deja un transform fijo, así el :hover (elevar la barra) sigue funcionando. */
@keyframes fl-crece { from { transform: scaleY(0); opacity: 0; } 60% { opacity: 1; } to { transform: scaleY(1); opacity: 1; } }
.__C__ .fl-barras:not(.sigue-a):not(.sigue-b) .fl-b { transform-origin: 50% 100%; animation: fl-crece .6s cubic-bezier(.22, 1, .36, 1) backwards; }
@media (prefers-reduced-motion: reduce) { .__C__ .fl-barras .corte, .__C__ .fl-barras .fl-b { animation: none !important; } }
/* Resaltado al pasar el mouse (o enfocar con el teclado): la barra activa se enciende y las demás se atenúan.
   Sin :has() (navegadores antiguos) simplemente no se atenúan; la barra activa sigue elevándose. */
.__C__ .fl-b { transition: transform .2s ease, filter .25s ease, opacity .25s ease; }
.__C__ .fl-b:hover, .__C__ .fl-b:focus { filter: brightness(1.14) saturate(1.12); }
.__C__ .fl-barras:has(.fl-b:hover, .fl-b:focus) .fl-b:not(:hover):not(:focus) { opacity: .4; filter: saturate(.6); }

/* Medidor del %: se llena de izquierda a derecha y un brillo lo recorre de vez en cuando. */
@keyframes fl-llena { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes fl-brilla { 0%, 55% { transform: translateX(-130%) skewX(-20deg); } 100% { transform: translateX(380%) skewX(-20deg); } }
.__C__ .fl-meter i { position: relative; overflow: hidden; transform-origin: left center; animation: fl-llena 1s cubic-bezier(.22, 1, .36, 1) .2s backwards;
  box-shadow: 0 0 12px rgba(74, 222, 128, .45); }
.__C__ .fl-meter i::after { content: ""; position: absolute; top: 0; bottom: 0; left: 0; width: 35%; pointer-events: none;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .65), transparent); animation: fl-brilla 3.4s ease-in-out 1.3s infinite; }
@media (prefers-reduced-motion: reduce) { .__C__ .fl-meter i, .__C__ .fl-meter i::after { animation: none !important; } .__C__ .fl-b { transition: none; } }
/* Chip de la línea: pulso suave con box-shadow (el chip ya usa transform para centrarse, por eso no se escala). */
@keyframes fl-pulso-chip { 0%, 100% { box-shadow: 0 0 0 0 rgba(165, 180, 252, .55); } 50% { box-shadow: 0 0 0 7px rgba(165, 180, 252, 0); } }
.__C__ .fl-barras .corte .chip { animation: fl-pulso-chip 2.6s ease-in-out infinite; }

/* Foto: flotación mínima (4 px, 7 s). */
@keyframes fl-flota { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
.__C__ .fl-foto { animation: fl-flota 7s ease-in-out infinite; will-change: transform; }

/* Número grande de la línea: entrada suave al cargar y un «pop» breve cada vez que cambia la línea
   (a y b se alternan, igual que en las barras, para que la animación se reinicie aunque el elemento se reutilice). */
@keyframes fl-num-entra { from { opacity: 0; transform: translateY(12px) scale(.96); } to { opacity: 1; transform: none; } }
@keyframes fl-num-a { 0% { transform: scale(1.08); filter: brightness(1.35); } 100% { transform: none; filter: none; } }
@keyframes fl-num-b { 0% { transform: scale(1.08); filter: brightness(1.35); } 100% { transform: none; filter: none; } }
.__C__ .fl-linea { transform-origin: left center; animation: fl-num-entra .6s cubic-bezier(.22, 1, .36, 1) backwards; }
.__C__ .fl:has(.fl-barras.sigue-a) .fl-linea { animation: fl-num-a .35s ease-out; }
.__C__ .fl:has(.fl-barras.sigue-b) .fl-linea { animation: fl-num-b .35s ease-out; }
@media (prefers-reduced-motion: reduce) { .__C__ .fl-barras .corte .chip, .__C__ .fl-foto, .__C__ .fl-linea { animation: none !important; } }
/* Veredicto «Superó la línea en 7 de 10»: punto vivo cuando está en verde (clase .v). En rojo/neutro no lleva punto. */
@keyframes fl-punto { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .35; transform: scale(.7); } }
.__C__ .fl-cab span.v::before { content: ""; display: inline-block; width: 7px; height: 7px; margin-right: .5rem; border-radius: 50%; vertical-align: middle;
  background: #4ade80; box-shadow: 0 0 8px #4ade80; animation: fl-punto 1.6s ease-in-out infinite; }

/* Barras que superan la línea: halo verde sutil (las «borde» conservan su resplandor propio).
   Las que no la superan: algo más apagadas (sin opacity, que ya usa el resaltado al pasar el mouse). */
.__C__ .fl-b.ok:not(.borde) { box-shadow: 0 8px 22px -10px rgba(74, 222, 128, .55); }
/* (las que no superan la línea van en rojo: ver «No superó en rojo» más abajo) */

/* ===== Ajustes finos de alineación y legibilidad ===== */

/* 1. Etiquetas LADO / LÍNEA / CUOTA (y las de los demás grupos): misma altura exacta, con o sin el icono «?» de ayuda,
      para que queden en la misma línea y los controles de abajo (42 px) arranquen a la misma altura. */
.__C__.__C__ [data-testid="stWidgetLabel"] { height: 1.25rem; min-height: 1.25rem; margin-bottom: .3rem; display: flex; align-items: center; }
.__C__.__C__ [data-testid="stWidgetLabel"] p, .__C__.__C__ [data-testid="stWidgetLabel"] label { margin: 0 !important; line-height: 1.25rem !important; }
.__C__.__C__ [data-testid="stWidgetLabel"] [data-testid="stTooltipIcon"], .__C__.__C__ [data-testid="stTooltipHoverTarget"] { display: inline-flex; align-items: center; height: 1.25rem; }
.__C__ [data-testid="stTooltipIcon"] svg { color: rgba(255, 255, 255, .7) !important; }   /* el «?» de la cuota también se lee */

/* 2. HISTORIAL y SIMULACIÓN: los dos números comparten la misma línea base (la de la última línea de cada bloque),
      aunque uno sea más grande. Si el navegador no entiende «last baseline», queda el alineado abajo de siempre. */
.__C__ .fl-duo { align-items: flex-end; align-items: last baseline; }
.__C__ .fl-d b { display: block; line-height: 1; }

/* 3. Hueco bajo el nombre: con foto, el bloque «MÁS DE 30.5» se centra en la altura que deja libre la foto
      en vez de quedarse pegado abajo, lejos del nombre. (En móvil no hay hueco: se deja como estaba.) */
@media (min-width: 641px) {
  .__C__ .fl:has(.fl-foto) .fl-fila { align-items: center; }
}

/* 4. Chip de la línea: ya no se sale por la derecha. En pantallas estrechas pasa a ir justo encima de la raya, pegado al borde. */
.__C__ .fl-barras .corte .chip { right: -12px; }
@media (max-width: 640px) {
  .__C__ .fl-barras .corte .chip { right: 0; top: 0; transform: translateY(-115%); }
}

/* 5. Cuota: el valor de ejemplo (1.91) y lo que se escribe tienen más contraste. */
.__C__.__C__.__C__ [data-testid="stTextInput"] input { color: #fff !important; }
.__C__.__C__.__C__ [data-testid="stTextInput"] input::placeholder { color: rgba(255, 255, 255, .62) !important; opacity: 1 !important; font-weight: 600; }

/* ===== Chip +EV ===== */
.__C__ .fl-tags { display: flex; align-items: center; flex-wrap: wrap; gap: .55rem; }
@keyframes fl-latido-ev { 0%, 100% { box-shadow: 0 0 0 0 rgba(74, 222, 128, .5); } 50% { box-shadow: 0 0 0 6px rgba(74, 222, 128, 0); } }
.__C__ .fl-ev { font-size: .68rem; font-weight: 800; letter-spacing: .08em; padding: .2rem .6rem; border-radius: 999px; cursor: help; white-space: nowrap;
  color: #052e16; background: linear-gradient(135deg, #86efac, #4ade80); animation: fl-latido-ev 2.4s ease-in-out infinite; }
.__C__ .fl-ev.parcial { color: #422006; background: linear-gradient(135deg, #fde68a, #fbbf24); box-shadow: 0 0 14px rgba(251, 191, 36, .4); animation: none; }

/* ===== Robustez: aviso de pocos partidos, foco visible y contraste ===== */
.__C__ .fl-aviso { display: flex; align-items: flex-start; gap: .55rem; margin: .1rem 0 1rem; padding: .55rem .85rem; border-radius: 12px;
  font-size: .8rem; line-height: 1.4; color: #fde68a; background: rgba(251, 191, 36, .12); border: 1px solid rgba(251, 191, 36, .38); }
.__C__ .fl-aviso::before { content: "⚠"; flex: none; line-height: 1.4; }
.__C__ .fl-aviso b { color: #fef3c7; }
.__C__ .fl-pct small.fl-ic.poco, .__C__ .fl-pct small.fl-ic.poco b { color: #fde68a; }
.__C__ .fl:has(.fl-aviso) .fl-pct b { text-decoration: underline dotted rgba(251, 191, 36, .75); text-underline-offset: 7px; }

/* Teclado: las barras eran enfocables pero sin indicador (outline: none). Ahora se ve cuál está activa. */
.__C__ .fl-b:focus-visible { outline: 2px solid #c7d2fe; outline-offset: 3px; }

/* Contraste (texto pequeño sobre el fondo índigo; WCAG AA pide 4.5:1). El blanco al 50 % da ~3.7:1 en la zona más clara
   del degradado; al 70 % o más da ≥ 5.5:1. Los cuadritos de la leyenda también ganan borde para verse sin depender del color. */
.__C__ .fl-cab { color: rgba(255, 255, 255, .74); }
.__C__ .fl-cl { color: rgba(255, 255, 255, .78); }
.__C__ .fl-kc.no { background: rgba(255, 255, 255, .3); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .6); }
.__C__ .fl-kc.push { border-color: rgba(255, 255, 255, .7); }
.__C__ .fl-pct small.fl-ic, .__C__ .fl-pct small.fl-pd { color: rgba(255, 255, 255, .72); }
.__C__ .fl-pct small.fl-dl { color: rgba(255, 255, 255, .7); }
.__C__ .fl-leg { color: rgba(255, 255, 255, .74); }
.__C__ .fl-b:not(.ok):not(.stk) .df, .__C__ .fl-b.stk:not(.ok) .tot .df { color: rgba(226, 232, 255, .88); }

/* ===== Marcas de sede y BTB: más claras bajo los equipos y leyenda en «píldoras» ===== */
/* Bajo cada escudo: punto + letra (L / V) y chip BTB; si no caben (muchos partidos o móvil) se ve solo el punto */
.__C__.__C__ .fl-riv span.fl-mk { flex-wrap: wrap; row-gap: 2px; column-gap: 5px; }
.__C__.__C__ .fl-riv span.fl-mkp { display: inline-flex; flex: none; width: auto; align-items: center; gap: 3px; overflow: visible; white-space: nowrap;
  font-size: .6rem; line-height: 1; color: rgba(224, 231, 255, .92); }
.__C__.__C__ .fl-riv span.fl-mkp b { font-weight: 800; letter-spacing: .06em; font-size: .6rem; color: inherit; }

/* Leyenda del eje: cada marca en una píldora con borde fino */
.__C__ .fl-lg { gap: 8px; color: rgba(255, 255, 255, .78); }
.__C__ .fl-lg .fl-k { gap: 6px; padding: .16rem .6rem; border-radius: 999px; background: rgba(165, 180, 252, .1); border: 1px solid rgba(165, 180, 252, .3);
  color: #e0e7ff; cursor: help; }
.__C__ .fl-lg .fl-k b { font-weight: 800; letter-spacing: .1em; font-size: .62rem; }
.__C__ .fl-lg .fl-k.btb { padding: 0; background: none; border: 0; }
.__C__.__C__ .fl-lg .fl-b2b { font-size: .6rem; padding: .16rem .6rem; border-radius: 999px; line-height: 1.2; border: 1px solid rgba(251, 191, 36, .4); }
.__C__ .fl-eje { color: rgba(255, 255, 255, .62); }

/* ===== No superó en rojo ===== */
/* Barras simples que no cumplen: mismo estilo que las verdes pero en rojo (también las «borde», que traían un gris más claro) */
.__C__.__C__ .fl-b:not(.ok):not(.push):not(.stk) { background: linear-gradient(180deg, #fca5a5 0%, #f87171 100%); color: #450a0a; border: 0;
  box-shadow: 0 8px 22px -10px rgba(248, 113, 113, .5); }
.__C__.__C__ .fl-b:not(.ok):not(.push):not(.stk) .df { color: rgba(69, 10, 10, .78); }
/* Combinadas (barras apiladas): los segmentos conservan su color por componente; solo la diferencia sobre la barra pasa a rojo */
.__C__.__C__ .fl-b.stk:not(.ok) .tot .df { color: #fca5a5; }
/* Leyenda, veredicto, ponderado y tooltip */
.__C__.__C__ .fl-kc.no { background: linear-gradient(180deg, #fca5a5, #f87171); box-shadow: none; }
.__C__.__C__ .fl-cab .r { color: #fca5a5; }
.__C__.__C__ .fl-pct small.fl-pd b.r { color: #fca5a5; }
.__C__.__C__ .tt .tt-v.no span { color: #fca5a5; }

/* Movimiento reducido: todo el panel queda estático (las animaciones terminan al instante en su estado final). */
@media (prefers-reduced-motion: reduce) {
  .__C__ *, .__C__ *::before, .__C__ *::after { animation-duration: .001ms !important; animation-delay: 0s !important;
    animation-iteration-count: 1 !important; transition-duration: .001ms !important; scroll-behavior: auto !important; }
}



/* Barras justo al borde de la línea (la superan o se quedan cortas por solo 0,5): un tono algo más luminoso, un destello fino
   en el borde superior y un resplandor suave que cae por debajo, como una barra «elevada». Sin bordes ni cambios en las demás. */
.__C__ .fl-b.borde { position: relative; z-index: 1; }
.__C__ .fl-b.borde.ok { background: linear-gradient(180deg, #a7f3c4 0%, #4ade80 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .55), 0 10px 28px -8px rgba(74, 222, 128, .65); }
.__C__ .fl-b.borde:not(.ok) { background: rgba(255, 255, 255, .20); color: rgba(255, 255, 255, .95);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .35), 0 10px 26px -8px rgba(165, 180, 252, .55); }

/* Encabezado doble: Historial y Simulación lado a lado */
.__C__ .fl-duo { display: flex; justify-content: flex-end; align-items: flex-end; gap: 1.1rem; }
.__C__ .fl-d { text-align: right; }
.__C__ .fl-d.sim { padding-left: 1.1rem; border-left: 1px solid rgba(255, 255, 255, .14); cursor: help; }
.__C__ .fl-d.sim b { font-size: 2.4rem; color: #a5b4fc; }
.__C__ .fl-pct small.fl-dl { display: block; margin: 0 0 .2rem; font-size: .64rem; font-weight: 700; letter-spacing: .14em;
  text-transform: uppercase; color: rgba(255, 255, 255, .5); }
.__C__ .fl-d.sim small.fl-dl { color: rgba(165, 180, 252, .75); }

/* Rango probable junto al porcentaje */
.__C__ .fl-pct small.fl-ic { margin-top: .1rem; font-size: .76rem; color: rgba(255, 255, 255, .5); cursor: help; }
.__C__ .fl-pct small.fl-ic b { font-family: inherit; font-size: inherit; font-weight: 700; letter-spacing: 0; color: rgba(255, 255, 255, .78); }

/* Porcentaje ponderado y estadísticas de resumen */
.__C__ .fl-pct small.fl-pd { margin-top: .1rem; font-size: .76rem; color: rgba(255, 255, 255, .5); cursor: help; }
.__C__ .fl-pct small.fl-pd b { font-family: inherit; font-size: inherit; font-weight: 700; letter-spacing: 0; color: rgba(255, 255, 255, .78); }
.__C__ .fl-pct small.fl-pd b.v { color: #4ade80; } .__C__ .fl-pct small.fl-pd b.r { color: #f87171; }
.__C__ .fl-res { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin-top: 1.1rem; }
.__C__ .fl-rt { padding: .5rem .4rem; border-radius: 12px; background: rgba(255, 255, 255, .06); text-align: center; }
.__C__ .fl-rt small { display: block; font-size: .62rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: rgba(255, 255, 255, .5); }
.__C__ .fl-rt b { display: block; margin-top: .12rem; font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-size: 1.15rem; font-weight: 800; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.__C__ .fl-rt.v b { color: #4ade80; } .__C__ .fl-rt.r b { color: #f87171; }
.__C__ .fl-res-nota { margin-top: .45rem; font-size: .76rem; color: rgba(255, 255, 255, .55); }
.__C__ .fl-res-nota b { color: rgba(255, 255, 255, .88); }
@media (max-width: 520px) { .__C__ .fl-res { grid-template-columns: repeat(3, minmax(0, 1fr)); } }

/* Etiqueta en el extremo de la línea punteada: la línea actual, sin depender del número grande de arriba */
.__C__ .fl-barras .corte .chip { position: absolute; right: -18px; top: 0; transform: translateY(-50%); z-index: 4; padding: 2px 8px;
  border-radius: 999px; background: rgba(165, 180, 252, .96); color: #1e1b4b; font-size: .68rem; font-weight: 800; line-height: 1.25;
  letter-spacing: .01em; font-variant-numeric: tabular-nums; box-shadow: 0 3px 10px rgba(10, 12, 40, .45); }

/* Diferencia respecto a la línea dentro de cada barra (valor arriba, «+4.5» / «−2.5» debajo) */
.__C__ .fl-b { position: relative; outline: none; }
.__C__ .fl-b:hover, .__C__ .fl-b:focus { z-index: 30; }
.__C__ .fl-b:not(.stk) { flex-direction: column; gap: 1px; }
.__C__ .fl-b .vv { font-weight: 800; line-height: 1.1; }
.__C__ .fl-b .df { font-style: normal; font-size: .62rem; font-weight: 700; line-height: 1.1; letter-spacing: .01em; font-variant-numeric: tabular-nums; }
.__C__ .fl-b.ok:not(.stk) .df { color: rgba(5, 46, 22, .72); }
.__C__ .fl-b:not(.ok):not(.stk) .df { color: #fca5a5; }
.__C__ .fl-b.push .df { color: rgba(255, 255, 255, .7); }
.__C__ .fl-barras.denso .fl-b .df { font-size: .56rem; }

/* Tooltip propio (solo CSS: aparece con el mouse o al tocar la barra) */
.__C__ .fl-b .tt { position: absolute; bottom: calc(100% + 10px); left: 50%; z-index: 40; width: max-content; min-width: 150px; max-width: 230px;
  padding: .6rem .75rem .65rem; border-radius: 12px; text-align: left; font-weight: 500; font-size: .74rem; line-height: 1.35; letter-spacing: 0;
  color: rgba(255, 255, 255, .86); background: rgba(17, 15, 48, .97); border: 1px solid rgba(165, 180, 252, .3);
  box-shadow: 0 14px 34px -8px rgba(5, 5, 30, .75); pointer-events: none; visibility: hidden; opacity: 0;
  transform: translate(-50%, 4px); transition: opacity .15s ease, transform .15s ease, visibility .15s; }
.__C__ .fl-b.stk .tt { bottom: calc(100% + 40px); }
.__C__ .fl-b.tt-l .tt { left: 0; transform: translate(0, 4px); }
.__C__ .fl-b.tt-rt .tt { left: auto; right: 0; transform: translate(0, 4px); }
.__C__ .fl-b:hover .tt, .__C__ .fl-b:focus .tt { visibility: visible; opacity: 1; transform: translate(-50%, 0); }
.__C__ .fl-b.tt-l:hover .tt, .__C__ .fl-b.tt-l:focus .tt, .__C__ .fl-b.tt-rt:hover .tt, .__C__ .fl-b.tt-rt:focus .tt { transform: translate(0, 0); }
.__C__ .fl-b .tt::after { content: ""; position: absolute; top: 100%; left: 50%; width: 9px; height: 9px; margin: -5px 0 0 -4.5px; transform: rotate(45deg);
  background: rgba(17, 15, 48, .97); border-right: 1px solid rgba(165, 180, 252, .3); border-bottom: 1px solid rgba(165, 180, 252, .3); }
.__C__ .fl-b.tt-l .tt::after { left: 26px; } .__C__ .fl-b.tt-rt .tt::after { left: auto; right: 26px; margin-right: -4.5px; }
.__C__ .tt .tt-c { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: .15rem; }
.__C__ .tt .tt-f { font-size: .66rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: rgba(255, 255, 255, .55); }
.__C__ .tt .tt-po { padding: 0 6px; border-radius: 6px; font-size: .58rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
  color: #fde68a; background: rgba(251, 191, 36, .16); }
.__C__ .tt .tt-r { font-size: .86rem; font-weight: 800; color: #fff; }
.__C__ .tt .tt-x { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: .1rem; font-size: .72rem; color: rgba(255, 255, 255, .62); }
.__C__ .tt .tt-x .g { font-weight: 700; color: #86efac; } .__C__ .tt .tt-x .p { font-weight: 700; color: #fca5a5; }
.__C__ .tt .tt-v { margin-top: .5rem; padding-top: .45rem; border-top: 1px solid rgba(255, 255, 255, .12); }
.__C__ .tt .tt-v b { display: block; font-size: .8rem; font-weight: 800; color: #fff; }
.__C__ .tt .tt-v span { font-size: .8rem; font-weight: 800; font-variant-numeric: tabular-nums; }
.__C__ .tt .tt-v.ok span { color: #86efac; } .__C__ .tt .tt-v.no span { color: #fca5a5; } .__C__ .tt .tt-v.push span { color: rgba(255, 255, 255, .7); }
.__C__ .tt .tt-v em { display: block; margin-top: .05rem; font-style: normal; font-size: .68rem; color: rgba(255, 255, 255, .5); }
.__C__ .tt .tt-k { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: .45rem; font-size: .7rem; font-weight: 700; color: rgba(255, 255, 255, .75); }
.__C__ .tt .tt-k span { display: inline-flex; align-items: center; gap: 5px; }
.__C__ .tt .tt-k i { width: 8px; height: 8px; border-radius: 2px; }
.__C__ .tt .tt-q { display: grid; grid-template-columns: repeat(auto-fit, minmax(2.2rem, 1fr)); gap: 4px; margin-top: .4rem; }
.__C__ .tt .tt-q span { display: grid; justify-items: center; padding: .2rem 0 .25rem; border-radius: 8px; background: rgba(255, 255, 255, .07); line-height: 1.15; }
.__C__ .tt .tt-q small { font-size: .56rem; font-weight: 800; letter-spacing: .08em; color: rgba(255, 255, 255, .5); }
.__C__ .tt .tt-q b { font-size: .8rem; font-weight: 800; color: #fff; font-variant-numeric: tabular-nums; }
.__C__ .tt .tt-p { display: grid; gap: 5px; margin-top: .5rem; padding-top: .5rem; border-top: 1px solid rgba(255, 255, 255, .12); font-size: .72rem; }
.__C__ .tt .tt-p div { display: grid; grid-template-columns: 8px 1fr auto 3.6rem; align-items: center; column-gap: 8px; }
.__C__ .tt .tt-p span { font-weight: 700; color: rgba(255, 255, 255, .85); }
.__C__ .tt .tt-p em { font-style: normal; font-size: .68rem; color: rgba(255, 255, 255, .5); font-variant-numeric: tabular-nums; }
.__C__ .tt .tt-p b { text-align: right; font-weight: 800; color: #fff; font-variant-numeric: tabular-nums; }
.__C__ .tt .tt-p .cero { opacity: .38; }
.__C__ .tt .tt-p i { width: 8px; height: 8px; border-radius: 2px; }
.__C__ .tt .tt-p .d2 i { background: #38bdf8; } .__C__ .tt .tt-p .d3 i { background: #fbbf24; } .__C__ .tt .tt-p .tl i { background: #f472b6; }
.__C__ .tt .tt-k .pts i { background: #4ade80; } .__C__ .tt .tt-k .reb i { background: #38bdf8; } .__C__ .tt .tt-k .ast i { background: #a78bfa; }

/* Barras apiladas de las combinadas: un segmento por componente (PTS abajo, luego REB, luego AST).
   Superó la línea = colores vivos; no la superó = los mismos tonos apagados. El total va sobre la barra. */
.__C__ .fl-barras.apilada { margin-top: 30px; }
.__C__ .fl-b.stk { position: relative; overflow: visible; background: none !important; }
.__C__ .fl-b.stk .stkw { position: absolute; inset: 0; display: flex; flex-direction: column-reverse; border-radius: inherit; overflow: hidden; }
.__C__ .fl-b.stk .sg { min-height: 0; display: flex; align-items: center; justify-content: center; font-size: .64rem; font-weight: 800; line-height: 1; }
.__C__ .fl-b.stk .sg + .sg { box-shadow: inset 0 2px 0 rgba(20, 18, 60, .55); }
.__C__ .fl-b.stk .tot { position: absolute; left: 50%; bottom: calc(100% + 3px); transform: translateX(-50%); z-index: 3; padding: 2px 7px;
  border-radius: 8px; background: rgba(26, 23, 66, .86); color: rgba(255, 255, 255, .72); font-size: .8rem; font-weight: 800; white-space: nowrap;
  display: flex; flex-direction: column; align-items: center; line-height: 1.1; }
.__C__ .fl-b.stk.ok .tot .df { color: #86efac; } .__C__ .fl-b.stk:not(.ok) .tot .df { color: #fca5a5; }
.__C__ .fl-b.stk.ok .tot { color: #fff; }
.__C__ .fl-b.stk.ok .sg.pts { background: linear-gradient(180deg, #86efac, #4ade80); color: #052e16; }
.__C__ .fl-b.stk.ok .sg.reb { background: linear-gradient(180deg, #7dd3fc, #38bdf8); color: #082f49; }
.__C__ .fl-b.stk.ok .sg.ast { background: linear-gradient(180deg, #c4b5fd, #a78bfa); color: #2e1065; }
.__C__ .fl-b.stk:not(.ok) .sg.pts { background: rgba(74, 222, 128, .24); color: rgba(220, 252, 231, .9); }
.__C__ .fl-b.stk:not(.ok) .sg.reb { background: rgba(56, 189, 248, .24); color: rgba(224, 242, 254, .9); }
.__C__ .fl-b.stk:not(.ok) .sg.ast { background: rgba(167, 139, 250, .27); color: rgba(237, 233, 254, .9); }
.__C__ .fl-b.stk.borde .sg { filter: brightness(1.1) saturate(1.1); }
.__C__ .fl-barras.denso .fl-b.stk .sg { font-size: .56rem; }
.__C__ .fl-barras.denso .fl-b.stk .tot { font-size: .7rem; padding: 1px 4px; }
.__C__ .fl-leg { display: flex; justify-content: flex-end; gap: 14px; margin: -.15rem 0 .55rem; font-size: .66rem; font-weight: 700;
  letter-spacing: .1em; text-transform: uppercase; color: rgba(255, 255, 255, .55); }
.__C__ .fl-leg .k { display: inline-flex; align-items: center; gap: 6px; }
.__C__ .fl-leg .k i { width: 10px; height: 10px; border-radius: 3px; }
.__C__ .fl-leg .k.pts i { background: #4ade80; } .__C__ .fl-leg .k.reb i { background: #38bdf8; } .__C__ .fl-leg .k.ast i { background: #a78bfa; }

/* Valor frente a la cuota */
.__C__ .fl-vh { display: flex; align-items: baseline; justify-content: space-between; gap: .6rem; flex-wrap: wrap; margin-bottom: .55rem; }
.__C__ .fl-vh b { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-size: 1.02rem; font-weight: 800; letter-spacing: -.01em; }
.__C__ .fl-vh.v b { color: #4ade80; } .__C__ .fl-vh.r b { color: #f87171; } .__C__ .fl-vh.n b { color: rgba(255, 255, 255, .88); }
.__C__ .fl-vh span { font-size: .72rem; color: rgba(255, 255, 255, .5); font-variant-numeric: tabular-nums; }
.__C__ .fl-vt { border-radius: 12px; background: rgba(255, 255, 255, .05); overflow: hidden; }
.__C__ .fl-vr { display: grid; grid-template-columns: 1fr auto 6.5rem; align-items: center; gap: .5rem; padding: .5rem .75rem;
  font-size: .8rem; font-variant-numeric: tabular-nums; border-top: 1px solid rgba(255, 255, 255, .06); }
.__C__ .fl-vr:first-child { border-top: 0; }
.__C__ .fl-vr.hd { padding: .4rem .75rem; font-size: .6rem; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: rgba(255, 255, 255, .42); }
.__C__ .fl-vr > span:not(:first-child) { text-align: right; }
.__C__ .fl-vr > span:first-child { font-weight: 600; color: rgba(255, 255, 255, .82); }
.__C__ .fl-vr .d { font-weight: 700; color: rgba(255, 255, 255, .6); }
.__C__ .fl-vr.v .d { color: #4ade80; } .__C__ .fl-vr.r .d { color: #f87171; }
.__C__ .fl-vr .m { color: rgba(255, 255, 255, .55); }

/* Contexto del partido: marca de pocos minutos bajo cada barra, filtros y próximo rival */
.__C__ .fl-mins { display: flex; gap: 8px; margin-top: .3rem; height: .7rem; }
.__C__ .fl-mins.medio { gap: 6px; } .__C__ .fl-mins.denso { gap: 4px; }
.__C__ .fl-mins span { flex: 1; text-align: center; font-size: .6rem; line-height: .7rem; color: #fbbf24; cursor: help; }
.__C__ .fl-filtros-nota { margin: .2rem 0 .5rem; font-size: .76rem; color: rgba(255, 255, 255, .55); }
.__C__ .fl-filtros-nota b { color: #fbbf24; }
.__C__ .fl-px { margin-top: 1.1rem; padding-top: .9rem; border-top: 1px solid rgba(255, 255, 255, .09); }
.__C__ .fl-px-g { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.__C__ .fl-pt { padding: .55rem .6rem; border-radius: 12px; background: rgba(255, 255, 255, .06); text-align: center; }
.__C__ .fl-pt small { display: block; font-size: .62rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: rgba(255, 255, 255, .5); }
.__C__ .fl-pt b { display: block; margin: .15rem 0 .05rem; font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-size: 1.3rem; font-weight: 800; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.__C__ .fl-pt em { display: block; font-style: normal; font-size: .68rem; color: rgba(255, 255, 255, .5); }
.__C__ .fl-pt.v b { color: #4ade80; } .__C__ .fl-pt.r b { color: #f87171; }
.__C__ .fl-bajas { margin-top: .6rem; font-size: .76rem; color: rgba(255, 255, 255, .55); display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.__C__ .fl-bj { padding: .15rem .55rem; border-radius: 999px; background: rgba(248, 113, 113, .16); color: #fca5a5; font-weight: 600; cursor: help; }
.__C__ .fl-bj.dtd { background: rgba(251, 191, 36, .16); color: #fcd34d; }

/* Panel de análisis: tendencia por ventana y escalera de líneas */
.__C__ .fl-an { margin-top: 1.1rem; padding-top: .9rem; border-top: 1px solid rgba(255, 255, 255, .09); }
.__C__ .fl-an-t { display: flex; justify-content: space-between; align-items: baseline; gap: .8rem; margin: .2rem 0 .55rem;
  font-size: .68rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: rgba(255, 255, 255, .5); }
.__C__ .fl-an-t span { font-weight: 600; letter-spacing: .04em; text-transform: none; color: rgba(255, 255, 255, .42); }
.__C__ .fl-tend { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(74px, 1fr); gap: 8px; overflow-x: auto; margin-bottom: 1.1rem; padding-bottom: 2px; }
.__C__ .fl-tc { position: relative; padding: .55rem .6rem .7rem; border-radius: 12px; background: rgba(255, 255, 255, .06); text-align: center; overflow: hidden; }
.__C__ .fl-tc.act { background: rgba(165, 180, 252, .16); }
.__C__ .fl-tc small { display: block; font-size: .62rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: rgba(255, 255, 255, .5); }
.__C__ .fl-tc b { display: block; margin: .15rem 0 .05rem; font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-size: 1.35rem; font-weight: 800; letter-spacing: -.02em; line-height: 1.1; font-variant-numeric: tabular-nums; }
.__C__ .fl-tc em { display: block; font-style: normal; font-size: .68rem; color: rgba(255, 255, 255, .5); }
.__C__ .fl-tc i { position: absolute; left: 0; bottom: 0; height: 3px; border-radius: 0 3px 0 0; background: rgba(255, 255, 255, .35); }
.__C__ .fl-tc.v b, .__C__ .fl-lc.v b { color: #4ade80; } .__C__ .fl-tc.v i, .__C__ .fl-lc.v i { background: #4ade80; }
.__C__ .fl-tc.r b, .__C__ .fl-lc.r b { color: #f87171; } .__C__ .fl-tc.r i, .__C__ .fl-lc.r i { background: #f87171; }
.__C__ .fl-lad { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(52px, 1fr); gap: 6px; overflow-x: auto; padding-bottom: 2px; }
.__C__ .fl-lc { position: relative; padding: .45rem .3rem .6rem; border-radius: 10px; background: rgba(255, 255, 255, .05); text-align: center; overflow: hidden; }
.__C__ .fl-lc.act { background: rgba(165, 180, 252, .2); box-shadow: inset 0 0 0 1px rgba(165, 180, 252, .55); }
.__C__ .fl-lc small { display: block; font-size: .7rem; font-weight: 700; color: rgba(255, 255, 255, .55); font-variant-numeric: tabular-nums; }
.__C__ .fl-lc.act small { color: #fff; }
.__C__ .fl-lc b { display: block; margin-top: .1rem; font-size: .95rem; font-weight: 800; font-variant-numeric: tabular-nums; }
.__C__ .fl-lc i { position: absolute; left: 0; right: 0; bottom: 0; width: auto !important; opacity: .18; border-radius: 0; background: rgba(255, 255, 255, .5); pointer-events: none; }
.__C__ .fl-an-nota { margin-top: .6rem; font-size: .76rem; color: rgba(255, 255, 255, .55); }
.__C__ .fl-an-nota b { color: rgba(255, 255, 255, .88); }
.__C__ .fl-barras.medio { gap: 6px; } .__C__ .fl-barras.denso { gap: 4px; }
.__C__ .fl-barras.denso .fl-b { font-size: .74rem; border-radius: 7px; }
.__C__ .fl-riv.medio { gap: 6px; } .__C__ .fl-riv.denso { gap: 4px; }
.__C__ .fl-riv.denso span.fl-esc i { font-size: .55rem; letter-spacing: .02em; }
@media (max-width: 900px) {
  .__C__ .fl-riv.denso span.fl-esc i, .__C__ .fl-riv.medio span.fl-esc i { display: none; }
  .__C__ .fl-riv.denso span.fl-esc img { width: clamp(12px, 92%, 28px); padding: 2px; }
  .__C__ .fl-barras.denso .fl-b { font-size: .6rem; }
}

/* Significado de los colores: el rojo se reserva para nada. «Más de / Menos de» es solo el lado elegido (neutro), y lo que no cumple va
   en gris suave, no en rojo. Verde = cumplió la línea, gris = no. La leyenda va junto al título de las barras. */
.__C__ .fl-tag.si, .__C__ .fl-tag.no { color: #a5b4fc; }
.__C__ .fl-cab .r { color: rgba(203, 213, 245, .68); }
.__C__ .fl-pct small.fl-pd b.r { color: rgba(203, 213, 245, .85); }
.__C__ .fl-b:not(.ok):not(.stk) .df, .__C__ .fl-b.stk:not(.ok) .tot .df { color: rgba(203, 213, 245, .62); }
.__C__ .tt .tt-v.no span { color: rgba(203, 213, 245, .78); }
.__C__ .fl-cl { display: inline-flex; align-items: center; gap: 6px; margin-left: 1.1rem; font-size: .66rem; font-weight: 600; letter-spacing: .06em;
  text-transform: none; color: rgba(255, 255, 255, .5); white-space: nowrap; }
.__C__ .fl-cl .fl-kc + .fl-kc, .__C__ .fl-cl .fl-kc:not(:first-child) { margin-left: .5rem; }
.__C__ .fl-kc { display: inline-block; flex: none; width: 10px; height: 10px; border-radius: 3px; box-sizing: border-box; }
.__C__ .fl-kc.ok { background: linear-gradient(180deg, #86efac, #4ade80); }
.__C__ .fl-kc.no { background: rgba(255, 255, 255, .2); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .22); }
.__C__ .fl-kc.push { border: 1.5px dashed rgba(255, 255, 255, .5); }

/* Eje de tiempo y marcas de contexto (local / visita / back-to-back) */
.__C__ .fl-eje { display: flex; align-items: center; gap: .6rem; margin-top: .65rem; font-size: .62rem; font-weight: 700;
  letter-spacing: .12em; text-transform: uppercase; color: rgba(255, 255, 255, .42); white-space: nowrap; }
.__C__ .fl-ln { position: relative; flex: 1 1 0; min-width: 12px; height: 1px; background: linear-gradient(90deg, rgba(165, 180, 252, .06), rgba(165, 180, 252, .4)); }
.__C__ .fl-ln.fin { background: linear-gradient(90deg, rgba(165, 180, 252, .4), rgba(165, 180, 252, .6)); }
.__C__ .fl-ln.fin::after { content: ""; position: absolute; right: 0; top: -3px; width: 6px; height: 6px; transform: rotate(45deg);
  border-top: 1px solid rgba(165, 180, 252, .75); border-right: 1px solid rgba(165, 180, 252, .75); }
.__C__ .fl-lg { display: inline-flex; align-items: center; gap: 12px; letter-spacing: .06em; font-weight: 600; color: rgba(255, 255, 255, .5); }
.__C__ .fl-lg .fl-k { display: inline-flex; align-items: center; gap: 5px; }
.__C__.__C__ .fl-sd { display: inline-block; flex: none; width: 7px; height: 7px; border-radius: 50%; box-sizing: border-box; }
.__C__.__C__ .fl-sd.l { background: rgba(165, 180, 252, .92); }
.__C__.__C__ .fl-sd.v { border: 1.5px solid rgba(165, 180, 252, .88); }
.__C__.__C__ .fl-b2b { flex: none; padding: 0 4px; border-radius: 5px; font-size: .5rem; font-weight: 800; letter-spacing: .06em; line-height: 1.6;
  color: #fde68a; background: rgba(251, 191, 36, .16); }
/* dentro de .fl-riv la regla base «.fl-riv span» (flex:1, texto pequeño) alcanza a los span anidados: se neutraliza aquí */
.__C__.__C__ .fl-riv span.fl-mk { display: flex; flex: none; align-items: center; justify-content: center; gap: 4px; min-height: 12px;
  width: auto; overflow: visible; white-space: nowrap; }
.__C__.__C__ .fl-riv .fl-esc .fl-mk .fl-sd, .__C__.__C__ .fl-riv .fl-esc .fl-mk .fl-b2b { flex: none; }
.__C__.__C__ .fl-riv.denso .fl-b2b { font-size: .44rem; padding: 0 3px; }
.__C__ .tt .tt-x .rb { font-weight: 700; color: #fde68a; }
@media (max-width: 640px) { .__C__ .fl-eje .fl-ln { display: none; } .__C__ .fl-eje { justify-content: space-between; gap: .4rem; font-size: .56rem; letter-spacing: .06em; } }

/* Foto y porcentaje: la foto conserva su tamaño y su aspecto de siempre; en las tarjetas con foto, el bloque del porcentaje
   baja lo justo para empezar donde la foto ya se ha desvanecido. Sin cajas ni degradados detrás: el número queda limpio
   sobre el fondo y nunca sobre la camiseta. */
.__C__ .fl-foto { -webkit-mask-image: linear-gradient(90deg, transparent, #000 40%), linear-gradient(180deg, #000 58%, transparent 90%);
  mask-image: linear-gradient(90deg, transparent, #000 40%), linear-gradient(180deg, #000 58%, transparent 90%);
  -webkit-mask-composite: source-in; mask-composite: intersect; }   /* mismo recorte de siempre, con el desvanecido inferior un poco más corto */
.__C__ .fl:has(.fl-foto) .fl-fila { margin-top: calc(1.3rem + 60px); }
.__C__ .fl:has(.fl-foto) .fl-pct b { text-shadow: 0 2px 12px rgba(10, 8, 40, .55); }
@media (max-width: 640px) {   /* móvil: foto más chica y el nombre se ajusta a su lado, sin pasar por debajo de ella */
  .__C__ .fl-foto { height: 108px; }
  .__C__ .fl:has(.fl-foto) .fl-nombre { font-size: 1.9rem; padding-right: 92px; }
  .__C__ .fl:has(.fl-foto) .fl-ctx { padding-right: 92px; }
  .__C__ .fl:has(.fl-foto) .fl-fila { margin-top: 1.1rem; }
}

/* Encabezado en chips: estadística destacada + datos del jugador */
.__C__ .fl-ctx { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem .45rem; margin-top: .35rem; }
.__C__ .fl-chip { display: inline-flex; align-items: center; padding: .22rem .65rem; border-radius: 999px; font-size: .78rem; font-weight: 700;
  letter-spacing: .01em; color: rgba(255, 255, 255, .9); background: rgba(255, 255, 255, .09); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .14); }
.__C__ .fl-chip-eq { margin-left: -.25rem; padding: .22rem .2rem; font-size: .95rem; font-weight: 800; letter-spacing: .06em; color: #fff; background: transparent; box-shadow: none; }
.__C__ .fl-chip-stat { font-size: .8rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; color: #fff;
  background: linear-gradient(135deg, #6366f1, #a855f7); box-shadow: 0 6px 18px -4px rgba(139, 92, 246, .75); }
.__C__ .fl-chip-rival { color: #fde68a; background: rgba(251, 191, 36, .14); box-shadow: inset 0 0 0 1px rgba(251, 191, 36, .4); }
.__C__ .fl-chip-n { color: rgba(255, 255, 255, .62); font-weight: 600; background: transparent; box-shadow: none; padding-left: .2rem; }

/* escudo del equipo del jugador, junto al texto de contexto */
.__C__ .fl-ctx.fl-ctx-logo { display: flex; align-items: center; gap: .6rem; }
.__C__ .fl-ctx .fl-logo-eq { width: 30px; height: 30px; flex: none; object-fit: contain; padding: 3px; border-radius: 50%;
  background: rgba(255,255,255,.94); box-shadow: 0 4px 10px rgba(2,6,23,.35), inset 0 0 0 1px rgba(15,23,42,.06); }

/* escudos de los rivales bajo cada barra */
.__C__ .fl-riv { align-items: flex-start; margin-top: .55rem !important; }
.__C__ .fl-riv span.fl-esc { display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 0; }
.__C__ .fl-riv span.fl-esc img { width: clamp(20px, 78%, 34px); aspect-ratio: 1; object-fit: contain; padding: 3px; border-radius: 50%;
  background: rgba(255,255,255,.94); box-shadow: 0 4px 10px rgba(2,6,23,.35), inset 0 0 0 1px rgba(15,23,42,.06);
  transition: transform .2s ease; }
.__C__ .fl-riv span.fl-esc:hover img { transform: translateY(-2px) scale(1.06); }
.__C__ .fl-riv span.fl-esc i { font-style: normal; font-size: .6rem; font-weight: 700; letter-spacing: .06em; white-space: nowrap;
  color: rgba(205,213,245,.62); }
@media (max-width: 640px) { .__C__ .fl-riv span.fl-esc i { font-size: .5rem; letter-spacing: 0; } }

/* ===== Marcas L / V / BTB: etiquetas pequeñas y sobrias, en tonos apagados (local = verde azulado suave, visita = lavanda con borde, BTB = arena) ===== */
.__C__.__C__ .fl-riv span.fl-mk { column-gap: 3px; row-gap: 3px; min-height: 14px; }
.__C__.__C__ .fl-riv span.fl-mkp, .__C__.__C__ .fl-lg .fl-mkp { display: inline-flex; flex: none; width: auto; align-items: center; justify-content: center;
  min-width: 15px; height: 14px; padding: 0 4px; border-radius: 5px; box-sizing: border-box; line-height: 1; font-size: .56rem; box-shadow: none; }
.__C__.__C__ .fl-riv span.fl-mkp b, .__C__.__C__ .fl-lg .fl-mkp b { display: inline; font-size: .56rem; font-weight: 700; letter-spacing: .05em; color: inherit; }
.__C__.__C__ .fl-mkp.l { color: #a8d5cf; background: rgba(125, 190, 180, .14); border: 1px solid rgba(125, 190, 180, .3); }
.__C__.__C__ .fl-mkp.v { color: #bdb9de; background: transparent; border: 1px solid rgba(180, 175, 225, .32); }
.__C__.__C__ .fl-riv span.fl-mk .fl-b2b, .__C__.__C__ .fl-lg .fl-b2b { height: 14px; display: inline-flex; align-items: center; padding: 0 4px; border-radius: 5px;
  font-size: .54rem; font-weight: 700; letter-spacing: .05em; box-sizing: border-box; color: #d9c898; background: rgba(214, 192, 140, .12);
  border: 1px solid rgba(214, 192, 140, .3); box-shadow: none; }
.__C__.__C__ .fl-riv.denso .fl-b2b { font-size: .5rem; padding: 0 3px; }
.__C__.__C__ .fl-riv.denso span.fl-mkp { min-width: 13px; padding: 0 3px; }
.__C__.__C__ .fl-lg { gap: 16px; }
.__C__.__C__ .fl-lg .fl-k, .__C__.__C__ .fl-lg .fl-k.btb { display: inline-flex; align-items: center; gap: 6px; padding: 0; background: none; border: 0;
  font-size: .6rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: rgba(255, 255, 255, .5); }
@media (max-width: 640px) { .__C__.__C__ .fl-lg .fl-k { font-size: 0; gap: 0; } .__C__.__C__ .fl-lg .fl-k .fl-mkp, .__C__.__C__ .fl-lg .fl-k .fl-b2b { font-size: .54rem; } }
</style>
"""


_RIVAL = re.compile(r"^(vs|@)\s+([A-Za-z]{2,5})$")


def _html_marcas(sede, descanso):
    """Marcas bajo el escudo, siempre con letra: «L» (píldora cian llena) = local, «V» (píldora violeta con borde) = visita, «BTB» = back-to-back."""
    partes = []
    if sede == "Local":
        partes.append('<span class="fl-mkp l" title="Local: jugó en casa"><b>L</b></span>')
    elif sede == "Visita":
        partes.append('<span class="fl-mkp v" title="Visita: jugó fuera"><b>V</b></span>')
    if descanso == 0:
        partes.append('<span class="fl-b2b" title="Back-to-back: jugó el día anterior">BTB</span>')
    return f'<span class="fl-mk">{"".join(partes)}</span>' if partes else ""


def _tile_vs(titulo, d, mas, unidad=""):
    """Casilla del próximo rival: verde si favorece al lado elegido, rojo si lo perjudica.

    d = {"valor", "liga"?, "rank"?, "rel"?, "nota"?}. Con "rel": True el valor ya es una diferencia en % frente al promedio
    (p. ej. +4 = concede un 4 % más); si no, se compara con "liga" (promedio de la liga)."""
    if not isinstance(d, dict) or d.get("valor") is None:
        return ""
    v, liga, rank = float(d["valor"]), d.get("liga"), d.get("rank")
    sub, cl = [], ""
    if d.get("rel"):
        sub.append("frente al promedio")
        if abs(v) >= 1:
            cl = "v" if (v > 0) == bool(mas) else "r"
        texto = f"{v:+.0f}%".replace("-", "−")
    else:
        texto = f"{v:.1f}{unidad}"
        if liga is not None:
            delta = v - float(liga)
            sub.append(f"liga {float(liga):.1f} · {delta:+.1f}")
            if abs(delta) >= 0.01 * max(abs(float(liga)), 1e-9):   # diferencia de al menos 1 % frente a la liga
                cl = "v" if (delta > 0) == bool(mas) else "r"
    if d.get("nota"):
        sub.append(str(d["nota"]))
    if rank:
        sub.append(f"#{int(rank)}")
    return f'<div class="fl-pt {cl}"><small>{_e(titulo)}</small><b>{_e(texto)}</b><em>{_e(" · ".join(sub))}</em></div>'


def _chips_bajas(bajas):
    out = []
    for b in sorted(bajas or [], key=lambda b: (str(b.get("Estado")).lower() not in _ESTADOS_OUT, str(b.get("Jugador")))):
        est = str(b.get("Estado") or "?")
        cl = "" if est.lower() in _ESTADOS_OUT else " dtd"
        out.append(f'<span class="fl-bj{cl}" title="{_e(str(b.get("Lesión") or ""))}">{_e(str(b.get("Jugador") or "?"))} · {_e(est)}</span>')
    return "".join(out)


def _html_proximo(px, stat, etiqueta_stat, mas, escudo=None):
    """Panel «Próximo rival»: lo que concede de la estadística elegida, su ritmo y las bajas (Out y Day-To-Day). "" si no hay datos."""
    if not isinstance(px, dict) or not str(px.get("rival") or "").strip():
        return ""
    rival = str(px["rival"]).strip()
    sede = str(px.get("sede") or "").strip()
    conc = px.get("concede") or {}
    d_conc = conc.get(stat) if isinstance(conc, dict) and stat in conc else (conc if isinstance(conc, dict) and "valor" in conc else None)
    tiles = _tile_vs(f"Concede · {etiqueta_stat}", d_conc, mas) + _tile_vs("Ritmo (posesiones)", px.get("ritmo"), mas)
    bajas = _chips_bajas(px.get("bajas"))
    propias = _chips_bajas(px.get("bajas_equipo"))
    if not (tiles or bajas or propias):
        return ""
    cuerpo = f'<div class="fl-px-g">{tiles}</div>' if tiles else ""
    if bajas:
        cuerpo += f'<div class="fl-bajas"><span>Bajas del rival:</span>{bajas}</div>'
    if propias:
        cuerpo += f'<div class="fl-bajas"><span>Bajas de su equipo:</span>{propias}</div>'
    cuerpo += ('<div class="fl-an-nota">Verde = favorece al lado elegido '
               '(más de: el rival concede más / juega más rápido; menos de: al revés).</div>')
    return f'<div class="fl-px"><div class="fl-an-t">Próximo rival<span>{_e((sede + " " + rival.upper()).strip())}</span></div>{cuerpo}</div>'


def _etiqueta_rival(corto, largo, escudo, marcas=""):
    """Una columna bajo la barra: escudo en una chapa clara, y debajo la sede y la sigla (más las marcas). Sin escudo, solo el texto."""
    m = _RIVAL.match(corto.strip())
    url = _url_segura(escudo(m.group(2))) if (escudo and m) else ""
    if not url:
        if marcas:
            return f'<span class="fl-esc" title="{_e(largo)}"><i>{_e(corto)}</i>{marcas}</span>'
        return f"<span>{_e(corto)}</span>"
    return (f'<span class="fl-esc" title="{_e(largo)}"><img src="{_e(url)}" alt="{_e(m.group(2))}" loading="lazy">'
            f'<i>{_e(m.group(1))} {_e(m.group(2).upper())}</i>{marcas}</span>')


# Estadísticas del selector, en dos grupos (el orden es el de los chips)
_BASICAS = ("PTS", "REB", "AST", "3PM", "STL", "BLK")
_COMBINADAS = ("REB+AST", "PTS+REB", "PTS+AST", "P+R+A")


def _elegir_stat(key, grupo):
    """Callback de los dos radios de estadística: la elegida pasa a «{key}_stat» y el otro grupo se vacía."""
    elegido = st.session_state.get(f"{key}_stat_{grupo}")
    if elegido is not None:
        st.session_state[f"{key}_stat"] = elegido
        st.session_state[f"{key}_stat_{'c' if grupo == 'b' else 'b'}"] = None


def _dibujar(nom, series, rivales, nombre, foto_url, contexto, key, ultimos, buscador, escudo=None, logo_equipo=None, ventanas=(), historico=None, simulacion=None, detalles=None, partidos=None, proximo=None):
    """Buscador (si hay), controles y tarjeta, todo dentro del contenedor."""
    if buscador:
        buscador()

    # Fila 1: estadística (en dos grupos) y últimos partidos. Fila 2: lado, línea y cuota. Cada grupo cabe en una sola línea.
    c_bas, c_com, cv = st.columns([3.6, 3.9, 2.0], vertical_alignment="bottom")
    c2, c3, c4, _ = st.columns([1.7, 1, 1, 3.5], vertical_alignment="bottom")
    if not ventanas:
        cv = None
    cont_f = st.container()   # fila de filtros de contexto, justo debajo de los controles
    # Estadística: dos radios (Básicas / Combinadas) con UNA sola elección. La clave «{key}_stat» guarda la elegida (la lee
    # nba_jugadores antes de dibujar la tarjeta) y un callback vacía el otro grupo al elegir en uno.
    basicas = [c for c in _BASICAS if c in series]
    combinadas = [c for c in _COMBINADAS if c in series]
    basicas += [c for c in series if c not in basicas and c not in combinadas]     # cualquier otra estadística, con las básicas
    sk_stat = f"{key}_stat"
    stat = st.session_state.get(sk_stat)
    if stat not in series:
        stat = (basicas + combinadas)[0]
    st.session_state[sk_stat] = stat
    for g, lista, col, titulo in (("b", basicas, c_bas, "Básicas"), ("c", combinadas, c_com, "Combinadas")):
        if not lista:
            continue
        st.session_state[f"{sk_stat}_{g}"] = stat if stat in lista else None
        col.radio(titulo, lista, index=None, horizontal=True, key=f"{sk_stat}_{g}", on_change=_elegir_stat, args=(key, g),
                  format_func=lambda c: ETIQ_RADIO.get(c, c))
    ventana = 0
    if cv is not None:
        if st.session_state.get(f"{key}_vent") not in ventanas:
            st.session_state.pop(f"{key}_vent", None)
        ventana = cv.radio("Últimos partidos", list(ventanas), index=ventanas.index(10) if 10 in ventanas else 0,
                           horizontal=True, key=f"{key}_vent")
    valores = series[stat][-ventana:] if ventana else series[stat]

    # ---- Contexto del partido: rivales, detalles y filtros, todo alineado con la ventana elegida
    n0 = len(valores)
    riv = [_corto_largo(r) for r in _riv_stat(rivales, stat)][-n0:]
    if len(riv) != n0:   # sin rivales, o desalineados con la serie: mejor nada que una etiqueta equivocada
        riv = []
    ctx_l, det_lista = unificar_contexto(partidos, detalles, riv, n0)
    desglose = desglose_combinada(stat, series, n0)          # combinadas: una lista de segmentos por partido
    pocos, umbral_min = pocos_minutos(ctx_l)
    filtros = {}
    disp = [c for c, (_, ops) in _FILTROS.items() if any(f(p) is not None for p in ctx_l for _, f in ops)]
    if disp:
        with cont_f:
            for col_f, c in zip(st.columns(len(disp)), disp):
                filtros[c] = col_f.selectbox(_FILTROS[c][0], ["Todos"] + [o for o, _ in _FILTROS[c][1]], key=f"{key}_f_{c}")
    mascara = filtrar_partidos(ctx_l, filtros)
    filtrado = not all(mascara)
    if filtrado:
        if not any(mascara):
            st.info("Ningún partido cumple los filtros elegidos.")
            return
        sel = lambda lst: [x for x, m in zip(lst, mascara) if m]   # noqa: E731
        valores, ctx_l, det_lista, pocos = sel(valores), sel(ctx_l), sel(det_lista), sel(pocos)
        riv = sel(riv) if riv else []
        desglose = sel(desglose) if desglose else None
        if desglose is not None and not any(x is not None for x in desglose):
            desglose = None
    lado = c2.radio("Lado", ["Más de", "Menos de"], horizontal=True, key=f"{key}_lado")
    # la línea siempre termina en .5 (como las casas de apuestas) y «+» / «−» no la sacan de ahí
    sugerida = min(max(math.floor(median(valores)) + 0.5, 0.5), 399.5)
    wk = f"{key}_linea_{stat}"
    if wk in st.session_state:   # un valor guardado antes (p. ej. 7.0) se corrige también en pantalla
        st.session_state[wk] = _a_medio(st.session_state[wk])
    linea = c3.number_input("Línea", 0.5, 399.5, float(sugerida), 1.0, format="%.1f", key=wk,
                            on_change=_ajusta_medio, args=(wk,))
    # Cuota de la casa: una por estadística y lado (cada mercado tiene la suya). Vacía = sin análisis de valor.
    cuota_txt = c4.text_input("Cuota", key=f"{key}_cuota_{stat}_{'mas' if lado == 'Más de' else 'menos'}", placeholder="1.91",
                              help="Cuota decimal de la casa para esta línea y lado (por ejemplo 1.91). "
                                   "Convierte la cuota en probabilidad implícita y la compara con el historial, el ponderado y la simulación.")
    linea = _a_medio(linea)

    mas = lado == "Más de"
    estados, k, n_validos, pct = evaluar(valores, linea, mas)
    n, pushes = len(valores), len(valores) - n_validos

    tope = max(max(valores), linea, 1) * 1.08

    # Animación al mover la línea: se recuerda dónde estaban la línea y las barras en el dibujo anterior de esta tarjeta.
    # Si la serie es la misma (solo cambió la línea o el lado), la línea punteada se desliza de su altura vieja a la nueva;
    # si cambió la serie (otra estadística o ventana), las barras entran como siempre.
    alturas = [max(v / tope * 100, 0) for v in valores]
    corte = linea / tope * 100
    sk = f"{key}_graf_prev"
    ctx_graf = (stat, ventana, tuple(valores))
    prev = st.session_state.get(sk)
    sigue = bool(prev) and prev["ctx"] == ctx_graf and len(prev["alturas"]) == len(alturas)
    par = 1 - prev["par"] if prev else 0
    st.session_state[sk] = {"ctx": ctx_graf, "corte": corte, "alturas": alturas, "par": par}
    de_corte = prev["corte"] if sigue else corte
    clase_sigue = f" sigue-{'ab'[par]}" if sigue else ""

    def _estilo_barra(i, h):
        if sigue:
            return f"height:{h:.0f}%;--de:{prev['alturas'][i]:.0f}%;--a:{h:.0f}%"
        return f"height:{h:.0f}%;animation-delay:{i * .04:.2f}s"

    # (el desglose de las combinadas ya se calculó arriba, alineado con la ventana y los filtros)

    nombre_stat = nom.get(stat, stat)

    def _tooltip(i, v, e, seg):
        """Tooltip propio (solo CSS): fecha, rival, resultado, minutos, valor frente a la línea y, si hay, el desglose."""
        det = det_lista[i]
        cab = f'<span class="tt-f">{_e(fecha_corta(det.get("fecha")))}</span>' if fecha_corta(det.get("fecha")) else ""
        if det.get("fase") == "Playoffs":
            cab += '<span class="tt-po">Playoffs</span>'
        if det.get("rival"):
            rival = f'{"vs" if det.get("sede") == "Local" else "@" if det.get("sede") == "Visita" else "vs"} {det["rival"]}'
        else:
            rival = riv[i][1] if riv else ""
        filas = []
        if cab:
            filas.append(f'<div class="tt-c">{cab}</div>')
        if rival:
            filas.append(f'<div class="tt-r">{_e(rival)}</div>')
        extra = []
        if det.get("resultado"):
            extra.append(f'<span class="{"g" if det.get("gano") else "p" if det.get("gano") is False else ""}">{_e(det["resultado"])}</span>')
        if det.get("minutos") is not None:
            m = round(float(det["minutos"]))
            extra.append(f'<span>Jugó {m} minuto{"s" if m != 1 else ""}</span>')
        if pocos[i]:
            extra.append('<span class="rb">Pocos minutos</span>')
        desc = det.get("descanso")
        if desc == 0:
            extra.append('<span class="rb">Back-to-back</span>')
        elif isinstance(desc, int) and desc > 0:
            extra.append(f'<span>{desc} día{"s" if desc != 1 else ""} de descanso</span>')
        if extra:
            filas.append(f'<div class="tt-x">{"".join(extra)}</div>')
        cuartos = det.get("cuartos")
        if cuartos:   # tiempo jugado en cada cuarto, en min:seg (el dato viene en segundos) (C1…C4 y, si hubo, TP1, TP2…)
            etq = [f"C{k + 1}" if k < 4 else f"TP{k - 3}" for k in range(len(cuartos))]
            filas.append('<div class="tt-q">' + "".join(
                f'<span><small>{t}</small><b>{int(c) // 60}:{int(c) % 60:02d}</b></span>' for t, c in zip(etq, cuartos)) + "</div>")
        sing, plur = _UNIDAD.get(stat, (nombre_stat.lower(), nombre_stat.lower()))
        filas.append(f'<div class="tt-v {e}"><span>Hizo {v:g} {sing if v == 1 else plur}</span></div>')
        anot = det.get("anotacion") if stat == "PTS" else None
        if anot:   # de dónde salieron los puntos: dobles (×2), triples (×3) y tiros libres (×1)
            etq = (("dobles", "Dobles", "d2", 2), ("triples", "Triples", "d3", 3), ("libres", "Tiros libres", "tl", 1))
            filas.append('<div class="tt-p">' + "".join(
                f'<div class="{c}{" cero" if anot[k][0] == 0 else ""}"><i></i><span>{n}</span>'
                f'<em>{anot[k][0]:g}/{m}</em><b>{anot[k][1]:g} pts</b></div>'
                for k, n, c, m in etq if k in anot) + "</div>")
        if seg:
            filas.append('<div class="tt-k">' + "".join(
                f'<span class="{c.lower()}"><i></i>{c} {x:g}</span>' for c, x in seg) + "</div>")
        return f'<div class="tt">{"".join(filas)}</div>'

    def _aria(i, v, e):
        """Texto que lee un lector de pantalla para cada barra: partido, valor, diferencia con la línea y veredicto."""
        det = det_lista[i]
        cuando = ", ".join(x for x in (fecha_corta(det.get("fecha")), det.get("rival") or (riv[i][1] if riv else "")) if x)
        ver = {"ok": "superó la línea" if mas else "quedó bajo la línea", "push": "empate con la línea",
               "no": "no superó la línea" if mas else "no quedó bajo la línea"}[e]
        return f"Partido {i + 1} de {n}{f' ({cuando})' if cuando else ''}: {v:g} {nombre_stat.lower()}, {fmt_dif(v - linea)} frente a la línea {linea:g}; {ver}."

    def _barra(i, v, e):
        clase_b = f'fl-b {"" if e == "no" else e}{" borde" if abs(v - linea) <= 0.5 + 1e-9 else ""}'
        lado_tt = "tt-l" if i < min(2, n // 2) else ("tt-rt" if i >= n - min(2, n // 2) else "")
        dif = f'<i class="df">{fmt_dif(v - linea)}</i>'
        seg = desglose[i] if desglose else None
        if seg and e != "push" and v > 0:
            total = sum(x for _, x in seg)
            segs = "".join(
                f'<span class="sg {c.lower()}" style="flex:{x:g}">{f"{x:g}" if x / total >= _SEG_MIN else ""}</span>'
                for c, x in seg if x > 0)
            return (f'<div class="{clase_b} stk {lado_tt}" tabindex="0" role="img" aria-label="{_e(_aria(i, v, e))}" style="{_estilo_barra(i, alturas[i])}">'
                    f'<span class="tot"><b>{v:g}</b>{dif}</span><div class="stkw">{segs}</div>{_tooltip(i, v, e, seg)}</div>')
        return (f'<div class="{clase_b} {lado_tt}" tabindex="0" role="img" aria-label="{_e(_aria(i, v, e))}" style="{_estilo_barra(i, alturas[i])}">'
                f'<b class="vv">{v:g}</b>{dif}{_tooltip(i, v, e, None)}</div>')

    barras = "".join(_barra(i, v, e) for i, (v, e) in enumerate(zip(valores, estados)))
    leyenda = ('<div class="fl-leg">' + "".join(f'<span class="k {c.lower()}"><i></i>{c}</span>' for c in _COMPONENTES[stat])
               + "</div>") if desglose else ""
    denso = " denso" if n >= 15 else (" medio" if n > 10 else "")
    def _sede(i):
        """Local / Visita de la barra i: del detalle y, si no está, del «vs» / «@» de la etiqueta del rival."""
        s = det_lista[i].get("sede")
        if s in ("Local", "Visita"):
            return s
        m = _RIVAL.match(riv[i][0].strip()) if riv else None
        return None if not m else ("Local" if m.group(1) == "vs" else "Visita")

    sedes = [_sede(i) for i in range(n)] if riv else []
    descansos = [det_lista[i].get("descanso") for i in range(n)]
    etiquetas = (f'<div class="fl-riv{denso}">' + "".join(
        _etiqueta_rival(c, l, escudo, _html_marcas(sedes[i], descansos[i])) for i, (c, l) in enumerate(riv)) + "</div>") if riv else ""

    # Marca ● bajo cada barra de un partido con pocos minutos (para no leerlo como mala racha) y nota con el % sin esos partidos
    mins_html = (f'<div class="fl-mins{denso}">' + "".join(
        f'<span title="Jugó solo {ctx_l[i]["min"]:g} min (menos de {umbral_min:.0f}, el {_FRAC_POCOS_MIN:.0%} de sus minutos habituales)">●</span>'
        if pocos[i] else "<span></span>" for i in range(n)) + "</div>") if any(pocos) else ""
    nota_min = ""
    if any(pocos):
        sin = [v for v, x in zip(valores, pocos) if not x]
        n_p = n - len(sin)
        extra_min = ""
        if len(sin) >= 3:
            _, ks, ns_, ps = evaluar(sin, linea, mas)
            extra_min = f' Sin ellos: <b>{ps}%</b> ({ks} de {ns_}).'
        nota_min = (f'<div class="fl-res-nota"><span style="color:#fbbf24">●</span> {n_p} partido{"s" if n_p != 1 else ""} con pocos minutos '
                    f'(&lt; {umbral_min:.0f} min): no leas esas barras como mala racha.{extra_min}</div>')
    nota_filtro = ""
    rot_n = f"{n} de {n0} partidos (filtrados)" if filtrado else f"últimos {n} partidos"
    if filtrado:
        activos = ", ".join(o.lower() for o in filtros.values() if o != "Todos")
        nota_filtro = (f'<div class="fl-filtros-nota">Filtro activo: <b>{_e(activos)}</b> · {n} de {n0} partidos. '
                       f'La tendencia por ventana no usa el filtro.</div>')
    prox = _html_proximo(proximo, stat, nombre_stat, mas, escudo)

    leyenda_mk = ""

    # Eje de tiempo: del partido más antiguo (izquierda) al más reciente (derecha), con la leyenda de las marcas en medio
    if any(sedes):
        leyenda_mk += ('<span class="fl-k" title="Local: jugó en casa"><span class="fl-mkp l"><b>L</b></span>Local</span>'
                       '<span class="fl-k" title="Visita: jugó fuera"><span class="fl-mkp v"><b>V</b></span>Visita</span>')
    if any(d == 0 for d in descansos):
        leyenda_mk += '<span class="fl-k btb" title="BTB (back-to-back): jugó el día anterior"><span class="fl-b2b">BTB</span>Back-to-back</span>'
    # Leyenda de colores de las barras (verde = cumplió la línea, gris = no; los empates, con borde punteado)
    t_ok, t_no = ("Superó", "No superó") if mas else ("Quedó bajo", "No quedó bajo")
    leyenda_col = (f'<span class="fl-cl"><span class="fl-kc ok"></span>{t_ok}<span class="fl-kc no"></span>{t_no}'
                   + ('<span class="fl-kc push"></span>Empate' if pushes else "") + '</span>')
    eje = ""
    if n >= 2 and (riv or any(det_lista)):
        medio = f'<span class="fl-ln"></span><span class="fl-lg">{leyenda_mk}</span>' if leyenda_mk else ""
        eje = f'<div class="fl-eje"><span>Más antiguo</span>{medio}<span class="fl-ln fin"></span><span>Más reciente</span></div>'
    clase = "si" if pct >= 50 else "no"

    # Simulación del próximo partido, para el encabezado: «Historial 47 % · Simulación 52 %»
    pct_sim = None
    if simulacion:
        try:
            pct_sim = simulacion(stat, linea, mas)
        except Exception:  # noqa: BLE001 - un fallo de la simulación nunca debe romper la tarjeta
            pct_sim = None
    if pct_sim is not None:
        tip_sim = (f"Probabilidad de que cumpla {lado} {linea:g} en el próximo partido, según 10 000 partidos simulados con su "
                   f"forma reciente, el rival, las bajas y el descanso. El interruptor de abajo activa o desactiva el contexto.")
        duo = (f'<div class="fl-duo"><div class="fl-d"><small class="fl-dl">Historial</small><b>{pct}%</b></div>'
               f'<div class="fl-d sim" title="{_e(tip_sim)}"><small class="fl-dl">Simulación</small><b>{round(pct_sim)}%</b></div></div>')
    else:
        duo = f"<b>{pct}%</b>"

    # Rango probable del porcentaje: con pocos partidos el % no es un dato exacto
    ic = intervalo_wilson(k, n_validos)
    poco = n_validos < _MIN_FIABLE
    ic_html = (f'<small class="fl-ic{" poco" if poco else ""}" title="Intervalo de confianza del 95 % (Wilson): con {n_validos} partidos, el porcentaje real '
               f'de cumplir la línea podría estar entre {ic[0]} % y {ic[1]} %.">Rango probable: <b>{ic[0]}–{ic[1]}%</b></small>') if ic else ""

    # Pocos partidos: aviso visible (el rango de Wilson, que ya se calcula, es lo que de verdad se puede afirmar)
    aviso = ""
    if poco:
        if ic:
            aviso = (f'<div class="fl-aviso" role="note"><span><b>Pocos partidos ({n_validos}).</b> El {pct} % no es fiable: con tan pocos datos '
                     f'el valor real podría estar entre <b>{ic[0]}–{ic[1]} %</b>.</span></div>')
        else:
            aviso = '<div class="fl-aviso" role="note"><span><b>Sin partidos válidos.</b> No hay datos para calcular el porcentaje.</span></div>'

    # % ponderado (más peso a lo reciente) y estadísticas de resumen
    pp_pond = pct_ponderado(valores, linea, mas)
    pond_html = ""
    if pp_pond is not None:
        dif = pp_pond - pct
        pond_html = (f'<small class="fl-pd" title="Cada partido pesa {_DECAY} veces el siguiente más reciente ({_DECAY}^k, k = partidos atrás): '
                     f'lo último cuenta más. Simple: {pct} %.">Reciente (ponderado): <b class="{_clase_pct(pp_pond)}">{pp_pond}%</b>'
                     f'{f" ({dif:+d})" if dif else ""}</small>')
    rs = resumen_stats(valores)
    resumen = ""
    if rs:
        mu, med, mn, mx, sd = rs
        favor = (mu > linea) if mas else (mu < linea)
        cl_mu = "" if mu == linea else ("v" if favor else "r")
        resumen = (
            '<div class="fl-res">'
            f'<div class="fl-rt {cl_mu}" title="Promedio frente a la línea {linea:g}"><small>Promedio</small><b>{mu:.1f}</b></div>'
            f'<div class="fl-rt"><small>Mediana</small><b>{med:g}</b></div>'
            f'<div class="fl-rt"><small>Mínimo</small><b>{mn:g}</b></div>'
            f'<div class="fl-rt"><small>Máximo</small><b>{mx:g}</b></div>'
            f'<div class="fl-rt" title="Desviación típica muestral"><small>Desviación</small><b>±{sd:.1f}</b></div></div>')
        if pp_pond is not None and (favor != (pp_pond >= 50) or abs(pp_pond - pct) >= 8):
            resumen += (f'<div class="fl-res-nota">Promedio <b>{mu:.1f}</b> {"por encima" if mu > linea else "por debajo" if mu < linea else "en"} '
                        f'de la línea {linea:g}, pero ponderando lo reciente el % es <b>{pp_pond}%</b> (simple {pct}%).</div>')

    # Valor frente a la cuota de la casa (solo si se escribió una cuota)
    valor = ""
    ev_chip = ""
    if str(cuota_txt or "").strip():
        cuota = parse_cuota(cuota_txt)
        if cuota is None:
            valor = ('<div class="fl-an"><div class="fl-an-nota">Cuota no válida: escribe una cuota decimal, '
                     'por ejemplo 1.91.</div></div>')
        else:
            implicita = 100 / cuota
            filas_v = valor_vs_cuota(cuota, [("Historial", pct), ("Reciente", pp_pond),
                                             ("Simulación", None if pct_sim is None else round(pct_sim))])
            clases_v = [f[5] for f in filas_v]
            if "v" in clases_v:   # chip junto al lado: dice en cuántas de las estimaciones la cuota paga más de lo que «vale»
                todas = all(c == "v" for c in clases_v)
                con = ", ".join(f[0] for f in filas_v if f[5] == "v")
                sin = ", ".join(f[0] for f in filas_v if f[5] != "v")
                explica = (f"La casa da {implicita:.0f} % de probabilidad a esta cuota ({cuota:g}). "
                           f"Con ventaja de {_EDGE_MIN:g} puntos o más sobre ese %: {con}."
                           + (f" Sin ventaja: {sin}." if sin else "")
                           + " Detalle abajo, en «Valor frente a la cuota».")
                texto_ev = "✓ Cuota con valor" if todas else f"Valor en {clases_v.count('v')} de {len(clases_v)}"
                ev_chip = f'<span class="fl-ev{"" if todas else " parcial"}" title="{_e(explica)}">{texto_ev}</span>'
            filas_html = []
            for nombre_v, pv, ventaja, ev, justa, cl in filas_v:
                etq = {"v": "Con valor", "r": "Sin valor", "n": "Parejo"}[cl]
                filas_html.append(
                    f'<div class="fl-vr {cl}" title="{_e(nombre_v)}: {pv}% estimado frente a {implicita:.0f}% de la casa '
                    f'({ventaja:+.1f} puntos porcentuales). Valor esperado {ev:+.0f}% por unidad apostada.">'
                    f'<span>{_e(nombre_v)}</span><span>{pv}%</span><span class="d">{etq}</span></div>')
            clase_h, titulo_h, detalle = "n", "Sin ventaja clara", ""
            if filas_v:
                n_v = sum(1 for f in filas_v if f[5] == "v")
                n_r = sum(1 for f in filas_v if f[5] == "r")
                if n_v == len(filas_v):
                    clase_h, titulo_h = "v", "Posible valor"
                elif n_v == 0 and n_r == len(filas_v):
                    clase_h, titulo_h = "r", "Sin valor"
                if n_v and ic and ic[0] <= implicita <= ic[1]:
                    detalle = " La ventaja es pequeña y podría ser casualidad."
            valor = (f'<div class="fl-an"><div class="fl-vh {clase_h}"><b>{titulo_h}</b>'
                     f'<span>{_e(lado)} {linea:g} @ {cuota:.2f}</span></div>'
                     f'<div class="fl-vt">{"".join(filas_html)}</div>'
                     f'<div class="fl-an-nota">Con esta cuota la casa le da {implicita:.0f}%. '
                     f'Hay valor si la estimación supera ese número.{detalle}</div></div>')

    # Tendencia en todas las ventanas a la vez (sin tocar el selector)
    vent_tend = ventanas if ventanas else tuple(w for w in (5, 10) if w < len(valores))
    celdas_t = []
    for etq, partidos, kk, nn, pp, es_temp in tendencia_ventanas(series[stat], linea, mas, vent_tend, historico.get(stat)):
        ici = intervalo_wilson(kk, nn)
        rango = f" · rango probable {ici[0]}–{ici[1]} %" if ici else ""
        actual = " act" if (not es_temp and ventana and partidos == len(valores)) else ""
        celdas_t.append(
            f'<div class="fl-tc {_clase_pct(pp)}{actual}" title="{_e(lado)} {linea:g}: {kk} de {nn} partidos{rango}">'
            f'<small>{etq}</small><b>{pp}%</b><em>{kk} de {nn}</em><i style="width:{pp}%"></i></div>')
    tendencia = (f'<div class="fl-an-t">Tendencia por ventana<span>{_e(lado)} {linea:g}</span></div>'
                 f'<div class="fl-tend">{"".join(celdas_t)}</div>') if len(celdas_t) > 1 else ""

    # Escalera de líneas: cómo cambia el % al mover la línea
    celdas_l = []
    for ln, kk, nn, pp in escalera_lineas(valores, linea, mas):
        celdas_l.append(
            f'<div class="fl-lc {_clase_pct(pp)}{" act" if ln == linea else ""}" '
            f'title="{_e(lado)} {ln:g}: {kk} de {nn} partidos">'
            f'<small>{ln:g}</small><b>{pp}%</b><i style="height:{pp}%"></i></div>')
    seg = linea_segura(valores, mas)
    nota_seg = (f'Línea más exigente con ≥ {_UMBRAL_SEGURA} %: <b>{_e(lado)} {seg[0]:g}</b> ({seg[1]}%)' if seg
                else f'Ninguna línea llega al {_UMBRAL_SEGURA} % con esta muestra.')
    escalera = (f'<div class="fl-an-t">Escalera de líneas<span>{_e(lado)} · últimos {n} partidos</span></div>'
                f'<div class="fl-lad">{"".join(celdas_l)}</div><div class="fl-an-nota">{nota_seg}</div>') if celdas_l else ""
    analisis = f'<div class="fl-an">{tendencia}{escalera}</div>' if (tendencia or escalera) else ""
    nota_push = f" · {pushes} empate{'s' if pushes != 1 else ''}" if pushes else ""
    aria_graf = (f"Últimos {n} partidos de {nombre}: {'superó' if mas else 'quedó bajo'} la línea {linea:g} en {k} de {n_validos}. "
                 "Cada barra es un partido; se puede recorrer con el teclado.")
    foto = _url_segura(foto_url)
    logo = _url_segura(logo_equipo)
    logo_html = f'<img class="fl-logo-eq" src="{_e(logo)}" alt="" loading="lazy">' if logo else ""
    img = f'<img class="fl-foto" src="{_e(foto)}" alt="">' if foto else ""
    # Encabezado en «chips»: la estadística bien visible y, aparte, equipo / posición / altura / rival y cuántos partidos se analizan
    partes = [x.strip() for x in str(contexto or "").split(" · ") if x.strip()]
    sigla = partes[0] if (logo and partes and partes[0].isalpha() and partes[0].isupper() and len(partes[0]) <= 4) else None
    if sigla:
        partes = partes[1:]
    chips_ctx = (f'<span class="fl-chip fl-chip-eq">{_e(sigla)}</span>' if sigla else "") + \
        f'<span class="fl-chip fl-chip-stat">{_e(nom.get(stat, stat))}</span>' + "".join(
        f'<span class="fl-chip{" fl-chip-rival" if x.lower().startswith("contra ") else ""}">{_e(x)}</span>' for x in partes)
    if ventana:
        aviso_n = (f"Elegiste los últimos {ventana}, pero solo hay {n} partidos disponibles" if n < ventana
                   else f"Se analizan los últimos {n} partidos")
        chips_ctx += f'<span class="fl-chip fl-chip-n" title="{_e(aviso_n)}">{n} partidos analizados</span>'
    html = f"""
<div class="fl">
  {img}
  <div class="fl-nombre">{_e(nombre)}</div>
  <div class="fl-ctx{' fl-ctx-logo' if logo else ''}">{logo_html}{chips_ctx}</div>
  <div class="fl-fila">
    <div><div class="fl-tags"><div class="fl-tag {clase}">{lado.upper()}</div>{ev_chip}</div><div class="fl-linea">{linea:g}</div></div>
    <div class="fl-pct">{duo}<small>Frecuencia en {rot_n}{nota_push}</small>{ic_html}{pond_html}
      <div class="fl-meter"><i style="width:{pct}%"></i></div></div>
  </div>
  {aviso}
  {nota_filtro}
  <div class="fl-cab"><span>Sus últimos {n} partidos{' · todos los disponibles' if ventana and n < ventana else ''}{leyenda_col}</span>
    <span class="{'v' if pct >= 50 else 'r'}">{'Superó' if mas else 'Quedó bajo'} la línea en {k} de {n_validos}</span></div>
  {leyenda}
  <div class="fl-barras{denso}{clase_sigue}{" apilada" if desglose else ""}" role="group" aria-label="{_e(aria_graf)}"><div class="corte" aria-hidden="true" style="bottom:{corte:.1f}%;--de:{de_corte:.1f}%;--a:{corte:.1f}%"><span class="chip">{linea:g}</span></div>{barras}</div>
  {mins_html}
  {etiquetas}
  {eje}
  {nota_min}
  {resumen}
  {prox}
  {valor}
  {analisis}
</div>"""
    st.markdown(html.replace("$", "&#36;"), unsafe_allow_html=True)
    if pushes:
        st.caption("Los empates exactos con la línea no cuentan a favor ni en contra.")
