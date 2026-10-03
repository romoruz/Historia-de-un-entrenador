"""La mezcla recupera tipos conocidos, K=1 es la cadena vieja y el EM es monótono."""
import numpy as np
import polars as pl
import pytest

from dtcoach.estimate import count_matrix, shrink
from dtcoach.grid import ABSORBING_4, StateSpace
from dtcoach.mezcla import (
    DatosPosesion, ajustar, bondad_largo, cv_k, loglik_por_posesion, pooled,
    reproducibilidad, responsabilidades, resumen_tipos,
)

SP = StateSpace(nx=2, ny=2, phases=("all",), absorbing=ABSORBING_4)   # 4 zonas + 4 absorbentes (la mezcla no depende
#                                                                   de cuántos absorbentes haya; ADR-v2-72)
# filas: 4 transitorios; columnas: 0..3 zonas, 4 GOAL, 5 SHOT_NOGOAL, 6 LOSS, 7 OUT
P_DIRECTO = np.array([
    [0, 0, .45, .45, 0, 0, .10, 0],
    [0, 0, .45, .45, 0, 0, .10, 0],
    [0, 0, .10, .10, .05, .45, .25, .05],
    [0, 0, .10, .10, .05, .45, .25, .05],
])
P_PACIENTE = np.array([
    [.35, .35, .10, .10, 0, 0, .10, 0],
    [.35, .35, .10, .10, 0, 0, .10, 0],
    [.10, .10, .30, .30, .01, .04, .10, .05],
    [.10, .10, .30, .30, .01, .04, .10, .05],
])
MU = np.array([[.1, .1, .4, .4], [.4, .4, .1, .1]])
PI = np.array([.3, .7])


def sintetico(n=6000, seed=0):
    rng = np.random.default_rng(seed)
    filas = []
    for p in range(n):
        k = rng.choice(2, p=PI)
        P = (P_DIRECTO, P_PACIENTE)[k]
        s, t = rng.choice(4, p=MU[k]), 0
        while True:
            j = rng.choice(8, p=P[s])
            filas.append((f"{p // 50}_{p}", p // 50, t, int(s), int(j), 0.2 if j in (4, 5) else None))
            t += 1
            if j >= 4:
                break
            s = j
    return pl.DataFrame(filas, schema={"poss_uid": pl.Utf8, "match_id": pl.Int64, "event_index": pl.Int64,
                                       "from_state": pl.Int64, "to_state": pl.Int64, "xg": pl.Float64},
                        orient="row").with_columns(pl.lit("X").alias("team"))


@pytest.fixture(scope="module")
def datos():
    tr = sintetico()
    return tr, DatosPosesion.desde_transiciones(tr, SP)


def test_datos_consistentes(datos):
    tr, d = datos
    assert d.n == tr["poss_uid"].n_unique()
    assert d.largo.sum() == tr.height == d.S.sum()
    C = np.asarray(d.S.sum(0)).reshape(4, 8)
    assert np.array_equal(C, count_matrix(tr, SP))
    assert abs(d.X.sum() - tr["xg"].sum()) < 1e-9


def test_K1_es_la_cadena_del_proyecto_viejo(datos):
    tr, d = datos
    Qp, mup = pooled(d)
    m = ajustar(d, 1, lam=5.0, Qp=Qp, mup=mup, paso_inicial=False)
    assert np.allclose(m.P[0], shrink(count_matrix(tr, SP), Qp, 5.0))
    assert m.pi[0] == 1.0


def test_recupera_dos_tipos_y_em_monotono(datos):
    """Modelo atado (sin paso inicial): recupera exactamente los dos tipos sembrados."""
    _, d = datos
    m = ajustar(d, 2, lam=1.0, n_init=3, seed=1, paso_inicial=False)
    J = np.array(m.objetivo)
    assert np.all(np.diff(J) >= -1e-7 * np.abs(J[:-1]))          # EM-MAP monótono
    assert abs(m.pi[0] - PI[0]) < 0.04                            # tipo 1 = el corto = directo
    assert np.abs(m.P[0] - P_DIRECTO).max() < 0.06
    assert np.abs(m.P[1] - P_PACIENTE).max() < 0.06
    r = responsabilidades(m, d)
    assert np.allclose(r.sum(1), 1.0)
    for t in resumen_tipos(m, d, r):                               # modelo ≈ empírico
        assert abs(t["E_T_modelo"] - t["E_T_empirico"]) / t["E_T_empirico"] < 0.05
        assert abs(t["xG_por_posesion_modelo"] - t["xG_por_posesion_empirico"]) < 0.01
        assert abs(sum(t["visitas_por_zona"]) - 1) < 1e-9
        assert t["posesiones_tipicas"]


def test_paso_inicial_no_desordena_la_mezcla_sin_efecto(datos):
    """ADR-v2-29: sin primer toque real, liberar P0 (tras el arranque atado) no cambia los tipos.
    Regresión: arrancando la escalera con P0 libre, el tipo corto salía con E[T] 1.91 (real 1.43)."""
    from dtcoach.absorbing import Cadena
    _, d = datos
    m = ajustar(d, 2, lam=1.0, seed=1, paso_inicial=True)
    J = np.array(m.objetivo)
    assert np.all(np.diff(J) >= -1e-7 * np.abs(J[:-1]))
    assert abs(m.pi[0] - PI[0]) < 0.04
    for k, Pv in enumerate((P_DIRECTO, P_PACIENTE)):
        ET_real = MU[k] @ Cadena(Pv, 4).largo_esperado()
        assert abs(m.inicio(k)["E_T"] - ET_real) / ET_real < 0.10


def test_cv_elige_dos_y_mezcla_mejora_bondad(datos):
    _, d = datos
    res, det = cv_k(d, [1, 2, 3], lam=1.0, folds=3, seed=0, n_init=2, verbose=False)
    s = dict(zip(res["K"].to_list(), res["score"].to_list()))
    t = dict(zip(res["K"].to_list(), res["t"].to_list()))
    assert s[2] > s[1] and t[2] > 3            # K=2 mejora claramente a K=1
    assert abs(t[3]) < t[2]                    # K=3 casi no añade: el modelo real tiene 2
    assert det.height == 9
    b1 = bondad_largo(ajustar(d, 1, lam=1.0), d, t_min=1)
    b2 = bondad_largo(ajustar(d, 2, lam=1.0, n_init=2), d, t_min=1, n_boot=20)
    assert b2["KS"] < b1["KS"]
    assert 0 < b2["p_conservador"] <= 1


def test_loglik_fuera_de_muestra_finita(datos):
    _, d = datos
    m = ajustar(d.sub(np.arange(d.n) < 3000), 2, lam=1.0, n_init=1)
    ll = loglik_por_posesion(m, d.sub(np.arange(d.n) >= 3000))
    assert np.all(np.isfinite(ll))


def test_estabilidad_con_dos_tipos_reales(datos):
    _, d = datos
    m = ajustar(d, 2, lam=1.0, n_init=3, seed=1)
    dg = m.diagnostico
    assert dg["todos_convergieron"] and dg["acuerdo_minimo"] > 0.9


def test_cierre_de_flujo_K1(datos):
    """Con trayectorias válidas (una absorción al final) y encogimiento mínimo,
    la cadena reproduce E[T] empírico. Si esto falla con datos reales, hay
    trayectorias que continúan después de absorber (ADR-v2-14)."""
    _, d = datos
    b = bondad_largo(ajustar(d, 1, lam=1e-3), d, t_min=1)
    assert abs(b["E_T_modelo"] - b["E_T_empirico"]) / b["E_T_empirico"] < 0.01


def test_escalera_es_reproducible_entre_semillas(datos):
    """ADR-v2-17: la escalera encuentra el mismo óptimo desde semillas distintas."""
    _, d = datos
    r = reproducibilidad(d, 2, lam=1.0, a0=1.0, semillas=[1, 7, 13], max_iter=200, tol=1e-6)
    assert r["rango_J"] < 1.0 and r["acuerdo_suave_minimo"] > 0.95


def test_escalera_no_es_peor_que_kmeans(datos):
    _, d = datos
    esc = ajustar(d, 2, lam=1.0, seed=3, init="escalera")
    km = ajustar(d, 2, lam=1.0, n_init=3, seed=3, init="kmeans")
    assert esc.objetivo[-1] >= km.objetivo[-1] - 1.0


def _sintetico_primer_toque(n=5000, seed=0):
    """Una sola cadena, pero la PRIMERA acción casi nunca se pierde (efecto primer toque)."""
    rng = np.random.default_rng(seed)
    P0 = np.array([[.1, .1, .4, .38, .005, .005, .01, 0], [.1, .1, .38, .4, .005, .005, .01, 0],
                   [.1, .1, .3, .3, .02, .08, .08, .02], [.1, .1, .3, .3, .02, .08, .08, .02]])
    filas = []
    for p in range(n):
        s, t = rng.choice(4, p=[.4, .4, .1, .1]), 0
        while True:
            P = P0 if t == 0 else P_PACIENTE
            j = rng.choice(8, p=P[s] / P[s].sum())
            filas.append((f"{p // 50}_{p}", p // 50, t, int(s), int(j), 0.2 if j in (4, 5) else None))
            t += 1
            if j >= 4:
                break
            s = j
    return pl.DataFrame(filas, schema={"poss_uid": pl.Utf8, "match_id": pl.Int64, "event_index": pl.Int64,
                                       "from_state": pl.Int64, "to_state": pl.Int64, "xg": pl.Float64},
                        orient="row").with_columns(pl.lit("X").alias("team"))


def test_paso_inicial_captura_el_primer_toque():
    """ADR-v2-29: con primer toque real, P0 corrige P(T > 1) y baja el KS; sin él, P0 no estorba."""
    d = DatosPosesion.desde_transiciones(_sintetico_primer_toque(), SP)
    sin = bondad_largo(ajustar(d, 1, lam=1.0, paso_inicial=False), d)
    con = bondad_largo(ajustar(d, 1, lam=1.0, paso_inicial=True), d)
    emp = con["supervivencia"][0]["empirica"]
    assert abs(con["supervivencia"][0]["modelo"] - emp) < abs(sin["supervivencia"][0]["modelo"] - emp)
    assert con["KS"] < sin["KS"]
    assert abs(con["E_T_modelo"] - con["E_T_empirico"]) / con["E_T_empirico"] < 0.01   # cierre exacto


def test_un_tipo_vacio_no_cuenta_como_reproducible(datos):
    """ADR-v2-35: con 2 tipos reales, K = 3 puede dejar un componente casi vacío; eso no es una familia."""
    _, d = datos
    r = reproducibilidad(d, 3, lam=1.0, a0=1.0, semillas=[1, 7, 13], max_iter=200, tol=1e-6)
    if r["pi_minimo"] < 0.01:
        assert not r["reproducible"]
    r2 = reproducibilidad(d, 2, lam=1.0, a0=1.0, semillas=[1, 7, 13], max_iter=200, tol=1e-6)
    assert r2["reproducible"] and r2["pi_minimo"] > 0.25
