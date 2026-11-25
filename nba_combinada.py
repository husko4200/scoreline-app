"""Analiza una combinada (parlay) de la NBA a partir de una foto o de datos escritos a mano.

Flujo:
  1. Subes la foto de la boleta. Claude (visión) lee las "patas" y la app las analiza al instante,
     sin pulsar nada más: jugador, mercado, línea y cuota.
  2. Puedes corregir la tabla (o escribir las patas a mano, sin foto) y el análisis se actualiza.
  3. La app compara cada línea con el historial real del jugador: en cuántos de sus últimos
     5, 10, 15, 20 y 25 partidos la habría superado, y estima la probabilidad de toda la combinada.

Requisitos para leer la foto:  pip install anthropic   y una clave de API en ANTHROPIC_API_KEY
(variable de entorno, .streamlit/secrets.toml, o pegándola en la propia pantalla).

Cómo usarlo desde otro archivo:
    import nba_combinada
    nba_combinada.render()
"""
import base64
import difflib
import hashlib
import html
import io
import json
import math
import os
import re
import unicodedata
from datetime import date

import pandas as pd
import streamlit as st

import nba_h2h_jugadores as h
import nba_jugadores as jg

MODELO = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")   # modelo que lee la foto

# Mercado -> estadísticas que se suman en cada partido
MERCADOS = {
    "Puntos": ["PTS"], "Rebotes": ["REB"], "Asistencias": ["AST"], "Triples": ["3PM"],
    "Robos": ["STL"], "Tapones": ["BLK"], "Pérdidas": ["TO"],
    "Pts+Reb+Ast": ["PTS", "REB", "AST"], "Pts+Reb": ["PTS", "REB"],
    "Pts+Ast": ["PTS", "AST"], "Reb+Ast": ["REB", "AST"],
}
OTRO = "Otro (no analizable)"
DIRECCIONES = ["Más de", "Menos de"]
COLUMNAS = ["Jugador", "Mercado", "Dirección", "Línea", "Cuota", "Detalle"]
VENTANAS = (5, 10, 15, 20, 25)

VERDE, AMBAR, ROJO, GRIS = "#22c55e", "#f59e0b", "#ef4444", "#94a3b8"

PROMPT = """Esta imagen es una boleta o ticket de una apuesta combinada (parlay) de baloncesto. Extrae cada selección ("pata").
Responde SOLO con JSON válido, sin texto adicional ni bloques de código, con esta forma:
{"patas":[{"jugador":"Nombre Apellido","mercado":"Puntos","direccion":"Más de","linea":24.5,"cuota":1.85,"detalle":"texto original breve"}],"cuota_total":null}
Reglas:
- "mercado" debe ser exactamente uno de: Puntos, Rebotes, Asistencias, Triples, Robos, Tapones, Pérdidas, Pts+Reb+Ast, Pts+Reb, Pts+Ast, Reb+Ast, Otro (no analizable).
- Usa "Otro (no analizable)" para selecciones que no sean la estadística de un jugador (ganador del partido, hándicap, total del partido, etc.). En ese caso pon el texto original en "detalle".
- "direccion" es "Más de" (over) o "Menos de" (under). Si la selección dice "X+" o "X o más" (p. ej. "25+ puntos"), es "Más de" con línea X menos 0.5 (24.5).
- "linea" es un número decimal con punto. "cuota" va en formato decimal (si está en formato americano o fraccionario, conviértela); usa null si no se ve.
- "cuota_total" es la cuota total de la combinada si aparece, o null.
- No inventes datos: si algo no se lee, usa null."""

CSS = """
<style>
@keyframes cb-subir { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
@keyframes cb-pop   { 0% { opacity: 0; transform: scale(.4); } 100% { opacity: 1; transform: scale(1); } }

.cb-resumen, .cb-pata { position: relative; overflow: hidden; border-radius: 18px; padding: 1.1rem 1.2rem 1rem; margin-bottom: 14px;
  background: var(--card, rgba(127,127,127,.07)); border: 1px solid var(--borde, rgba(127,127,127,.22));
  animation: cb-subir .55s ease both; transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease; }
.cb-pata::before, .cb-resumen::before { content: ""; position: absolute; inset: 0 0 auto 0; height: 5px; background: var(--c, #6366f1); }
.cb-resumen::before { background: linear-gradient(90deg, #4f46e5, #7c3aed, #c9a227); }
.cb-pata:hover { transform: translateY(-4px); box-shadow: 0 14px 30px rgba(79,70,229,.22); border-color: var(--c); }

.cb-resumen { background: linear-gradient(135deg, rgba(99,102,241,.12), rgba(127,127,127,.05) 50%, rgba(201,162,39,.14)); }
.cb-r-titulo { font-size: .72rem; letter-spacing: .12em; font-weight: 700; opacity: .7; text-transform: uppercase; margin-top: .2rem; }
.cb-r-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: .7rem 0; }
.cb-r-n { text-align: center; padding: .6rem .3rem; border-radius: 14px; background: rgba(127,127,127,.09); }
.cb-r-n b { display: block; font-size: 2rem; font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums; animation: cb-pop .6s cubic-bezier(.2,1.4,.4,1) both; }
.cb-r-n span { font-size: .66rem; letter-spacing: .1em; font-weight: 700; opacity: .7; }
.cb-r-n small { display: block; font-size: .72rem; opacity: .75; margin-top: 2px; }
.cb-r-txt { font-size: .9rem; line-height: 1.5; margin-top: .2rem; }

.cb-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap; margin-top: .2rem; }
.cb-jug { font-family: 'Playfair Display', Georgia, serif; font-size: 1.25rem; font-weight: 700; }
.cb-eq { margin-left: 6px; padding: 0 .5rem; border-radius: 999px; border: 1px solid currentColor; font-family: Inter, sans-serif; font-size: .66rem; font-weight: 700; letter-spacing: .1em; vertical-align: middle; opacity: .8; }
.cb-linea { font-size: .92rem; margin-top: 2px; }
.cb-linea b { font-size: 1.05rem; }
.cb-cuota { margin-left: 6px; padding: .05rem .5rem; border-radius: 999px; background: rgba(201,162,39,.2); border: 1px solid rgba(201,162,39,.5); font-size: .74rem; font-weight: 700; }
.cb-ver { padding: .3rem .8rem; border-radius: 999px; font-weight: 700; font-size: .82rem; color: #fff; background: var(--c); animation: cb-pop .5s ease both; }

.cb-vent { display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; margin: .9rem 0 .7rem; }
.cb-v { text-align: center; }
.cb-aroW { position: relative; width: 58px; height: 58px; margin: 0 auto; }
.cb-aro { position: absolute; inset: 0; border-radius: 50%; animation: cb-pop .6s cubic-bezier(.2,1.4,.4,1) both;
  background: conic-gradient(var(--col) calc(var(--p) * 1%), rgba(127,127,127,.22) 0);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 7px), #000 calc(100% - 6px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 7px), #000 calc(100% - 6px)); }
.cb-aroW b { position: absolute; inset: 0; display: grid; place-items: center; font-size: .82rem; font-variant-numeric: tabular-nums; }
.cb-v span { display: block; font-size: .64rem; letter-spacing: .08em; font-weight: 700; opacity: .75; margin-top: 3px; }
.cb-v small { font-size: .66rem; opacity: .6; }

.cb-t { font-size: .64rem; letter-spacing: .1em; font-weight: 700; opacity: .65; text-transform: uppercase; margin: .6rem 0 .3rem; }
.cb-racha { display: flex; flex-wrap: wrap; gap: 4px; }
.cb-racha i { display: grid; place-items: center; min-width: 30px; height: 26px; padding: 0 3px; border-radius: 7px; font-style: normal; font-size: .72rem; font-weight: 700; color: #fff;
  animation: cb-pop .45s ease both; }
.cb-racha i.ok { background: #22c55e; } .cb-racha i.no { background: #ef4444; } .cb-racha i.push { background: #94a3b8; }
.cb-stats { margin-top: .6rem; font-size: .8rem; opacity: .85; line-height: 1.5; }
.cb-aviso { font-size: .85rem; padding: .3rem 0; }
.cb-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: .2rem 0 .4rem; }
.cb-chip { padding: .25rem .7rem; border-radius: 999px; font-size: .76rem; border: 1px solid var(--cc); background: rgba(127,127,127,.08);
  box-shadow: inset 3px 0 0 var(--cc); }

@media (max-width: 560px) { .cb-vent { grid-template-columns: repeat(3, 1fr); row-gap: 10px; } }
@media (prefers-reduced-motion: reduce) { .cb-resumen, .cb-pata, .cb-resumen *, .cb-pata * { animation: none !important; transition: none !important; } }
</style>
"""


# ---------------------------------------------------------------------------
# Lectura de la foto con Claude
# ---------------------------------------------------------------------------
def _clave_api():
    clave = st.session_state.get("comb_clave") or os.environ.get("ANTHROPIC_API_KEY")
    if not clave:
        try:
            clave = st.secrets.get("ANTHROPIC_API_KEY")
        except Exception:  # noqa: BLE001 - si no hay archivo de secretos, simplemente no hay clave
            clave = None
    return clave


def _preparar_imagen(datos):
    """Corrige la rotación de las fotos de celular, reduce el tamaño y devuelve (base64, tipo)."""
    from PIL import Image, ImageOps
    imagen = ImageOps.exif_transpose(Image.open(io.BytesIO(datos)))
    imagen.thumbnail((1800, 1800))
    buffer = io.BytesIO()
    imagen.convert("RGB").save(buffer, "JPEG", quality=90)
    return base64.b64encode(buffer.getvalue()).decode(), "image/jpeg"


def _extraer_json(texto):
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fin <= inicio:
        raise ValueError("La respuesta no contiene datos legibles.")
    return json.loads(texto[inicio:fin + 1])


def _numero(valor):
    try:
        n = float(str(valor).replace(",", "."))
        return None if math.isnan(n) else n
    except (TypeError, ValueError):
        return None


def _normalizar_pata(p):
    mercado = str(p.get("mercado") or "").strip()
    por_minuscula = {m.lower(): m for m in MERCADOS}
    mercado = por_minuscula.get(mercado.lower(), OTRO)
    direccion = str(p.get("direccion") or "").lower()
    direccion = "Menos de" if any(t in direccion for t in ("menos", "under", "men")) else "Más de"
    return {"Jugador": str(p.get("jugador") or "").strip(), "Mercado": mercado, "Dirección": direccion,
            "Línea": _numero(p.get("linea")), "Cuota": _numero(p.get("cuota")), "Detalle": str(p.get("detalle") or "")}


def leer_boleta(datos_imagen, clave):
    """Devuelve (DataFrame de patas, cuota total o None). Lanza excepciones con mensaje claro."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("Falta instalar la librería: ejecuta  pip install anthropic  y reinicia la app.") from e
    b64, tipo = _preparar_imagen(datos_imagen)
    cliente = anthropic.Anthropic(api_key=clave)
    respuesta = cliente.messages.create(
        model=MODELO, max_tokens=2000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": tipo, "data": b64}},
            {"type": "text", "text": PROMPT}]}])
    texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text")
    datos = _extraer_json(texto)
    filas = [_normalizar_pata(p) for p in datos.get("patas", [])]
    return pd.DataFrame(filas, columns=COLUMNAS), _numero(datos.get("cuota_total"))


# ---------------------------------------------------------------------------
# Búsqueda del jugador por nombre
# ---------------------------------------------------------------------------
SUFIJOS = {"jr", "sr", "ii", "iii", "iv"}


def _tokens(texto):
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    limpio = re.sub(r"[^a-z\s]", " ", sin_tildes.lower())
    return [t for t in limpio.split() if t not in SUFIJOS]


def buscar_jugador(nombre, jugadores):
    """Encuentra al jugador aunque venga como 'J. Brunson' o con tildes distintas. None si no hay coincidencia."""
    tokens = _tokens(nombre)
    if not tokens:
        return None
    completo = " ".join(tokens)
    claves = {" ".join(_tokens(j["nombre"])): j for j in jugadores}
    if completo in claves:
        return claves[completo]
    apellido, inicial = tokens[-1], tokens[0][0]
    candidatos = [j for j in jugadores if _tokens(j["nombre"]) and _tokens(j["nombre"])[-1] == apellido]
    if len(candidatos) == 1 and (len(tokens) == 1 or _tokens(candidatos[0]["nombre"])[0][0] == inicial):
        return candidatos[0]
    if len(candidatos) > 1:
        con_inicial = [j for j in candidatos if _tokens(j["nombre"])[0][0] == inicial]
        if len(con_inicial) == 1:
            return con_inicial[0]
    cercano = difflib.get_close_matches(completo, list(claves), n=1, cutoff=0.72)
    return claves[cercano[0]] if cercano else None


# ---------------------------------------------------------------------------
# Análisis de una pata
# ---------------------------------------------------------------------------
def valor_mercado(partido, mercado):
    """Valor de un partido para el mercado (suma las estadísticas si es combinado tipo Pts+Reb)."""
    partes = [partido.get(c) for c in MERCADOS[mercado]]
    return None if any(p is None for p in partes) else sum(partes)


def _cumple(valor, linea, direccion):
    return valor > linea if direccion == "Más de" else valor < linea


def analizar_pata(juegos, mercado, direccion, linea):
    """Aciertos por ventana de partidos. `juegos` va del más reciente al más antiguo."""
    vals = [(g, valor_mercado(g, mercado)) for g in juegos]
    vals = [(g, v) for g, v in vals if v is not None]
    ventanas = {}
    for n in VENTANAS + (0,):                      # 0 = todos los partidos disponibles
        if n and len(vals) < n:
            ventanas[n] = None
            continue
        sub = vals if n == 0 else vals[:n]
        if not sub:
            ventanas[n] = None
            continue
        empates = sum(1 for _, v in sub if v == linea)
        aciertos = sum(1 for _, v in sub if _cumple(v, linea, direccion))
        validos = len(sub) - empates
        ventanas[n] = {"hits": aciertos, "n": len(sub), "validos": validos, "push": empates,
                       "pct": round(100 * aciertos / validos) if validos else None}
    return vals, ventanas


def probabilidad(ventanas):
    """Probabilidad estimada: promedio de las tasas de acierto de cada ventana, suavizadas (+1/+2)."""
    tasas = []
    for n in VENTANAS:
        v = ventanas.get(n)
        if v and v["validos"]:
            tasas.append((v["hits"] + 1) / (v["validos"] + 2))
    if not tasas and ventanas.get(0) and ventanas[0]["validos"]:
        v = ventanas[0]
        tasas.append((v["hits"] + 1) / (v["validos"] + 2))
    return sum(tasas) / len(tasas) if tasas else None


def veredicto(p):
    if p is None:
        return "Sin datos", GRIS
    if p >= 0.70:
        return "🟢 Sólida", VERDE
    if p >= 0.55:
        return "🟡 Aceptable", AMBAR
    return "🔴 Débil", ROJO


def _color_pct(pct):
    if pct is None:
        return GRIS
    return VERDE if pct >= 70 else AMBAR if pct >= 55 else ROJO


def racha_actual(vals, linea, direccion):
    """Racha vigente desde el partido más reciente: (+N) partidos seguidos cumpliendo, (-N) seguidos fallando.
    Un empate con la línea (push) corta la racha. `vals` es [(partido, valor)] del más reciente al más antiguo."""
    if not vals or vals[0][1] == linea:
        return 0
    cumple = _cumple(vals[0][1], linea, direccion)
    n = 0
    for _, v in vals:
        if v == linea or _cumple(v, linea, direccion) != cumple:
            break
        n += 1
    return n if cumple else -n


MAX_PARTIDOS_DESV = 20   # la desviación se mide sobre los últimos 20 partidos (o los que haya)


def desviacion(vals, maximo=MAX_PARTIDOS_DESV):
    """(desviación estándar muestral, promedio, partidos usados) de los últimos `maximo` partidos; None si hay menos de 3."""
    nums = [v for _, v in vals[:maximo]]
    if len(nums) < 3:
        return None
    media = sum(nums) / len(nums)
    desv = math.sqrt(sum((x - media) ** 2 for x in nums) / (len(nums) - 1))
    return desv, media, len(nums)


def constancia(desv, media):
    """Etiqueta según el coeficiente de variación (desviación ÷ promedio): menor = jugador más constante."""
    if not media:
        return "—", GRIS
    cv = desv / media
    if cv < 0.25:
        return "Alta", VERDE
    if cv < 0.40:
        return "Media", AMBAR
    return "Baja", ROJO


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
def _fmt(v):
    return h._fmt(v)


def _aro(titulo, v, retraso):
    esc = html.escape
    if not v or v["pct"] is None:
        return (f'<div class="cb-v"><div class="cb-aroW"><div class="cb-aro" style="--p:0;--col:{GRIS}"></div><b>–</b></div>'
                f'<span>{esc(titulo)}</span><small>sin datos</small></div>')
    return (f'<div class="cb-v"><div class="cb-aroW"><div class="cb-aro" style="--p:{v["pct"]};--col:{_color_pct(v["pct"])};animation-delay:{retraso:.2f}s"></div>'
            f'<b>{v["pct"]}%</b></div><span>{esc(titulo)}</span><small>{v["hits"]}/{v["validos"]}</small></div>')


def _pata_html(i, fila, info):
    esc = html.escape
    base = min(i, 8) * 0.08
    nombre = esc(fila["Jugador"] or "—")
    cuota = f'<span class="cb-cuota">@{fila["Cuota"]:.2f}</span>' if fila["Cuota"] else ""

    if info["estado"] != "ok":
        mensajes = {
            "otro": f'ℹ️ Selección no analizable{": " + esc(fila["Detalle"]) if fila["Detalle"] else ""}. No se incluye en la probabilidad.',
            "falta_linea": "⚠️ Falta la línea (por ejemplo 24.5). Complétala en la tabla y vuelve a analizar.",
            "no_jugador": f'❓ No encontré a «{nombre}» en las plantillas actuales. Revisa cómo está escrito el nombre en la tabla.',
            "sin_partidos": "📭 No hay partidos de este jugador en las temporadas elegidas.",
        }
        return (f'<div class="cb-pata" style="--c:{GRIS};animation-delay:{base:.2f}s"><div class="cb-top"><div>'
                f'<div class="cb-jug">{nombre}</div></div></div><div class="cb-aviso">{mensajes[info["estado"]]}</div></div>')

    texto_ver, color = veredicto(info["prob"])
    vent = info["ventanas"]
    anillos = "".join(_aro(f"Últ. {n}", vent.get(n), base + 0.1 + 0.06 * k) for k, n in enumerate(VENTANAS))
    anillos += _aro("Todos", vent.get(0), base + 0.5)
    racha = "".join(
        f'<i class="{"push" if v == fila["Línea"] else "ok" if _cumple(v, fila["Línea"], fila["Dirección"]) else "no"}" '
        f'title="{esc(g["fecha"])} {"vs" if g["sede"] == "Local" else "@"} {esc(g["rival"])}: {_fmt(v)}" '
        f'style="animation-delay:{base + 0.3 + 0.03 * k:.2f}s">{_fmt(v)}</i>'
        for k, (g, v) in enumerate(info["vals"][:15]))
    ref = [v for _, v in info["vals"][:10]]
    prom = sum(ref) / len(ref)
    ordenados = sorted(ref)
    mediana = (ordenados[len(ordenados) // 2] if len(ordenados) % 2 else (ordenados[len(ordenados) // 2 - 1] + ordenados[len(ordenados) // 2]) / 2)
    estadisticas = (f'Últimos {len(ref)} partidos: promedio <b>{_fmt(prom)}</b> ({prom - fila["Línea"]:+.1f} frente a la línea) · '
                    f'mediana {_fmt(mediana)} · mín {_fmt(min(ref))} · máx {_fmt(max(ref))}')

    # Racha actual y desviación estándar (qué tan constante es el jugador)
    r = racha_actual(info["vals"], fila["Línea"], fila["Dirección"])
    if r > 0:
        chip_racha = f'<span class="cb-chip" style="--cc:{VERDE}">🔥 Racha: <b>{r}</b> seguidos cumpliendo</span>'
    elif r < 0:
        chip_racha = f'<span class="cb-chip" style="--cc:{ROJO}">🧊 Racha: <b>{-r}</b> seguidos fallando</span>'
    else:
        chip_racha = f'<span class="cb-chip" style="--cc:{GRIS}">➖ Último partido igual a la línea</span>'
    d = desviacion(info["vals"])
    if d:
        desv, media, usados = d
        nivel, color_c = constancia(desv, media)
        chip_desv = (f'<span class="cb-chip" style="--cc:{color_c}" title="Desviación estándar de los últimos {usados} partidos '
                     f'(promedio {_fmt(media)}). Menor = jugador más constante.">📐 Desv. est. <b>{desv:.1f}</b> · constancia <b>{nivel}</b></span>')
    else:
        chip_desv = f'<span class="cb-chip" style="--cc:{GRIS}">📐 Desv. est.: pocos partidos</span>'
    chips = f'<div class="cb-chips">{chip_racha}{chip_desv}</div>'
    return (f'<div class="cb-pata" style="--c:{color};animation-delay:{base:.2f}s">'
            f'<div class="cb-top"><div><div class="cb-jug">{nombre}<span class="cb-eq">{esc(info["equipo"])}</span></div>'
            f'<div class="cb-linea">{fila["Dirección"]} <b>{_fmt(fila["Línea"])}</b> {esc(fila["Mercado"])}{cuota}</div></div>'
            f'<div class="cb-ver">{texto_ver} · {round(100 * info["prob"])}%</div></div>'
            f'<div class="cb-vent">{anillos}</div>{chips}'
            f'<div class="cb-t">Últimos partidos · del más reciente al más antiguo (🟩 cumple · 🟥 falla)</div>'
            f'<div class="cb-racha">{racha}</div><div class="cb-stats">{estadisticas}</div></div>')


def _resumen_html(analizadas, omitidas, cuota_total):
    esc = html.escape
    probs = [info["prob"] for _, info in analizadas]
    p_total = math.prod(probs)
    justa = 1 / p_total if p_total > 0 else None
    debil_fila, debil_info = min(analizadas, key=lambda x: x[1]["prob"])
    sin_debil = math.prod(info["prob"] for f, info in analizadas if f is not debil_fila) if len(analizadas) > 1 else None
    color = VERDE if p_total >= 0.35 else AMBAR if p_total >= 0.15 else ROJO

    tu_cuota = ""
    juicio = ""
    if cuota_total and justa:
        valor = cuota_total >= justa
        tu_cuota = (f'<div class="cb-r-n"><b style="color:{VERDE if valor else ROJO}">{cuota_total:.2f}</b><span>TU CUOTA</span>'
                    f'<small>{"por encima" if valor else "por debajo"} de la cuota justa</small></div>')
        juicio = (" La cuota que te pagan es <b>mayor</b> que la cuota justa según el historial."
                  if valor else " La cuota que te pagan es <b>menor</b> que la cuota justa según el historial.")
    texto_debil = (f'💡 La pata más débil es <b>{esc(debil_fila["Jugador"])}</b> ({esc(debil_fila["Dirección"].lower())} {_fmt(debil_fila["Línea"])} '
                   f'{esc(debil_fila["Mercado"].lower())}, {round(100 * debil_info["prob"])}%).')
    if sin_debil is not None:
        texto_debil += f' Sin ella, la probabilidad de la combinada subiría a {round(100 * sin_debil)}%.'
    texto_omitidas = (f' {omitidas} selección(es) no analizable(s) no se incluyen en el cálculo.' if omitidas else "")
    return (f'<div class="cb-resumen"><div class="cb-r-titulo">🎫 Resumen de la combinada · {len(analizadas)} patas analizadas</div>'
            f'<div class="cb-r-grid">'
            f'<div class="cb-r-n"><b style="color:{color}">{round(100 * p_total)}%</b><span>PROBABILIDAD ESTIMADA</span><small>de acertar todas</small></div>'
            f'<div class="cb-r-n"><b>{justa:.2f}</b><span>CUOTA JUSTA</span><small>1 ÷ probabilidad</small></div>{tu_cuota}</div>'
            f'<div class="cb-r-txt">{texto_debil}{juicio}{texto_omitidas}</div></div>')


# ---------------------------------------------------------------------------
# Pantalla
# ---------------------------------------------------------------------------
def _tabla_vacia():
    return pd.DataFrame({"Jugador": pd.Series(dtype="object"), "Mercado": pd.Series(dtype="object"),
                         "Dirección": pd.Series(dtype="object"), "Línea": pd.Series(dtype="float"),
                         "Cuota": pd.Series(dtype="float"), "Detalle": pd.Series(dtype="object")})


def _etiqueta_temporada(t):
    return f"{t - 1}-{str(t)[2:]}"


def _bloque_clave_api():
    if _clave_api():
        return
    with st.expander("🔑 Para leer fotos necesitas una clave de API de Anthropic", expanded=False):
        st.write("La foto se envía a Claude para leer las selecciones. Puedes crear una clave en console.anthropic.com. "
                 "Para no pegarla cada vez, guárdala en la variable de entorno `ANTHROPIC_API_KEY` o en `.streamlit/secrets.toml`. "
                 "Si no quieres usar foto, también puedes escribir las patas a mano en la tabla.")
        clave = st.text_input("Clave de API (solo se guarda mientras la app esté abierta)", type="password", key="comb_clave_input")
        if clave:
            st.session_state["comb_clave"] = clave
            st.rerun()


def render():
    st.title("🎫 Analizar combinada")
    st.caption("Sube la foto de tu boleta (o escribe las patas) y la app compara cada línea con el historial real del jugador.")
    st.markdown(CSS, unsafe_allow_html=True)   # aparte del HTML: la app oculta los bloques que traen <style>

    st.session_state.setdefault("comb_tabla", _tabla_vacia())
    st.session_state.setdefault("comb_version", 0)
    st.session_state.setdefault("comb_cuota_img", None)

    # ---- 1. Foto ----
    _bloque_clave_api()
    foto = st.file_uploader("📷 Sube la foto de tu combinada y se analiza al instante",
                            type=["png", "jpg", "jpeg", "webp"], key="comb_foto")
    if foto is not None:
        datos = foto.getvalue()
        huella = hashlib.md5(datos).hexdigest()
        col_img, col_info = st.columns([1, 2])
        col_img.image(datos, width=240)
        with col_info:
            nueva = st.session_state.get("comb_foto_huella") != huella
            if nueva or st.button("🔄 Volver a leer la foto", key="comb_releer"):
                clave = _clave_api()
                if not clave:
                    st.error("Falta la clave de API. Ábrela en el recuadro «🔑» de arriba o escribe las patas a mano.")
                else:
                    st.session_state["comb_foto_huella"] = huella      # evita repetir la lectura en cada recarga
                    try:
                        with st.spinner("Leyendo y analizando la boleta..."):
                            tabla, cuota_total = leer_boleta(datos, clave)
                    except Exception as e:  # noqa: BLE001
                        st.error(f"No pude leer la foto: {e}")
                    else:
                        if tabla.empty:
                            st.warning("No encontré selecciones en la imagen. Prueba con una foto más nítida o escribe las patas a mano.")
                        else:
                            st.session_state["comb_tabla"] = tabla
                            st.session_state["comb_cuota_img"] = cuota_total
                            st.session_state["comb_version"] += 1
                            st.session_state["comb_analizar"] = True    # análisis inmediato
                            st.success(f"Encontré {len(tabla)} selección(es) y ya las analicé. Puedes corregir la tabla si algo no se leyó bien.")
            else:
                st.caption("Foto ya leída. Si quieres, corrige la tabla de abajo o vuelve a leerla.")

    # ---- 2. Tabla editable ----
    st.markdown("#### Patas de la combinada")
    st.caption("Corrige lo que haga falta o agrega filas con el botón ➕ de la tabla. En «Línea» pon el número de la apuesta (por ejemplo 24.5).")
    editada = st.data_editor(
        st.session_state["comb_tabla"], num_rows="dynamic", use_container_width=True, hide_index=True,
        key=f"comb_editor_{st.session_state['comb_version']}",
        column_config={
            "Jugador": st.column_config.TextColumn("Jugador", help="Nombre del jugador, por ejemplo Jalen Brunson"),
            "Mercado": st.column_config.SelectboxColumn("Mercado", options=list(MERCADOS) + [OTRO], default="Puntos", required=True),
            "Dirección": st.column_config.SelectboxColumn("Dirección", options=DIRECCIONES, default="Más de", required=True),
            "Línea": st.column_config.NumberColumn("Línea", step=0.5, format="%.1f"),
            "Cuota": st.column_config.NumberColumn("Cuota", min_value=1.0, step=0.01, format="%.2f", help="Cuota decimal de esta selección (opcional)"),
            "Detalle": st.column_config.TextColumn("Detalle"),
        })

    hoy = date.today()
    actual = hoy.year + (1 if hoy.month >= 10 else 0)
    opciones = list(range(actual, actual - 4, -1))
    c1, c2 = st.columns([3, 1])
    temporadas = c1.multiselect("Temporadas a revisar", opciones, default=opciones[:2], format_func=_etiqueta_temporada, key="comb_temporadas")
    playoffs = c2.toggle("Incluir playoffs", True, key="comb_playoffs")

    if st.button("📊 Analizar combinada", type="primary", key="comb_analizar_btn"):
        st.session_state["comb_analizar"] = True
    if not st.session_state.get("comb_analizar"):
        return

    # ---- 3. Análisis ----
    filas = [f for f in editada.to_dict("records") if str(f.get("Jugador") or "").strip() or _numero(f.get("Línea")) is not None]
    if not filas:
        st.info("Agrega al menos una pata en la tabla.")
        return
    if not temporadas:
        st.warning("Elige al menos una temporada.")
        return
    try:
        jugadores = h._jugadores()
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo cargar la lista de jugadores ({type(e).__name__}). Revisa la sección Diagnóstico.")
        return

    resultados = []   # (fila normalizada, info)
    with st.spinner("Revisando el historial de cada jugador..."):
        for f in filas:
            fila = {"Jugador": str(f.get("Jugador") or "").strip(), "Mercado": f.get("Mercado") or OTRO,
                    "Dirección": f.get("Dirección") or "Más de", "Línea": _numero(f.get("Línea")),
                    "Cuota": _numero(f.get("Cuota")), "Detalle": str(f.get("Detalle") or "")}
            if fila["Mercado"] not in MERCADOS:
                resultados.append((fila, {"estado": "otro"}))
                continue
            if fila["Línea"] is None:
                resultados.append((fila, {"estado": "falta_linea"}))
                continue
            jugador = buscar_jugador(fila["Jugador"], jugadores)
            if not jugador:
                resultados.append((fila, {"estado": "no_jugador"}))
                continue
            juegos = jg._historial_ordenado(jugador["id"], temporadas, playoffs)
            vals, ventanas = analizar_pata(juegos, fila["Mercado"], fila["Dirección"], fila["Línea"])
            prob = probabilidad(ventanas)
            if not vals or prob is None:
                resultados.append((fila, {"estado": "sin_partidos"}))
                continue
            fila["Jugador"] = jugador["nombre"]
            resultados.append((fila, {"estado": "ok", "equipo": jugador["equipo"], "vals": vals, "ventanas": ventanas, "prob": prob}))

    analizadas = [(f, i) for f, i in resultados if i["estado"] == "ok"]
    omitidas = sum(1 for _, i in resultados if i["estado"] == "otro")
    html_patas = "".join(_pata_html(k, f, i) for k, (f, i) in enumerate(resultados))

    if analizadas:
        cuotas = [f["Cuota"] for f, _ in resultados]
        producto = math.prod(cuotas) if cuotas and all(cuotas) else None
        por_defecto = st.session_state.get("comb_cuota_img") or producto or 0.0
        cuota_total = st.number_input("Cuota total de tu combinada (opcional)", min_value=0.0, value=float(round(por_defecto, 2)), step=0.05,
                                      key=f"comb_cuota_total_{st.session_state['comb_version']}_{round(por_defecto, 2)}",
                                      help="Se rellena sola con la cuota de la boleta o con el producto de las cuotas de cada pata.")
        st.markdown(_resumen_html(analizadas, omitidas, cuota_total or None), unsafe_allow_html=True)
    st.markdown(html_patas, unsafe_allow_html=True)
    st.caption("⚠️ Es una estimación basada solo en partidos pasados: no garantiza resultados y supone que las patas son independientes "
               "(las de un mismo partido suelen estar relacionadas). Úsalo como ayuda, no como seguridad, y apuesta con responsabilidad.")
