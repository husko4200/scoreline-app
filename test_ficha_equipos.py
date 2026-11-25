"""Pruebas de ficha_equipos.py (sin red ni Streamlit real).  Ejecutar:  python test_ficha_equipos.py   (o  pytest)"""
import sys
import types

try:
    import streamlit  # noqa: F401
except ImportError:   # sin Streamlit instalado se usan módulos vacíos: estas pruebas no dibujan nada
    for _m in ("streamlit", "ficha_linea", "nba", "nba_extra", "common"):
        sys.modules.setdefault(_m, types.ModuleType(_m))
    sys.modules["common"]._session = None
    sys.modules["common"].normalizar = lambda x: x
    sys.modules["streamlit"].cache_data = lambda **k: (lambda f: f)

import ficha_equipos as fe  # noqa: E402


def test_estadisticas_mas_de():
    est = fe._estadisticas([100, 110, 120], 105.5, "Más de", "over")
    assert (est.n, est.k, est.pct) == (3, 2, 67)
    assert est.cumple == [False, True, True]
    assert est.margenes == [-5.5, 4.5, 14.5]
    assert est.mu == 110 and est.tendencia is None      # menos de 6 partidos: sin tendencia


def test_estadisticas_menos_de_invierte_el_margen():
    est = fe._estadisticas([100, 110, 120], 105.5, "Menos de", "over")
    assert est.cumple == [True, False, False] and est.direc == -1
    assert est.margenes == [5.5, -4.5, -14.5]


def test_estadisticas_handicap_ignora_el_lado():
    est = fe._estadisticas([-3, 4, 10], 2.5, "Menos de", "handicap")   # umbral = margen necesario para cubrir
    assert est.cumple == [False, True, True] and est.direc == 1


def test_estadisticas_tendencia_y_probabilidad():
    est = fe._estadisticas([100, 101, 99, 100, 120, 125], 110.5, "Más de", "over")
    assert est.tendencia[0] == "↑" and est.prob is not None
    assert fe._estadisticas([100, 100, 100], 99.5, "Más de", "over").prob is None   # sin variación no hay probabilidad


def test_registro_de_mercados_es_coherente():
    claves = [m.clave for m in fe.MERCADOS.values()]
    assert len(claves) == len(set(claves)), "claves repetidas"
    for nombre, m in fe.MERCADOS.items():
        assert m.tipo in ("over", "handicap", "ganador"), nombre
        if m.tipo == "handicap":
            assert m.rango > 0, nombre
        if m.tipo == "ganador":
            assert m.ayuda and m.tag and m.verbo, nombre
    # los alias apuntan a datos que _serie_equipo sí calcula
    assert fe.MERCADOS["Hándicap del 1.er cuarto"].campo == "gq1"
    assert fe.MERCADOS["Hándicap del segundo tiempo"].campo == "gh2"
    assert fe.MERCADOS["Ganador (local o visita)"].campo == "margen"


def test_mercados_pedidos_existen():
    for nombre in ("Total de puntos del segundo tiempo (ambos equipos)", "Puntos del equipo en el primer tiempo",
                   "Puntos del equipo en el segundo tiempo", "Ganador del primer tiempo", "Ganador del segundo tiempo",
                   "Hándicap del primer tiempo", "Hándicap del 4.º cuarto", "Tiros libres intentados", "Rebotes ofensivos"):
        assert nombre in fe.MERCADOS, nombre


def test_stats_de_caja_trae_fta_y_oreb():
    caja = {"equipos": {"1": {"fta": 22, "oreb": 9, "tpm": 10, "fgm": 40, "ftm": 18}}, "cuartos": {"1": [30, 25, 20, 28]}}
    d = fe._stats_de_caja(caja)["1"]
    assert d["fta"] == 22 and d["oreb"] == 9 and d["q4"] == 28 and d["ftp"] == 81.8


if __name__ == "__main__":
    pruebas = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for f in pruebas:
        f()
        print("ok ", f.__name__)
    print(f"{len(pruebas)} pruebas pasan")
