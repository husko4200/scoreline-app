"""Fútbol · tarjeta de línea de un equipo, con el mismo diseño que la de la NBA pero con datos de fútbol y fondo verde degradado.

Es autocontenida: devuelve el HTML y su propio CSS (clases `.ft-*`), así que no depende de `estilos.py` ni de la tarjeta de
`ficha_equipos.py`.

Uso (en football_lineas.render, en lugar de fe._tarjeta):

    col.markdown(football_tarjeta.tarjeta(eq, serie, m, umbral, lado, etiqueta, hand=ln, h2h=h2h,
                                          rival=(eq_rival, serie_rival), bajas=lista_de_bajas), unsafe_allow_html=True)

Igual que la NBA: encabezado con escudo brillante, la línea grande con su anillo de % de acierto, el banner, las barras de los
últimos partidos (verde = se cumplió, rojo = no) con la raya punteada de la línea, las insignias L/V dentro de cada barra y las marcas
de poco descanso, «Local vs visita» (resalta el mejor), contra quién no se cumplió, el panel «Rival frente a esta línea» (cuando
hay Equipo B), las bajas, los siete datos del mercado y el contexto del equipo. Los números de cada partido salen al pasar el mouse.
"""
import math
import re
from html import escape as _e
from statistics import mean, pstdev

_POCO_DESCANSO = 3        # días: con 3 o menos se considera poco descanso (jugó hace poco)
_PESO = 0.9               # ponderado: cada partido anterior pesa un 10 % menos que el siguiente
_MIN_GRUPO = 3            # menos partidos que esto en un grupo: su porcentaje no es confiable
_ALTO, _BAJO = 0.6, 0.4   # % desde el que un dato se pinta verde / rojo
_ALTO_GRAF = 230          # alto del gráfico de barras, en píxeles
_MAX_BAJAS = 6

# Dato del equipo -> dato equivalente del rival «frente a esta línea» (lo que sus rivales logran contra él)
_ESPEJO = {"pf": "pc", "pc": "pf", "p1": "pc1", "p2": "pc2", "pc1": "p1", "pc2": "p2",
           "tiros": "tiros_riv", "tiros_riv": "tiros", "tp": "tp_riv", "tp_riv": "tp", "corners": "corners_riv", "corners_riv": "corners",
           "faltas": "faltas_riv", "faltas_riv": "faltas", "amarillas": "amarillas_riv", "amarillas_riv": "amarillas",
           "rojas": "rojas_riv", "rojas_riv": "rojas", "tarjetas": "tarjetas_riv", "tarjetas_riv": "tarjetas", "tf": "tf_riv", "tf_riv": "tf",
           "anota": "rival_anota", "rival_anota": "anota"}
# Datos del partido entero: el rival tiene el mismo valor, así que se compara directamente con sus propios partidos
_SIMETRICOS = {"total", "t1", "t2", "tiros_tot", "tp_tot", "tf_tot", "corners_tot", "faltas_tot", "amarillas_tot", "rojas_tot", "tarjetas_tot",
               "pts_tarj_tot", "btts_si", "btts_no", "impar", "par", "hay_gol", "hay_gol_1t", "hay_gol_2t", "btts_1t", "btts_2t",
               "empate", "empate_1t", "no_empata", "rojas_partido", "mas_goles_1t", "mas_goles_2t"}

_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Source+Sans+3:wght@400;600;700;800&display=swap');
.ft{--c:#16a34a;--cond:"Barlow Condensed","Oswald","Archivo Narrow","Arial Narrow",sans-serif;font-family:"Source Sans 3","Source Sans Pro",Inter,system-ui,sans-serif;position:relative;overflow:hidden;box-sizing:border-box;
  margin:0 0 16px;padding:26px 24px 18px;border-radius:26px;color:#e8f5ee;font-size:14px;line-height:1.35;
  background:radial-gradient(520px 300px at 100% 0%,rgba(163,230,53,.20),transparent 68%),radial-gradient(560px 380px at 0% 100%,rgba(20,184,166,.18),transparent 70%),
    linear-gradient(155deg,#14573a 0%,#0c3d2b 42%,#062219 100%);
  border:1px solid rgba(134,239,172,.16);box-shadow:0 22px 44px -22px rgba(3,20,12,.85),inset 0 1px 0 rgba(255,255,255,.07)}
.ft::before{content:"";position:absolute;left:0;right:0;top:0;height:4px;background:linear-gradient(90deg,#86efac,#22c55e 45%,#2dd4bf)}
.ft *{box-sizing:border-box}
.ft b{font-weight:700}
.ft-top{display:flex;align-items:center;gap:18px}
.ft-lg{flex:none;width:96px;height:96px;border-radius:50%;background:radial-gradient(circle at 30% 25%,#fff,#e6ecf2);display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 0 4px rgba(255,255,255,.20),0 0 30px color-mix(in srgb,var(--c) 75%,transparent),0 10px 22px -8px rgba(0,0,0,.6)}
.ft-lg img{width:62px;height:62px;object-fit:contain;display:block}
.ft-nom{font-family:var(--cond);font-size:2.7rem;font-weight:800;letter-spacing:.02em;text-transform:uppercase;line-height:1;color:#fff;
  text-shadow:0 2px 0 rgba(0,0,0,.25)}
.ft-sub{margin-top:5px;font-size:.84rem;color:#9fc7b2}
.ft-box{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:20px 0 14px;padding:20px 26px;border-radius:20px;
  background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.10)}
.ft-pill{display:inline-block;padding:3px 13px;border-radius:99px;font-size:.66rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;
  background:rgba(34,197,94,.16);color:#6ee7a0;border:1px solid rgba(74,222,128,.5)}
.ft-pill.menos{background:rgba(248,113,113,.14);color:#fca5a5;border-color:rgba(248,113,113,.5)}
.ft-linea{margin-top:8px;font-family:var(--cond);font-size:5rem;font-weight:800;line-height:.95;color:#fff;font-variant-numeric:tabular-nums}
.ft-aro{flex:none;position:relative;width:132px;height:132px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  background:conic-gradient(var(--col) calc(var(--p) * 1%),rgba(255,255,255,.13) 0);filter:drop-shadow(0 0 10px color-mix(in srgb,var(--col) 40%,transparent))}
.ft-aro::before{content:"";position:absolute;inset:12px;border-radius:50%;background:#0c3a29}
.ft-aro div{position:relative;text-align:center;line-height:1.05}
.ft-aro b{display:block;font-size:2.1rem;font-weight:500;color:var(--col);letter-spacing:-.01em}
.ft-aro small{font-size:.62rem;font-weight:800;color:#9fc7b2}
.ft-banner{margin:0 0 4px;padding:10px 16px;border-radius:12px;font-size:.84rem;font-weight:800;color:#6ee7a0;background:rgba(34,197,94,.10);border:1px solid rgba(74,222,128,.32)}
.ft-banner.mal{color:#fca5a5;background:rgba(248,113,113,.10);border-color:rgba(248,113,113,.34)}
.ft-banner.med{color:#fcd34d;background:rgba(251,191,36,.10);border-color:rgba(251,191,36,.34)}
.ft-chart{position:relative;display:flex;gap:9px;height:230px;margin-top:26px;padding:0 4px;border-bottom:1px solid rgba(255,255,255,.18);
  background:linear-gradient(rgba(255,255,255,.07),rgba(255,255,255,.07)) 0 25%/100% 1px no-repeat,linear-gradient(rgba(255,255,255,.07),rgba(255,255,255,.07)) 0 50%/100% 1px no-repeat,
    linear-gradient(rgba(255,255,255,.07),rgba(255,255,255,.07)) 0 75%/100% 1px no-repeat}
.ft-linea-y{position:absolute;left:0;right:0;border-top:2px dashed rgba(250,204,21,.9);pointer-events:none;z-index:4}
.ft-linea-y::after{content:"";position:absolute;right:-5px;top:-7px;width:11px;height:11px;border-radius:50%;background:#facc15;box-shadow:0 0 0 2px #0b3426}
.ft-cero{position:absolute;left:0;right:0;border-top:1px solid rgba(255,255,255,.26);pointer-events:none;z-index:1}
.ft-col{position:relative;flex:1 1 0;min-width:0;height:100%}
.ft-bar{position:absolute;left:0;right:0;border-radius:11px 11px 3px 3px;background:linear-gradient(180deg,#4ade80,#15803d);box-shadow:0 0 14px -4px rgba(74,222,128,.55);transition:filter .15s}
.ft-bar.mal{background:linear-gradient(180deg,#d8566b,#7a1f35);box-shadow:none}
.ft-bar.neg{border-radius:3px 3px 11px 11px}
.ft-col:hover .ft-bar{filter:brightness(1.18)}
.ft-lv{position:absolute;left:50%;transform:translateX(-50%);width:21px;height:21px;border-radius:50%;display:flex;align-items:center;justify-content:center;z-index:3;
  font-size:.66rem;font-weight:800;color:#fff;background:#0284c7;box-shadow:0 0 0 2px rgba(255,255,255,.28)}
.ft-lv.v{background:#ea580c}.ft-lv.n{background:#64748b}
.ft-mk{position:absolute;left:50%;bottom:6px;transform:translateX(-50%);width:12px;height:12px;border-radius:50%;background:#facc15;box-shadow:0 0 0 3px rgba(0,0,0,.30);z-index:3}
.ft-tip{display:none;position:absolute;top:-6px;left:50%;transform:translate(-50%,-100%);width:max-content;max-width:230px;padding:8px 11px;border-radius:10px;z-index:20;
  background:#04130c;color:#e8f5ee;border:1px solid rgba(134,239,172,.35);font-size:.7rem;line-height:1.4;box-shadow:0 10px 24px -8px #000;pointer-events:none}
.ft-col:hover .ft-tip{display:block}
.ft-col.izq .ft-tip{left:0;transform:translate(0,-100%)}.ft-col.der .ft-tip{left:auto;right:0;transform:translate(0,-100%)}
.ft-tip b{display:block;font-size:.76rem;margin-bottom:2px}
.ft-eti{display:flex;gap:9px;padding:0 4px;margin-top:8px}
.ft-eti span{flex:1 1 0;min-width:0;text-align:center;font-size:.68rem;color:#9fc7b2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ft-leyenda{display:flex;flex-wrap:wrap;align-items:center;gap:16px;margin-top:14px;font-size:.74rem;color:#9fc7b2}
.ft-leyenda i{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:7px;vertical-align:-1px;background:#facc15}
.ft-tit{margin:26px 0 12px;font-size:.7rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#9fc7b2;display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.ft-tit em{font-style:normal;letter-spacing:0;text-transform:none;font-weight:800;font-size:.86rem;color:#fff}
.ft-tit i.n{font-style:normal;letter-spacing:0;text-transform:none;font-weight:600;font-size:.74rem;color:#8fb5a2;margin-left:4px}
.ft-tit.reg{justify-content:flex-start;gap:14px;align-items:center}.ft-tit.reg::after{content:"";flex:1;height:1px;background:rgba(255,255,255,.16)}
.ft-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.ft-sede{padding:14px 16px;border-radius:16px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.10)}
.ft-sede.top{border-color:rgba(74,222,128,.55);background:rgba(34,197,94,.09)}
.ft-sede-h{display:flex;justify-content:space-between;align-items:baseline;font-size:.74rem;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:#cfe8da}
.ft-sede-h b{font-size:1.2rem;letter-spacing:0;color:#fff}
.ft-prog{height:6px;margin:10px 0 7px;border-radius:99px;background:rgba(255,255,255,.12);overflow:hidden}
.ft-prog i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#22c55e,#86efac)}
.ft-prog.mal i{background:linear-gradient(90deg,#ef4444,#f87171)}.ft-prog.med i{background:linear-gradient(90deg,#f59e0b,#fbbf24)}
.ft-sede small{font-size:.72rem;color:#9fc7b2}
.ft-nota{margin-top:9px;font-size:.72rem;color:#9fc7b2}
.ft-chips{display:flex;flex-wrap:wrap;gap:7px}
.ft-chip{padding:4px 12px;border-radius:99px;font-size:.74rem;font-weight:700;background:rgba(190,60,80,.22);color:#fecdd3;border:1px solid rgba(248,113,113,.5);white-space:nowrap}
.ft-chip.neu{background:rgba(125,211,252,.12);color:#bae6fd;border-color:rgba(125,211,252,.35)}
.ft-chip.hl{background:rgba(129,140,248,.22);color:#c7d2fe;border-color:rgba(129,140,248,.6)}
.ft-chip.amar{background:rgba(251,191,36,.12);color:#fde68a;border-color:rgba(251,191,36,.5)}
.ft-x{color:#f87171;margin-right:3px}
.ft-riv{margin-top:24px;padding:16px 18px;border-radius:16px;background:rgba(0,0,0,.18);border:1px solid rgba(255,255,255,.10);border-left:4px solid var(--rc)}
.ft-riv-h{display:flex;justify-content:space-between;align-items:center;gap:8px}
.ft-riv-t{font-size:.7rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#e2f3ea}
.ft-riv-b{padding:3px 11px;border-radius:99px;font-size:.6rem;font-weight:800;letter-spacing:.09em;color:var(--rc);border:1px solid var(--rc);background:rgba(0,0,0,.22)}
.ft-riv-c{display:flex;align-items:center;gap:16px;margin:10px 0 12px}
.ft-riv-p{font-family:var(--cond);font-size:2.5rem;font-weight:700;color:var(--rc);line-height:1}
.ft-riv-x{font-size:.8rem;color:#cfe8da}
.ft-riv .ft-tit{margin:14px 0 8px}
.ft-aviso{margin-top:12px;padding:9px 14px;border-radius:12px;font-size:.76rem;font-weight:700;color:#fcd34d;background:rgba(251,191,36,.10);border:1px solid rgba(251,191,36,.35)}
.ft-bajas{margin-top:20px;padding:14px 18px;border-radius:16px;background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.10)}
.ft-prox{font-size:.92rem;font-weight:600;color:#f1faf5}.ft-prox span{color:#cfe8da;font-weight:400}
.ft-baj{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-top:9px}.ft-baj>b{font-size:.92rem;color:#f1faf5;margin-right:3px}
.ft-sp{height:20px}
.ft-sigue{margin-top:12px;font-size:.72rem;color:#8fb5a2}
.ft-tiles{display:grid;grid-template-columns:repeat(var(--n,6),minmax(0,1fr));gap:8px}
.ft-t{padding:11px 10px;border-radius:14px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.10)}
.ft-t small{display:block;font-size:.54rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#9fc7b2;margin-bottom:5px}
.ft-t b{font-family:var(--cond);font-size:1.5rem;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums;color:#fff}
.ft-t.ok b{color:#6ee7a0}.ft-t.mal b{color:#fb7185}.ft-t.med b{color:#fbbf24}
.ft-t em{display:block;margin-top:2px;font-style:normal;font-size:.68rem;font-weight:700;color:#9fc7b2}
.ft-t.ok em{color:#6ee7a0}.ft-t.mal em{color:#fb7185}.ft-t.med em{color:#fbbf24}
@media (max-width:640px){.ft-tiles{grid-template-columns:repeat(2,minmax(0,1fr)) !important}.ft-2{grid-template-columns:1fr}.ft-nom{font-size:2rem}.ft-linea{font-size:3.6rem}.ft-aro{width:100px;height:100px}.ft-aro::before{inset:10px}}
</style>"""


CSS = _CSS   # estilo de la tarjeta: dibújalo UNA vez por pantalla con st.markdown(football_tarjeta.CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _f(v, signo=False):
    """Número corto: sin decimales si es entero, con uno si no (el -0.0 se muestra como 0)."""
    if v is None:
        return "—"
    v = round(float(v), 1)
    v = 0.0 if v == 0 else v
    txt = f"{v:+.1f}" if signo else f"{v:.1f}"
    return txt[:-2] if txt.endswith(".0") else txt


def _d1(v, signo=False):
    """Siempre con un decimal (2.0, −1.0), como los datos de la tarjeta de la NBA."""
    v = round(float(v), 1)
    v = 0.0 if v == 0 else v
    return f"{v:+.1f}" if signo else f"{v:.1f}"


def _pct(x):
    return f"{round(x * 100):d}%"


def _clase(p):
    return "ok" if p >= _ALTO else "mal" if p <= _BAJO else "med"


def _cdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _pesos(n):
    return [_PESO ** (n - 1 - i) for i in range(n)]


def _color_ok(c):
    return c if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) else "#16a34a"


def _logo_ok(url):
    url = str(url or "")
    return url if (url.startswith("https://") or url.startswith("data:image/svg+xml;base64,")) and not any(c in url for c in "\"'()<> \\") else ""


def _acierta(v, umbral, lado, tipo):
    if v is None:
        return None
    if tipo in ("ganador", "handicap"):
        return v > umbral
    return v > umbral if lado == "Más de" else v < umbral


def _tendencia(vals):
    """Media de los 3 partidos más recientes menos la de los 3 primeros (con pocos partidos, mitad contra mitad)."""
    n = len(vals)
    if n < 4:
        return None
    k = 3 if n >= 6 else n // 2
    return mean(vals[-k:]) - mean(vals[:k])


def _racha(oks):
    """(cantidad, ¿se cumplió?) de la racha actual, contando desde el partido más reciente."""
    if not oks:
        return 0, True
    ult, n = oks[-1], 0
    for o in reversed(oks):
        if o != ult:
            break
        n += 1
    return n, ult


# ---------------------------------------------------------------------------
# Piezas
# ---------------------------------------------------------------------------
def _barras(juegos, umbral, lado, tipo, sn):
    """Barras de los partidos con la línea punteada. Verde = se cumplió (más intenso = más margen), rojo = no.

    Como en la NBA, las barras no llevan número: el detalle de cada partido sale al pasar el mouse. La insignia L/V va dentro de la barra
    (arriba) y la marca de poco descanso abajo; si la barra es muy baja, la insignia se pone justo encima."""
    vals = [g["v"] for g in juegos]
    if sn:
        lo, hi = -1.0, 1.0
    else:
        lo, hi = min(min(vals + [umbral]), 0.0), max(max(vals + [umbral]), 0.0)
    span = (hi - lo) or 1.0
    if lo < 0:
        lo -= span * 0.12   # espacio abajo para la insignia de las barras negativas
        span *= 1.12
    span *= 1.08
    pos = lambda x: (x - lo) / span * 100   # noqa: E731  (% desde abajo)
    base = pos(0.0)
    n = len(juegos)
    cols = []
    for i, g in enumerate(juegos):
        v, ok = g["v"], g["ok"]
        top, bot = (pos(v), base) if v >= 0 else (base, pos(v))
        alto = max(top - bot, 2.5)
        h_px = alto / 100 * _ALTO_GRAF
        fuerza = 0.62 + 0.38 * min(abs(v - umbral) / (span / 1.08 or 1), 1.0) if not sn else 1.0
        clase = ("" if ok else " mal") + (" neg" if v < 0 else "")
        if v < 0:
            lv_pos = f"bottom:calc({bot:.1f}% - 25px)"
        elif h_px >= 34:
            lv_pos = f"bottom:calc({top:.1f}% - 27px)"   # dentro de la barra, arriba
        else:
            lv_pos = f"bottom:calc({top:.1f}% + 4px)"    # barra muy baja: justo encima
        lv = f'<span class="ft-lv {g["sede_c"]}" style="{lv_pos}">{g["sede_l"]}</span>'
        marca = '<span class="ft-mk"></span>' if g["poco_desc"] and v >= 0 else ""
        pos_tip = " izq" if i < 2 else " der" if i >= n - 2 else ""
        tip = f'<div class="ft-tip"><b>{_e(g["etq"])} · {_e(g["rival"])}</b>{g["tip_html"]}</div>'
        cols.append(f'<div class="ft-col{pos_tip}">{tip}<div class="ft-bar{clase}" style="bottom:{bot:.1f}%;height:{alto:.1f}%;opacity:{fuerza:.2f}"></div>{lv}{marca}</div>')
    cero = f'<div class="ft-cero" style="bottom:{base:.1f}%"></div>' if lo < 0 else ""
    linea = "" if sn else f'<div class="ft-linea-y" style="bottom:{pos(umbral):.1f}%"></div>'
    eti = "".join(f'<span>{_e(g["etq"])}</span>' for g in juegos)
    return f'<div class="ft-chart">{cero}{linea}{"".join(cols)}</div><div class="ft-eti">{eti}</div>'


def _sede_html(juegos, sn=False):
    """«Local vs visita»: dos cuadros con su récord frente a la línea (el mejor resaltado) y un comentario comparándolos."""
    grupos = {}
    for clave, tit, icono in (("home", "Local", "🏠"), ("away", "Visita", "✈️")):
        js = [g for g in juegos if g["sede"] == clave]
        grupos[clave] = (tit, icono, js, sum(g["ok"] for g in js))
    (_, _, jl, kl), (_, _, jv, kv) = grupos["home"], grupos["away"]
    pl = kl / len(jl) if jl else None
    pv = kv / len(jv) if jv else None
    mejor = None if pl is None or pv is None or abs(pl - pv) < 0.15 else ("home" if pl > pv else "away")
    cuadros = []
    for clave in ("home", "away"):
        tit, icono, js, k = grupos[clave]
        if js:
            p = k / len(js)
            prom = mean(g["v"] for g in js)
            extra = "" if sn else f" · promedio {_d1(prom)}"
            cuadros.append(f'<div class="ft-sede{" top" if mejor == clave else ""}"><div class="ft-sede-h"><span>{icono} {tit}</span><b>{k}/{len(js)}</b></div>'
                           f'<div class="ft-prog {_clase(p)}"><i style="width:{p * 100:.0f}%"></i></div><small>{_pct(p)}{extra}</small></div>')
        else:
            cuadros.append(f'<div class="ft-sede"><div class="ft-sede-h"><span>{icono} {tit}</span><b>—</b></div><small>Sin partidos de esta sede</small></div>')
    if pl is not None and pv is not None:
        if mejor is None:
            titulo = f"Rinde parecido en casa y de visita ({_pct(pl)} · {_pct(pv)})"
        else:
            titulo = f"{'🏠' if mejor == 'home' else '✈️'} Se cumple más de {'local' if mejor == 'home' else 'visita'} ({_pct(max(pl, pv))} vs {_pct(min(pl, pv))})"
    else:
        titulo = ""
    return (f'<div class="ft-tit"><span>Local vs visita</span><em>{_e(titulo)}</em></div><div class="ft-2">{"".join(cuadros)}</div>'
            '<div class="ft-nota">En las barras, L = partido de local y V = de visita.</div>')


def _fallos_html(juegos, sn):
    fallos = [g for g in juegos if not g["ok"]]
    if not fallos:
        return '<div class="ft-tit"><span>✓ Se cumplió en todos los partidos</span></div>'
    chips = "".join(f'<span class="ft-chip">{_e(g["etq"])}{"" if sn else " · " + _f(g["v"])}</span>' for g in reversed(fallos))
    return (f'<div class="ft-tit"><span><span class="ft-x">✕</span> No se cumplió contra<i class="n">({len(fallos)} de {len(juegos)})</i></span></div>'
            f'<div class="ft-chips">{chips}</div>')


def _panel_rival(rival, campo, umbral, lado, tipo, p_equipo, sn, etiqueta, proximo=None):
    """«Rival frente a esta línea»: cuántas veces se dio esta línea en los partidos del rival (lo que sus oponentes logran contra él)."""
    if not rival or tipo not in ("linea", "ganador") or (tipo == "ganador" and not sn):
        return ""
    eq_r, serie_r = rival
    campo_r = campo if campo in _SIMETRICOS else _ESPEJO.get(campo)
    if not campo_r or not serie_r:
        return ""
    js = []
    for g in serie_r:
        v = g.get(campo_r)
        if v is None:
            continue
        js.append({"v": float(v), "ok": _acierta(float(v), umbral, lado, tipo), "sede": g.get("sede"), "etq": g.get("etq", "")})
    if len(js) < 3:
        return ""
    k = sum(j["ok"] for j in js)
    p = k / len(js)
    ab = _e(eq_r.get("abbr") or eq_r.get("nombre", "RIV"))
    estado, col = ("A FAVOR", "#4ade80") if p >= _ALTO else ("EN CONTRA", "#f87171") if p <= _BAJO else ("NEUTRO", "#fbbf24")
    mercado = _e(str(etiqueta).split(" · ")[0])
    if sn:
        texto = f"Se dio en <b>{k} de {len(js)}</b> partidos de {ab} («{mercado}»)."
    else:
        verbo = "superó" if lado == "Más de" else "quedó por debajo de"
        texto = (f"Se dio en <b>{k} de {len(js)}</b> partidos de {ab}, su rival {verbo} {_f(umbral)} en «{mercado}». "
                 f"Promedio de {ab} en esto: <b>{_d1(mean(j['v'] for j in js))}</b> (línea {_f(umbral)}).")
    # si el próximo partido del equipo es justo contra este rival, se resalta la sede en que el rival lo jugará
    juega_vs_rival = bool(proximo and eq_r.get("espn_id") and str(proximo.get("rival_id")) == str(eq_r.get("espn_id")))
    sede_rival = ("away" if proximo.get("sede") == "home" else "home") if juega_vs_rival else None
    chips = []
    for clave, txt, ico in (("home", "en casa", "🏠"), ("away", "de visita", "✈️")):
        g = [j for j in js if j["sede"] == clave]
        if g:
            ya = clave == sede_rival
            marca = f' · {"hoy " if proximo.get("cuando") == "hoy" else ""}juega así' if ya else ""
            chips.append(f'<span class="ft-chip {"hl" if ya else "neu"}">{ico} {ab} {txt}: {sum(j["ok"] for j in g)} de {len(g)}{marca}</span>')
    fallos = [j for j in js if not j["ok"]]
    bloque_fallos = ""
    if fallos:
        c = "".join(f'<span class="ft-chip">{_e(j["etq"])}{"" if sn else " · " + _f(j["v"])}</span>' for j in reversed(fallos))
        bloque_fallos = (f'<div class="ft-tit"><span><span class="ft-x">✕</span> No se dio contra (partidos de {ab})<i class="n">({len(fallos)} de {len(js)})</i></span></div>'
                         f'<div class="ft-chips">{c}</div>')
    aviso = ""
    if (p_equipo >= 0.5 and p <= 0.3) or (p_equipo <= 0.3 and p >= 0.5):
        cuerpo = (f"el equipo cumple la línea, pero los partidos de {ab} van en contra" if p_equipo >= 0.5
                  else f"el equipo no la cumple, pero los partidos de {ab} van a favor")
        aviso = f'<div class="ft-aviso">⚠ Se contradicen: {cuerpo}.</div>'
    sigue = (f'<div class="ft-sigue">Próximo partido ({_e(str(proximo.get("cuando", "")))}): vs {ab}</div>' if juega_vs_rival else "")
    return (f'<div class="ft-riv" style="--rc:{col}"><div class="ft-riv-h"><span class="ft-riv-t">🆚 Rival: {ab} frente a esta línea</span>'
            f'<span class="ft-riv-b">{estado}</span></div><div class="ft-riv-c"><span class="ft-riv-p">{_pct(p)}</span>'
            f'<span class="ft-riv-x">{texto}</span></div><div class="ft-chips">{"".join(chips)}</div>{bloque_fallos}{aviso}{sigue}</div>')


def _extra_html(bajas, proximo, serie, h2h):
    """Recuadro de debajo del panel del rival: el próximo partido (con días de descanso y partidos de la última semana) y las bajas.

    Como en la NBA: «📅 Próximo (hoy): vs MCI · 1 día de descanso · 3 partidos en los últimos 7 días» y «🩹 Bajas (n)» con un chip por jugador
    (los «Out» y sancionados en rojo; dudas y «día a día» en amarillo)."""
    linea_prox = ""
    if proximo and proximo.get("fecha") is not None:
        partes = [f'vs {_e(str(proximo.get("rival", "?")))}' if proximo.get("sede") == "home" else f'@ {_e(str(proximo.get("rival", "?")))}']
        if not h2h:   # con «enfrentamientos directos» la serie no es la agenda real del equipo
            dias = [g["dia"] for g in serie if g.get("dia") is not None and g["dia"] < proximo["fecha"]]
            if dias:
                desc = (proximo["fecha"] - max(dias)).days - 1
                partes.append(f"{desc} día{'s' if desc != 1 else ''} de descanso")
                sem = sum(1 for d in dias if (proximo["fecha"] - d).days <= 7)
                partes.append(f"{sem} partido{'s' if sem != 1 else ''} en los últimos 7 días")
        linea_prox = f'<div class="ft-prox">📅 Próximo ({_e(str(proximo.get("cuando", "")))}): <span>{" · ".join(partes)}</span></div>'
    linea_baj = ""
    if bajas:
        def grav(b):
            e = str(b.get("Estado", "")).lower()
            return 0 if ("out" in e or "suspen" in e) else 1
        orden = sorted(bajas, key=lambda b: (grav(b), b.get("Jugador", "")))
        chips = "".join(f'<span class="ft-chip{"" if grav(b) == 0 else " amar"}">{_e(b.get("Jugador", "?"))} · {_e(str(b.get("Estado", "")))}</span>'
                        for b in orden[:_MAX_BAJAS])
        if len(orden) > _MAX_BAJAS:
            chips += f'<span class="ft-chip neu">+{len(orden) - _MAX_BAJAS} más</span>'
        linea_baj = f'<div class="ft-baj"><b>🩹 Bajas ({len(orden)}):</b>{chips}</div>'
    return f'<div class="ft-bajas">{linea_prox}{linea_baj}</div>' if (linea_prox or linea_baj) else ""


def _grid(tiles):
    """Cuadros en una sola fila (7 en «Datos del mercado», 6 en «Contexto»); en pantallas angostas pasan a 2 columnas."""
    return f'<div class="ft-tiles" style="--n:{max(len(tiles), 1)}">{"".join(tiles)}</div>'


def _tile(titulo, valor, clase="", sub=""):
    return f'<div class="ft-t {clase}"><small>{_e(titulo)}</small><b>{_e(str(valor))}</b>{f"<em>{_e(sub)}</em>" if sub else ""}</div>'


def _tiles_datos(juegos, umbral, lado, tipo, sn, prob_equipo):
    vals = [g["v"] for g in juegos]
    oks = [1.0 if g["ok"] else 0.0 for g in juegos]
    w = _pesos(len(juegos))
    sw = sum(w)
    if sn:   # sí/no: no tiene sentido promediar los +1/−1, se resumen los aciertos
        k = int(sum(oks))
        pond = sum(wi * o for wi, o in zip(w, oks)) / sw
        n_r, cumplio = _racha([bool(o) for o in oks])
        tr = _tendencia(oks)
        return ([
            _tile("Se cumplió", f"{k}/{len(oks)}", _clase(k / len(oks)), _pct(k / len(oks))),
            _tile("Ponderado", _pct(pond), _clase(pond), "pesan más los últimos"),
            _tile("Racha actual", f"{n_r} {'✓' if cumplio else '✗'}", "ok" if cumplio else "mal"),
            _tile("Tendencia", "—" if tr is None else f"{'↑' if tr > 0 else '↓' if tr < 0 else '→'} {abs(tr) * 100:.0f} pp", "" if tr is None else "ok" if tr > 0.05 else "mal" if tr < -0.05 else ""),
            _tile("Prob. estimada", _pct(prob_equipo), _clase(prob_equipo)),
        ])
    prom = mean(vals)
    pond = sum(wi * v for wi, v in zip(w, vals)) / sw
    sd = pstdev(vals) if len(vals) > 1 else 0.0
    margen = (prom - umbral) if (lado == "Más de" or tipo == "handicap") else (umbral - prom)
    tr = _tendencia(vals)
    tr_ok = None if tr is None else (tr if lado == "Más de" or tipo == "handicap" else -tr)
    justa = round(pond * 2) / 2
    return ([
        _tile("Margen medio vs línea", _d1(margen, True), "ok" if margen > 0 else "mal" if margen < 0 else ""),
        _tile("Promedio", _d1(prom)),
        _tile("Ponderado", _d1(pond), "", "pesan más los últimos"),
        _tile("Variación (±)", _d1(sd)),
        _tile("Tendencia", "—" if tr is None else f"{'↑' if tr > 0 else '↓' if tr < 0 else '→'} {_d1(tr, True)}",
              "" if tr_ok is None else "ok" if tr_ok > 0 else "mal" if tr_ok < 0 else ""),
        _tile("Línea justa", _f(justa)),
        _tile("Prob. estimada", _pct(prob_equipo), _clase(prob_equipo)),
    ])


def _prob(juegos, umbral, lado, tipo, sn):
    """Probabilidad de que se cumpla. Datos con escala: curva normal con el promedio ponderado y la variación; sí/no: acierto ponderado suavizado."""
    w = _pesos(len(juegos))
    if sn or len(juegos) < 3:
        return (sum(wi * g["ok"] for wi, g in zip(w, juegos)) + 1) / (sum(w) + 2)
    vals = [g["v"] for g in juegos]
    pond = sum(wi * v for wi, v in zip(w, vals)) / sum(w)
    sd = pstdev(vals)
    if sd < 1e-9:
        return 1.0 if _acierta(pond, umbral, lado, tipo) else 0.0
    mas = 1 - _cdf((umbral - pond) / sd)
    return mas if (lado == "Más de" or tipo in ("handicap", "ganador")) else 1 - mas


def _contexto(serie, juegos):
    """Datos del equipo en esos partidos: descanso, goles y récord (no dependen del mercado elegido)."""
    pd_ = [g for g in juegos if g["desc"] is not None and g["desc"] <= _POCO_DESCANSO]
    cd = [g for g in juegos if g["desc"] is not None and g["desc"] > _POCO_DESCANSO]

    def tile_grupo(titulo, js):
        if not js:
            return _tile(titulo, "—", "", "sin partidos")
        k = sum(g["ok"] for g in js)
        return _tile(titulo, f"{k}/{len(js)}", _clase(k / len(js)), _pct(k / len(js)))

    con_marcador = [g for g in serie if g.get("pf") is not None and g.get("pc") is not None]
    tiles = [tile_grupo("⏱ Poco descanso", pd_), tile_grupo("😴 Con descanso", cd)]
    if con_marcador:
        gf, gc = mean(g["pf"] for g in con_marcador), mean(g["pc"] for g in con_marcador)
        gan = sum(g["pf"] > g["pc"] for g in con_marcador)
        emp = sum(g["pf"] == g["pc"] for g in con_marcador)
        per = len(con_marcador) - gan - emp
        cero = sum(g["pc"] == 0 for g in con_marcador)
        tiles += [_tile("⚽ Goles a favor", _d1(gf)), _tile("🧤 Goles en contra", _d1(gc)),
                  _tile("📊 Récord (G-E-P)", f"{gan}-{emp}-{per}", "ok" if gan / len(con_marcador) >= _ALTO else "mal" if gan / len(con_marcador) <= _BAJO else ""),
                  _tile("🧱 Portería a cero", f"{cero}/{len(con_marcador)}", _clase(cero / len(con_marcador)), _pct(cero / len(con_marcador)))]
    poca = [titulo for titulo, js in (("poco descanso", pd_), ("con descanso", cd)) if 0 < len(js) < _MIN_GRUPO]
    return tiles, poca


# ---------------------------------------------------------------------------
# Tarjeta
# ---------------------------------------------------------------------------
def tarjeta(eq, serie, m, umbral, lado, etiqueta, hand=None, h2h=False, rival=None, bajas=None, proximo=None):
    """HTML de la tarjeta de un equipo. `serie` = lista de partidos (football_lineas._serie), `umbral` = valor que hay que superar,
    `lado` = «Más de» / «Menos de», `hand` = hándicap elegido (solo en los mercados de hándicap), `rival` = (equipo, serie) del Equipo B,
    `bajas` = lista [{Jugador, Estado}] de lesionados/sancionados (opcional), `proximo` = próximo partido del equipo
    {cuando, rival, rival_id, sede, fecha} (opcional). Devuelve solo el HTML de la tarjeta: el estilo (CSS) va aparte, una vez por pantalla."""
    campo = getattr(m, "campo", None) or getattr(m, "clave", "")
    tipo = getattr(m, "tipo", "linea") or "linea"
    datos = [g for g in serie if g.get(campo) is not None]
    if not datos:
        return f'<div class="ft"><div class="ft-nom">{_e(eq.get("nombre", ""))}</div><div class="ft-sub">Sin datos de este mercado en estos partidos.</div></div>'
    sn = tipo == "ganador" and all(abs(abs(float(g[campo])) - 1) < 1e-9 for g in datos)   # +1 se cumplió / −1 no

    juegos = []
    for g in datos:
        v = float(g[campo])
        ok = bool(_acierta(v, umbral, lado, tipo))
        sede = g.get("sede", "neutral")
        marg = v - umbral
        pf, pc = g.get("pf"), g.get("pc")
        dia = g.get("dia")
        desc = g.get("desc")
        sede_txt = {"home": "🏠 Local", "away": "✈️ Visita"}.get(sede, "Cancha neutral")
        lineas_tip = [f'{"✅ Cumple" if ok else "❌ No cumple"}' + ("" if sn else f' · <b style="display:inline">{_f(v)}</b> ({"+" if marg >= 0 else "−"}{_f(abs(marg))} vs la línea)')]
        lineas_tip.append(" · ".join(x for x in (f"{dia:%d/%m/%y}" if dia is not None else "", f"Resultado {pf}-{pc}" if pf is not None and pc is not None else "", sede_txt) if x))
        if desc is not None:
            lineas_tip.append(f"{desc} días de descanso" + (" ⏱" if desc <= _POCO_DESCANSO else ""))
        juegos.append({"v": v, "ok": ok, "sede": sede, "etq": g.get("etq", ""), "rival": g.get("rival", ""), "desc": desc,
                       "poco_desc": desc is not None and desc <= _POCO_DESCANSO,
                       "sede_l": {"home": "L", "away": "V"}.get(sede, "N"), "sede_c": {"home": "l", "away": "v"}.get(sede, "n"),
                       "tip_html": "".join(f"<div>{x}</div>" for x in lineas_tip)})
    n, k = len(juegos), sum(j["ok"] for j in juegos)
    p = k / n
    prob = _prob(juegos, umbral, lado, tipo, sn)

    # --- línea grande ---
    if tipo == "handicap":
        h = hand if hand is not None else -umbral
        pill, grande, clase_pill = "HÁNDICAP", _f(h, True), ""
    elif sn or tipo == "ganador":
        pill, grande, clase_pill = str(getattr(m, "tag", None) or "SE CUMPLE"), str(getattr(m, "grande", None) or "Sí"), ""
    else:
        pill, grande = ("MÁS DE", _f(umbral)) if lado == "Más de" else ("MENOS DE", _f(umbral))
        clase_pill = "" if lado == "Más de" else " menos"
    col_aro = "#4ade80" if p >= _ALTO else "#fb7185" if p <= _BAJO else "#fbbf24"
    verbo = getattr(m, "verbo", None) if sn else None
    if verbo:
        banner_txt = f"{verbo} {k} de {n} partidos"
    elif tipo == "linea":
        banner_txt = f"{'Superó' if lado == 'Más de' else 'Se quedó por debajo de'} la línea en {k} de {n}"
    else:
        banner_txt = f"Se cumplió en {k} de {n} partidos"

    color = _color_ok(eq.get("color"))
    logo = _logo_ok(eq.get("logo"))
    img = f'<img src="{_e(logo)}" alt="">' if logo else f'<b style="color:#334155">{_e(eq.get("abbr", ""))}</b>'
    sub = f'{_e(etiqueta)} · {"enfrentamientos directos" if h2h else f"últimos {n} partidos"}'

    ctx, poca = _contexto(serie, juegos)
    hay_marcas = any(j["poco_desc"] for j in juegos)
    leyenda = (f'<div class="ft-leyenda"><span>Marcas en las barras:</span><span><i></i>poco descanso (≤{_POCO_DESCANSO} días)</span></div>'
               if hay_marcas else "")
    aviso_grupos = ""
    pocos = [t for t, js in (("local", [j for j in juegos if j["sede"] == "home"]), ("visita", [j for j in juegos if j["sede"] == "away"])) if 0 < len(js) < _MIN_GRUPO] + poca
    if pocos:
        aviso_grupos = f'<div class="ft-aviso">⚠ Algún grupo tiene menos de {_MIN_GRUPO} partidos: su porcentaje no es confiable.</div>'

    partes = [
        f'<div class="ft" style="--c:{color}">',
        f'<div class="ft-top"><div class="ft-lg">{img}</div><div><div class="ft-nom">{_e(eq.get("nombre", ""))}</div><div class="ft-sub">{sub}</div></div></div>',
        f'<div class="ft-box"><div><span class="ft-pill{clase_pill}">{_e(pill)}</span><div class="ft-linea">{_e(grande)}</div></div>'
        f'<div class="ft-aro" style="--p:{p * 100:.0f};--col:{col_aro}"><div><b>{_pct(p)}</b><small>{k} de {n}</small></div></div></div>',
        f'<div class="ft-banner {_clase(p)}">{_e(banner_txt)}</div>',
        _barras(juegos, umbral, lado, tipo, sn), leyenda,
        _sede_html(juegos, sn), _fallos_html(juegos, sn),
        _panel_rival(rival, campo, umbral, lado, tipo, p, sn, etiqueta, proximo),
        _extra_html(bajas, proximo, serie, h2h),
        f'<div class="ft-sp"></div>{_grid(_tiles_datos(juegos, umbral, lado, tipo, sn, prob))}',
        f'<div class="ft-tit reg"><span>Contexto del partido</span></div>{_grid(ctx)}', aviso_grupos, "</div>",
    ]
    return "".join(partes)
