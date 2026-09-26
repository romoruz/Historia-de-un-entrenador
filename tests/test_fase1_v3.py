"""Fase 1 v3: métricas de Markov y calibración del mallado contra verdades conocidas."""
import numpy as np
import polars as pl

from dtcoach.estimate import count_matrix, shrink
from dtcoach.grid import StateSpace
from dtcoach.mallado import _agregar, _ll_region, camino_agregacion, elegir_malla, evaluar_agregacion
from dtcoach.markov import irreversibilidad, llegada, llegada_empirica, memoria, tripletas, verificar
from dtcoach.mezcla import DatosPosesion

SP = StateSpace(nx=2, ny=2, phases=("all",))


def _cadena(P, mu, n=4000, seed=0, orden2=None):
    """Simula secuencias. `orden2(h, i)` opcional devuelve otra fila si hay memoria."""
    rng = np.random.default_rng(seed)
    filas = []
    for p in range(n):
        s, t, prev = rng.choice(4, p=mu), 0, None
        while True:
            fila = P[s] if (orden2 is None or prev is None) else orden2(prev, s)
            j = rng.choice(8, p=fila)
            filas.append((f"{p // 40}_{p}", p // 40, t, int(s), int(j), 0.2 if j in (4, 5) else None))
            t += 1
            if j >= 4:
                break
            prev, s = s, j
    return pl.DataFrame(filas, schema={"seq_uid": pl.Utf8, "match_id": pl.Int64, "event_index": pl.Int64,
                                       "from_state": pl.Int64, "to_state": pl.Int64, "xg": pl.Float64},
                        orient="row").with_columns(pl.lit("X").alias("team"))


P1 = np.array([[.3, .3, .15, .15, 0, .01, .09, 0], [.3, .3, .15, .15, 0, .01, .09, 0],
               [.1, .1, .35, .3, .02, .05, .06, .02], [.1, .1, .3, .35, .02, .05, .06, .02]])
MU = np.array([.4, .4, .1, .1])


def test_verificacion_formal_de_una_cadena_valida():
    tr = _cadena(P1, MU)
    C = count_matrix(tr, SP)
    ini = np.bincount(DatosPosesion.desde_transiciones(tr, SP).inicio, minlength=4)
    v = verificar(shrink(C, np.full(C.shape, 1 / 8), 1.0), MU, C, ini)
    assert v["termina_cs"] and v["irreducible"] and v["aperiodica"]
    assert v["estacionaria_igual_a_visitas_err"] < 1e-8          # π reiniciada ∝ μᵀN


def test_irreversibilidad_cero_si_hay_balance_detallado_y_positiva_si_no():
    cx = np.array([10.0, 10.0, 90.0, 90.0])
    sim = np.zeros((4, 8)); sim[:, :4] = 100.0; np.fill_diagonal(sim[:, :4], 0)
    ir0 = irreversibilidad(sim, cx, pseudo=0.0)
    assert abs(ir0["sigma_nats_por_transicion"]) < 1e-12 and ir0["G2_balance_detallado"] < 1e-9
    dirig = sim.copy(); dirig[0, 2] = dirig[1, 3] = 400.0            # más flujo hacia adelante
    ir1 = irreversibilidad(dirig, cx, pseudo=0.0)
    assert ir1["sigma_nats_por_transicion"] > 0.01 and ir1["avance_neto_metros_por_transicion"] > 0


def test_llegada_modelo_coincide_con_lo_observado():
    tr = _cadena(P1, MU, n=6000)
    A = np.array([False, False, True, True])
    mod = llegada(P1, MU, A)
    emp = llegada_empirica(tr, A, "seq_uid")
    assert abs(mod["P_llega"] - emp["P_llega"]) < 0.02
    assert abs(mod["E_acciones_si_llega"] - emp["E_acciones_si_llega"]) < 0.1


def test_memoria_nula_en_cadena_de_primer_orden_y_positiva_con_orden_2():
    tr = _cadena(P1, MU, n=6000)
    m0 = memoria(tripletas(tr, "seq_uid"), 4, 8)
    assert m0["I_orden2"] < 0.002                                  # Miller-Madow deja ~0

    def orden2(h, i):                                              # si viene de atrás, sigue hacia adelante
        return P1[3] if h in (0, 1) else P1[i]
    tr2 = _cadena(P1, MU, n=6000, orden2=orden2)
    m2 = memoria(tripletas(tr2, "seq_uid"), 4, 8)
    assert m2["I_orden2"] > 5 * max(m0["I_orden2"], 1e-4)


def test_la_heterogeneidad_fabrica_memoria_aparente_que_el_tipo_explica():
    """Dos tipos de PRIMER orden mezclados parecen tener memoria; condicionado al tipo, desaparece."""
    PB = np.array([[.05, .05, .4, .4, .02, .04, .04, 0], [.05, .05, .4, .4, .02, .04, .04, 0],
                   [0, 0, .45, .45, .02, .04, .04, 0], [0, 0, .45, .45, .02, .04, .04, 0]])
    a = _cadena(P1, MU, n=4000, seed=1)
    b = _cadena(PB, MU, n=4000, seed=2).with_columns(("b" + pl.col("seq_uid")).alias("seq_uid"),
                                                      (pl.col("match_id") + 1000).alias("match_id"))
    tr = pl.concat([a, b])
    t3 = tripletas(tr, "seq_uid")
    d = DatosPosesion.desde_transiciones(tr, SP)
    es_b = d.meta["seq_uid"].str.starts_with("b").to_numpy()
    R = np.column_stack([~es_b, es_b]).astype(float)
    m = memoria(t3, 4, 8, R)
    assert m["I_orden2"] > 0.003
    assert m["memoria_explicada_por_tipos"] > 0.7


# ---------------------------------------------------------------- mallado
def test_agregar_conserva_conteos_y_el_camino_pierde_verosimilitud_monotonamente():
    rng = np.random.default_rng(0)
    C = rng.integers(0, 50, size=(8, 12)).astype(float)
    lab = np.array([0, 0, 1, 1, 2, 2, 3, 3])
    assert abs(_agregar(C, lab, 4).sum() - C.sum()) < 1e-9
    lls = [_ll_region(_agregar(C, l, l.max() + 1), np.bincount(l).astype(float), 8)
           for l in camino_agregacion(C, 4, 2, R_min=1)]
    assert all(b <= a + 1e-9 for a, b in zip(lls, lls[1:]))       # fusionar nunca gana en muestra


def test_agregacion_encuentra_la_particion_agregable_verdadera():
    """Malla fina 4×2 cuya dinámica depende solo de la mitad (izq./der.): R óptimo pequeño y
    la partición de 2 regiones separa exactamente las mitades (lumpability)."""
    rng = np.random.default_rng(0)
    nf, izq = 8, np.array([True] * 4 + [False] * 4)
    fila_i = np.r_[np.where(izq, 0.2, 0.0), [0, 0, 0.2, 0]]         # izq.: se queda en izq. 80 %
    fila_d = np.r_[np.where(~izq, 0.125, 0.0), [0.1, 0.2, 0.2, 0]]  # der.: se queda 50 %, remata más
    filas = np.array([fila_i if izq[z] else fila_d for z in range(nf)])
    C = np.stack([np.stack([rng.multinomial(3000, filas[z]) for z in range(nf)]) for _ in range(5)]).astype(float)
    ag = evaluar_agregacion(C, 4, 2, R_min=1, lam=1.0)
    assert ag["R_opt"] <= 3
    dos = next(l for l in camino_agregacion(C.sum(0), 4, 2, R_min=1) if l.max() + 1 == 2)
    assert len(set(dos[izq])) == 1 and len(set(dos[~izq])) == 1 and dos[0] != dos[-1]


def test_regla_de_eleccion_prefiere_la_malla_simple_si_empatan():
    res = {"5x4": {"score": 1.000, "pliegues": np.array([1.0, 1.01, .99, 1.0, 1.0]), "zonas": 20, "lam": 10,
                   "params_por_obs": .01, "frac_filas_menos_30": 0},
           "10x6": {"score": 1.001, "pliegues": np.array([1.02, 1.0, .98, 1.01, .994]), "zonas": 60, "lam": 10,
                    "params_por_obs": .05, "frac_filas_menos_30": 0}}
    elegida, _ = elegir_malla(res)
    assert elegida == "5x4"


# ---------------------------------------------------------------- memoria fuera de muestra (ADR-v2-34)
def test_memoria_cv_sin_memoria_no_gana_y_con_orden2_si():
    from dtcoach.markov import memoria_cv
    tr = _cadena(P1, MU, n=6000)
    m0 = memoria_cv(tripletas(tr, "seq_uid"), 4, 8, folds=3)
    g0 = m0["orden2_todas"]
    assert g0["ganancia"] < 2 * g0["se"] + 1e-4                      # sin memoria: no gana fuera de muestra

    def orden2(h, i):
        return P1[3] if h in (0, 1) else P1[i]
    tr2 = _cadena(P1, MU, n=6000, orden2=orden2)
    g2 = memoria_cv(tripletas(tr2, "seq_uid"), 4, 8, folds=3)["orden2_todas"]
    assert g2["ganancia"] > 5 * g2["se"] and g2["ganancia"] > 0.01


def test_memoria_cv_la_heterogeneidad_se_explica_por_el_tipo():
    from dtcoach.markov import memoria_cv
    PB = np.array([[.05, .05, .4, .4, .02, .04, .04, 0], [.05, .05, .4, .4, .02, .04, .04, 0],
                   [0, 0, .45, .45, .02, .04, .04, 0], [0, 0, .45, .45, .02, .04, .04, 0]])
    a = _cadena(P1, MU, n=4000, seed=1)
    b = _cadena(PB, MU, n=4000, seed=2).with_columns(("b" + pl.col("seq_uid")).alias("seq_uid"),
                                                      (pl.col("match_id") + 1000).alias("match_id"))
    tr = pl.concat([a, b])
    d = DatosPosesion.desde_transiciones(tr, SP)
    es_b = d.meta["seq_uid"].str.starts_with("b").to_numpy()
    R = np.column_stack([~es_b, es_b]).astype(float)
    m = memoria_cv(tripletas(tr, "seq_uid"), 4, 8, R, folds=3)
    assert m["orden2_todas"]["ganancia"] > 0.005
    assert m["orden2_explicada_por_tipos"] > 0.7
