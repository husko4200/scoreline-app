"""Alertas de tus favoritos: partido por empezar, cambio de estado de lesión y movimiento de línea.

Uso (en app.py, dentro del menú lateral):
    alertas.panel()

Cómo funciona
  · Un fragmento revisa los favoritos cada 60 s en TODAS las secciones (no hace falta estar en Inicio).
  · Qué cuenta como favorito: tus equipos, y los jugadores (y sus equipos para los avisos de partido y de línea).
  · Los avisos nuevos viajan al navegador, donde movimiento.py los muestra como aviso en pantalla + sonido + notificación del
    sistema (si diste permiso). El navegador recuerda cuáles ya mostró, así que nunca se repiten.
  · Lo que ya se «vio» (estado de lesiones, línea de referencia de cada partido) se guarda en alertas_estado.json. La primera
    vez solo se toma como punto de partida: no avisa de lo que ya estaba así.
  · Ajustes en alertas_config.json.
"""
import json
import os
import time

import streamlit as st
import streamlit.components.v1 as components

import favoritos
import favoritos_datos as fd

_CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_CONFIG = os.path.join(_CARPETA, "alertas_config.json")
ARCHIVO_ESTADO = os.path.join(_CARPETA, "alertas_estado.json")
CONFIG_BASE = {"partido": True, "lesion": True, "linea": True, "minutos": 30, "umbral": 1.0}
HORIZONTE_LINEA_MIN = 48 * 60          # solo se vigila la línea de partidos que empiezan en las próximas 48 h
MAX_HISTORIAL = 12


# ---------------------------------------------------------------- archivos
def _leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, type(defecto)) else defecto
    except (OSError, ValueError):
        return defecto


def _escribir_json(ruta, datos):
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
    except OSError:
        pass


def cargar_config() -> dict:
    cfg = {**CONFIG_BASE, **_leer_json(ARCHIVO_CONFIG, {})}
    cfg["minutos"] = int(min(180, max(5, cfg["minutos"])))
    cfg["umbral"] = float(min(10.0, max(0.5, cfg["umbral"])))
    return cfg


# ---------------------------------------------------------------- lógica (funciones puras: fáciles de probar)
def alerta(tipo, emoji, titulo, texto, ident, **extra) -> dict:
    """`texto` es el resumen en una línea (respaldo y cuerpo de la notificación del sistema). `extra` trae lo estructurado
    del aviso v2 que dibuja movimiento.py: kicker, titulo2, sub, equipos, jugador, chips, movs, lineas, nivel, icono."""
    base = {"id": ident, "tipo": tipo, "emoji": emoji, "titulo": titulo, "texto": texto}
    if extra:
        base.update(extra, v=2)
    return base


def equipo_datos(abrev, nombre=None, fav=False) -> dict:
    return {"abrev": str(abrev or "?"), "nombre": nombre or str(abrev or "?"), "url": fd.escudo(abrev), "fav": bool(fav)}


def explicar_estado(estado):
    """(etiqueta, frase que explica qué significa para el próximo partido). Estado vacío = ya no figura en el reporte."""
    e = str(estado or "").lower()
    if not estado:
        return "Disponible", "Ya no figura en el reporte de lesiones: queda disponible para jugar."
    nivel = fd.nivel_lesion(estado)
    if nivel == "out":
        return "Fuera", "No jugará el próximo partido."
    if nivel == "dudoso":
        return "Dudoso", "Es poco probable que juegue; lo más normal es que se quede fuera."
    if nivel == "probable":
        return "Probable", "Lo más probable es que juegue."
    if "day" in e:
        return "Día a día", "Su participación se decide el mismo día del partido."
    return "En duda", "Es una incógnita: se confirma poco antes del partido."


def _favorito(spread_local, local, visita):
    """(equipo favorito, puntos de ventaja esperada) según el handicap del local; (None, 0) si está parejo o no hay dato."""
    if spread_local is None or spread_local == 0:
        return None, 0.0
    return (local, abs(spread_local)) if spread_local < 0 else (visita, abs(spread_local))


def explicar_favorito(spread_local, local, visita):
    """Frase sobre quién es favorito según el handicap; '' si no hay dato."""
    if spread_local is None:
        return ""
    fav, pts = _favorito(spread_local, local, visita)
    return f"El mercado ve a {fav} como favorito por {pts:g} pts." if fav else "El mercado lo ve parejo."


def explicar_handicap(a, b, local, visita):
    """Explica en palabras qué cambió al pasar el handicap del local de `a` a `b`."""
    fa, pa = _favorito(a, local, visita)
    fb, pb = _favorito(b, local, visita)
    if fa is None and fb is None:
        return "El partido sigue parejo."
    if fa is None:
        return f"{fb} pasa a ser favorito por {pb:g} pts."
    if fb is None:
        return f"{fa} deja de ser favorito: el partido queda parejo."
    if fa != fb:
        return f"Cambio de favorito: ahora lo es {fb} (por {pb:g} pts); antes lo era {fa}."
    if pb > pa:
        return f"{fb} es más favorito: su ventaja esperada pasa de {pa:g} a {pb:g} pts."
    return f"{fb} es menos favorito: su ventaja esperada baja de {pa:g} a {pb:g} pts."


def movimientos_linea(ref, actual, umbral, local, visita) -> list[dict]:
    """Cada mercado que se movió >= umbral, ya explicado. Mismo criterio que movimiento_linea()."""
    out = []
    for clave in ("spread", "total"):
        x, y = ref.get(clave), actual.get(clave)
        if x is None or y is None or abs(y - x) < umbral:
            continue
        d = round(y - x, 2)
        if clave == "spread":
            et, de, a_txt, txt = f"Handicap {local}", f"{x:+g}", f"{y:+g}", explicar_handicap(x, y, local, visita)
        else:
            et, de, a_txt = "Total de puntos", f"{x:g}", f"{y:g}"
            txt = f"El mercado espera {'más' if d > 0 else 'menos'} puntos en el partido ({abs(d):g} {'más' if d > 0 else 'menos'})."
        out.append({"etiqueta": et, "de": de, "a": a_txt, "delta": f"{abs(d):g}", "sube": d > 0, "texto": txt})
    return out


def cambio_lesion(prev, actual):
    """Texto del cambio de estado, o None si no hay cambio. '' = sin reporte."""
    if prev == actual:
        return None
    a = actual or "sin reporte"
    if not actual:
        return "ya no figura en el reporte de lesiones"
    if not prev:
        return f"ahora figura como {actual}"
    return f"{prev} → {a}"


def movimiento_linea(ref, actual, umbral):
    """Texto si la línea se movió >= umbral respecto de la de referencia (handicap del local o total); si no, None.
    `ref` y `actual` son dicts {spread, total}."""
    partes = []
    for clave, etiqueta in (("spread", "Handicap local"), ("total", "Total")):
        a, b = ref.get(clave), actual.get(clave)
        if a is not None and b is not None and abs(b - a) >= umbral:
            partes.append(f"{etiqueta} {a:+g} → {b:+g}" if clave == "spread" else f"{etiqueta} {a:g} → {b:g}")
    return " · ".join(partes) or None


def _objetivos():
    """Equipos a vigilar: favoritos directos + el equipo de cada jugador favorito. {id_equipo: [quién lo pidió]}."""
    mapa = fd.mapa_equipos()
    out = {}
    for tid in favoritos.equipos():
        if tid in mapa:
            out.setdefault(tid, []).append(mapa[tid]["nombre"])
    info = fd.jugadores_info()
    for pid in favoritos.jugadores():
        eq = fd.equipo_de_jugador(pid)
        if eq:
            out.setdefault(eq["id"], []).append(info.get(pid, {}).get("nombre", f"Jugador {pid}"))
    return out


def revisar(cfg, ahora=None) -> list[dict]:
    """Calcula los avisos NUEVOS y actualiza el estado en disco. No toca la interfaz."""
    ahora = ahora or int(time.time())
    estado = _leer_json(ARCHIVO_ESTADO, {})
    est_les, est_lin = estado.get("lesiones", {}), estado.get("lineas", {})
    avisos, mapa = [], fd.mapa_equipos()
    objetivos = _objetivos()
    fd.precargar(list(objetivos), favoritos.jugadores())   # pide todo a la vez; el resto sale de la caché

    # --- partido por empezar y movimiento de línea (por equipo; un partido entre dos favoritos avisa una sola vez)
    vistos_evento = set()
    for tid, quienes in objetivos.items():
        prox = fd.calendario_seguro(tid).get("proximo")
        if not prox or prox["evento"] in vistos_evento:
            continue
        vistos_evento.add(prox["evento"])
        _, mins = fd.cuando(prox["fecha"])
        if mins is None:
            continue
        eq = mapa.get(tid, {})
        local, visita = (eq.get("abrev", "?"), prox["rival"]) if prox["local"] else (prox["rival"], eq.get("abrev", "?"))
        duelo = f"{visita} @ {local}"
        mio = equipo_datos(eq.get("abrev", "?"), eq.get("nombre"), fav=True)
        rival = equipo_datos(prox["rival"], prox["rival_nombre"] or prox["rival"])
        loc_d, vis_d = (mio, rival) if prox["local"] else (rival, mio)
        hora = fd.cuando(prox["fecha"])[0]
        lin = fd.linea(prox["evento"], prox["fecha"]) if -5 <= mins <= HORIZONTE_LINEA_MIN else None

        if cfg["partido"] and prox.get("estado") == "pre" and 0 <= mins <= cfg["minutos"]:
            extra = ""
            if lin:
                extra = " · " + " · ".join(x for x in (str(lin["txt"]) if lin.get("txt") else "",
                                                       f'total {lin["total"]:g}' if lin.get("total") is not None else "") if x)
            siguiendo = ", ".join(dict.fromkeys(quienes))
            frases = [f"Lo ves porque sigues a {siguiendo}."]
            if lin:
                fav = explicar_favorito(lin.get("spread_local"), local, visita)
                if fav:
                    frases.append(fav)
                if lin.get("total") is not None:
                    frases.append(f'Se esperan unos {lin["total"]:g} puntos entre los dos equipos.')
            chips = ([{"k": "Handicap", "t": str(lin["txt"])}] if lin and lin.get("txt") else []) + \
                    ([{"k": "Total", "t": f'{lin["total"]:g}'}] if lin and lin.get("total") is not None else [])
            cuenta = fd.cuenta_regresiva(mins)
            avisos.append(alerta("partido", "🏀", "Tu favorito juega pronto",
                                 f'{duelo} {cuenta} ({siguiendo}){extra}', f'ini:{prox["evento"]}',
                                 kicker="Partido por empezar", titulo2=f"Empieza {cuenta}", nivel="info", equipos=[vis_d, loc_d], sede="@",
                                 sub=f'{vis_d["nombre"]} @ {loc_d["nombre"]} · {hora}', chips=chips, lineas=frases, icono=mio["url"],
                                 cuerpo=f'{vis_d["nombre"]} @ {loc_d["nombre"]} empieza {cuenta} ({hora}). ' + " ".join(frases)))

        if cfg["linea"] and lin and prox.get("estado") == "pre":
            actual = {"spread": lin.get("spread_local"), "total": lin.get("total")}
            ref = est_lin.get(prox["evento"])
            if ref is None:
                est_lin[prox["evento"]] = actual                       # punto de partida: no avisa
            else:
                texto = movimiento_linea(ref, actual, cfg["umbral"])
                if texto:
                    movs = movimientos_linea(ref, actual, cfg["umbral"], local, visita)
                    signos = {m["sube"] for m in movs}
                    nivel = ("sube" if True in signos else "baja") if len(signos) == 1 else "info"
                    avisos.append(alerta("linea", "📈", "Se movió la línea", f"{duelo}: {texto}", f'lin:{prox["evento"]}:{ahora}',
                                         kicker="Línea movida", titulo2="El mercado ajustó la línea", nivel=nivel, equipos=[vis_d, loc_d], sede="@",
                                         sub=f'{vis_d["nombre"]} @ {loc_d["nombre"]} · {hora}', movs=movs, icono=mio["url"],
                                         lineas=[f'Te avisamos porque cambió {cfg["umbral"]:g} pts o más desde la última referencia.'],
                                         cuerpo=f'{vis_d["nombre"]} @ {loc_d["nombre"]}: ' + " ".join(f'{m["etiqueta"]} {m["de"]} → {m["a"]}. {m["texto"]}' for m in movs)))
                    est_lin[prox["evento"]] = actual                   # nueva referencia: el siguiente aviso mide desde aquí

    # --- lesiones de jugadores favoritos
    if cfg["lesion"] and favoritos.jugadores():
        les = fd.lesiones()
        if les is not None:                                            # None = no se pudo leer: no se compara (evita falsos «ya no figura»)
            info = fd.jugadores_info()
            for pid in favoritos.jugadores():
                actual = (les.get(pid) or {}).get("estado", "")
                if pid not in est_les:
                    est_les[pid] = actual                              # punto de partida
                    continue
                texto = cambio_lesion(est_les[pid], actual)
                if texto:
                    nombre = info.get(pid, {}).get("nombre", f"Jugador {pid}")
                    x = les.get(pid) or {}
                    det = " · ".join(v for v in (x.get("lesion"), f'regreso est. {x["regreso"]}' if x.get("regreso") else "") if v)
                    et_n, frase = explicar_estado(actual)
                    et_p = explicar_estado(est_les[pid])[0] if est_les[pid] else "Sin reporte"
                    nivel_n = fd.nivel_lesion(actual) if actual else "ok"
                    nivel_p = fd.nivel_lesion(est_les[pid]) if est_les[pid] else "ok"
                    eqj = fd.equipo_de_jugador(pid)
                    eq_d = equipo_datos(eqj["abrev"], eqj["nombre"], fav=True) if eqj else None
                    chips = [{"k": "Antes", "t": et_p, "c": nivel_p}, {"k": "Ahora", "t": et_n, "c": nivel_n}]
                    if x.get("lesion"):
                        chips.append({"k": "Lesión", "t": x["lesion"]})
                    if x.get("regreso"):
                        chips.append({"k": "Regreso est.", "t": x["regreso"]})
                    avisos.append(alerta("lesion", "🩹", "Cambió el estado de lesión", f'{nombre}: {texto}' + (f" ({det})" if det else ""),
                                         f"les:{pid}:{ahora}", kicker="Estado de lesión", nivel=nivel_n, titulo2=f"{et_p} → {et_n}",
                                         jugador={"nombre": nombre, "foto": fd.foto(pid), "equipo": eq_d, "sub": eqj["nombre"] if eqj else ""},
                                         chips=chips, lineas=[frase], icono=fd.foto(pid),
                                         cuerpo=f"{nombre}: {et_p} → {et_n}. {frase}" + (f" {det}." if det else "")))
                    est_les[pid] = actual

    # limpiar referencias de partidos que ya pasaron (el diccionario no crece sin límite)
    if len(est_lin) > 80:
        est_lin = dict(list(est_lin.items())[-60:])
    _escribir_json(ARCHIVO_ESTADO, {"lesiones": est_les, "lineas": est_lin})
    return avisos


# ---------------------------------------------------------------- entrega al navegador
def _enviar(avisos):
    """Pasa los avisos a movimiento.py (ya instalado en la página). Reintenta unos segundos si aún no está listo."""
    if not avisos:
        return
    carga = json.dumps(avisos, ensure_ascii=True).replace("</", "<\\/")
    components.html(
        "<script>(function(){var A=" + carga + ",n=0;(function t(){var p=window.parent&&window.parent.__pl;"
        "if(p&&p.alertas){p.alertas(A);return}if(n++<25)setTimeout(t,400)})()})()</script>", height=0)


_BOTON_NOTIF = """
<style>body{margin:0;font-family:Inter,system-ui,sans-serif}
button{width:100%;padding:.5rem .7rem;border-radius:10px;border:1px solid #D9DFEA;background:#fff;color:#0F172A;font-weight:600;font-size:.85rem;cursor:pointer}
button:hover{border-color:#4F46E5;color:#3730A3}</style>
<button id="b" type="button">🔔 Activar avisos del navegador</button>
<script>
(function(){var P=window.parent,b=document.getElementById('b');
function pintar(){var N=P&&P.Notification;
  if(!N){b.textContent='🔕 Este navegador no admite notificaciones';b.disabled=true;return}
  if(N.permission==='granted'){b.textContent='✅ Avisos del navegador activados';}
  else if(N.permission==='denied'){b.textContent='🚫 Bloqueados: actívalos en el candado de la barra de direcciones';b.disabled=true;}
  else{b.textContent='🔔 Activar avisos del navegador';}}
b.onclick=function(){var N=P.Notification;if(!N)return;
  (N.requestPermission()||Promise.resolve()).then(function(){pintar();
    if(N.permission==='granted'&&P.__pl&&P.__pl.alertas){P.__pl.alertas([{id:'prueba:'+Date.now(),emoji:'🔔',titulo:'Avisos activados',texto:'Así te llegarán las alertas de tus favoritos.',tipo:'prueba'}])}});};
pintar();})();
</script>
"""


def _guardar_config():
    cfg = {"partido": st.session_state.get("al_partido", True), "lesion": st.session_state.get("al_lesion", True),
           "linea": st.session_state.get("al_linea", True), "minutos": int(st.session_state.get("al_minutos", 30)),
           "umbral": float(st.session_state.get("al_umbral", 1.0))}
    _escribir_json(ARCHIVO_CONFIG, cfg)


def _probar():
    st.session_state["al_prueba"] = True


@st.fragment(run_every=60)
def _vigilar():
    cfg = cargar_config()
    hist = st.session_state.setdefault("al_hist", [])
    nuevos = []
    if st.session_state.pop("al_prueba", False):
        nuevos.append(alerta("prueba", "🔔", "Aviso de prueba", "Así se verá y sonará una alerta de tus favoritos.", f"prueba:{int(time.time() * 1000)}",
                             kicker="Aviso de prueba", titulo2="Así te llegarán las alertas", nivel="info", sede="@",
                             equipos=[equipo_datos("BOS", "Boston Celtics"), equipo_datos("LAL", "Los Angeles Lakers", fav=True)],
                             sub="Ejemplo con dos equipos (★ = tu favorito)", chips=[{"k": "Handicap", "t": "LAL -3.5"}, {"k": "Total", "t": "221.5"}],
                             lineas=["Pasa el mouse por encima para pausar el tiempo y usa la ✕ para cerrarlo cuando quieras."]))
    # La primera pasada de la sesión no revisa: así no frena el arranque de la página. Revisa desde el minuto siguiente.
    primera = not st.session_state.get("al_listo")
    st.session_state["al_listo"] = True
    if (cfg["partido"] or cfg["lesion"] or cfg["linea"]) and favoritos.hay_favoritos() and not primera:
        try:
            nuevos += revisar(cfg)
        except Exception:  # noqa: BLE001 - una falla de red no debe romper el menú
            pass
    if nuevos:
        _enviar(nuevos)
        hora = time.strftime("%H:%M")
        hist[:0] = [{**a, "hora": hora} for a in nuevos]
        del hist[MAX_HISTORIAL:]
    if hist:
        st.caption("Últimos avisos")
        for a in hist[:6]:
            st.markdown(f'<div style="font-size:.8rem;line-height:1.35;margin:.15rem 0">{a["emoji"]} <b>{a["hora"]}</b> · {_esc(a["texto"])}</div>',
                        unsafe_allow_html=True)
    elif favoritos.hay_favoritos():
        st.caption("Vigilando tus favoritos… aquí aparecerán los avisos.")
    else:
        st.caption("Agrega favoritos en Inicio para recibir avisos.")


def _esc(t):
    from html import escape
    return escape(str(t))


def panel():
    """Panel «🔔 Alertas» del menú lateral + vigilancia en segundo plano (solo ScoreLine Pro)."""
    import planes
    if not planes.es_pro():
        with st.sidebar.expander("Notificaciones (Pro)", expanded=False):
            st.caption("Las alertas y notificaciones en vivo de tus favoritos son exclusivas de ScoreLine Pro.")
            if st.button("Desbloquear notificaciones", key="al_unlock_pro", use_container_width=True):
                planes.modal_pro("Activa ScoreLine Pro para recibir alertas de partidos, lesiones y líneas.")
        return
    cfg = cargar_config()
    with st.sidebar.expander("Alertas de favoritos", expanded=False):
        st.toggle("Partido por empezar", cfg["partido"], key="al_partido", on_change=_guardar_config)
        opciones_mins = [10, 15, 30, 45, 60]
        idx = opciones_mins.index(cfg["minutos"]) if cfg["minutos"] in opciones_mins else 1
        mins = st.selectbox("Avisar con … min de anticipación", opciones_mins, index=idx,
                            format_func=lambda m: f"{m} minutos", key="al_minutos_sel")
        st.toggle("Cambio de estado de lesión", cfg["lesion"], key="al_lesion", on_change=_guardar_config)
        st.toggle("Movimiento de la línea", cfg["linea"], key="al_linea", on_change=_guardar_config)
        if st.button("Guardar preferencias", use_container_width=True, key="al_guardar_btn", type="primary"):
            st.session_state["al_minutos"] = mins
            cfg["minutos"] = mins
            _escribir_json(ARCHIVO_CONFIG, cfg)
            st.success("Preferencias guardadas")
        st.button("Probar un aviso", on_click=_probar, use_container_width=True, key="al_probar")
        _vigilar()
