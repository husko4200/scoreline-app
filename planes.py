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

OFERTA_ENTRADA = "Oferta de bienvenida: primera semana por $1.990 CLP (o $1 USD) · Cancela en 1 clic cuando quieras."
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
    if uid is None:
        uid = uid_actual()
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
@st.dialog("Elige tu plan ScoreLine", width="large")
def modal_pro(motivo: str = ""):
    """Modal profesional con comparativa de planes, cupón de descuento y acceso Pro."""
    sub_txt = motivo or "Proyecciones avanzadas, cuotas con valor esperado (EV) y verificación ilimitada en un solo lugar."
    st.markdown(
        f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-left:3px solid #4F46E5;'
        f'border-radius:10px;padding:10px 14px;margin-bottom:12px;font-size:.86rem;color:#334155;">'
        f'<b style="color:#0F172A;">Análisis deportivo de nivel profesional</b> · {_esc(sub_txt)}'
        f'</div>',
        unsafe_allow_html=True,
    )

    cupon_in = st.text_input("¿Tienes un cupón de descuento?", placeholder="Ej. SCORELINE20", key="pro_cupon_in")
    ok_cup, pct_cup, msg_cup = validar_cupon(cupon_in)
    precio_txt = f"${PRECIO_MENSUAL_CLP:,}".replace(",", ".")
    precio_html = f'<span style="font-size:1.55rem;font-weight:800;color:#0F172A;">{precio_txt}</span> <span style="font-size:.82rem;color:#64748B;">CLP / mes</span>'
    if cupon_in.strip():
        if ok_cup:
            precio_final = round(PRECIO_MENSUAL_CLP * (100 - pct_cup) / 100)
            pf_txt = f"${precio_final:,}".replace(",", ".")
            precio_html = (
                f'<span style="font-size:.95rem;color:#94A3B8;text-decoration:line-through;margin-right:6px;">{precio_txt}</span>'
                f'<span style="font-size:1.55rem;font-weight:800;color:#047857;">{pf_txt}</span> '
                f'<span style="font-size:.82rem;color:#047857;font-weight:700;">CLP 1.er mes (-{pct_cup}%)</span>'
            )
            st.success(f"{msg_cup} Primer mes: **{pf_txt} CLP**.")
        else:
            st.warning(msg_cup)

    st.markdown(
        f"""
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin:8px 0 14px;">
          <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:16px;padding:16px 18px;display:flex;flex-direction:column;justify-content:space-between;">
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <span style="font-weight:800;font-size:1.02rem;color:#0F172A;">Plan Esencial</span>
                <span style="font-size:.68rem;font-weight:700;padding:2px 8px;border-radius:999px;background:#F1F5F9;color:#475569;border:1px solid #E2E8F0;">GRATIS</span>
              </div>
              <div style="margin-bottom:12px;">
                <span style="font-size:1.55rem;font-weight:800;color:#0F172A;">$0</span>
                <span style="font-size:.82rem;color:#64748B;">CLP / mes</span>
              </div>
              <div style="font-size:.82rem;color:#334155;line-height:1.65;">
                <div>✓ Marcadores en vivo y agenda diaria</div>
                <div>✓ Planteles completos y reporte de lesiones</div>
                <div>✓ Posiciones y rachas básicas de equipos</div>
                <div>✓ Top Expected pasados + 1 partido gratis</div>
                <div>✓ Ficha individual (últimos 5 partidos)</div>
              </div>
            </div>
            <div style="margin-top:12px;padding-top:10px;border-top:1px dashed #E2E8F0;font-size:.74rem;color:#64748B;">
              Ideal para seguir marcadores y resultados del día.
            </div>
          </div>

          <div style="background:linear-gradient(180deg,#F5F7FF 0%,#FFFFFF 45%);border:2px solid #4F46E5;border-radius:16px;padding:16px 18px;box-shadow:0 10px 26px -10px rgba(79,70,229,.22);display:flex;flex-direction:column;justify-content:space-between;">
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <span style="font-weight:800;font-size:1.02rem;color:#1E1B4B;">★ ScoreLine Pro</span>
                <span style="font-size:.68rem;font-weight:800;padding:2px 9px;border-radius:999px;background:#4F46E5;color:#FFFFFF;letter-spacing:.03em;">RECOMENDADO</span>
              </div>
              <div style="margin-bottom:12px;">{precio_html}</div>
              <div style="font-size:.82rem;color:#1E293B;line-height:1.65;">
                <div><b style="color:#4F46E5;">★</b> <b>Comparador total</b> y autoanálisis (5 a 20 PJ)</div>
                <div><b style="color:#4F46E5;">★</b> <b>Simulación estadística</b> frente al rival reciente</div>
                <div><b style="color:#4F46E5;">★</b> <b>Cuotas con valor real (EV/ROI)</b> + análisis IA</div>
                <div><b style="color:#4F46E5;">★</b> <b>Top Expected próximos</b> y alertas de favoritos</div>
                <div><b style="color:#4F46E5;">★</b> <b>Verificación ilimitada</b>, boletas IA y métricas</div>
              </div>
            </div>
            <div style="margin-top:12px;padding-top:10px;border-top:1px dashed #C7D2FE;font-size:.74rem;color:#4338CA;font-weight:600;">
              Acceso inmediato a toda la plataforma sin límites.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div style="background:linear-gradient(90deg,#FFFBEB,#EEF2FF);border:1px solid #FDE68A;'
        f'border-radius:12px;padding:10px 14px;margin-bottom:10px;font-size:.82rem;color:#1E293B;text-align:center;">'
        f'⚡ <b>{_esc(OFERTA_ENTRADA)}</b>'
        f'</div>',
        unsafe_allow_html=True,
    )
    uid = uid_actual()
    if not uid:
        st.markdown(
            '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;'
            'margin:6px 0 4px;padding-top:8px;border-top:1px solid #E2E8F0;">'
            '<span style="font-weight:700;font-size:.92rem;color:#0F172A;">🔐 Accede a tu cuenta</span>'
            '<span style="font-size:.76rem;color:#64748B;">Inicia sesión o regístrate gratis para continuar</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        t1, t2 = st.tabs(["👤 Iniciar sesión", "✨ Crear cuenta gratis"])
        with t1:
            with st.form("form_pro_login"):
                st.markdown(
                    '<div style="font-size:.82rem;color:#64748B;margin-bottom:6px;">'
                    'Bienvenido de nuevo · Ingresa con tu correo y contraseña.'
                    '</div>',
                    unsafe_allow_html=True,
                )
                mail = st.text_input("Correo electrónico", placeholder="tu@correo.com")
                pwd = st.text_input("Contraseña", type="password", placeholder="••••••••")
                if st.form_submit_button("Ingresar a ScoreLine", type="primary", use_container_width=True):
                    ok, msg = auth.iniciar_sesion(mail, pwd)
                    if ok:
                        st.rerun()
                    else:
                        st.error(msg)
        with t2:
            with st.form("form_pro_reg"):
                st.markdown(
                    '<div style="font-size:.82rem;color:#64748B;margin-bottom:6px;">'
                    'Crea tu cuenta gratuita en segundos · Sin tarjeta requerida.'
                    '</div>',
                    unsafe_allow_html=True,
                )
                c_n, c_m = st.columns(2)
                nom = c_n.text_input("Nombre", placeholder="Carlos")
                rmail = c_m.text_input("Correo electrónico", placeholder="tu@correo.com")
                rpwd = st.text_input("Contraseña (mínimo 6 caracteres)", type="password", placeholder="••••••••")
                mayor18 = st.checkbox("Confirmo que soy mayor de 18 años")
                if st.form_submit_button("✨ Crear mi cuenta gratis", type="primary", use_container_width=True):
                    if not mayor18:
                        st.error("Debes confirmar que tienes al menos 18 años.")
                    else:
                        ok, msg = auth.registrar_usuario(nom, rmail, rpwd)
                        if ok:
                            auth.iniciar_sesion(rmail, rpwd)
                            st.rerun()
                        else:
                            st.error(msg)
                st.markdown(
                    '<div style="text-align:center;font-size:.73rem;color:#94A3B8;margin-top:6px;">'
                    '🔒 Tus datos están protegidos · Cancela cuando quieras'
                    '</div>',
                    unsafe_allow_html=True,
                )
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
        '<div class="sl-sb-pro-head"><span data-icon="pro" data-size="14" style="display:inline-flex;vertical-align:middle;margin-right:4px;"></span>ScoreLine Pro</div>'
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



def aviso_gratuito(etiqueta: str, texto_html: str) -> None:
    """Muestra un aviso destacado y elegante para el alcance del Plan Gratuito."""
    st.markdown(
        f'<div class="sl-free-banner">'
        f'<span class="sl-free-tag">✦ {etiqueta}</span>'
        f'<span class="sl-free-msg">{texto_html}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
