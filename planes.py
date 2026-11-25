"""Gestión centralizada de planes Freemium (Gratuito y Pro) para ScoreLine.

Única fuente de verdad para:
- Constantes: FUNCIONES_PRO, OFERTA_ENTRADA.
- Lectura de plan: obtener_plan(uid) -> 'gratis' | 'pro', es_pro(uid) -> bool.
- Persistencia en servidor: Firestore (`usuarios/{uid}.plan = "gratis" | "pro"`)
  con respaldo atómico local en `usuarios_planes.json` cuando Firestore no está configurado.
- Seguridad: bloque_pro() y html_bloque_pro() NUNCA envían `contenido_real` al cliente
  si el usuario tiene plan gratuito; en su lugar renderizan `contenido_falso` desenfocado.
- Placeholder de pago: iniciar_pago(uid) con documentación para Stripe / Flow / Mercado Pago.
"""
from __future__ import annotations

from html import escape as _esc
import json
import os
import threading
from typing import Any

import streamlit as st

import auth

OFERTA_ENTRADA = "Oferta de entrada: primera semana por $1.990 CLP (o 1 USD) · cancela cuando quieras."
PRECIO_MENSUAL_CLP = 9990
PRECIO_MENSUAL_USD = 9.99

# Cupones válidos: código en mayúsculas -> porcentaje de descuento (1..90)
CUPONES: dict[str, int] = {
    "SCORELINE20": 20,
    "BIENVENIDA": 30,
    "PRO50": 50,
}


def validar_cupon(codigo: str | None) -> tuple[bool, int, str]:
    """Valida un código promocional y retorna (es_valido, pct_descuento, mensaje)."""
    c = str(codigo or "").strip().upper()
    if not c:
        return False, 0, ""
    if c in CUPONES:
        pct = CUPONES[c]
        return True, pct, f"Cupón {c} aplicado: {pct}% de descuento."
    return False, 0, "Cupón no válido o expirado."

FUNCIONES_PRO = (
    "Pick o línea recomendada",
    "Probabilidad exacta Over/Under",
    "Simulación Monte Carlo (4.000 corridas)",
    "Modelo Poisson (marcador exacto y goles esperados)",
    "Línea de referencia y % de acierto de jugadores",
    "Cuotas sin margen, ROI y análisis de árbitros",
    "Lector de boletas de combinadas con IA",
)

_CARPETA = os.path.dirname(os.path.abspath(__file__))
_ARCHIVO_PLANES = os.path.join(_CARPETA, "usuarios_planes.json")
_LOCK = threading.Lock()
_DB_FIRESTORE = None
_MEMORIA_TESTS: dict[str, dict[str, Any]] | None = None


def _normalizar_uid(uid: str | None) -> str:
    return str(uid or "").strip().lower()


def _parsear_credencial_dict(valor: Any) -> dict[str, Any] | None:
    """Convierte un JSON string o mapping (p. ej. st.secrets) a dict de cuenta de servicio."""
    if not valor:
        return None
    if isinstance(valor, str):
        txt = valor.strip()
        if not txt.startswith("{"):
            return None
        try:
            data = json.loads(txt)
        except ValueError:
            return None
    elif hasattr(valor, "items"):
        data = {k: v for k, v in valor.items()}
    else:
        return None
    if not isinstance(data, dict) or "project_id" not in data:
        return None
    if isinstance(data.get("private_key"), str):
        data["private_key"] = data["private_key"].replace("\\n", "\n")
    return data


def _credencial_firebase(credentials_mod: Any):
    """Obtiene credencial de Firebase desde env var (ruta o JSON) o st.secrets."""
    for env_key in ("FIREBASE_CREDENTIALS", "GOOGLE_APPLICATION_CREDENTIALS"):
        val = (os.environ.get(env_key) or "").strip()
        if not val:
            continue
        if os.path.isfile(val):
            return credentials_mod.Certificate(val)
        info = _parsear_credencial_dict(val)
        if info:
            return credentials_mod.Certificate(info)

    try:
        secrets = st.secrets
        if "FIREBASE_CREDENTIALS" in secrets:
            val = secrets["FIREBASE_CREDENTIALS"]
            if isinstance(val, str) and os.path.isfile(val):
                return credentials_mod.Certificate(val)
            info = _parsear_credencial_dict(val)
            if info:
                return credentials_mod.Certificate(info)
        if "firebase" in secrets:
            sec = secrets["firebase"]
            for sub in ("FIREBASE_CREDENTIALS", "credentials"):
                if sub in sec:
                    info = _parsear_credencial_dict(sec[sub])
                    if info:
                        return credentials_mod.Certificate(info)
            info = _parsear_credencial_dict(sec)
            if info:
                return credentials_mod.Certificate(info)
    except Exception:  # noqa: BLE001
        pass
    return None


def _obtener_firestore():
    """Inicializa cliente Firestore desde variables de entorno o st.secrets."""
    global _DB_FIRESTORE
    if _DB_FIRESTORE is not None:
        return _DB_FIRESTORE
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            cred = _credencial_firebase(credentials)
            if cred is None:
                return None
            firebase_admin.initialize_app(cred)
        _DB_FIRESTORE = firestore.client()
        return _DB_FIRESTORE
    except Exception:  # noqa: BLE001
        return None


def _leer_local() -> dict[str, dict[str, Any]]:
    if _MEMORIA_TESTS is not None:
        return _MEMORIA_TESTS
    if not os.path.exists(_ARCHIVO_PLANES):
        return {}
    try:
        with open(_ARCHIVO_PLANES, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _escribir_local(data: dict[str, dict[str, Any]]) -> None:
    if _MEMORIA_TESTS is not None:
        return
    tmp = _ARCHIVO_PLANES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _ARCHIVO_PLANES)


# ---------------------------------------------------------------------------
# API pública (única fuente de verdad)
# ---------------------------------------------------------------------------
def uid_actual() -> str | None:
    """Retorna el UID (correo normalizado) del usuario autenticado, o None si es visitante."""
    try:
        usr = auth.usuario_actual()
        return _normalizar_uid(usr.get("email")) if usr else None
    except Exception:  # noqa: BLE001
        return None


def obtener_plan(uid: str | None = None) -> str:
    """Retorna 'pro' o 'gratis'. Visitante sin sesión siempre es 'gratis'."""
    uid = _normalizar_uid(uid)
    if not uid:
        return "gratis"

    # Compatibilidad con cuentas admin/pro existentes en auth.py
    try:
        usr = auth.usuario_actual()
        if usr and _normalizar_uid(usr.get("email")) == uid and usr.get("rol") in ("pro", "admin"):
            return "pro"
    except Exception:  # noqa: BLE001
        pass

    db = _obtener_firestore()
    if db is not None:
        snap = db.collection("usuarios").document(uid).get()
        doc = snap.to_dict() if snap.exists else None
    else:
        with _LOCK:
            doc = _leer_local().get(uid)

    if not doc:
        return "gratis"
    return "pro" if str(doc.get("plan", "")).lower() in ("pro", "premium", "admin") else "gratis"


def es_pro(uid: str | None = None) -> bool:
    """True solo si el usuario tiene plan 'pro' activo en servidor."""
    return obtener_plan(uid) == "pro"


def actualizar_plan_servidor(uid: str, plan: str) -> None:
    """Guarda `usuarios/{uid}.plan` ('gratis' | 'pro') en Firestore o respaldo local."""
    uid = _normalizar_uid(uid)
    if not uid:
        return
    plan_norm = "pro" if str(plan).lower() in ("pro", "premium", "admin") else "gratis"
    db = _obtener_firestore()
    if db is not None:
        db.collection("usuarios").document(uid).set({"plan": plan_norm}, merge=True)
        return
    with _LOCK:
        datos = _leer_local()
        doc = datos.get(uid) or {}
        doc["plan"] = plan_norm
        datos[uid] = doc
        _escribir_local(datos)


# ---------------------------------------------------------------------------
# Pasarela de pago (placeholder documentado)
# ---------------------------------------------------------------------------
def iniciar_pago(uid: str | None) -> str:
    """Placeholder para iniciar suscripción Pro.

    Cómo conectar Stripe Checkout (o Flow / Mercado Pago) en producción:
    1. En un endpoint Cloud Run / Cloud Function (`/api/crear-checkout`), crea una sesión de pago:
       - Stripe: `stripe.checkout.Session.create(mode="subscription", client_reference_id=uid,
         line_items=[{"price": PRICE_ID, "quantity": 1}], success_url=..., cancel_url=...)`
       - Flow / Mercado Pago: crea preferencia con `external_reference=uid`.
    2. Configura el webhook del proveedor (`/api/webhook-pago`) verificando su firma criptográfica:
       - Al recibir `checkout.session.completed` (Stripe) o `payment.approved` (MP/Flow),
         llama `actualizar_plan_servidor(uid, "pro")` para escribir `plan: "pro"`
         en Firestore `usuarios/{uid}`.
    3. Redirige al usuario a `session.url` desde el botón "Pasar a Pro".
    """
    uid = _normalizar_uid(uid)
    return f"?checkout=pendiente&uid={uid}"


# ---------------------------------------------------------------------------
# Modales y componentes reutilizables (seguridad en servidor)
# ---------------------------------------------------------------------------
@st.dialog("Planes ScoreLine · Suscripción Mensual", width="small")
def modal_pro(motivo: str = ""):
    """Modal con comparativa de planes mensuales, cupón de descuento y acceso Pro."""
    if motivo:
        st.caption(motivo)

    c_free, c_pro = st.columns(2)
    with c_free:
        st.markdown(
            """
            **Plan Gratuito · $0/mes**
            - Marcadores en vivo y calendario
            - Planteles completos y lesionados
            - Posiciones Este / Oeste
            - Top Expected (aciertos pasados)
            - 1 jugador por vez (PTS, 5 PJ)
            """
        )
    with c_pro:
        st.markdown(
            f"""
            **★ ScoreLine Pro · ${PRECIO_MENSUAL_CLP:,} CLP/mes**
            - Comparador completo + autoanálisis (5/10/15/20 PJ)
            - Simulación stats vs rival reciente
            - Cuota rentable (EV/ROI) + Análisis IA
            - Top Expected próximos + Alertas favoritos
            - Boletas IA + todas las métricas
            """.replace(",", ".")
        )

    cupon_in = st.text_input("¿Tienes un cupón de descuento?", placeholder="Ej. SCORELINE20", key="pro_cupon_in")
    ok_cup, pct_cup, msg_cup = validar_cupon(cupon_in)
    if cupon_in.strip():
        if ok_cup:
            precio_final = round(PRECIO_MENSUAL_CLP * (100 - pct_cup) / 100)
            st.success(f"{msg_cup} Primer mes: **${precio_final:,} CLP**.".replace(",", "."))
        else:
            st.warning(msg_cup)

    st.info(OFERTA_ENTRADA)
    uid = uid_actual()
    if not uid:
        st.caption("Inicia sesión o crea tu cuenta gratuita para activar tu suscripción.")
        t1, t2 = st.tabs(["Iniciar sesión", "Crear cuenta gratis"])
        with t1:
            with st.form("form_pro_login"):
                mail = st.text_input("Correo", placeholder="tu@correo.com")
                pwd = st.text_input("Contraseña", type="password")
                if st.form_submit_button("Ingresar", type="primary", use_container_width=True):
                    ok, msg = auth.iniciar_sesion(mail, pwd)
                    if ok:
                        st.rerun()
                    else:
                        st.error(msg)
        with t2:
            with st.form("form_pro_reg"):
                nom = st.text_input("Nombre", placeholder="Carlos")
                rmail = st.text_input("Correo", placeholder="tu@correo.com")
                rpwd = st.text_input("Contraseña (mín. 6)", type="password")
                mayor18 = st.checkbox("Declaro tener al menos 18 años")
                if st.form_submit_button("Crear cuenta", use_container_width=True):
                    if not mayor18:
                        st.error("Debes confirmar que tienes al menos 18 años.")
                    else:
                        ok, msg = auth.registrar_usuario(nom, rmail, rpwd)
                        if ok:
                            auth.iniciar_sesion(rmail, rpwd)
                            st.rerun()
                        else:
                            st.error(msg)
        return

    c1, c2 = st.columns(2)
    if c1.button("Pasar a Pro", type="primary", key="btn_modal_go_pro", use_container_width=True):
        url = iniciar_pago(uid)
        st.success(f"Checkout preparado ({url}). En producción redirige a la pasarela de pago.")
    if c2.button("Seguir gratis", key="btn_modal_stay_gratis", use_container_width=True):
        st.rerun()


def html_bloque_pro(titulo: str, contenido_real: str, contenido_falso: str, uid: str | None = None) -> str:
    """Genera HTML seguro: si es Pro envía `contenido_real`; si es Gratis envía `contenido_falso` desenfocado.

    Garantiza que inspeccionando el HTML como usuario gratuito NO aparezca ningún dato real.
    """
    uid_eff = uid_actual() if uid is None else uid
    if es_pro(uid_eff):
        return f'<div class="sl-pro-open"><span class="sl-pro-tag">★ {_esc(titulo)}</span> {contenido_real}</div>'
    return (
        f'<div class="sl-pro-locked" title="Solo con plan Pro">'
        f'<div class="sl-pro-blur" aria-hidden="true">{contenido_falso}</div>'
        f'<div class="sl-pro-overlay"><span class="sl-gold-tag">★ Pro</span> <span>Solo con plan Pro</span></div>'
        f'</div>'
    )


def bloque_pro(titulo: str, contenido_real: str, contenido_falso: str = "Contenido exclusivo Pro", key: str = "", en_dialogo: bool = False) -> None:
    """Componente reutilizable Streamlit: renderiza dato real para Pro o dato falso desenfocado + botón modal."""
    uid = uid_actual()
    if es_pro(uid):
        st.markdown(f"**★ {_esc(titulo)}:** {contenido_real}")
        return
    st.markdown(
        f'<div class="sl-pro-box">'
        f'<div class="sl-pro-box-title">{_esc(titulo)}</div>'
        f'{html_bloque_pro(titulo, contenido_real, contenido_falso, uid=uid)}'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.button("🔒 Desbloquear con ScoreLine Pro", key=key or f"btn_pro_{abs(hash(titulo))}", use_container_width=True):
        motivo = f"Desbloquea «{titulo}» y todas las métricas avanzadas con ScoreLine Pro."
        if en_dialogo:
            st.session_state["_abrir_modal_pro"] = motivo
            st.rerun()
        else:
            modal_pro(motivo)


def insignia_sidebar():
    """Muestra tarjeta ScoreLine Pro dorada en el sidebar (o insignia activa si ya es Pro)."""
    uid = uid_actual()
    if es_pro(uid):
        st.sidebar.markdown(
            '<div class="sl-plan-pill is-pro">★ ScoreLine Pro · Acceso total</div>',
            unsafe_allow_html=True,
        )
        return
    st.sidebar.markdown(
        '<div class="sl-sb-pro-card">'
        '<div class="sl-sb-pro-head">★ ScoreLine Pro</div>'
        '<div class="sl-sb-pro-list">'
        '<div class="sl-sb-pro-item"><span class="sl-sb-pro-dot">✓</span><span>Proyecciones exactas</span></div>'
        '<div class="sl-sb-pro-item"><span class="sl-sb-pro-dot">✓</span><span>Líneas recomendadas</span></div>'
        '<div class="sl-sb-pro-item"><span class="sl-sb-pro-dot">✓</span><span>Alertas avanzadas</span></div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if st.sidebar.button("Mejorar a Pro", type="primary", key="sb_btn_mejorar_pro", use_container_width=True):
        modal_pro()


def banner_plan_header():
    """Banner Pro: solo se muestra si no hay tarjeta Pro en sidebar (evita llamada doble).
    Se omite aquí porque la tarjeta Pro del sidebar ya cubre la CTA principal.
    El bloqueo per-feature se muestra en cada bloque_pro() en su punto de uso.
    """
    # No se renderiza nada: la tarjeta Pro en el sidebar + el modal en cada bloque Pro son suficientes.
    return
