"""NBA · Equipos: escudos de los 30 equipos -> plantel actual -> ficha completa de cada jugador.

Flujo de navegación (se guarda en st.session_state):
  eq_equipo   = id del equipo elegido (None = se ven todos los escudos)
  eq_jugador  = id del jugador elegido (None = se ve el plantel)

Fuente de datos: API pública de ESPN (la misma que usa el resto de la app).
"""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st

try:
    from common import _session  # misma sesión HTTP que usan los demás módulos
except Exception:  # noqa: BLE001
    import requests
    _session = requests.Session()

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
WEB = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"

POSICIONES = {"PG": "Base", "SG": "Escolta", "G": "Base/Escolta", "SF": "Alero", "PF": "Ala-pívot",
              "F": "Alero/Ala-pívot", "C": "Pívot"}

GRUPOS_POS = [("Bases y escoltas", ("PG", "SG", "G")),
              ("Aleros y ala-pívots", ("SF", "PF", "F")),
              ("Pívots", ("C",))]


# ---------------------------------------------------------------------------
# Descarga de datos (todo con caché para que la app sea rápida)
# ---------------------------------------------------------------------------
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AnalisisDeportivo/1.0)", "Accept": "application/json"}


def _get(url, params=None):
    """Descarga JSON; reintenta con la sesión de la app y luego con requests directo."""
    import requests
    for intento in (_session, requests):
        try:
            r = intento.get(url, params=params, headers=_HEADERS, timeout=12)
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            continue
    return None


# Respaldo con los 30 equipos (id de ESPN, abreviatura, nombre) por si la API de ESPN falla.
_RESPALDO = [
    ("1", "ATL", "Atlanta Hawks"), ("2", "BOS", "Boston Celtics"), ("17", "BKN", "Brooklyn Nets"),
    ("30", "CHA", "Charlotte Hornets"), ("4", "CHI", "Chicago Bulls"), ("5", "CLE", "Cleveland Cavaliers"),
    ("6", "DAL", "Dallas Mavericks"), ("7", "DEN", "Denver Nuggets"), ("8", "DET", "Detroit Pistons"),
    ("9", "GS", "Golden State Warriors"), ("10", "HOU", "Houston Rockets"), ("11", "IND", "Indiana Pacers"),
    ("12", "LAC", "LA Clippers"), ("13", "LAL", "Los Angeles Lakers"), ("29", "MEM", "Memphis Grizzlies"),
    ("14", "MIA", "Miami Heat"), ("15", "MIL", "Milwaukee Bucks"), ("16", "MIN", "Minnesota Timberwolves"),
    ("3", "NO", "New Orleans Pelicans"), ("18", "NY", "New York Knicks"), ("25", "OKC", "Oklahoma City Thunder"),
    ("19", "ORL", "Orlando Magic"), ("20", "PHI", "Philadelphia 76ers"), ("21", "PHX", "Phoenix Suns"),
    ("22", "POR", "Portland Trail Blazers"), ("23", "SAC", "Sacramento Kings"), ("24", "SA", "San Antonio Spurs"),
    ("28", "TOR", "Toronto Raptors"), ("26", "UTAH", "Utah Jazz"), ("27", "WSH", "Washington Wizards"),
]


def _equipos_respaldo():
    return sorted(({"id": i, "nombre": n, "abbr": a,
                    "escudo": f"https://a.espncdn.com/i/teamlogos/nba/500/{a.lower()}.png", "color": "#4f46e5"}
                   for i, a, n in _RESPALDO), key=lambda e: e["nombre"])


@st.cache_data(ttl=3600, show_spinner=False)
def _equipos_api():
    """Lista de equipos desde ESPN. Si falla LANZA error, así Streamlit no guarda un resultado vacío en caché."""
    js = _get(BASE + "/teams", {"limit": 40})
    if not js:
        raise RuntimeError("ESPN no respondió")
    try:
        crudos = js["sports"][0]["leagues"][0]["teams"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Formato inesperado") from exc
    equipos = []
    for t in crudos:
        t = t.get("team", t)
        abbr = (t.get("abbreviation") or "").lower()
        logos = t.get("logos") or []
        escudo = logos[0].get("href") if logos else f"https://a.espncdn.com/i/teamlogos/nba/500/{abbr}.png"
        equipos.append({"id": str(t.get("id")), "nombre": t.get("displayName", "?"), "abbr": t.get("abbreviation", ""),
                        "escudo": escudo, "color": "#" + (t.get("color") or "4f46e5")})
    if len(equipos) < 20:
        raise RuntimeError("Lista incompleta")
    return sorted(equipos, key=lambda e: e["nombre"])


def _equipos():
    """Equipos de la NBA: ESPN si responde; si no, la lista de respaldo (nunca queda vacía)."""
    try:
        return _equipos_api()
    except Exception:  # noqa: BLE001
        return _equipos_respaldo()


@st.cache_data(ttl=600, show_spinner=False)
def _plantel(equipo_id):
    """Jugadores actuales del equipo (ESPN actualiza el plantel con cada fichaje o corte)."""
    js = _get(f"{BASE}/teams/{equipo_id}/roster")
    if not js:
        return None
    crudos = js.get("athletes") or []
    if crudos and isinstance(crudos[0], dict) and "items" in crudos[0]:  # por si vienen agrupados
        crudos = [a for g in crudos for a in g.get("items", [])]
    jugadores = []
    for a in crudos:
        lesiones = a.get("injuries") or []
        jugadores.append({
            "id": str(a.get("id")), "nombre": a.get("displayName") or a.get("fullName", "?"),
            "camiseta": a.get("jersey") or "–",
            "pos": (a.get("position") or {}).get("abbreviation", ""),
            "altura": a.get("displayHeight") or "–", "peso": a.get("displayWeight") or "–",
            "altura_cm": round(a["height"] * 2.54) if isinstance(a.get("height"), (int, float)) else None,
            "nacimiento": (a.get("dateOfBirth") or "")[:10],
            "edad": a.get("age"), "exp": (a.get("experience") or {}).get("years"),
            "universidad": (a.get("college") or {}).get("name") or "–",
            "foto": (a.get("headshot") or {}).get("href"),
            "lesion": (lesiones[0].get("status") if lesiones else None),
        })
    return {"jugadores": jugadores, "nombre": (js.get("team") or {}).get("displayName"),
            "record": (js.get("team") or {}).get("recordSummary")}


def _fila_temporada(s, labels):
    temporada = s.get("season")
    if isinstance(temporada, dict):
        temporada = temporada.get("displayName") or temporada.get("year")
    fila = {"Temporada": temporada, "Equipo": (s.get("teamSlug") or "").replace("-", " ").title()}
    fila.update(zip(labels, s.get("stats", [])))
    return fila


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=600, show_spinner=False)
def _estadisticas(jugador_id):
    """{categoria: DataFrame} con promedios y totales por temporada (y la fila de carrera)."""
    js = _get(f"{WEB}/athletes/{jugador_id}/stats")
    if not js:
        return {}
    tablas = {}
    for cat in js.get("categories", []) or []:
        labels = cat.get("labels") or []
        filas = [_fila_temporada(s, labels) for s in cat.get("statistics", []) or []]
        if cat.get("totals"):
            filas.append({"Temporada": "Carrera", "Equipo": "", **dict(zip(labels, cat["totals"]))})
        if filas:
            tablas[cat.get("displayName") or cat.get("name", "Stats")] = pd.DataFrame(filas)
    return tablas


def _promedios_actuales(tablas):
    """(temporada, {etiqueta: valor}) de la última temporada con promedios; ({}, None) si no hay."""
    for nombre, df in tablas.items():
        if "average" in nombre.lower() or "promedio" in nombre.lower():
            df = df[df["Temporada"] != "Carrera"]
            if len(df):
                ult = df.iloc[-1]
                return ult["Temporada"], ult.to_dict()
    return None, {}


@st.cache_data(ttl=600, show_spinner=False)
def _ultimos_partidos(jugador_id):
    js = _get(f"{WEB}/athletes/{jugador_id}/gamelog")
    if not js:
        return pd.DataFrame()
    labels = js.get("labels") or js.get("names") or []
    meta = js.get("events") or {}
    filas = []
    for tipo in (js.get("seasonTypes") or [])[:1]:  # temporada actual (la primera que informa ESPN)
        for cat in tipo.get("categories", []) or []:
            for ev in cat.get("events", []) or []:
                m = meta.get(str(ev.get("eventId")), {})
                res = {"W": "G", "L": "P"}.get(m.get("gameResult"), m.get("gameResult") or "")
                rival = (m.get("opponent") or {}).get("displayName", "?")
                fila = {"Fecha": (m.get("gameDate") or "")[:10],
                        "Rival": ("vs " if m.get("atVs") == "vs" else "@ ") + rival,
                        "Resultado": f"{res} {m.get('score', '')}".strip()}
                fila.update(zip(labels, ev.get("stats", [])))
                filas.append(fila)
    df = pd.DataFrame(filas)
    return df.sort_values("Fecha", ascending=False).reset_index(drop=True) if len(df) else df


@st.cache_data(ttl=600, show_spinner=False)
def _promedios_plantel(equipo_id):
    """{jugador_id: {PTS, REB, AST, GP, GS, MIN}} de toda la plantilla, descargado en paralelo."""
    ids = [j["id"] for j in (_plantel(equipo_id) or {"jugadores": []})["jugadores"]]

    def una(jid):
        _, prom = _promedios_actuales(_estadisticas(jid))
        return jid, {k: _num(prom.get(k)) for k in ("GP", "GS", "MIN", "PTS", "REB", "AST")}

    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(una, ids))


# ---------------------------------------------------------------------------
# Navegación
# ---------------------------------------------------------------------------
def _elegir_equipo(equipo_id):
    st.session_state["eq_equipo"] = equipo_id
    st.session_state["eq_jugador"] = None


def _elegir_jugador(jugador_id):
    st.session_state["eq_jugador"] = jugador_id


def _volver_a_equipos():
    st.session_state["eq_equipo"] = None
    st.session_state["eq_jugador"] = None


def _volver_al_plantel():
    st.session_state["eq_jugador"] = None


# ---------------------------------------------------------------------------
# Pantallas
# ---------------------------------------------------------------------------
def _pantalla_escudos():
    st.title("Equipos de la NBA")
    st.caption("Toca el escudo de un equipo para ver su plantel actual.")
    equipos = _equipos()
    if not equipos:
        st.error("No se pudo cargar la lista de equipos. Revisa **Diagnóstico** (fuente «Equipos»).")
        return
    for i in range(0, len(equipos), 5):
        for col, e in zip(st.columns(5), equipos[i:i + 5]):
            with col, st.container(border=True):
                st.image(e["escudo"], width=84)
                st.markdown(f"**{e['nombre']}**")
                st.button("Ver plantel", key=f"eq_{e['id']}", on_click=_elegir_equipo, args=(e["id"],),
                          use_container_width=True)


def _cabecera_equipo(equipo, plantel):
    c1, c2 = st.columns([1, 6], vertical_alignment="center")
    c1.image(equipo["escudo"], width=96)
    c2.title(equipo["nombre"])
    if plantel.get("record"):
        c2.caption(f"Récord: {plantel['record']}")


def _quinteto(jugadores, prom):
    """Quinteto probable: los 5 con más partidos de titular (desempata por minutos) esta temporada."""
    con_datos = [j for j in jugadores if (prom.get(j["id"], {}).get("GP") or 0) > 0]
    if len(con_datos) < 5:
        return []
    clave = lambda j: ((prom[j["id"]].get("GS") or 0), (prom[j["id"]].get("MIN") or 0))  # noqa: E731
    return sorted(con_datos, key=clave, reverse=True)[:5]


def _tarjeta_jugador(j, prom, clave):
    with st.container(border=True):
        a, b = st.columns([1, 2], vertical_alignment="center")
        if j["foto"]:
            a.image(j["foto"], use_container_width=True)
        else:
            a.markdown("## 🏀")
        b.markdown(f"**{j['nombre']}**")
        b.caption(f"#{j['camiseta']} · {j['pos'] or '–'} · {j['altura']}")
        p = prom.get(j["id"], {})
        if p.get("PTS") is not None:
            b.caption(f"{p['PTS']:.1f} PTS · {p['REB']:.1f} REB · {p['AST']:.1f} AST")
        if j["lesion"]:
            b.caption(f"🩹 {j['lesion']}")
        st.button("Ver estadísticas", key=f"jug_{clave}_{j['id']}", on_click=_elegir_jugador, args=(j["id"],),
                  use_container_width=True)


def _pantalla_plantel(equipo):
    st.button("← Todos los equipos", on_click=_volver_a_equipos)
    plantel = _plantel(equipo["id"])
    if not plantel or not plantel["jugadores"]:
        st.error("No se pudo cargar el plantel de este equipo. Inténtalo de nuevo en unos minutos.")
        return
    _cabecera_equipo(equipo, plantel)
    jugadores = plantel["jugadores"]

    with st.spinner("Cargando estadísticas del plantel..."):
        prom = _promedios_plantel(equipo["id"])

    quinteto = _quinteto(jugadores, prom)
    if quinteto:
        st.subheader("Quinteto probable")
        st.caption("Los cinco con más partidos como titular en la temporada actual.")
        for col, j in zip(st.columns(5), quinteto):
            with col:
                _tarjeta_jugador(j, prom, "q")

    st.subheader(f"Plantel completo ({len(jugadores)} jugadores)")
    for titulo, posiciones in GRUPOS_POS:
        grupo = [j for j in jugadores if j["pos"] in posiciones]
        if not grupo:
            continue
        st.markdown(f"##### {titulo}")
        for i in range(0, len(grupo), 4):
            for col, j in zip(st.columns(4), grupo[i:i + 4]):
                with col:
                    _tarjeta_jugador(j, prom, "p")
    otros = [j for j in jugadores if j["pos"] not in {p for _, ps in GRUPOS_POS for p in ps}]
    if otros:
        st.markdown("##### Otros")
        for i in range(0, len(otros), 4):
            for col, j in zip(st.columns(4), otros[i:i + 4]):
                with col:
                    _tarjeta_jugador(j, prom, "o")

    with st.expander("Ver plantel como tabla"):
        filas = []
        for j in jugadores:
            p = prom.get(j["id"], {})
            filas.append({"#": j["camiseta"], "Jugador": j["nombre"], "Pos": j["pos"], "Altura": j["altura"],
                          "Peso": j["peso"], "Edad": j["edad"], "Años NBA": j["exp"], "Universidad": j["universidad"],
                          "PJ": p.get("GP"), "MIN": p.get("MIN"), "PTS": p.get("PTS"), "REB": p.get("REB"),
                          "AST": p.get("AST"), "Estado": j["lesion"] or "Disponible"})
        st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)


def _pantalla_jugador(equipo, jugador_id):
    st.button(f"← Plantel de {equipo['nombre']}", on_click=_volver_al_plantel)
    plantel = _plantel(equipo["id"]) or {"jugadores": []}
    j = next((x for x in plantel["jugadores"] if x["id"] == jugador_id), None)
    if j is None:
        st.warning("Este jugador ya no aparece en el plantel.")
        return

    # Cabecera grande: foto a la izquierda, datos al centro, escudo del equipo a la derecha.
    with st.container(border=True):
        c1, c2, c3 = st.columns([1.5, 4, 1.5], vertical_alignment="center")
        if j["foto"]:
            c1.image(j["foto"], use_container_width=True)
        else:
            c1.markdown("# 🏀")
        c2.title(j["nombre"])
        lineas = [f"**{POSICIONES.get(j['pos'], j['pos'] or '–')}** ({equipo['nombre']}) · #{j['camiseta']}"]
        if j["edad"] is not None:
            nac = j["nacimiento"]
            if nac:
                nac = f" ({nac[8:10]}.{nac[5:7]}.{nac[:4]})"
            lineas.append(f"**Edad:** {j['edad']}{nac}")
        altura = f"{j['altura_cm']} cm" if j["altura_cm"] else j["altura"]
        lineas.append(f"**Altura:** {altura}")
        c2.markdown("  \n".join(lineas))
        c3.image(equipo["escudo"], use_container_width=True)
    if j["lesion"]:
        st.warning(f"🩹 Estado: {j['lesion']}")

    a, b, c, d, e = st.columns(5)
    a.metric("Altura", j["altura"])
    b.metric("Peso", j["peso"])
    c.metric("Edad", j["edad"] if j["edad"] is not None else "–")
    d.metric("Años en la NBA", j["exp"] if j["exp"] is not None else "–")
    e.metric("Universidad", j["universidad"])

    with st.spinner("Cargando estadísticas..."):
        tablas = _estadisticas(jugador_id)
        recientes = _ultimos_partidos(jugador_id)
    if not tablas:
        st.info("ESPN no tiene estadísticas para este jugador todavía (por ejemplo, si es novato o recién llegó).")
        return

    temporada, p = _promedios_actuales(tablas)
    if p:
        st.subheader(f"Temporada {temporada} · promedios por partido")
        principales = [("PTS", "Puntos"), ("REB", "Rebotes"), ("AST", "Asistencias"), ("STL", "Robos"),
                       ("BLK", "Tapones"), ("TO", "Pérdidas"), ("MIN", "Minutos"), ("GP", "Partidos")]
        for fila in (principales[:4], principales[4:]):
            for col, (k, nombre) in zip(st.columns(4), fila):
                col.metric(nombre, p.get(k, "–"))
        st.markdown("##### Tiros")
        tiros = [("FG", "FG%", "Tiros de campo"), ("3PT", "3P%", "Triples"), ("FT", "FT%", "Tiros libres")]
        for col, (hechos, pct, nombre) in zip(st.columns(3), tiros):
            valor = p.get(hechos, "–")
            col.metric(nombre, f"{p.get(pct, '–')}%" if p.get(pct) not in (None, "–") else "–",
                       help=f"Encestados-intentados por partido: {valor}")
            col.caption(f"Encestados-intentados por partido: {valor}")

    nombres = list(tablas) + (["Últimos partidos"] if len(recientes) else [])
    for pestana, nombre in zip(st.tabs(nombres), nombres):
        with pestana:
            if nombre == "Últimos partidos":
                st.dataframe(recientes.head(15), hide_index=True, use_container_width=True)
                if "PTS" in recientes.columns:
                    graf = recientes.head(10).iloc[::-1].copy()
                    graf["PTS"] = pd.to_numeric(graf["PTS"], errors="coerce")
                    st.caption("Puntos en los últimos 10 partidos (del más antiguo al más reciente)")
                    st.bar_chart(graf.set_index("Fecha")["PTS"])
            else:
                st.dataframe(tablas[nombre].iloc[::-1].reset_index(drop=True), hide_index=True,
                             use_container_width=True)


def render():
    st.session_state.setdefault("eq_equipo", None)
    st.session_state.setdefault("eq_jugador", None)

    equipo_id = st.session_state["eq_equipo"]
    if equipo_id is None:
        _pantalla_escudos()
        return
    equipo = next((e for e in _equipos() if e["id"] == equipo_id), None)
    if equipo is None:
        _volver_a_equipos()
        _pantalla_escudos()
        return
    if st.session_state["eq_jugador"] is None:
        _pantalla_plantel(equipo)
    else:
        _pantalla_jugador(equipo, st.session_state["eq_jugador"])
