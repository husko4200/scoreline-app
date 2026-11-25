"""Carga de hojas de estilo: el CSS de las vistas vive en la carpeta css/.

    estilos.cargar("hoy")          # inyecta tokens.css + hoy.css (la paleta compartida va siempre primero)
    estilos.css("escudos")         # solo el texto, para quien necesita componerlo (p. ej. con reglas dinámicas)

Si existe css/<nombre>.css se usa ese archivo (así puedes editarlo). Si no existe, se usa la copia
incluida en este módulo (DEFAULTS), de modo que la app funciona aunque falte la carpeta css/.
Si una hoja no existe en ningún lado, simplemente se omite (nunca muestra avisos ni errores).
"""
from pathlib import Path

import streamlit as st

CARPETA = Path(__file__).resolve().parent / "css"

# Tipografía unificada ScoreLine (Roboto + Roboto Condensed + Roboto Mono).
FUENTES = "@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&family=Roboto+Condensed:wght@500;600;700&family=Roboto+Mono:wght@500;700&display=swap');"

DEFAULTS: dict[str, str] = {
    "tokens": """/* Alias de compatibilidad hacia los tokens consolidados --pl-* de pulido.py */
:root {
  --indigo: var(--pl-acc, #4f46e5);
  --violeta: var(--pl-tenis, #7c3aed);
  --oro: #c9a227;
  --tinta: var(--pl-ink, #0f172a);
  --vivo: var(--pl-vivo, #ef4444);
  --ok: var(--pl-futbol, #16a34a);
  --aviso: #d97706;
  --cancha: var(--pl-bg, #0b1020);
  --cancha-2: var(--pl-sidebar, #15103f);
  --fuente-marcador: var(--pl-font-cond, 'Roboto Condensed', 'Roboto', sans-serif);
  --borde: var(--pl-borde, rgba(127, 127, 127, .20));
  --card: var(--pl-card, rgba(127, 127, 127, .07));
  --sombra: var(--pl-sombra, 0 2px 10px -2px rgba(19, 10, 63, .06));
  --sombra-alta: 0 2px 4px rgba(15, 23, 42, .08), 0 18px 40px rgba(79, 70, 229, .22);
}""",
    "hoy": """/* Vista «Hoy» de la NBA: tarjetas de partido con estilo de marcador deportivo.
   Cada tarjeta recibe --hv y --hl (tono de color de visita y local) desde nba_hoy.py. */

@keyframes hoy-entra  { from { opacity: 0; transform: translateY(20px) scale(.985); } to { opacity: 1; transform: none; } }
@keyframes hoy-pulso  { 0% { box-shadow: 0 0 0 0 rgba(255, 255, 255, .75); } 70% { box-shadow: 0 0 0 7px rgba(255, 255, 255, 0); } 100% { box-shadow: 0 0 0 0 rgba(255, 255, 255, 0); } }
@keyframes hoy-brillo { 0% { transform: translateX(-140%) skewX(-18deg); } 100% { transform: translateX(380%) skewX(-18deg); } }
@keyframes hoy-pop    { 0% { opacity: 0; transform: scale(.55); } 60% { transform: scale(1.12); } 100% { opacity: 1; transform: scale(1); } }
@keyframes hoy-crece-v { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes hoy-flota  { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
@keyframes hoy-flujo  { from { background-position: 0% 50%; } to { background-position: 200% 50%; } }
@keyframes hoy-latido { 0%, 100% { box-shadow: 0 0 0 1px rgba(239, 68, 68, .55), 0 14px 38px -14px rgba(239, 68, 68, .55); }
                        50%      { box-shadow: 0 0 0 1px rgba(239, 68, 68, .9),  0 18px 46px -10px rgba(239, 68, 68, .85); } }

/* ---------- Tarjeta (siempre oscura, como un marcador de estadio) ---------- */
.hoy-card {
  --hv: 235; --hl: 285;
  box-sizing: border-box; position: relative; overflow: hidden; isolation: isolate;
  margin-top: 1rem; padding: 1.1rem 1.35rem 1.2rem; border-radius: 22px; color: #eef1ff;
  background:
    radial-gradient(540px 280px at 0% 55%, hsl(var(--hv) 85% 52% / .30), transparent 70%),
    radial-gradient(540px 280px at 100% 55%, hsl(var(--hl) 85% 52% / .30), transparent 70%),
    linear-gradient(160deg, var(--cancha-2) 0%, var(--cancha) 100%);
  border: 1px solid rgba(255, 255, 255, .09);
  box-shadow: 0 16px 36px -16px rgba(10, 14, 32, .6);
  transition: transform .28s cubic-bezier(.2, .8, .2, 1), box-shadow .28s ease, border-color .28s ease;
}
.hoy-card.nuevo { animation: hoy-entra .6s cubic-bezier(.2, .7, .2, 1) backwards; }  /* backwards: al terminar no bloquea el hover */
.hoy-card > * { position: relative; z-index: 2; }

/* Franja de color superior (visita → local) y reflejo que cruza al pasar el mouse */
.hoy-card::before {
  content: ""; position: absolute; left: 0; right: 0; top: 0; height: 4px; z-index: 3;
  background: linear-gradient(90deg, hsl(var(--hv) 85% 55%), hsl(var(--hl) 85% 55%));
}
.hoy-card::after {
  content: ""; position: absolute; top: 0; bottom: 0; left: 0; width: 28%; z-index: 1; pointer-events: none;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .10), transparent);
  transform: translateX(-140%) skewX(-18deg);
}
.hoy-card:hover {
  transform: translateY(-5px);
  border-color: rgba(255, 255, 255, .2);
  box-shadow: 0 26px 48px -18px hsl(var(--hv) 80% 50% / .5), 0 18px 40px -18px hsl(var(--hl) 80% 50% / .5);
}
.hoy-card:hover::after { animation: hoy-brillo 1.1s ease; }

/* Partido en vivo: borde que late y franja roja animada */
.hoy-card.vivo { border-color: transparent; animation: hoy-latido 2.4s ease-in-out infinite; }
.hoy-card.vivo.nuevo { animation: hoy-entra .6s cubic-bezier(.2, .7, .2, 1) backwards, hoy-latido 2.4s ease-in-out .6s infinite; }
.hoy-card.vivo::before {
  background: linear-gradient(90deg, #ef4444, #f59e0b, #ef4444); background-size: 200% 100%; animation: hoy-flujo 2.4s linear infinite;
}

/* ---------- Cabecera ---------- */
.hoy-top { display: flex; align-items: center; justify-content: space-between; gap: .6rem; flex-wrap: wrap; margin-bottom: .9rem; }
.hoy-pill {
  display: inline-flex; align-items: center; gap: .45rem; font-size: .68rem; font-weight: 700; letter-spacing: .14em;
  padding: .28rem .8rem; border-radius: 999px; color: #cdd5f5;
  background: rgba(255, 255, 255, .08); border: 1px solid rgba(255, 255, 255, .14);
}
.hoy-pill.vivo { color: #fff; border-color: transparent; background: linear-gradient(135deg, #ef4444, #dc2626); box-shadow: 0 0 20px rgba(239, 68, 68, .55); }
.hoy-dot { width: .5rem; height: .5rem; border-radius: 50%; background: #fff; animation: hoy-pulso 1.5s infinite; }
.hoy-linea { display: flex; gap: .45rem; flex-wrap: wrap; }
.hoy-linea span {
  font-size: .76rem; font-weight: 600; font-variant-numeric: tabular-nums; padding: .22rem .7rem; border-radius: 8px;
  color: #f3dc8a; background: rgba(201, 162, 39, .14); border: 1px solid rgba(201, 162, 39, .35);
}

/* ---------- Cuerpo: visita | marcador | local ---------- */
.hoy-main { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 1rem; }
.hoy-main > .hoy-eq:first-child { --c: var(--hv); }
.hoy-main > .hoy-eq:last-child  { --c: var(--hl); }
.hoy-eq { display: flex; flex-direction: column; align-items: center; text-align: center; gap: .35rem; min-width: 0; }
.hoy-ins {
  width: 66px; height: 66px; border-radius: 50%; display: grid; place-items: center; flex: none;
  color: #fff; font-family: var(--fuente-marcador); font-weight: 800; font-size: 1.35rem; letter-spacing: .04em;
  text-shadow: 0 1px 3px rgba(0, 0, 0, .45);
  box-shadow: 0 0 0 3px rgba(255, 255, 255, .14), 0 10px 26px -4px hsl(var(--c, 235) 85% 50% / .75), inset 0 0 0 2px rgba(255, 255, 255, .16);
  transition: transform .4s cubic-bezier(.3, 1.6, .5, 1);
}
.hoy-card:hover .hoy-ins { transform: scale(1.09) rotate(-5deg); }
.hoy-card:hover .hoy-main > .hoy-eq:last-child .hoy-ins { transform: scale(1.09) rotate(5deg); }
.hoy-card.vivo .hoy-ins { animation: hoy-flota 3.2s ease-in-out infinite; }
.hoy-card.vivo .hoy-main > .hoy-eq:last-child .hoy-ins { animation-delay: -1.6s; }
.hoy-nom { font-weight: 700; font-size: 1.02rem; line-height: 1.2; letter-spacing: -.01em; color: #fff; }
.hoy-meta { display: flex; flex-direction: column; align-items: center; gap: .25rem; font-size: .8rem; color: rgba(220, 228, 255, .72); font-variant-numeric: tabular-nums; }
.hoy-elo { font-size: .7rem; padding: .1rem .55rem; border-radius: 999px; background: rgba(255, 255, 255, .08); border: 1px solid rgba(255, 255, 255, .1); }

.hoy-centro { display: flex; flex-direction: column; align-items: center; justify-content: center; min-width: 140px; }
.hoy-hora {
  font-family: var(--fuente-marcador); font-weight: 800; font-size: 2.7rem; line-height: 1; letter-spacing: .02em; font-variant-numeric: tabular-nums;
  background: linear-gradient(180deg, #ffffff, #aab4e8); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.hoy-marc {
  display: flex; align-items: baseline; gap: .6rem; font-family: var(--fuente-marcador);
  font-weight: 800; font-size: 3.6rem; line-height: .95; letter-spacing: .01em; font-variant-numeric: tabular-nums;
}
.hoy-marc span { opacity: .5; display: inline-block; }
.hoy-marc span.gana { opacity: 1; color: #fff; text-shadow: 0 0 26px rgba(255, 255, 255, .4); }
.hoy-marc .sep { opacity: .3; font-weight: 600; font-size: .6em; }
.hoy-card.nuevo .hoy-marc span:not(.sep) { animation: hoy-pop .7s cubic-bezier(.3, 1.5, .5, 1) .25s backwards; }
.hoy-sub { margin-top: .45rem; font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; color: rgba(205, 213, 245, .6); min-height: 1em; }
.hoy-card.vivo .hoy-sub { color: #fca5a5; font-weight: 700; }

/* ---------- Probabilidad Elo ---------- */
.hoy-prob { margin-top: 1.15rem; }
.hoy-prob-cab { display: flex; justify-content: space-between; align-items: baseline; gap: .6rem; font-variant-numeric: tabular-nums; margin-bottom: .45rem; }
.hoy-prob-cab > span { font-family: var(--fuente-marcador); font-weight: 700; font-size: 1.05rem; letter-spacing: .03em; }
.hoy-prob-cab > span:first-child { color: hsl(var(--hv) 95% 72%); }
.hoy-prob-cab > span:last-child  { color: hsl(var(--hl) 95% 72%); }
.hoy-prob-cab .mid { flex: 1; text-align: center; font-family: inherit; font-weight: 500; font-size: .72rem; letter-spacing: 0; color: rgba(205, 213, 245, .55); }
.hoy-barra { position: relative; display: flex; height: 10px; gap: 3px; background: rgba(255, 255, 255, .07); border-radius: 99px; }
.hoy-barra::after { content: ""; position: absolute; left: 50%; top: -4px; bottom: -4px; width: 2px; margin-left: -1px; border-radius: 2px; background: rgba(255, 255, 255, .4); }
.hoy-barra .v, .hoy-barra .l { height: 100%; }
.hoy-barra .v { flex: none; border-radius: 99px 4px 4px 99px; transform-origin: left; box-shadow: 0 0 16px hsl(var(--hv) 85% 50% / .65); animation: hoy-crece-v 1s cubic-bezier(.2, .8, .2, 1) .15s backwards; }
.hoy-barra .l { flex: 1; border-radius: 4px 99px 99px 4px; transform-origin: right; box-shadow: 0 0 16px hsl(var(--hl) 85% 50% / .65); animation: hoy-crece-v 1s cubic-bezier(.2, .8, .2, 1) .15s backwards; }

/* ---------- Lesionados ---------- */
.hoy-bajas { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1.1rem; padding-top: .9rem; border-top: 1px solid rgba(255, 255, 255, .09); }
.hoy-bajas > div { display: flex; flex-wrap: wrap; align-items: center; gap: .38rem; min-width: 0; }
.hoy-bajas b { flex: 0 0 100%; font-size: .64rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: rgba(205, 213, 245, .55); margin-bottom: .1rem; }
.hoy-chip {
  display: inline-block; max-width: 100%; font-size: .74rem; font-weight: 600; padding: .2rem .65rem; border-radius: 999px; color: #dbe2ff;
  background: rgba(255, 255, 255, .07); border: 1px solid rgba(255, 255, 255, .12); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: transform .18s ease, background .18s ease;
}
.hoy-chip:hover { transform: translateY(-2px); background: rgba(255, 255, 255, .13); }
.hoy-chip.out { color: #fecaca; background: rgba(239, 68, 68, .16); border-color: rgba(239, 68, 68, .42); }
.hoy-chip.dud { color: #fed7aa; background: rgba(249, 115, 22, .16); border-color: rgba(249, 115, 22, .42); }
.hoy-chip.qst { color: #fde68a; background: rgba(234, 179, 8, .14); border-color: rgba(234, 179, 8, .4); }
.hoy-ok { font-size: .78rem; font-weight: 600; color: #86efac; }
.hoy-nd { font-size: .78rem; color: rgba(205, 213, 245, .45); font-style: italic; }

/* ---------- Pantallas angostas ---------- */
@media (max-width: 680px) {
  .hoy-card { padding: 1rem 1rem 1.1rem; }
  .hoy-main { gap: .5rem; }
  .hoy-ins { width: 48px; height: 48px; font-size: 1rem; }
  .hoy-nom { font-size: .85rem; }
  .hoy-marc { font-size: 2.5rem; gap: .4rem; }
  .hoy-hora { font-size: 1.9rem; }
  .hoy-centro { min-width: 90px; }
  .hoy-bajas { grid-template-columns: 1fr; }
}""",
    "deporte": """/* Capa global «app deportiva»: se aplica a toda la app encima de diseno.py. */

@keyframes dep-entra { from { opacity: 0; transform: translateX(-14px); } to { opacity: 1; transform: none; } }
@keyframes dep-sube  { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

/* Fondo: luces de estadio + líneas diagonales muy tenues */
.stApp {
  background-image:
    radial-gradient(900px 420px at 100% -6%, rgba(239, 68, 68, .08), transparent 60%),
    radial-gradient(1100px 520px at 4% -8%, rgba(79, 70, 229, .15), transparent 60%),
    repeating-linear-gradient(115deg, rgba(127, 127, 127, .035) 0 2px, transparent 2px 46px);
}

/* Títulos tipo transmisión deportiva */
.stApp h1, .stApp h2, .stApp h3 {
  font-family: var(--fuente-marcador) !important; text-transform: uppercase; letter-spacing: .035em;
}
/* Título en color sólido: con el degradado en el texto, los emojis se ven como una mancha */
.stApp h1 {
  position: relative; padding-bottom: .6rem; font-size: 3rem; font-weight: 800; line-height: 1.05;
  background: none !important; -webkit-text-fill-color: currentColor !important;
  animation: dep-entra .6s cubic-bezier(.2, .7, .2, 1) both;
}
.stApp h1::after { content: ""; position: absolute; left: 0; bottom: 0; width: 72px; height: 4px; border-radius: 4px; background: linear-gradient(90deg, var(--indigo), var(--violeta), var(--oro)); }
.stApp h2 { font-size: 1.9rem; font-weight: 700; }
.stApp h3 { font-size: 1.45rem; font-weight: 700; }

/* Menú lateral: marca y navegación con acento */
[data-testid="stSidebar"] { backdrop-filter: blur(6px); }
[data-testid="stSidebar"] div[role="radiogroup"] label { font-weight: 600; letter-spacing: .01em; position: relative; }
[data-testid="stSidebar"] div[role="radiogroup"] label:not(:has(input:checked))::before {
  content: ""; position: absolute; left: 0; top: 22%; bottom: 22%; width: 3px; border-radius: 3px; background: var(--oro);
  transform: scaleY(0); transition: transform .2s ease;
}
[data-testid="stSidebar"] div[role="radiogroup"] label:not(:has(input:checked)):hover::before { transform: scaleY(1); }

/* Métricas: números tipo marcador */
[data-testid="stMetricValue"] { font-family: var(--fuente-marcador) !important; font-size: 2.3rem !important; font-weight: 800 !important; letter-spacing: .01em; }
[data-testid="stMetricLabel"] { text-transform: uppercase; letter-spacing: .1em; font-size: .72rem !important; }

/* Pestañas en forma de píldora */
[data-baseweb="tab-list"] { border-bottom: none; background: var(--card); border: 1px solid var(--borde); border-radius: 14px; padding: 4px; width: fit-content; max-width: 100%; }
button[data-baseweb="tab"] { border-radius: 10px; }
button[data-baseweb="tab"][aria-selected="true"] { background: linear-gradient(135deg, var(--indigo), var(--violeta)); color: #fff; box-shadow: 0 6px 16px rgba(79, 70, 229, .35); }
button[data-baseweb="tab"][aria-selected="true"] * { color: #fff !important; }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none !important; }

/* Botones: más presencia */
.stButton > button { letter-spacing: .02em; padding: .45rem 1.1rem; }
.stButton > button:hover { background-color: rgba(79, 70, 229, .10); }

/* Entradas: brillo al enfocar */
[data-baseweb="select"] > div:focus-within, [data-baseweb="input"]:focus-within, [data-baseweb="base-input"]:focus-within {
  border-color: var(--indigo) !important; box-shadow: 0 0 0 3px rgba(79, 70, 229, .22);
}

/* Avisos y leyendas */
[data-testid="stCaptionContainer"] { letter-spacing: .01em; }
[data-testid="stAlert"] { backdrop-filter: blur(4px); }

/* Tablas: encabezado con acento dorado */
.tabla th { border-bottom-color: rgba(201, 162, 39, .55); }
.tabla tbody tr:hover td:first-child { box-shadow: inset 3px 0 0 var(--oro); }""",
    "ficha_linea": """.fl { position: relative; overflow: hidden; border-radius: 24px; padding: 1.4rem 1.5rem 1.2rem; color: #fff;
  background: linear-gradient(160deg, #0f172a 0%, #1e1b4b 100%); border: 1px solid rgba(255,255,255,.10);
  box-shadow: 0 24px 60px rgba(15,23,42,.35); margin: .4rem 0 1rem; }
.fl-foto { position: absolute; right: 0; top: 0; height: 190px; opacity: .95;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 40%), linear-gradient(180deg, #000 70%, transparent);
  -webkit-mask-composite: source-in; mask-composite: intersect; }
.fl-nombre { font-family: 'Plus Jakarta Sans','Inter',sans-serif; font-weight: 800; font-size: 2.4rem; letter-spacing: -.03em; line-height: 1.05; position: relative; }
.fl-ctx { color: rgba(255,255,255,.6); margin-top: .3rem; font-weight: 500; position: relative; }
.fl-fila { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; margin: 1.3rem 0 1rem; position: relative; flex-wrap: wrap; }
.fl-tag { font-size: .78rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
.fl-tag.si { color: #4ade80; } .fl-tag.no { color: #f87171; }
.fl-linea { font-family: 'Plus Jakarta Sans','Inter',sans-serif; font-weight: 800; font-size: 4rem; line-height: 1; letter-spacing: -.04em; }
.fl-pct { text-align: right; } .fl-pct b { font-family: 'Plus Jakarta Sans','Inter',sans-serif; font-size: 3rem; font-weight: 800; line-height: 1; letter-spacing: -.03em; }
.fl-pct small { display: block; color: rgba(255,255,255,.6); margin-top: .25rem; }
.fl-meter { width: 220px; max-width: 100%; height: 6px; border-radius: 9px; background: rgba(255,255,255,.14); margin-top: .6rem; margin-left: auto; overflow: hidden; }
.fl-meter i { display: block; height: 100%; border-radius: inherit; background: #4ade80; }
.fl-cab { display: flex; justify-content: space-between; font-size: .78rem; font-weight: 600; letter-spacing: .1em; text-transform: uppercase;
  color: rgba(255,255,255,.55); margin-bottom: .6rem; } .fl-cab .v { color: #4ade80; } .fl-cab .r { color: #f87171; }
.fl-barras { position: relative; display: flex; align-items: flex-end; gap: 8px; height: 150px; }
.fl-barras .corte { position: absolute; left: 0; right: 0; border-top: 2px dashed rgba(255,255,255,.55); pointer-events: none; z-index: 2; }
.fl-b { flex: 1; min-height: 26px; border-radius: 9px; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: .85rem;
  background: rgba(255,255,255,.10); color: rgba(255,255,255,.75); transition: transform .2s ease; animation: subir .5s ease both; }
.fl-b.ok { background: linear-gradient(180deg, #86efac, #4ade80); color: #052e16; }
.fl-b.push { background: transparent; border: 2px dashed rgba(255,255,255,.45); color: rgba(255,255,255,.85); }
.fl-b:hover { transform: translateY(-4px); }
.fl-riv { display: flex; gap: 8px; margin-top: .35rem; } .fl-riv span { flex: 1; text-align: center; font-size: .65rem; color: rgba(255,255,255,.45); }""",
    "equipos": """/* Tarjeta de líneas por equipo (ficha_equipos.py → clase «.fl.eq»).
   Todas las reglas llevan «.fl.eq» delante para ganarle a los estilos base de ficha_linea y no tocar la tarjeta de jugadores.
   --tc = color del equipo (lo pone ficha_equipos.py). */

@keyframes fe-entra { from { opacity: 0; transform: translateY(18px) scale(.985); } to { opacity: 1; transform: none; } }
@keyframes fe-sube  { from { transform: scaleY(0); } to { transform: scaleY(1); } }
@keyframes fe-ancho { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes fe-pop   { 0% { opacity: 0; transform: scale(.7); } 60% { transform: scale(1.06); } 100% { opacity: 1; transform: scale(1); } }

/* ---------- Tarjeta ---------- */
.fl.eq {
  --tc: #4f46e5;
  position: relative; box-sizing: border-box; overflow: hidden; isolation: isolate; width: auto; max-width: none;
  display: grid; grid-template-columns: 76px 1fr; column-gap: 1.1rem; align-content: start; text-align: left;
  margin: 0 0 1rem; padding: 1.35rem 1.4rem 1.25rem; border-radius: 24px; color: #eef1ff;
  /* mismo fondo que la tarjeta de línea y tendencia de jugadores (ficha_linea): azul noche con luces índigo y violeta */
  background:
    radial-gradient(620px 300px at 0% 0%, rgba(99, 102, 241, .40), transparent 62%),
    radial-gradient(600px 320px at 100% 100%, rgba(139, 92, 246, .32), transparent 62%),
    radial-gradient(460px 240px at 100% 0%, rgba(56, 189, 248, .12), transparent 65%),
    linear-gradient(160deg, #0f172a 0%, #1e1b4b 55%, #2b1d66 100%);
  border: 1px solid rgba(165, 180, 252, .24); box-shadow: 0 26px 60px -20px rgba(30, 27, 75, .65), 0 2px 0 rgba(255, 255, 255, .07) inset;
  animation: fe-entra .55s cubic-bezier(.2, .7, .2, 1) backwards;
  transition: transform .28s cubic-bezier(.2, .8, .2, 1), box-shadow .28s ease;
}
.fl.eq:hover { transform: translateY(-4px); box-shadow: 0 30px 56px -20px rgba(99, 102, 241, .55), 0 2px 0 rgba(255, 255, 255, .07) inset; }
.fl.eq::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 55%, #38bdf8 100%); }
.fl.eq::after { display: none; }
.fl.eq > * { grid-column: 1 / -1; position: relative; z-index: 1; min-width: 0; }

/* ---------- Cabecera: logo + nombre ---------- */
.fl.eq > .fl-logo {
  grid-column: 1; grid-row: 1 / span 2; align-self: center; box-sizing: border-box;
  width: 76px !important; height: 76px !important; max-width: 76px; max-height: 76px; padding: 9px; object-fit: contain; margin: 0;
  border-radius: 50%; background: radial-gradient(circle at 30% 25%, #ffffff, #e6e9f4);
  box-shadow: 0 0 0 3px rgba(255, 255, 255, .16), 0 12px 28px -6px color-mix(in srgb, var(--tc) 75%, transparent);
  transition: transform .4s cubic-bezier(.3, 1.6, .5, 1);
}
.fl.eq:hover > .fl-logo { transform: scale(1.07) rotate(-5deg); }
.fl.eq > .fl-nombre {
  grid-column: 2; grid-row: 1; align-self: end; margin: 0;
  font-family: var(--fuente-marcador, 'Barlow Condensed', sans-serif); font-weight: 800; font-size: 2.2rem; line-height: 1;
  letter-spacing: .02em; text-transform: uppercase; color: #fff;
}
.fl.eq > .fl-ctx { grid-column: 2; grid-row: 2; align-self: start; margin: .3rem 0 0; font-size: .82rem; color: rgba(205, 213, 245, .66); }
.fl.eq > .fl-nombre:first-child, .fl.eq > .fl-nombre:first-child + .fl-ctx { grid-column: 1 / -1; }   /* tarjeta sin datos (sin logo) */

/* ---------- Línea y frecuencia ---------- */
.fl.eq .fl-fila {
  display: flex; justify-content: space-between; align-items: flex-end; gap: 1.4rem; margin-top: 1.2rem; padding: 1.05rem 1.2rem;
  border-radius: 18px; background: rgba(255, 255, 255, .05); border: 1px solid rgba(255, 255, 255, .08);
}
.fl.eq .fl-tag {
  display: inline-block; padding: .22rem .75rem; border-radius: 999px; font-size: .68rem; font-weight: 800; letter-spacing: .14em;
  color: #cdd5f5; background: rgba(255, 255, 255, .08); border: 1px solid rgba(255, 255, 255, .14);
}
.fl.eq .fl-tag.si { color: #86efac; background: rgba(34, 197, 94, .14); border-color: rgba(34, 197, 94, .4); }
.fl.eq .fl-tag.no { color: #fca5a5; background: rgba(239, 68, 68, .14); border-color: rgba(239, 68, 68, .4); }
.fl.eq .fl-linea {
  margin-top: .45rem; font-family: var(--fuente-marcador, 'Barlow Condensed', sans-serif); font-weight: 800; font-size: 3.6rem; line-height: .95;
  letter-spacing: .01em; color: #fff; font-variant-numeric: tabular-nums;
}
.fl.eq .fl-pct { flex: 0 1 46%; text-align: right; }
.fl.eq .fl-pct b {
  display: block; font-family: var(--fuente-marcador, 'Barlow Condensed', sans-serif); font-weight: 800; font-size: 3.6rem; line-height: .95;
  font-variant-numeric: tabular-nums; color: #f87171; animation: fe-pop .6s cubic-bezier(.3, 1.5, .5, 1) .2s backwards;
}
.fl.eq .fl-fila:has(.fl-tag.si) .fl-pct b { color: #4ade80; }
.fl.eq .fl-pct small { display: block; margin-top: .3rem; font-size: .72rem; color: rgba(205, 213, 245, .6); }
.fl.eq .fl-meter { height: 8px; margin-top: .6rem; border-radius: 99px; overflow: hidden; background: rgba(255, 255, 255, .1); }
.fl.eq .fl-meter i {
  display: block; height: 100%; border-radius: inherit; transform-origin: left; background: linear-gradient(90deg, #ef4444, #f87171);
  animation: fe-ancho .9s cubic-bezier(.2, .8, .2, 1) .2s backwards;
}
.fl.eq .fl-fila:has(.fl-tag.si) .fl-meter i { background: linear-gradient(90deg, #10b981, #4ade80); }

/* ---------- Barras por partido ---------- */
.fl.eq .fl-cab { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-top: 1.3rem; font-size: .8rem; color: rgba(205, 213, 245, .62); }
.fl.eq .fl-cab .v { color: #86efac; font-weight: 700; }
.fl.eq .fl-cab .r { color: #fca5a5; font-weight: 700; }
.fl.eq .fl-barras {
  position: relative; display: flex; align-items: flex-end; gap: 5px; height: 190px; margin-top: .6rem; padding: 8px 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, .2);
  background: repeating-linear-gradient(180deg, rgba(255, 255, 255, .05) 0 1px, transparent 1px 25%);
}
.fl.eq .fl-barras.denso { gap: 3px; }
.fl.eq .fl-barras .corte { position: absolute; left: 0; right: 0; height: 0; z-index: 3; border-top: 2px dashed #f5c542; pointer-events: none; opacity: .95; }
.fl.eq .fl-barras .corte::after { content: ""; position: absolute; right: -2px; top: -6px; width: 9px; height: 9px; border-radius: 50%; background: #f5c542; }
.fl.eq .fl-b {
  position: relative; flex: 1 1 0; min-width: 0; display: flex; justify-content: center; align-items: flex-start; padding-top: 5px;
  border-radius: 9px 9px 0 0; color: rgba(255, 255, 255, .92); font-size: .72rem; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums;
  background: linear-gradient(180deg, rgba(248, 113, 113, .85), rgba(185, 28, 28, .5));
  transform-origin: bottom; animation: fe-sube .65s cubic-bezier(.2, .8, .2, 1) backwards;
  transition: filter .18s ease, transform .18s ease;
}
.fl.eq .fl-b.ok { background: linear-gradient(180deg, #34d399, #059669); }
.fl.eq .fl-b.ot { box-shadow: inset 0 0 0 2px #a78bfa; }
.fl.eq .fl-b:hover { filter: brightness(1.18); }
.fl.eq .fl-barras.denso .fl-b { writing-mode: vertical-rl; font-size: .62rem; padding: 6px 0 0; border-radius: 6px 6px 0 0; }
.fl.eq .fl-b .mk { position: absolute; bottom: 5px; left: 50%; width: 7px; height: 7px; margin-left: -3.5px; border-radius: 50%; box-shadow: 0 0 0 2px rgba(10, 14, 32, .75); }
.fl.eq .fl-b .mk.a { background: #fbbf24; }
.fl.eq .fl-b .mk.r { background: #f43f5e; }
.fl.eq .fl-b .mk.dos.a { margin-left: -9px; }
.fl.eq .fl-b .mk.dos.r { margin-left: 2px; }
.fl.eq .fl-riv { display: flex; gap: 5px; margin-top: 6px; padding: 0 4px; }
.fl.eq .fl-riv.denso { gap: 3px; }
.fl.eq .fl-riv span { flex: 1 1 0; min-width: 0; text-align: center; white-space: nowrap; overflow: hidden; font-size: .64rem; color: rgba(205, 213, 245, .6); }
.fl.eq .fl-riv.denso span { font-size: .5rem; }
.fl.eq .fl-leyenda { margin-top: .75rem; font-size: .72rem; color: rgba(205, 213, 245, .6); }
.fl.eq .fl-leyenda i { display: inline-block; width: 8px; height: 8px; margin: 0 .4rem 0 1rem; border-radius: 50%; vertical-align: middle; background: #fbbf24; }
.fl.eq .fl-leyenda i.r { background: #f43f5e; }
.fl.eq .fl-leyenda i.o { border-radius: 3px; background: transparent; box-shadow: inset 0 0 0 2px #a78bfa; }

/* ---------- Próximo partido y bajas ---------- */
.fl.eq .fl-hoy {
  margin-top: 1.1rem; padding: .85rem 1.05rem; border-radius: 16px; font-size: .82rem; line-height: 1.75; color: #dbe2ff;
  background: rgba(255, 255, 255, .05); border: 1px solid rgba(255, 255, 255, .08);
}
.fl.eq .fl-hoy b { color: #fff; }
.fl.eq .fl-hoy .tag {
  display: inline-block; margin-left: .5rem; padding: .08rem .55rem; border-radius: 999px; font-size: .62rem; font-weight: 800; letter-spacing: .1em;
  color: #fcd34d; background: rgba(251, 191, 36, .16); border: 1px solid rgba(251, 191, 36, .4);
}
.fl.eq .fl-hoy .chip {
  display: inline-block; margin: .15rem .3rem .15rem 0; padding: .1rem .6rem; border-radius: 999px; font-size: .72rem; font-weight: 600;
  color: #fecaca; background: rgba(239, 68, 68, .16); border: 1px solid rgba(239, 68, 68, .4);
}
.fl.eq .fl-hoy .chip.dud { color: #fde68a; background: rgba(234, 179, 8, .14); border-color: rgba(234, 179, 8, .4); }

/* ---------- Estadísticas ---------- */
.fl.eq .fl-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(112px, 1fr)); gap: 8px; margin-top: 1.1rem; }
.fl.eq .fl-st {
  padding: .65rem .8rem; border-radius: 14px; background: rgba(255, 255, 255, .05); border: 1px solid rgba(255, 255, 255, .07);
  transition: transform .18s ease, background .18s ease;
}
.fl.eq .fl-st:hover { transform: translateY(-3px); background: rgba(255, 255, 255, .09); }
.fl.eq .fl-st small { display: block; margin-bottom: .25rem; font-size: .62rem; line-height: 1.25; letter-spacing: .08em; text-transform: uppercase; color: rgba(205, 213, 245, .6); }
.fl.eq .fl-st b { font-family: var(--fuente-marcador, 'Barlow Condensed', sans-serif); font-weight: 700; font-size: 1.4rem; line-height: 1.15; color: #fff; font-variant-numeric: tabular-nums; white-space: nowrap; }
.fl.eq .fl-st b.pos { color: #4ade80; }
.fl.eq .fl-st b.neg { color: #f87171; }
.fl.eq .fl-sub {
  display: flex; align-items: center; gap: .7rem; margin-top: 1.3rem; font-size: .68rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase;
  color: rgba(205, 213, 245, .6);
}
.fl.eq .fl-sub::after { content: ""; flex: 1; height: 1px; background: rgba(255, 255, 255, .1); }
.fl.eq .fl-aviso {
  margin-top: .9rem; padding: .55rem .85rem; border-radius: 12px; font-size: .76rem; color: #fde68a;
  background: rgba(234, 179, 8, .1); border: 1px solid rgba(234, 179, 8, .3);
}

@media (max-width: 720px) {
  .fl.eq { grid-template-columns: 60px 1fr; padding: 1.1rem 1rem; }
  .fl.eq > .fl-logo { width: 60px !important; height: 60px !important; }
  .fl.eq > .fl-nombre { font-size: 1.6rem; }
  .fl.eq .fl-linea, .fl.eq .fl-pct b { font-size: 2.6rem; }
  .fl.eq .fl-fila { padding: .9rem; }
}""",
    "escudos": """/* Selector de equipos con escudos pequeños (ficha_equipos.py).
   ficha_equipos agrega después una regla por equipo con su logo como background-image del botón. */

/* Fila de escudos: una banda con los botones en horizontal, que baja de línea si no caben */
div[class*="st-key-fe_"][class*="_barra"] {
  display: flex !important; flex-direction: row !important; flex-wrap: wrap !important; align-items: center !important;
  gap: 6px !important; padding: .6rem .7rem; margin-bottom: .6rem;
  border: 1px solid var(--borde); border-radius: 18px; background: var(--card);
}
div[class*="st-key-fe_"][class*="_barra"] > div { width: auto !important; flex: 0 0 auto !important; min-width: 0 !important; }

/* Cada botón es un escudo: el texto (abreviatura) queda oculto y se ve en el tooltip */
div[class*="st-key-fe_"][class*="_barra"] button {
  position: relative; width: 44px !important; min-width: 44px !important; height: 44px !important; min-height: 44px !important;
  padding: 0 !important; border-radius: 13px !important; margin: 0;
  border: 1px solid var(--borde) !important; color: transparent !important;
  font-size: 0 !important; line-height: 0 !important; letter-spacing: 0;
  background-color: rgba(127, 127, 127, .08) !important;
  background-repeat: no-repeat !important; background-position: center !important; background-size: 74% !important;
  transition: transform .22s cubic-bezier(.3, 1.6, .5, 1), box-shadow .2s ease, background-color .2s ease, border-color .2s ease, filter .2s ease;
}
div[class*="st-key-fe_"][class*="_barra"] button * { font-size: 0 !important; line-height: 0 !important; color: transparent !important; }
div[class*="st-key-fe_"][class*="_barra"] button:hover:not(:disabled) {
  transform: translateY(-4px) scale(1.12); z-index: 2;
  border-color: var(--indigo) !important; background-color: rgba(79, 70, 229, .13) !important;
  box-shadow: 0 10px 22px rgba(79, 70, 229, .3);
}
div[class*="st-key-fe_"][class*="_barra"] button:active:not(:disabled) { transform: scale(.96); }

/* Equipo elegido: anillo índigo y un punto dorado */
div[class*="st-key-fe_"][class*="_barra"] button[kind="primary"],
div[class*="st-key-fe_"][class*="_barra"] button[data-testid="stBaseButton-primary"] {
  border: 1px solid var(--indigo) !important; background-color: rgba(79, 70, 229, .18) !important;
  box-shadow: 0 0 0 2px var(--indigo), 0 10px 22px rgba(79, 70, 229, .35) !important; transform: scale(1.08);
}
div[class*="st-key-fe_"][class*="_barra"] button[kind="primary"]::after,
div[class*="st-key-fe_"][class*="_barra"] button[data-testid="stBaseButton-primary"]::after {
  content: ""; position: absolute; top: -4px; right: -4px; left: auto; bottom: auto; width: 10px; height: 10px; border-radius: 50%;
  background: var(--oro); border: 2px solid var(--st-background-color, #fff); transform: none; animation: none;
}

/* Equipo que ya es el A: no se puede elegir como B */
div[class*="st-key-fe_"][class*="_barra"] button:disabled {
  opacity: .28 !important; filter: grayscale(1); cursor: not-allowed; transform: none !important; box-shadow: none !important;
}

/* Botón «Quitar Equipo B» */
div[class*="st-key-fe_b_ninguno"] button { border-radius: 999px; padding: .25rem 1rem; font-size: .85rem; }

@media (max-width: 640px) {
  div[class*="st-key-fe_"][class*="_barra"] button { width: 38px !important; min-width: 38px !important; height: 38px !important; min-height: 38px !important; }
}""",
}


def _leer(nombre: str) -> str | None:
    """Texto de css/<nombre>.css; si el archivo no existe, la copia incluida; si tampoco, None."""
    ruta = CARPETA / f"{nombre}.css"
    if ruta.is_file():
        return ruta.read_text(encoding="utf-8").strip()
    return DEFAULTS.get(nombre)


def css(*nombres: str) -> str:
    """Texto CSS de las hojas pedidas, con la paleta compartida («tokens») siempre al principio."""
    orden = ["tokens"] + [n for n in nombres if n != "tokens"]
    textos = [t for t in (_leer(n) for n in orden) if t]
    return "\n".join(textos) + "\n"


def cargar(*nombres: str) -> None:
    st.markdown(f"<style>{FUENTES}\n{css(*nombres)}</style>", unsafe_allow_html=True)