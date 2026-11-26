"""Página de Inicio: Centro Deportivo ScoreLine claro, compacto y directo."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from html import escape as _esc
import json
import textwrap
import unicodedata
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


def _extraer_partidos(datos, deporte, liga_nombre, liga_slug=""):
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
                "liga_slug": liga_slug,
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
    pedidos = ([(NBA, "NBA", "nba", nba.BASE + "/scoreboard")]
               + [(FUTBOL, _NOMBRES_LIGA.get(liga, "Fútbol"), liga, football.ESPN.format(liga=liga))
                  for liga in LIGAS_RESUMEN])
    with ThreadPoolExecutor(max_workers=8) as pool:
        respuestas = list(pool.map(lambda p: _descargar_json(p[3]), pedidos))
    resumen = {d: {"vivo": 0, "pre": 0, "post": 0, "ok": 0, "total": 0} for d in (NBA, FUTBOL)}
    partidos = []
    for (deporte, liga_nom, liga_slug, _), datos in zip(pedidos, respuestas):
        r = resumen[deporte]
        r["total"] += 1
        if datos is not None:
            r["ok"] += 1
            v, p, f = _contar_partidos(datos)
            r["vivo"] += v
            r["pre"] += p
            r["post"] += f
            partidos.extend(_extraer_partidos(datos, deporte, liga_nom, liga_slug))
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


def _sin_tildes(txt):
    """Normaliza texto en minúsculas sin tildes para búsquedas rápidas."""
    s = unicodedata.normalize("NFD", str(txt or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _jugadores_destacados_lista(filtro_texto=""):
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

    q = _sin_tildes(filtro_texto).strip()

    for pid in fav_ids:
        spid = str(pid)
        if spid in vistos:
            continue
        j = info.get(spid) or {}
        nom = j.get("nombre") or f"Jugador #{spid}"
        eq = j.get("equipo") or "NBA"
        if q and q not in _sin_tildes(f"{nom} {eq}"):
            continue
        vistos.add(spid)
        candidatos.append((spid, nom, eq, True))
        if len(candidatos) >= 6:
            break

    if len(candidatos) < 6:
        for pid, nombre, eq in _ESTRELLAS_RESPALDO:
            if pid in vistos:
                continue
            if q and q not in _sin_tildes(f"{nombre} {eq}"):
                continue
            vistos.add(pid)
            candidatos.append((pid, nombre, eq, False))
            if len(candidatos) >= 6:
                break

    if q and len(candidatos) < 6 and info:
        for spid, j in info.items():
            if spid in vistos:
                continue
            nom = j.get("nombre") or ""
            eq = j.get("equipo") or "NBA"
            if q in _sin_tildes(f"{nom} {eq}"):
                vistos.add(spid)
                candidatos.append((spid, nom, eq, False))
                if len(candidatos) >= 6:
                    break

    formas = fd._paralelo([lambda p=c[0]: fd.forma_jugador_segura(p) for c in candidatos])
    return [(*c, f) for c, f in zip(candidatos, formas)]


def _render_jugadores_destacados(filtro_texto=""):
    """Carrusel horizontal scroll-snap con foto, equipo, promedio real, línea, sparkline y tendencia ↑/↓/=."""
    jugadores = _jugadores_destacados_lista(filtro_texto)

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
            ultimos = serie[-5:]
            tope = max(ultimos + [1])
            barras = "".join(
                f'<div class="sl-pspark-col" title="{p:g} pts">'
                f'<span class="sl-pspark-val{" last" if idx == len(ultimos) - 1 else ""}">{p:g}</span>'
                f'<div class="sl-pspark-track">'
                f'<i class="{"last" if idx == len(ultimos) - 1 else ""}" style="height:{max(18, round(100 * p / tope))}%"></i>'
                f'</div></div>'
                for idx, p in enumerate(ultimos)
            )
            spark_html = f'<div class="sl-pspark" title="Últimos {len(ultimos)} partidos">{barras}</div>'
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


@st.cache_data(ttl=30, show_spinner=False)
def _resumen_evento(event_id, deporte, liga_slug):
    """Descarga resumen en vivo de un partido (estadísticas, cuartos y alineaciones)."""
    if not event_id:
        return None
    if deporte == NBA:
        url = f"{nba.BASE}/summary?event={event_id}"
    else:
        slug = liga_slug or "eng.1"
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary?event={event_id}"
    return _descargar_json(url)


_STAT_NOMBRES = {
    "FG%": "% Tiros de campo", "fieldGoalPct": "% Tiros de campo",
    "3P%": "% Triples", "threePointFieldGoalPct": "% Triples",
    "FT%": "% Tiros libres", "freeThrowPct": "% Tiros libres",
    "REB": "Rebotes", "totalRebounds": "Rebotes",
    "OREB": "Rebotes ofensivos", "offensiveRebounds": "Rebotes ofensivos",
    "AST": "Asistencias", "assists": "Asistencias",
    "STL": "Robos", "steals": "Robos",
    "BLK": "Tapones", "blocks": "Tapones",
    "TO": "Pérdidas", "turnovers": "Pérdidas",
    "Points in Paint": "Puntos en pintura", "pointsInPaint": "Puntos en pintura",
    "Fast Break Points": "Puntos al contraataque",
    "Possession": "Posesión", "possessionPct": "Posesión %",
    "Shots": "Tiros totales", "totalShots": "Tiros totales",
    "Shots on Target": "Tiros al arco", "shotsOnTarget": "Tiros al arco",
    "Corner Kicks": "Córners", "wonCorners": "Córners",
    "Fouls": "Faltas", "foulsCommitted": "Faltas",
    "Yellow Cards": "Tarjetas amarillas", "yellowCards": "Tarjetas amarillas",
    "Red Cards": "Tarjetas rojas", "redCards": "Tarjetas rojas",
    "Offsides": "Fueras de juego", "offsides": "Fueras de juego",
}


def _parsear_estadisticas_y_alineacion(resumen_json, m):
    """Extrae parciales, estadísticas de equipo y alineaciones/quintetos desde el JSON de summary."""
    out = {"cuartos": {"h": [], "a": []}, "stats": [], "alineaciones": {}}
    if not isinstance(resumen_json, dict):
        return out

    hid = str(m["home"].get("id") or "")
    aid = str(m["away"].get("id") or "")

    # 1. Parciales (cuartos / tiempos)
    comps = (resumen_json.get("header") or {}).get("competitions") or []
    if comps:
        for comp in (comps[0].get("competitors") or []):
            tid = str((comp.get("team") or {}).get("id") or comp.get("id") or "")
            ls = [str(x.get("displayValue") or x.get("value") or "0") for x in (comp.get("linescores") or [])]
            if tid == hid:
                out["cuartos"]["h"] = ls
            elif tid == aid:
                out["cuartos"]["a"] = ls

    # 2. Estadísticas de equipo comparadas
    box = resumen_json.get("boxscore") or {}
    equipos_box = box.get("teams") or []
    mapa_stats = {}
    orden_claves = []
    for tb in equipos_box:
        tid = str((tb.get("team") or {}).get("id") or "")
        lado = "h" if tid == hid else ("a" if tid == aid else None)
        if not lado:
            continue
        for st_item in (tb.get("statistics") or []):
            raw_k = str(st_item.get("name") or st_item.get("label") or "")
            lbl = _STAT_NOMBRES.get(raw_k) or _STAT_NOMBRES.get(st_item.get("label") or "") or st_item.get("label") or raw_k
            val = str(st_item.get("displayValue") or "")
            if not lbl or not val:
                continue
            if lbl not in mapa_stats:
                mapa_stats[lbl] = {"h": "–", "a": "–"}
                orden_claves.append(lbl)
            mapa_stats[lbl][lado] = val
    for lbl in orden_claves[:10]:
        out["stats"].append((lbl, mapa_stats[lbl]["h"], mapa_stats[lbl]["a"]))

    # 3. Alineación NBA (boxscore.players)
    for pb in (box.get("players") or []):
        tid = str((pb.get("team") or {}).get("id") or "")
        lado = "h" if tid == hid else ("a" if tid == aid else None)
        if not lado:
            continue
        titulares, suplentes = [], []
        bloques = pb.get("statistics") or []
        if bloques:
            b0 = bloques[0]
            cols = [str(c).upper() for c in (b0.get("names") or [])]
            idx_min = cols.index("MIN") if "MIN" in cols else -1
            idx_pts = cols.index("PTS") if "PTS" in cols else -1
            idx_reb = cols.index("REB") if "REB" in cols else -1
            idx_ast = cols.index("AST") if "AST" in cols else -1
            for ath in (b0.get("athletes") or []):
                info_a = ath.get("athlete") or {}
                nom = info_a.get("shortName") or info_a.get("displayName") or ""
                if not nom:
                    continue
                pos = (info_a.get("position") or {}).get("abbreviation") or ""
                dorsal = info_a.get("jersey") or ""
                pid = str(info_a.get("id") or "")
                vals = ath.get("stats") or []
                partes = []
                if 0 <= idx_pts < len(vals):
                    partes.append(f"{vals[idx_pts]} pts")
                if 0 <= idx_reb < len(vals):
                    partes.append(f"{vals[idx_reb]} reb")
                if 0 <= idx_ast < len(vals):
                    partes.append(f"{vals[idx_ast]} ast")
                if 0 <= idx_min < len(vals) and vals[idx_min] not in ("0", "00", ""):
                    partes.append(f"{vals[idx_min]} min")
                fila = {
                    "id": pid,
                    "nom": nom,
                    "pos": pos,
                    "dorsal": dorsal,
                    "stats": " · ".join(partes) if partes else ("DNP" if ath.get("didNotPlay") else ""),
                }
                if ath.get("starter"):
                    titulares.append(fila)
                else:
                    suplentes.append(fila)
        out["alineaciones"][lado] = {"formacion": "", "titulares": titulares, "suplentes": suplentes}

    # 4. Alineación Fútbol (rosters)
    if not out["alineaciones"]:
        for rb in (resumen_json.get("rosters") or []):
            tid = str((rb.get("team") or {}).get("id") or "")
            lado = "h" if tid == hid else ("a" if tid == aid else None)
            if not lado:
                continue
            titulares, suplentes = [], []
            for pl in (rb.get("roster") or []):
                info_a = pl.get("athlete") or {}
                nom = info_a.get("shortName") or info_a.get("displayName") or ""
                if not nom:
                    continue
                pos = (pl.get("position") or info_a.get("position") or {}).get("abbreviation") or ""
                dorsal = pl.get("jersey") or info_a.get("jersey") or ""
                fila = {"id": str(info_a.get("id") or ""), "nom": nom, "pos": pos, "dorsal": str(dorsal), "stats": ""}
                if pl.get("starter"):
                    titulares.append(fila)
                else:
                    suplentes.append(fila)
            out["alineaciones"][lado] = {
                "formacion": str(rb.get("formation") or ""),
                "titulares": titulares,
                "suplentes": suplentes,
            }

    return out


def _num_val(s):
    """Convierte '45.2%' o '12' a float para calcular el ancho relativo de la barra comparativa."""
    try:
        return float(str(s).replace("%", "").strip())
    except Exception:  # noqa: BLE001
        return None


@st.dialog("Centro del partido", width="large")
def _mostrar_detalle_partido(m):
    """Modal interactivo con marcador, estadísticas en vivo, alineaciones, línea, forma y bajas."""
    h, a = m["home"], m["away"]
    st.markdown(f"**{_esc(m['liga'])}** · {_esc(m['hora'])}")
    c1, c2, c3 = st.columns([2, 1.1, 2], vertical_alignment="center")
    with c1:
        if h["logo"]:
            st.image(h["logo"], width=50)
        st.markdown(f"### {h['nombre']}")
    with c2:
        marc = f"{h['score']} - {a['score']}" if m["state"] in ("in", "post") else "vs"
        badge = '<div style="display:inline-block;padding:2px 8px;border-radius:999px;background:#FFF1F2;color:#E11D48;border:1px solid #FECDD3;font-size:.7rem;font-weight:700;margin-bottom:4px;">EN VIVO</div>' if m["state"] == "in" else ""
        st.markdown(
            f"<div style='text-align:center;'>{badge}<div style='font-family:var(--pl-font-mono);font-size:1.65rem;font-weight:800;color:#0F172A;'>{_esc(marc)}</div></div>",
            unsafe_allow_html=True,
        )
    with c3:
        if a["logo"]:
            st.image(a["logo"], width=50)
        st.markdown(f"### {a['nombre']}")

    resumen_json = None
    if m.get("id"):
        with st.spinner("Cargando estadísticas en vivo y alineaciones…"):
            resumen_json = _resumen_evento(m["id"], m["deporte"], m.get("liga_slug", ""))
    parsed = _parsear_estadisticas_y_alineacion(resumen_json, m)

    # Parciales por cuarto/tiempo si existen
    ch, ca = parsed["cuartos"]["h"], parsed["cuartos"]["a"]
    if ch and ca and len(ch) == len(ca):
        pref = "Q" if m["deporte"] == NBA else "T"
        cols_th = "".join(f"<th>{pref}{i + 1}</th>" for i in range(len(ch)))
        cols_h = "".join(f"<td>{_esc(v)}</td>" for v in ch)
        cols_a = "".join(f"<td>{_esc(v)}</td>" for v in ca)
        st.markdown(
            f"<div style='overflow-x:auto;margin:6px 0 10px;'>"
            f"<table style='width:100%;border-collapse:collapse;background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;font-size:.82rem;text-align:center;'>"
            f"<thead><tr style='background:#F8FAFC;color:#64748B;border-bottom:1px solid #E2E8F0;'><th style='text-align:left;padding:6px 10px;'>Equipo</th>{cols_th}<th style='padding:6px 10px;'>Total</th></tr></thead>"
            f"<tbody>"
            f"<tr style='border-bottom:1px solid #F1F5F9;'><td style='text-align:left;padding:6px 10px;font-weight:700;color:#0F172A;'>{_esc(h['abrev'] or h['nombre'])}</td>{cols_h}<td style='font-weight:800;color:#4F46E5;'>{_esc(h['score'])}</td></tr>"
            f"<tr><td style='text-align:left;padding:6px 10px;font-weight:700;color:#0F172A;'>{_esc(a['abrev'] or a['nombre'])}</td>{cols_a}<td style='font-weight:800;color:#0F172A;'>{_esc(a['score'])}</td></tr>"
            f"</tbody></table></div>",
            unsafe_allow_html=True,
        )

    tab_stats, tab_alin, tab_forma = st.tabs(["📊 Estadísticas en vivo", "👥 Alineación y jugadores", "📈 Forma, líneas y bajas"])

    with tab_stats:
        if parsed["stats"]:
            rows_html = []
            for lbl, vh, va in parsed["stats"]:
                nh, na = _num_val(vh), _num_val(va)
                if nh is not None and na is not None and (nh + na) > 0:
                    pw_h = round(100 * nh / (nh + na), 1)
                else:
                    pw_h = 50.0
                rows_html.append(
                    f"<div style='margin-bottom:10px;'>"
                    f"<div style='display:flex;justify-content:space-between;font-size:.82rem;font-weight:700;color:#0F172A;margin-bottom:4px;'>"
                    f"<span>{_esc(vh)}</span><span style='font-weight:600;color:#64748B;'>{_esc(lbl)}</span><span>{_esc(va)}</span>"
                    f"</div>"
                    f"<div style='display:flex;height:6px;border-radius:999px;overflow:hidden;background:#F1F5F9;'>"
                    f"<div style='width:{pw_h}%;background:#4F46E5;'></div>"
                    f"<div style='flex:1;background:#CBD5E1;'></div>"
                    f"</div></div>"
                )
            st.markdown(
                f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;padding:14px 16px;'>{''.join(rows_html)}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("Las estadísticas en vivo estarán disponibles en cuanto comience el partido.")

    with tab_alin:
        alin_h = parsed["alineaciones"].get("h")
        alin_a = parsed["alineaciones"].get("a")
        if (alin_h and (alin_h["titulares"] or alin_h["suplentes"])) or (alin_a and (alin_a["titulares"] or alin_a["suplentes"])):
            ca1, ca2 = st.columns(2)
            for col_a, eq_inf, alin in ((ca1, h, alin_h), (ca2, a, alin_a)):
                with col_a:
                    form_txt = f" · `{alin['formacion']}`" if alin and alin.get("formacion") else ""
                    st.markdown(f"**{eq_inf['nombre']}**{form_txt}")
                    if not alin or (not alin["titulares"] and not alin["suplentes"]):
                        st.caption("Sin datos de alineación.")
                        continue
                    if alin["titulares"]:
                        st.caption("Titulares")
                        filas_t = "".join(
                            f"<div style='display:flex;justify-content:space-between;align-items:center;padding:5px 8px;border-bottom:1px solid #F1F5F9;font-size:.8rem;'>"
                            f"<span><b style='color:#4F46E5;'>{_esc(f['dorsal'] or '•')}</b> <b style='color:#0F172A;'>{_esc(f['nom'])}</b> "
                            f"<span style='color:#64748B;font-size:.72rem;'>{_esc(f['pos'])}</span></span>"
                            f"<span style='font-family:var(--pl-font-mono);font-size:.73rem;color:#334155;'>{_esc(f['stats'])}</span>"
                            f"</div>"
                            for f in alin["titulares"]
                        )
                        st.markdown(f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;margin-bottom:8px;'>{filas_t}</div>", unsafe_allow_html=True)
                    if alin["suplentes"]:
                        with st.expander(f"Banca / Suplentes ({len(alin['suplentes'])})"):
                            filas_s = "".join(
                                f"<div style='display:flex;justify-content:space-between;align-items:center;padding:4px 6px;border-bottom:1px solid #F1F5F9;font-size:.78rem;'>"
                                f"<span><span style='color:#64748B;'>{_esc(f['dorsal'] or '•')}</span> {_esc(f['nom'])} "
                                f"<span style='color:#94A3B8;font-size:.7rem;'>{_esc(f['pos'])}</span></span>"
                                f"<span style='font-family:var(--pl-font-mono);font-size:.72rem;color:#475569;'>{_esc(f['stats'])}</span>"
                                f"</div>"
                                for f in alin["suplentes"]
                            )
                            st.markdown(f"<div>{filas_s}</div>", unsafe_allow_html=True)
        else:
            st.info("Alineación oficial aún no publicada (se habilita cerca del inicio del partido).")

    with tab_forma:
        # Barra de probabilidad (solo Pro; en plan gratuito se oculta con dato falso desenfocado)
        if planes.es_pro():
            st.markdown(
                f'<div class="sl-prob-wrap"><div class="sl-prob-labels">'
                f'<span>{h["abrev"] or h["nombre"]} {m["prob_h"]}%</span>'
                f'<span>Prob. de victoria</span>'
                f'<span>{m["prob_a"]}% {a["abrev"] or a["nombre"]}</span></div>'
                f'<div class="sl-prob-bar"><div class="sl-prob-home" style="width:{m["prob_h"]}%;"></div>'
                f'<div class="sl-prob-away" style="width:{m["prob_a"]}%;"></div></div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                planes.html_bloque_pro(
                    "Probabilidad de victoria",
                    "",
                    "EQU 55% · Prob. de victoria · 45% RIV",
                ),
                unsafe_allow_html=True,
            )

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

            h2h = [g for g in (cal_h.get("forma") or []) if str(g.get("rival_id")) == str(a["id"])]
            if h2h:
                st.markdown("**Últimos cruces directos encontrados**")
                for g in h2h[:3]:
                    st.caption(f"{'Victoria' if g['res'] == 'G' else 'Derrota'} de {h['nombre']} · {g['pf']}-{g['pc']}")

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
    es_pro_usr = planes.es_pro()
    prev_scores = st.session_state.setdefault("_prev_scores", {})
    n_cols = 2 if len(lista) == 1 else min(3, max(1, len(lista)))
    for i in range(0, len(lista), n_cols):
        fila = lista[i:i + n_cols]
        cols = st.columns(n_cols, gap="small")
        for j, (col, m) in enumerate(zip(cols, fila)):
            idx = i + j
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

                if es_pro_usr or idx == 0:
                    prob_html = (
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
                else:
                    prob_html = (
                        '<div class="sl-prob-wrap" style="position:relative;" title="Prob. de victoria solo con Acceso Pro">'
                        '<div style="filter:blur(5px);user-select:none;pointer-events:none;" aria-hidden="true">'
                        '<div class="sl-prob-labels"><span>55%</span><span class="sl-prob-title" style="margin:0;">Prob. de victoria</span><span>45%</span></div>'
                        '<div class="sl-prob-bar"><div class="sl-prob-home" style="width:55%;"></div><div class="sl-prob-away" style="width:45%;"></div></div>'
                        '</div>'
                        '<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;">'
                        '<span style="padding:2px 10px;border-radius:999px;background:linear-gradient(135deg,#7C3AED,#A855F7);color:#fff;font-size:.72rem;font-weight:700;box-shadow:0 2px 8px rgba(124,58,237,.35);">🔒 Acceso Pro</span>'
                        '</div>'
                        '</div>'
                    )
                if st_cls == "pre":
                    rest = _tiempo_restante(m.get("fecha"))
                    extra_txt = rest or "Próximo partido"
                    pie_html = (
                        f'<div class="sl-pre-info">'
                        f'<span>⏱️ {_esc(extra_txt)}</span>'
                        f'<span class="sl-pre-info-sub">{_esc(m["hora"])}</span>'
                        f'</div>'
                        f'{prob_html}'
                    )
                else:
                    pie_html = prob_html

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

    potd_prob_html = (
        f'<div class="sl-prob-wrap" style="margin-top:10px;padding-top:8px;border-top:1px dashed rgba(255,255,255,.14);">'
        f'<div class="sl-prob-labels" style="color:#E2E8F0;">'
        f'<span>{int(foco.get("prob_h", 50))}%</span>'
        f'<span style="font-size:.72rem;color:#94A3B8;font-weight:600;">Prob. de victoria</span>'
        f'<span>{int(foco.get("prob_a", 50))}%</span>'
        f'</div>'
        f'<div class="sl-prob-bar" style="background:rgba(255,255,255,.14);">'
        f'<div class="sl-prob-home" style="width:{int(foco.get("prob_h", 50))}%;background:#8B5CF6;"></div>'
        f'<div class="sl-prob-away" style="width:{int(foco.get("prob_a", 50))}%;background:rgba(255,255,255,.16);"></div>'
        f'</div>'
        f'</div>'
    )

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
          {potd_prob_html}
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

        if len(partidos) > 1:
            foco2 = partidos[1]
            h2_nom = foco2["home"]["nombre"]
            a2_nom = foco2["away"]["nombre"]
            h2_ab = (foco2["home"].get("abrev") or h2_nom[:3]).upper()
            a2_ab = (foco2["away"].get("abrev") or a2_nom[:3]).upper()
            h2_badge = (f'<img src="{_esc(foco2["home"]["logo"])}" style="width:32px;height:32px;object-fit:contain;">'
                        if foco2["home"]["logo"] else f'<div class="potd-badge potd-badge--mc" style="width:32px;height:32px;font-size:.7rem;">{_esc(h2_ab)}</div>')
            a2_badge = (f'<img src="{_esc(foco2["away"]["logo"])}" style="width:32px;height:32px;object-fit:contain;">'
                        if foco2["away"]["logo"] else f'<div class="potd-badge potd-badge--nap" style="width:32px;height:32px;font-size:.7rem;">{_esc(a2_ab)}</div>')

            es_pro_usr = planes.es_pro()
            if es_pro_usr:
                ph, pa = int(foco2.get("prob_h", 50)), int(foco2.get("prob_a", 50))
                fav_nom = h2_nom if ph >= pa else a2_nom
                fav_pct = max(ph, pa)
                bloque2_res = (
                    f'<div style="margin-top:10px;padding:10px 12px;border-radius:10px;'
                    f'background:rgba(139,92,246,.16);border:1px solid rgba(167,139,250,.38);'
                    f'color:#F8FAFC;font-size:.82rem;display:flex;justify-content:space-between;align-items:center;">'
                    f'<span>★ <b>{_esc(fav_nom)}</b></span>'
                    f'<span style="color:#C4B5FD;font-weight:700;">{fav_pct}% prob.</span>'
                    f'</div>'
                )
            else:
                bloque2_res = (
                    '<div style="position:relative;margin-top:10px;border-radius:12px;overflow:hidden;'
                    'background:rgba(255,255,255,.04);border:1px solid rgba(167,139,250,.22);padding:14px 12px;min-height:66px;" '
                    'title="Acceso Pro">'
                    '<div style="filter:blur(7px);user-select:none;pointer-events:none;opacity:.75;" aria-hidden="true">'
                    '<div style="height:10px;width:72%;background:rgba(196,181,253,.45);border-radius:6px;margin-bottom:8px;"></div>'
                    '<div style="font-size:.78rem;color:#CBD5E1;">Pick principal: Equipo Local · Cuota 1.92 · Confianza alta</div>'
                    '</div>'
                    '<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;'
                    'background:radial-gradient(circle, rgba(11,15,32,.35) 0%, rgba(11,15,32,.75) 100%);">'
                    '<span style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:999px;'
                    'background:linear-gradient(135deg,#7C3AED,#A855F7);color:#FFFFFF;font-size:.78rem;font-weight:700;'
                    'box-shadow:0 4px 16px rgba(124,58,237,.45);border:1px solid rgba(255,255,255,.22);">'
                    '🔒 Acceso Pro</span>'
                    '</div>'
                    '</div>'
                )

            html_col2_b = textwrap.dedent(f"""
            <div style="margin-top:10px;padding:14px;border-radius:16px;
                        background:linear-gradient(160deg,#131836 0%,#0B0F20 100%);
                        border:1px solid rgba(139,92,246,.42);
                        box-shadow:0 10px 26px rgba(11,15,32,.28);color:#F8FAFC;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span style="font-size:.72rem;font-weight:700;letter-spacing:.05em;color:#C4B5FD;">¿QUIÉN GANARÁ?</span>
                <span style="font-size:.72rem;color:#94A3B8;">{_esc(foco2["liga"])} · {_esc(foco2["hora"])}</span>
              </div>
              <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;
                          padding:8px 10px;border-radius:10px;background:rgba(255,255,255,.04);">
                <div style="display:flex;align-items:center;gap:6px;min-width:0;">
                  {h2_badge}
                  <span style="font-size:.82rem;font-weight:700;color:#F8FAFC;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_esc(h2_nom)}</span>
                </div>
                <span style="font-size:.72rem;color:#64748B;font-weight:700;">vs</span>
                <div style="display:flex;align-items:center;gap:6px;min-width:0;justify-content:flex-end;">
                  <span style="font-size:.82rem;font-weight:700;color:#F8FAFC;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_esc(a2_nom)}</span>
                  {a2_badge}
                </div>
              </div>
              {bloque2_res}
            </div>
            """).strip()
            st.markdown(html_col2_b, unsafe_allow_html=True)
            if not es_pro_usr:
                if st.button("🔒 Acceso Pro", key="btn_potd2_pro", use_container_width=True):
                    planes.modal_pro("Desbloquea el pronóstico de todos los partidos del día con ScoreLine Pro.")

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


def _catalogo_busqueda(partidos):
    """Construye catálogo deduplicado de equipos, ligas y jugadores con imágenes para autocompletar."""
    items = []
    vistos_eq = set()

    # 1. Equipos de partidos de hoy (priorizando los en vivo)
    for m in partidos or []:
        es_vivo = m.get("state") == "in"
        liga = m.get("liga") or ""
        hora = "En vivo" if es_vivo else (m.get("hora") or "Hoy")
        for lado in ("home", "away"):
            eq = m.get(lado) or {}
            nom = (eq.get("nombre") or "").strip()
            if not nom:
                continue
            clave = _sin_tildes(nom)
            if clave in vistos_eq:
                continue
            vistos_eq.add(clave)
            ab = eq.get("abrev") or ""
            img = eq.get("logo") or (fd.escudo(ab) if m.get("deporte") == NBA else "")
            items.append({
                "n": nom,
                "s": f"{liga} · {hora}".strip(" ·"),
                "t": "En vivo" if es_vivo else "Hoy",
                "k": "eq",
                "img": img,
                "ab": ab or nom[:3].upper(),
                "p": 0 if es_vivo else 1,
            })

    # 2. Ligas activas
    ligas_meta = [
        ("NBA", "Baloncesto · USA", "🏀"),
        ("Premier League", "Fútbol · Inglaterra", "⚽"),
        ("LaLiga", "Fútbol · España", "⚽"),
        ("Champions League", "Fútbol · Europa", "⚽"),
        ("Liga Chilena", "Fútbol · Chile", "⚽"),
        ("Liga Argentina", "Fútbol · Argentina", "⚽"),
    ]
    for nom_l, sub_l, ico in ligas_meta:
        items.append({
            "n": nom_l,
            "s": sub_l,
            "t": "Liga",
            "k": "liga",
            "img": "",
            "ab": ico,
            "p": 2,
        })

    # 3. Todos los equipos NBA (si no estaban ya en partidos de hoy)
    try:
        eq_nba = fd.mapa_equipos()
    except Exception:  # noqa: BLE001
        eq_nba = {}
    for eq in eq_nba.values():
        nom = (eq.get("nombre") or "").strip()
        if not nom:
            continue
        clave = _sin_tildes(nom)
        if clave in vistos_eq:
            continue
        vistos_eq.add(clave)
        ab = eq.get("abrev") or ""
        items.append({
            "n": nom,
            "s": f"NBA · {ab}" if ab else "NBA",
            "t": "Equipo",
            "k": "eq",
            "img": fd.escudo(ab),
            "ab": ab or nom[:3].upper(),
            "p": 3,
        })

    # 4. Jugadores NBA (favoritos y estrellas primero)
    vistos_jug = set()
    try:
        info_jug = fd.jugadores_info()
    except Exception:  # noqa: BLE001
        info_jug = {}
    try:
        fav_ids = {str(x) for x in favoritos.jugadores()}
    except Exception:  # noqa: BLE001
        fav_ids = set()

    for pid in fav_ids:
        j = info_jug.get(pid) or {}
        nom = (j.get("nombre") or "").strip()
        if not nom or pid in vistos_jug:
            continue
        vistos_jug.add(pid)
        eq = j.get("equipo") or "NBA"
        items.append({
            "n": nom,
            "s": f"Favorito · {eq}",
            "t": "Jugador",
            "k": "jug",
            "img": fd.foto(pid),
            "ab": "".join(p[0] for p in nom.split()[:2]).upper() or "NB",
            "p": 1,
        })

    for pid, nom, eq in _ESTRELLAS_RESPALDO:
        if pid in vistos_jug:
            continue
        vistos_jug.add(pid)
        items.append({
            "n": nom,
            "s": f"NBA · {eq}",
            "t": "Jugador",
            "k": "jug",
            "img": fd.foto(pid),
            "ab": "".join(p[0] for p in nom.split()[:2]).upper() or "NB",
            "p": 1,
        })

    for pid, j in info_jug.items():
        if pid in vistos_jug:
            continue
        nom = (j.get("nombre") or "").strip()
        if not nom:
            continue
        vistos_jug.add(pid)
        eq = j.get("equipo") or "NBA"
        items.append({
            "n": nom,
            "s": f"NBA · {eq}",
            "t": "Jugador",
            "k": "jug",
            "img": fd.foto(pid),
            "ab": "".join(p[0] for p in nom.split()[:2]).upper() or "NB",
            "p": 4,
        })

    return items


def _inyectar_buscador_js(catalogo):
    """Inyecta autocompletado instantáneo con logos/fotos sobre el buscador de Inicio."""
    payload = json.dumps(catalogo, ensure_ascii=False).replace("</", "<\\/")
    html = f"""<script>
(function() {{
  try {{
    var P = window.parent;
    var doc = P.document;
    P.__slSearchCatalog = {payload};

    if (!doc.getElementById('sl-ac-style')) {{
      var st = doc.createElement('style');
      st.id = 'sl-ac-style';
      st.textContent = `
        .sl-ac-drop {{
          position: fixed; z-index: 999999; display: none;
          background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 14px;
          box-shadow: 0 20px 44px -10px rgba(15,23,42,.18), 0 4px 12px -2px rgba(15,23,42,.06);
          overflow: hidden; font-family: 'Plus Jakarta Sans', 'Inter', system-ui, sans-serif;
        }}
        .sl-ac-head {{
          display: flex; align-items: center; justify-content: space-between;
          padding: 7px 14px; background: #F8FAFC; border-bottom: 1px solid #EEF2F6;
          font-size: .71rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: #64748B;
        }}
        .sl-ac-list {{ max-height: 320px; overflow-y: auto; }}
        .sl-ac-item {{
          display: flex; align-items: center; gap: 11px; padding: 8px 14px;
          cursor: pointer; border-bottom: 1px solid #F1F5F9; transition: background .1s ease;
        }}
        .sl-ac-item:last-child {{ border-bottom: none; }}
        .sl-ac-item:hover, .sl-ac-item.active {{ background: #F5F7FF; }}
        .sl-ac-av {{
          width: 36px; height: 36px; flex-shrink: 0; display: grid; place-items: center;
          overflow: hidden; position: relative; font-weight: 800; font-size: .74rem; color: #4338CA;
        }}
        .sl-ac-av.jug {{
          border-radius: 50%; background: radial-gradient(circle at 50% 25%, #F8FAFC, #E0E7FF);
          border: 1.5px solid #C7D2FE;
        }}
        .sl-ac-av.eq {{
          border-radius: 10px; background: #F8FAFC; border: 1px solid #E2E8F0; padding: 3px;
        }}
        .sl-ac-av.liga {{
          border-radius: 10px; background: #EEF2FF; border: 1px solid #C7D2FE; font-size: 1rem;
        }}
        .sl-ac-av img {{ width: 100%; height: 100%; display: block; }}
        .sl-ac-av.jug img {{ object-fit: cover; object-position: 50% 10%; }}
        .sl-ac-av.eq img {{ object-fit: contain; }}
        .sl-ac-info {{ flex: 1; min-width: 0; }}
        .sl-ac-name {{
          font-size: .88rem; font-weight: 700; color: #0F172A; line-height: 1.2;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .sl-ac-name mark {{
          background: #EEF2FF; color: #4338CA; padding: 0 2px; border-radius: 4px; font-weight: 800;
        }}
        .sl-ac-sub {{
          font-size: .74rem; color: #64748B; margin-top: 1px;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .sl-ac-tag {{
          flex-shrink: 0; font-size: .68rem; font-weight: 700; padding: 2px 8px;
          border-radius: 999px; border: 1px solid #E2E8F0; background: #F8FAFC; color: #475569;
        }}
        .sl-ac-tag.vivo {{ background: #FFF1F2; color: #E11D48; border-color: #FECDD3; }}
        .sl-ac-tag.eq, .sl-ac-tag.hoy {{ background: #EEF2FF; color: #4338CA; border-color: #C7D2FE; }}
        .sl-ac-tag.jug {{ background: #F5F3FF; color: #6D28D9; border-color: #DDD6FE; }}
        .sl-ac-foot {{
          padding: 6px 14px; background: #F8FAFC; border-top: 1px solid #EEF2F6;
          font-size: .7rem; color: #94A3B8; display: flex; justify-content: space-between;
        }}
        .sl-ac-clear {{
          position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
          width: 22px; height: 22px; border-radius: 50%; border: none;
          background: #F1F5F9; color: #64748B; font-size: .82rem; line-height: 1;
          cursor: pointer; display: none; place-items: center; z-index: 3;
        }}
        .sl-ac-clear:hover {{ background: #E2E8F0; color: #0F172A; }}
      `;
      doc.head.appendChild(st);
    }}

    var drop = doc.getElementById('sl-ac-drop');
    if (!drop) {{
      drop = doc.createElement('div');
      drop.id = 'sl-ac-drop';
      drop.className = 'sl-ac-drop';
      doc.body.appendChild(drop);
    }}

    var norm = function(s) {{
      return (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
    }};
    var esc = function(s) {{
      return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }};

    var bind = function() {{
      var wrap = doc.querySelector('.st-key-inicio_busqueda');
      var inp = wrap ? wrap.querySelector('input') : null;
      if (!inp) return;

      var base = inp.closest('[data-baseweb="input"]') || inp.parentElement;
      if (base && !base.querySelector('.sl-ac-clear')) {{
        base.style.position = 'relative';
        var clr = doc.createElement('button');
        clr.type = 'button';
        clr.className = 'sl-ac-clear';
        clr.title = 'Limpiar búsqueda';
        clr.textContent = '×';
        clr.addEventListener('mousedown', function(e) {{
          e.preventDefault();
          commitValue(inp, '');
          clr.style.display = 'none';
          drop.style.display = 'none';
        }});
        base.appendChild(clr);
      }}
      var clrBtn = base ? base.querySelector('.sl-ac-clear') : null;
      if (clrBtn) clrBtn.style.display = inp.value ? 'grid' : 'none';

      if (inp.dataset.slAcBound === '1') return;
      inp.dataset.slAcBound = '1';

      var activeIdx = -1;
      var currentItems = [];

      var commitValue = function(targetInp, val) {{
        var setter = Object.getOwnPropertyDescriptor(P.HTMLInputElement.prototype, 'value').set;
        setter.call(targetInp, val);
        targetInp.dispatchEvent(new P.Event('input', {{ bubbles: true }}));
        targetInp.dispatchEvent(new P.KeyboardEvent('keydown', {{
          key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
        }}));
      }};

      var placeDrop = function() {{
        var box = (inp.closest('[data-baseweb="input"]') || inp).getBoundingClientRect();
        drop.style.left = Math.max(8, box.left) + 'px';
        drop.style.top = (box.bottom + 6) + 'px';
        drop.style.width = Math.max(280, box.width) + 'px';
      }};

      var highlightMatch = function(name, rawQ) {{
        if (!rawQ) return esc(name);
        var nName = norm(name);
        var nQ = norm(rawQ);
        var idx = nName.indexOf(nQ);
        if (idx < 0) return esc(name);
        return esc(name.slice(0, idx)) + '<mark>' + esc(name.slice(idx, idx + rawQ.length)) + '</mark>' + esc(name.slice(idx + rawQ.length));
      }};

      var renderDrop = function(rawQ) {{
        var cat = P.__slSearchCatalog || [];
        var q = norm((rawQ || '').trim());
        var list = [];
        if (!q) {{
          list = cat.filter(function(x) {{ return x.p <= 2; }}).slice(0, 6);
        }} else {{
          var scored = [];
          for (var i = 0; i < cat.length; i++) {{
            var it = cat[i];
            var nName = norm(it.n);
            var nSub = norm(it.s);
            var pos = nName.indexOf(q);
            var inSub = nSub.indexOf(q);
            if (pos === -1 && inSub === -1) continue;
            var rank = (pos === 0 ? 0 : (nName.indexOf(' ' + q) >= 0 ? 1 : (pos > 0 ? 2 : 3))) * 10 + (it.p || 4);
            scored.push({{ item: it, rank: rank }});
          }}
          scored.sort(function(a, b) {{ return a.rank - b.rank; }});
          list = scored.slice(0, 8).map(function(x) {{ return x.item; }});
        }}
        currentItems = list;
        activeIdx = -1;
        if (!list.length) {{
          drop.innerHTML = '<div class="sl-ac-head"><span>Sin coincidencias</span></div>'
            + '<div style="padding:12px 14px;font-size:.82rem;color:#64748B;">No encontramos equipos, ligas ni jugadores con <b>' + esc(rawQ) + '</b>.</div>';
          placeDrop();
          drop.style.display = 'block';
          return;
        }}
        var headTxt = q ? ('Sugerencias · ' + list.length) : 'Búsquedas rápidas';
        var rows = list.map(function(it, idx) {{
          var av = '';
          if (it.img) {{
            av = '<div class="sl-ac-av ' + it.k + '"><img src="' + esc(it.img) + '" alt="" onerror="this.style.display=\\'none\\';this.nextElementSibling.style.display=\\'block\\';"><span style="display:none">' + esc(it.ab || '?') + '</span></div>';
          }} else {{
            av = '<div class="sl-ac-av ' + it.k + '">' + esc(it.ab || '★') + '</div>';
          }}
          var tagCls = it.t === 'En vivo' ? 'vivo' : (it.k === 'jug' ? 'jug' : (it.k === 'eq' ? 'eq' : ''));
          return '<div class="sl-ac-item" data-idx="' + idx + '">' + av
            + '<div class="sl-ac-info"><div class="sl-ac-name">' + highlightMatch(it.n, (rawQ || '').trim()) + '</div>'
            + '<div class="sl-ac-sub">' + esc(it.s) + '</div></div>'
            + '<span class="sl-ac-tag ' + tagCls + '">' + esc(it.t) + '</span></div>';
        }}).join('');
        drop.innerHTML = '<div class="sl-ac-head"><span>' + headTxt + '</span><span>Click o Enter</span></div>'
          + '<div class="sl-ac-list">' + rows + '</div>'
          + '<div class="sl-ac-foot"><span>↑↓ navegar · Enter aplicar</span><span>Esc cerrar</span></div>';
        placeDrop();
        drop.style.display = 'block';
        drop.querySelectorAll('.sl-ac-item').forEach(function(el) {{
          el.addEventListener('mousedown', function(ev) {{
            ev.preventDefault();
            var it = currentItems[parseInt(el.dataset.idx, 10)];
            if (it) {{
              drop.style.display = 'none';
              commitValue(inp, it.n);
            }}
          }});
        }});
      }};

      inp.addEventListener('focus', function() {{ renderDrop(inp.value); }});
      inp.addEventListener('input', function() {{
        if (clrBtn) clrBtn.style.display = inp.value ? 'grid' : 'none';
        renderDrop(inp.value);
      }});
      inp.addEventListener('blur', function() {{
        setTimeout(function() {{ drop.style.display = 'none'; }}, 140);
      }});
      inp.addEventListener('keydown', function(e) {{
        if (drop.style.display !== 'block') return;
        var items = drop.querySelectorAll('.sl-ac-item');
        if (e.key === 'ArrowDown') {{
          e.preventDefault();
          activeIdx = (activeIdx + 1) % Math.max(1, items.length);
        }} else if (e.key === 'ArrowUp') {{
          e.preventDefault();
          activeIdx = (activeIdx - 1 + items.length) % Math.max(1, items.length);
        }} else if (e.key === 'Escape') {{
          drop.style.display = 'none';
          return;
        }} else if (e.key === 'Enter' && activeIdx >= 0 && currentItems[activeIdx]) {{
          e.preventDefault();
          e.stopPropagation();
          var chosen = currentItems[activeIdx];
          drop.style.display = 'none';
          commitValue(inp, chosen.n);
          return;
        }} else {{
          return;
        }}
        items.forEach(function(el, i) {{
          el.classList.toggle('active', i === activeIdx);
          if (i === activeIdx) el.scrollIntoView({{ block: 'nearest' }});
        }});
      }});

      P.addEventListener('resize', function() {{ if (drop.style.display === 'block') placeDrop(); }});
      doc.addEventListener('scroll', function() {{ if (drop.style.display === 'block') placeDrop(); }}, true);
    }};

    bind();
    setTimeout(bind, 120);
  }} catch(e) {{}}
}})();
</script>"""
    components.html(html, height=0, width=0)


def pagina_inicio():
    """Pantalla principal: compacta, directa y con En vivo + Partidos de hoy visibles sin scroll."""
    _abrir_alertas_js()

    # 1. Línea de saludo/resumen + buscador compacto con autocompletado en vivo
    c_sal, c_bus = st.columns([1.3, 1.4], vertical_alignment="center")
    c_sal.markdown(
        '<div class="sl-top-bar">'
        '<div class="sl-top-ico">'
        '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>'
        '</svg>'
        '</div>'
        '<div>'
        '<div class="sl-top-title">Centro de análisis deportivo</div>'
        '<div class="sl-top-sub">Marcadores en directo, partidos de hoy y tus favoritos en un solo lugar.</div>'
        '</div>'
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
    partidos = _bloque_jornada(busqueda)

    # 3. Jugadores destacados con foto real y líneas clave
    _render_jugadores_destacados(busqueda)

    # 4. Autocompletado instantáneo con fotos de jugadores y escudos de equipos
    _inyectar_buscador_js(_catalogo_busqueda(partidos or []))
