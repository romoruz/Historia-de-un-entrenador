"""Fase 3b: decisiones y simulador contra verdades conocidas."""
import itertools
import json

import numpy as np
import polars as pl

from dtcoach.decisiones import (correr_decisiones, modelo_tiempo, nivel_puesto, once_titular,
                                panel_cambios, tabla_equipo_partido)
from dtcoach.simulador import poisson_binomial, resultado_esperado

CFG2 = {"n_sim": 60, "n_boot": 200, "alpha": 0.05}


# ---------------------------------------------------------------- Poisson-binomial
def test_poisson_binomial_exacta_contra_fuerza_bruta():
    p = np.array([0.1, 0.35, 0.02, 0.6])
    f = poisson_binomial(p)
    bruto = np.zeros(5)
    for r in itertools.product([0, 1], repeat=4):
        bruto[sum(r)] += np.prod([pi if ri else 1 - pi for pi, ri in zip(p, r)])
    assert np.allclose(f, bruto) and abs(f.sum() - 1) < 1e-12
    assert abs((np.arange(5) * f).sum() - p.sum()) < 1e-12


def test_resultado_esperado_es_simetrico():
    r1 = resultado_esperado([0.3, 0.1, 0.05], [0.4, 0.2])
    r2 = resultado_esperado([0.4, 0.2], [0.3, 0.1, 0.05])
    assert abs(r1["P_gana"] - r2["P_pierde"]) < 1e-12
    assert abs(r1["P_gana"] + r1["P_empata"] + r1["P_pierde"] - 1) < 1e-12
    assert resultado_esperado([], [])["P_empata"] == 1.0


# ---------------------------------------------------------------- puestos y onces
def test_nivel_de_puesto():
    assert nivel_puesto("Goalkeeper") == 0
    assert nivel_puesto("Left Wing Back") == 1
    assert nivel_puesto("Center Defensive Midfield") == 2
    assert nivel_puesto("Right Center Midfield") == 3
    assert nivel_puesto("Left Wing") == 4 and nivel_puesto("Center Attacking Midfield") == 4
    assert nivel_puesto("Striker") == 5 and nivel_puesto("Left Center Forward") == 5
    assert nivel_puesto(None) is None


def _xi(ids):
    return json.dumps([{"player": {"id": i}, "position": {"name": "X"}} for i in ids])


def test_rotacion_por_jaccard():
    assert once_titular(_xi(range(11))) == frozenset(range(11))
    tp = pl.DataFrame({"match_id": [1, 2, 3], "team": ["A"] * 3, "coach": ["F"] * 3,
                       "match_date": [1, 2, 3], "local": [True] * 3, "elo_dif": [0.0] * 3, "season_id": [1] * 3})
    ev = {"shift": pl.DataFrame(schema={"match_id": pl.Int64, "team": pl.Utf8, "period": pl.Int64, "minute": pl.Int64}),
          "xi": pl.DataFrame({"match_id": [1, 2, 3], "team": ["A"] * 3, "tactics_formation": [433] * 3,
                              "tactics_lineup": [_xi(range(11)), _xi(range(11)), _xi(list(range(10)) + [99])]})}
    t = tabla_equipo_partido(ev, tp)
    assert t["rotacion"].to_list() == [None, 0.0, 1 - 10 / 12]


# ---------------------------------------------------------------- tiempo de cambios
def _liga_cambios(n=400, adelanto=12, seed=0):
    """El DT 'F' hace su primer cambio `adelanto` minutos antes que la liga."""
    rng = np.random.default_rng(seed)
    sub, goles, tp = [], [], []
    for mid in range(n):
        eq = [("A", "F") if mid < 80 else (f"L{mid % 7}", f"DT{mid % 7}"), (f"R{mid % 5}", f"DR{mid % 5}")]
        for local, (team, coach) in enumerate(eq):
            tp.append({"match_id": mid, "team": team, "coach": coach, "local": local == 0,
                       "elo_dif": 0.0, "season_id": 1, "match_date": mid})
            base = 72 - (adelanto if coach == "F" else 0)
            m1 = int(np.clip(rng.normal(base, 6), 46, 88))
            for k, mm in enumerate([m1, min(m1 + 8, 89), min(m1 + 15, 90)]):
                sub.append({"match_id": mid, "team": team, "period": 2, "minute": mm, "index": k,
                            "position": "Center Midfield", "substitution_replacement_id": 1000 * mid + k})
        if rng.random() < 0.5:
            goles.append({"match_id": mid, "team": eq[0][0], "minute": int(rng.integers(1, 90))})
    ev = {"sub": pl.DataFrame(sub),
          "goles": pl.DataFrame(goles, schema={"match_id": pl.Int64, "team": pl.Utf8, "minute": pl.Int64})}
    return ev, pl.DataFrame(tp)


def test_panel_marca_la_ventana_y_el_marcador():
    ev, tp = _liga_cambios(n=20)
    p = panel_cambios(ev, tp)
    fila = p.filter((pl.col("match_id") == 0) & pl.col("cambia")).sort("minuto")
    assert fila.height >= 1 and fila["ventanas_usadas"][0] == 0
    assert set(p["dif_goles"].unique().to_list()) <= {-1, 0, 1}


def test_modelo_tiempo_detecta_un_adelanto_sembrado():
    ev, tp = _liga_cambios(adelanto=12)
    r = modelo_tiempo(panel_cambios(ev, tp), "F", n_sim=60, seed=0)
    assert r["H13"]["p"] < 0.01
    assert r["primer_cambio"]["empatando"]["dif"] < -5


def test_modelo_tiempo_sin_adelanto_no_inventa():
    ev, tp = _liga_cambios(adelanto=0, seed=5)
    r = modelo_tiempo(panel_cambios(ev, tp), "F", n_sim=60, seed=0)
    assert r["H13"]["p"] > 0.01


def test_decisiones_de_punta_a_punta():
    ev, tp = _liga_cambios(n=200, adelanto=10)
    ev["pos"] = pl.DataFrame({"match_id": ev["sub"]["match_id"], "player_id": ev["sub"]["substitution_replacement_id"],
                              "puesto_entra": ["Striker"] * ev["sub"].height})
    ev["shift"] = pl.DataFrame(schema={"match_id": pl.Int64, "team": pl.Utf8, "period": pl.Int64, "minute": pl.Int64})
    ev["xi"] = tp.select("match_id", "team").with_columns(pl.lit(433).alias("tactics_formation"),
                                                          pl.lit(_xi(range(11))).alias("tactics_lineup"))
    r = correr_decisiones(ev, tp, "F", CFG2, seed=0)
    assert set(r["hipotesis"]) == {"H13", "H14", "H15", "H16", "H17"}
    assert r["hipotesis"]["H13"]["etiqueta"] == "🟢"
    assert all(0 <= h["q"] <= 1 for k, h in r["hipotesis"].items() if k != "H17")
    # H17 es exploratoria (enmienda 2026-09-26): se reporta sin q ni 🟢
    assert r["hipotesis"]["H17"]["etiqueta"] == "🔎" and np.isnan(r["hipotesis"]["H17"]["q"])
    # todos los cambios sembrados son medio -> delantero: ofensivos
    assert r["tipo_cambio"]["empatando"]["P_foco"][2] > 0.95


def test_el_panel_conserva_las_filas_del_foco():
    """Regresión: el panel se armaba sin el rival del foco y perdía TODAS sus filas en silencio."""
    ev, tp = _liga_cambios(n=100, adelanto=10)
    ev["pos"] = pl.DataFrame({"match_id": ev["sub"]["match_id"], "player_id": ev["sub"]["substitution_replacement_id"],
                              "puesto_entra": ["Striker"] * ev["sub"].height})
    ev["shift"] = pl.DataFrame(schema={"match_id": pl.Int64, "team": pl.Utf8, "period": pl.Int64, "minute": pl.Int64})
    ev["xi"] = tp.select("match_id", "team").with_columns(pl.lit(433).alias("tactics_formation"),
                                                          pl.lit(_xi(range(11))).alias("tactics_lineup"))
    r = correr_decisiones(ev, tp, "F", CFG2, seed=0)
    assert r["_pan"].filter(pl.col("coach") == "F").height > 1000
    assert "nota" not in r["hipotesis"]["H13"]           # f estimable
