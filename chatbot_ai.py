"""ScoreLine AI: asistente de análisis deportivo basado exclusivamente en datos de la app.

- Lee el system prompt desde `scoreline-ai-system-prompt.md`.
- Aplica límite diario en servidor (1 consulta/día para plan gratuito, ilimitado para Pro)
  usando Firestore (`ai_uso/{clave_dia}`) con respaldo atómico en `ai_uso.json`.
- Usa claves de API desde `st.secrets` o variables de entorno (nunca en el navegador).
"""
from __future__ import annotations

import base64
from datetime import date, datetime
import hashlib
from html import escape as _esc
import re as _re


def _md_simple(txt: str) -> str:
    """Convierte Markdown básico (negrita, listas) a HTML inline seguro en una sola línea."""
    txt = _esc(txt)
    txt = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", txt)
    out = []
    for ln in txt.split("\n"):
        s = ln.strip()
        if not s:
            continue
        m = _re.match(r"^[-•]\s+(.+)$", s)
        if m:
            out.append(f'<div class="sl-ai-li"><span class="sl-ai-dot">•</span><span>{m.group(1)}</span></div>')
        else:
            out.append(f'<div class="sl-ai-p">{s}</div>')
    return "".join(out)
import json
import os
import threading
from typing import Any

import requests
import streamlit as st
import streamlit.components.v1 as _comp

import planes

LIMITE_GRATIS_DIA = 1


def consultas_restantes_hoy() -> int | None:
    """Devuelve cuántas consultas gratis quedan hoy, o None si el usuario es Pro."""
    if planes.es_pro():
        return None
    return max(0, LIMITE_GRATIS_DIA - consultas_usadas_hoy())

_CARPETA = os.path.dirname(os.path.abspath(__file__))
_PROMPT_PATH = os.path.join(_CARPETA, "scoreline-ai-system-prompt.md")
_USO_LOCAL_PATH = os.path.join(_CARPETA, "ai_uso.json")
_LOCK = threading.Lock()


@st.cache_data(show_spinner=False)
def _leer_prompt() -> str:
    try:
        with open(_PROMPT_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return (
            "Eres ScoreLine AI, asistente de análisis deportivo. "
            "Responde en español usando solo los datos recibidos en <datos_app>. "
            "No des recomendaciones de apuestas ni asesoría legal."
        )


@st.cache_data(show_spinner=False)
def _img_b64(nombre_archivo: str) -> str:
    ruta = os.path.join(_CARPETA, "assets", nombre_archivo)
    try:
        with open(ruta, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""


def _robot_por_seccion(seccion: str) -> str:
    s = str(seccion or "").lower()
    if "nba" in s or "baloncesto" in s:
        return _img_b64("robot_nba.png") or _img_b64("robot_avatar.png")
    if "fútbol" in s or "futbol" in s:
        return _img_b64("robot_futbol.png") or _img_b64("robot_avatar.png")
    if "tenis" in s:
        return _img_b64("robot_tenis.png") or _img_b64("robot_avatar.png")
    return _img_b64("robot_avatar.png")


# ---------------------------------------------------------------------------
# Cuota diaria en servidor (Firestore + respaldo local atómico)
# ---------------------------------------------------------------------------
def _clave_uso_hoy() -> str:
    hoy = date.today().isoformat()
    uid = planes.uid_actual()
    if uid:
        raw = f"u:{uid}:{hoy}"
    else:
        ua, ip = "", ""
        try:
            hdrs = st.context.headers or {}
            ua = str(hdrs.get("User-Agent") or hdrs.get("user-agent") or "")
            ip = str(hdrs.get("X-Forwarded-For") or hdrs.get("x-forwarded-for") or hdrs.get("Host") or "")
        except Exception:  # noqa: BLE001
            pass
        if not (ua or ip):
            if "_ai_anon_id" not in st.session_state:
                st.session_state["_ai_anon_id"] = os.urandom(8).hex()
            raw = f"s:{st.session_state['_ai_anon_id']}:{hoy}"
        else:
            raw = f"g:{ip}|{ua}:{hoy}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _leer_uso_local() -> dict[str, int]:
    if not os.path.exists(_USO_LOCAL_PATH):
        return {}
    try:
        with open(_USO_LOCAL_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _escribir_uso_local(data: dict[str, int]) -> None:
    tmp = _USO_LOCAL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _USO_LOCAL_PATH)


def consultas_usadas_hoy() -> int:
    clave = _clave_uso_hoy()
    db = planes._obtener_firestore()
    if db is not None:
        try:
            snap = db.collection("ai_uso").document(clave).get()
            if snap.exists:
                return int((snap.to_dict() or {}).get("count", 0))
            return 0
        except Exception:  # noqa: BLE001
            pass
    with _LOCK:
        return int(_leer_uso_local().get(clave, 0))


def _incrementar_uso_hoy() -> int:
    clave = _clave_uso_hoy()
    hoy = date.today().isoformat()
    db = planes._obtener_firestore()
    if db is not None:
        try:
            ref = db.collection("ai_uso").document(clave)
            snap = ref.get()
            nuevo = (int((snap.to_dict() or {}).get("count", 0)) if snap.exists else 0) + 1
            ref.set({"count": nuevo, "fecha": hoy}, merge=True)
            return nuevo
        except Exception:  # noqa: BLE001
            pass
    with _LOCK:
        data = _leer_uso_local()
        nuevo = int(data.get(clave, 0)) + 1
        data[clave] = nuevo
        _escribir_uso_local(data)
        return nuevo


# ---------------------------------------------------------------------------
# Contexto real <datos_app>
# ---------------------------------------------------------------------------
def _limpiar_seccion(seccion: str) -> str:
    txt = _re.sub(r"[^\w\sáéíóúÁÉÍÓÚñÑ·-]", "", str(seccion or "")).strip()
    return txt or "Inicio"


def _construir_datos_app(seccion: str) -> str:
    lineas = [f"Sección activa: {_limpiar_seccion(seccion)}", f"Fecha actual: {date.today().isoformat()}"]
    try:
        import inicio
        _, partidos = inicio._resumen_dia()
        if partidos:
            vivos = [m for m in partidos if m.get("state") == "in"]
            prox = [m for m in partidos if m.get("state") == "pre"]
            finales = [m for m in partidos if m.get("state") == "post"]

            def _fmt(m: dict[str, Any]) -> str:
                h, a = m.get("home") or {}, m.get("away") or {}
                st_m = m.get("state", "pre")
                if st_m == "in":
                    est = f"EN VIVO {h.get('score', '-')}-{a.get('score', '-')} ({m.get('hora', '')})"
                elif st_m == "post":
                    est = f"YA FINALIZADO (resultado pasado): {h.get('score', '-')}-{a.get('score', '-')}"
                else:
                    est = f"Programado (por jugarse): {m.get('hora', '')}"
                prob = m.get("prob")
                prob_txt = f" · Prob Local {prob}%" if prob is not None else ""
                return (
                    f"- [{m.get('deporte', '')} · {m.get('liga', '')}] "
                    f"{h.get('nombre', '?')} (Local) vs {a.get('nombre', '?')} (Visita): {est}{prob_txt}"
                )

            if vivos:
                lineas.append(f"PARTIDOS EN VIVO ({len(vivos)}):")
                lineas.extend(_fmt(m) for m in vivos[:12])
            if prox:
                lineas.append(f"PRÓXIMOS PARTIDOS POR JUGARSE ({len(prox)}, mostrando hasta 15):")
                lineas.extend(_fmt(m) for m in prox[:15])
            if finales:
                lineas.append(f"PARTIDOS YA FINALIZADOS / RESULTADOS PASADOS ({len(finales)}, NO son próximos):")
                lineas.extend(_fmt(m) for m in finales[:10])
        else:
            lineas.append("No hay partidos cargados en el resumen del día.")
    except Exception:  # noqa: BLE001
        lineas.append("Resumen de partidos no disponible en este momento.")
    return "<datos_app>\n" + "\n".join(lineas) + "\n</datos_app>"


# ---------------------------------------------------------------------------
# Llamada a proveedor de IA en servidor (sin exponer claves)
# ---------------------------------------------------------------------------
def _secret(nombre: str) -> str:
    val = (os.environ.get(nombre) or "").strip()
    if val:
        return val
    try:
        return str(st.secrets.get(nombre, "") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _llamar_openai_compatible(
    url: str,
    api_key: str,
    modelo: str,
    sys_prompt: str,
    historial: list[dict[str, str]],
    pregunta: str,
) -> str:
    """Llama a un endpoint compatible con Chat Completions (Groq, OpenRouter, OpenAI)."""
    msgs = [{"role": "system", "content": sys_prompt}]
    msgs.extend({"role": m["role"], "content": m["content"]} for m in historial[-6:])
    msgs.append({"role": "user", "content": pregunta})
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": modelo, "messages": msgs, "temperature": 0.4, "max_tokens": 420},
            timeout=20,
        )
        if r.ok:
            return (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    except requests.RequestException:
        pass
    return ""


def _respuesta_local_datos(pregunta: str, seccion: str) -> str:
    """Motor local gratuito basado en los datos reales de ScoreLine (sin API externa)."""
    q = pregunta.lower().strip()

    # 1. Reglas estrictas del prompt: juego problemático, apuestas, legal
    if any(w in q for w in ("perdiendo dinero", "deuda", "adicc", "no me control", "ansiedad", "ludopat", "recuperar dinero")):
        return (
            "Siento mucho que estés pasando por un momento difícil. "
            "Si sientes que estás perdiendo el control, hablar con un profesional o con un servicio de ayuda de tu país puede marcar la diferencia. "
            "Cuando quieras, sigo aquí para ayudarte únicamente con análisis deportivo."
        )
    if any(w in q for w in ("legal", "impuesto", "licencia", "regula", "prohibid")):
        return (
            "De temas legales no puedo orientarte. Para eso te conviene consultar fuentes oficiales o a un profesional. "
            "Si quieres, seguimos con el análisis de algún partido de hoy."
        )
    if any(w in q for w in ("apuesto", "apostar", "apuesta", "cuota", "combinada", "parlay", "casa de", "pick", "seguro que gana", "fijo")):
        return (
            "No doy recomendaciones de apuestas ni sugiero picks o cuotas, pero sí puedo ayudarte a entender el partido. "
            "Pregúntame por los partidos en vivo, los favoritos según ScoreLine o cómo interpretar nuestras métricas."
        )

    # 2. Cargar partidos reales del día
    partidos: list[dict[str, Any]] = []
    try:
        import inicio
        _, partidos = inicio._resumen_dia()
    except Exception:  # noqa: BLE001
        partidos = []

    if any(w in q for w in ("métrica", "metrica", "expected", "como interpreto", "cómo interpreto", "qué significa", "que significa", "probabilidad")):
        return (
            "Las métricas de **ScoreLine** combinan forma reciente, rendimiento como local/visita, ritmo de juego y promedios históricos:\n"
            "- **Prob. de Victoria**: estimación porcentual basada en los datos disponibles (no es una certeza).\n"
            "- **Top Expected**: líneas estadísticas proyectadas según el ritmo reciente de equipos o jugadores.\n"
            "- **Rachas y H2H**: comparan los últimos partidos y enfrentamientos directos."
        )

    if not partidos:
        return (
            "En este momento no tengo partidos cargados en el resumen del día en la app. "
            "Prueba abrir la sección **En vivo**, **NBA**, **Fútbol** o **Tenis** para ver el detalle actualizado."
        )

    en_vivo = [m for m in partidos if m.get("state") == "in"]
    programados = [m for m in partidos if m.get("state") == "pre"]

    # 3. Búsqueda de equipo/jugador específico en la pregunta
    _stop = {
        "que", "qué", "como", "cómo", "para", "con", "hoy", "ayer", "mañana", "manana",
        "partido", "partidos", "quien", "quién", "gana", "tiene", "mejor", "sobre",
        "entre", "local", "visita", "cuando", "cuándo", "juega", "jugo", "jugó",
        "hora", "proximo", "próximo", "resultado", "marcador", "pero", "esta", "está",
    }
    palabras = [p for p in _re.findall(r"[a-záéíóúñ0-9]{3,}", q) if p not in _stop]
    coincidencias = []
    for m in partidos:
        h = (m.get("home") or {}).get("nombre", "")
        a = (m.get("away") or {}).get("nombre", "")
        texto_m = f"{h} {a} {m.get('liga', '')} {m.get('deporte', '')}".lower()
        if any(w in texto_m for w in palabras):
            coincidencias.append(m)

    if coincidencias and palabras:
        activos = [m for m in coincidencias if m.get("state") in ("in", "pre")]
        pasados = [m for m in coincidencias if m.get("state") == "post"]
        pide_futuro = any(w in q for w in ("cuando", "cuándo", "juega", "hoy", "hora", "próximo", "proximo", "mañana", "manana"))
        lineas = []
        if activos:
            lineas.append("Esto es lo que encontré en la programación actual:")
            for m in activos[:4]:
                h, a = m.get("home") or {}, m.get("away") or {}
                est = f"EN VIVO {h.get('score', '-')}-{a.get('score', '-')}" if m.get("state") == "in" else f"Programado ({m.get('hora', '')})"
                prob = m.get("prob")
                prob_txt = f" · Estimación Local: **{prob}%**" if prob is not None else ""
                lineas.append(f"- **{h.get('nombre', '?')}** vs **{a.get('nombre', '?')}** ({m.get('deporte', '')}) — {est}{prob_txt}")
        if pasados:
            if not activos and pide_futuro:
                lineas.append("No tengo un próximo partido programado en la app para esa búsqueda. El partido más reciente registrado **ya finalizó**:")
            elif not activos:
                lineas.append("Partido(s) ya finalizados encontrados en ScoreLine:")
            else:
                lineas.append("También figura este resultado ya finalizado:")
            for m in pasados[:3]:
                h, a = m.get("home") or {}, m.get("away") or {}
                lineas.append(f"- **{h.get('nombre', '?')} {h.get('score', '-')} - {a.get('score', '-')} {a.get('nombre', '?')}** ({m.get('deporte', '')} · Ya finalizado)")
        lineas.append("Recuerda que las probabilidades son estimaciones basadas en los datos de la app, no certezas.")
        return "\n".join(lineas)

    # 4. Partidos en vivo
    if any(w in q for w in ("vivo", "directo", "jugando", "ahora")):
        if not en_vivo:
            prox = programados[:3]
            if not prox:
                return "No hay partidos en vivo en este momento según los datos cargados en ScoreLine."
            lineas = ["No hay partidos en vivo ahora mismo, pero estos son los próximos del día:"]
            for m in prox:
                h, a = m.get("home") or {}, m.get("away") or {}
                lineas.append(f"- **{h.get('nombre', '?')}** vs **{a.get('nombre', '?')}** ({m.get('deporte', '')}) — {m.get('hora', '')}")
            return "\n".join(lineas)
        lineas = [f"Hay **{len(en_vivo)}** partido(s) en vivo ahora en ScoreLine:"]
        for m in en_vivo[:5]:
            h, a = m.get("home") or {}, m.get("away") or {}
            prob = m.get("prob")
            prob_txt = f" · Prob. Local {prob}%" if prob is not None else ""
            lineas.append(f"- **{h.get('nombre', '?')} {h.get('score', '-')} - {a.get('score', '-')} {a.get('nombre', '?')}** ({m.get('hora', '')}){prob_txt}")
        return "\n".join(lineas)

    # 5. Favorito / mayor probabilidad
    con_prob = [m for m in partidos if m.get("prob") is not None]
    if any(w in q for w in ("favorit", "mayor prob", "prob", "quien gana", "quién gana", "ventaja")) and con_prob:
        top = sorted(con_prob, key=lambda m: max(int(m["prob"]), 100 - int(m["prob"])), reverse=True)[:3]
        lineas = ["Según las estimaciones actuales de ScoreLine, los duelos más inclinados hoy son:"]
        for m in top:
            h, a = m.get("home") or {}, m.get("away") or {}
            p_loc = int(m["prob"])
            fav = h.get("nombre", "Local") if p_loc >= 50 else a.get("nombre", "Visita")
            pct = max(p_loc, 100 - p_loc)
            lineas.append(f"- **{h.get('nombre', '?')}** vs **{a.get('nombre', '?')}**: ventaja estimada para **{fav} ({pct}%)**.")
        lineas.append("Son estimaciones basadas en forma reciente y rendimiento local/visita, nunca resultados seguros.")
        return "\n".join(lineas)

    # 6. Saludo / resumen general del día (sin emojis ni cifras técnicas frías)
    sec_txt = _limpiar_seccion(seccion)
    return (
        f"Estoy revisando **{sec_txt}** en tiempo real. "
        f"Ahora hay **{len(en_vivo)}** encuentro(s) en vivo y **{len(programados)}** próximos en cartelera. "
        "Dime qué equipo, jugador o probabilidad quieres analizar."
    )


def _llamar_ia(pregunta: str, historial: list[dict[str, str]], datos_app: str, seccion: str = "") -> tuple[bool, str]:
    sys_prompt = _leer_prompt() + "\n\n" + datos_app

    # 1) Gemini API — Google AI Studio (tiene plan GRATUITO sin tarjeta)
    gem_key = _secret("GEMINI_API_KEY")
    if gem_key:
        modelo = _secret("GEMINI_MODEL") or "gemini-2.5-flash"
        contents = []
        for msg in historial[-6:]:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        contents.append({"role": "user", "parts": [{"text": pregunta}]})
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                params={"key": gem_key},
                json={
                    "system_instruction": {"parts": [{"text": sys_prompt}]},
                    "contents": contents,
                    "generationConfig": {"temperature": 0.4, "maxOutputTokens": 420},
                },
                timeout=20,
            )
            if r.ok:
                cands = (r.json().get("candidates") or [])
                if cands:
                    parts = (cands[0].get("content") or {}).get("parts") or []
                    txt = "".join(p.get("text", "") for p in parts).strip()
                    if txt:
                        return True, txt
        except requests.RequestException:
            pass

    # 2) Groq Cloud (plan GRATUITO sin tarjeta, Llama 3.3 70B)
    groq_key = _secret("GROQ_API_KEY")
    if groq_key:
        txt = _llamar_openai_compatible(
            "https://api.groq.com/openai/v1/chat/completions",
            groq_key,
            _secret("GROQ_MODEL") or "llama-3.3-70b-versatile",
            sys_prompt,
            historial,
            pregunta,
        )
        if txt:
            return True, txt

    # 3) OpenRouter (modelos :free gratuitos)
    or_key = _secret("OPENROUTER_API_KEY")
    if or_key:
        txt = _llamar_openai_compatible(
            "https://openrouter.ai/api/v1/chat/completions",
            or_key,
            _secret("OPENROUTER_MODEL") or "meta-llama/llama-3.3-70b-instruct:free",
            sys_prompt,
            historial,
            pregunta,
        )
        if txt:
            return True, txt

    # 4) Anthropic Claude (opcional)
    ant_key = _secret("ANTHROPIC_API_KEY")
    if ant_key:
        try:
            import anthropic
            cli = anthropic.Anthropic(api_key=ant_key)
            msgs = [{"role": m["role"], "content": m["content"]} for m in historial[-6:]]
            msgs.append({"role": "user", "content": pregunta})
            resp = cli.messages.create(
                model=_secret("ANTHROPIC_MODEL") or "claude-3-5-haiku-latest",
                max_tokens=420,
                temperature=0.4,
                system=sys_prompt,
                messages=msgs,
            )
            txt = "".join(getattr(b, "text", "") for b in resp.content).strip()
            if txt:
                return True, txt
        except Exception:  # noqa: BLE001
            pass

    # 5) OpenAI (opcional)
    oai_key = _secret("OPENAI_API_KEY")
    if oai_key:
        txt = _llamar_openai_compatible(
            "https://api.openai.com/v1/chat/completions",
            oai_key,
            _secret("OPENAI_MODEL") or "gpt-4o-mini",
            sys_prompt,
            historial,
            pregunta,
        )
        if txt:
            return True, txt

    # 6) Respaldo local gratuito con datos reales de ScoreLine (siempre disponible sin costo)
    return True, _respuesta_local_datos(pregunta, seccion)


# ---------------------------------------------------------------------------
# Panel lateral flotante UI de ScoreLine AI
# ---------------------------------------------------------------------------
def _render_mensajes_html(
    msgs: list[dict[str, str]],
    av_src: str,
    mascot_src: str,
    escribiendo: bool = False,
) -> str:
    if not msgs and not escribiendo:
        return (
            '<div class="sl-ai-welcome">'
            '<div class="sl-ai-bot-stage">'
            '<div class="sl-ai-bot-aura"></div>'
            f'<img class="sl-ai-welcome-img" src="{mascot_src}" alt="ScoreLine AI">'
            '</div>'
            '<div class="sl-ai-welcome-title">¡Hola! Soy ScoreLine AI</div>'
            '<div class="sl-ai-welcome-txt">Tu asistente de análisis deportivo. Elige una sugerencia o pregúntame por cualquier partido.</div>'
            '</div>'
        )
    burbujas = []
    for m in msgs:
        hora = _esc(m.get("ts", ""))
        hora_html = f'<div class="sl-ai-time">{hora}</div>' if hora else ""
        if m["role"] == "user":
            burbujas.append(
                f'<div class="sl-ai-row user">'
                f'<div class="sl-ai-bwrap user"><div class="sl-ai-bubble user">{_esc(m["content"])}</div>{hora_html}</div>'
                f'</div>'
            )
        else:
            burbujas.append(
                f'<div class="sl-ai-row bot">'
                f'<img class="sl-ai-msg-av" src="{av_src}" alt="">'
                f'<div class="sl-ai-bwrap bot"><div class="sl-ai-bubble bot">{_md_simple(m["content"])}</div>{hora_html}</div>'
                f'</div>'
            )
    if escribiendo:
        burbujas.append(
            f'<div class="sl-ai-row bot">'
            f'<img class="sl-ai-msg-av" src="{av_src}" alt="">'
            f'<div class="sl-ai-bwrap bot"><div class="sl-ai-bubble bot sl-ai-typing-box">'
            f'<span class="sl-ai-typing"><span></span><span></span><span></span></span>'
            f'<span class="sl-ai-typing-lbl">Analizando…</span>'
            f'</div></div></div>'
        )
    return f'<div class="sl-ai-msgs" id="sl-ai-msgs-box">{"".join(burbujas)}</div>'


def panel_chat(seccion_actual: str = "") -> None:
    es_pro = planes.es_pro()
    usadas = 0 if es_pro else consultas_usadas_hoy()
    bloqueado = (not es_pro) and (usadas >= LIMITE_GRATIS_DIA)

    av_b64 = _img_b64("robot_avatar.png")
    mascot_b64 = _robot_por_seccion(seccion_actual)
    av_src = f"data:image/png;base64,{av_b64}" if av_b64 else ""
    mascot_src = f"data:image/png;base64,{mascot_b64}" if mascot_b64 else av_src

    restantes = max(0, LIMITE_GRATIS_DIA - usadas)
    if es_pro:
        badge_txt, badge_cls = "Pro · Ilimitado", "is-pro"
    elif restantes == 1:
        badge_txt, badge_cls = "1 pregunta gratis hoy", "is-free"
    else:
        badge_txt, badge_cls = "0 gratis hoy", "is-empty"

    if "sl_ai_msgs" not in st.session_state:
        st.session_state["sl_ai_msgs"] = []
    msgs: list[dict[str, str]] = st.session_state["sl_ai_msgs"]

    with st.container(key="sl_ai_drawer"):
        # Cabecera única: robot + punto verde + título + badge + Nuevo chat (icono) + Cerrar (icono)
        c_head, c_rst, c_cls = st.columns([6.4, 0.9, 0.9], vertical_alignment="center")
        c_head.markdown(
            f'<div class="sl-ai-head">'
            f'<div class="sl-ai-head-av-wrap"><img class="sl-ai-head-ico" src="{av_src}" alt="ScoreLine AI"><span class="sl-ai-online-dot"></span></div>'
            f'<div class="sl-ai-head-info">'
            f'<div class="sl-ai-title">ScoreLine AI <span class="sl-ai-online-txt">En línea</span></div>'
            f'<span class="sl-ai-badge {badge_cls}">{_esc(badge_txt)}</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if msgs and not bloqueado:
            if c_rst.button("↺", key="sl_ai_clear", help="Nuevo chat", use_container_width=True):
                st.session_state["sl_ai_msgs"] = []
                st.rerun()
        if c_cls.button("✕", key="sl_ai_close", help="Cerrar asistente", use_container_width=True):
            st.session_state["_sl_ai_drawer_open"] = False
            st.rerun()

        chat_body_html = _render_mensajes_html(msgs, av_src, mascot_src)

        if bloqueado:
            st.markdown(
                f'<div class="sl-ai-blur-stage">'
                f'<div class="sl-ai-blurred-bg">{chat_body_html}</div>'
                f'<div class="sl-ai-glass-overlay">'
                '<div class="sl-ai-bot-stage is-compact">'
                '<div class="sl-ai-bot-aura"></div>'
                f'<img class="sl-ai-glass-bot" src="{mascot_src}" alt="ScoreLine AI">'
                '</div>'
                f'<div class="sl-ai-glass-title">Ya usaste tu pregunta gratis de hoy</div>'
                f'<div class="sl-ai-glass-sub">Pasa a Pro para seguir analizando partidos, rachas y probabilidades sin límites.</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("★ Pasar a Pro", key="sl_ai_go_pro", use_container_width=True):
                st.session_state["_sl_ai_drawer_open"] = False
                st.session_state["_abrir_modal_pro"] = "Desbloquea consultas ilimitadas con ScoreLine AI."
                st.rerun()
            st.markdown('<div class="sl-ai-foot">ScoreLine AI analiza datos y no recomienda apuestas.</div>', unsafe_allow_html=True)
            return

        zona_chat = st.empty()
        zona_chat.markdown(chat_body_html, unsafe_allow_html=True)

        if msgs:
            _comp.html(
                '<script>try{var b=window.parent.document.getElementById("sl-ai-msgs-box");'
                'if(b)b.scrollTo({top:b.scrollHeight,behavior:"smooth"});}catch(e){}</script>',
                height=0,
                width=0,
            )

        # Sugerencias rápidas cuando el chat está vacío
        pregunta_chip = None
        if not msgs:
            sugs = [
                "¿Quién es favorito hoy?",
                "Partidos en vivo",
                "Explícame una probabilidad",
            ]
            for idx, sug in enumerate(sugs):
                if st.button(sug, key=f"sl_ai_sug_{idx}", use_container_width=True):
                    pregunta_chip = sug

        with st.form("sl_ai_form", clear_on_submit=True):
            c_inp, c_btn = st.columns([6.0, 1.0], vertical_alignment="center")
            texto = c_inp.text_input(
                "Mensaje",
                placeholder="Pregunta sobre un partido o métrica…",
                label_visibility="collapsed",
                key="sl_ai_input",
            )
            enviado = c_btn.form_submit_button("➤", use_container_width=True)

        st.markdown('<div class="sl-ai-foot">ScoreLine AI analiza datos y no recomienda apuestas.</div>', unsafe_allow_html=True)

        pregunta = (pregunta_chip or (texto if enviado else "")).strip()
        if pregunta:
            ahora = datetime.now().strftime("%H:%M")
            msgs.append({"role": "user", "content": pregunta, "ts": ahora})
            # Mostrar burbuja del usuario + indicador "escribiendo…" con 3 puntos
            zona_chat.markdown(
                _render_mensajes_html(msgs, av_src, mascot_src, escribiendo=True),
                unsafe_allow_html=True,
            )
            datos = _construir_datos_app(seccion_actual)
            ok, resp = _llamar_ia(pregunta, msgs[:-1], datos, seccion_actual)
            msgs.append({"role": "assistant", "content": resp, "ts": datetime.now().strftime("%H:%M")})
            if ok and not es_pro:
                _incrementar_uso_hoy()
            st.rerun()


modal_chat = panel_chat

