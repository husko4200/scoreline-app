"""Fútbol: misma estructura que la NBA, en un solo archivo.

Un grupo (Equipos) con sus vistas. Datos: football-data.co.uk (resultados, tiros, córners, tarjetas) y ESPN
(marcadores en vivo). Los datos se cargan una vez por selección de liga y temporadas.
"""
import io
import math
from collections import namedtuple

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import confederaciones
import pulido
import selecciones
from common import (COLOR_A, COLOR_B, COLOR_NEG, COLOR_NEUTRO, COLOR_POS, ZONA, get_bytes, get_json,
                    num, racha_resultado)

# ================================================================ constantes
LIGAS = {
    "Premier League (Inglaterra)": "E0", "La Liga (España)": "SP1", "Bundesliga (Alemania)": "D1",
    "Serie A (Italia)": "I1", "Ligue 1 (Francia)": "F1", "Eredivisie (Países Bajos)": "N1",
    "Primeira Liga (Portugal)": "P1", "Premiership (Escocia)": "SC0",
    "Championship (Inglaterra, 2ª)": "E1", "Segunda División (España)": "SP2", "2. Bundesliga (Alemania)": "D2",
    "Serie B (Italia)": "I2", "Ligue 2 (Francia)": "F2", "Pro League (Bélgica)": "B1",
    "Süper Lig (Turquía)": "T1", "Super League (Grecia)": "G1",
}
SELECCIONES = "🌍 Selecciones nacionales"   # opción extra del selector de liga (no es una liga de football-data)
URL_SELECCIONES = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
DESDE_SELECCIONES = 2010   # se descarga desde aquí: sirve para calcular el Elo con historia y elegir los años a analizar
LIGAS_AMERICA = {"Liga Argentina": "ARG", "Brasileirão (Brasil)": "BRA", "MLS (EE.UU.)": "USA", "Liga MX (México)": "MEX"}
TEMPORADAS = {"2026/27": "2627", "2025/26": "2526", "2024/25": "2425", "2023/24": "2324",
              "2022/23": "2223", "2021/22": "2122", "2020/21": "2021", "2019/20": "1920"}
BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
URL_NEW = "https://www.football-data.co.uk/new/{code}.csv"
NUM = ["FTHG", "FTAG", "HTHG", "HTAG", "HS", "AS", "HST", "AST", "HC", "AC", "HF", "AF", "HY", "AY", "HR", "AR"]

# Códigos de liga de ESPN para el marcador en vivo
LIGAS_VIVO = {
    "Primera División de Chile": "chi.1", "Premier League": "eng.1", "La Liga": "esp.1",
    "Bundesliga": "ger.1", "Serie A": "ita.1", "Ligue 1": "fra.1", "Champions League": "uefa.champions",
    "Copa Libertadores": "conmebol.libertadores", "Copa Sudamericana": "conmebol.sudamericana",
    "MLS": "usa.1", "Liga Argentina": "arg.1", "Brasileirão": "bra.1",
    "Mundial (selecciones)": "fifa.world", "Amistosos de selecciones": "fifa.friendly",
}
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/scoreboard"

# Etiquetas de las vistas (un solo lugar para editar nombres)
G_EQUIPOS = "🛡️ Equipos"
LINEAS, PROXIMOS, JUGADOR = "🎯 Líneas", "📅 Próximos", "🧍 Jugador"

Liga = namedtuple("Liga", "df t rat hist codigo")  # partidos, partidos por equipo, Elo, historial de Elo, código de liga


# ================================================================ datos
def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"]).copy()
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    for c in NUM:
        if c not in df.columns:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False)
def descargar(season: str, league: str) -> pd.DataFrame:
    status, contenido = get_bytes(BASE_URL.format(season=season, league=league))
    if status == 404:
        return pd.DataFrame()
    return limpiar(pd.read_csv(io.StringIO(contenido.decode("latin-1"))))


@st.cache_data(ttl=3600, show_spinner=False)
def descargar_america(codigo: str) -> pd.DataFrame:
    """Archivos /new/: todas las temporadas en un CSV (sin tiros ni córners)."""
    status, contenido = get_bytes(URL_NEW.format(code=codigo))
    if status == 404:
        return pd.DataFrame()
    raw = pd.read_csv(io.StringIO(contenido.decode("latin-1")))
    raw = raw.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG"})
    if "HomeTeam" not in raw.columns or "FTHG" not in raw.columns:
        return pd.DataFrame()
    raw["Temporada"] = raw["Season"].astype(str) if "Season" in raw.columns else "Todas"
    return limpiar(raw)


@st.cache_data(ttl=3600, show_spinner=False)
def descargar_selecciones() -> pd.DataFrame:
    """Resultados de selecciones nacionales (martj42/international_results). No trae tiros, córners ni tarjetas."""
    status, contenido = get_bytes(URL_SELECCIONES)
    if status == 404:
        return pd.DataFrame()
    raw = pd.read_csv(io.StringIO(contenido.decode("utf-8")))
    raw = raw.rename(columns={"date": "Date", "home_team": "HomeTeam", "away_team": "AwayTeam", "home_score": "FTHG",
                              "away_score": "FTAG", "tournament": "Torneo"})
    raw["Date"] = pd.to_datetime(raw["Date"], errors="coerce")
    raw = raw[raw["Date"].dt.year >= DESDE_SELECCIONES].copy()
    raw["Neutral"] = raw["neutral"].astype(str).str.upper().eq("TRUE")
    # confederación según el nombre original (en inglés), antes de traducir los nombres
    raw["ConfHome"], raw["ConfAway"] = raw["HomeTeam"].map(confederaciones.de), raw["AwayTeam"].map(confederaciones.de)
    raw["HomeTeam"], raw["AwayTeam"] = raw["HomeTeam"].map(selecciones.nombre), raw["AwayTeam"].map(selecciones.nombre)
    raw["Temporada"] = raw["Date"].dt.year.astype(str)
    return limpiar(raw)


def partidos_por_equipo(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por equipo y partido, con estadísticas y banderas para rachas y líneas."""
    def lado(local: bool) -> pd.DataFrame:
        p, q = ("H", "A") if local else ("A", "H")
        return pd.DataFrame({
            "Date": df["Date"], "Temporada": df["Temporada"],
            "Equipo": df["HomeTeam"] if local else df["AwayTeam"], "Rival": df["AwayTeam"] if local else df["HomeTeam"],
            "Condicion": "Local" if local else "Visita", "Neutral": df["Neutral"] if "Neutral" in df.columns else False,
            "Conf": df["ConfHome" if local else "ConfAway"] if "ConfHome" in df.columns else None,
            "GF": df[f"FT{p}G"], "GC": df[f"FT{q}G"], "GF1T": df[f"HT{p}G"], "GC1T": df[f"HT{q}G"],
            "Tiros": df[f"{p}S"], "TirosRival": df[f"{q}S"], "TP": df[f"{p}ST"], "TPRival": df[f"{q}ST"],
            "Corners": df[f"{p}C"], "CornersRival": df[f"{q}C"], "Faltas": df[f"{p}F"],
            "Amarillas": df[f"{p}Y"], "Rojas": df[f"{p}R"],
            "FaltasRival": df[f"{q}F"], "AmarillasRival": df[f"{q}Y"], "RojasRival": df[f"{q}R"]})

    t = pd.concat([lado(True), lado(False)], ignore_index=True).sort_values(["Equipo", "Date"]).reset_index(drop=True)
    t["Resultado"] = np.where(t.GF > t.GC, "G", np.where(t.GF < t.GC, "P", "E"))
    t["Puntos"] = t["Resultado"].map({"G": 3, "E": 1, "P": 0})
    t["Gana"], t["Pierde"] = t.Resultado == "G", t.Resultado == "P"
    t["SinPerder"], t["SinGanar"] = t.Resultado != "P", t.Resultado != "G"
    t["ArcoEnCero"], t["Anota"], t["Concede"] = t.GC == 0, t.GF > 0, t.GC > 0
    t["Total"], t["Margen"] = t.GF + t.GC, t.GF - t.GC
    t["Over25"], t["BTTS"] = t.Total > 2.5, (t.GF > 0) & (t.GC > 0)
    t["BTTSn"] = t["BTTS"].astype(float)
    t["Goles1T"] = t.GF1T + t.GC1T
    t["Goles2T"] = t.Total - t.Goles1T
    t["CornersTotal"] = t.Corners + t.CornersRival
    dia = t["Date"].dt.normalize()
    desc = (dia - dia.groupby(t["Equipo"]).shift()).dt.days - 1
    t["Descanso"] = desc.where(desc <= 14).clip(lower=0)
    return t


# ================================================================ modelos
@st.cache_data(show_spinner=False)
def calcular_elo(df: pd.DataFrame, k: float = 20.0, ventaja: float = 60.0, regresion: float = 0.25):
    """Elo por equipo con multiplicador por diferencia de goles y regresión parcial entre temporadas."""
    rat, ult, hist = {}, {}, []
    for r in df.sort_values("Date").itertuples(index=False):
        h, a = r.HomeTeam, r.AwayTeam
        for tm in (h, a):
            if tm not in rat:
                rat[tm] = 1500.0
            elif regresion and ult.get(tm) != r.Temporada:
                rat[tm] = (1 - regresion) * rat[tm] + regresion * 1500.0
            ult[tm] = r.Temporada
        dif = rat[h] + (0.0 if getattr(r, "Neutral", False) else ventaja) - rat[a]
        esp = 1 / (1 + 10 ** (-dif / 400))
        res = 1.0 if r.FTHG > r.FTAG else 0.0 if r.FTHG < r.FTAG else 0.5
        delta = k * (math.log(abs(r.FTHG - r.FTAG) + 1) + 1) * (res - esp)
        rat[h], rat[a] = rat[h] + delta, rat[a] - delta
        hist += [(r.Date, h, rat[h]), (r.Date, a, rat[a])]
    return rat, pd.DataFrame(hist, columns=["Date", "Equipo", "Elo"])


def _poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def predecir(df: pd.DataFrame, local: str, visita: str, max_goles: int = 7):
    """Modelo Poisson con ataque y defensa local/visita. Devuelve (goles esperados local, visita, matriz de marcadores)."""
    pl, pv = df["FTHG"].mean(), df["FTAG"].mean()
    loc = df.groupby("HomeTeam").agg(gf=("FTHG", "mean"), gc=("FTAG", "mean"))
    vis = df.groupby("AwayTeam").agg(gf=("FTAG", "mean"), gc=("FTHG", "mean"))
    lam_l = (loc.gf[local] / pl) * (vis.gc[visita] / pl) * pl
    lam_v = (vis.gf[visita] / pv) * (loc.gc[local] / pv) * pv
    m = np.array([[_poisson(i, lam_l) * _poisson(j, lam_v) for j in range(max_goles + 1)] for i in range(max_goles + 1)])
    return lam_l, lam_v, m / m.sum()


def _resumen_modelo(m: np.ndarray) -> dict:
    n = m.shape[0]
    idx = np.add.outer(np.arange(n), np.arange(n))
    return {"L": np.tril(m, -1).sum(), "E": np.trace(m), "V": np.triu(m, 1).sum(),
            "o15": m[idx > 1.5].sum(), "o25": m[idx > 2.5].sum(), "o35": m[idx > 3.5].sum(), "btts": m[1:, 1:].sum()}


# ================================================================ vistas: Equipos
FILAS_COMPARATIVA = [  # (nombre, columna, ¿más es mejor? None = sin líder)
    ("Puntos por partido", "Puntos", True), ("Goles a favor", "GF", True), ("Goles en contra", "GC", False),
    ("Goles del partido", "Total", None), ("Tiros", "Tiros", True), ("Tiros a puerta", "TP", True),
    ("Córners", "Corners", True), ("Faltas", "Faltas", False), ("Amarillas", "Amarillas", False),
    ("Portería en cero %", "ArcoEnCero", True), ("Más de 2.5 goles %", "Over25", None), ("Ambos anotan %", "BTTS", None)]


def _comparativa(a, b, sa, sb, titulo):
    filas = []
    for nombre, col, mejor in FILAS_COMPARATIVA:
        va, vb = sa[col].astype(float).mean(), sb[col].astype(float).mean()
        if pd.isna(va) and pd.isna(vb):
            continue
        k = 100 if col in ("ArcoEnCero", "Over25", "BTTS") else 1
        lider = "—"
        if mejor is not None and pd.notna(va) and pd.notna(vb) and round(va, 2) != round(vb, 2):
            lider = a if (va > vb) == mejor else b
        filas.append({titulo: nombre, a: round(va * k, 2), b: round(vb * k, 2), "Líder": lider})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------- Líneas
def vista_lineas(liga):
    """Líneas de equipos con escudos, igual que la NBA (ver football_lineas.py)."""
    import football_lineas  # aquí dentro para no crear una importación circular
    football_lineas.render(liga, _comparativa)


def vista_proximos(liga):
    """Partidos de hoy y mañana con su pronóstico; «Analizar» lleva a «Líneas» con los dos equipos ya cargados."""
    import planes
    if not planes.es_pro(planes.uid_actual()):
        planes.bloque_pro(
            "Modelo Poisson (marcador exacto y goles esperados)",
            "Proyección completa habilitada",
            "Local 2 - 1 Visita · 2.65 goles esperados · Más de 2.5 (63%)",
            key="btn_lock_fut_prox",
        )
        return
    import football_proximos
    football_proximos.proximos(liga)


def vista_jugador(liga):
    """Estadísticas de un jugador y cómo le fue contra el rival (ver football_lineas.render_jugador)."""
    import football_lineas  # aquí dentro para no crear una importación circular
    football_lineas.render_jugador(liga)


# ================================================================ en vivo
@st.cache_data(ttl=20, show_spinner=False)
def marcador_en_vivo(liga: str) -> list[dict]:
    j = get_json(ESPN.format(liga=liga))
    out = []
    for e in j.get("events", []):
        comp = (e.get("competitions") or [{}])[0]
        est = e.get("status") or comp.get("status") or {}
        tipo = est.get("type") or {}
        cs = comp.get("competitors") or []
        loc = next((c for c in cs if c.get("homeAway") == "home"), None)
        vis = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not loc or not vis:
            continue
        nombre = lambda c: (c.get("team") or {}).get("displayName") or "?"  # noqa: E731
        ids = {str((loc.get("team") or {}).get("id")): "L", str((vis.get("team") or {}).get("id")): "V"}
        eventos = []
        for d in comp.get("details") or []:
            tx = (d.get("type") or {}).get("text") or ""
            minuto = (d.get("clock") or {}).get("displayValue") or ""
            quien = ", ".join(a.get("displayName", "") for a in d.get("athletesInvolved", []))
            eventos.append((minuto, tx, quien, ids.get(str((d.get("team") or {}).get("id")), "")))
        out.append({"estado": tipo.get("state", "pre"), "minuto": est.get("displayClock") or tipo.get("shortDetail") or "",
                    "detalle": tipo.get("shortDetail") or "", "fecha": e.get("date"),
                    "local": nombre(loc), "visita": nombre(vis),
                    "gl": num(loc.get("score")), "gv": num(vis.get("score")), "eventos": eventos})
    return out


def _avisar_marcadores(liga_n, partidos, filas):
    """Marca (invisible) el marcador de cada partido en vivo; movimiento.py detecta el cambio y celebra el gol.
    El id lleva liga y equipos para que no se confunda un partido con otro."""
    from html import escape
    marcas = []
    for p, fila in zip(partidos, filas):
        if p["estado"] != "in":
            continue
        ident = escape(f"{liga_n}|{p['local']}|{p['visita']}", quote=True)
        nombre = escape(f"{p['local']} vs {p['visita']}", quote=True)
        marcas.append(f'<span class="pl-hook" data-pl-score data-pl-id="{ident}" data-pl-nombre="{nombre}">{escape(fila["Marcador"])}</span>')
    if marcas:
        st.markdown("".join(marcas), unsafe_allow_html=True)


def live_panel():
    liga_n = st.selectbox("Liga", list(LIGAS_VIVO), key="f_live_liga")
    try:
        partidos = marcador_en_vivo(LIGAS_VIVO[liga_n])
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo leer el marcador de ESPN: {e}")
        return
    if not partidos:
        st.info("No hay partidos de esta liga hoy.")
        return
    orden = {"in": 0, "pre": 1, "post": 2}
    partidos = sorted(partidos, key=lambda p: orden.get(p["estado"], 3))
    filas = []
    for p in partidos:
        det = p["minuto"] if p["estado"] == "in" else p["detalle"]
        if p["estado"] == "pre" and p["fecha"]:
            try:
                det = pd.to_datetime(p["fecha"], utc=True).tz_convert(ZONA).strftime("%d/%m %H:%M")
            except Exception:  # noqa: BLE001
                pass
        marc = f"{p['gl']:.0f} - {p['gv']:.0f}" if p["gl"] is not None and p["gv"] is not None else "-"
        filas.append({"Estado": {"in": "🔴 En vivo", "post": "Final", "pre": "Por jugar"}.get(p["estado"], p["estado"]),
                      "Detalle": det, "Local": p["local"], "Marcador": marc, "Visita": p["visita"]})
    vivo = sum(p["estado"] == "in" for p in partidos)
    st.caption(f"{vivo} en vivo · {len(partidos)} partidos · actualizado {pd.Timestamp.now(tz=ZONA).strftime('%H:%M:%S')}")
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    _avisar_marcadores(liga_n, partidos, filas)   # movimiento.py: fanfarria, confeti y aviso cuando cambia un marcador
    con_ev = [i for i, p in enumerate(partidos) if p["eventos"]]
    if con_ev:
        i = st.selectbox("Ver goles y tarjetas", con_ev, key="f_live_ev",
                         format_func=lambda i: f"{partidos[i]['local']} {filas[i]['Marcador']} {partidos[i]['visita']}")
        for minuto, tx, quien, lado in partidos[i]["eventos"]:
            st.write(f"`{minuto}` {tx} — {quien} ({'local' if lado == 'L' else 'visita' if lado == 'V' else ''})")


# ================================================================ página
# Un solo lugar para añadir, quitar o reordenar vistas: grupo -> {etiqueta: función(liga)}.
VISTAS = {
    G_EQUIPOS: {LINEAS: vista_lineas, PROXIMOS: vista_proximos, JUGADOR: vista_jugador},
}
GRUPOS = {grupo: list(vistas) for grupo, vistas in VISTAS.items()}


def _temporadas_por_defecto():
    """La temporada en curso y la anterior (las europeas empiezan en agosto), solo si existen en TEMPORADAS."""
    hoy = pd.Timestamp.today()
    ini = hoy.year if hoy.month >= 7 else hoy.year - 1
    etiquetas = [f"{a}/{(a + 1) % 100:02d}" for a in (ini, ini - 1)]
    return [e for e in etiquetas if e in TEMPORADAS] or list(TEMPORADAS)[:2]


_CLAVE_TS = "f_datos_ts"  # momento en que esta sesión cargó los datos de la liga


def _actualizar():
    """Callback del botón: vacía las cachés de datos y fuerza a recargar la liga."""
    for f in (descargar, descargar_america, descargar_selecciones, calcular_elo, marcador_en_vivo):
        f.clear()
    import football_recientes
    football_recientes.limpiar_cache()
    st.session_state.pop(_CLAVE_TS, None)


def _barra_datos():
    """Misma barra que la NBA: cuándo se cargaron los datos + botón para actualizarlos."""
    ts = st.session_state.get(_CLAVE_TS)
    c1, c2 = st.columns([5, 2], vertical_alignment="center")
    if ts is None:
        c1.caption("🕒 Datos de la liga: aún sin cargar.")
    else:
        mins = int((pd.Timestamp.now(tz=ZONA) - ts).total_seconds() // 60)
        hace = "hace menos de 1 min" if mins < 1 else f"hace {mins} min"
        c1.caption(f"🕒 Datos al: {ts:%d/%m/%Y %H:%M} ({hace})")
    c2.button("🔄 Actualizar datos", on_click=_actualizar, use_container_width=True, key="f_actualizar",
              help="Vuelve a descargar los partidos y marcadores. Los archivos de football-data.co.uk se guardan 1 hora.")


def _cargar_selecciones(columna):
    """Selecciones nacionales: años y tipo de partido en la página. El Elo se calcula con todo el historial descargado
    (desde 2010), así el ranking es el de hoy aunque analices solo un año. Devuelve Liga o None si falla."""
    try:
        completo = descargar_selecciones()
    except Exception as e:  # noqa: BLE001
        _barra_datos()
        st.error(f"No se pudieron descargar los resultados de selecciones: {e}")
        return None
    if completo.empty:
        _barra_datos()
        st.error("No hay resultados de selecciones disponibles ahora.")
        return None
    anios = sorted(completo["Temporada"].unique(), reverse=True)
    hoy = pd.Timestamp.today().year
    temps = columna.multiselect("Años", anios, default=[a for a in (str(hoy), str(hoy - 1), str(hoy - 2)) if a in anios] or anios[:3],
                                key="f_sel_anios")
    tipo = st.radio("Partidos", ["Todos", "Oficiales (sin amistosos)", "Solo amistosos"], horizontal=True, key="f_sel_tipo")
    if not temps:
        _barra_datos()
        st.info("Elige al menos un año arriba.")
        return None
    df = completo[completo["Temporada"].isin(temps)]
    if tipo.startswith("Oficiales"):
        df = df[df["Torneo"] != "Friendly"]
    elif tipo.startswith("Solo"):
        df = df[df["Torneo"] == "Friendly"]
    df = df.reset_index(drop=True)
    if df.empty:
        _barra_datos()
        st.error("No hay partidos con ese filtro.")
        return None
    rat, hist = calcular_elo(completo, 30.0, 100.0, 0.0)   # sin ventaja de local en cancha neutral ni regresión por año
    st.session_state.setdefault(_CLAVE_TS, pd.Timestamp.now(tz=ZONA))
    _barra_datos()
    st.caption(f"Selecciones nacionales · {len(df):,} partidos · último: {df.Date.max():%d/%m/%Y} · {(df.FTHG + df.FTAG).mean():.2f} goles por partido "
               "· solo resultados: no trae tiros, córners ni tarjetas.")
    return Liga(df, partidos_por_equipo(df), rat, hist, "INT")


def _cargar_liga():
    """Selector de liga y temporadas dentro de la página (ya no en el menú lateral) + carga de datos.
    Devuelve Liga o None si falla."""
    c1, c2 = st.columns([2, 3], vertical_alignment="bottom")
    liga_n = c1.selectbox("Liga", list(LIGAS) + list(LIGAS_AMERICA) + [SELECCIONES], key="f_liga")
    if liga_n == SELECCIONES:
        return _cargar_selecciones(c2)
    america = liga_n in LIGAS_AMERICA
    base_am = None
    if america:
        try:
            base_am = descargar_america(LIGAS_AMERICA[liga_n])
        except Exception as e:  # noqa: BLE001
            st.error(f"No se pudo descargar {liga_n}: {e}")
        opciones = sorted(base_am["Temporada"].unique(), reverse=True) if base_am is not None and not base_am.empty else []
        temps = c2.multiselect("Temporadas", opciones, default=opciones[:2], key=f"f_temps_{LIGAS_AMERICA[liga_n]}")
    else:
        temps = c2.multiselect("Temporadas", list(TEMPORADAS), default=_temporadas_por_defecto(), key="f_temps_eu")
    if not temps:
        _barra_datos()
        st.info("Elige al menos una temporada arriba.")
        return None

    frames = []
    if america:
        if base_am is not None and not base_am.empty:
            frames.append(base_am[base_am["Temporada"].isin(temps)].copy())
    else:
        for tn in temps:
            try:
                d = descargar(TEMPORADAS[tn], LIGAS[liga_n])
            except Exception as e:  # noqa: BLE001
                st.warning(f"No se pudo cargar {tn}: {e}")
                continue
            if d.empty:
                st.warning(f"No se pudo cargar {tn}: archivo no disponible aún")
            else:
                frames.append(d.assign(Temporada=tn))
    if not frames:
        _barra_datos()
        st.error("No hay datos para mostrar.")
        return None
    df = pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)
    rat, hist = calcular_elo(df)
    st.session_state.setdefault(_CLAVE_TS, pd.Timestamp.now(tz=ZONA))
    _barra_datos()
    st.caption(f"{liga_n} · {len(df):,} partidos · {df.Temporada.nunique()} temporadas · último: {df.Date.max():%d/%m/%Y} "
               f"· {(df.FTHG + df.FTAG).mean():.2f} goles por partido")
    return Liga(df, partidos_por_equipo(df), rat, hist, None if america else LIGAS[liga_n])


def render():
    import football_lineas  # aquí dentro para no crear una importación circular
    football_lineas.fondo_futbol()   # fondo de cancha animado y botones sólidos
    pulido.cabecera("Fútbol", "Ligas y selecciones")
    if st.session_state.pop("f_ir_a_lineas", False):   # lo pone el botón «Analizar» de Próximos
        st.session_state["f_grupo"] = G_EQUIPOS
        st.session_state[f"f_vista_{G_EQUIPOS}"] = LINEAS
    # Con un solo grupo no hace falta el selector; si vuelves a añadir otro, aparece solo.
    if len(VISTAS) > 1:
        grupo = st.radio("Grupo", list(VISTAS), horizontal=True, label_visibility="collapsed", key="f_grupo")
    else:
        grupo = next(iter(VISTAS))
    if st.session_state.get(f"f_vista_{grupo}") not in VISTAS[grupo]:   # p. ej. quedó guardada una vista que ya no existe
        st.session_state.pop(f"f_vista_{grupo}", None)
    nombre = st.radio("Vista", list(VISTAS[grupo]), horizontal=True, label_visibility="collapsed", key=f"f_vista_{grupo}")
    st.divider()
    if nombre == JUGADOR:   # el buscador de jugadores no usa la liga ni las temporadas
        VISTAS[grupo][nombre](None)
        return
    liga = _cargar_liga()
    if liga is not None:
        VISTAS[grupo][nombre](liga)
