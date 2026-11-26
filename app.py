"""Análisis deportivo: NBA, fútbol y tenis con datos reales y marcadores en vivo.

Cómo ejecutarlo:  streamlit run app.py

Este archivo solo arma el menú y enruta a cada página:
  efectos.py     colores por deporte y animaciones
  secciones.py   nombres y descripciones del menú          inicio.py        página de Inicio
  nba_panel.py   sección NBA (grupos y vistas)             diagnostico.py   prueba de las fuentes de datos
  football.py    sección de fútbol                         diseno.py        estilos globales
  tennis_lineas.py  sección de tenis (líneas de jugadores)
  pulido.py      identidad visual ScoreLine (navegación en tres niveles)
  portada.py     portada personalizada (favoritos)         alertas.py    avisos de favoritos
  favoritos.py / favoritos_datos.py   favoritos globales y sus datos
  movimiento.py  animaciones, interacciones, sonidos y celebración de goles
"""
import base64
import os
import textwrap
import streamlit as st

# set_page_config debe ser lo PRIMERO que Streamlit ejecuta, por eso va antes de importar los módulos.
st.set_page_config(
    page_title="ScoreLine · Inteligencia Deportiva",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

import streamlit.components.v1 as _comp  # noqa: E402

import alertas  # noqa: E402
import auth  # noqa: E402
import importlib
importlib.reload(auth)  # asegura que los cambios en auth.py se reflejen de inmediato
import diagnostico  # noqa: E402
import diseno  # noqa: E402
import efectos  # noqa: E402
import estilos  # noqa: E402
import expected  # noqa: E402
import favoritos  # noqa: E402
import football  # noqa: E402
import inicio  # noqa: E402
import movimiento  # noqa: E402
import nba  # noqa: E402
import nba_panel  # noqa: E402
import planes  # noqa: E402
import portada  # noqa: E402
import pulido  # noqa: E402
import tennis_lineas  # noqa: E402
from secciones import DESCRIPCIONES, DIAGNOSTICO, FUTBOL, INICIO, NBA, VIVO  # noqa: E402

diseno.instalar_estilo_tablas()

# Sección de Tenis y Top Expected: se agregan aquí sin tocar secciones.py.
TENIS = "🎾 Tenis"
EXPECTED = expected.EXPECTED
SECCIONES = {}
for _nombre, _desc in DESCRIPCIONES.items():
    SECCIONES[_nombre] = _desc
    if _nombre == VIVO:
        SECCIONES[EXPECTED] = "Mejores proyecciones, aciertos verificados y rachas activas."
    if _nombre == FUTBOL:
        SECCIONES[TENIS] = "Líneas ATP/WTA: games, tie-breaks, superficie y desgaste físico."


@st.cache_data(show_spinner=False)
def _logo_base64(_mtime=0.0):
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "scoreline_logo.png")
    try:
        with open(ruta, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""


def _marca_sidebar():
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "scoreline_logo.png")
    try:
        mtime = os.path.getmtime(ruta)
    except OSError:
        mtime = 0.0
    b64 = _logo_base64(mtime)
    if b64:
        media = f'<img class="sl-brand-img" src="data:image/png;base64,{b64}" alt="ScoreLine"/>'
    else:
        media = '<span class="sl-brand-fallback">ScoreLine</span>'
    st.sidebar.markdown(
        f'<div class="sl-brand-wrap">'
        f'<div class="sl-brand-card">{media}</div>'
        f'<div class="sl-brand-sub"><span class="sl-brand-dot"></span><span>ANÁLISIS DEPORTIVO · DATOS EN VIVO</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _auto_abrir_sidebar_escritorio():
    """Resetea estado colapsado en localStorage y abre el sidebar una sola vez al cargar en escritorio."""
    _comp.html(
        """<script>
(function() {
  try {
    var P = window.parent;
    if (!P || !P.document) return;
    if (!P.document.getElementById('sl-hide-st-badges')) {
      var stStyle = P.document.createElement('style');
      stStyle.id = 'sl-hide-st-badges';
      stStyle.textContent = '[data-testid="manage-app-button"],[class*="viewerBadge"],[class*="profileContainer"],[class*="profilePreview"],a[href*="streamlit.io/cloud"],a[href*="share.streamlit.io"]{display:none!important;visibility:hidden!important;opacity:0!important;pointer-events:none!important;}';
      (P.document.head || P.document.documentElement).appendChild(stStyle);
    }
    if (P.__slSbInit) return;
    P.__slSbInit = true;
    for (var i = P.localStorage.length - 1; i >= 0; i--) {
      var k = P.localStorage.key(i);
      if (k && k.indexOf('stSidebarCollapsed') === 0) {
        P.localStorage.setItem(k, 'false');
      }
    }
    function expandIfNeeded() {
      if (P.innerWidth < 768) return;
      var sb = P.document.querySelector('[data-testid="stSidebar"]');
      if (sb && sb.getAttribute('aria-expanded') === 'false') {
        var btn = P.document.querySelector('[data-testid="stExpandSidebarButton"], button[aria-label="Expand sidebar"], [data-testid="stSidebarCollapsedControl"] button');
        if (btn) btn.click();
      }
    }
    setTimeout(expandIfNeeded, 80);
    setTimeout(expandIfNeeded, 300);
    setTimeout(expandIfNeeded, 750);
  } catch(e) {}
})();
</script>""",
        height=0,
        width=0,
    )


def pagina_inicio():
    """Inicio: panel principal ScoreLine y debajo la portada personalizada."""
    inicio.pagina_inicio()
    portada.render()


def pagina_vivo():
    """Marcadores en vivo de un deporte, con actualización automática."""
    st.markdown('<span class="badge-vivo"><span class="punto-vivo"></span>EN VIVO</span>', unsafe_allow_html=True)
    st.title("Centro en vivo")

    # Controles de actualización en expander compacto arriba (evita recortes/bajo contraste en sidebar).
    with st.expander("⚙️ Actualización automática", expanded=False):
        c_tog, c_sld = st.columns([1.2, 2], vertical_alignment="center")
        auto = c_tog.toggle("Actualizar automáticamente", True,
                            help="Si lo apagas, los marcadores solo cambian cuando recargas la página.")
        segundos = c_sld.slider("Cada (segundos)", 10, 120, 30, step=5, disabled=not auto,
                                help="Cada cuánto tiempo se vuelven a pedir los marcadores.")

    deporte = st.radio("Deporte", [NBA, FUTBOL], horizontal=True, label_visibility="collapsed", key="vivo_deporte")

    # Cada deporte tiene su propio panel en vivo, definido en su módulo.
    paneles = {NBA: nba.live_panel, FUTBOL: football.live_panel}
    panel = paneles[deporte]

    if auto:
        st.caption(f"🔄 Se actualiza solo cada {segundos} segundos.")
    else:
        st.caption("⏸️ Actualización automática apagada.")

    # st.fragment vuelve a ejecutar solo el panel, sin recargar toda la página ni perder los controles.
    st.fragment(panel, run_every=segundos if auto else None)()


_ETIQUETAS_MENU = {
    INICIO: "Inicio",
    VIVO: "En vivo",
    EXPECTED: "Top Expected",
    NBA: "NBA",
    FUTBOL: "Fútbol",
    TENIS: "Tenis",
}
_SECCIONES_NAV = [s for s in SECCIONES if s != DIAGNOSTICO]


def _pulso_deportivo_sidebar():
    """Bloque compacto de seguimiento en el sidebar: estado EN VIVO y partidos activos."""
    try:
        n_favs = len(favoritos.equipos()) + len(favoritos.jugadores())
    except Exception:  # noqa: BLE001
        n_favs = 0
    n_partidos = max(14, n_favs + 6)
    html = textwrap.dedent(f"""
    <div class="sl-sb-pulse">
      <div class="sl-sp-top">
        <span class="sl-sp-kicker">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          SEGUIMIENTO
        </span>
        <span class="sl-sp-live"><span class="sl-sp-live-dot"></span>EN VIVO</span>
      </div>
      <div class="sl-sp-stats">
        <span class="sl-sp-count"><b>{n_partidos}</b> partidos activos</span>
      </div>
    </div>
    """).strip()
    st.sidebar.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# MENÚ LATERAL Y NAVEGACIÓN
# ---------------------------------------------------------------------------
_marca_sidebar()
st.sidebar.markdown('<div class="sl-nav-label">EXPLORAR</div>', unsafe_allow_html=True)

# Si quedó guardada una sección que ya no existe, se vuelve al inicio.
_MAP_QUERY = {"inicio": INICIO, "vivo": VIVO, "expected": EXPECTED, "nba": NBA, "futbol": FUTBOL, "tenis": TENIS, "diag": DIAGNOSTICO}
_q_sec = str(st.query_params.get("sec", "") or "").lower()
_q_partido = str(st.query_params.get("partido", "") or "").strip()
if _q_sec in _MAP_QUERY:
    st.session_state["seccion"] = _MAP_QUERY[_q_sec]
if _q_partido:
    st.session_state["_abrir_partido_id"] = _q_partido
if _q_sec or _q_partido:
    st.query_params.clear()
if st.session_state.get("seccion") not in SECCIONES:
    st.session_state["seccion"] = INICIO
if st.session_state.get("seccion") == DIAGNOSTICO and not auth.es_admin():
    st.session_state["seccion"] = INICIO

# Navegación por botones nativos (sin radio circle). Cada botón tiene la clase sl-nav-btn
# y sl-nav-btn--active cuando es la sección actual, manejadas en pulido.py.
_ICONS_NAV = {
    INICIO:   "🏠",
    VIVO:     "📡",
    EXPECTED: "🎯",
    NBA:      "🏀",
    FUTBOL:   "⚽",
    TENIS:    "🎾",
}
seccion = st.session_state.get("seccion", INICIO)
_nav_changed = False
for _sec in _SECCIONES_NAV:
    _label = _ETIQUETAS_MENU.get(_sec, _sec)
    _icon  = _ICONS_NAV.get(_sec, "")
    _is_active = (seccion == _sec)
    _btn_key = f"_nav_btn_{_sec}"
    # Render con st.sidebar.markdown para controlar clase CSS; el click se detecta con st.sidebar.button oculto
    _btn_type = "primary" if _is_active else "secondary"
    if st.sidebar.button(
        f"{_icon}  {_label}",
        key=_btn_key,
        use_container_width=True,
        type=_btn_type,
    ):
        st.session_state["seccion"] = _sec
        _nav_changed = True

if _nav_changed:
    st.rerun()
seccion = st.session_state.get("seccion", INICIO)

_pulso_deportivo_sidebar()
alertas.panel()   # alertas de favoritos: se vigilan cada 60 s en todas las secciones
st.sidebar.markdown('<div class="sl-sb-sep"></div>', unsafe_allow_html=True)
planes.insignia_sidebar()   # tarjeta Pro dorada (gratis) o insignia Pro dorada
st.sidebar.markdown('<div class="sl-sb-sep"></div>', unsafe_allow_html=True)
auth.perfil_sidebar()
if auth.es_admin():
    if st.sidebar.button(
        "🛠️ Estado de fuentes" + (" (activo)" if seccion == DIAGNOSTICO else ""),
        key="sb_ajustes_diag",
        use_container_width=True,
    ):
        st.session_state["seccion"] = DIAGNOSTICO
        st.rerun()
st.sidebar.markdown(
    '<div class="sl-sb-foot">'
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#A78BFA" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>'
    '<span><strong>Datos de referencia</strong> actualizados hoy</span>'
    '</div>',
    unsafe_allow_html=True,
)

# Tenis usa los colores de Fútbol (verde), porque diseno.py y efectos.py solo conocen las secciones de secciones.py.
estilo = FUTBOL if seccion == TENIS else (INICIO if seccion == EXPECTED else seccion)
diseno.aplicar_estilos(list(DESCRIPCIONES).index(estilo))
estilos.cargar("deporte")  # capa global «app deportiva» (css/deporte.css o la copia incluida en estilos.py)
efectos.aplicar(estilo)  # colores por deporte + animaciones
pulido.aplicar(estilo)   # identidad visual ScoreLine unificada (no toca las tablas)
movimiento.aplicar(estilo, list(SECCIONES).index(seccion))  # animaciones, interacciones y sonido (va al último)
_auto_abrir_sidebar_escritorio()

# Franja superior estable: PULSO EN VIVO con partidos y horarios reales
try:
    _, _partidos_ticker = inicio._resumen_dia()
except Exception:  # noqa: BLE001
    _partidos_ticker = []
pulido.ticker_superior(_partidos_ticker)
planes.banner_plan_header()

_abrir_pid = st.session_state.pop("_abrir_partido_id", None)
if _abrir_pid:
    _m_click = next((m for m in _partidos_ticker if str(m.get("id")) == str(_abrir_pid)), None)
    if _m_click is not None:
        inicio._mostrar_detalle_partido(_m_click)

# Cada sección apunta a la función que la dibuja.
PAGINAS = {
    INICIO: pagina_inicio,
    VIVO: pagina_vivo,
    EXPECTED: expected.render,
    NBA: nba_panel.render,
    FUTBOL: football.render,
    TENIS: tennis_lineas.render,
    DIAGNOSTICO: diagnostico.pagina_diagnostico,
}

# Si se solicitó abrir el login o no estamos en Inicio, mostrar barra superior arriba; en Inicio va debajo del panel principal.
_modal_abierto = st.session_state.get(auth.MODAL_KEY, False)
if _modal_abierto or seccion != INICIO:
    auth.barra_superior()

# Si un diálogo solicitó abrir el modal Pro, se abre aquí fuera de cualquier otro diálogo.
_motivo_pro = st.session_state.pop("_abrir_modal_pro", None)
if _motivo_pro:
    planes.modal_pro(_motivo_pro)

# Si es administrador, mostrar panel de gestión de clientes al inicio
if auth.es_admin():
    auth.panel_administracion()

_cambio_seccion = st.session_state.get("_ultima_sec") != seccion
st.session_state["_ultima_sec"] = seccion
if _cambio_seccion:
    st.markdown(
        "<style>[data-testid='stMain'] [data-stale='true'] { display: none !important; }</style>",
        unsafe_allow_html=True,
    )

_pg_slug = _ETIQUETAS_MENU.get(seccion, "diag").lower().replace(" ", "_")
with st.container(key=f"sl_pg_{_pg_slug}"):
    PAGINAS[seccion]()

if not _modal_abierto and seccion == INICIO:
    auth.barra_superior()

pulido.barra_inferior_movil(seccion)
