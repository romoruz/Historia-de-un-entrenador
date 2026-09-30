"""Secciones nuevas (G0–G6) contra verdades conocidas: cuentas exactas en jugadas armadas a
mano, fórmulas analíticas y efectos SEMBRADOS que cada método debe encontrar (y no inventar
donde no se sembraron)."""
import math

import numpy as np
import polars as pl
import pytest

from dtcoach import balon_parado as bp
from dtcoach import defensa as dfn
from dtcoach import extra, rival
from dtcoach import futbol as fb
from dtcoach import ofensiva as of
from dtcoach import proyeccion as pr
from dtcoach import sustituciones as su
from dtcoach import xdefensa as xd
from dtcoach.comparar import foco_vs_liga
from dtcoach.geometria import saque

FC = {"tl_min_x": 60.0, "lateral_min_x": 80.0, "ventana_bp": 15.0, "contacto_s": 5.0, "prog_min_m": 10.0,
      "prog_frac": 0.75, "presion_m": 2.0, "ancho_min": 70.0, "largo_m": 30.0, "cambio_m": 35.0}


def _ev(i, **kw):
    b = {"id": f"e{i}", "index": i, "match_id": 1, "period": 1, "minute": 0, "second": 0, "reloj": float(i),
         "type": "Pass", "team": "A", "possession": 1, "possession_team": "A", "play_pattern": "Regular Play",
         "player": "p", "player_id": 1, "position": "x", "x": 50.0, "y": 40.0, "fin_x": None, "fin_y": None,
         "pass_outcome": None, "pass_type": None, "pass_recipient_id": None, "shot_outcome": None,
         "shot_statsbomb_xg": None, "obv_total_net": 0.0, "under_pressure": False, "counterpress": False,
         "duration": 1.0, "shot_type": None, "shot_body_part": None, "pass_height": None, "pass_technique": None,
         "pass_cross": False, "pass_through_ball": False, "pass_cut_back": False, "shot_first_time": False,
         "shot_key_pass_id": None}
    b.update(kw)
    return b


# ----------------------------------------------------------------------
# G0: campos extra
# ----------------------------------------------------------------------
def test_extra_lee_banderas_y_tecnica():
    r = extra.fila({"id": "a", "type": {"name": "Pass"}, "pass": {"cross": True, "technique": {"name": "Inswinging"},
                                                                  "length": 31.5, "shot_assist": True}}, 7)
    assert r["pass_cross"] and r["pass_shot_assist"] and not r["pass_switch"]
    assert r["pass_technique"] == "Inswinging" and r["pass_length"] == 31.5 and r["match_id"] == 7
    viejo = extra.fila({"id": "b", "type": {"name": "Pass"}, "pass": {"outswinging": True}}, 1)
    assert viejo["pass_technique"] == "Outswinging"                         # formato viejo de banderas
    s = extra.fila({"id": "c", "type": {"name": "Shot"}, "shot": {"first_time": True, "key_pass_id": "a"}}, 1)
    assert s["shot_first_time"] and s["shot_key_pass_id"] == "a"
    assert extra.fila({"id": "d", "type": {"name": "Carry"}}, 1) is None     # tipos sin campos extra: fuera


def test_extra_unir_sin_tabla_no_inventa():
    ev = pl.DataFrame([_ev(1)]).drop("pass_cross", "pass_technique")
    u = extra.unir(ev, None)
    assert u["pass_cross"].to_list() == [False] and u["pass_technique"].to_list() == [None]
    assert not extra.tiene_extra(u)


# ----------------------------------------------------------------------
# G5: el frame del saque
# ----------------------------------------------------------------------
def _frame():
    return {"freeze_frame": [
        {"location": [119, 1], "teammate": True, "actor": True},                     # lanza desde y = 1
        {"location": [116, 40], "teammate": True}, {"location": [117, 41], "teammate": True},
        {"location": [110, 45], "teammate": True},
        {"location": [119.5, 40], "teammate": False, "keeper": True},
        {"location": [116.5, 40.5], "teammate": False}, {"location": [119.5, 36], "teammate": False},
        {"location": [108, 40], "teammate": False}, {"location": [103, 50], "teammate": False}]}


def test_saque_cuenta_marca_y_linea():
    s = saque(_frame())
    assert (s["at_area"], s["de_area"], s["at_chica"], s["de_chica"]) == (3, 4, 2, 2)
    assert s["palo_cercano"] == 1 and s["palo_lejano"] == 0                     # saque desde y < 40: poste en 36
    assert s["al_hombre"] + s["zonales"] == s["de_area"]
    # línea legal = penúltimo defensor con el portero: el del poste (119.5) empata al portero;
    # la táctica no cuenta a los de la línea de gol: penúltimo entre {116.5, 108, 103, portero} = 116.5
    assert s["linea_x"] == pytest.approx(119.5) and s["altura_linea"] == pytest.approx(0.5)
    assert s["altura_linea_tactica"] == pytest.approx(3.5)


def test_saque_linea_alta_de_tiro_libre():
    fr = {"freeze_frame": [{"location": [70, 10], "teammate": True, "actor": True},
                           {"location": [100, 30], "teammate": True}, {"location": [103, 45], "teammate": True},
                           {"location": [118, 40], "teammate": False, "keeper": True},
                           *[{"location": [101 + 0.5 * k, 25 + 5 * k], "teammate": False} for k in range(5)]]}
    s = saque(fr)
    assert s["linea_x"] == pytest.approx(103.0) and s["altura_linea"] == pytest.approx(17.0)
    assert s["en_linea"] == 5 and s["at_adelantados"] == 0
    assert s["dist_linea_balon"] == pytest.approx(33.0)


# ----------------------------------------------------------------------
# G5: las jugadas y su desenlace
# ----------------------------------------------------------------------
def _jugadas_a_mano():
    ev = pl.DataFrame([
        _ev(1, x=120., y=0., fin_x=116., fin_y=38., pass_type="Corner", pass_technique="Inswinging", reloj=0.,
            play_pattern="From Corner"),
        _ev(2, type="Shot", x=116., y=38., shot_statsbomb_xg=0.2, shot_outcome="Goal", reloj=2.),
        _ev(3, team="B", x=60., y=40., pass_type="Kick Off", reloj=60.),
        _ev(4, team="B", x=119., y=79., fin_x=112., fin_y=45., pass_type="Corner", reloj=100.),
        _ev(5, team="A", type="Clearance", x=8., y=35., reloj=102.),
        _ev(6, team="B", type="Shot", x=100., y=40., shot_statsbomb_xg=0.05, shot_outcome="Saved", reloj=110.),
        _ev(7, team="B", type="Shot", x=100., y=40., shot_statsbomb_xg=0.05, shot_outcome="Saved", reloj=130.),
        _ev(8, team="A", type="Shot", x=95., y=40., shot_type="Free Kick", shot_statsbomb_xg=0.06,
            shot_outcome="Saved", reloj=200.),
        _ev(9, team="A", x=90., y=2., fin_x=110., fin_y=40., pass_type="Throw-in", reloj=300.),
        _ev(10, team="B", x=70., y=10., fin_x=108., fin_y=30., pass_type="Free Kick", pass_outcome="Pass Offside",
            reloj=400.),
    ], infer_schema_length=None)
    return bp.jugadas(ev, FC)


def test_jugadas_tipo_zona_ventana_y_primer_contacto():
    j = {r["id_saque"]: r for r in _jugadas_a_mano().iter_rows(named=True)}
    assert j["e1"]["tipo"] == "corner" and j["e1"]["zona"] == "area_chica" and j["e1"]["tecnica"] == "Inswinging"
    assert j["e1"]["remate_directo"] and j["e1"]["goles"] == 1 and j["e1"]["primer_contacto"] == "ataque"
    # corner de B desde y = 79: u = (45 − 40)·(+1) = 5 > 4 → primer palo; despeja A; remata a los 10 s (cuenta)
    # pero no a los 30 s (fuera de la ventana de 15 s)
    assert j["e4"]["zona"] == "primer_palo" and j["e4"]["primer_contacto"] == "defensa"
    assert j["e4"]["remates"] == 1 and j["e4"]["xg"] == pytest.approx(0.05)
    assert j["e8"]["tipo"] == "tl_directo" and j["e8"]["remates"] == 1
    assert j["e9"]["tipo"] == "lateral_largo" and j["e9"]["zona"] == "penal"
    assert j["e10"]["tipo"] == "tl_centrado" and j["e10"]["fuera_de_lugar"]


def test_metricas_asignan_la_defensa_al_rival():
    j = _jugadas_a_mano()
    tp = pl.DataFrame({"match_id": [1, 1], "team": ["A", "B"], "rival": ["B", "A"]})
    M = fb.unir(bp.metricas(j, tp), tp.with_columns(pl.lit("c").alias("coach")))
    a = M.filter(pl.col("team") == "A").row(0, named=True)
    b = M.filter(pl.col("team") == "B").row(0, named=True)
    assert a["corner_cerrado__n"] == 1 and a["corner_area_chica__n"] == 1
    assert a["primer_contacto_def__n"] == 1 and a["primer_contacto_def__d"] == 1       # A despejó el corner de B
    assert b["primer_contacto_def__n"] == 0                                              # B no tocó primero
    assert a["fuera_juego_tl__n"] == 1                                                   # A dejó en fuera de juego a B
    assert a["xg_bp__n"] == pytest.approx(0.26)


def test_poisson_con_los_tipos_nuevos():
    rng = np.random.default_rng(0)
    filas = []
    for m in range(300):
        for t, coach in (("A", "F" if m < 80 else "L"), ("B", "R")):
            for k in range(6):
                filas.append({"match_id": m, "team": t, "tipo": "lateral_largo",
                              "remates": int(rng.random() < (0.4 if coach == "F" else 0.15))})
    j = pl.DataFrame(filas)
    tp = pl.DataFrame([{"match_id": m, "team": t, "coach": c, "coach_rival": cr} for m in range(300)
                       for t, c, cr in (("A", "F" if m < 80 else "L", "R"), ("B", "R", "F" if m < 80 else "L"))])
    r = bp.razon_de_tasas(j, tp, "F", "lateral_largo")
    assert r["razon"] == pytest.approx(0.4 / 0.15, rel=0.2) and r["lo"] > 1.5


# ----------------------------------------------------------------------
# G5: xDefense
# ----------------------------------------------------------------------
def test_goal_open_contra_la_formula():
    assert xd.goal_open(100, 40, np.zeros((0, 2))) == 1.0
    ancho = xd.angulo_arco(np.array([100.0]), np.array([40.0]))[0]
    esperado = 1 - 2 * math.asin(0.5 / 10) / ancho
    assert xd.goal_open(100, 40, np.array([[110.0, 40.0]])) == pytest.approx(esperado, rel=1e-9)
    assert xd.goal_open(100, 40, np.array([[95.0, 40.0]])) == 1.0            # detrás del que remata: no tapa
    dos = xd.goal_open(100, 40, np.array([[110.0, 40.0], [110.0, 40.0]]))
    assert dos == pytest.approx(esperado)                                    # sombras solapadas no se cuentan dos veces


def test_rasgos_del_remate():
    import json
    ff = json.dumps([{"location": [110, 40], "teammate": False, "position": {"name": "Center Back"}},
                     {"location": [119, 42], "teammate": False, "position": {"name": "Goalkeeper"}},
                     {"location": [105, 30], "teammate": True, "position": {"name": "Center Forward"}}])
    r = xd.rasgos_remate(100, 40, ff)
    assert r["d_def"] == pytest.approx(10) and r["def_cerca"] == 0 and r["gk_prof"] == pytest.approx(1)
    assert r["gk_desvio"] == pytest.approx(2) and r["con_frame"] == 1


def _centros_sembrados(seed=0, n_partidos=400):
    """Centros de toda una liga; los defensores de T2 conceden la mitad de remates."""
    rng = np.random.default_rng(seed)
    filas, tp = [], []
    eq = [f"E{i}" for i in range(6)]
    for m in range(n_partidos):
        a, b = rng.choice(6, 2, replace=False)
        for t, r in ((eq[a], eq[b]), (eq[b], eq[a])):
            tp.append({"match_id": m, "team": t, "rival": r, "coach": f"T{t[1]}", "coach_rival": f"T{r[1]}"})
            for k in range(8):
                tec = rng.choice(["Inswinging", "Outswinging"])
                zona = rng.choice(["primer_palo", "area_chica", "segundo_palo", "penal", "corto"])
                base = -1.2 + 0.4 * (tec == "Inswinging") + 0.5 * (zona == "area_chica") - 0.8 * (zona == "corto")
                p = 1 / (1 + np.exp(-base)) * (0.5 if r == "E2" else 1.0)
                filas.append({"match_id": m, "team": t, "id_saque": f"{m}-{t}-{k}", "tipo": "corner",
                              "lado": "y0", "tecnica": tec, "altura": "High Pass", "zona": zona, "largo": 30.0,
                              "x_saque": 120.0, "y_saque": 0.0, "minute": int(rng.integers(0, 90)),
                              "remates": int(rng.random() < p)})
    return pl.DataFrame(filas), pl.DataFrame(tp)


def test_capa1_encuentra_la_defensa_sembrada_y_no_inventa():
    j, tp = _centros_sembrados()
    p1, r1 = xd.capa1(j, folds=5, lam=1.0, seed=0)
    assert r1["auc_fuera_de_muestra"] > 0.55 and abs(r1["calibracion"] - 1) < 0.1
    vacio = pl.DataFrame(schema={"match_id": pl.Int64, "id": pl.Utf8, "team": pl.Utf8, "tipo_bp": pl.Utf8,
                                 "gol": pl.Boolean, "xg_sb": pl.Float64, "xg_base": pl.Float64,
                                 "xg_full": pl.Float64})
    M = fb.unir(xd.metricas_equipo(p1, vacio, tp), tp)
    t2 = foco_vs_liga(M, ["xd_prev"], "T2", "propio", 400, 0)["xd_prev"]
    assert t2["dif"] > 0.05 and t2["lo"] > 0                                  # sembrado: evita remates
    t4 = foco_vs_liga(M, ["xd_prev"], "T4", "propio", 400, 0)["xd_prev"]
    assert t4["lo"] < 0.02 and t4["foco"] < 0.02                               # no sembrado
    E = xd.por_etapa(M, "xd_prev", "propio", 30)
    assert E.filter(pl.col("coach") == "T2")["contraido"][0] == E["contraido"].max()


def test_capa2_la_geometria_defensiva_mejora_el_modelo():
    rng = np.random.default_rng(1)
    n = 6000
    go = rng.random(n)
    ld = np.log(rng.uniform(5, 30, n))
    p = 1 / (1 + np.exp(-(-0.5 + 3.0 * go - 1.0 * ld)))
    r = pl.DataFrame({"match_id": rng.integers(0, 600, n), "id": [str(i) for i in range(n)],
                      "team": rng.choice(["A", "B"], n), "tipo_bp": "abierto", "gol": rng.random(n) < p,
                      "xg_sb": p, "log_dist": ld, "angulo": 0.3, "cabeza": 0.0, "de_primera": 0.0,
                      "bp_corner": 0.0, "bp_tl_centrado": 0.0, "bp_lateral_largo": 0.0, "bp_tl_directo": 0.0,
                      "bp_otro": 0.0, "goal_open": go, "d_def": rng.uniform(1, 5, n), "def_cerca": 1.0,
                      "gk_prof": 1.0, "gk_desvio": 0.5, "con_frame": 1})
    _, res = xd.capa2(r, folds=5, lam=1.0, seed=0, n_boot=100)
    assert res["delta_auc"] > 0.03 and res["delta_auc_lo"] > 0
    coef = {c["rasgo"]: c["coef_de"] for c in res["coeficientes_full"]}
    assert coef["goal_open"] > 0.5


def test_contraccion_normal_normal():
    rng = np.random.default_rng(0)
    th = rng.normal(0, 0.1, 400)
    v = np.full(400, 0.1 ** 2)
    x = th + rng.normal(0, 0.1, 400)
    c = xd.contraccion(x, v)
    assert c["tau2"] == pytest.approx(0.01, rel=0.3)
    assert np.allclose(c["confiabilidad"], c["tau2"] / (c["tau2"] + 0.01))
    nulo = xd.contraccion(rng.normal(0, 0.1, 400), v)
    assert nulo["tau2"] < 0.003 and np.nanstd(nulo["contraido"]) < 0.05       # sin variación real: todo a la media


def test_rutinas_y_receta():
    j, tp = _centros_sembrados(n_partidos=200)
    j = j.with_columns(pl.lit(0.0).alias("xg"), pl.Series("at_portero", np.random.default_rng(0).integers(0, 3,
                                                                                                          j.height)))
    j = j.with_columns(pl.when((pl.col("tecnica") == "Inswinging") & pl.col("zona").is_in(["area_chica", "primer_palo"])
                               & (pl.col("at_portero") >= 1)).then(0.08).otherwise(0.02).alias("xg"))
    r = bp.rutinas(j, tp, "T0", n_boot=100, seed=0, min_corners=50)
    assert r["rutinas"][0]["tecnica"] == "Inswinging" and r["rutinas"][0]["zona"] in ("area_chica", "primer_palo")
    ra = r["receta_arsenal"]
    assert ra["dif"] > 0.03 and ra["lo"] > 0


# ----------------------------------------------------------------------
# G1: ofensiva
# ----------------------------------------------------------------------
def test_motivos_de_pase():
    assert of.etiqueta_motivo([1, 2, 1, 2]) == "ABAB" and of.etiqueta_motivo([1, 2, 3, 1]) == "ABCA"
    assert of.etiqueta_motivo([1, 2, 3, 4]) == "ABCD" and of.etiqueta_motivo([1, 2, 1, 3]) == "ABAC"
    # 1→2, 2→1, 1→2, 2→3: ventanas ABAB y ABAC; luego se rompe la cadena (3 no pasa)
    ev = pl.DataFrame([_ev(1, player_id=1, pass_recipient_id=2), _ev(2, player_id=2, pass_recipient_id=1),
                       _ev(3, player_id=1, pass_recipient_id=2), _ev(4, player_id=2, pass_recipient_id=3),
                       _ev(5, player_id=5, pass_recipient_id=6)], infer_schema_length=None)
    m = of.motivos(ev).row(0, named=True)
    assert m["motivo_ABAB__n"] == 1 and m["motivo_ABAC__n"] == 1 and m["motivo_ABAB__d"] == 2


def test_directness_entradas_y_asistencias_exactas():
    ev = pl.DataFrame([
        _ev(1, x=50., y=40., fin_x=70., fin_y=40.),                                   # 20 hacia adelante, largo 20
        _ev(2, x=70., y=40., fin_x=70., fin_y=60.),                                   # 0 adelante, largo 20
        _ev(3, id="k", x=95., y=10., fin_x=110., fin_y=40., pass_cross=True),         # centro que entra al área
        _ev(4, type="Carry", x=100., y=40., fin_x=106., fin_y=40.),                    # conducción que entra
        _ev(5, type="Shot", x=110., y=40., shot_statsbomb_xg=0.3, shot_key_pass_id="k", shot_body_part="Head"),
        _ev(6, type="Shot", x=100., y=40., shot_statsbomb_xg=0.1),                     # sin asistencia
    ], infer_schema_length=None)
    from dtcoach.eventos import posesiones
    tp = pl.DataFrame({"match_id": [1], "team": ["A"], "coach": ["c"]})
    M = fb.unir(of.metricas(ev, posesiones(ev), FC, con_extra=True), tp).row(0, named=True)
    # directness: pases completos de juego y conducciones: Σ Δx = 20 + 0 + 15 + 6 = 41
    largo3 = math.hypot(15, 30)
    assert M["directness__n"] == pytest.approx(41) and M["directness__d"] == pytest.approx(20 + 20 + largo3 + 6)
    assert M["entrada_centro__n"] == 1 and M["entrada_conduccion__n"] == 1 and M["entrada_centro__d"] == 2
    assert M["asist_centro__n"] == 1 and M["asist_sin__n"] == 1 and M["asist_centro__d"] == 2
    assert M["remate_cabeza__n"] == 1 and M["remate_area__n"] == 1


def test_camino_tipico_es_el_de_maxima_probabilidad():
    P = np.zeros((3, 5))
    P[0, 1], P[0, 2], P[0, 3] = 0.6, 0.2, 0.2
    P[1, 2], P[1, 3], P[1, 4] = 0.5, 0.1, 0.4
    P[2, 3], P[2, 4] = 0.9, 0.1
    c = of.camino_tipico(P, 0, 3, (3,))
    assert c["estados"] == [0, 1, 2] and c["prob"] == pytest.approx(0.6 * 0.5 * 0.9)


# ----------------------------------------------------------------------
# G2: rival
# ----------------------------------------------------------------------
def test_estratos_y_ajuste_distinto_sembrado():
    rng = np.random.default_rng(0)
    elo, filas = [], []
    for m in range(1200):
        for t, r in (("A", "B"), ("B", "A")):
            er = rng.normal(1500, 100)
            elo.append({"match_id": m, "team": t, "elo": 1500.0, "elo_rival": er})
    E = pl.DataFrame(elo)
    est, cortes = rival.estratos(E)
    assert cortes["p25"] < 1500 < cortes["p75"]
    assert est["estrato"].value_counts().filter(pl.col("estrato") == "fuerte")["count"][0] == pytest.approx(600, rel=0.1)
    fuerte = dict(zip(zip(est["match_id"], est["team"]), est["estrato"]))
    for m in range(1200):
        for t, r in (("A", "B"), ("B", "A")):
            coach = ("F" if m < 300 else "L") if t == "A" else "R"
            e = fuerte[(m, t)]
            # el foco se echa atrás SOLO contra fuertes (la liga no)
            mu = 0.5 - (0.15 if coach == "F" and e == "fuerte" else 0.0)
            filas.append({"match_id": m, "team": t, "rival": r, "coach": coach,
                          "coach_rival": "R" if t == "A" else ("F" if m < 300 else "L"),
                          "tilt__n": float(np.clip(mu + rng.normal(0, 0.05), 0, 1)), "tilt__d": 1.0})
    M = pl.DataFrame(filas)
    res = rival.por_estrato(M, est, ["tilt"], "F", "propio", 400, 0)
    assert res["fuerte"]["tilt"]["dif"] < -0.1 and abs(res["debil"]["tilt"]["dif"]) < 0.03
    aj = rival.ajuste_distinto(res, ["tilt"])
    assert aj["tilt"]["delta"] < -0.1 and aj["tilt"]["etiqueta"] == "🟢"


# ----------------------------------------------------------------------
# G3: defensa
# ----------------------------------------------------------------------
def test_curva_de_presion_y_tercios_sembrados():
    rng = np.random.default_rng(0)
    ev, ras, tp = [], [], []
    k = 0
    for m in range(120):
        foco = m < 30
        for t, r in (("A", "B"), ("B", "A")):
            ca = ("F" if foco else "L") if t == "A" else "R"
            cr = "R" if t == "A" else ("F" if foco else "L")
            tp.append({"match_id": m, "team": t, "rival": r, "coach": ca, "coach_rival": cr})
            for _ in range(40):
                k += 1
                x = float(rng.uniform(0, 120))
                ev.append({"match_id": m, "index": k, "team": t, "type": "Pass", "x": x, "y": 40.0})
                # el rival de F (lo que F defiende) juega con alguien más cerca
                d = rng.exponential(2.0 if cr == "F" else 4.0)
                ras.append({"match_id": m, "event_index": k, "d_rival": d})
    ev, ras, tp = pl.DataFrame(ev), pl.DataFrame(ras), pl.DataFrame(tp)
    c = dfn.curva_presion(ev, ras, tp, "F", n_boot=100, seed=0)
    i2 = c["radios"].index(2.0)
    assert c["foco"][i2] == pytest.approx(1 - math.exp(-1), abs=0.04)
    assert c["liga"][i2] == pytest.approx(1 - math.exp(-0.5), abs=0.03)
    assert all(np.diff(c["foco"]) >= 0)
    M = fb.unir(dfn.metricas(ev, ras, None, tp, FC), tp)
    r = foco_vs_liga(M, ["presion_tercio_alto", "presion_tercio_bajo"], "F", "propio", 300, 0)
    assert r["presion_tercio_alto"]["lo"] > 0.1 and r["presion_tercio_bajo"]["lo"] > 0.1


# ----------------------------------------------------------------------
# G4: sustituciones
# ----------------------------------------------------------------------
def test_did_de_todos_los_cambios_y_reacomodo_sembrados():
    rng = np.random.default_rng(0)
    pan, subs, tp, shift = [], [], [], []
    for mid in range(1, 121):
        foco = mid <= 30
        for eq, rv in (("A", "B"), ("B", "A")):
            coach = ("F" if foco else "L") if eq == "A" else "R"
            tp.append({"match_id": mid, "team": eq, "rival": rv, "coach": coach,
                       "coach_rival": "R" if eq == "A" else ("F" if foco else "L")})
            for m in range(46, 91):
                extra_ = 0.05 if (foco and eq == "A" and m >= 65) else 0.0
                pan.append({"match_id": mid, "team": eq, "minute": m, "xg": 0.02 + extra_ + rng.normal(0, 0.005),
                            "obv": 0.0, "tercio": 5.0, "n_seq": 3.0, "r0": 1.0, "r1": 1.0, "r2": 1.0})
        subs.append({"match_id": mid, "team": "A", "minute": 65, "tipo": 1, "dif_goles": 0,
                     "coach": "F" if foco else "L", "substitution_replacement_id": 7 + (mid % 2),
                     "puesto_entra": "Center Forward"})
        if foco or mid % 2 == 0:
            shift.append({"match_id": mid, "team": "A", "period": 2, "minute": 66})
    panel, subs, tp = pl.DataFrame(pan), pl.DataFrame(subs), pl.DataFrame(tp)
    d = su.did_cambios(panel, subs, tp, "F", ["x", "y", "z"], 10, 300, 0)
    t = d["todos"]
    assert t["xg_propio"]["efecto"] == pytest.approx(0.5, abs=0.05) and t["xg_propio"]["lo"] > 0.3
    assert t["xg_rival"]["lo"] < 0 < t["xg_rival"]["hi"] and abs(t["fam_0"]["efecto"]) < 1e-9
    rc = su.reacomodo_tras_cambio(subs, pl.DataFrame(shift), tp, "F", 3, 300, 0)
    assert rc["foco"] == 1.0 and rc["liga"] == pytest.approx(0.5, abs=0.05) and rc["lo"] > 0.3
    q = su.quien_entra(subs, panel, {7: "Siete", 8: "Ocho"}, "F")
    assert {x["jugador"] for x in q} == {"Siete", "Ocho"} and sum(x["entradas"] for x in q) == 30
    assert q[0]["xg_favor_90_con"] > q[0]["xg_favor_90_antes"]


# ----------------------------------------------------------------------
# G6: proyección
# ----------------------------------------------------------------------
def _liga_proy(seed=0):
    """8 equipos, 6 temporadas. El técnico C sube 40 % el xG a favor de donde llega (E5 en t2, E6 en t4)."""
    rng = np.random.default_rng(seed)
    eq = [f"E{i}" for i in range(8)]
    fuerza = {t: np.exp(rng.normal(0, 0.2)) for t in eq}
    dfz = {t: np.exp(rng.normal(0, 0.2)) for t in eq}
    filas, tp = [], []
    mid = 0
    coach = {t: f"K{t}" for t in eq}
    import datetime as dt
    fecha = dt.date(2020, 1, 1)
    for s in range(6):
        if s in (1, 3, 5):                         # llegadas SIN efecto: la nula de la liga
            for t in ("E0", "E1", "E2", "E3"):
                coach[t] = f"N{s}{t}"
        if s == 2:
            coach["E5"] = "C"
        if s == 4:
            coach["E6"] = "C"
            coach["E5"] = "KE5b"
        for _ in range(2):
            for a in range(8):
                for b in range(a + 1, 8):
                    mid += 1
                    fecha += dt.timedelta(days=1)
                    A, B = eq[a], eq[b]
                    la = 1.3 * fuerza[A] * dfz[B] * (1.4 if coach[A] == "C" else 1.0)
                    lb = 1.3 * fuerza[B] * dfz[A] * (1.4 if coach[B] == "C" else 1.0)
                    xa, xb = rng.gamma(25, la / 25), rng.gamma(25, lb / 25)
                    ga, gb = rng.poisson(xa), rng.poisson(xb)
                    for t, r, x, y, g, h, loc in ((A, B, xa, xb, ga, gb, True), (B, A, xb, xa, gb, ga, False)):
                        filas.append({"match_id": mid, "team": t, "coach": coach[t], "gf": g, "gc": h,
                                      "pts": 3 if g > h else (1 if g == h else 0), "xG": x, "xG_rival": y})
                        tp.append({"match_id": mid, "team": t, "rival": r, "match_date": fecha, "local": loc,
                                   "season_id": s})
    return pl.DataFrame(filas), pl.DataFrame(tp)


def test_proyeccion_detecta_el_efecto_de_llegada_y_proyecta():
    x, tp = _liga_proy()
    b = pr.base(x, tp)
    mu, h = pr.localia(b)
    fz = pr.fuerza_temporada(b, mu, h)
    ll = pr.llegadas(b, fz, mu, h, n_pre=14, n_post=14, n_boot=50)
    c = ll.filter(pl.col("coach") == "C")
    assert c.height == 2 and all(abs(v - math.log(1.4)) < 0.25 for v in c["e_ataque"].to_list())
    nulas = ll.filter(pl.col("coach").str.starts_with("N"))
    assert nulas.height == 12 and abs(float(nulas["e_ataque"].mean())) < 0.1   # sin efecto sembrado: ≈ 0
    assert ll.filter(pl.col("coach") == "KE5b")["e_ataque"][0] < -0.1          # E5 pierde el efecto de C
    ef = pr.efecto_tecnico(ll, "C", "E6")
    a = ef["ataque"]
    assert ef["llegadas_suyas"] == 1 and a["mu_liga"] < a["contraido"] <= a["suyo_crudo"] + 1e-9
    out = pr.proyectar(b, "C", n_pre=14, n_post=14, n_sim=2000, seed=0)
    assert out["club"] == "E6" and out["escenarios"]["con_el"]["A"] > out["escenarios"]["inercia"]["A"]
    assert out["escenarios"]["con_el"]["pts_media"] > out["escenarios"]["inercia"]["pts_media"]
    assert 0 <= out["validacion"]["cobertura_80"] <= 1 and out["validacion"]["llegadas"] >= 1


def test_torneo_simulado():
    s = pr.simular_torneo(["a", "b", "c", "d"], np.array([2.0, 1, 1, 0.5]), np.array([0.5, 1, 1, 2.0]), 1.3, 1.1,
                          2000, 0)
    assert s["pts"].sum(1).min() >= 12 and s["pts"].sum(1).max() <= 18        # 6 partidos: entre 2 y 3 puntos c/u
    r = pr.resumen_equipo(s, "a", 1, (2, 3))
    assert r["P_lider"] > 0.6 and r["pos_media"] < 1.6
    assert sum(r["dist_pos"]) == 2000


# ----------------------------------------------------------------------
# figuras (humo: se escriben sin error)
# ----------------------------------------------------------------------
def test_figuras_de_las_secciones(tmp_path):
    from dtcoach import graficas_secciones as g
    c = {"radios": [0.5, 1.0, 2.0], "foco": [0.1, 0.2, 0.3], "liga": [0.05, 0.1, 0.2], "foco_lo": [0.09, 0.19, 0.29],
         "foco_hi": [0.11, 0.21, 0.31], "liga_lo": [0.04, 0.09, 0.19], "liga_hi": [0.06, 0.11, 0.21]}
    assert g.curva_presion(c, "F", tmp_path / "a.png").exists()
    assert g.pictograma(0.21, 0.17, "F", tmp_path / "b.png").exists()
    assert g.esquema_bloque(tmp_path / "c.png").exists()
    bt = {q: {"altura": 45.0, "anchura": 36.0, "profundidad": 25.0, "area": 500.0} for q in ("foco", "liga")}
    assert g.bloque_tipico(bt, "F", tmp_path / "d.png").exists()
    perfil = {q: {"de_area": 8.0, "de_chica": 3.0, "palo_cercano": 0.6, "palo_lejano": 0.2, "al_hombre": 5.0,
                  "zonales": 3.0, "at_area": 6.0, "at_chica": 2.0, "at_portero": 1.0, "corners": 100}
              for q in ("foco", "liga")}
    assert g.corner_defensivo(perfil, "F", tmp_path / "e.png").exists()
    assert g.linea_tiros_libres(np.array([15.0, 16, 18]), np.array([12.0, 13, 14]), "F", tmp_path / "f.png").exists()
    res = {m: {"foco": v, "liga": 1 - v} for m, v in (("a", 0.3), ("b", 0.7))}
    assert g.reparto(res, {"x": ["a", "b"]}, {}, "F", tmp_path / "g.png", "t").exists()
    fams = [{"foco": {"visitas": list(np.full(20, 0.05)), "camino": [5, 9, 17], "prob_camino": 0.01},
             "liga": {"visitas": list(np.full(20, 0.05)), "camino": [5, 13, 17], "prob_camino": 0.02}}] * 3
    assert g.familias_cancha(fams, ["a", "b", "c"], 5, 4, "F", tmp_path / "h.png").exists()


# ----------------------------------------------------------------------
# Balón parado: la cadena completa (5.1–5.4)
# ----------------------------------------------------------------------
def test_cadena_de_un_lateral_con_peinada():
    ev = pl.DataFrame([
        _ev(1, x=100., y=0., fin_x=112., fin_y=36., pass_type="Throw-in", player_id=10, reloj=0.),
        _ev(2, type="Ball Receipt*", x=112., y=36., player_id=11, reloj=1.),
        _ev(3, x=112., y=36., fin_x=113., fin_y=42., player_id=11, reloj=1.5),      # la peinada
        _ev(4, type="Clearance", team="B", x=8., y=38., player_id=20, reloj=2.),
        _ev(5, type="Shot", x=113., y=42., player_id=12, shot_statsbomb_xg=0.3, shot_outcome="Goal", reloj=3.),
        _ev(6, x=100., y=80., fin_x=95., fin_y=70., pass_type="Throw-in", player_id=10, reloj=60.),
    ], infer_schema_length=None)
    j = {r["id_saque"]: r for r in bp.jugadas(ev, {**FC, "lateral_min_x": 90.0}).iter_rows(named=True)}
    assert j["e1"]["tipo"] == "lateral_largo" and j["e1"]["intervienen"] == 2 and j["e1"]["pases_cadena"] == 1
    assert j["e6"]["tipo"] == "lateral_zona" and j["e6"]["intervienen"] is None      # sin remate: no hay cadena
    J = bp.jugadas(ev, {**FC, "lateral_min_x": 90.0})
    tp = pl.DataFrame([{"match_id": 1, "team": "A", "rival": "B", "coach": "F", "coach_rival": "L"},
                       {"match_id": 1, "team": "B", "rival": "A", "coach": "L", "coach_rival": "F"}])
    M = fb.unir(bp.metricas(J, tp, 0.8, 90.0), tp)
    a = M.filter(pl.col("team") == "A").row(0, named=True)
    assert a["lat_cuarto__n"] == 2 and a["lat_segunda__n"] == 1 and a["lat_cuarto_area__n"] == 1


def _descomposicion_sembrada(seed=0, n=3000):
    rng = np.random.default_rng(seed)
    tipos = rng.choice(["corner", "tl_centrado", "tl_directo", "lateral_largo", "lateral_zona"], n)
    rem = np.where(tipos == "tl_directo", 1, rng.integers(0, 3, n) * (rng.random(n) < 0.4))
    ids = [[f"s{i}-{k}" for k in range(r)] if r else None for i, r in enumerate(rem)]
    xs = [rng.uniform(0.02, 0.3, r) for r in rem]
    goles = [int((rng.random(r) < x).sum()) for r, x in zip(rem, xs)]
    j = pl.DataFrame({"match_id": rng.integers(0, 200, n), "team": rng.choice(["A", "B"], n),
                      "id_saque": [f"s{i}" for i in range(n)], "tipo": tipos, "x_saque": 110.0, "y_saque": 5.0,
                      "zona": "penal", "remates": rem, "goles": goles, "xg": [float(x.sum()) for x in xs],
                      "ids_remate": ids}, schema_overrides={"ids_remate": pl.List(pl.Utf8)})
    p1 = j.filter(pl.col("tipo") != "tl_directo").select("match_id", "team", "id_saque", "tipo").with_columns(
        pl.Series("p_remate", rng.uniform(0.1, 0.6, int((tipos != "tl_directo").sum()))))
    filas = [{"id": f"s{i}-{k}", "xg_sb": float(x[k]), "xg_base": float(x[k] * 1.1), "xg_full": float(x[k] * 0.9)}
             for i, x in enumerate(xs) for k in range(len(x)) if k == 0]          # solo el 1.º remate tiene foto
    return j, p1, pl.DataFrame(filas)


def test_descomposicion_exacta_y_kappa():
    j, p1, p2 = _descomposicion_sembrada()
    D = xd.descomposicion(j, p1, p2)
    assert D.height == j.height
    suma = (D["prev"] + D["lej"] + D["sup"] + D["port"]).to_numpy()
    assert np.allclose(suma, D["total"].to_numpy(), atol=1e-12)                    # la identidad es exacta
    d = D.filter(pl.col("tipo") == "tl_directo")
    assert (d["p"] == 1).all() and np.allclose(d["prev"].to_numpy(), 0)             # el directo no tiene capa 1
    k = D.filter((pl.col("tipo") == "corner") & (pl.col("s") == 1))
    assert k["kappa"][0] == pytest.approx(k["B"].mean())
    # un remate sin foto entra con su xG en B y en F: la supresión solo mira los remates con foto
    r = D.filter(pl.col("remates") == 2).row(0, named=True)
    x1 = p2.filter(pl.col("id") == f"{r['id_saque']}-0")["xg_sb"][0]
    assert r["B"] - r["F"] == pytest.approx(0.2 * x1)                              # 1.1·x1 − 0.9·x1
    assert r["B"] == pytest.approx(r["xg"] + 0.1 * x1)


def test_cadena_signos_y_grupos():
    j, p1, p2 = _descomposicion_sembrada(n=2000)
    tp = pl.DataFrame([{"match_id": m, "team": t, "rival": r, "coach": c, "coach_rival": cr}
                       for m in range(200) for t, r, c, cr in (("A", "B", "F" if m < 60 else "L", "R"),
                                                               ("B", "A", "R", "F" if m < 60 else "L"))])
    D = xd.descomposicion(j, p1, p2)
    c = xd.cadena(D, tp, "F", n_boot=50, seed=0)
    fa, fd = c["todas"]["foco_ataque"], c["todas"]["foco_defensa"]
    x = D.join(tp.select("match_id", "team", "coach"), on=["match_id", "team"])
    esp = -100 * x.filter(pl.col("coach") == "F")["total"].mean()
    assert fa["total"]["valor"] == pytest.approx(esp)                                # al atacar: xO = −xD
    assert fd["total"]["lo"] <= fd["total"]["valor"] <= fd["total"]["hi"]
    M = fb.unir(xd.metricas_descomposicion(D, tp), tp)
    a = M.filter(pl.col("team") == "A")
    assert a["xo_total_todas__n"].sum() == pytest.approx(-100 * D.filter(pl.col("team") == "A")["total"].sum())


def test_barrera():
    # tiro libre a 20 m, centrado: tres en la barrera a 9.15 m, uno lejos, uno fuera del ángulo
    de = np.array([[109.15, 39.5], [109.15, 40.0], [109.15, 40.5], [118.0, 30.0], [105.0, 60.0]])
    assert xd.barrera(100.0, 40.0, de) == 3


def test_conteo_por_partido_incluye_partidos_sin_saque():
    j = pl.DataFrame({"match_id": [1, 1], "team": ["A", "A"], "tipo": ["tl_directo", "tl_directo"],
                      "x_saque": [95.0, 95.0], "y_saque": [40.0, 40.0], "remates": [1, 1], "xg": [0.05, 0.05],
                      "goles": [0, 0], "tecnica": [None, None], "zona": [None, None],
                      "primer_contacto": [None, None], "remate_directo": [True, True],
                      "fuera_de_lugar": [False, False], "intervienen": [0, 0]},
                     schema_overrides={"tecnica": pl.Utf8, "zona": pl.Utf8, "primer_contacto": pl.Utf8})
    tp = pl.DataFrame([{"match_id": m, "team": t, "rival": r, "coach": "F" if t == "A" else "L",
                        "coach_rival": "L" if t == "A" else "F"} for m in (1, 2) for t, r in (("A", "B"), ("B", "A"))])
    M = fb.unir(bp.metricas(j, tp), tp)
    a = M.filter(pl.col("team") == "A")
    assert a["n_tl_directo__n"].sum() / a["n_tl_directo__d"].sum() == pytest.approx(1.0)   # 2 en 2 partidos
    b = M.filter(pl.col("team") == "B")
    assert b["n_tl_directo__d"].sum() == 2 and b["n_tl_directo__n"].sum() == 0


def test_varianza_comun_no_sesga_la_media_con_goles():
    # 45 etapas iguales en la realidad; goles raros: quien no recibe goles tiene θ alto y varianza propia ~0
    rng = np.random.default_rng(3)
    filas = []
    for e in range(45):
        for m in range(40):
            n = int(rng.integers(3, 8))
            g = rng.binomial(n, 0.03)
            filas.append({"match_id": e * 100 + m, "team": f"E{e}", "coach": f"T{e}",
                          "x__n": 100 * (0.03 * n - g), "x__d": float(n)})
    M = pl.DataFrame(filas)
    prop = xd.por_etapa(M, "x", "propio", 30, "propia")
    com = xd.por_etapa(M, "x", "propio", 30, "comun")
    assert abs(com["mu"][0]) < abs(prop["mu"][0])          # la propia arrastra μ hacia los que no reciben goles
    assert abs(com["mu"][0]) < 0.5


def test_demostracion_un_solo_bh(tmp_path):
    import json

    from dtcoach.demostracion import demostrar, reporte
    a = {"bloque": {"comparacion": {
            "remates": {"foco": 16.0, "liga": 13.0, "dif": 3.0, "lo": 2.0, "hi": 4.0, "p": 0.0005,
                        "partidos_foco": 166, "lado": "propio"},
            "xg": {"foco": 1.3, "liga": 1.29, "dif": 0.01, "lo": -0.1, "hi": 0.12, "p": 0.8, "partidos_foco": 166}}},
         "club_America": {"comparacion": {
            "remates": {"foco": 20.0, "liga": 13.0, "dif": 7.0, "lo": 4.0, "hi": 10.0, "p": 0.001, "partidos_foco": 7}}},
         "hipotesis": {"H17": {"nombre": "rotación", "p": 0.3, "etiqueta": "🔎", "nota": "calendario"},
                       "H22": {"nombre": "ajuste", "p": 0.9, "etiqueta": "⚪", "partidos_foco": 166}},
         "pruebas": [{"id": "arsenal/equivalencia", "afirmacion": "igual ± 0.01", "p": 0.3, "tipo": "equivalencia"}],
         "contexto": {"dif": [0.05, 0.0], "lo": [0.03, -0.02], "hi": [0.07, 0.02]}}
    (tmp_path / "x.json").write_text(json.dumps(a))
    D = demostrar({"sec": tmp_path / "x.json"})
    v = {r["id"]: r["veredicto"] for r in D.iter_rows(named=True)}
    assert v["bloque/comparacion/remates"] == "demostrado"
    assert v["bloque/comparacion/xg"] == "no demostrado"
    assert v["club_America/comparacion/remates"] == "pocos partidos"      # 7 partidos: nunca demostrado
    assert v["H17"] == "no demostrable" and v["H22"] == "no demostrado"
    assert v["contexto[0]"] == "demostrado" and v["contexto[1]"] == "no demostrado"
    assert v["arsenal/equivalencia"] == "no demostrado"
    q = D.filter(pl.col("id") == "bloque/comparacion/remates")["q"][0]
    assert q == pytest.approx(0.0005 * 7 / 2)             # 7 pruebas con p; «remates» es la 2.ª menor (BH: p·m/rango)
    assert any("demostradas" in x for x in reporte(D, "F"))
