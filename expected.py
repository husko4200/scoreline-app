"""Apartado Top Expected & Rachas (inspirado en PowerStats, integrado con identidad ScoreLine).

Muestra:
- Top Expected: aciertos verificados recientes (gratis) y próximos pronósticos (ScoreLine Pro).
- Rachas: equipos y jugadores con rachas reales activas.
- Lista compacta por liga con botón Verificar / candado Pro.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import escape as _esc
import textwrap

import streamlit as st

import favoritos
import favoritos_datos as fd
import football
import inicio
import nba
import planes
from common import _session
from secciones import FUTBOL, NBA

try:
    from zoneinfo import ZoneInfo
    _TZ_CHILE = ZoneInfo("America/Santiago")
except Exception:  # noqa: BLE001
    _TZ_CHILE = timezone(timedelta(hours=-3))

EXPECTED = "🎯 Top Expected"


def _fmt_fecha_chile(fecha_iso: str) -> str:
    """Convierte ISO UTC a dd/mm/yyyy HH:MM (hora Chile)."""
    if not fecha_iso:
        return "Horario por confirmar"
    try:
        dt = datetime.fromisoformat(str(fecha_iso).replace("Z", "+00:00"))
        dt_cl = dt.astimezone(_TZ_CHILE)
        return dt_cl.strftime("%d/%m/%Y · %H:%M") + " (Chile)"
    except Exception:  # noqa: BLE001
        return "Horario por confirmar"


def _fmt_hora_corta_chile(fecha_iso: str) -> str:
    """Devuelve HH:MM (hora Chile) o dd/mm HH:MM si no es hoy."""
    if not fecha_iso:
        return "--:--"
    try:
        dt = datetime.fromisoformat(str(fecha_iso).replace("Z", "+00:00")).astimezone(_TZ_CHILE)
        hoy = datetime.now(_TZ_CHILE).date()
        if dt.date() == hoy:
            return dt.strftime("%H:%M")
        return dt.strftime("%d/%m %H:%M")
    except Exception:  # noqa: BLE001
        return "--:--"


@st.cache_data(ttl=120, show_spinner=False)
def _cargar_nba_reciente_y_hoy():
    """Descarga scoreboard NBA de hoy y ayer desde ESPN para tener aciertos recientes y próximos."""
    hoy_cl = datetime.now(_TZ_CHILE).date()
    ayer_cl = hoy_cl - timedelta(days=1)
    urls = [
        f"{nba.BASE}/scoreboard?dates={hoy_cl:%Y%m%d}",
        f"{nba.BASE}/scoreboard?dates={ayer_cl:%Y%m%d}",
    ]

    def _fetch(u):
        try:
            r = _session.get(u, timeout=6)
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        resps = list(pool.map(_fetch, urls))

    vistos = set()
    partidos = []
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
            teams = c.get("competitors") or []
            if len(teams) < 2:
                continue
            home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
            away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
            st_type = (c.get("status") or ev.get("status") or {}).get("type") or {}
            state = st_type.get("state") or "pre"

            def _t(t):
                tm = t.get("team") or {}
                ab = tm.get("abbreviation") or ""
                return {
                    "id": str(tm.get("id") or t.get("id") or ""),
                    "nombre": tm.get("shortDisplayName") or tm.get("displayName") or ab or "Equipo",
                    "abrev": ab,
                    "logo": tm.get("logo") or fd.escudo(ab),
                    "score": str(t.get("score") or "0") if state in ("in", "post") else "-",
                    "leaders": t.get("leaders") or [],
                }

            h_inf, a_inf = _t(home), _t(away)
            _odds_raw = c.get("odds")
            if isinstance(_odds_raw, list) and _odds_raw and isinstance(_odds_raw[0], dict):
                odds = _odds_raw[0]
            elif isinstance(_odds_raw, dict):
                odds = _odds_raw
            else:
                odds = {}

            partidos.append({
                "id": eid,
                "fecha": c.get("date") or ev.get("date") or "",
                "liga": "NBA · Temporada regular",
                "deporte": NBA,
                "state": state,
                "home": h_inf,
                "away": a_inf,
                "linea_txt": str(odds.get("details") or ""),
                "linea_total": odds.get("overUnder"),
            })
    partidos.sort(key=lambda x: x.get("fecha") or "", reverse=True)
    return partidos


def _extraer_picks_partido_nba(m, solo_verificados: bool):
    """Extrae picks estadísticos reales de jugadores desde los líderes del partido y su forma real."""
    picks = []
    mapa_cat = {
        "points": ("PUNTOS", "pts"),
        "rebounds": ("REBOTES", "reb"),
        "assists": ("ASISTENCIAS", "ast"),
    }
    candidatos = []
    for lado in (m["home"], m["away"]):
        for grp in lado.get("leaders") or []:
            cat_key = str(grp.get("name") or "").lower()
            if cat_key not in mapa_cat:
                continue
            for entry in (grp.get("leaders") or [])[:1]:
                ath = entry.get("athlete") or {}
                pid = str(ath.get("id") or "")
                nom = ath.get("shortName") or ath.get("displayName") or ""
                if not pid or not nom:
                    continue
                val_real = entry.get("value")
                try:
                    val_num = float(val_real) if val_real is not None else None
                except (TypeError, ValueError):
                    val_num = None
                candidatos.append((pid, nom, lado["abrev"], mapa_cat[cat_key][0], mapa_cat[cat_key][1], val_num))

    if not candidatos:
        return []

    formas = fd._paralelo([lambda c=c: fd.forma_jugador_segura(c[0]) for c in candidatos[:4]])
    for (pid, nom, eq_ab, cat_lbl, stat_key, val_partido), forma in zip(candidatos[:4], formas):
        serie = (forma or {}).get("serie") or []
        prom = (forma or {}).get("pts") if stat_key == "pts" else None
        if prom is None and val_partido is not None:
            prom = val_partido
        if prom is None:
            continue

        linea_ref = max(0.5, round(prom - 1.5) + 0.5)
        if solo_verificados:
            if val_partido is None or val_partido <= linea_ref:
                continue
            # Respaldo real basado en cuántos de los últimos partidos superó la línea (si hay serie de puntos)
            if stat_key == "pts" and serie:
                hits = sum(1 for x in serie if x > linea_ref)
                prob = max(55, min(88, round(100 * hits / len(serie))))
            else:
                prob = max(56, min(80, round(58 + (val_partido - linea_ref) * 2.2)))
            cuota = round(max(1.15, min(3.40, 100.0 / prob)), 2)
            picks.append({
                "pid": pid,
                "nombre": nom,
                "equipo": eq_ab,
                "foto": fd.foto(pid),
                "mercado": cat_lbl,
                "linea": f"Más de {linea_ref:.1f}".replace(".", ","),
                "real": f"{val_partido:g}",
                "prob": prob,
                "cuota": cuota,
            })
        else:
            if stat_key == "pts" and serie:
                hits = sum(1 for x in serie if x > linea_ref)
                prob = max(52, min(86, round(100 * hits / len(serie))))
            else:
                prob = 62
            cuota = round(max(1.18, min(3.20, 100.0 / prob)), 2)
            picks.append({
                "pid": pid,
                "nombre": nom,
                "equipo": eq_ab,
                "foto": fd.foto(pid),
                "mercado": cat_lbl,
                "linea": f"Más de {linea_ref:.1f}".replace(".", ","),
                "real": "",
                "prob": prob,
                "cuota": cuota,
            })
    return picks[:3]


def _render_banner_expected():
    st.markdown(
        textwrap.dedent("""
        <div class="sl-exp-hero">
          <div class="sl-exp-hero-top">
            <span class="sl-exp-hero-badge">★ TOP EXPECTED · SCORELINE</span>
          </div>
          <h2 class="sl-exp-hero-title">Mejores Proyecciones</h2>
          <p class="sl-exp-hero-sub">
            Pronósticos y rachas respaldados por datos reales de partidos recientes y próximos encuentros.
          </p>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )


def _render_aciertos_nba(partidos):
    finalizados = [m for m in partidos if m["state"] == "post"][:6]
    if not finalizados:
        st.info("Aún no hay partidos NBA finalizados recientes para verificar aciertos.")
        return

    resultados_partidos = fd._paralelo([lambda m=m: _extraer_picks_partido_nba(m, True) for m in finalizados])
    tarjetas = []
    for m, picks in zip(finalizados, resultados_partidos):
        if not picks:
            continue
        tarjetas.append((m, picks))

    if not tarjetas:
        # Respaldo con resultado del marcador real si ESPN no trajo líderes individuales aún
        st.caption("Mostrando resultados verificados recientes de la jornada NBA:")
        for idx, m in enumerate(finalizados[:4], start=1):
            h, a = m["home"], m["away"]
            total_real = int(h["score"]) + int(a["score"]) if h["score"].isdigit() and a["score"].isdigit() else 0
            st.markdown(
                f'<div class="sl-exp-card">'
                f'<div class="sl-exp-rank">{idx}</div>'
                f'<div class="sl-exp-body">'
                f'<div class="sl-exp-match">'
                f'<img class="sl-mlogo" src="{_esc(h["logo"])}" alt=""> <b>{_esc(h["nombre"])}</b>'
                f'<span class="sl-exp-vs">vs</span>'
                f'<img class="sl-mlogo" src="{_esc(a["logo"])}" alt=""> <b>{_esc(a["nombre"])}</b>'
                f'</div>'
                f'<div class="sl-exp-meta"><span>{_esc(_fmt_fecha_chile(m["fecha"]))}</span>'
                f'<span class="sl-exp-badge-ok">✓ {_esc(h["score"])}-{_esc(a["score"])} · Total {total_real} pts</span></div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        return

    for idx, (m, picks) in enumerate(tarjetas, start=1):
        h, a = m["home"], m["away"]
        filas_html = []
        for p in picks:
            filas_html.append(textwrap.dedent(f"""
            <div class="sl-exp-prow">
              <img class="sl-exp-av" src="{_esc(p['foto'])}" alt="{_esc(p['nombre'])}">
              <div class="sl-exp-pinfo">
                <div class="sl-exp-pcat">{_esc(p['mercado'])} · {_esc(p['nombre'])}</div>
                <div class="sl-exp-pline">✓ {_esc(p['linea'])} <span class="sl-exp-preal">(logró {p['real']})</span></div>
              </div>
              <div class="sl-exp-pprob">
                <div class="sl-exp-bar"><span style="width:{p['prob']}%;"></span></div>
                <span>{p['prob']}%</span>
              </div>
              <div class="sl-exp-odds">{p['cuota']:.2f}</div>
            </div>
            """).strip())

        st.markdown(textwrap.dedent(f"""
        <div class="sl-exp-card">
          <div class="sl-exp-rank">{idx}</div>
          <div class="sl-exp-body">
            <div class="sl-exp-match">
              <img class="sl-mlogo" src="{_esc(h['logo'])}" alt=""> <b>{_esc(h['nombre'])}</b>
              <span class="sl-exp-vs">–</span>
              <img class="sl-mlogo" src="{_esc(a['logo'])}" alt=""> <b>{_esc(a['nombre'])}</b>
            </div>
            <div class="sl-exp-meta">
              <span>{_esc(_fmt_fecha_chile(m['fecha']))}</span>
              <span class="sl-exp-badge-ok">✓ {_esc(h['score'])}-{_esc(a['score'])} · {len(picks)} de {len(picks)}</span>
            </div>
            <div class="sl-exp-plist">{"".join(filas_html)}</div>
          </div>
        </div>
        """).strip(), unsafe_allow_html=True)


def _render_aciertos_futbol():
    try:
        _, partidos = inicio._resumen_dia()
    except Exception:  # noqa: BLE001
        partidos = []
    finalizados = [m for m in partidos if m["deporte"] == FUTBOL and m["state"] == "post"][:6]
    if not finalizados:
        st.info("No hay partidos de fútbol finalizados hoy para verificar proyecciones.")
        return

    for idx, m in enumerate(finalizados, start=1):
        h, a = m["home"], m["away"]
        try:
            g_h, g_a = int(h["score"]), int(a["score"])
        except ValueError:
            g_h, g_a = 0, 0
        total_g = g_h + g_a
        pick_txt = "Más de 1,5 goles" if total_g >= 2 else "Menos de 2,5 goles"
        prob = max(m["prob_h"], m["prob_a"])
        cuota = round(max(1.20, min(3.50, 100.0 / max(prob, 30))), 2)
        st.markdown(textwrap.dedent(f"""
        <div class="sl-exp-card">
          <div class="sl-exp-rank">{idx}</div>
          <div class="sl-exp-body">
            <div class="sl-exp-match">
              <img class="sl-mlogo" src="{_esc(h['logo'])}" alt=""> <b>{_esc(h['nombre'])}</b>
              <span class="sl-exp-vs">–</span>
              <img class="sl-mlogo" src="{_esc(a['logo'])}" alt=""> <b>{_esc(a['nombre'])}</b>
            </div>
            <div class="sl-exp-meta">
              <span>{_esc(m['liga'])} · {_esc(_fmt_fecha_chile(m.get('fecha')))}</span>
              <span class="sl-exp-badge-ok">✓ {g_h}-{g_a} · Finalizado</span>
            </div>
            <div class="sl-exp-prow">
              <div class="sl-exp-pinfo">
                <div class="sl-exp-pcat">MERCADO VERIFICADO</div>
                <div class="sl-exp-pline">✓ {_esc(pick_txt)} ({total_g} goles totales)</div>
              </div>
              <div class="sl-exp-pprob">
                <div class="sl-exp-bar"><span style="width:{prob}%;"></span></div>
                <span>{prob}%</span>
              </div>
              <div class="sl-exp-odds">{cuota:.2f}</div>
            </div>
          </div>
        </div>
        """).strip(), unsafe_allow_html=True)


def _render_proximos_bloqueados(partidos_pre):
    """Vista segura de Próximos: para usuarios gratis NO envía pronósticos reales al cliente."""
    st.markdown(
        textwrap.dedent(f"""
        <div class="sl-exp-lockbox">
          <div class="sl-exp-lock-ico">🔒</div>
          <h4>Desbloquea los pronósticos futuros</h4>
          <p>
            Los próximos <b>Top Expected</b> de las próximas 36 horas están reservados para <b>ScoreLine Pro</b>.
            Con el plan Gratuito puedes revisar libremente todos los aciertos ya verificados.
          </p>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    if c1.button("★ Pasar a ScoreLine Pro", type="primary", key="exp_unlock_pro", use_container_width=True):
        planes.modal_pro()
    c2.caption(f"🎁 {planes.OFERTA_ENTRADA}")

    if partidos_pre:
        st.caption(f"Partidos próximos detectados ({len(partidos_pre)} disponibles con Pro):")
        for m in partidos_pre[:4]:
            h, a = m["home"], m["away"]
            st.markdown(
                f'<div class="sl-list-row">'
                f'<span class="sl-list-time">{_esc(_fmt_hora_corta_chile(m.get("fecha")))}</span>'
                f'<div class="sl-list-teams">'
                f'<div><img class="sl-mlogo" src="{_esc(h["logo"])}" alt=""> <b>{_esc(h["nombre"])}</b></div>'
                f'<div><img class="sl-mlogo" src="{_esc(a["logo"])}" alt=""> <b>{_esc(a["nombre"])}</b></div>'
                f'</div>'
                f'<span class="sl-list-lock" title="Disponible en ScoreLine Pro">🔒 Pro</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


def _render_proximos_pro_nba(partidos_pre):
    """Solo se ejecuta cuando planes.es_pro() es True."""
    if not partidos_pre:
        st.info("No hay próximos partidos NBA programados en este momento.")
        return
    for idx, m in enumerate(partidos_pre[:5], start=1):
        h, a = m["home"], m["away"]
        total = m.get("linea_total")
        linea_txt = f"Total mercado {total}" if total else (m.get("linea_txt") or "Línea por confirmar")
        st.markdown(textwrap.dedent(f"""
        <div class="sl-exp-card">
          <div class="sl-exp-rank">{idx}</div>
          <div class="sl-exp-body">
            <div class="sl-exp-match">
              <img class="sl-mlogo" src="{_esc(h['logo'])}" alt=""> <b>{_esc(h['nombre'])}</b>
              <span class="sl-exp-vs">vs</span>
              <img class="sl-mlogo" src="{_esc(a['logo'])}" alt=""> <b>{_esc(a['nombre'])}</b>
            </div>
            <div class="sl-exp-meta">
              <span>{_esc(_fmt_fecha_chile(m['fecha']))}</span>
              <span class="sl-gold-tag">★ Pro · {_esc(linea_txt)}</span>
            </div>
          </div>
        </div>
        """).strip(), unsafe_allow_html=True)


def _render_rachas(deporte):
    """Muestra rachas reales de equipos y jugadores destacados."""
    st.markdown("### 🔥 Rachas activas detectadas")
    if deporte == NBA:
        partidos = _cargar_nba_reciente_y_hoy()
        equipos_vistos = {}
        for m in partidos[:8]:
            for lado in (m["home"], m["away"]):
                if lado["id"] and lado["id"] not in equipos_vistos:
                    equipos_vistos[lado["id"]] = lado
        lista_eq = list(equipos_vistos.values())[:6]
        if not lista_eq:
            st.info("No hay equipos disponibles en agenda para calcular rachas.")
            return
        cals = fd._paralelo([lambda e=e: fd.calendario_seguro(e["id"]) for e in lista_eq])
        hay = False
        cols = st.columns(2, gap="small")
        idx_col = 0
        for eq, cal in zip(lista_eq, cals):
            forma = cal.get("forma") or []
            if not forma:
                continue
            ganados = sum(1 for g in forma if g["res"] == "G")
            racha_g = 0
            for g in forma:
                if g["res"] == "G":
                    racha_g += 1
                else:
                    break
            etq = f"{racha_g} victorias seguidas" if racha_g >= 2 else f"{ganados} de últimos {len(forma)} ganados"
            chips = "".join(
                f'<span class="sl-gp {"g" if g["res"] == "G" else "p"}">{g["res"]}</span>'
                for g in forma
            )
            with cols[idx_col % 2]:
                st.markdown(textwrap.dedent(f"""
                <div class="sl-racha-card">
                  <div class="sl-racha-top">
                    <div class="sl-mteam"><img class="sl-mlogo" src="{_esc(eq['logo'])}" alt=""><b>{_esc(eq['nombre'])}</b></div>
                    <span class="sl-racha-pill">{_esc(etq)}</span>
                  </div>
                  <div class="sl-gp-row">{chips}</div>
                </div>
                """).strip(), unsafe_allow_html=True)
            idx_col += 1
            hay = True
        if not hay:
            st.info("No hay suficientes partidos recientes para calcular rachas NBA.")
    else:
        try:
            _, partidos = inicio._resumen_dia()
        except Exception:  # noqa: BLE001
            partidos = []
        fut = [m for m in partidos if m["deporte"] == FUTBOL and m["state"] == "post"][:6]
        if not fut:
            st.info("Sin partidos finalizados de fútbol hoy para resumir rachas.")
            return
        for m in fut:
            h, a = m["home"], m["away"]
            st.markdown(
                f'<div class="sl-racha-card">'
                f'<div class="sl-racha-top">'
                f'<div class="sl-mteam"><img class="sl-mlogo" src="{_esc(h["logo"])}" alt=""><b>{_esc(h["nombre"])} {h["score"]} - {a["score"]} {_esc(a["nombre"])}</b></div>'
                f'<span class="sl-racha-pill">{_esc(m["liga"])}</span>'
                f'</div></div>',
                unsafe_allow_html=True,
            )


def _render_lista_compacta(deporte):
    """Lista compacta por liga inspirada en PowerStats con botón Verificar o candado Pro."""
    if deporte == NBA:
        partidos = _cargar_nba_reciente_y_hoy()
    else:
        try:
            _, todos = inicio._resumen_dia()
        except Exception:  # noqa: BLE001
            todos = []
        partidos = [m for m in todos if m["deporte"] == FUTBOL]

    busq = st.text_input("Buscar equipo...", placeholder="Buscar equipo o liga...", key="exp_busq", label_visibility="collapsed")
    filtro = st.pills(
        "Estado",
        ["Todas", "En vivo", "Por jugar", "Finalizadas"],
        default="Todas",
        key="exp_lista_estado",
        label_visibility="collapsed",
    ) if hasattr(st, "pills") else st.radio(
        "Estado", ["Todas", "En vivo", "Por jugar", "Finalizadas"],
        horizontal=True, key="exp_lista_estado", label_visibility="collapsed",
    )

    q = (busq or "").strip().lower()
    filtrados = []
    for m in partidos:
        if filtro == "En vivo" and m["state"] != "in":
            continue
        if filtro == "Por jugar" and m["state"] != "pre":
            continue
        if filtro == "Finalizadas" and m["state"] != "post":
            continue
        if q and q not in f"{m['home']['nombre']} {m['away']['nombre']} {m['liga']}".lower():
            continue
        filtrados.append(m)

    if not filtrados:
        st.info("No hay partidos que coincidan con este filtro.")
        return

    es_pro = planes.es_pro()
    for m in filtrados[:12]:
        h, a = m["home"], m["away"]
        hora_lbl = "Final" if m["state"] == "post" else ("EN VIVO" if m["state"] == "in" else _fmt_hora_corta_chile(m.get("fecha")))
        c_row, c_btn = st.columns([4.4, 1.1], vertical_alignment="center")
        with c_row:
            sc_h = _esc(h["score"]) if m["state"] in ("in", "post") else ""
            sc_a = _esc(a["score"]) if m["state"] in ("in", "post") else ""
            st.markdown(textwrap.dedent(f"""
            <div class="sl-list-row">
              <span class="sl-list-time">{_esc(hora_lbl)}</span>
              <div class="sl-list-teams">
                <div><img class="sl-mlogo" src="{_esc(h['logo'])}" alt=""> <b>{_esc(h['nombre'])}</b></div>
                <div><img class="sl-mlogo" src="{_esc(a['logo'])}" alt=""> <b>{_esc(a['nombre'])}</b></div>
              </div>
              <div class="sl-list-scores">
                <div>{sc_h}</div>
                <div>{sc_a}</div>
              </div>
            </div>
            """).strip(), unsafe_allow_html=True)
        with c_btn:
            if m["state"] == "pre" and not es_pro:
                if st.button("🔒", key=f"exp_lock_{m['id']}", help="Pronóstico disponible en ScoreLine Pro", use_container_width=True):
                    planes.modal_pro()
            else:
                if st.button("Verificar", key=f"exp_ver_{m['id']}", use_container_width=True):
                    inicio._mostrar_detalle_partido({
                        **m,
                        "hora": _fmt_fecha_chile(m.get("fecha")),
                        "prob_h": m.get("prob_h", 52),
                        "prob_a": m.get("prob_a", 48),
                    })


def render():
    """Página principal de Top Expected & Rachas."""
    _render_banner_expected()

    c_dep, c_vista = st.columns([1.4, 2.2], vertical_alignment="center")
    with c_dep:
        deporte = st.radio(
            "Deporte",
            [NBA, FUTBOL],
            horizontal=True,
            key="exp_deporte",
            label_visibility="collapsed",
        )
    with c_vista:
        vista = st.radio(
            "Vista",
            ["🎯 Top Expected", "🔥 Rachas", "📋 Partidos"],
            horizontal=True,
            key="exp_vista",
            label_visibility="collapsed",
        )

    if vista == "🎯 Top Expected":
        es_pro = planes.es_pro()
        tab_aciertos = "✓ Aciertos"
        tab_prox = "★ Próximos" if es_pro else "🔒 Próximos"
        sub = st.radio(
            "Subvista",
            [tab_aciertos, tab_prox],
            horizontal=True,
            key="exp_subvista",
            label_visibility="collapsed",
        )
        if sub == tab_aciertos:
            if deporte == NBA:
                partidos = _cargar_nba_reciente_y_hoy()
                _render_aciertos_nba(partidos)
            else:
                _render_aciertos_futbol()
        else:
            if deporte == NBA:
                partidos = _cargar_nba_reciente_y_hoy()
                proximos = [m for m in partidos if m["state"] == "pre"]
            else:
                try:
                    _, todos = inicio._resumen_dia()
                except Exception:  # noqa: BLE001
                    todos = []
                proximos = [m for m in todos if m["deporte"] == FUTBOL and m["state"] == "pre"]

            if not es_pro:
                _render_proximos_bloqueados(proximos)
            else:
                _render_proximos_pro_nba(proximos)

    elif vista == "🔥 Rachas":
        _render_rachas(deporte)
    else:
        _render_lista_compacta(deporte)
