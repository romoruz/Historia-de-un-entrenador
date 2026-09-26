"""Experimento 360 (ADR-v2-36): geometría contra áreas analíticas, recodificación
zona × nivel consistente y validación cruzada contra verdades conocidas."""
import math

import numpy as np
import polars as pl
import pytest

from dtcoach.cli import _space
from dtcoach.config import RAIZ, Config
from dtcoach.voronoi import (
    Discretizador,
    aumentar,
    comparar,
    conteos_marginales,
    dentro_poligono,
    pliegues_partido,
    puntaje_cv,
    puntos_disco,
    rasgos_frames,
)


def _jug(x, y, comp=False, actor=False):
    return {"location": [x, y], "teammate": comp, "actor": actor, "keeper": False}


def test_poligono_y_disco():
    cuadrado = np.array([[[0, 0], [10, 0], [10, 10], [0, 10]]], dtype=float)
    px = np.array([[5.0, 15.0, 9.9, -1.0]])
    py = np.array([[5.0, 5.0, 9.9, 5.0]])
    assert dentro_poligono(px, py, cuadrado).tolist() == [[True, False, True, False]]
    D = puntos_disco(10.0)
    assert len(D) == 128 and np.linalg.norm(D, axis=1).max() < 10.0


def test_celda_de_voronoi_contra_area_analitica():
    R, h = 10.0, 1.5              # rival a 3 m: la frontera es la mediatriz, a 1.5 m del actor
    f = {"event_uuid": "a", "freeze_frame": [_jug(60, 40, True, True), _jug(63, 40)]}
    r = rasgos_frames([f], R=R, r_presion=5.0)
    segmento = R * R * math.acos(h / R) - h * math.sqrt(R * R - h * h)
    esperado = math.pi * R * R - segmento
    assert r["d_rival"][0] == pytest.approx(3.0)
    assert r["n_rivales"][0] == 1
    assert r["area_local"][0] == pytest.approx(esperado, rel=0.05)


def test_lo_que_la_camara_no_ve_no_cuenta_como_del_rival():
    # la cámara solo ve x <= 60: el rival (x = 63) está fuera y la mitad visible es toda del actor
    vis = [0, 0, 60, 0, 60, 80, 0, 80]
    f = {"event_uuid": "a", "visible_area": vis, "freeze_frame": [_jug(60, 40, True, True), _jug(75, 40)]}
    r = rasgos_frames([f], R=10.0)
    assert r["area_local"][0] == pytest.approx(math.pi * 100, rel=0.03)
    assert r["frac_visible"][0] == pytest.approx(0.5, abs=0.05)


def test_borde_de_la_cancha_y_sin_actor():
    f1 = {"event_uuid": "a", "freeze_frame": [_jug(0, 40, True, True)]}
    f2 = {"event_uuid": "b", "freeze_frame": [_jug(50, 40)]}
    r = rasgos_frames([f1, f2], R=10.0)
    assert r["area_local"][0] == pytest.approx(math.pi * 100 / 2, rel=0.05)   # medio disco en la cancha
    assert np.isnan(r["d_rival"][0])                                            # sin rivales visibles
    assert np.isnan(r["area_local"][1]) and np.isnan(r["d_rival"][1])          # sin actor


def test_discretizador_ordena_de_libre_a_presionado():
    rng = np.random.default_rng(0)
    d = np.r_[rng.uniform(6, 12, 500), rng.uniform(0.3, 1.5, 500)]
    df = pl.DataFrame({"d_rival": d, "n_rivales": (d < 2).astype(float) * 2,
                       "area_local": np.where(d > 5, 250.0, 40.0) + rng.normal(0, 5, 1000)})
    for metodo in ("cuantiles", "kmeans"):
        disc = Discretizador.ajustar(df, metodo, 2, seed=1)
        n = disc.nivel(df)
        assert (n[:500] == 0).mean() > 0.95 and (n[500:] == 1).mean() > 0.95, metodo
    assert (Discretizador.ajustar(df, "kmeans", 1).nivel(df) == 0).all()


# ----------------------------------------------------------------------
# cadenas sintéticas: 2×2 zonas + 4 absorbentes (GOAL, SHOT, LOSS, OUT)
# ----------------------------------------------------------------------
NZ = 4


def _simular(importa: bool, n_partidos=40, por_partido=150, seed=0):
    rng = np.random.default_rng(seed)
    filas, ras = [], []
    for m in range(n_partidos):
        ev = 0
        for p in range(por_partido):
            uid = f"{m}_{p}"
            z = int(rng.integers(NZ))
            while True:
                pres = rng.random() < 0.5
                ev += 1
                d = rng.uniform(0.3, 1.5) if pres else rng.uniform(6, 12)
                ras.append((m, ev, d, 2.0 if pres else 0.0, 40.0 if pres else 250.0))
                p_loss = (0.35 if pres else 0.04) if importa else 0.2
                u = rng.random()
                if u < p_loss:
                    j = NZ + 2
                elif u < p_loss + 0.05:
                    j = NZ + 1
                elif u < p_loss + 0.08:
                    filas.append((uid, m, ev, "Pass", z, int(rng.integers(NZ))))
                    filas.append((uid, m, ev + 1, "TERMINAL", filas[-1][5], NZ + 2))
                    ev += 1
                    break
                else:
                    j = int(rng.integers(NZ))
                filas.append((uid, m, ev, "Pass", z, j))
                if j >= NZ:
                    break
                z = j
    t = pl.DataFrame(filas, schema={"poss_uid": pl.Utf8, "match_id": pl.Int64, "event_index": pl.Int64,
                                    "action_type": pl.Utf8, "from_state": pl.Int64, "to_state": pl.Int64},
                     orient="row").with_columns(pl.col("poss_uid").alias("seq_uid"),
                                                pl.lit(None, dtype=pl.Float64).alias("xg"))
    r = pl.DataFrame(ras, schema={"match_id": pl.Int64, "event_index": pl.Int64, "d_rival": pl.Float64,
                                  "n_rivales": pl.Float64, "area_local": pl.Float64}, orient="row")
    return t, r


def test_aumentar_es_consistente():
    t, r = _simular(True, n_partidos=5, por_partido=40)
    r = r.filter(pl.col("event_index") % 7 != 0)          # frames faltantes: se imputan
    disc = Discretizador.ajustar(r, "cuantiles", 2)
    a, diag = aumentar(t, r, disc, NZ, min_cobertura=0.5)
    assert diag["frac_origen_imputado"] > 0
    # posesiones sin NINGÚN frame salen completas (no hay de dónde imputar)
    t = t.filter(pl.col("seq_uid").is_in(a["seq_uid"].unique().to_list()))
    assert a.height == t.height and diag["secuencias_sin_nivel"] > 0
    nt = NZ * 2
    a = a.sort(["poss_uid", "event_index"])
    fr, to = a["from_state"].to_numpy(), a["to_state"].to_numpy()
    mismo = (a["poss_uid"].to_numpy()[1:] == a["poss_uid"].to_numpy()[:-1])
    enc = mismo & (to[:-1] < nt)
    assert (to[:-1][enc] == fr[1:][enc]).all()             # destino(t) = origen(t+1)
    orig = t.sort(["poss_uid", "event_index"])
    assert ((fr // 2) == orig["from_state"].to_numpy()).all()   # la zona no cambia
    ab = orig["to_state"].to_numpy() >= NZ
    assert (to[ab] == orig["to_state"].to_numpy()[ab] - NZ + nt).all()
    b, _ = aumentar(t, r, Discretizador("cuantiles", 1), NZ, min_cobertura=0.5)
    assert b.sort(["poss_uid", "event_index"])["from_state"].equals(orig["from_state"])


def test_partidos_sin_360_salen_completos():
    t, r = _simular(True, n_partidos=4, por_partido=30)
    r = r.filter(pl.col("match_id") != 2)
    _, diag = aumentar(t, r, Discretizador.ajustar(r, "cuantiles", 2), NZ)
    assert diag["partidos_total"] == 4 and diag["partidos_con_360"] == 3


def _cv(importa):
    t, r = _simular(importa)
    base, _ = aumentar(t, r, Discretizador("cuantiles", 1), NZ)
    folds = pliegues_partido(base["match_id"].to_numpy(), 5, 0)
    res = {"base:1": puntaje_cv(conteos_marginales(base, NZ, 1, folds), NZ, [1, 10, 100])}
    for cand in ("cuantiles:2", "kmeans:2", "kmeans:3"):
        m, L = cand.split(":")
        tk, _ = aumentar(t, r, Discretizador.ajustar(r, m, int(L), 0), NZ)
        res[cand] = puntaje_cv(conteos_marginales(tk, NZ, int(L), folds), NZ, [1, 10, 100])
    return comparar(res)


def test_cv_detecta_presion_que_importa():
    elegido, tab = _cv(True)
    assert elegido in ("cuantiles:2", "kmeans:2")           # 1-EE: no premia el nivel de más
    fila = tab.filter(pl.col("candidato") == elegido)
    assert fila["mejora"][0] and fila["score_absorbente"][0] > tab.filter(
        pl.col("candidato") == "base:1")["score_absorbente"][0]


def test_cv_no_inventa_mejora_si_la_presion_no_importa():
    elegido, tab = _cv(False)
    assert not tab.filter(pl.col("candidato") != "base:1")["mejora"].any()
    assert elegido == "base:1"


def test_config_del_experimento_hereda_y_no_pisa_rutas():
    base = Config.load()
    c = Config.load(RAIZ / "config" / "presion.yaml")
    assert c["pitch"] == base["pitch"] and c["mezcla"] == base["mezcla"]
    assert c["voronoi"]["activo"] and c["voronoi"]["R"] == base["voronoi"]["R"]
    assert c.ruta("transiciones") != base.ruta("transiciones")
    assert c.ruta("mezcla_dir") != base.ruta("mezcla_dir") and c.ruta("reportes") != base.ruta("reportes")
    sp = _space(c)
    assert sp.n_transient == sp.n_zones * c["voronoi"]["L"]
    assert not base["voronoi"]["activo"] and _space(base).n_transient == _space(base).n_zones
    cb = Config.load(RAIZ / "config" / "presion_base.yaml")
    assert cb.ruta("transiciones") == c.ruta("transiciones").parent / "base" / "transitions.parquet"
