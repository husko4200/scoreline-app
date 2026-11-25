"""Pruebas de nba_profundo con partidos sintéticos. Ejecutar:  python test_nba_profundo.py  (o con pytest)."""
import nba_profundo as P

N = 15
TID, RIV = "1", "2"


def _fila(tid, nombre, pid, minutos, pts, titular=False, fga=None, fta=2):
    return {"team_id": tid, "id": pid, "Jugador": nombre, "Titular": titular, "MIN": minutos, "PTS": pts, "REB": 4, "AST": 3,
            "FGA": fga if fga is not None else pts * 0.8, "FTA": fta}


def construir():
    """Equipo local con: ESTRELLA (ausente en los partidos 7-11, vuelve en el 12 con minutos limitados), LESIONADO (no juega los
    últimos 2 y figura Day-To-Day), CALIENTE (sube su promedio en los últimos 5) y 7 más de rotación."""
    serie, cajas = [], []
    for i in range(N):
        ausente_estrella = 7 <= i <= 11
        ausente_les = i >= 13
        filas = []
        if not ausente_estrella:
            filas.append(_fila(TID, "Star Player", "10", 24 if i >= 12 else 34, 25, True))
        if not ausente_les:
            filas.append(_fila(TID, "Hurt Guy", "11", 30, 18, True))
        filas.append(_fila(TID, "Hot Hand", "12", 28, 30 if i >= 10 else 14, True))
        for j in range(13, 20):
            # cuando falta la estrella, "Suplente 13" absorbe minutos y puntos
            extra = 8 if (ausente_estrella and j == 13) else 0
            filas.append(_fila(TID, f"Suplente {j}", str(j), 22 + extra, 9 + (6 if extra else 0), j <= 14))
        # rival: 5 jugadores con posiciones conocidas (ids 100-104)
        for k, (pid, pts) in enumerate((("100", 20), ("101", 18), ("102", 15), ("103", 12), ("104", 10))):
            filas.append(_fila(RIV, f"Rival {pid}", pid, 30, pts))
        # el equipo gana más cuando juega la estrella
        pf = 100 if not ausente_estrella else 92
        serie.append({"pf": pf, "pc": 95, "sede": "home" if i % 2 == 0 else "away", "evento": str(i)})
        cajas.append({"jugadores": filas})
    return serie, cajas


def test_forma_y_sede():
    serie, _ = construir()
    f = P.forma(serie, True)
    assert f["u5"]["n"] == 5 and f["total"]["n"] == N
    assert f["sede"]["n"] >= 3 and f["es_local"] is True
    assert f["racha"]["gano"] is True and f["racha"]["n"] >= 3        # pf 100 > pc 95 al final
    assert P.forma(serie[:3], True) is None                          # muestra insuficiente → None, no un número engañoso


def test_eficiencia_solo_si_todos_los_partidos_la_traen():
    serie, _ = construir()
    assert P.forma(serie, True)["u5"]["ortg"] is None                # sin ortg/drtg en la serie → None, no 0
    for g in serie:
        g["ortg"], g["drtg"] = 110.0, 105.0
    f = P.forma(serie, True)
    assert f["u5"]["ortg"] == 110.0 and f["total"]["drtg"] == 105.0
    serie[-1]["ortg"] = None                                         # un solo partido sin dato invalida el promedio de los últimos 5
    assert P.forma(serie, True)["u5"]["ortg"] is None and P.forma(serie, True)["total"]["ortg"] is None


def test_absorcion_exige_muestra_minima():
    serie, cajas = construir()
    vg = P.partidos_jugados(serie, cajas, TID)
    fs = P.fichas(vg)
    # «Hurt Guy» faltó solo 2 partidos: hay comparación (con / sin) pero NO se atribuye quién absorbe su juego
    out = P.bajas_con_impacto(vg, fs, [{"Jugador": "Hurt Guy", "Estado": "Out"}])
    assert out[0]["sin"]["n"] == 2 and out[0]["absorben"] == []


def test_regreso_con_minutos_limitados():
    serie, cajas = construir()
    vg = P.partidos_jugados(serie, cajas, TID)
    fs = P.fichas(vg)
    r = P.regresos(vg, fs, {})
    estrella = next(x for x in r if x["nombre"] == "Star Player")
    assert estrella["perdidos"] == 5 and estrella["desde"] == 3
    assert estrella["limitado"] is True                              # 24 min tras el regreso vs 34 antes (70 %)
    assert round(estrella["min_antes"]) == 34 and round(estrella["min_desde"]) == 24
    assert estrella["equipo_sin"]["dif"] < estrella["equipo_desde"]["dif"]


def test_baja_con_impacto_y_absorcion():
    serie, cajas = construir()
    vg = P.partidos_jugados(serie, cajas, TID)
    fs = P.fichas(vg)
    bajas = [{"Jugador": "Hurt Guy", "Estado": "Day-To-Day", "Lesión": "Tobillo"}, {"Jugador": "Star Player", "Estado": "Probable"}]
    out = P.bajas_con_impacto(vg, fs, bajas)
    hurt = next(b for b in out if b["nombre"] == "Hurt Guy")
    assert hurt["fuera_n"] == 2 and hurt["puede_volver"] is True and hurt["lesion"] == "Tobillo"
    star = next(b for b in out if b["nombre"] == "Star Player")
    assert star["sin"]["n"] == 5 and star["con"]["n"] == N - 5
    assert star["sin"]["dif"] < star["con"]["dif"]                   # sin la estrella el equipo rinde peor
    assert star["absorben"] and star["absorben"][0]["nombre"] == "Suplente 13"
    assert star["absorben"][0]["d_pts"] >= 2 and star["absorben"][0]["d_min"] >= 3


def test_baja_de_larga_duracion_no_inventa_datos():
    serie, cajas = construir()
    vg = P.partidos_jugados(serie, cajas, TID)
    fs = P.fichas(vg)
    out = P.bajas_con_impacto(vg, fs, [{"Jugador": "Nunca Jugó", "Estado": "Out"}])
    assert out[0]["larga"] is True and out[0]["con"] is None and out[0]["sin"] is None and out[0]["mpg"] is None


def test_foco_caliente():
    serie, cajas = construir()
    vg = P.partidos_jugados(serie, cajas, TID)
    f = P.foco(P.fichas(vg), {"hurt guy": "Day-To-Day"})
    hot = next(x for x in f if x["nombre"] == "Hot Hand")
    assert hot["etiqueta"] == "caliente" and hot["d_pts"] > 3
    assert len(f) <= 5


def test_box_incompleto_se_descarta():
    serie, cajas = construir()
    cajas[3] = {"jugadores": cajas[3]["jugadores"][:3]}               # solo 3 filas
    cajas[4] = None                                                   # sin box score
    assert len(P.partidos_jugados(serie, cajas, TID)) == N - 2


def test_emparejamientos_y_concede():
    serie, cajas = construir()
    pos = {"10": {"pos": "PG", "alt": 188}, "11": {"pos": "SG", "alt": 193}, "12": {"pos": "SF", "alt": 201},
           "13": {"pos": "PF", "alt": 206}, "14": {"pos": "C", "alt": 213},
           "100": {"pos": "PG", "alt": 185}, "101": {"pos": "SG", "alt": 195}, "102": {"pos": "SF", "alt": 203},
           "103": {"pos": "PF", "alt": 208}, "104": {"pos": "C", "alt": 211}}
    r = P.analizar(serie, serie, cajas, cajas, [], [], TID, TID, pos)       # mismo equipo en ambos lados: basta para probar el flujo
    pares = r["emparejamientos"]
    assert pares and [p["l"]["pos"] for p in pares] == ["PG", "SG", "SF", "PF", "C"]
    assert pares[0]["dalt"] == 0                                              # mismo equipo → misma altura
    assert r["concede"]["l"]["Guardias"] == 20 + 18 and r["concede"]["l"]["Interiores"] == 12 + 10
    # sin posiciones conocidas del rival: no se publica nada (cobertura < 85 %)
    pobre = {k: v for k, v in pos.items() if k in ("10", "11")}
    assert P.concede_por_posicion(serie, cajas, TID, pobre) is None
    assert P.analizar(serie, serie, cajas, cajas, [], [], TID, TID, None)["emparejamientos"] is None


def test_entradas_vacias_no_rompen():
    r = P.analizar([], [], [], [], None, None, TID, RIV, {})
    assert r["l"]["forma"] is None and r["l"]["foco"] is None and r["l"]["bajas_conocidas"] is False
    assert P.norm("Nikola Jokić Jr.") == "nikola jokic jr" and P.norm("De'Aaron Fox") == "deaaron fox"
    assert P.norm(None) == ""


if __name__ == "__main__":
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in pruebas:
        t()
        print("ok ", t.__name__)
    print(f"{len(pruebas)} pruebas pasaron")
