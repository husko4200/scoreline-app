"""Gráficos reutilizables para el análisis de jugadores (Altair, que ya viene con Streamlit).

Tres piezas, pensadas para llamarse desde cualquier módulo con un DataFrame:

  1. grafico_partidos(...)   Barras por partido + línea horizontal + medias móviles (5 y 10).
  2. barras_comparativas(...) Un mini gráfico por estadística para comparar jugadores (Jugadores / Cara a cara).
  3. mostrar_*()             Versiones que dibujan en Streamlit con controles y un resumen («superó la línea X de N»).

Las funciones `preparar_*` son puras (solo pandas) para poder probarlas sin Streamlit.
"""
from __future__ import annotations

import pandas as pd

# Colores a juego con la paleta de la app (índigo / oro) más verde y rojo para superó / no superó.
C_SUPERO = "#16a34a"
C_NO_SUPERO = "#dc2626"
C_LINEA = "#c9a227"
C_MM5 = "#4f46e5"
C_MM10 = "#a855f7"
PALETA_JUGADORES = ["#4f46e5", "#c9a227", "#16a34a", "#dc2626"]


# ---------------------------------------------------------------------------
# Preparación de datos (sin Streamlit ni Altair)
# ---------------------------------------------------------------------------
def preparar_partidos(df, columna, linea=None, columna_fecha="Fecha", columna_rival="Rival",
                      mas_reciente_primero=True):
    """Devuelve un DataFrame en orden cronológico (antiguo → reciente) con:
    n (nº de partido), etiqueta, valor, mm5, mm10, supero (bool si hay línea).

    `mas_reciente_primero=True` indica que `df` viene como se muestra en la app (último partido arriba).
    Si `columna_fecha` se puede leer como fecha, se ordena por ella y se ignora ese parámetro.
    """
    if df is None or columna not in getattr(df, "columns", []):
        return pd.DataFrame()
    d = df.copy()
    d["valor"] = pd.to_numeric(d[columna], errors="coerce")
    d = d.dropna(subset=["valor"])
    if d.empty:
        return pd.DataFrame()

    ordenado = False
    if columna_fecha in d.columns:
        fechas = pd.to_datetime(d[columna_fecha], errors="coerce", format="ISO8601")  # la app guarda AAAA-MM-DD
        if not fechas.notna().all():
            fechas = pd.to_datetime(d[columna_fecha], errors="coerce", dayfirst=True)
        if fechas.notna().all():
            d = d.assign(_f=fechas).sort_values("_f", kind="stable").drop(columns="_f")
            ordenado = True
    if not ordenado and mas_reciente_primero:
        d = d.iloc[::-1]
    d = d.reset_index(drop=True)

    d["n"] = range(1, len(d) + 1)
    fecha = d[columna_fecha].astype(str) if columna_fecha in d.columns else d["n"].astype(str)
    rival = d[columna_rival].astype(str) if columna_rival in d.columns else ""
    d["etiqueta"] = (fecha + " · " + rival).str.strip(" ·") if columna_rival in d.columns else fecha
    # min_periods=1: las primeras medias se calculan con los partidos disponibles, así la línea no empieza tarde.
    d["mm5"] = d["valor"].rolling(5, min_periods=1).mean().round(2)
    d["mm10"] = d["valor"].rolling(10, min_periods=1).mean().round(2)
    if linea is not None:
        d["supero"] = d["valor"] > float(linea)
    return d[[c for c in ("n", "etiqueta", "valor", "mm5", "mm10", "supero") if c in d.columns]]


def resumen_linea(d, linea):
    """(veces que superó, total, porcentaje) o None si no hay datos."""
    if d is None or d.empty or linea is None:
        return None
    total = len(d)
    veces = int((d["valor"] > float(linea)).sum())
    return veces, total, veces / total * 100


def preparar_comparacion(medias, estadisticas=None):
    """`medias` = {jugador: {estadística: valor}} → DataFrame largo (Jugador, Estadística, Valor)."""
    filas = []
    for jugador, stats in medias.items():
        for est, val in stats.items():
            if estadisticas and est not in estadisticas:
                continue
            v = pd.to_numeric(val, errors="coerce")
            if pd.notna(v):
                filas.append({"Jugador": jugador, "Estadística": est, "Valor": float(v)})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Gráficos (Altair)
# ---------------------------------------------------------------------------
def grafico_partidos(d, linea=None, titulo="", etiqueta_y="Valor", ver_mm5=True, ver_mm10=True, alto=340,
                     solo_tendencia=False):
    """Barras por partido (verde = superó la línea, rojo = no) + raya horizontal + medias móviles.

    solo_tendencia=True cambia las barras por una línea fina con puntos (para no repetir un gráfico de barras
    que ya se muestra aparte)."""
    import altair as alt

    if d is None or d.empty:
        return None
    x = alt.X("n:O", title="Partido (de más antiguo a más reciente)", axis=alt.Axis(labelAngle=0, labelOverlap=True))
    tip = [alt.Tooltip("etiqueta:N", title="Partido"), alt.Tooltip("valor:Q", title=etiqueta_y)]

    if linea is not None and "supero" in d.columns:
        color = alt.Color("supero:N", legend=None,
                          scale=alt.Scale(domain=[True, False], range=[C_SUPERO, C_NO_SUPERO]))
    else:
        color = alt.value(C_MM5)
    if solo_tendencia:
        barras = alt.Chart(d).mark_line(point=alt.OverlayMarkDef(size=45), color="#8a8f98", strokeWidth=1.5,
                                        opacity=.8).encode(x=x, y=alt.Y("valor:Q", title=etiqueta_y), tooltip=tip)
    else:
        barras = alt.Chart(d).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, opacity=.85).encode(
            x=x, y=alt.Y("valor:Q", title=etiqueta_y), color=color, tooltip=tip)

    capas = [barras]
    if linea is not None:
        regla = alt.Chart(pd.DataFrame({"linea": [float(linea)]})).mark_rule(
            color=C_LINEA, strokeWidth=2.5, strokeDash=[6, 4]).encode(
            y="linea:Q", tooltip=[alt.Tooltip("linea:Q", title="Línea")])
        texto = alt.Chart(pd.DataFrame({"linea": [float(linea)], "t": [f"Línea {linea:g}"]})).mark_text(
            align="left", dx=4, dy=-6, color=C_LINEA, fontWeight="bold").encode(
            y="linea:Q", text="t:N", x=alt.value(2))
        capas += [regla, texto]

    medias = []
    if ver_mm5:
        medias.append(("mm5", "Media móvil 5"))
    if ver_mm10:
        medias.append(("mm10", "Media móvil 10"))
    if medias:
        largo = d.melt(id_vars=["n", "etiqueta"], value_vars=[m[0] for m in medias],
                       var_name="serie", value_name="media")
        largo["serie"] = largo["serie"].map(dict(medias))
        lineas = alt.Chart(largo).mark_line(point=alt.OverlayMarkDef(size=30), strokeWidth=2.5).encode(
            x=x, y=alt.Y("media:Q"),
            color=alt.Color("serie:N", title=None, scale=alt.Scale(
                domain=[m[1] for m in medias],
                range=[C_MM5 if m[0] == "mm5" else C_MM10 for m in medias]),
                legend=alt.Legend(orient="top")),
            tooltip=[alt.Tooltip("etiqueta:N", title="Partido"), alt.Tooltip("serie:N", title="Serie"),
                     alt.Tooltip("media:Q", title="Media", format=".1f")])
        capas.append(lineas)

    return alt.layer(*capas).properties(title=titulo, height=alto)


def barras_comparativas(largo, titulo="", alto=220, normalizar=False, colores=None):
    """Un mini gráfico de barras por estadística (cada uno con su propia escala: PTS ≠ STL).

    Si `normalizar=True`, cada estadística se expresa como % del máximo entre los jugadores
    (útil para ver quién domina en qué, sin importar la escala).
    """
    import altair as alt

    if largo is None or largo.empty:
        return None
    d = largo.copy()
    if normalizar:
        maximo = d.groupby("Estadística")["Valor"].transform("max").replace(0, pd.NA)
        d["Relativo"] = (d["Valor"] / maximo * 100).fillna(0).round(0)
    jugadores = list(dict.fromkeys(d["Jugador"]))
    orden = list(dict.fromkeys(d["Estadística"]))
    y = alt.Y("Relativo:Q", title="% del mejor", scale=alt.Scale(domain=[0, 100])) if normalizar \
        else alt.Y("Valor:Q", title=None)
    return alt.Chart(d).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("Jugador:N", title=None, axis=alt.Axis(labels=False, ticks=False)),
        y=y,
        color=alt.Color("Jugador:N", scale=alt.Scale(domain=jugadores,
                        range=(colores or PALETA_JUGADORES)[:max(len(jugadores), 1)]), legend=alt.Legend(orient="top", title=None)),
        column=alt.Column("Estadística:N", sort=orden, title=None,
                          header=alt.Header(labelFontWeight="bold", labelOrient="top")),
        tooltip=["Jugador:N", "Estadística:N", alt.Tooltip("Valor:Q", format=".1f")],
    ).properties(width=70, height=alto, title=titulo).configure_view(stroke=None)


# ---------------------------------------------------------------------------
# Dibujo en Streamlit
# ---------------------------------------------------------------------------
def _mostrar(chart):
    import streamlit as st

    try:
        st.altair_chart(chart, width="stretch")  # Streamlit reciente
    except TypeError:
        st.altair_chart(chart, use_container_width=True)  # versiones anteriores


mostrar_grafico = _mostrar  # para otros módulos que ya tienen su propio gráfico


def mostrar_partidos(df, columna, linea=None, jugador="", etiqueta="", clave="graf", **kw):
    """Barras por partido + línea + medias móviles, con selector de medias y resumen de la línea.

    df: tabla de partidos tal como la muestra la app. columna: estadística a graficar (p. ej. "PTS").
    linea: valor de la línea (o None). clave: texto único por gráfico (para que los widgets no choquen).
    kw se pasa a preparar_partidos (columna_fecha, columna_rival, mas_reciente_primero).
    """
    import streamlit as st

    d = preparar_partidos(df, columna, linea, **kw)
    if d.empty:
        st.info("No hay partidos con datos para graficar.")
        return
    ultimos = st.slider("Partidos a mostrar", 5, max(len(d), 6), min(len(d), 20), key=f"{clave}_n") if len(d) > 5 else len(d)
    c1, c2 = st.columns(2)
    mm5 = c1.checkbox("Media móvil 5", True, key=f"{clave}_m5")
    mm10 = c2.checkbox("Media móvil 10", True, key=f"{clave}_m10")
    # Las medias se calculan con TODO el historial y luego se recorta, para que no cambien al ajustar el control.
    d = d.tail(ultimos)

    r = resumen_linea(d, linea)
    if r:
        st.metric(f"Superó la línea de {linea:g}", f"{r[0]} de {r[1]}", f"{r[2]:.0f}%", delta_color="off")
    chart = grafico_partidos(d, linea, titulo=f"{jugador} · {etiqueta or columna}".strip(" ·"),
                             etiqueta_y=etiqueta or columna, ver_mm5=mm5, ver_mm10=mm10)
    _mostrar(chart)
    if len(d):
        ult = d.iloc[-1]
        tendencia = ult["mm5"] - ult["mm10"]
        if abs(tendencia) >= 0.05:
            st.caption(("📈 En alza" if tendencia > 0 else "📉 A la baja")
                       + f": media de los últimos 5 = {ult['mm5']:.1f} vs. últimos 10 = {ult['mm10']:.1f}.")


def mostrar_comparacion(medias, estadisticas=None, titulo="", clave="comp", colores=None):
    """Barras comparativas por estadística. medias = {jugador: {estadística: valor}}."""
    import streamlit as st

    largo = preparar_comparacion(medias, estadisticas)
    if largo.empty:
        st.info("No hay datos para comparar.")
        return
    rel = st.toggle("Ver en % del mejor (compara la forma, no la escala)", False, key=f"{clave}_rel")
    _mostrar(barras_comparativas(largo, titulo=titulo, normalizar=rel, colores=colores))


def mostrar_jugador_vs_linea(juegos, clave, etiqueta, clave_ui, nombre=""):
    """Para una lista de partidos como diccionarios (los de nba_h2h_jugadores: 'fecha', 'rival', PTS, REB...),
    pide la línea y dibuja barras + medias móviles. El partido más reciente va primero en `juegos`.
    La línea propuesta es el promedio de los últimos 10 redondeado a .5; con 0 se oculta."""
    import streamlit as st

    filas = [{"Fecha": g.get("fecha"), "Rival": g.get("rival", ""), clave: g.get(clave)} for g in juegos]
    df = pd.DataFrame(filas)
    if df.empty or clave not in df.columns or pd.to_numeric(df[clave], errors="coerce").dropna().empty:
        st.info(f"Sin datos de {etiqueta.lower()} para {nombre or 'este jugador'}.")
        return
    recientes = pd.to_numeric(df[clave], errors="coerce").dropna().head(10)
    sugerida = round(float(recientes.mean()) * 2) / 2
    linea = st.number_input(f"Línea de {etiqueta.lower()} · {nombre}".strip(" ·"), min_value=0.0, step=0.5,
                            value=float(sugerida), key=f"{clave_ui}_linea",
                            help="Pon 0 para ocultar la línea. Propuesta: promedio de los últimos 10 partidos.")
    mostrar_partidos(df, clave, linea=linea or None, jugador=nombre, etiqueta=etiqueta, clave=clave_ui)
