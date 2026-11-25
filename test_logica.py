"""Pruebas de la lógica pura (sin red ni pantalla). Ejecutar desde la carpeta de la app:  pytest tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

import ficha_equipos as fe  # noqa: E402
import graficos  # noqa: E402
import nba_extra  # noqa: E402
import nba_jugadores as nj  # noqa: E402
import nba_panel as pn  # noqa: E402


# ------------------------------------------------------------------ nba_panel._traspasar_jugadores
def test_traspaso_stats_a_h2h_toma_los_dos_primeros():
    estado = {}
    snap = {pn.JUG_STATS: {"jug_elegidos": ["a", "b", "c"]}}
    pn._traspasar_jugadores(snap, pn.JUG_STATS, pn.JUG_H2H, estado)
    assert estado == {"h2h_jug_a": "a", "h2h_jug_b": "b"}


def test_traspaso_h2h_a_stats_pone_a_y_b_primero_y_limita_a_4():
    estado = {}
    snap = {pn.JUG_H2H: {"h2h_jug_a": "a", "h2h_jug_b": "b"},
            pn.JUG_STATS: {"jug_elegidos": ["b", "c", "d", "e"]}}
    pn._traspasar_jugadores(snap, pn.JUG_H2H, pn.JUG_STATS, estado)
    assert estado["jug_elegidos"] == ["a", "b", "c", "d"]


def test_traspaso_sin_datos_no_falla():
    estado = {}
    pn._traspasar_jugadores({}, pn.JUG_STATS, pn.JUG_H2H, estado)
    pn._traspasar_jugadores({}, pn.JUG_H2H, pn.JUG_STATS, estado)
    assert estado == {"jug_elegidos": []}


def test_traspaso_entre_vistas_ajenas_no_toca_nada():
    estado = {}
    pn._traspasar_jugadores({}, pn.RANKING, pn.JUG_STATS, estado)
    assert estado == {}


# ------------------------------------------------------------------ graficos (funciones puras)
def _df():
    return pd.DataFrame({"Fecha": ["2026-01-03", "2026-01-01", "2026-01-02"],
                         "Rival": ["LAL", "DEN", "BOS"], "PTS": [30, 10, 20]})


def test_preparar_partidos_ordena_por_fecha_y_marca_la_linea():
    d = graficos.preparar_partidos(_df(), "PTS", linea=15)
    assert list(d["valor"]) == [10, 20, 30]
    assert list(d["mm5"]) == [10.0, 15.0, 20.0]
    assert list(d["supero"]) == [False, True, True]


def test_preparar_partidos_sin_columna_devuelve_vacio():
    assert graficos.preparar_partidos(_df(), "XYZ").empty
    assert graficos.preparar_partidos(None, "PTS").empty


def test_resumen_linea():
    d = graficos.preparar_partidos(_df(), "PTS")
    veces, total, pct = graficos.resumen_linea(d, 15)
    assert (veces, total) == (2, 3) and round(pct, 1) == 66.7
    assert graficos.resumen_linea(d, None) is None


def test_preparar_comparacion_ignora_valores_no_numericos():
    largo = graficos.preparar_comparacion({"A": {"PTS": 25, "REB": None}, "B": {"PTS": "x", "REB": 8}})
    assert sorted(zip(largo["Jugador"], largo["Estadística"])) == [("A", "PTS"), ("B", "REB")]


# ------------------------------------------------------------------ nba_jugadores
def test_hechos_y_porcentaje_suman_tiros():
    assert nj._hechos("10-20") == (10, 20)
    assert nj._hechos(None) == (0, 0) and nj._hechos("abc") == (0, 0)
    assert nj._porcentaje([{"FG": "5-10"}, {"FG": "10-10"}], "FG") == 75.0   # 15/20, no el promedio de 50 % y 100 %
    assert nj._porcentaje([{"FG": None}], "FG") is None


def test_lideres_empate_no_tiene_lider():
    col, _, mas_es_mejor = nj.GRANDES[0]
    assert col not in nj.lideres([{col: 5}, {col: 5}])
    mejor, peor = (9, 5) if mas_es_mejor else (1, 8)
    assert nj.lideres([{col: peor}, {col: mejor}])[col] == 1
    assert nj.lideres([{col: 5}]) == {}


# ------------------------------------------------------------------ ficha_equipos._estadisticas
def test_estadisticas_mas_y_menos_de():
    vals = [20, 25, 30, 18]
    mas = fe._estadisticas(vals, 22.5, "Más de", "over")
    menos = fe._estadisticas(vals, 22.5, "Menos de", "over")
    assert (mas.k, mas.pct, mas.direc) == (2, 50, 1)
    assert (menos.k, menos.pct, menos.direc) == (2, 50, -1)
    assert mas.cumple == [False, True, True, False] and menos.cumple == [True, False, False, True]
    assert menos.margenes == [2.5, -2.5, -7.5, 4.5]      # cuánto cumplió (+) o falló (−)


def test_estadisticas_handicap_siempre_va_hacia_arriba():
    est = fe._estadisticas([3, -4, 8], 2.5, "Menos de", "handicap")   # en hándicap el lado se ignora
    assert est.cumple == [True, False, True] and est.direc == 1


def test_estadisticas_una_sola_muestra_no_falla():
    est = fe._estadisticas([20], 19.5, "Más de", "over")
    assert est.sd == 0.0 and est.prob is None and est.tendencia is None


# ------------------------------------------------------------------ nba_extra.cargar_cajas
def test_cargar_cajas_cuenta_fallos_y_avisa_el_progreso(monkeypatch):
    def falso(i):
        if i == "3":
            raise RuntimeError("sin red")
        return {"equipos": {"x": 1}} if i != "2" else {"equipos": {}}

    monkeypatch.setattr(nba_extra, "box_compacto", falso)
    avances = []
    cajas, fallos = nba_extra.cargar_cajas(["1", "2", "3", "4"], lambda h, t: avances.append((h, t)))
    assert sorted(cajas) == ["1", "4"] and fallos == 2        # "2" viene vacía y "3" lanza error
    assert [h for h, _ in avances] == [1, 2, 3, 4] and {t for _, t in avances} == {4}


def test_cargar_cajas_funciona_sin_callback(monkeypatch):
    monkeypatch.setattr(nba_extra, "box_compacto", lambda i: {"equipos": {"x": 1}})
    assert nba_extra.cargar_cajas(["a", "b"]) == ({"a": {"equipos": {"x": 1}}, "b": {"equipos": {"x": 1}}}, 0)
