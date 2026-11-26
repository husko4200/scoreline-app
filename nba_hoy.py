"""Vista «Hoy»: los partidos del día con Elo, línea de mercado y lesionados en una sola pantalla.

Junta lo que antes estaba repartido en Ranking y Elo, Líneas y Lesiones. Si la liga no se pudo cargar
(liga=None) la vista sigue funcionando, solo sin Elo.
"""
import json
import logging
import math
import statistics
import os
import re
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html import escape as _e
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import estilos
import nba
import nba_extra
import nba_profundo as npf
import nba_sim_jugadores as sj
from common import ZONA, normalizar

log = logging.getLogger(__name__)

_ET = "America/New_York"  # ESPN agrupa los partidos por día en hora del Este
_GRAVEDAD = {"out": 0, "doubtful": 1, "questionable": 2, "day-to-day": 3}
_MAX_BAJAS = 4


def _hoy_et() -> date:
    return pd.Timestamp.now(tz=_ET).date()


def _lesiones_por_equipo():
    """{nombre de equipo: [lesionados]}; {} si no hay ninguno; None si no se pudo leer."""
    try:
        df = nba_extra.lesiones()
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty:
        return {}
    return {n: g.to_dict("records") for n, g in df.groupby("Equipo")}


def _elo_y_puesto(liga):
    """(Elo por id de equipo, puesto por id) o ({}, {}) sin liga."""
    if not liga:
        return {}, {}
    rat = liga[2]
    puesto = {tid: i + 1 for i, tid in enumerate(sorted(rat, key=rat.get, reverse=True))}
    return rat, puesto




def _insignia(eq) -> tuple[str, int]:
    """Círculo con la abreviatura; el color sale de la abreviatura (siempre el mismo para cada equipo)."""
    ab = eq["abrev"] or eq["nombre"][:3].upper()
    h = zlib.crc32(ab.encode()) % 360
    fondo = f"linear-gradient(135deg,hsl({h},72%,52%),hsl({(h + 35) % 360},72%,34%))"
    return f'<div class="hoy-ins" style="background:{fondo}">{_e(ab)}</div>', h


def _equipo_html(eq, rat, puesto) -> str:
    ins, _ = _insignia(eq)
    meta = ""
    if eq.get("record"):
        meta += f"<span>{_e(eq['record'])}</span>"
    if eq["id"] in rat:
        meta += f'<span class="hoy-elo">Elo {rat[eq["id"]]:.0f} · #{puesto[eq["id"]]}</span>'
    return f'<div class="hoy-eq">{ins}<div class="hoy-nom">{_e(eq["nombre"])}</div><div class="hoy-meta">{meta}</div></div>'


def _centro_html(j) -> str:
    L, V = j["local"], j["visita"]
    if j["estado"] == "pre":
        hora = pd.to_datetime(j["fecha"], utc=True).tz_convert(ZONA).strftime("%H:%M") if j["fecha"] else "—"
        return f'<div class="hoy-centro"><div class="hoy-hora">{hora}</div><div class="hoy-sub">hora local</div></div>'
    pv, pl = V["puntos"], L["puntos"]
    cv = ' class="gana"' if pv >= pl else ""
    cl = ' class="gana"' if pl >= pv else ""
    sub = _e(j["detalle"]) if j["estado"] == "in" and j["detalle"] else ""
    return (f'<div class="hoy-centro"><div class="hoy-marc"><span{cv}>{pv:.0f}</span><span class="sep">–</span>'
            f'<span{cl}>{pl:.0f}</span></div><div class="hoy-sub">{sub}</div></div>')


def _pastilla(j) -> str:
    if j["estado"] == "in":
        return '<span class="hoy-pill vivo"><span class="hoy-dot"></span>EN VIVO</span>'
    return '<span class="hoy-pill">FINAL</span>' if j["estado"] == "post" else '<span class="hoy-pill">POR JUGAR</span>'


def _linea_html(j) -> str:
    partes = []
    if j.get("linea_txt"):
        partes.append(f"<span>🎯 {_e(str(j['linea_txt']))}</span>")
    if j.get("linea_total"):
        partes.append(f"<span>Total {j['linea_total']:.1f}</span>")
    return f'<div class="hoy-linea">{"".join(partes)}</div>' if partes else ""


def _prob_html(j, rat) -> str:
    """Barra de probabilidad Elo (visita a la izquierda, local a la derecha)."""
    L, V = j["local"], j["visita"]
    if L["id"] not in rat or V["id"] not in rat:
        return ""
    p_loc, margen = nba.prob_elo(rat, L["id"], V["id"], a_local=True)
    p_vis = 1 - p_loc
    hv = _insignia(V)[1]
    hl = _insignia(L)[1]
    abv, abl = _e(V["abrev"] or V["nombre"]), _e(L["abrev"] or L["nombre"])
    fav = abl if p_loc >= 0.5 else abv
    return (f'<div class="hoy-prob"><div class="hoy-prob-cab"><span>{abv} {p_vis:.0%}</span>'
            f'<span class="mid">Elo · favorito {fav} por {abs(margen):.1f}</span><span>{p_loc:.0%} {abl}</span></div>'
            f'<div class="hoy-barra"><div class="v" style="width:{p_vis * 100:.1f}%;background:hsl({hv},72%,48%)"></div>'
            f'<div class="l" style="background:hsl({hl},72%,48%)"></div></div></div>')


def _chips_bajas(bajas) -> str:
    if bajas is None:
        return '<span class="hoy-nd">sin datos ahora</span>'
    if not bajas:
        return '<span class="hoy-ok">✔ sin bajas reportadas</span>'
    orden = sorted(bajas, key=lambda b: (_GRAVEDAD.get(str(b.get("Estado")).lower(), 9), str(b.get("Jugador"))))
    chips = []
    for b in orden[:_MAX_BAJAS]:
        g = _GRAVEDAD.get(str(b.get("Estado")).lower(), 9)
        clase = {0: "out", 1: "dud", 2: "qst"}.get(g, "")
        chips.append(f'<span class="hoy-chip {clase}" title="{_e(str(b.get("Lesión") or ""))}">'
                     f'{_e(str(b.get("Jugador")))} · {_e(str(b.get("Estado")))}</span>')
    if len(orden) > _MAX_BAJAS:
        chips.append(f'<span class="hoy-chip">+{len(orden) - _MAX_BAJAS} más</span>')
    return "".join(chips)


def _tarjeta(j, rat, puesto, lesiones, nombres, idx=0, nuevo=False):
    L, V = j["local"], j["visita"]

    def bajas(eq):
        nom = nombres.get(eq["id"], eq["nombre"])
        return None if lesiones is None else lesiones.get(nom, [])

    clases = "hoy-card" + (" vivo" if j["estado"] == "in" else "") + (" nuevo" if nuevo else "")
    # --hv / --hl: tono de color de visita y local; el CSS los usa para el brillo y los acentos de cada equipo.
    estilo = f' style="--hv:{_insignia(V)[1]};--hl:{_insignia(L)[1]}' + (f';animation-delay:{idx * 70}ms' if nuevo else "") + '"'
    html = (f'<div class="{clases}"{estilo}>'
            f'<div class="hoy-top">{_pastilla(j)}{_linea_html(j)}</div>'
            f'<div class="hoy-main">{_equipo_html(V, rat, puesto)}{_centro_html(j)}{_equipo_html(L, rat, puesto)}</div>'
            f'{_prob_html(j, rat)}'
            f'<div class="hoy-bajas"><div><b>{_e(V["abrev"] or V["nombre"])} · LESIONADOS</b>{_chips_bajas(bajas(V))}</div>'
            f'<div><b>{_e(L["abrev"] or L["nombre"])} · LESIONADOS</b>{_chips_bajas(bajas(L))}</div></div>'
            f'</div>')
    st.markdown(html, unsafe_allow_html=True)


INTERVALO_S = 30   # cada cuánto se refrescan las tarjetas mientras hay partidos en juego
MIN_ANTES, MIN_DESPUES = 10, 15  # se vigila desde 10 min antes del salto inicial (y hasta 15 min después si ESPN tarda)


def _hay_actividad(juegos) -> bool:
    """¿Hay algún partido en vivo o a punto de empezar? Solo entonces conviene refrescar solo."""
    ahora = pd.Timestamp.now(tz="UTC")
    for j in juegos:
        if j["estado"] == "in":
            return True
        if j["estado"] == "pre" and j["fecha"]:
            mins = (pd.to_datetime(j["fecha"], utc=True) - ahora).total_seconds() / 60
            if -MIN_DESPUES <= mins <= MIN_ANTES:
                return True
    return False


def _cuerpo(fecha, rat, puesto, lesiones, nombres, vigilando):
    """Marcadores y tarjetas. Va dentro de un fragmento: se puede repetir solo, sin recargar el resto de la página.

    Solo vuelve a pedir el marcador; Elo, lesiones y nombres vienen de la ejecución completa anterior.
    """
    try:
        juegos = nba.scoreboard(fecha)
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo leer el calendario de ESPN: {e}")
        return
    if not juegos:
        st.info("No hay partidos programados ese día.")
        return

    vivos = sum(j["estado"] == "in" for j in juegos)
    ahora = pd.Timestamp.now(tz=ZONA).strftime("%H:%M:%S")
    st.caption(f"{len(juegos)} partidos" + (f" · {vivos} en vivo" if vivos else "")
               + f" · actualizado {ahora}"
               + (f" · actualización automática cada {INTERVALO_S} s" if vigilando else ""))
    orden = {"in": 0, "pre": 1, "post": 2}  # en vivo primero, luego por jugar, luego terminados
    vistos = st.session_state.setdefault("nba_hoy_vistos", set())  # la animación de entrada se ve una sola vez
    for idx, j in enumerate(sorted(juegos, key=lambda x: (orden.get(x["estado"], 3), x["fecha"] or ""))):
        _tarjeta(j, rat, puesto, lesiones, nombres, idx, nuevo=j["id"] not in vistos)
        vistos.add(j["id"])

    # Si ya no queda nada en juego, hace falta una ejecución completa para apagar el temporizador del fragmento.
    if vigilando and not _hay_actividad(juegos):
        st.rerun()


def render(liga=None):
    estilos.cargar("hoy")
    st.session_state["nba_hoy_vistos"] = set()  # ejecución completa: las tarjetas vuelven a entrar animadas
    dia = _hoy_et()
    auto = st.toggle(f"Actualizar automáticamente (cada {INTERVALO_S} s)", value=True,
                     key="nba_hoy_auto", help="Se activa solo cuando hay partidos en juego")
    fecha = f"{dia:%Y%m%d}"
    if liga is None:
        st.warning("Sin datos de la liga: se muestran los partidos sin Elo.")

    rat, puesto = _elo_y_puesto(liga)
    lesiones = _lesiones_por_equipo()
    nombres = nba.equipos().set_index("id")["Equipo"].to_dict()

    try:
        vigilando = auto and _hay_actividad(nba.scoreboard(fecha))
    except Exception:  # noqa: BLE001
        vigilando = False  # el error real lo muestra _cuerpo
    # run_every se fija al crear el fragmento: por eso se decide aquí, en cada ejecución completa.
    fragmento = st.fragment(run_every=INTERVALO_S if vigilando else None)(_cuerpo)
    fragmento(fecha, rat, puesto, lesiones, nombres, vigilando)


def _a_lineas(local_id, visita_id, total):
    """Callback de «Analizar»: deja elegidos en «Líneas» el local (A), la visita (B), el mercado Total y la línea de ESPN.

    Corre antes de dibujar los widgets, por eso puede fijar sus valores. Las claves son las de ficha_equipos.render().
    """
    ss = st.session_state
    ss["nba_ir_a_lineas"] = True                    # nba_panel lleva a la vista «Líneas», donde está el análisis
    ss["fe_a"], ss["fe_b"] = str(local_id), str(visita_id)
    ss.pop("fe_voz_msg", None)                      # el aviso de la voz ya no describe lo elegido
    ss["fe_grupo_mercado"] = "🏀 Puntos"
    ss["fe_mercado_🏀 Puntos"] = "Total de puntos (over/under)"
    if total:
        t = float(total)
        t = t if t % 1 else t + 0.5                 # la línea siempre termina en .5
        ss[f"fe_l5_total_{local_id}_{visita_id}"] = min(max(t, 0.5), 399.5)


_CSS_PROX = """
/* La barra superior fija de Streamlit (invisible) tapaba lo que pasa por debajo al hacer scroll: no dejaba ver la manito ni
   hacer clic en los desplegables. Se vuelve «transparente» al mouse y solo sus botones (menú ⋮) siguen siendo clicables. */
[data-testid="stHeader"]{pointer-events:none !important}
[data-testid="stHeader"] [data-testid="stToolbar"],[data-testid="stHeader"] button,[data-testid="stHeader"] a,
[data-testid="stHeader"] [role="button"]{pointer-events:auto !important}
[data-testid="stExpander"] summary{cursor:pointer !important}
/* Sin marco de enfoque alrededor de toda la pantalla (aparecía al usar el teclado, p. ej. la tecla R). */
html:focus-visible,body:focus-visible,.stApp:focus-visible,[data-testid="stApp"]:focus-visible,[data-testid="stAppViewContainer"]:focus-visible,
[data-testid="stMain"]:focus-visible,[data-testid="stMainBlockContainer"]:focus-visible,[data-testid="stVerticalBlock"]:focus-visible,
section.main:focus-visible,.main:focus-visible,.block-container:focus-visible,[tabindex="-1"]:focus-visible{outline:none !important}
/* Marcos o capas de decoración que cubren toda la pantalla no deben interceptar el mouse (no se veía la manito ni se podía hacer clic). */
.stApp::before,.stApp::after,body::before,body::after,html::before,html::after,
[data-testid="stAppViewContainer"]::before,[data-testid="stAppViewContainer"]::after,
[data-testid="stMain"]::before,[data-testid="stMain"]::after,[data-testid="stDecoration"]{pointer-events:none !important}
/* Barra de scroll siempre visible: la de «overlay» del navegador (transparente) se esconde al acercar el mouse y solo se podía bajar con la rueda. */
html,body,[data-testid="stMain"],[data-testid="stAppViewContainer"],section.main{scrollbar-width:auto !important;scrollbar-color:#6366f1 #e2e8f0 !important}
/* La franja inferior fija de Streamlit (invisible, para el chat) cubre el borde de abajo y tapaba la flecha «bajar» de la barra de scroll;
   igual que la barra superior, se vuelve transparente al mouse. */
[data-testid="stBottom"],[data-testid="stBottomBlockContainer"],[data-testid="stStatusWidget"]{pointer-events:none !important}
[data-testid="stBottom"] button,[data-testid="stBottom"] input,[data-testid="stBottom"] textarea,[data-testid="stBottom"] a,
[data-testid="stBottom"] [role="button"]{pointer-events:auto !important}
::-webkit-scrollbar{width:12px !important;height:12px !important}
::-webkit-scrollbar-track{background:#e2e8f0 !important}
::-webkit-scrollbar-thumb{background:#6366f1 !important;border-radius:8px;border:2px solid #e2e8f0}
::-webkit-scrollbar-thumb:hover{background:#4f46e5 !important}
.st-key-nba_prox_panel{background:#F6F7FB;border:1px solid #E5E7EB;border-radius:16px;padding:14px 16px 10px;
  box-shadow:0 2px 10px -4px rgba(19,10,63,.06)}
[class*="st-key-nba_prox_fila_"]{box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;gap:0 !important;
  height:auto !important;min-height:66px;overflow:visible;background:#fff;border:1px solid #E5E7EB;border-left:4px solid #4F46E5;
  border-radius:16px;padding:14px 18px !important;box-shadow:0 2px 10px -4px rgba(19,10,63,.07);
  transition:box-shadow .16s ease,transform .16s ease,border-color .16s ease}
[class*="st-key-nba_prox_fila_"] > div,[class*="st-key-nba_prox_fila_"] [data-testid="stElementContainer"]{height:auto !important;min-height:0}
[class*="st-key-nba_prox_fila_"]:hover{box-shadow:0 10px 22px -10px rgba(79,70,229,.22);border-color:#C7D2FE;transform:translateY(-1px)}
[class*="st-key-nba_prox_fila_"] [data-testid="stHorizontalBlock"]{gap:.5rem;align-items:center}
[class*="st-key-nba_prox_fila_"] [data-testid="stMarkdownContainer"] p{margin:0}
[class*="st-key-nba_prox_fila_"] [data-testid="stMarkdownContainer"],[class*="st-key-nba_prox_fila_"] [data-testid="stMarkdown"]{margin:0 !important;padding:0 !important}
[class*="st-key-nba_prox_fila_"] [data-testid="stElementContainer"],[class*="st-key-nba_prox_fila_"] [data-testid="stHorizontalBlock"]{margin:0 !important}
[class*="st-key-nba_prox_fila_"] [data-testid="stVerticalBlock"]{gap:0 !important}
[class*="st-key-nba_prox_fila_"] button{min-height:1.9rem !important;padding:0 .5rem !important;font-size:.78rem !important;
  border-radius:9px !important;box-shadow:none !important}
.px{display:flex;align-items:center;gap:14px;min-height:58px;color:#1e1b4b}
.px-hora{flex:none;text-align:center;padding:7px 13px;margin-right:6px;border-radius:12px;background:linear-gradient(180deg,#f5f7ff,#e8ecff);
  border:1px solid #dde3ff;color:#3730a3;font-weight:800;font-size:.9rem;letter-spacing:.02em;font-variant-numeric:tabular-nums;
  box-shadow:0 1px 2px rgba(67,56,202,.10)}
.px-eq{display:flex;align-items:center;gap:12px;flex:none;min-width:0}
.px-lg,.px-ab{flex:none;width:52px;height:52px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 0 1px rgba(15,23,42,.06),0 6px 14px -6px rgba(15,23,42,.30)}
.px-lg{background:radial-gradient(circle at 30% 25%,#fff,#f1f4f9)}
.px-lg img{width:34px !important;height:34px !important;object-fit:contain;border-radius:0 !important;margin:0 !important}
.px-ab{background:#e0e7ff;font-size:.68rem;font-weight:800;color:#3730a3}
.px-eq span{display:flex;flex-direction:column;line-height:1.2;min-width:0}
.px-eq b{font-size:1.08rem;font-weight:800;letter-spacing:.03em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.px-eq small{font-size:.6rem;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:#7c8798}
.px-eq.loc b{color:#312e81}
.px-at{flex:none;margin:0 -4px;padding:2px 9px;border-radius:99px;border:1px solid #e2e8f0;background:rgba(255,255,255,.85);
  color:#94a3b8;font-weight:700;font-size:.66rem;letter-spacing:.12em;text-transform:uppercase}
.px-lin{flex:none;margin-left:auto;display:flex;flex-direction:column;gap:3px;padding-left:18px;border-left:1px solid #e2e8f0;font-size:.74rem;line-height:1.3;color:#4b5563;text-align:right}
.px-lin b{color:#111827}
.px-lin em{font-style:normal;color:#6b7280}
.px-lin b.px-mas{color:#047857}
.px-lin b.px-menos{color:#b91c1c}
.pr{margin-top:12px;padding:12px 0 2px;border-top:1px dashed #dbe2ee}
.pr-marc{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:14px}
.pr-eq{display:flex;align-items:baseline;gap:10px;color:#64748b}
.pr-eq.der{justify-content:flex-end}
.pr-eq b{font-size:.78rem;letter-spacing:.06em}
.pr-pts{font-size:1.7rem;font-weight:800;line-height:1;color:#64748b;font-variant-numeric:tabular-nums}
.pr-eq.gana,.pr-eq.gana b,.pr-eq.gana .pr-pts{color:#312e81}
.pr-mid{text-align:center;font-size:.68rem;letter-spacing:.05em;text-transform:uppercase;color:#64748b;line-height:1.35}
.pr-mid strong{display:block;font-size:.84rem;letter-spacing:0;text-transform:none;color:#111827}
.pr-bar{display:flex;height:6px;margin:9px 0 8px;border-radius:99px;overflow:hidden;background:#e2e8f0}
.pr-bar i{display:block;height:100%;background:linear-gradient(90deg,#6366f1,#818cf8)}
.pr-bar i.v{background:#94a3b8}
.pr-chips{display:flex;flex-wrap:wrap;gap:6px}
.pr-chip{padding:3px 10px;border-radius:99px;font-size:.7rem;font-weight:600;background:#f1f5f9;color:#334155;border:1px solid #e2e8f0}
.pr-chip.ok{background:#ecfdf5;color:#047857;border-color:#a7f3d0}
.pr-chip.no{background:#fef2f2;color:#b91c1c;border-color:#fecaca}
.pr-chip.med{background:#fffbeb;color:#b45309;border-color:#fde68a}
.pr-bajas{margin-top:8px;padding-bottom:2px;font-size:.7rem;line-height:1.5;color:#64748b}
.pr-bajas b{color:#334155}
.pr-bajas em{font-style:normal;color:#94a3b8}
.pr-bajas img.pr-esc{display:inline-block !important;width:16px !important;height:16px !important;min-width:0 !important;max-width:16px !important;max-height:16px !important;margin:0 4px 0 0 !important;padding:0 !important;border-radius:0 !important;object-fit:contain;vertical-align:-3px}
.pr-bj{display:inline-block;margin-right:2px;padding:0 6px;border-radius:6px;font-size:.62rem;font-weight:800;letter-spacing:.03em}
.pr-bj.out{background:#fee2e2;color:#b91c1c}
.pr-bj.dtd{background:#fef3c7;color:#b45309}
.pk{margin-top:12px;padding-top:10px;border-top:1px dashed #dbe2ee}
.pk-cols{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media (max-width:900px){.pk-cols{grid-template-columns:1fr}}
.pk-tit{font-size:.66rem;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:#475569;margin-bottom:6px}
.pk-lista{display:flex;flex-direction:column;gap:5px}
.pk-it{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:5px 10px;border-radius:10px;font-size:.74rem;
  background:#f8fafc;border:1px solid #e2e8f0;color:#334155}
.pk-it b{color:#111827}
.pk-it .pk-p{flex:none;font-weight:800;font-variant-numeric:tabular-nums}
.pk-it.alto{background:#ecfdf5;border-color:#a7f3d0}.pk-it.alto .pk-p{color:#047857}
.pk-it.med{background:#fffbeb;border-color:#fde68a}.pk-it.med .pk-p{color:#b45309}
.pk-it.riesgo{background:#fef2f2;border-color:#fecaca}.pk-it.riesgo .pk-p{color:#b91c1c}
.pk-it em{font-style:normal;color:#64748b;font-size:.68rem}
.pk-as{display:block;margin-top:3px;font-size:.68rem;line-height:1.4;color:#334155}
.esc-b{padding:8px 4px;font-size:.74rem;line-height:1.5;color:#334155}
.esc-b h5{margin:8px 0 2px;font-size:.68rem;letter-spacing:.05em;text-transform:uppercase;color:#475569}
.esc-b ul{margin:0;padding-left:18px}
.esc-g{display:grid;grid-template-columns:repeat(auto-fit,minmax(92px,1fr));gap:6px}
.esc-g div{background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:6px 8px;text-align:center}
.esc-g b{display:block;font-size:1rem;color:#9a3412}.esc-g span{font-size:.64rem;color:#7c2d12}
.esc-n{margin-top:8px;font-size:.66rem;color:#64748b}
.pk-ana{display:block;margin-top:5px}
.pk-ana>summary{cursor:pointer;font-size:.7rem;font-weight:700;color:#4338ca;list-style:none}
.pk-ana>summary::-webkit-details-marker{display:none}
.pk-ana .an{margin-top:5px;padding:8px 10px;border-radius:10px;background:#f8fafc;border:1px solid #e2e8f0;font-size:.7rem;line-height:1.5;color:#334155}
.pk-ana .an h5{margin:6px 0 2px;font-size:.68rem;letter-spacing:.05em;text-transform:uppercase;color:#475569}
.pk-ana .an h5:first-child{margin-top:0}
.pk-ana .an ul{margin:0;padding-left:16px}
.pk-ana .an li.no{color:#92400e}
.pk-ana .gr{display:inline-block;padding:0 7px;border-radius:999px;font-weight:800;font-size:.66rem;margin-left:4px}
.pk-ana .gr.Fuerte{background:#d1fae5;color:#065f46}.pk-ana .gr.Medio{background:#fef3c7;color:#92400e}.pk-ana .gr.Arriesgado{background:#fee2e2;color:#991b1b}
.pk-ana .cu{margin-top:6px;padding:6px 8px;border-radius:8px;background:#eef2ff;color:#312e81}
.pk-as.ok{color:#047857}.pk-as.reservas{color:#92400e}.pk-as.poco{color:#b91c1c;font-weight:600}
.pk-nota{margin-top:6px;font-size:.7rem;line-height:1.45;color:#92400e;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:5px 10px}
.pk-nota b{color:#78350f}
.pk-vacio{font-size:.7rem;color:#94a3b8}
.hx-g{margin-top:10px;padding:10px 12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff}
.hx-h{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.hx-f{font-size:.72rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#475569}
.hx-f small{display:block;font-weight:600;letter-spacing:0;text-transform:none;color:#94a3b8;font-size:.66rem}
.hx-m{display:grid;grid-template-columns:1fr 22px 1fr;align-items:center;justify-items:center;width:100%;max-width:340px;margin:0 auto}
.hx-m>.hx-e:first-child{justify-self:end}.hx-m>.hx-e:last-child{justify-self:start}
.hx-e{display:flex;align-items:center;gap:7px;font-size:.8rem;color:#475569;font-weight:700}
.hx-e b{font-size:1.15rem;font-variant-numeric:tabular-nums;color:#64748b}
.hx-e.gana b,.hx-e.gana{color:#111827}
.hx-lg{flex:none;width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  background:radial-gradient(circle at 30% 25%,#fff,#f1f4f9);border:1px solid #e2e8f0;font-size:.62rem;font-weight:800;color:#475569}
.hx-lg img{width:24px !important;height:24px !important;object-fit:contain;margin:0 !important;border-radius:0 !important}
.hx-sc{margin-bottom:10px;border-radius:14px;border:1px solid #0f172a;overflow:hidden;box-shadow:0 2px 8px rgba(15,23,42,.18)}
.hx-sr{display:grid;grid-template-columns:116px 1fr 168px;align-items:center;gap:10px;padding:10px 14px}
.hx-sr>.hx-ch{justify-self:end}
.hx-et{font-size:.62rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase}
.hx-sr.res{background:linear-gradient(135deg,#0f172a,#1e293b);color:#fff}
.hx-sr.res .hx-et{color:#94a3b8}
.hx-sr.res .hx-e,.hx-sr.res .hx-e b{color:#fff}
.hx-sr.res .hx-e:not(.gana),.hx-sr.res .hx-e:not(.gana) b{color:#cbd5e1}
.hx-sr.res .hx-g{margin-top:22px !important;padding:14px 16px !important;border:1.5px solid #cbd5e1 !important;box-shadow:0 2px 10px rgba(15,23,42,.08)}
.hx-g .hx-h{padding-bottom:10px;margin-bottom:12px;border-bottom:1.5px solid #e2e8f0}
.hx-g .hx-v{padding:2px 0 14px;margin-bottom:14px;border-bottom:1.5px solid #e2e8f0}
.hx-g .pk-cols>div{padding:10px 12px 12px;border:1px solid #cbd5e1;border-radius:14px;background:#fbfcfe}
.hx-g .pk-tit.hx-t,.hx-g .pk-cols>div>.pk-tit{padding-bottom:8px;margin-bottom:10px;border-bottom:1px solid #e2e8f0}
.hx-v{gap:10px !important}
.hx-vc{flex:1 1 190px;display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:14px;border:1.5px solid;border-left-width:5px}
.hx-vc.ok{background:#ecfdf5;border-color:#34d399}.hx-vc.no{background:#fef2f2;border-color:#f87171}.hx-vc.med{background:#fffbeb;border-color:#fbbf24}
.hx-vi{flex:none;width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.15rem;font-weight:900;color:#fff}
.hx-vc.ok .hx-vi{background:#059669}.hx-vc.no .hx-vi{background:#dc2626}.hx-vc.med .hx-vi{background:#d97706}
.hx-vt{display:flex;flex-direction:column;line-height:1.25;min-width:0}
.hx-vt small{font-size:.64rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#64748b}
.hx-vt b{font-size:1.08rem;font-weight:800;color:#0f172a;display:flex;align-items:center;gap:7px}
.hx-vt em{font-style:normal;font-size:.76rem;font-weight:700}
.hx-vc.ok .hx-vt em{color:#047857}.hx-vc.no .hx-vt em{color:#b91c1c}.hx-vc.med .hx-vt em{color:#b45309}
.hx-ex{display:flex;flex-direction:column;align-items:flex-end;line-height:1.2;padding:6px 14px;border-radius:12px;border:1.5px solid}
.hx-ex small{font-size:.6rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase;opacity:.85}
.hx-ex b{font-size:1rem;font-weight:800}
.hx-ex.no{background:#fef2f2;border-color:#f87171;color:#b91c1c}.hx-ex.ok{background:#ecfdf5;border-color:#34d399;color:#047857}
.hx-sep{color:#475569}
.hx-sr.res .pr-chip{background:rgba(255,255,255,.1);color:#e2e8f0;border-color:rgba(255,255,255,.2)}
.hx-sr.sim{background:#eef2ff;border-bottom:2px dashed #a5b4fc}
.hx-sr.sim .hx-et{color:#4f46e5}
.hx-sr.sim .hx-e,.hx-sr.sim .hx-e b{color:#4338ca;font-weight:600}
.hx-sr.sim .hx-e b{font-style:italic}
.hx-sr.sim .hx-sep{color:#a5b4fc}
.hx-sc,.hx-sc .hx-e,.hx-sc .hx-et{font-family:'Roboto Condensed','Roboto',sans-serif !important}
.hx-sc .hx-e{letter-spacing:.04em}
.hx-sr .hx-e b{font-size:1.45rem;font-weight:600;letter-spacing:.02em;min-width:3.4ch;text-align:center}
.hx-sr .hx-e{min-width:0}
.hx-m>.hx-e{width:100%}
.hx-m>.hx-e:first-child{justify-content:flex-end}.hx-m>.hx-e:last-child{justify-content:flex-start}
.hx-sr .pr-chip{font-size:.68rem;white-space:nowrap}
@media (max-width:700px){.hx-sr{grid-template-columns:1fr;justify-items:center;gap:6px}.hx-sr>.hx-ch{justify-self:center}.hx-et{justify-self:start}}
.pk-tit.hx-t{display:flex !important;flex-direction:row !important;align-items:center;gap:7px}
.pk-tit.hx-t .hx-lg{width:28px !important;height:28px !important;font-size:.52rem}
.pk-fc{flex:none;position:relative;width:30px;height:30px;border-radius:50%;overflow:hidden;background:#e2e8f0;border:1px solid #cbd5e1;
  display:flex;align-items:center;justify-content:center;font-size:.55rem;font-weight:800;color:#64748b}
.pk-it .pk-q{display:flex !important;flex-direction:row !important;align-items:center;gap:8px;min-width:0}
.hx-sep{color:#cbd5e1;font-weight:700}
.hx-v{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.hx-v .pr-chip{font-size:.7rem}
.hx-r{margin-left:auto;font-size:.7rem;font-weight:700;color:#64748b}
.pk-it.hit{background:#ecfdf5;border-color:#86efac}
.pk-it.fail{background:#fef2f2;border-color:#fca5a5}
.pk-it.dnp{background:#f1f5f9;border-color:#e2e8f0;opacity:.75}
.pk-it .pk-r{flex:none;display:flex;align-items:center;gap:8px}
.pk-it .pk-m{font-weight:800;font-size:.68rem;white-space:nowrap}
.pk-it.hit .pk-m{color:#047857}.pk-it.fail .pk-m{color:#b91c1c}.pk-it.dnp .pk-m{color:#64748b}
.pk-it.hit .pk-p,.pk-it.fail .pk-p,.pk-it.dnp .pk-p{color:#64748b;font-weight:700}
.pk-nota.pal{margin-top:10px;color:#991b1b;background:#fef2f2;border-color:#fecaca}
.sp{margin-top:6px;border:1px solid #fecaca;border-radius:10px;background:#fff;padding:6px 10px}
.sp summary{cursor:pointer;font-size:.74rem;font-weight:800;color:#991b1b}
.sp-n{margin:8px 0 10px;font-size:.74rem;line-height:1.55;color:#334155}
.sp-n b{color:#0f172a}
.sp-f{margin-top:10px;font-size:.66rem;line-height:1.45;color:#64748b}
.sp-t{width:100%;border-collapse:collapse;font-size:.7rem;font-variant-numeric:tabular-nums}
.sp-t th{font-size:.6rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#64748b;text-align:center;padding:2px 4px}
.sp-t td{text-align:center;padding:3px 4px;border-top:1px solid #eef2f7;color:#334155}
.sp-t td.n{text-align:left;font-weight:700;color:#0f172a;white-space:nowrap}
.sp-t .ok{color:#047857;font-weight:700}.sp-t .mal{color:#b91c1c;font-weight:700}
.pk-nota.cor{color:#1e3a8a;background:#eff6ff;border-color:#bfdbfe}
.pk-it .pk-cor{margin-left:4px;font-size:.7rem}
/* Contexto del partido: estética ScoreLine limpia, sin desbordes y responsiva */
.cx{margin-top:12px;padding:12px 14px 14px;border-radius:16px;background:#F6F7FB;border:1px solid #E5E7EB}
.cx-tit{display:flex;align-items:center;gap:6px;font-family:'Roboto Condensed',sans-serif;font-size:.76rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#15103F;margin-bottom:10px}
.cx-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.cx-b{min-width:0;padding:12px 14px;border-radius:14px;background:#fff;border:1px solid #E5E7EB;border-top:3px solid #4F46E5;
  box-shadow:0 2px 10px -4px rgba(19,10,63,.07);font-size:.76rem;line-height:1.5;color:#334155}
.cx-b.ancho{grid-column:1 / -1}
.cx-h{font-family:'Roboto Condensed',sans-serif;font-size:.74rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#15103F;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #ECEEF5}
@media (max-width:768px){
  .px{flex-wrap:wrap;gap:10px}
  .px-lin{margin-left:0;padding-left:0;border-left:0;text-align:left;width:100%}
  .cx-grid{grid-template-columns:1fr}
  .pf-2{grid-template-columns:1fr !important}
  .pf-r{grid-template-columns:minmax(0,1fr) auto !important}
}
.cx-b b{color:#0f172a}
.cx-b em{font-style:normal;color:#64748b}
.cx-f{display:flex;flex-wrap:wrap;align-items:center;gap:5px 6px;margin:3px 0}
.cx-pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:.66rem;font-weight:700;background:#eef2f7;color:#334155;border:1px solid #cbd5e1}
.cx-pill.mal{background:#fee2e2;color:#991b1b;border-color:#fca5a5}
.cx-pill.bien{background:#dcfce7;color:#166534;border-color:#86efac}
.cx-pill.med{background:#fef3c7;color:#92400e;border-color:#fcd34d}
.cx-q{display:grid;grid-template-columns:38px repeat(5,1fr);gap:0;text-align:center;font-variant-numeric:tabular-nums;margin:2px 0 8px;
  border:1px solid #e2e8f0;border-radius:10px;overflow:hidden}
.cx-q span{padding:5px 0;border-bottom:1px solid #e8edf4;color:#334155}
.cx-q span:nth-last-child(-n+6){border-bottom:0}
.cx-q span:first-child,.cx-q .l{text-align:left;padding-left:9px;font-weight:800;color:#0f172a}
.cx-q span:nth-child(-n+6){background:#eef2f7}
.cx-q .h{font-size:.62rem;font-weight:800;color:#475569;letter-spacing:.06em}
.cx-q .t{font-weight:800;color:#3730a3;background:#eef2ff}
.cx-q span:nth-child(6){background:#e0e7ff;color:#3730a3}
/* Análisis profundo: forma, jugadores en foco, bajas y regresos, emparejamientos */
.pf-eq{font-size:.7rem;font-weight:800;color:#0f172a;margin:6px 0 2px;letter-spacing:.04em}
.pf-eq:first-of-type{margin-top:0}
.pf-r{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1.3fr) auto;gap:2px 10px;align-items:center;padding:4px 0;border-bottom:1px dashed #e2e8f0}
.pf-r:last-child{border-bottom:0}
.pf-n{font-weight:700;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pf-sp{display:inline-flex;align-items:flex-end;gap:2px;height:16px;margin-left:6px;vertical-align:middle}
.pf-sp i{display:block;width:5px;border-radius:2px 2px 0 0;background:#a5b4fc;min-height:2px}
.pf-sp i:last-child{background:#6366f1}
.pf-up{color:#047857;font-weight:700}.pf-dn{color:#b91c1c;font-weight:700}
.pf-2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:4px 22px}
.pf-b{padding:5px 0 6px;border-bottom:1px dashed #e2e8f0}
.pf-b:last-child{border-bottom:0}
.pf-s{font-size:.7rem;color:#475569;line-height:1.5}
.pf-m{padding:6px 0;border-bottom:1px dashed #e2e8f0}
.pf-m:last-of-type{border-bottom:0}
.pf-par{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:4px 10px;align-items:center}
.pf-par .d{text-align:right}
.pf-vs{font-size:.62rem;font-weight:800;color:#94a3b8;letter-spacing:.08em}
.pf-pos{display:inline-block;min-width:26px;text-align:center;padding:0 5px;margin-right:5px;border-radius:6px;font-size:.62rem;font-weight:800;background:#e0e7ff;color:#3730a3}
.pf-chips{display:flex;flex-wrap:wrap;gap:4px 6px;margin-top:3px}
.ok{color:#047857;font-weight:700}.mal{color:#b91c1c;font-weight:700}
.hp-tit{font-size:.7rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#475569;margin:14px 0 4px}
.hp-ok{color:#047857;font-weight:700}.hp-no{color:#b91c1c;font-weight:700}

"""


# --- Pronóstico: puntos de cada equipo según su rendimiento reciente y sus bajas ---------------------------------
_VENTANA = 15            # últimos partidos de cada equipo
_VENTAJA_LOCAL = 1.2     # puntos que se suman al local y se restan a la visita (≈ 2.4 de diferencia)
_SD_MARGEN = 12.0        # desviación típica del margen de un partido NBA (para pasar de margen a probabilidad)
_SD_TOTAL = 18.0         # desviación típica del total de puntos de un partido (para la probabilidad de Más/Menos)
_PROB_BAJA = {"out": 1.0, "doubtful": 0.85, "questionable": 0.5, "day-to-day": 0.3}   # probabilidad de no jugar


def _pond(serie, clave):
    """Promedio donde el partido más reciente pesa 1 y cada anterior un 10 % menos; None si no hay dato."""
    n = len(serie)
    pares = [(g[clave], 0.9 ** (n - 1 - i)) for i, g in enumerate(serie) if g.get(clave) is not None]
    return sum(v * w for v, w in pares) / sum(w for _, w in pares) if pares else None


def _jugadores_ventana(serie, team_id, cajas=None):
    """{nombre normalizado: {nombre, ppg, mpg, pres}} con lo que hizo cada jugador del equipo en la ventana.

    pres = fracción de los partidos de la ventana en que jugó (si faltó mucho, el promedio del equipo ya refleja su ausencia).
    """
    if cajas is None:
        cajas = _cajas(serie)
    tid, acum, validas = str(team_id), {}, 0
    for g, c in zip(serie, cajas):
        jug = [x for x in (c or {}).get("jugadores", []) if x.get("team_id") == tid and (x.get("MIN") or 0) > 0]
        if len(jug) < 5:        # box score incompleto: no se cuenta
            continue
        idx, validas = validas, validas + 1
        pf, pc = g.get("pf"), g.get("pc")
        mg = abs(pf - pc) if pf is not None and pc is not None else None   # diferencia final de ese partido
        for x in jug:
            a = acum.setdefault(normalizar(x.get("Jugador", "")),
                                {"nombre": x.get("Jugador", ""), "pts": 0.0, "min": 0.0, "pj": 0, "juegos": []})
            a["pts"] += x.get("PTS") or 0
            a["min"] += x.get("MIN") or 0
            a["pj"] += 1
            # PTS/REB/AST/3PM de ese partido; ev = número de partido (para saber cuándo faltó un compañero), mg = diferencia final
            a["juegos"].append({**{s: _valor(x, s) for s in _CLAVES}, "ev": idx, "mg": mg, "loc": g.get("sede") == "home"})
    return {k: {"nombre": a["nombre"], "ppg": a["pts"] / a["pj"], "mpg": a["min"] / a["pj"], "pres": a["pj"] / validas,
                "juegos": a["juegos"], "n": validas}
            for k, a in acum.items() if validas and a["pj"]}


def _cajas(serie):
    """Box scores (en paralelo) de los partidos de una serie; None donde ESPN no entrega uno."""
    import ficha_equipos as fe
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda g: fe._caja(g["evento"]), serie))


# --- Ajuste por rival: cuánto concede cada equipo de puntos, rebotes, asistencias y triples -------------------------
_EQ_KEY = {"REB": "reb", "AST": "ast", "3PM": "tpm"}      # claves del box score de equipo (PTS sale del marcador)


def _perfil_equipo(serie, cajas, team_id):
    """{'for': {stat: [por partido]}, 'ag': {stat: [por partido]}}: lo que el equipo hizo y lo que permitió a sus rivales."""
    tid = str(team_id)
    out = {"for": {s: [] for s in _CLAVES}, "ag": {s: [] for s in _CLAVES}}
    for g, c in zip(serie, cajas):
        eq = (c or {}).get("equipos") or {}
        own, riv = eq.get(tid), next((v for k, v in eq.items() if k != tid), None)
        if g.get("pf") is not None and g.get("pc") is not None:
            out["for"]["PTS"].append(g["pf"])
            out["ag"]["PTS"].append(g["pc"])
        if own and riv:
            for s, k in _EQ_KEY.items():
                if own.get(k) is not None and riv.get(k) is not None:
                    out["for"][s].append(own[k])
                    out["ag"][s].append(riv[k])
    return out


def _factores_rival(perfil_rival, perfiles):
    """{stat: factor} para los jugadores que enfrentan a ese rival.

    factor = lo que el rival concede / promedio de todos los partidos mirados (de ambos equipos). Se suaviza (solo se
    toma el 60 % de la desviación) y se limita a ±12 %, porque con 15 partidos hay mucho ruido."""
    res = {}
    for s in _CLAVES:
        todos = [v for p in perfiles for lado in ("for", "ag") for v in p[lado][s]]
        ag = perfil_rival["ag"][s]
        if len(ag) < 5 or not todos or sum(todos) <= 0:
            res[s] = 1.0
            continue
        raw = (sum(ag) / len(ag)) / (sum(todos) / len(todos))
        res[s] = max(0.88, min(1.12, 1 + 0.6 * (raw - 1)))
    return res


# --- Contexto del partido: descanso y viaje, ritmo, cuartos, línea contra el historial y cara a cara ------------------
_AJ_B2B, _AJ_3EN4, _AJ_VIAJE = -1.3, -0.7, -0.5   # puntos que se restan al equipo (back-to-back, 3 en 4 noches, viaje largo)
_KM_VIAJE_LARGO = 2000                              # desde aquí un viaje con poco descanso pesa
_RITMO_LIGA = 99.5       # posesiones por 48 min de un partido «normal»; solo sirve para poner la etiqueta rápido / lento
# Sede de cada equipo: (latitud, longitud, huso horario respecto del Este: 0 = ET, -1 = CT, -2 = MT, -3 = PT)
_SEDES = {
    "ATL": (33.76, -84.40, 0), "BOS": (42.37, -71.06, 0), "BKN": (40.68, -73.98, 0), "CHA": (35.23, -80.84, 0),
    "CHI": (41.88, -87.67, -1), "CLE": (41.50, -81.69, 0), "DAL": (32.79, -96.81, -1), "DEN": (39.75, -105.01, -2),
    "DET": (42.34, -83.06, 0), "GS": (37.77, -122.39, -3), "HOU": (29.75, -95.36, -1), "IND": (39.76, -86.16, 0),
    "LAC": (34.04, -118.27, -3), "LAL": (34.04, -118.27, -3), "MEM": (35.14, -90.05, -1), "MIA": (25.78, -80.19, 0),
    "MIL": (43.05, -87.92, -1), "MIN": (44.98, -93.28, -1), "NO": (29.95, -90.08, -1), "NY": (40.75, -73.99, 0),
    "OKC": (35.46, -97.52, -1), "ORL": (28.54, -81.38, 0), "PHI": (39.90, -75.17, 0), "PHX": (33.45, -112.07, -2),
    "POR": (45.53, -122.67, -3), "SAC": (38.58, -121.50, -3), "SA": (29.43, -98.44, -1), "TOR": (43.64, -79.38, 0),
    "UTAH": (40.77, -111.90, -2), "WSH": (38.90, -77.02, 0),
}


def _sede(ab):
    return _SEDES.get(_ALIAS_ABREV.get(str(ab).upper(), str(ab).upper()))


def _viaje(desde, hasta):
    """(km, horas de huso) entre dos sedes; (0, 0) si alguna no se conoce."""
    a, b = _sede(desde), _sede(hasta)
    if not a or not b:
        return 0.0, 0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h)), b[2] - a[2]


def _fatiga(completos, dia, es_local, abrev, rival_abrev):
    """Descanso, carga de partidos y viaje del equipo para el partido del día `dia`; None si no hay historial.

    completos = partidos terminados del equipo (de ficha_equipos._partidos). aj = puntos que se restan por cansancio."""
    import ficha_equipos as fe
    prev = sorted(((fe._fecha_et(g["fecha"]), g) for g in completos), key=lambda x: (x[0] is None, x[0]))
    prev = [(f, g) for f, g in prev if f and f < dia]
    if not prev:
        return None
    f_ult, g_ult = prev[-1]
    desc = (dia - f_ult).days - 1
    desc = desc if 0 <= desc <= 10 else None
    g7 = sum(1 for f, _ in prev if 0 < (dia - f).days <= 7)
    g4 = sum(1 for f, _ in prev if 0 < (dia - f).days <= 3)     # partidos en las 3 noches anteriores
    ult = abrev if g_ult.get("sede") == "home" else g_ult.get("rival", "")
    km, dh = _viaje(ult, abrev if es_local else rival_abrev)
    fuera = 0
    for _, g in reversed(prev):
        if g.get("sede") == "home":
            break
        fuera += 1
    b2b, tres4 = desc == 0, g4 >= 2
    aj = (_AJ_B2B if b2b else 0.0) + (_AJ_3EN4 if tres4 else 0.0)
    if km >= _KM_VIAJE_LARGO and desc is not None and desc <= 1:
        aj += _AJ_VIAJE
    return {"desc": desc, "g7": g7, "g4": g4, "b2b": b2b, "tres4": tres4, "km": km, "dh": dh, "desde": ult, "gira": fuera,
            "aj": aj}


def _ritmo_esperado(sl, sv):
    """Ritmo del partido (promedio de los dos equipos) y cuánto cambia lo que cada equipo suele hacer; None sin datos."""
    a, b = _pond(sl, "ritmo"), _pond(sv, "ritmo")
    if a is None or b is None:
        return None
    pos = (a + b) / 2
    med = lambda s: (lambda v: sum(v) / len(v))([g["ritmo"] for g in s if g.get("ritmo") is not None])
    f = lambda m: max(0.93, min(1.07, (pos / m) ** 0.8))       # los conteos suben algo menos que las posesiones
    cat = "rápido" if pos >= _RITMO_LIGA + 1.5 else "lento" if pos <= _RITMO_LIGA - 1.5 else "normal"
    return {"pos": pos, "cat": cat, "f_l": f(med(sl)), "f_v": f(med(sv)), "m_l": med(sl), "m_v": med(sv)}


def _correlados(picks, ab):
    """Avisos de picks de un equipo que dependen de lo mismo y se caen juntos. Marca esos picks con c['corr'] = True."""
    motivo = {"AST": "que el equipo juegue fluido y le entren los tiros", "REB": "que haya muchos tiros fallados y buen ritmo",
              "3PM": "que el equipo tire de tres con buen acierto", "PTS": "el ritmo del partido y que no sea paliza"}
    notas, por_stat, por_jug = [], {}, {}
    for c in picks or []:
        por_stat.setdefault(c["stat"], []).append(c)
        por_jug.setdefault(c["nombre"], []).append(c)
    for s, lst in por_stat.items():          # misma estadística: dependen del mismo guion del partido
        if len(lst) >= 2:
            for c in lst:
                c["corr"] = True
            apellidos = ", ".join(dict.fromkeys(c["nombre"].split()[-1] for c in lst))
            notas.append(f"🔗 {len(lst)} picks de {_NOM_STAT[s]} de {_e(ab)} ({_e(apellidos)}) dependen de lo mismo: "
                         f"{motivo[s]}. Si eso falla, caen juntos: no los trates como independientes.")
    repetidos = [n for n, lst in por_jug.items() if len(lst) >= 2]     # mismo jugador: dependen de sus minutos
    for n in repetidos:
        for c in por_jug[n]:
            c["corr"] = True
    if repetidos:
        notas.append(f'🔗 {_e(" y ".join(repetidos))} {"aparece" if len(repetidos) == 1 else "aparecen"} 2 veces: '
                     f'ambos picks dependen de que juegue sus minutos de siempre.')
    return notas[:2]


def _prom(v, minimo=5):
    return sum(v) / len(v) if len(v) >= minimo else None


def _cuartos_proy(sl, sv, pts_l, pts_v):
    """Puntos proyectados por cuarto (ataque propio y lo que concede el rival en ese cuarto) y rasgos de cada equipo."""
    col = lambda serie, k: [g[k] for g in serie if g.get(k) is not None]
    ql, qv = [], []
    for k in (1, 2, 3, 4):
        a, b = _prom(col(sl, f"pq{k}")), _prom(col(sv, f"r_q{k}"))
        c, d = _prom(col(sv, f"pq{k}")), _prom(col(sl, f"r_q{k}"))
        if None in (a, b, c, d):
            return None
        ql.append((a + b) / 2)
        qv.append((c + d) / 2)
    sl_, sv_ = sum(ql), sum(qv)
    if sl_ <= 0 or sv_ <= 0:
        return None
    wl, wv = [x / sl_ for x in ql], [x / sv_ for x in qv]                      # forma de los cuartos (suma 1)
    rasgos = lambda s: {"g1": _prom(col(s, "gq1")), "g4": _prom(col(s, "gq4")),
                        "mejora": (lambda a, b: None if a is None or b is None else b - a)(_prom(col(s, "gh1")), _prom(col(s, "gh2")))}
    return _cuartos_enteros({"wl": wl, "wv": wv, "rl": rasgos(sl), "rv": rasgos(sv)}, pts_l, pts_v)


def _repartir_entero(pesos, total):
    """Reparte `total` (entero) entre los cuartos según `pesos` sin perder ni sobrar un punto (mayor resto)."""
    total = int(round(total))
    cuota = [w * total for w in pesos]
    base = [math.floor(x) for x in cuota]
    for i in sorted(range(len(cuota)), key=lambda i: -(cuota[i] - base[i]))[:total - sum(base)]:
        base[i] += 1
    return base


def _cuartos_enteros(cq, pts_l, pts_v):
    """Cuartos en puntos enteros que suman EXACTAMENTE el marcador que se muestra (el mismo redondeo que la tarjeta).

    Se llama con el marcador final (ya anclado al mercado), para que los cuartos, las mitades y el marcador nunca se contradigan."""
    if not cq:
        return cq
    wl = cq.get("wl") or [x / max(sum(cq["ql"]), 1e-9) for x in cq["ql"]]      # pronósticos viejos en caché no traen los pesos
    wv = cq.get("wv") or [x / max(sum(cq["qv"]), 1e-9) for x in cq["qv"]]
    return {**cq, "wl": wl, "wv": wv, "ql": _repartir_entero(wl, round(pts_l)), "qv": _repartir_entero(wv, round(pts_v))}


_TOPE_AJ_TOTAL = 5.0     # los ajustes de «partido de más / menos puntos» no mueven el total más de esto


def _ajuste_total(sl, sv, hist_l, hist_v, aj_l, aj_v):
    """(puntos extra al total, motivos en texto, residuos reales de totales) a partir de lo que de verdad pasó.

    · tendencia: si los últimos 5 partidos de los dos equipos tuvieron más (o menos) puntos que su promedio de 15, se sigue
      una parte (30 %).
    · línea: si los dos equipos vienen pasándose (o quedándose cortos) de la línea del mercado en sus últimos 10, se suma una parte.
    · cansancio: el equipo cansado ataca peor, pero también defiende peor: el rival se lleva un poco de esos puntos.
    Los residuos son «total de cada partido − promedio de su equipo»: la forma real (con sus partidos de 250) de cómo varía el total."""
    extra, motivos, res = 0.0, [], []
    tend = []
    for nom, serie in (("local", sl), ("visita", sv)):
        tots = [g["pf"] + g["pc"] for g in serie if g.get("pf") is not None and g.get("pc") is not None]
        if len(tots) >= 8:
            m = sum(tots) / len(tots)
            res += [x - m for x in tots]
            if len(tots) >= 10:
                tend.append(sum(tots[-5:]) / 5 - m)
    if len(tend) == 2:
        x = 0.30 * (sum(tend) / 2)
        extra += x
        if abs(x) >= 0.8:
            motivos.append(f'sus últimos 5 partidos tuvieron {abs(sum(tend) / 2):.0f} puntos {"más" if x > 0 else "menos"} que su promedio '
                           f'({x:+.1f} al total)')
    (o1, n1), (o2, n2) = hist_l["over"], hist_v["over"]
    if n1 >= 6 and n2 >= 6:
        tasa = (o1 / n1 + o2 / n2) / 2
        x = 0.6 * (tasa - 0.5) * 10
        extra += x
        if abs(x) >= 0.8:
            motivos.append(f'en sus últimos 10 partidos pasaron la línea de total {o1}/{n1} (local) y {o2}/{n2} (visita) '
                           f'veces ({x:+.1f} al total)')
    x = 0.4 * (max(0.0, -aj_l) + max(0.0, -aj_v))
    if x >= 0.3:
        extra += x
        motivos.append(f'el equipo cansado también defiende peor ({x:+.1f} al total)')
    return max(-_TOPE_AJ_TOTAL, min(_TOPE_AJ_TOTAL, extra)), motivos, [round(r, 1) for r in res]


def _escenario_total(t, m, res, lt, seed):
    """Distribución realista del total y de los partidos que se disparan o se apagan.

    Se toma el total proyectado y se le suma la variación REAL de los totales de los dos equipos (remuestreo de sus últimos
    partidos), no una campana simétrica: así los partidos de 250 puntos tienen la probabilidad que de verdad tienen."""
    if not res or len(res) < 12:
        return None
    rng = np.random.default_rng(zlib.crc32(str(seed).encode()))
    r = np.array(res, dtype=float)
    r = r - r.mean()
    sd = float(r.std()) or 1.0
    r = r * (min(max(sd, 16.0), 20.0) / sd)              # dispersión creíble de un total NBA, conservando la forma
    sims = t + rng.choice(r, 20000) + rng.normal(0, 3.0, 20000)
    q = lambda x: float(np.percentile(sims, x))
    alto, bajo = sims[sims >= q(75)].mean(), sims[sims <= q(25)].mean()
    out = {"p10": q(10), "p50": q(50), "p90": q(90), "p240": float((sims >= 240).mean()), "p250": float((sims >= 250).mean()),
           "p210": float((sims <= 210).mean()), "alto": float(alto), "bajo": float(bajo), "m": m, "lt": lt,
           "p_mas": None, "p_mas10": None, "p_menos10": None}
    if lt:
        out.update(p_mas=float((sims > lt).mean()), p_mas10=float((sims >= lt + 10).mean()), p_menos10=float((sims <= lt - 10).mean()))
    return out


def _historial_linea(serie, cajas, team_id, n=10):
    """Cuántas veces cubrió el hándicap y fue Más/Menos en sus últimos n partidos con línea guardada."""
    tid, ats, ou = str(team_id), [], []
    pares = [(g, c) for g, c in zip(serie, cajas) if c][-n:]
    for g, c in pares:
        esp = c.get("spread_local")
        es_local = c.get("home_id") == tid if c.get("home_id") else g.get("sede") == "home"
        esp_eq = None if esp is None else (esp if es_local else -esp)
        a, o = nba_extra.veredicto_linea(g["pf"] - g["pc"], esp_eq, g["pf"], g["pc"], c.get("total"))
        if a in ("Cubre", "No cubre"):
            ats.append(a == "Cubre")
        if o in ("Over", "Under"):
            ou.append(o == "Over")
    return {"ats": (sum(ats), len(ats)), "over": (sum(ou), len(ou))}


def _cara_a_cara(completos_local, visita_id, dia):
    """Partidos de esta temporada entre los dos equipos, desde la mirada del local: [{fecha, sede, pl, pv}]."""
    import ficha_equipos as fe
    inicio = date(dia.year if dia.month >= 9 else dia.year - 1, 9, 1)
    out = []
    for g in completos_local:
        f = fe._fecha_et(g["fecha"])
        if g.get("rival_id") == str(visita_id) and f and inicio <= f < dia:
            out.append({"fecha": f.isoformat(), "sede": g.get("sede"), "pl": g["pf"], "pv": g["pc"]})
    return sorted(out, key=lambda x: x["fecha"])


def _prob_paliza(margen):
    """Probabilidad de que el partido se decida por _MARGEN_PALIZA puntos o más (con el margen proyectado)."""
    cdf = lambda x: 0.5 * (1 + math.erf(x / _SD_MARGEN / math.sqrt(2)))
    return max(0.0, min(1.0, 1 - (cdf(_MARGEN_PALIZA - margen) - cdf(-_MARGEN_PALIZA - margen))))


# --- Picks de jugadores: puntos, rebotes, asistencias y triples ---------------------------------------------------
# Las claves del box score pueden llamarse distinto según la fuente: se prueban varias. Si el valor viene como «3-8»
# (anotados-intentados) se toma el primer número.
_CLAVES = {"PTS": ("PTS",), "REB": ("REB", "TRB", "Reb"), "AST": ("AST", "Ast"),
           "3PM": ("3PM", "FG3M", "3P", "3PT", "3PTM", "TRIPLES")}
_NOM_STAT = {"PTS": "pts", "REB": "reb", "AST": "ast", "3PM": "triples"}
_LINEA_MIN = {"PTS": 9.5, "REB": 3.5, "AST": 2.5, "3PM": 1.5}   # líneas más bajas que esto no aportan nada
_ABSORBE = 0.75          # de lo que produce un ausente, los compañeros absorben este %
_ESTRELLA_PPG = 15.0     # desde aquí un jugador cuenta como «estrella» del equipo
_PICKS_EQUIPO = 5        # picks que se muestran por equipo
_CONF_MIN = 0.70         # confianza mínima para mostrar un pick
_CONF_MAX = 0.92         # ningún pick de jugador puede prometer más: con ~15 partidos de historial y el azar del baloncesto, 98 % no es creíble
_PRIOR_ACIERTO, _PRIOR_PESO = 0.65, 8   # antes de ver al jugador se asume 65 % (con el peso de 8 partidos): evita 15/15 = 100 %
_SD_MIN_REL = {"PTS": 0.28, "REB": 0.32, "AST": 0.36, "3PM": 0.50}   # desviación mínima (como fracción del promedio) por estadística
_TOPE_BAJAS = 0.35       # las bajas del equipo no pueden mover a un jugador más de este % de su promedio
_PESO_BAJA_EST, _PESO_BAJA_REAL = 0.60, 0.85   # cuánto de ese efecto se cree si es estimado / si se comprobó en partidos sin el ausente
_MIN_PARTIDOS = 8        # historial mínimo del jugador para poder hacerle un pick
_MPG_PICK = 18.0         # minutos mínimos por partido para hacerle un pick
_CV_MIN_MAX = 0.30       # si sus minutos varían más que esto (desv./promedio), su rol es inestable y no se le hace pick
_MARGEN_PALIZA = 15      # un partido decidido por tantos puntos o más es «paliza»: los titulares juegan menos
_AVISO_PALIZA = 0.30     # desde esta probabilidad de paliza se muestra el aviso en la tarjeta


def _valor(x, stat):
    """Valor de una estadística en el box score de un jugador; None si no viene."""
    for k in _CLAVES[stat]:
        v = x.get(k)
        if v is None:
            continue
        if isinstance(v, str):
            v = v.split("-")[0]
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _prob_no_juega(bajas):
    """{nombre normalizado: probabilidad de no jugar} según el estado reportado."""
    out = {}
    for b in bajas or []:
        e = str(b.get("Estado") or "").lower()
        out[normalizar(str(b.get("Jugador", "")))] = 1.0 if "out" in e else next(
            (v for k, v in _PROB_BAJA.items() if k in e), 0.5)
    return out


def _media_stat(d, s, solo=None):
    """Promedio de una estadística de un jugador (solo = conjunto de partidos a considerar; None = todos)."""
    v = [g[s] for g in d["juegos"] if g.get(s) is not None and (solo is None or g["ev"] in solo)]
    return sum(v) / len(v) if v else None


# --- A quién asiste cada jugador (para juzgar si un pick de asistencias es fiable) ---------------------------------
# Una asistencia solo existe si el receptor encesta: si el compañero al que más pasa no juega, las asistencias del
# pasador caen. Los pares «pasador → receptor» salen de las jugadas de cada partido (ESPN) y se guardan en disco.
_RUTA_ASIST = Path(__file__).parent / ".cache_picks" / "asistencias.json"
_ASIST_DISCO = None            # {evento: {id_pasador: {id_receptor: n}}}, cargado una vez
_ASIST_MIN = 15                # asistencias mínimas en la ventana para opinar sobre sus receptores
_REC_SHARE_MIN = 0.10          # un receptor cuenta desde este % de las asistencias del pasador
_REC_PERDIDA_RESERVA, _REC_PERDIDA_POCO = 0.12, 0.30


def _asist_disco():
    global _ASIST_DISCO
    if _ASIST_DISCO is None:
        try:
            _ASIST_DISCO = json.loads(_RUTA_ASIST.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _ASIST_DISCO = {}
    return _ASIST_DISCO


def _guardar_asist_disco():
    try:
        _RUTA_ASIST.parent.mkdir(exist_ok=True)
        tmp = _RUTA_ASIST.with_suffix(".tmp")
        tmp.write_text(json.dumps(_asist_disco(), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _RUTA_ASIST)
    except OSError:
        pass


def _pares_evento(evento):
    """{id pasador: {id receptor: asistencias}} de un partido terminado; None si ESPN no trae las jugadas."""
    ev = str(evento)
    cache = _asist_disco()
    if ev in cache:
        return cache[ev]
    try:
        plays = (nba.resumen(ev) or {}).get("plays") or []
    except Exception:  # noqa: BLE001
        return None
    if not plays:
        return None                      # no se guarda: puede ser un fallo momentáneo
    pares = {}
    for p in plays:
        part = p.get("participants") or []
        if not p.get("scoringPlay") or len(part) < 2 or "assist" not in str(p.get("text") or "").lower():
            continue
        rec = str(((part[0] or {}).get("athlete") or {}).get("id") or "")     # el primero encesta, el segundo asiste
        pas = str(((part[1] or {}).get("athlete") or {}).get("id") or "")
        if pas and rec and pas != rec:
            pares.setdefault(pas, {})
            pares[pas][rec] = pares[pas].get(rec, 0) + 1
    cache[ev] = pares
    return pares


def _receptores(serie, team_id, cajas):
    """{pasador (nombre normalizado): {tot, rec: {receptor normalizado: n}, nombres}} sobre la ventana; {} sin datos."""
    tid = str(team_id)
    with ThreadPoolExecutor(max_workers=8) as pool:
        todos = list(pool.map(lambda g: _pares_evento(g.get("evento")), serie))
    _guardar_asist_disco()
    out, con_datos = {}, 0
    for pares, c in zip(todos, cajas):
        jug = [x for x in (c or {}).get("jugadores", []) if x.get("team_id") == tid and (x.get("MIN") or 0) > 0]
        if pares is None or len(jug) < 5:
            continue
        con_datos += 1
        nom = {str(x.get("id")): x.get("Jugador", "") for x in jug}
        for pid, recs in pares.items():
            if pid not in nom:
                continue
            a = out.setdefault(normalizar(nom[pid]), {"tot": 0, "rec": {}, "nombres": {}})
            for rid, n in recs.items():
                if rid in nom:
                    kr = normalizar(nom[rid])
                    a["rec"][kr] = a["rec"].get(kr, 0) + n
                    a["nombres"][kr] = nom[rid]
                    a["tot"] += n
    return out if con_datos >= 5 else {}


def _analisis_asist(k, d, rec, prob_no, activos, jug):
    """Juzga si las asistencias de un jugador son fiables según quiénes son sus receptores y si juegan.

    Devuelve None sin datos; si no, {factor, nivel (ok/reservas/poco), txt}. `factor` multiplica sus asistencias:
    dato real (partidos de la ventana sin el receptor) si hay 3+, y si no una estimación (la mitad de lo que
    iba al ausente se pierde, porque parte de esos pases termina en otro compañero)."""
    r = (rec or {}).get(k)
    if not r or r["tot"] < _ASIST_MIN:
        return None
    todos = sorted(r["rec"].items(), key=lambda x: -x[1])
    top = [(kr, n / r["tot"]) for kr, n in todos if n / r["tot"] >= _REC_SHARE_MIN][:3]
    if not top:
        return None
    ape = lambda kr: (r["nombres"].get(kr) or kr).split()[-1]
    est, pre = {}, top
    top = []
    for kr, sh in pre:
        p = prob_no.get(kr, 0.0)
        if kr not in activos and p < 0.85:
            p = 0.85                     # ya no juega con el equipo o casi no juega: no se puede contar con él
            est[kr] = "no está en la rotación"
        top.append((kr, sh, p))
    perdido = sum(sh * p for _, sh, p in top)
    factor = max(0.7, 1 - 0.5 * perdido)
    real_txt = None
    ausentes = [(sh * p, kr, sh, p) for kr, sh, p in top if p >= 0.3]
    if ausentes:
        _, kr, sh, p = max(ausentes)
        rd = jug.get(kr)
        if rd:
            sin = set(range(rd["n"])) - {g["ev"] for g in rd["juegos"]}
            a_sin = [g["AST"] for g in d["juegos"] if g["ev"] in sin and g.get("AST") is not None]
            a_con = [g["AST"] for g in d["juegos"] if g["ev"] not in sin and g.get("AST") is not None]
            if len(a_sin) >= 3 and len(a_con) >= 3:
                m_sin, m_con = sum(a_sin) / len(a_sin), sum(a_con) / len(a_con)
                ratio = max(0.7, min(1.2, m_sin / max(m_con, 0.1)))
                w = min(1.0, (len(a_sin) - 1) / 5)
                resto = max(0.7, 1 - 0.5 * (perdido - sh * p))
                factor = w * (1 + p * (ratio - 1)) * resto + (1 - w) * factor
                real_txt = (f"sin {ape(kr)} promedia {m_sin:.1f} ast ({len(a_sin)} partidos) vs {m_con:.1f} con él "
                            f"(comprobado)")
    conc = top[0][1] >= 0.40 and top[0][2] > 0
    if perdido >= _REC_PERDIDA_POCO:
        nivel = "poco"
    elif perdido >= _REC_PERDIDA_RESERVA or conc:
        nivel = "reservas"
    else:
        nivel = "ok"
    def parte(kr, sh, p):
        e = est.get(kr) or ("baja" if p >= 0.85 else "duda" if p > 0 else "")
        return f"{ape(kr)} {sh:.0%}" + (f" ({e})" if e else "")
    txt = "Asiste sobre todo a " + ", ".join(parte(*t) for t in top)
    if nivel == "ok":
        txt += " · todos juegan: asistencias fiables"
    else:
        txt += (" · " + ("POCO FIABLE" if nivel == "poco" else "con reservas") + f": ~{perdido:.0%} de sus asistencias "
                f"van a alguien que podría no jugar; " + (real_txt or f"se estima {factor - 1:+.0%} de ast (estimado)"))
    return {"factor": factor, "nivel": nivel, "txt": txt, "perdido": perdido,
            "ausentes": [(ape(kr), sh, p) for kr, sh, p in top if p >= 0.3]}


def _picks_equipo(jug, bajas, fr=None, p_pal=0.0, es_local=True, f_ritmo=1.0, f_fat=1.0, rec=None):
    """(picks, notas) de un equipo.

    Para cada jugador y estadística busca la línea «Más de X.5» que superó en ~80 % de sus últimos partidos, con estos ajustes:
      · rival: los valores se multiplican por `fr` (lo que el rival concede de esa estadística).
      · ritmo: se multiplican por `f_ritmo` (el partido será más rápido o más lento de lo que el equipo suele jugar).
      · cansancio: se multiplican por `f_fat` (back-to-back, 3 partidos en 4 noches, viaje largo).
      · sede: si el jugador rinde distinto en casa y de visita (4+ partidos de cada lado) se corrige, con cautela.
      · ausencias: lo que producía un ausente se reparte entre los que juegan. Si hay 3+ partidos de la ventana sin el
        ausente, se usa lo que el compañero hizo de verdad en ellos; si no, se supone que absorben el _ABSORBE %.
      · paliza: se mezcla el historial normal con el de los partidos decididos por _MARGEN_PALIZA+ según la probabilidad
        de paliza (los titulares juegan menos en ellos).
      · receptores (solo asistencias): si los compañeros a quienes más asiste no juegan, sus asistencias bajan y el pick
        se marca como poco fiable (ver `_analisis_asist`).
      · tendencia: los últimos 5 partidos pesan 20 % (si hay 8+); además se marca si el jugador va en alza o a la baja.
    Confianza = % de partidos en que la habría superado × probabilidad de que el jugador juegue.
    Cada pick lleva `etq`: las razones (en texto corto) que movieron su línea o su confianza.
    """
    fr = fr or {}
    prob_no = _prob_no_juega(bajas)
    activos = {k: d for k, d in jug.items() if prob_no.get(k, 0) < 0.85 and d["mpg"] >= 12 and d["pres"] >= 0.5}

    # producción que se pierde por ausencias, repartida entre los que sí juegan según sus minutos
    extra = {k: {s: 0.0 for s in _CLAVES} for k in activos}
    con_dato_real = {k: False for k in activos}
    quien = {k: {s: {} for s in _CLAVES} for k in activos}     # quién se lleva qué de cada ausente: {k: {stat: {ausente: valor}}}
    top_pts = set(sorted(jug, key=lambda x: -jug[x]["ppg"])[:3])      # los 3 máximos anotadores del equipo
    notas_est = []
    for ks, p in prob_no.items():
        sd = jug.get(ks)
        if not sd:
            continue
        if (sd["ppg"] >= _ESTRELLA_PPG or ks in top_pts) and p >= 0.3:
            notas_est.append((sd["nombre"], p, ks))
        mins = sum(d["mpg"] for k, d in activos.items() if k != ks) or 1.0
        sin = set(range(sd["n"])) - {g["ev"] for g in sd["juegos"]}          # partidos de la ventana en que faltó
        for k, d in activos.items():
            if k == ks:
                continue
            for s in _CLAVES:
                m = _media_stat(d, s) or 0.0
                valor = _ABSORBE * (_media_stat(sd, s) or 0.0) * sd["pres"] * d["mpg"] / mins   # supuesto
                n_sin = sum(1 for g in d["juegos"] if g["ev"] in sin and g.get(s) is not None)
                con = _media_stat(d, s, set(range(sd["n"])) - sin)
                if n_sin >= 3 and con is not None:
                    real = max(-0.25 * m, min(0.6 * m, _media_stat(d, s, sin) - con))   # dato real, acotado
                    w = min(1.0, (n_sin - 1) / 5)                                      # más partidos sin él, más peso
                    valor = w * real + (1 - w) * valor
                    con_dato_real[k] = con_dato_real[k] or w >= 0.5
                extra[k][s] += p * valor
                quien[k][s][ks] = quien[k][s].get(ks, 0.0) + p * valor
    for k, d in activos.items():     # tope: las ausencias no pueden cambiar a nadie más de lo razonable
        for s in _CLAVES:
            m = _media_stat(d, s) or 0.0
            extra[k][s] = max(-0.25 * m, min(_TOPE_BAJAS * m, extra[k][s]))
            extra[k][s] *= _PESO_BAJA_REAL if con_dato_real[k] else _PESO_BAJA_EST     # lo estimado se cree menos

    cand = []
    for k, d in activos.items():
        p_juega = 1 - prob_no.get(k, 0)
        titular = d["mpg"] >= 26
        for s in _CLAVES:
            reg = [g for g in d["juegos"] if g.get(s) is not None]
            if len(reg) < _MIN_PARTIDOS or d["mpg"] < _MPG_PICK:
                continue
            mins_j = [g["MIN"] for g in reg if g.get("MIN")]
            cv_min = None
            if len(mins_j) >= _MIN_PARTIDOS:
                cv_min = statistics.pstdev(mins_j) / max(statistics.mean(mins_j), 1.0)
                if cv_min > _CV_MIN_MAX:
                    continue        # sus minutos cambian demasiado de un partido a otro: no se puede apostar a su cifra
            f_riv = fr.get(s, 1.0)
            f = f_riv * f_ritmo * f_fat
            asist = _analisis_asist(k, d, rec, prob_no, activos, jug) if s == "AST" else None
            if asist:
                f *= asist["factor"]
            media_t = sum(g[s] for g in reg) / len(reg)
            # sede: diferencia entre su promedio del lado de hoy y el general, suavizada y acotada a ±20 %
            ladj = 0.0
            lado = [g[s] for g in reg if g.get("loc") == es_local]
            if len(lado) >= 4 and len(reg) - len(lado) >= 4:
                ladj = max(-0.2 * media_t, min(0.2 * media_t, (sum(lado) / len(lado) - media_t) * len(lado) / (len(lado) + 6)))
            adj = [(g[s] * f + extra[k][s] + ladj, g.get("mg")) for g in reg]    # cronológico: el último es el más reciente
            vals = sorted(v for v, _ in adj)
            linea = math.floor(vals[int(0.2 * len(vals))]) - 0.5
            if linea < _LINEA_MIN[s]:
                continue
            hit = sum(v > linea for v in vals) / len(vals)
            tend = None
            if len(adj) >= 8:      # forma reciente: los últimos 5 partidos pesan 20 %
                hit = 0.8 * hit + 0.2 * sum(v > linea for v, _ in adj[-5:]) / 5
                tend = (sum(g[s] for g in reg[-5:]) / 5, media_t)
            # partidos de paliza: si hay pocos, se mezcla con lo esperado (un titular rinde menos en una paliza)
            pal = [v for v, mg in adj if mg is not None and mg >= _MARGEN_PALIZA]
            fb = hit * (0.88 if titular else 1.0)
            hit_pal = (sum(v > linea for v in pal) + 3 * fb) / (len(pal) + 3)
            conf_emp = (1 - p_pal) * hit + p_pal * hit_pal
            # 1) lo observado, encogido: pocos partidos o una línea escogida justo donde le salió bien no valen como 98 %
            n_v = len(vals)
            conf_emp = (conf_emp * n_v + _PRIOR_ACIERTO * _PRIOR_PESO) / (n_v + _PRIOR_PESO)
            # 2) lo que dice el modelo: promedio ajustado (rival, ritmo, bajas, sede) y su dispersión real
            prom = sum(vals) / n_v
            sd = max(statistics.pstdev(vals), _SD_MIN_REL[s] * prom, math.sqrt(max(prom, 0.5)))
            niv_ast = asist["nivel"] if asist else "ok"
            sd *= {"poco": 1.30, "reservas": 1.12}.get(niv_ast, 1.0)      # si faltan sus receptores, su cifra es más incierta
            p_mod = 1 - _phi((linea - prom) / sd)
            prom_pal = prom * (0.85 if titular else 1.0)      # en una paliza los titulares juegan menos
            p_mod_pal = 1 - _phi((linea - prom_pal) / sd)
            conf_mod = (1 - p_pal) * p_mod + p_pal * p_mod_pal
            # vale el más prudente de los dos, por la probabilidad de que juegue, y con techo
            conf = min(conf_emp, conf_mod) * p_juega
            conf *= {"poco": 0.92, "reservas": 0.97}.get(niv_ast, 1.0)     # asistencias poco fiables: se paga con probabilidad
            conf = min(conf, _CONF_MAX)
            if conf < _CONF_MIN or (niv_ast == "poco" and conf < 0.80):    # con receptores en duda solo sobreviven los muy holgados
                continue
            etq = []     # razones, de la más a la menos importante (en lenguaje simple: qué pasa y cuánto cambia la estadística)
            nom = _NOM_STAT[s]
            if abs(extra[k][s]) >= 0.8:
                x = extra[k][s]
                causas = [(ks_, v) for ks_, v in sorted(quien[k][s].items(), key=lambda kv: -abs(kv[1])) if abs(v) >= 0.3][:3]
                quienes = " y ".join(f'{jug[ks_]["nombre"].split()[-1]} ({"baja" if prob_no[ks_] >= 0.85 else "duda"}, '
                                     f'{"+" if v > 0 else "−"}{abs(v):.1f})' for ks_, v in causas)
                etq.append((f'sin {quienes}, ' if quienes else 'por las bajas de su equipo, ')
                           + f'se espera {"+" if x > 0 else "−"}{abs(x):.1f} {nom}'
                           + (" (comprobado: así le fue sin ellos)" if con_dato_real[k] else " (estimado)"))
            if abs(f_riv - 1) >= 0.03:
                etq.append(f'contra este rival se suele conseguir un {abs(f_riv - 1):.0%} {"más" if f_riv > 1 else "menos"} de {nom}')
            if abs(f_ritmo - 1) >= 0.02:
                etq.append(f'partido {"rápido" if f_ritmo > 1 else "lento"}: {"más" if f_ritmo > 1 else "menos"} jugadas, '
                           f'un {abs(f_ritmo - 1):.0%} {"más" if f_ritmo > 1 else "menos"} de {nom}')
            if tend:
                dif, rel = tend[0] - tend[1], (tend[0] - tend[1]) / max(tend[1], 1.0)
                if abs(rel) >= 0.15 and abs(dif) >= (1.5 if s == "PTS" else 0.6):
                    etq.append(f'{"▲ viene en alza" if dif > 0 else "▼ viene a la baja"}: {tend[0]:.1f} {nom} en sus últimos 5 partidos '
                               f'(su promedio es {tend[1]:.1f})')
            if abs(ladj) >= max(0.4, 0.06 * prom):
                etq.append(f'rinde {"mejor" if ladj > 0 else "peor"} {"en casa" if es_local else "de visita"}: '
                           f'{"+" if ladj > 0 else "−"}{abs(ladj):.1f} {nom}')
            cand.append({"nombre": d["nombre"], "k": k, "stat": s, "linea": linea, "conf": conf, "prom": prom,
                         "sube": extra[k][s], "riesgo": prob_no.get(k, 0) > 0, "fr": f_riv, "real": con_dato_real[k],
                         "etq": etq, "tend": tend, "ladj": ladj, "asist": asist, "p_mod": conf_mod, "p_emp": conf_emp,
                         "ana": {"n": n_v, "raw_hits": sum(g[s] > linea for g in reg), "ult5": [g[s] for g in reg[-5:]],
                                 "min10": min(g[s] for g in reg[-10:]), "med": statistics.median(vals), "mu": prom, "sd": sd,
                                 "mpg": d["mpg"], "cv_min": cv_min, "titular": titular, "p_juega": p_juega, "p_pal": p_pal,
                                 "f_riv": f_riv, "f_ritmo": f_ritmo, "f_fat": f_fat, "ladj": ladj, "local": es_local,
                                 "extra": extra[k][s], "real": con_dato_real[k],
                                 "ast": ({"nivel": asist["nivel"], "factor": asist["factor"], "perdido": asist["perdido"],
                                          "ausentes": asist["ausentes"]} if asist else None)}})
    # más seguros primero; a igual confianza, el que tiene más margen sobre la línea
    cand.sort(key=lambda c: (-round(c["conf"], 2), -(c["prom"] - c["linea"]) / max(c["prom"], 1.0)))
    picks, por_jugador = [], {}
    for c in cand:
        if por_jugador.get(c["nombre"], 0) >= 2:
            continue
        por_jugador[c["nombre"]] = por_jugador.get(c["nombre"], 0) + 1
        picks.append(c)
        if len(picks) == _PICKS_EQUIPO:
            break

    # nota de cada estrella / máximo anotador ausente y de quién se queda con sus puntos (por nombre)
    notas = []
    for nombre, p, ks in sorted(notas_est, key=lambda x: (-x[1], -jug[x[2]]["ppg"])):
        ppg = jug[ks]["ppg"]
        ben = sorted(((k, quien[k]["PTS"].get(ks, 0.0) / p) for k in activos), key=lambda kv: -kv[1])[:3]
        partes = []
        for k, pts in ben:
            if pts < 0.8:
                continue
            suben = [f"+{pts:.1f} pts"] + [f"+{v:.1f} {_NOM_STAT[s]}" for s in ("REB", "AST")
                                           if (v := quien[k][s].get(ks, 0.0) / p) >= 0.8]
            partes.append(f"<b>{_e(activos[k]['nombre'])}</b> ({', '.join(suben)})")
        if p >= 0.85:
            notas.append(f"⭐ Sin <b>{_e(nombre)}</b> ({ppg:.1f} pts de promedio){': sube ' if partes else ''}{', '.join(partes)}")
        else:
            notas.append(f"⚠ <b>{_e(nombre)}</b> ({ppg:.1f} pts de promedio) es duda: sus picks bajan de confianza"
                         + (f". Si no juega, suben {', '.join(partes)}" if partes else ""))
    return picks, notas


def _impacto_bajas(bajas, jug):
    """(puntos que pierde el equipo, puntos que gana el rival por perder defensores, detalle [(jugador, estado, puntos)]).

    Un jugador ausente no se lleva todos sus puntos: sus compañeros absorben parte (aquí se pierde el 25 % de su promedio).
    Se escala por la probabilidad de que no juegue y por la fracción de partidos en que sí jugó en la ventana.
    """
    perdidos, defensa, detalle = 0.0, 0.0, []
    for b in bajas or []:
        d = jug.get(normalizar(str(b.get("Jugador", ""))))
        if not d:
            continue
        estado = str(b.get("Estado") or "")
        e = estado.lower()
        prob = 1.0 if "out" in e else next((v for k, v in _PROB_BAJA.items() if k in e), 0.5)
        peso = prob * d["pres"]
        pts = 0.25 * d["ppg"] * peso
        perdidos += pts
        if d["mpg"] >= 20:
            defensa += 0.035 * d["mpg"] * peso
        if pts >= 0.4:
            detalle.append((d["nombre"], estado, pts))
    detalle.sort(key=lambda x: -x[2])
    return min(perdidos, 14.0), min(defensa, 4.0), detalle[:3]


@st.cache_data(ttl=3600, show_spinner=False)
def _posiciones_liga() -> dict:
    """{id de jugador: {pos, alt}} de los planteles de toda la liga (para los emparejamientos); {} si ESPN no responde.

    Son ~30 consultas en paralelo, cacheadas una hora. Si alguna falla se ignora: los emparejamientos solo se publican cuando se
    conoce la posición de casi todos los jugadores (ver nba_profundo.COBERTURA_POSICIONES)."""
    try:
        import ficha_equipos as fe
        ids = [str(e["id"]) for e in fe._equipos()]
    except Exception:  # noqa: BLE001
        log.warning("posiciones: no se pudo leer la lista de equipos", exc_info=True)
        return {}

    def plantel(tid):
        try:
            js = fe._json(f"{nba.BASE}/teams/{tid}/roster") or {}
        except Exception:  # noqa: BLE001
            return []
        crudos = js.get("athletes") or []
        if crudos and isinstance(crudos[0], dict) and "items" in crudos[0]:
            crudos = [a for g in crudos for a in g.get("items", [])]
        return crudos

    out = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for crudos in pool.map(plantel, ids):
            for a in crudos:
                pos = (a.get("position") or {}).get("abbreviation")
                if a.get("id") and pos:
                    alt = a.get("height")
                    out[str(a["id"])] = {"pos": str(pos), "alt": round(alt * 2.54) if isinstance(alt, (int, float)) else None}
    return out


def _prof_seguro(*args):
    """Análisis profundo sin que un fallo tire abajo el pronóstico: si algo sale mal se registra y el bloque no se muestra."""
    try:
        return npf.analizar(*args)
    except Exception:  # noqa: BLE001
        log.exception("análisis profundo del partido falló")
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _pronostico(local_id, visita_id, dia_iso=None):
    """Puntos proyectados de cada equipo = ritmo esperado × (ataque propio + defensa rival) / 2, con ventaja de local,
    bajas y cansancio. También arma el contexto del partido (descanso y viaje, ritmo, cuartos, línea contra el historial
    y cara a cara) y los picks de jugadores. `dia_iso` = día del partido (AAAA-MM-DD, hora del Este); por defecto, hoy."""
    import ficha_equipos as fe
    dia = date.fromisoformat(dia_iso) if dia_iso else _hoy_et()
    actual = fe._temporada_actual()
    temps = (actual, actual - 1)
    sl = fe._serie_equipo(local_id, temps, _VENTANA)
    sv = fe._serie_equipo(visita_id, temps, _VENTANA)
    if len(sl) < 5 or len(sv) < 5:
        return None
    eqs = fe._equipos()
    nombres = {e["id"]: e["nombre"] for e in eqs}
    abrevs = {e["id"]: e.get("abbr", "") for e in eqs}
    ab_l, ab_v = abrevs.get(str(local_id), ""), abrevs.get(str(visita_id), "")
    ritmo = [x for x in (_pond(sl, "ritmo"), _pond(sv, "ritmo")) if x is not None]
    a_l, d_l, a_v, d_v = _pond(sl, "ortg"), _pond(sl, "drtg"), _pond(sv, "ortg"), _pond(sv, "drtg")
    if len(ritmo) == 2 and None not in (a_l, d_l, a_v, d_v):
        pos = sum(ritmo) / 2
        base_l, base_v = (a_l + d_v) / 2 * pos / 100, (a_v + d_l) / 2 * pos / 100
    else:   # sin box scores completos: puntos anotados y recibidos
        base_l = (_pond(sl, "pf") + _pond(sv, "pc")) / 2
        base_v = (_pond(sv, "pf") + _pond(sl, "pc")) / 2
    base_l, base_v = base_l + _VENTAJA_LOCAL, base_v - _VENTAJA_LOCAL

    bajas_l = fe._bajas_hoy(local_id, nombres.get(str(local_id), ""))
    bajas_v = fe._bajas_hoy(visita_id, nombres.get(str(visita_id), ""))
    caj_l, caj_v = _cajas(sl), _cajas(sv)
    jug_l, jug_v = _jugadores_ventana(sl, local_id, caj_l), _jugadores_ventana(sv, visita_id, caj_v)
    perd_l, def_l, det_l = _impacto_bajas(bajas_l, jug_l)
    perd_v, def_v, det_v = _impacto_bajas(bajas_v, jug_v)
    # cansancio: back-to-back, 3 partidos en 4 noches y viajes largos restan puntos a quien los sufre
    comp_l, comp_v = fe._partidos(local_id, temps), fe._partidos(visita_id, temps)
    fat_l = _fatiga(comp_l, dia, True, ab_l, ab_v)
    fat_v = _fatiga(comp_v, dia, False, ab_v, ab_l)
    aj_l, aj_v = (fat_l or {}).get("aj", 0.0), (fat_v or {}).get("aj", 0.0)

    hist_l, hist_v = _historial_linea(sl, caj_l, local_id), _historial_linea(sv, caj_v, visita_id)
    aj_tot, motivos_tot, res_tot = _ajuste_total(sl, sv, hist_l, hist_v, aj_l, aj_v)
    pts_l = base_l - perd_l + def_v + aj_l + aj_tot / 2      # lo que pierde el rival en defensa lo gana este equipo
    pts_v = base_v - perd_v + def_l + aj_v + aj_tot / 2
    margen = pts_l - pts_v

    # picks de jugadores: ajustados por rival, ritmo, cansancio, sede, ausencias y riesgo de paliza
    perf_l, perf_v = _perfil_equipo(sl, caj_l, local_id), _perfil_equipo(sv, caj_v, visita_id)
    fr_l = _factores_rival(perf_v, (perf_l, perf_v))     # los jugadores locales enfrentan la defensa de la visita
    fr_v = _factores_rival(perf_l, (perf_l, perf_v))
    p_pal = _prob_paliza(margen)
    rit = _ritmo_esperado(sl, sv)
    ff_l, ff_v = max(0.94, 1 + aj_l / 100), max(0.94, 1 + aj_v / 100)
    rec_l, rec_v = _receptores(sl, local_id, caj_l), _receptores(sv, visita_id, caj_v)
    picks_l, notas_l = _picks_equipo(jug_l, bajas_l, fr_l, p_pal, True, rit["f_l"] if rit else 1.0, ff_l, rec_l)
    picks_v, notas_v = _picks_equipo(jug_v, bajas_v, fr_v, p_pal, False, rit["f_v"] if rit else 1.0, ff_v, rec_v)
    corr_l, corr_v = _correlados(picks_l, ab_l), _correlados(picks_v, ab_v)

    return {"pts_l": pts_l, "pts_v": pts_v, "margen": margen, "total": pts_l + pts_v,
            "p_local": 0.5 * (1 + math.erf(margen / _SD_MARGEN / math.sqrt(2))),
            "bajas_l": None if bajas_l is None else det_l, "bajas_v": None if bajas_v is None else det_v,
            "perd_l": perd_l, "perd_v": perd_v, "p_pal": p_pal,
            "jug_l": _resumen_plantel(jug_l), "jug_v": _resumen_plantel(jug_v),       # para simular la paliza
            "sj_l": sj.plantel(sl, local_id, caj_l), "sj_v": sj.plantel(sv, visita_id, caj_v),   # simulación de jugadores
            "fr_l": fr_l, "fr_v": fr_v, "ff_l": ff_l, "ff_v": ff_v,
            "raw_bajas_l": bajas_l or [], "raw_bajas_v": bajas_v or [],
            "picks_l": picks_l, "picks_v": picks_v, "notas_l": notas_l, "notas_v": notas_v,
            "corr_l": corr_l, "corr_v": corr_v,
            "ab_l": ab_l, "ab_v": ab_v, "fat_l": fat_l, "fat_v": fat_v, "ritmo": rit,
            "cuartos": _cuartos_proy(sl, sv, pts_l, pts_v),
            "hist_l": hist_l, "hist_v": hist_v, "aj_tot": aj_tot, "motivos_tot": motivos_tot, "res_tot": res_tot,
            "h2h": _cara_a_cara(comp_l, visita_id, dia),
            "prof": _prof_seguro(sl, sv, caj_l, caj_v, bajas_l, bajas_v, local_id, visita_id, _posiciones_liga())}


# --- Simulación de la paliza ---------------------------------------------------------------------------------------
# Se simulan miles de partidos cuarto a cuarto (con el marcador y los cuartos proyectados, que ya incluyen ritmo, bajas y
# cansancio) y se separan los que acaban en paliza de los que no. En cada uno se reparten los minutos por tramos de 6:
# si la ventaja es grande para el tiempo que queda, se sientan los titulares y entran los del fondo del banquillo (el que
# gana antes, sobre todo sus estrellas; el que pierde aguanta un poco más). Los puntos del equipo se reparten según el
# ritmo de anotación de cada jugador × sus minutos, y las bajas se sortean según su estado (duda, probable...).
_SIM_N = 30000           # partidos simulados
_SIM_MAX = 5000          # máximo que se analiza de cada tipo (paliza / partido parejo)
_FRAC_TIT = np.array([0.150, 0.115, 0.070, 0.115, 0.150, 0.120, 0.095, 0.185])   # reparto de los minutos de un titular por tramo
_FRAC_BAN = np.array([0.090, 0.130, 0.180, 0.130, 0.100, 0.140, 0.130, 0.100])   # ídem para un suplente
_UMBRAL_PULL = np.array([60., 55., 50., 45., 36., 28., 21., 15.])   # ventaja a partir de la cual se «tira la toalla» en cada tramo
_MIN_TRAMO = 6.0
_TRAMOS_TXT = ("al empezar el 1.º cuarto", "a mitad del 1.º cuarto", "al empezar el 2.º cuarto", "a mitad del 2.º cuarto",
               "al empezar el 3.º cuarto", "a mitad del 3.º cuarto", "al empezar el 4.º cuarto", "a mitad del 4.º cuarto")


def _prob_paliza_lado(margen):
    """(prob. de que el local gane por 15+, prob. de que gane la visita por 15+) con el margen proyectado."""
    return (1 - _phi((_MARGEN_PALIZA - margen) / _SD_MARGEN), _phi((-_MARGEN_PALIZA - margen) / _SD_MARGEN))


def _resumen_plantel(jug):
    """Lo mínimo de cada jugador para simular (así el pronóstico guardado en caché pesa poco)."""
    return {k: {"nombre": d["nombre"], "ppg": d["ppg"], "mpg": d["mpg"], "pres": d["pres"],
                "REB": _media_stat(d, "REB") or 0.0, "AST": _media_stat(d, "AST") or 0.0,
                "3PM": _media_stat(d, "3PM") or 0.0}
            for k, d in jug.items()}


def _plantel_sim(jug, bajas):
    """[(clave, datos, prob. de no jugar)] de los 14 jugadores con más minutos que de verdad están disponibles."""
    p_no = _prob_no_juega(bajas)
    items = [(k, d, p_no.get(k, 0.0)) for k, d in jug.items() if d["pres"] >= 0.4 and d["mpg"] >= 4 and p_no.get(k, 0.0) < 1.0]
    items.sort(key=lambda x: -x[1]["mpg"])
    return items[:14]


def _minutos_sim(mpg, juega, ventaja):
    """Minutos de cada jugador en cada tramo: (n, jugadores, 8) y el «nivel de basura» g (0 = partido vivo, 1 = decidido).

    mpg: (P,) minutos habituales · juega: (n, P) 1 si el jugador está disponible · ventaja: (n, 8) del equipo al empezar
    cada tramo (positiva = va ganando)."""
    tit = mpg >= 26
    base = np.where(tit[:, None], _FRAC_TIT[None, :], _FRAC_BAN[None, :]) * mpg[:, None]            # (P, 8)
    arriba = ventaja > 0
    desp = np.where(arriba[:, None, :], np.where(mpg >= 34, -2.0, 0.0)[None, :, None], 3.0)           # (n, P, 8)
    g = 1 / (1 + np.exp(-(np.abs(ventaja)[:, None, :] - (_UMBRAL_PULL[None, None, :] + desp)) / 3.0))
    f_tit = 1 - np.where(arriba[:, None, :], 0.93, 0.85) * g          # titulares: casi desaparecen
    f_med = 1 - 0.55 * g                                              # rotación media: juega bastante menos
    f_fon = 1 + 2.2 * g                                               # fondo de banquillo: sube mucho
    f = np.where(tit[None, :, None], f_tit, np.where((mpg >= 18)[None, :, None], f_med, f_fon))
    m = base[None, :, :] * f * juega[:, :, None]
    for _ in range(4):               # en cada tramo hay 5 jugadores × 6 min = 30 min; nadie pasa de 6 en un tramo
        m = np.minimum(m * (30.0 / np.maximum(m.sum(axis=1, keepdims=True), 1e-9)), _MIN_TRAMO)
    return m, g


def _equipo_sim(plantel, idx, ventaja, pts_eq, rng):
    """Simula a un equipo en los partidos `idx`: minutos, puntos y demás estadísticas de cada jugador."""
    n, P = len(idx), len(plantel)
    mpg = np.array([x[1]["mpg"] for x in plantel])
    p_no = np.array([x[2] for x in plantel])
    juega = (rng.random((n, P)) >= p_no[None, :]).astype(float)
    mins, g = _minutos_sim(mpg, juega, ventaja[idx])
    tot = mins.sum(axis=2)                                             # (n, P)
    ppm = np.array([x[1]["ppg"] / max(x[1]["mpg"], 1.0) for x in plantel])
    w = ppm[None, :] * tot * rng.lognormal(-0.045, 0.30, (n, P))       # el que tiene la noche buena se lleva más tiros
    pts = pts_eq[idx, None] * w / np.maximum(w.sum(axis=1, keepdims=True), 1e-9)
    est = {"PTS": pts}
    for s in ("REB", "AST", "3PM"):
        mu = np.array([x[1][s] / max(x[1]["mpg"], 1.0) for x in plantel])
        est[s] = rng.poisson(mu[None, :] * tot).astype(float)
    return {"min": tot, "est": est, "g": g, "juega": juega}


def _sim_paliza(pr, rl, rv, semilla=""):
    """Simula el partido miles de veces y devuelve cómo sería la paliza más probable frente a un partido parejo.

    Devuelve None si faltan datos de los planteles o si la paliza es tan improbable que no hay muestra."""
    jl, jv = pr.get("jug_l"), pr.get("jug_v")
    if not jl or not jv:
        return None
    m, tot = pr["margen"], pr["total"]
    p_l, p_v = _prob_paliza_lado(m)
    lado_l = p_l >= p_v
    sg = 1.0 if lado_l else -1.0
    rng = np.random.default_rng(zlib.crc32(f"{rl}{rv}{semilla}".encode()))

    cq = pr.get("cuartos")
    if cq:
        T, D = np.array(cq["ql"]) + np.array(cq["qv"]), np.array(cq["ql"]) - np.array(cq["qv"])
    else:
        T, D = np.full(4, tot / 4), np.full(4, m / 4)
    T = T * tot / T.sum()
    D = D + (m - D.sum()) / 4                              # los cuartos suman el margen final proyectado
    d = D[None, :] + rng.normal(0, _SD_MARGEN / 2, (_SIM_N, 4))        # margen (local − visita) de cada cuarto
    t = T[None, :] + rng.normal(0, _SD_TOTAL / 2, (_SIM_N, 4))         # puntos totales de cada cuarto
    M, TOT = d.sum(axis=1), t.sum(axis=1)
    blow = np.where(sg * M >= _MARGEN_PALIZA)[0][:_SIM_MAX]
    comp = np.where(np.abs(M) < _MARGEN_PALIZA)[0][:_SIM_MAX]
    if len(blow) < 300 or len(comp) < 300:
        return None

    C = np.cumsum(d, axis=1)                                           # ventaja del local al final de cada cuarto
    ini = np.concatenate([np.zeros((_SIM_N, 1)), C[:, :3]], axis=1)    # ... y al empezar cada cuarto
    lead = np.empty((_SIM_N, 8))
    lead[:, 0::2], lead[:, 1::2] = ini, ini + 0.5 * d                  # al empezar cada tramo de 6 minutos
    pts_l_s, pts_v_s = (TOT + M) / 2, (TOT - M) / 2

    pl_, pv_ = _plantel_sim(jl, pr.get("raw_bajas_l")), _plantel_sim(jv, pr.get("raw_bajas_v"))
    if len(pl_) < 8 or len(pv_) < 8:
        return None
    res = {}
    for nombre, idx in (("blow", blow), ("comp", comp)):
        res[nombre] = {"l": _equipo_sim(pl_, idx, lead, pts_l_s, rng), "v": _equipo_sim(pv_, idx, -lead, pts_v_s, rng)}

    gan = "l" if lado_l else "v"                                       # el equipo que gana la paliza
    plan = {"l": pl_, "v": pv_}
    ab = {"l": rl, "v": rv}
    # cuándo se sientan los titulares del que gana
    tit = np.array([x[1]["mpg"] >= 26 for x in plan[gan]])
    gs = res["blow"][gan]["g"][:, tit, :].mean(axis=1) if tit.any() else res["blow"][gan]["g"].mean(axis=1)
    se_sientan = gs > 0.5
    primero = np.where(se_sientan.any(axis=1), se_sientan.argmax(axis=1), -1)
    hay = primero >= 0
    out = {"lado": ab[gan], "otro": ab["v" if gan == "l" else "l"], "gana_l": lado_l, "p_lado": max(p_l, p_v),
           "p_otro": min(p_l, p_v), "n_pal": int(len(blow)),
           "marcador": (float((pts_l_s if lado_l else pts_v_s)[blow].mean()), float((pts_v_s if lado_l else pts_l_s)[blow].mean())),
           "ventaja_q": [float((sg * C[blow, q]).mean()) for q in range(4)],
           "p_sientan": float(hay.mean()),
           "tramo_sientan": int(np.median(primero[hay])) if hay.any() else None,
           "p_sientan_q4": float((gs[:, 6] > 0.5).mean()),
           "equipos": {}, "picks": []}

    for e in ("l", "v"):
        filas = []
        for i, (k, dd, pno) in enumerate(plan[e][:9]):
            fila = {"nombre": dd["nombre"], "mpg": dd["mpg"], "p_no": pno, "tit": dd["mpg"] >= 26}
            for tag, nom in (("c", "comp"), ("p", "blow")):
                r = res[nom][e]
                disp = r["juega"][:, i] > 0                               # solo cuentan las simulaciones en que juega
                fila["min_" + tag] = float(r["min"][disp, i].mean()) if disp.any() else 0.0
                fila["pts_" + tag] = float(r["est"]["PTS"][disp, i].mean()) if disp.any() else 0.0
            filas.append(fila)
        out["equipos"][ab[e]] = filas
        key = "picks_l" if e == "l" else "picks_v"
        idx_k = {x[0]: i for i, x in enumerate(plan[e])}
        for c in pr.get(key) or []:
            i = idx_k.get(c["k"])
            if i is None:
                continue
            pc = float((res["comp"][e]["est"][c["stat"]][:, i] > c["linea"]).mean())
            pb = float((res["blow"][e]["est"][c["stat"]][:, i] > c["linea"]).mean())
            out["picks"].append({"ab": ab[e], "nombre": c["nombre"], "stat": c["stat"], "linea": c["linea"],
                                 "conf": c["conf"], "p_comp": pc, "p_pal": pb})
    return out


def _html_paliza(rl, rv, pr) -> str:
    """Aviso de paliza (qué equipo la ganaría) y, desplegable, la simulación de cómo sería."""
    p_pal = pr.get("p_pal") or 0
    if p_pal < _AVISO_PALIZA:
        return ""
    p_l, p_v = pr.get("p_pal_l"), pr.get("p_pal_v")
    if p_l is None:
        p_l, p_v = _prob_paliza_lado(pr["margen"])
    (ag, pg), (ao, po) = ((rl, p_l), (rv, p_v)) if p_l >= p_v else ((rv, p_v), (rl, p_l))
    aviso = (f'<div class="pk-nota pal">⚠ Riesgo de paliza ({p_pal:.0%} de que se decida por {_MARGEN_PALIZA}+): la ganaría '
             f'<b>{_e(ag)}</b> ({pg:.0%}; que la gane {_e(ao)}: {po:.0%}). Los titulares podrían jugar menos y los picks '
             f'ya bajaron de confianza.')
    sim = pr.get("sim_pal")
    if not sim:
        return aviso + '</div>'
    gm, pm = sim["marcador"]
    vq = sim["ventaja_q"]
    if sim["tramo_sientan"] is not None and sim["p_sientan"] >= 0.5:
        sale = (f'Los titulares de <b>{_e(sim["lado"])}</b> se sientan <b>{_TRAMOS_TXT[sim["tramo_sientan"]]}</b> '
                f'(pasa en el {sim["p_sientan"]:.0%} de las palizas simuladas; el {sim["p_sientan_q4"]:.0%} ya no vuelve en el 4.º).')
    else:
        sale = f'Aun así, los titulares de <b>{_e(sim["lado"])}</b> suelen jugar casi todo el partido en la mayoría de las simulaciones.'
    narr = (f'Si ocurre, lo más típico es <b>{_e(sim["lado"])} {gm:.0f}–{pm:.0f} {_e(sim["otro"])}</b> '
            f'(+{gm - pm:.0f}). Ventaja de {_e(sim["lado"])} al final de cada cuarto: '
            + ", ".join(f"{v:+.0f}" for v in vq).replace("-", "−") + f'. {sale}')

    def delta(a, b, dec=1):
        d = b - a
        cl = "ok" if d >= 0.5 else "mal" if d <= -0.5 else ""
        return f'<span class="{cl}">{d:+.{dec}f}</span>'.replace("-", "−")

    tablas = []
    for ab, filas in sim["equipos"].items():
        trs = "".join(
            f'<tr><td class="n">{_e(f["nombre"])}{" ⚠" if f["p_no"] > 0 else ""}</td>'
            f'<td>{f["min_c"]:.0f}</td><td>{f["min_p"]:.0f}</td><td>{delta(f["min_c"], f["min_p"], 0)}</td>'
            f'<td>{f["pts_c"]:.1f}</td><td>{f["pts_p"]:.1f}</td><td>{delta(f["pts_c"], f["pts_p"])}</td></tr>'
            for f in filas)
        tablas.append(f'<div><div class="pk-tit">{_e(ab)} · minutos y puntos</div><table class="sp-t"><thead><tr><th></th>'
                      f'<th colspan="3">Min</th><th colspan="3">Pts</th></tr><tr><th></th><th>parejo</th><th>paliza</th><th>Δ</th>'
                      f'<th>parejo</th><th>paliza</th><th>Δ</th></tr></thead><tbody>{trs}</tbody></table></div>')
    picks = ""
    if sim["picks"]:
        its = "".join(
            f'<div class="pk-it {"alto" if p["p_pal"] >= 0.8 else "med" if p["p_pal"] >= 0.65 else "riesgo"}"><span><b>{_e(p["nombre"])}</b> '
            f'({_e(p["ab"])}) · Más de {p["linea"]:.1f} {_NOM_STAT[p["stat"]]}</span>'
            f'<span class="pk-p">{p["p_comp"]:.0%} → {p["p_pal"]:.0%}</span></div>' for p in sim["picks"])
        picks = (f'<div class="pk-tit" style="margin-top:12px">🎯 Tus picks: partido parejo → paliza (simulado)</div>'
                 f'<div class="pk-lista">{its}</div>')
    cuerpo = (f'<div class="sp-n">{narr}</div><div class="pk-cols">{"".join(tablas)}</div>{picks}'
              f'<div class="sp-f">Simulación de {sim["n_pal"]:,} palizas de {_e(sim["lado"])} frente a {sim["n_pal"]:,} partidos que '
              f'no se deciden por {_MARGEN_PALIZA}+. Usa los cuartos proyectados, las bajas (según su estado), la rotación habitual '
              f'de cada jugador y un corte de «partido decidido» que depende del tiempo que queda. Es una estimación, no una certeza.</div>')
    return (aviso + '</div>' + f'<details class="sp"><summary>🌊 Ver simulación de la paliza de {_e(sim["lado"])}</summary>'
            f'{cuerpo}</details>')


# --- Anclar el pronóstico al mercado y no olvidar a los underdogs ---------------------------------------------------
# El mercado ya sabe de alineaciones, lesiones y descanso, y acierta más que un modelo de 15 partidos. Por eso el margen
# final mezcla ambos, y del desvío del modelo en el total solo se conserva una parte (_ENCOGE_TOTAL).
_PESO_MERCADO = 0.40         # cuánto pesa el hándicap del mercado en el margen final (el resto es el modelo)
_ENCOGE_TOTAL = 0.55         # del desvío «modelo − línea» del total, se conserva este %
_P_SORPRESA_ALERTA = 0.38    # desde esta probabilidad de que gane el underdog, se muestra la alerta
_SESGO_MIN_PARTIDOS = 10     # con tantos partidos resueltos en el historial se aprende el sesgo real del modelo


def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _sesgo_total(difs):
    """Cuánto se aleja el total del modelo de la línea de forma sistemática (puntos; negativo = proyecta de menos).

    El modelo resta bajas y cansancio pero la línea ya los incluye, así que tiende a proyectar por debajo y a decir
    siempre «Menos». Si el historial de picks tiene 10+ partidos resueltos, se usa el sesgo real contra los totales
    jugados. Si no, el de la jornada (mediana de «modelo − línea» de 4+ partidos), aplicado al 80 %."""
    reg = _cargar_registro()
    res = [sum(r["final"]) - r["total_modelo"] for r in reg.values()
           if r.get("cerrado") and r.get("final") and r.get("total_modelo") is not None]
    if len(res) >= _SESGO_MIN_PARTIDOS:
        n = len(res)
        return -(sum(res) / n) * n / (n + 10)          # modelo − real, encogido con pocos partidos
    if len(difs) >= 4:
        s = sorted(difs)
        med = s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2
        return 0.8 * med
    return 0.0


def _con_mercado(pr, j, sesgo=0.0):
    """Copia del pronóstico anclada a la línea: margen mezclado con el hándicap, total corregido por sesgo y encogido.

    Guarda lo del modelo puro (margen_modelo, total_modelo) y calcula el favorito, el underdog y la probabilidad
    de que gane el underdog. Sin línea de mercado se queda con lo del modelo."""
    p = dict(pr)
    L, V = j["local"], j["visita"]
    rl, rv = L["abrev"] or L["nombre"][:3].upper(), V["abrev"] or V["nombre"][:3].upper()
    mod_m, mod_t = pr["margen"], pr["total"]
    m, mkt = mod_m, None
    mh = _RE_HANDICAP.match(str(j.get("linea_txt") or "").strip())
    if mh and mh.group(1) in (rl, rv):
        v = float(mh.group(2))
        mkt = -v if mh.group(1) == rl else v           # margen esperado del local según el mercado
        m = (1 - _PESO_MERCADO) * mod_m + _PESO_MERCADO * mkt
    t = mod_t
    try:
        lt = float(j.get("linea_total") or 0)
    except (TypeError, ValueError):
        lt = 0.0
    if lt > 0:
        t = lt + _ENCOGE_TOTAL * (mod_t - sesgo - lt)
    fav_local = (mkt > 0) if mkt else (m >= 0)          # sin línea (o línea parejo) el favorito es el que da el modelo
    fm = m if fav_local else -m                         # margen proyectado del favorito
    p.update(margen_modelo=mod_m, total_modelo=mod_t, margen=m, total=t, pts_l=(t + m) / 2, pts_v=(t - m) / 2,
             p_local=_phi(m / _SD_MARGEN), p_pal=_prob_paliza(m), mkt_margen=mkt, fav_local=fav_local,
             fav_ab=rl if fav_local else rv, dog_ab=rv if fav_local else rl, p_sorpresa=_phi(-fm / _SD_MARGEN))
    # marcador en puntos enteros que cuadra con el total mostrado: local + visita = total redondeado (sin sumar 215 si el total dice 214)
    pl_i = round((t + m) / 2)
    p["pts_l"], p["pts_v"] = float(pl_i), float(round(t) - pl_i)
    p["cuartos"] = _cuartos_enteros(pr.get("cuartos"), p["pts_l"], p["pts_v"])     # cuartos que suman el marcador final mostrado
    p["p_pal_l"], p["p_pal_v"] = _prob_paliza_lado(m)      # quién ganaría la paliza: local o visita
    p["esc"] = _escenario_total(t, m, pr.get("res_tot"), lt if lt > 0 else None, j.get("id"))
    p["sim_pal"] = None
    if p["p_pal"] >= _AVISO_PALIZA:
        try:
            p["sim_pal"] = _sim_paliza(p, rl, rv, str(j.get("id") or ""))
        except Exception:  # noqa: BLE001 — la simulación es un extra: si falla, el aviso se muestra igual
            p["sim_pal"] = None
    try:    # simulación de jugadores y rotaciones (con el marcador final, ya anclado al mercado)
        p["sim_jug"] = sj.simular(p, rl, rv, str(j.get("id") or ""), j.get("id"))
    except Exception:  # noqa: BLE001 — otro extra: si falla, el resto de la tarjeta sigue igual
        p["sim_jug"] = None
    _conciliar_picks_con_simulacion(p, rl, rv)
    return p


def _conciliar_picks_con_simulacion(p, rl, rv):
    """Un pick solo se muestra si el historial Y la simulación del partido coinciden.

    La simulación ya conoce el quinteto, los minutos y las bajas de ESTE partido. Si dice 42 % y el historial dice 98 %,
    no hay 98 %: se queda la menor de las dos probabilidades y, si baja de _CONF_MIN, el pick se descarta."""
    sim = p.get("sim_jug")
    if not sim:
        return
    for key, ab in (("picks_l", rl), ("picks_v", rv)):
        eq = (sim.get("equipos") or {}).get(ab)
        if not eq or not p.get(key):
            continue
        psim = {(f["k"], c["stat"], c["linea"]): c["p"] for f in eq["filas"] for c in f["picks"]}
        nuevos = []
        for c in p[key]:
            ps = psim.get((c["k"], c["stat"], c["linea"]))
            if ps is not None:
                c["conf_hist"], c["p_sim"] = c["conf"], ps
                c["conf"] = min(c["conf"], ps)
            if c["conf"] >= _CONF_MIN:
                nuevos.append(c)
        p[key] = nuevos
        for f in eq["filas"]:      # que la tabla de la simulación muestre la misma confianza que el pick
            f["picks"] = [{**c, "conf": min(c["conf"], c["p"])} for c in f["picks"] if min(c["conf"], c["p"]) >= _CONF_MIN]


def _lectura_handicap(pr, j):
    """Qué lado del hándicap conviene (favorito o underdog) y con qué probabilidad; None si no hay línea o está parejo."""
    L, V = j["local"], j["visita"]
    rl, rv = L["abrev"] or L["nombre"][:3].upper(), V["abrev"] or V["nombre"][:3].upper()
    m = _RE_HANDICAP.match(str(j.get("linea_txt") or "").strip())
    if not m or m.group(1) not in (rl, rv) or float(m.group(2)) == 0:
        return None
    ab, v = m.group(1), float(m.group(2))
    otro = rv if ab == rl else rl
    borde = (pr["margen"] if ab == rl else -pr["margen"]) + v        # >0: el equipo de la línea cubre
    p_ab = _phi(borde / _SD_MARGEN)
    pick, pick_v, p_lado = (ab, v, p_ab) if borde >= 0 else (otro, -v, 1 - p_ab)
    fav = ab if v < 0 else otro
    return {"ab": ab, "v": v, "borde": borde, "pick": pick, "pick_v": pick_v, "p": p_lado, "fav": fav,
            "dog": otro if v < 0 else ab, "dog_pick": pick != fav}


def _elegir_total(pr, linea):
    """Elige siempre un lado del total: (¿Más?, diferencia con la línea, probabilidad del lado elegido, ¿ajustado?)."""
    dif = pr["total"] - float(linea)
    p_mas = 0.5 * (1 + math.erf(dif / _SD_TOTAL / math.sqrt(2)))
    esc = pr.get("esc")
    if esc and esc.get("p_mas") is not None and abs((esc.get("lt") or 0) - float(linea)) < 1e-6:
        p_mas = esc["p_mas"]          # distribución real de totales (con cola derecha), no una campana simétrica
    mas = p_mas >= 0.5
    return mas, dif, (p_mas if mas else 1 - p_mas), abs(dif) < 2.5


_MARGEN_VALOR = 0.06     # una cuota solo tiene valor si supera la justa en este % (cubre el error del modelo)


def _cuota_pick(conf):
    """(cuota justa, cuota mínima con valor) en formato decimal a partir de la probabilidad estimada."""
    p = max(min(conf, 0.99), 0.05)
    return 1 / p, (1 + _MARGEN_VALOR) / p


def _grado_pick(c):
    a = c.get("ana") or {}
    z = (a.get("mu", 0) - c["linea"]) / max(a.get("sd", 1), 0.1)
    ps = c.get("p_sim")
    niv = (a.get("ast") or {}).get("nivel", "ok")
    estimado = abs(a.get("extra", 0)) >= 0.8 and not a.get("real")
    if niv == "poco" or c.get("riesgo") and c["conf"] < 0.8:
        return "Arriesgado"
    # «Fuerte» solo si no hay ningún aviso pendiente: duda de jugar, receptores dudosos o bajas solo estimadas
    if (c["conf"] >= 0.80 and z >= 0.9 and not c.get("riesgo") and niv == "ok" and not estimado
            and a.get("n", 0) >= 12 and (ps is None or ps >= 0.75)):
        return "Fuerte"
    if c["conf"] >= 0.72 and z >= 0.6:
        return "Medio"
    return "Arriesgado"


def _html_analisis(c) -> str:
    """Desplegable con el razonamiento del pick: por qué la línea es viable, qué puede fallar y qué cuota la hace rentable."""
    a = c.get("ana")
    if not a:
        return ""
    nom, lin = _NOM_STAT[c["stat"]], c["linea"]
    z = (a["mu"] - lin) / max(a["sd"], 0.1)
    pro = []
    pro.append(f'Sin ajustes, superó {lin:.1f} {nom} en <b>{a["raw_hits"]} de sus últimos {a["n"]}</b> partidos; '
               f'últimos 5: {", ".join(f"{v:.0f}" for v in a["ult5"])} (su peor de los últimos 10: {a["min10"]:.0f}).')
    pro.append(f'Proyección ajustada <b>{a["mu"]:.1f}</b> {nom} contra la línea {lin:.1f}: colchón de {a["mu"] - lin:+.1f} '
               f'({z:.1f} desviaciones); mediana {a["med"]:.1f}.')
    rol = "titular" if a["titular"] else "de rotación"
    est = ""
    if a.get("cv_min") is not None:
        est = ", minutos muy estables" if a["cv_min"] <= 0.15 else ", minutos bastante estables" if a["cv_min"] <= 0.25 else ", minutos algo variables"
    pro.append(f'Rol: {rol}, {a["mpg"]:.0f} min por partido{est}; probabilidad de jugar {a["p_juega"]:.0%}.')
    fr = a["f_riv"]
    pro.append(f'Rival: concede un {abs(fr - 1):.0%} {"más" if fr > 1 else "menos"} de {nom} que el promedio (ya incluido en la proyección).'
               if abs(fr - 1) >= 0.03 else f'Rival: concede {nom} en la media, no ayuda ni frena.')
    ctx = []
    if abs(a["f_ritmo"] - 1) >= 0.02:
        ctx.append(f'ritmo {"rápido" if a["f_ritmo"] > 1 else "lento"} ({a["f_ritmo"] - 1:+.0%})')
    if a["f_fat"] < 0.99:
        ctx.append(f'equipo cansado por descanso/viaje ({a["f_fat"] - 1:+.0%})')
    if abs(a["ladj"]) >= 0.4:
        ctx.append(f'rinde {"mejor" if a["ladj"] > 0 else "peor"} {"en casa" if a["local"] else "de visita"} ({a["ladj"]:+.1f})')
    if abs(a["extra"]) >= 0.8:
        ctx.append(f'bajas del equipo ({a["extra"]:+.1f}, {"comprobado en partidos sin ellos" if a["real"] else "estimado"})')
    if ctx:
        pro.append("Contexto: " + "; ".join(ctx) + ".")
    if c.get("p_sim") is not None:
        pro.append(f'La simulación de este partido (quinteto, minutos y bajas) da <b>{c["p_sim"]:.0%}</b> de superar la línea.')
    con = []
    if c.get("riesgo"):
        con.append("tiene duda de jugar: si no juega, el pick se pierde.")
    if a["p_pal"] >= 0.2:
        con.append(f'riesgo de paliza ({a["p_pal"]:.0%}): los titulares podrían descansar el 4.º cuarto.')
    if abs(a["extra"]) >= 0.8 and not a["real"]:
        con.append("el efecto de las bajas es una estimación, sin partidos comparables que lo confirmen.")
    if a["n"] < 12:
        con.append(f'muestra corta: solo {a["n"]} partidos.')
    if z < 0.6:
        con.append("margen justo sobre la línea: un partido normal basta para perderla.")
    if a.get("cv_min") is not None and a["cv_min"] > 0.2:
        con.append("sus minutos varían entre partidos.")
    aa = a.get("ast")
    if aa and aa["nivel"] != "ok":
        base = a["mu"] / max(aa["factor"], 0.5)                 # su promedio de asistencias antes del ajuste
        peor = base * (1 - aa["perdido"])                       # si todos los receptores en duda faltan y nadie los reemplaza
        p_peor = 1 - _phi((lin - peor) / max(a["sd"], 0.1))
        quienes = ", ".join(f'{n} ({"baja" if p >= 0.85 else "duda"}, recibe el {sh:.0%})' for n, sh, p in aa["ausentes"])
        con.append(f'<b>Asistencias y receptores:</b> {quienes} reciben parte de sus pases. Con ellos fuera, no todos esos '
                   f'pases se pierden (otro compañero encesta), pero bajan: la proyección ya descuenta {aa["factor"] - 1:+.0%} '
                   f'(de {base:.1f} a {a["mu"]:.1f}). Si faltaran todos y nadie los reemplazara bajaría a ~{peor:.1f} y la '
                   f'probabilidad caería a ~{p_peor:.0%}. Por eso la probabilidad de arriba ya está recortada y el pick '
                   f'{"no puede ser «Fuerte»" if aa["nivel"] == "poco" else "queda como máximo en «Medio»"}.')
        con.append("Confirma la alineación antes del partido: si los receptores en duda juegan, la probabilidad sube; "
                   "si se confirma su baja, baja.")
    con.append("una lesión o falta temprana durante el partido no se puede prever.")
    justa, minima = _cuota_pick(c["conf"])
    g = _grado_pick(c)
    return (f'<details class="pk-ana"><summary>🧠 Análisis del pick <span class="gr {g}">{g}</span></summary><div class="an">'
            f'<h5>Por qué la línea es viable</h5><ul>{"".join(f"<li>{x}</li>" for x in pro)}</ul>'
            f'<h5>Qué puede salir mal</h5><ul>{"".join(f"<li class=no>{x}</li>" for x in con)}</ul>'
            f'<div class="cu">💰 Probabilidad estimada <b>{c["conf"]:.0%}</b> → cuota justa <b>{justa:.2f}</b>. '
            f'Solo tiene valor si la casa paga <b>{minima:.2f} o más</b> (+{_MARGEN_VALOR:.0%} sobre la justa); '
            f'si paga menos, no compensa aunque el pick sea probable.</div></div></details>')


def _html_escenario(rl, rv, pr) -> str:
    """Rango realista del total, probabilidad de partidos de muchos puntos y cómo sería uno (con los jugadores que más suben)."""
    e = pr.get("esc")
    if not e:
        return ""
    lt = e.get("lt")
    celdas = []
    if lt:
        celdas += [(f"Más de {lt:.1f}", e["p_mas"]), (f"{lt + 10:.0f}+ pts", e["p_mas10"]), (f"{lt - 10:.0f} o menos", e["p_menos10"])]
    celdas += [("240+ pts", e["p240"]), ("250+ pts", e["p250"]), ("210 o menos", e["p210"])]
    grid = "".join(f'<div><b>{v:.0%}</b><span>{_e(k)}</span></div>' for k, v in celdas)
    m = e["m"]
    sc = lambda tot: f'{_e(rl)} {(tot + m) / 2:.0f} – {(tot - m) / 2:.0f} {_e(rv)} ({tot:.0f})'
    mot = pr.get("motivos_tot") or []
    rit = pr.get("ritmo")
    if rit and rit["cat"] != "normal":
        mot = [f'ritmo {rit["cat"]}: {rit["pos"]:.1f} posesiones esperadas'] + mot
    h2h = pr.get("h2h") or []
    if h2h:
        mot.append("cara a cara este año: " + ", ".join(f'{g["pl"] + g["pv"]:.0f}' for g in h2h[-3:]) + " pts totales")
    # jugadores que más suben si el partido se dispara: lo que la simulación les da, escalado al total de ese escenario
    jug = ""
    sim = pr.get("sim_jug")
    if sim and e["p50"] > 0:
        k = e["alto"] / max(pr["total"], 1.0)
        partes = []
        for ab in (rl, rv):
            eq = (sim.get("equipos") or {}).get(ab)
            if not eq:
                continue
            top = sorted((f for f in eq["filas"] if f["p_juega"] >= 0.5), key=lambda f: -f["est"]["PTS"][0])[:3]
            partes.append(f'<b>{_e(ab)}</b>: ' + ", ".join(f'{_e(f["nombre"].split()[-1])} {f["est"]["PTS"][0] * k:.0f} pts' for f in top))
        if partes:
            jug = f'<h5>Anotadores si se dispara</h5><div>{" · ".join(partes)}</div>'
    cuerpo = (f'<div class="esc-g">{grid}</div>'
              f'<h5>Cómo sería</h5><ul><li>Se dispara (25 % de los casos más altos): <b>{sc(e["alto"])}</b></li>'
              f'<li>Se apaga (25 % de los más bajos): <b>{sc(e["bajo"])}</b></li>'
              f'<li>Lo más típico: total de {e["p50"]:.0f}</li></ul>'
              + (f'<h5>Qué empuja los puntos</h5><ul>{"".join(f"<li>{_e(x)}</li>" for x in mot)}</ul>' if mot else "")
              + jug +
              '<div class="esc-n">Las probabilidades salen de cómo variaron de verdad los totales de estos dos equipos, no de una campana '
              'simétrica: por eso un 130-125 tiene su sitio.</div>')
    return (f'<details class="sp esc"><summary>🔥 Escenarios de puntos · rango realista {e["p10"]:.0f}–{e["p90"]:.0f} '
            f'(80 % de los casos)</summary><div class="esc-b">{cuerpo}</div></details>')


def _html_picks(rl, rv, pr, ids=None, logos=None) -> str:
    """Dos columnas (local y visita) con los picks más seguros de puntos, rebotes, asistencias y triples."""
    ids, logos = ids or {}, logos or {}

    def col(ab, picks, notas, corr):
        if picks:
            items = []
            for c in picks:
                clase = "riesgo" if c["riesgo"] else "alto" if c["conf"] >= 0.9 else "med"
                etq = c.get("etq") or []
                sube = f' <em>({_e(" · ".join(etq))})</em>' if etq else ""
                aviso = " ⚠" if c["riesgo"] else ""
                enlace = ' <span class="pk-cor" title="Depende de lo mismo que otro pick">🔗</span>' if c.get("corr") else ""
                a = c.get("asist")
                sub = (f'<span class="pk-as {a["nivel"]}">🅰 {_e(a["txt"])}'
                       + (' · la probabilidad ya lo descuenta' if a["nivel"] != "ok" else "") + '</span>') if a else ""
                items.append(f'<div class="pk-it {clase}"><span><b>{_e(c["nombre"])}</b>{aviso} · Más de {c["linea"]:.1f} '
                             f'{_NOM_STAT[c["stat"]]}{sube}{enlace}{sub}{_html_analisis(c)}</span><span class="pk-p">{c["conf"]:.0%}</span></div>')
            cuerpo = f'<div class="pk-lista">{"".join(items)}</div>'
        else:
            cuerpo = '<div class="pk-vacio">Sin picks con suficiente confianza.</div>'
        cuerpo += "".join(f'<div class="pk-nota">{n}</div>' for n in notas)
        cuerpo += "".join(f'<div class="pk-nota cor">{n}</div>' for n in corr)
        esc = _escudo_hist(ab, ids.get(ab), logos) if logos else ""     # escudo al lado del nombre (el mismo del historial)
        return f'<div><div class="pk-tit hx-t">{esc}<span>🎯 {_e(ab)} · picks más seguros</span></div>{cuerpo}</div>'

    pal = _html_paliza(rl, rv, pr) + _html_escenario(rl, rv, pr)
    return (f'<div class="pk"><div class="pk-cols">'
            f'{col(rl, pr.get("picks_l"), pr.get("notas_l", []), pr.get("corr_l", []))}'
            f'{col(rv, pr.get("picks_v"), pr.get("notas_v", []), pr.get("corr_v", []))}'
            f'</div>{pal}</div>')


def _pill(txt, clase=""):
    return f'<span class="cx-pill {clase}">{_e(txt)}</span>'


def _html_fatiga(ab, f, aj) -> str:
    """Una línea por equipo: descanso, carga de partidos y viaje."""
    if not f:
        return f'<div class="cx-f"><b>{_e(ab)}</b> <em>sin datos de calendario</em></div>'
    p = []
    d = f["desc"]
    if f["b2b"]:
        p.append(_pill("Back-to-back", "mal"))
    elif d is not None:
        p.append(_pill(f'{d} {"día" if d == 1 else "días"} de descanso', "bien" if d >= 2 else ""))
    if f["tres4"]:
        p.append(_pill("3.º partido en 4 noches", "mal"))
    p.append(_pill(f'{f["g7"]} partidos en 7 días', "med" if f["g7"] >= 4 else ""))
    if f["km"] >= 300:
        km = f'{f["km"]:,.0f}'.replace(",", ".")
        dh = f' · {f["dh"]:+d} h de huso'.replace("-", "−") if f["dh"] else ""
        p.append(_pill(f'viaje {km} km{dh}', "med" if f["km"] >= _KM_VIAJE_LARGO else ""))
    if f["gira"] >= 3:
        p.append(_pill(f'{f["gira"]}.º partido de gira', "med"))
    efecto = f' <em>({aj:+.1f} pts)</em>'.replace("-", "−") if aj else ""
    return f'<div class="cx-f"><b>{_e(ab)}</b>{"".join(p)}{efecto}</div>'


def _fmt_fecha(iso):
    try:
        return date.fromisoformat(iso).strftime("%d/%m")
    except Exception:  # noqa: BLE001
        return iso


def _sg(x, dec=1) -> str:
    """Número con signo y el menos tipográfico (+3.2 / −1.5)."""
    return f"{x:+.{dec}f}".replace("-", "\u2212")


def _rec(b) -> str:
    return f'{b["g"]}-{b["p"]}'


def _html_forma(rl, rv, prof) -> str:
    """Forma actual: récord y diferencial de los últimos 5 frente a toda la ventana, racha y rendimiento en la sede de hoy."""
    filas = []
    for ab, lado in ((rl, "l"), (rv, "v")):
        f = (prof.get(lado) or {}).get("forma")
        if not f:
            filas.append(f'<div class="cx-f"><b>{_e(ab)}</b> <em>sin partidos suficientes</em></div>')
            continue
        u5, tot, sede = f["u5"], f["total"], f["sede"]
        pills = [_pill(f'Últ. 5: {_rec(u5)}', "bien" if u5["g"] >= 4 else "mal" if u5["g"] <= 1 else "")]
        if f["tendencia"] == "alza":
            pills.append(_pill("\u25B2 en alza", "bien"))
        elif f["tendencia"] == "baja":
            pills.append(_pill("\u25BC a la baja", "mal"))
        if f["racha"] and f["racha"]["n"] >= 2:
            r = f["racha"]
            texto = f'{r["n"]} {"victorias" if r["gano"] else "derrotas"} seguidas'
            pills.append(_pill(texto, "bien" if r["gano"] else "mal"))
        detalle = (f'Diferencial últ. 5: <b>{_sg(u5["dif"])}</b> pts por partido · en {tot["n"]}: {_rec(tot)} ({_sg(tot["dif"])})')
        if sede:
            lugar = "en casa" if f["es_local"] else "de visita"
            detalle += f' · {lugar}: {_rec(sede)} ({_sg(sede["dif"])})'
        eficiencia = ""
        if u5["ortg"] is not None and tot["ortg"] is not None:
            # en defensa menos es mejor: la flecha se invierte para que verde siempre signifique «mejor que su ventana»
            eficiencia = (f'<div class="pf-s">Por 100 posesiones · ataque <b>{u5["ortg"]:.1f}</b>{_flecha(u5["ortg"] - tot["ortg"], 2.0)}'
                          f' · defensa <b>{u5["drtg"]:.1f}</b>{_flecha(tot["drtg"] - u5["drtg"], 2.0)}</div>')
        filas.append(f'<div class="cx-f"><b>{_e(ab)}</b>{"".join(pills)}</div><div class="pf-s">{detalle}</div>{eficiencia}')
    return ('<div class="cx-b"><div class="cx-h">\U0001F4CA Forma actual</div>' + "".join(filas)
            + '<div class="pf-s"><em>Flechas verdes: mejor que su promedio de la ventana (en defensa, menos puntos permitidos).</em></div></div>')


def _spark(ult) -> str:
    """Mini barras con los puntos de sus últimos partidos (la última, más oscura)."""
    if not ult:
        return ""
    tope = max([p for p, _ in ult] + [1])
    barras = "".join(f'<i title="{p:.0f} pts" style="height:{max(12, round(100 * p / tope))}%"></i>' for p, _ in ult)
    return f'<span class="pf-sp" aria-hidden="true">{barras}</span>'


def _flecha(d, umbral, dec=1) -> str:
    if d is None or abs(d) < umbral:
        return ""
    clase, simbolo = ("pf-up", "\u25B2") if d > 0 else ("pf-dn", "\u25BC")
    return f' <span class="{clase}">{simbolo} {_sg(d, dec)}</span>'


def _html_foco(rl, rv, prof) -> str:
    """Los jugadores más usados: puntos de los últimos 5 frente a su promedio, minutos y señales de racha (un equipo por columna)."""
    cols = []
    for ab, lado in ((rl, "l"), (rv, "v")):
        lista = (prof.get(lado) or {}).get("foco")
        partes = [f'<div class="pf-eq">{_e(ab)}</div>']
        if not lista:
            partes.append('<div class="pf-s"><em>sin partidos suficientes</em></div>')
        for j in lista or []:
            marca = {"caliente": " \U0001F525", "frio": " \U0001F9CA"}.get(j["etiqueta"], "")
            estado = f' {_pill(j["estado"], "mal" if "out" in j["estado"].lower() else "med")}' if j["estado"] else ""
            pts = f'<b>{j["ppg5"]:.1f}</b> pts <em>(prom. {j["ppg"]:.1f})</em>' if j["g5"] else f'<em>prom. {j["ppg"]:.1f} pts</em>'
            mins = f'{j["mpg5"]:.0f} min' if j["g5"] else f'{j["mpg"]:.0f} min'
            partes.append(f'<div class="pf-r"><span class="pf-n" title="{_e(j["nombre"])}">{_e(j["nombre"])}{marca}{estado}</span>'
                          f'<span>{pts}{_flecha(j["d_pts"], 2.0)}{_spark(j["ult"])}</span>'
                          f'<span class="pf-s">{mins}{_flecha(j["d_min"], 3.0, 0)}</span></div>')
        cols.append(f'<div>{"".join(partes)}</div>')
    return ('<div class="cx-b ancho"><div class="cx-h">\U0001F525 Jugadores en foco (últimos 5 vs su ventana)</div>'
            f'<div class="pf-2">{"".join(cols)}</div>'
            '<div class="pf-s"><em>\U0001F525 / \U0001F9CA = muy por encima / por debajo de su promedio. Las barras son sus puntos en los últimos partidos; '
            'los minutos comparan los últimos 5 con el resto.</em></div></div>')


def _clase_estado(estado) -> str:
    e = str(estado).lower()
    return "mal" if "out" in e or "doubtful" in e else "med" if e else ""


def _html_baja(b) -> str:
    estado = _pill(b["estado"], _clase_estado(b["estado"])) if b["estado"] else ""
    lesion = f' <em>{_e(b["lesion"])}</em>' if b["lesion"] else ""
    lineas = [f'<div>\U0001FA7A <b>{_e(b["nombre"])}</b> {estado}{lesion}</div>']
    info = []
    if b["larga"]:
        info.append("fuera de larga duración: no aparece en sus últimos partidos")
    else:
        info.append(f'{b["ppg"]:.1f} pts · {b["mpg"]:.0f} min')
        k = b["fuera_n"]
        info.append(f'lleva {k} partido{"s" if k != 1 else ""} sin jugar' if k else "jugó el último partido")
    if b["puede_volver"]:
        info.append("podría volver hoy: revisa sus minutos")
    if b["regreso"]:
        info.append(f'regreso estimado: {_e(b["regreso"])}')
    lineas.append(f'<div class="pf-s">{" · ".join(info)}</div>')
    con, sin = b["con"], b["sin"]
    if con and sin:
        cae = con["dif"] - sin["dif"]
        if sin["n"] < npf.MIN_MUESTRA_VEREDICTO:
            veredicto = f'<em>muestra pequeña ({sin["n"]} partidos sin él): sin conclusión</em>'
        else:
            veredicto = (f'<span class="pf-dn">cae {cae:.1f} pts de diferencia sin él</span>' if cae >= 3
                         else f'<span class="pf-up">rinde {abs(cae):.1f} pts mejor sin él</span>' if cae <= -3 else "casi no cambia sin él")
        lineas.append(f'<div class="pf-s">Sin él: <b>{_rec(sin)}</b> ({_sg(sin["dif"])}) en {sin["n"]} · con él: <b>{_rec(con)}</b> '
                      f'({_sg(con["dif"])}) en {con["n"]} · {veredicto}</div>')
    if b["absorben"]:
        quienes = ", ".join(f'{_e(a["nombre"])} {_sg(a["d_pts"])} pts ({_sg(a["d_min"], 0)} min)' for a in b["absorben"])
        lineas.append(f'<div class="pf-s">Lo absorben: {quienes}</div>')
    return f'<div class="pf-b">{"".join(lineas)}</div>'


def _html_regreso(r) -> str:
    hace = f'regresó hace {r["desde"]} partido{"s" if r["desde"] != 1 else ""}'
    pills = [_pill(hace, "med")]
    if r["limitado"]:
        pills.append(_pill("minutos limitados", "mal"))
    perdidos = f'al menos {r["perdidos"]}' if r["desde_antes_ventana"] else f'{r["perdidos"]}'
    mins = f'{r["min_desde"]:.0f} min desde que volvió'
    if r["min_antes"]:
        mins += f' (antes {r["min_antes"]:.0f})'
    lineas = [f'<div>\u21A9\uFE0F <b>{_e(r["nombre"])}</b> {"".join(pills)}</div>',
              f'<div class="pf-s">Se perdió {perdidos} partidos · {mins} · {r["ppg_desde"]:.1f} pts</div>']
    if r["equipo_sin"] and r["equipo_desde"]:
        lineas.append(f'<div class="pf-s">Equipo: {_rec(r["equipo_desde"])} ({_sg(r["equipo_desde"]["dif"])}) desde su vuelta · '
                      f'{_rec(r["equipo_sin"])} ({_sg(r["equipo_sin"]["dif"])}) sin él</div>')
    return f'<div class="pf-b">{"".join(lineas)}</div>'


def _html_bajas_regresos(rl, rv, prof) -> str:
    cols = []
    for ab, lado in ((rl, "l"), (rv, "v")):
        d = prof.get(lado) or {}
        cuerpo = [f'<div class="pf-eq">{_e(ab)}</div>']
        if d.get("bajas_conocidas") is False:
            cuerpo.append('<div class="pf-s"><em>ESPN no entregó el parte de lesiones ahora.</em></div>')
        cuerpo += [_html_baja(b) for b in d.get("bajas") or []]
        cuerpo += [_html_regreso(r) for r in d.get("regresos") or []]
        if len(cuerpo) == 1:
            cuerpo.append('<div class="pf-s"><em>Sin bajas reportadas ni regresos recientes.</em></div>')
        cols.append(f'<div>{"".join(cuerpo)}</div>')
    return ('<div class="cx-b ancho"><div class="cx-h">\U0001FA7A Bajas, impacto y regresos de lesión</div>'
            f'<div class="pf-2">{"".join(cols)}</div>'
            '<div class="pf-s"><em>«Sin él / con él» compara los partidos de la ventana en que faltó y en que jugó (récord y diferencial de puntos); '
            'con pocos partidos es orientativo.</em></div></div>')


def _chip_concede(ab_def, grupo, x, y, ab_otro) -> str:
    """«OKC concede 24.3 pts a Guardias (+2.1 vs MIA)»: verde si la defensa es permisiva para ese atacante."""
    if x is None:
        return ""
    d = None if y is None else x - y
    clase = "bien" if d is not None and d >= 2 else "mal" if d is not None and d <= -2 else ""
    extra = f' ({_sg(d)} vs {_e(ab_otro)})' if d is not None else ""
    return _pill(f'{ab_def} concede {x:.1f} pts a {grupo.lower()}{extra}', clase)


def _html_emparejamientos(rl, rv, prof) -> str:
    """Quinteto probable emparejado por posición y altura, con lo que cada defensa permite a esa posición."""
    pares = prof.get("emparejamientos")
    if not pares:
        return ""
    conc = prof.get("concede") or {}
    cl, cv = conc.get("l") or {}, conc.get("v") or {}

    def jug(j):
        alt = f'{j["alt"]} cm · ' if j.get("alt") else ""
        pts = j["ppg5"] if j.get("ppg5") is not None else j["ppg"]
        return f'<span class="pf-pos">{_e(j["pos"])}</span><b>{_e(j["nombre"])}</b> <em>{alt}{pts:.1f} pts</em>'

    filas = []
    for p in pares:
        a, b = p["l"], p["v"]
        alt = ""
        if p["dalt"] is not None and abs(p["dalt"]) >= 5:
            quien = rl if p["dalt"] > 0 else rv
            alt = _pill(f'{quien} +{abs(p["dalt"])} cm', "med")
        chips = _chip_concede(rv, a["grupo"], cv.get(a["grupo"]), cl.get(a["grupo"]), rl) + _chip_concede(rl, b["grupo"], cl.get(b["grupo"]), cv.get(b["grupo"]), rv)
        filas.append(f'<div class="pf-m"><div class="pf-par"><span>{jug(a)}</span><span class="pf-vs">VS</span><span class="d">{jug(b)}</span></div>'
                     f'<div class="pf-chips">{alt}{chips}</div></div>')
    return ('<div class="cx-b ancho"><div class="cx-h">\U0001F6E1\uFE0F Emparejamientos probables (por posición y tamaño)</div>'
            f'<div class="pf-s"><em>{_e(rl)} (izquierda) vs {_e(rv)} (derecha). Quinteto probable = los más titulares de los últimos 5 partidos, sin bajas seguras.</em></div>'
            + "".join(filas)
            + '<div class="pf-s"><em>ESPN no publica quién defiende a quién: el cruce es orientativo (por posición y altura). «Concede» = puntos por partido que esa '
              'defensa permitió a rivales de esa posición en sus últimos partidos (verde = permisiva frente al otro equipo).</em></div></div>')


def _bloques_profundos(rl, rv, pr) -> list:
    """Bloques del análisis profundo para añadir al contexto del partido; lista vacía si no hubo datos."""
    prof = pr.get("prof")
    if not prof:
        return []
    bloques = [_html_forma(rl, rv, prof), _html_foco(rl, rv, prof)]
    bloques.append(_html_bajas_regresos(rl, rv, prof))
    emp = _html_emparejamientos(rl, rv, prof)
    if emp:
        bloques.append(emp)
    return bloques


def _html_contexto(rl, rv, pr) -> str:
    """Bloque «Contexto del partido»: descanso y viaje, ritmo, cuartos, línea contra el historial y cara a cara."""
    bloques = []

    # 5. descanso, fatiga y viaje
    if pr.get("fat_l") or pr.get("fat_v"):
        cansado = any((pr.get(k) or {}).get("aj") for k in ("fat_l", "fat_v"))
        bloques.append('<div class="cx-b"><div class="cx-h">😴 Descanso y viaje</div>'
                       + _html_fatiga(rl, pr.get("fat_l"), (pr.get("fat_l") or {}).get("aj", 0))
                       + _html_fatiga(rv, pr.get("fat_v"), (pr.get("fat_v") or {}).get("aj", 0))
                       + ('<div><em>El marcador y los picks del equipo cansado ya incluyen este ajuste.</em></div>' if cansado else "")
                       + '</div>')

    # 6. ritmo esperado
    rit = pr.get("ritmo")
    if rit:
        clase = "mal" if rit["cat"] == "lento" else "bien" if rit["cat"] == "rápido" else ""
        efecto = []
        for ab, f in ((rl, rit["f_l"]), (rv, rit["f_v"])):
            if abs(f - 1) >= 0.02:
                efecto.append(f'{_e(ab)} {f - 1:+.0%}'.replace("-", "−"))
        bloques.append(
            f'<div class="cx-b"><div class="cx-h">⏱ Ritmo esperado</div>'
            f'<div class="cx-f"><b>{rit["pos"]:.1f}</b> posesiones {_pill(rit["cat"], clase)}</div>'
            f'<div>{_e(rl)} suele jugar a <b>{rit["m_l"]:.1f}</b> · {_e(rv)} a <b>{rit["m_v"]:.1f}</b>.'
            + (f' Efecto en los picks: {" · ".join(efecto)}.' if efecto else " Sin efecto notable en los picks.") + '</div></div>')

    # 8. cuartos
    cq = pr.get("cuartos")
    if cq:
        def fila(ab, q):
            return (f'<span class="l">{_e(ab)}</span>' + "".join(f"<span>{v:.0f}</span>" for v in q)
                    + f'<span class="t">{sum(q):.0f}</span>')
        mitad = sum(cq["ql"][:2]) + sum(cq["qv"][:2])

        def rasgo(ab, r):
            t = []
            if r.get("g1") is not None:
                if r["g1"] >= 1.5:
                    t.append(f'arranca fuerte ({r["g1"]:+.1f} en el 1.º)')
                elif r["g1"] <= -1.5:
                    t.append(f'arranca lento ({r["g1"]:+.1f} en el 1.º)')
            if r.get("mejora") is not None:
                if r["mejora"] >= 2:
                    t.append(f'remonta en la 2.ª mitad ({r["mejora"]:+.1f})')
                elif r["mejora"] <= -2:
                    t.append(f'se apaga en la 2.ª mitad ({r["mejora"]:+.1f})')
            return f'<div><b>{_e(ab)}</b> {_e(", ".join(t)).replace("-", "−")}</div>' if t else ""
        bloques.append(
            '<div class="cx-b"><div class="cx-h">🕐 Cuartos proyectados</div>'
            '<div class="cx-q"><span></span><span class="h">1.º</span><span class="h">2.º</span><span class="h">3.º</span>'
            '<span class="h">4.º</span><span class="h">TOTAL</span>'
            + fila(rl, cq["ql"]) + fila(rv, cq["qv"]) + '</div>'
            f'<div>1.ª mitad proyectada: <b>{mitad:.0f}</b> pts entre ambos '
            f'<em>({sum(cq["ql"][:2]):.0f}–{sum(cq["qv"][:2]):.0f})</em></div>'
            + rasgo(rl, cq["rl"]) + rasgo(rv, cq["rv"]) + '</div>')

    # 9. línea contra el historial
    hl, hv = pr.get("hist_l"), pr.get("hist_v")
    if hl and hv and (hl["ats"][1] or hv["ats"][1] or hl["over"][1] or hv["over"][1]):
        def lado(ab, h):
            def un(par, nom):
                a, n = par
                if n < 3:
                    return f'{nom} <em>sin datos</em>'
                c = a / n
                return f'{nom} <span class="{"ok" if c >= 0.6 else "mal" if c <= 0.4 else ""}">{a}/{n}</span>'
            return f'<div><b>{_e(ab)}</b> · {un(h["ats"], "cubrió")} · {un(h["over"], "Más")}</div>'
        bloques.append('<div class="cx-b"><div class="cx-h">📈 Línea vs historial (últimos 10)</div>'
                       + lado(rl, hl) + lado(rv, hv)
                       + '<div><em>«cubrió» = hándicap · «Más» = total sobre la línea</em></div></div>')

    # 12. cara a cara de la temporada
    h2h = pr.get("h2h")
    if h2h is not None:
        if not h2h:
            cuerpo = '<div><em>Aún no se enfrentan esta temporada.</em></div>'
        else:
            gl = sum(1 for x in h2h if x["pl"] > x["pv"])
            filas = "".join(
                f'<div>{_fmt_fecha(x["fecha"])} · {"en casa" if x["sede"] == "home" else "de visita"}: '
                f'{_e(rl)} <span class="{"ok" if x["pl"] > x["pv"] else "mal"}">{x["pl"]}–{x["pv"]}</span> {_e(rv)}</div>'
                for x in h2h[-3:])
            tot = sum(x["pl"] + x["pv"] for x in h2h) / len(h2h)
            cuerpo = (f'<div><b>{_e(rl)} {gl}–{len(h2h) - gl} {_e(rv)}</b> esta temporada · total promedio <b>{tot:.0f}</b></div>'
                      + filas)
        bloques.append(f'<div class="cx-b"><div class="cx-h">⚔️ Cara a cara</div>{cuerpo}</div>')

    bloques += _bloques_profundos(rl, rv, pr)
    if not bloques:
        return ""
    return f'<div class="cx"><div class="cx-tit">🧭 Contexto del partido</div><div class="cx-grid">{"".join(bloques)}</div></div>'


def _html_pron(j, pr, logos=None) -> str:
    """Bloque del pronóstico dentro de la tarjeta: marcador proyectado, ganador (aunque no sea el favorito) y lectura de las líneas."""
    L, V = j["local"], j["visita"]
    rl, rv = L["abrev"] or L["nombre"][:3].upper(), V["abrev"] or V["nombre"][:3].upper()
    ml = pr["margen"]
    gana_l = ml >= 0
    p_gan = pr["p_local"] if gana_l else 1 - pr["p_local"]
    pl, pv = round(pr["pts_l"]), round(pr["pts_v"])
    if pl == pv:                       # un empate no se muestra: el ganador proyectado se lleva el punto
        pl, pv = (pl + 1, pv) if gana_l else (pl, pv + 1)
    m = abs(ml)
    fuerza = "Muy parejo" if m < 2 else "Ligera ventaja" if m < 5 else "Ventaja clara" if m < 9 else "Amplia ventaja"
    chips = [f'<span class="pr-chip">Margen <b>{_e(rl if gana_l else rv)} +{m:.1f}</b></span>']

    lec = _lectura_handicap(pr, j)
    if lec:
        # siempre se elige un lado: si la línea del favorito no cubre, el pick es el underdog (con sus puntos de ventaja)
        chips.append(f'<span class="pr-chip {"med" if lec["p"] < 0.58 else "ok"}">Hándicap: '
                     f'<b>{_e(lec["pick"])} {lec["pick_v"]:+g}</b>{" (underdog)" if lec["dog_pick"] else " (favorito)"} · '
                     f'{lec["p"]:.0%} <span style="opacity:.7">({_e(lec["ab"])} {lec["v"]:+g}: '
                     f'{"cubre" if lec["borde"] > 0 else "no cubre"} {lec["borde"]:+.1f})</span></span>')
    if pr.get("p_sorpresa") is not None:
        p_up = pr["p_sorpresa"]
        alerta = p_up >= _P_SORPRESA_ALERTA
        chips.append(f'<span class="pr-chip {"med" if alerta else ""}">{"⚠ " if alerta else ""}Sorpresa: '
                     f'<b>{_e(pr["dog_ab"])}</b> gana {p_up:.0%}</span>')
    lt = j.get("linea_total")
    if lt:
        mas, dif, p_lado, ajustado = _elegir_total(pr, lt)
        lado = f'▲ Más +{float(lt):.1f}' if mas else f'▼ Menos −{float(lt):.1f}'
        chips.append(f'<span class="pr-chip {"med" if ajustado else "ok"}">Total: <b>{lado} pts</b> · proyectado '
                     f'<b>{pr["total"]:.0f}</b> ({dif:+.1f}) · {p_lado:.0%}{" · ajustado" if ajustado else ""}</span>')

    def nombre_eq(ab, tid):
        """Escudo pequeño + sigla del equipo (si no hay escudo válido, solo la sigla)."""
        logo = str((logos or {}).get(str(tid), ""))
        img = ""
        if logo.startswith("https://") and not any(c in logo for c in "\"'()<> \\"):
            img = f'<img class="pr-esc" src="{_e(logo)}" alt="" width="16" height="16">'
        return f"{img}<b>{_e(ab)}</b>"

    def bajas(ab, det, tid=None):
        eq = nombre_eq(ab, tid)
        if det is None:
            return f"{eq} <em>sin datos de lesiones</em>"
        if not det:
            return f"{eq} <em>sin bajas que muevan el marcador</em>"
        # Se separan los que están fuera (Out) de los dudosos (Day-To-Day, Questionable...): cada grupo con su etiqueta
        fuera = [x for x in det if "out" in str(x[1]).lower()]
        dudas = [x for x in det if "out" not in str(x[1]).lower()]

        def lista(items, mostrar_estado):
            return ", ".join(
                f"{_e(n)}" + (f" <em>({_e(est)})</em>" if mostrar_estado and str(est).lower() != "day-to-day" else "") + f" −{pts:.1f}"
                for n, est, pts in items)

        grupos = []
        if fuera:
            grupos.append(f'<span class="pr-bj out">Out</span> {lista(fuera, False)}')
        if dudas:
            grupos.append(f'<span class="pr-bj dtd">Day-To-Day</span> {lista(dudas, True)}')
        return f"{eq} " + " &nbsp;|&nbsp; ".join(grupos)

    return (f'<div class="pr"><div class="pr-marc">'
            f'<div class="pr-eq{" gana" if gana_l else ""}"><b>{_e(rl)}</b><span class="pr-pts">{pl}</span></div>'
            f'<div class="pr-mid">Pronóstico<strong>Gana {_e(rl if gana_l else rv)} · {p_gan:.0%}</strong>{fuerza}</div>'
            f'<div class="pr-eq der{"" if gana_l else " gana"}"><span class="pr-pts">{pv}</span><b>{_e(rv)}</b></div></div>'
            f'<div class="pr-bar"><i style="width:{pr["p_local"] * 100:.1f}%"></i><i class="v" style="flex:1"></i></div>'
            f'<div class="pr-chips">{"".join(chips)}</div>'
            f'<div class="pr-bajas">🩹 {bajas(rl, pr["bajas_l"], L["id"])}<br>🩹 {bajas(rv, pr["bajas_v"], V["id"])}</div>'
            f'{_html_contexto(rl, rv, pr)}{sj.html(rl, rv, pr, {rl: L["id"], rv: V["id"]}, logos)}'
            f'{_html_picks(rl, rv, pr, {rl: L["id"], rv: V["id"]}, logos)}</div>')


def _eq_prox(eq, logos, rol, clase=""):
    """Escudo + sigla + «LOCAL»/«VISITA» de un equipo de la lista de próximos partidos."""
    ab = eq.get("abrev") or eq["nombre"][:3].upper()
    logo = str(logos.get(str(eq["id"]), ""))
    if logo.startswith("https://") and not any(c in logo for c in "\"'()<> "):
        img = f'<div class="px-lg"><img src="{_e(logo)}" alt=""></div>'
    else:
        img = f'<div class="px-ab">{_e(ab)}</div>'
    return f'<div class="px-eq {clase}">{img}<span><b title="{_e(eq["nombre"])}">{_e(ab)}</b><small>{rol}</small></span></div>'


def _linea_prox(j, pr=None) -> str:
    """Dos renglones: hándicap (con el equipo al que corresponde) y total de puntos de ambos equipos."""
    import re
    filas = []
    txt = str(j.get("linea_txt") or "").strip()
    if txt:
        m = re.match(r"^(\S+)\s+([+-]?\d+(?:\.\d+)?)$", txt)
        if m:
            ab, v = m.group(1), float(m.group(2))
            if v < 0:
                filas.append(f"🎯 Hándicap <b>{_e(ab)} {v:+g}</b> <em>(favorito)</em>")
            elif v > 0:
                filas.append(f"🎯 Hándicap <b>{_e(ab)} {v:+g}</b> <em>(underdog)</em>")
            else:
                filas.append("🎯 Hándicap <b>parejo</b> <em>(sin favorito)</em>")
        elif txt.upper() in ("EVEN", "PK", "PICK", "PICK'EM", "PICKEM"):
            filas.append("🎯 Hándicap <b>parejo</b> <em>(sin favorito)</em>")
        else:
            filas.append(f"🎯 Hándicap <b>{_e(txt)}</b>")
    lec = _lectura_handicap(pr, j) if pr else None
    if lec:       # el pick del hándicap: puede ser el underdog (+) o el favorito (−)
        filas.append(f'Pick <b class="{"px-mas" if lec["dog_pick"] else ""}">{_e(lec["pick"])} {lec["pick_v"]:+g}</b> '
                     f'<em>({"underdog" if lec["dog_pick"] else "favorito"} · {lec["p"]:.0%})</em>')
    if j.get("linea_total"):
        t = float(j["linea_total"])
        if pr:   # con pronóstico se elige un lado; sin él solo se muestra la línea
            mas = _elegir_total(pr, t)[0]
            filas.append('Total de puntos <em>(ambos)</em> ' + (f'<b class="px-mas">▲ Más +{t:.1f} pts</b>' if mas
                                                               else f'<b class="px-menos">▼ Menos −{t:.1f} pts</b>'))
        else:
            filas.append(f'Total de puntos <em>(ambos)</em> <b>{t:.1f}</b> <em>pts</em>')
    if pr and (pr.get("p_sorpresa") or 0) >= _P_SORPRESA_ALERTA:
        filas.append(f'<b class="px-menos">⚠ Sorpresa posible:</b> {_e(pr["dog_ab"])} gana {pr["p_sorpresa"]:.0%}')
    return "".join(f"<span>{f}</span>" for f in filas) or "<span><em>sin línea aún</em></span>"


# --- Registro de picks: se guardan al verlos y se corrigen solos cuando el partido termina --------------------------
# Sirve para medir cuánto acierta de verdad cada nivel de confianza. Se guarda en .cache_picks/picks.json (junto a este
# archivo); borrar esa carpeta reinicia el historial. Solo se guarda la última versión que se vio ANTES del partido.
_RUTA_REGISTRO = Path(__file__).parent / ".cache_picks" / "picks.json"
_RE_HANDICAP = re.compile(r"^(\S+)\s+([+-]?\d+(?:\.\d+)?)$")
_CLAVE_RES_TS = "nba_pk_res_ts"
_ESPERA_RESOLVER_S = 90     # cada cuánto se buscan resultados nuevos (como máximo)


def _cargar_registro() -> dict:
    try:
        return json.loads(_RUTA_REGISTRO.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _guardar_registro(reg: dict):
    try:
        _RUTA_REGISTRO.parent.mkdir(exist_ok=True)
        tmp = _RUTA_REGISTRO.with_suffix(".tmp")
        tmp.write_text(json.dumps(reg, ensure_ascii=False, default=_json_def),
                        encoding="utf-8")
        os.replace(tmp, _RUTA_REGISTRO)
    except Exception:  # noqa: BLE001
        pass


def _json_def(o):
    """Para guardar en JSON lo que venga de numpy (escalares y arreglos) sin que falle todo el guardado."""
    if hasattr(o, "tolist"):
        return o.tolist()
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def _registro_partido(j, pr, dia) -> dict:
    """Lo que se guarda de un partido: pronóstico, lectura de líneas y los picks de jugadores."""
    L, V = j["local"], j["visita"]
    rl, rv = L["abrev"] or L["nombre"][:3].upper(), V["abrev"] or V["nombre"][:3].upper()
    picks = [{"tid": str(eq["id"]), "jug": c["nombre"], "k": c["k"], "stat": c["stat"], "linea": c["linea"],
              "conf": round(c["conf"], 3), "res": None, "real": None,
              "ab": rl if eq is L else rv, "etq": list(c.get("etq") or []),
              "riesgo": bool(c.get("riesgo")), "corr": bool(c.get("corr"))}
             for eq, lista in ((L, pr.get("picks_l")), (V, pr.get("picks_v"))) for c in lista or []]
    lt = j.get("linea_total")
    fav = pr.get("fav_local")
    return {"fecha": f"{dia:%Y%m%d}", "ab_l": rl, "ab_v": rv, "margen": round(pr["margen"], 2), "total": round(pr["total"], 1),
            "total_modelo": round(pr.get("total_modelo", pr["total"]), 1),     # sin corregir: sirve para aprender el sesgo
            "fav": None if fav is None else ("l" if fav else "v"), "p_sorpresa": round(pr.get("p_sorpresa") or 0, 3),
            "linea_total": float(lt) if lt else None, "linea_txt": str(j.get("linea_txt") or ""),
            "picks": picks, "cerrado": False,
            "sim": pr.get("sim_jug")}      # simulación de jugadores de antes del partido, para verla en el historial


def _registrar(juegos, pron, dia):
    """Guarda (o actualiza, mientras el partido no termine) los picks de los partidos que se están mostrando."""
    reg, cambio = _cargar_registro(), False
    for j in juegos:
        pr = pron.get(j["id"])
        gid = str(j["id"])
        if not pr or reg.get(gid, {}).get("cerrado"):
            continue
        nuevo = json.loads(json.dumps(_registro_partido(j, pr, dia), default=_json_def))   # mismo formato que el guardado
        if reg.get(gid) != nuevo:
            reg[gid], cambio = nuevo, True
    if cambio:
        _guardar_registro(reg)


def _resolver_partido(gid, r, x) -> bool:
    """Completa el resultado de un partido terminado (x = el partido del marcador). True si quedó cerrado."""
    import ficha_equipos as fe
    pl, pv = x["local"]["puntos"], x["visita"]["puntos"]
    if pl is None or pv is None:
        return False
    r["final"] = [int(pl), int(pv)]
    for k, lado in (("id_l", "local"), ("id_v", "visita")):
        if x[lado].get("id") is not None:
            r[k] = str(x[lado]["id"])
    r["ok_gana"] = (pl > pv) == (r["margen"] >= 0)
    if r.get("fav"):
        r["sorpresa"] = (pl > pv) != (r["fav"] == "l")       # ganó el underdog
    lt = r.get("linea_total")
    if lt and pl + pv != lt:
        r["ok_total"] = ((pl + pv) > lt) == (r["total"] >= lt)
    m = _RE_HANDICAP.match(str(r.get("linea_txt") or "").strip())
    if m and m.group(1) in (r["ab_l"], r["ab_v"]) and float(m.group(2)) != 0:
        ab, v = m.group(1), float(m.group(2))
        real = ((pl - pv) if ab == r["ab_l"] else (pv - pl)) + v          # >0: ese equipo cubrió
        pred = (r["margen"] if ab == r["ab_l"] else -r["margen"]) + v
        if real != 0:
            r["ok_hand"] = (real > 0) == (pred > 0)
    caja = fe._caja(gid)     # el partido ya terminó: es seguro bajar y guardar su box score
    if not caja:
        return False
    por = {(jg.get("team_id"), normalizar(jg.get("Jugador", ""))): jg for jg in caja.get("jugadores", [])}
    for p in r["picks"]:
        jg = por.get((p["tid"], p["k"]))
        if not jg or not (jg.get("MIN") or 0) > 0:
            p["res"] = "dnp"                   # no jugó: el pick no cuenta
            continue
        v = _valor(jg, p["stat"])
        if v is not None:
            p["real"], p["res"] = v, ("ok" if v > p["linea"] else "no")
    r["cerrado"] = True
    return True


def _resolver_registro():
    """Busca los partidos guardados que ya terminaron y anota sus resultados (a lo más cada _ESPERA_RESOLVER_S)."""
    ss = st.session_state
    if time.time() - ss.get(_CLAVE_RES_TS, 0) < _ESPERA_RESOLVER_S:
        return
    ss[_CLAVE_RES_TS] = time.time()
    reg = _cargar_registro()
    pend = [g for g, r in reg.items() if not r.get("cerrado")]
    hoy, cambio = f"{_hoy_et():%Y%m%d}", False
    for fecha in sorted({reg[g]["fecha"] for g in pend if reg[g]["fecha"] <= hoy}):
        try:
            marcador = {str(x["id"]): x for x in nba.scoreboard(fecha)}
        except Exception:  # noqa: BLE001
            continue
        for gid in pend:
            x = marcador.get(gid)
            if reg[gid]["fecha"] == fecha and x and x["estado"] == "post":
                cambio = _resolver_partido(gid, reg[gid], x) or cambio
    if cambio:
        _guardar_registro(reg)


_ALIAS_AB = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}
_DIAS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _mapa_escudos():
    """({id: url del escudo}, {sigla ESPN: id}) para pintar los escudos del historial; vacíos si no se pueden leer."""
    try:
        import ficha_equipos
        eqs = ficha_equipos._equipos()
        return {e["id"]: e["logo"] for e in eqs}, {e["abbr"].upper(): e["id"] for e in eqs}
    except Exception:  # noqa: BLE001
        return {}, {}


@st.cache_data(ttl=3600, show_spinner=False)
def _fotos_plantel(tid) -> dict:
    """{nombre normalizado: url de la foto} de los jugadores del plantel de un equipo (vacío si ESPN no responde)."""
    try:
        import ficha_equipos
        js = ficha_equipos._json(f"{nba.BASE}/teams/{tid}/roster") or {}
        crudos = js.get("athletes") or []
        if crudos and isinstance(crudos[0], dict) and "items" in crudos[0]:
            crudos = [a for g in crudos for a in g.get("items", [])]
        out = {}
        for a in crudos:
            url = (a.get("headshot") or {}).get("href") or (
                f"https://a.espncdn.com/i/headshots/nba/players/full/{a['id']}.png" if a.get("id") else "")
            if url.startswith("https://") and not any(c in url for c in "\"'()<> \\"):
                out[normalizar(a.get("displayName") or a.get("fullName") or "")] = url
        return out
    except Exception:  # noqa: BLE001
        return {}


def _cara(nombre, url) -> str:
    ini = "".join(w[0] for w in nombre.split()[:2]).upper()
    img = (f'<img src="{_e(url)}" alt="" loading="lazy" style="position:absolute;left:0;top:2px;width:30px !important;'
           f'height:30px !important;max-width:none !important;object-fit:cover;object-position:top center;margin:0;border-radius:0">') if url else ""
    return (f'<span class="pk-fc" style="position:relative;display:inline-block;flex:none;width:30px;height:30px;min-width:30px;'
            f'border-radius:50%;overflow:hidden">{_e(ini) if not url else ""}{img}</span>')


def _escudo_hist(ab, tid, logos) -> str:
    logo = str(logos.get(str(tid), ""))
    if logo.startswith("https://") and not any(c in logo for c in "\"'()<> \\"):
        return (f'<div class="hx-lg"><img src="{_e(logo)}" alt="" style="width:22px !important;height:22px !important;'
                f'max-width:none !important;margin:0;border-radius:0;object-fit:contain"></div>')
    return f'<div class="hx-lg">{_e(ab)}</div>'


def _veredictos(r):
    """Qué se pronosticó del partido y si se dio: [(clase, etiqueta, valor, detalle, equipo)] con clase ok / no / med (empate con la línea).

    «equipo» es la abreviatura del equipo del pick (para mostrar su escudo) o None si el veredicto no es de un equipo."""
    fin = r.get("final")
    if not fin:
        return []
    pl, pv = int(fin[0]), int(fin[1])
    ab_l, ab_v, m = r["ab_l"], r["ab_v"], r["margen"]
    out = []
    sl, sv = _simulacion(r)          # el ganador es el del marcador simulado (el mismo que muestra la fila «Simulación»)
    gana_l = sl > sv
    out.append(("ok" if (pl > pv) == gana_l else "no", "Ganador", ab_l if gana_l else ab_v,
                f'Ganó {ab_l if pl > pv else ab_v}', ab_l if gana_l else ab_v))
    h = _RE_HANDICAP.match(str(r.get("linea_txt") or "").strip())
    if h and h.group(1) in (ab_l, ab_v) and float(h.group(2)) != 0:
        ab, v = h.group(1), float(h.group(2))
        otro = ab_v if ab == ab_l else ab_l
        borde = (m if ab == ab_l else -m) + v
        pick, pv_ = (ab, v) if borde >= 0 else (otro, -v)
        real = ((pl - pv) if pick == ab_l else (pv - pl)) + pv_
        out.append(("med" if real == 0 else "ok" if real > 0 else "no", "Hándicap", f"{pick} {pv_:+g}".replace("-", "−"),
                    "", pick))
    lt = r.get("linea_total")
    if lt:
        mas, tot = r["total"] >= lt, pl + pv
        out.append(("med" if tot == lt else "ok" if (tot > lt) == mas else "no", "Total de puntos",
                    f'{"Más" if mas else "Menos"} {lt:.1f}', f"Simulado {sl + sv} pts · Real {tot} pts", None))
    return out


def _simulacion(r):
    """Marcador proyectado (local, visita) tal como se mostraba en el pronóstico."""
    m = r["margen"]
    tl, tv = round((r["total"] + m) / 2), round((r["total"] - m) / 2)
    if tl == tv:
        tl, tv = (tl + 1, tv) if m >= 0 else (tl, tv + 1)
    return tl, tv


def _marcador_hist(ab_l, id_l, pl, ab_v, id_v, pv, logos) -> str:
    return (f'<div class="hx-m"><div class="hx-e{" gana" if pl > pv else ""}">{_escudo_hist(ab_l, id_l, logos)}{_e(ab_l)}<b>{pl}</b></div>'
            f'<span class="hx-sep">–</span>'
            f'<div class="hx-e{" gana" if pv > pl else ""}"><b>{pv}</b>{_e(ab_v)}{_escudo_hist(ab_v, id_v, logos)}</div></div>')


def _completar_sim(reg, limite):
    """Partidos ya jugados que se guardaron SIN simulación de jugadores: la recalcula (una vez) para poder compararla con lo real.

    Usa los datos de hoy, no los exactos de antes del partido; por eso queda marcada como «recalculada» (sim_retro)."""
    hechos = sorted((g for g, r in reg.items() if r.get("cerrado")
                     and any(p.get("res") in ("ok", "no", "dnp") for p in r.get("picks", []))),
                    key=lambda g: reg[g]["fecha"], reverse=True)[:limite]
    cambio = False
    faltan = [g for g in hechos if not reg[g].get("sim") and not reg[g].get("sim_intento")]
    if not faltan:
        return
    with st.spinner("Recalculando la simulación de partidos que se guardaron sin ella…"):
        for g in faltan:
            r = reg[g]
            r["sim_intento"], cambio = True, True
            try:
                if not (r.get("id_l") and r.get("id_v")):
                    continue
                f = r["fecha"]
                j = {"id": g, "local": {"id": r["id_l"], "abrev": r["ab_l"], "nombre": r["ab_l"]},
                     "visita": {"id": r["id_v"], "abrev": r["ab_v"], "nombre": r["ab_v"]},
                     "linea_txt": r.get("linea_txt"), "linea_total": r.get("linea_total")}
                pr = _pronostico(str(r["id_l"]), str(r["id_v"]), f"{f[:4]}-{f[4:6]}-{f[6:8]}")
                if not pr:
                    continue
                pr = _con_mercado(pr, j, 0.0)
                if pr.get("sim_jug"):
                    r["sim"] = json.loads(json.dumps(pr["sim_jug"], default=_json_def))
                    r["sim_retro"] = True
            except Exception:  # noqa: BLE001 — es un extra: si falla, el partido se queda sin la tabla
                continue
    if cambio:
        _guardar_registro(reg)


def _html_comparacion(gid, r, id_l, id_v) -> str:
    """Tabla «simulado vs real» por jugador de un partido ya jugado: sirve para ver si el sistema acertó cada estadística."""
    import ficha_equipos as fe
    sim = r.get("sim")
    if not sim or not gid:
        return ""
    try:
        caja = fe._caja(str(gid))
    except Exception:  # noqa: BLE001
        caja = None
    if not caja:
        return ""
    por = {(str(jg.get("team_id")), normalizar(jg.get("Jugador", ""))): jg for jg in caja.get("jugadores", [])}
    cols = (("PTS", "PTS", 4.0), ("REB", "REB", 2.0), ("AST", "AST", 2.0), ("3PM", "3P", 1.0))
    th = "padding:6px 8px;text-align:center;font-size:.72rem;color:#475569;border-bottom:1px solid #e2e8f0;white-space:nowrap"
    cabeza = "".join('<th style="' + th + '">' + t + "</th>" for _, t, _ in cols)
    bloques, tot_ok, tot_n = [], 0, 0
    for ab, tid in ((r["ab_l"], id_l), (r["ab_v"], id_v)):
        eq = (sim.get("equipos") or {}).get(ab)
        if not eq:
            continue
        filas = []
        for f in eq.get("filas", []):
            jg = por.get((str(tid), f.get("k") or normalizar(f.get("nombre", ""))))
            if not jg or not (jg.get("MIN") or 0) > 0:
                continue                      # no jugó: no hay nada que comparar
            celdas = []
            for stat, tit, tol in cols:
                try:
                    est = f["est"][stat][0]
                except Exception:  # noqa: BLE001
                    est = None
                real = _valor(jg, stat)
                if est is None or real is None:
                    celdas.append(f'<td style="{th};border-bottom:1px solid #f1f5f9">—</td>')
                    continue
                bien = abs(real - est) <= tol
                tot_ok, tot_n = tot_ok + bien, tot_n + 1
                col, fondo = ("#166534", "#dcfce7") if bien else ("#991b1b", "#fee2e2")
                pk = [c for c in f.get("picks", []) if c.get("stat") == stat]
                marca = "".join(f'<div style="font-size:.66rem;color:#475569">Más de {c["linea"]:g}: '
                                f'{"✅" if real > c["linea"] else "❌"}</div>' for c in pk)
                celdas.append(f'<td style="padding:6px 8px;text-align:center;background:{fondo};border-bottom:1px solid #fff">'
                              f'<div style="font-weight:800;color:{col}">{real:g}</div>'
                              f'<div style="font-size:.68rem;color:#64748b">sim {est:.1f}</div>{marca}</td>')
            filas.append(f'<tr><td style="padding:6px 8px;font-weight:600;border-bottom:1px solid #f1f5f9;white-space:nowrap">'
                         f'{_e(f.get("nombre", ""))}</td>{"".join(celdas)}</tr>')
        if filas:
            bloques.append(f'<div style="margin-top:8px;font-weight:800;color:#334155">{_e(ab)}</div>'
                           f'<table style="width:100%;border-collapse:collapse;font-size:.82rem"><tr>'
                           f'<th style="{th};text-align:left">Jugador</th>{cabeza}</tr>'
                           f'{"".join(filas)}</table>')
    if not bloques:
        return ""
    resumen = f" · {tot_ok} de {tot_n} dentro del margen" if tot_n else ""
    return (f'<details open style="margin-top:10px;border:1px solid #c7d2fe;border-radius:12px;background:#fff;padding:8px 12px">'
            f'<summary style="cursor:pointer;font-weight:800;color:#4338ca">🎯 Simulado vs real por jugador{resumen}</summary>'
            f'<div style="font-size:.72rem;color:#64748b;margin:4px 0">Verde: el real quedó cerca de lo simulado '
            f'(±4 pts, ±2 reb, ±2 ast, ±1 triple). Rojo: se desvió. ✅/❌ = si se dio el pick.</div>'
            + ('<div style="font-size:.72rem;color:#b45309;margin:4px 0">⚠ Simulación recalculada hoy: este partido se guardó antes de '
               'que se guardara la simulación, así que usa datos de ahora y no los exactos de antes del partido.</div>' if r.get("sim_retro") else "")
            + f'{"".join(bloques)}</details>')


def _html_historial(reg, limite, con_sim=True) -> str:
    """Partidos ya resueltos: escudos, fecha, marcador, si se dieron hándicap/total/marcador y los picks de jugadores."""
    logos, abr_id = _mapa_escudos()
    juegos = [dict(r, _gid=g) for g, r in reg.items() if any(p.get("res") in ("ok", "no", "dnp") for p in r.get("picks", []))]
    juegos.sort(key=lambda r: r["fecha"], reverse=True)

    def item(p, fotos):
        res = p.get("res")
        clase, marca = {"ok": ("hit", "✅ Acertado"), "no": ("fail", "❌ Fallado")}.get(res, ("dnp", "➖ No jugó"))
        etq = p.get("etq") or []
        sube = f' <em>({_e(" · ".join(etq))})</em>' if etq else ""
        aviso = " ⚠" if p.get("riesgo") else ""
        enlace = ' <span class="pk-cor" title="Depende de lo mismo que otro pick">🔗</span>' if p.get("corr") else ""
        real = f' · hizo {p["real"]:g}' if p.get("real") is not None else ""
        cara = _cara(p["jug"], fotos.get(p.get("k") or normalizar(p["jug"])))
        return (f'<div class="pk-it {clase}"><span class="pk-q">{cara}<span><b>{_e(p["jug"])}</b>{aviso} · Más de {p["linea"]:.1f} '
                f'{_NOM_STAT[p["stat"]]}{sube}{enlace}</span></span>'
                f'<span class="pk-r"><span class="pk-m">{marca}{real}</span><span class="pk-p">{p["conf"]:.0%}</span></span></div>')

    out = []
    for r in juegos[:limite]:
        ab_l, ab_v = r["ab_l"], r["ab_v"]
        id_l = r.get("id_l") or abr_id.get(_ALIAS_AB.get(ab_l, ab_l).upper()) or abr_id.get(ab_l.upper())
        id_v = r.get("id_v") or abr_id.get(_ALIAS_AB.get(ab_v, ab_v).upper()) or abr_id.get(ab_v.upper())
        ps = [p for p in r["picks"] if p.get("res") in ("ok", "no", "dnp")]

        def lado(p):
            if p.get("ab") in (ab_l, ab_v):
                return p["ab"]
            return ab_l if id_l and str(p.get("tid")) == str(id_l) else ab_v if id_v and str(p.get("tid")) == str(id_v) else None
        fotos = {}
        for i in {i for i in (id_l, id_v) if i}:
            fotos.update(_fotos_plantel(i))
        cols = []
        for ab, tid in ((ab_l, id_l), (ab_v, id_v)):
            mios = [p for p in ps if lado(p) == ab]
            if mios:
                cols.append((f'{_escudo_hist(ab, tid, logos)}<span>{_e(ab)} · picks</span>', mios))
        resto = [p for p in ps if lado(p) is None]
        if resto:
            cols.append((f"<span>🎯 {_e(ab_l)} / {_e(ab_v)} · picks</span>", resto))
        cuerpo = "".join(f'<div><div class="pk-tit hx-t">{t}</div><div class="pk-lista">'
                         f'{"".join(item(p, fotos) for p in sorted(l, key=lambda q: -q["conf"]))}</div></div>' for t, l in cols)
        fin = r.get("final")
        try:
            d = date(int(r["fecha"][:4]), int(r["fecha"][4:6]), int(r["fecha"][6:8]))
            fecha = f'{_DIAS[d.weekday()]} {d.day} {_MESES[d.month - 1]}<small>{d.year}</small>'
        except ValueError:
            fecha = _e(r["fecha"])
        if fin:
            pl, pv = int(fin[0]), int(fin[1])
            sl, sv = _simulacion(r)
            marc = (f'<div class="hx-sc"><div class="hx-sr sim"><span class="hx-et">🧪 Simulación</span>'
                    f'{_marcador_hist(ab_l, id_l, sl, ab_v, id_v, sv, logos)}<span class="hx-ch"></span></div>'
                    f'<div class="hx-sr res"><span class="hx-et">🏁 Resultado</span>'
                    f'{_marcador_hist(ab_l, id_l, pl, ab_v, id_v, pv, logos)}<span class="hx-ch pr-chip">Final</span></div></div>')
        else:
            marc = ""
        valid = [p for p in ps if p["res"] in ("ok", "no")]
        aciertos = sum(1 for p in valid if p["res"] == "ok")
        ids = {ab_l: id_l, ab_v: id_v}
        chips = "".join(f'<div class="hx-vc {c}"><span class="hx-vi">{"✓" if c == "ok" else "=" if c == "med" else "✕"}</span>'
                        f'<span class="hx-vt"><small>{_e(et)}</small>'
                        f'<b>{_escudo_hist(eq, ids.get(eq), logos) if eq else ""}{_e(val)}</b><em>{_e(det)}</em></span></div>'
                        for c, et, val, det, eq in _veredictos(r))
        out.append(f'<div class="hx-g"><div class="hx-h"><div class="hx-f">{fecha}</div>'
                   f'<div class="hx-r">Picks: {aciertos} de {len(valid)} se dieron</div></div>'
                   f'{marc}<div class="hx-v">{chips}</div><div class="pk-cols">{cuerpo}</div>'
                   + (sj.html(ab_l, ab_v, {"sim_jug": r["sim"]}, {ab_l: id_l, ab_v: id_v}, logos)
                      if (con_sim and r.get("sim")) else "") + '</div>')
    return "".join(out)


def _html_pendientes(reg, con_sim=True) -> str:
    """Partidos guardados que aún no terminan (por jugar o en juego): sus picks con la confianza prometida."""
    logos, abr_id = _mapa_escudos()
    out = []
    for r in sorted((r for r in reg.values() if not r.get("cerrado") and r.get("picks")), key=lambda r: r["fecha"]):
        ab_l, ab_v = r["ab_l"], r["ab_v"]
        id_l = r.get("id_l") or abr_id.get(_ALIAS_AB.get(ab_l, ab_l).upper()) or abr_id.get(ab_l.upper())
        id_v = r.get("id_v") or abr_id.get(_ALIAS_AB.get(ab_v, ab_v).upper()) or abr_id.get(ab_v.upper())
        cols = []
        for ab, tid in ((ab_l, id_l), (ab_v, id_v)):
            mios = sorted((p for p in r["picks"] if p.get("ab") == ab), key=lambda q: -q["conf"])
            if not mios:
                continue
            fotos = _fotos_plantel(tid) if tid else {}
            its = "".join(
                f'<div class="pk-it {"riesgo" if p.get("riesgo") else "alto" if p["conf"] >= 0.9 else "med"}"><span class="pk-q">'
                f'{_cara(p["jug"], fotos.get(p.get("k") or normalizar(p["jug"])))}<span><b>{_e(p["jug"])}</b>'
                f'{" ⚠" if p.get("riesgo") else ""} · Más de {p["linea"]:.1f} {_NOM_STAT[p["stat"]]}</span></span>'
                f'<span class="pk-p">{p["conf"]:.0%}</span></div>' for p in mios)
            cols.append(f'<div><div class="pk-tit hx-t">{_escudo_hist(ab, tid, logos)}<span>{_e(ab)} · picks</span></div>'
                        f'<div class="pk-lista">{its}</div></div>')
        try:
            d = date(int(r["fecha"][:4]), int(r["fecha"][4:6]), int(r["fecha"][6:8]))
            fecha = f'{_DIAS[d.weekday()]} {d.day} {_MESES[d.month - 1]}<small>{d.year}</small>'
        except ValueError:
            fecha = _e(r["fecha"])
        out.append(f'<div class="hx-g"><div class="hx-h"><div class="hx-f">{fecha}</div>'
                   f'<div class="hx-r">{_e(ab_l)} vs {_e(ab_v)} · pendiente</div></div>'
                   f'<div class="hx-m" style="margin-bottom:10px">'
                   f'<div class="hx-e">{_escudo_hist(ab_l, id_l, logos)}{_e(ab_l)}</div><span class="hx-sep">vs</span>'
                   f'<div class="hx-e">{_e(ab_v)}{_escudo_hist(ab_v, id_v, logos)}</div></div>'
                   + (sj.html(ab_l, ab_v, {"sim_jug": r["sim"]}, {ab_l: id_l, ab_v: id_v}, logos)
                      if (con_sim and r.get("sim")) else f'<div class="pk-cols">{"".join(cols)}</div>') + '</div>')
    return "".join(out)


def _filtrar_registro(reg, vista):
    """Partidos del registro según la vista elegida: Hoy, Mañana, En vivo o Todos."""
    from datetime import timedelta
    hoy = _hoy_et()
    if vista == "Hoy":
        return {g: r for g, r in reg.items() if r["fecha"] == f"{hoy:%Y%m%d}"}
    if vista == "Mañana":
        return {g: r for g, r in reg.items() if r["fecha"] == f"{hoy + timedelta(days=1):%Y%m%d}"}
    if vista == "En vivo":
        vivos = set()
        for d in (hoy - timedelta(days=1), hoy):
            try:
                vivos |= {str(x["id"]) for x in nba.scoreboard(f"{d:%Y%m%d}") if x["estado"] == "in"}
            except Exception:  # noqa: BLE001
                pass
        return {g: r for g, r in reg.items() if str(g) in vivos}
    return reg


def _panel_historial():
    """Desplegable con cuánto aciertan los picks y el pronóstico, comparado con la confianza que prometían."""
    _resolver_registro()
    reg_total = _cargar_registro()
    res_t = sum(1 for r in reg_total.values() for p in r.get("picks", []) if p.get("res") in ("ok", "no"))
    pen_t = sum(1 for r in reg_total.values() for p in r.get("picks", []) if p.get("res") is None)
    st.caption(f"{res_t} picks resueltos")
    if True:
        st.markdown(f"<style>{sj.CSS}</style>", unsafe_allow_html=True)
        vista = "Todos"
        con_sim = st.toggle("🎲 Simulación de jugadores", value=True, key="nba_hist_sim",
                            help="Muestra, en cada partido ya jugado, la simulación de jugadores y rotaciones que se hizo antes del partido.")
        reg = _filtrar_registro(reg_total, vista)
        if not reg:
            st.info({"Hoy": "No hay partidos guardados de hoy.", "Mañana": "No hay partidos guardados de mañana.",
                     "En vivo": "No hay partidos en vivo guardados ahora mismo."}.get(vista, "Todavía no hay partidos guardados."))
            return
        filas, juegos = [], {"ok_gana": [], "ok_total": [], "ok_hand": []}
        for r in reg.values():
            for k in juegos:
                if k in r:
                    juegos[k].append(bool(r[k]))
            for p in r.get("picks", []):
                if p.get("res") in ("ok", "no"):
                    filas.append({"Fecha": r["fecha"], "Jugador": p["jug"], "stat": p["stat"], "conf": p["conf"],
                                  "Pick": f'Más de {p["linea"]:.1f} {_NOM_STAT[p["stat"]]}', "Real": p["real"], "ok": p["res"] == "ok"})
        n = len(filas)
        if not n and not any(juegos.values()):
            st.info("Todavía no hay resultados de estos partidos. Los picks se guardan solos al verlos y se corrigen cuando termina el partido.")
            return
        if n:
            df = pd.DataFrame(filas)
            k = st.columns(3)
            k[0].metric("Picks resueltos", n)
            k[1].metric("Acierto real", f"{df.ok.mean():.0%}")
            k[2].metric("Confianza que prometían", f"{df.conf.mean():.0%}")
            if n < 50:
                st.caption("Con menos de 50 picks resueltos el porcentaje varía mucho: tómalo como una primera señal.")
            st.markdown('<div class="hp-tit">¿Acierta lo que promete?</div>', unsafe_allow_html=True)
            cal = []
            for lo, hi, nom in ((0.9, 1.01, "90–100 %"), (0.8, 0.9, "80–90 %"), (0.7, 0.8, "70–80 %")):
                s = df[(df.conf >= lo) & (df.conf < hi)]
                if len(s):
                    cal.append({"Confianza": nom, "Picks": len(s), "Prometida": f"{s.conf.mean():.0%}", "Acierto real": f"{s.ok.mean():.0%}"})
            st.dataframe(pd.DataFrame(cal), hide_index=True, use_container_width=True)
            st.markdown('<div class="hp-tit">Por estadística</div>', unsafe_allow_html=True)
            est = [{"Estadística": _NOM_STAT[s], "Picks": len(g), "Acierto real": f"{g.ok.mean():.0%}"} for s, g in df.groupby("stat")]
            st.dataframe(pd.DataFrame(est), hide_index=True, use_container_width=True)
            st.markdown('<div class="hp-tit">Picks resueltos</div>', unsafe_allow_html=True)
            todos = False
            if vista == "Todos":
                todos = st.toggle("Ver todos los partidos", key="hist_todos")
            limite = 10_000 if (todos or vista != "Todos") else 8
            if con_sim:
                _completar_sim(reg_total, limite)
            st.markdown(_html_historial(reg, limite, con_sim), unsafe_allow_html=True)
        if any(juegos.values()):
            st.markdown('<div class="hp-tit">Pronóstico del partido</div>', unsafe_allow_html=True)
            nombres = {"ok_gana": "Ganador", "ok_hand": "Hándicap (cubre o no)", "ok_total": "Total de puntos (más / menos)"}
            tabla = [{"Mercado": nombres[k], "Partidos": len(v), "Aciertos": sum(v), "Acierto": f"{sum(v) / len(v):.0%}"}
                     for k, v in juegos.items() if v]
            st.dataframe(pd.DataFrame(tabla), hide_index=True, use_container_width=True)
            sor = [r for r in reg.values() if "sorpresa" in r]
            if sor:
                ganaron = sum(1 for r in sor if r["sorpresa"])
                alerta = [r for r in sor if (r.get("p_sorpresa") or 0) >= _P_SORPRESA_ALERTA]
                txt = f"Underdogs que ganaron: {ganaron} de {len(sor)} ({ganaron / len(sor):.0%})."
                if alerta:
                    acertadas = sum(1 for r in alerta if r["sorpresa"])
                    txt += f" Con alerta de sorpresa: {acertadas} de {len(alerta)}."
                st.caption(txt)
        st.caption(f"Se guarda en {_RUTA_REGISTRO.parent.name}/{_RUTA_REGISTRO.name}. No cuentan los picks de jugadores que no jugaron.")


# --- Colores de cada equipo para el fondo degradado de su tarjeta --------------------------------------------------
# (color del borde de la tarjeta, color hacia el centro). El local va a la izquierda y la visita a la derecha.
_COLORES = {
    "ATL": ("#E03A3E", "#C1D32F"), "BOS": ("#007A33", "#BA9653"), "BKN": ("#1F1F1F", "#8E959C"),
    "CHA": ("#1D1160", "#00A3B8"), "CHI": ("#CE1141", "#4A4A4A"), "CLE": ("#6A0F2E", "#C23A5E"),
    "DAL": ("#00538C", "#8FB3D1"), "DEN": ("#0E2240", "#FEC524"), "DET": ("#C8102E", "#1D42BA"),
    "GS": ("#1D428A", "#FFC72C"), "HOU": ("#CE1141", "#A7B1B7"), "IND": ("#002D62", "#FDBB30"),
    "LAC": ("#C8102E", "#1D428A"), "LAL": ("#552583", "#FDB927"), "MEM": ("#12173F", "#5D9BD6"),
    "MIA": ("#98002E", "#F9A01B"), "MIL": ("#00471B", "#C9BC8E"), "MIN": ("#0C2340", "#78BE20"),
    "NO": ("#0C2340", "#C8102E"), "NY": ("#006BB6", "#F58426"), "OKC": ("#007AC1", "#EF3B24"),
    "ORL": ("#0077C0", "#A7B1B7"), "PHI": ("#006BB6", "#ED174C"), "PHX": ("#1D1160", "#E56020"),
    "POR": ("#E03A3E", "#3A3A3A"), "SAC": ("#5A2D81", "#8A97A0"), "SA": ("#1A1A1A", "#9AA5AC"),
    "TOR": ("#CE1141", "#3A3A3A"), "UTAH": ("#002B5C", "#F9A01B"), "WSH": ("#002B5C", "#E31837"),
}
_ALIAS_ABREV = {"GSW": "GS", "NOP": "NO", "NYK": "NY", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH"}


def _colores_equipo(eq):
    """(borde, centro) en hexadecimal; si el equipo no está en la tabla, se deriva de su abreviatura."""
    ab = (eq.get("abrev") or eq["nombre"][:3]).upper()
    ab = _ALIAS_ABREV.get(ab, ab)
    if ab in _COLORES:
        return _COLORES[ab]
    h = zlib.crc32(ab.encode()) % 360
    return f"hsl({h},65%,32%)", f"hsl({h},70%,60%)"


_OPACIDAD_ESCUDO = 0.09   # transparencia de los escudos de fondo (0 = invisible, 1 = opaco)
_TAM_ESCUDO = 230         # tamaño (px) de cada escudo de fondo


def _rgba(color, alfa):
    """'#RRGGBB' o 'hsl(...)' -> mismo color con transparencia."""
    if color.startswith("#"):
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
        return f"rgba({r},{g},{b},{alfa})"
    return color.replace("hsl(", "hsla(").rstrip(")") + f",{alfa})"


def _url_escudo(logos, eq):
    """URL del escudo si es https y segura para ir dentro de un CSS; si no, ''."""
    logo = str(logos.get(str(eq["id"]), ""))
    return logo if logo.startswith("https://") and not any(c in logo for c in "\"'()<> \\") else ""


def _css_fondos_juegos(juegos, logos) -> str:
    """Una regla por partido: panel blanco sólido (no deja ver el fondo de la página) con la identidad de cada equipo.

    - Franja fina arriba con los colores de ambos equipos (local a la izquierda, visita a la derecha).
    - Un velo muy suave del color de cada equipo en su esquina superior; el centro queda blanco.
    - Escudo grande y translúcido de cada equipo en su esquina, detrás del contenido (::before / ::after con z-index negativo).
    """
    reglas = []
    for j in juegos:
        sel = f".st-key-nba_prox_fila_{j['id']}"
        l_borde, l_centro = _colores_equipo(j["local"])
        v_borde, v_centro = _colores_equipo(j["visita"])
        fondo = (f"linear-gradient(90deg,{l_borde} 0%,{l_centro} 22%,{v_centro} 78%,{v_borde} 100%) top/100% 5px no-repeat,"
                 f"radial-gradient(560px 300px at 0% 0%,{_rgba(l_borde, .13)},transparent 70%),"
                 f"radial-gradient(560px 300px at 100% 0%,{_rgba(v_borde, .13)},transparent 70%)")
        reglas.append(
            f"{sel}{{position:relative;isolation:isolate;overflow:hidden !important;background:{fondo},#fff !important;"
            f"border:1px solid #d9e0ec !important;"
            f"box-shadow:0 1px 2px rgba(15,23,42,.05),0 16px 34px -18px rgba(15,23,42,.38) !important}}")
        for pseudo, lado, eq in (("before", "left", j["local"]), ("after", "right", j["visita"])):
            url = _url_escudo(logos, eq)
            if url:
                reglas.append(
                    f"{sel}::{pseudo}{{content:'';position:absolute;{lado}:-46px;top:-24px;"
                    f"width:{_TAM_ESCUDO}px;height:{_TAM_ESCUDO}px;background:url('{url}') center/contain no-repeat;"
                    f"opacity:{_OPACIDAD_ESCUDO};pointer-events:none;z-index:-1}}")
    return "".join(reglas)


_CSS_VIVO = """
.vv-est{flex:none;text-align:center;padding:7px 12px;border-radius:12px;background:#fef2f2;color:#b91c1c;font-weight:800;font-size:.72rem;
  letter-spacing:.08em;line-height:1.35}
.vv-est small{display:block;font-weight:600;letter-spacing:.02em;color:#7f1d1d;font-size:.72rem}
.vv-pts{font-family:'Oswald',sans-serif;font-size:1.9rem;font-weight:600;color:#1e1b4b;min-width:2.2ch;text-align:center}
.vv-pts.lider{color:#047857}
.vv-sep{color:#94a3b8;font-weight:600}
"""


def _proyeccion_vivo(j):
    """Puntos finales de ambos a ritmo actual, a partir del texto «5:32 - 3rd Quarter» de ESPN. None si es muy pronto o hay prórroga."""
    import re
    txt = str(j.get("detalle") or "")
    tot = (j["local"]["puntos"] or 0) + (j["visita"]["puntos"] or 0)
    if "OT" in txt.upper():
        return None
    m = re.search(r"(\d+):(\d+)(?:\.\d+)?\s*-\s*(\d)", txt)
    if m:
        q = int(m.group(3))
        trans = (q - 1) * 12 + 12 - (int(m.group(1)) + int(m.group(2)) / 60)
    elif re.search(r"half", txt, re.I):
        trans = 24.0
    else:
        m = re.search(r"end of (\d)", txt, re.I)
        trans = int(m.group(1)) * 12.0 if m else None
    if not trans or trans < 6:
        return None
    return tot / trans * 48.0


def _html_vivo(j, logos, pr=None) -> str:
    """Una fila de partido en juego: marcador en vivo + las mismas líneas y picks de los partidos por jugar."""
    L, V = j["local"], j["visita"]
    pl, pv = L["puntos"] or 0, V["puntos"] or 0
    en_juego = j["estado"] == "in"
    det = _e(str(j.get("detalle") or "en juego")) if en_juego else "FINAL"
    extra = []
    proy = _proyeccion_vivo(j) if en_juego else None
    if proy is not None and j.get("linea_total"):
        dif = proy - float(j["linea_total"])
        extra.append(f'<span>Ritmo actual <b class="{"px-mas" if dif > 0 else "px-menos"}">{proy:.0f}</b> pts entre ambos '
                     f'<em>({dif:+.1f} vs línea)</em></span>')
    elif proy is not None:
        extra.append(f"<span>Ritmo actual <b>{proy:.0f}</b> pts entre ambos</span>")
    margen = abs(pl - pv)
    ab = _e((L if pl > pv else V).get("abrev") or "")
    extra.append(f"<span>{'Empatado' if margen == 0 else f'Gana {ab} por {margen:.0f}'}</span>")
    return (f'<div class="px"><div class="vv-est">{"🔴 EN VIVO" if en_juego else "🏁"}<small>{det}</small></div>'
            f'{_eq_prox(L, logos, "Local", "loc")}<span class="vv-pts{" lider" if pl > pv else ""}">{pl:.0f}</span>'
            f'<span class="vv-sep">–</span><span class="vv-pts{" lider" if pv > pl else ""}">{pv:.0f}</span>'
            f'{_eq_prox(V, logos, "Visita")}<div class="px-lin">{_linea_prox(j, pr)}{"".join(extra)}</div></div>')


def _vivo_fila(gid, fecha, logos, pr, j0):
    """Marcador de un partido en juego. Va en un fragmento: se refresca solo sin recalcular pronósticos ni picks."""
    try:
        j = next((x for x in nba.scoreboard(fecha) if str(x["id"]) == str(gid)), j0)
    except Exception:  # noqa: BLE001
        j = j0
    st.markdown(_html_vivo(j, logos, pr), unsafe_allow_html=True)


def _panel_cuotas(juegos, pron):
    """Tabla de todos los picks del día: escribes la cuota que ofrece la casa y calcula si hay valor y cuánto apostar."""
    filas = []
    for j in sorted(juegos, key=lambda x: x["fecha"] or ""):
        pr = pron.get(j["id"])
        if not pr:
            continue
        for lado, clave in (("local", "picks_l"), ("visita", "picks_v")):
            for c in pr.get(clave) or []:
                justa, minima = _cuota_pick(c["conf"])
                filas.append({"Partido": f'{j["local"]["abrev"]} vs {j["visita"]["abrev"]}', "Pick": f'{c["nombre"]} · Más de {c["linea"]:.1f} {_NOM_STAT[c["stat"]]}',
                              "Nivel": _grado_pick(c), "Prob.": c["conf"], "Cuota justa": round(justa, 2),
                              "Cuota mínima con valor": round(minima, 2), "Cuota ofrecida": None})
    if not filas:
        return
    with st.expander("💰 Evaluador de cuotas · escribe la cuota que te ofrece la casa"):
        st.caption("La probabilidad es una estimación prudente (la menor entre historial, modelo y simulación), no una garantía. "
                   "Una cuota solo conviene si es mayor que la mínima con valor; si es menor, el pick puede salir y aun así no compensa a largo plazo.")
        df = pd.DataFrame(filas)
        ed = st.data_editor(df, hide_index=True, use_container_width=True, key="nba_cuotas_ed",
                            disabled=[c for c in df.columns if c != "Cuota ofrecida"],
                            column_config={"Prob.": st.column_config.NumberColumn(format="percent"),
                                           "Cuota ofrecida": st.column_config.NumberColumn(min_value=1.01, max_value=50.0, step=0.01, format="%.2f")})
        res = []
        for _, r in ed.dropna(subset=["Cuota ofrecida"]).iterrows():
            q, pb = float(r["Cuota ofrecida"]), float(r["Prob."])
            ev = pb * q - 1
            kelly = max(0.0, ev / (q - 1)) * 0.25
            res.append({"Pick": r["Pick"], "Cuota": q, "Valor esperado": ev,
                        "Apuesta sugerida (% del banco)": min(kelly, 0.02),
                        "Veredicto": "✅ Hay valor" if ev >= _MARGEN_VALOR else "➖ Marginal: no compensa el error del modelo" if ev >= 0 else "❌ Sin valor"})
        if res:
            st.dataframe(pd.DataFrame(res), hide_index=True, use_container_width=True,
                         column_config={"Valor esperado": st.column_config.NumberColumn(format="percent"),
                                        "Apuesta sugerida (% del banco)": st.column_config.NumberColumn(format="percent")})
            st.caption("Apuesta sugerida = ¼ de Kelly con tope de 2 % del banco. Con valor esperado negativo no se sugiere apostar.")


def _proximos_cuerpo():
    from datetime import timedelta

    import ficha_equipos

    st.subheader("📅 Próximos partidos")
    cuando = st.radio("Día", ["Hoy", "Mañana", "En vivo", "📊 Historial"], horizontal=True, key="nba_prox_dia",
                      label_visibility="collapsed")
    if cuando == "📊 Historial":
        try:
            _panel_historial()
        except Exception as e:  # noqa: BLE001
            st.caption(f"No se pudo leer el historial de picks: {e}")
        return
    en_vivo = cuando == "En vivo"
    dia = _hoy_et() + (timedelta(days=1) if cuando == "Mañana" else timedelta(0))
    mostrar = st.toggle("📊 Pronóstico por equipo (rendimiento reciente y bajas)", value=True, key="nba_prox_pron",
                        help="Proyecta los puntos de cada equipo con sus últimos partidos (ritmo, ataque y defensa), la ventaja de local "
                             "y el peso de los lesionados. La primera vez descarga box scores y tarda; después queda guardado.")
    try:
        juegos = [j for j in nba.scoreboard(f"{dia:%Y%m%d}") if j["estado"] == ("in" if en_vivo else "pre")]
        nombres = nba.equipos().set_index("id")["Equipo"].to_dict()
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo leer el calendario de ESPN: {e}")
        return
    try:
        logos = {e["id"]: e["logo"] for e in ficha_equipos._equipos()}
    except Exception:  # noqa: BLE001
        logos = {}
    if not juegos:
        st.info("No hay partidos en vivo ahora mismo." if en_vivo else "No hay partidos por jugar ese día.")
        return
    st.markdown(f"<style>{_css_fondos_juegos(juegos, logos)}</style>", unsafe_allow_html=True)

    pron = {}
    if mostrar:
        with st.spinner("Calculando pronósticos…"):
            for j in juegos:
                try:
                    pron[j["id"]] = _pronostico(str(j["local"]["id"]), str(j["visita"]["id"]), f"{dia:%Y-%m-%d}")
                except Exception:  # noqa: BLE001
                    pron[j["id"]] = None
        # anclar al mercado: corrige el sesgo del modelo hacia el «Menos» y calcula favorito, underdog y sorpresa
        por_id = {j["id"]: j for j in juegos}
        try:
            difs = [p["total"] - float(por_id[g]["linea_total"]) for g, p in pron.items() if p and por_id[g].get("linea_total")]
            sesgo = _sesgo_total(difs)
        except Exception:  # noqa: BLE001
            sesgo = 0.0
        for g, p in list(pron.items()):
            if p:
                pron[g] = _con_mercado(p, por_id[g], sesgo)
        if not en_vivo:     # en juego las líneas se mueven: el registro conserva la versión de antes del partido
            try:
                _registrar(juegos, pron, dia)      # guarda los picks para poder medir después cuánto aciertan
            except Exception:  # noqa: BLE001
                pass

    for j in sorted(juegos, key=lambda x: x["fecha"] or ""):
        L, V = j["local"], j["visita"]
        hora = pd.to_datetime(j["fecha"], utc=True).tz_convert(ZONA).strftime("%H:%M") if j["fecha"] else "—"
        with st.container(key=f"nba_prox_fila_{j['id']}"):
            c1, c2 = st.columns([9, 1.6], vertical_alignment="center")
            if en_vivo:
                with c1:
                    st.fragment(run_every=INTERVALO_S)(_vivo_fila)(j["id"], f"{dia:%Y%m%d}", logos, pron.get(j["id"]), j)
            else:
                c1.markdown(
                    f'<div class="px"><span class="px-hora">{hora}</span>{_eq_prox(L, logos, "Local", "loc")}'
                    f'<span class="px-at">vs</span>{_eq_prox(V, logos, "Visita")}'
                    f'<div class="px-lin">{_linea_prox(j, pron.get(j["id"]))}</div></div>',
                    unsafe_allow_html=True)
            c2.button("🎯 Analizar", key=f"nba_prox_lin_{j['id']}", use_container_width=True, type="primary",
                      on_click=_a_lineas, args=(L["id"], V["id"], j.get("linea_total")),
                      help="Carga estos dos equipos (A = local, B = visita) y la línea de total de ESPN en el análisis de abajo.")
            if mostrar:
                pr = pron.get(j["id"])
                st.markdown(_html_pron(j, pr, logos) if pr else
                            '<div class="pr"><div class="pr-bajas">Sin datos suficientes para proyectar este partido.</div></div>',
                            unsafe_allow_html=True)
    if mostrar and pron:
        _panel_cuotas(juegos, pron)


def proximos():
    """Partidos por jugar (hoy o mañana, hora del Este) para la pestaña «Líneas». No necesita la liga."""
    st.markdown(f"<style>{_CSS_PROX}{_CSS_VIVO}{sj.CSS}</style>", unsafe_allow_html=True)
    with st.container(key="nba_prox_panel"):
        _proximos_cuerpo()
