"""Utilidades comunes: HTTP robusto, rachas y colores de los gráficos."""
import time
import unicodedata

import pandas as pd
import requests

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (analisis-deportivo)"})

ZONA = "America/Santiago"

# Colores fijos por entidad (A vs B), seguros para daltonismo; nunca se reciclan.
COLOR_A = "#0072B2"   # azul
COLOR_B = "#E69F00"   # naranja
COLOR_NEUTRO = "#8A8F98"
COLOR_POS = "#009E73"
COLOR_NEG = "#D55E00"
# Orden fijo para series múltiples (paleta Okabe-Ito); más de 5 series se agrupan, no se inventan tonos.
PALETA = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9"]


def get_json(url: str, params: dict | None = None, timeout: int = 20, retries: int = 2):
    ultimo = None
    for i in range(retries + 1):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            ultimo = e
            time.sleep(0.6 * (i + 1))
    raise ultimo


def get_bytes(url: str, timeout: int = 40):
    """Devuelve (status, contenido). 404 no lanza excepción."""
    r = _session.get(url, timeout=timeout)
    if r.status_code == 404:
        return 404, b""
    r.raise_for_status()
    return r.status_code, r.content


def num(x):
    """Convierte puntajes de ESPN (str, número o dict con value/displayValue) a float."""
    if isinstance(x, dict):
        x = x.get("value", x.get("displayValue"))
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def normalizar(nombre: str) -> str:
    s = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", " ").replace("-", " ").split())


# ---------------------------------------------------------------- rachas
def _tramos(flags: pd.Series) -> pd.DataFrame:
    """Tramos consecutivos de True: índices de inicio/fin (posicionales) y largo."""
    f = flags.fillna(False).astype(bool).reset_index(drop=True)
    if f.empty:
        return pd.DataFrame(columns=["i0", "i1", "largo"])
    grupo = (f != f.shift()).cumsum()
    filas = []
    for _, g in f.groupby(grupo):
        if g.iloc[0]:
            filas.append((g.index[0], g.index[-1], len(g)))
    return pd.DataFrame(filas, columns=["i0", "i1", "largo"])


def buscar_rachas(df: pd.DataFrame, entidad: str, fecha: str, bandera: str,
                  min_largo: int = 15, particion: list[str] | None = None) -> pd.DataFrame:
    """Rachas consecutivas de `bandera` == True por entidad (equipo/jugador).

    `particion`: columnas extra que cortan la racha (p. ej. temporada para no cruzar temporadas).
    Devuelve las rachas con largo >= min_largo, de la más larga a la más corta.
    """
    claves = [entidad] + (particion or [])
    filas = []
    for clave, g in df.sort_values(fecha).groupby(claves, sort=False):
        g = g.reset_index(drop=True)
        t = _tramos(g[bandera])
        t = t[t["largo"] >= min_largo]
        for x in t.itertuples():
            clave_t = clave if isinstance(clave, tuple) else (clave,)
            fila = {entidad: clave_t[0], "Largo": int(x.largo),
                    "Inicio": g.loc[x.i0, fecha], "Fin": g.loc[x.i1, fecha],
                    "En curso": bool(x.i1 == len(g) - 1)}
            for k, v in zip(claves[1:], clave_t[1:]):
                fila[k] = v
            filas.append(fila)
    cols = [entidad, "Largo", "Inicio", "Fin", "En curso"] + (particion or [])
    out = pd.DataFrame(filas, columns=cols)
    return out.sort_values("Largo", ascending=False).reset_index(drop=True)


def racha_maxima(df: pd.DataFrame, entidad: str, fecha: str, bandera: str,
                 particion: list[str] | None = None) -> int:
    """Largo de la racha más larga encontrada (para avisar cuando nada supera el umbral)."""
    r = buscar_rachas(df, entidad, fecha, bandera, min_largo=1, particion=particion)
    return int(r["Largo"].max()) if not r.empty else 0


def racha_actual(df: pd.DataFrame, entidad: str, fecha: str, bandera: str) -> pd.DataFrame:
    """Racha activa de `bandera` == True al final de los datos de cada entidad."""
    filas = []
    for k, g in df.sort_values(fecha).groupby(entidad, sort=False):
        v = g[bandera].fillna(False).astype(bool).to_numpy()
        n = 0
        for x in v[::-1]:
            if not x:
                break
            n += 1
        filas.append({entidad: k, "Racha actual": n})
    return pd.DataFrame(filas).sort_values("Racha actual", ascending=False).reset_index(drop=True)


def racha_resultado(serie_gana: pd.Series) -> str:
    """Texto tipo 'G7' o 'P3' a partir de una serie booleana ordenada en el tiempo."""
    v = serie_gana.dropna().astype(bool).to_numpy()
    if len(v) == 0:
        return "-"
    ult, n = v[-1], 0
    for x in v[::-1]:
        if x != ult:
            break
        n += 1
    return f"{'G' if ult else 'P'}{n}"


def mostrar_rachas(st, df, entidad, fecha, bandera, min_largo, particion=None, etiqueta="rachas"):
    """Muestra tabla de rachas >= min_largo + racha activa; avisa si no hay ninguna."""
    r = buscar_rachas(df, entidad, fecha, bandera, min_largo, particion)
    if r.empty:
        mx = racha_maxima(df, entidad, fecha, bandera, particion)
        st.info(f"No hay {etiqueta} de {min_largo} o más con estos datos. "
                f"La más larga encontrada es de {mx}. Baja el umbral o amplía el rango de temporadas.")
    else:
        v = r.copy()
        for c in ("Inicio", "Fin"):
            v[c] = pd.to_datetime(v[c]).dt.strftime("%d/%m/%Y")
        v["En curso"] = v["En curso"].map({True: "🔥 sí", False: ""})
        st.dataframe(v, hide_index=True, use_container_width=True)
    return r
