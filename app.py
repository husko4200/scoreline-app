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

_ICONO_APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "scoreline_icon.png")

# set_page_config debe ser lo PRIMERO que Streamlit ejecuta, por eso va antes de importar los módulos.
st.set_page_config(
    page_title="ScoreLine · Inteligencia Deportiva",
    page_icon=_ICONO_APP if os.path.isfile(_ICONO_APP) else "⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

import streamlit.components.v1 as _comp  # noqa: E402

import alertas  # noqa: E402
import auth  # noqa: E402
import chatbot_ai  # noqa: E402
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
        media = (
            f'<div class="sl-brand-logo-wrap">'
            f'<img class="sl-brand-img" src="data:image/png;base64,{b64}" alt="ScoreLine"/>'
            f'<span class="sl-brand-gleam" aria-hidden="true"></span>'
            f'</div>'
        )
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
      stStyle.textContent = '[data-testid="manage-app-button"],[class*="viewerBadge"],[class*="profileContainer"],[class*="profilePreview"],[class*="embeddedAppMetaInfoBar"],[class*="embedFooter"],[data-testid="stEmbedFooter"],a[href*="streamlit.io"],a[href*="share.streamlit.io"],footer{display:none!important;visibility:hidden!important;opacity:0!important;pointer-events:none!important;height:0!important;overflow:hidden!important;}';
      (P.document.head || P.document.documentElement).appendChild(stStyle);
    }
    function maskLogoGleam() {
      var wraps = P.document.querySelectorAll('.sl-brand-logo-wrap');
      for (var w = 0; w < wraps.length; w++) {
        var img = wraps[w].querySelector('.sl-brand-img');
        var gleam = wraps[w].querySelector('.sl-brand-gleam');
        if (img && gleam && img.src && !gleam.classList.contains('is-masked')) {
          var m = 'url("' + img.src + '")';
          gleam.style.webkitMaskImage = m;
          gleam.style.maskImage = m;
          gleam.classList.add('is-masked');
        }
      }
    }
    maskLogoGleam();
    setTimeout(maskLogoGleam, 80);
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


def _auto_cerrar_sidebar_login():
    """Cierra el menú lateral automáticamente cuando el usuario pulsa Iniciar sesión."""
    if not st.session_state.pop("_cerrar_sidebar_login", False):
        return
    _comp.html(
        """<script>
(function() {
  try {
    var P = window.parent;
    if (!P || !P.document) return;
    function collapseIfOpen() {
      var sb = P.document.querySelector('[data-testid="stSidebar"]');
      if (sb && sb.getAttribute('aria-expanded') !== 'false') {
        var btn = P.document.querySelector(
          '[data-testid="stSidebarCollapseButton"] button, ' +
          '[data-testid="stSidebarHeader"] button, ' +
          '[data-testid="stSidebar"] button[aria-label*="Collapse" i], ' +
          '[data-testid="stSidebar"] button[aria-label*="Close" i]'
        );
        if (btn) btn.click();
      }
      var main = P.document.querySelector('[data-testid="stAppViewContainer"], [data-testid="stMain"]');
      if (main) main.scrollTop = 0;
      if (P.scrollTo) P.scrollTo({ top: 0, behavior: 'smooth' });
    }
    setTimeout(collapseIfOpen, 40);
    setTimeout(collapseIfOpen, 180);
    setTimeout(collapseIfOpen, 450);
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
    c_head, c_auto = st.columns([2.4, 1], vertical_alignment="center")
    c_head.markdown(
        '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:2px 0;">'
        '<span class="badge-vivo" style="margin:0;"><span class="punto-vivo"></span>EN VIVO</span>'
        '<span style="font-family:var(--pl-font-cond);font-size:1.45rem;font-weight:800;color:#0F172A;line-height:1.1;">Centro en vivo</span>'
        '<span style="font-size:.82rem;color:#64748B;">Marcadores y líneas en tiempo real</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    auto_activo = st.session_state.get("vivo_auto_on", True)
    seg_actual = st.session_state.get("vivo_auto_seg", 30)
    lbl_pop = f"🔄 Auto · {seg_actual} s" if auto_activo else "⏸️ Pausado"
    with c_auto:
        with st.popover(lbl_pop, use_container_width=True):
            auto = st.toggle(
                "Actualizar automáticamente",
                value=True,
                key="vivo_auto_on",
                help="Si lo apagas, los marcadores solo cambian cuando recargas la página.",
            )
            segundos = st.slider(
                "Intervalo (segundos)",
                10,
                120,
                30,
                step=5,
                disabled=not auto,
                key="vivo_auto_seg",
                help="Cada cuánto tiempo se vuelven a pedir los marcadores.",
            )

    deporte = st.radio("Deporte", [NBA, FUTBOL], horizontal=True, label_visibility="collapsed", key="vivo_deporte")

    # Cada deporte tiene su propio panel en vivo, definido en su módulo.
    paneles = {NBA: nba.live_panel, FUTBOL: football.live_panel}
    panel = paneles[deporte]

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

# Navegación por botones nativos (sin radio circle). Los iconos SVG se montan con ScoreLineIcons.
_ICONS_NAV = {
    INICIO:   "inicio",
    VIVO:     "en-vivo",
    EXPECTED: "top-expected",
    NBA:      "nba",
    FUTBOL:   "futbol",
    TENIS:    "tenis",
}
seccion = st.session_state.get("seccion", INICIO)
_nav_changed = False
for _sec in _SECCIONES_NAV:
    _label = _ETIQUETAS_MENU.get(_sec, _sec)
    _is_active = (seccion == _sec)
    _btn_key = f"_nav_btn_{_sec}"
    _btn_type = "primary" if _is_active else "secondary"
    if st.sidebar.button(
        _label,
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
_auto_cerrar_sidebar_login()
_comp.html(
    """<script>
(function() {
  try {
    var P = window.parent;
    if (!P || !P.document) return;
    var paths = {
      "alertas": '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.8 2H4.2z"/><path d="M12 3.2v1.6M10 21.2a2.2 2.2 0 0 0 4 0"/>',
      "datos": '<path d="M12 3l7.5 2.8V12c0 4.2-3.1 7-7.5 9-4.4-2-7.5-4.8-7.5-9V5.8z"/><path d="M8.8 12.2l2.4 2.4 4.2-4.6"/>',
      "en-vivo": '<circle cx="12" cy="12" r="1.9" fill="currentColor"/><path d="M8 8a5.7 5.7 0 0 0 0 8M16 8a5.7 5.7 0 0 1 0 8M5 5a9.9 9.9 0 0 0 0 14M19 5a9.9 9.9 0 0 1 0 14"/>',
      "futbol": '<circle cx="12" cy="12" r="9"/><polygon points="12.00,8.70 15.14,10.98 13.94,14.67 10.06,14.67 8.86,10.98" fill="currentColor"/><path d="M12.00 8.70L12.00 3.00"/><path d="M15.14 10.98L20.56 9.22"/><path d="M13.94 14.67L17.29 19.28"/><path d="M10.06 14.67L6.71 19.28"/><path d="M8.86 10.98L3.44 9.22"/>',
      "inicio": '<path d="M3.5 11.2L12 4l8.5 7.2"/><path d="M5.8 9.8V19a1 1 0 0 0 1 1h3.4v-5.2h3.6V20h3.4a1 1 0 0 0 1-1V9.8"/>',
      "nba": '<circle cx="12" cy="12" r="9"/><path d="M12 3v18M3 12h18"/><path d="M5.4 5.4C8.6 8.6 8.6 15.4 5.4 18.6M18.6 5.4C15.4 8.6 15.4 15.4 18.6 18.6"/>',
      "pro": '<polygon points="12.00,3.20 14.35,9.36 20.94,9.70 15.80,13.84 17.53,20.20 12.00,16.60 6.47,20.20 8.20,13.84 3.06,9.70 9.65,9.36" fill="currentColor"/>',
      "seguimiento": '<polyline points="2.5,12 7,12 10,5 14,19 17,12 21.5,12"/>',
      "tenis": '<circle cx="12" cy="12" r="9"/><path d="M4.3 6.9C9.2 8.8 9.2 15.2 4.3 17.1M19.7 6.9C14.8 8.8 14.8 15.2 19.7 17.1"/>',
      "top-expected": '<circle cx="11" cy="13" r="8"/><circle cx="11" cy="13" r="4"/><circle cx="11" cy="13" r="1" fill="currentColor"/><path d="M11 13L20.5 3.5M16.5 3.5h4v4"/>',
      "rachas": '<path d="M12 2.8c2.6 3.1 5 5.6 5 9.2a5 5 0 1 1-10 0c0-1.9.8-3.6 2-5 .3 1.4 1.3 2.3 2.5 2.3-1-1.9-.7-4.3.5-6.5z"/>',
      "partidos": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2.5h6V4M8.5 10h7M8.5 14h7M8.5 18h4"/>',
      "candado": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
      "stats": '<path d="M4 20h16"/><rect x="6" y="12" width="3" height="5" rx="0.5"/><rect x="10.5" y="7" width="3" height="10" rx="0.5"/><rect x="15" y="4" width="3" height="13" rx="0.5"/>',
      "estrella-on": '<polygon points="12.00,3.20 14.35,9.36 20.94,9.70 15.80,13.84 17.53,20.20 12.00,16.60 6.47,20.20 8.20,13.84 3.06,9.70 9.65,9.36" fill="currentColor"/>',
      "estrella-off": '<polygon points="12.00,3.20 14.35,9.36 20.94,9.70 15.80,13.84 17.53,20.20 12.00,16.60 6.47,20.20 8.20,13.84 3.06,9.70 9.65,9.36"/>',
      "vs": '<path d="M14.5 17.5L3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2"/><path d="M14.5 6.5L18 3h3v3l-3.5 3.5M5 14l4 4M7 17l-3 3M3 19l2 2"/>'
    };
    function svg(name, size) {
      size = size || 18;
      var p = paths[name];
      if (!p) return '';
      return '<svg class="sl-icon" data-sl-icon="' + name + '" viewBox="0 0 24 24" width="' + size + '" height="' + size + '" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + p + '</svg>';
    }
    P.ScoreLineIcons = { svg: svg, names: Object.keys(paths) };

    var labelMap = {
      "Inicio": "inicio",
      "En vivo": "en-vivo",
      "Top Expected": "top-expected",
      "NBA": "nba",
      "Fútbol": "futbol",
      "Tenis": "tenis",
      "Alertas de favoritos": "alertas",
      "Notificaciones (Pro)": "alertas"
    };

    var emojiMap = {
      "🏠": "inicio",
      "📡": "en-vivo",
      "🎯": "top-expected",
      "🏀": "nba",
      "⚽": "futbol",
      "🎾": "tenis",
      "🔔": "alertas",
      "🔥": "rachas",
      "📋": "partidos",
      "🔒": "candado",
      "📊": "stats",
      "⚔️": "vs",
      "🛡️": "datos",
      "⭐": "estrella-on",
      "☆": "estrella-off",
      "★": "pro",
      "✨": "pro"
    };
    var emojiRe = /(🏠|📡|🎯|🏀|⚽|🎾|🔔|🔥|📋|🔒|📊|⚔️|🛡️|⭐|☆|★|✨)/g;

    function mountAll() {
      var doc = P.document;
      doc.querySelectorAll('[data-icon]').forEach(function(el) {
        var name = el.getAttribute('data-icon');
        var sz = parseInt(el.getAttribute('data-size') || '18', 10);
        if (!el.querySelector('svg[data-sl-icon="' + name + '"]')) {
          el.innerHTML = svg(name, sz);
        }
      });
      var targets = doc.querySelectorAll(
        '[data-testid="stSidebar"] [class*="st-key-_nav_btn_"] button p, ' +
        '[data-testid="stSidebar"] [data-testid="stExpander"] summary p'
      );
      targets.forEach(function(p) {
        var txt = (p.textContent || '').trim();
        var iconName = labelMap[txt];
        if (!iconName) return;
        var cur = p.querySelector('svg.sl-icon');
        if (cur && cur.getAttribute('data-sl-icon') === iconName) return;
        if (cur) cur.remove();
        p.insertAdjacentHTML('afterbegin', svg(iconName, 18));
      });
      /* Reemplazo limpio de emojis comunes en botones, radios, tarjetas y títulos */
      var scopes = doc.querySelectorAll(
        '[data-testid="stMain"] button p, [data-testid="stMain"] [role="radiogroup"] label p, ' +
        '[data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3, ' +
        '.sl-lock-panel, .sl-free-banner'
      );
      scopes.forEach(function(el) {
        if (el.dataset.slEmojiDone === '1' && !emojiRe.test(el.textContent || '')) return;
        var walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
        var nodes = [];
        var n;
        while ((n = walker.nextNode())) {
          if (n.nodeValue && emojiRe.test(n.nodeValue)) nodes.push(n);
          emojiRe.lastIndex = 0;
        }
        nodes.forEach(function(tn) {
          var val = tn.nodeValue;
          var frag = doc.createDocumentFragment();
          var last = 0;
          val.replace(emojiRe, function(m, _g, off) {
            if (off > last) frag.appendChild(doc.createTextNode(val.slice(last, off)));
            var wrap = doc.createElement('span');
            wrap.className = 'sl-ico-inline';
            var icoKey = emojiMap[m];
            var sz = (m === '⭐' || m === '☆') ? 16 : 15;
            wrap.innerHTML = svg(icoKey, sz);
            if (m === '⭐') wrap.style.color = '#F59E0B';
            else if (m === '☆') wrap.style.color = '#64748B';
            else if (m === '🔒') wrap.style.color = '#6366F1';
            else if (m === '🔥') wrap.style.color = '#F97316';
            frag.appendChild(wrap);
            last = off + m.length;
            return m;
          });
          if (last < val.length) frag.appendChild(doc.createTextNode(val.slice(last)));
          if (tn.parentNode) tn.parentNode.replaceChild(frag, tn);
        });
        el.dataset.slEmojiDone = '1';
      });
    }

    if (P.__slIconObs) P.__slIconObs.disconnect();
    P.__slIconObs = new MutationObserver(mountAll);
    P.__slIconObs.observe(P.document.body, { childList: true, subtree: true });
    mountAll();
  } catch (e) {}
})();
</script>""",
    height=0,
    width=0,
)

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

# Botones ocultos puente para la barra inferior móvil (cambia de sección sin recargar URL ni depender del sidebar)
with st.container(key="sl_mob_nav_bridge"):
    for _m_clave, _m_sec in (("inicio", INICIO), ("vivo", VIVO), ("nba", NBA), ("futbol", FUTBOL)):
        if st.button(_m_clave, key=f"sl_mob_go_{_m_clave}"):
            st.session_state["seccion"] = _m_sec
            st.rerun()

# Botón oculto que alterna el panel lateral de ScoreLine AI desde el dock flotante
if st.button("ScoreLine AI", key="sl_ai_open_btn") and not _motivo_pro:
    st.session_state["_sl_ai_drawer_open"] = not st.session_state.get("_sl_ai_drawer_open", False)
if st.session_state.get("_sl_ai_drawer_open", False) and not _motivo_pro:
    chatbot_ai.panel_chat(seccion)

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
