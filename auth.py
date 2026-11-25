"""Módulo de autenticación Freemium, gestión de suscripciones PRO y control de anuncios.

Permite:
- Navegación libre para visitantes sin forzar login.
- Botón en barra superior y menú lateral para Iniciar Sesión / Registrarse.
- Distinción de niveles: 'invitado', 'gratuito', 'pro' y 'admin'.
- Candado visual para bloquear herramientas exclusivas a usuarios de pago (PRO).
- Banners de anuncios para usuarios gratuitos (que se ocultan automáticamente al pagar).
- Panel de administración para activar clientes con fechas de vencimiento.
"""
import hashlib
import json
import os
import secrets
from datetime import date, datetime
import streamlit as st

_CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_USUARIOS = os.path.join(_CARPETA, "usuarios.json")
CLAVE_SESION = "auth_usuario"
MODAL_KEY = "abrir_modal_login"


# ---------------------------------------------------------------------------
# Seguridad y Criptografía
# ---------------------------------------------------------------------------
def _generar_salt() -> str:
    return secrets.token_hex(16)


def _hashear(password: str, salt: str) -> str:
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,
    )
    return hash_bytes.hex()


# ---------------------------------------------------------------------------
# Persistencia de Usuarios (Firestore con respaldo local en usuarios.json)
# ---------------------------------------------------------------------------
def _db_firestore():
    """Obtiene el cliente Firestore compartido sin provocar importación circular."""
    try:
        import planes
        return planes._obtener_firestore()
    except Exception:
        return None


def _admin_defecto() -> dict:
    salt = _generar_salt()
    pwd_def = os.environ.get("ADMIN_DEFAULT_PASS", "admin123")
    try:
        pwd_def = str(st.secrets.get("ADMIN_DEFAULT_PASS", pwd_def) or pwd_def)
    except Exception:
        pass
    return {
        "nombre": "Administrador",
        "email": "admin@deporte.com",
        "salt": salt,
        "password_hash": _hashear(pwd_def, salt),
        "rol": "admin",
        "plan": "pro",
        "activo": True,
        "vence": None,
        "creado": str(date.today()),
    }


def _cargar_usuarios_local() -> dict:
    if not os.path.exists(ARCHIVO_USUARIOS):
        usuarios_defecto = {"admin@deporte.com": _admin_defecto()}
        _guardar_usuarios_local(usuarios_defecto)
        return usuarios_defecto
    try:
        with open(ARCHIVO_USUARIOS, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _guardar_usuarios_local(usuarios: dict) -> bool:
    try:
        with open(ARCHIVO_USUARIOS, "w", encoding="utf-8") as f:
            json.dump(usuarios, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def _cargar_usuarios() -> dict:
    db = _db_firestore()
    if db is not None:
        try:
            usuarios = {}
            for snap in db.collection("usuarios").stream():
                data = snap.to_dict() or {}
                if "password_hash" in data or "email" in data:
                    usuarios[snap.id] = data
            if "admin@deporte.com" not in usuarios:
                adm = _admin_defecto()
                db.collection("usuarios").document("admin@deporte.com").set(adm, merge=True)
                usuarios["admin@deporte.com"] = adm
            return usuarios
        except Exception:
            pass
    return _cargar_usuarios_local()


def _guardar_usuarios(usuarios: dict) -> bool:
    db = _db_firestore()
    if db is not None:
        try:
            for mail, datos in usuarios.items():
                doc = dict(datos)
                doc["plan"] = "pro" if doc.get("rol") in ("pro", "admin") else "gratis"
                db.collection("usuarios").document(mail).set(doc, merge=True)
            return True
        except Exception:
            return False
    return _guardar_usuarios_local(usuarios)


def _obtener_usuario(email: str) -> dict | None:
    db = _db_firestore()
    if db is not None:
        try:
            snap = db.collection("usuarios").document(email).get()
            if snap.exists:
                data = snap.to_dict() or {}
                if "password_hash" in data:
                    return data
            if email == "admin@deporte.com":
                adm = _admin_defecto()
                db.collection("usuarios").document(email).set(adm, merge=True)
                return adm
            return None
        except Exception:
            pass
    return _cargar_usuarios_local().get(email)


def _guardar_usuario(email: str, datos: dict) -> bool:
    doc = dict(datos)
    doc["plan"] = "pro" if doc.get("rol") in ("pro", "admin") else "gratis"
    db = _db_firestore()
    if db is not None:
        try:
            db.collection("usuarios").document(email).set(doc, merge=True)
            return True
        except Exception:
            return False
    usuarios = _cargar_usuarios_local()
    usuarios[email] = doc
    return _guardar_usuarios_local(usuarios)


def _eliminar_usuario(email: str) -> bool:
    db = _db_firestore()
    if db is not None:
        try:
            db.collection("usuarios").document(email).delete()
            return True
        except Exception:
            return False
    usuarios = _cargar_usuarios_local()
    if email in usuarios:
        del usuarios[email]
        return _guardar_usuarios_local(usuarios)
    return True


# ---------------------------------------------------------------------------
# Control de Sesión y Niveles de Usuario
# ---------------------------------------------------------------------------
def usuario_actual() -> dict | None:
    return st.session_state.get(CLAVE_SESION)


def esta_autenticado() -> bool:
    usr = usuario_actual()
    if not usr:
        return False
    if not usr.get("activo", True):
        cerrar_sesion()
        return False
    vence = usr.get("vence")
    if vence:
        try:
            if date.today() > datetime.strptime(vence, "%Y-%m-%d").date():
                usr["rol"] = "gratuito"  # si venció, baja a plan gratuito
        except ValueError:
            pass
    return True


def es_pro() -> bool:
    """Retorna True si el usuario tiene plan de pago activo o es administrador."""
    if not esta_autenticado():
        return False
    usr = usuario_actual()
    return usr.get("rol") in ("pro", "admin")


def es_admin() -> bool:
    return esta_autenticado() and usuario_actual().get("rol") == "admin"


def cerrar_sesion():
    if CLAVE_SESION in st.session_state:
        del st.session_state[CLAVE_SESION]
    st.rerun()


def iniciar_sesion(email: str, password: str) -> tuple[bool, str]:
    email = email.strip().lower()
    usr = _obtener_usuario(email)
    if not usr:
        return False, "Usuario o contraseña incorrectos."
    if not usr.get("activo", True):
        return False, "Esta cuenta ha sido desactivada."

    salt = usr.get("salt", "")
    if _hashear(password, salt) != usr.get("password_hash"):
        return False, "Usuario o contraseña incorrectos."

    rol = usr.get("rol", "gratuito")
    if rol == "gratuito" and str(usr.get("plan", "")).lower() in ("pro", "premium"):
        rol = "pro"
    vence = usr.get("vence")
    if vence:
        try:
            if date.today() > datetime.strptime(vence, "%Y-%m-%d").date():
                rol = "gratuito"
        except ValueError:
            pass

    st.session_state[CLAVE_SESION] = {
        "email": usr.get("email", email),
        "nombre": usr.get("nombre", email.split("@")[0]),
        "rol": rol,
        "activo": usr.get("activo", True),
        "vence": usr.get("vence"),
    }
    return True, "¡Sesión iniciada con éxito!"


def registrar_usuario(nombre: str, email: str, password: str, rol: str = "gratuito", vence: str | None = None) -> tuple[bool, str]:
    email = email.strip().lower()
    if not email or "@" not in email:
        return False, "Ingresa un correo electrónico válido."
    if len(password) < 6:
        return False, "La contraseña debe tener al menos 6 caracteres."

    if _obtener_usuario(email):
        return False, "Ya existe una cuenta con este correo."

    salt = _generar_salt()
    nuevo = {
        "nombre": nombre.strip() or email.split("@")[0],
        "email": email,
        "salt": salt,
        "password_hash": _hashear(password, salt),
        "rol": rol,
        "activo": True,
        "vence": vence,
        "creado": str(date.today()),
    }
    _guardar_usuario(email, nuevo)
    return True, "Cuenta creada exitosamente."


# ---------------------------------------------------------------------------
# Componentes Visuales: Barra Superior, Login Modal y Candados PRO
# ---------------------------------------------------------------------------
_CSS_AUTH = """
<style>
/* Barra superior de usuario */
.auth-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 1.1rem;
    margin-bottom: 1.2rem;
    background: #ffffff;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    box-shadow: 0 2px 8px -2px rgba(15, 23, 42, 0.05);
}
.auth-bar-left {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.88rem;
    color: #475569;
}
.auth-badge-pro {
    background: linear-gradient(135deg, #F59E0B, #D97706);
    color: #ffffff;
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    box-shadow: 0 2px 8px rgba(245, 158, 11, 0.35);
}
.auth-badge-free {
    background: #F1F5F9;
    color: #475569;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 0.2rem 0.55rem;
    border-radius: 999px;
}
/* Tarjeta de bloqueo PRO */
.pro-card-lock {
    background: radial-gradient(circle at 10% 20%, rgba(245, 158, 11, 0.08), transparent 45%), #ffffff;
    border: 1px solid rgba(245, 158, 11, 0.35);
    border-radius: 20px;
    padding: 2.2rem 2rem;
    text-align: center;
    margin: 1.5rem 0;
    box-shadow: 0 14px 34px -10px rgba(245, 158, 11, 0.14);
}
.pro-crown {
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
    display: inline-block;
}
.pro-title {
    font-size: 1.4rem;
    font-weight: 800;
    color: #0F172A;
    margin-bottom: 0.4rem;
    font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
}
.pro-desc {
    font-size: 0.92rem;
    color: #64748B;
    max-width: 500px;
    margin: 0 auto 1.4rem;
    line-height: 1.5;
}
/* Banner de anuncios para usuarios gratis */
.ad-banner {
    background: linear-gradient(90deg, #F8FAFC 0%, #EEF2F6 100%);
    border: 1px dashed #CBD5E1;
    border-radius: 12px;
    padding: 0.9rem 1.2rem;
    margin: 1rem 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
}
.ad-text {
    font-size: 0.82rem;
    color: #64748B;
}
.ad-tag {
    font-size: 0.68rem;
    font-weight: 700;
    background: #E2E8F0;
    color: #475569;
    padding: 0.15rem 0.45rem;
    border-radius: 4px;
    margin-right: 0.4rem;
}
.sl-auth-status {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding-top: 0.35rem;
}
@media (max-width: 768px) {
    .sl-auth-status {
        justify-content: center !important;
        text-align: center !important;
        width: 100% !important;
        padding-top: 0 !important;
    }
}
</style>
"""


def barra_superior():
    """Barra superior elegante con estado del usuario y botón de login/registro."""
    try:
        st.markdown(_CSS_AUTH, unsafe_allow_html=True)
        usr = usuario_actual()

        col_izq, col_der = st.columns([2.5, 1])

        with col_izq:
            if esta_autenticado():
                badge = '<span class="auth-badge-pro">⭐ PRO ACTIVO</span>' if es_pro() else '<span class="auth-badge-free">MODO GRATUITO</span>'
                if es_admin():
                    badge = '<span class="auth-badge-pro" style="background:#4F46E5;">👑 ADMIN</span>'
                st.markdown(
                    f'<div class="sl-auth-status">'
                    f'<span style="font-weight:700; color:#0F172A;">Hola, {usr.get("nombre")}</span> {badge}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="sl-auth-status" style="gap:0.5rem;">'
                    '<span style="font-weight:700; color:#0F172A;">ScoreLine · Acceso gratuito</span> '
                    '</div>',
                    unsafe_allow_html=True,
                )

        with col_der:
            if esta_autenticado():
                if st.button("🚪 Cerrar sesión", key="top_logout", use_container_width=True):
                    cerrar_sesion()
            else:
                if st.button("✨ Iniciar Sesión / Registrarse", type="primary", key="top_login", use_container_width=True):
                    st.session_state[MODAL_KEY] = True

        # Si se pulsa el botón, mostrar formulario desplegable
        if st.session_state.get(MODAL_KEY, False):
            dialogo_autenticacion()
    except Exception:
        pass


def dialogo_autenticacion():
    """Ventana o expander de inicio de sesión y registro."""
    with st.expander("⚡ ScoreLine · Acceso a tu Cuenta / Suscripción PRO", expanded=True):
        t1, t2, t3 = st.tabs(["Iniciar Sesión", "Crear Cuenta Gratis", "💎 Adquirir Plan PRO"])

        with t1:
            with st.form("form_modal_login"):
                email = st.text_input("Correo", placeholder="tu@correo.com", key="m_email")
                pwd = st.text_input("Contraseña", type="password", key="m_pass")
                if st.form_submit_button("Ingresar", type="primary", use_container_width=True):
                    ok, msg = iniciar_sesion(email, pwd)
                    if ok:
                        st.session_state[MODAL_KEY] = False
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        with t2:
            with st.form("form_modal_reg"):
                nom = st.text_input("Tu Nombre", placeholder="Carlos", key="m_nom")
                reg_mail = st.text_input("Correo", placeholder="carlos@correo.com", key="m_reg_mail")
                reg_pwd = st.text_input("Contraseña (mínimo 6 caracteres)", type="password", key="m_reg_pwd")
                if st.form_submit_button("Crear cuenta gratuita", use_container_width=True):
                    ok, msg = registrar_usuario(nom, reg_mail, reg_pwd)
                    if ok:
                        st.success(f"{msg} Inicia sesión en la pestaña 'Iniciar Sesión'.")
                    else:
                        st.error(msg)

        with t3:
            st.markdown(
                """
                ### 🚀 Ventajas del Plan PRO:
                * **Sin Anuncios:** Navegación 100% limpia sin interrupciones.
                * **Picks Predictivos Automáticos:** Modelo Poisson con cuotas de alto valor.
                * **Simulación Monte Carlo (4.000 iteraciones):** Minutos y estadísticas simuladas de la NBA.
                * **Lector de Boletas de Apuestas con IA:** Sube la foto de tu combinada y calcula la probabilidad real.
                
                👉 **¿Quieres activarlo?** Contáctanos por WhatsApp o correo para habilitar tu acceso mensual o anual al instante.
                """
            )
        if st.button("Cerrar ventana de acceso", key="cerrar_modal"):
            st.session_state[MODAL_KEY] = False
            st.rerun()


def perfil_sidebar():
    """Widget de cuenta en la barra lateral."""
    try:
        usr = usuario_actual()
        if esta_autenticado():
            rol_txt = "👑 Administrador" if es_admin() else ("⭐ Suscripción PRO" if es_pro() else "Plan Gratuito")
            st.sidebar.markdown(
                f"""
                <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px; padding: 0.75rem 0.9rem; margin-bottom: 0.8rem;">
                    <div style="display: flex; align-items: center; gap: 0.6rem;">
                        <div style="width: 32px; height: 32px; border-radius: 50%; background: #4F46E5; color: #fff; display: grid; place-items: center; font-weight: 700; font-size: 0.82rem;">
                            {usr.get('nombre', 'U')[:1].upper()}
                        </div>
                        <div style="min-width: 0; flex: 1;">
                            <div style="font-weight: 700; font-size: 0.84rem; color: #0F172A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                {usr.get('nombre')}
                            </div>
                            <div style="font-size: 0.72rem; color: {'#D97706' if es_pro() else '#64748B'}; font-weight: 700;">
                                {rol_txt}
                            </div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            if st.sidebar.button("Cuenta / Iniciar sesión", key="sb_login_btn", use_container_width=True):
                st.session_state[MODAL_KEY] = True
                st.rerun()
    except Exception:
        pass


def tarjeta_bloqueo_pro(herramienta: str = "esta herramienta", descripcion: str = ""):
    """Muestra un candado visual llamativo cuando una función es exclusiva para clientes PRO."""
    st.markdown(_CSS_AUTH, unsafe_allow_html=True)
    desc = descripcion or "Esta herramienta incluye cálculos avanzados de inteligencia artificial, modelos predictivos y proyecciones de alto valor reservadas para miembros suscriptores."
    st.markdown(
        f"""
        <div class="pro-card-lock">
            <span class="pro-crown">👑</span>
            <div class="pro-title">Desbloquea {herramienta} con PRO</div>
            <div class="pro-desc">{desc}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        if st.button("✨ Iniciar Sesión o Desbloquear Acceso PRO", type="primary", key=f"btn_lock_{herramienta}", use_container_width=True):
            st.session_state[MODAL_KEY] = True
            st.rerun()


def mostrar_anuncio(formato: str = "banner"):
    """Si el usuario es PRO o Admin, NUNCA muestra anuncios. Si es gratuito, muestra el espacio publicitario."""
    try:
        if es_pro():
            return  # Sin anuncios para usuarios de pago

        if formato == "sidebar":
            st.sidebar.markdown(
                """
                <div style="background: #F1F5F9; border: 1px dashed #94A3B8; border-radius: 10px; padding: 0.8rem; text-align: center; margin: 1rem 0;">
                    <span style="font-size: 0.65rem; font-weight: 700; color: #64748B; background: #E2E8F0; padding: 0.1rem 0.4rem; border-radius: 4px;">PUBLICIDAD</span>
                    <div style="font-size: 0.8rem; font-weight: 700; color: #1E293B; margin: 0.4rem 0;">Tu Anuncio Aquí</div>
                    <div style="font-size: 0.7rem; color: #64748B;">Espacio disponible para patrocinadores deportivos.</div>
                    <div style="font-size: 0.68rem; color: #4F46E5; margin-top: 0.4rem; font-weight: 600;">Pasa a PRO para no ver anuncios</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="ad-banner">
                    <div>
                        <span class="ad-tag">ANUNCIO</span>
                        <span class="ad-text">¿Quieres anunciar tu canal de apuestas o marca deportiva aquí? Contáctanos para publicidad.</span>
                    </div>
                    <span style="font-size: 0.74rem; font-weight: 700; color: #4F46E5; white-space: nowrap;">⚡ Eliminar anuncios con PRO</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    except Exception:
        pass


def panel_administracion():
    """Panel de gestión de clientes exclusivo para el administrador."""
    if not es_admin():
        return

    with st.expander("⚙️ Panel de Gestión de Clientes (Solo Admin)", expanded=False):
        st.caption("Administra las cuentas de tus clientes y asígnales plan PRO o Gratuito.")
        usuarios = _cargar_usuarios()

        tab_lista, tab_crear = st.tabs(["👥 Clientes Registrados", "➕ Crear / Ascender a PRO"])

        with tab_lista:
            for mail, u in usuarios.items():
                if mail == "admin@deporte.com":
                    continue
                c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
                rol_badge = "⭐ PRO" if u.get("rol") == "pro" else "Gratuito"
                c1.write(f"**{u.get('nombre')}**\n\n`{mail}`\n\nPlan: **{rol_badge}**")
                c2.write(f"Estado: {'✅ Activo' if u.get('activo', True) else '❌ Inactivo'}\nVence: {u.get('vence') or 'Permanente'}")

                # Botón ascender a PRO o bajar a Gratis
                if u.get("rol") == "pro":
                    if c3.button("Bajar a Gratis", key=f"free_{mail}"):
                        u["rol"] = "gratuito"
                        _guardar_usuario(mail, u)
                        st.rerun()
                else:
                    if c3.button("⭐ Dar PRO", key=f"pro_{mail}"):
                        u["rol"] = "pro"
                        _guardar_usuario(mail, u)
                        st.rerun()

                # Botón eliminar
                if c4.button("🗑️ Eliminar", key=f"del_{mail}"):
                    _eliminar_usuario(mail)
                    st.rerun()
                st.divider()

        with tab_crear:
            with st.form("form_admin_crear_pro"):
                nuevo_nom = st.text_input("Nombre del cliente")
                nuevo_mail = st.text_input("Email")
                nuevo_pass = st.text_input("Contraseña", value="pro123")
                dias_sub = st.selectbox("Duración del Plan PRO", ["30 días (1 mes)", "90 días (3 meses)", "365 días (1 año)", "Permanente"])
                btn_crear = st.form_submit_button("Crear cuenta PRO")

                if btn_crear:
                    from datetime import timedelta
                    vence_str = None
                    if "30" in dias_sub:
                        vence_str = str(date.today() + timedelta(days=30))
                    elif "90" in dias_sub:
                        vence_str = str(date.today() + timedelta(days=90))
                    elif "365" in dias_sub:
                        vence_str = str(date.today() + timedelta(days=365))

                    ok, msg = registrar_usuario(nuevo_nom, nuevo_mail, nuevo_pass, rol="pro", vence=vence_str)
                    if ok:
                        st.success(f"Cuenta PRO creada con éxito para {nuevo_mail}. Vence: {vence_str or 'Sin vencimiento'}")
                        st.rerun()
                    else:
                        st.error(msg)
