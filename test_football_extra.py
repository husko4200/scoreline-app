"""Lógica pura de football_extra (cuotas, ROI, calibración, tabla por equipo). Sin red ni pantalla."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import football_extra as fx  # noqa: E402


def _cuotas():
    # tres partidos: (local, empate, visita)
    return pd.DataFrame({"H": [2.0, 3.0, 5.0], "D": [3.5, 3.2, 4.0], "A": [4.0, 2.5, 1.6]})


def test_probs_mercado_normaliza_y_calcula_margen():
    p = fx.probs_mercado(pd.DataFrame({"H": [2.0, 1.9], "D": [4.0, 3.5], "A": [4.0, 4.2]}), "H", "D", "A")
    assert np.allclose(p[["pH", "pD", "pA"]].sum(axis=1), 1)
    assert round(p["margen"].iloc[0], 6) == 0 and round(p["margen"].iloc[1], 3) == 0.05
    assert p["pH"].iloc[0] == 0.5


def test_probs_mercado_descarta_cuotas_invalidas():
    df = pd.DataFrame({"H": [2.0, np.nan, 0.9, 2.0], "D": [3.0, 3.0, 3.0, 1.0], "A": [4.0, 4.0, 4.0, 4.0]})
    assert list(fx.probs_mercado(df, "H", "D", "A").index) == [0]     # NaN, cuota <= 1 y empate de 1.0 quedan fuera


def test_casas_disponibles_exige_cobertura_minima():
    df = pd.DataFrame({"PSH": [2.0] * 10, "PSD": [3.0] * 10, "PSA": [4.0] * 10,       # 100 % de filas válidas
                       "AvgH": [2.0] + [np.nan] * 9, "AvgD": [3.0] + [np.nan] * 9, "AvgA": [4.0] + [np.nan] * 9})  # 10 %
    casas = fx.casas_disponibles(df, 0.3)
    assert "Pinnacle" in casas and "Promedio del mercado" not in casas and "Bet365" not in casas
    assert fx.casas_disponibles(pd.DataFrame(), 0.3) == {}


def test_resultado_1x2():
    df = pd.DataFrame({"FTHG": [2, 1, 0], "FTAG": [1, 1, 3]})
    assert list(fx.resultado_1x2(df)) == ["H", "D", "A"]


def test_tabla_roi_local_y_favorito():
    p = fx.probs_mercado(_cuotas(), "H", "D", "A")
    res = pd.Series(["H", "H", "A"], index=p.index)
    t = fx.tabla_roi(p, res).set_index("Estrategia")
    assert (t.loc["Siempre local", "Apuestas"], t.loc["Siempre local", "ROI %"]) == (3, 66.7)   # (+1 +2 -1) / 3
    assert t.loc["Siempre el favorito", "ROI %"] == 20.0                                      # (+1 -1 +0.6) / 3
    assert t.loc["Siempre local", "Aciertos %"] == 66.7


def test_calibracion_cuenta_todas_las_opciones():
    p = fx.probs_mercado(_cuotas(), "H", "D", "A")
    c = fx.calibracion(p, pd.Series(["H", "H", "A"], index=p.index))
    assert c["n"].sum() == 9                                  # 3 partidos x 3 resultados posibles
    assert c["real"].between(0, 1).all() and c["esperado"].between(0, 1).all()


def test_largo_ext_una_fila_por_equipo_y_partido():
    df = pd.DataFrame({"Date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "Temporada": ["2526", "2526"],
                       "HomeTeam": ["A", "C"], "AwayTeam": ["B", "D"], "FTHG": [2, 2], "FTAG": [0, 2]})
    t = fx.largo_ext(df).set_index(["Equipo"])
    assert len(t) == 4                                          # faltan columnas (tiros, córners...): quedan en NaN, sin error
    assert (t.loc["A", "Resultado"], t.loc["A", "Puntos"], bool(t.loc["A", "ArcoEnCero"])) == ("G", 3, True)
    assert (t.loc["B", "Resultado"], t.loc["B", "Puntos"]) == ("P", 0)
    assert bool(t.loc["C", "Over25"]) and bool(t.loc["C", "BTTS"]) and t.loc["C", "Resultado"] == "E"
    assert not bool(t.loc["A", "Over25"]) and not bool(t.loc["A", "BTTS"])
