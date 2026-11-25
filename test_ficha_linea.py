import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ficha_linea as fl


def test_redondeo_medio():
    assert fl._redondea_medio(24.3) == 24.5
    assert fl._redondea_medio(24.8) == 25.0


def test_mas_de():
    estados, k, n, pct = fl.evaluar([20, 25, 30, 18], 22.5, mas=True)
    assert estados == ["no", "ok", "ok", "no"] and (k, n, pct) == (2, 4, 50)


def test_menos_de():
    estados, k, n, pct = fl.evaluar([20, 25, 30, 18], 22.5, mas=False)
    assert estados == ["ok", "no", "no", "ok"] and (k, n, pct) == (2, 4, 50)


def test_empate_no_cuenta_en_ningun_lado():
    for mas in (True, False):
        estados, k, n, _ = fl.evaluar([25, 25, 30, 20], 25, mas)
        assert estados.count("push") == 2 and n == 2
    assert fl.evaluar([25, 25, 30, 20], 25, True)[1:] == (1, 2, 50)


def test_todo_empate_o_vacio_no_divide_por_cero():
    assert fl.evaluar([25, 25], 25)[3] == 0
    assert fl.evaluar([], 10)[3] == 0


def test_url_segura():
    assert fl._url_segura("https://a.espncdn.com/x.png").startswith("https://")
    assert fl._url_segura("http://x.com/a.png") == ""
    assert fl._url_segura("javascript:alert(1)") == ""
    assert fl._url_segura(None) == ""
