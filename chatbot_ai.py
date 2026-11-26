"""ScoreLine AI: asistente de análisis deportivo basado exclusivamente en datos de la app.

- Lee el system prompt desde `scoreline-ai-system-prompt.md`.
- Aplica límite diario en servidor (1 consulta/día para plan gratuito, ilimitado para Pro)
  usando Firestore (`ai_uso/{clave_dia}`) con respaldo atómico en `ai_uso.json`.
- Usa claves de API desde `st.secrets` o variables de entorno (nunca en el navegador).
"""
from __future__ import annotations

import base64
from datetime import date
import hashlib
from html import escape as _esc
import json
import os
import threading
from typing import Any

import requests
import streamlit as st

import planes

LIMITE_GRATIS_DIA = 1

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
def _construir_datos_app(seccion: str) -> str:
    lineas = [f"Sección activa: {seccion or 'Inicio'}", f"Fecha: {date.today().isoformat()}"]
    try:
        import inicio
        _, partidos = inicio._resumen_dia()
        if partidos:
            lineas.append(f"Partidos del día ({len(partidos)} total, mostrando hasta 25):")
            for m in partidos[:25]:
                h = m.get("home") or {}
                a = m.get("away") or {}
                st_m = m.get("state", "pre")
                if st_m == "in":
                    est = f"EN VIVO {h.get('score', '-')}-{a.get('score', '-')} ({m.get('hora', '')})"
                elif st_m == "post":
                    est = f"FINAL {h.get('score', '-')}-{a.get('score', '-')}"
                else:
                    est = f"Programado {m.get('hora', '')}"
                prob = m.get("prob")
                prob_txt = f" · Prob Local {prob}%" if prob is not None else ""
                lineas.append(
                    f"- [{m.get('deporte', '')} · {m.get('liga', '')}] "
                    f"{h.get('nombre', '?')} (Local) vs {a.get('nombre', '?')} (Visita): {est}{prob_txt}"
                )
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


def _llamar_ia(pregunta: str, historial: list[dict[str, str]], datos_app: str) -> tuple[bool, str]:
    sys_prompt = _leer_prompt() + "\n\n" + datos_app

    # 1) Gemini API (vía REST con requests, sin dependencias extra)
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

    # 2) Anthropic Claude (ya instalado en requirements.txt)
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

    # 3) OpenAI fallback
    oai_key = _secret("OPENAI_API_KEY")
    if oai_key:
        msgs = [{"role": "system", "content": sys_prompt}]
        msgs.extend({"role": m["role"], "content": m["content"]} for m in historial[-6:])
        msgs.append({"role": "user", "content": pregunta})
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {oai_key}"},
                json={"model": _secret("OPENAI_MODEL") or "gpt-4o-mini", "messages": msgs, "temperature": 0.4, "max_tokens": 420},
                timeout=20,
            )
            if r.ok:
                txt = (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                if txt:
                    return True, txt
        except requests.RequestException:
            pass

    return False, (
        "ScoreLine AI aún no tiene configurada su clave en el servidor "
        "(agrega `GEMINI_API_KEY` o `ANTHROPIC_API_KEY` en los Secrets de Streamlit)."
    )


# ---------------------------------------------------------------------------
# Diálogo UI de ScoreLine AI
# ---------------------------------------------------------------------------
@st.dialog("ScoreLine AI", width="large")
def modal_chat(seccion_actual: str = "") -> None:
    es_pro = planes.es_pro()
    usadas = 0 if es_pro else consultas_usadas_hoy()
    bloqueado = (not es_pro) and (usadas >= LIMITE_GRATIS_DIA)

    av_b64 = _img_b64("robot_avatar.png")
    mascot_b64 = _robot_por_seccion(seccion_actual)
    av_src = f"data:image/png;base64,{av_b64}" if av_b64 else ""
    mascot_src = f"data:image/png;base64,{mascot_b64}" if mascot_b64 else av_src

    badge_txt = "ScoreLine Pro · Ilimitado" if es_pro else f"Plan Gratuito · {max(0, LIMITE_GRATIS_DIA - usadas)}/{LIMITE_GRATIS_DIA} consulta hoy"
    badge_cls = "is-pro" if es_pro else ("is-empty" if bloqueado else "is-free")

    st.markdown(
        f'<div class="sl-ai-head">'
        f'<img class="sl-ai-head-ico" src="{av_src}" alt="ScoreLine AI">'
        f'<div class="sl-ai-head-info">'
        f'<div class="sl-ai-title">ScoreLine AI</div>'
        f'<div class="sl-ai-sub">Análisis deportivo con datos en tiempo real de la app</div>'
        f'</div>'
        f'<span class="sl-ai-badge {badge_cls}">{_esc(badge_txt)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if "sl_ai_msgs" not in st.session_state:
        st.session_state["sl_ai_msgs"] = []
    msgs: list[dict[str, str]] = st.session_state["sl_ai_msgs"]

    # Construir historial HTML
    if msgs:
        burbujas = []
        for m in msgs:
            if m["role"] == "user":
                burbujas.append(f'<div class="sl-ai-row user"><div class="sl-ai-bubble user">{_esc(m["content"])}</div></div>')
            else:
                burbujas.append(
                    f'<div class="sl-ai-row bot">'
                    f'<img class="sl-ai-msg-av" src="{av_src}" alt="">'
                    f'<div class="sl-ai-bubble bot">{_esc(m["content"])}</div>'
                    f'</div>'
                )
        chat_body_html = f'<div class="sl-ai-msgs">{"".join(burbujas)}</div>'
    else:
        chat_body_html = (
            '<div class="sl-ai-welcome">'
            f'<img class="sl-ai-welcome-img" src="{mascot_src}" alt="ScoreLine AI">'
            '<div class="sl-ai-welcome-txt">Pregúntame sobre los partidos de hoy, probabilidades de ScoreLine, forma reciente o métricas.</div>'
            '</div>'
        )

    if bloqueado:
        # Efecto cristal suave difuminado + robot + botón Pasar a Pro con animación de entrada
        st.markdown(
            f'<div class="sl-ai-blur-stage">'
            f'<div class="sl-ai-blurred-bg">{chat_body_html}</div>'
            f'<div class="sl-ai-glass-overlay">'
            f'<img class="sl-ai-glass-bot" src="{mascot_src}" alt="ScoreLine AI">'
            f'<div class="sl-ai-glass-title">Alcanzaste tu consulta gratis de hoy</div>'
            f'<div class="sl-ai-glass-sub">Pasa a ScoreLine Pro para hacer preguntas ilimitadas sobre todos los partidos y métricas.</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("★ Pasar a Pro", type="primary", key="sl_ai_go_pro", use_container_width=True):
            st.session_state["_abrir_modal_pro"] = "Desbloquea consultas ilimitadas con ScoreLine AI."
            st.rerun()
        return

    st.markdown(chat_body_html, unsafe_allow_html=True)

    # Sugerencias rápidas cuando el chat está vacío
    pregunta_chip = None
    if not msgs:
        sugs = [
            "¿Qué partidos hay en vivo ahora?",
            "¿Por qué tiene mayor probabilidad el favorito hoy?",
            "¿Cómo interpreto las métricas de ScoreLine?",
        ]
        cols_s = st.columns(3, gap="small")
        for idx, sug in enumerate(sugs):
            if cols_s[idx].button(sug, key=f"sl_ai_sug_{idx}", use_container_width=True):
                pregunta_chip = sug

    with st.form("sl_ai_form", clear_on_submit=True):
        c_inp, c_btn = st.columns([4.4, 1.1], vertical_alignment="center")
        texto = c_inp.text_input(
            "Mensaje",
            placeholder="Escribe tu pregunta sobre un partido o métrica...",
            label_visibility="collapsed",
            key="sl_ai_input",
        )
        enviado = c_btn.form_submit_button("Enviar", type="primary", use_container_width=True)

    pregunta = (pregunta_chip or (texto if enviado else "")).strip()
    if pregunta:
        datos = _construir_datos_app(seccion_actual)
        with st.spinner("Analizando datos de ScoreLine..."):
            ok, resp = _llamar_ia(pregunta, msgs, datos)
        msgs.append({"role": "user", "content": pregunta})
        msgs.append({"role": "assistant", "content": resp})
        if ok and not es_pro:
            _incrementar_uso_hoy()
        st.rerun()

