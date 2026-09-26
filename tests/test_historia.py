"""Capa de fútbol (fases A–F) contra verdades conocidas: cuentas exactas en partidos
armados a mano, y rasgos SEMBRADOS en una liga sintética (sinteticos.py) que cada
métrica debe encontrar, sin encontrar nada donde no se sembró."""
import math

import numpy as np
import polars as pl
import pytest
from sinteticos import liga

from dtcoach import balon_parado as bp
from dtcoach import futbol as fb
from dtcoach.comparar import etiquetar, fiabilidad, foco_vs_liga, percentil, por_era
from dtcoach.eventos import posesiones
from dtcoach.geometria import bloque, marcaje
from dtcoach.identidad import auc, auc_cv, nivel_local, reconocimiento
from dtcoach.jugadores import cadena_jugadores, roles_espectrales

FC = {"prog_min_m": 10.0, "prog_frac": 0.75, "saque_corto_m": 35.0, "ventana_perdida": 5, "ventana_recuperar": 10,
      "presion_m": 2.0, "tl_min_x": 60.0, "lateral_min_x": 80.0}


@pytest.fixture(scope="module")
def sint():
    ev, tp = liga(vueltas=4, seed=1)
    pos = posesiones(ev)
    tablas = (fb.ofensiva(ev, pos, FC) + fb.defensiva(ev, tp) + fb.transiciones(pos, FC)
              + bp.metricas(bp.jugadas(ev, FC), None, tp))
    return ev, tp, pos, fb.unir(tablas, tp)


# ----------------------------------------------------------------------
# cuentas exactas
# ----------------------------------------------------------------------
def _ev(**kw):
    base = {"id": "x", "index": 1, "match_id": 1, "period": 1, "minute": 0, "second": 0, "reloj": 0.0,
            "type": "Pass", "team": "A", "possession": 1, "possession_team": "A", "play_pattern": "Regular Play",
            "player": "p", "player_id": 1, "position": "CM", "x": 50.0, "y": 40.0, "fin_x": 70.0, "fin_y": 40.0,
            "pass_outcome": None, "pass_type": None, "pass_recipient_id": 2, "shot_outcome": None,
            "shot_statsbomb_xg": None, "obv_total_net": 0.0, "under_pressure": False, "counterpress": False,
            "duration": 1.0}
    base.update(kw)
    return base


def test_progresivos_entradas_y_field_tilt_exactos():
    ev = pl.DataFrame([
        _ev(index=1, x=40, fin_x=60),                                   # 80 → 60 m: progresivo (−20, 75 %)
        _ev(index=2, x=90, fin_x=95),                                   # 30 → 25: no (solo −5)
        _ev(index=3, x=60, fin_x=85),                                   # entra al último tercio y es progresivo
        _ev(index=4, type="Carry", x=95, fin_x=105, fin_y=40),          # entra al área; progresiva (25 → 15 m)
        _ev(index=5, x=60, fin_x=90, pass_outcome="Incomplete"),        # incompleto: no cuenta
        _ev(index=6, x=100, fin_x=110, pass_type="Corner"),             # balón parado: no es progresivo
        _ev(index=7, team="B", possession_team="B", x=85, fin_x=90),    # pase del rival en SU último tercio
    ], infer_schema_length=None)
    tp = pl.DataFrame({"match_id": [1, 1], "team": ["A", "B"], "rival": ["B", "A"]})
    pos = posesiones(ev)
    M = fb.unir(fb.ofensiva(ev, pos, FC), tp.with_columns(pl.lit("c").alias("coach")))
    a = M.filter(pl.col("team") == "A").row(0, named=True)
    assert a["pases_prog__n"] == 2 and a["conducciones_prog__n"] == 1
    assert a["entradas_tercio__n"] == 1 and a["entradas_area__n"] == 1
    # field tilt: pases de A con x ≥ 80 = los de índice 2 y 6 (2); de B: 1 → 2/3
    assert a["field_tilt__n"] == 2 and a["field_tilt__d"] == 3
    assert a["posesion__n"] == 5 and a["posesion__d"] == 6          # la conducción no es pase


def test_ppda_exacto():
    ev = pl.DataFrame([
        *[_ev(index=i, team="B", possession_team="B", x=30.0) for i in range(1, 7)],   # 6 pases de B en su 60 %
        _ev(index=7, team="B", possession_team="B", x=90.0),                           # fuera de la zona
        _ev(index=8, type="Duel", team="A", x=70.0), _ev(index=9, type="Interception", team="A", x=60.0),
        _ev(index=10, type="Duel", team="A", x=20.0),                                   # en su campo: no cuenta
    ], infer_schema_length=None)
    tp = pl.DataFrame({"match_id": [1, 1], "team": ["A", "B"], "rival": ["B", "A"]})
    d = fb.defensiva(ev, tp)[0].filter(pl.col("team") == "A").row(0, named=True)
    assert d["ppda__n"] == 6 and d["ppda__d"] == 2


def test_kaplan_meier_contra_la_formula():
    t = np.array([1, 2, 2, 3, 5, 8])
    e = np.array([1, 1, 0, 1, 0, 1], bool)
    S = fb.kaplan_meier(t, e, np.array([0, 1, 2, 3, 6, 8]))
    s1 = 5 / 6
    s2 = s1 * (1 - 1 / 5)
    s3 = s2 * (1 - 1 / 3)
    assert S == pytest.approx([1, s1, s2, s3, s3, 0.0])


# ----------------------------------------------------------------------
# rasgos sembrados
# ----------------------------------------------------------------------
def test_detecta_la_presion_sembrada_y_no_inventa(sint):
    _, _, _, M = sint
    r = etiquetar(foco_vs_liga(M, ["ppda", "altura_recuperacion", "recupera_5s", "contrapresion", "pases_prog"],
                               "T0", "propio", 400, 0), 0.05, 5)
    assert r["ppda"]["dif"] < 0 and r["ppda"]["hi"] < 0 and r["ppda"]["etiqueta"] == "🟢"
    assert r["altura_recuperacion"]["lo"] > 0 and r["recupera_5s"]["lo"] > 0 and r["contrapresion"]["lo"] > 0
    nula = etiquetar(foco_vs_liga(M, ["pases_prog", "entradas_tercio", "ppda"], "T3", "propio", 400, 0), 0.05, 5)
    assert nula["pases_prog"]["etiqueta"] == "⚪" and nula["entradas_tercio"]["etiqueta"] == "⚪"


def test_lado_rival_es_lo_que_le_hacen(sint):
    _, _, _, M = sint
    # contra T0, los rivales recuperan poco arriba... y T0 les quita la pelota: su posesión efectiva baja
    r = foco_vs_liga(M, ["recupera_5s"], "T0", "rival", 300, 0)["recupera_5s"]
    assert r["partidos_foco"] > 0 and np.isfinite(r["foco"])


def test_percentil_y_fiabilidad(sint):
    _, _, _, M = sint
    eras = por_era(M, ["ppda", "posesion"], "propio", 5)
    p = percentil(eras, "ppda", "T0")
    assert p and p[0]["percentil"] < 20                       # el que más presiona: percentil bajo de PPDA
    fi = fiabilidad(M, ["ppda"], "propio", 5)
    assert fi["ppda"]["etapas"] == 6 and fi["ppda"]["spearman_brown"] > 0.8   # rasgo sembrado: se repite


def test_balon_parado_razon_de_tasas_sembrada(sint):
    ev, tp, _, _ = sint
    j = bp.jugadas(ev, FC)
    r = bp.razon_de_tasas(j, tp, "T1", "corner", "remates")
    assert r["lo"] > 1.2 and r["razon"] == pytest.approx(3.0, rel=0.35)      # sembrado: 1/2 contra 1/6
    n = bp.razon_de_tasas(j, tp, "T4", "corner", "remates")
    assert n["lo"] < 1 < n["hi"]
    _, _, Z = bp.densidad(np.array([110.0]), np.array([40.0]), 2, bw=3.0, paso=0.5)
    assert Z.sum() * 0.25 == pytest.approx(0.5, rel=0.02)                   # integra a remates por jugada


def test_poisson_exposicion_recupera_la_tasa():
    rng = np.random.default_rng(0)
    n = rng.integers(1, 10, 400)
    f = (np.arange(400) < 100).astype(float)
    y = rng.poisson(n * 0.2 * np.exp(np.log(2) * f))
    r = bp.poisson_exposicion(y, n, np.column_stack([np.ones(400), f]), np.arange(400))
    assert math.exp(r["b"][1]) == pytest.approx(2.0, rel=0.25) and r["dispersion_pearson"] == pytest.approx(1, abs=0.3)


# ----------------------------------------------------------------------
# geometría
# ----------------------------------------------------------------------
def _fr(jug):
    return {"freeze_frame": [{"location": list(p), "teammate": c, "actor": a, "keeper": k} for p, c, a, k in jug]}


def test_bloque_envolvente_de_un_rectangulo():
    defs = [((x, y), False, False, False) for x, y in ((60, 20), (60, 60), (80, 20), (80, 60), (70, 40), (65, 30))]
    b = bloque(_fr([((50, 40), True, True, False), *defs]), min_defensores=6)
    assert b["area"] == pytest.approx(20 * 40) and b["anchura"] == pytest.approx(40)
    assert b["altura"] == pytest.approx(120 - np.mean([60, 60, 80, 80, 70, 65]))
    assert bloque(_fr([((50, 40), True, True, False), *defs[:4]]), min_defensores=6) is None


def test_marcaje_hungaro():
    at = [((100, 30), True, False, False), ((100, 50), True, False, False)]
    de = [((101, 30), False, False, False), ((100, 52), False, False, False), ((110, 40), False, False, False)]
    m = marcaje(_fr([((120, 0), True, True, False), *at, *de]))
    assert m["dist_marca"] == pytest.approx((1 + 2) / 2) and m["sobra"] == 1


# ----------------------------------------------------------------------
# jugadores
# ----------------------------------------------------------------------
def test_espectral_separa_dos_comunidades():
    W = np.zeros((8, 8))
    for g in (range(4), range(4, 8)):
        for i in g:
            for j in g:
                if i != j:
                    W[i, j] = 20
    W[3, 4] = W[4, 3] = 1
    lab, k, _ = roles_espectrales(W)
    assert k == 2 and len(set(lab[:4])) == 1 and len(set(lab[4:])) == 1 and lab[0] != lab[4]


def test_cadena_de_jugadores(sint):
    ev, _, _, _ = sint
    partidos = ev["match_id"].unique().to_list()
    # el receptor de cada pase: el ejecutante del siguiente evento del mismo equipo
    ev2 = ev.with_columns(pl.col("player_id").shift(-1).over("match_id", "team").alias("pass_recipient_id"))
    c = cadena_jugadores(ev2, partidos, "E0", min_acciones=20)
    fl = np.array([j["flujo"] for j in c["jugadores"]])
    assert fl.sum() == pytest.approx(1.0) and c["rho_Q"] < 1
    assert all(0 <= j["P_remate_desde"] <= 1 for j in c["jugadores"])


# ----------------------------------------------------------------------
# identidad y tiempo
# ----------------------------------------------------------------------
def test_auc_mann_whitney():
    assert auc(np.array([1, 2, 3, 4]), np.array([0, 0, 1, 1])) == 1.0
    assert auc(np.array([1, 2, 3, 4]), np.array([1, 0, 1, 0])) == 0.25


def test_reconocimiento_sembrado_y_nulo():
    rng = np.random.default_rng(0)
    n = 300
    coach = np.where(np.arange(n) < 60, "F", "otro")
    x1 = rng.normal(0, 1, n) + (coach == "F") * 1.5
    H = pl.DataFrame({"match_id": np.arange(n), "team": np.where(coach == "F", "C", "D"), "coach": coach,
                      "coach_rival": ["z"] * n, "x1": x1, "x2": rng.normal(0, 1, n)})
    r = reconocimiento(H, ["x1", "x2"], "F", "liga", n_perm=30)
    assert r["auc"] > 0.8 and r["p"] < 0.05 and r["rasgos"][0]["rasgo"] == "x1"
    y = (coach == "F").astype(float)
    Xn = rng.normal(0, 1, (n, 2))
    assert abs(auc_cv(Xn, y, np.arange(n)) - 0.5) < 0.12


def test_kalman_distingue_estable_de_cambiante():
    rng = np.random.default_rng(0)
    r = np.full(120, 0.04)
    estable = 0.3 + rng.normal(0, 0.2, 120)
    paseo = 0.3 + np.cumsum(rng.normal(0, 0.1, 120)) + rng.normal(0, 0.2, 120)
    a, b = nivel_local(estable, r), nivel_local(paseo, r)
    assert a["q_sobre_r"] < 0.05 and b["q_sobre_r"] > 0.1
    assert np.mean(np.abs(np.array(a["nivel"]) - 0.3)) < 0.05


# ----------------------------------------------------------------------
# simulador
# ----------------------------------------------------------------------
def test_simulador_simetrico_y_sensible():
    from dtcoach.simulacion import simular
    th = {"lam": 60.0, "pi": np.array([0.4, 0.3, 0.3]), "p": np.array([0.14, 0.03, 0.12]),
          "g": np.array([0.1, 0.1, 0.1])}
    s = simular(th, th, 20000, 0)
    assert abs(s["P_gana"] - s["P_pierde"]) < 0.02
    fuerte = {**th, "p": th["p"] * 2}
    s2 = simular(fuerte, th, 20000, 0)
    assert s2["P_gana"] > s2["P_pierde"] + 0.2 and s2["goles_A"] == pytest.approx(2 * s["goles_A"], rel=0.1)


def test_simulador_deja_el_partido_fuera():
    from dtcoach.simulacion import Parametros
    st = pl.DataFrame({"match_id": [1, 1, 2, 2], "team": ["A", "B", "A", "B"], "n": [50, 50, 50, 50],
                       "u0": [50.0, 25, 50, 25], "u1": [0.0, 25, 0, 25], "s0": [10.0, 5, 0, 5], "s1": [0.0, 1, 0, 1],
                       "x0": [1.0, 0.5, 0, 0.5], "x1": [0.0, 0.1, 0, 0.1]})
    tp = pl.DataFrame({"match_id": [1, 1, 2, 2], "team": ["A", "B", "A", "B"], "coach": ["a", "b", "a", "b"],
                       "rival": ["B", "A", "B", "A"], "coach_rival": ["b", "a", "b", "a"]})
    par = Parametros(st, tp, 2, a=1e-9)
    todo = par.etapa(("a", "A"), "ataque")
    sin1 = par.etapa(("a", "A"), "ataque", 1, "A")
    assert todo["p"][0] == pytest.approx(10 / 100) and sin1["p"][0] == pytest.approx(0.0, abs=1e-6)


# ----------------------------------------------------------------------
# blindaje
# ----------------------------------------------------------------------
def test_score_bootstrap_no_rechaza_bajo_la_nula_y_si_con_efecto():
    from dtcoach.pesos import score_bootstrap
    rng = np.random.default_rng(0)
    G, m = 40, 30
    g = np.repeat(np.arange(G), m)
    f = (g < 8).astype(float)
    z = rng.normal(0, 1, G * m)
    X = np.column_stack([np.ones(G * m), z, f, f * z])
    nombres = ["intercepto", "z", "f", "f×z"]

    def R_de(beta):
        eta = np.column_stack([np.zeros(G * m), X @ beta, 0.3 * X[:, 1]])
        P = np.exp(eta - eta.max(1, keepdims=True))
        return P / P.sum(1, keepdims=True)
    nulo = score_bootstrap(X, R_de(np.array([0.0, 0.5, 0.2, 0.0])), g, nombres, ["f×z"], ref=0, n_boot=299)
    efecto = score_bootstrap(X, R_de(np.array([0.0, 0.5, 0.2, 1.5])), g, nombres, ["f×z"], ref=0, n_boot=299)
    assert nulo["p_boot"] > 0.05 and efecto["p_boot"] < 0.05


def test_splines_restringidos_son_lineales_fuera_de_los_nudos():
    from dtcoach.contexto import rcs
    x = np.linspace(-10, 110, 241)
    B = rcs(x, np.array([5.0, 30.0, 60.0, 90.0]))
    fuera = x > 95
    for c in B.T:
        d2 = np.diff(c[fuera], 2)
        assert np.abs(d2).max() < 1e-8
    assert np.abs(B[x < 5]).max() == 0


def test_bh_global_junta_todas_las_familias(tmp_path):
    import json

    from dtcoach.blindaje import bh_global
    a = tmp_path / "hipotesis_x.json"
    a.write_text(json.dumps({"hipotesis": {"H1": {"p": 0.001, "etiqueta": "🟢"}, "H2": {"p": 0.04, "etiqueta": "🟢"}}}))
    b = tmp_path / "decisiones_x.json"
    b.write_text(json.dumps({"hipotesis": {"H13": {"p": 0.03, "etiqueta": "🟢"},
                                           "H17": {"p": 0.001, "etiqueta": "🔎"}}}))
    d = bh_global([a, b])
    assert d.height == 3 and "decisiones:H17" not in d["id"].to_list()        # la exploratoria no entra
    assert d.filter(pl.col("id") == "hipotesis:H1")["etiqueta_global"][0] == "🟢"


def test_impacto_de_los_cambios_sembrado():
    from dtcoach.jugadores import impacto_cambios
    rng = np.random.default_rng(0)
    filas, subs, tp = [], [], []
    for mid in range(1, 81):
        foco = mid <= 20
        for eq, rival in (("A", "B"), ("B", "A")):
            coach = ("F" if foco else "L") if eq == "A" else "R"
            tp.append({"match_id": mid, "team": eq, "rival": rival, "coach": coach,
                       "coach_rival": "R" if eq == "A" else ("F" if foco else "L")})
            for m in range(46, 90):
                extra = 0.05 if (foco and eq == "A" and m >= 65) else 0.0
                filas.append({"match_id": mid, "team": eq, "period": 2, "minute": m,
                              "shot_statsbomb_xg": 0.02 + extra + rng.normal(0, 0.005), "obv_total_net": 0.0})
        subs.append({"match_id": mid, "team": "A", "minute": 65, "tipo": 2, "dif_goles": 0,
                     "coach": "F" if foco else "L"})
    r = impacto_cambios(pl.DataFrame(filas), pl.DataFrame(subs), pl.DataFrame(tp), "F", 10, 300, 0)
    assert r["xg_propio"]["did"] == pytest.approx(0.5, abs=0.05) and r["xg_propio"]["lo"] > 0.3
    assert r["xg_rival"]["lo"] < 0 < r["xg_rival"]["hi"]
