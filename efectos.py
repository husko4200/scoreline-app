"""Color por deporte y animaciones de balones, encima de diseno.py y estilos.py.

Se usa desde app.py (después de diseno.aplicar_estilos y estilos.cargar):
    efectos.aplicar(seccion)   # recolorea la app según el deporte y añade fondos, cargas y destellos
    efectos.pista(seccion)     # franja animada con balones al inicio de la página

Cómo se integra con lo que ya tienes:
  · NBA, Fútbol y En vivo redefinen --indigo / --violeta (y los tonos fijos rgba(79,70,229,…)) con su color;
    así botones, pestañas, tablas, título, barra superior y menú cambian de color solos.
  · Inicio y Diagnóstico conservan tu paleta índigo original.
  · No repite nada que diseno.py ya hace (entradas, tarjetas, métricas, tablas...). Todos los nombres
    propios llevan el prefijo «ef-» para no chocar con tus @keyframes.

Clases listas para usar en cualquier panel:
    .ef-flash   destello al cambiar un marcador (añádela al elemento que cambió)
    .ef-latido  latido suave para algo «en juego»
"""
import streamlit as st

from secciones import DIAGNOSTICO, FUTBOL, INICIO, NBA, VIVO

try:  # para saber si el tema ya usa índigo y calcular bien el giro de color de sliders/casillas
    import diseno
    _BASE_HUE = 243 if diseno._tema_ya_es_indigo() else 0
except Exception:  # noqa: BLE001
    _BASE_HUE = 0

# Tema por sección. rgb = acento, rgb2 = secundario (para sombras y brillos), hue = tono destino de sliders.
TEMAS = {
    NBA: dict(ac="#F26B21", ac2="#1D428A", rgb="242,107,33", rgb2="29,66,138", hue=24, emoji="🏀",
              suelo="repeating-linear-gradient(90deg, rgba(242,107,33,.055) 0 2px, transparent 2px 64px)"),   # tablones
    FUTBOL: dict(ac="#16A34A", ac2="#0B5D36", rgb="22,163,74", rgb2="11,93,54", hue=142, emoji="⚽",
                 suelo="repeating-linear-gradient(90deg, rgba(22,163,74,.07) 0 90px, transparent 90px 180px)"),  # césped segado
    VIVO: dict(ac="#E5334B", ac2="#F26B21", rgb="229,51,75", rgb2="242,107,33", hue=0, emoji="🔴",
               suelo="repeating-linear-gradient(115deg, rgba(229,51,75,.04) 0 2px, transparent 2px 46px)"),
}

_BASQUET = (
    '<svg viewBox="0 0 48 48"><circle cx="24" cy="24" r="22" fill="#F26B21" stroke="#6b2a09" stroke-width="2"/>'
    '<path d="M24 2v44M2 24h44M8 8c10 9 10 23 0 32M40 8c-10 9-10 23 0 32" fill="none" stroke="#6b2a09" stroke-width="2"/></svg>'
)
_FUTBOL = (
    '<svg viewBox="0 0 48 48"><circle cx="24" cy="24" r="22" fill="#fff" stroke="#16231b" stroke-width="2"/>'
    '<polygon points="24,14 33,20.5 29.5,31 18.5,31 15,20.5" fill="#16231b"/>'
    '<path d="M24 14V3M33 20.5l10-3.5M29.5 31l6.5 8.5M18.5 31L12 39.5M15 20.5L5 17" stroke="#16231b" stroke-width="2" fill="none"/></svg>'
)
# Líneas de cancha / campo, dibujadas con poca opacidad al fondo de la franja.
_LINEAS = (
    '<svg class="ef-lineas" viewBox="0 0 800 80" preserveAspectRatio="xMidYMid slice"><g fill="none" stroke="#fff" stroke-width="2">'
    '<circle cx="400" cy="40" r="26"/><path d="M400 0v80"/>'
    '<path d="M0 14h110v52H0M800 14H690v52h110"/><path d="M110 28a16 16 0 0 1 0 24M690 28a16 16 0 0 0 0 24"/></g></svg>'
)

# ---------------------------------------------------------------------------
# CSS común a todas las secciones (franja de balones, cargas, destellos)
# ---------------------------------------------------------------------------
_CSS_BASE = """
<style>
@keyframes ef-bote { 0%, 100% { transform: translateY(0) scale(1.12, .86); } 8% { transform: translateY(0) scale(1, 1); }
                     50% { transform: translateY(-30px) scale(1, 1); } 92% { transform: translateY(0) scale(1, 1); } }
@keyframes ef-sombra { 0%, 100% { transform: scaleX(1.1); opacity: .45; } 50% { transform: scaleX(.55); opacity: .15; } }
@keyframes ef-rodar { from { transform: translateX(0); } to { transform: translateX(min(50vw, 520px)); } }
@keyframes ef-gira { from { transform: rotate(0); } to { transform: rotate(900deg); } }
@keyframes ef-reflejo { 0%, 55% { transform: translateX(-130%) skewX(-18deg); } 100% { transform: translateX(330%) skewX(-18deg); } }
@keyframes ef-destello { 0% { background: rgba(242, 180, 33, .55); transform: scale(1.05); } 100% { background: transparent; transform: none; } }
@keyframes ef-latido { 0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, .45); } 50% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); } }
@keyframes ef-bote-carga { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-9px); } }

/* ---------- Franja con balones ---------- */
.ef-pista { position: relative; height: 78px; margin: 0 0 1.1rem; border-radius: 18px; overflow: hidden; isolation: isolate;
  background: linear-gradient(105deg, var(--pa), var(--pb));
  box-shadow: 0 12px 30px -14px rgba(var(--pr), .7), inset 0 0 0 1px rgba(255, 255, 255, .14); }
.ef-pista .ef-lineas { position: absolute; inset: 0; width: 100%; height: 100%; opacity: .16; }
.ef-pista::after { content: ""; position: absolute; top: 0; bottom: 0; left: 0; width: 30%; pointer-events: none;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .22), transparent);
  animation: ef-reflejo 7s ease-in-out 1.2s infinite; }
.ef-balon { position: absolute; width: 42px; height: 42px; bottom: 11px; z-index: 1; }
.ef-balon svg { width: 100%; height: 100%; display: block; }
.ef-balon.bota { right: 12%; transform-origin: 50% 100%; animation: ef-bote 1.05s cubic-bezier(.3, 0, .6, 1) infinite; }
.ef-balon .sombra { position: absolute; left: 10%; right: 10%; bottom: -6px; height: 7px; border-radius: 50%;
  background: rgba(0, 0, 0, .35); filter: blur(2px); animation: ef-sombra 1.05s cubic-bezier(.3, 0, .6, 1) infinite; }
.ef-balon.rueda { left: 6%; animation: ef-rodar 7s ease-in-out infinite alternate; }
.ef-balon.rueda svg { animation: ef-gira 7s ease-in-out infinite alternate; }
@media (max-width: 640px) { .ef-pista { height: 62px; } .ef-balon { width: 34px; height: 34px; bottom: 9px; } }

/* ---------- Carga: el indicador de Streamlit se vuelve un balón que bota ---------- */
[data-testid="stSpinnerIcon"] { display: none !important; }
[data-testid="stSpinner"]::before, [data-testid="stStatusWidget"]::before {
  content: var(--ef-emoji, "⚽"); display: inline-block; margin-right: .5rem; animation: ef-bote-carga .7s ease-in-out infinite; }

/* ---------- Utilidades para los paneles ---------- */
.ef-flash { animation: ef-destello 1.1s ease-out 1; }
.ef-latido { animation: ef-latido 1.8s ease-in-out infinite; }
</style>
"""

# ---------------------------------------------------------------------------
# CSS por deporte: redefine la paleta y los tonos fijos de diseno.py / estilos.py
# ---------------------------------------------------------------------------
_CSS_TEMA = """
<style>
:root { --indigo: __AC__; --violeta: __AC2__; --ef-emoji: "__EMOJI__";
  --sombra-alta: 0 2px 4px rgba(15, 23, 42, .08), 0 18px 40px rgba(__RGB__, .24); }

/* Fondo: luces de estadio + el «suelo» del deporte (tablones o césped segado) */
.stApp { background-image:
  radial-gradient(1100px 520px at 4% -8%, rgba(__RGB__, .16), transparent 60%),
  radial-gradient(900px 420px at 100% -6%, rgba(__RGB2__, .12), transparent 60%),
  __SUELO__; }
::selection { background: rgba(__RGB__, .28); }
:focus-visible { outline: 2px solid rgba(__RGB__, .7) !important; }

/* Menú lateral */
[data-testid="stSidebar"] { background: linear-gradient(180deg, rgba(__RGB__, .11), rgba(__RGB2__, .06)); }
.marca-logo { box-shadow: 0 8px 20px rgba(__RGB__, .45); }
div[role="radiogroup"] label:hover { background: rgba(__RGB__, .13); }
div[role="radiogroup"] label:has(input:checked) { box-shadow: 0 6px 18px rgba(__RGB__, .38); }

/* Botones, pestañas, entradas */
.stButton > button:hover, .stDownloadButton > button:hover { box-shadow: 0 8px 20px rgba(__RGB__, .25); }
.stButton > button:hover { background-color: rgba(__RGB__, .10); }
[data-testid="stBaseButton-primary"], button[kind="primary"] { box-shadow: 0 6px 16px rgba(__RGB__, .35); }
[data-testid="stBaseButton-primary"]:hover, button[kind="primary"]:hover { box-shadow: 0 10px 26px rgba(__RGB__, .5) !important; }
button[data-baseweb="tab"][aria-selected="true"] { box-shadow: 0 6px 16px rgba(__RGB__, .35); }
[data-baseweb="select"] > div:focus-within, [data-baseweb="input"]:focus-within, [data-baseweb="base-input"]:focus-within {
  box-shadow: 0 0 0 3px rgba(__RGB__, .22); }
[data-testid="stNumberInput"] button:hover, [data-testid="stNumberInput"] button:focus { background: __AC__ !important; }
/* Sliders, interruptores y casillas: el rojo de Streamlit se gira al color del deporte */
[data-baseweb="slider"], [data-baseweb="checkbox"] { filter: __FILTRO__; }

/* Tablas con el color del deporte */
.tabla th { background-image: linear-gradient(180deg, rgba(__RGB__, .20), rgba(__RGB__, .08)); border-bottom-color: rgba(__RGB__, .55); }
.tabla tbody tr:hover td { background: rgba(__RGB__, .09); }
.tabla-wrap:hover, [data-testid="stDataFrame"]:hover { border-color: rgba(__RGB__, .4); }
.tabla a { color: __AC__; border-bottom-color: rgba(__RGB__, .5); }
[data-testid="stTable"] th { background: rgba(__RGB__, .12); }
::-webkit-scrollbar-thumb { background: linear-gradient(__AC__, __AC2__); }
</style>
"""


def aplicar(seccion):
    """Inyecta los efectos comunes y, si la sección es de un deporte, recolorea toda la app."""
    html = _CSS_BASE
    t = TEMAS.get(seccion)
    if t:
        giro = (t["hue"] - _BASE_HUE) % 360
        filtro = "none" if giro == 0 else f"hue-rotate({giro}deg) saturate(.95)"
        css = (_CSS_TEMA.replace("__AC2__", t["ac2"]).replace("__AC__", t["ac"])
               .replace("__RGB2__", t["rgb2"]).replace("__RGB__", t["rgb"])
               .replace("__EMOJI__", t["emoji"]).replace("__SUELO__", t["suelo"]).replace("__FILTRO__", filtro))
        html += css
    st.markdown(html, unsafe_allow_html=True)


def pista(seccion):
    """Franja decorativa con balones animados; cambia según la sección."""
    if seccion == DIAGNOSTICO:
        return  # página técnica: sin decoración
    basquet = f'<div class="ef-balon bota">{_BASQUET}<span class="sombra"></span></div>'
    futbol = f'<div class="ef-balon rueda">{_FUTBOL}</div>'
    if seccion == NBA:
        balones, colores = basquet, ("#F26B21", "#1D428A", "242,107,33")
    elif seccion == FUTBOL:
        balones, colores = futbol, ("#16A34A", "#0B5D36", "22,163,74")
    elif seccion == VIVO:
        balones, colores = basquet + futbol, ("#E5334B", "#F26B21", "229,51,75")
    else:  # Inicio: los dos deportes
        balones, colores = basquet + futbol, ("#F26B21", "#16A34A", "242,107,33")
    estilo = f"--pa:{colores[0]};--pb:{colores[1]};--pr:{colores[2]}"
    st.markdown(f'<div class="ef-pista" style="{estilo}" aria-hidden="true">{_LINEAS}{balones}</div>',
                unsafe_allow_html=True)
