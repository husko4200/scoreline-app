"""Favoritos globales: equipos y jugadores, guardados en disco y compartidos por todas las secciones.

  · Jugadores: usa el MISMO archivo (favoritos_jugadores.json) y la MISMA clave de sesión («jug_favoritos») que la vista
    Jugadores, así que una estrella puesta allí aparece aquí y al revés.
  · Equipos: favoritos_equipos.json, clave de sesión «fav_equipos».

Todos los ids son texto (los de ESPN). Si el archivo no se puede escribir, los favoritos siguen valiendo durante la sesión.
"""
import json
import os

import streamlit as st

_CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_EQUIPOS = os.path.join(_CARPETA, "favoritos_equipos.json")
ARCHIVO_JUGADORES = os.path.join(_CARPETA, "favoritos_jugadores.json")   # el que ya usa nba_jugadores.py
CLAVE_EQUIPOS = "fav_equipos"
CLAVE_JUGADORES = "jug_favoritos"                                         # la que ya usa nba_jugadores.py


def _leer(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        return [str(i) for i in datos] if isinstance(datos, list) else []
    except (OSError, ValueError):
        return []


def _unicos(ids):
    vistos, salida = set(), []
    for i in ids:
        i = str(i)
        if i and i not in vistos:
            vistos.add(i)
            salida.append(i)
    return salida


def _guardar(ruta, clave, ids):
    ids = _unicos(ids)
    st.session_state[clave] = ids
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(ids, f, ensure_ascii=False)
        return True
    except OSError:
        return False


def equipos() -> list[str]:
    if CLAVE_EQUIPOS not in st.session_state:
        st.session_state[CLAVE_EQUIPOS] = _leer(ARCHIVO_EQUIPOS)
    return list(st.session_state[CLAVE_EQUIPOS])


def jugadores() -> list[str]:
    if CLAVE_JUGADORES not in st.session_state:
        st.session_state[CLAVE_JUGADORES] = _leer(ARCHIVO_JUGADORES)
    return list(st.session_state[CLAVE_JUGADORES])


def guardar_equipos(ids) -> bool:
    return _guardar(ARCHIVO_EQUIPOS, CLAVE_EQUIPOS, ids)


def guardar_jugadores(ids) -> bool:
    return _guardar(ARCHIVO_JUGADORES, CLAVE_JUGADORES, ids)


def hay_favoritos() -> bool:
    return bool(equipos() or jugadores())
