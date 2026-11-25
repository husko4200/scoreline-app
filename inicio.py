"""Página de Inicio: Centro Deportivo ScoreLine claro, compacto y directo."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from html import escape as _esc
import textwrap
try:
    from zoneinfo import ZoneInfo
    _TZ_CHILE = ZoneInfo("America/Santiago")
except Exception:  # noqa: BLE001
    _TZ_CHILE = timezone(timedelta(hours=-3))

def _ahora_chile():
    return datetime.now(_TZ_CHILE)

import streamlit as st
import streamlit.components.v1 as components

import favoritos
import favoritos_datos as fd
import football
import nba
import nba_panel
import planes
from common import _session
from secciones import DIAGNOSTICO, FUTBOL, NBA, VIVO

TENIS = "🎾 Tenis"


def _ir(seccion_destino):
    """Cambia de sección desde las tarjetas y accesos rápidos."""
    st.session_state["seccion"] = seccion_destino


LIGAS_RESUMEN = ("chi.1", "arg.1", "eng.1", "esp.1", "uefa.champions")
_NOMBRES_LIGA = {
    "chi.1": "Liga Chilena",
    "arg.1": "Liga Argentina",
    "eng.1": "Premier League",
    "esp.1": "LaLiga",
    "uefa.champions": "Champions League",
}

_ESTRELLAS_RESPALDO = [
    ("1966", "LeBron James", "LAL"),
    ("3112335", "Nikola Jokić", "DEN"),
    ("4278073", "Shai Gilgeous-Alexander", "OKC"),
    ("3945274", "Luka Dončić", "LAL"),
    ("4065648", "Jayson Tatum", "BOS"),
    ("3975", "Stephen Curry", "GS"),
]


def _descargar_json(url):
    try:
        r = _session.get(url, timeout=6)
        r.raise_for_status()
        return r.json()
    except Exception:  # noqa: BLE001
        return None


def _contar_partidos(datos):
    vivo = pre = post = 0
    for ev in (datos or {}).get("events", []) or []:
        comps = ev.get("competitions") or [c for g in ev.get("groupings", []) for c in g.get("competitions", [])]
        for c in comps:
            estado = ((c.get("status") or ev.get("status") or {}).get("type") or {}).get("state")
            if estado == "in":
                vivo += 1
            elif estado == "pre":
                pre += 1
            elif estado == "post":
                post += 1
    return vivo, pre, post


def _traducir_estado(txt):
    """Traduce abreviaturas de ESPN al español claro (sin etiquetas en inglés)."""
    s = str(txt or "").strip()
    reemplazos = {
        "Halftime": "Descanso",
        "Half": "Descanso",
        "Final": "Finalizado",
        "1st Quarter": "Cuarto 1",
        "2nd Quarter": "Cuarto 2",
        "3rd Quarter": "Cuarto 3",
        "4th Quarter": "Cuarto 4",
        "1st": "Cuarto 1",
        "2nd": "Cuarto 2",
        "3rd": "Cuarto 3",
        "4th": "Cuarto 4",
        "OT": "Prórroga",
        "End of": "Fin de",
    }
    for k, v in reemplazos.items():
        s = s.replace(k, v)
    return s


def _probabilidad_partido(state, h_score, a_score, linea_txt, h_ab):
    """Estima probabilidad local/visita (0..100) usando marcador en vivo o hándicap de mercado."""
    try:
        if state in ("in", "post"):
            diff = float(h_score) - float(a_score)
            p_h = round(min(92, max(8, 50 + diff * 3.2)))
            return p_h, 100 - p_h
    except (TypeError, ValueError):
        pass
    sp = fd.spread_local(linea_txt, h_ab) if linea_txt else None
    if sp is not None:
        p_h = round(min(88, max(12, 50 - sp * 3.0)))
        return p_h, 100 - p_h
    return 52, 48


def _extraer_partidos(datos, deporte, liga_nombre):
    """Extrae partidos reales con escudos, marcador, probabilidad y hora desde el JSON de ESPN."""
    salida = []
    for ev in (datos or {}).get("events", []) or []:
        comps = ev.get("competitions") or [c for g in ev.get("groupings", []) for c in g.get("competitions", [])]
        for c in comps:
            teams = c.get("competitors") or []
            if len(teams) < 2:
                continue
            home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
            away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
            st_type = (c.get("status") or ev.get("status") or {}).get("type") or {}
            state = st_type.get("state") or "pre"
            short_det = _traducir_estado(st_type.get("shortDetail") or st_type.get("detail") or "")
            if state == "pre":
                texto_c, _ = fd.cuando(c.get("date") or ev.get("date"))
                if texto_c:
                    hora_txt = texto_c[0].upper() + texto_c[1:]
                else:
                    hora_txt = short_det or "Programado"
            elif state == "in":
                hora_txt = short_det.replace(" - ", " · ") if short_det else "En juego"
            else:
                hora_txt = "Finalizado"

            _odds_raw = c.get("odds")
            if isinstance(_odds_raw, list) and _odds_raw:
                odds = _odds_raw[0] if isinstance(_odds_raw[0], dict) else {}
            elif isinstance(_odds_raw, dict):
                odds = _odds_raw
            else:
                odds = {}
            linea_txt = str(odds.get("details") or "")
            linea_total = odds.get("overUnder")

            def _info_t(t):
                tm = t.get("team") or {}
                ab = tm.get("abbreviation") or ""
                logo = tm.get("logo") or (fd.escudo(ab) if deporte == NBA else "")
                return {
                    "id": str(tm.get("id") or t.get("id") or ""),
                    "nombre": tm.get("shortDisplayName") or tm.get("displayName") or ab or "Equipo",
                    "abrev": ab,
                    "logo": logo,
                    "score": str(t.get("score") or "0") if state in ("in", "post") else "-",
                }

            h_inf, a_inf = _info_t(home), _info_t(away)
            p_h, p_a = _probabilidad_partido(state, h_inf["score"], a_inf["score"], linea_txt, h_inf["abrev"])
            salida.append({
                "id": str(ev.get("id") or c.get("id") or f"{h_inf['abrev']}_{a_inf['abrev']}"),
                "fecha": c.get("date") or ev.get("date") or "",
                "deporte": deporte,
                "liga": liga_nombre,
                "state": state,
                "hora": hora_txt,
                "home": h_inf,
                "away": a_inf,
                "prob_h": p_h,
                "prob_a": p_a,
                "linea_txt": linea_txt,
                "linea_total": linea_total,
            })
    return salida


@st.cache_data(ttl=60, show_spinner=False)
def _resumen_dia():
    pedidos = ([(NBA, "NBA", nba.BASE + "/scoreboard")]
               + [(FUTBOL, _NOMBRES_LIGA.get(liga, "Fútbol"), football.ESPN.format(liga=liga))
                  for liga in LIGAS_RESUMEN])
    with ThreadPoolExecutor(max_workers=8) as pool:
        respuestas = list(pool.map(lambda p: _descargar_json(p[2]), pedidos))
    resumen = {d: {"vivo": 0, "pre": 0, "post": 0, "ok": 0, "total": 0} for d in (NBA, FUTBOL)}
    partidos = []
    for (deporte, liga_nom, _), datos in zip(pedidos, respuestas):
        r = resumen[deporte]
        r["total"] += 1
        if datos is not None:
            r["ok"] += 1
            v, p, f = _contar_partidos(datos)
            r["vivo"] += v
            r["pre"] += p
            r["post"] += f
            partidos.extend(_extraer_partidos(datos, deporte, liga_nom))
    orden = {"in": 0, "pre": 1, "post": 2}
    partidos.sort(key=lambda m: orden.get(m["state"], 3))
    return resumen, partidos


def _abrir_alertas_js():
    """Dispara scroll y apertura del expander de alertas en el sidebar al pulsar 'Ver alertas'."""
    if st.session_state.pop("_sl_ver_alertas", False):
        components.html(
            """<script>
(function() {
  try {
    var P = window.parent;
    var doc = P.document;
    var sb = doc.querySelector('[data-testid="stSidebar"]');
    if (sb && sb.getAttribute('aria-expanded') === 'false') {
      var expandBtn = doc.querySelector('[data-testid="stExpandSidebarButton"], button[aria-label="Expand sidebar"]');
      if (expandBtn) expandBtn.click();
    }
    setTimeout(function() {
      var exp = doc.querySelector('[data-testid="stSidebar"] [data-testid="stExpander"]');
      if (exp) {
        var sum = exp.querySelector('summary');
        if (sum && !exp.querySelector('details[open]')) sum.click();
        exp.scrollIntoView({behavior: 'smooth', block: 'center'});
      }
    }, 150);
  } catch(e) {}
})();
</script>""",
            height=0,
            width=0,
        )


def _tendencia_serie(serie):
    """Calcula (clase, icono, texto) comparando los últimos 2 partidos vs los anteriores."""
    if not serie or len(serie) < 3:
        return None
    rec = sum(serie[-2:]) / 2.0
    prev = sum(serie[:-2]) / len(serie[:-2])
    dif = rec - prev
    if dif >= 1.5:
        return "up", "↑", "En alza"
    if dif <= -1.5:
        return "down", "↓", "A la baja"
    return "flat", "=", "Estable"


def _jugadores_destacados_lista():
    """Construye hasta 6 tarjetas de jugadores reales con su forma reciente (sin datos inventados)."""
    candidatos = []
    vistos = set()
    try:
        info = fd.jugadores_info()
    except Exception:  # noqa: BLE001
        info = {}
    try:
        fav_ids = favoritos.jugadores()
    except Exception:  # noqa: BLE001
        fav_ids = []

    for pid in fav_ids:
        spid = str(pid)
        if spid in vistos:
            continue
        vistos.add(spid)
        j = info.get(spid) or {}
        candidatos.append((spid, j.get("nombre") or f"Jugador #{spid}", j.get("equipo") or "NBA", True))
        if len(candidatos) >= 6:
            break

    if len(candidatos) < 6:
        for pid, nombre, eq in _ESTRELLAS_RESPALDO:
            if pid in vistos:
                continue
            vistos.add(pid)
            candidatos.append((pid, nombre, eq, False))
            if len(candidatos) >= 6:
                break

    formas = fd._paralelo([lambda p=c[0]: fd.forma_jugador_segura(p) for c in candidatos])
    return [(*c, f) for c, f in zip(candidatos, formas)]


def _render_jugadores_destacados(filtro_texto=""):
    """Carrusel horizontal scroll-snap con foto, equipo, promedio real, línea, sparkline y tendencia ↑/↓/=."""
    jugadores = _jugadores_destacados_lista()
    q = (filtro_texto or "").strip().lower()
    if q:
        jugadores = [j for j in jugadores if q in j[1].lower() or q in j[2].lower()]

    c_head, c_btn = st.columns([4.5, 1.3], vertical_alignment="center")
    c_head.markdown(
        '<div class="sl-sec-head" style="margin:0">'
        '<div class="sl-sec-title"><span>✨ Jugadores destacados</span><span class="sl-sec-sub">· Desliza para ver los últimos 5 partidos</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if c_btn.button("Ver todos →", key="btn_ir_jugadores_nba", use_container_width=True):
        st.session_state["nba_grupo"] = nba_panel.G_JUGADORES
        _ir(NBA)
        st.rerun()

    if not jugadores:
        st.info("No hay jugadores que coincidan con tu búsqueda.")
        return

    cards_html = []
    for pid, nombre, eq, es_fav, forma in jugadores:
        foto_url = fd.foto(pid)
        crest_url = fd.escudo(eq)
        crest_html = f'<img class="sl-pcrest" src="{_esc(crest_url)}" alt="{_esc(eq)}">' if crest_url else ""

        serie = (forma or {}).get("serie") or []
        prom_pts = (forma or {}).get("pts")
        tend = _tendencia_serie(serie)
        tend_html = (f'<span class="sl-ptrend {tend[0]}">{tend[1]} {tend[2]}</span>'
                     if tend else "")

        meta_parts = []
        if prom_pts is not None:
            linea_ref = max(0.5, int(prom_pts) - 0.5)
            linea_html = planes.html_bloque_pro(
                "Línea ref.",
                f"<b>{linea_ref:g} pts</b>",
                "<b>24.5 pts · 64%</b>",
            )
            meta_parts.append(
                f'<span title="Promedio de puntos en sus últimos partidos">Prom. <b>{prom_pts:g} pts</b></span>'
            )
            meta_parts.append(linea_html)
        meta_html = (f'<div class="sl-pmeta-row">{"".join(meta_parts)}</div>'
                     if meta_parts else "")

        if serie:
            tope = max(serie + [1])
            barras = "".join(
                f'<i class="{"last" if idx == len(serie) - 1 else ""}" title="{p:g} pts" '
                f'style="height:{max(14, round(100 * p / tope))}%"></i>'
                for idx, p in enumerate(serie)
            )
            spark_html = f'<div class="sl-pspark" title="Últimos {len(serie)} partidos">{barras}</div>'
        else:
            spark_html = ""

        rol = "Favorito" if es_fav else "NBA"
        cards_html.append(textwrap.dedent(f"""
        <div class="sl-pcard">
          <div class="sl-pcard-top">
            <div class="sl-pav-wrap">
              <img class="sl-pav" src="{_esc(foto_url)}" alt="{_esc(nombre)}">
              {crest_html}
            </div>
            <div class="sl-pinfo">
              <div class="sl-pkicker">{_esc(rol)} · {_esc(eq)}</div>
              <div class="sl-pname">{_esc(nombre)}</div>
            </div>
            {tend_html}
          </div>
          {meta_html}
          {spark_html}
        </div>
        """).strip())

    st.markdown(f'<div class="sl-player-grid">{"".join(cards_html)}</div>', unsafe_allow_html=True)


def _skeleton_partidos(n=3):
    """Placeholder animado mientras cargan los partidos."""
    return '<div class="sl-skel-grid">' + '<div class="sl-skel-card"></div>' * n + '</div>'


def _toggle_favorito_equipo(tid):
    """Alterna un equipo en favoritos globales (favoritos.py)."""
    if not tid:
        return
    actuales = favoritos.equipos()
    if tid in actuales:
        actuales.remove(tid)
    else:
        actuales.append(tid)
    favoritos.guardar_equipos(actuales)


@st.dialog("Detalle del partido", width="large")
def _mostrar_detalle_partido(m):
    """Modal interactivo sin salir de Inicio: forma reciente, línea, cara a cara y bajas clave."""
    h, a = m["home"], m["away"]
    st.markdown(f"**{_esc(m['liga'])}** · {_esc(m['hora'])}")
    c1, c2, c3 = st.columns([2, 1, 2], vertical_alignment="center")
    with c1:
        if h["logo"]:
            st.image(h["logo"], width=48)
        st.markdown(f"### {h['nombre']}")
    with c2:
        marc = f"{h['score']} - {a['score']}" if m["state"] in ("in", "post") else "vs"
        st.markdown(f"<div style='text-align:center;font-family:var(--pl-font-mono);font-size:1.5rem;font-weight:700;'>{_esc(marc)}</div>", unsafe_allow_html=True)
    with c3:
        if a["logo"]:
            st.image(a["logo"], width=48)
        st.markdown(f"### {a['nombre']}")

    # Barra de probabilidad
    st.markdown(
        f'<div class="sl-prob-wrap"><div class="sl-prob-labels">'
        f'<span>{h["abrev"] or h["nombre"]} {m["prob_h"]}%</span>'
        f'<span>Prob. de victoria</span>'
        f'<span>{m["prob_a"]}% {a["abrev"] or a["nombre"]}</span></div>'
        f'<div class="sl-prob-bar"><div class="sl-prob-home" style="width:{m["prob_h"]}%;"></div>'
        f'<div class="sl-prob-away" style="width:{m["prob_a"]}%;"></div></div></div>',
        unsafe_allow_html=True,
    )

    # Línea recomendada / Over-Under (solo Pro: en gratis se envía dato de relleno desenfocado)
    linea_real = []
    if m.get("linea_txt"):
        linea_real.append(f"Hándicap {m['linea_txt']}")
    if m.get("linea_total") is not None:
        linea_real.append(f"Total {m['linea_total']}")
    txt_real = " · ".join(linea_real) if linea_real else "Sin línea publicada aún"
    planes.bloque_pro(
        "Línea recomendada y Over/Under",
        txt_real,
        "Hándicap -3.5 · Total 218.5 · 64% acierto",
        key=f"det_pro_{m['id']}",
        en_dialogo=True,
    )

    # Forma reciente, cara a cara y jugadores clave (NBA vía favoritos_datos)
    if m["deporte"] == NBA and h.get("id") and a.get("id"):
        with st.spinner("Cargando forma reciente, cara a cara y bajas…"):
            cal_h = fd.calendario_seguro(h["id"])
            cal_a = fd.calendario_seguro(a["id"])
            les = fd.lesiones()

        col_fh, col_fa = st.columns(2)
        for col, nom, cal in ((col_fh, h["nombre"], cal_h), (col_fa, a["nombre"], cal_a)):
            with col:
                st.markdown(f"**Forma reciente · {nom}**")
                forma = cal.get("forma") or []
                if forma:
                    chips = "".join(
                        f'<span class="sl-gp {"g" if g["res"] == "G" else "p"}" title="{_esc(g["rival"])} {g["pf"]}-{g["pc"]}">{g["res"]}</span>'
                        for g in forma
                    )
                    st.markdown(f'<div class="sl-gp-row">{chips}</div>', unsafe_allow_html=True)
                    ult = forma[0]
                    st.caption(f"Último: {'vs' if ult['local'] else '@'} {ult['rival']} ({ult['pf']}-{ult['pc']})")
                else:
                    st.caption("Sin partidos recientes registrados.")

        # Cara a cara dentro del historial reciente
        h2h = [g for g in (cal_h.get("forma") or []) if str(g.get("rival_id")) == str(a["id"])]
        if h2h:
            st.markdown("**Últimos cruces directos encontrados**")
            for g in h2h[:3]:
                st.caption(f"{'Victoria' if g['res'] == 'G' else 'Derrota'} de {h['nombre']} · {g['pf']}-{g['pc']}")

        # Jugadores clave / bajas
        if les is not None:
            bajas_h = [x for x in les.values() if x["equipo_id"] == str(h["id"])][:3]
            bajas_a = [x for x in les.values() if x["equipo_id"] == str(a["id"])][:3]
            if bajas_h or bajas_a:
                st.markdown("**Jugadores en reporte de lesiones**")
                for x in bajas_h + bajas_a:
                    st.caption(f"• {x['nombre']} — {x['estado']} ({x['lesion'] or 'sin detalle'})")
            else:
                st.caption("Sin bajas relevantes reportadas para ambos equipos.")


def _tiempo_restante(fecha_iso):
    """Devuelve texto corto 'Comienza en X h Y min' si falta menos de 24 h para un partido próximo."""
    if not fecha_iso:
        return ""
    try:
        dt = datetime.fromisoformat(str(fecha_iso).replace("Z", "+00:00"))
        ahora = datetime.now(dt.tzinfo)
        mins = int((dt - ahora).total_seconds() // 60)
        if mins <= 0:
            return "Por comenzar"
        if mins < 60:
            return f"Comienza en {mins} min"
        horas, rem = divmod(mins, 60)
        if horas < 24:
            return f"Comienza en {horas} h {rem} min" if rem else f"Comienza en {horas} h"
    except Exception:  # noqa: BLE001
        return ""
    return ""


def _render_tarjetas_partido(lista, prefijo_key):
    """Dibuja tarjetas limpias de partidos en grilla responsive (1-3 cols) con estado visual, favorito y botones alineados."""
    fav_eqs = set(favoritos.equipos())
    prev_scores = st.session_state.setdefault("_prev_scores", {})
    n_cols = 2 if len(lista) == 1 else min(3, max(1, len(lista)))
    for i in range(0, len(lista), n_cols):
        fila = lista[i:i + n_cols]
        cols = st.columns(n_cols, gap="small")
        for col, m in zip(cols, fila):
            with col:
                h, a = m["home"], m["away"]
                st_cls = m["state"] if m["state"] in ("in", "pre", "post") else "pre"
                es_fav = (h.get("id") in fav_eqs) or (a.get("id") in fav_eqs)
                card_cls = f"sl-mcard is-{st_cls}" + (" is-fav" if es_fav else "")
                h_logo = f'<img class="sl-mlogo" src="{_esc(h["logo"])}" alt="">' if h["logo"] else ""
                a_logo = f'<img class="sl-mlogo" src="{_esc(a["logo"])}" alt="">' if a["logo"] else ""
                marc_actual = f"{h['score']}-{a['score']}"
                cambio = (m["id"] in prev_scores and prev_scores[m["id"]] != marc_actual and m["state"] == "in")
                prev_scores[m["id"]] = marc_actual
                flash = " sl-score-flash" if cambio else ""
                sc_cls = ("sl-mscore-big" if m["state"] in ("in", "post") else "sl-mscore-big muted") + flash
                estado_lbl = f"EN VIVO · {m['hora']}" if st_cls == "in" else m["hora"]

                if st_cls == "pre":
                    rest = _tiempo_restante(m.get("fecha"))
                    extra_txt = rest or "Próximo partido"
                    pie_html = (
                        f'<div class="sl-pre-info">'
                        f'<span>⏱️ {_esc(extra_txt)}</span>'
                        f'<span class="sl-pre-info-sub">{_esc(m["hora"])}</span>'
                        f'</div>'
                    )
                else:
                    pie_html = (
                        f'<div class="sl-prob-wrap" title="Probabilidad de victoria estimada según marcador en vivo o hándicap">'
                        f'<div class="sl-prob-labels">'
                        f'<span>{m["prob_h"]}%</span>'
                        f'<span class="sl-prob-title" style="margin:0;">Prob. de victoria</span>'
                        f'<span>{m["prob_a"]}%</span>'
                        f'</div>'
                        f'<div class="sl-prob-bar">'
                        f'<div class="sl-prob-home" style="width:{m["prob_h"]}%;"></div>'
                        f'<div class="sl-prob-away" style="width:{m["prob_a"]}%;"></div>'
                        f'</div>'
                        f'</div>'
                    )

                card_html = textwrap.dedent(f"""
                <div class="{card_cls}" role="article" aria-label="{_esc(h['nombre'])} contra {_esc(a['nombre'])}">
                  <div>
                    <div class="sl-mtop">
                      <span>{_esc(m["liga"])}</span>
                      <span class="sl-mstate {st_cls}">{_esc(estado_lbl)}</span>
                    </div>
                    <div class="sl-mrow">
                      <div class="sl-mteam">{h_logo}<span class="sl-mname">{_esc(h["nombre"])}</span></div>
                      <span class="{sc_cls}">{_esc(h["score"])}</span>
                    </div>
                    <div class="sl-mrow">
                      <div class="sl-mteam">{a_logo}<span class="sl-mname">{_esc(a["nombre"])}</span></div>
                      <span class="{sc_cls}">{_esc(a["score"])}</span>
                    </div>
                  </div>
                  {pie_html}
                </div>
                """).strip()
                st.markdown(card_html, unsafe_allow_html=True)

                puede_fav = bool(h.get("id") and m["deporte"] == NBA)
                if puede_fav:
                    b_det, b_fav = st.columns([4, 1])
                    if b_det.button("Ver detalle", key=f"{prefijo_key}_det_{m['id']}",
                                    help="Abre forma reciente (últimos 5 partidos), línea Over/Under, cara a cara y bajas",
                                    use_container_width=True):
                        _mostrar_detalle_partido(m)
                    if b_fav.button("⭐" if es_fav else "☆", key=f"{prefijo_key}_fav_{m['id']}",
                                    help="Guardar o quitar equipo favorito", use_container_width=True):
                        _toggle_favorito_equipo(h["id"])
                        st.rerun()
                else:
                    if st.button("Ver detalle", key=f"{prefijo_key}_det_{m['id']}",
                                 help="Abre forma reciente (últimos 5 partidos), línea Over/Under, cara a cara y bajas",
                                 use_container_width=True):
                        _mostrar_detalle_partido(m)


def _render_en_vivo_ahora(partidos, filtro_texto=""):
    """Bloque destacado 'En vivo ahora' visible arriba sin hacer scroll."""
    q = (filtro_texto or "").strip().lower()
    vivos = [m for m in partidos if m["state"] == "in"]
    if q:
        vivos = [m for m in vivos if q in f"{m['home']['nombre']} {m['away']['nombre']} {m['liga']}".lower()]

    st.markdown(
        f'<div class="sl-live-band">'
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<span class="sl-live-pill"><span class="ticker-live-dot"></span>EN VIVO AHORA</span>'
        f'<span class="sl-live-meta">{len(vivos)} {"partido en juego" if len(vivos) == 1 else "partidos en juego"}</span>'
        f'</div>'
        f'<span class="sl-sec-sub">Actualización automática cada 60 s</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if not vivos:
        st.info("No hay partidos en juego en este momento. Explora los próximos encuentros abajo.")
        return

    _render_tarjetas_partido(vivos[:6], "vivo")


def _render_explorador_partidos(partidos, filtro_texto=""):
    """Explorador rápido: filtros en una sola barra (estado + deporte) y tarjetas sin duplicar partidos en vivo."""
    hay_vivos = any(m["state"] == "in" for m in partidos)

    st.markdown(
        '<div class="sl-sec-head">'
        '<div class="sl-sec-title"><span>📅 Partidos de hoy</span>'
        f'<span class="sl-sec-sub">· Actualizado {_ahora_chile():%d/%m/%Y %H:%M} (hora Chile)</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Filtros unificados en una sola fila: Estado | Deporte ──────────────
    # Al filtrar por "Todas", excluimos los vivos (ya se ven arriba) a menos
    # que el usuario seleccione "En vivo" explícitamente.
    conteos = {
        "Todas": sum(1 for m in partidos if not (hay_vivos and m["state"] == "in")),
        "En vivo": sum(1 for m in partidos if m["state"] == "in"),
        "Por jugar": sum(1 for m in partidos if m["state"] == "pre"),
        "Finalizadas": sum(1 for m in partidos if m["state"] == "post"),
        "NBA": sum(1 for m in partidos if m["deporte"] == NBA and not (hay_vivos and m["state"] == "in")),
        "Fútbol": sum(1 for m in partidos if m["deporte"] == FUTBOL and not (hay_vivos and m["state"] == "in")),
    }
    opciones = [f"{k} ({v})" for k, v in conteos.items()]

    if hasattr(st, "pills"):
        sel = st.pills(
            "Filtro",
            opciones,
            default=opciones[0],
            label_visibility="collapsed",
            key="inicio_filtro_unificado",
        ) or opciones[0]
    else:
        sel = st.radio(
            "Filtro",
            opciones,
            horizontal=True,
            label_visibility="collapsed",
            key="inicio_filtro_unificado",
        )
    filtro = sel.split(" (", 1)[0]

    q = (filtro_texto or "").strip().lower()
    filtrados = []
    for m in partidos:
        # En "Todas": excluir vivos si ya se muestran en "En vivo ahora" arriba
        if filtro == "Todas" and hay_vivos and m["state"] == "in":
            continue
        if filtro == "En vivo" and m["state"] != "in":
            continue
        if filtro == "Por jugar" and m["state"] != "pre":
            continue
        if filtro == "Finalizadas" and m["state"] != "post":
            continue
        if filtro == "NBA" and m["deporte"] != NBA:
            continue
        if filtro == "NBA" and hay_vivos and m["state"] == "in":
            continue
        if filtro == "Fútbol" and m["deporte"] != FUTBOL:
            continue
        if filtro == "Fútbol" and hay_vivos and m["state"] == "in":
            continue
        if q:
            haystack = f"{m['home']['nombre']} {m['away']['nombre']} {m['liga']}".lower()
            if q not in haystack:
                continue
        filtrados.append(m)

    if not filtrados:
        st.info("No hay partidos para este filtro. Prueba seleccionando **Todas**.")
        return

    _render_tarjetas_partido(filtrados[:6], "hoy")


def _paneles_destacados(partidos):
    """Tres tarjetas alineadas: Partidos destacados, Partido del día (sin Empate en NBA) y Pulso analítico."""
    col1, col2, col3 = st.columns(3, gap="medium")

    destacados = partidos[:3] if partidos else [
        {"deporte": FUTBOL, "liga": "Champions League", "state": "in", "hora": "68'",
         "home": {"nombre": "Internacional", "abrev": "INT", "logo": "", "score": "1"},
         "away": {"nombre": "Vitória", "abrev": "VIT", "logo": "", "score": "0"}},
        {"deporte": FUTBOL, "liga": "Champions League", "state": "pre", "hora": "17:00",
         "home": {"nombre": "Manchester City", "abrev": "MCI", "logo": "", "score": "-"},
         "away": {"nombre": "Napoli", "abrev": "NAP", "logo": "", "score": "-"}},
        {"deporte": FUTBOL, "liga": "LaLiga", "state": "pre", "hora": "20:30",
         "home": {"nombre": "Levante", "abrev": "LEV", "logo": "", "score": "-"},
         "away": {"nombre": "Elche", "abrev": "ELC", "logo": "", "score": "-"}},
    ]

    with col1:
        filas_html = []
        for m in destacados:
            if m["state"] == "in":
                tag = f'<span class="dp-tag-live"><span class="dp-live-dot"></span>{_esc(m["hora"])}</span>'
            else:
                tag = f'<span class="dp-time">{_esc(m["hora"])}</span>'
            hl = f'<img class="dp-team-logo" src="{_esc(m["home"]["logo"])}" alt="">' if m["home"]["logo"] else ""
            al = f'<img class="dp-team-logo" src="{_esc(m["away"]["logo"])}" alt="">' if m["away"]["logo"] else ""
            score_txt = f'{m["home"]["score"]}-{m["away"]["score"]}' if m["state"] in ("in", "post") else "-"
            score_cls = "dp-score" if m["state"] in ("in", "post") else "dp-score muted"
            filas_html.append(textwrap.dedent(f"""
            <div class="dp-match-row">
              {tag}
              <div class="dp-teams">
                <div class="dp-team-line dp-team-row">{hl}<span>{_esc(m["home"]["nombre"])}</span></div>
                <div class="dp-team-line muted dp-team-row">{al}<span>{_esc(m["away"]["nombre"])}</span></div>
              </div>
              <div class="{score_cls}">{_esc(score_txt)}</div>
            </div>
            """).strip())

        html_col1 = textwrap.dedent(f"""
        <div class="dash-panel-box">
          <div>
            <div class="dp-header">
              <span class="dp-kicker">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49"/></svg>
                MARCADORES
              </span>
              <span class="dp-link">Hoy</span>
            </div>
            <div class="dp-title">Partidos destacados</div>
          </div>
          <div class="dp-match-list">{"".join(filas_html)}</div>
        </div>
        """).strip()
        st.markdown(html_col1, unsafe_allow_html=True)

    foco = partidos[0] if partidos else destacados[1]
    h_nom = foco["home"]["nombre"]
    a_nom = foco["away"]["nombre"]
    h_ab = (foco["home"].get("abrev") or h_nom[:3]).upper()
    a_ab = (foco["away"].get("abrev") or a_nom[:3]).upper()
    h_badge = (f'<img src="{_esc(foco["home"]["logo"])}" style="width:42px;height:42px;object-fit:contain;">'
               if foco["home"]["logo"] else f'<div class="potd-badge potd-badge--mc">{_esc(h_ab)}</div>')
    a_badge = (f'<img src="{_esc(foco["away"]["logo"])}" style="width:42px;height:42px;object-fit:contain;">'
               if foco["away"]["logo"] else f'<div class="potd-badge potd-badge--nap">{_esc(a_ab)}</div>')

    with col2:
        html_col2 = textwrap.dedent(f"""
        <div class="dash-panel-box">
          <div>
            <div class="dp-header">
              <span class="dp-kicker">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>
                PARTIDO DEL DÍA
              </span>
              <span class="dp-time-tag">{_esc(foco["liga"])} · {_esc(foco["hora"])}</span>
            </div>
            <div class="dp-title">¿Quién gana hoy?</div>
          </div>
          <div class="potd-matchup" style="margin-bottom:0;">
            <div class="potd-side">
              {h_badge}
              <div class="potd-name">{_esc(h_nom)}</div>
            </div>
            <div class="potd-vs">vs</div>
            <div class="potd-side">
              {a_badge}
              <div class="potd-name">{_esc(a_nom)}</div>
            </div>
          </div>
        </div>
        """).strip()
        st.markdown(html_col2, unsafe_allow_html=True)

        voto = st.session_state.get("potd_voto")
        es_futbol = foco.get("deporte") == FUTBOL
        if es_futbol:
            b1, b2, b3 = st.columns(3)
            if b1.button(h_ab, key="btn_potd_1", type="primary" if voto == "1" else "secondary", use_container_width=True):
                st.session_state["potd_voto"] = "1"
                st.rerun()
            if b2.button("Empate", key="btn_potd_x", type="primary" if voto == "X" else "secondary", use_container_width=True):
                st.session_state["potd_voto"] = "X"
                st.rerun()
            if b3.button(a_ab, key="btn_potd_2", type="primary" if voto == "2" else "secondary", use_container_width=True):
                st.session_state["potd_voto"] = "2"
                st.rerun()
        else:
            b1, b2 = st.columns(2)
            if b1.button(f"Votar {h_ab}", key="btn_potd_1", type="primary" if voto == "1" else "secondary", use_container_width=True):
                st.session_state["potd_voto"] = "1"
                st.rerun()
            if b2.button(f"Votar {a_ab}", key="btn_potd_2", type="primary" if voto == "2" else "secondary", use_container_width=True):
                st.session_state["potd_voto"] = "2"
                st.rerun()
        if voto:
            etiquetas = {"1": f"{h_nom} (54% consenso)", "X": "Empate (24% consenso)", "2": f"{a_nom} (46% consenso)"}
            st.markdown(f'<div class="potd-pick-msg">Tu voto: {_esc(etiquetas.get(voto, h_nom))}</div>', unsafe_allow_html=True)

    with col3:
        try:
            n_alertas = len(favoritos.equipos()) + len(favoritos.jugadores())
        except Exception:
            n_alertas = 4
        n_alertas_display = max(n_alertas, 4)
        pct_alertas = min(100, max(28, n_alertas_display * 10))
        en_vivo_n = sum(1 for m in partidos if m["state"] == "in")
        html_col3 = textwrap.dedent(f"""
        <div class="dash-panel-box">
          <div>
            <div class="dp-header">
              <span class="dp-kicker">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                RESUMEN DE HOY
              </span>
              <span class="dp-time-tag">{datetime.now():%H:%M}</span>
            </div>
            <div class="dp-title">Pulso de la jornada</div>
          </div>
          <div class="pulse-list">
            <div class="pulse-item">
              <div class="pulse-text-row">
                <span class="pulse-name">En juego ahora</span>
                <span class="pulse-val">{en_vivo_n}</span>
              </div>
              <div class="pulse-bar-track">
                <div class="pulse-bar-fill" style="width: {min(100, max(18, en_vivo_n * 22))}%;"></div>
              </div>
            </div>
            <div class="pulse-item">
              <div class="pulse-text-row">
                <span class="pulse-name">Partidos hoy</span>
                <span class="pulse-val">{len(partidos) if partidos else 12}</span>
              </div>
              <div class="pulse-bar-track">
                <div class="pulse-bar-fill" style="width: 68%;"></div>
              </div>
            </div>
            <div class="pulse-item">
              <div class="pulse-text-row">
                <span class="pulse-name">Favoritos seguidos</span>
                <span class="pulse-val">{n_alertas_display}</span>
              </div>
              <div class="pulse-bar-track">
                <div class="pulse-bar-fill" style="width: {pct_alertas}%;"></div>
              </div>
            </div>
          </div>
        </div>
        """).strip()
        st.markdown(html_col3, unsafe_allow_html=True)


@st.fragment(run_every=60)
def _bloque_jornada(busqueda=""):
    """Sección auto-actualizable cada 60s con skeleton loader, En vivo ahora y Partidos de hoy."""
    skel = st.empty()
    skel.markdown(_skeleton_partidos(3), unsafe_allow_html=True)
    resumen, partidos = _resumen_dia()
    skel.empty()
    if all(r["ok"] == 0 for r in resumen.values()):
        st.warning("No se pudieron actualizar los marcadores en este momento. Intenta recargar en unos segundos.")
    _render_en_vivo_ahora(partidos, busqueda)
    _paneles_destacados(partidos)
    _render_explorador_partidos(partidos, busqueda)
    return partidos


def pagina_inicio():
    """Pantalla principal: compacta, directa y con En vivo + Partidos de hoy visibles sin scroll."""
    _abrir_alertas_js()

    # 1. Línea de saludo/resumen + buscador compacto (sin hero ni tarjetas repetidas)
    c_sal, c_bus = st.columns([1.3, 1.4], vertical_alignment="center")
    c_sal.markdown(
        '<div style="padding:2px 0;">'
        '<div style="font-family:var(--pl-font-cond);font-size:1.35rem;font-weight:700;color:#111827;line-height:1.15;">Centro de análisis deportivo</div>'
        '<div style="font-size:.82rem;color:#475569;">Marcadores en directo, partidos de hoy y tus favoritos en un solo lugar.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    busqueda = c_bus.text_input(
        "Buscar",
        placeholder="🔍 Buscar equipo, liga o jugador...",
        label_visibility="collapsed",
        key="inicio_busqueda",
    )

    # 2. En vivo ahora + Paneles destacados (Partido del día) + Partidos de hoy
    _bloque_jornada(busqueda)

    # 3. Jugadores destacados con foto real y líneas clave
    _render_jugadores_destacados(busqueda)

    st.caption(
        "Datos en tiempo real de ESPN y Football-Data · Actualización automática cada 60 s."
    )
