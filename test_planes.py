"""Pruebas unitarias para planes.py (Freemium, seguridad anti-HTML-leak y placeholder de pago)."""
import planes


def _setup_memoria(monkeypatch):
    mem = {}
    monkeypatch.setattr(planes, "_MEMORIA_TESTS", mem)
    monkeypatch.setattr(planes, "_obtener_firestore", lambda: None)
    monkeypatch.setattr(planes.auth, "usuario_actual", lambda: None)
    return mem


def test_visitante_y_usuario_nuevo_son_gratis(monkeypatch):
    _setup_memoria(monkeypatch)
    assert planes.obtener_plan(None) == "gratis"
    assert planes.es_pro(None) is False
    assert planes.obtener_plan("nuevo@test.com") == "gratis"
    assert planes.es_pro("nuevo@test.com") is False


def test_usuario_pro_en_servidor(monkeypatch):
    _setup_memoria(monkeypatch)
    uid = "vip@test.com"
    planes.actualizar_plan_servidor(uid, "pro")
    assert planes.obtener_plan(uid) == "pro"
    assert planes.es_pro(uid) is True


def test_seguridad_html_gratis_no_filtra_dato_real(monkeypatch):
    _setup_memoria(monkeypatch)
    uid = "gratis@test.com"
    real = "LAL -6.5 · 68% · Cuota 1.91"
    falso = "EQU -3.5 · 55% · Cuota 1.85"
    html = planes.html_bloque_pro("Línea recomendada", real, falso, uid=uid)
    assert "LAL -6.5" not in html
    assert "68%" not in html
    assert "1.91" not in html
    assert falso in html
    assert "Solo con plan Pro" in html
    assert "sl-pro-blur" in html


def test_html_pro_muestra_dato_real_sin_candado(monkeypatch):
    _setup_memoria(monkeypatch)
    uid = "pro@test.com"
    planes.actualizar_plan_servidor(uid, "pro")
    real = "LAL -6.5 · 68% · Cuota 1.91"
    falso = "EQU -3.5 · 55% · Cuota 1.85"
    html = planes.html_bloque_pro("Línea recomendada", real, falso, uid=uid)
    assert real in html
    assert falso not in html
    assert "Solo con plan Pro" not in html


def test_funciones_pro_y_placeholder_pago(monkeypatch):
    _setup_memoria(monkeypatch)
    assert len(planes.FUNCIONES_PRO) >= 5
    url = planes.iniciar_pago("cliente@test.com")
    assert "cliente@test.com" in url
