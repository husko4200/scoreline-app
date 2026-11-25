"""Fútbol (datos extra): cuotas del mercado, primer tiempo, estadísticas por equipo, árbitros,
próximos partidos con cuotas y ligas de América.

Todo sale de football-data.co.uk: los CSV que ya usa la app traen cuotas, árbitro, faltas y goles del
primer tiempo; `fixtures.csv` trae los próximos partidos con cuotas; /new/ trae Argentina, Brasil, etc.
"""
import io

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from common import COLOR_A, COLOR_B, COLOR_NEUTRO, get_bytes

FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"
URL_NEW = "https://www.football-data.co.uk/new/{code}.csv"
LIGAS_AMERICA = {"Liga Argentina": "ARG", "Brasileirão (Brasil)": "BRA", "MLS (EE.UU.)": "USA", "Liga MX (México)": "MEX"}

# fuente: (local, empate, visita, más de 2.5, menos de 2.5), de la mejor a la menos fina
CASAS = {
    "Pinnacle (cierre)": ("PSCH", "PSCD", "PSCA", "PC>2.5", "PC<2.5"),
    "Promedio del mercado (cierre)": ("AvgCH", "AvgCD", "AvgCA", "AvgC>2.5", "AvgC<2.5"),
    "Pinnacle": ("PSH", "PSD", "PSA", "P>2.5", "P<2.5"),
    "Promedio del mercado": ("AvgH", "AvgD", "AvgA", "Avg>2.5", "Avg<2.5"),
    "Promedio (formato antiguo)": ("BbAvH", "BbAvD", "BbAvA", "BbAv>2.5", "BbAv<2.5"),
    "Bet365": ("B365H", "B365D", "B365A", "B365>2.5", "B365<2.5"),
    "Mejor cuota del mercado": ("MaxH", "MaxD", "MaxA", "Max>2.5", "Max<2.5"),
}


# ================================================================ utilidades
def _asegurar(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    d = df.copy()
    for c in cols:
        if c not in d.columns:
            d[c] = np.nan
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def casas_disponibles(df: pd.DataFrame, minimo: float = 0.3) -> dict:
    """Fuentes de cuotas con al menos `minimo` de partidos con las tres cuotas 1X2 válidas."""
    out = {}
    for nombre, cols in CASAS.items():
        h, d, a = cols[:3]
        if all(c in df.columns for c in (h, d, a)):
            x = df[[h, d, a]].apply(pd.to_numeric, errors="coerce")
            if len(x) and (x > 1).all(axis=1).mean() >= minimo:
                out[nombre] = cols
    return out


def probs_mercado(df: pd.DataFrame, h: str, d: str, a: str) -> pd.DataFrame:
    """Probabilidades implícitas sin margen (normalizadas) y cuotas, solo en filas con las 3 cuotas."""
    o = df[[h, d, a]].apply(pd.to_numeric, errors="coerce")
    ok = (o > 1).all(axis=1)
    inv = 1 / o[ok]
    s = inv.sum(axis=1)
    p = inv.div(s, axis=0)
    p.columns = ["pH", "pD", "pA"]
    p["margen"] = s - 1
    p["oH"], p["oD"], p["oA"] = o.loc[ok, h], o.loc[ok, d], o.loc[ok, a]
    return p


def resultado_1x2(df: pd.DataFrame) -> pd.Series:
    return pd.Series(np.where(df.FTHG > df.FTAG, "H", np.where(df.FTHG < df.FTAG, "A", "D")), index=df.index)


def _elegir(p: pd.DataFrame, sel: pd.Series, prefijo: str) -> pd.Series:
    """Valor de la columna {prefijo}H/D/A que corresponde a la opción elegida en cada fila."""
    idx = sel.map({"H": 0, "D": 1, "A": 2}).to_numpy()
    arr = p[[f"{prefijo}H", f"{prefijo}D", f"{prefijo}A"]].to_numpy()
    return pd.Series(arr[np.arange(len(p)), idx], index=p.index)


def tabla_roi(p: pd.DataFrame, res: pd.Series) -> pd.DataFrame:
    fav = p[["pH", "pD", "pA"]].idxmax(axis=1).str[1:]
    out_ = p[["pH", "pD", "pA"]].idxmin(axis=1).str[1:]
    opciones = {"Siempre local": pd.Series("H", index=p.index), "Siempre empate": pd.Series("D", index=p.index),
                "Siempre visita": pd.Series("A", index=p.index), "Siempre el favorito": fav,
                "Siempre el menos probable": out_}
    filas = []
    for nombre, sel in opciones.items():
        cuota = _elegir(p, sel, "o")
        prob = _elegir(p, sel, "p")
        gana = (sel == res)
        filas.append({"Estrategia": nombre, "Apuestas": len(sel), "Aciertos %": gana.mean() * 100,
                      "Prob. del mercado %": prob.mean() * 100, "Cuota media": cuota.mean(),
                      "ROI %": (np.where(gana, cuota - 1, -1)).mean() * 100})
    return pd.DataFrame(filas).round(1)


def calibracion(p: pd.DataFrame, res: pd.Series) -> pd.DataFrame:
    partes = [pd.DataFrame({"p": p[f"p{k}"], "hit": (res == k).astype(float)}) for k in "HDA"]
    x = pd.concat(partes)
    x["tramo"] = pd.cut(x["p"], np.arange(0, 1.01, 0.1), include_lowest=True)
    g = x.groupby("tramo", observed=True).agg(n=("hit", "size"), esperado=("p", "mean"), real=("hit", "mean")).reset_index()
    g["tramo"] = g["tramo"].astype(str)
    return g


def largo_ext(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por equipo y partido con goles por tiempo, tiros, córners, faltas, tarjetas y mercados de goles."""
    cols = ["FTHG", "FTAG", "HTHG", "HTAG", "HS", "AS", "HST", "AST", "HC", "AC", "HF", "AF", "HY", "AY", "HR", "AR"]
    d = _asegurar(df, cols)

    def lado(local: bool) -> pd.DataFrame:
        p, q = ("H", "A") if local else ("A", "H")
        return pd.DataFrame({
            "Date": d["Date"], "Temporada": d["Temporada"],
            "Equipo": d["HomeTeam"] if local else d["AwayTeam"], "Rival": d["AwayTeam"] if local else d["HomeTeam"],
            "Condicion": "Local" if local else "Visita",
            "GF": d[f"FT{p}G"], "GC": d[f"FT{q}G"], "GF1T": d[f"HT{p}G"], "GC1T": d[f"HT{q}G"],
            "Tiros": d[f"{p}S"], "TirosRival": d[f"{q}S"], "TP": d[f"{p}ST"], "TPRival": d[f"{q}ST"],
            "Corners": d[f"{p}C"], "CornersRival": d[f"{q}C"], "Faltas": d[f"{p}F"], "FaltasRival": d[f"{q}F"],
            "Amarillas": d[f"{p}Y"], "AmarillasRival": d[f"{q}Y"], "Rojas": d[f"{p}R"]})

    t = pd.concat([lado(True), lado(False)], ignore_index=True).sort_values(["Equipo", "Date"]).reset_index(drop=True)
    t["Resultado"] = np.where(t.GF > t.GC, "G", np.where(t.GF < t.GC, "P", "E"))
    t["Puntos"] = t["Resultado"].map({"G": 3, "E": 1, "P": 0})
    t["Over25"] = (t.GF + t.GC) > 2.5
    t["BTTS"] = (t.GF > 0) & (t.GC > 0)
    t["ArcoEnCero"] = t.GC == 0
    return t


# ================================================================ mercado y cuotas
def vista_mercado(df: pd.DataFrame):
    casas = casas_disponibles(df)
    if not casas:
        st.info("Estas temporadas/ligas no traen cuotas en el archivo de football-data. "
                "Prueba con una liga europea y temporadas recientes.")
        return
    nombre = st.selectbox("Fuente de cuotas", list(casas), key="fx_casa",
                          help="Las de cierre (Pinnacle) son las más precisas; el promedio del mercado es más robusto.")
    h, d, a, o, u = casas[nombre]
    p = probs_mercado(df, h, d, a)
    if p.empty:
        st.info("No hay partidos con cuotas completas.")
        return
    base = df.loc[p.index]
    res = resultado_1x2(base)
    fav = p[["pH", "pD", "pA"]].idxmax(axis=1).str[1:]

    k = st.columns(5)
    k[0].metric("Partidos con cuotas", f"{len(p):,}")
    k[1].metric("Margen medio de la casa", f"{p['margen'].mean():.1%}")
    k[2].metric("El favorito gana", f"{(fav == res).mean():.1%}")
    k[3].metric("Gana local", f"{(res == 'H').mean():.1%}")
    k[4].metric("Empates", f"{(res == 'D').mean():.1%}")

    st.markdown("**Rentabilidad histórica de apostar siempre a la misma opción** (1 unidad por partido, sin comisiones)")
    st.dataframe(tabla_roi(p, res), hide_index=True, use_container_width=True)
    st.caption("ROI = ganancia media por unidad apostada. Con margen de la casa, lo normal es un ROI levemente negativo. "
               "Un ROI alto en pocos partidos suele ser azar, no una ventaja.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**¿Qué tan bien calibrado está el mercado?**")
        g = calibracion(p, res)
        pts = alt.Chart(g).mark_circle(size=90, color=COLOR_A).encode(
            x=alt.X("esperado:Q", title="Probabilidad según el mercado", scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("real:Q", title="Frecuencia real", scale=alt.Scale(domain=[0, 1])),
            tooltip=["tramo", "n", alt.Tooltip("esperado", format=".1%"), alt.Tooltip("real", format=".1%")])
        diag = alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]})).mark_line(
            color=COLOR_NEUTRO, strokeDash=[4, 4]).encode(x="x:Q", y="y:Q")
        st.altair_chart((diag + pts).properties(height=300), use_container_width=True)
        st.caption("Si los puntos están sobre la diagonal, el mercado acierta sus probabilidades.")
    with c2:
        st.markdown("**Más/menos de 2.5 goles**")
        if o in df.columns and u in df.columns:
            ou = base[[o, u]].apply(pd.to_numeric, errors="coerce")
            ok = (ou > 1).all(axis=1)
            if ok.any():
                inv = 1 / ou[ok]
                p_over = inv[o] / inv.sum(axis=1)
                over = ((base.FTHG + base.FTAG)[ok] > 2.5)
                st.dataframe(pd.DataFrame({
                    "Métrica": ["Partidos", "Over 2.5 real %", "Over 2.5 según mercado %", "ROI siempre over %", "ROI siempre under %"],
                    "Valor": [int(ok.sum()), round(over.mean() * 100, 1), round(p_over.mean() * 100, 1),
                              round(np.where(over, ou.loc[ok, o] - 1, -1).mean() * 100, 1),
                              round(np.where(~over, ou.loc[ok, u] - 1, -1).mean() * 100, 1)]}),
                    hide_index=True, use_container_width=True)
            else:
                st.caption("Sin cuotas de goles válidas.")
        else:
            st.caption("Esta fuente no trae cuotas de más/menos de goles.")

    st.markdown("**Rendimiento de cada equipo frente a lo que esperaba el mercado**")
    loc = pd.DataFrame({"Equipo": base.HomeTeam, "p": p.pH, "o": p.oH, "gana": res == "H"})
    vis = pd.DataFrame({"Equipo": base.AwayTeam, "p": p.pA, "o": p.oA, "gana": res == "A"})
    x = pd.concat([loc, vis])
    x["r"] = np.where(x.gana, x.o - 1, -1.0)
    g = x.groupby("Equipo").agg(PJ=("gana", "size"), Victorias=("gana", "mean"), Esperado=("p", "mean"), ROI=("r", "mean"))
    g["Victorias %"], g["Esperado %"] = g.pop("Victorias") * 100, g.pop("Esperado") * 100
    g["Diferencia (pp)"] = g["Victorias %"] - g["Esperado %"]
    g["ROI %"] = g.pop("ROI") * 100
    minimo = st.slider("Mínimo de partidos", 1, int(max(g.PJ.max(), 2)), int(min(10, max(g.PJ.max(), 1))), key="fx_roi_min")
    v = g[g.PJ >= minimo].sort_values("Diferencia (pp)", ascending=False).round(1).reset_index()
    st.dataframe(v, hide_index=True, use_container_width=True)
    st.caption("Diferencia positiva = el equipo gana más de lo que el mercado esperaba (ROI > 0 si apostabas por él siempre).")


# ================================================================ primer tiempo
def vista_primer_tiempo(df: pd.DataFrame):
    d = _asegurar(df, ["HTHG", "HTAG", "FTHG", "FTAG"]).dropna(subset=["HTHG", "HTAG", "FTHG", "FTAG"])
    if d.empty:
        st.info("Estos datos no traen goles del primer tiempo.")
        return
    nombres = {"H": "Local", "D": "Empate", "A": "Visita"}
    ht = pd.Series(np.where(d.HTHG > d.HTAG, "H", np.where(d.HTHG < d.HTAG, "A", "D")), index=d.index).map(nombres)
    ft = resultado_1x2(d).map(nombres)
    orden = ["Local", "Empate", "Visita"]
    cnt = pd.crosstab(ht, ft).reindex(index=orden, columns=orden, fill_value=0)
    pct = (cnt.div(cnt.sum(axis=1).replace(0, np.nan), axis=0) * 100).round(1)
    g1, g2 = (d.HTHG + d.HTAG), (d.FTHG + d.FTAG) - (d.HTHG + d.HTAG)
    k = st.columns(4)
    k[0].metric("Goles 1er tiempo", f"{g1.mean():.2f}")
    k[1].metric("Goles 2do tiempo", f"{g2.mean():.2f}")
    k[2].metric("% de goles en el 2do tiempo", f"{g2.sum() / max(g1.sum() + g2.sum(), 1):.1%}")
    k[3].metric("Partidos con gol en el 1T", f"{(g1 > 0).mean():.0%}")

    st.markdown("**Del descanso al final** (cada fila suma 100%)")
    st.dataframe(pct.rename_axis("Al descanso ↓ / Final →"), use_container_width=True)
    st.caption(f"Muestra: {len(d):,} partidos. Cuenta de partidos: " +
               " · ".join(f"{i} → {', '.join(f'{c} {cnt.loc[i, c]}' for c in orden)}" for i in orden))

    t = largo_ext(df).dropna(subset=["GF1T", "GC1T"])
    t["GF2T"], t["GC2T"] = t.GF - t.GF1T, t.GC - t.GC1T
    filas = []
    for eq, x in t.groupby("Equipo"):
        gan, per = x[x.GF1T > x.GC1T], x[x.GF1T < x.GC1T]
        filas.append({"Equipo": eq, "PJ": len(x), "GF 1T": x.GF1T.mean(), "GF 2T": x.GF2T.mean(),
                      "GC 1T": x.GC1T.mean(), "GC 2T": x.GC2T.mean(),
                      "% goles a favor en 2T": x.GF2T.sum() / x.GF.sum() * 100 if x.GF.sum() else np.nan,
                      "Gana si va ganando al descanso %": (gan.Resultado == "G").mean() * 100 if len(gan) else np.nan,
                      "Remonta si va perdiendo %": (per.Resultado == "G").mean() * 100 if len(per) else np.nan})
    st.markdown("**Por equipo**")
    tabla = pd.DataFrame(filas).sort_values("% goles a favor en 2T", ascending=False).round(2)
    st.dataframe(tabla, hide_index=True, use_container_width=True)


# ================================================================ estadísticas por equipo
def vista_stats_equipos(df: pd.DataFrame):
    t = largo_ext(df)
    c1, c2 = st.columns(2)
    ts = c1.selectbox("Temporada", ["Todas"] + sorted(t.Temporada.unique(), reverse=True), key="fx_st_temp")
    cond = c2.selectbox("Condición", ["Todos", "Local", "Visita"], key="fx_st_cond")
    x = t
    if ts != "Todas":
        x = x[x.Temporada == ts]
    if cond != "Todos":
        x = x[x.Condicion == cond]
    if x.empty:
        st.info("Sin partidos con ese filtro.")
        return
    g = x.groupby("Equipo").agg(PJ=("GF", "size"), GF=("GF", "mean"), GC=("GC", "mean"), Tiros=("Tiros", "mean"),
                                TirosRival=("TirosRival", "mean"), TP=("TP", "mean"), TPRival=("TPRival", "mean"),
                                Corners=("Corners", "mean"), CornersRival=("CornersRival", "mean"),
                                Faltas=("Faltas", "mean"), Amarillas=("Amarillas", "mean"), Rojas=("Rojas", "mean"),
                                Over25=("Over25", "mean"), BTTS=("BTTS", "mean"), Cero=("ArcoEnCero", "mean"))
    conv = x.groupby("Equipo")["GF"].sum() / x.groupby("Equipo")["Tiros"].sum().replace(0, np.nan)
    g["Conversión %"] = conv * 100
    for c in ("Over25", "BTTS", "Cero"):
        g[c] = g[c] * 100
    g = g.rename(columns={"GF": "Goles a favor", "GC": "Goles en contra", "TirosRival": "Tiros rival", "TP": "A puerta",
                          "TPRival": "A puerta rival", "Corners": "Córners", "CornersRival": "Córners rival",
                          "Over25": "Over 2.5 %", "BTTS": "Ambos anotan %", "Cero": "Arco en 0 %"}).dropna(axis=1, how="all")
    g = g.round(2).reset_index()
    metricas = [c for c in g.columns if c not in ("Equipo", "PJ")]
    orden = st.selectbox("Ordenar por", metricas, index=0, key="fx_st_ord")
    g = g.sort_values(orden, ascending=False).reset_index(drop=True)
    st.dataframe(g, hide_index=True, use_container_width=True)
    top = g.head(20)
    st.altair_chart(alt.Chart(top).mark_bar(color=COLOR_A).encode(
        x=alt.X(f"{orden}:Q"), y=alt.Y("Equipo:N", sort="-x", title=None),
        tooltip=["Equipo", "PJ", alt.Tooltip(f"{orden}:Q", format=".2f")]).properties(height=max(120, 22 * len(top))),
        use_container_width=True)
    if "Tiros" not in g.columns:
        st.caption("Esta liga no trae tiros, córners ni tarjetas en sus archivos.")


# ================================================================ árbitros
def vista_arbitros(df: pd.DataFrame):
    if "Referee" not in df.columns or df["Referee"].dropna().empty:
        st.info("Estos datos no traen el nombre del árbitro (solo las ligas europeas de football-data).")
        return
    d = _asegurar(df, ["HY", "AY", "HR", "AR", "HF", "AF", "FTHG", "FTAG"]).dropna(subset=["Referee"])
    d["Amarillas"], d["Rojas"], d["Faltas"] = d.HY + d.AY, d.HR + d.AR, d.HF + d.AF
    d["Goles"], d["Local"] = d.FTHG + d.FTAG, (d.FTHG > d.FTAG).astype(float)
    d["Over25"] = (d.Goles > 2.5).astype(float)
    g = d.groupby("Referee").agg(PJ=("Goles", "size"), Amarillas=("Amarillas", "mean"), Rojas=("Rojas", "mean"),
                                 Faltas=("Faltas", "mean"), Goles=("Goles", "mean"), Local=("Local", "mean"),
                                 Over25=("Over25", "mean"))
    g["Local"], g["Over25"] = g["Local"] * 100, g["Over25"] * 100
    g = g.rename(columns={"Local": "Gana local %", "Over25": "Over 2.5 %", "Goles": "Goles / partido",
                          "Amarillas": "Amarillas / partido", "Rojas": "Rojas / partido", "Faltas": "Faltas / partido"})
    minimo = st.slider("Mínimo de partidos del árbitro", 1, int(max(g.PJ.max(), 2)), int(min(15, max(g.PJ.max(), 1))), key="fx_arb_min")
    orden = st.selectbox("Ordenar por", [c for c in g.columns if c != "PJ"], index=0, key="fx_arb_ord")
    v = g[g.PJ >= minimo].sort_values(orden, ascending=False).round(2).reset_index().rename(columns={"Referee": "Árbitro"})
    prom = g.mul(g.PJ, axis=0).sum() / g.PJ.sum()
    st.caption("Promedio de la liga en los datos cargados: " + " · ".join(
        f"{c} {prom[c]:.2f}" for c in g.columns if c != "PJ"))
    st.dataframe(v, hide_index=True, use_container_width=True)


# ================================================================ próximos partidos con cuotas
@st.cache_data(ttl=1800, show_spinner=False)
def descargar_fixtures() -> pd.DataFrame:
    status, contenido = get_bytes(FIXTURES_URL)
    if status == 404:
        return pd.DataFrame()
    f = pd.read_csv(io.StringIO(contenido.decode("latin-1")))
    f["Date"] = pd.to_datetime(f["Date"], dayfirst=True, errors="coerce")
    return f.dropna(subset=["HomeTeam", "AwayTeam"]).reset_index(drop=True)


def vista_proximos(df: pd.DataFrame, codigo_liga: str | None):
    import football  # import tardío: football importa este módulo desde render()

    if not codigo_liga:
        st.info("Los próximos partidos con cuotas solo están disponibles para las ligas europeas.")
        return
    try:
        fx = descargar_fixtures()
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo descargar la lista de próximos partidos: {e}")
        return
    if fx.empty:
        st.info("football-data no publica próximos partidos ahora mismo.")
        return
    if "Div" in fx.columns:
        fx = fx[fx["Div"] == codigo_liga]
    hoy = pd.Timestamp.today().normalize()
    fx = fx[fx["Date"] >= hoy - pd.Timedelta(days=1)].sort_values("Date").head(40)
    if fx.empty:
        st.info("No hay próximos partidos publicados para esta liga (el archivo solo cubre las siguientes jornadas).")
        return
    casas = casas_disponibles(fx, 0.3)
    casa = None
    if casas:
        casa = st.selectbox("Fuente de cuotas", list(casas), key="fx_prox_casa")
    st.caption("Modelo: Poisson con ataque/defensa local y visita (el mismo de «Predicción»). Es un modelo simple: "
               "el mercado suele ser más preciso. Una diferencia grande muestra dónde discrepan, no una apuesta segura.")
    filas = []
    for r in fx.to_dict("records"):
        fila = {"Fecha": r["Date"].strftime("%d/%m") if pd.notna(r["Date"]) else "", "Local": r["HomeTeam"], "Visita": r["AwayTeam"]}
        try:
            _, _, m = football.predecir(df, r["HomeTeam"], r["AwayTeam"])
            n = m.shape[0]
            mod = np.array([np.tril(m, -1).sum(), np.trace(m), np.triu(m, 1).sum()])
            fila.update({"Modelo L %": mod[0] * 100, "Modelo E %": mod[1] * 100, "Modelo V %": mod[2] * 100})
            mod_over = sum(m[i, j] for i in range(n) for j in range(n) if i + j > 2.5)
        except KeyError:
            mod, mod_over = None, None
            fila["Modelo L %"] = fila["Modelo E %"] = fila["Modelo V %"] = np.nan
        if casa:
            h, dd, a, o, u = casas[casa]
            try:
                oh, od, oa = float(r[h]), float(r[dd]), float(r[a])
                inv = np.array([1 / oh, 1 / od, 1 / oa])
                mk = inv / inv.sum()
                fila.update({"Cuota L": oh, "Cuota E": od, "Cuota V": oa, "Mercado L %": mk[0] * 100,
                             "Mercado E %": mk[1] * 100, "Mercado V %": mk[2] * 100})
                if mod is not None:
                    dif = (mod - mk) * 100
                    i = int(np.argmax(np.abs(dif)))
                    fila["Mayor diferencia"] = f"{['Local', 'Empate', 'Visita'][i]} {dif[i]:+.1f} pp"
                if mod_over is not None and o in r and u in r:
                    io_, iu = 1 / float(r[o]), 1 / float(r[u])
                    fila["Over 2.5 mercado %"] = io_ / (io_ + iu) * 100
                    fila["Over 2.5 modelo %"] = mod_over * 100
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                pass
        filas.append(fila)
    st.dataframe(pd.DataFrame(filas).round(1), hide_index=True, use_container_width=True)


# ================================================================ ligas de América
@st.cache_data(ttl=3600, show_spinner=False)
def descargar_america(codigo: str) -> pd.DataFrame:
    """Archivos /new/ de football-data: todas las temporadas en un CSV, sin tiros ni córners."""
    import football

    status, contenido = get_bytes(URL_NEW.format(code=codigo))
    if status == 404:
        return pd.DataFrame()
    raw = pd.read_csv(io.StringIO(contenido.decode("latin-1")))
    raw = raw.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG",
                              "PH": "PSH", "PD": "PSD", "PA": "PSA"})
    if "HomeTeam" not in raw.columns or "FTHG" not in raw.columns:
        return pd.DataFrame()
    raw["Temporada"] = raw["Season"].astype(str) if "Season" in raw.columns else "Todas"
    return football.limpiar(raw)
