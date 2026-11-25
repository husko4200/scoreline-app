"""Tenis · Líneas: el mismo cuadro que la NBA y el fútbol, pero para jugadores.

Elige un jugador (o dos para compararlos), un mercado y una línea: mira cuántas veces la cumplió en sus últimos 5 a 25
partidos o en sus enfrentamientos directos. Incluye tarjetas con una barra por partido, comparativa, historial entre
ambos, perfil por superficie y líneas con racha del cruce.

Datos: tennis-data.co.uk (ATP y WTA, partidos completados de los últimos años; no incluye aces ni dobles faltas).
Es autocontenido: no usa ficha_equipos.py ni los módulos de tenis anteriores.

Uso desde app.py:   import tennis_lineas  ...  tennis_lineas.render()
Prueba suelta:      streamlit run tennis_lineas.py
"""
import glob
import math
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
import zlib
from dataclasses import dataclass
from datetime import date
from html import escape as _e
from io import BytesIO
from statistics import mean, median

import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Mercados
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class M:
    """clave = dato de cada partido que se mide. tipo: «linea» (más/menos), «sino» (+1 se cumplió, −1 no) o «handicap»."""
    clave: str
    tipo: str = "linea"
    grande: str = ""      # sí/no: texto grande de la tarjeta
    tag: str = ""         # sí/no: título corto de la tarjeta
    ayuda: str = ""
    rango: float = 0.0    # hándicap: límite del selector
    dato: str = ""        # hándicap: dato que se compara (la diferencia contra el rival)


def _sino(clave, tag, ayuda, grande="Sí"):
    return M(clave, "sino", grande=grande, tag=tag,
             ayuda=f"{ayuda} Cada barra vale +1 si se cumplió y −1 si no (verde = se cumplió).")


MERCADOS_T = {
    "🎾 Games": {
        "Total de games del partido (más/menos)": M("gtot"),
        "Games ganados por el jugador": M("gw"),
        "Games ganados por el rival": M("gl"),
        "Gana más games que el rival": _sino("gana_games", "MÁS GAMES", "Mide cuántas veces el jugador ganó más games que su rival (aunque haya perdido el partido)."),
        "Hándicap de games": M("hc_games", "handicap", dato="gm", rango=12.0,
                               ayuda="Ej.: -3.5 = debe ganar por 4 o más games en total. +2.5 = puede perder por hasta 2 games."),
        "Total de games del 1.er set": M("g1tot"),
        "Games del jugador en el 1.er set": M("g1w"),
        "Hándicap de games del 1.er set": M("hc_g1", "handicap", dato="g1m", rango=5.0,
                                            ayuda="Diferencia de games solo en el 1.er set."),
    },
    "🧮 Sets y resultado": {
        "Gana el partido": _sino("gana", "GANA", "Mide cuántas veces el jugador ganó el partido."),
        "Pierde el partido": _sino("pierde", "PIERDE", "Mide cuántas veces el jugador perdió el partido."),
        "Gana el 1.er set": _sino("gana_1s", "GANA 1.er SET", "Mide cuántas veces ganó el primer set."),
        "Gana al menos un set": _sino("gana_algun", "GANA ALGÚN SET", "Mide cuántas veces ganó al menos un set (aunque perdiera el partido)."),
        "Gana sin ceder sets": _sino("sin_ceder", "GANA SIN CEDER SET", "Mide cuántas veces ganó el partido sin perder ningún set (2-0 o 3-0)."),
        "Gana el 1.er set y el partido": _sino("gana_1s_partido", "1.er SET + PARTIDO", "Mide cuántas veces ganó el primer set y también el partido."),
        "Pierde el 1.er set y remonta": _sino("remonta", "REMONTADA", "Mide cuántas veces perdió el primer set y aun así ganó el partido."),
        "Va a set decisivo (3.º o 5.º set)": _sino("decisivo", "SET DECISIVO", "Mide cuántas veces el partido se definió en el último set posible."),
        "Total de sets del partido (más/menos)": M("stot"),
        "Sets ganados por el jugador": M("sw"),
        "Hándicap de sets": M("hc_sets", "handicap", dato="sm", rango=3.0,
                              ayuda="Ej.: -1.5 = debe ganar por 2 o más sets de diferencia (2-0)."),
    },
    "🔥 Tie-breaks y sets": {
        "Hay tie-break en el partido": _sino("hay_tb", "TIE-BREAK", "Mide cuántas veces el partido tuvo al menos un set 7-6."),
        "Total de tie-breaks (más/menos)": M("tb"),
        "Hay un set liquidado (6-0 o 6-1)": _sino("set_liq", "SET LIQUIDADO", "Mide cuántas veces algún set terminó 6-0 o 6-1 (para cualquiera de los dos)."),
        "El jugador gana un set por 6-0 o 6-1": _sino("liq_gana", "GANA UN SET FÁCIL", "Mide cuántas veces el jugador ganó un set por 6-0 o 6-1."),
        "El jugador pierde un set por 6-0 o 6-1": _sino("liq_pierde", "PIERDE UN SET FÁCIL", "Mide cuántas veces el jugador perdió un set por 6-0 o 6-1."),
    },
}
MERCADOS = {nombre: m for grupo in MERCADOS_T.values() for nombre, m in grupo.items()}

# (nombre, dato, ¿del partido entero? True = una sola línea para los dos jugadores; False = una por jugador,
#  mínimo posible, máximo posible a mejor de 3). Se descartan las líneas que no se pueden fallar (Más de 1.5 sets, Menos de 3.5 sets).
MERCADOS_RACHA = [("Total de games", "gtot", True, 12, None), ("Games", "gw", False, 0, None),
                  ("Total de games del 1.er set", "g1tot", True, 6, 13), ("Total de sets", "stot", True, 2, 3),
                  ("Total de tie-breaks", "tb", True, 0, 3)]

VERDE, ROJO, AMBAR = "#16a34a", "#dc2626", "#d97706"
PALETA = ["#1d4ed8", "#b91c1c", "#15803d", "#a16207", "#7e22ce", "#0e7490", "#be185d", "#374151"]
SUPERFICIES = {"Hard": "Dura", "Clay": "Arcilla", "Grass": "Césped", "Carpet": "Dura"}
ANIOS = 5   # temporadas que se cargan (la actual y las anteriores)
_HOSTS = ["http://tennis-data.co.uk", "https://tennis-data.co.uk", "http://www.tennis-data.co.uk", "https://www.tennis-data.co.uk"]
# El sitio publica los archivos sin «www» (p. ej. http://tennis-data.co.uk/2025/2025.xlsx); se prueban todas las variantes.
FUENTES = {"ATP": [h + "/{y}/{y}.xlsx" for h in _HOSTS] + [h + "/{y}/{y}.xls" for h in _HOSTS],
           "WTA": [h + "/{y}w/{y}.xlsx" for h in _HOSTS] + [h + "/{y}w/{y}.xls" for h in _HOSTS]}


# ---------------------------------------------------------------------------
# Datos (tennis-data.co.uk)
# ---------------------------------------------------------------------------
def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _col(ref):
    """«AB12» -> 27 (posición de la columna, desde 0)."""
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _leer_xlsx(contenido):
    """Lector mínimo de .xlsx (primera hoja) que NO necesita openpyxl: un .xlsx es un zip con XML. Solo se usa si openpyxl no está instalado."""
    import xml.etree.ElementTree as ET
    import zipfile
    M_ = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(BytesIO(contenido))
    nombres = z.namelist()
    compartidos = []
    if "xl/sharedStrings.xml" in nombres:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(M_ + "si"):
            compartidos.append("".join(t.text or "" for t in si.iter(M_ + "t")))
    hoja = "xl/worksheets/sheet1.xml" if "xl/worksheets/sheet1.xml" in nombres else sorted(n for n in nombres if n.startswith("xl/worksheets/sheet"))[0]
    filas = []
    for fila in ET.fromstring(z.read(hoja)).iter(M_ + "row"):
        d = {}
        for c in fila.iter(M_ + "c"):
            tipo, v = c.get("t"), c.find(M_ + "v")
            if tipo == "inlineStr":
                val = "".join(t.text or "" for t in c.iter(M_ + "t"))
            elif v is None or v.text is None:
                continue
            elif tipo == "s":
                val = compartidos[int(v.text)]
            elif tipo in ("str", "e", "b"):
                val = v.text
            else:
                val = float(v.text)
            d[_col(c.get("r"))] = val
        filas.append(d)
    if not filas:
        return pd.DataFrame()
    ancho = max(max(f) for f in filas if f) + 1
    cab = [str(filas[0].get(i, f"col{i}")).strip() for i in range(ancho)]
    df = pd.DataFrame([[f.get(i) for i in range(ancho)] for f in filas[1:]], columns=cab)
    if "Date" in df.columns and pd.api.types.is_numeric_dtype(df["Date"]):   # fechas de Excel: días desde 1899-12-30
        df["Date"] = pd.to_datetime(df["Date"], unit="D", origin="1899-12-30", errors="coerce")
    return df


def _bajar(tour, anio):
    """Un año del circuito como DataFrame. Lanza error si no se pudo bajar."""
    ultimo = "sin respuesta"
    for plantilla in FUENTES[tour]:
        try:
            r = requests.get(plantilla.format(y=anio), timeout=(5, 20), headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and len(r.content) > 5000:
                try:
                    return pd.read_excel(BytesIO(r.content))
                except ImportError:   # sin openpyxl (o xlrd para .xls): se usa el lector propio si es .xlsx
                    if r.content[:2] == b"PK":
                        return _leer_xlsx(r.content)
                    ultimo = "falta instalar xlrd para leer .xls"
                    continue
                except Exception as ex:  # noqa: BLE001  (archivo corrupto o no es Excel: probar la siguiente URL)
                    ultimo = f"archivo ilegible ({ex})"
                    continue
            ultimo = f"HTTP {r.status_code}"
        except Exception as ex:  # noqa: BLE001
            ultimo = str(ex)
    raise RuntimeError(f"{tour} {anio}: {ultimo}")


def _a_filas(df):
    """Una fila por jugador y partido (el ganador y el perdedor ven el mismo partido desde su lado). Solo partidos completados."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    if not {"Date", "Winner", "Loser"} <= set(df.columns):
        return pd.DataFrame()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Winner", "Loser"])
    if "Comment" in df.columns:   # fuera retiros, walkovers y descalificaciones: sus games y sets no son comparables
        df = df[df["Comment"].astype(str).str.strip().str.lower() == "completed"]
    out = []
    for r in df.to_dict("records"):
        sets = []
        for i in range(1, 6):
            w, l = _num(r.get(f"W{i}")), _num(r.get(f"L{i}"))
            if w is None or l is None:
                break
            sets.append((int(w), int(l)))
        if not sets:
            continue
        mejor = _num(r.get("Best of"))
        mejor = int(mejor) if mejor in (3, 5) else (5 if len(sets) > 3 else 3)
        base = {"Date": r["Date"], "Torneo": str(r.get("Tournament", "") or ""), "Ronda": str(r.get("Round", "") or ""),
                "Superficie": SUPERFICIES.get(str(r.get("Surface", "")).strip(), "Otra"), "MejorDe": mejor}
        g, p = str(r["Winner"]).strip(), str(r["Loser"]).strip()
        rg, rp = _num(r.get("WRank")), _num(r.get("LRank"))
        out.append({**base, "Jugador": g, "Rival": p, "Rank": rg, "RankRival": rp, "Sets": tuple(sets), "Gana": True})
        out.append({**base, "Jugador": p, "Rival": g, "Rank": rp, "RankRival": rg,
                    "Sets": tuple((b, a) for a, b in sets), "Gana": False})
    res = pd.DataFrame(out)
    return res.sort_values("Date").reset_index(drop=True) if not res.empty else res


# Respaldos (formato Sackmann). TML publica en su sitio oficial datos en vivo (el espejo de GitHub quedó congelado el 17/01/2026,
# por eso ya no se usa). Los CSV de Sackmann en GitHub se actualizan con meses de retraso: quedan solo como último recurso.
TML = "https://stats.tennismylife.org/data/"
FUENTES_RESPALDO = {
    "ATP": [TML + "{y}.csv",
            "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_{y}.csv",
            "https://cdn.jsdelivr.net/gh/JeffSackmann/tennis_atp@master/atp_matches_{y}.csv"],
    "WTA": [TML + "{y}_wta.csv",
            "https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/wta_matches_{y}.csv",
            "https://cdn.jsdelivr.net/gh/JeffSackmann/tennis_wta@master/wta_matches_{y}.csv"]}
# Partidos del torneo de esta semana (aún no están en el archivo del año). Mismo formato que el archivo anual.
EN_CURSO = {"ATP": TML + "ongoing_tourneys.csv", "WTA": TML + "wta_ongoing_tourneys.csv"}
_SET = re.compile(r"^(\d+)-(\d+)(?:\(\d+\))?$")
# Carpeta con archivos propios (la opción 100 % segura, no depende de internet). Ver _leer_local.
CARPETA_DATOS = "datos_tenis"


def _sackmann_a_df(df):
    """CSV en formato Sackmann (winner_name, score...) -> mismo formato de columnas que tennis-data (Winner, Loser, W1..L5...)."""
    filas = []
    for x in df.to_dict("records"):
        toks = str(x.get("score", "")).split()
        sets = [_SET.match(t) for t in toks]
        if not toks or any(s is None for s in sets):   # retiros, walkovers, súper tie-breaks: fuera
            continue
        try:
            fecha = pd.to_datetime(str(int(x["tourney_date"])), format="%Y%m%d", errors="coerce")
        except (KeyError, TypeError, ValueError):
            continue
        f = {"Date": fecha, "Tournament": x.get("tourney_name"), "Round": x.get("round"), "Surface": x.get("surface"),
             "Best of": x.get("best_of"), "Winner": x.get("winner_name"), "Loser": x.get("loser_name"),
             "WRank": x.get("winner_rank"), "LRank": x.get("loser_rank"), "Comment": "Completed"}
        n = _num(x.get("match_num"))
        if n is not None and pd.notna(f["Date"]):   # el CSV solo trae la fecha de inicio del torneo: se ordena por nº de partido
            f["Date"] = f["Date"] + pd.Timedelta(minutes=n)
        for i, s in enumerate(sets[:5], 1):
            f[f"W{i}"], f[f"L{i}"] = int(s.group(1)), int(s.group(2))
        filas.append(f)
    return pd.DataFrame(filas)


def _sumar_en_curso(df, tour):
    """Agrega los partidos del torneo que se está jugando ahora (ongoing_tourneys.csv) al año en curso, sin duplicar.
    Si no se puede leer, devuelve el año tal cual (no es un error: solo faltarían los de esta semana)."""
    try:
        r = requests.get(EN_CURSO[tour], timeout=(5, 20), headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and len(r.content) > 200:
            extra = _sackmann_a_df(pd.read_csv(BytesIO(r.content)))
            if not extra.empty:
                df = pd.concat([df, extra], ignore_index=True)
                df = df.drop_duplicates(subset=["Tournament", "Round", "Winner", "Loser"], keep="last")
    except Exception:  # noqa: BLE001
        pass
    return df


def _bajar_respaldo(tour, anio):
    """Un año desde los respaldos. Prueba cada URL; lanza error con el detalle de todas si ninguna sirve."""
    errores = []
    for plantilla in FUENTES_RESPALDO[tour]:
        url = plantilla.format(y=anio)
        host = url.split("/")[2]
        try:
            r = requests.get(url, timeout=(5, 20), headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                errores.append(f"{host}: HTTP {r.status_code}")
                continue
            df = _sackmann_a_df(pd.read_csv(BytesIO(r.content)))
            if not df.empty:
                if host == "stats.tennismylife.org" and anio >= date.today().year:
                    df = _sumar_en_curso(df, tour)
                return df
            errores.append(f"{host}: sin partidos")
        except Exception as ex:  # noqa: BLE001
            errores.append(f"{host}: {str(ex)[:60]}")
    raise RuntimeError(f"{tour} {anio}: " + " | ".join(errores))


def _leer_bytes(nombre, contenido):
    """Archivo (xlsx, xls o csv) en formato tennis-data O Sackmann -> DataFrame con columnas tennis-data."""
    if nombre.lower().endswith(".csv"):
        try:
            df = pd.read_csv(BytesIO(contenido))
        except UnicodeDecodeError:
            df = pd.read_csv(BytesIO(contenido), encoding="latin-1")
    else:
        try:
            df = pd.read_excel(BytesIO(contenido))
        except ImportError:
            if contenido[:2] != b"PK":
                raise
            df = _leer_xlsx(contenido)
    return _sackmann_a_df(df) if "winner_name" in df.columns else df


def _leer_local(tour, anio):
    """Busca el año en la carpeta datos_tenis/ (junto a este archivo o donde se ejecuta Streamlit).
    Nombres válidos: ATP_2025.xlsx, WTA_2025.xlsx, atp_matches_2025.csv, wta_matches_2025.csv (mayúsculas da igual)."""
    t = tour.lower()
    validos = {f"{t}_{anio}", f"{t}_matches_{anio}"}
    for base in (os.path.join(os.path.dirname(os.path.abspath(__file__)), CARPETA_DATOS), CARPETA_DATOS):
        if not os.path.isdir(base):
            continue
        for nombre in sorted(os.listdir(base)):
            stem, ext = os.path.splitext(nombre.lower())
            if stem in validos and ext in (".xlsx", ".xls", ".csv"):
                with open(os.path.join(base, nombre), "rb") as fh:
                    return _leer_bytes(nombre, fh.read())
    raise RuntimeError(f"{tour} {anio}: sin archivo local")


_CACHE_DIR = os.path.join(tempfile.gettempdir(), "tennis_lineas_cache_v2")


def _anio_filas(tour, anio, anio_actual):
    """Un año ya convertido a filas. Los años pasados no cambian: se guardan en disco 7 días (el actual, 6 horas),
    así sobreviven a reinicios de la app y no se vuelven a descargar. Devuelve (DataFrame o None, lista de fallos).
    Para el año en curso se consultan TODAS las fuentes (local, tennis-data, respaldos) y se queda la que tenga el
    partido más reciente; para los años pasados basta la primera que responda."""
    ruta = os.path.join(_CACHE_DIR, f"{tour}_{anio}.pkl")
    vigencia = 30 * 60 if anio >= anio_actual else 7 * 86400
    try:
        if os.path.exists(ruta) and time.time() - os.path.getmtime(ruta) < vigencia:
            return pd.read_pickle(ruta), []
    except Exception:  # noqa: BLE001  (caché dañada: se descarga de nuevo)
        pass
    fallos, candidatos = [], []
    # Primero archivo local y TML (nombres completos, «Daniil Medvedev», iguales en todos los años). tennis-data.co.uk usa
    # «Medvedev D.», así que solo entra si lo anterior falló, para no partir el historial de un jugador en dos nombres.
    for bajar in (_leer_local, _bajar_respaldo, _bajar):
        if bajar is _bajar and candidatos:
            continue
        try:
            f = _a_filas(bajar(tour, anio))
        except Exception as ex:  # noqa: BLE001
            if bajar is not _leer_local:
                fallos.append(str(ex))
            continue
        if not f.empty:
            candidatos.append(f)
            if anio < anio_actual:      # los años pasados no cambian: basta la primera fuente
                break
    if candidatos:
        f = max(candidatos, key=lambda d: d["Date"].max())   # la fuente con el partido más reciente
        try:
            os.makedirs(_CACHE_DIR, exist_ok=True)
            f.to_pickle(ruta)
        except Exception:  # noqa: BLE001
            pass
        return f, fallos
    return None, fallos


@st.cache_data(ttl=30 * 60, show_spinner=False)
def _partidos(tour, anio_actual):
    """Partidos del circuito en las últimas ANIOS temporadas. Los años se bajan EN PARALELO (antes uno tras otro) y cada
    uno prueba: archivo local -> tennis-data.co.uk -> respaldos (en el año actual gana la fuente más reciente). Si no se
    logra ningún año LANZA error (así Streamlit no guarda un resultado vacío en caché)."""
    anios = list(range(anio_actual - ANIOS + 1, anio_actual + 1))
    with ThreadPoolExecutor(max_workers=len(anios)) as ex:
        resultados = list(ex.map(lambda a: _anio_filas(tour, a, anio_actual), anios))
    trozos = [f for f, _ in resultados if f is not None]
    fallos = [m for _, fs in resultados for m in fs]
    if not trozos:
        raise RuntimeError(" || ".join(fallos) or "sin datos")
    return pd.concat(trozos, ignore_index=True).sort_values("Date").reset_index(drop=True)


def _partidos_subidos(archivos):
    """Partidos a partir de archivos que la persona sube a mano (xlsx/xls/csv de tennis-data o de Sackmann)."""
    trozos = []
    for a in archivos:
        try:
            f = _a_filas(_leer_bytes(a.name, a.getvalue()))
        except Exception as ex:  # noqa: BLE001
            st.warning(f"No pude leer {a.name}: {ex}")
            continue
        if not f.empty:
            trozos.append(f)
    if not trozos:
        raise RuntimeError("ninguno de los archivos subidos tiene partidos válidos")
    return pd.concat(trozos, ignore_index=True).sort_values("Date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cálculos de cada partido
# ---------------------------------------------------------------------------
def _metricas(r):
    """Todos los datos medibles de un partido, desde el lado del jugador (r = una fila de _a_filas)."""
    sets, mejor = r["Sets"], r["MejorDe"]
    gw, gl = sum(a for a, _ in sets), sum(b for _, b in sets)
    sw, sl = sum(a > b for a, b in sets), sum(b > a for a, b in sets)
    a1, b1 = sets[0]
    gana = sw > sl
    tb = sum(1 for a, b in sets if {a, b} == {6, 7})
    liq = lambda a, b: max(a, b) == 6 and min(a, b) <= 1   # noqa: E731
    sn = lambda c: 1.0 if c else -1.0                      # noqa: E731
    return {"gw": gw, "gl": gl, "gtot": gw + gl, "gm": gw - gl, "g1w": a1, "g1l": b1, "g1tot": a1 + b1, "g1m": a1 - b1,
            "sw": sw, "sl": sl, "stot": sw + sl, "sm": sw - sl, "tb": tb,
            "gana": sn(gana), "pierde": sn(not gana), "gana_games": sn(gw > gl), "gana_1s": sn(a1 > b1),
            "gana_algun": sn(sw > 0), "sin_ceder": sn(gana and sl == 0), "gana_1s_partido": sn(a1 > b1 and gana),
            "remonta": sn(a1 < b1 and gana), "decisivo": sn(len(sets) == mejor), "hay_tb": sn(tb > 0),
            "set_liq": sn(any(liq(a, b) for a, b in sets)), "liq_gana": sn(any(liq(a, b) and a > b for a, b in sets)),
            "liq_pierde": sn(any(liq(a, b) and b > a for a, b in sets))}


def _ventana(rows, jugador, n, rival=None, sup=None, mejor=None):
    """Últimos n partidos del jugador (opcionalmente solo contra `rival`, en una superficie o a mejor de 3/5), del más antiguo al más reciente."""
    d = rows[rows.Jugador == jugador]
    if rival:
        d = d[d.Rival == rival]
    if sup:
        d = d[d.Superficie == sup]
    if mejor:
        d = d[d.MejorDe == mejor]
    return d.sort_values("Date").tail(n)


def _serie(d):
    """Convierte la ventana (DataFrame) en la lista de partidos que dibujan las tarjetas."""
    out = []
    for r in d.to_dict("records"):
        g = {"fecha": r["Date"], "rival": r["Rival"], "rank_riv": r["RankRival"], "torneo": r["Torneo"], "sup": r["Superficie"],
             "ronda": r["Ronda"], "gana": r["Gana"], "marcador": " ".join(f"{a}-{b}" for a, b in r["Sets"])}
        g.update(_metricas(r))
        out.append(g)
    return out


def _valores(serie, clave):
    return [g[clave] for g in serie if g.get(clave) is not None]


def _medio(x):
    """La línea de media (x.5) que deja el valor `x` justo en el límite."""
    return math.floor(x) + 0.5


def _cumple(v, m, linea, lado):
    if m.tipo == "sino":
        return v > 0
    if m.tipo == "handicap":
        return v + linea > 0   # `linea` = hándicap del jugador
    return v > linea if lado == "Más de" else v < linea


def _racha(vals, cumple):
    """Partidos seguidos cumpliendo la línea, contados desde el más reciente."""
    k = 0
    for v in reversed(vals):
        if not cumple(v):
            break
        k += 1
    return k


# ---------------------------------------------------------------------------
# Tarjeta de un jugador
# ---------------------------------------------------------------------------
CSS = """<style>
.tl{border:1px solid #dbe5de;border-radius:16px;padding:16px 16px 12px;background:#fff;color:#1f2a24;box-shadow:0 1px 2px rgba(16,40,28,.06),0 8px 24px -12px rgba(16,40,28,.25);animation:tlUp .55s cubic-bezier(.2,.7,.2,1) backwards;transition:transform .25s ease,box-shadow .25s ease,border-color .25s ease}
.tl:hover{transform:translateY(-3px);border-color:#16a34a;box-shadow:0 2px 4px rgba(16,40,28,.08),0 18px 34px -14px rgba(16,40,28,.35)}
.tl-h{display:flex;align-items:center;gap:10px;margin-bottom:4px}
.tl-b{width:44px;height:44px;border-radius:50%;box-shadow:0 0 0 3px #fff,0 0 0 4px rgba(0,0,0,.12);transition:transform .3s ease;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:15px;flex:none}
.tl-n{font-weight:700;font-size:16px;line-height:1.15}
.tl-s{font-size:12px;opacity:.7}
.tl-e{font-size:12px;opacity:.75;margin:2px 0 8px}
.tl-big{font-size:22px;font-weight:800;line-height:1.1}
.tl-big small{font-size:13px;font-weight:600;opacity:.75}
.tl-m{height:8px;border-radius:5px;background:#e6ede8;margin:8px 0 10px;overflow:hidden}
.tl-m i{display:block;height:100%;border-radius:5px;transform-origin:left;animation:tlGrow .9s cubic-bezier(.2,.7,.2,1) .15s both}
.tl-bars{display:flex;align-items:stretch;gap:4px;overflow-x:auto;padding-bottom:4px}
.tl-c{flex:1 0 24px;max-width:46px;display:flex;flex-direction:column;align-items:center;font-size:10px}
.tl-v{font-weight:700;height:14px;line-height:14px}
.tl-bw{position:relative;width:100%;display:flex;flex-direction:column;justify-content:flex-end}
.tl-bar{width:70%;margin:0 auto;border-radius:5px 5px 0 0;transform-origin:bottom;animation:tlBar .6s cubic-bezier(.2,.7,.2,1) backwards;animation-delay:var(--d,0ms);transition:filter .2s ease,transform .2s ease}
.tl-c:hover .tl-bar{filter:brightness(1.12) saturate(1.1);transform:scaleX(1.12)}
.tl-dn .tl-bar{transform-origin:top}
.tl-up{display:flex;align-items:flex-end;justify-content:center;border-bottom:1px solid rgba(128,128,128,.6)}
.tl-dn{display:flex;align-items:flex-start;justify-content:center}
.tl-dn .tl-bar{border-radius:0 0 4px 4px}
.tl-ln{position:absolute;left:-2px;right:-2px;border-top:2px dashed rgba(128,128,128,.9)}
.tl-r{opacity:.8;margin-top:3px;white-space:nowrap}
.tl-f{font-size:9px;opacity:.55}
.tl-st{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin-top:8px;opacity:.9}
.tl-st span{margin-right:14px}
.tl-chip{display:inline-block;min-width:22px;text-align:center;border-radius:6px;color:#fff;font-weight:700;font-size:12px;padding:2px 5px;margin-right:3px;animation:tlPop .4s cubic-bezier(.3,1.6,.5,1) backwards;transition:transform .15s ease}
.tl-chip:hover{transform:translateY(-2px) scale(1.08)}
.tl-c:nth-child(1){--d:148ms}.tl-c:nth-child(2){--d:176ms}.tl-c:nth-child(3){--d:204ms}.tl-c:nth-child(4){--d:232ms}.tl-c:nth-child(5){--d:260ms}.tl-c:nth-child(6){--d:288ms}.tl-c:nth-child(7){--d:316ms}.tl-c:nth-child(8){--d:344ms}.tl-c:nth-child(9){--d:372ms}.tl-c:nth-child(10){--d:400ms}.tl-c:nth-child(11){--d:428ms}.tl-c:nth-child(12){--d:456ms}.tl-c:nth-child(13){--d:484ms}.tl-c:nth-child(14){--d:512ms}.tl-c:nth-child(15){--d:540ms}.tl-c:nth-child(16){--d:568ms}.tl-c:nth-child(17){--d:596ms}.tl-c:nth-child(18){--d:624ms}.tl-c:nth-child(19){--d:652ms}.tl-c:nth-child(20){--d:680ms}.tl-c:nth-child(21){--d:708ms}.tl-c:nth-child(22){--d:736ms}.tl-c:nth-child(23){--d:764ms}.tl-c:nth-child(24){--d:792ms}.tl-c:nth-child(25){--d:820ms}.tl-c:nth-child(26){--d:848ms}.tl-c:nth-child(27){--d:876ms}.tl-c:nth-child(28){--d:904ms}.tl-c:nth-child(29){--d:932ms}.tl-c:nth-child(30){--d:960ms}

.tlt-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin:8px 0 14px}
.tlt{position:relative;background:#fff;color:#1f2a24;border:1px solid #dbe5de;border-radius:16px;padding:14px 14px 12px;overflow:hidden;
  box-shadow:0 1px 2px rgba(16,40,28,.06),0 8px 24px -12px rgba(16,40,28,.25);
  animation:tlUp .55s cubic-bezier(.2,.7,.2,1) backwards;animation-delay:var(--d,0ms);transition:transform .25s ease,box-shadow .25s ease,border-color .25s ease}
.tlt:hover{transform:translateY(-4px);border-color:#16a34a;box-shadow:0 18px 34px -14px rgba(16,40,28,.4)}
.tlt::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--c,#16a34a)}
.tlt-top{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;margin-bottom:6px}
.tlt-medal{font-size:18px}
.tlt-who{padding:2px 8px;border-radius:999px;color:#fff;font-size:11px;font-weight:700}
.tlt-mk{font-size:13px;opacity:.8;line-height:1.25}
.tlt-pick{font-size:17px;font-weight:800;margin:3px 0 6px;line-height:1.15}
.tlt-pct{font-size:26px;font-weight:800;line-height:1;color:#15803d}
.tlt-sub{font-size:11px;opacity:.7;margin-top:4px}
.tlt-bar{height:7px;border-radius:5px;background:#e6ede8;margin-top:8px;overflow:hidden}
.tlt-bar i{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,#16a34a,#0f6b32);transform-origin:left;animation:tlGrow .9s cubic-bezier(.2,.7,.2,1) .2s both}
.tl-ver{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid #dbe5de;border-radius:16px;padding:14px 16px;margin:6px 0 12px;
  box-shadow:0 8px 24px -14px rgba(16,40,28,.3);animation:tlUp .5s ease backwards}
.tl-ver b{font-size:18px}
@keyframes tlUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes tlGrow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes tlBar{from{transform:scaleY(0);opacity:.3}to{transform:scaleY(1);opacity:1}}
@keyframes tlPop{from{opacity:0;transform:scale(.5)}to{opacity:1;transform:none}}
</style>"""

# ---------------------------------------------------------------------------
# Tema de los controles (botones sólidos, selectores, deslizadores) + animaciones
# ---------------------------------------------------------------------------
THEME = """<style>
:root{--g1:#15803d;--g2:#0f6b32;--gl:#16a34a;--surf:#ffffff;--surf2:#f1f5f2;--bd:#d3ded6;--tx:#1f2a24}
/* --- Grupos de opciones (radio) como botones segmentados SÓLIDOS (solo área principal) --- */
[data-testid="stMain"] div[data-testid="stRadio"] [role="radiogroup"]{background:#e9efea;border:1px solid var(--bd);border-radius:16px;padding:5px;gap:6px;
  flex-wrap:wrap;box-shadow:inset 0 1px 2px rgba(16,40,28,.08)}
[data-testid="stMain"] div[data-testid="stRadio"] label[data-baseweb="radio"]{background:var(--surf);border:1px solid var(--bd);border-radius:12px;margin:0;
  padding:8px 16px;cursor:pointer;color:var(--tx);font-weight:600;box-shadow:0 1px 2px rgba(16,40,28,.08);
  transition:transform .18s ease,box-shadow .18s ease,background .25s ease,border-color .18s ease,color .2s ease}
[data-testid="stMain"] div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child{display:none}
[data-testid="stMain"] div[data-testid="stRadio"] label[data-baseweb="radio"] p{color:inherit;font-weight:inherit;margin:0}
[data-testid="stMain"] div[data-testid="stRadio"] label[data-baseweb="radio"]:hover{transform:translateY(-2px);border-color:var(--gl);box-shadow:0 6px 14px -6px rgba(21,128,61,.45)}
[data-testid="stMain"] div[data-testid="stRadio"] label[data-baseweb="radio"]:active{transform:translateY(0) scale(.96)}
[data-testid="stMain"] div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked){background:linear-gradient(135deg,var(--g1),var(--g2));
  border-color:var(--g2);color:#fff;box-shadow:0 8px 18px -8px rgba(15,107,50,.8);animation:tlSel .35s cubic-bezier(.3,1.5,.5,1)}
[data-testid="stMain"] div[data-testid="stRadio"] label[data-baseweb="radio"]:focus-within{outline:3px solid rgba(22,163,74,.35);outline-offset:1px}
/* --- Selectores y campos numéricos con fondo sólido --- */
[data-testid="stMain"] div[data-baseweb="select"] > div,[data-testid="stMain"] div[data-testid="stNumberInput"] div[data-baseweb="input"],[data-testid="stMain"] div[data-testid="stNumberInput"] input{
  background:var(--surf) !important;border-color:var(--bd) !important;border-radius:12px !important;color:var(--tx);
  transition:border-color .2s ease,box-shadow .2s ease,transform .2s ease}
[data-testid="stMain"] div[data-baseweb="select"] > div:hover,[data-testid="stMain"] div[data-testid="stNumberInput"] div[data-baseweb="input"]:hover{border-color:var(--gl) !important;
  box-shadow:0 6px 16px -8px rgba(21,128,61,.5);transform:translateY(-1px)}
[data-testid="stMain"] div[data-baseweb="select"] > div:focus-within,[data-testid="stMain"] div[data-testid="stNumberInput"] div[data-baseweb="input"]:focus-within{
  border-color:var(--gl) !important;box-shadow:0 0 0 3px rgba(22,163,74,.25)}
ul[role="listbox"]{background:var(--surf) !important;border-radius:12px;box-shadow:0 18px 40px -12px rgba(16,40,28,.35);animation:tlUp .2s ease both}
ul[role="listbox"] li{transition:background .15s ease,padding-left .15s ease}
ul[role="listbox"] li:hover{background:#e3f2e8 !important;padding-left:18px}
/* --- Botones normales y de subida de archivos --- */
[data-testid="stMain"] div[data-testid="stButton"] button,[data-testid="stMain"] div[data-testid="stFileUploader"] button{background:linear-gradient(135deg,var(--g1),var(--g2)) !important;
  color:#fff !important;border:0 !important;border-radius:12px !important;font-weight:700;box-shadow:0 8px 18px -8px rgba(15,107,50,.8);
  transition:transform .18s ease,box-shadow .18s ease,filter .18s ease}
[data-testid="stMain"] div[data-testid="stButton"] button:hover,[data-testid="stMain"] div[data-testid="stFileUploader"] button:hover{transform:translateY(-2px);filter:brightness(1.08);
  box-shadow:0 12px 22px -8px rgba(15,107,50,.9)}
div[data-testid="stButton"] button:active,div[data-testid="stFileUploader"] button:active{transform:scale(.96)}
div[data-testid="stFileUploaderDropzone"]{background:var(--surf);border:2px dashed var(--bd);border-radius:14px;transition:border-color .2s ease,background .2s ease}
div[data-testid="stFileUploaderDropzone"]:hover{border-color:var(--gl);background:#f1faf4}
/* --- Deslizador --- */
div[data-testid="stSlider"] [role="slider"]{background:var(--g1) !important;box-shadow:0 0 0 4px rgba(22,163,74,.25);transition:transform .15s ease,box-shadow .15s ease}
div[data-testid="stSlider"] [role="slider"]:hover{transform:scale(1.2);box-shadow:0 0 0 7px rgba(22,163,74,.25)}
/* --- Mensajes, tablas y apariciones suaves --- */
div[data-testid="stAlert"]{border-radius:14px;animation:tlUp .4s ease both}
div[data-testid="stDataFrame"]{border-radius:14px;overflow:hidden;box-shadow:0 8px 24px -14px rgba(16,40,28,.35);animation:tlUp .5s ease both}
div[data-testid="stHorizontalBlock"] > div{animation:tlUp .45s cubic-bezier(.2,.7,.2,1) both}
h4{animation:tlUp .4s ease both}
@keyframes tlSel{0%{transform:scale(.92)}100%{transform:scale(1)}}
@media (prefers-reduced-motion:reduce){*{animation:none !important;transition:none !important}}
</style>"""
ALTO = 110   # px de la zona de barras


def _fmt(v):
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


def _iniciales(nombre):
    pal = re.findall(r"[^\W\d_]+", nombre)
    return ("".join(p[0] for p in pal[:2]) or "?").upper()


def _color_jugador(nombre):
    return PALETA[zlib.crc32(nombre.encode()) % len(PALETA)]


def _barras(pts, m, linea, lado):
    """HTML de las barras: una por partido (más antiguo a la izquierda)."""
    if m.tipo == "linea":
        vmax = max([v for _, v in pts] + [linea * 1.15, 1.0])
    elif m.tipo == "handicap":
        vmax = max([abs(v) for _, v in pts] + [abs(linea), 1.0])
    celdas = []
    for g, v in pts:
        ok = _cumple(v, m, linea, lado)
        color = VERDE if ok else ROJO
        if m.tipo == "linea":
            h = max(3, round(v / vmax * ALTO))
            marca = f'<div class="tl-ln" style="bottom:{round(linea / vmax * ALTO)}px"></div>'
            cuerpo = f'<div class="tl-bw" style="height:{ALTO}px"><div class="tl-bar" style="height:{h}px;background:{color}"></div>{marca}</div>'
            etiqueta = _fmt(v)
        else:
            mitad = ALTO // 2
            if m.tipo == "sino":
                h = round(mitad * 0.8)
                arriba, abajo = (h, 0) if ok else (0, h)
                etiqueta = "✓" if ok else "✗"
            else:
                h = max(3, round(abs(v) / vmax * (mitad - 2)))
                arriba, abajo = (h, 0) if v > 0 else (0, h)
                etiqueta = f"{v:+.0f}"
            bar = lambda alto: f'<div class="tl-bar" style="height:{alto}px;background:{color}"></div>' if alto else ""   # noqa: E731
            cuerpo = (f'<div class="tl-bw" style="height:{ALTO}px"><div class="tl-up" style="height:{mitad}px">{bar(arriba)}</div>'
                      f'<div class="tl-dn" style="height:{mitad}px">{bar(abajo)}</div></div>')
        rk = g["rank_riv"]
        rk_txt = "" if rk is None or pd.isna(rk) else " (#%d)" % int(rk)
        res_txt = "ganó" if g["gana"] else "perdió"
        tip = "%s · %s (%s, %s) · vs %s%s · %s %s" % (g["fecha"].strftime("%d/%m/%Y"), g["torneo"], g["sup"], g["ronda"],
                                                      g["rival"], rk_txt, res_txt, g["marcador"])
        codigo = re.sub(r"[^A-Za-z]", "", g["rival"])[:3].upper() or "?"
        celdas.append(f'<div class="tl-c" title="{_e(tip, quote=True)}"><div class="tl-v">{etiqueta}</div>{cuerpo}'
                      f'<div class="tl-r">{_e(codigo)}</div><div class="tl-f">{g["fecha"]:%d/%m}</div></div>')
    return '<div class="tl-bars">' + "".join(celdas) + "</div>"


def _tarjeta(jug, serie, m, linea, lado, etiqueta, h2h=False):
    """Tarjeta del jugador: cuántas veces cumplió la línea en los partidos de `serie` (con una barra por partido)."""
    campo = m.dato or m.clave
    pts = [(g, g[campo]) for g in serie if g.get(campo) is not None]
    nombre = _e(jug["nombre"])
    rank = f'#{int(jug["rank"])} del ranking' if jug.get("rank") and not pd.isna(jug["rank"]) else "sin ranking"
    cab = (f'<div class="tl-h"><div class="tl-b" style="background:{jug["color"]}">{_e(jug["ini"])}</div>'
           f'<div><div class="tl-n">{nombre}</div><div class="tl-s">{rank}</div></div></div>'
           f'<div class="tl-e">{_e(etiqueta)} · {"enfrentamientos directos" if h2h else f"últimos {len(serie)} partidos"}</div>')
    if not pts:
        return f'<div class="tl">{cab}<div class="tl-s">Sin partidos con este dato.</div></div>'
    hits = [_cumple(v, m, linea, lado) for _, v in pts]
    k, n = sum(hits), len(hits)
    pct = round(100 * k / n)
    color = VERDE if pct >= 70 else AMBAR if pct >= 50 else ROJO
    if m.tipo == "linea":
        grande = f'{lado} {linea:g}'
    elif m.tipo == "handicap":
        grande = f'Hándicap {linea:+g}'
    else:
        grande = f'{m.tag}: {m.grande}'
    vals = [v for _, v in pts]
    racha = 0
    for h in reversed(hits):
        if h != hits[-1]:
            break
        racha += 1
    sufijo = "✓" if hits[-1] else "✗"
    stats = [f"<span>Cumplió <b>{k}/{n}</b></span>", f"<span>Racha <b>{racha} {sufijo}</b></span>"]
    if m.tipo == "linea":
        stats.insert(0, f"<span>Prom <b>{mean(vals):.1f}</b> · Mediana <b>{_fmt(median(vals))}</b></span>")
    return (f'<div class="tl">{cab}<div class="tl-big">{_e(grande)} <small>· {k}/{n} · {pct}%</small></div>'
            f'<div class="tl-m"><i style="width:{pct}%;background:{color}"></i></div>'
            f'{_barras(pts, m, linea, lado)}<div class="tl-st">{"".join(stats)}</div></div>')


# ---------------------------------------------------------------------------
# Comparativa, perfil e historial
# ---------------------------------------------------------------------------
def _prom(serie, clave):
    v = _valores(serie, clave)
    return mean(v) if v else None


def _pct_si(serie, clave):
    v = _valores(serie, clave)
    return None if not v else round(100 * sum(x > 0 for x in v) / len(v))


def _comparativa(nom_a, nom_b, sa, sb, titulo):
    def col(s):
        rk = [g["rank_riv"] for g in s if g["rank_riv"] is not None and not pd.isna(g["rank_riv"])]
        f = lambda x, d=1: "—" if x is None else f"{x:.{d}f}"          # noqa: E731
        p = lambda x: "—" if x is None else f"{x}%"                     # noqa: E731
        return [str(len(s)), p(_pct_si(s, "gana")), f(_prom(s, "gw")), f(_prom(s, "gl")), f(_prom(s, "gtot")), f(_prom(s, "sw")),
                p(_pct_si(s, "gana_1s")), p(_pct_si(s, "decisivo")), p(_pct_si(s, "hay_tb")), f(_prom(s, "tb"), 2),
                f(mean(rk), 0) if rk else "—"]
    filas = ["Partidos analizados", "Victorias (%)", "Games ganados", "Games recibidos", "Games totales del partido", "Sets ganados",
             "Gana el 1.er set (%)", "Va a set decisivo (%)", "Partidos con tie-break (%)", "Tie-breaks por partido", "Ranking medio del rival"]
    return pd.DataFrame({titulo: filas, nom_a: col(sa), nom_b: col(sb)})


def _perfil(rows, nombre):
    """Récord y promedios del jugador por superficie (todos sus partidos cargados)."""
    d = rows[rows.Jugador == nombre]
    filas = []
    for sup in ["Dura", "Arcilla", "Césped"]:
        s = _serie(d[d.Superficie == sup])
        if s:
            filas.append({"Superficie": sup, "Partidos": len(s), "Victorias (%)": _pct_si(s, "gana"),
                          "Games ganados": round(_prom(s, "gw"), 1), "Games recibidos": round(_prom(s, "gl"), 1),
                          "Total de games": round(_prom(s, "gtot"), 1), "Con tie-break (%)": _pct_si(s, "hay_tb"),
                          "A set decisivo (%)": _pct_si(s, "decisivo")})
    return pd.DataFrame(filas)


def _forma_html(rows, nombre, n=10):
    d = rows[rows.Jugador == nombre].sort_values("Date").tail(n)
    chips = "".join(f'<span class="tl-chip" style="background:{VERDE if g else ROJO}" title="{_e(str(r))}">{"G" if g else "P"}</span>'
                    for g, r in zip(d.Gana, d.Rival))
    return f'<div class="tl-s" style="margin-bottom:4px">Forma (últimos {len(d)}, el más reciente a la derecha)</div>{chips}'


def _historial(rows, a, b):
    d = rows[(rows.Jugador == a) & (rows.Rival == b)].sort_values("Date", ascending=False)
    return pd.DataFrame({"Fecha": d.Date.dt.strftime("%d/%m/%Y"), "Torneo": d.Torneo, "Superficie": d.Superficie, "Ronda": d.Ronda,
                         "Ganó": [a if g else b for g in d.Gana],
                         f"Marcador (visto desde {a})": [" ".join(f"{x}-{y}" for x, y in s) for s in d.Sets]})


# ---------------------------------------------------------------------------
# Líneas con racha del cruce
# ---------------------------------------------------------------------------
def _mejor_linea(series, vh, lado, minimo, piso=0, techo=None):
    """La línea más exigente de `lado` que se cumplió al menos `minimo` de las veces en los recientes (series) y en el cara a cara (vh)."""
    todos = [v for s in series for v in s]
    if not todos:
        return None
    lo, hi = math.floor(min(todos)) - 0.5, math.floor(max(todos)) + 1.5
    lineas = [lo + i for i in range(int(hi - lo) + 1) if lo + i >= piso + 0.5 and (techo is None or lo + i <= techo - 0.5)]
    if not lineas:
        return None
    ok = (lambda v, L: v > L) if lado == "Más de" else (lambda v, L: v < L)
    elegida = None
    for L in (lineas if lado == "Más de" else reversed(lineas)):
        kr = sum(ok(v, L) for v in todos)
        hr = kr / len(todos)
        kh = sum(ok(v, L) for v in vh)
        hh = kh / len(vh) if len(vh) >= 2 else None
        if hr >= minimo and (hh is None or hh >= minimo):
            elegida = {"L": L, "kr": kr, "nr": len(todos), "hr": hr, "kh": kh, "nh": len(vh), "hh": hh,
                       "racha": min(_racha(s, lambda v, L=L: ok(v, L)) for s in series if s)}
        elif elegida:
            break
    return elegida


def _picks_racha(a, b, ra, rb, ha, hb, minimo):
    filas = []
    for nombre, clave, partido, piso, techo in MERCADOS_RACHA:
        if partido:
            grupos = [(nombre, [_valores(ra, clave), _valores(rb, clave)], _valores(ha, clave))]
        else:
            grupos = [(f'{nombre} de {x["nombre"]}', [_valores(r, clave)], _valores(h, clave))
                      for x, r, h in ((a, ra, ha), (b, rb, hb))]
        for etq, series, vh in grupos:
            series = [s for s in series if s]
            if not series:
                continue
            esperado = mean([v for s in series for v in s])
            if len(vh) >= 2:
                esperado = (esperado + mean(vh)) / 2
            for lado in ("Más de", "Menos de"):
                r = _mejor_linea(series, vh, lado, minimo, piso, techo)
                if not r:
                    continue
                filas.append({"Mercado": etq, "Apuesta": lado, "Línea": r["L"],
                              "Recientes": f'{r["kr"]}/{r["nr"]} · {round(100 * r["hr"])}%',
                              "Cara a cara": "sin cruces" if r["hh"] is None else f'{r["kh"]}/{r["nh"]} · {round(100 * r["hh"])}%',
                              "Racha actual": r["racha"], "Esperado": round(esperado, 1), "Holgura": round(abs(esperado - r["L"]), 1),
                              "_score": (r["hr"] + (r["hh"] if r["hh"] is not None else r["hr"])) / 2})
    df = pd.DataFrame(filas)
    if not df.empty:
        df = df.sort_values(["_score", "Racha actual", "Holgura"], ascending=[False, False, True]).drop(columns="_score").reset_index(drop=True)
    # games esperados: lo que anota cada uno cruzado con lo que concede el otro
    proy = None
    if all(_valores(s, k) for s in (ra, rb) for k in ("gw", "gl")):
        ga = mean([mean(_valores(ra, "gw")), mean(_valores(rb, "gl"))])
        gb = mean([mean(_valores(rb, "gw")), mean(_valores(ra, "gl"))])
        h2h = mean(_valores(ha, "gtot")) if len(_valores(ha, "gtot")) >= 2 else None
        proy = {"a": ga, "b": gb, "total": ga + gb, "h2h": h2h}
    return proy, df


def _seccion_racha(a, b, ra, rb, ha, hb):
    st.markdown("#### 🔥 Líneas con racha del cruce")
    minimo = st.slider("Mínimo de cumplimiento", 60, 100, 80, 5, format="%d%%", key="tl_racha_min",
                       help="Busca la línea más exigente que cumplieron al menos este % de las veces, tanto en los partidos "
                            "recientes como en los enfrentamientos directos.") / 100
    proy, df = _picks_racha(a, b, ra, rb, ha, hb, minimo)
    if proy:
        c1, c2, c3 = st.columns(3)
        c1.metric(f"{a['nombre']} esperado", f"{proy['a']:.1f} games", help="Promedio entre lo que gana y lo que concede el rival.")
        c2.metric(f"{b['nombre']} esperado", f"{proy['b']:.1f} games")
        c3.metric("Total esperado", f"{proy['total']:.1f} games",
                  None if proy["h2h"] is None else f"cara a cara: {proy['h2h']:.1f}", delta_color="off")
        tot = [v for s in (ra, rb) for v in _valores(s, "gtot")]
        if tot:
            central = _medio(proy["total"] if proy["h2h"] is None else (proy["total"] + proy["h2h"]) / 2)
            mas = round(100 * sum(v > central for v in tot) / len(tot))
            menos = 100 - mas
            lean = "Más de" if mas >= 60 else "Menos de" if menos >= 60 else None
            st.markdown(f"**Línea central {central:g} games:** Más de {mas}% · Menos de {menos}% (partidos recientes de ambos). "
                        + (f"👉 Inclinación: **{lean}**." if lean else "Sin ventaja clara: está parejo."))
    if df.empty:
        st.info(f"Ninguna línea llega al {round(minimo * 100)}% en recientes y cara a cara a la vez. Baja el mínimo o cambia la ventana.")
        return
    st.dataframe(df, hide_index=True, use_container_width=True, column_config={
        "Línea": st.column_config.NumberColumn(format="%.1f"),
        "Racha actual": st.column_config.NumberColumn(help="Partidos seguidos cumpliéndola, desde el más reciente (el menor de los dos jugadores en los mercados del partido)."),
        "Esperado": st.column_config.NumberColumn(help="Promedio del mercado (recientes y cara a cara)."),
        "Holgura": st.column_config.NumberColumn(help="Distancia entre la línea y el promedio: más holgura = más margen de seguridad.")})
    st.caption("Son líneas históricas «seguras» (las más exigentes que se cumplieron con esa frecuencia). "
               "No es una predicción ni garantiza el resultado.")



# ---------------------------------------------------------------------------
# Autoanálisis: quién tiene las mejores estadísticas en cada línea
# ---------------------------------------------------------------------------
_INDIV = {"gw", "gl", "g1w", "sw"}   # mercados de un solo jugador: cada uno con su propia línea; el resto es del partido (línea común)


def _mejor_lado(v, h, m, linea):
    """Mejor lado (Más/Menos, o Sí/No) de un jugador en esa línea. Puntuación suavizada (evita que 3/3 valga más que 17/20),
    promediando recientes y cara a cara cuando hay al menos 2 cruces."""
    if m.tipo == "sino":
        opciones = [("Sí", lambda x: x > 0), ("No", lambda x: x <= 0)]
    else:
        opciones = [("Más de", lambda x: x > linea), ("Menos de", lambda x: x < linea)]
    mejor = None
    for lado, ok in opciones:
        k = sum(ok(x) for x in v)
        sr = (k + 1) / (len(v) + 2)
        kh = sum(ok(x) for x in h)
        sh = (kh + 1) / (len(h) + 2) if len(h) >= 2 else None
        score = sr if sh is None else (sr + sh) / 2
        c = {"lado": lado, "k": k, "n": len(v), "pct": k / len(v), "kh": kh, "nh": len(h),
             "hpct": (kh / len(h) if len(h) >= 2 else None), "score": score, "racha": _racha(v, ok)}
        if mejor is None or c["score"] > mejor["score"]:
            mejor = c
    return mejor


def _auto_filas(ra, rb, ha, hb, minimo=3):
    """Una fila por línea (mercado): la mejor apuesta de cada jugador y quién la tiene mejor."""
    filas = []
    for grupo, mercados in MERCADOS_T.items():
        for nombre, m in mercados.items():
            if m.tipo == "handicap":
                continue   # los hándicaps ya los cubren «Gana games» y «Gana el partido»
            va, vb = _valores(ra, m.clave), _valores(rb, m.clave)
            if len(va) < minimo or len(vb) < minimo:
                continue
            h_a, h_b = _valores(ha, m.clave), _valores(hb, m.clave)
            if m.tipo == "sino":
                la = lb = None
            elif m.clave in _INDIV:
                la, lb = max(0.5, _medio(mean(va))), max(0.5, _medio(mean(vb)))
            else:
                la = lb = max(0.5, _medio((mean(va) + mean(vb)) / 2))
            pa, pb = _mejor_lado(va, h_a, m, la), _mejor_lado(vb, h_b, m, lb)
            dif = pa["score"] - pb["score"]
            filas.append({"grupo": grupo, "mercado": nombre, "clave": m.clave, "la": la, "lb": lb, "pa": pa, "pb": pb,
                          "ganador": "A" if dif > 0.05 else "B" if dif < -0.05 else "="})
    return filas


def _txt_pick(p, linea):
    return p["lado"] if linea is None else f"{p['lado']} {linea:g}"


def _txt_pct(p):
    base = f"{p['k']}/{p['n']}"
    return base if p["hpct"] is None else f"{base} · cruces {p['kh']}/{p['nh']}"


def _autoanalisis_ui(jug_a, jug_b, ra, rb, ha, hb, ventana_txt):
    filas = _auto_filas(ra, rb, ha, hb)
    if not filas:
        st.info("No hay partidos suficientes (mínimo 3 por jugador) con estos filtros para hacer el autoanálisis. Prueba con otra superficie o formato.")
        return
    na, nb = jug_a["nombre"], jug_b["nombre"]
    ga, gb = sum(f["ganador"] == "A" for f in filas), sum(f["ganador"] == "B" for f in filas)
    ge = len(filas) - ga - gb
    if ga == gb:
        veredicto = f"Parejo: {ga} líneas para cada uno"
    else:
        lider, gl = (jug_a, ga) if ga > gb else (jug_b, gb)
        veredicto = f"Mejores estadísticas: <b style=\"color:{lider['color']}\">{_e(lider['nombre'])}</b> en {gl} de {len(filas)} líneas"
    st.markdown(f'<div class="tl-ver"><span style="font-size:26px">🏆</span><div><b>{veredicto}</b><br>'
                f'<span style="font-size:12px;opacity:.7">{_e(na)}: {ga} · {_e(nb)}: {gb} · parejo: {ge} · base: {ventana_txt}</span></div></div>',
                unsafe_allow_html=True)

    # Las mejores apuestas históricas de los dos (sin la redundante «Pierde el partido»)
    cand = []
    for f in filas:
        if f["clave"] == "pierde":
            continue
        for jug, p, ln in ((jug_a, f["pa"], f["la"]), (jug_b, f["pb"], f["lb"])):
            cand.append((p["score"], p["n"], jug, f["mercado"], p, ln))
    cand.sort(key=lambda t: (-t[0], -t[1]))
    vistos, top = set(), []
    for sc, _n, jug, merc, p, ln in cand:
        clave = (jug["nombre"], merc)
        if clave in vistos:
            continue
        vistos.add(clave)
        top.append((jug, merc, p, ln))
        if len(top) == 6:
            break
    medallas = ["🥇", "🥈", "🥉", "④", "⑤", "⑥"]
    tarjetas = []
    for i, (jug, merc, p, ln) in enumerate(top):
        pct = round(100 * p["pct"])
        tarjetas.append(
            f'<div class="tlt" style="--c:{jug["color"]};--d:{i * 70}ms"><div class="tlt-top"><span class="tlt-medal">{medallas[i]}</span>'
            f'<span class="tlt-who" style="background:{jug["color"]}">{_e(jug["nombre"])}</span></div>'
            f'<div class="tlt-mk">{_e(merc)}</div><div class="tlt-pick">{_e(_txt_pick(p, ln))}</div>'
            f'<div class="tlt-pct">{pct}%</div><div class="tlt-sub">{_e(_txt_pct(p))}</div>'
            f'<div class="tlt-bar"><i style="width:{pct}%"></i></div></div>')
    st.markdown("**Mejores líneas de los dos jugadores**")
    st.markdown('<div class="tlt-grid">' + "".join(tarjetas) + "</div>", unsafe_allow_html=True)

    # Tabla completa: una fila por línea
    tabla = []
    for f in filas:
        pa, pb = f["pa"], f["pb"]
        mejor = f"🏆 {na}" if f["ganador"] == "A" else f"🏆 {nb}" if f["ganador"] == "B" else "🤝 Parejo"
        tabla.append({"Tipo": f["grupo"], "Línea (mercado)": f["mercado"],
                      f"{na}": f"{_txt_pick(pa, f['la'])} ({_txt_pct(pa)})", f"{na} %": round(100 * pa["pct"]),
                      f"{nb}": f"{_txt_pick(pb, f['lb'])} ({_txt_pct(pb)})", f"{nb} %": round(100 * pb["pct"]),
                      "Mejor estadística": mejor})
    st.markdown("**Línea por línea**")
    st.dataframe(pd.DataFrame(tabla), hide_index=True, use_container_width=True, column_config={
        f"{na} %": st.column_config.ProgressColumn(f"{na} %", min_value=0, max_value=100, format="%d%%"),
        f"{nb} %": st.column_config.ProgressColumn(f"{nb} %", min_value=0, max_value=100, format="%d%%")})
    st.caption("Para cada línea se toma la apuesta (Más/Menos o Sí/No) que mejor le funcionó a cada jugador y se compara. "
               "La puntuación mezcla sus partidos recientes y los cruces entre ambos, y penaliza las muestras pequeñas; "
               "«Parejo» = diferencia menor a 5 puntos. Son frecuencias históricas, no una predicción.")


def _boton_autoanalisis(rows, jug_a, jug_b, tour, ventana, sup, mejor):
    par = (tour, jug_a["nombre"], jug_b["nombre"])
    b1, b2, _ = st.columns([2, 1, 3])
    if b1.button("🤖 Autoanálisis de todas las líneas", key="tl_auto_btn", use_container_width=True,
                 help="Compara a los dos jugadores en cada línea y te dice quién tiene las mejores estadísticas."):
        st.session_state["tl_auto_par"] = par
    if st.session_state.get("tl_auto_par") == par and b2.button("✖ Ocultar", key="tl_auto_off", use_container_width=True):
        st.session_state["tl_auto_par"] = None
    if st.session_state.get("tl_auto_par") != par:
        return
    n_rec = ventana if isinstance(ventana, int) else 10
    with st.spinner("Analizando todas las líneas..."):
        ra = _serie(_ventana(rows, jug_a["nombre"], n_rec, None, sup, mejor))
        rb = _serie(_ventana(rows, jug_b["nombre"], n_rec, None, sup, mejor))
        ha = _serie(_ventana(rows, jug_a["nombre"], 25, jug_b["nombre"]))
        hb = _serie(_ventana(rows, jug_b["nombre"], 25, jug_a["nombre"]))
    st.markdown("#### 🤖 Autoanálisis")
    _autoanalisis_ui(jug_a, jug_b, ra, rb, ha, hb, f"últimos {n_rec} partidos de cada uno")


# ---------------------------------------------------------------------------
# Pantalla
# ---------------------------------------------------------------------------
def _lista_jugadores(rows, minimo=5):
    """Jugadores con al menos `minimo` partidos, el mejor ranking primero."""
    cuenta = rows.groupby("Jugador").size()
    rank = rows.dropna(subset=["Rank"]).sort_values("Date").groupby("Jugador").tail(1).set_index("Jugador")["Rank"]
    return sorted(cuenta[cuenta >= minimo].index, key=lambda n: (n not in rank.index, rank.get(n, 0), n)), rank.to_dict()


def render():
    st.title("🎾 Líneas de jugadores")
    st.caption("Elige un jugador (o dos para compararlos) y un mercado: mira cuántas veces cumplió la línea en sus últimos 5 a 25 partidos "
               "o en sus enfrentamientos directos.")
    st.markdown(THEME + CSS, unsafe_allow_html=True)
    circuito = st.radio("Circuito", ["ATP (hombres)", "WTA (mujeres)"], horizontal=True, key="tl_circuito")
    tour = "ATP" if circuito.startswith("ATP") else "WTA"
    if st.button("🔄 Actualizar datos ahora", key="tl_refresh", help="Borra la memoria guardada y vuelve a descargar los partidos más recientes."):
        st.cache_data.clear()
        for ruta in glob.glob(os.path.join(_CACHE_DIR, f"*_{date.today().year}.pkl")):
            try:
                os.remove(ruta)
            except OSError:
                pass
        st.rerun()
    try:
        with st.spinner("Cargando partidos..."):
            rows = _partidos(tour, date.today().year)
    except Exception as ex:  # noqa: BLE001
        st.error(f"No se pudieron descargar los partidos de {tour} desde internet. Detalle: {str(ex)[:700]}")
        st.info(f"Solución: descarga los archivos de https://www.tennis-data.co.uk/data.php (columna {tour}) y súbelos aquí, "
                f"o ponlos en la carpeta «{CARPETA_DATOS}/» del repositorio como {tour}_2025.xlsx, {tour}_2024.xlsx, etc.")
        subidos = st.file_uploader(f"Sube los archivos de {tour} (.xlsx, .xls o .csv; puedes subir varios años a la vez)",
                                   type=["xlsx", "xls", "csv"], accept_multiple_files=True, key=f"tl_sube_{tour}")
        if not subidos:
            return
        try:
            rows = _partidos_subidos(subidos)
        except Exception as ex2:  # noqa: BLE001
            st.error(f"No se pudo usar lo que subiste: {ex2}")
            return

    jugadores, rankings = _lista_jugadores(rows)
    st.caption(f"🗓️ Datos cargados hasta el {rows['Date'].max():%d/%m/%Y}. Si faltan partidos recientes, "
               f"pulsa «Actualizar datos ahora».")
    if not jugadores:
        st.warning("No hay jugadores con partidos suficientes en el periodo cargado.")
        return
    fmt = lambda n: n if n not in rankings else f"{n} · #{int(rankings[n])}"   # noqa: E731
    c1, c2 = st.columns(2)
    nom_a = c1.selectbox("Jugador A", jugadores, key=f"tl_a_{tour}", format_func=fmt)
    opciones_b = ["—"] + [j for j in jugadores if j != nom_a]
    if st.session_state.get(f"tl_b_{tour}") not in opciones_b:
        st.session_state.pop(f"tl_b_{tour}", None)
    nom_b = c2.selectbox("Jugador B (opcional, para comparar)", opciones_b, key=f"tl_b_{tour}",
                         format_func=lambda n: n if n == "—" else fmt(n))
    dos = nom_b != "—"
    jug_a = {"nombre": nom_a, "rank": rankings.get(nom_a), "color": _color_jugador(nom_a), "ini": _iniciales(nom_a)}
    jug_b = {"nombre": nom_b, "rank": rankings.get(nom_b), "color": _color_jugador(nom_b), "ini": _iniciales(nom_b)} if dos else None

    grupo = st.radio("Tipo de mercado", list(MERCADOS_T), horizontal=True, key="tl_grupo", label_visibility="collapsed")
    opciones_m = list(MERCADOS_T[grupo])
    if st.session_state.get(f"tl_mercado_{grupo}") not in opciones_m:
        st.session_state.pop(f"tl_mercado_{grupo}", None)
    mercado = st.selectbox("Mercado", opciones_m, key=f"tl_mercado_{grupo}")
    ventanas = [5, 10, 15, 20, 25] + (["h2h"] if dos else [])
    ventana = st.radio("Partidos a analizar", ventanas, index=1, horizontal=True, key="tl_ventana",
                       format_func=lambda v: "⚔️ Enfrentamientos directos" if v == "h2h" else f"Últimos {v}")
    h2h = ventana == "h2h"
    f1, f2 = st.columns(2)
    sup_txt = f1.radio("Superficie", ["Todas", "Dura", "Arcilla", "Césped"], horizontal=True, key="tl_sup",
                       help="Filtra los partidos analizados: por ejemplo, cómo rinde solo en arcilla. Se toman los últimos N de esa superficie.")
    mejor_txt = f2.radio("Formato", ["Todos", "Mejor de 3", "Mejor de 5"], horizontal=True, key="tl_mejor",
                         help="Los Grand Slam masculinos se juegan a 5 sets; casi todo lo demás, a 3.")
    sup = None if sup_txt == "Todas" else sup_txt
    mejor = {"Mejor de 3": 3, "Mejor de 5": 5}.get(mejor_txt)

    n = 25 if h2h else ventana
    if h2h:
        da = _ventana(rows, nom_a, n, nom_b, sup, mejor)
        db = _ventana(rows, nom_b, n, nom_a, sup, mejor)
    else:
        da = _ventana(rows, nom_a, n, None, sup, mejor)
        db = _ventana(rows, nom_b, n, None, sup, mejor) if dos else None
    sa, sb = _serie(da), (_serie(db) if dos else [])
    if not sa:
        if h2h:
            st.info("Estos jugadores no se enfrentan con estos filtros en el periodo cargado. Prueba con otra superficie o formato.")
        else:
            st.warning(f"No hay partidos de {nom_a} con estos filtros. Prueba con otra superficie o formato.")
        return
    if dos and not sb and not h2h:
        st.warning(f"No hay partidos de {nom_b} con estos filtros. Prueba con otra superficie o formato.")
        return
    u = sa[-1]
    st.caption(f"📌 Último partido cargado de {nom_a}: {u['fecha']:%d/%m/%Y} vs {u['rival']} ({u['torneo']}, {u['sup']}) · "
               f"{'ganó' if u['gana'] else 'perdió'} {u['marcador']}")

    m = MERCADOS[mercado]
    campo = m.dato or m.clave
    medianas = [median(_valores(s, campo)) for s in (sa, sb) if _valores(s, campo)]
    if m.tipo == "handicap":
        sugerida = -(math.ceil(medianas[0] if len(medianas) == 1 else (medianas[0] - medianas[1]) / 2) - 0.5)
    else:
        sugerida = _medio(mean(medianas))

    l1, l2 = st.columns(2)
    if m.tipo == "sino":
        linea, lado = 0.0, "Más de"
        l1.caption(m.ayuda)
    elif m.tipo == "handicap":
        linea = l1.number_input(f"Hándicap de {nom_a}", -m.rango, m.rango, float(min(max(sugerida, -m.rango), m.rango)), 0.5,
                                format="%+.1f", key=f"tl_l_{m.clave}_{nom_a}_{nom_b}", help=m.ayuda)
        lado = "Más de"
    else:
        sugerida = min(max(sugerida, 0.5), 99.5)
        linea = l1.number_input("Línea", 0.5, 99.5, float(sugerida), 1.0, format="%.1f", key=f"tl_l5_{m.clave}_{nom_a}_{nom_b}")
        if linea % 1 == 0:
            linea += 0.5
        lado = l2.radio("Apuesta", ["Más de", "Menos de"], horizontal=True, key="tl_lado")

    etiqueta = mercado + (f" · {sup_txt}" if sup else "") + (f" · {mejor_txt.lower()}" if mejor else "")
    cards = [(jug_a, sa, linea)] + ([(jug_b, sb, -linea if m.tipo == "handicap" else linea)] if dos else [])
    for col, (jug, serie, ln) in zip(st.columns(len(cards)), cards):
        col.markdown(_tarjeta(jug, serie, m, ln, lado, etiqueta, h2h=h2h), unsafe_allow_html=True)

    if dos:
        _boton_autoanalisis(rows, jug_a, jug_b, tour, ventana, sup, mejor)
    else:
        st.button("🤖 Autoanálisis de todas las líneas", key="tl_auto_dis", disabled=True,
                  help="Elige un Jugador B para comparar y activar el autoanálisis.")
    if dos:
        st.markdown("#### Comparativa")
        st.dataframe(_comparativa(nom_a, nom_b, sa, sb, "Promedio (enfrentamientos directos)" if h2h else f"Promedio (últimos {ventana})"),
                     hide_index=True, use_container_width=True)
        hist = _historial(rows, nom_a, nom_b)
        with st.expander(f"⚔️ Historial entre ambos ({len(hist)} partidos cargados)"):
            if hist.empty:
                st.write("No se han enfrentado en el periodo cargado.")
            else:
                ganados = int(rows[(rows.Jugador == nom_a) & (rows.Rival == nom_b)].Gana.sum())
                st.markdown(f"**{nom_a} {ganados} – {len(hist) - ganados} {nom_b}**")
                st.dataframe(hist, hide_index=True, use_container_width=True)
        with st.spinner("Calculando líneas con racha..."):
            n_rec = ventana if isinstance(ventana, int) else 10
            ra = sa if not h2h else _serie(_ventana(rows, nom_a, n_rec, None, sup, mejor))
            rb = sb if not h2h else _serie(_ventana(rows, nom_b, n_rec, None, sup, mejor))
            ha = sa if h2h else _serie(_ventana(rows, nom_a, 25, nom_b))
            hb = sb if h2h else _serie(_ventana(rows, nom_b, 25, nom_a))
        if ra and rb:
            _seccion_racha(jug_a, jug_b, ra, rb, ha, hb)

    with st.expander("📋 Perfil por superficie y forma reciente"):
        for jug in [jug_a] + ([jug_b] if dos else []):
            st.markdown(f"**{jug['nombre']}**")
            st.markdown(_forma_html(rows, jug["nombre"]), unsafe_allow_html=True)
            perfil = _perfil(rows, jug["nombre"])
            if not perfil.empty:
                st.dataframe(perfil, hide_index=True, use_container_width=True)
    st.caption("La frecuencia es histórica (cuántas veces cumplió la línea), no una predicción del partido. El hándicap del Jugador B es el opuesto al del A. "
               f"Datos: TennisMyLife (en vivo), con respaldo en tennis-data.co.uk; últimas {ANIOS} temporadas; solo partidos completados (sin retiros ni walkovers). "
               "Esta herramienta no usa aces ni dobles faltas. Pasa el cursor sobre una barra para ver el partido.")


if __name__ == "__main__":
    st.set_page_config(page_title="Líneas de jugadores · Tenis", layout="wide")
    render()
