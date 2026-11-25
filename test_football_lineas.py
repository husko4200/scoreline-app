"""Fútbol · Líneas: cálculo de las series y dibujo de la tarjeta (con una pantalla falsa, sin Streamlit)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import ficha_linea as fl  # noqa: E402
import football_extra as fx  # noqa: E402
import football_lineas as fli  # noqa: E402


def _partidos():
    nan = np.nan
    return pd.DataFrame({
        "Date": pd.to_datetime(["2026-01-15", "2026-01-01", "2026-01-08"]),      # a propósito desordenadas
        "Temporada": ["2526"] * 3,
        "HomeTeam": ["Arsenal", "Arsenal", "Chelsea"], "AwayTeam": ["Dover", "Brighton", "Arsenal"],
        "FTHG": [1, 2, 0], "FTAG": [1, 1, 3],
        "HTHG": [nan, 1, 0], "HTAG": [0, 0, 2],
        "HC": [8, 6, 5], "AC": [2, 4, 7], "HY": [2, 1, 3], "AY": [2, 2, 0]})


def _t():
    return fx.largo_ext(_partidos())


def test_largo_ext_trae_amarillas_del_rival():
    t = _t().set_index(["Equipo", "Rival"])
    assert t.loc[("Arsenal", "Brighton"), "AmarillasRival"] == 2      # AY del partido 1


def test_partido_suma_los_dos_equipos_en_orden_cronologico():
    s, r = fli.series_equipo(_t(), "Arsenal", fli.PARTIDO)
    assert s["Goles"] == [3, 3, 2] and s["Córners"] == [10, 12, 10] and s["Amarillas"] == [3, 3, 4]
    assert r["Goles"] == [("BRI", "Brighton"), ("CHE", "Chelsea"), ("DOV", "Dover")]


def test_partido_ignora_los_partidos_sin_dato_y_oculta_mercados_vacios():
    s, r = fli.series_equipo(_t(), "Arsenal", fli.PARTIDO)
    assert s["Goles 1T"] == [1, 2] and len(r["Goles 1T"]) == 2       # al 3.º le falta HTHG
    assert "Tiros a puerta" not in s and "Faltas" not in s            # no hay tiros ni faltas en estos datos


def test_equipo_usa_solo_las_cifras_del_equipo():
    s, _ = fli.series_equipo(_t(), "Arsenal", fli.EQUIPO)
    assert s["Goles"] == [2, 3, 1] and s["Goles recibidos"] == [1, 0, 1]
    assert s["Córners"] == [6, 7, 8] and s["Amarillas"] == [1, 0, 2]   # local, visita, local


def test_filtros_condicion_ultimos_y_rival():
    t = _t()
    assert fli.series_equipo(t, "Arsenal", fli.PARTIDO, condicion=fli.LOCAL)[0]["Goles"] == [3, 2]
    assert fli.series_equipo(t, "Arsenal", fli.PARTIDO, condicion=fli.VISITA)[0]["Goles"] == [3]
    assert fli.series_equipo(t, "Arsenal", fli.PARTIDO, ultimos=2)[0]["Goles"] == [3, 2]
    s, r = fli.series_equipo(t, "Arsenal", fli.PARTIDO, rival="Brighton")
    assert s["Goles"] == [3] and r["Goles"] == [("BRI", "Brighton")]


def test_equipo_sin_partidos_devuelve_vacio():
    assert fli.series_equipo(_t(), "Nadie", fli.PARTIDO) == ({}, {})
    assert fli.series_equipo(_t(), "Arsenal", fli.PARTIDO, rival="Nadie") == ({}, {})


# ------------------------------------------------------------------ ficha_linea.render con pantalla falsa
class _Col:
    def radio(self, etiqueta, opciones, **k):
        return opciones[k.get("index", 0)]

    def number_input(self, etiqueta, *a, **k):
        return k["value"] if "value" in k else a[2]


class _Pantalla:
    def __init__(self):
        self.html, self.avisos = [], []

    def columns(self, spec, **k):
        return [_Col() for _ in range(len(spec) if isinstance(spec, (list, tuple)) else spec)]

    def markdown(self, texto, **k):
        self.html.append(texto)

    def caption(self, texto, **k):
        self.avisos.append(texto)

    info = caption


def _dibujar(monkeypatch, **kw):
    pantalla = _Pantalla()
    monkeypatch.setattr(fl, "st", pantalla)
    monkeypatch.setattr(fl.estilos, "cargar", lambda *a: None)
    fl.render(**kw)
    return "".join(pantalla.html), pantalla


def test_tarjeta_futbol_linea_termina_en_medio(monkeypatch):
    html, _ = _dibujar(monkeypatch, nombre="Arsenal", foto_url=None, contexto="ambos equipos",
                       series={"Goles": [3, 1, 2, 4, 2, 3]}, key="k", medios=True)
    assert 'class="fl-linea">2.5<' in html            # mediana 2.5 -> línea 2.5
    assert "<b>50%</b>" in html and "3 de 6" in html
    assert "<img" not in html                         # sin foto no hay <img>


def test_tarjeta_etiquetas_cortas_y_nombre_completo(monkeypatch):
    series = {"Goles": [3, 1, 2]}
    rivales = {"Goles": [("BRI", "Brighton"), ("CHE", "Chelsea"), ("DOV", "Dover")]}
    html, _ = _dibujar(monkeypatch, nombre="Arsenal", foto_url=None, contexto="x", series=series,
                       rivales=rivales, key="k", medios=True)
    assert 'title="Brighton"' in html and "<span>BRI</span>" in html


def test_tarjeta_rivales_desalineados_no_dibujan_etiquetas(monkeypatch):
    html, _ = _dibujar(monkeypatch, nombre="X", foto_url=None, contexto="x", series={"Goles": [3, 1, 2]},
                       rivales=["solo uno"], key="k")
    assert "fl-riv" not in html


def test_tarjeta_nba_sigue_igual(monkeypatch):
    html, _ = _dibujar(monkeypatch, nombre="Kevin Durant", foto_url="https://a.espncdn.com/x.png", contexto="HOU",
                       series={"PTS": [20, 25, 30, 18]}, rivales=["LAL", "DEN", "BOS", "MIA"], key="k")
    assert 'class="fl-linea">22.5<' in html and "<img" in html and "<span>LAL</span>" in html


def test_tarjeta_sin_series_avisa(monkeypatch):
    _, pantalla = _dibujar(monkeypatch, nombre="X", foto_url=None, contexto="x", series={}, key="k")
    assert pantalla.avisos and not pantalla.html
