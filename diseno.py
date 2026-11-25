"""Sistema de diseño de la app: tablas con diseño propio, paleta, tipografía, componentes y animaciones en CSS.

Lo usa app.py con:
    diseno.instalar_estilo_tablas()      # una vez, al arrancar: todas las st.dataframe pasan por el diseño propio
    diseno.aplicar_estilos(indice)       # en cada ejecución: inyecta el CSS (indice = posición de la sección del menú)

No ejecuta nada de Streamlit al importarse, así que se puede importar antes o después de st.set_page_config.
"""
import numbers
import re
from datetime import date
from html import escape as _escapar

import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------------
# TABLAS CON DISEÑO PROPIO (ya no parecen una hoja de Excel)
# ---------------------------------------------------------------------------
# Todas las tablas de la app (también las de los módulos de análisis) pasan por aquí. En vez de la cuadrícula de
# st.dataframe se dibuja una tarjeta limpia: sin líneas verticales, encabezado de vidrio, resultados como
# etiquetas de color, barras de progreso y enlaces. Si una tabla es muy grande o necesita selección de filas,
# se usa el st.dataframe de siempre (con el estilo anterior) para no romper nada.
MAX_FILAS_TARJETA = 500
COLUMNAS_ETIQUETA = ("Resultado", "Estado")  # columnas que se dibujan como etiqueta de color
COLOR_GANADO = "color: #15803d; font-weight: 600; background-color: rgba(22, 163, 74, .12)"
COLOR_PERDIDO = "color: #b91c1c; font-weight: 600; background-color: rgba(220, 38, 38, .10)"
FILA_ALTERNA = "background-color: rgba(127, 127, 127, .06)"


def _tema_ya_es_indigo():
    try:
        return str(st.get_option("theme.primaryColor") or "").lower() == "#4f46e5"
    except Exception:  # noqa: BLE001
        return False


def _estilos_de_tabla(df):
    """DataFrame de estilos CSS (mismo tamaño que la tabla): filas alternadas y columna Resultado coloreada."""
    estilos = pd.DataFrame("", index=df.index, columns=df.columns)
    estilos.iloc[1::2, :] = FILA_ALTERNA
    if "Resultado" in df.columns:
        texto = df["Resultado"].astype(str)
        ganado = texto.str.contains(r"✅|(?:^|\s)G\s", regex=True)
        perdido = texto.str.contains(r"❌|(?:^|\s)P\s", regex=True)
        estilos.loc[ganado.values, "Resultado"] = COLOR_GANADO
        estilos.loc[perdido.values, "Resultado"] = COLOR_PERDIDO
    return estilos


def _config_de_columnas(df, existente):
    """Anchos y formato para las columnas que el módulo no configuró (nunca pisa lo que ya definió)."""
    cfg = dict(existente or {})
    # Compacta: las columnas que el módulo configuró con ancho medium/large (p. ej. las barras de PTS/REB/AST)
    # pasan a "small" para que la tabla entera quepa sin scroll horizontal.
    for col, c in list(cfg.items()):
        if isinstance(c, dict) and c.get("width") in (None, "medium", "large") and col not in ("Resultado", "URL"):
            cfg[col] = {**c, "width": "small"}
    for col in df.columns:
        if col in cfg:
            continue
        if col in ("Fecha", "Rival", "Fase", "Resultado"):
            cfg[col] = st.column_config.TextColumn(col, width="small" if col != "Resultado" else "medium")
        elif pd.api.types.is_numeric_dtype(df[col]):
            valores = df[col].dropna()
            entero = bool((valores % 1 == 0).all()) if len(valores) else True
            cfg[col] = st.column_config.NumberColumn(col, width="small", format="%d" if entero else "%.1f")
    return cfg


def _decorar_tabla(data, kwargs):
    """Devuelve (datos, kwargs) listos para st.dataframe; si algo falla, devuelve lo original sin cambios."""
    try:
        if isinstance(data, pd.DataFrame) and 0 < len(data) <= 2000 and data.index.is_unique and data.columns.is_unique:
            nuevo = dict(kwargs)
            nuevo["column_config"] = _config_de_columnas(data, kwargs.get("column_config"))
            return data.style.apply(_estilos_de_tabla, axis=None), nuevo
    except Exception:  # noqa: BLE001
        pass
    return data, kwargs


def _config_de(cfgs, col):
    """Configuración de una columna como diccionario (o None si no hay)."""
    c = (cfgs or {}).get(col)
    return c if isinstance(c, dict) else None


def _formato_numero(valor, formato, por_defecto):
    """Aplica un formato tipo '%.1f' (el mismo de st.column_config); si no se puede, usa el formato por defecto."""
    for f in (formato, por_defecto):
        if not isinstance(f, str) or "%" not in f:
            continue
        try:
            return f % (int(round(valor)) if re.search(r"%[-+ #0-9.]*d", f) else valor)
        except (TypeError, ValueError, OverflowError):
            continue
    return str(valor)


def _formato_defecto(serie):
    """Enteros sin decimales; proporciones (menores que 1) con 3 decimales; el resto con 1."""
    v = serie.dropna()
    if v.empty or bool((v % 1 == 0).all()):
        return "%d"
    return "%.3f" if float(v.abs().max()) < 1 else "%.1f"


def _celda_html(valor, col, cfg, defecto):
    """HTML de una celda según el tipo de dato (número, barra, enlace, imagen, etiqueta de resultado...)."""
    tc = cfg.get("type_config") if cfg and isinstance(cfg.get("type_config"), dict) else {}
    tipo = tc.get("type")
    if hasattr(valor, "tolist") and getattr(valor, "ndim", 0) > 0:
        valor = valor.tolist()
    if isinstance(valor, (list, tuple)):
        nums = [x for x in valor if isinstance(x, numbers.Real) and not isinstance(x, bool)]
        if valor and len(nums) == len(valor):  # mini gráfico de barras
            tope = max(abs(x) for x in nums) or 1
            barras = "".join(f'<i style="height:{max(12, abs(x) / tope * 100):.0f}%"></i>' for x in nums[:30])
            return f'<span class="mini">{barras}</span>'
        return _escapar(", ".join(map(str, valor)))
    try:
        vacio = bool(pd.isna(valor))
    except (TypeError, ValueError):
        vacio = False
    if vacio:
        return '<span class="vacio">—</span>'
    if isinstance(valor, bool) or tipo == "checkbox":
        return '<span class="si">✓</span>' if valor else '<span class="vacio">—</span>'
    if tipo == "progress" and isinstance(valor, numbers.Real):
        lo, hi = tc.get("min_value") or 0, tc.get("max_value") or 100
        frac = 0 if hi == lo else min(1, max(0, (valor - lo) / (hi - lo)))
        texto = _formato_numero(valor, tc.get("format"), defecto)
        return (f'<div class="barra"><div class="barra-pista"><i style="width:{frac * 100:.0f}%"></i></div>'
                f'<b>{_escapar(texto)}</b></div>')
    if isinstance(valor, numbers.Real):
        return _escapar(_formato_numero(valor, tc.get("format"), defecto))
    if isinstance(valor, date):
        con_hora = bool(getattr(valor, "hour", 0) or getattr(valor, "minute", 0))
        return valor.strftime("%d/%m/%Y %H:%M" if con_hora else "%d/%m/%Y")
    texto = str(valor)
    if tipo == "image" and texto.startswith(("http://", "https://", "data:image")):
        return f'<img src="{_escapar(texto)}" alt="" loading="lazy">'
    if texto.startswith(("http://", "https://")):
        etiqueta = tc.get("display_text")
        if etiqueta and "(" in etiqueta:  # display_text puede ser una expresión regular
            m = re.search(etiqueta, texto)
            etiqueta = m.group(1) if m else None
        return (f'<a href="{_escapar(texto)}" target="_blank" rel="noopener noreferrer">'
                f'{_escapar(etiqueta or "abrir")} ↗</a>')
    if col in COLUMNAS_ETIQUETA:
        if re.search(r"✅|(?:^|\s)G\s", texto):
            clase = "ok"
        elif re.search(r"❌|(?:^|\s)P\s", texto):
            clase = "mal"
        elif "🟡" in texto:
            clase = "aviso"
        else:
            clase = ""
        return f'<span class="pill {clase}">{_escapar(texto)}</span>'
    return _escapar(texto)


def _tabla_html(df, kwargs):
    """Convierte un DataFrame en una tabla HTML con el diseño de la app, respetando column_config / column_order / hide_index."""
    if df.empty:
        return '<div class="tabla-vacia">Sin datos para mostrar.</div>'
    cfgs = kwargs.get("column_config") or {}
    orden = kwargs.get("column_order")
    columnas = [c for c in (orden or df.columns) if c in df.columns and cfgs.get(c, 0) is not None]
    oculto = kwargs.get("hide_index")
    con_indice = oculto is False or (oculto is None and not isinstance(df.index, pd.RangeIndex))

    meta = []  # (columna, configuración, es_numérica, formato_por_defecto)
    cabecera = [f'<th class="idx">{_escapar(str(df.index.name or ""))}</th>'] if con_indice else []
    for c in columnas:
        cfg = _config_de(cfgs, c)
        tipo = ((cfg or {}).get("type_config") or {}).get("type")
        serie = df[c]
        numerica = (pd.api.types.is_numeric_dtype(serie) and not pd.api.types.is_bool_dtype(serie)
                    and tipo not in ("progress", "checkbox"))
        defecto = _formato_defecto(serie) if pd.api.types.is_numeric_dtype(serie) and not pd.api.types.is_bool_dtype(serie) else None
        meta.append((c, cfg, numerica, defecto))
        etiqueta = (cfg or {}).get("label") or str(c)
        ayuda = (cfg or {}).get("help")
        titulo = f' title="{_escapar(str(ayuda))}"' if ayuda else ""
        cabecera.append(f'<th class="{"num" if numerica else ""}"{titulo}>{_escapar(str(etiqueta))}</th>')

    filas = []
    for indice, fila in zip(df.index, df[columnas].itertuples(index=False, name=None)):
        celdas = [f'<td class="idx">{_escapar(str(indice))}</td>'] if con_indice else []
        for j, (valor, (c, cfg, numerica, defecto)) in enumerate(zip(fila, meta)):
            clase = "num" if numerica else ("primera" if j == 0 and not con_indice else "")
            celdas.append(f'<td class="{clase}">{_celda_html(valor, c, cfg, defecto)}</td>')
        filas.append(f'<tr>{"".join(celdas)}</tr>')

    alto = kwargs.get("height")
    alto = alto if isinstance(alto, int) and alto > 0 else 560
    pie = f'{len(df)} {"fila" if len(df) == 1 else "filas"}'
    tabla = (f'<div class="tabla-wrap" style="max-height:{alto}px"><table class="tabla"><thead><tr>{"".join(cabecera)}</tr></thead>'
             f'<tbody>{"".join(filas)}</tbody></table><div class="tabla-pie">{pie}</div></div>')
    return tabla.replace("$", "&#36;")  # evita que el markdown lo confunda con una fórmula


def _puede_dibujar(data, kwargs):
    """Solo se dibuja con el diseño propio si es un DataFrame normal, no muy grande y sin selección de filas."""
    return (isinstance(data, pd.DataFrame) and len(data) <= MAX_FILAS_TARJETA and data.columns.is_unique
            and kwargs.get("on_select") in (None, "ignore"))


def _instalar_estilo_tablas():
    """Envuelve st.dataframe una sola vez (Streamlit vuelve a ejecutar el script en cada interacción)."""
    from streamlit.delta_generator import DeltaGenerator

    original = getattr(DeltaGenerator.dataframe, "_original", DeltaGenerator.dataframe)
    if getattr(DeltaGenerator.dataframe, "_diseno", None) == 2:
        return

    def dataframe(self, data=None, *args, **kwargs):
        try:
            if _puede_dibujar(data, kwargs):
                return self.markdown(_tabla_html(data, kwargs), unsafe_allow_html=True)
        except Exception:  # noqa: BLE001
            pass  # si el diseño propio falla, se usa la tabla de Streamlit
        data, kwargs = _decorar_tabla(data, kwargs)
        return original(self, data, *args, **kwargs)

    dataframe._diseno = 2
    dataframe._original = original
    DeltaGenerator.dataframe = dataframe
    st.dataframe = st._main.dataframe  # el st.dataframe del módulo apunta al método anterior; se vuelve a enlazar


def instalar_estilo_tablas():
    """Activa las tablas con diseño propio. Si algo falla, la app sigue con las tablas normales de Streamlit."""
    try:
        _instalar_estilo_tablas()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# 2. SISTEMA DE DISEÑO
# ---------------------------------------------------------------------------
# Paleta: índigo (acción principal), violeta (degradados), dorado (detalle premium), tinta (fondos oscuros).
# Los fondos de tarjetas usan gris translúcido: se adaptan solos al tema claro u oscuro.
ESTILOS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&family=Roboto+Condensed:wght@500;600;700&display=swap');

:root {
  --indigo: var(--pl-acc, #4f46e5); --violeta: var(--pl-tenis, #7c3aed); --oro: #c9a227;
  --tinta: var(--pl-ink, #0f172a); --vivo: var(--pl-vivo, #ef4444);
  --borde: var(--pl-borde, rgba(127, 127, 127, .20)); --card: var(--pl-card, rgba(127, 127, 127, .07));
  --sombra: var(--pl-sombra, 0 1px 2px rgba(15, 23, 42, .06));
  --sombra-alta: 0 2px 4px rgba(15, 23, 42, .08), 0 18px 40px rgba(79, 70, 229, .22);
}

/* ---------- Animaciones ---------- */
@keyframes flujo    { 0% { background-position: 0% 50%; } 100% { background-position: 300% 50%; } }
@keyframes subir    { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }
@keyframes aparece  { from { opacity: 0; } to { opacity: 1; } }
@keyframes pulso    { 0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, .6); } 70% { box-shadow: 0 0 0 9px rgba(239, 68, 68, 0); } 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); } }
@keyframes flotar   { 0%, 100% { transform: translate(0, 0); } 50% { transform: translate(22px, -16px); } }

/* ---------- Base: fondo, ancho y tipografía ---------- */
.stApp {
  background-image:
    radial-gradient(1100px 520px at 6% -8%, rgba(79, 70, 229, .11), transparent 60%),
    radial-gradient(900px 520px at 100% 0%, rgba(201, 162, 39, .09), transparent 55%);
}
[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 1320px; padding-top: 2.4rem; padding-bottom: 4rem; }
.stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp textarea, .stButton button,
[data-testid="stMetricLabel"], [data-testid="stMetricValue"] {
  font-family: var(--pl-font, 'Roboto', system-ui, -apple-system, sans-serif);
}
h1, h2, h3, h4 { font-family: var(--pl-font-cond, 'Roboto Condensed', 'Roboto', sans-serif) !important; letter-spacing: -.015em; }
::selection { background: rgba(79, 70, 229, .25); }
:focus-visible { outline: 2px solid rgba(79, 70, 229, .65) !important; outline-offset: 2px; }
/* Al usar el teclado (p. ej. la tecla R de Streamlit) el contenedor principal queda «enfocado» y dibujaba un marco alrededor
   de toda la pantalla. Los contenedores de la página no necesitan contorno: solo los controles (botones, campos, enlaces). */
html:focus-visible, body:focus-visible, .stApp:focus-visible, [data-testid="stApp"]:focus-visible,
[data-testid="stAppViewContainer"]:focus-visible, [data-testid="stMain"]:focus-visible, [data-testid="stMainBlockContainer"]:focus-visible,
[data-testid="stVerticalBlock"]:focus-visible, section.main:focus-visible, .main:focus-visible, .block-container:focus-visible,
[tabindex="-1"]:focus-visible { outline: none !important; }
footer { visibility: hidden; }
hr { border-color: var(--borde); }

/* Línea de color en el borde superior */
.stApp::before {
  content: ""; position: fixed; top: 0; left: 0; right: 0; height: 3px; z-index: 999991;
  background: linear-gradient(90deg, var(--indigo), var(--violeta), var(--oro), var(--indigo));
  background-size: 300% 100%; animation: flujo 8s linear infinite;
}
/* Los bloques que solo inyectan <style> no deben ocupar espacio */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdownContainer"] > style),
.element-container:has(> .stMarkdown style) { display: none; }

/* ---------- Títulos ---------- */
h1 {
  font-size: 2.2rem; font-weight: 800;
  background: linear-gradient(90deg, var(--indigo), var(--violeta), var(--oro), var(--indigo));
  background-size: 300% auto; -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent; animation: flujo 14s linear infinite;
}
h2 { font-size: 1.55rem; font-weight: 700; padding-left: .75rem; border-left: 4px solid; border-image: linear-gradient(180deg, var(--indigo), var(--oro)) 1; }
h3 { font-size: 1.2rem; font-weight: 700; }

/* ---------- Menú lateral ---------- */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(79, 70, 229, .09), rgba(201, 162, 39, .05));
  border-right: 1px solid var(--borde);
}
.marca { display: flex; align-items: center; gap: .75rem; padding: .3rem 0 1rem; animation: aparece .6s ease both; }
.marca-logo {
  width: 44px; height: 44px; border-radius: 13px; display: grid; place-items: center; font-size: 1.35rem; flex: none;
  background: linear-gradient(135deg, var(--indigo), var(--violeta)); box-shadow: 0 8px 20px rgba(79, 70, 229, .45);
}
.marca-nombre { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-weight: 800; font-size: 1.08rem; letter-spacing: -.02em; line-height: 1.1; }
.marca-sub { font-size: .68rem; opacity: .62; letter-spacing: .12em; text-transform: uppercase; margin-top: .25rem; }

/* Selectores (radio): lista vertical en el menú, control segmentado en la página */
div[role="radiogroup"] label {
  border-radius: 11px; padding: .4rem .95rem; margin: 0; border: 1px solid transparent; background: transparent;
  transition: background .18s ease, box-shadow .18s ease, transform .18s ease;
}
div[role="radiogroup"] label:hover { background: rgba(79, 70, 229, .12); }
div[role="radiogroup"] label:has(input:checked) {
  background: linear-gradient(135deg, var(--indigo), var(--violeta)); box-shadow: 0 6px 18px rgba(79, 70, 229, .38);
}
div[role="radiogroup"] label:has(input:checked) * { color: #fff !important; }
/* Oculta el circulito del radio solo si la etiqueta tiene su estructura habitual (marca + texto) */
label[data-baseweb="radio"]:has(> div:nth-of-type(2)) > div:first-of-type { display: none; }
[data-testid="stSidebar"] div[role="radiogroup"] { gap: 4px; }
[data-testid="stSidebar"] div[role="radiogroup"] label { display: flex; width: 100%; padding: .55rem .9rem; }
[data-testid="stSidebar"] div[role="radiogroup"] label:hover { transform: translateX(4px); }
[data-testid="stMain"] div[role="radiogroup"] {
  display: inline-flex; flex-wrap: wrap; gap: 4px; padding: 4px; background: var(--card);
  border: 1px solid var(--borde); border-radius: 14px;
}

/* ---------- Métricas ---------- */
[data-testid="stMetric"] {
  position: relative; overflow: hidden; border: 1px solid var(--borde); border-radius: 16px; padding: 1rem 1.15rem;
  background: linear-gradient(180deg, rgba(127, 127, 127, .09), rgba(127, 127, 127, .03)); box-shadow: var(--sombra);
  transition: transform .22s ease, box-shadow .22s ease;
}
[data-testid="stMetric"]::before {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
  background: linear-gradient(180deg, var(--indigo), var(--oro));
}
[data-testid="stMetric"]:hover { transform: translateY(-4px); box-shadow: var(--sombra-alta); }
[data-testid="stMetricLabel"] { opacity: .78; font-weight: 500; }
[data-testid="stMetricValue"] { font-weight: 700; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }

/* ---------- Botones y entradas ---------- */
.stButton > button, .stDownloadButton > button {
  border-radius: 12px; border: 1px solid var(--borde); font-weight: 600; background: var(--card);
  color: var(--texto, #334155) !important;
  -webkit-text-fill-color: var(--texto, #334155) !important;
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover { transform: translateY(-2px); border-color: var(--indigo); box-shadow: 0 8px 20px rgba(79, 70, 229, .22); }
.stButton > button:active { transform: scale(.98); }
[data-testid="stBaseButton-primary"], button[kind="primary"] {
  background: linear-gradient(135deg, var(--indigo), var(--violeta)) !important; color: #fff !important;
  -webkit-text-fill-color: #fff !important;
  border: none !important;
  box-shadow: 0 6px 16px rgba(79, 70, 229, .35);
}
[data-testid="stBaseButton-primary"]:hover, button[kind="primary"]:hover { box-shadow: 0 10px 26px rgba(124, 58, 237, .5) !important; }
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="base-input"] {
  border-radius: 11px !important; transition: border-color .2s ease, box-shadow .2s ease;
}
[data-baseweb="select"] > div:hover, [data-baseweb="input"]:hover { border-color: var(--indigo) !important; }
/* Menús desplegables (selectores y multiselectores): panel SÓLIDO claro azulado (no blanco, no transparente) con texto oscuro,
   a juego con las tarjetas y tablas claras. Las opciones no llevan fondo propio; el panel, el menú y la lista se pintan opacos. */
body [data-baseweb="popover"] *, body [data-testid="stSelectboxVirtualDropdown"] * { background: transparent !important; background-color: transparent !important; }
body [data-baseweb="popover"], body [data-baseweb="popover"] [data-baseweb="menu"], body [data-baseweb="popover"] ul[role="listbox"],
body [data-testid="stSelectboxVirtualDropdown"] { background: #eaeffb !important; background-color: #eaeffb !important; opacity: 1 !important; }
body [data-baseweb="popover"] {
  border: 1px solid #a5b4fc !important; border-radius: 14px !important; overflow: hidden; z-index: 1000060 !important;
  box-shadow: 0 16px 38px rgba(30, 41, 90, .28) !important;
}
body [data-baseweb="popover"] li, body [data-baseweb="popover"] li *, body [data-baseweb="popover"] [role="option"],
body [data-baseweb="popover"] [role="option"] * { color: #1e293b !important; }
body [data-baseweb="popover"] [role="option"] { border-bottom: 1px solid rgba(99, 102, 241, .14) !important; }
body [data-baseweb="popover"] [role="option"]:hover, body [data-baseweb="popover"] [role="option"][aria-selected="true"],
body [data-baseweb="popover"] li:hover { background: #c7d2fe !important; background-color: #c7d2fe !important; }
[data-testid="stNumberInput"] button:hover, [data-testid="stNumberInput"] button:focus { background: var(--indigo) !important; color: #fff !important; }
/* El rojo por defecto de Streamlit (sliders, interruptores, casillas) se gira al índigo de la marca */
.stProgress > div > div > div > div { background-image: linear-gradient(90deg, var(--indigo), var(--violeta), var(--oro)); }

/* ---------- Pestañas, tablas, avisos, desplegables ---------- */
[data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--borde); }
button[data-baseweb="tab"] { font-weight: 600; border-radius: 10px 10px 0 0; transition: color .2s ease, background .2s ease; }
button[data-baseweb="tab"]:hover { background: var(--card); }
[data-baseweb="tab-highlight"] { background: linear-gradient(90deg, var(--indigo), var(--oro)) !important; height: 3px !important; border-radius: 3px; }
[data-testid="stTabs"] [role="tabpanel"] { animation: aparece .4s ease; }
[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; border: 1px solid var(--borde); box-shadow: var(--sombra); }
[data-testid="stAlert"] { border-radius: 14px; border: 1px solid var(--borde); animation: subir .35s ease; }
[data-testid="stExpander"] { border-radius: 14px; border: 1px solid var(--borde); background: var(--card); transition: box-shadow .2s ease; }
[data-testid="stExpander"]:hover { box-shadow: var(--sombra); }
[data-testid="stCaptionContainer"] { opacity: .8; }
[data-testid="stFileUploader"] section { border-radius: 16px; border: 2px dashed rgba(79, 70, 229, .45); background: var(--card); transition: border-color .2s ease, background .2s ease; }
[data-testid="stFileUploader"] section:hover { border-color: var(--oro); background: rgba(201, 162, 39, .07); }
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-thumb { background: linear-gradient(var(--indigo), var(--violeta)); border-radius: 8px; }
::-webkit-scrollbar-track { background: transparent; }

/* ---------- Componentes propios: pantalla de inicio ---------- */
.hero {
  position: relative; overflow: hidden; border-radius: 22px; padding: 2.4rem 2.2rem 2.1rem; margin-bottom: 1.4rem; color: #fff;
  background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 55%, #312e81 100%);
  border: 1px solid rgba(255, 255, 255, .08); box-shadow: 0 24px 60px rgba(15, 23, 42, .35); animation: subir .6s ease both;
}
.hero::before, .hero::after { content: ""; position: absolute; border-radius: 50%; filter: blur(60px); animation: flotar 12s ease-in-out infinite; }
.hero::before { width: 320px; height: 320px; right: -60px; top: -100px; background: rgba(124, 58, 237, .55); }
.hero::after { width: 260px; height: 260px; right: 180px; bottom: -140px; background: rgba(201, 162, 39, .35); animation-delay: -5s; }
.hero > * { position: relative; z-index: 1; }
.hero-tag { display: inline-block; font-size: .7rem; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; color: var(--oro);
  border: 1px solid rgba(201, 162, 39, .5); border-radius: 999px; padding: .28rem .8rem; margin-bottom: 1rem; }
.hero-titulo { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-weight: 800; font-size: 2.5rem; line-height: 1.1; letter-spacing: -.03em; max-width: 640px; }
.hero-titulo b { background: linear-gradient(90deg, #e9d36b, var(--oro)); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.hero p { margin: .9rem 0 1.2rem; max-width: 560px; font-size: 1.02rem; line-height: 1.6; color: rgba(255, 255, 255, .78); }
.hero-chips span { display: inline-block; margin: 0 .45rem .4rem 0; padding: .35rem .9rem; border-radius: 999px; font-size: .85rem; font-weight: 600;
  background: rgba(255, 255, 255, .09); border: 1px solid rgba(255, 255, 255, .14); backdrop-filter: blur(6px); }
.rejilla { display: flex; flex-wrap: wrap; justify-content: center; gap: 16px; margin: 0 0 1.4rem; }
.rejilla .tarjeta { box-sizing: border-box; flex: 0 1 calc((100% - 32px) / 3); min-width: 250px; }
.hero, .tarjeta, .paso { box-sizing: border-box; }
.tarjeta {
  position: relative; background: var(--card); border: 1px solid var(--borde); border-radius: 18px; padding: 1.25rem 1.3rem;
  box-shadow: var(--sombra); animation: subir .55s ease both; transition: transform .24s ease, box-shadow .24s ease, border-color .24s ease;
}
.tarjeta:hover { transform: translateY(-6px); box-shadow: var(--sombra-alta); border-color: rgba(201, 162, 39, .7); }
.tarjeta-icono { width: 46px; height: 46px; border-radius: 13px; display: grid; place-items: center; font-size: 1.5rem; margin-bottom: .8rem;
  background: linear-gradient(135deg, rgba(79, 70, 229, .22), rgba(201, 162, 39, .22)); }
.tarjeta-etiqueta { position: absolute; top: 1.1rem; right: 1.2rem; font-size: .66rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--oro); }
.tarjeta h4 { margin: 0 0 .35rem; font-size: 1.08rem; font-weight: 700; }
.tarjeta p { margin: 0; opacity: .8; font-size: .92rem; line-height: 1.55; }
.pasos { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; margin: 0 0 1.2rem; }
.paso { display: flex; gap: .85rem; align-items: flex-start; animation: subir .6s ease both; }
.paso > span { flex: none; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: .9rem; color: #fff;
  background: linear-gradient(135deg, var(--indigo), var(--violeta)); box-shadow: 0 6px 14px rgba(79, 70, 229, .4); }
.paso b { display: block; font-size: .95rem; } .paso small { opacity: .75; font-size: .85rem; line-height: 1.45; }
.subtitulo-seccion { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-weight: 700; font-size: 1.15rem; margin: 1.4rem 0 .8rem; }

/* ---------- En vivo ---------- */
.punto-vivo { display: inline-block; width: .5rem; height: .5rem; border-radius: 50%; background: var(--vivo); margin-right: .5rem; vertical-align: middle; animation: pulso 1.6s infinite; }
.badge-vivo { display: inline-block; font-size: .7rem; font-weight: 700; letter-spacing: .14em; color: var(--vivo); border: 1px solid rgba(239, 68, 68, .45);
  background: rgba(239, 68, 68, .09); border-radius: 999px; padding: .28rem .8rem; margin-bottom: .2rem; }


/* =====================================================================
   PULIDO VISUAL: animaciones e interacciones (solo transform/opacity,
   que son baratas para el navegador y no hacen repintar la página)
   ===================================================================== */
@property --num { syntax: '<integer>'; inherits: false; initial-value: 0; }
@keyframes contar  { from { --num: 0; } }
@keyframes brillo  { 0% { transform: translateX(-120%) skewX(-20deg); } 100% { transform: translateX(260%) skewX(-20deg); } }
@keyframes esqueleto { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
@keyframes respira { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.06); } }
@keyframes revelar { from { opacity: 0; transform: translateY(26px) scale(.98); } to { opacity: 1; transform: none; } }

/* Columnas y bloques: entran una tras otra */
[data-testid="stHorizontalBlock"] > div { animation: subir .55s cubic-bezier(.2, .7, .2, 1) both; }
[data-testid="stHorizontalBlock"] > div:nth-child(2) { animation-delay: .06s; }
[data-testid="stHorizontalBlock"] > div:nth-child(3) { animation-delay: .12s; }
[data-testid="stHorizontalBlock"] > div:nth-child(4) { animation-delay: .18s; }
[data-testid="stHorizontalBlock"] > div:nth-child(n+5) { animation-delay: .24s; }

/* Aparecer al hacer scroll (solo en navegadores que lo soportan) */
@supports (animation-timeline: view()) {
  .tarjeta, .paso, [data-testid="stDataFrame"], [data-testid="stExpander"] {
    animation: revelar linear both; animation-timeline: view(); animation-range: entry 0% entry 55%;
  }
}

/* Hero: reflejo que cruza de vez en cuando + estadísticas que cuentan */
.hero .brillo { position: absolute; inset: 0; overflow: hidden; border-radius: inherit; pointer-events: none; z-index: 0; }
.hero .brillo::after { content: ""; position: absolute; top: 0; bottom: 0; width: 38%; left: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .10), transparent); animation: brillo 7s ease-in-out 1.2s infinite; }
.hero-chips span { transition: transform .2s ease, background .2s ease, border-color .2s ease; cursor: default; }
.hero-chips span:hover { transform: translateY(-3px); background: rgba(255, 255, 255, .17); border-color: rgba(201, 162, 39, .7); }
.hero-stats { display: flex; flex-wrap: wrap; gap: 2.2rem; margin-top: 1.3rem; padding-top: 1.1rem; border-top: 1px solid rgba(255, 255, 255, .12); }
.hero-stats > div { display: flex; flex-direction: column; }
.hero-stats .contador { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-weight: 800; font-size: 1.9rem; line-height: 1;
  font-variant-numeric: tabular-nums; color: #fff; animation: contar 1.8s cubic-bezier(.2, .7, .2, 1) both; counter-reset: n var(--num); }
.hero-stats .contador::after { content: counter(n) attr(data-sufijo); }
.hero-stats small { margin-top: .35rem; font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; color: rgba(255, 255, 255, .6); }

/* Tarjetas: borde con degradado al pasar el mouse + icono que reacciona */
.tarjeta::before { content: ""; position: absolute; inset: 0; border-radius: inherit; padding: 1.5px; pointer-events: none; opacity: 0; transition: opacity .3s ease;
  background: linear-gradient(135deg, var(--indigo), var(--violeta), var(--oro));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude; }
.tarjeta:hover::before { opacity: 1; }
.tarjeta-icono { transition: transform .3s cubic-bezier(.3, 1.6, .5, 1); }
.tarjeta:hover .tarjeta-icono { transform: rotate(-8deg) scale(1.12); }
.paso > span { transition: transform .25s cubic-bezier(.3, 1.6, .5, 1); }
.paso:hover > span { transform: scale(1.18) rotate(8deg); }

/* Marca del menú */
.marca-logo { transition: transform .35s cubic-bezier(.3, 1.6, .5, 1); }
.marca:hover .marca-logo { transform: rotate(-10deg) scale(1.08); }
.marca-logo { animation: respira 4.5s ease-in-out infinite; }

/* Botones: destello al pasar el mouse */
.stButton > button, .stDownloadButton > button { position: relative; overflow: hidden; }
.stButton > button::after, .stDownloadButton > button::after { content: ""; position: absolute; top: 0; bottom: 0; left: 0; width: 45%; pointer-events: none;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .28), transparent); transform: translateX(-130%) skewX(-20deg); }
.stButton > button:hover::after, .stDownloadButton > button:hover::after { animation: brillo .9s ease; }
[data-testid="stBaseButton-primary"]:hover, button[kind="primary"]:hover { transform: translateY(-2px) scale(1.02); }

/* Métricas: línea de color que se ilumina y número que se acentúa */
[data-testid="stMetric"]::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 2px; transform: scaleX(0); transform-origin: left;
  transition: transform .4s ease; background: linear-gradient(90deg, var(--indigo), var(--oro)); }
[data-testid="stMetric"]:hover::after { transform: scaleX(1); }
[data-testid="stMetricValue"] { transition: transform .25s ease; transform-origin: left; }
[data-testid="stMetric"]:hover [data-testid="stMetricValue"] { transform: scale(1.06); }

/* Contenedores con borde del resumen de hoy */
[class*="st-key-hoy_"] { border-radius: 18px; transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease; }
[class*="st-key-hoy_"]:hover { transform: translateY(-5px); box-shadow: var(--sombra-alta); border-color: rgba(201, 162, 39, .6); }
[class*="st-key-hoy_"] [data-testid="stMetric"] { box-shadow: none; background: transparent; border: none; padding: .4rem .2rem; }
[class*="st-key-hoy_"] [data-testid="stMetric"]:hover { transform: none; box-shadow: none; }

/* Esqueletos de carga */
.esqueletos { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
.esqueleto { height: 132px; border-radius: 18px; border: 1px solid var(--borde);
  background: linear-gradient(100deg, rgba(127, 127, 127, .06) 30%, rgba(127, 127, 127, .17) 50%, rgba(127, 127, 127, .06) 70%); background-size: 200% 100%;
  animation: esqueleto 1.4s linear infinite; }
[data-testid="stSpinner"] { animation: aparece .3s ease; }

/* Botones del menú lateral y de los accesos: el seleccionado respira con suavidad */
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) { animation: aparece .25s ease; }
[data-testid="stToast"], [data-testid="stNotification"] { border-radius: 14px; border: 1px solid var(--borde); box-shadow: var(--sombra-alta); }


/* Tablas */
[data-testid="stDataFrame"] { transition: box-shadow .25s ease, border-color .25s ease; }
[data-testid="stDataFrame"]:hover { box-shadow: var(--sombra-alta); border-color: rgba(79, 70, 229, .35); }

/* =====================================================================
   TABLAS CON DISEÑO PROPIO (tarjeta limpia en vez de cuadrícula tipo Excel)
   ===================================================================== */
.tabla-wrap {
  overflow: auto; border: 1px solid var(--borde); border-radius: 18px; background: var(--card);
  box-shadow: var(--sombra); margin: .3rem 0 1.1rem; animation: aparece .45s ease both;
  transition: box-shadow .25s ease, border-color .25s ease;
}
.tabla-wrap:hover { box-shadow: var(--sombra-alta); border-color: rgba(79, 70, 229, .35); }
.tabla { width: 100%; border-collapse: separate; border-spacing: 0; font-size: .92rem; font-variant-numeric: tabular-nums; }
.tabla th {
  position: sticky; top: 0; z-index: 2; text-align: left; white-space: nowrap; padding: .95rem 1.05rem;
  font-size: .68rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase;
  /* Fondo OPACO: color base del tema + tinte índigo encima. Si fuera translúcido, las filas se verían por debajo al hacer scroll. */
  background-color: var(--st-background-color, var(--background-color, Canvas));
  background-image: linear-gradient(180deg, rgba(79, 70, 229, .20), rgba(79, 70, 229, .08));
  border-bottom: 2px solid rgba(79, 70, 229, .35);
}
.tabla td { position: relative; z-index: 0; }
.tabla td { padding: .72rem 1.05rem; white-space: nowrap; border-bottom: 1px solid rgba(127, 127, 127, .13); transition: background .15s ease; }
.tabla tbody tr:last-child td { border-bottom: none; }
.tabla tbody tr:hover td { background: rgba(79, 70, 229, .09); }
.tabla tbody tr:hover td:first-child { box-shadow: inset 3px 0 0 var(--indigo); }
.tabla .num { text-align: right; }
.tabla td.primera { font-weight: 600; }
.tabla .idx { opacity: .55; font-size: .8rem; width: 1%; }
.tabla .vacio { opacity: .4; }
.tabla .si { color: #16a34a; font-weight: 700; }
.tabla a { color: var(--indigo); font-weight: 600; text-decoration: none; border-bottom: 1px dashed rgba(79, 70, 229, .5); }
.tabla a:hover { border-bottom-style: solid; }
.tabla img { width: 28px; height: 28px; object-fit: contain; border-radius: 8px; vertical-align: middle; }
.tabla .pill { display: inline-block; padding: .2rem .75rem; border-radius: 999px; font-size: .82rem; font-weight: 600;
  background: rgba(127, 127, 127, .14); }
.tabla .pill.ok { color: #16a34a; background: rgba(22, 163, 74, .15); }
.tabla .pill.mal { color: #dc2626; background: rgba(220, 38, 38, .13); }
.tabla .pill.aviso { color: #d97706; background: rgba(217, 119, 6, .15); }
.tabla .barra { display: flex; align-items: center; gap: .6rem; min-width: 120px; }
.tabla .barra-pista { flex: 1; height: 7px; border-radius: 99px; background: rgba(127, 127, 127, .2); overflow: hidden; }
.tabla .barra-pista i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--indigo), var(--violeta), var(--oro)); }
.tabla .barra b { font-weight: 600; min-width: 2.2rem; text-align: right; }
.tabla .mini { display: inline-flex; align-items: flex-end; gap: 2px; height: 22px; }
.tabla .mini i { width: 4px; border-radius: 2px; background: linear-gradient(var(--violeta), var(--indigo)); }
.tabla-pie { padding: .55rem 1.05rem; font-size: .74rem; text-align: right; opacity: .55; border-top: 1px solid rgba(127, 127, 127, .13); }
.tabla-vacia { padding: 1.4rem; text-align: center; border: 1px dashed var(--borde); border-radius: 16px; opacity: .7; margin: .3rem 0 1.1rem; }
/* st.table (tablas fijas) con el mismo aire */
[data-testid="stTable"] table { border-collapse: separate; border-spacing: 0; border: 1px solid var(--borde); border-radius: 16px; overflow: hidden; }
[data-testid="stTable"] th { font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; background: rgba(79, 70, 229, .12); }
[data-testid="stTable"] td, [data-testid="stTable"] th { border-left: none; border-right: none; padding: .65rem 1rem; }

/* Textos de Streamlit que vienen en inglés: se muestran en español */
[data-testid="stAppDeployButton"], .stDeployButton { display: none !important; }
[data-testid="stFileUploaderDropzoneInstructions"] > div > span,
[data-testid="stFileUploaderDropzoneInstructions"] > div > small { position: relative; display: block; visibility: hidden; height: 1.3rem; }
[data-testid="stFileUploaderDropzoneInstructions"] > div > span::before { content: "Arrastra y suelta tu imagen aquí"; visibility: visible; position: absolute; left: 0; top: 0; white-space: nowrap; }
[data-testid="stFileUploaderDropzoneInstructions"] > div > small::before { content: "Hasta 200 MB por archivo"; visibility: visible; position: absolute; left: 0; top: 0; white-space: nowrap; }
[data-testid="stFileUploaderDropzone"] button { font-size: 0 !important; }
[data-testid="stFileUploaderDropzone"] button::after { content: "Buscar archivos"; font-size: .875rem; }

/* Quien prefiere menos movimiento (accesibilidad) no ve animaciones */
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
</style>
"""


def aplicar_estilos(indice_seccion: int):
    """Inyecta el CSS. La transición de entrada se repite solo cuando cambias de sección (el nombre de la
    animación cambia con cada sección), así que no parpadea con las actualizaciones automáticas."""
    entrada = (f"<style>@keyframes entrada-{indice_seccion} {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: none; }} }}"
               f".block-container {{ animation: entrada-{indice_seccion} .5s ease both; }}</style>")
    # Si el tema (config.toml) ya usa el índigo como color principal, no hace falta girar el rojo por defecto.
    giro = "" if _tema_ya_es_indigo() else (
        "<style>[data-baseweb=\"slider\"], [data-baseweb=\"checkbox\"] { filter: hue-rotate(244deg) saturate(.92); }</style>")
    st.markdown(ESTILOS + entrada + giro, unsafe_allow_html=True)
