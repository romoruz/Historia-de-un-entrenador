"""Fase 2: cada pieza recupera una verdad conocida antes de tocar datos reales."""
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from dtcoach.contexto import diseno
from dtcoach.elo import ajustar_elo
from dtcoach.hipotesis import correr
from dtcoach.pesos import ajustar_pesos, efecto_promedio
from dtcoach.perfil import perfiles


# ---------------------------------------------------------------- Elo
def _liga(n_fechas=60, seed=0, ventaja_local=0.15):
    rng = np.random.default_rng(seed)
    eq = [f"E{i}" for i in range(8)]
    fuerza = {e: (1.0 if e == "E0" else 0.0) for e in eq}
    filas, mid = [], 0
    for f in range(n_fechas):
        orden = rng.permutation(eq)
        for a, b in zip(orden[::2], orden[1::2]):
            mu = fuerza[a] - fuerza[b] + ventaja_local
            u = rng.normal(mu, 1.0)
            ga, gb = (1, 0) if u > 0.4 else ((0, 1) if u < -0.4 else (1, 1))
            filas.append({"match_id": mid, "match_date": date(2024, 1, 1) + timedelta(days=f),
                          "kick_off": "19:00", "home_team": a, "away_team": b,
                          "home_score": ga, "away_score": gb})
            mid += 1
    return pl.DataFrame(filas)


def test_elo_recupera_al_fuerte_y_la_ventaja_de_local():
    r = ajustar_elo(_liga(), [10, 20, 30], [0, 40, 80, 120], burn_in=40)
    final = r.previo.group_by("team").agg(pl.col("elo").last()).sort("elo", descending=True)
    assert final["team"][0] == "E0"
    assert r.h > 0
    S = r.calibracion["S_medio"].to_list()
    assert S[-1] > S[0] + 0.15                        # calibrado en los extremos (bins intermedios: ruido)


def test_elo_es_previo_al_partido():
    r = ajustar_elo(_liga(n_fechas=3), [20], [0], burn_in=0)
    primero = r.previo.filter(pl.col("match_id") == 0)
    assert (primero["elo"] == 1500).all()             # nadie ha jugado aún: sin fuga


# ---------------------------------------------------------------- logit fraccional
def _datos_logit(n=30000, K=3, seed=0, efecto_f=True):
    rng = np.random.default_rng(seed)
    grupos = rng.integers(0, 300, n)
    x1 = rng.integers(0, 2, n).astype(float)
    f = (grupos < 30).astype(float)
    X = np.column_stack([np.ones(n), x1, f, f * x1])
    B = np.array([[0.2, 0.0, -0.3], [0.5, 0.0, -0.4], [0.6 if efecto_f else 0, 0, -0.5 if efecto_f else 0],
                  [0.0, 0.0, 0.0]])
    Z = X @ B
    P = np.exp(Z - Z.max(1, keepdims=True))
    P /= P.sum(1, keepdims=True)
    return X, P, grupos, B, ["intercepto", "x1", "f", "f×x1"]


def test_logit_fraccional_recupera_coeficientes_con_respuesta_exacta():
    X, P, g, B, nom = _datos_logit()
    m = ajustar_pesos(X, P, g, nom, ref=1)
    assert m.convergio
    assert np.abs(m.B() - B).max() < 1e-3        # con E[r|x] exacta, el óptimo ES la verdad


def test_logit_fraccional_con_etiquetas_ruidosas_y_se_robusto():
    X, P, g, B, nom = _datos_logit()
    rng = np.random.default_rng(1)
    u = rng.random(len(P))[:, None]
    R = (u < P.cumsum(1)).astype(float)
    R = np.diff(np.concatenate([np.zeros((len(R), 1)), R], 1), axis=1)   # one-hot muestreado
    m = ajustar_pesos(X, R, g, nom, ref=1)
    se = np.sqrt(np.diag(m.V))
    z = (m.theta - B[:, [0, 2]].ravel()) / se
    assert np.all(np.abs(z) < 4)


def test_wald_no_rechaza_sin_efecto_y_efecto_promedio_cero():
    X, P, g, B, nom = _datos_logit(efecto_f=False)
    m = ajustar_pesos(X, P, g, nom, ref=1)
    assert np.abs(m.theta[m.indices("f") + m.indices("f×x1")]).max() < 1e-3
    f1 = X[:, 2] == 1
    X1 = X[f1]
    X0 = X1.copy(); X0[:, 2] = 0; X0[:, 3] = 0
    e = efecto_promedio(m, X1, X0, m.simular(200, 0))
    assert np.abs(e["delta_pi"]).max() < 1e-3


# ---------------------------------------------------------------- tabla sintética de punta a punta
def _tabla(n_partidos=120, seed=0, efecto=0.0):
    rng = np.random.default_rng(seed)
    filas = []
    for mid in range(n_partidos):
        foco = mid < 30
        for s in range(80):
            f = foco and s < 40
            g = foco and s >= 40
            base = np.array([0.32, 0.27, 0.41])
            if f:
                base = base + np.array([efecto, 0, -efecto])
            r = rng.dirichlet(40 * base)
            filas.append({
                "match_id": mid, "season_id": 1 + mid % 2,
                "score_state": rng.choice(["losing", "drawing", "winning"]),
                "tramo": rng.choice(["0-29", "30-44", "45-59", "60-74", "75+"]),
                "local": bool(rng.integers(0, 2)), "elo_dif": float(rng.normal(0, 1)),
                "origen": rng.choice(["open", "transition", "restart", "set_piece"]),
                "r_1": r[0], "r_2": r[1], "r_3": r[2],
                "xg": float(rng.exponential(0.01)), "remata": bool(rng.random() < 0.1),
                "f": f, "g": g, "partido_foco": foco,
            })
    return pl.DataFrame(filas)


CFG2 = {"n_sim": 60, "n_boot": 100, "alpha": 0.05, "ref": 1, "foco": "DT Prueba"}
FAM = ["Directa", "Circulación estéril", "Ataque elaborado"]


def test_perfiles_sin_diferencia_cubren_cero():
    t = _tabla()
    pf = perfiles(t, 3, n_boot=300, seed=0)
    cubre = [(lo <= 0 <= hi) for lo, hi in zip(pf["ataque"]["lo"], pf["ataque"]["hi"])]
    assert sum(cubre) >= len(cubre) - 1


def test_hipotesis_de_punta_a_punta_detecta_un_efecto_sembrado():
    res = correr(_tabla(efecto=0.08), FAM, CFG2, seed=0)
    h1 = res["hipotesis"]["H1"]
    assert h1["delta_pi"][0] > 0.03 and h1["delta_pi"][2] < -0.03
    assert h1["etiqueta"] == "🟢"
    assert set(res["hipotesis"]) >= {"H1", "H2", "H3", "H4", "H5", "H6", "H7.1", "H8.3"}
    assert all(0 <= h["q"] <= 1 for h in res["hipotesis"].values())
    assert res["frases"]


def test_hipotesis_sin_efecto_no_inventa_identidad():
    res = correr(_tabla(efecto=0.0, seed=3), FAM, CFG2, seed=0)
    assert res["hipotesis"]["H1"]["etiqueta"] == "⚪"


def test_columnas_colineales_se_quitan_y_se_reportan():
    t = _tabla(efecto=0.05).with_columns(pl.lit(True).alias("local"))   # local constante: f×local = f
    res = correr(t, FAM, CFG2, seed=0)
    assert "f×local" in res["modelo"]["columnas_no_estimables"] or "local" in res["modelo"]["columnas_no_estimables"]
    assert res["hipotesis"]["H5"]["p"] == 1.0 or "nota" in res["hipotesis"]["H5"]
