# 🚀 Despliegue 100% Gratis (Sin Tarjeta) con Streamlit Cloud + Firebase `.web.app`

Esta guía deja tu aplicación funcionando **sin costo y sin tarjeta de crédito**:
- **Backend Python + Streamlit:** alojado gratis en **Streamlit Community Cloud** (`https://tu-app.streamlit.app`).
- **Base de datos (usuarios, roles y planes Pro):** **Firebase Firestore** (plan gratuito Spark).
- **Dominio limpio `.web.app`:** **Firebase Hosting** (plan gratuito Spark) mostrando tu app en `https://tu-proyecto.web.app`.

---

## 1. Cuenta de Administrador Inicial

* **Correo:** `admin@deporte.com`
* **Contraseña por defecto:** `admin123` (puedes cambiarla definiendo `ADMIN_DEFAULT_PASS` en los Secrets de Streamlit Cloud antes del primer arranque).

> Desde el panel superior de administrador puedes ver clientes, crear cuentas Pro con vencimiento y activar/desactivar planes. Todo se guardará en Firestore en cuanto conectes Firebase.

---

## 2. Paso 1 — Crear Firebase + Firestore (Gratis, plan Spark)

1. Ve a **[console.firebase.google.com](https://console.firebase.google.com/)** → **Agregar proyecto** (elige el nombre que quieras, p. ej. `scoreline-app`).
   * Ese nombre definirá tu enlace final: **`https://scoreline-app.web.app`**.
2. En el menú izquierdo entra a **Compilación → Firestore Database → Crear base de datos** (elige modo producción y una ubicación cercana).
3. Ve a ⚙️ **Configuración del proyecto → Cuentas de servicio**.
4. Haz clic en **"Generar nueva clave privada"** y guarda el archivo `.json` en tu PC (fuera del repositorio; **nunca lo subas a GitHub**).

---

## 3. Paso 2 — Subir el código a GitHub

En la carpeta del proyecto (`c:\xampp\htdocs\analisis_deportivo-main`), ejecuta:

```powershell
git init
git add .
git commit -m "ScoreLine listo para despliegue"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git push -u origin main
```

*(El archivo `.gitignore` ya protege `usuarios.json`, `usuarios_planes.json`, `.streamlit/secrets.toml` y archivos de credenciales Firebase para que no se suban).*

---

## 4. Paso 3 — Desplegar en Streamlit Community Cloud (Gratis)

1. Ve a **[share.streamlit.io](https://share.streamlit.io/)** e inicia sesión con tu cuenta de GitHub.
2. Haz clic en **"Create app"** → **"Yup, I have an app"** (o **"Deploy a public/private app from GitHub"**):
   * **Repository:** `TU_USUARIO/TU_REPO`
   * **Branch:** `main`
   * **Main file path:** `app.py`
3. Antes o justo después de desplegar, ve a **Settings → Secrets** de tu app en Streamlit Cloud y pega el contenido de tu archivo JSON de Firebase con este formato:

```toml
ADMIN_DEFAULT_PASS = "TuClaveAdminSegura123"

[firebase]
type = "service_account"
project_id = "tu-proyecto-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "firebase-adminsdk-xxxx@tu-proyecto-id.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

*(Opcional: si usas el lector de boletas con IA, agrega también `ANTHROPIC_API_KEY = "sk-ant-..."` arriba de `[firebase]`.)*

4. Guarda los Secrets y reinicia la app si es necesario. Cuando termine de cargar, copia la URL que te dio Streamlit (por ejemplo `https://scoreline-app.streamlit.app`).

---

## 5. Paso 4 — Conectar tu dominio `.web.app` con Firebase Hosting

1. Abre [`public/index.html`](public/index.html) y cambia la línea:
   ```js
   var STREAMLIT_APP_URL = "https://TU-APP.streamlit.app";
   ```
   por la URL real que te dio Streamlit Cloud en el paso anterior.
2. Instala Firebase CLI (si aún no lo tienes, requiere Node.js):
   ```powershell
   npm install -g firebase-tools
   ```
3. Inicia sesión, vincula tu proyecto y publica:
   ```powershell
   firebase login
   firebase use --add
   firebase deploy --only hosting
   ```

¡Listo! Tu aplicación quedará accesible en **`https://tu-proyecto.web.app`** sin tarjeta de crédito y con usuarios y planes guardados en Firestore.

> **Nota sobre navegadores con bloqueo estricto (ej. Brave):** Si algún usuario tiene bloqueadas las cookies de terceros dentro de iframes, puede pulsar el botón **"Abrir aplicación directamente"** o entrar por la URL directa `.streamlit.app`.
