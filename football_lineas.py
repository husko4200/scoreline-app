"""Fútbol · Líneas: el mismo cuadro que la NBA (escudos, tarjetas con una barra por partido, comparativa y líneas con racha).

Reutiliza las tarjetas y los cálculos de ficha_equipos.py (NBA), así que se ven y se calculan igual.
Datos: los partidos de la liga ya cargada (football-data.co.uk, `liga.t`). Escudos: ESPN, cruzados por nombre; si un
equipo no aparece allí, se dibuja una insignia con sus iniciales.

Se usa desde football.py:  football_lineas.render(liga, comparativa)
"""
import base64
import requests
from urllib.parse import quote
import difflib
import math
import re
import zlib
from concurrent.futures import ThreadPoolExecutor
from html import escape as _e
from statistics import mean, median

import pandas as pd
import streamlit as st

import estilos
import confederaciones
import ficha_equipos as fe
import football_recientes as fr
import football_tarjeta
import selecciones
from common import get_json, normalizar

# ---------------------------------------------------------------------------
# Mercados (un Mercado por entrada; ficha_equipos._tarjeta decide tipo de tarjeta, textos y colores)
# ---------------------------------------------------------------------------
_O = fe.Mercado
_TIEMPO = {1: "1.er", 2: "2.º"}

def _sino(clave, tag, grande, verbo, ayuda):
    """Mercado de sí/no (como «Ambos anotan» en las casas de apuestas). Cada barra vale +1 si se cumplió y −1 si no."""
    return fe.Mercado(clave, "ganador", tag=tag, grande=grande, verbo=verbo,
                      ayuda=f"{ayuda} Cada barra vale +1 si se cumplió y −1 si no (verde = se cumplió).")


def _mas(clave, que):
    """Mercado «más X que el rival»: la barra es la diferencia contra el rival (verde = tuvo más)."""
    return fe.Mercado(clave, "ganador", tag=f"MÁS {que.upper()}", grande="Más", verbo=f"Tuvo más {que} que el rival en", ayuda=(
        f"Mide cuántas veces el equipo tuvo más {que} que su rival (verde = tuvo más; un empate no cuenta). "
        "El número de cada barra es la diferencia contra el rival."))


MERCADOS_F = {
    "⚽ Goles": {
        "Total de goles del partido (más/menos)": _O("total"),
        "Goles del equipo (más/menos)": _O("pf"),
        "Goles del rival (más/menos)": _O("pc"),
        **{f"Goles del partido en el {o} tiempo (más/menos)": _O(f"t{k}") for k, o in _TIEMPO.items()},
        **{f"Goles del equipo en el {o} tiempo (más/menos)": _O(f"p{k}") for k, o in _TIEMPO.items()},
        **{f"Goles del rival en el {o} tiempo (más/menos)": _O(f"pc{k}") for k, o in _TIEMPO.items()},
        "Ambos anotan: Sí": _sino("btts_si", "AMBOS ANOTAN", "Sí", "Ambos anotaron en", "Mide cuántas veces los dos equipos anotaron al menos un gol."),
        "Ambos anotan: No": _sino("btts_no", "AMBOS ANOTAN", "No", "Alguno no anotó en", "Mide cuántas veces al menos uno de los dos equipos se quedó sin anotar."),
        "El equipo anota (+0.5 gol)": _sino("anota", "EL EQUIPO ANOTA", "+0.5", "Anotó al menos 1 gol en", "Mide cuántas veces el equipo anotó al menos un gol."),
        "El rival anota (+0.5 gol)": _sino("rival_anota", "EL RIVAL ANOTA", "+0.5", "El rival anotó en", "Mide cuántas veces el rival anotó al menos un gol contra el equipo."),
        "Portería a cero (el rival no anota)": _sino("porteria_cero", "PORTERÍA A CERO", "Sí", "Dejó la portería a cero en", "Mide cuántas veces el equipo no recibió goles."),
        "Gana sin recibir gol": _sino("gana_cero", "GANA A CERO", "Sí", "Ganó sin recibir gol en", "Mide cuántas veces el equipo ganó y además dejó su portería a cero."),
        "Total de goles impar": _sino("impar", "GOLES TOTALES", "Impar", "Total impar en", "Mide cuántas veces el total de goles del partido fue impar (1, 3, 5...)."),
        "Total de goles par": _sino("par", "GOLES TOTALES", "Par", "Total par en", "Mide cuántas veces el total de goles del partido fue par (0, 2, 4...)."),
        "Hay goles (no termina 0-0)": _sino("hay_gol", "HAY GOLES", "Sí", "Hubo goles en", "Mide cuántas veces el partido NO terminó 0-0."),
        "Hay gol en el 1.er tiempo": _sino("hay_gol_1t", "GOL 1.er T", "Sí", "Hubo gol en el 1.er tiempo en", "Mide cuántas veces el 1.er tiempo NO terminó 0-0."),
        "Hay gol en el 2.º tiempo": _sino("hay_gol_2t", "GOL 2.º T", "Sí", "Hubo gol en el 2.º tiempo en", "Mide cuántas veces hubo al menos un gol en el 2.º tiempo."),
    },
    "🆚 Resultado": {
        "Gana el equipo (1X2)": fe.Mercado("ganador", "ganador", dato="margen", ayuda=(
            "Mide cuántas veces ganó el equipo (verde = victoria; un empate no cuenta como victoria). "
            "«En casa» y «De visita» muestran su récord según la sede. El número de cada barra es la diferencia de goles.")),
        "Empata (X)": _sino("empate", "EMPATE", "Sí", "Empató en", "Mide cuántas veces el partido terminó empatado."),
        "Pierde el equipo": _sino("pierde", "DERROTA", "Sí", "Perdió en", "Mide cuántas veces el equipo perdió."),
        "Doble oportunidad: gana o empata (no pierde)": _sino("no_pierde", "NO PIERDE", "1X", "No perdió en", "Mide cuántas veces el equipo ganó o empató."),
        "Doble oportunidad: gana o pierde (sin empate)": _sino("no_empata", "SIN EMPATE", "12", "No empató en", "Mide cuántas veces el partido tuvo ganador (sin empate)."),
        "Gana por 2 o más goles": _sino("gana_2", "GANA POR 2+", "Sí", "Ganó por 2 o más goles en", "Mide cuántas veces el equipo ganó con una diferencia de 2 goles o más."),
        "Gana por 1 gol exacto": _sino("gana_1", "GANA POR 1", "Sí", "Ganó por un solo gol en", "Mide cuántas veces el equipo ganó por exactamente 1 gol."),
        "Pierde por 2 o más goles": _sino("pierde_2", "PIERDE POR 2+", "Sí", "Perdió por 2 o más goles en", "Mide cuántas veces el equipo perdió con una diferencia de 2 goles o más."),
        "Hándicap de goles": fe.Mercado("margen", "handicap", rango=6.0),
    },
    "⏱️ Tiempos": {
        **{f"Total de goles del {o} tiempo": _O(f"t{k}") for k, o in _TIEMPO.items()},
        **{f"Goles del equipo en el {o} tiempo": _O(f"p{k}") for k, o in _TIEMPO.items()},
        **{f"Goles del rival en el {o} tiempo": _O(f"pc{k}") for k, o in _TIEMPO.items()},
        **{f"Ganador del {o} tiempo": fe._ganar_periodo(f"g{k}", "tiempo") for k, o in _TIEMPO.items()},
        **{f"Hándicap del {o} tiempo": fe.Mercado(f"hg{k}", "handicap", dato=f"g{k}", rango=3.0) for k, o in _TIEMPO.items()},
        "Empata el 1.er tiempo": _sino("empate_1t", "EMPATE 1.er T", "Sí", "Empató el 1.er tiempo en", "Mide cuántas veces el 1.er tiempo terminó empatado."),
        "Ambos anotan en el 1.er tiempo": _sino("btts_1t", "AMBOS ANOTAN 1.er T", "Sí", "Ambos anotaron en el 1.er tiempo en", "Mide cuántas veces los dos anotaron antes del descanso."),
        "Ambos anotan en el 2.º tiempo": _sino("btts_2t", "AMBOS ANOTAN 2.º T", "Sí", "Ambos anotaron en el 2.º tiempo en", "Mide cuántas veces los dos anotaron en el 2.º tiempo."),
        "Más goles en el 2.º tiempo que en el 1.º": _sino("mas_goles_2t", "MITAD CON MÁS GOLES", "2.º T", "Hubo más goles en el 2.º tiempo en", "Mide cuántas veces el 2.º tiempo tuvo más goles que el 1.º (empate = no)."),
        "Más goles en el 1.er tiempo que en el 2.º": _sino("mas_goles_1t", "MITAD CON MÁS GOLES", "1.er T", "Hubo más goles en el 1.er tiempo en", "Mide cuántas veces el 1.er tiempo tuvo más goles que el 2.º (empate = no)."),
        "El equipo anota en ambos tiempos": _sino("anota_ambos_t", "ANOTA EN AMBOS T", "Sí", "Anotó en los dos tiempos en", "Mide cuántas veces el equipo anotó en el 1.º y en el 2.º tiempo."),
        "El equipo gana ambos tiempos": _sino("gana_ambos_t", "GANA AMBOS T", "Sí", "Ganó los dos tiempos en", "Mide cuántas veces el equipo ganó el 1.º y el 2.º tiempo."),
        "El equipo anota en el 1.er tiempo (+0.5 gol)": _sino("anota_1t", "ANOTA 1.er T", "+0.5", "Anotó en el 1.er tiempo en", "Mide cuántas veces el equipo anotó antes del descanso."),
        "El equipo anota en el 2.º tiempo (+0.5 gol)": _sino("anota_2t", "ANOTA 2.º T", "+0.5", "Anotó en el 2.º tiempo en", "Mide cuántas veces el equipo anotó después del descanso."),
        "Hay gol en el 1.er tiempo": _sino("hay_gol_1t", "GOL 1.er T", "Sí", "Hubo gol en el 1.er tiempo en", "Mide cuántas veces el 1.er tiempo NO terminó 0-0."),
        "Hay gol en el 2.º tiempo": _sino("hay_gol_2t", "GOL 2.º T", "Sí", "Hubo gol en el 2.º tiempo en", "Mide cuántas veces hubo al menos un gol en el 2.º tiempo."),
        "Gana al descanso y gana el partido": _sino("ht_ft", "DESCANSO/FINAL", "G/G", "Ganó al descanso y al final en", "Mide cuántas veces el equipo iba ganando al descanso y terminó ganando."),
        "Pierde al descanso y remonta (gana)": _sino("remonta", "REMONTADA", "Sí", "Remontó (perdía al descanso y ganó) en", "Mide cuántas veces el equipo perdía al descanso y terminó ganando."),
        "Gana al descanso y no gana el partido": _sino("pierde_ventaja", "PIERDE LA VENTAJA", "Sí", "Perdió la ventaja del descanso en", "Mide cuántas veces el equipo iba ganando al descanso y terminó empatando o perdiendo."),
    },
    "🎯 Tiros y córners": {
        "Tiros del equipo": _O("tiros"), "Tiros del rival": _O("tiros_riv"), "Tiros totales del partido": _O("tiros_tot"),
        "Tiros a puerta del equipo": _O("tp"), "Tiros a puerta del rival": _O("tp_riv"), "Tiros a puerta totales del partido": _O("tp_tot"),
        "Córners del equipo": _O("corners"), "Córners del rival": _O("corners_riv"), "Córners totales del partido": _O("corners_tot"),
        "Tiros fuera de puerta del equipo": _O("tf"), "Tiros fuera de puerta del rival": _O("tf_riv"),
        "Tiros fuera de puerta totales del partido": _O("tf_tot"),
        "Más córners que el rival": _mas("corners_m", "córners"),
        "Más tiros que el rival": _mas("tiros_m", "tiros"),
        "Más tiros a puerta que el rival": _mas("tp_m", "tiros a puerta"),
        "Hándicap de córners": fe.Mercado("hc_corners", "handicap", dato="corners_m", rango=8.0),
        "Hándicap de tiros a puerta": fe.Mercado("hc_tp", "handicap", dato="tp_m", rango=6.0),
        "Hándicap de tiros": fe.Mercado("hc_tiros", "handicap", dato="tiros_m", rango=12.0),
    },
    "🟨 Disciplina": {
        "Faltas del equipo": _O("faltas"), "Faltas del rival": _O("faltas_riv"), "Faltas totales del partido": _O("faltas_tot"),
        "Tarjetas amarillas del equipo": _O("amarillas"), "Tarjetas amarillas del rival": _O("amarillas_riv"),
        "Tarjetas amarillas totales del partido": _O("amarillas_tot"),
        "Tarjetas rojas del equipo": _O("rojas"), "Tarjetas rojas del rival": _O("rojas_riv"),
        "Tarjetas rojas totales del partido": _O("rojas_tot"),
        "Tarjetas (amarillas + rojas) del equipo": _O("tarjetas"), "Tarjetas (amarillas + rojas) del rival": _O("tarjetas_riv"),
        "Tarjetas (amarillas + rojas) totales del partido": _O("tarjetas_tot"),
        "Más faltas que el rival": _mas("faltas_m", "faltas"),
        "Más tarjetas amarillas que el rival": _mas("amarillas_m", "tarjetas amarillas"),
        "Hándicap de faltas": fe.Mercado("hc_faltas", "handicap", dato="faltas_m", rango=10.0),
        "Hay tarjeta roja en el partido": _sino("rojas_partido", "TARJETA ROJA", "Sí", "Hubo roja en", "Mide cuántas veces se mostró al menos una tarjeta roja en el partido."),
        "Puntos de tarjetas del equipo (amarilla 10, roja 25)": _O("pts_tarj"),
        "Puntos de tarjetas del partido (amarilla 10, roja 25)": _O("pts_tarj_tot"),
    },
}
MERCADOS = {nombre: m for grupo in MERCADOS_F.values() for nombre, m in grupo.items()}
GRUPOS_SELECCIONES = ("⚽ Goles", "🆚 Resultado")   # las selecciones solo traen el marcador final (sin tiempos, tiros ni córners)
TOP_ELO = 32                                         # escudos de la pestaña «Mejores por Elo»; las demás se ven por región o en la búsqueda
MEJORES = "⭐ Mejores por Elo"

# (nombre, clave, ¿del partido entero? True = una sola línea para los dos equipos; False = una por equipo)
MERCADOS_RACHA = [("Total de goles", "total", True), ("Goles", "pf", False), ("Córners", "corners", False),
                  ("Tiros", "tiros", False), ("Tiros a puerta", "tp", False), ("Córners totales", "corners_tot", True),
                  ("Faltas", "faltas", False), ("Tarjetas amarillas", "amarillas", False)]

# Columna de la tabla por equipo (liga.t) que alimenta cada dato de la tarjeta
CAMPOS = {"pf": "GF", "pc": "GC", "total": "Total", "margen": "Margen", "tiros": "Tiros", "tiros_riv": "TirosRival", "tp": "TP",
          "tp_riv": "TPRival", "corners": "Corners", "corners_riv": "CornersRival", "corners_tot": "CornersTotal",
          "faltas": "Faltas", "amarillas": "Amarillas", "rojas": "Rojas", "t1": "Goles1T", "t2": "Goles2T",
          "faltas_riv": "FaltasRival", "amarillas_riv": "AmarillasRival", "rojas_riv": "RojasRival"}


# ---------------------------------------------------------------------------
# Equipos y escudos
# ---------------------------------------------------------------------------
ESPN_LIGA = {
    "Premier League (Inglaterra)": "eng.1", "La Liga (España)": "esp.1", "Bundesliga (Alemania)": "ger.1", "Serie A (Italia)": "ita.1",
    "Ligue 1 (Francia)": "fra.1", "Eredivisie (Países Bajos)": "ned.1", "Primeira Liga (Portugal)": "por.1",
    "Premiership (Escocia)": "sco.1", "Championship (Inglaterra, 2ª)": "eng.2", "Segunda División (España)": "esp.2",
    "2. Bundesliga (Alemania)": "ger.2", "Serie B (Italia)": "ita.2", "Ligue 2 (Francia)": "fra.2", "Pro League (Bélgica)": "bel.1",
    "Süper Lig (Turquía)": "tur.1", "Super League (Grecia)": "gre.1", "Liga Argentina": "arg.1", "Brasileirão (Brasil)": "bra.1",
    "MLS (EE.UU.)": "usa.1", "Liga MX (México)": "mex.1",
}
ESPN_EQUIPOS = "https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/teams"

# Nombres de football-data.co.uk (normalizados) que ESPN escribe distinto
ALIAS = {
    "man united": "manchester united", "man city": "manchester city", "nottm forest": "nottingham forest",
    "tottenham": "tottenham hotspur", "wolves": "wolverhampton wanderers", "newcastle": "newcastle united",
    "west ham": "west ham united", "brighton": "brighton and hove albion", "leeds": "leeds united", "leicester": "leicester city",
    "norwich": "norwich city", "west brom": "west bromwich albion", "qpr": "queens park rangers", "hull": "hull city",
    "stoke": "stoke city", "swansea": "swansea city", "cardiff": "cardiff city", "birmingham": "birmingham city",
    "derby": "derby county", "preston": "preston north end", "sheffield weds": "sheffield wednesday", "oxford": "oxford united",
    "luton": "luton town", "ath madrid": "atletico madrid", "ath bilbao": "athletic club", "betis": "real betis",
    "sociedad": "real sociedad", "vallecano": "rayo vallecano", "espanol": "espanyol", "celta": "celta vigo",
    "mgladbach": "borussia monchengladbach", "ein frankfurt": "eintracht frankfurt", "leverkusen": "bayer leverkusen",
    "dortmund": "borussia dortmund", "fc koln": "koln", "hertha": "hertha berlin", "hoffenheim": "tsg hoffenheim",
    "wolfsburg": "vfl wolfsburg", "bochum": "vfl bochum", "stuttgart": "vfb stuttgart", "freiburg": "sc freiburg",
    "inter": "internazionale", "milan": "ac milan", "paris sg": "paris saint germain", "st etienne": "saint etienne",
    "sp lisbon": "sporting cp", "sp braga": "braga", "porto": "fc porto", "psv": "psv eindhoven", "az": "az alkmaar",
    "nijmegen": "nec nijmegen", "zwolle": "pec zwolle", "waalwijk": "rkc waalwijk", "sittard": "fortuna sittard",
}
UMBRAL_NOMBRE = 0.78

# Segunda división de cada liga: ESPN solo lista los equipos de la temporada actual, así que los que descendieron
# (o ascendieron) se buscan también aquí.
LIGA_VECINA = {"eng.1": ["eng.2"], "esp.1": ["esp.2"], "ger.1": ["ger.2"], "ita.1": ["ita.2"], "fra.1": ["fra.2"],
               "eng.2": ["eng.1"], "esp.2": ["esp.1"], "ger.2": ["ger.1"], "ita.2": ["ita.1"], "fra.2": ["fra.1"]}

# Escudos fijos por nombre (el de football-data.co.uk, normalizado) -> (abreviatura, id del equipo en ESPN).
# Sirve de respaldo cuando ESPN no devuelve el equipo. Para añadir otro: busca su id en espn.com y agrégalo aquí.
ESCUDO_FIJO = {"west ham": ("WHU", 371), "burnley": ("BUR", 379), "wolves": ("WOL", 380)}
URL_ESCUDO = "https://a.espncdn.com/i/teamlogos/soccer/500/{id}.png"
PALETA_INSIGNIA = ["#1d4ed8", "#b91c1c", "#15803d", "#a16207", "#7e22ce", "#0e7490", "#be185d", "#374151"]


def _n(s):
    return normalizar(s).replace("'", "")


def _puntaje(a, b):
    """Parecido entre dos nombres ya normalizados (0-1). «man united» encaja con «manchester united»."""
    if a == b:
        return 1.0
    ta, tb = a.split(), b.split()
    if ta and all(any(y.startswith(x) for y in tb) for x in ta):
        return 0.92
    if tb and all(any(x.startswith(y) for x in ta) for y in tb):
        return 0.85
    return difflib.SequenceMatcher(None, a, b).ratio()


def _emparejar(nombres, espn):
    """{nombre de football-data: equipo de ESPN}. Cada equipo de ESPN se usa una sola vez (gana el mejor parecido)."""
    pares = []
    for nombre in nombres:
        n = _n(nombre)
        n = ALIAS.get(n, n)
        for i, e in enumerate(espn):
            mejor = max((_puntaje(n, _n(x)) for x in e["nombres"] if x), default=0.0)
            if mejor >= UMBRAL_NOMBRE:
                pares.append((mejor, nombre, i))
    pares.sort(reverse=True)
    res, usados = {}, set()
    for _, nombre, i in pares:
        if nombre not in res and i not in usados:
            res[nombre] = espn[i]
            usados.add(i)
    return res


@st.cache_data(ttl=86400, show_spinner=False)
def _equipos_espn(liga):
    """Equipos de una liga de ESPN. Si falla LANZA error, así Streamlit no guarda un resultado vacío en caché."""
    js = get_json(ESPN_EQUIPOS.format(liga=liga), params={"limit": 100})
    out = []
    for t in js["sports"][0]["leagues"][0]["teams"]:
        t = t.get("team", t)
        logos = t.get("logos") or []
        out.append({"nombres": [t.get(k) for k in ("displayName", "shortDisplayName", "name", "location")],
                    "abbr": t.get("abbreviation", ""), "espn_id": t.get("id"), "logo": logos[0].get("href", "") if logos else "",
                    "color": t.get("color"), "alternateColor": t.get("alternateColor")})
    if not out:
        raise RuntimeError("ESPN no devolvió equipos")
    return out


def _insignia(nombre, color):
    """Escudo de reemplazo: círculo de color con las iniciales (para equipos sin escudo en ESPN)."""
    ini = "".join(w[0] for w in re.findall(r"[^\W_]+", nombre)[:3]).upper() or "?"
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="48" fill="' + color + '"/>'
           '<text x="50" y="62" font-family="Arial,sans-serif" font-size="34" font-weight="700" text-anchor="middle" fill="#fff">'
           + _e(ini) + "</text></svg>")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


@st.cache_data(ttl=3600, show_spinner=False)
def _equipos_liga(nombres, liga_espn):
    """Lista de equipos [{id, nombre, abbr, logo, color}] con escudo de ESPN cuando se encuentra (si no, insignia)."""
    espn = []
    for codigo in ([liga_espn] + LIGA_VECINA.get(liga_espn, [])) if liga_espn else []:
        try:
            espn += _equipos_espn(codigo)
        except Exception:  # noqa: BLE001
            continue
    asignado = _emparejar(nombres, espn)
    out, vistos = [], set()
    for nombre in nombres:
        e = asignado.get(nombre)
        ident = re.sub(r"[^a-z0-9]", "", _n(nombre)) or "eq"
        while ident in vistos:
            ident += "x"
        vistos.add(ident)
        base = PALETA_INSIGNIA[zlib.crc32(nombre.encode()) % len(PALETA_INSIGNIA)]
        color = fe._color_equipo(e) if e else "#16a34a"
        logo = (e or {}).get("logo") or _insignia(nombre, base)
        abbr = (e or {}).get("abbr") or _n(nombre)[:3].upper()
        espn_id = (e or {}).get("espn_id")
        fijo = ESCUDO_FIJO.get(_n(nombre))
        if fijo:   # escudo fijo: manda sobre lo que devuelva ESPN
            abbr, logo, espn_id = fijo[0], URL_ESCUDO.format(id=fijo[1]), fijo[1]
        out.append({"id": ident, "nombre": nombre, "abbr": abbr, "logo": logo, "color": color, "espn_id": espn_id})
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def _equipos_selecciones(nombres):
    """Selecciones nacionales [{id, nombre, abbr, logo, color}] con su bandera (si no está en la tabla, insignia)."""
    out, vistos = [], set()
    for nombre in nombres:
        ident = re.sub(r"[^a-z0-9]", "", _n(nombre)) or "eq"
        while ident in vistos:
            ident += "x"
        vistos.add(ident)
        base = PALETA_INSIGNIA[zlib.crc32(nombre.encode()) % len(PALETA_INSIGNIA)]
        out.append({"id": ident, "nombre": nombre, "abbr": selecciones.codigo(nombre) or _n(nombre)[:3].upper(),
                    "logo": selecciones.bandera(nombre) or _insignia(nombre, base), "color": "#16a34a"})
    return out


def _elegir_otro(clave, widget, ids, regiones=None):
    """Callback de «Buscar otro país»: lo elegido pasa a ser el Equipo A o B (igual que tocar su escudo)."""
    nombre = st.session_state.get(widget)
    if not nombre or nombre == "—":
        return
    if clave == "fe_b" and ids[nombre] == st.session_state.get("fe_a"):
        return   # A y B no pueden ser el mismo equipo
    fe._elegir(clave, ids[nombre])
    if regiones and nombre in regiones:   # la región mostrada pasa a ser la del país elegido
        st.session_state["ff_conf_" + clave[-1]] = regiones[nombre]


def _css_escudos(equipos):
    """Igual que ficha_equipos._css_escudos, pero también acepta las insignias (data:image/svg+xml)."""
    reglas = []
    for e in equipos:
        url = str(e.get("logo", ""))
        if not (url.startswith("https://") or url.startswith("data:image/svg+xml;base64,")) or any(c in url for c in "\"'()<> "):
            continue
        for lado in ("a", "b"):
            reglas.append(f'.st-key-fe_{lado}_{e["id"]} button[data-testid^="stBaseButton"] {{ background-image: url("{url}") !important; }}')
    return "<style>" + estilos.css("escudos") + "\n".join(reglas) + "</style>"


# ---------------------------------------------------------------------------
# Series de partidos
# ---------------------------------------------------------------------------
def _de_sede(d, sede):
    """Filtra por sede: «Local» o «Visita» (sin los partidos en cancha neutral). Sin sede devuelve todo."""
    if not sede or d.empty:
        return d
    neutral = d["Neutral"].fillna(False).astype(bool) if "Neutral" in d.columns else False
    return d[(d.Condicion == sede) & ~neutral]


def _ventana(t, equipo, n, rival=None, sede=None):
    """Últimos n partidos del equipo (opcionalmente solo contra `rival` y/o solo de local o de visita), del más antiguo al más reciente."""
    d = t[t.Equipo == equipo]
    if rival:
        d = d[d.Rival == rival]
    return _de_sede(d, sede).sort_values("Date").tail(n)


def _recientes(t, eq, n, liga_espn, sede=None):
    """Últimos n partidos del equipo en TODAS las competiciones (ESPN). Si ESPN no responde o trae menos de n,
    completa (o reemplaza) con los partidos de liga de football-data. Devuelve (DataFrame, ¿se usó ESPN?)."""
    base = _ventana(t, eq["nombre"], n, sede=sede)
    try:
        d = fr.ultimos(eq.get("espn_id"), eq["nombre"], n, liga_espn, sede)
    except Exception:  # noqa: BLE001
        d = pd.DataFrame()
    if d.empty:
        return base, False
    if len(d) < n:   # ESPN trae pocos: se completan con partidos de liga anteriores al primero de ESPN
        antes = _de_sede(t[(t.Equipo == eq["nombre"]) & (t.Date < d.Date.min())], sede).sort_values("Date").tail(n - len(d))
        d = pd.concat([antes, d], ignore_index=True)
    return d.tail(n), True


def _derivados(r):
    """Datos que no son una columna de la tabla: los sí/no (+1 se cumplió, −1 no) y las sumas y diferencias contra el rival."""
    def v(c):
        x = r.get(c)
        return None if x is None or pd.isna(x) else float(x)

    sn = lambda cond: 1.0 if cond else -1.0   # noqa: E731
    gf, gc = v("GF"), v("GC")
    d = {}
    if gf is not None and gc is not None:
        d.update({"btts_si": sn(gf > 0 and gc > 0), "btts_no": sn(not (gf > 0 and gc > 0)), "anota": sn(gf > 0), "rival_anota": sn(gc > 0),
                  "porteria_cero": sn(gc == 0), "gana_cero": sn(gf > gc and gc == 0), "impar": sn((gf + gc) % 2 == 1),
                  "par": sn((gf + gc) % 2 == 0), "empate": sn(gf == gc), "pierde": sn(gf < gc), "no_pierde": sn(gf >= gc),
                  "no_empata": sn(gf != gc), "gana_2": sn(gf - gc >= 2), "gana_1": sn(gf - gc == 1),
                  "pierde_2": sn(gc - gf >= 2), "hay_gol": sn(gf + gc > 0)})
        gf1, gc1 = v("GF1T"), v("GC1T")
        if gf1 is not None and gc1 is not None:
            gf2, gc2 = gf - gf1, gc - gc1
            d.update({"empate_1t": sn(gf1 == gc1), "btts_1t": sn(gf1 > 0 and gc1 > 0), "btts_2t": sn(gf2 > 0 and gc2 > 0),
                      "mas_goles_2t": sn(gf2 + gc2 > gf1 + gc1), "mas_goles_1t": sn(gf1 + gc1 > gf2 + gc2),
                      "anota_ambos_t": sn(gf1 > 0 and gf2 > 0), "gana_ambos_t": sn(gf1 > gc1 and gf2 > gc2),
                      "pc1": gc1, "pc2": gc2, "anota_1t": sn(gf1 > 0), "anota_2t": sn(gf2 > 0),
                      "hay_gol_1t": sn(gf1 + gc1 > 0), "hay_gol_2t": sn(gf2 + gc2 > 0),
                      "ht_ft": sn(gf1 > gc1 and gf > gc), "remonta": sn(gf1 < gc1 and gf > gc),
                      "pierde_ventaja": sn(gf1 > gc1 and gf <= gc)})
    for clave, (a, b) in {"tiros": ("Tiros", "TirosRival"), "tp": ("TP", "TPRival"), "corners": ("Corners", "CornersRival"),
                          "faltas": ("Faltas", "FaltasRival"), "amarillas": ("Amarillas", "AmarillasRival")}.items():
        x, y = v(a), v(b)
        if x is not None and y is not None:
            d[f"{clave}_tot"] = x + y
            if clave in ("tiros", "tp", "corners", "faltas", "amarillas"):
                d[f"{clave}_m"] = x - y
    ti, tp_, ti_r, tp_r = v("Tiros"), v("TP"), v("TirosRival"), v("TPRival")   # tiros fuera de puerta = tiros − tiros a puerta
    if ti is not None and tp_ is not None:
        d["tf"] = max(ti - tp_, 0.0)
    if ti_r is not None and tp_r is not None:
        d["tf_riv"] = max(ti_r - tp_r, 0.0)
    if "tf" in d and "tf_riv" in d:
        d["tf_tot"] = d["tf"] + d["tf_riv"]
    ya, yr, ra, rr = v("Amarillas"), v("AmarillasRival"), v("Rojas"), v("RojasRival")
    if ya is not None and ra is not None:
        d["tarjetas"] = ya + ra
    if yr is not None and rr is not None:
        d["tarjetas_riv"] = yr + rr
    if "tarjetas" in d and "tarjetas_riv" in d:
        d["tarjetas_tot"] = d["tarjetas"] + d["tarjetas_riv"]
    if ra is not None and rr is not None:
        d["rojas_tot"] = ra + rr
    if ya is not None and ra is not None:
        d["pts_tarj"] = 10 * ya + 25 * ra
        if yr is not None and rr is not None:
            d["pts_tarj_tot"] = 10 * (ya + yr) + 25 * (ra + rr)
    if ra is not None and rr is not None:
        d["rojas_partido"] = sn(ra + rr > 0)
    return d


def _serie(d, abbr):
    """Convierte la ventana (DataFrame) en la lista de partidos que entienden las tarjetas de ficha_equipos."""
    out = []
    for r in d.to_dict("records"):
        ra = r.get("RivalAbbr")
        ra = ra if isinstance(ra, str) and ra else abbr.get(r["Rival"], r["Rival"][:3].upper())
        local = r["Condicion"] == "Local"
        neutral = bool(r.get("Neutral"))   # cancha neutral (selecciones): ni local ni visita
        g = {"fecha": r["Date"].isoformat(), "dia": r["Date"].date(), "rival": r["Rival"], "ot": False,
             "sede": "neutral" if neutral else "home" if local else "away",
             "rival_abbr": ra,
             "etq": f'{"vs" if local or neutral else "@"} {ra}'}
        datos = {k: r.get(col) for k, col in CAMPOS.items()}
        datos.update(_derivados(r))
        gf1, gc1 = r.get("GF1T"), r.get("GC1T")
        if pd.notna(gf1) and pd.notna(gc1):
            datos["p1"], datos["g1"] = gf1, gf1 - gc1
            datos["p2"], datos["g2"] = r["GF"] - gf1, (r["GF"] - gf1) - (r["GC"] - gc1)
        for k, v in datos.items():
            if pd.notna(v):
                g[k] = fe._limpio(float(v))
        g["pf"], g["pc"] = int(r["GF"]), int(r["GC"])
        desc = r.get("Descanso")
        g["desc"] = None if pd.isna(desc) else int(desc)
        out.append(g)
    return out


# ---------------------------------------------------------------------------
# Líneas con racha del cruce
# ---------------------------------------------------------------------------
def _picks_racha(a, b, ra, rb, ha, hb, minimo):
    """(proyección, línea central del total, DataFrame de líneas con racha). Misma lógica que la NBA, con mercados de fútbol."""
    filas = []
    for nombre, clave, partido in MERCADOS_RACHA:
        if partido:
            grupos = [(nombre, [fe._valores(ra, clave), fe._valores(rb, clave)], fe._valores(ha, clave))]
        else:
            grupos = [(f'{nombre} {x["abbr"] or x["nombre"]}', [fe._valores(r, clave)], fe._valores(h, clave))
                      for x, r, h in ((a, ra, ha), (b, rb, hb))]
        for etq, series, vh in grupos:
            series = [s for s in series if s]
            if not series:
                continue
            esperado = mean([v for s in series for v in s])
            if len(vh) >= 2:
                esperado = (esperado + mean(vh)) / 2
            for lado in ("Más de", "Menos de"):
                r = fe._mejor_linea(series, vh, lado, minimo)
                if not r:
                    continue
                filas.append({"Mercado": etq, "Apuesta": lado, "Línea": r["L"],
                              "Recientes": f'{r["kr"]}/{r["nr"]} · {round(100 * r["hr"])}%',
                              "Cara a cara": "sin cruces" if r["hh"] is None else f'{r["kh"]}/{r["nh"]} · {round(100 * r["hh"])}%',
                              "Racha actual": r["racha"], "Esperado": round(esperado, 1),
                              "Holgura": round(abs(esperado - r["L"]), 1),
                              "_score": (r["hr"] + (r["hh"] if r["hh"] is not None else r["hr"])) / 2})
    df = pd.DataFrame(filas)
    if not df.empty:
        df = df.sort_values(["_score", "Racha actual", "Holgura"], ascending=[False, False, True]).drop(columns="_score").reset_index(drop=True)
    proy = fe._proyeccion(ra, rb, ha)
    central = None
    tot = [fe._valores(ra, "total"), fe._valores(rb, "total")]
    if proy and all(tot):
        central = fe._medio(proy["total"] if proy["h2h"] is None else (proy["total"] + proy["h2h"]) / 2)
        central = (central, *fe._inclinacion(tot, fe._valores(ha, "total"), central))
    return proy, central, df


def _seccion_racha(eq_a, eq_b, ra, rb, ha, hb):
    st.markdown("#### 🔥 Líneas con racha del cruce")
    minimo = st.slider("Mínimo de cumplimiento", 60, 100, 80, 5, format="%d%%", key="ff_racha_min",
                       help="Busca la línea más exigente que cumplieron al menos este % de las veces, tanto en los partidos "
                            "recientes como en los enfrentamientos directos.") / 100
    proy, central, df = _picks_racha(eq_a, eq_b, ra, rb, ha, hb, minimo)
    if proy:
        c1, c2, c3 = st.columns(3)
        c1.metric(f"{eq_a['abbr']} esperado", f"{proy['a']:.1f} goles", help="Promedio entre lo que anota y lo que recibe el rival.")
        c2.metric(f"{eq_b['abbr']} esperado", f"{proy['b']:.1f} goles")
        c3.metric("Total esperado", f"{proy['total']:.1f} goles",
                  None if proy["h2h"] is None else f"cara a cara: {proy['h2h']:.1f}", delta_color="off")
    if central:
        linea, mas, menos = central
        lean = "Más de" if mas >= 60 and mas > menos else "Menos de" if menos >= 60 and menos > mas else None
        txt = f"**Línea central {linea:g}:** Más de {mas}% · Menos de {menos}% (recientes y cara a cara mezclados). "
        st.markdown(txt + (f"👉 Inclinación: **{lean}**." if lean else "Sin ventaja clara: está parejo."))
    if df.empty:
        st.info(f"Ninguna línea llega al {round(minimo * 100)}% en recientes y cara a cara a la vez. Baja el mínimo o cambia la ventana.")
        return
    st.dataframe(df, hide_index=True, use_container_width=True, column_config={
        "Línea": st.column_config.NumberColumn(format="%.1f"),
        "Racha actual": st.column_config.NumberColumn(help="Partidos seguidos cumpliéndola, desde el más reciente (el menor de los dos equipos en el total)."),
        "Esperado": st.column_config.NumberColumn(help="Promedio del mercado (recientes y cara a cara)."),
        "Holgura": st.column_config.NumberColumn(help="Distancia entre la línea y el promedio: más holgura = más margen de seguridad.")})
    st.caption("Son líneas históricas «seguras» (las más exigentes que se cumplieron con esa frecuencia). "
               "No es una predicción ni garantiza el resultado.")


# ---------------------------------------------------------------------------
# Autoanálisis: qué líneas cumple cada equipo y si también las cumplieron sus rivales
# ---------------------------------------------------------------------------
# dato del equipo -> el mismo dato pero del rival en esos mismos partidos
_CONTRARIO = {"pf": "pc", "tiros": "tiros_riv", "tp": "tp_riv", "tf": "tf_riv", "corners": "corners_riv", "faltas": "faltas_riv",
              "amarillas": "amarillas_riv", "rojas": "rojas_riv", "tarjetas": "tarjetas_riv", "p1": "pc1", "p2": "pc2",
              "anota": "rival_anota"}
_DEL_PARTIDO = {"total", "t1", "t2", "pts_tarj_tot"}   # además de todo lo que termina en «_tot»: una sola línea para los dos equipos
_NO_TOP = {"btts_no", "par", "pierde"}                 # complementarios de otro mercado: no se repiten en las tarjetas «mejores líneas»
_AUTO_CSS = """<style>
.fa-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin:8px 0 14px}
.fa-card{position:relative;background:#fff;color:#1f2a24;border:1px solid #dbe5de;border-radius:16px;padding:14px 14px 12px;overflow:hidden;
  box-shadow:0 1px 2px rgba(16,40,28,.06),0 8px 24px -12px rgba(16,40,28,.25);animation:faUp .55s cubic-bezier(.2,.7,.2,1) backwards;
  animation-delay:var(--d,0ms);transition:transform .25s ease,box-shadow .25s ease,border-color .25s ease}
.fa-card:hover{transform:translateY(-4px);border-color:#16a34a;box-shadow:0 18px 34px -14px rgba(16,40,28,.4)}
.fa-card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--c,#16a34a)}
.fa-top{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;margin-bottom:6px}
.fa-who{padding:2px 8px;border-radius:999px;color:#fff;font-size:11px;font-weight:700}
.fa-mk{font-size:13px;opacity:.8;line-height:1.25}
.fa-pick{font-size:17px;font-weight:800;margin:3px 0 6px;line-height:1.15}
.fa-pct{font-size:26px;font-weight:800;line-height:1;color:#15803d}
.fa-sub{font-size:11px;opacity:.75;margin-top:4px}
.fa-bar{height:7px;border-radius:5px;background:#e6ede8;margin-top:8px;overflow:hidden}
.fa-bar i{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,#16a34a,#0f6b32);transform-origin:left;animation:faGrow .9s cubic-bezier(.2,.7,.2,1) .2s both}
.fa-riv{display:inline-block;margin-top:6px;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700}
.fa-ok{background:#dcfce7;color:#166534}.fa-mal{background:#fef3c7;color:#92400e}.fa-na{background:#e5e7eb;color:#374151}
.fa-ver{display:flex;align-items:center;gap:12px;background:#fff;color:#1f2a24;border:1px solid #dbe5de;border-radius:16px;padding:14px 16px;margin:6px 0 12px;
  box-shadow:0 8px 24px -14px rgba(16,40,28,.3);animation:faUp .5s ease backwards}
.fa-ver b{font-size:18px}
.st-key-ff_auto_btn button,.st-key-ff_auto_off button{background:linear-gradient(135deg,#15803d,#0f6b32) !important;color:#fff !important;border:0 !important;
  border-radius:12px !important;font-weight:700;box-shadow:0 8px 18px -8px rgba(15,107,50,.8);transition:transform .18s ease,filter .18s ease,box-shadow .18s ease}
.st-key-ff_auto_btn button:hover,.st-key-ff_auto_off button:hover{transform:translateY(-2px);filter:brightness(1.08)}
.st-key-ff_auto_btn button:active,.st-key-ff_auto_off button:active{transform:scale(.96)}
@keyframes faUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes faGrow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@media (prefers-reduced-motion:reduce){*{animation:none !important;transition:none !important}}
</style>"""


def _color_eq(nombre):
    return PALETA_INSIGNIA[zlib.crc32(nombre.encode()) % len(PALETA_INSIGNIA)]


def _pred(tipo, lado, linea):
    """La condición de «cumplir» según el tipo de mercado: Más/Menos de una línea, o Sí/No (un dato > 0 se cumplió)."""
    if tipo == "linea":
        return (lambda x: x > linea) if lado == "Más de" else (lambda x: x < linea)
    return (lambda x: x > 0) if lado == "Sí" else (lambda x: x <= 0)


def _mejor_lado_f(v, h, tipo, linea):
    """Mejor lado de un equipo en esa línea. La puntuación está suavizada (3/3 no vale más que 17/20) y mezcla recientes y cruces."""
    lados = ("Más de", "Menos de") if tipo == "linea" else ("Sí", "No")
    mejor = None
    for lado in lados:
        ok = _pred(tipo, lado, linea)
        k = sum(ok(x) for x in v)
        sr = (k + 1) / (len(v) + 2)
        kh = sum(ok(x) for x in h)
        sh = (kh + 1) / (len(h) + 2) if len(h) >= 2 else None
        c = {"lado": lado, "linea": linea, "k": k, "n": len(v), "pct": k / len(v), "kh": kh, "nh": len(h),
             "hpct": kh / len(h) if len(h) >= 2 else None, "score": sr if sh is None else (sr + sh) / 2, "ok": ok}
        if mejor is None or c["score"] > mejor["score"]:
            mejor = c
    return mejor


def _contra(p, serie, clave):
    """¿Cumplieron lo mismo los rivales de ese equipo en esos partidos? (mismo lado y misma línea). None si el mercado no tiene versión del rival."""
    cont = _CONTRARIO.get(clave)
    if not cont:
        return None
    vr = fe._valores(serie, cont)
    if len(vr) < 3:
        return None
    k = sum(p["ok"](x) for x in vr)
    return {"k": k, "n": len(vr), "pct": k / len(vr)}


def _auto_filas(grupos, sa, sb, ha, hb, minimo=3):
    """Una fila por línea (mercado). Con sb=None es el análisis individual de un equipo; con sb compara a los dos."""
    filas = []
    for grupo, mercados in grupos.items():
        for nombre, m in mercados.items():
            if m.tipo == "handicap":
                continue   # los hándicaps ya los cubren «Gana el equipo» y los «más X que el rival»
            clave = m.campo
            va = fe._valores(sa, clave)
            vb = fe._valores(sb, clave) if sb is not None else None
            if len(va) < minimo or (vb is not None and len(vb) < minimo):
                continue
            partido = clave in _DEL_PARTIDO or clave.endswith("_tot")
            tipo = "sino" if m.tipo == "ganador" else "linea"   # «ganador» = sí/no (dato > 0 se cumplió); lo demás, más/menos de una línea
            if tipo == "sino":
                la = lb = None
            elif partido and vb is not None:
                la = lb = max(0.5, fe._medio((mean(va) + mean(vb)) / 2))
            else:
                la = max(0.5, fe._medio(mean(va)))
                lb = max(0.5, fe._medio(mean(vb))) if vb is not None else None
            pa = _mejor_lado_f(va, fe._valores(ha, clave) if ha else [], tipo, la)
            pa["riv"] = _contra(pa, sa, clave)
            fila = {"grupo": grupo, "mercado": nombre, "clave": clave, "pa": pa, "ganador": None}
            if vb is not None:
                pb = _mejor_lado_f(vb, fe._valores(hb, clave) if hb else [], tipo, lb)
                pb["riv"] = _contra(pb, sb, clave)
                dif = pa["score"] - pb["score"]
                fila.update({"pb": pb, "ganador": "A" if dif > 0.05 else "B" if dif < -0.05 else "="})
            filas.append(fila)
    return filas


def _txt_pick(p):
    return p["lado"] if p["linea"] is None else f"{p['lado']} {p['linea']:g}"


def _txt_k(p):
    return f"{p['k']}/{p['n']}" + ("" if p["hpct"] is None else f" · cruces {p['kh']}/{p['nh']}")


def _veredicto(p):
    """Individual: ¿el equipo la cumple y los rivales no?"""
    riv = p.get("riv")
    if p["pct"] < 0.7:
        return "➖ Sin ventaja clara"
    if riv is None:
        return "✅ La cumple (sin dato del rival)"
    if riv["pct"] < 0.5:
        return "✅ La cumple y sus rivales NO"
    return "⚠️ La cumple, pero sus rivales también"


def _tarjetas_top(candidatos, color_de):
    medallas = ["🥇", "🥈", "🥉", "④", "⑤", "⑥"]
    out = []
    for i, (nombre_eq, merc, p) in enumerate(candidatos):
        pct = round(100 * p["pct"])
        riv = p.get("riv")
        if riv is None:
            chip = '<span class="fa-riv fa-na">Rivales: sin dato</span>'
        else:
            rp = round(100 * riv["pct"])
            chip = f'<span class="fa-riv {"fa-ok" if riv["pct"] < 0.5 else "fa-mal"}">Rivales en esos partidos: {rp}% ({riv["k"]}/{riv["n"]})</span>'
        out.append(
            f'<div class="fa-card" style="--c:{color_de(nombre_eq)};--d:{i * 70}ms"><div class="fa-top"><span style="font-size:18px">{medallas[i]}</span>'
            f'<span class="fa-who" style="background:{color_de(nombre_eq)}">{_e(nombre_eq)}</span></div>'
            f'<div class="fa-mk">{_e(merc)}</div><div class="fa-pick">{_e(_txt_pick(p))}</div>'
            f'<div class="fa-pct">{pct}%</div><div class="fa-sub">{_e(_txt_k(p))}</div>'
            f'<div class="fa-bar"><i style="width:{pct}%"></i></div>{chip}</div>')
    return '<div class="fa-grid">' + "".join(out) + "</div>"


def _top(filas, lados):
    """Las 6 mejores líneas (equipo, mercado, pick) por puntuación, una por equipo y mercado."""
    cand = [(f[l]["score"], f[l]["n"], nom, f["mercado"], f[l]) for f in filas if f["clave"] not in _NO_TOP for l, nom in lados]
    cand.sort(key=lambda t: (-t[0], -t[1]))
    vistos, top = set(), []
    for _s, _n, nom, merc, p in cand:
        if (nom, merc) in vistos:
            continue
        vistos.add((nom, merc))
        top.append((nom, merc, p))
        if len(top) == 6:
            break
    return top


def _autoanalisis_ui(eq_a, eq_b, grupos, sa, sb, ha, hb, base_txt):
    filas = _auto_filas(grupos, sa, sb, ha, hb)
    if not filas:
        st.info("No hay datos suficientes (mínimo 3 partidos con ese dato) para el autoanálisis. Prueba con otra sede o más partidos.")
        return
    na = eq_a["nombre"]
    ca = _color_eq(na)
    st.markdown(_AUTO_CSS, unsafe_allow_html=True)
    if eq_b is None:
        # ---------- Individual: el equipo y sus rivales ----------
        fuertes = [f for f in filas if f["pa"]["pct"] >= 0.7]
        solo = [f for f in fuertes if f["pa"].get("riv") and f["pa"]["riv"]["pct"] < 0.5]
        st.markdown(f'<div class="fa-ver"><span style="font-size:26px">📊</span><div><b><span style="color:{ca}">{_e(na)}</span> cumple '
                    f'{len(fuertes)} de {len(filas)} líneas con 70% o más</b><br><span style="font-size:12px;opacity:.75">'
                    f'En {len(solo)} de ellas sus rivales no la cumplieron (menos de 50%) · base: {base_txt}</span></div></div>', unsafe_allow_html=True)
        st.markdown("**Mejores líneas del equipo y qué hicieron sus rivales**")
        st.markdown(_tarjetas_top(_top(filas, [("pa", na)]), lambda _n: ca), unsafe_allow_html=True)
        tabla = []
        for f in filas:
            p, riv = f["pa"], f["pa"].get("riv")
            tabla.append({"Tipo": f["grupo"], "Línea (mercado)": f["mercado"], "Apuesta": _txt_pick(p), f"{na} (partidos)": _txt_k(p),
                          f"{na} %": round(100 * p["pct"]), "Rivales %": None if riv is None else round(100 * riv["pct"]),
                          "Veredicto": _veredicto(p)})
        st.markdown("**Línea por línea**")
        st.dataframe(pd.DataFrame(tabla), hide_index=True, use_container_width=True, column_config={
            f"{na} %": st.column_config.ProgressColumn(f"{na} %", min_value=0, max_value=100, format="%d%%"),
            "Rivales %": st.column_config.ProgressColumn("Rivales %", min_value=0, max_value=100, format="%d%%",
                                                         help="Cuántas veces sus rivales cumplieron la MISMA línea y lado en esos mismos partidos.")})
        st.caption("«Rivales %» mide el mismo dato pero del rival de cada partido (por ejemplo, los córners que sacaron los rivales de este equipo). "
                   "Solo existe para mercados con versión del rival: goles, tiros, córners, faltas y tarjetas. "
                   "Son frecuencias históricas, no una predicción.")
        return

    # ---------- Dos equipos: quién tiene las mejores estadísticas en cada línea ----------
    nb = eq_b["nombre"]
    cb = _color_eq(nb)
    ga, gb = sum(f["ganador"] == "A" for f in filas), sum(f["ganador"] == "B" for f in filas)
    if ga == gb:
        ver = f"Parejo: {ga} líneas para cada uno"
    else:
        lider, c, g = (na, ca, ga) if ga > gb else (nb, cb, gb)
        ver = f'Mejores estadísticas: <span style="color:{c}">{_e(lider)}</span> en {g} de {len(filas)} líneas'
    st.markdown(f'<div class="fa-ver"><span style="font-size:26px">🏆</span><div><b>{ver}</b><br><span style="font-size:12px;opacity:.75">'
                f'{_e(na)}: {ga} · {_e(nb)}: {gb} · parejo: {len(filas) - ga - gb} · base: {base_txt}</span></div></div>', unsafe_allow_html=True)
    st.markdown("**Mejores líneas de los dos equipos**")
    st.markdown(_tarjetas_top(_top(filas, [("pa", na), ("pb", nb)]), lambda n: ca if n == na else cb), unsafe_allow_html=True)
    tabla = []
    for f in filas:
        pa, pb = f["pa"], f["pb"]
        ra, rb = pa.get("riv"), pb.get("riv")
        tabla.append({"Tipo": f["grupo"], "Línea (mercado)": f["mercado"],
                      na: f"{_txt_pick(pa)} ({_txt_k(pa)})", f"{na} %": round(100 * pa["pct"]), f"Rivales de {na} %": None if ra is None else round(100 * ra["pct"]),
                      nb: f"{_txt_pick(pb)} ({_txt_k(pb)})", f"{nb} %": round(100 * pb["pct"]), f"Rivales de {nb} %": None if rb is None else round(100 * rb["pct"]),
                      "Mejor estadística": f"🏆 {na}" if f["ganador"] == "A" else f"🏆 {nb}" if f["ganador"] == "B" else "🤝 Parejo"})
    pc = lambda t: st.column_config.ProgressColumn(t, min_value=0, max_value=100, format="%d%%")   # noqa: E731
    st.markdown("**Línea por línea**")
    st.dataframe(pd.DataFrame(tabla), hide_index=True, use_container_width=True, column_config={
        f"{na} %": pc(f"{na} %"), f"{nb} %": pc(f"{nb} %"), f"Rivales de {na} %": pc(f"Rivales de {na} %"), f"Rivales de {nb} %": pc(f"Rivales de {nb} %")})
    st.caption("Para cada línea se toma la apuesta (Más/Menos o Sí/No) que mejor le funcionó a cada equipo y se compara. La puntuación mezcla sus partidos "
               "recientes y los cruces entre ambos, y penaliza las muestras pequeñas; «Parejo» = diferencia menor a 5 puntos. «Rivales de X %» es cuántas veces "
               "los rivales de X cumplieron esa misma línea contra él. Son frecuencias históricas, no una predicción.")


def _boton_auto(eq_a, eq_b, grupos, sa, sb, h2h, ventana, recientes, sede_a, sede_b, t, abbr):
    par = (eq_a["id"], eq_b["id"] if eq_b else None)
    b1, b2, _ = st.columns([2, 1, 3])
    texto = "🤖 Autoanálisis de todas las líneas" if eq_b else "🤖 Autoanálisis del equipo y sus rivales"
    if b1.button(texto, key="ff_auto_btn", use_container_width=True,
                 help="Revisa todas las líneas: si el equipo las cumple y si también las cumplieron sus rivales."
                      + (" Con dos equipos, además dice quién tiene las mejores estadísticas en cada línea." if eq_b else "")):
        st.session_state["ff_auto_par"] = par
    if st.session_state.get("ff_auto_par") == par and b2.button("✖ Ocultar", key="ff_auto_off", use_container_width=True):
        st.session_state["ff_auto_par"] = None
    if st.session_state.get("ff_auto_par") != par:
        return
    with st.spinner("Analizando todas las líneas..."):
        if eq_b is None:
            ra, rb, ha, hb = sa, None, None, None
            base = f"últimos {ventana} partidos"
        else:
            n_rec = ventana if isinstance(ventana, int) else 10
            ra = sa if not h2h else _serie(recientes(eq_a, n_rec, sede_a), abbr)
            rb = sb if not h2h else _serie(recientes(eq_b, n_rec, sede_b), abbr)
            ha = sa if h2h else _serie(_ventana(t, eq_a["nombre"], 25, eq_b["nombre"]), abbr)
            hb = sb if h2h else _serie(_ventana(t, eq_b["nombre"], 25, eq_a["nombre"]), abbr)
            base = f"últimos {n_rec} partidos de cada uno + cruces"
    st.markdown("#### 🤖 Autoanálisis")
    _autoanalisis_ui(eq_a, eq_b, grupos, ra, rb, ha, hb, base)


# ---------------------------------------------------------------------------
# Modo jugador: estadísticas de UN jugador (ESPN, partido a partido) y cómo le fue contra el rival
# ---------------------------------------------------------------------------
ESPN_AGENDA = "https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/teams/{id}/schedule"
ESPN_RESUMEN = "https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/summary"
MAX_PJ = 30   # partidos de liga que se cargan por equipo (un resumen de ESPN por partido)

# clave -> (nombres posibles del dato en ESPN, etiqueta)
_STATS_J = {"tiros": (("totalShots", "shotsTotal", "shots"), "Tiros"), "tp": (("shotsOnTarget", "shotsOnGoal"), "Tiros a puerta"),
            "goles": (("totalGoals", "goals"), "Goles"), "asist": (("goalAssists", "assists"), "Asistencias"),
            "faltas": (("foulsCommitted", "fouls"), "Faltas cometidas"), "faltas_rec": (("foulsSuffered",), "Faltas recibidas"),
            "amarillas": (("yellowCards",), "Tarjetas amarillas"), "rojas": (("redCards",), "Tarjetas rojas"),
            "paradas": (("saves",), "Paradas"), "fuera_juego": (("offsides",), "Fueras de juego"),
            "goles_rec": (("goalsConceded",), "Goles recibidos")}
# nombre del mercado -> (clave, tipo, solo porteros / solo jugadores de campo / ambos)
MERCADOS_J = {
    "Tiros del jugador": ("tiros", "linea", "campo"), "Tiros a puerta del jugador": ("tp", "linea", "campo"),
    "Goles del jugador": ("goles", "linea", "campo"), "Asistencias del jugador": ("asist", "linea", "campo"),
    "Goles + asistencias": ("ga", "linea", "campo"), "Anota gol (+0.5)": ("gol_si", "sino", "campo"),
    "Anota o asiste": ("ga_si", "sino", "campo"), "Faltas cometidas": ("faltas", "linea", "todos"),
    "Faltas recibidas": ("faltas_rec", "linea", "todos"), "Tarjetas amarillas": ("amarillas", "linea", "todos"),
    "Recibe tarjeta (amarilla o roja)": ("tarjeta_si", "sino", "todos"), "Fueras de juego": ("fuera_juego", "linea", "campo"),
    "Paradas del portero": ("paradas", "linea", "portero"), "Goles recibidos (portero)": ("goles_rec", "linea", "portero")}
_ETQ_J = {c: e for c, (_n_, e) in _STATS_J.items()} | {"ga": "Goles + asistencias", "gol_si": "Anota gol", "ga_si": "Anota o asiste", "tarjeta_si": "Recibe tarjeta"}
_JUG_CSS = """<style>
.fj{background:#fff;color:#1f2a24;border:1px solid #dbe5de;border-radius:16px;padding:14px 14px 12px;height:100%;
  box-shadow:0 1px 2px rgba(16,40,28,.06),0 8px 24px -12px rgba(16,40,28,.25);animation:faUp .55s cubic-bezier(.2,.7,.2,1) backwards;
  transition:transform .25s ease,box-shadow .25s ease,border-color .25s ease}
.fj:hover{transform:translateY(-3px);border-color:#16a34a;box-shadow:0 18px 34px -14px rgba(16,40,28,.4)}
.fj-t{font-size:12px;font-weight:700;opacity:.75;margin-bottom:2px}
.fj-n{font-size:16px;font-weight:800;line-height:1.15}
.fj-pct{font-size:28px;font-weight:800;line-height:1.1;margin:6px 0 0}
.fj-sub{font-size:12px;opacity:.75;margin-bottom:8px}
.fj-bars{position:relative;display:flex;align-items:flex-end;gap:4px;height:100px;border-bottom:1px solid rgba(128,128,128,.5);overflow-x:auto;padding-top:14px}
.fj-c{flex:1 0 22px;max-width:44px;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;font-size:10px;height:100%}
.fj-b{width:70%;border-radius:5px 5px 0 0;transform-origin:bottom;animation:fjBar .6s cubic-bezier(.2,.7,.2,1) backwards;animation-delay:var(--d,0ms);transition:filter .2s,transform .2s}
.fj-c:hover .fj-b{filter:brightness(1.12);transform:scaleX(1.12)}
.fj-v{font-weight:700;margin-bottom:2px}
.fj-ln{position:absolute;left:0;right:0;border-top:2px dashed rgba(60,60,60,.7);pointer-events:none}
.fj-o{display:flex;gap:4px;margin-top:3px}
.fj-o span{flex:1 0 22px;max-width:44px;text-align:center;font-size:9px;opacity:.65;white-space:nowrap}
</style>"""


_FONDO_CSS = """<style>
/* ---- botones y controles sólidos en área principal (sin afectar sidebar ScoreLine) ---- */
[data-testid="stMain"] [data-testid="stRadio"] div[role="radiogroup"]{background:#fff !important;border:1px solid #cfe3d3 !important;box-shadow:0 2px 8px rgba(16,40,28,.08)}
[data-testid="stMain"] [data-testid="stRadio"] label{background:#fff}
[data-testid="stMain"] [data-testid="stRadio"] label:has(input:checked){background:linear-gradient(135deg,#16a34a,#166534) !important;color:#fff !important}
[data-testid="stMain"] [data-testid="stRadio"] label:has(input:checked) *{color:#fff !important}
[data-testid="stMain"] .stButton>button,[data-testid="stMain"] [data-testid="stBaseButton-secondary"]{background:#fff !important;border:1px solid #cfe3d3 !important}
[data-testid="stMain"] .stButton>button:hover{border-color:#16a34a !important;color:#166534 !important}
[data-testid="stMain"] [data-baseweb="select"]>div,[data-testid="stMain"] [data-baseweb="input"],[data-testid="stMain"] [data-testid="stNumberInput"] [data-baseweb="input"]>div,[data-testid="stMain"] [data-baseweb="base-input"]{background:#fff !important}
[data-testid="stMain"] [data-testid="stExpander"] details{background:#fff !important}
/* ---- tarjeta del jugador con su cara ---- */
.fj-card{display:flex;gap:18px;align-items:center;flex-wrap:wrap;background:#fff;border:1px solid #cfe3d3;border-radius:20px;padding:16px 20px;
  box-shadow:0 10px 28px -14px rgba(16,40,28,.45);animation:faUp .5s cubic-bezier(.2,.7,.2,1) backwards;margin:6px 0 14px}
.fj-av{position:relative;flex:0 0 auto;width:104px;height:104px;border-radius:50%;overflow:hidden;background:radial-gradient(circle at 50% 30%,#fff,var(--c,#16a34a));
  border:4px solid var(--c,#16a34a);box-shadow:0 6px 16px -6px rgba(0,0,0,.4)}
.fj-av img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:top}
.fj-info{flex:1 1 240px;min-width:0}
.fj-nom{font-size:26px;font-weight:800;line-height:1.1;color:#14231a}
.fj-eq{display:flex;align-items:center;gap:8px;margin-top:6px;font-size:14px;color:#3c4a42}
.fj-eq img{width:26px;height:26px;object-fit:contain}
.fj-chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.fj-chip{background:#ecf7ee;border:1px solid #cfe3d3;border-radius:999px;padding:4px 12px;font-size:12px;font-weight:700;color:#166534}
.fj-chip b{font-size:15px;margin-right:4px}
.fj-mini{text-align:center;font-size:11px;line-height:1.2;color:#1f2a24;margin-top:4px;min-height:28px}
.fj-mini-av{position:relative;width:64px;height:64px;margin:0 auto;border-radius:50%;overflow:hidden;background:radial-gradient(circle at 50% 30%,#fff,#bfe3c8);border:3px solid #16a34a}
.fj-mini-av img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:top}
</style>"""


def fondo_futbol():
    """Fondo general de cancha animada + botones sólidos. Se inyecta una vez por pantalla de Fútbol (ver football.render)."""
    pelotas = "".join(f'<span class="fj-pelota" style="bottom:{b}px;--t:{t}s;--r:-{r}s"><i>⚽</i></span>'
                      for b, t, r in ((14, 26, 0), (58, 34, 11), (30, 42, 23)))
    st.markdown(_FONDO_CSS + '<div class="fj-cancha"><div class="medio"></div><div class="centro"></div>'
                '<div class="area i"></div><div class="area d"></div>' + pelotas + "</div>", unsafe_allow_html=True)


_UA = {"User-Agent": "Mozilla/5.0 (futbol-app)"}


def _es_imagen(url):
    """True si la URL responde 200 con una imagen (la foto de ESPN no existe para todos los jugadores)."""
    try:
        r = requests.get(url, headers=_UA, timeout=6, stream=True)
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("image")
        r.close()
        return ok
    except Exception:  # noqa: BLE001
        return False


def _foto_wikipedia(nombre):
    """Foto del jugador en Wikipedia (inglés y español), solo si la página es de un futbolista. '' si no hay."""
    for idioma in ("en", "es"):
        for titulo in (nombre, f"{nombre} (footballer)", f"{nombre} (futbolista)"):
            try:
                r = requests.get(f"https://{idioma}.wikipedia.org/api/rest_v1/page/summary/{quote(titulo.replace(' ', '_'), safe='')}",
                                 headers=_UA, timeout=6)
                if r.status_code != 200:
                    continue
                js = r.json()
                txt = f"{js.get('description') or ''} {js.get('extract') or ''}".lower()
                if js.get("type") == "disambiguation" or not any(k in txt for k in ("footballer", "soccer", "futbolista", "fútbol", "goalkeeper")):
                    continue
                foto = (js.get("thumbnail") or js.get("originalimage") or {}).get("source")
                if foto:
                    return foto
            except Exception:  # noqa: BLE001
                continue
    return ""


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def _foto_jugador(nombre, foto_espn):
    """Primera foto que exista: la de ESPN o, si no está, la de Wikipedia. '' si no hay ninguna."""
    if foto_espn and _es_imagen(foto_espn):
        return foto_espn
    return _foto_wikipedia(nombre)


@st.cache_data(ttl=86400, show_spinner=False)
def _fotos_equipo(pares):
    """{jid: url} de las fotos de ESPN que sí existen para una lista de (jid, url) (se comprueban en paralelo)."""
    with ThreadPoolExecutor(max_workers=10) as pool:
        ok = list(pool.map(lambda p: _es_imagen(p[1]) if p[1] else False, pares))
    return {jid: url for (jid, url), v in zip(pares, ok) if v}


def _avatar(nombre, equipo):
    return _insignia(nombre, PALETA_INSIGNIA[zlib.crc32(equipo.encode()) % len(PALETA_INSIGNIA)])


def _tarjeta_jugador(jug, dj):
    """Cabecera con la cara del jugador, su escudo y un resumen de los partidos cargados."""
    color = PALETA_INSIGNIA[zlib.crc32(jug["equipo"].encode()) % len(PALETA_INSIGNIA)]
    pj, tit = dj.evento.nunique(), int(dj.titular.sum()) if len(dj) else 0
    goles, asist = (int(dj.goles.sum()), int(dj.asist.sum())) if len(dj) else (0, 0)
    chips = "".join(f'<span class="fj-chip"><b>{v}</b>{_e(t)}</span>' for v, t in ((pj, "partidos"), (tit, "de titular"), (goles, "goles"), (asist, "asistencias")))
    logo = f'<img src="{_e(jug["logo"])}" alt="">' if jug.get("logo") else ""
    foto = _foto_jugador(jug["nombre"], jug["foto"]) or _avatar(jug["nombre"], jug["equipo"])   # sin foto en ningún sitio: iniciales
    st.markdown(f'<div class="fj-card"><div class="fj-av" style="--c:{color}"><img src="{_e(foto)}" alt="" referrerpolicy="no-referrer"></div>'
                f'<div class="fj-info"><div class="fj-nom">{_e(jug["nombre"])}</div>'
                f'<div class="fj-eq">{logo}<span>{_e(jug["equipo"])} · {_e(jug["liga_n"])}{" · " + _e(jug["pos"]) if jug["pos"] else ""}</span></div>'
                f'<div class="fj-chips">{chips}<span class="fj-chip">últimos {MAX_PJ} de liga</span></div></div></div>', unsafe_allow_html=True)


def _ir_a_jugador(i):
    st.session_state["ff_jug_mundo"] = i


def _compañeros(mundo, sel):
    """Caras de la plantilla del mismo equipo; con «Ver» se salta a ese jugador."""
    jug = mundo[sel]
    otros = [i for i, j in enumerate(mundo) if j["team_id"] == jug["team_id"] and j["liga"] == jug["liga"]][:30]
    with st.expander(f"👥 Plantilla de {jug['equipo']} ({len(otros)})"):
        fotos = _fotos_equipo(tuple((mundo[i]["jid"], mundo[i]["foto"]) for i in otros))
        for fila in range(0, len(otros), 6):
            for col, i in zip(st.columns(6), otros[fila:fila + 6]):
                j = mundo[i]
                foto = fotos.get(j["jid"]) or _avatar(j["nombre"], j["equipo"])
                col.markdown(f'<div class="fj-mini-av"><img src="{_e(foto)}" alt="" referrerpolicy="no-referrer"></div>'
                             f'<div class="fj-mini">{_e(j["nombre"])}<br><span style="opacity:.6">{_e(j["pos"] or "—")}</span></div>', unsafe_allow_html=True)
                col.button("Ver", key=f"ff_ver_{i}", on_click=_ir_a_jugador, args=(i,), use_container_width=True, disabled=i == sel)


def _grupo_pos(pos):
    """Posición de ESPN (G, CD-L, LB, CM, AM, RF...) -> portero / defensa / medio / delantero. None si es suplente o no se sabe."""
    p = (pos or "").upper().strip()
    if not p or p in ("SUB", "S"):
        return None
    if p == "G" or p.startswith("GK"):
        return "Portero"
    if p.startswith("CD") or p.endswith("B") or p in ("D", "SW", "WB"):
        return "Defensa"
    if "M" in p:
        return "Medio"
    return "Delantero"


def _numero(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _stats_dict(lista):
    if isinstance(lista, dict):
        return {k: _numero(v) for k, v in lista.items() if _numero(v) is not None}
    d = {}
    for s in lista or []:
        if isinstance(s, dict) and s.get("name") is not None:
            v = _numero(s.get("value", s.get("displayValue")))
            if v is not None:
                d[s["name"]] = v
    return d


def _parse_resumen(js):
    """{id del equipo: [jugadores que jugaron con sus estadísticas]} a partir del resumen de un partido de ESPN."""
    out = {}
    for ro in (js or {}).get("rosters") or []:
        tid = str((ro.get("team") or {}).get("id", ""))
        jug = []
        for p in ro.get("roster") or []:
            at = p.get("athlete") or {}
            if not at.get("id"):
                continue
            s = _stats_dict(p.get("stats"))
            pos = (p.get("position") or {}).get("abbreviation") or (at.get("position") or {}).get("abbreviation") or ""
            titular = bool(p.get("starter"))
            jugo = titular or bool(p.get("subbedIn")) or (s.get("appearances") or 0) > 0
            if jugo:
                jug.append({"id": str(at["id"]), "nombre": at.get("displayName") or at.get("shortName") or "?", "pos": pos, "titular": titular, "stats": s})
        out[tid] = jug
    return out


def _puntos(x):
    sc = x.get("score") if isinstance(x, dict) else x
    if isinstance(sc, dict):
        sc = sc.get("value", sc.get("displayValue"))
    return _numero(sc)


def _agenda_equipo(liga, team_id):
    """Últimos partidos terminados del equipo en esa liga (la temporada actual y, si faltan, la anterior). Sin caché: lo usa _cargar_jugadores."""
    eventos, vistos, temporada = [], set(), None
    for intento in range(2):
        params = {} if intento == 0 else {"season": (temporada or 0) - 1}
        if intento and not temporada:
            break
        js = get_json(ESPN_AGENDA.format(liga=liga, id=team_id), params=params)
        if intento == 0:
            try:
                temporada = int((js.get("requestedSeason") or js.get("season") or {}).get("year"))
            except (TypeError, ValueError):
                temporada = None
        for ev in js.get("events") or []:
            comp = (ev.get("competitions") or [{}])[0]
            tipo = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
            if not tipo.get("completed") or ev.get("id") in vistos:
                continue
            comps = comp.get("competitors") or []
            yo = next((c for c in comps if str((c.get("team") or {}).get("id")) == str(team_id)), None)
            otro = next((c for c in comps if c is not yo), None)
            if not yo or not otro:
                continue
            vistos.add(ev.get("id"))
            eq = otro.get("team") or {}
            eventos.append({"id": ev.get("id"), "fecha": pd.to_datetime(ev.get("date"), errors="coerce", utc=True), "local": yo.get("homeAway") == "home",
                            "opp_id": str(eq.get("id")), "opp": eq.get("displayName") or eq.get("name") or "?", "opp_abbr": eq.get("abbreviation") or "",
                            "gf": _puntos(yo), "gc": _puntos(otro)})
        if len(eventos) >= MAX_PJ:
            break
    eventos.sort(key=lambda e: (e["fecha"] is pd.NaT, e["fecha"]))
    return eventos[-MAX_PJ:]


@st.cache_data(ttl=3600, show_spinner=False)
def _cargar_jugadores(liga, team_id):
    """DataFrame con una fila por jugador y partido (los del equipo: propio=True; los rivales de esos partidos: propio=False) + diagnóstico.
    Si ESPN no responde LANZA error, así Streamlit no guarda un resultado vacío en caché."""
    eventos = _agenda_equipo(liga, team_id)
    if not eventos:
        raise RuntimeError("ESPN no devolvió partidos terminados de este equipo en la liga")

    def uno(e):
        try:
            return e, _parse_resumen(get_json(ESPN_RESUMEN.format(liga=liga), params={"event": e["id"]}))
        except Exception as ex:  # noqa: BLE001
            return e, str(ex)[:80]

    with ThreadPoolExecutor(max_workers=8) as pool:
        res = list(pool.map(uno, eventos))
    filas, ok, fallos, nombres = [], 0, [], set()
    for e, ros in res:
        if not isinstance(ros, dict) or not ros:
            fallos.append(ros if isinstance(ros, str) else "sin alineaciones")
            continue
        ok += 1
        for tid, jug in ros.items():
            for p in jug:
                s = p["stats"]
                nombres.update(s)
                v = {}
                for k, (nom, _etq) in _STATS_J.items():
                    v[k] = next((s[n] for n in nom if n in s), 0.0)
                v["ga"] = v["goles"] + v["asist"]
                v["gol_si"] = 1.0 if v["goles"] > 0 else -1.0
                v["ga_si"] = 1.0 if v["ga"] > 0 else -1.0
                v["tarjeta_si"] = 1.0 if v["amarillas"] + v["rojas"] > 0 else -1.0
                filas.append({"fecha": e["fecha"], "evento": e["id"], "propio": tid == str(team_id), "opp_id": e["opp_id"], "opp": e["opp"],
                              "opp_abbr": e["opp_abbr"] or e["opp"][:3].upper(), "local": e["local"], "jid": p["id"], "jugador": p["nombre"],
                              "pos": p["pos"], "grupo": _grupo_pos(p["pos"]), "titular": p["titular"], **v})
    if not filas:
        raise RuntimeError(f"ESPN no trajo estadísticas por jugador ({len(eventos)} partidos; fallos: {'; '.join(sorted(set(fallos)))[:200] or 'sin datos'})")
    diag = {"partidos": len(eventos), "resumenes_ok": ok, "filas": len(filas), "datos_espn": sorted(nombres)[:40], "fallos": sorted(set(fallos))[:3]}
    return pd.DataFrame(filas), diag


def _vals(d, clave):
    return [float(x) for x in d[clave].tolist()] if len(d) else []


def _tasa(ok, v):
    return (sum(ok(x) for x in v) / len(v)) if v else None


def _plantilla(df):
    """Jugadores del equipo con sus partidos jugados, el más usado primero: [(id, etiqueta)]."""
    p = df[df.propio]
    g = p.groupby("jid").agg(nombre=("jugador", "last"), pj=("evento", "nunique"), tit=("titular", "sum"), fecha=("fecha", "max"))
    pos = p[p.grupo.notna()].groupby("jid")["pos"].agg(lambda s: s.mode().iat[0])
    g = g.join(pos.rename("pos")).fillna({"pos": ""}).sort_values(["tit", "pj", "fecha"], ascending=False)
    return [(i, f"{r.nombre} · {r.pos or '—'} · {int(r.pj)} PJ ({int(r.tit)} de titular)") for i, r in g.iterrows()]


def _barras_j(valores, opps, linea, ok, tipo):
    alto = 86
    vmax = max([abs(v) for v in valores] + [linea or 0, 1.0])
    celdas, etq = [], []
    for i, (v, o) in enumerate(zip(valores, opps)):
        h = max(4, round(abs(v) / vmax * alto)) if tipo == "linea" else 30
        txt = (f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}") if tipo == "linea" else ("Sí" if v > 0 else "No")
        celdas.append(f'<div class="fj-c" title="{_e(o)}: {txt}"><span class="fj-v">{txt}</span><div class="fj-b" '
                      f'style="height:{h}px;background:{"#16a34a" if ok(v) else "#dc2626"};--d:{i * 30}ms"></div></div>')
        etq.append(f"<span>{_e(o[:3])}</span>")
    marca = f'<div class="fj-ln" style="bottom:{round(linea / vmax * alto)}px"></div>' if tipo == "linea" and linea else ""
    return f'<div class="fj-bars">{marca}{"".join(celdas)}</div><div class="fj-o">{"".join(etq)}</div>'


def _tarjeta_j(titulo, nombre, valores, opps, linea, lado, tipo, color="#16a34a", nota=""):
    ok = _pred(tipo, lado, linea)
    if not valores:
        return f'<div class="fj"><div class="fj-t">{_e(titulo)}</div><div class="fj-n">{_e(nombre)}</div><div class="fj-sub">{_e(nota or "Sin partidos")}</div></div>'
    k = sum(ok(x) for x in valores)
    pct = round(100 * k / len(valores))
    color = "#15803d" if pct >= 70 else "#b45309" if pct >= 50 else "#b91c1c"
    return (f'<div class="fj"><div class="fj-t">{_e(titulo)}</div><div class="fj-n">{_e(nombre)}</div>'
            f'<div class="fj-pct" style="color:{color}">{pct}%</div><div class="fj-sub">{k}/{len(valores)} · {_e(lado)} {linea:g}'.replace(" Sí 0", " Sí").replace(" No 0", " No")
            + (f" · {_e(nota)}" if nota else "") + f'</div>{_barras_j(valores, opps, linea, ok, tipo)}</div>')


def _auto_jugador(d_rec, d_riv, d_perm, tit_txt):
    """Filas del autoanálisis de un jugador: recientes, contra el rival y lo que el rival permite a su posición."""
    filas = []
    for nombre, (clave, tipo, quien) in MERCADOS_J.items():
        va = _vals(d_rec, clave)
        if len(va) < 3:
            continue
        linea = None if tipo == "sino" else max(0.5, fe._medio(mean(va)))
        vr = _vals(d_riv, clave)
        p = _mejor_lado_f(va, vr, tipo, linea)
        perm = _vals(d_perm, clave)
        tr = _tasa(p["ok"], vr)
        tp_ = _tasa(p["ok"], perm) if len(perm) >= 3 else None
        filas.append({"mercado": nombre, "clave": clave, "p": p, "riv": None if tr is None else (sum(p["ok"](x) for x in vr), len(vr)),
                      "perm": tp_, "n_perm": len(perm)})
    return filas


def _veredicto_j(f, hay_rival):
    p = f["p"]
    if p["pct"] < 0.7:
        return "➖ Sin ventaja clara"
    if not hay_rival or f["perm"] is None:
        return "✅ La cumple"
    return "✅ La cumple y el rival lo permite" if f["perm"] >= 0.5 else "⚠️ La cumple, pero el rival lo limita"


def _a_medio(clave):
    """Callback: si la línea escrita no termina en .5 (p. ej. 1.0 o 1.3), la deja en el .5 de abajo+1 (1.0 -> 1.5)."""
    v = st.session_state.get(clave)
    if v is not None and v % 1 != 0.5:
        st.session_state[clave] = min(max(math.floor(v) + 0.5, 0.5), 99.5)


def _input_linea(contenedor, sugerida, clave):
    """Selector de línea que siempre queda en .5 (0.5, 1.5, 2.5...), también si se escribe a mano."""
    _a_medio(clave)   # por si quedó guardado un valor entero de antes
    inicial = min(max(math.floor(sugerida) + 0.5, 0.5), 99.5)
    return contenedor.number_input("Línea", 0.5, 99.5, float(inicial), 1.0, format="%.1f", key=clave, on_change=_a_medio, args=(clave,))


ESPN_PLANTILLA = "https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/teams/{id}/roster"
FOTO_ESPN = "https://a.espncdn.com/i/headshots/soccer/players/full/{id}.png"   # cara del jugador si la plantilla no trae la suya


def _atletas(js):
    """Lista plana de jugadores de la respuesta de plantilla de ESPN (acepta la lista plana o agrupada por posición)."""
    out = []
    for a in js.get("athletes") or []:
        out += a.get("items") or [a] if isinstance(a, dict) and "items" in a else [a]
    return [a for a in out if isinstance(a, dict) and a.get("id")]


@st.cache_data(ttl=86400, show_spinner=False)
def _jugadores_mundo():
    """Todos los jugadores de las plantillas de todas las ligas de ESPN_LIGA:
    [{jid, nombre, pos, equipo, liga_n, liga, team_id}]. Se guarda 24 h (son unas cientos de peticiones la primera vez)."""
    tareas = []
    for liga_n, codigo in ESPN_LIGA.items():
        try:
            tareas += [(liga_n, codigo, e) for e in _equipos_espn(codigo) if e.get("espn_id")]
        except Exception:  # noqa: BLE001
            continue

    def uno(t):
        liga_n, codigo, e = t
        try:
            js = get_json(ESPN_PLANTILLA.format(liga=codigo, id=e["espn_id"]))
        except Exception:  # noqa: BLE001
            return []
        eq = next((n for n in e["nombres"] if n), "?")
        return [{"jid": str(a["id"]), "nombre": a.get("displayName") or a.get("fullName") or "?",
                 "pos": ((a.get("position") or {}).get("abbreviation") or ""), "equipo": eq, "liga_n": liga_n,
                 "liga": codigo, "team_id": str(e["espn_id"]), "logo": e.get("logo") or "",
                 "foto": (a.get("headshot") or {}).get("href") or FOTO_ESPN.format(id=a["id"])} for a in _atletas(js)]

    with ThreadPoolExecutor(max_workers=16) as pool:
        filas = [j for lista in pool.map(uno, tareas) for j in lista]
    if not filas:
        raise RuntimeError("ESPN no devolvió plantillas")
    vistos, out = set(), []
    for j in sorted(filas, key=lambda j: _n(j["nombre"])):
        if (j["jid"], j["team_id"]) not in vistos:
            vistos.add((j["jid"], j["team_id"]))
            out.append(j)
    return out


def _seccion_jugador():
    st.markdown(_AUTO_CSS + _JUG_CSS + "<style>@keyframes fjBar{from{transform:scaleY(0);opacity:.3}to{transform:scaleY(1);opacity:1}}</style>", unsafe_allow_html=True)
    try:
        with st.spinner("Cargando las plantillas de todas las ligas (la primera vez tarda un poco)..."):
            mundo = _jugadores_mundo()
    except Exception as ex:  # noqa: BLE001
        st.error(f"No se pudo cargar la lista de jugadores: {str(ex)[:300]}")
        return
    sel = st.selectbox("Jugador", range(len(mundo)), index=None, key="ff_jug_mundo", placeholder="Escribe el nombre de un jugador…",
                       format_func=lambda i: f"{mundo[i]['nombre']} · {mundo[i]['pos'] or '—'} · {mundo[i]['equipo']} ({mundo[i]['liga_n']})")
    st.caption(f"{len(mundo):,} jugadores de {len({j['liga'] for j in mundo})} ligas con datos de ESPN. "
               f"Estadísticas de sus últimos {MAX_PJ} partidos de liga.")
    if sel is None:
        st.info("Busca un jugador por su nombre para ver cuántas veces cumplió cada estadística.")
        return
    jug = mundo[sel]
    liga_espn, pid = jug["liga"], jug["jid"]
    eq_a = {"id": jug["team_id"], "nombre": jug["equipo"], "espn_id": jug["team_id"]}
    eq_b = None   # sin rival: ya no se elige equipo ni rival
    try:
        with st.spinner(f"Cargando estadísticas de {jug['nombre']} ({eq_a['nombre']})..."):
            df, diag = _cargar_jugadores(liga_espn, str(eq_a["espn_id"]))
    except Exception as ex:  # noqa: BLE001
        st.error(f"No se pudieron cargar las estadísticas de {jug['nombre']}: {str(ex)[:300]}")
        return
    _compañeros(mundo, sel)
    solo_tit = st.toggle("Solo partidos de titular", value=False, key="ff_jug_tit")
    df["jid"] = df["jid"].astype(str)
    dj = df[df.propio & (df.jid == pid)].sort_values("fecha")
    _tarjeta_jugador(jug, dj)
    if not len(dj):
        st.warning(f"ESPN no trae partidos de {jug['nombre']} con {eq_a['nombre']} en esta liga (puede ser un fichaje reciente o no haber jugado).")
        return
    if solo_tit:
        dj = dj[dj.titular]
    nombre_j = dj.jugador.iloc[-1] if len(dj) else jug["nombre"]
    grupos_j = dj.grupo.dropna()
    grupo = grupos_j.mode().iat[0] if len(grupos_j) else None
    es_portero = grupo == "Portero"
    mercados = {k: v for k, v in MERCADOS_J.items() if v[2] == "todos" or (v[2] == "portero") == es_portero}
    if not len(dj):
        st.warning("Ese jugador no tiene partidos con ese filtro.")
        return

    ventana = st.radio("Partidos a analizar", [5, 10, 15, 20, 25, MAX_PJ], index=1, horizontal=True, key="ff_jug_vent",
                       format_func=lambda v: "Todos los cargados" if v == MAX_PJ else f"Últimos {v}")
    merc = st.selectbox("Estadística (mercado)", list(mercados), key="ff_jug_merc")
    clave, tipo, _q = mercados[merc]
    rec = dj.tail(ventana)
    vrec = _vals(rec, clave)
    # ----- el rival -----
    dr_hist, dr_perm = dj.iloc[0:0], df.iloc[0:0]
    if eq_b is not None and eq_b.get("espn_id"):
        dr_hist = dj[dj.opp_id == str(eq_b["espn_id"])]
        try:
            with st.spinner(f"Cargando datos de {eq_b['nombre']}..."):
                df_b, _d = _cargar_jugadores(liga_espn, str(eq_b["espn_id"]))
            perm = df_b[(~df_b.propio) & df_b.titular & (df_b.grupo == grupo)] if grupo else df_b.iloc[0:0]
            ult = sorted(perm.evento.unique(), key=lambda e: perm[perm.evento == e].fecha.max())[-min(ventana, MAX_PJ):]
            dr_perm = perm[perm.evento.isin(ult)]
        except Exception as ex:  # noqa: BLE001
            st.warning(f"No se pudieron cargar los datos del rival: {str(ex)[:200]}")

    if tipo == "sino":
        linea, lado = 0.0, "Sí"
        lado = st.radio("Apuesta", ["Sí", "No"], horizontal=True, key="ff_jug_lado_sino")
        st.caption("Sí = se cumplió en ese partido (verde); No = no se cumplió.")
    else:
        medi = median(vrec) if vrec else 0.5
        sug = min(max(fe._medio(medi), 0.5), 99.5)
        l1, l2 = st.columns(2)
        linea = _input_linea(l1, sug, f"ff_jug_l_{clave}_{pid}")
        lado = l2.radio("Apuesta", ["Más de", "Menos de"], horizontal=True, key="ff_jug_lado")
    ok = _pred(tipo, lado, linea)

    cols = st.columns(3 if eq_b is not None else 1)
    cols[0].markdown(_tarjeta_j(f"{merc} · últimos {len(vrec)} partidos", nombre_j, vrec, rec.opp_abbr.tolist(), linea, lado, tipo,
                                nota=f"{grupo or ''}".strip(" ")), unsafe_allow_html=True)
    if eq_b is not None:
        vh = _vals(dr_hist, clave)
        cols[1].markdown(_tarjeta_j(f"Contra {eq_b['nombre']}", nombre_j, vh, dr_hist.opp_abbr.tolist(), linea, lado, tipo,
                                    nota="" if vh else f"no se han enfrentado en los {MAX_PJ} partidos cargados"), unsafe_allow_html=True)
        vp = _vals(dr_perm, clave)
        ap = [j.split()[-1] if j else "" for j in dr_perm.jugador.tolist()]
        cols[2].markdown(_tarjeta_j(f"{eq_b['nombre']} permite", f"Rivales de posición «{grupo or '—'}»", vp[-30:], ap[-30:],
                                    linea, lado, tipo, nota=f"{len(vp)} titulares de esa posición" if vp else "sin datos"), unsafe_allow_html=True)
        tr, tp_ = _tasa(ok, vh), _tasa(ok, vp)
        t0 = _tasa(ok, vrec)
        partes = [f"**{nombre_j}** la cumple {round(100 * t0)}% de las veces" if t0 is not None else ""]
        if tr is not None:
            partes.append(f"contra {eq_b['nombre']} la cumplió {round(100 * tr)}% ({sum(ok(x) for x in vh)}/{len(vh)})")
        if tp_ is not None:
            partes.append(f"los rivales de {eq_b['nombre']} en su posición la cumplen {round(100 * tp_)}%")
        st.markdown("👉 " + " · ".join(p for p in partes if p) + ".")

    # ----- Autoanálisis del jugador -----
    par = (str(eq_a["id"]), pid, eq_b["id"] if eq_b else None)
    b1, b2, _ = st.columns([2, 1, 3])
    if b1.button("🤖 Autoanálisis de todas las estadísticas del jugador", key="ff_auto_btn", use_container_width=True,
                 help="Revisa todas las estadísticas del jugador: si las cumple, cómo le fue contra el rival y si el rival las permite."):
        st.session_state["ff_jug_auto"] = par
    if st.session_state.get("ff_jug_auto") == par and b2.button("✖ Ocultar", key="ff_auto_off", use_container_width=True):
        st.session_state["ff_jug_auto"] = None
    if st.session_state.get("ff_jug_auto") == par:
        filas = _auto_jugador(rec, dr_hist, dr_perm, solo_tit)
        filas = [f for f in filas if f["clave"] in {v[0] for v in mercados.values()}]
        if not filas:
            st.info("Hay pocos partidos del jugador (mínimo 3) para el autoanálisis. Sube la cantidad de partidos.")
        else:
            hay = eq_b is not None
            fuertes = [f for f in filas if f["p"]["pct"] >= 0.7]
            st.markdown(f'<div class="fa-ver"><span style="font-size:26px">📊</span><div><b>{_e(nombre_j)} cumple {len(fuertes)} de {len(filas)} '
                        f'estadísticas con 70% o más</b><br><span style="font-size:12px;opacity:.75">base: últimos {len(rec)} partidos'
                        f'{" · rival: " + _e(eq_b["nombre"]) if hay else ""}</span></div></div>', unsafe_allow_html=True)
            top = sorted(filas, key=lambda f: (-f["p"]["score"], -f["p"]["n"]))[:6]
            tarjetas, medallas = [], ["🥇", "🥈", "🥉", "④", "⑤", "⑥"]
            for i, f in enumerate(top):
                p = f["p"]
                pct = round(100 * p["pct"])
                if not hay or f["perm"] is None:
                    chip = '<span class="fa-riv fa-na">Rival: sin dato</span>'
                else:
                    chip = f'<span class="fa-riv {"fa-ok" if f["perm"] >= 0.5 else "fa-mal"}">{_e(eq_b["nombre"])} lo permite: {round(100 * f["perm"])}%</span>'
                tarjetas.append(f'<div class="fa-card" style="--c:#16a34a;--d:{i * 70}ms"><div class="fa-top"><span style="font-size:18px">{medallas[i]}</span></div>'
                                f'<div class="fa-mk">{_e(f["mercado"])}</div><div class="fa-pick">{_e(_txt_pick(p))}</div><div class="fa-pct">{pct}%</div>'
                                f'<div class="fa-sub">{_e(_txt_k(p))}</div><div class="fa-bar"><i style="width:{pct}%"></i></div>{chip}</div>')
            st.markdown("**Mejores líneas del jugador**")
            st.markdown('<div class="fa-grid">' + "".join(tarjetas) + "</div>", unsafe_allow_html=True)
            tabla = [{"Estadística": f["mercado"], "Apuesta": _txt_pick(f["p"]), "Jugador (partidos)": _txt_k(f["p"]), "Jugador %": round(100 * f["p"]["pct"]),
                      "Contra el rival %": None if f["riv"] is None else round(100 * f["riv"][0] / f["riv"][1]),
                      "El rival permite %": None if f["perm"] is None else round(100 * f["perm"]), "Veredicto": _veredicto_j(f, hay)} for f in filas]
            pc = lambda t, h="": st.column_config.ProgressColumn(t, min_value=0, max_value=100, format="%d%%", help=h)   # noqa: E731
            st.dataframe(pd.DataFrame(tabla), hide_index=True, use_container_width=True, column_config={
                "Jugador %": pc("Jugador %"),
                "Contra el rival %": pc("Contra el rival %", "Cuántas veces el jugador cumplió esa misma línea en sus partidos contra el rival elegido."),
                "El rival permite %": pc("El rival permite %", "Cuántas veces los titulares de su misma posición cumplieron esa línea contra el rival elegido.")})
            st.caption("La línea de cada estadística es la que deja al promedio del jugador en el límite. «El rival permite» = cuántos titulares de la misma posición "
                       "(portero, defensa, medio o delantero) la cumplieron contra el rival elegido. Son frecuencias históricas, no una predicción.")
    with st.expander("🔧 Diagnóstico de datos"):
        st.write(f"Partidos del equipo: {diag['partidos']} · resúmenes leídos: {diag['resumenes_ok']} · filas jugador-partido: {diag['filas']}")
        st.write("Datos que trae ESPN por jugador: " + (", ".join(diag["datos_espn"]) or "ninguno"))
        if diag["fallos"]:
            st.write("Fallos: " + "; ".join(diag["fallos"]))


# ---------------------------------------------------------------------------
# Pantalla
# ---------------------------------------------------------------------------
def render_jugador(liga):
    """Pestaña «Jugador»: estadísticas de un jugador y cómo le fue contra el rival. Se usa desde football.py igual que render()."""
    render(liga, None, jugador=True)


def _proximos_de(liga_espn, eqs):
    """{id del equipo: próximo partido} dentro de hoy y mañana, según el calendario de ESPN (el mismo de la pestaña Próximos).

    Cada valor: {cuando: «hoy»/«mañana», rival, rival_id, sede: «home»/«away», fecha}. Vacío si no hay dato o ESPN no responde."""
    if not liga_espn:
        return {}
    try:
        import football_proximos as fp   # aquí dentro: football_proximos importa football_lineas
        from datetime import timedelta
        hoy = fp._hoy()
        crudo = fp._calendario(liga_espn, tuple(f"{hoy + timedelta(days=k):%Y%m%d}" for k in (-1, 0, 1)))
        out = {}
        for p in sorted((p for p in crudo if p["estado"] == "pre" and p["fecha"]), key=lambda p: p["fecha"]):
            dia = pd.to_datetime(p["fecha"], utc=True).tz_convert(fp.ZONA).date()
            if dia < hoy:
                continue
            cuando = "hoy" if dia == hoy else "mañana" if dia == hoy + timedelta(days=1) else f"{dia:%d/%m}"
            for lado, otro, sede in (("local", "visita", "home"), ("visita", "local", "away")):
                for e in eqs:
                    if e and str(e.get("espn_id")) == p[lado]["espn_id"] and e["id"] not in out:
                        out[e["id"]] = {"cuando": cuando, "rival": p[otro]["abbr"], "rival_id": p[otro]["espn_id"], "sede": sede, "fecha": dia}
        return out
    except Exception:  # noqa: BLE001
        return {}


def _bajas_de(liga_espn, eq):
    """Lesionados y sancionados del equipo según ESPN (para la tarjeta). None si no hay dato o ESPN no responde."""
    if not liga_espn or not eq.get("espn_id"):
        return None
    try:
        import football_proximos   # aquí dentro: football_proximos importa football_lineas
        return football_proximos._bajas_espn(liga_espn, str(eq["espn_id"]))
    except Exception:  # noqa: BLE001
        return None


def render(liga, comparativa, jugador=False):
    """`liga` = la Liga cargada por football.py. `comparativa` = football._comparativa (tabla de promedios A vs B).
    `jugador=True` muestra la pantalla de un jugador en vez de la de equipos (ver render_jugador)."""
    modo_jugador = jugador
    if jugador:
        st.markdown("#### 🧍 Estadísticas de un jugador")
        _seccion_jugador()   # buscador de todos los jugadores: no usa Equipo A/B ni la liga cargada
        return
    else:
        st.title("🎯 Líneas de equipos")
        st.caption("Elige un equipo (o dos para compararlos) y una línea: mira cuántas veces la cumplieron en sus últimos 5 a 25 partidos "
                   "o en sus enfrentamientos directos.")
    t = liga.t
    nacional = liga.codigo == "INT"   # selecciones nacionales (ver football._cargar_selecciones)
    nombres = tuple(sorted(t.Equipo.unique()))
    todos = _equipos_selecciones(nombres) if nacional else _equipos_liga(nombres, ESPN_LIGA.get(st.session_state.get("f_liga")))
    abbr = {e["nombre"]: e["abbr"] for e in todos}
    por_todos = {e["id"]: e for e in todos}
    if nacional:
        # TODAS las selecciones con partidos en el periodo, separadas por confederación (más fuertes primero, por Elo)
        por_nombre = {e["nombre"]: e for e in todos}
        region = t.drop_duplicates("Equipo").set_index("Equipo")["Conf"].to_dict() if "Conf" in t.columns else {}
        region = {n: (region.get(n) if isinstance(region.get(n), str) else confederaciones.OTRAS) for n in por_nombre}
        elo = lambda n: -liga.rat.get(n, 1500.0)   # noqa: E731
        cuenta = t.groupby("Equipo").size()
        por_region = {r: [por_nombre[n] for n in sorted((n for n in por_nombre if region[n] == r), key=elo)] for r in confederaciones.ORDEN}
        mejores = sorted((n for n in cuenta.index if cuenta[n] >= 3), key=elo)[:TOP_ELO]
        por_region = {MEJORES: [por_nombre[n] for n in mejores] or todos[:TOP_ELO], **{r: v for r, v in por_region.items() if v}}
        por_id = por_todos   # el equipo elegido puede estar en otra región distinta de la que se ve
        equipos = por_region[MEJORES]
    else:
        # Escudos: los equipos de la temporada más reciente cargada (los que se pueden querer analizar hoy)
        ultima = t.loc[t.Date.idxmax(), "Temporada"]
        actuales = set(t.loc[t.Temporada == ultima, "Equipo"])
        equipos = [e for e in todos if e["nombre"] in actuales] if len(actuales) >= 4 else todos
        por_id = {e["id"]: e for e in equipos}

    st.session_state.setdefault("fe_a", equipos[0]["id"])
    st.session_state.setdefault("fe_b", None)
    if st.session_state["fe_a"] not in por_id:   # p. ej. quedó guardado un equipo de otra liga o de la NBA
        st.session_state["fe_a"] = equipos[0]["id"]
    if st.session_state["fe_b"] not in por_id:
        st.session_state["fe_b"] = None
    if nacional:
        # cada equipo tiene su propia región: se puede comparar, p. ej., Chile (Sudamérica) contra España (Europa)
        en_mejores = {e["id"] for e in por_region[MEJORES]}
        for lado in ("a", "b"):
            clave_r, elegido = f"ff_conf_{lado}", st.session_state.get(f"fe_{lado}")
            if st.session_state.get(clave_r) not in por_region:   # primera vez, o esa región ya no tiene equipos con los filtros actuales
                st.session_state[clave_r] = (region.get(por_id[elegido]["nombre"]) if elegido in por_id and elegido not in en_mejores
                                             else MEJORES)
        lista = {}
        for lado, titulo, kw in (("a", "Local", {}),
                                 ("b", "Visita (opcional, para comparar)", {"bloqueado": st.session_state["fe_a"], "con_ninguno": True})):
            sel = st.radio(f"Región de {titulo.split(' (')[0]}", list(por_region), horizontal=True, key=f"ff_conf_{lado}",
                           format_func=lambda r: r if r == MEJORES else f"{r} ({len(por_region[r])})")
            lista[lado] = por_region[sel]
            fe._fila_escudos(titulo, f"fe_{lado}", lista[lado], por_id, **kw)
        st.markdown(_css_escudos(lista["a"] + lista["b"]), unsafe_allow_html=True)
        ids = {e["nombre"]: e["id"] for e in todos}
        with st.expander("🔎 Buscar un país por nombre"):
            o1, o2 = st.columns(2)
            o1.selectbox("Local", ["—"] + list(ids), key="ff_otro_a", on_change=_elegir_otro, args=("fe_a", "ff_otro_a", ids, region))
            o2.selectbox("Visita (opcional)", ["—"] + list(ids), key="ff_otro_b", on_change=_elegir_otro, args=("fe_b", "ff_otro_b", ids, region))
    else:
        fe.selector_equipos(equipos, por_id, key_pref="ff", con_abbr=False)
        with st.expander("🛡️ Elegir desde cuadrícula de escudos", expanded=False):
            st.markdown(_css_escudos(equipos), unsafe_allow_html=True)
            fe._fila_escudos("Local", "fe_a", equipos, por_id)
            fe._fila_escudos("Visita (opcional, para comparar)", "fe_b", equipos, por_id,
                             bloqueado=st.session_state["fe_a"], con_ninguno=True)
    ida, idb = st.session_state["fe_a"], st.session_state["fe_b"]
    eq_a, eq_b = por_id[ida], (por_id[idb] if idb else None)
    import planes
    es_pro = planes.es_pro()
    if es_pro:
        grupos_f = {k: v for k, v in MERCADOS_F.items() if not nacional or k in GRUPOS_SELECCIONES}
        grupo = st.radio("Tipo de mercado", list(grupos_f), horizontal=True, key="ff_grupo_mercado_sel" if nacional else "ff_grupo_mercado",
                         label_visibility="collapsed")
        opciones_m = list(grupos_f[grupo])
        if st.session_state.get(f"ff_mercado_{grupo}") not in opciones_m:
            st.session_state.pop(f"ff_mercado_{grupo}", None)
        mercado = st.selectbox("Mercado", opciones_m, key=f"ff_mercado_{grupo}")
        ventanas = [5, 10, 15, 20, 25] + (["h2h"] if idb else [])
        ventana = st.radio("Partidos a analizar", ventanas, index=1, horizontal=True, key="ff_ventana",
                           format_func=lambda v: "⚔️ Enfrentamientos directos" if v == "h2h" else f"Últimos {v}")
    else:
        st.caption("Plan Gratuito en Fútbol: mercado **Total de goles del partido (más/menos)** y **últimos 5 partidos**.")
        mercado = "Total de goles del partido (más/menos)"
        ventana = 5
        planes.bloque_pro(
            "Todos los mercados de fútbol y ventanas de 10 a 25 partidos",
            "Resultado, tiempos, tiros, córners, disciplina y enfrentamientos directos están disponibles en ScoreLine Pro.",
            "Resultado · Córners · Tarjetas · Últimos 10/15/20/25 PJ",
            key="lock_ff_mercados",
        )
    h2h = ventana == "h2h"
    if idb:   # los dos equipos de local, o los dos de visita
        sedes = {"Todos los partidos": (None, None), "🏠 A y B de local": ("Local", "Local"),
                 "✈️ A y B de visita": ("Visita", "Visita")}
    else:
        sedes = {"Todos los partidos": (None, None), "🏠 Solo de local": ("Local", None), "✈️ Solo de visita": ("Visita", None)}
    sede_a, sede_b = sedes[st.radio("Sede de los partidos", list(sedes), horizontal=True, key=f"ff_sede_{'par' if idb else 'uno'}",
                                    help="Filtra los partidos analizados: por ejemplo, cómo rinde un equipo solo cuando juega en casa. "
                                         "Se toman los últimos N de esa sede (sin los de cancha neutral).")]

    n = 25 if h2h else ventana
    liga_espn = None if nacional else ESPN_LIGA.get(st.session_state.get("f_liga"))
    espn_ok = False

    def recientes(eq, k, sede=None):
        nonlocal espn_ok
        if nacional:
            return _ventana(t, eq["nombre"], k, sede=sede)
        d, ok = _recientes(t, eq, k, liga_espn, sede)
        espn_ok = espn_ok or ok
        return d

    with st.spinner("Cargando últimos partidos de todas las competiciones..."):
        da = _ventana(t, eq_a["nombre"], n, eq_b["nombre"], sede_a) if h2h else recientes(eq_a, n, sede_a)
        db = (_ventana(t, eq_b["nombre"], n, eq_a["nombre"], sede_b) if h2h else recientes(eq_b, n, sede_b)) if idb else None
    sa, sb = _serie(da, abbr), (_serie(db, abbr) if idb else [])
    if not sa:
        if h2h:
            st.info("Estos equipos no se enfrentan en el periodo cargado. Amplía las temporadas o los años arriba.")
        else:
            st.warning("No hay partidos terminados para el Equipo A" + (f" jugando de {sede_a.lower()}" if sede_a else "")
                       + " en las temporadas cargadas.")
        return

    def _ultimo(eq, serie):
        u = serie[-1] if serie else None
        return f"**{eq['nombre']}**: {u['dia']:%d/%m/%Y} {u['etq']} ({u['pf']}-{u['pc']})" if u else f"**{eq['nombre']}**: sin partidos"

    st.caption("📌 Último partido cargado · " + " · ".join(
        [_ultimo(eq_a, _serie(recientes(eq_a, 1), abbr))]
        + ([_ultimo(eq_b, _serie(recientes(eq_b, 1), abbr))] if idb else []))
        + (". Resultados de selecciones según el filtro de arriba (amistosos y torneos)." if nacional else
           (". Incluye liga, Champions, Europa League y copas (ESPN)." if espn_ok else
           ". ESPN no respondió: solo partidos de liga (football-data.co.uk), sin Champions ni copas.")))
    if h2h:
        u = sa[-1]
        st.caption(f"⚔️ Último cruce: {u['dia']:%d/%m/%Y} · {eq_a['abbr']} {u['pf']} – {u['rival_abbr']} {u['pc']}"
                   f" ({'ganó' if u['pf'] > u['pc'] else 'empató' if u['pf'] == u['pc'] else 'perdió'} {eq_a['abbr']}, "
                   f"{'local' if u['sede'] == 'home' else 'cancha neutral' if u['sede'] == 'neutral' else 'visita'}).")
    m = MERCADOS[mercado]
    clave = m.campo
    medianas = [median([g[clave] for g in s if g.get(clave) is not None]) for s in (sa, sb) if any(g.get(clave) is not None for g in s)]
    if not medianas:
        st.warning("Estos partidos no traen datos de este mercado (los goles por tiempo, tiros, córners y tarjetas solo vienen en las ligas europeas; las selecciones y otras ligas traen solo el marcador final). Prueba otro mercado.")
        return
    if m.tipo == "handicap":
        sugerida = -fe._medio(medianas[0] if len(medianas) == 1 else (medianas[0] - medianas[1]) / 2)
    else:
        sugerida = fe._medio(mean(medianas))

    l1, l2 = st.columns(2)
    if m.tipo == "ganador":
        linea, lado = 0.0, "Más de"
        l1.caption(m.ayuda)
    elif m.tipo == "handicap":
        linea = l1.number_input(f"Hándicap de {eq_a['nombre']}", -m.rango, m.rango, float(min(max(sugerida, -m.rango), m.rango)), 0.5,
                                format="%+.1f", key=f"ff_l_{m.clave}_{ida}_{idb}",
                                help="Ej.: -1.5 = debe ganar por 2 o más goles. +0.5 = no puede perder.")
        lado = "Más de"
    else:
        linea = _input_linea(l1, sugerida, f"ff_l5_{m.clave}_{ida}_{idb}")
        lado = l2.radio("Apuesta", ["Más de", "Menos de"], horizontal=True, key="ff_lado")

    estilos.cargar("ficha_linea", "equipos")   # primero la base (.fl), luego lo propio de equipos
    modo = m.tipo
    linea_b = -linea if modo == "handicap" else linea   # solo el hándicap se invierte para el Equipo B
    cards = [(eq_a, sa, linea, sede_a, (eq_b, sb) if idb else None)] + ([(eq_b, sb, linea_b, sede_b, (eq_a, sa))] if idb else [])
    st.markdown(football_tarjeta.CSS, unsafe_allow_html=True)   # estilo de la tarjeta (una sola vez por pantalla)
    proximos = {} if h2h else _proximos_de(liga_espn, [eq_a, eq_b])
    for col, (eq, serie, ln, sede, rival) in zip(st.columns(len(cards)), cards):
        umbral = -ln if modo == "handicap" else abs(ln)
        # la sede elegida se ve en el encabezado de la tarjeta: «Tiros a puerta del equipo · 🏠 de local · últimos 5 partidos»
        etiqueta = mercado + {"Local": " · 🏠 de local", "Visita": " · ✈️ de visita"}.get(sede, "")
        try:
            html = football_tarjeta.tarjeta(eq, serie, m, umbral, lado, etiqueta, hand=ln, h2h=h2h, rival=None if h2h else rival,
                                            bajas=_bajas_de(liga_espn, eq), proximo=proximos.get(eq["id"]))
        except Exception as e:  # noqa: BLE001  (un dato raro no debe dejar la pantalla sin análisis)
            col.error(f"No se pudo dibujar la tarjeta de {eq['nombre']}: {e!r}")
            col.markdown(fe._tarjeta(eq, serie, m, umbral, lado, etiqueta, hand=ln, h2h=h2h), unsafe_allow_html=True)
            continue
        col.markdown(html, unsafe_allow_html=True)

    _boton_auto(eq_a, eq_b, grupos_f, sa, sb, h2h, ventana, recientes, sede_a, sede_b, t, abbr)

    if idb:
        st.markdown("#### Comparativa")
        st.dataframe(comparativa(eq_a["nombre"], eq_b["nombre"], da, db,
                                 "Promedio (enfrentamientos directos)" if h2h else f"Promedio (últimos {ventana})"),
                     hide_index=True, use_container_width=True)
        with st.spinner("Calculando líneas con racha..."):
            n_rec = ventana if isinstance(ventana, int) else 10
            ra = sa if not h2h else _serie(recientes(eq_a, n_rec, sede_a), abbr)
            rb = sb if not h2h else _serie(recientes(eq_b, n_rec, sede_b), abbr)
            ha = sa if h2h else _serie(_ventana(t, eq_a["nombre"], 25, eq_b["nombre"]), abbr)
            hb = sb if h2h else _serie(_ventana(t, eq_b["nombre"], 25, eq_a["nombre"]), abbr)
        if ra and rb:
            _seccion_racha(eq_a, eq_b, ra, rb, ha, hb)
    st.caption("La frecuencia es histórica (cuántas veces cumplieron la línea), no una predicción del partido. "
               "El hándicap del Equipo B es el opuesto al del A. Verde más intenso = superó la línea por más margen. "
               + ("Las banderas vienen de flagcdn.com; si un país no está en la tabla, se muestra una insignia con sus iniciales." if nacional else
                  "Los escudos vienen de ESPN; si un equipo no aparece allí, se muestra una insignia con sus iniciales."))
