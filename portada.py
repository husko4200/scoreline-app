"""Portada personalizada: tus equipos y jugadores favoritos con su próximo partido, forma reciente, línea del día y lesiones.

Uso (en la página de Inicio):
    portada.render()

Se refresca sola cada 60 s (solo esa zona, sin recargar la página). Las tarjetas usan la clase .tarjeta, así que heredan el
foco de luz y la inclinación 3D de movimiento.py. No hay tablas aquí: todo son tarjetas.
"""
from html import escape as e

import pandas as pd
import streamlit as st

import favoritos
import favoritos_datos as fd
from common import ZONA

_CSS = """
<style>
.pt-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: .35rem 0 .9rem;
}
@media (max-width: 960px) {
  .pt-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 520px) {
  .pt-kpi-grid { grid-template-columns: 1fr; }
}
.pt-kpi {
  position: relative;
  overflow: hidden;
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 14px;
  padding: 13px 15px 12px;
  box-shadow: 0 4px 16px -4px rgba(15, 23, 42, .06), 0 1px 2px rgba(15, 23, 42, .03);
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.pt-kpi:hover {
  transform: translateY(-2px);
  border-color: #CBD5E1;
  box-shadow: 0 10px 22px -6px rgba(15, 23, 42, .10);
}
.pt-kpi::before {
  content: "";
  position: absolute;
  left: 0; right: 0; top: 0;
  height: 3px;
  background: var(--kpi-acc, #4F46E5);
}
.pt-kpi--indigo { --kpi-acc: #4F46E5; }
.pt-kpi--violet { --kpi-acc: #7C3AED; }
.pt-kpi--live   { --kpi-acc: #E11D48; }
.pt-kpi--gold   { --kpi-acc: #F59E0B; }
.pt-kpi-head {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 6px;
}
.pt-kpi-ico {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  display: grid;
  place-items: center;
  font-size: .8rem;
  background: #F1F5F9;
  flex-shrink: 0;
}
.pt-kpi--indigo .pt-kpi-ico { background: #EEF2FF; }
.pt-kpi--violet .pt-kpi-ico { background: #F5F3FF; }
.pt-kpi--live   .pt-kpi-ico { background: #FFF1F2; }
.pt-kpi--gold   .pt-kpi-ico { background: #FFFBEB; }
.pt-kpi-lbl {
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: #64748B;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pt-kpi-val {
  font-family: 'Roboto Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-size: 1.65rem;
  font-weight: 800;
  line-height: 1.1;
  color: #0F172A;
}
.pt-kpi--live .pt-kpi-val { color: #E11D48; }
.pt-kpi-sub {
  margin-top: 4px;
  font-size: .72rem;
  font-weight: 500;
  color: #64748B;
}
.pt-kpi-name {
  font-family: 'Roboto Condensed', 'Roboto', sans-serif;
  font-size: 1.12rem;
  font-weight: 700;
  line-height: 1.2;
  color: #0F172A;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pt-kpi-pill {
  display: inline-block;
  margin-top: 5px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #FFFBEB;
  border: 1px solid #FDE68A;
  color: #B45309;
  font-family: 'Roboto Mono', monospace;
  font-size: .72rem;
  font-weight: 700;
}
.pt-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; margin: .4rem 0 1.2rem; }
.pt-card {
  display: flex; flex-direction: column; gap: .75rem; padding: 1.1rem 1.15rem 1.05rem !important;
  background: linear-gradient(155deg, #0F172A 0%, #1E1B4B 100%) !important;
  border: 1px solid rgba(196,181,253,.20) !important;
  border-radius: 16px !important;
  box-shadow: 0 10px 26px -12px rgba(15,23,42,.55) !important;
  color: #F8FAFC !important;
}
.pt-top { display: flex; align-items: center; gap: .8rem; }
.pt-logo { width: 46px; height: 46px; object-fit: contain; flex: none; filter: drop-shadow(0 4px 10px rgba(0,0,0,.35)); }
.pt-foto { width: 54px; height: 54px; border-radius: 50%; object-fit: cover; object-position: 50% 8%; flex: none;
  background: radial-gradient(circle at 50% 28%, #4F46E5, #1E1B4B); box-shadow: 0 0 0 2px rgba(196,181,253,.55), 0 6px 14px -6px rgba(0,0,0,.6); }
.pt-id { min-width: 0; flex: 1; }
.pt-nom { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-weight: 800; font-size: 1.04rem; line-height: 1.15; color: #FFFFFF !important;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pt-sub { font-size: .76rem; color: #CBD5E1 !important; margin-top: .14rem; }
.pt-tag { flex: none; font-size: .68rem; font-weight: 700; letter-spacing: .04em; padding: .24rem .62rem; border-radius: 999px; white-space: nowrap;
  color: #E0E7FF; background: rgba(99,102,241,.28); border: 1px solid rgba(165,180,252,.3); }
.pt-tag.ya { color: #fff; background: #E11D48; border-color: #FDA4AF; }
.pt-tag.pronto { color: #111827; background: #FBBF24; border-color: #FDE68A; }
.pt-prox { font-size: .88rem; color: #E2E8F0 !important; }
.pt-prox b { color: #FFFFFF !important; }
.pt-linea { display: flex; flex-wrap: wrap; gap: .4rem; }
.pt-linea span { font-size: .78rem; font-weight: 600; font-variant-numeric: tabular-nums; padding: .24rem .62rem; border-radius: 8px;
  background: rgba(255,255,255,.08); color: #F1F5F9; border: 1px solid rgba(255,255,255,.14); }
.pt-linea span i { font-style: normal; font-weight: 500; color: #CBD5E1; margin-right: .3rem; }
.pt-forma { display: flex; align-items: center; gap: 5px; }
.pt-forma small { font-size: .68rem; letter-spacing: .08em; text-transform: uppercase; color: #94A3B8; margin-right: .25rem; }
.pt-f { width: 24px; height: 24px; border-radius: 7px; display: grid; place-items: center; font-size: .72rem; font-weight: 800; color: #fff; cursor: default; }
.pt-f.g { background: #10B981; } .pt-f.p { background: #EF4444; }
.pt-racha { margin-left: auto; font-size: .78rem; font-weight: 700; color: #E2E8F0; }
.pt-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.pt-stats div { text-align: center; padding: .45rem .2rem; border-radius: 10px; background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.12); }
.pt-stats b { display: block; font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-size: 1.3rem; font-variant-numeric: tabular-nums; color: #FFFFFF; }
.pt-stats span { font-size: .66rem; letter-spacing: .1em; color: #CBD5E1; }
.pt-spark { display: flex; align-items: flex-end; gap: 4px; height: 34px; }
.pt-spark i { flex: 1; border-radius: 4px 4px 2px 2px; background: linear-gradient(180deg, #34D399, #10B981); min-height: 4px; }
.pt-chip { display: inline-flex; align-items: center; gap: .35rem; font-size: .76rem; font-weight: 700; padding: .22rem .65rem; border-radius: 999px; width: fit-content; }
.pt-chip.out { color: #FECACA; background: rgba(220,38,38,.28); } .pt-chip.dudoso { color: #FED7AA; background: rgba(234,88,12,.28); }
.pt-chip.duda { color: #FEF08A; background: rgba(202,138,4,.28); } .pt-chip.probable { color: #BBF7D0; background: rgba(22,163,74,.28); }
.pt-chip.ok { color: #A7F3D0; background: rgba(16,185,129,.22); border: 1px solid rgba(52,211,153,.3); }
.pt-bajas { font-size: .78rem; color: #CBD5E1; line-height: 1.5; }
.pt-bajas b { color: #FFFFFF; }
.pt-vacio { text-align: center; padding: 1.6rem 1rem; border: 1px dashed var(--pl-borde, #D9DFEA); border-radius: 16px; background: #fff; color: var(--pl-suave, #64748B); margin: .4rem 0 1rem; }
.pt-vacio b { display: block; font-size: 1.05rem; color: var(--pl-ink, #0F172A); margin-bottom: .25rem; }
</style>
"""

_SEVERIDAD = {"out": 0, "dudoso": 1, "duda": 2, "probable": 3}
_ETQ_ESTADO = {"out": "Fuera", "dudoso": "Dudoso", "duda": "En duda", "probable": "Probable"}


# ---------------------------------------------------------------- piezas
def _etiqueta_partido(prox):
    """(texto del chip, clase) según cuánto falta."""
    texto, mins = fd.cuando(prox["fecha"])
    if prox.get("estado") == "in":
        return "🔴 En juego", "ya"
    if mins is None:
        return texto, ""
    return fd.cuenta_regresiva(mins), ("pronto" if 0 <= mins <= 120 else "")


def _html_proximo(cal):
    prox = cal.get("proximo")
    if not prox:
        return '<div class="pt-prox">📅 Sin próximo partido programado.</div>', "", ""
    texto, _ = fd.cuando(prox["fecha"])
    sede = "vs" if prox["local"] else "@"
    chip, clase = _etiqueta_partido(prox)
    html = f'<div class="pt-prox">📅 <b>{sede} {e(prox["rival"] or prox["rival_nombre"])}</b> · {e(texto)}</div>'
    return html, chip, clase


def _html_linea(prox):
    if not prox:
        return ""
    lin = fd.linea(prox["evento"], prox["fecha"])
    if not lin:
        return '<div class="pt-linea"><span><i>Línea</i>aún sin publicar</span></div>'
    partes = []
    if lin.get("txt"):
        partes.append(f'<span><i>Handicap</i>{e(str(lin["txt"]))}</span>')
    if lin.get("total") is not None:
        partes.append(f'<span><i>Total</i>{lin["total"]:g}</span>')
    return f'<div class="pt-linea">{"".join(partes)}</div>'


def _html_forma(cal):
    forma = cal.get("forma") or []
    if not forma:
        return ""
    chips = "".join(
        f'<span class="pt-f {"g" if g["res"] == "G" else "p"}" title="{"vs" if g["local"] else "@"} {e(g["rival"])} · {g["pf"]}-{g["pc"]}">{g["res"]}</span>'
        for g in forma)
    racha = f'<span class="pt-racha">Racha {e(cal["racha"])}</span>' if cal.get("racha") else ""
    return f'<div class="pt-forma"><small>Forma</small>{chips}{racha}</div>'


def _html_bajas_equipo(tid, les):
    if les is None:
        return '<div class="pt-bajas">🩹 Lesiones: no se pudieron leer ahora.</div>'
    mias = [x for x in les.values() if x["equipo_id"] == str(tid)]
    if not mias:
        return '<div class="pt-bajas">🩹 Sin lesionados reportados.</div>'
    mias.sort(key=lambda x: _SEVERIDAD.get(fd.nivel_lesion(x["estado"]), 9))
    vistos = ", ".join(f'{e(x["nombre"])} ({e(_ETQ_ESTADO[fd.nivel_lesion(x["estado"])])})' for x in mias[:3])
    mas = f" y {len(mias) - 3} más" if len(mias) > 3 else ""
    return f'<div class="pt-bajas">🩹 <b>{len(mias)} baja{"s" if len(mias) != 1 else ""}:</b> {vistos}{mas}</div>'


def _tarjeta_equipo(eq, cal, les):
    prox_html, chip, clase = _html_proximo(cal)
    tag = f'<span class="pt-tag {clase}">{e(chip)}</span>' if chip else ""
    return (f'<div class="tarjeta pt-card"><div class="pt-top"><img class="pt-logo" src="{e(fd.escudo(eq["abrev"]))}" alt="">'
            f'<div class="pt-id"><div class="pt-nom">{e(eq["nombre"])}</div><div class="pt-sub">Equipo favorito</div></div>{tag}</div>'
            f'{prox_html}{_html_linea(cal.get("proximo"))}{_html_forma(cal)}{_html_bajas_equipo(eq["id"], les)}</div>')


def _chip_lesion(pid, les):
    if les is None:
        return '<span class="pt-chip duda">🩹 Lesiones no disponibles</span>'
    x = les.get(str(pid))
    if not x:
        return '<span class="pt-chip ok">✅ Sin reporte de lesión</span>'
    n = fd.nivel_lesion(x["estado"])
    detalle = f' · {e(x["lesion"])}' if x.get("lesion") else ""
    vuelve = f' · vuelve ~{e(x["regreso"])}' if x.get("regreso") else ""
    return f'<span class="pt-chip {n}">🩹 {e(x["estado"])}{detalle}{vuelve}</span>'


def _tarjeta_jugador(pid, info, forma, cal, les):
    nombre = info["nombre"] if info else f"Jugador {pid}"
    sigla = info["equipo"] if info else ""
    prox_html, chip, clase = _html_proximo(cal)
    tag = f'<span class="pt-tag {clase}">{e(chip)}</span>' if chip else ""
    if forma:
        v = lambda x: "–" if x is None else f"{x:g}"   # noqa: E731
        tope = max(forma["serie"] + [1])
        barras = "".join(f'<i title="{p:g} pts" style="height:{max(8, round(100 * p / tope))}%"></i>' for p in forma["serie"])
        stats = (f'<div class="pt-stats"><div><b>{v(forma["pts"])}</b><span>PTS</span></div><div><b>{v(forma["reb"])}</b><span>REB</span></div>'
                 f'<div><b>{v(forma["ast"])}</b><span>AST</span></div></div><div class="pt-spark" title="Puntos de sus últimos {forma["n"]} partidos">{barras}</div>')
    else:
        stats = '<div class="pt-bajas">📈 Sin partidos recientes para mostrar.</div>'
    return (f'<div class="tarjeta pt-card"><div class="pt-top"><img class="pt-foto" src="{e(fd.foto(pid))}" alt="">'
            f'<div class="pt-id"><div class="pt-nom">{e(nombre)}</div><div class="pt-sub">{e(sigla)} · Jugador favorito · últimos 5</div></div>{tag}</div>'
            f'{_chip_lesion(pid, les)}{stats}{prox_html}{_html_linea(cal.get("proximo"))}</div>')


# ---------------------------------------------------------------- administrar
def _guardar_eq():
    favoritos.guardar_equipos(st.session_state.get("pt_eq", []))


def _guardar_jug():
    favoritos.guardar_jugadores(st.session_state.get("pt_jug", []))


def _administrar():
    eqs, jugs = favoritos.equipos(), favoritos.jugadores()
    st.session_state["pt_eq"], st.session_state["pt_jug"] = eqs, jugs     # reflejar cambios hechos en otras vistas (p. ej. Jugadores)
    mapa, info = fd.mapa_equipos(), fd.jugadores_info()
    op_eq = sorted(set(mapa) | set(eqs), key=lambda i: mapa.get(i, {}).get("nombre", i))
    op_j = sorted(set(info) | set(jugs), key=lambda i: info.get(i, {}).get("nombre", i))
    with st.expander("⚙️ Administrar favoritos", expanded=not (eqs or jugs)):
        st.multiselect("Equipos favoritos", op_eq, key="pt_eq", on_change=_guardar_eq,
                       format_func=lambda i: mapa.get(i, {}).get("nombre", f"Equipo {i}"), placeholder="Elige tus equipos…")
        if info:
            st.multiselect("Jugadores favoritos (los mismos de la vista Jugadores)", op_j, key="pt_jug", on_change=_guardar_jug,
                           format_func=lambda i: (f'{info[i]["nombre"]} ({info[i]["equipo"]})' if i in info else f"Jugador {i}"),
                           placeholder="Busca un jugador…")
        else:
            st.caption("La lista de jugadores no está disponible ahora; los favoritos de jugadores se conservan.")
        if st.session_state.get("jug_fav_error"):
            st.warning("No se pudo escribir el archivo de favoritos; se conservan solo mientras dure la sesión.")


# ---------------------------------------------------------------- portada
@st.fragment(run_every=60)
def _cuerpo():
    eqs, jugs = favoritos.equipos(), favoritos.jugadores()
    if not (eqs or jugs):
        st.markdown('<div class="pt-vacio"><b>Aún no tienes favoritos</b>Elige equipos o jugadores abajo y aquí verás su próximo partido, '
                    'su forma, la línea del día y sus lesiones.</div>', unsafe_allow_html=True)
        return
    mapa, info = fd.mapa_equipos(), fd.jugadores_info()
    with st.spinner("Cargando tus favoritos…"):
        fd.precargar(eqs, jugs)        # todo a la vez; lo de abajo ya sale de la caché
        les = fd.lesiones()

        items_eq = []
        en_juego_o_hoy = 0
        mejor_racha = ("–", 0)
        for tid in eqs:
            eq = mapa.get(tid)
            if not eq:
                continue
            cal = fd.calendario_seguro(tid)
            prox = cal.get("proximo") or {}
            txt_c, mins = fd.cuando(prox.get("fecha"))
            es_hoy_vivo = (prox.get("estado") == "in") or (mins is not None and mins <= 24 * 60)
            if es_hoy_vivo:
                en_juego_o_hoy += 1
            racha_txt = cal.get("racha") or ""
            if racha_txt.startswith("G"):
                try:
                    n_r = int(racha_txt[1:])
                    if n_r > mejor_racha[1]:
                        mejor_racha = (f"{eq['abrev']} ({racha_txt})", n_r)
                except ValueError:
                    pass
            items_eq.append({
                "tipo": "eq",
                "nombre": eq["nombre"],
                "abrev": eq["abrev"],
                "hoy": es_hoy_vivo,
                "html": _tarjeta_equipo(eq, cal, les),
            })

        items_jug = []
        top_anotador = ("–", None, 0.0)
        for pid in jugs:
            inf = info.get(pid)
            eq = fd.equipo_por_abrev(inf["equipo"]) if inf else None
            cal = fd.calendario_seguro(eq["id"]) if eq else {"proximo": None, "forma": [], "racha": ""}
            forma = fd.forma_jugador_segura(pid)
            prox = cal.get("proximo") or {}
            _, mins = fd.cuando(prox.get("fecha"))
            es_hoy_vivo = (prox.get("estado") == "in") or (mins is not None and mins <= 24 * 60)
            nom = inf["nombre"] if inf else f"Jugador {pid}"
            ab = inf["equipo"] if inf else ""
            if forma and forma.get("pts") is not None and float(forma["pts"]) > top_anotador[2]:
                partes_nom = nom.split()
                nom_corto = f"{partes_nom[0][0]}. {' '.join(partes_nom[1:])}" if len(partes_nom) > 1 else nom
                top_anotador = (nom_corto, f"{forma['pts']:g} pts prom.", float(forma["pts"]))
            items_jug.append({
                "tipo": "jug",
                "nombre": nom,
                "abrev": ab,
                "hoy": es_hoy_vivo,
                "html": _tarjeta_jugador(pid, inf, forma, cal, les),
            })

    # 1. KPIs resumen de Tu portada
    top_pill = f'<span class="pt-kpi-pill">{e(top_anotador[1])}</span>' if top_anotador[1] else '<div class="pt-kpi-sub">Sin datos</div>'
    st.markdown(
        f'<div class="pt-kpi-grid">'
        f'<div class="pt-kpi pt-kpi--indigo">'
        f'<div class="pt-kpi-head"><span class="pt-kpi-ico">🛡️</span><span class="pt-kpi-lbl">Equipos favoritos</span></div>'
        f'<div class="pt-kpi-val">{len(items_eq)}</div>'
        f'<div class="pt-kpi-sub">En seguimiento</div>'
        f'</div>'
        f'<div class="pt-kpi pt-kpi--violet">'
        f'<div class="pt-kpi-head"><span class="pt-kpi-ico">👤</span><span class="pt-kpi-lbl">Jugadores favoritos</span></div>'
        f'<div class="pt-kpi-val">{len(items_jug)}</div>'
        f'<div class="pt-kpi-sub">Con forma reciente</div>'
        f'</div>'
        f'<div class="pt-kpi pt-kpi--live">'
        f'<div class="pt-kpi-head"><span class="pt-kpi-ico">🔥</span><span class="pt-kpi-lbl">Juegan hoy / en vivo</span></div>'
        f'<div class="pt-kpi-val">{en_juego_o_hoy}</div>'
        f'<div class="pt-kpi-sub">Partidos activos</div>'
        f'</div>'
        f'<div class="pt-kpi pt-kpi--gold">'
        f'<div class="pt-kpi-head"><span class="pt-kpi-ico">🏆</span><span class="pt-kpi-lbl">Top anotador (5 PJ)</span></div>'
        f'<div class="pt-kpi-name" title="{e(top_anotador[0])}">{e(top_anotador[0])}</div>'
        f'{top_pill}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 2. Controles de filtro + buscador
    c_flt, c_bus = st.columns([2.6, 1.4], vertical_alignment="center")
    opciones_flt = [
        f"🔥 Hoy / En vivo",
        f"🛡️ Equipos ({len(items_eq)})",
        f"👤 Jugadores ({len(items_jug)})",
        f"⭐ Todos ({len(items_eq) + len(items_jug)})",
    ]
    with c_flt:
        sel = st.pills(
            "Vista portada",
            opciones_flt,
            default=opciones_flt[0] if en_juego_o_hoy > 0 else opciones_flt[1],
            key="pt_filtro",
            label_visibility="collapsed",
        ) if hasattr(st, "pills") else st.radio(
            "Vista portada",
            opciones_flt,
            horizontal=True,
            key="pt_filtro",
            label_visibility="collapsed",
        )
        sel = sel or opciones_flt[0]
    busq = c_bus.text_input("Buscar favorito", placeholder="Filtrar equipo o jugador...", key="pt_busq", label_visibility="collapsed")

    todos = items_eq + items_jug
    q = (busq or "").strip().lower()
    filtrados = []
    for it in todos:
        if sel.startswith("🔥") and not it["hoy"]:
            continue
        if sel.startswith("🛡️") and it["tipo"] != "eq":
            continue
        if sel.startswith("👤") and it["tipo"] != "jug":
            continue
        if q and q not in f"{it['nombre']} {it['abrev']}".lower():
            continue
        filtrados.append(it)

    if not filtrados:
        st.info("No hay favoritos que coincidan con este filtro. Prueba seleccionando **Todos**.")
    else:
        ver_todos = st.session_state.get("pt_ver_todos", False)
        limite = len(filtrados) if ver_todos else 6
        visibles = filtrados[:limite]
        st.markdown(f'<div class="pt-grid">{"".join(it["html"] for it in visibles)}</div>', unsafe_allow_html=True)
        if len(filtrados) > 6:
            lbl = "Mostrar menos (6)" if ver_todos else f"Ver todos ({len(filtrados)})"
            if st.button(lbl, key="pt_btn_todos"):
                st.session_state["pt_ver_todos"] = not ver_todos
                st.rerun()

    st.caption(f"Actualizado {pd.Timestamp.now(tz=ZONA):%H:%M:%S} · se refresca solo cada minuto · lesiones y líneas según ESPN")


def render():
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown("### ⭐ Tu portada")
    _cuerpo()
    _administrar()
    st.divider()