"""Capa de movimiento: animaciones, interacciones, sonidos y efectos de celebración. Va encima de pulido.py.

Uso en app.py (lo ÚLTIMO que se inyecta):
    movimiento.aplicar(estilo, indice_de_seccion)

Qué incluye
  VISUAL    aurora ambiental con el color del deporte · entrada escalonada al cambiar de sección · barra de carga superior
            · barra de progreso de scroll · pulso en el encabezado · subrayado animado en pestañas · «pop» al elegir opciones
  INTERACCIÓN  ondas (ripple) al pulsar · foco de luz que sigue al mouse en tarjetas y métricas · inclinación 3D en tarjetas de
            partido · botón «subir» · panel flotante para silenciar el sonido y pasar al modo ligero
  SONIDO    sintetizado con Web Audio (cero archivos): clic, tictac suave, interruptor, confirmación y fanfarria de gol
  ALERTAS   alertas.py entrega aquí los avisos de favoritos: aviso en pantalla + sonido + notificación del sistema (sin repetir)
  EN VIVO   si cambia un marcador (.hoy-card) → destello, fanfarria, confeti y aviso. Para otros paneles marca el marcador con
            data-pl-score="" y data-pl-id="<id único del partido>" y funcionará igual.

Optimización
  · Todo lo animado usa solo transform y opacity (compositor de la GPU); la aurora usa degradados, no desenfoques costosos.
  · Un único script, instalado una sola vez (no se duplica en cada ejecución de Streamlit), con delegación de eventos, listeners
    pasivos y un solo requestAnimationFrame por movimiento del mouse.
  · Se pausa cuando la pestaña no está visible, se apaga con prefers-reduced-motion y en equipos débiles arranca en modo ligero.
  · Las tablas quedan fuera de TODOS los efectos (ni inclinación, ni ondas, ni sonidos, ni entrada animada).
"""
import streamlit as st
import streamlit.components.v1 as components

_CSS = """
<style>
html { scroll-behavior: smooth; }

/* ============ Aurora ambiental (la crea el script; degradados baratos, sin blur) ============ */
[data-testid="stAppViewContainer"] { position: relative; z-index: 1; }
#pl-aurora { position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; contain: strict; }
#pl-aurora i { position: absolute; width: 64vmax; height: 64vmax; border-radius: 50%; will-change: transform; }
#pl-aurora i:nth-child(1) { left: -22vmax; top: -30vmax;
  background: radial-gradient(circle, color-mix(in srgb, var(--pl-sport, #4F46E5) 26%, transparent), transparent 66%); animation: pl-aurora-a 42s ease-in-out infinite alternate; }
#pl-aurora i:nth-child(2) { right: -26vmax; bottom: -34vmax;
  background: radial-gradient(circle, rgba(79, 70, 229, .20), transparent 66%); animation: pl-aurora-b 52s ease-in-out infinite alternate; }
@keyframes pl-aurora-a { from { transform: translate3d(0, 0, 0) scale(1); } to { transform: translate3d(14vmax, 10vmax, 0) scale(1.18); } }
@keyframes pl-aurora-b { from { transform: translate3d(0, 0, 0) scale(1.1); } to { transform: translate3d(-12vmax, -8vmax, 0) scale(.92); } }
html.pl-pausa #pl-aurora i { animation-play-state: paused; }
html.pl-lite #pl-aurora { display: none; }

/* ============ Entrada escalonada: se repite SOLO al cambiar de sección (el nombre de la animación cambia). Las tablas no se animan. ============ */
@keyframes pl-in-__IDX__ { from { opacity: 0; transform: translate3d(0, 16px, 0); } to { opacity: 1; transform: none; } }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:not(:has(.tabla-wrap)):not(:has([data-testid="stDataFrame"])):not(:has([data-testid="stTable"])):not(:has(.tg-wrap)) {
  animation: pl-in-__IDX__ .55s cubic-bezier(.2, .7, .2, 1) both; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:nth-child(2) { animation-delay: .05s; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:nth-child(3) { animation-delay: .10s; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:nth-child(4) { animation-delay: .15s; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:nth-child(5) { animation-delay: .20s; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:nth-child(n+6) { animation-delay: .25s; }
@keyframes pl-in-lado { from { opacity: 0; transform: translate3d(-12px, 0, 0); } to { opacity: 1; transform: none; } }
[data-testid="stSidebar"] div[role="radiogroup"] label { animation: pl-in-lado .45s cubic-bezier(.2, .7, .2, 1) both; }
[data-testid="stSidebar"] div[role="radiogroup"] label:nth-child(2) { animation-delay: .04s; }
[data-testid="stSidebar"] div[role="radiogroup"] label:nth-child(3) { animation-delay: .08s; }
[data-testid="stSidebar"] div[role="radiogroup"] label:nth-child(4) { animation-delay: .12s; }
[data-testid="stSidebar"] div[role="radiogroup"] label:nth-child(n+5) { animation-delay: .16s; }
html.pl-lite [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"],
html.pl-lite [data-testid="stSidebar"] div[role="radiogroup"] label { animation: none !important; }

/* ============ Barra de carga (arriba) y progreso de scroll (abajo) ============ */
#pl-load { position: fixed; top: 0; left: 0; right: 0; height: 3px; z-index: 1000001; pointer-events: none; opacity: 0; transition: opacity .25s ease; overflow: hidden; }
#pl-load::before { content: ""; position: absolute; top: 0; bottom: 0; left: 0; width: 38%;
  background: linear-gradient(90deg, transparent, var(--pl-acc, #4F46E5), var(--pl-sport, #F26B21), transparent); animation: pl-carga 1.1s ease-in-out infinite; }
html:has([data-test-script-state="running"]) #pl-load { opacity: 1; }
@keyframes pl-carga { from { transform: translate3d(-100%, 0, 0); } to { transform: translate3d(360%, 0, 0); } }
#pl-scroll { position: fixed; left: 0; right: 0; bottom: 0; height: 3px; z-index: 1000001; pointer-events: none; }
#pl-scroll i { display: block; height: 100%; width: 100%; transform-origin: 0 50%; transform: scaleX(0);
  background: linear-gradient(90deg, var(--pl-acc, #4F46E5), var(--pl-sport, #F26B21)); }

/* ============ Encabezado: punto que emite un pulso ============ */
.pl-punto { position: relative; }
.pl-punto::after { content: ""; position: absolute; inset: 0; border-radius: 50%; background: var(--pl-sport); animation: pl-ping 2.4s ease-out infinite; }
@keyframes pl-ping { 0% { transform: scale(1); opacity: .55; } 80%, 100% { transform: scale(3.4); opacity: 0; } }

/* ============ Opciones: «pop» al elegir; pestañas con subrayado que crece ============ */
@keyframes pl-pop { 0% { transform: scale(.94); } 55% { transform: scale(1.04); } 100% { transform: scale(1); } }
div[role="radiogroup"] label:has(input:checked) { animation: pl-pop .32s cubic-bezier(.3, 1.5, .5, 1); }
[data-testid="stMain"] button[data-baseweb="tab"] { position: relative; overflow: hidden; }
[data-testid="stMain"] button[data-baseweb="tab"][aria-selected="true"] { box-shadow: none !important; }
[data-testid="stMain"] button[data-baseweb="tab"]::after { content: ""; position: absolute; left: 12%; right: 12%; bottom: 0; height: 2px; border-radius: 2px;
  background: var(--pl-acc, #4F46E5); transform: scaleX(0); transition: transform .3s cubic-bezier(.2, .8, .2, 1); }
[data-testid="stMain"] button[data-baseweb="tab"][aria-selected="true"]::after { transform: scaleX(1); }
.stButton > button:active, .stDownloadButton > button:active { transform: scale(.96) !important; }
.stButton > button, .stDownloadButton > button, label[data-baseweb="radio"] { position: relative; overflow: hidden; }

/* ============ Onda al pulsar (la crea el script) ============ */
.pl-rip { position: absolute; border-radius: 50%; pointer-events: none; background: currentColor; opacity: .22; transform: scale(0); animation: pl-rip .6s ease-out forwards; }
@keyframes pl-rip { to { transform: scale(1); opacity: 0; } }

/* ============ Foco de luz que sigue al mouse (métricas y tarjetas) ============ */
[data-testid="stMetric"], .tarjeta { --mx: 50%; --my: 50%; }
[data-testid="stMetric"]::before, .tarjeta::before { display: block !important; content: ""; position: absolute; inset: 0; width: auto; height: auto; padding: 0; border-radius: inherit;
  pointer-events: none; opacity: 0; transition: opacity .25s ease; -webkit-mask: none; mask: none;
  background: radial-gradient(280px circle at var(--mx) var(--my), rgba(79, 70, 229, .16), transparent 62%); }
[data-testid="stMetric"]:hover::before, .tarjeta:hover::before { opacity: 1; }
[data-testid="stMetric"] > *, .tarjeta > * { position: relative; }
@keyframes pl-valor { from { opacity: 0; transform: translate3d(0, 8px, 0) scale(.96); } to { opacity: 1; transform: none; } }
[data-testid="stMetricValue"] { animation: pl-valor .55s cubic-bezier(.2, .8, .2, 1) both; }

/* ============ Tarjetas de partido: inclinación 3D (la mueve el script) y celebración de gol ============ */
.hoy-card, .fl, .tarjeta { transform-style: preserve-3d; backface-visibility: hidden; }
@keyframes pl-gol { 0% { box-shadow: 0 0 0 0 rgba(250, 204, 21, .85); } 100% { box-shadow: 0 0 0 26px rgba(250, 204, 21, 0); } }
.hoy-card.pl-gol { animation: pl-gol 1.1s ease-out 2; }
.hoy-marc.ef-flash { border-radius: 12px; }

/* ============ Panel flotante, avisos y confeti ============ */
.pl-dock { position: fixed; right: 16px; bottom: 18px; z-index: 1000002; display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 6px; border-radius: 16px;
  background: rgba(255, 255, 255, .90); backdrop-filter: blur(10px); border: 1px solid var(--pl-linea, #E2E8F0); box-shadow: 0 10px 30px -10px rgba(15, 23, 42, .35);
  animation: pl-in-lado .6s cubic-bezier(.2, .7, .2, 1) 1s both; }
.pl-dock button { all: unset; box-sizing: border-box; width: 38px; height: 38px; display: grid; place-items: center; border-radius: 12px; cursor: pointer; font-size: 1rem; color: #334155;
  transition: background .15s ease, transform .15s ease, opacity .2s ease, box-shadow .15s ease; }
.pl-dock button:hover { background: #EEF0FF; transform: translateY(-2px); color: #4F46E5; }
.pl-dock button:active { transform: scale(.92); }
.pl-dock button:focus-visible { outline: 2px solid var(--pl-acc, #4F46E5); outline-offset: 1px; }
.pl-dock button.off { opacity: .45; filter: grayscale(1); }
.pl-dock button.sl-ai-btn { width: 42px; height: 42px; border-radius: 50%; padding: 0; background: linear-gradient(135deg, #2E1F7A, #4F46E5); box-shadow: 0 4px 14px -2px rgba(79, 70, 229, .55), 0 0 0 2px rgba(94, 234, 212, .55); overflow: hidden; animation: sl-ai-pulse 2.8s ease-in-out infinite; }
@keyframes sl-ai-pulse { 0%, 100% { box-shadow: 0 4px 14px -2px rgba(79,70,229,.55), 0 0 0 2px rgba(94,234,212,.55); } 50% { box-shadow: 0 4px 18px -2px rgba(79,70,229,.8), 0 0 0 4px rgba(94,234,212,.35), 0 0 20px 4px rgba(99,102,241,.25); } }
.pl-dock button.sl-ai-btn:hover { background: linear-gradient(135deg, #3730A3, #6366F1); transform: translateY(-2px) scale(1.05); box-shadow: 0 8px 20px -2px rgba(79, 70, 229, .65), 0 0 0 2.5px #5EEAD4; animation: none; }
.pl-dock button.sl-ai-btn img { width: 100%; height: 100%; object-fit: cover; display: block; border-radius: 50%; }
.pl-dock button.sube { height: 0; width: 38px; opacity: 0; pointer-events: none; overflow: hidden; margin-top: -6px; }
.pl-dock button.sube.ver { height: 36px; opacity: 1; pointer-events: auto; margin-top: 0; }
#pl-toasts { position: fixed; left: 18px; bottom: 18px; z-index: 1000002; display: flex; flex-direction: column; gap: 8px; pointer-events: none; }
.pl-toast { display: flex; align-items: center; gap: .6rem; padding: .7rem 1rem; border-radius: 14px; color: #fff; font-weight: 600; font-size: .9rem; max-width: min(86vw, 380px);
  background: linear-gradient(135deg, #0F172A, #1E1B4B); border: 1px solid rgba(255, 255, 255, .14); box-shadow: 0 16px 36px -12px rgba(15, 23, 42, .6);
  animation: pl-toast-in .4s cubic-bezier(.2, .9, .3, 1.2) both; }
.pl-toast.sale { animation: pl-toast-out .35s ease forwards; }
.pl-toast b { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-variant-numeric: tabular-nums; }
@keyframes pl-toast-in { from { opacity: 0; transform: translate3d(-24px, 0, 0) scale(.95); } to { opacity: 1; transform: none; } }
@keyframes pl-toast-out { to { opacity: 0; transform: translate3d(-24px, 0, 0); } }

/* Aviso enriquecido (cambio de línea y alertas de favoritos): icono, partido, mercado, de → a, variación y barra de tiempo */
.pl-toast { pointer-events: auto; cursor: default; position: relative; overflow: hidden; --acr: 165, 180, 252;
  transition: height .38s cubic-bezier(.4, 0, .2, 1), margin .38s cubic-bezier(.4, 0, .2, 1), padding .38s cubic-bezier(.4, 0, .2, 1),
              border-color .2s ease, box-shadow .25s ease; }
.pl-toast:not(.pl-rica) { padding-right: 2.6rem; }
.pl-toast:hover, .pl-toast:focus-within { border-color: rgba(var(--acr), .55); box-shadow: 0 18px 40px -12px rgba(15, 23, 42, .7), 0 0 0 1px rgba(var(--acr), .25); }
/* Salida: se desliza y se pliega, y los demás avisos bajan suavemente en vez de saltar */
.pl-toast.sale { height: 0 !important; margin-bottom: -8px; padding-top: 0 !important; padding-bottom: 0 !important; border-width: 0; opacity: 0; pointer-events: none; }
/* Cerrar: aparece solo con el mouse encima (o con el foco del teclado); en pantallas táctiles se ve siempre */
.pl-x { position: absolute; top: 8px; right: 8px; z-index: 3; width: 26px; height: 26px; padding: 0; display: grid; place-items: center; border: 0; border-radius: 50%;
  font: inherit; font-size: .78rem; line-height: 1; color: #fff; cursor: pointer; background: rgba(255, 255, 255, .14);
  opacity: 0; transform: scale(.6); transition: opacity .18s ease, transform .22s cubic-bezier(.3, 1.5, .5, 1), background .15s ease; }
.pl-toast:hover .pl-x, .pl-toast:focus-within .pl-x, .pl-x:focus-visible { opacity: 1; transform: scale(1); }
.pl-x:hover { background: rgba(255, 255, 255, .3); } .pl-x:active { transform: scale(.88); }
.pl-x:focus-visible { outline: 2px solid rgb(var(--acr)); outline-offset: 2px; }
.pl-tk em { transition: opacity .15s ease; }
.pl-toast:hover .pl-tk em, .pl-toast:focus-within .pl-tk em { opacity: 0; }
@media (hover: none) { .pl-x { opacity: 1; transform: none; } .pl-toast .pl-tk em { opacity: 0; } }
/* Con el mouse encima el tiempo se detiene: la barra se congela y se atenúa */
.pl-toast.pausa .pl-pb { animation-play-state: paused; opacity: .45; }
.pl-pb { transition: opacity .2s ease; }
.pl-todo { align-self: flex-start; pointer-events: auto; padding: .28rem .8rem; border: 1px solid rgba(255, 255, 255, .16); border-radius: 999px; cursor: pointer;
  font: inherit; font-size: .72rem; font-weight: 700; color: rgba(255, 255, 255, .85); background: rgba(15, 23, 42, .82); backdrop-filter: blur(8px);
  animation: pl-toast-in .35s cubic-bezier(.2, .9, .3, 1.2) both; transition: background .15s ease; }
.pl-todo:hover { background: rgba(79, 70, 229, .9); } .pl-todo[hidden] { display: none; }

/* ---- Avisos de favoritos v2: escudos, foto, chips y explicación ---- */
.pl-v2 { width: min(92vw, 380px); }
.pl-v2.n-out { --acr: 248, 113, 113; } .pl-v2.n-dudoso { --acr: 251, 146, 60; } .pl-v2.n-duda { --acr: 250, 204, 21; }
.pl-v2.n-probable, .pl-v2.n-ok, .pl-v2.sube { --acr: 74, 222, 128; } .pl-v2.baja { --acr: 251, 146, 60; } .pl-v2.n-marcador { --acr: 250, 204, 21; }
.pl-duelo { display: flex; align-items: center; gap: .55rem; margin: .65rem 0 .1rem; }
.pl-eqb { display: flex; flex-direction: column; align-items: center; gap: .22rem; min-width: 56px; padding: .35rem .5rem .3rem; border-radius: 12px; background: rgba(255, 255, 255, .06); }
.pl-eqb b { font-size: .66rem; font-weight: 800; letter-spacing: .1em; color: rgba(255, 255, 255, .85); }
.pl-eqb.fav { background: rgba(var(--acr), .14); box-shadow: inset 0 0 0 1px rgba(var(--acr), .45); }
.pl-eqb.fav b::after { content: " ★"; color: rgb(var(--acr)); }
.pl-esc { width: 42px; height: 42px; object-fit: contain; filter: drop-shadow(0 4px 8px rgba(0, 0, 0, .45)); }
.pl-at { font-style: normal; font-size: .8rem; font-weight: 700; color: rgba(255, 255, 255, .4); }
.pl-jug { display: flex; align-items: center; gap: .8rem; margin: .6rem 0 .1rem; }
.pl-av { position: relative; flex: none; width: 54px; height: 54px; }
.pl-foto { width: 54px; height: 54px; border-radius: 50%; object-fit: cover; object-position: 50% 8%; background: radial-gradient(circle at 50% 28%, #c7d2fe, #6366f1);
  box-shadow: 0 0 0 2px rgba(var(--acr), .85); }
.pl-av .pl-esc { position: absolute; right: -7px; bottom: -5px; width: 26px; height: 26px; padding: 2px; border-radius: 50%; background: #fff; filter: none; box-shadow: 0 2px 6px rgba(0, 0, 0, .45); }
.pl-jn { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-size: 1.05rem; font-weight: 800; line-height: 1.15; }
.pl-js { margin-top: .15rem; font-size: .78rem; color: rgba(255, 255, 255, .62); }
.pl-h { margin-top: .6rem; font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-size: 1.05rem; font-weight: 800; line-height: 1.25; }
.pl-sub { margin-top: .15rem; font-size: .78rem; color: rgba(255, 255, 255, .6); }
.pl-chs { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; margin-top: .6rem; }
.pl-ch { display: inline-flex; align-items: baseline; gap: .35rem; padding: .22rem .6rem; border-radius: 8px; font-size: .76rem; font-weight: 700; font-variant-numeric: tabular-nums;
  color: rgba(255, 255, 255, .92); background: rgba(255, 255, 255, .1); }
.pl-ch i { font-style: normal; font-size: .62rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; opacity: .62; }
.pl-ch.out { color: #fecaca; background: rgba(248, 113, 113, .2); } .pl-ch.dudoso { color: #fed7aa; background: rgba(251, 146, 60, .2); }
.pl-ch.duda { color: #fef08a; background: rgba(250, 204, 21, .18); } .pl-ch.probable, .pl-ch.ok { color: #bbf7d0; background: rgba(74, 222, 128, .18); }
.pl-v2 .pl-tx { margin-top: .45rem; font-size: .8rem; line-height: 1.4; color: rgba(255, 255, 255, .74); }
.pl-v2 .pl-mv:first-of-type { margin-top: .2rem; }

.pl-toast.pl-rica { position: relative; overflow: hidden; align-items: flex-start; gap: .75rem; width: min(86vw, 360px); padding: .8rem .95rem .95rem 1.05rem;
  font-weight: 500; background: linear-gradient(145deg, #12102f, #1e1b4b 72%); --acr: 165, 180, 252; }
.pl-rica.sube { --acr: 74, 222, 128; } .pl-rica.baja { --acr: 251, 146, 60; }
.pl-rica::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: rgb(var(--acr)); }
.pl-ti { flex: none; display: grid; place-items: center; width: 38px; height: 38px; border-radius: 11px; font-size: 1.15rem;
  background: rgba(var(--acr), .16); box-shadow: inset 0 0 0 1px rgba(var(--acr), .38); }
.pl-tb { min-width: 0; flex: 1; }
.pl-tk { display: flex; justify-content: space-between; align-items: center; gap: .6rem; font-size: .62rem; font-weight: 800; letter-spacing: .14em;
  text-transform: uppercase; color: rgb(var(--acr)); }
.pl-tk em { font-style: normal; font-weight: 600; letter-spacing: .04em; color: rgba(255, 255, 255, .45); font-variant-numeric: tabular-nums; }
.pl-tp { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; margin-top: .25rem; font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-size: 1rem; font-weight: 800; }
.pl-tp i { font-style: normal; font-size: .75rem; font-weight: 600; color: rgba(255, 255, 255, .5); }
.pl-eq { padding: .05rem .5rem; border-radius: 7px; background: rgba(255, 255, 255, .1); }
.pl-tp.pl-tt { font-family: inherit; font-size: .88rem; font-weight: 600; line-height: 1.35; display: block; }
.pl-tm { display: flex; flex-wrap: wrap; align-items: baseline; gap: .4rem; margin-top: .55rem; }
.pl-mk { align-self: center; padding: .1rem .5rem; border-radius: 999px; font-size: .64rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
  color: rgba(255, 255, 255, .78); background: rgba(255, 255, 255, .1); }
.pl-de { font-size: .95rem; font-weight: 600; font-variant-numeric: tabular-nums; color: rgba(255, 255, 255, .5); text-decoration: line-through; text-decoration-color: rgba(255, 255, 255, .3); }
.pl-ar { color: rgba(255, 255, 255, .45); }
.pl-toast .pl-a { font-size: 1.5rem; line-height: 1; color: #fff; }
.pl-dl { align-self: center; margin-left: auto; padding: .12rem .55rem; border-radius: 999px; font-size: .72rem; font-weight: 800; font-variant-numeric: tabular-nums;
  color: rgb(var(--acr)); background: rgba(var(--acr), .16); }
.pl-tx { margin-top: .4rem; font-size: .74rem; font-weight: 500; color: rgba(255, 255, 255, .62); }
.pl-mv + .pl-mv { margin-top: .55rem; padding-top: .55rem; border-top: 1px solid rgba(255, 255, 255, .09); }
.pl-mv .pl-tm { margin-top: .5rem; }
.pl-mv + .pl-mv .pl-tm { margin-top: 0; }
.pl-dl.sube { color: #4ade80; background: rgba(74, 222, 128, .16); } .pl-dl.baja { color: #fb923c; background: rgba(251, 146, 60, .16); }
.pl-pb { position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: rgba(var(--acr), .85); transform-origin: left;
  animation: pl-pb var(--ms, 9s) linear forwards; }
@keyframes pl-pb { to { transform: scaleX(0); } }
@media (prefers-reduced-motion: reduce) { .pl-pb { display: none; } .pl-toast { transition: none; } }
.pl-confeti { position: fixed; inset: 0; z-index: 1000003; pointer-events: none; }
@media (max-width: 640px) { .pl-dock { right: 10px; bottom: 12px; } #pl-toasts { left: 10px; bottom: 64px; } }

/* El iframe del script no ocupa espacio */
[data-testid="stElementContainer"]:has(iframe[height="0"]), [data-testid="element-container"]:has(iframe[height="0"]) {
  position: absolute !important; width: 0 !important; height: 0 !important; margin: 0 !important; overflow: hidden !important; }


/* Ganchos invisibles de marcador (football.py) y panel oculto cuando hay un diálogo abierto (p. ej. «Abrir tabla en grande») */
[data-testid="stElementContainer"]:has(.pl-hook), [data-testid="element-container"]:has(.pl-hook) {
  position: absolute !important; width: 0 !important; height: 0 !important; margin: 0 !important; overflow: hidden !important; }
.pl-hook { display: none; }
html:has([role="dialog"]) .pl-dock { opacity: 0; pointer-events: none; transition: opacity .2s ease; }

/* Quien prefiere menos movimiento: sin nada de esto */
@media (prefers-reduced-motion: reduce) {
  #pl-aurora, #pl-load::before, .pl-punto::after, .pl-rip, .pl-confeti { display: none !important; }
  *, *::before, *::after {
    animation-duration: .001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .001ms !important;
  }
}
</style>
"""

_JS = r"""
<script>
(function () {
  const P = window.parent, D = P && P.document, V = 8;
  if (!P || !D) return;
  if (P.__pl && P.__pl.v === V) return;                         // ya instalado: no se duplica en cada ejecución de Streamlit
  if (P.__pl && P.__pl.destroy) { try { P.__pl.destroy(); } catch (e) {} }

  const root = D.documentElement, clean = [], timers = [];
  const on = (t, ev, fn, o) => { t.addEventListener(ev, fn, o); clean.push(() => t.removeEventListener(ev, fn, o)); };
  const store = { get(k, d) { try { const v = P.localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
                  set(k, v) { try { P.localStorage.setItem(k, v); } catch (e) {} } };
  const reduce = P.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fino = P.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const debil = (P.navigator.hardwareConcurrency || 8) <= 2 || (P.navigator.deviceMemory || 8) <= 2;
  const est = { snd: store.get('pl_snd', '1') === '1', fx: store.get('pl_fx', debil ? '0' : '1') === '1' };
  const ligero = () => !est.fx || reduce;
  const aplicarFx = () => root.classList.toggle('pl-lite', ligero());
  aplicarFx();

  // Las tablas quedan fuera de todo efecto
  const NO = '.tabla-wrap, .tabla, .tg-wrap, [data-testid="stDataFrame"], [data-testid="stTable"]';
  const mk = (tag, cls, txt) => { const e = D.createElement(tag); if (cls) e.className = cls; if (txt) e.textContent = txt; return e; };

  // ---------------------------------------------------------------- Sonido (Web Audio, sin archivos)
  let ctx = null, master = null;
  function audio() {
    if (ctx) return ctx;
    const AC = P.AudioContext || P.webkitAudioContext; if (!AC) return null;
    ctx = new AC();
    const comp = ctx.createDynamicsCompressor(); master = ctx.createGain(); master.gain.value = .5;
    master.connect(comp); comp.connect(ctx.destination); return ctx;
  }
  function tono(f0, f1, dur, tipo, vol, retraso) {
    const t = ctx.currentTime + (retraso || 0), o = ctx.createOscillator(), g = ctx.createGain();
    o.type = tipo; o.frequency.setValueAtTime(f0, t); if (f1) o.frequency.exponentialRampToValueAtTime(f1, t + dur);
    g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + .008); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    o.connect(g); g.connect(master); o.start(t); o.stop(t + dur + .03);
  }
  const SND = {
    tick:   () => tono(1900, 1500, .03, 'sine', .035),
    click:  () => { tono(540, 820, .07, 'triangle', .2); tono(1200, 0, .04, 'sine', .05, .01); },
    on:     () => { tono(523, 0, .09, 'sine', .18); tono(784, 0, .13, 'sine', .18, .07); },
    off:    () => { tono(784, 0, .09, 'sine', .16); tono(523, 0, .13, 'sine', .16, .07); },
    ok:     () => { tono(523, 0, .1, 'triangle', .18); tono(659, 0, .1, 'triangle', .18, .07); tono(988, 0, .18, 'triangle', .18, .14); },
    alerta: () => { tono(880, 0, .12, 'sine', .22); tono(1175, 0, .14, 'sine', .22, .12); tono(1760, 0, .32, 'triangle', .16, .26); },
    gol:    () => { [523, 659, 784, 1047].forEach((f, i) => tono(f, 0, .3, 'triangle', .22, i * .09)); tono(1568, 0, .6, 'sine', .12, .4); tono(262, 0, .7, 'sawtooth', .05, 0); }
  };
  function sonar(n) {
    if (!est.snd) return; const c = audio(); if (!c) return;
    if (c.state === 'suspended') c.resume();
    const f = SND[n]; if (f) f();
  }
  on(D, 'pointerdown', () => { if (est.snd) { const c = audio(); if (c && c.state === 'suspended') c.resume(); } }, { passive: true, capture: true });

  // ---------------------------------------------------------------- Clic: sonido + onda
  const CLIC = '.stButton button, [data-testid="stButtonGroup"] button, .stDownloadButton button, [data-baseweb="tab"], label[data-baseweb="radio"], [data-testid="stCheckbox"] label, [data-testid="stToggle"] label, [data-baseweb="select"]';
  const ONDA = '.stButton button, [data-testid="stButtonGroup"] button, .stDownloadButton button, [data-baseweb="tab"], label[data-baseweb="radio"]';
  function onda(el, e) {
    if (ligero()) return;
    const r = el.getBoundingClientRect(), s = Math.max(r.width, r.height) * 2, i = mk('span', 'pl-rip');
    i.style.cssText = `width:${s}px;height:${s}px;left:${e.clientX - r.left - s / 2}px;top:${e.clientY - r.top - s / 2}px`;
    el.appendChild(i); timers.push(setTimeout(() => i.remove(), 650));
  }
  on(D, 'pointerdown', e => {
    const t = e.target; if (!t || !t.closest || t.closest(NO)) return;
    const el = t.closest(CLIC); if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return;
    if (el.matches(ONDA)) onda(el, e);
    if (el.closest('[data-testid="stCheckbox"], [data-testid="stToggle"]')) sonar('on');
    else if (el.matches('[kind="primary"], [data-testid="stBaseButton-primary"]')) sonar('ok');
    else sonar('click');
  }, { passive: true, capture: true });

  // Tictac muy suave al pasar por controles
  const HOVER = '.stButton button, [data-testid="stButtonGroup"] button, [data-baseweb="tab"], label[data-baseweb="radio"]';
  let ultHover = null, ultTick = 0;
  on(D, 'pointerover', e => {
    if (!fino || !est.snd) return;
    const t = e.target; if (!t || !t.closest || t.closest(NO)) return;
    const el = t.closest(HOVER); if (!el || el === ultHover) return;
    ultHover = el; const n = performance.now(); if (n - ultTick < 70) return; ultTick = n; sonar('tick');
  }, { passive: true });

  // ---------------------------------------------------------------- Foco de luz + inclinación 3D (un solo rAF)
  const GLOW = '[data-testid="stMetric"], .tarjeta', TILT = '.hoy-card, .fl, .tarjeta';
  let raf = 0, px = 0, py = 0, pt = null, inclinada = null;
  function soltar() { if (inclinada) { inclinada.style.transform = ''; inclinada.style.willChange = ''; inclinada = null; } }
  function cuadro() {
    raf = 0; const t = pt; if (!t || !t.closest) return;
    if (t.closest(NO)) { soltar(); return; }
    const g = t.closest(GLOW);
    if (g) { const r = g.getBoundingClientRect(); g.style.setProperty('--mx', (px - r.left) + 'px'); g.style.setProperty('--my', (py - r.top) + 'px'); }
    const c = t.closest(TILT);
    if (c !== inclinada) { soltar(); inclinada = c; if (c) c.style.willChange = 'transform'; }
    if (c) {
      const r = c.getBoundingClientRect(), x = (px - r.left) / r.width - .5, y = (py - r.top) / r.height - .5, m = Math.min(6, 2600 / r.width);
      c.style.transform = `perspective(1000px) rotateX(${(-y * m).toFixed(2)}deg) rotateY(${(x * m).toFixed(2)}deg) translateY(-3px)`;
    }
  }
  on(D, 'pointermove', e => {
    if (!fino || ligero()) return;
    px = e.clientX; py = e.clientY; pt = e.target; if (!raf) raf = P.requestAnimationFrame(cuadro);
  }, { passive: true });
  on(root, 'pointerleave', soltar);

  // ---------------------------------------------------------------- Aurora, barras, panel
  const aurora = mk('div'); aurora.id = 'pl-aurora'; aurora.setAttribute('aria-hidden', 'true'); aurora.append(mk('i'), mk('i')); D.body.prepend(aurora);
  const carga = mk('div'); carga.id = 'pl-load'; carga.setAttribute('aria-hidden', 'true'); D.body.appendChild(carga);
  const prog = mk('div'); prog.id = 'pl-scroll'; prog.setAttribute('aria-hidden', 'true'); const barra = mk('i'); prog.appendChild(barra); D.body.appendChild(prog);

  const dock = mk('div', 'pl-dock'); dock.setAttribute('role', 'toolbar'); dock.setAttribute('aria-label', 'Asistente y sonido');
  const bAi = mk('button', 'sl-ai-btn'), bSnd = mk('button'), bUp = mk('button', 'sube');
  [bAi, bSnd, bUp].forEach(b => b.type = 'button');
  bAi.title = 'ScoreLine AI · Analista deportivo'; bAi.setAttribute('aria-label', 'Abrir ScoreLine AI');
  const avSrc = '__ROBOT_AVATAR_URI__';
  if (avSrc) {
    const imgAi = D.createElement('img');
    imgAi.src = avSrc; imgAi.alt = 'ScoreLine AI';
    bAi.appendChild(imgAi);
  } else {
    bAi.textContent = 'AI';
  }
  bAi.onclick = () => {
    sonar('click');
    const trig = D.querySelector('[class*="st-key-sl_ai_open_btn"] button');
    if (trig) trig.click();
  };
  const icoSndOn  = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a9.5 9.5 0 0 1 0 14"/></svg>';
  const icoSndOff = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>';
  bUp.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>';
  bUp.title = 'Volver arriba'; bUp.setAttribute('aria-label', 'Volver arriba');
  function pintarDock() {
    bSnd.innerHTML = est.snd ? icoSndOn : icoSndOff; bSnd.classList.toggle('off', !est.snd);
    bSnd.title = est.snd ? 'Sonido activado (clic para silenciar)' : 'Sonido silenciado (clic para activar)'; bSnd.setAttribute('aria-label', bSnd.title);
  }
  bSnd.onclick = () => { est.snd = !est.snd; store.set('pl_snd', est.snd ? '1' : '0'); pintarDock(); if (est.snd) sonar('on'); };
  dock.append(bAi, bSnd, bUp); D.body.appendChild(dock); pintarDock();

  let scroller = null, rafS = 0;
  const ES_SCROLL = '[data-testid="stMain"], section.main, [data-testid="stAppViewContainer"]';
  function pintarScroll() {
    rafS = 0; const s = scroller || root, max = s.scrollHeight - s.clientHeight, p = max > 0 ? s.scrollTop / max : 0;
    barra.style.transform = `scaleX(${Math.min(1, Math.max(0, p)).toFixed(4)})`; bUp.classList.toggle('ver', s.scrollTop > 500);
  }
  on(D, 'scroll', e => {
    const t = e.target === D ? root : e.target;
    if (t.nodeType === 1 && (t === root || (t.matches && t.matches(ES_SCROLL)))) { scroller = t; if (!rafS) rafS = P.requestAnimationFrame(pintarScroll); }
  }, { passive: true, capture: true });
  bUp.onclick = () => { (scroller || root).scrollTo({ top: 0, behavior: 'smooth' }); sonar('click'); };
  on(D, 'visibilitychange', () => root.classList.toggle('pl-pausa', D.hidden));

  // ---------------------------------------------------------------- Avisos y confeti
  const cont = mk('div'); cont.id = 'pl-toasts'; cont.setAttribute('aria-live', 'polite'); D.body.appendChild(cont);
  const bTodo = mk('button', 'pl-todo', 'Cerrar todo'); bTodo.type = 'button'; bTodo.hidden = true; cont.appendChild(bTodo);
  const activos = () => Array.from(cont.querySelectorAll('.pl-toast:not(.sale)'));
  const refTodo = () => { bTodo.hidden = activos().length < 2; };
  function cerrar(t, rapido) {
    if (!t || !t.isConnected || t.classList.contains('sale')) return;
    t.style.height = t.offsetHeight + 'px'; void t.offsetHeight;          // fija la altura para que los demás avisos bajen suave al irse este
    t.classList.add('sale'); refTodo();
    timers.push(setTimeout(() => { t.remove(); refTodo(); }, rapido ? 60 : 400));
  }
  bTodo.addEventListener('click', () => { activos().forEach(t => cerrar(t)); sonar('tick'); });
  function colocar(t, ms) {                                   // pone un aviso en pantalla: se quita solo, o con la ✕
    ms = ms || 5200;
    while (activos().length >= 4) cerrar(activos()[0], true);
    t.style.setProperty('--ms', ms + 'ms');
    const x = mk('button', 'pl-x', '\u2715'); x.type = 'button'; x.title = 'Cerrar'; x.setAttribute('aria-label', 'Cerrar aviso');
    x.addEventListener('click', e => { e.stopPropagation(); sonar('tick'); cerrar(t); });
    if (!t.querySelector('.pl-pb')) t.append(mk('i', 'pl-pb'));
    t.append(x); cont.appendChild(t); refTodo();
    // El tiempo corre SOLO mientras el mouse (o el foco del teclado) no está encima; al soltarlo sigue por donde iba.
    let resta = ms, ini = performance.now(), h = setTimeout(() => cerrar(t), resta);
    const pausar = () => { if (!h) return; clearTimeout(h); h = 0; resta -= performance.now() - ini; t.classList.add('pausa'); };
    const seguir = () => { if (h || !t.isConnected || t.classList.contains('sale')) return; ini = performance.now(); h = setTimeout(() => cerrar(t), Math.max(1500, resta)); t.classList.remove('pausa'); };
    t.addEventListener('pointerenter', pausar); t.addEventListener('pointerleave', seguir);
    t.addEventListener('focusin', pausar); t.addEventListener('focusout', seguir);
    t.addEventListener('keydown', e => { if (e.key === 'Escape') cerrar(t); });
  }
  function aviso(emoji, partes, ms) {
    const t = mk('div', 'pl-toast'); t.append(mk('span', '', emoji));
    partes.forEach(p => t.append(p.b ? mk('b', '', p.t) : D.createTextNode(p.t)));
    colocar(t, ms);
  }
  function confeti(x, y) {
    if (ligero()) return;
    const cv = mk('canvas', 'pl-confeti'); cv.width = P.innerWidth; cv.height = P.innerHeight; D.body.appendChild(cv);
    const g = cv.getContext('2d'), dep = (P.getComputedStyle(root).getPropertyValue('--pl-sport') || '').trim() || '#F26B21';
    const cs = [dep, '#F5B921', '#4F46E5', '#22C55E', '#EF4444', '#38BDF8'];
    const ps = Array.from({ length: 70 }, () => ({ x, y, vx: (Math.random() - .5) * 10, vy: -Math.random() * 9 - 3, w: 5 + Math.random() * 5, h: 3 + Math.random() * 4,
                                                   r: Math.random() * 6, vr: (Math.random() - .5) * .5, c: cs[Math.random() * cs.length | 0] }));
    let n = 0;
    (function bucle() {
      g.clearRect(0, 0, cv.width, cv.height); n++;
      ps.forEach(p => { p.vy += .28; p.vx *= .99; p.x += p.vx; p.y += p.vy; p.r += p.vr;
        g.save(); g.translate(p.x, p.y); g.rotate(p.r); g.globalAlpha = Math.max(0, 1 - n / 80); g.fillStyle = p.c; g.fillRect(-p.w / 2, -p.h / 2, p.w, p.h); g.restore(); });
      if (n < 80 && cv.isConnected) P.requestAnimationFrame(bucle); else cv.remove();
    })();
  }


  // ---------------------------------------------------------------- Alertas de favoritos (las envía alertas.py)
  let vistas = []; try { vistas = JSON.parse(store.get('pl_alertas', '[]')) || []; } catch (e) { vistas = []; }
  function notificar(a) {
    const N = P.Notification; if (!N || N.permission !== 'granted') return;
    try { const n = new N(a.titulo || 'Aviso', { body: a.cuerpo || a.texto || '', tag: a.id, icon: a.icono || undefined }); n.onclick = () => { P.focus(); n.close(); }; } catch (e) {}
  }
  const hora = () => { const d = new Date(); return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); };
  const NUM = '([+\\u2212\\u2013-]?[0-9]+(?:[.,][0-9]+)?)';       // admite +, -, − (U+2212) y – (U+2013)
  const RE_MOV = new RegExp('^(.+?) +' + NUM + ' *\\u2192 *' + NUM + ' *$');
  const num = s => parseFloat(String(s).replace(/[\u2212\u2013]/g, '-').replace(',', '.'));
  // Un cambio de línea llega como «BOS @ GS: Handicap local +8.5 → +7.5 · Total 210.5 → 209.5» (uno o varios mercados separados
  // por « · »), o con campos partido / mercado / de / a. Devuelve null si no es un cambio de línea.
  function leerLinea(a) {
    let partido, movs = [];
    if (a.de !== undefined && a.a !== undefined) { partido = String(a.partido || ''); movs = [{ mercado: String(a.mercado || 'Línea'), de: String(a.de), a: String(a.a) }]; }
    else {
      if (!(a.tipo === 'linea' || /l[ií]nea/i.test(String(a.titulo || '')))) return null;
      const txt = String(a.texto || ''), i = txt.indexOf(': ');
      if (i < 0) return null;
      partido = txt.slice(0, i);
      txt.slice(i + 2).split(' \u00B7 ').forEach(seg => { const m = RE_MOV.exec(seg.trim()); if (m) movs.push({ mercado: m[1], de: m[2], a: m[3] }); });
    }
    if (!movs.length) return null;
    const pp = partido.split(' @ '), pv = partido.split(' vs ');       // «visita @ local» o «local vs visita»
    const L = { partido, movs, local: '', visita: '' };
    if (pp.length === 2) { L.visita = pp[0]; L.local = pp[1]; } else if (pv.length === 2) { L.local = pv[0]; L.visita = pv[1]; }
    return L;
  }
  function cabecera(titulo) { const c = mk('div', 'pl-tk'); c.append(mk('span', '', titulo), mk('em', '', hora())); return c; }
  function explicar(m, L) {
    const de = num(m.de), x = num(m.a), dn = x - de;
    if (/^total/i.test(m.mercado)) return dn > 0 ? 'El mercado espera más puntos' : 'El mercado espera menos puntos';
    let eq = null;
    if (/local/i.test(m.mercado)) eq = L.local; else if (/visita/i.test(m.mercado)) eq = L.visita;
    else { const t = /[A-Z]{2,5}$/.exec(m.mercado); eq = t && t[0]; }
    if (!eq) return dn > 0 ? 'La línea sube' : 'La línea baja';
    if (de < 0 && x > 0) return eq + ' deja de ser favorito';
    if (de > 0 && x < 0) return eq + ' pasa a ser favorito';
    return dn < 0 ? eq + ' gana terreno en la línea' : eq + ' pierde terreno en la línea';
  }
  function filaMov(m, L) {
    const dn = num(m.a) - num(m.de), sube = dn > 0, w = mk('div', 'pl-mv');
    const etiqueta = m.mercado.replace(/local/i, L.local || 'local').replace(/visita/i, L.visita || 'visita');
    const fila = mk('div', 'pl-tm');
    fila.append(mk('span', 'pl-mk', etiqueta), mk('span', 'pl-de', m.de), mk('span', 'pl-ar', '\u2192'), mk('b', 'pl-a', m.a),
                mk('span', 'pl-dl ' + (sube ? 'sube' : 'baja'), (sube ? '\u25B2 ' : '\u25BC ') + String(+Math.abs(dn).toFixed(2))));
    w.append(fila, mk('div', 'pl-tx', explicar(m, L)));
    return w;
  }
  function tarjetaLinea(L) {
    const sig = L.movs.map(m => Math.sign(num(m.a) - num(m.de))), mismo = sig.every(x => x === sig[0]);
    const t = mk('div', 'pl-toast pl-rica' + (mismo ? (sig[0] > 0 ? ' sube' : ' baja') : '')), cuerpo = mk('div', 'pl-tb');
    const par = mk('div', 'pl-tp');
    if (L.local && L.visita) par.append(mk('span', 'pl-eq', L.partido.indexOf(' @ ') > 0 ? L.visita : L.local), mk('i', '', L.partido.indexOf(' @ ') > 0 ? '@' : 'vs'),
                                         mk('span', 'pl-eq', L.partido.indexOf(' @ ') > 0 ? L.local : L.visita));
    else par.append(D.createTextNode(L.partido));
    cuerpo.append(cabecera('Línea movida'), par);
    L.movs.forEach(m => cuerpo.append(filaMov(m, L)));
    t.append(mk('div', 'pl-ti', mismo ? (sig[0] > 0 ? '\uD83D\uDCC8' : '\uD83D\uDCC9') : '\uD83D\uDCCA'), cuerpo, mk('i', 'pl-pb'));
    return t;
  }
  function tarjetaGenerica(a) {
    const t = mk('div', 'pl-toast pl-rica'), cuerpo = mk('div', 'pl-tb');
    cuerpo.append(cabecera(a.titulo || 'Aviso'), mk('div', 'pl-tp pl-tt', a.texto || ''));
    t.append(mk('div', 'pl-ti', a.emoji || '\uD83D\uDD14'), cuerpo, mk('i', 'pl-pb'));
    return t;
  }
  // Aviso v2 (lo arma alertas.py con todo explicado): escudos del duelo o foto del jugador, titular, chips, cambios de línea y frases.
  const dur = t => Math.min(22000, Math.max(9000, 5500 + (t.textContent || '').length * 55));   // más texto, más tiempo para leerlo
  function img(src, cls, alt) { const i = mk('img', cls); i.alt = alt || ''; i.decoding = 'async'; i.referrerPolicy = 'no-referrer'; i.onerror = () => { i.style.visibility = 'hidden'; }; i.src = src; return i; }
  function cresta(e) {
    const w = mk('div', 'pl-eqb' + (e.fav ? ' fav' : '')); w.title = (e.nombre || e.abrev || '') + (e.fav ? ' (tu favorito)' : '');
    if (e.url) w.append(img(e.url, 'pl-esc', e.abrev)); w.append(mk('b', '', e.abrev || '')); return w;
  }
  function filaMovV2(m) {
    const w = mk('div', 'pl-mv'), f = mk('div', 'pl-tm');
    f.append(mk('span', 'pl-mk', m.etiqueta), mk('span', 'pl-de', m.de), mk('span', 'pl-ar', '\u2192'), mk('b', 'pl-a', m.a),
             mk('span', 'pl-dl ' + (m.sube ? 'sube' : 'baja'), (m.sube ? '\u25B2 ' : '\u25BC ') + m.delta));
    w.append(f, mk('div', 'pl-tx', m.texto)); return w;
  }
  function tarjetaV2(a) {
    const t = mk('div', 'pl-toast pl-rica pl-v2 n-' + (a.nivel || 'info') + (a.nivel === 'sube' || a.nivel === 'baja' ? ' ' + a.nivel : '')), c = mk('div', 'pl-tb');
    t.setAttribute('role', 'status');
    c.append(cabecera((a.emoji ? a.emoji + '  ' : '') + (a.kicker || a.titulo || 'Aviso')));
    if (a.equipos && a.equipos.length) { const d = mk('div', 'pl-duelo'); a.equipos.forEach((e, i) => { if (i) d.append(mk('i', 'pl-at', a.sede || '@')); d.append(cresta(e)); }); c.append(d); }
    if (a.jugador) {
      const j = a.jugador, av = mk('div', 'pl-av'), tx = mk('div');
      if (j.foto) av.append(img(j.foto, 'pl-foto', j.nombre));
      if (j.equipo && j.equipo.url) av.append(img(j.equipo.url, 'pl-esc', j.equipo.abrev));
      tx.append(mk('div', 'pl-jn', j.nombre || ''), mk('div', 'pl-js', j.sub || ''));
      const f = mk('div', 'pl-jug'); f.append(av, tx); c.append(f);
    }
    if (a.titulo2) c.append(mk('div', 'pl-h', a.titulo2));
    if (a.sub) c.append(mk('div', 'pl-sub', a.sub));
    if (a.chips && a.chips.length) {
      const f = mk('div', 'pl-chs');
      a.chips.forEach(x => { const s = mk('span', 'pl-ch' + (x.c ? ' ' + x.c : '')); if (x.k) s.append(mk('i', '', x.k)); s.append(D.createTextNode(x.t)); f.append(s); });
      c.append(f);
    }
    (a.movs || []).forEach(m => c.append(filaMovV2(m)));
    (a.lineas || []).forEach(s => c.append(mk('div', 'pl-tx', s)));
    t.append(c, mk('i', 'pl-pb')); return t;
  }
  function alertas(items) {
    (items || []).forEach(a => {
      if (!a || !a.id || vistas.indexOf(a.id) !== -1) return;       // el navegador recuerda lo que ya mostró: nunca se repite
      vistas.push(a.id);
      const v2 = a.v === 2, L = v2 ? null : leerLinea(a), t = v2 ? tarjetaV2(a) : (L ? tarjetaLinea(L) : tarjetaGenerica(a));
      colocar(t, v2 ? dur(t) : 9000);
      sonar('alerta');
      notificar(L ? { id: a.id, titulo: 'Línea movida' + (L.partido ? ' \u00B7 ' + L.partido : ''),
                      texto: L.movs.map(m => m.mercado.replace(/local/i, L.local || 'local').replace(/visita/i, L.visita || 'visita') + ' ' + m.de + ' \u2192 ' + m.a
                             + ' (' + (num(m.a) > num(m.de) ? '\u25B2 ' : '\u25BC ') + String(+Math.abs(num(m.a) - num(m.de)).toFixed(2)) + ')').join(' \u00B7 ') } : a);
    });
    store.set('pl_alertas', JSON.stringify(vistas.slice(-300)));
  }

  // ---------------------------------------------------------------- Marcadores en vivo: detectar cambios
  const visto = new Map();
  function puntaje(card) { return Array.from(card.querySelectorAll('.hoy-marc > span:not(.sep)')).map(s => s.textContent.trim()).join(' - '); }
  function celebrar(el, nombres, marcador) {
    sonar('gol'); aviso('🏆', [{ t: 'Cambio de marcador: ' }, { t: nombres + '  ' + marcador, b: true }]);
    const r = el.getBoundingClientRect(); confeti(r.left + r.width / 2, r.top + r.height / 2);
    el.classList.remove('pl-gol'); void el.offsetWidth; el.classList.add('pl-gol');
    const m = el.querySelector('.hoy-marc'); if (m) { m.classList.remove('ef-flash'); void m.offsetWidth; m.classList.add('ef-flash'); }
  }
  function revisar() {
    D.querySelectorAll('.hoy-card').forEach(card => {
      const noms = Array.from(card.querySelectorAll('.hoy-nom')).map(n => n.textContent.trim()); if (noms.length < 2) return;
      const clave = noms.join('|'), nuevo = puntaje(card); if (!nuevo) return;
      const antes = visto.get(clave); visto.set(clave, nuevo);
      if (antes !== undefined && antes !== nuevo) celebrar(card, noms.join(' vs '), nuevo);
    });
    D.querySelectorAll('[data-pl-score]').forEach(el => {                      // gancho genérico para otros paneles (fútbol, tenis...)
      const clave = 'x:' + (el.dataset.plId || el.id); const nuevo = el.textContent.trim(); if (!clave || !nuevo) return;
      const antes = visto.get(clave); visto.set(clave, nuevo);
      if (antes !== undefined && antes !== nuevo) celebrar(el, el.dataset.plNombre || 'Marcador', nuevo);
    });
  }
  let pend = 0;
  const mo = new MutationObserver(() => { if (!pend) pend = setTimeout(() => { pend = 0; revisar(); }, 250); });   // solo agenda; el trabajo va con retraso
  mo.observe(D.body, { childList: true, subtree: true });
  timers.push(setTimeout(revisar, 600));

  P.__pl = { v: V, play: sonar, confetti: confeti, toast: aviso, alertas: alertas,
    destroy() { clean.forEach(f => f()); timers.forEach(clearTimeout); mo.disconnect(); soltar();
      [aurora, carga, prog, dock, cont].forEach(n => n.remove()); root.classList.remove('pl-lite', 'pl-pausa'); delete P.__pl; } };
})();
</script>
"""


@st.cache_data(show_spinner=False)
def _robot_avatar_uri() -> str:
    import base64
    import os
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "robot_avatar.png")
    try:
        with open(ruta, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""


def aplicar(seccion=None, indice: int = 0):
    """Inyecta el CSS (en cada ejecución) y el script (una sola vez; el propio script evita duplicarse)."""
    st.markdown(_CSS.replace("__IDX__", str(int(indice))), unsafe_allow_html=True)
    components.html(_JS.replace("__ROBOT_AVATAR_URI__", _robot_avatar_uri()), height=0)
