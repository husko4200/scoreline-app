"""Página de Diagnóstico: prueba cada fuente de datos en paralelo y resume el estado de la app."""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import football
import football_extra
import nba
import nba_extra
from common import _session
from secciones import DIAGNOSTICO, FUTBOL, NBA


def fuentes_de_datos():
    """Fuentes que se prueban en Diagnóstico, agrupadas por deporte: (nombre, dirección web)."""
    return {
        NBA: [
            ("Marcador del día", nba.BASE + "/scoreboard"),
            ("Equipos", nba.BASE + "/teams"),
            ("Calendario (Lakers)", nba.BASE + "/teams/13/schedule?season=2025&seasontype=2"),
            ("Posiciones", nba_extra.V2 + "/standings"),
            ("Lesiones", nba.BASE + "/injuries"),
        ],
        FUTBOL: [
            ("Liga de Chile (ESPN)", football.ESPN.format(liga="chi.1")),
            ("Datos históricos (football-data.co.uk)", football.BASE_URL.format(season="2526", league="E0")),
            ("Próximos partidos (football-data)", football_extra.FIXTURES_URL),
            ("Argentina (football-data)", football_extra.URL_NEW.format(code="ARG")),
        ],
    }


SEGUNDOS_LENTA = 5  # una fuente que responde pero tarda más que esto se marca como lenta


def _probar_fuente(url):
    """Descarga una dirección y devuelve (estado, código HTTP, KB, segundos, detalle del error)."""
    inicio = time.time()
    codigo, kb, detalle = None, None, ""
    try:
        r = _session.get(url, timeout=15)
        codigo = r.status_code
        kb = round(len(r.content) / 1024, 1)
        ok = r.ok and len(r.content) > 0
        if not r.ok:
            detalle = f"HTTP {codigo}"
        elif not ok:
            detalle = "Respuesta vacía"
    except Exception as e:  # noqa: BLE001
        ok = False
        detalle = f"{type(e).__name__}: {str(e)[:80]}"
    segundos = round(time.time() - inicio, 1)
    if not ok:
        estado = "❌ Falla"
    elif segundos > SEGUNDOS_LENTA:
        estado = "🟡 Lenta"
    else:
        estado = "✅ Funciona"
    return estado, codigo, kb, segundos, detalle


def _probar_todas(pendientes):
    """Prueba varias fuentes a la vez. `pendientes` es una lista de (deporte, nombre, url); devuelve filas."""
    def una(p):
        deporte, nombre, url = p
        estado, codigo, kb, segundos, detalle = _probar_fuente(url)
        return {"Deporte": deporte, "Fuente": nombre, "Estado": estado, "HTTP": codigo,
                "Tamaño (KB)": kb, "Segundos": segundos, "Detalle": detalle, "URL": url}
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(una, pendientes))


def _mostrar_resultados(diag):
    filas = diag["filas"]
    df = pd.DataFrame(filas)
    buenas = sum(f["Estado"].startswith("✅") for f in filas)
    lentas = sum(f["Estado"].startswith("🟡") for f in filas)
    fallas = sum(f["Estado"].startswith("❌") for f in filas)
    tiempos = [f["Segundos"] for f in filas if not f["Estado"].startswith("❌")]

    if fallas:
        st.warning(f"{fallas} de {len(filas)} fuentes no responden. Las secciones que dependen de ellas no mostrarán datos. "
                   "Revisa tu conexión o inténtalo de nuevo en unos minutos.")
    elif lentas:
        st.info(f"Todas responden, pero {lentas} van lentas (más de {SEGUNDOS_LENTA} s). La app puede tardar en cargar esas secciones.")
    else:
        st.success(f"Todo en orden: las {len(filas)} fuentes responden.")

    a, b, c, d = st.columns(4)
    a.metric("Funcionan", f"{buenas}/{len(filas)}")
    b.metric("Lentas", lentas)
    c.metric("Con fallas", fallas)
    d.metric("Tiempo medio", f"{sum(tiempos) / len(tiempos):.1f} s" if tiempos else "—")
    st.caption(f"Prueba hecha a las {diag['hora']:%H:%M:%S}.")

    # Salud por deporte
    st.markdown("##### Salud por deporte")
    deportes = list(dict.fromkeys(df["Deporte"]))
    for col, deporte in zip(st.columns(len(deportes)), deportes):
        sub = df[df["Deporte"] == deporte]
        ok = int(sub["Estado"].str.startswith(("✅", "🟡")).sum())
        col.metric(deporte, f"{ok}/{len(sub)}", delta="todo bien" if ok == len(sub) else f"{len(sub) - ok} con falla",
                   delta_color="normal" if ok == len(sub) else "inverse")

    # Tabla con filtros
    st.markdown("##### Detalle por fuente")
    filtro = st.radio("Mostrar", ["Todas", "Solo con problemas"], horizontal=True, label_visibility="collapsed")
    vista = df if filtro == "Todas" else df[~df["Estado"].str.startswith("✅")]
    if vista.empty:
        st.caption("No hay fuentes con problemas. 🎉")
    else:
        st.dataframe(vista, hide_index=True, use_container_width=True,
                     column_config={"URL": st.column_config.LinkColumn("URL", display_text="abrir"),
                                    "Segundos": st.column_config.NumberColumn(format="%.1f")})

    # Tiempos de respuesta
    st.markdown("##### Tiempo de respuesta (segundos)")
    st.bar_chart(df.set_index("Fuente")["Segundos"], horizontal=True)

    st.download_button("⬇️ Descargar resultados (CSV)", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"diagnostico_{diag['hora']:%Y%m%d_%H%M}.csv", mime="text/csv")




def _modulos_de_la_app():
    """Módulos cargados que viven en la carpeta de la app (sin lista que mantener: un módulo nuevo aparece solo)."""
    carpeta = Path(__file__).resolve().parent
    return sorted(n for n, m in list(sys.modules.items())
                  if not n.startswith("__") and getattr(m, "__file__", None)
                  and Path(m.__file__).resolve().parent == carpeta)


def _info_entorno():
    """Datos útiles para reportar un problema: versiones, módulos cargados y datos en memoria."""
    modulos = _modulos_de_la_app()
    guardados = sum(1 for k in st.session_state if isinstance(k, tuple))
    a, b, c = st.columns(3)
    a.metric("Python", sys.version.split()[0])
    b.metric("Streamlit", st.__version__)
    c.metric("pandas", pd.__version__)
    a, b = st.columns(2)
    a.metric("Módulos de la app cargados", len(modulos))
    b.metric("Conjuntos de datos en memoria", guardados)
    st.caption("Módulos: " + ", ".join(f"`{n}`" for n in modulos))


def pagina_diagnostico():
    """Prueba cada fuente de datos (en paralelo) y muestra un resumen fácil de leer."""
    st.title(f"{DIAGNOSTICO}")
    st.write("Comprueba si tu conexión llega a cada fuente de datos. "
             "Si alguna falla, la sección correspondiente mostrará un error en vez de datos.")

    fuentes = fuentes_de_datos()
    todas = [(deporte, nombre, url) for deporte, lista in fuentes.items() for nombre, url in lista]
    diag = st.session_state.get("diag")
    hay_fallas = bool(diag) and any(f["Estado"].startswith("❌") for f in diag["filas"])

    c1, c2, _ = st.columns([1, 1.3, 3])
    probar = c1.button("Probar conexiones", type="primary")
    reintentar = c2.button("Reintentar las que fallan", disabled=not hay_fallas)

    if probar:
        with st.spinner(f"Probando {len(todas)} fuentes a la vez..."):
            st.session_state["diag"] = {"filas": _probar_todas(todas), "hora": datetime.now()}
        _fallas = sum(f["Estado"].startswith("❌") for f in st.session_state["diag"]["filas"])
        st.toast("Todas las fuentes responden" if not _fallas else f"{_fallas} fuente(s) con falla",
                 icon="✅" if not _fallas else "⚠️")
    elif reintentar:
        fallidas = [f for f in diag["filas"] if f["Estado"].startswith("❌")]
        with st.spinner(f"Reintentando {len(fallidas)} fuente(s)..."):
            nuevas = {f["URL"]: f for f in _probar_todas([(f["Deporte"], f["Fuente"], f["URL"]) for f in fallidas])}
        filas = [nuevas.get(f["URL"], f) for f in diag["filas"]]
        st.session_state["diag"] = {"filas": filas, "hora": datetime.now()}

    if st.session_state.get("diag"):
        _mostrar_resultados(st.session_state["diag"])
    else:
        st.caption(f"Se probarán {len(todas)} fuentes de NBA y fútbol. Tarda unos segundos.")

    st.divider()
    st.subheader("Datos guardados")
    st.write("La app guarda datos descargados para ir más rápido. Si ves información vieja, vacía este almacenamiento.")
    if st.button("Vaciar caché y datos cargados"):
        st.cache_data.clear()
        # Los módulos guardan datos cargados en session_state usando tuplas como clave.
        for clave in [k for k in st.session_state if isinstance(k, tuple)]:
            del st.session_state[clave]
        st.success("Listo. La próxima vez se volverán a descargar los datos.")
        st.toast("Caché vaciada", icon="🧹")

    with st.expander("Información técnica (útil para reportar un problema)"):
        _info_entorno()
