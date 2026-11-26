"""Capa de diseño «pulido»: identidad visual ScoreLine moderna, limpia y consistente.

Uso en app.py (siempre lo ÚLTIMO que se inyecta antes de movimiento.py):
    pulido.aplicar(estilo)
    pulido.cabecera("NBA", "Equipos y jugadores")
    pulido.ticker_superior()

Principios de diseño
  1. Identidad ScoreLine: índigo profundo (#130A3F) + acento índigo-violeta (#4F46E5).
  2. Superficies claras (#F6F7FB -> #F2F0FA), tarjetas blanco puro con borde sutil (#E5E7EB).
  3. Tipografía Roboto + Roboto Condensed + Roboto Mono con cifras tabulares.
  4. Sidebar siempre accesible: nunca se oculta [data-testid="stToolbar"] y [data-testid="stExpandSidebarButton"]
     permanece visible cuando el menú lateral está contraído.
  5. Mantiene --pl-sport: __SPORT__ para compatibilidad con otros módulos y NO altera las tablas.
"""
import streamlit as st

try:
    import diseno
    _TEMA_INDIGO = diseno._tema_ya_es_indigo()
except Exception:  # noqa: BLE001
    _TEMA_INDIGO = False

try:
    from efectos import TEMAS
except Exception:  # noqa: BLE001
    TEMAS = {}

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@100;400;500;700&family=Roboto+Condensed:wght@100;300;500;600;700&family=Roboto+Mono:wght@500;700&display=swap');

:root {
  /* ── Tokens consolidados ScoreLine (--pl-*): Modo oscuro por defecto (AA >= 4.5:1) ── */
  --pl-bg:        #0D0A26;
  --pl-bg-2:      #130F36;
  --pl-sidebar:   #15103F;
  --pl-surface:   #1A1548;
  --pl-surface-2: #221C5A;
  --pl-ink:       #F8FAFC;   /* contraste ~17:1 sobre #0D0A26 */
  --pl-texto:     #E2E8F0;   /* contraste ~13:1 sobre #1A1548 */
  --pl-suave:     #B8C2D8;   /* contraste ~8.2:1 sobre #1A1548 */
  --pl-linea:     rgba(255, 255, 255, .12);
  --pl-borde:     rgba(196, 181, 253, .22);
  --pl-pista:     #1E1854;

  /* Acentos (AA >= 4.5:1 con texto blanco/oscuro según par) */
  --pl-acc:       #6366F1;
  --pl-acc-osc:   #4338CA;
  --pl-acc-sua:   rgba(167, 139, 250, .18);
  --pl-lavanda:   #C4B5FD;
  --pl-indigo:    #15103F;
  --pl-indigo2:   #2B1B72;

  /* Escala de espaciado 4/8 px */
  --pl-sp-1: 4px;
  --pl-sp-2: 8px;
  --pl-sp-3: 12px;
  --pl-sp-4: 16px;
  --pl-sp-5: 24px;
  --pl-sp-6: 32px;

  /* Radios y sombras */
  --pl-r-sm: 8px;
  --pl-r-md: 12px;
  --pl-r-lg: 16px;
  --pl-sombra:    0 4px 16px -4px rgba(0, 0, 0, .35);
  --pl-sombra-sm: 0 2px 6px rgba(0, 0, 0, .25);

  /* Tipografía unificada (base 15px, metadatos >= 12px, tabular-nums) */
  --pl-font:      'Roboto', system-ui, -apple-system, sans-serif;
  --pl-font-cond: 'Roboto Condensed', 'Roboto', sans-serif;
  --pl-font-mono: 'Roboto Mono', ui-monospace, monospace;
  --pl-fs-base:   15px;
  --pl-fs-meta:   12px;

  /* Compatibilidad con superficies claras actuales (.sl-light / modo claro preparado) */
  --pl-fondo:     #F6F7FB;
  --pl-fondo2:    #F1EFFA;
  --pl-card:      #FFFFFF;

  /* Colores de deporte */
  --pl-sport:     __SPORT__;
  --pl-vivo:      #E11D48;
  --pl-nba:       #EA580C;
  --pl-futbol:    #16A34A;
  --pl-tenis:     #7C3AED;
}

/* Modo claro preparado (AA >= 4.5:1) */
[data-theme="light"], .sl-theme-light {
  --pl-bg:        #F6F7FB;
  --pl-bg-2:      #F1EFFA;
  --pl-surface:   #FFFFFF;
  --pl-surface-2: #F8FAFC;
  --pl-ink:       #111827;   /* contraste 17.7:1 sobre #FFFFFF */
  --pl-texto:     #334155;   /* contraste 10.3:1 sobre #FFFFFF */
  --pl-suave:     #475569;   /* contraste 7.5:1 sobre #FFFFFF */
  --pl-linea:     #E5E7EB;
  --pl-borde:     #D8DCE6;
  --pl-pista:     #EEF0F8;
  --pl-acc:       #4F46E5;   /* contraste 6.3:1 con blanco */
  --pl-acc-osc:   #37247E;
  --pl-acc-sua:   #EEF2FF;
  --pl-sombra:    0 2px 10px -2px rgba(19,10,63,.06), 0 1px 3px rgba(19,10,63,.04);
  --pl-sombra-sm: 0 1px 3px rgba(19,10,63,.05);
}

/* ───────── Ocultar solo branding de Streamlit (NUNCA ocultar stToolbar ni stExpandSidebarButton) ───────── */
#MainMenu, footer,
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
.stDeployButton,
[data-testid="stAppDeployButton"],
div[data-testid="stToolbarActions"],
[data-testid="stMainMenu"],
[data-testid="manage-app-button"],
[data-testid="stEmbedFooter"],
[class*="embedFooter"],
[class*="viewerBadge"],
[class*="profileContainer"],
[class*="profilePreview"],
a[href*="streamlit.io/cloud"],
a[href*="share.streamlit.io"] {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
  pointer-events: none !important;
}
header, [data-testid="stHeader"] {
  background: transparent !important;
  pointer-events: none !important;
  height: 0 !important;
  min-height: 0 !important;
}
[data-testid="stMain"] {
  overflow-x: hidden !important;
}
[data-testid="stMainBlockContainer"] {
  padding-bottom: 56px !important;
}
[data-testid="stToolbar"] {
  background: transparent !important;
  pointer-events: none !important;
}

/* Botón nativo de Streamlit 1.67+ para abrir el sidebar cuando está contraído */
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapsedControl"] {
  pointer-events: auto !important;
  display: inline-flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  z-index: 9999999 !important;
  position: fixed !important;
  top: 12px !important;
  left: 12px !important;
  background: #FFFFFF !important;
  color: #130A3F !important;
  border: 1.5px solid #D5D0EE !important;
  border-radius: 10px !important;
  box-shadow: 0 4px 14px rgba(19,10,63,.16) !important;
  width: 38px !important;
  height: 38px !important;
  align-items: center !important;
  justify-content: center !important;
  cursor: pointer !important;
  transition: transform .15s ease, border-color .15s ease, background .15s ease !important;
}
[data-testid="stExpandSidebarButton"]:hover,
[data-testid="stSidebarCollapsedControl"]:hover {
  background: #F4F2FF !important;
  border-color: #4F46E5 !important;
  transform: scale(1.04) !important;
}
[data-testid="stExpandSidebarButton"] svg,
[data-testid="stSidebarCollapsedControl"] svg {
  fill: #130A3F !important;
  stroke: #130A3F !important;
  color: #130A3F !important;
  width: 20px !important;
  height: 20px !important;
}
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapseButton"] *,
[data-testid="stSidebarHeader"] button,
[data-testid="stSidebarHeader"] button * {
  pointer-events: auto !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
}
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarHeader"] button {
  background: rgba(255,255,255,.12) !important;
  border: 1px solid rgba(255,255,255,.22) !important;
  border-radius: 10px !important;
}
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarHeader"] button svg {
  fill: #FFFFFF !important;
  stroke: #FFFFFF !important;
  color: #FFFFFF !important;
}

/* ───────── Marca de agua "SL" sutil en esquina inferior ───────── */
[data-testid="stMainBlockContainer"]::before,
[data-testid="stAppViewBlockContainer"]::before,
.block-container::before {
  content: "SL";
  position: fixed;
  right: 18px;
  bottom: 14px;
  font-family: 'Roboto Condensed', 'Roboto', sans-serif;
  font-size: clamp(72px, 8vw, 120px);
  font-weight: 300;
  letter-spacing: -0.04em;
  line-height: 1;
  color: #4F46E5;
  opacity: .022;
  pointer-events: none !important;
  user-select: none;
  z-index: -1;
}
@media (prefers-color-scheme: dark) {
  [data-testid="stMainBlockContainer"]::before,
  [data-testid="stAppViewBlockContainer"]::before,
  .block-container::before { opacity: .030; }
}
@media (prefers-reduced-motion: reduce) {
  [data-testid="stMainBlockContainer"]::before,
  [data-testid="stAppViewBlockContainer"]::before,
  .block-container::before { animation: none !important; }
}

/* ───────── Lienzo principal ───────── */
html, body {
  background: var(--pl-fondo) !important;
  background-image: none !important;
  font-family: var(--pl-font) !important;
  font-size: var(--pl-fs-base);
}
.stApp {
  background: linear-gradient(180deg, var(--pl-fondo) 0%, var(--pl-fondo2) 100%) !important;
  --pl-ink: #111827;
  --pl-texto: #334155;
  --pl-suave: #475569;
  --pl-linea: #E5E7EB;
  --pl-borde: #D8DCE6;
  --pl-pista: #EEF0F8;
  --pl-acc: #4F46E5;
  --pl-acc-osc: #37247E;
  --pl-acc-sua: #EEF2FF;
  --pl-sombra: 0 2px 10px -2px rgba(19,10,63,.06), 0 1px 3px rgba(19,10,63,.04);
  --pl-sombra-sm: 0 1px 3px rgba(19,10,63,.05);
}
.stApp::before {
  height: 2px !important;
  background: linear-gradient(90deg, var(--pl-indigo), var(--pl-acc), #7C3AED) !important;
  animation: none !important;
  opacity: 1;
}
[data-testid="stMainBlockContainer"],
[data-testid="stAppViewBlockContainer"],
.block-container {
  max-width: 1440px;
  padding-top: 0 !important;
  padding-left: 1.4rem !important;
  padding-right: 1.4rem !important;
  padding-bottom: 2.25rem !important;
  animation: none !important;
  position: relative;
  z-index: 1;
}
[data-testid="stCaptionContainer"] {
  opacity: 1;
  color: var(--pl-suave);
  font-size: .82rem;
}

/* ───────── Tipografía de títulos ───────── */
[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3 {
  font-family: 'Roboto Condensed', 'Roboto', sans-serif !important;
  text-transform: none !important;
  letter-spacing: -.015em !important;
  color: var(--pl-ink);
  background: none !important;
  -webkit-text-fill-color: currentColor !important;
  border: none !important;
  border-image: none !important;
  padding-left: 0 !important;
  animation: none !important;
}
[data-testid="stMain"] h1 { font-size: 1.85rem !important; font-weight: 700 !important; line-height: 1.2 !important; }
[data-testid="stMain"] h1::after { display: none !important; }
[data-testid="stMain"] h2 { font-size: 1.35rem !important; font-weight: 700 !important; }
[data-testid="stMain"] h3 { font-size: 1.1rem !important; font-weight: 600 !important; }

/* ───────── Sidebar ScoreLine (#15103F continuo) ───────── */
[data-testid="stSidebar"] {
  background: #15103F !important;
  background-color: #15103F !important;
  background-image: none !important;
  border-right: none !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  min-width: 226px;
  max-width: 242px;
}
[data-testid="stSidebar"] > div:first-child {
  background: #15103F !important;
  background-image: none !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
  position: absolute !important;
  top: 6px !important;
  right: 6px !important;
  left: auto !important;
  padding: 0 !important;
  margin: 0 !important;
  min-height: 0 !important;
  height: auto !important;
  width: auto !important;
  z-index: 5 !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
  padding-top: 14px !important;
  margin-top: 0 !important;
  padding-left: .85rem !important;
  padding-right: .85rem !important;
  padding-bottom: 1.1rem !important;
}

/* Logo ScoreLine — más grande + reflejo limpio */
@keyframes sl-logo-gleam {
  0%   { transform: translateX(-140%) skewX(-16deg); }
  100% { transform: translateX(360%) skewX(-16deg); }
}
.sl-brand-wrap {
  margin: 0 0 .7rem;
  padding-bottom: .7rem;
  border-bottom: 1px solid rgba(255,255,255,.1);
}
.sl-brand-card {
  background: transparent !important;
  border-radius: 12px !important;
  padding: 6px 8px 6px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  box-shadow: none !important;
  border: none !important;
  position: relative;
  overflow: hidden;
}
/* Franja de reflejo que cruza el logo cada 4 s */
.sl-brand-card::after {
  content: '';
  position: absolute;
  top: 0; bottom: 0;
  left: 0;
  width: 32%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255,255,255,.45),
    transparent
  );
  animation: sl-logo-gleam 4s cubic-bezier(.4,0,.6,1) infinite;
  animation-delay: 1.5s;
  pointer-events: none;
  z-index: 10;
}
.sl-brand-img {
  width: 100%;
  width: 100%;
  max-width: 100%;
  height: auto;
  display: block;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  filter: none;
  transition: transform .35s ease;
}
.sl-brand-img:hover {
  transform: scale(1.04);
}
.sl-brand-fallback {
  font-family: 'Roboto', sans-serif;
  font-weight: 800;
  font-style: italic;
  font-size: 1.35rem;
  color: #FFFFFF;
  letter-spacing: -.02em;
}
.sl-brand-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  padding-left: 2px;
  font-family: 'Roboto', sans-serif;
  font-size: .62rem;
  font-weight: 700;
  letter-spacing: .09em;
  text-transform: uppercase;
  color: #C4B5FD;
}
.sl-brand-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #A78BFA;
  box-shadow: 0 0 0 2.5px rgba(167,139,250,.22);
  flex-shrink: 0;
}

/* Etiqueta EXPLORAR y menú de navegación */
.sl-nav-label {
  font-family: 'Roboto', sans-serif;
  font-size: .67rem;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: rgba(255,255,255,.46);
  margin: .15rem 0 .4rem .35rem;
}
/* Radio en contenido principal: ocultar siempre el circulito nativo (control segmentado profesional) */
[data-testid="stMain"] [data-testid="stRadio"] label[data-baseweb="radio"] > div:not(:last-of-type),
[data-testid="stMain"] [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child,
[data-testid="stMain"] [data-testid="stRadio"] label[data-baseweb="radio"] > span:first-child,
[data-testid="stMain"] [data-testid="stRadio"] input[type="radio"] {
  display: none !important;
  width: 0 !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
  position: absolute !important;
}
/* ── Bug fix: botones en área principal con texto siempre visible (evita conflicto con sport theme) ── */
body .stApp [data-testid="stMain"] .stButton > button,
body .stApp [data-testid="stMain"] .stButton > button * {
  color: #1E293B !important;
  -webkit-text-fill-color: #1E293B !important;
  background-clip: border-box !important;
  -webkit-background-clip: border-box !important;
}
body .stApp [data-testid="stMain"] .stButton > button {
  background: #FFFFFF !important;
  border: 1px solid #D1D5DB !important;
}
body .stApp [data-testid="stMain"] .stButton > button:hover,
body .stApp [data-testid="stMain"] .stButton > button:hover * {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
body .stApp [data-testid="stMain"] .stButton > button:hover {
  border-color: #6366F1 !important;
  background: #F9FAFB !important;
}
body .stApp [data-testid="stMain"] .stButton > button[data-testid="stBaseButton-primary"],
body .stApp [data-testid="stMain"] .stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #4F46E5, #7C3AED) !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
  border: none !important;
}
body .stApp [data-testid="stMain"] .stButton > button[data-testid="stBaseButton-primary"] *,
body .stApp [data-testid="stMain"] .stButton > button[kind="primary"] * {
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
}
.sl-prob-title {
  font-size: .68rem;
  font-weight: 600;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: .04em;
  margin-bottom: 2px;
}

/* ── Bug fix: Toggle/slider/checkbox en sidebar — contraste visible ── */
[data-testid="stSidebar"] [data-testid="stToggle"] label,
[data-testid="stSidebar"] [data-testid="stToggle"] p,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stSlider p,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
  color: rgba(255,255,255,.88) !important;
  -webkit-text-fill-color: rgba(255,255,255,.88) !important;
}
[data-testid="stSidebar"] [data-testid="stSliderTickBarMin"],
[data-testid="stSidebar"] [data-testid="stSliderTickBarMax"] {
  color: rgba(255,255,255,.65) !important;
}

/* ── Navegación lateral: botones limpios alineados a la izquierda ── */
[data-testid="stSidebar"] .stButton > button {
  background: transparent !important;
  color: rgba(255,255,255,.82) !important;
  -webkit-text-fill-color: rgba(255,255,255,.82) !important;
  border: none !important;
  border-left: 3px solid transparent !important;
  border-radius: 10px !important;
  font-size: .90rem !important;
  font-weight: 500 !important;
  padding: .44rem .80rem !important;
  min-height: 36px !important;
  justify-content: flex-start !important;
  text-align: left !important;
  transition: background .15s ease, color .15s ease !important;
  margin: 0 !important;
  letter-spacing: .01em !important;
  box-shadow: none !important;
}
[data-testid="stSidebar"] .stButton > button > div,
[data-testid="stSidebar"] .stButton > button p {
  text-align: left !important;
  justify-content: flex-start !important;
  width: 100% !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: rgba(255,255,255,.08) !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
  border-left-color: rgba(196,181,253,.35) !important;
}
/* Ítems de navegación activos: fondo morado sólido */
[data-testid="stSidebar"] [class*="st-key-_nav_btn_"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] [class*="st-key-_nav_btn_"] button[kind="primary"] {
  background: #4F46E5 !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
  border: none !important;
  border-left: 3px solid #C4B5FD !important;
  border-radius: 10px !important;
  font-weight: 700 !important;
  font-size: .90rem !important;
  justify-content: flex-start !important;
  text-align: left !important;
  box-shadow: 0 4px 14px rgba(79,70,229,.35) !important;
}
[data-testid="stSidebar"] [class*="st-key-_nav_btn_"] .stButton > button[kind="primary"]:hover {
  background: #4338CA !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
}
/* Ítems de nav inactivos */
[data-testid="stSidebar"] [class*="st-key-_nav_btn_"] .stButton > button[kind="secondary"] {
  background: transparent !important;
  color: rgba(255,255,255,.82) !important;
  -webkit-text-fill-color: rgba(255,255,255,.82) !important;
  border: none !important;
  border-left: 3px solid transparent !important;
  box-shadow: none !important;
}
[data-testid="stSidebar"] [class*="st-key-_nav_btn_"] .stButton > button[kind="secondary"]:hover {
  background: rgba(255,255,255,.08) !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
  border-left-color: rgba(196,181,253,.35) !important;
}
/* Botón dorado CTA "Mejorar a Pro" (key sb_btn_mejorar_pro) */
[data-testid="stSidebar"] .st-key-sb_btn_mejorar_pro .stButton > button,
[data-testid="stSidebar"] .st-key-sb_btn_mejorar_pro button {
  background: linear-gradient(135deg, #F59E0B 0%, #D97706 100%) !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  border: 1px solid #FCD34D !important;
  border-radius: 9px !important;
  font-weight: 700 !important;
  font-size: .85rem !important;
  justify-content: center !important;
  text-align: center !important;
  box-shadow: 0 4px 14px rgba(245,158,11,.28) !important;
  margin-top: 4px !important;
}
[data-testid="stSidebar"] .st-key-sb_btn_mejorar_pro button > div,
[data-testid="stSidebar"] .st-key-sb_btn_mejorar_pro button p {
  text-align: center !important;
  justify-content: center !important;
}
[data-testid="stSidebar"] .st-key-sb_btn_mejorar_pro button:hover {
  background: linear-gradient(135deg, #FBBF24 0%, #EAB308 100%) !important;
  border-color: #FEF08A !important;
  color: #0F172A !important;
  -webkit-text-fill-color: #0F172A !important;
}
/* Foco visible solo para teclado */
[data-testid="stSidebar"] .stButton > button:focus-visible {
  outline: 2px solid #C4B5FD !important;
  outline-offset: 2px !important;
}
[data-testid="stSidebar"] .stButton > button:focus:not(:focus-visible) {
  outline: none !important;
}

/* Bloque SEGUIMIENTO compacto en el sidebar oscuro */
.sl-sb-pulse {
  background: rgba(255,255,255,.04);
  border: 1px solid rgba(255,255,255,.10);
  border-radius: 10px;
  padding: 9px 11px;
  margin: .45rem 0 .55rem;
  box-shadow: none;
}
.sl-sp-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 5px;
}
.sl-sp-kicker {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: 'Roboto', sans-serif;
  font-size: .68rem;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: #DDD6FE;
}
.sl-sp-live {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
  flex-shrink: 0;
  background: rgba(225,29,72,.28);
  color: #FFE4E6;
  border: 1px solid rgba(253,164,175,.38);
  font-family: 'Roboto Mono', monospace;
  font-size: .62rem;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 999px;
  letter-spacing: .04em;
}
.sl-sp-live-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #FB7185;
  animation: livePulse 1.4s infinite;
}
.sl-sp-stats {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 0;
}
.sl-sp-count {
  font-family: 'Roboto', sans-serif;
  font-size: .82rem;
  color: rgba(255,255,255,.88);
  font-variant-numeric: tabular-nums;
}
.sl-sp-count b {
  color: #FFFFFF;
  font-weight: 700;
}
.sl-sp-pct {
  font-family: 'Roboto Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-size: .88rem;
  font-weight: 700;
  color: #C4B5FD;
}
.sl-sp-track {
  width: 100%;
  height: 6px;
  background: rgba(255,255,255,.12);
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 10px;
}
.sl-sp-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #8B5CF6 0%, #C4B5FD 100%);
}
.sl-sp-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.sl-sp-tag {
  font-family: 'Roboto', sans-serif;
  font-size: .59rem;
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: #DDD6FE;
  background: rgba(167,139,250,.14);
  border: 1px solid rgba(167,139,250,.28);
  border-radius: 6px;
  padding: 2px 7px;
}

/* Expander de alertas y controles en sidebar oscuro */
[data-testid="stSidebar"] [data-testid="stExpander"],
[data-testid="stSidebar"] [data-testid="stExpander"] details {
  border-radius: 10px !important;
  border: 1px solid rgba(255,255,255,.10) !important;
  background: rgba(255,255,255,.04) !important;
  box-shadow: none !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary,
[data-testid="stSidebar"] [data-testid="stExpander"] summary *,
[data-testid="stSidebar"] [data-testid="stExpander"] p,
[data-testid="stSidebar"] [data-testid="stExpander"] label,
[data-testid="stSidebar"] [data-testid="stExpander"] span {
  color: rgba(255,255,255,.88) !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] svg {
  fill: rgba(255,255,255,.7) !important;
  color: rgba(255,255,255,.7) !important;
}
.sl-sb-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: .72rem;
  color: rgba(255,255,255,.45);
  margin-top: .75rem;
  padding: 0 2px;
}
.sl-sb-foot strong {
  color: rgba(255,255,255,.78);
  font-weight: 600;
}

/* ───────── Navegación de página y filtros: control segmentado profesional unificado ───────── */
[data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] {
  display: inline-flex !important;
  flex-wrap: wrap !important;
  background: #F1F5F9 !important;
  border: 1px solid #E2E8F0 !important;
  border-radius: 12px !important;
  padding: 4px !important;
  gap: 4px !important;
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, .03) !important;
  width: fit-content !important;
  max-width: 100% !important;
}
[data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] label[data-baseweb="radio"] {
  margin: 0 !important;
  border-radius: 8px !important;
  padding: 6px 14px !important;
  background: transparent !important;
  background-image: none !important;
  border: 1px solid transparent !important;
  box-shadow: none !important;
  transform: none !important;
  transition: background .15s ease, color .15s ease, box-shadow .15s ease !important;
  cursor: pointer !important;
}
[data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] label[data-baseweb="radio"]:hover {
  background: rgba(255, 255, 255, .75) !important;
}
[data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) {
  background: #FFFFFF !important;
  background-image: none !important;
  border: 1px solid #E2E8F0 !important;
  box-shadow: 0 2px 6px -1px rgba(15, 23, 42, .08), 0 1px 2px rgba(15, 23, 42, .04) !important;
}
[data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] label[data-baseweb="radio"] * {
  color: #475569 !important;
  -webkit-text-fill-color: #475569 !important;
  font-size: .85rem !important;
  font-weight: 500 !important;
}
[data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] label[data-baseweb="radio"]:hover * {
  color: #0F172A !important;
  -webkit-text-fill-color: #0F172A !important;
}
[data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) * {
  color: #4338CA !important;
  -webkit-text-fill-color: #4338CA !important;
  font-weight: 700 !important;
}

/* ───────── Pestañas ───────── */
[data-testid="stMain"] [data-baseweb="tab-list"] {
  background: transparent !important;
  border: none !important;
  border-bottom: 1px solid var(--pl-linea) !important;
  border-radius: 0 !important;
  padding: 0 !important;
  gap: 4px;
  width: 100%;
  box-shadow: none !important;
}
[data-testid="stMain"] button[data-baseweb="tab"] {
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: .6rem .95rem !important;
  color: var(--pl-suave);
  font-weight: 600;
  font-family: 'Roboto Condensed', sans-serif;
}
[data-testid="stMain"] button[data-baseweb="tab"] * { color: inherit !important; }
[data-testid="stMain"] button[data-baseweb="tab"]:hover {
  background: rgba(79,70,229,.05) !important;
  color: var(--pl-ink);
}
[data-testid="stMain"] button[data-baseweb="tab"][aria-selected="true"] {
  color: var(--pl-acc) !important;
  box-shadow: inset 0 -2px 0 var(--pl-acc) !important;
}

/* ───────── Botones ───────── */
.stButton > button, .stDownloadButton > button {
  background: #fff !important;
  color: var(--pl-ink);
  border: 1px solid var(--pl-borde) !important;
  border-radius: 9px !important;
  font-weight: 600;
  font-family: 'Roboto', sans-serif;
  box-shadow: var(--pl-sombra-sm);
  transform: none !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  background: #F6F5FE !important;
  border-color: var(--pl-acc) !important;
  color: var(--pl-acc-osc);
  box-shadow: 0 3px 10px rgba(79,70,229,.12) !important;
  transform: none !important;
}
.stButton > button::after, .stDownloadButton > button::after { display: none !important; }
[data-testid="stMain"] [data-testid="stBaseButton-primary"],
[data-testid="stMain"] button[kind="primary"] {
  background: linear-gradient(135deg, #190E4F 0%, #4F46E5 100%) !important;
  color: #fff !important;
  border: 1px solid #37247E !important;
  box-shadow: 0 3px 10px -2px rgba(79,70,229,.35) !important;
}
[data-testid="stMain"] [data-testid="stBaseButton-primary"]:hover,
[data-testid="stMain"] button[kind="primary"]:hover {
  background: linear-gradient(135deg, #130A3F 0%, #4338CA 100%) !important;
  color: #fff !important;
  box-shadow: 0 6px 16px -4px rgba(79,70,229,.45) !important;
}

/* ───────── Entradas y selectores ───────── */
[data-baseweb="select"] > div,
[data-baseweb="input"],
[data-baseweb="base-input"] {
  border-radius: 9px !important;
  border-color: var(--pl-borde) !important;
}
[data-baseweb="select"] > div:hover,
[data-baseweb="input"]:hover { border-color: #A5B0C8 !important; }
[data-baseweb="select"] > div:focus-within,
[data-baseweb="input"]:focus-within,
[data-baseweb="base-input"]:focus-within {
  border-color: var(--pl-acc) !important;
  box-shadow: 0 0 0 3px rgba(79,70,229,.14) !important;
}
[data-testid="stWidgetLabel"] p, label[data-testid="stWidgetLabel"] {
  font-weight: 600;
  font-size: .86rem;
}
[data-baseweb="tag"] {
  background: var(--pl-acc-sua) !important;
  border-radius: 6px !important;
  border: 1px solid rgba(79,70,229,.22) !important;
}
[data-baseweb="tag"] * { color: var(--pl-acc-osc) !important; }
[data-baseweb="slider"], [data-baseweb="checkbox"] { filter: __FILTRO__ !important; }

/* Menú desplegable de selectores (tema oscuro ScoreLine + resalte al bajar con teclas) */
div[data-baseweb="popover"] > div,
div[data-baseweb="popover"] ul[role="listbox"] {
  background: linear-gradient(180deg, #131836 0%, #0B0F20 100%) !important;
  border: 1px solid rgba(139, 92, 246, .45) !important;
  border-radius: 14px !important;
  box-shadow: 0 16px 36px rgba(11, 15, 32, .45) !important;
  color: #E2E8F0 !important;
}
div[data-baseweb="popover"] ul[role="listbox"] li[role="option"] {
  display: flex !important;
  align-items: center !important;
  gap: 8px !important;
  padding: 9px 12px !important;
  margin: 2px 6px !important;
  border-radius: 9px !important;
  border-left: 3px solid transparent !important;
  color: #E2E8F0 !important;
  font-size: .88rem !important;
  background: transparent !important;
  transition: background .12s ease, border-color .12s ease !important;
}
div[data-baseweb="popover"] ul[role="listbox"] li[role="option"][aria-selected="true"],
div[data-baseweb="popover"] ul[role="listbox"] li[role="option"][data-highlighted="true"],
div[data-baseweb="popover"] ul[role="listbox"] li[role="option"]:hover,
div[data-baseweb="popover"] ul[role="listbox"] li[role="option"]:focus {
  background: linear-gradient(90deg, rgba(99, 102, 241, .45), rgba(139, 92, 246, .25)) !important;
  border-left: 3px solid #A855F7 !important;
  color: #FFFFFF !important;
  font-weight: 700 !important;
}
div[data-baseweb="popover"] ul[role="listbox"] li[role="option"][aria-selected="true"]::after,
div[data-baseweb="popover"] ul[role="listbox"] li[role="option"][data-highlighted="true"]::after,
div[data-baseweb="popover"] ul[role="listbox"] li[role="option"]:hover::after {
  content: "↵";
  margin-left: auto;
  color: #C4B5FD;
  font-size: .82rem;
  font-weight: 700;
}
.sl-team-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  margin-bottom: 6px;
  border-radius: 11px;
  background: linear-gradient(135deg, #131836 0%, #1B2148 100%);
  border: 1px solid rgba(139, 92, 246, .38);
  color: #F8FAFC;
  font-size: .84rem;
  font-weight: 700;
}
.sl-team-pill img {
  width: 22px;
  height: 22px;
  object-fit: contain;
  flex-shrink: 0;
}
/* Al hacer clic para escribir en cualquier selectbox, oculta el texto fantasma del equipo anterior */
[data-testid="stMain"] [data-baseweb="select"]:focus-within div:has(> input) > div:not(:has(input)) {
  opacity: 0 !important;
  visibility: hidden !important;
}
[data-testid="stMain"] [data-baseweb="select"]:focus-within input {
  opacity: 1 !important;
  color: #0F172A !important;
  -webkit-text-fill-color: #0F172A !important;
  font-weight: 600 !important;
}

/* ───────── Tarjetas, métricas, avisos ───────── */
[data-testid="stMetric"] {
  background: var(--pl-card) !important;
  border: 1px solid var(--pl-linea) !important;
  border-radius: 12px !important;
  box-shadow: var(--pl-sombra) !important;
  transform: none !important;
}
[data-testid="stMetric"]::before,
[data-testid="stMetric"]::after { display: none !important; }
[data-testid="stMetric"]:hover {
  transform: none !important;
  box-shadow: var(--pl-sombra) !important;
}
[data-testid="stMetric"]:hover [data-testid="stMetricValue"] { transform: none !important; }
[data-testid="stMetricValue"] {
  font-family: 'Roboto Mono', monospace !important;
  font-variant-numeric: tabular-nums;
  font-size: 1.85rem !important;
  font-weight: 700 !important;
  letter-spacing: -.01em !important;
}
[data-testid="stMetricLabel"] {
  text-transform: none !important;
  letter-spacing: 0 !important;
  font-size: .8rem !important;
  color: var(--pl-suave);
}
.tarjeta {
  background: var(--pl-card) !important;
  border-color: var(--pl-linea) !important;
  box-shadow: var(--pl-sombra) !important;
}
.tarjeta:hover { transform: translateY(-2px) !important; border-color: #C7CEE0 !important; }
.tarjeta::before { display: none !important; }
[data-testid="stExpander"] {
  border-radius: 12px !important;
  border: 1px solid var(--pl-linea) !important;
  background: var(--pl-card) !important;
}
[data-testid="stExpander"]:hover { box-shadow: none !important; }
[data-testid="stAlert"] { border-radius: 12px !important; backdrop-filter: none !important; }

/* ───────── Encabezado de subsección (pl-cab) ───────── */
.pl-cab {
  display: flex; align-items: center; gap: .55rem;
  margin: 0 0 .85rem;
  font-size: .72rem; font-weight: 700;
  letter-spacing: .14em; text-transform: uppercase;
  color: var(--pl-suave);
  font-family: 'Roboto Condensed', sans-serif;
}
.pl-punto {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--pl-sport);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--pl-sport) 16%, transparent);
}
.pl-cab-d {
  font-weight: 500; letter-spacing: .02em;
  text-transform: none; font-size: .82rem;
}
.pl-cab-d::before { content: "·"; margin-right: .55rem; opacity: .6; }

/* ───────── Franja superior: PULSO EN VIVO (#15103F unificada con el sidebar) ───────── */
[data-testid="stMain"] [data-testid="stElementContainer"]:has(.top-ticker-bar) {
  margin-top: .55rem !important;
}
.top-ticker-bar {
  background: #15103F;
  border-radius: 14px;
  width: 100%;
  position: relative;
  padding: 8px 16px 7px;
  margin-bottom: .55rem;
  border: 1px solid rgba(167,139,250,.22);
  box-shadow: 0 6px 18px -6px rgba(19,10,63,.22);
  color: #fff;
  overflow: hidden;
  z-index: 20;
  transition: margin-left .2s ease, width .2s ease;
}
body:has([data-testid="stSidebar"][aria-expanded="false"]) .top-ticker-bar {
  margin-left: 44px;
  width: calc(100% - 44px);
}
.ticker-inner {
  max-width: 1392px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 10px;
}
.ticker-badge-live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #E11D48;
  border: none;
  color: #FFFFFF;
  font-family: 'Roboto Condensed', sans-serif;
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .06em;
  padding: 4px 10px;
  border-radius: 7px;
  white-space: nowrap;
  flex-shrink: 0;
}
.ticker-live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #FB7185;
  animation: livePulse 1.4s infinite;
}
.ticker-summary {
  font-family: 'Roboto', sans-serif;
  font-size: .76rem;
  font-weight: 600;
  color: #DDD6FE;
  background: rgba(167,139,250,.14);
  border: 1px solid rgba(167,139,250,.25);
  padding: 5px 11px;
  border-radius: 8px;
  white-space: nowrap;
  flex-shrink: 0;
}
.ticker-viewport {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  -webkit-mask-image: linear-gradient(90deg, transparent 0%, #000 22px, #000 calc(100% - 22px), transparent 100%);
  mask-image: linear-gradient(90deg, transparent 0%, #000 22px, #000 calc(100% - 22px), transparent 100%);
}
.ticker-track {
  display: flex;
  align-items: center;
  gap: 10px;
  width: max-content;
  animation: slTickerScroll 42s linear infinite;
  will-change: transform;
}
.ticker-viewport:hover .ticker-track {
  animation-play-state: paused;
}
@keyframes slTickerScroll {
  0%   { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}
@media (prefers-reduced-motion: reduce) {
  .ticker-track { animation: none; }
}
.ticker-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  background: rgba(255,255,255,.07);
  border: 1px solid rgba(255,255,255,.10);
  border-radius: 7px;
  padding: 4px 10px;
  font-size: .78rem;
  color: #F8FAFC !important;
  text-decoration: none !important;
  cursor: pointer;
  flex-shrink: 0;
  transition: background .15s ease, border-color .15s ease, transform .15s ease;
}
.ticker-chip:hover {
  background: rgba(255,255,255,.16);
  border-color: rgba(196,181,253,.55);
  transform: translateY(-1px);
  color: #FFFFFF !important;
  text-decoration: none !important;
}
.ticker-chip.is-live {
  background: rgba(225,29,72,.16);
  border-color: rgba(251,113,133,.36);
}
.ticker-teams {
  font-family: 'Roboto Condensed', sans-serif;
  font-weight: 700;
  letter-spacing: .01em;
  color: #FFFFFF;
}
.ticker-time {
  font-family: 'Roboto Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-size: .73rem;
  color: #CBD5E1;
}
.ticker-chip.is-live .ticker-time {
  color: #FDA4AF;
  font-weight: 700;
}
.ticker-sport { font-size: .86rem; line-height: 1; }
.ticker-score {
  font-family: 'Roboto Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: #FFFFFF;
  background: rgba(255,255,255,.12);
  padding: 1px 7px;
  border-radius: 6px;
}

/* ───────── Breadcrumb + Barra de acciones ───────── */
.dash-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
  padding: 2px 2px .4rem;
}
.dash-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: 'Roboto', sans-serif;
  font-size: .86rem;
}
.bc-dot-indigo {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #6366F1;
  box-shadow: 0 0 0 3px rgba(99,102,241,.18);
  display: inline-block;
}
.bc-section {
  font-weight: 700;
  color: #111827;
}
.bc-sep {
  color: #CBD5E1;
  font-size: .85rem;
}
.bc-sub {
  color: #64748B;
  font-size: .84rem;
}
.dash-quick-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.dash-act-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 5px 9px;
  font-family: 'Roboto', sans-serif;
  font-size: .82rem;
  font-weight: 500;
  color: #475569;
  cursor: pointer;
  transition: background .15s ease, color .15s ease, border-color .15s ease;
}
.dash-act-btn:hover {
  background: #FFFFFF;
  border-color: #E5E7EB;
  color: #130A3F;
}

/* ───────── Contenedor Hero unificado (SCORELINE) ───────── */
.st-key-sl_hero_box {
  background: linear-gradient(135deg, #FFFFFF 0%, #FFFFFF 60%, #F4F2FF 100%) !important;
  border: 1px solid #E5E7EB !important;
  border-radius: 16px !important;
  padding: 1rem 1.25rem .95rem !important;
  box-shadow: var(--pl-sombra) !important;
  position: relative !important;
  overflow: hidden !important;
  margin-bottom: .65rem !important;
}
.st-key-sl_hero_box::after {
  content: "SL";
  position: absolute;
  top: 6px;
  right: 28px;
  font-family: 'Roboto Condensed', sans-serif;
  font-weight: 800;
  font-size: 6.2rem;
  letter-spacing: -.04em;
  color: rgba(19,10,63,.04);
  pointer-events: none;
  line-height: 1;
  z-index: 0;
}
.st-key-sl_hero_box > div {
  position: relative;
  z-index: 1;
}

.hero-kicker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: 'Roboto', sans-serif;
  font-size: .72rem;
  font-weight: 700;
  color: #4F46E5;
  letter-spacing: .09em;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.hero-title {
  font-family: 'Roboto Condensed', 'Roboto', sans-serif;
  font-size: 2.05rem;
  font-weight: 700;
  color: #111827;
  line-height: 1.15;
  letter-spacing: -.02em;
  margin-bottom: 6px;
}
.hero-desc {
  font-family: 'Roboto', sans-serif;
  font-size: .92rem;
  color: #64748B;
  margin-bottom: 14px;
}

/* 4 Tarjetas de deporte clicables sin botón sobresaliente */
[data-testid="stColumn"]:has(.sp-card) [data-testid="stVerticalBlock"] {
  position: relative !important;
  gap: 0 !important;
}
[data-testid="stColumn"]:has(.sp-card) [data-testid="stElementContainer"]:has(.stButton) {
  position: absolute !important;
  inset: 0 !important;
  z-index: 5 !important;
  margin: 0 !important;
}
[data-testid="stColumn"]:has(.sp-card) .stButton,
[data-testid="stColumn"]:has(.sp-card) .stButton > button {
  width: 100% !important;
  height: 100% !important;
  min-height: 128px !important;
  opacity: 0 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  cursor: pointer !important;
  margin: 0 !important;
  padding: 0 !important;
}
.sp-card {
  background: #FFFFFF;
  border: 1.5px solid #E5E7EB;
  border-radius: 16px;
  padding: 14px 15px 13px;
  position: relative;
  overflow: hidden;
  transition: transform .18s cubic-bezier(.2,.8,.2,1), border-color .18s ease, box-shadow .18s ease;
  min-height: 128px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-shadow: 0 3px 10px -4px rgba(19,10,63,.08);
}
.sp-card--vivo {
  background: linear-gradient(145deg, #FFFFFF 0%, #FFF1F2 100%);
  border-color: #FECDD3;
}
.sp-card--nba {
  background: linear-gradient(145deg, #FFFFFF 0%, #FFF7ED 100%);
  border-color: #FED7AA;
}
.sp-card--futbol {
  background: linear-gradient(145deg, #FFFFFF 0%, #F0FDF4 100%);
  border-color: #BBF7D0;
}
.sp-card--tenis {
  background: linear-gradient(145deg, #FFFFFF 0%, #F5F3FF 100%);
  border-color: #DDD6FE;
}
[data-testid="stColumn"]:has(.sp-card):hover .sp-card {
  transform: translateY(-4px);
}
[data-testid="stColumn"]:has(.sp-card--vivo):hover .sp-card--vivo {
  border-color: #FB7185;
  box-shadow: 0 14px 26px -10px rgba(225,29,72,.28);
}
[data-testid="stColumn"]:has(.sp-card--nba):hover .sp-card--nba {
  border-color: #FB923C;
  box-shadow: 0 14px 26px -10px rgba(234,88,12,.26);
}
[data-testid="stColumn"]:has(.sp-card--futbol):hover .sp-card--futbol {
  border-color: #4ADE80;
  box-shadow: 0 14px 26px -10px rgba(22,163,74,.26);
}
[data-testid="stColumn"]:has(.sp-card--tenis):hover .sp-card--tenis {
  border-color: #A78BFA;
  box-shadow: 0 14px 26px -10px rgba(124,58,237,.26);
}
[data-testid="stColumn"]:has(.sp-card):active .sp-card {
  transform: scale(.98);
}
.sp-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  position: relative;
  z-index: 1;
}
.sp-icon {
  width: 38px; height: 38px;
  border-radius: 11px;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 14px -4px rgba(19,10,63,.22);
}
.sp-icon--vivo   { background: linear-gradient(135deg, #F43F5E 0%, #BE123C 100%); }
.sp-icon--nba    { background: linear-gradient(135deg, #FB923C 0%, #C2410C 100%); }
.sp-icon--futbol { background: linear-gradient(135deg, #22C55E 0%, #15803D 100%); }
.sp-icon--tenis  { background: linear-gradient(135deg, #8B5CF6 0%, #5B21B6 100%); }

.sp-pill {
  font-family: 'Roboto Mono', monospace;
  font-size: .62rem;
  font-weight: 700;
  letter-spacing: .05em;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.sp-pill--vivo   { background: #FFE4E6; color: #BE123C; border: 1px solid #FECDD3; }
.sp-pill--nba    { background: #FFEDD5; color: #C2410C; border: 1px solid #FED7AA; }
.sp-pill--futbol { background: #DCFCE7; color: #15803D; border: 1px solid #BBF7D0; }
.sp-pill--tenis  { background: #EDE9FE; color: #6D28D9; border: 1px solid #DDD6FE; }
.sp-pill-dot {
  width: 5px; height: 5px; border-radius: 50%;
  background: #E11D48;
  animation: livePulse 1.4s infinite;
}

.sp-body {
  position: relative;
  z-index: 1;
}
.sp-nom {
  font-family: 'Roboto Condensed', 'Roboto', sans-serif;
  font-size: 1.15rem;
  font-weight: 700;
  color: #111827;
  margin-bottom: 2px;
  letter-spacing: -.01em;
}
.sp-sub {
  font-family: 'Roboto', sans-serif;
  font-size: .78rem;
  color: #475569;
  line-height: 1.3;
  padding-right: 18px;
}
.sp-wm {
  position: absolute;
  right: -8px;
  bottom: -10px;
  width: 68px;
  height: 68px;
  opacity: .08;
  pointer-events: none;
  z-index: 0;
  transition: transform .22s ease, opacity .22s ease;
}
[data-testid="stColumn"]:has(.sp-card):hover .sp-wm {
  transform: scale(1.08) rotate(-6deg);
  opacity: .14;
}
.sp-arrow {
  position: absolute;
  right: 13px;
  bottom: 11px;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: rgba(255,255,255,.85);
  border: 1px solid rgba(19,10,63,.08);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: .95rem;
  color: #475569;
  font-weight: 700;
  z-index: 1;
  transition: transform .18s ease, background .18s ease, color .18s ease;
}
[data-testid="stColumn"]:has(.sp-card):hover .sp-arrow {
  transform: translateX(3px);
  background: #15103F;
  color: #FFFFFF;
}
  color: #4F46E5;
}

/* Banner inferior dentro de Hero */
.hero-alert-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: rgba(255,255,255,.88);
  border: 1px solid #EAECEF;
  border-radius: 12px;
  padding: 10px 14px;
  font-size: .82rem;
  color: #475569;
  margin-top: 6px;
}
.hab-left {
  display: flex;
  align-items: center;
  gap: 9px;
}
.hab-btn {
  background: #FFFFFF;
  border: 1px solid #D8DCE6;
  border-radius: 8px;
  padding: 5px 12px;
  font-size: .78rem;
  font-weight: 600;
  color: #130A3F;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color .15s ease, background .15s ease;
}
.hab-btn:hover {
  border-color: #4F46E5;
  background: #F4F2FF;
}

/* ───────── 3 Paneles Deportivos Inferiores ───────── */
[data-testid="stHorizontalBlock"]:has(.dash-panel-box) {
  align-items: stretch !important;
}
[data-testid="stHorizontalBlock"]:has(.dash-panel-box) > [data-testid="stColumn"] > div,
[data-testid="stHorizontalBlock"]:has(.dash-panel-box) [data-testid="stVerticalBlock"] {
  height: 100%;
}
.dash-panel-box {
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 16px;
  padding: 16px 18px;
  box-shadow: 0 4px 18px -4px rgba(15, 23, 42, .07), 0 1px 3px rgba(15, 23, 42, .04);
  color: #0F172A;
  min-height: 244px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.dp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.dp-kicker {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: 'Roboto Condensed', sans-serif;
  font-size: .74rem;
  font-weight: 700;
  color: #4F46E5;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.dp-link, .dp-time-tag, .dp-dots {
  font-size: .76rem;
  color: #64748B;
  font-weight: 600;
}
.dp-title {
  font-family: 'Roboto Condensed', 'Roboto', sans-serif;
  font-size: 1.15rem;
  font-weight: 700;
  color: #0F172A;
  margin-bottom: 12px;
}

/* Panel 1: Marcadores */
.dp-match-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dp-match-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 11px;
  border-radius: 10px;
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
}
.dp-tag-live {
  font-family: 'Roboto Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-size: .74rem;
  font-weight: 700;
  color: #E11D48;
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 46px;
}
.dp-live-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #E11D48;
  animation: livePulse 1.4s infinite;
}
.dp-time {
  font-family: 'Roboto Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-size: .74rem;
  font-weight: 700;
  color: #64748B;
  min-width: 46px;
}
.dp-teams {
  flex: 1;
  min-width: 0;
}
.dp-team-line {
  font-family: 'Roboto', sans-serif;
  font-size: .85rem;
  font-weight: 600;
  color: #0F172A;
  line-height: 1.3;
}
.dp-team-line.muted {
  color: #64748B;
  font-weight: 400;
  font-size: .8rem;
}
.dp-score {
  font-family: 'Roboto Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-size: 1.02rem;
  font-weight: 700;
  color: #0F172A;
}
.dp-score.muted {
  color: #94A3B8;
}

/* Panel 2: Partido del día */
.potd-matchup {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  padding: 16px 10px;
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 12px;
  margin-bottom: 12px;
}
.potd-side {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.potd-badge {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Roboto Condensed', sans-serif;
  font-weight: 700;
  font-size: .86rem;
  color: #fff;
  box-shadow: 0 3px 10px -2px rgba(19,10,63,.22);
}
.potd-badge--mc  { background: #4F46E5; }
.potd-badge--nap { background: #0284C7; }
.potd-vs {
  font-size: .75rem;
  font-weight: 700;
  color: #64748B;
  text-transform: uppercase;
}
.potd-name {
  font-family: 'Roboto Condensed', sans-serif;
  font-size: .92rem;
  font-weight: 700;
  color: #0F172A;
}
.potd-sub-prompt {
  font-size: .78rem;
  color: #64748B;
  margin-bottom: 8px;
  text-align: center;
}
.potd-pick-msg {
  font-size: .74rem;
  color: #4F46E5;
  font-weight: 600;
  text-align: center;
  margin-top: 6px;
}

/* Panel 3: Pulso analítico */
.pulse-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
  margin-top: 4px;
}
.pulse-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pulse-text-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: .84rem;
}
.pulse-name {
  color: #475569;
  font-weight: 500;
}
.pulse-val {
  font-family: 'Roboto Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: #0F172A;
}
.pulse-bar-track {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: #EEF2FF;
  overflow: hidden;
}
.pulse-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #4F46E5 0%, #7C3AED 100%);
}

/* ───────── Live badge / pulse ───────── */
.live-dot {
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #E11D48;
  margin-right: 5px;
  animation: livePulse 1.4s infinite;
}
@keyframes livePulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: .5; transform: scale(1.3); }
}

/* ───────── Escudos NBA: selección con halo índigo/violeta ───────── */
[class*="st-key-fe_a_"] button, [class*="st-key-fe_b_"] button {
  border-radius: 10px !important;
  border: 1.5px solid var(--pl-linea) !important;
  transition: all .15s ease !important;
}
[class*="st-key-fe_a_"] button:hover, [class*="st-key-fe_b_"] button:hover {
  border-color: #6366F1 !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 4px 10px rgba(79,70,229,.16) !important;
}
[class*="st-key-fe_a_"] button[kind="primary"], [class*="st-key-fe_b_"] button[kind="primary"],
[class*="st-key-fe_a_"] button[data-testid="stBaseButton-primary"], [class*="st-key-fe_b_"] button[data-testid="stBaseButton-primary"] {
  border: 2px solid #4F46E5 !important;
  box-shadow: 0 0 0 4px rgba(79,70,229,.22) !important;
}

/* ───────── Responsive ───────── */
@media (max-width: 768px) {
  .block-container {
    padding-left: .85rem !important;
    padding-right: .85rem !important;
    padding-top: 3.65rem !important;
    padding-bottom: 7.5rem !important;
  }
  .stButton > button,
  .stDownloadButton > button,
  button[data-baseweb="tab"],
  [data-testid="stSidebar"] div[role="radiogroup"] label {
    min-height: 44px !important;
    min-width: 44px !important;
  }
  [data-testid="stExpandSidebarButton"],
  [data-testid="stSidebarCollapsedControl"] {
    top: 8px !important;
    left: 10px !important;
    width: 38px !important;
    height: 38px !important;
    min-width: 38px !important;
    min-height: 38px !important;
  }
  .sl-mobile-nav {
    display: flex !important;
  }
  .st-key-sl_hero_box {
    padding: 1.1rem 1rem !important;
  }
  .hero-title { font-size: 1.5rem; }
  [data-testid="stHorizontalBlock"]:has(.sp-card) {
    flex-wrap: wrap !important;
    gap: 10px !important;
  }
  [data-testid="stHorizontalBlock"]:has(.sp-card) > [data-testid="stColumn"] {
    flex: 1 1 45% !important;
    min-width: 140px !important;
  }
  [data-testid="stHorizontalBlock"]:not(:has(.sp-card)) {
    flex-wrap: wrap !important;
    gap: .6rem !important;
  }
  [data-testid="stHorizontalBlock"]:not(:has(.sp-card)) > [data-testid="stColumn"] {
    flex: 1 1 100% !important;
    min-width: 100% !important;
  }
  .hero-alert-banner { flex-direction: column; align-items: flex-start; }
  .auth-bar { flex-direction: column !important; align-items: stretch !important; gap: .6rem !important; text-align: center !important; }
  .ticker-summary { display: none; }
  [data-testid="stSidebar"] .sl-sb-pulse,
  [data-testid="stSidebar"] .sl-sb-foot {
    display: none !important;
  }
}

/* ───────── PowerStats-style Player Props & Match Explorer ───────── */
.sl-top-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 2px 0;
}
.sl-top-ico {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%);
  border: 1px solid #C7D2FE;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  color: #4338CA;
  box-shadow: 0 3px 10px -3px rgba(79, 70, 229, .22);
}
.sl-top-title {
  font-family: var(--pl-font-cond);
  font-size: 1.38rem;
  font-weight: 800;
  color: #0F172A;
  line-height: 1.12;
  letter-spacing: -.01em;
}
.sl-top-sub {
  font-size: .81rem;
  color: #64748B;
  margin-top: 2px;
}
[data-testid="stMain"] .st-key-inicio_busqueda [data-testid="InputInstructions"] {
  display: none !important;
}
[data-testid="stMain"] .st-key-inicio_busqueda [data-baseweb="input"],
[data-testid="stMain"] .st-key-inicio_busqueda [data-baseweb="base-input"] {
  background: #FFFFFF !important;
  border: 1.5px solid #E2E8F0 !important;
  border-radius: 14px !important;
  min-height: 44px !important;
  box-shadow: 0 4px 16px -6px rgba(15, 23, 42, .08), 0 1px 2px rgba(15, 23, 42, .03) !important;
  transition: border-color .16s ease, box-shadow .16s ease !important;
}
[data-testid="stMain"] .st-key-inicio_busqueda [data-baseweb="input"]:hover {
  border-color: #CBD5E1 !important;
}
[data-testid="stMain"] .st-key-inicio_busqueda [data-baseweb="input"]:focus-within,
[data-testid="stMain"] .st-key-inicio_busqueda [data-baseweb="base-input"]:focus-within {
  border-color: #4F46E5 !important;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, .14), 0 10px 24px -8px rgba(79, 70, 229, .18) !important;
}
[data-testid="stMain"] .st-key-inicio_busqueda input {
  font-size: .9rem !important;
  font-weight: 500 !important;
  color: #0F172A !important;
  padding-right: 34px !important;
}
[data-testid="stMain"] .st-key-inicio_busqueda input::placeholder {
  color: #94A3B8 !important;
  font-weight: 400 !important;
}
.sl-sec-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 1.15rem 0 .65rem;
}
.sl-sec-title {
  font-family: 'Roboto Condensed', sans-serif;
  font-size: 1.18rem;
  font-weight: 700;
  color: #111827;
  display: flex;
  align-items: center;
  gap: 8px;
}
.sl-sec-sub {
  font-size: .84rem;
  font-weight: 500;
  color: #334155;
}
.sl-live-band {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  background: linear-gradient(90deg, rgba(225,29,72,.08) 0%, rgba(99,102,241,.06) 100%);
  border: 1px solid rgba(225,29,72,.20);
  border-left: 4px solid #E11D48;
  border-radius: 10px;
  padding: 8px 14px;
  margin: .25rem 0 .65rem;
}
.sl-live-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #E11D48;
  color: #FFFFFF;
  font-family: 'Roboto Condensed', sans-serif;
  font-size: .76rem;
  font-weight: 700;
  letter-spacing: .06em;
  padding: 3px 9px;
  border-radius: 6px;
}
.sl-live-meta {
  font-size: .82rem;
  font-weight: 600;
  color: #334155;
  font-variant-numeric: tabular-nums;
}
.sl-player-grid {
  display: flex;
  flex-direction: row;
  gap: 12px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scroll-padding-left: 2px;
  padding: 2px 2px 10px;
  margin-bottom: .75rem;
  scrollbar-width: thin;
  scrollbar-color: #C4B5FD transparent;
}
.sl-player-grid::-webkit-scrollbar { height: 6px; }
.sl-player-grid::-webkit-scrollbar-thumb { background: #C4B5FD; border-radius: 999px; }
.sl-pcard {
  flex: 0 0 296px;
  scroll-snap-align: start;
  background: #FFFFFF;
  border: 1px solid #E6E8F2;
  border-radius: 16px;
  padding: 13px 14px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  min-width: 0;
  height: auto;
  overflow: visible;
  box-shadow: 0 2px 10px -4px rgba(19,10,63,.06);
  transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
}
.sl-pcard-top {
  display: flex;
  align-items: center;
  gap: 11px;
}
.sl-ptrend {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--pl-font);
  font-size: 12px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 999px;
  white-space: nowrap;
  flex-shrink: 0;
}
.sl-ptrend.up   { background: #DCFCE7; color: #166534; border: 1px solid #BBF7D0; }
.sl-ptrend.down { background: #FEE2E2; color: #991B1B; border: 1px solid #FECACA; }
.sl-ptrend.flat { background: #EEF2FF; color: #3730A3; border: 1px solid #C7D2FE; }
.sl-pmeta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: #475569;
  font-variant-numeric: tabular-nums;
}
.sl-pmeta-row b {
  color: #111827;
  font-family: var(--pl-font-mono, 'Roboto Mono', monospace);
  font-size: 13px;
}
.sl-pspark {
  display: flex;
  align-items: flex-end;
  gap: 5px;
  height: 46px;
  padding-top: 4px;
}
.sl-pspark-col {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 3px;
}
.sl-pspark-val {
  font-family: var(--pl-font-mono, 'Roboto Mono', monospace);
  font-size: 10.5px;
  font-weight: 700;
  line-height: 1;
  color: #64748B;
  font-variant-numeric: tabular-nums;
}
.sl-pspark-val.last {
  color: #4F46E5;
}
.sl-pspark-track {
  width: 100%;
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: flex-end;
}
.sl-pspark i {
  width: 100%;
  min-height: 4px;
  border-radius: 4px 4px 2px 2px;
  background: #C7D2FE;
  display: block;
}
.sl-pspark i.last {
  background: #4F46E5;
}
.sl-pcard:hover {
  transform: translateY(-2px);
  border-color: #C4B5FD;
  box-shadow: 0 10px 22px -8px rgba(79,70,229,.16);
}
.sl-pav-wrap {
  position: relative;
  width: 54px;
  height: 54px;
  flex-shrink: 0;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 20%, #F8FAFC 0%, #E0E7FF 55%, #A5B4FC 100%);
  box-shadow: 0 3px 10px -2px rgba(79, 70, 229, .22);
}
.sl-pav-wrap::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: linear-gradient(180deg, rgba(255,255,255,0) 55%, rgba(79,70,229,.16) 100%);
  pointer-events: none;
  z-index: 1;
}
.sl-pav {
  width: 54px;
  height: 54px;
  border-radius: 50%;
  object-fit: cover;
  object-position: 50% 8%;
  border: 2px solid #FFFFFF;
  outline: 1.5px solid #C7D2FE;
  display: block;
}
.sl-pcrest {
  position: absolute;
  right: -3px;
  bottom: -2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  padding: 2px;
  object-fit: contain;
  box-shadow: 0 1px 4px rgba(19,10,63,.15);
  z-index: 2;
}
.sl-pinfo {
  flex: 1;
  min-width: 0;
}
.sl-pkicker {
  font-family: 'Roboto', sans-serif;
  font-size: .64rem;
  font-weight: 700;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: #6D28D9;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sl-pname {
  font-family: 'Roboto Condensed', sans-serif;
  font-size: .98rem;
  font-weight: 700;
  color: #111827;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sl-pline {
  font-size: .82rem;
  font-weight: 700;
  color: #1E293B;
  margin-top: 2px;
}
.sl-pbar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.sl-pbar-track {
  flex: 1;
  height: 6px;
  background: #ECEEF7;
  border-radius: 999px;
  overflow: hidden;
}
.sl-pbar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #6366F1 0%, #8B5CF6 100%);
}
.sl-ppct {
  font-family: 'Roboto Mono', monospace;
  font-size: .76rem;
  font-weight: 700;
  color: #4F46E5;
}
.sl-pbadge {
  flex-shrink: 0;
  background: #ECFDF5;
  color: #047857;
  border: 1px solid #A7F3D0;
  font-family: 'Roboto Mono', monospace;
  font-size: .78rem;
  font-weight: 700;
  padding: 5px 10px;
  border-radius: 10px;
}

/* Match explorer cards (PowerStats style) */
.sl-match-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: .45rem;
  margin-bottom: .75rem;
}
[data-testid="stMain"] div[role="radiogroup"] {
  flex-wrap: wrap !important;
}
@media (max-width: 1100px) {
  .sl-match-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 768px) {
  .sl-match-grid {
    grid-template-columns: 1fr;
  }
  .sl-pcard {
    flex: 0 0 82vw;
  }
}
.sl-mcard {
  background: #FFFFFF;
  border: 1px solid #D8DCE6;
  border-radius: 10px;
  padding: 12px 14px 10px;
  min-width: 0;
  min-height: 158px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  overflow: visible;
  box-shadow: none;
  transition: border-color .15s ease, background .15s ease;
}
.sl-mcard:hover {
  border-color: #94A3B8;
}
.sl-mcard.is-in {
  background: linear-gradient(180deg, #FFF5F7 0%, #FFFFFF 48%) !important;
  border: 1px solid #FECDD3 !important;
  border-left: 3px solid #E11D48 !important;
  box-shadow: 0 4px 16px -4px rgba(225, 29, 72, .10), 0 1px 3px rgba(15, 23, 42, .04) !important;
}
.sl-mcard.is-in .sl-mtop { color: #64748B !important; }
.sl-mcard.is-in .sl-mname { color: #0F172A !important; }
.sl-mcard.is-in .sl-mscore-big { color: #0F172A !important; }
.sl-mcard.is-in .sl-prob-wrap { border-top-color: #E2E8F0 !important; }
.sl-mcard.is-in .sl-prob-labels { color: #334155 !important; }
.sl-mcard.is-in .sl-prob-bar { background: #E2E8F0 !important; }
.sl-mcard.is-in .sl-prob-home { background: #4F46E5 !important; }
.sl-mcard.is-live {
  border-color: #FDA4AF;
  border-left: 3px solid #E11D48;
  background: linear-gradient(180deg, #FFF5F7 0%, #FFFFFF 48%);
}
.sl-mcard.is-pre {
  border-color: #D8DCE6;
  border-left: 3px solid #4F46E5;
}
.sl-mcard.is-post {
  border-color: #E2E8F0;
  background: #F8FAFC;
}
.sl-mcard.is-fav {
  box-shadow: inset 0 0 0 1px #F59E0B;
}
.sl-pcard {
  min-width: 0;
  height: auto;
  overflow: visible;
}
.sl-mscore-big {
  font-family: var(--pl-font-mono, 'Roboto Mono', monospace);
  font-variant-numeric: tabular-nums;
  font-size: 1.42rem;
  font-weight: 700;
  color: #0F172A;
  line-height: 1;
}
.sl-mcard.is-post .sl-mscore-big {
  color: #475569;
  font-size: 1.24rem;
}
.sl-mscore-big.muted {
  color: #64748B;
  font-size: 1rem;
}
.sl-prob-wrap {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px dashed #E2E8F0;
}
.sl-prob-labels {
  display: flex;
  justify-content: space-between;
  font-size: 12.5px;
  font-weight: 700;
  color: #1E293B;
  font-variant-numeric: tabular-nums;
  margin-bottom: 4px;
}
.sl-pre-info {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px dashed #E2E8F0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12.5px;
  font-weight: 600;
  color: #312E81;
  font-variant-numeric: tabular-nums;
}
.sl-pre-info-sub {
  color: #475569;
  font-weight: 500;
}
.sl-prob-bar {
  display: flex;
  height: 5px;
  border-radius: 999px;
  overflow: hidden;
  background: #E2E8F0;
}
.sl-prob-home { background: #4F46E5; }
.sl-prob-away { background: #CBD5E1; }
.sl-skel-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 8px 0;
}
.sl-skel-card {
  height: 118px;
  border-radius: 14px;
  background: linear-gradient(90deg, #EEF0F7 25%, #F7F8FC 50%, #EEF0F7 75%);
  background-size: 200% 100%;
  animation: slSkel 1.4s ease-in-out infinite;
}
@keyframes slSkel {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.sl-gp-row {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 6px 0;
}
.sl-gp {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 700;
  color: #FFFFFF;
}
.sl-gp.g { background: #16A34A; }
.sl-gp.p { background: #DC2626; }
.sl-mtop {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: .75rem;
  font-weight: 700;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: #334155;
  margin-bottom: 8px;
}
.sl-mstate {
  padding: 2px 8px;
  border-radius: 6px;
  font-family: 'Roboto Mono', monospace;
  font-size: .72rem;
  font-weight: 700;
}
.sl-mstate.in   { background: #E11D48; color: #FFFFFF; }
.sl-mstate.pre  { background: #E0E7FF; color: #312E81; }
.sl-mstate.post { background: #E2E8F0; color: #334155; }
.sl-mrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 3px 0;
}
.sl-mteam {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.sl-mlogo {
  width: 22px;
  height: 22px;
  object-fit: contain;
  flex-shrink: 0;
}
.sl-mname {
  font-family: 'Roboto Condensed', sans-serif;
  font-size: .92rem;
  font-weight: 600;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sl-mscore {
  font-family: 'Roboto Mono', monospace;
  font-size: .92rem;
  font-weight: 700;
  color: #130A3F;
}
.dp-team-row {
  display: flex;
  align-items: center;
  gap: 7px;
}
.dp-team-logo {
  width: 18px;
  height: 18px;
  object-fit: contain;
  flex-shrink: 0;
}

/* Barra inferior fija solo para móvil (< 768px) */
.sl-mobile-nav {
  display: none;
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 999990;
  background: #15103F;
  border-top: 1px solid rgba(196,181,253,.22);
  padding: 6px 8px calc(6px + env(safe-area-inset-bottom, 0px));
  justify-content: space-around;
  align-items: center;
  box-shadow: 0 -6px 20px rgba(15,10,40,.28);
}
.sl-mnav-item {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-width: 58px;
  min-height: 44px;
  padding: 4px 10px;
  border-radius: 10px;
  color: rgba(255,255,255,.78) !important;
  text-decoration: none !important;
  font-family: var(--pl-font, 'Roboto', sans-serif);
  font-size: 12px;
  font-weight: 600;
}
.sl-mnav-item.active {
  background: rgba(167,139,250,.22);
  color: #FFFFFF !important;
}
.sl-mnav-item:focus-visible {
  outline: 2px solid #C4B5FD !important;
  outline-offset: 2px !important;
}

/* Micro-animación sutil al cambiar un marcador */
@keyframes slScoreFlash {
  0%   { background: rgba(79,70,229,.22); transform: scale(1.06); }
  100% { background: transparent; transform: scale(1); }
}
.sl-score-flash {
  animation: slScoreFlash 1.2s ease-out 1;
  border-radius: 6px;
  padding: 2px 5px;
}
@media (prefers-reduced-motion: reduce) {
  .sl-score-flash, .sl-skel-card, .live-dot, .sl-sp-live-dot, .ticker-live-dot {
    animation: none !important;
  }
}

/* Tarjeta ScoreLine Pro dorada en el sidebar */
.sl-sb-pro-card {
  background: linear-gradient(135deg, rgba(245,158,11,.24) 0%, rgba(124,58,237,.22) 58%, rgba(21,16,63,.85) 100%);
  border: 1px solid rgba(251,191,36,.42);
  border-radius: 12px;
  padding: 11px 12px 10px;
  margin: .55rem 0 .45rem;
}
.sl-sb-pro-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: 'Roboto Condensed', sans-serif;
  font-size: .92rem;
  font-weight: 700;
  color: #FEF08A;
  margin-bottom: 6px;
}
.sl-sb-pro-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: .76rem;
  color: rgba(255,255,255,.90);
}
.sl-sb-pro-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.sl-sb-pro-dot {
  color: #FBBF24;
  font-weight: 700;
}
.sl-sb-sep {
  height: 1px;
  background: rgba(255,255,255,.10);
  margin: .5rem 0;
}
/* Insignia de plan en sidebar y banner discreto en área principal */
.sl-plan-pill {
  background: rgba(255,255,255,.06);
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 9px;
  padding: 7px 10px;
  margin: .35rem 0 .45rem;
  font-size: 12px;
  font-weight: 600;
  color: #E2E8F0;
}
.sl-plan-pill.is-pro {
  background: linear-gradient(135deg, rgba(245,158,11,.26), rgba(167,139,250,.22));
  border-color: rgba(251,191,36,.52);
  color: #FEF08A;
}
.sl-free-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  background: linear-gradient(90deg, #FFFBEB 0%, #EEF2FF 100%);
  border: 1px solid #FDE68A;
  color: #1E1B4B;
  border-radius: 9px;
  padding: 7px 12px;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: .55rem;
}
.sl-gold-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
  flex-shrink: 0;
  background: linear-gradient(135deg, #F59E0B 0%, #D97706 100%);
  color: #FFFFFF;
  font-size: 10.5px;
  font-weight: 800;
  padding: 2px 7px;
  border-radius: 999px;
  letter-spacing: .04em;
  text-transform: uppercase;
  box-shadow: 0 1px 3px rgba(217, 119, 6, .28);
}
/* Bloque Pro desenfocado (el contenido real nunca se envía en modo gratis) */
.sl-pro-box {
  background: #FFFDF7;
  border: 1px solid #FDE68A;
  border-radius: 10px;
  padding: 10px 12px;
  margin: 6px 0;
}
.sl-pro-box-title {
  font-size: 12.5px;
  font-weight: 700;
  color: #1E293B;
  margin-bottom: 5px;
}
.sl-pro-locked {
  position: relative;
  border-radius: 999px;
  padding: 4px 12px;
  background: linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 100%);
  border: 1px solid #FDE68A;
  overflow: hidden;
  min-height: 28px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 1px 4px rgba(217, 119, 6, .10);
}
.sl-pro-blur {
  filter: blur(6px);
  -webkit-user-select: none;
  user-select: none;
  pointer-events: none;
  font-size: 11.5px;
  font-weight: 700;
  color: #334155;
  white-space: nowrap;
}
.sl-pro-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 10px;
  white-space: nowrap;
  font-size: 11px;
  font-weight: 700;
  color: #92400E;
  background: rgba(255, 251, 235, .86);
  backdrop-filter: blur(2px);
}
.sl-pro-open {
  font-size: 12.5px;
  color: #1E293B;
}
.sl-pro-tag {
  font-weight: 700;
  color: #B45309;
}

/* ───────── Top Expected & Rachas (inspirado en PowerStats) ───────── */
.sl-exp-hero {
  background: linear-gradient(135deg, #EEF2FF 0%, #F5F3FF 60%, #EDE9FE 100%);
  color: #1E1B4B;
  border: 1px solid #C7D2FE;
  border-radius: 16px;
  padding: 18px 22px;
  margin-bottom: 14px;
  box-shadow: 0 4px 18px -6px rgba(79,70,229,.15), 0 1px 3px rgba(79,70,229,.06);
}
.sl-exp-hero-badge {
  display: inline-block;
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .08em;
  color: #4338CA;
  background: rgba(79,70,229,.10);
  border: 1px solid #C7D2FE;
  padding: 3px 10px;
  border-radius: 999px;
  margin-bottom: 6px;
}
.sl-exp-hero-title {
  margin: 0 0 4px 0 !important;
  color: #1E1B4B !important;
  -webkit-text-fill-color: #1E1B4B !important;
  font-size: 1.45rem !important;
  font-weight: 800 !important;
}
.sl-exp-hero-sub {
  margin: 0;
  color: #4338CA;
  font-size: .9rem;
}
.sl-exp-card {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 16px;
  padding: 16px 18px;
  margin-bottom: 12px;
  box-shadow: 0 4px 18px -6px rgba(15,23,42,.07), 0 1px 3px rgba(15,23,42,.03);
  color: #0F172A;
  transition: border-color .16s ease, box-shadow .16s ease;
}
.sl-exp-card:hover {
  border-color: #C7D2FE;
  box-shadow: 0 10px 24px -8px rgba(79,70,229,.12);
}
.sl-exp-rank {
  min-width: 28px;
  height: 28px;
  border-radius: 9px;
  background: #FFFBEB;
  color: #B45309;
  border: 1px solid #FDE68A;
  font-weight: 800;
  font-size: .84rem;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}
.sl-exp-body { flex: 1; min-width: 0; }
.sl-exp-match {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  color: #0F172A;
  font-size: .98rem;
}
.sl-exp-vs { color: #94A3B8; font-weight: 500; }
.sl-exp-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 5px 0 10px;
  font-size: .78rem;
  color: #64748B;
}
.sl-exp-badge-ok {
  background: #ECFDF5;
  color: #047857;
  border: 1px solid #A7F3D0;
  font-weight: 700;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: .75rem;
}
.sl-exp-plist { display: flex; flex-direction: column; gap: 8px; }
.sl-exp-prow {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 13px;
  border-radius: 12px;
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
}
.sl-exp-av {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  object-position: 50% 10%;
  background: radial-gradient(circle at 50% 25%, #F8FAFC, #E0E7FF);
  flex-shrink: 0;
  border: 1.5px solid #C7D2FE;
}
.sl-exp-pinfo { flex: 1; min-width: 0; }
.sl-exp-pcat {
  font-size: .71rem;
  font-weight: 700;
  color: #4338CA;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.sl-exp-pline {
  font-size: .9rem;
  font-weight: 700;
  color: #0F172A;
}
.sl-exp-preal { font-weight: 500; color: #64748B; font-size: .8rem; }
.sl-exp-pprob {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: .8rem;
  font-weight: 700;
  color: #334155;
}
.sl-exp-bar {
  width: 58px;
  height: 6px;
  border-radius: 999px;
  background: #E2E8F0;
  overflow: hidden;
}
.sl-exp-bar span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #34D399, #10B981);
  border-radius: 999px;
}
.sl-exp-odds {
  background: #ECFDF5;
  color: #047857;
  border: 1px solid #A7F3D0;
  font-weight: 800;
  font-size: .88rem;
  padding: 5px 13px;
  border-radius: 10px;
  font-family: var(--pl-font-mono);
  white-space: nowrap;
  box-shadow: 0 1px 4px rgba(16, 185, 129, .10);
}
.sl-exp-lockbox {
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 16px;
  padding: 22px 20px;
  text-align: center;
  margin-bottom: 14px;
  color: #0F172A;
  box-shadow: 0 4px 18px -6px rgba(15,23,42,.06);
}
.sl-exp-lock-ico {
  width: 48px;
  height: 48px;
  margin: 0 auto 10px;
  border-radius: 50%;
  background: #FFFBEB;
  border: 1px solid #FDE68A;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4rem;
}
.sl-exp-lockbox h4 { margin: 0 0 6px; color: #0F172A; font-weight: 800; }
.sl-exp-lockbox p { margin: 0 auto; max-width: 480px; color: #64748B; font-size: .9rem; }
.sl-racha-card {
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 14px;
  padding: 14px 16px;
  margin-bottom: 10px;
  color: #0F172A;
  box-shadow: 0 3px 14px -6px rgba(15,23,42,.06);
}
.sl-racha-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.sl-racha-pill {
  background: #FFF7ED;
  color: #C2410C;
  border: 1px solid #FED7AA;
  font-size: .74rem;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 999px;
}
.sl-list-head {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr) 136px 72px;
  gap: 12px;
  padding: 6px 14px;
  margin-bottom: 4px;
  font-size: .71rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: #64748B;
}
.sl-list-row {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr) 136px 72px;
  align-items: center;
  gap: 12px;
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 12px;
  padding: 9px 14px;
  margin-bottom: 6px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, .03);
}
.sl-list-time {
  font-size: .78rem;
  font-weight: 700;
  color: #334155;
  font-family: var(--pl-font-mono);
  white-space: nowrap;
}
.sl-list-time.is-live { color: #E11D48; }
.sl-list-time.is-post { color: #64748B; }
.sl-list-teams { min-width: 0; display: flex; flex-direction: column; gap: 4px; font-size: .88rem; color: #0F172A; }
.sl-list-teams > div { display: flex; align-items: center; gap: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sl-list-liga {
  font-size: .72rem;
  font-weight: 600;
  color: #475569;
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  padding: 3px 8px;
  border-radius: 999px;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sl-list-scores { font-weight: 800; font-family: var(--pl-font-mono); color: #0F172A; text-align: right; font-size: .86rem; }
.sl-list-lock { font-size: .76rem; font-weight: 700; color: #4F46E5; background: #EEF2FF; padding: 3px 8px; border-radius: 8px; }
@media (max-width: 720px) {
  .sl-list-head { display: none; }
  .sl-list-row { grid-template-columns: 96px minmax(0, 1fr) 54px; }
  .sl-list-liga { display: none; }
}

/* ───────── Spinner / carga y formularios delicados ───────── */
[data-testid="stSpinnerIcon"] { display: block !important; }
[data-testid="stSpinner"]::before,
[data-testid="stStatusWidget"]::before { content: none !important; }
[data-testid="InputInstructions"] { display: none !important; }
[data-testid="stForm"] {
  background: #FFFFFF !important;
  border: 1px solid #E2E8F0 !important;
  border-radius: 14px !important;
  padding: 18px 20px !important;
  box-shadow: 0 4px 18px -8px rgba(15, 23, 42, .06) !important;
}
</style>
"""


def aplicar(seccion=None):
    """Inyecta la capa de diseño. `seccion` solo decide el color de detalle (el del deporte)."""
    sport = TEMAS.get(seccion, {}).get("ac", "#4F46E5")
    filtro = "none" if _TEMA_INDIGO else "hue-rotate(244deg) saturate(.92)"
    st.markdown(_CSS.replace("__SPORT__", sport).replace("__FILTRO__", filtro), unsafe_allow_html=True)


def cabecera(titulo: str, detalle: str = ""):
    """Encabezado discreto de página: punto con el color del deporte + nombre en versalitas."""
    extra = f'<span class="pl-cab-d">{detalle}</span>' if detalle else ""
    st.markdown(f'<div class="pl-cab"><span class="pl-punto"></span><span>{titulo}</span>{extra}</div>', unsafe_allow_html=True)


def ticker_superior(partidos=None):
    """Franja superior PULSO EN VIVO: partidos activos, horarios y marcadores reales en español."""
    from html import escape as _esc

    items = list(partidos or [])[:6]
    en_vivo = sum(1 for m in (partidos or []) if m.get("state") == "in")
    total = len(partidos or [])

    if not items:
        chips_html = (
            '<div class="ticker-chip"><span class="ticker-sport">🏀</span>'
            '<span class="ticker-teams">NBA</span><span class="ticker-time">Hoy</span></div>'
            '<div class="ticker-chip"><span class="ticker-sport">⚽</span>'
            '<span class="ticker-teams">Fútbol</span><span class="ticker-time">Ligas activas</span></div>'
            '<div class="ticker-chip"><span class="ticker-sport">🎾</span>'
            '<span class="ticker-teams">Tenis</span><span class="ticker-time">ATP / WTA</span></div>'
        )
        resumen = "Actualizado hoy"
    else:
        chips = []
        for m in items:
            icono = "🏀" if "NBA" in str(m.get("deporte", "")) else "⚽"
            h_ab = (m["home"].get("abrev") or m["home"]["nombre"][:3]).upper()
            a_ab = (m["away"].get("abrev") or m["away"]["nombre"][:3]).upper()
            estado = m.get("state", "pre")
            cls = "ticker-chip is-live" if estado == "in" else "ticker-chip"
            if estado == "in":
                marc = f'<span class="ticker-score">{_esc(m["home"]["score"])}-{_esc(m["away"]["score"])}</span>'
                hora_html = '<span class="ticker-time">EN VIVO</span>'
            elif estado == "post":
                marc = f'<span class="ticker-score">{_esc(m["home"]["score"])}-{_esc(m["away"]["score"])}</span>'
                hora_html = '<span class="ticker-time">Fin</span>'
            else:
                marc = ""
                hora_raw = str(m.get("hora") or "Hoy").strip()
                hora_html = f'<span class="ticker-time">{_esc(hora_raw)}</span>'
            mid = _esc(str(m.get("id") or ""))
            tag_open = f'<a class="{cls}" href="?partido={mid}" target="_self" title="Ver estadísticas en vivo y alineación">' if mid else f'<div class="{cls}">'
            tag_close = '</a>' if mid else '</div>'
            chips.append(
                f'{tag_open}'
                f'<span class="ticker-sport">{icono}</span>'
                f'<span class="ticker-teams">{_esc(h_ab)} vs {_esc(a_ab)}</span>'
                f'{marc}{hora_html}'
                f'{tag_close}'
            )
        chips_html = "".join(chips)
        resumen = f"{en_vivo} en vivo · {total} hoy" if en_vivo else f"{total} partidos hoy"

    # Duplicar los chips para lograr un carrusel continuo sin saltos (y pausa al pasar el cursor)
    track_html = f"{chips_html}{chips_html}"
    st.markdown(
        f'<div class="top-ticker-bar" role="region" aria-label="Pulso en vivo de partidos"><div class="ticker-inner">'
        f'<div class="ticker-badge-live" aria-live="polite"><span class="ticker-live-dot"></span>PULSO EN VIVO</div>'
        f'<div class="ticker-viewport"><div class="ticker-track">{track_html}</div></div>'
        f'<div class="ticker-summary">{_esc(resumen)}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def barra_inferior_movil(seccion_actual: str):
    """Barra inferior fija en móvil (<768px) con 4 accesos rápidos y objetivos táctiles >=44px."""
    items = [
        ("inicio", "🏠", "Inicio"),
        ("vivo", "🔴", "En vivo"),
        ("nba", "🏀", "NBA"),
        ("futbol", "⚽", "Fútbol"),
    ]
    links = []
    for clave, ico, nom in items:
        activo = (
            (clave == "inicio" and "Inicio" in seccion_actual)
            or (clave == "vivo" and "vivo" in seccion_actual.lower())
            or (clave == "nba" and "NBA" in seccion_actual)
            or (clave == "futbol" and "Fútbol" in seccion_actual)
        )
        cls = "sl-mnav-item active" if activo else "sl-mnav-item"
        links.append(
            f'<a class="{cls}" href="?sec={clave}" target="_self" aria-label="Ir a {nom}">'
            f'<span aria-hidden="true">{ico}</span><span>{nom}</span></a>'
        )
    st.markdown(
        f'<nav class="sl-mobile-nav" role="navigation" aria-label="Navegación móvil">{"".join(links)}</nav>',
        unsafe_allow_html=True,
    )
