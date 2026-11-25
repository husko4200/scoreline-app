"""Sección NBA: un solo lugar con dos grupos (Equipos y Jugadores) y sus vistas.

Cada herramienta aparece una sola vez.
"""
import base64
import os
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

import streamlit as st

import auth
import ficha_equipos
import nba
import nba_calendario
import nba_equipos
import nba_extra as nx
import nba_hoy
import nba_jugadores
import pulido

# Etiquetas de las vistas (un solo lugar para editar nombres)
LINEAS, PLANTELES, PROXIMOS = "🎯 Líneas", "🛡️ Planteles", "📅 Próximos"
CAL_POS = "🗓️ Calendario y Posiciones"
JUG_STATS = "📈 Estadísticas"
COMBINADAS = "💎 Combinadas con IA (PRO)"

G_EQUIPOS, G_JUGADORES = "🛡️ Equipos", "👤 Jugadores"

@dataclass(frozen=True)
class Vista:
    dibujar: Callable            # dibuja la vista (sin argumentos)


# --- Actualizar datos -------------------------------------------------------------------------------------------
# Cachés que cambian con los partidos. NO se toca _temporada_cerrada ni los box scores: están en disco y volver a
# bajarlos cuesta decenas de consultas, y las temporadas cerradas no cambian. (st.cache_data.clear() global
# borraría también esas.)
_CACHES_VOLATILES = [(nba, ["_temporada_en_curso", "scoreboard", "resumen"]),
                     (nx, ["lesiones", "posiciones"]),
                     (nba_hoy, ["_pronostico"]),
                     (ficha_equipos, ["_eventos", "_partidos", "_serie_guardada"])]


def _actualizar():
    """Callback del botón: vacía las cachés volátiles (partidos en curso, líneas, lesiones, pronósticos)."""
    for modulo, nombres in _CACHES_VOLATILES:
        for nombre in nombres:
            limpiar = getattr(getattr(modulo, nombre, None), "clear", None)
            if limpiar:
                limpiar()


def _boton_actualizar(col):
    """El botón va en la misma fila que los selectores de grupo y vista, a la derecha (así no ocupa una fila propia)."""
    col.button("🔄 Actualizar datos", on_click=_actualizar, use_container_width=True, key="nba_actualizar",
               help="Vuelve a leer partidos en curso, líneas y lesiones. Las temporadas cerradas guardadas en disco se conservan.")


def _lineas():
    """El análisis de líneas (los próximos partidos tienen ahora su propia vista)."""
    ficha_equipos.render()


def _proximos():
    """Partidos de hoy y mañana con su pronóstico; «Analizar» lleva a «Líneas» con los dos equipos ya cargados."""
    nba_hoy.proximos()


def _combinadas():
    """Analizador de combinadas: exclusivo para miembros Pro (bloqueado entero por costo de IA)."""
    import planes
    if not planes.es_pro(planes.uid_actual()):
        st.info("🔒 **Lector de Boletas con IA** está bloqueado en el plan gratuito.")
        if st.button("🔒 Solo con plan Pro · Desbloquear", type="primary", key="btn_lock_nba_comb"):
            planes.modal_pro("El Lector de Boletas con IA es exclusivo del plan Pro.")
        return
    import nba_combinada
    nba_combinada.render()


def _calendario_y_posiciones():
    """Calendario mensual con conteo de partidos, tabla Este/Oeste y reporte de lesionados."""
    t_cal, t_pos, t_les = st.tabs(["🗓️ Calendario del mes", "🏆 Posiciones Este / Oeste", "🩹 Lesionados"])
    with t_cal:
        nba_calendario.render()
    with t_pos:
        nx.vista_posiciones()
    with t_les:
        nx.vista_lesiones()


# Un solo lugar para añadir, quitar o reordenar vistas: grupo -> {etiqueta: Vista}. El orden de aquí es el de los radios.
VISTAS = {
    G_EQUIPOS: {
        LINEAS:     Vista(_lineas),
        PLANTELES:  Vista(nba_equipos.render),
        PROXIMOS:   Vista(_proximos),
        CAL_POS:    Vista(_calendario_y_posiciones),
    },
    G_JUGADORES: {
        JUG_STATS:   Vista(nba_jugadores.render),
        COMBINADAS:  Vista(_combinadas),
    },
}
GRUPOS = {grupo: list(vistas) for grupo, vistas in VISTAS.items()}   # la app lo usa para contar herramientas


# --- Conservar lo elegido en la vista de Jugadores -------------------------------------------------------------
# Streamlit borra el estado de un widget cuando deja de dibujarse en una ejecución (p. ej. al cambiar de grupo). Para
# que lo elegido no se pierda, se guarda una copia de los valores de la vista y se restauran antes de volver a
# dibujarla. Las claves se detectan solas: son las que la vista crea.
_SNAP = "nba_jug_snap"        # {nombre de la vista: {clave: valor}}


def _dibujar_conservando(nombre, vista):
    snap = st.session_state.setdefault(_SNAP, {})
    for k, v in snap.get(nombre, {}).items():
        if k not in st.session_state:
            st.session_state[k] = v          # restaura lo que Streamlit había borrado
    antes = set(st.session_state)
    vista.dibujar()
    claves = set(snap.get(nombre, {})) | (set(st.session_state) - antes)
    # Los botones (valor True/False) no se guardan: no admiten que se les asigne un valor.
    snap[nombre] = {k: st.session_state[k] for k in claves
                    if k in st.session_state and not isinstance(st.session_state[k], bool)}


# --- Fondo de la página -------------------------------------------------------------------------------------------
# Fondo claro y sobrio: degradado azul grisáceo, dos luces suaves y las líneas de una cancha dibujadas muy tenues.
# Si junto a este archivo hay una foto llamada fondo_nba.jpg (o .jpeg, .png, .webp) se usa como fondo, con un velo claro
# encima para que el texto siga leyéndose bien.
_CANCHA_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='1880' height='1000' viewBox='0 0 940 500' fill='none' "
    "stroke='#1e3a8a' stroke-opacity='.075' stroke-width='2.2'>"
    "<rect x='10' y='10' width='920' height='480' rx='6'/><path d='M470 10V490'/><circle cx='470' cy='250' r='60'/>"
    "<rect x='10' y='170' width='190' height='160'/><circle cx='200' cy='250' r='60'/>"
    "<path d='M10 30H150A237 237 0 0 1 150 470H10'/><circle cx='52' cy='250' r='9'/>"
    "<rect x='740' y='170' width='190' height='160'/><circle cx='740' cy='250' r='60'/>"
    "<path d='M930 30H790A237 237 0 0 0 790 470H930'/><circle cx='888' cy='250' r='9'/></svg>")


@st.cache_resource(show_spinner=False)
def _foto_fondo():
    """Data URI de fondo_nba.* si existe junto a este archivo; None si no hay foto."""
    base = os.path.dirname(os.path.abspath(__file__))
    for ext, mime in ((".jpg", "jpeg"), (".jpeg", "jpeg"), (".png", "png"), (".webp", "webp")):
        ruta = os.path.join(base, "fondo_nba" + ext)
        if os.path.isfile(ruta):
            try:
                with open(ruta, "rb") as f:
                    return f"data:image/{mime};base64,{base64.b64encode(f.read()).decode()}"
            except OSError:
                continue
    return None


# Superficies opacas: tablas, grupos de botones (radios), filas de escudos y desplegables dejan de ser translúcidos, así las
# líneas de la cancha del fondo no se ven a través de ellos.
_SUPERFICIES = [   # (selectores, reglas); solo se aplican al contenido principal, no a la barra lateral
    ('[data-testid="stDataFrame"],[data-testid="stTable"]',
     'background:#fff !important;border:1px solid #dbe3f0 !important;border-radius:16px !important;overflow:hidden;'
     'box-shadow:0 10px 26px -14px rgba(30,41,90,.28)'),
    ('[data-testid="stDataFrameResizable"],[data-testid="stDataFrame"] iframe', 'background:#fff !important'),
    ('.st-key-fe_a_barra,.st-key-fe_b_barra',
     'background:#fff !important;border:1px solid #dbe3f0 !important;border-radius:18px !important;padding:12px !important;'
     'box-shadow:0 8px 22px -14px rgba(30,41,90,.25)'),
    ('[data-testid="stExpander"] details',
     'background:#fff !important;border:1px solid #dbe3f0 !important;border-radius:14px !important'),
    ('[data-baseweb="select"] > div', 'background:#fff !important'),
]
_CSS_SUPERFICIES = "".join(
    "{" .join((",".join(f'[data-testid="stMain"] {x}' for x in sel.split(",")), regla)) + "}"
    for sel, regla in _SUPERFICIES)


def _css_fondo() -> str:
    foto = _foto_fondo()
    if foto:
        capa = f'linear-gradient(rgba(244,246,251,.90),rgba(238,242,249,.95)),url("{foto}") center/cover no-repeat fixed'
    else:
        capa = "linear-gradient(180deg,#F7F9FD 0%,#F1F4FA 100%) fixed"
    return (f'html,body{{background:{capa} !important;background-color:#F5F7FB !important}}.stApp{{background:transparent !important}}'
            '[data-testid="stAppViewContainer"],[data-testid="stMain"],[data-testid="stHeader"],.main,.block-container'
            '{background:transparent !important;background-image:none !important}'
            '.stApp::before,.stApp::after,[data-testid="stAppViewContainer"]::before,[data-testid="stAppViewContainer"]::after,'
            '[data-testid="stMain"]::before,[data-testid="stMain"]::after{{background:none !important;background-image:none !important;'
            'animation:none !important}}'
            # Grupo y vista: cada grupo de botones ocupa todo el ancho de su columna, en una sola línea y con las opciones centradas
            '[data-testid="stMain"] .st-key-nba_grupo [role="radiogroup"],[data-testid="stMain"] [class*="st-key-nba_vista_"] [role="radiogroup"]'
            '{width:100% !important;flex-wrap:nowrap !important;justify-content:center !important}'
            '[data-testid="stMain"] .st-key-nba_grupo [role="radiogroup"] label,'
            '[data-testid="stMain"] [class*="st-key-nba_vista_"] [role="radiogroup"] label'
            '{flex:1 1 auto !important;justify-content:center !important;white-space:nowrap}'
            # Menos aire vertical: el título de cada vista pegado a la barra de herramientas
            '[data-testid="stMain"] h1{{margin-top:0 !important;padding-top:.2rem !important;padding-bottom:.2rem !important}}'
            + _CSS_SUPERFICIES)


def render():
    st.markdown(f"<style>{_css_fondo()}</style>", unsafe_allow_html=True)
    pulido.cabecera("NBA", "Equipos y jugadores")
    if st.session_state.pop("nba_ir_a_lineas", False):   # lo pone el botón «Analizar» de Próximos
        st.session_state["nba_grupo"] = G_EQUIPOS
        st.session_state[f"nba_vista_{G_EQUIPOS}"] = LINEAS
    if st.session_state.get("nba_grupo") not in VISTAS:
        st.session_state.pop("nba_grupo", None)   # un grupo que ya no existe (p. ej. «Liga», de una sesión anterior)
    # Una sola fila compacta: grupo, vista y «Actualizar datos»
    c_grupo, c_vista, _, c_btn = st.columns([2.2, 3.4, 0.2, 1.6], vertical_alignment="center", gap="small")
    grupo = c_grupo.radio("Grupo", list(VISTAS), horizontal=True, label_visibility="collapsed", key="nba_grupo")
    if st.session_state.get(f"nba_vista_{grupo}") not in VISTAS[grupo]:
        st.session_state.pop(f"nba_vista_{grupo}", None)   # una vista que ya no existe (p. ej. de una sesión anterior)
    nombre = c_vista.radio("Vista", list(VISTAS[grupo]), horizontal=True, label_visibility="collapsed",
                           key=f"nba_vista_{grupo}")
    vista = VISTAS[grupo][nombre]
    _boton_actualizar(c_btn)
    if grupo == G_JUGADORES:
        _dibujar_conservando(nombre, vista)
    else:
        vista.dibujar()
