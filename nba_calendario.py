"""Calendario mensual NBA: muestra cuántos partidos hay cada día y los enfrentamientos al elegir un día."""
import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import streamlit as st

import favoritos_datos as fd
import nba
from common import _session

try:
    from zoneinfo import ZoneInfo
    _TZ_CHILE = ZoneInfo("America/Santiago")
except Exception:  # noqa: BLE001
    _TZ_CHILE = timezone(timedelta(hours=-3))

_DIAS_SEM = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
_MESES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


@st.cache_data(ttl=900, show_spinner=False)
def _partidos_mes(anio: int, mes: int) -> dict[str, list[dict]]:
    """Descarga el scoreboard de todos los días del mes desde ESPN (en paralelo) y agrupa por fecha Chile."""
    _, num_dias = calendar.monthrange(anio, mes)
    fechas_api = [f"{anio}{mes:02d}{d:02d}" for d in range(1, num_dias + 1)]

    def _fetch(f_str):
        try:
            r = _session.get(f"{nba.BASE}/scoreboard?dates={f_str}", timeout=6)
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        resps = list(pool.map(_fetch, fechas_api))

    por_dia: dict[str, list[dict]] = {}
    vistos: set[str] = set()
    for datos in resps:
        for ev in (datos or {}).get("events", []) or []:
            eid = str(ev.get("id") or "")
            if not eid or eid in vistos:
                continue
            vistos.add(eid)
            comps = ev.get("competitions") or []
            if not comps:
                continue
            c = comps[0]
            fecha_iso = c.get("date") or ev.get("date") or ""
            try:
                dt_cl = datetime.fromisoformat(str(fecha_iso).replace("Z", "+00:00")).astimezone(_TZ_CHILE)
                clave_dia = dt_cl.strftime("%Y-%m-%d")
                hora_cl = dt_cl.strftime("%H:%M")
            except Exception:  # noqa: BLE001
                continue
            teams = c.get("competitors") or []
            if len(teams) < 2:
                continue
            home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
            away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
            st_type = (c.get("status") or ev.get("status") or {}).get("type") or {}
            state = st_type.get("state") or "pre"
            por_dia.setdefault(clave_dia, []).append({
                "id": eid,
                "hora": hora_cl,
                "state": state,
                "home": (home.get("team") or {}).get("shortDisplayName") or "Local",
                "home_ab": (home.get("team") or {}).get("abbreviation") or "",
                "home_sc": home.get("score") or "",
                "away": (away.get("team") or {}).get("shortDisplayName") or "Visita",
                "away_ab": (away.get("team") or {}).get("abbreviation") or "",
                "away_sc": away.get("score") or "",
            })
    for lista in por_dia.values():
        lista.sort(key=lambda x: x["hora"])
    return por_dia


def render():
    """Dibuja el calendario del mes con conteo de partidos por día y detalle al pulsar un día."""
    hoy = datetime.now(_TZ_CHILE).date()
    st.session_state.setdefault("nba_cal_anio", hoy.year)
    st.session_state.setdefault("nba_cal_mes", hoy.month)
    st.session_state.setdefault("nba_cal_sel", hoy.strftime("%Y-%m-%d"))

    c_prev, c_tit, c_next = st.columns([1, 3, 1], vertical_alignment="center")
    if c_prev.button("◀ Mes anterior", key="cal_prev", use_container_width=True):
        m = st.session_state["nba_cal_mes"] - 1
        a = st.session_state["nba_cal_anio"]
        if m < 1:
            m, a = 12, a - 1
        st.session_state["nba_cal_mes"], st.session_state["nba_cal_anio"] = m, a
        st.rerun()

    anio = st.session_state["nba_cal_anio"]
    mes = st.session_state["nba_cal_mes"]
    c_tit.markdown(f"<h3 style='text-align:center;margin:0;'>🗓️ {_MESES[mes]} {anio}</h3>", unsafe_allow_html=True)

    if c_next.button("Mes siguiente ▶", key="cal_next", use_container_width=True):
        m = st.session_state["nba_cal_mes"] + 1
        a = st.session_state["nba_cal_anio"]
        if m > 12:
            m, a = 1, a + 1
        st.session_state["nba_cal_mes"], st.session_state["nba_cal_anio"] = m, a
        st.rerun()

    with st.spinner("Cargando calendario de partidos NBA..."):
        por_dia = _partidos_mes(anio, mes)

    # Cabecera días de la semana
    cols_h = st.columns(7)
    for col, nom in zip(cols_h, _DIAS_SEM):
        col.markdown(f"<div style='text-align:center;font-weight:700;font-size:.8rem;color:#64748B;'>{nom}</div>", unsafe_allow_html=True)

    cal = calendar.Calendar(firstweekday=0)
    semanas = cal.monthdatescalendar(anio, mes)
    sel_actual = st.session_state["nba_cal_sel"]

    for sem in semanas:
        cols = st.columns(7, gap="small")
        for col, d in zip(cols, sem):
            with col:
                if d.month != mes:
                    st.markdown("<div style='height:48px;'></div>", unsafe_allow_html=True)
                    continue
                clave = d.strftime("%Y-%m-%d")
                n = len(por_dia.get(clave, []))
                es_sel = (clave == sel_actual)
                etq = f"{d.day}\n({n} pj)" if n else f"{d.day}"
                if st.button(
                    etq,
                    key=f"cal_d_{clave}",
                    type="primary" if es_sel else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["nba_cal_sel"] = clave
                    st.rerun()

    st.divider()
    sel_dt = date.fromisoformat(sel_actual) if sel_actual else hoy
    lista = por_dia.get(sel_actual, [])
    st.subheader(f"Enfrentamientos del {sel_dt:%d/%m/%Y} ({len(lista)} partidos · hora Chile)")
    if not lista:
        st.info("No hay partidos NBA programados para este día.")
        return

    for m in lista:
        with st.container(border=True):
            c1, c2, c3 = st.columns([2.2, 1.2, 2.2], vertical_alignment="center")
            esc_a = fd.escudo(m["away_ab"])
            esc_h = fd.escudo(m["home_ab"])
            c1.markdown(
                f"<div style='display:flex;align-items:center;gap:8px;'>"
                f"<img src='{esc_a}' width='24'> <b>{m['away']}</b></div>",
                unsafe_allow_html=True,
            )
            if m["state"] in ("in", "post"):
                centro = f"**{m['away_sc']} - {m['home_sc']}**"
            else:
                centro = f"🕒 {m['hora']}"
            c2.markdown(f"<div style='text-align:center;'>{centro}</div>", unsafe_allow_html=True)
            c3.markdown(
                f"<div style='display:flex;align-items:center;justify-content:flex-end;gap:8px;'>"
                f"<b>{m['home']}</b> <img src='{esc_h}' width='24'></div>",
                unsafe_allow_html=True,
            )
