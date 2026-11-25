"""Tarjeta de línea como imagen PNG, lista para enviar por WhatsApp/Telegram.

Solo usa Pillow (ya viene con Streamlit). El dibujo es una función pura:  crear_png(datos, foto=None) -> bytes
así que se puede probar sin Streamlit. La parte de Streamlit (botón, vista previa, descarga) está en  panel_imagen().

Fuentes: si pones una carpeta «fuentes» junto a este archivo con Inter-Regular.ttf, Inter-SemiBold.ttf e Inter-ExtraBold.ttf se usan esas;
si no, se busca Segoe UI / Arial / DejaVu del sistema, y como último recurso la fuente interna de Pillow.
"""
from __future__ import annotations

import io
import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, S = 1080, 1500, 2          # tamaño final y factor de supersampling (se dibuja al doble y se reduce: bordes suaves)
_AQUI = os.path.dirname(os.path.abspath(__file__))

C = dict(fondo=(11, 15, 32), panel=(20, 26, 51), linea=(39, 48, 90), texto=(238, 240, 248), suave=(143, 151, 184),
         cuerpo=(201, 206, 230), azul=(58, 155, 232), lila=(124, 134, 216), verde=(95, 216, 164), ambar=(242, 193, 78),
         rojo=(240, 101, 122), naranja=(242, 112, 74))

# Color de cada equipo (solo para el resplandor del fondo)
EQUIPO_COLOR = {
    "ATL": (225, 68, 52), "BOS": (0, 150, 70), "BKN": (150, 150, 160), "CHA": (29, 140, 171), "CHI": (206, 17, 65),
    "CLE": (160, 30, 80), "DAL": (0, 110, 190), "DEN": (80, 140, 230), "DET": (200, 16, 46), "GSW": (255, 199, 44),
    "HOU": (206, 17, 65), "IND": (253, 187, 48), "LAC": (200, 16, 46), "LAL": (120, 70, 190), "MEM": (93, 118, 169),
    "MIA": (200, 30, 70), "MIL": (0, 130, 70), "MIN": (35, 97, 146), "NOP": (180, 150, 90), "NYK": (245, 132, 38),
    "OKC": (0, 122, 193), "ORL": (0, 125, 197), "PHI": (0, 107, 182), "PHX": (229, 95, 32), "POR": (224, 58, 62),
    "SAC": (120, 90, 160), "SAS": (196, 206, 211), "TOR": (206, 17, 65), "UTA": (80, 60, 160), "WAS": (0, 43, 92),
}

_FUENTES = {
    400: ["fuentes/Inter-Regular.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc",
          "/usr/share/fonts/opentype/inter/Inter-Regular.otf"],
    600: ["fuentes/Inter-SemiBold.ttf", "seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Helvetica.ttc",
          "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"],
    800: ["fuentes/Inter-ExtraBold.ttf", "seguibl.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Helvetica.ttc",
          "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"],
}


@lru_cache(maxsize=64)
def _f(peso: int, px: int):
    for cand in _FUENTES[peso]:
        ruta = cand if os.path.isabs(cand) else os.path.join(_AQUI, cand)
        for r in (ruta, cand):
            try:
                return ImageFont.truetype(r, px * S)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=px * S)
    except TypeError:   # Pillow antiguo
        return ImageFont.load_default()


def _mezcla(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ----------------------------------------------------------------------------------------------------------------------------
# Veredicto (lógica pura)
# ----------------------------------------------------------------------------------------------------------------------------
def veredicto(d: dict):
    """(texto, color) según la simulación (o el historial si no hay) frente al punto de equilibrio de la cuota (50 % sin cuota)."""
    est = d.get("estado_jugador") or {}
    p = est.get("p_juega")
    if p is not None and p <= 0:
        return "No jugar: el jugador está fuera", "rojo"
    ref = 100 / d["cuota"] if d.get("cuota") and d["cuota"] > 1 else 50.0
    base = d["sim"] if d.get("sim") is not None else d["hist"]
    edge = base - ref
    rmin = d.get("rmin")
    if edge >= 5 and (rmin is None or rmin >= ref - 5):
        txt, col = "Línea fiable", "verde"
    elif edge >= 0:
        txt, col = "Línea fiable, con margen justo", "verde"
    else:
        txt, col = "Línea no fiable", "rojo"
    if col == "verde" and p is not None and p < 1:
        txt, col = txt + " · si juega", "ambar"
    return txt, col


def valor_esperado(d: dict):
    """Valor esperado por unidad apostada (en %), usando la simulación (o el historial). None sin cuota."""
    if not d.get("cuota") or d["cuota"] <= 1:
        return None
    base = d["sim"] if d.get("sim") is not None else d["hist"]
    return (base / 100 * d["cuota"] - 1) * 100


# ----------------------------------------------------------------------------------------------------------------------------
# Lienzo
# ----------------------------------------------------------------------------------------------------------------------------
class _L:
    def __init__(self, color_eq):
        self.im = Image.new("RGB", (W * S, H * S), C["fondo"])
        # degradado vertical suave
        g = Image.linear_gradient("L").resize((W * S, H * S))
        self.im.paste(Image.new("RGB", (W * S, H * S), (22, 27, 58)), (0, 0), g.point(lambda v: int(v * 0.55)))
        # resplandor del color del equipo arriba a la derecha y uno cálido abajo a la izquierda
        self._glow((W - 60, 40), 620, color_eq, 120)
        self._glow((0, H), 520, (110, 40, 90), 70)
        self.d = ImageDraw.Draw(self.im)

    def _glow(self, centro, radio, color, alfa):
        m = Image.new("L", self.im.size, 0)
        ImageDraw.Draw(m).ellipse([(centro[0] - radio) * S, (centro[1] - radio) * S, (centro[0] + radio) * S, (centro[1] + radio) * S], fill=alfa)
        m = m.filter(ImageFilter.GaussianBlur(radio * S * 0.45))
        self.im.paste(Image.new("RGB", self.im.size, color), (0, 0), m)

    def rr(self, box, r, fill=None, outline=None, w=2):
        x0, y0, x1, y1 = [v * S for v in box]
        self.d.rounded_rectangle([x0, y0, x1, y1], r * S, fill=fill, outline=outline, width=w * S)

    def txt(self, x, y, s, peso, px, fill, anchor="ls"):
        self.d.text((x * S, y * S), str(s), font=_f(peso, px), fill=fill, anchor=anchor)

    def ancho(self, s, peso, px):
        return self.d.textlength(str(s), font=_f(peso, px)) / S

    def parrafo(self, x, y, s, peso, px, fill, ancho, interlineal, max_lineas):
        """Texto con saltos de línea automáticos; devuelve cuántas líneas dibujó."""
        pal, linea, n = str(s).split(), "", 0
        for p in pal:
            t = f"{linea} {p}".strip()
            if self.ancho(t, peso, px) > ancho and linea:
                if n + 1 >= max_lineas:
                    linea = linea.rstrip(",.;") + "…"
                    self.txt(x, y + n * interlineal, linea, peso, px, fill)
                    return n + 1
                self.txt(x, y + n * interlineal, linea, peso, px, fill)
                n, linea = n + 1, p
            else:
                linea = t
        if linea and n < max_lineas:
            self.txt(x, y + n * interlineal, linea, peso, px, fill)
            n += 1
        return n

    def salida(self) -> bytes:
        out = self.im.resize((W, H), Image.LANCZOS)
        buf = io.BytesIO()
        out.save(buf, "PNG", optimize=True)
        return buf.getvalue()


# ----------------------------------------------------------------------------------------------------------------------------
# La tarjeta
# ----------------------------------------------------------------------------------------------------------------------------
def crear_png(d: dict, foto: bytes | None = None) -> bytes:
    """Dibuja la tarjeta. `d` (todo texto/números simples):

      nombre, equipo, partido (texto libre: «OKC @ MIA · dom 22 nov»), stat (p. ej. «puntos»), lado («Más de»/«Menos de»), linea,
      cuota (float o None), hist (%), sim (% o None), pond (% o None), rmin, rmax, k, n, ventana,
      estado_jugador ({estado, detalle, p_juega} o None), rol, prom_min, titular (True/False/None),
      rival, sede, defensor (texto libre), bajas_rival [texto], bajas_propias [texto], notas [texto]
    """
    L = _L(EQUIPO_COLOR.get(str(d.get("equipo", "")).upper(), (79, 70, 229)))
    P = 72
    ver_txt, ver_col = veredicto(d)
    col = C[ver_col]

    # ---- encabezado
    L.txt(P, 92, d["nombre"], 600, 26, C["texto"])
    L.txt(P + L.ancho(d["nombre"], 600, 26), 92, f" · {d.get('equipo', '')}", 400, 26, C["suave"])
    L.parrafo(P, 128, d.get("partido", ""), 400, 22, C["suave"], 500, 30, 2)

    # ---- rostro
    bx0, by0, bx1, by1 = 604, 44, 1008, 556
    panel = Image.new("RGBA", ((bx1 - bx0) * S, (by1 - by0) * S))
    eq = EQUIPO_COLOR.get(str(d.get("equipo", "")).upper(), (79, 70, 229))
    grad = Image.linear_gradient("L").rotate(0).resize(panel.size)
    panel.paste(Image.new("RGBA", panel.size, _mezcla(C["panel"], eq, 0.55) + (255,)), (0, 0))
    panel.paste(Image.new("RGBA", panel.size, C["panel"] + (255,)), (0, 0), grad)
    if foto:
        try:
            f = Image.open(io.BytesIO(foto)).convert("RGBA")
            esc = panel.size[0] / f.width * 1.08
            f = f.resize((round(f.width * esc), round(f.height * esc)), Image.LANCZOS)
            panel.alpha_composite(f, ((panel.size[0] - f.width) // 2, max(0, int(S * 30))))
        except Exception:  # noqa: BLE001 - foto dañada: se deja el fondo
            foto = None
    if not foto:
        ini = "".join(x[0] for x in d["nombre"].split()[:3]).upper()
        dd = ImageDraw.Draw(panel)
        dd.text((panel.size[0] // 2, panel.size[1] // 2), ini, font=_f(800, 150), fill=(255, 255, 255, 40), anchor="mm")
    vel = Image.linear_gradient("L").resize((panel.size[0], 190 * S))
    sombra = Image.new("RGBA", vel.size, C["fondo"] + (255,))
    sombra.putalpha(vel.point(lambda v: int(v * 0.95)))
    panel.alpha_composite(sombra, (0, panel.size[1] - vel.size[1]))
    mascara = Image.new("L", panel.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, panel.size[0] - 1, panel.size[1] - 1], 36 * S, fill=255)
    L.im.paste(panel.convert("RGB"), (bx0 * S, by0 * S), mascara)
    L.rr((bx0, by0, bx1, by1), 36, outline=C["linea"], w=2)

    # ---- héroe: lado, línea, estadística y cuota
    L.txt(P, 262, d["lado"], 400, 36, C["suave"])
    L.txt(P - 8, 450, f"{d['linea']:g}", 800, 210, C["texto"])
    L.txt(P, 512, d["stat"], 600, 40, C["texto"])
    if d.get("cuota"):
        L.txt(P + L.ancho(d["stat"], 600, 40), 512, f" · cuota {d['cuota']:.2f}", 400, 40, C["suave"])

    # ---- veredicto
    wv = L.ancho(ver_txt, 600, 30) + 88
    L.rr((P, 552, P + wv, 622), 35, fill=_mezcla(C["fondo"], col, 0.14), outline=col, w=2)
    L.d.ellipse([(P + 26) * S, (587 - 8) * S, (P + 42) * S, (587 + 8) * S], fill=col)
    L.txt(P + 58, 598, ver_txt, 600, 30, col)

    # ---- barras de probabilidad
    cuota = d.get("cuota")
    eq_pct = 100 / cuota if cuota and cuota > 1 else 50.0
    ev = valor_esperado(d)
    L.txt(P, 688, "¿Cuánto necesita acertar para que valga la pena?", 600, 28, C["texto"])
    sub = (f"Con cuota {cuota:.2f} basta con superar {eq_pct:.1f}%." if cuota and cuota > 1 else "Sin cuota: se usa 50% como referencia.")
    if ev is not None:
        sub += f" Valor esperado: {ev:+.1f}%."
    L.txt(P, 724, sub, 400, 22, C["suave"])
    filas = [("Historial", d["hist"], C["azul"])]
    if d.get("sim") is not None:
        filas.append(("Simulación", d["sim"], C["lila"]))
    if d.get("pond") is not None:
        filas.append(("Reciente ponderado", d["pond"], C["verde"]))
    bx, bw, y0 = P + 290, W - P * 2 - 290 - 100, 790
    for i, (et, v, c) in enumerate(filas):
        y = y0 + i * 58
        L.txt(P, y + 8, et, 400, 23, C["cuerpo"])
        L.rr((bx, y - 10, bx + bw, y + 10), 10, fill=C["panel"])
        L.rr((bx, y - 10, bx + max(20, bw * v / 100), y + 10), 10, fill=c)
        L.txt(W - P, y + 11, f"{v:g}%", 800, 32, C["texto"], "rs")
    xe = bx + bw * eq_pct / 100
    yb = y0 + (len(filas) - 1) * 58 + 30
    for yy in range(y0 - 28, yb, 14):   # línea punteada del equilibrio
        L.d.line([xe * S, yy * S, xe * S, (yy + 8) * S], fill=C["naranja"], width=3 * S)
    L.txt(xe, yb + 26, f"equilibrio {eq_pct:.1f}%", 600, 20, C["naranja"], "ms")
    rango = f" · rango probable {d['rmin']}–{d['rmax']}%" if d.get("rmin") is not None else ""
    L.txt(P, 998, f"Superó la línea en {d['k']} de {d['n']} (últimos {d.get('ventana', d['n'])}){rango}", 400, 22, C["suave"])

    # ---- tarjetas de contexto
    est = d.get("estado_jugador")
    l1 = [(f"{est['estado']}" + (f" · {est['detalle']}" if est.get("detalle") else "")) if est else "Sin reporte de lesión"]
    if d.get("rol"):
        l1.append(f"Rol: {d['rol']}" + (f" · {d['prom_min']:.0f} min prom." if d.get("prom_min") else ""))
    if d.get("titular") is True:
        l1.append("Titular confirmado")
    rv = d.get("rival") or ""
    l2 = [(f"{'vs' if d.get('sede') == 'Local' else '@'} {rv}" if rv else "Rival por confirmar")]
    l2.append(f"Defensor: {d['defensor']}" if d.get("defensor") else "Defensor: sin dato")
    l2.append("Bajas rival: " + ("; ".join(d["bajas_rival"][:3]) if d.get("bajas_rival") else "ninguna reportada"))
    l3 = d.get("bajas_propias")[:4] if d.get("bajas_propias") else ["Sin bajas reportadas"]
    l4 = d.get("notas") or ["Sin datos extra de contexto."]
    tarjetas = [("Estado del jugador", l1), ("Rival y defensa", l2), ("Bajas de su equipo", l3), ("Ritmo y contexto", l4)]
    cw, ch, gap = (W - P * 2 - 24) // 2, 194, 22
    for i, (tit, lineas) in enumerate(tarjetas):
        x, y = P + (i % 2) * (cw + gap), 1030 + (i // 2) * (ch + gap)
        L.rr((x, y, x + cw, y + ch), 24, fill=C["panel"], outline=C["linea"], w=2)
        L.txt(x + 26, y + 46, tit, 800, 24, C["texto"])
        yy, restante = y + 80, 5
        for ln in lineas:
            n = L.parrafo(x + 26, yy, ln, 400, 20, C["cuerpo"], cw - 52, 27, max(1, min(restante, 3)))
            yy += n * 27 + 4
            restante -= n
            if restante <= 0:
                break

    # ---- pie
    L.d.line([P * S, 1450 * S, (W - P) * S, 1450 * S], fill=C["linea"], width=2)
    L.txt(P, 1480, "Análisis estadístico, no una garantía.", 400, 19, C["suave"])
    L.txt(W - P, 1480, "Solo +18 · Juega con responsabilidad", 400, 19, C["suave"], "rs")
    return L.salida()
