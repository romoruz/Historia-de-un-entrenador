"""
Fase 1 -- Propiedades formales de la cadena y métricas derivadas (ADR-v2-31).

Cada métrica responde una pregunta concreta y se valida contra los datos. Lo que
NO se hace, y por qué:
  - MCMC: la posterior de cada fila es Dirichlet (conjugada), se muestrea exacta;
    y la incertidumbre relevante (dependencia dentro del partido) la da el
    bootstrap por partido, no la posterior multinomial.
  - "Probar que la cadena es reversible": no lo es por construcción (se ataca
    hacia un arco). Lo que tiene sentido es MEDIR cuánto no lo es (irreversibilidad).

1. VERIFICACION FORMAL (cadena reiniciada: cada absorción vuelve a empezar con μ)
   - rho(Q) < 1          -> toda secuencia termina c.s. (serie de Neumann converge)
   - irreducible         -> componente fuertemente conexa única (teoría de grafos)
   - aperiódica          -> algún P_ii > 0 en una cadena irreducible => periodo 1
   => existe estacionaria única y P^n -> 1 π' (teorema de convergencia); además
      π_transitorios ∝ μ' N (argumento regenerativo). Se comprueba numéricamente.

2. ESPECTRO de Q
   - rho(Q): tasa de decaimiento de P(T > t) ~ c·rho^t -> "vida media" en acciones
   - distribución cuasi-estacionaria (Yaglom): vector de Perron izquierdo de Q,
     = dónde vive el balón en las secuencias LARGAS (condicionado a no terminar).

3. IRREVERSIBILIDAD (producción de entropía, Schnakenberg)
       sigma = 1/2 sum_{i != j} (F_ij - F_ji) log(F_ij / F_ji),   F_ij = flujo i -> j
   sigma = 0 si y solo si hay balance detallado (cadena reversible). Mide la
   "direccionalidad" del juego en nats por transición: circulación de ida y
   vuelta -> sigma chica; juego vertical -> sigma grande. Más el flujo neto
   hacia adelante en metros por transición.

4. PRIMER PASO / TIEMPOS DE LLEGADA (análisis de primer paso, propiedad fuerte de Markov)
   Para un conjunto objetivo A (p. ej. el último tercio):
       h_i = P(llegar a A antes de absorber)   h = 1 en A,  h_i = sum_j Q_ij h_j
       g_i = E[tau_A · 1{llega}]               g = 0 en A,  g_i = h_i + sum_j Q_ij g_j
   => E[acciones hasta A | llega] = g/h. Se valida contra lo observado.

5. MEMORIA (Anderson y Goodman, 1957): ¿el estado anterior informa el siguiente
   dado el actual? Información mutua condicional
       I(X_{t+1}; X_{t-1} | X_t) = G² / (2N)   (corrección de Miller-Madow)
   y la misma cantidad CONDICIONADA AL TIPO de secuencia. Si la memoria cae al
   condicionar al tipo, la heterogeneidad la explica; si no, es memoria real.
   Igual para el "primer toque": I(X_{t+1}; 1{t = 0} | X_t [, tipo]).
"""
from __future__ import annotations

import numpy as np
import polars as pl
import scipy.linalg as sla
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

_EPS = 1e-300


# ----------------------------------------------------------------------
# 1. Verificación formal
# ----------------------------------------------------------------------
def cadena_reiniciada(P: np.ndarray, mu: np.ndarray) -> np.ndarray:
    """(nt+na)×(nt+na): los absorbentes regresan al inicio con μ."""
    nt, ns = P.shape
    Pr = np.zeros((ns, ns))
    Pr[:nt] = P
    Pr[nt:, :nt] = mu[None]
    return Pr


def verificar(P: np.ndarray, mu: np.ndarray, C: np.ndarray, inicios: np.ndarray) -> dict:
    """C: conteos OBSERVADOS (nt, ns); inicios: conteo de inicios por estado.

    Irreducibilidad y aperiodicidad se comprueban sobre el grafo de lo OBSERVADO,
    no sobre la P encogida: el encogimiento hace positiva toda entrada y la
    comprobación sería trivialmente cierta.
    """
    nt, ns = P.shape
    Q = P[:, :nt]
    rho = float(np.max(np.abs(np.linalg.eigvals(Q))))
    A = np.zeros((ns, ns))
    A[:nt] = C > 0
    A[nt:, :nt] = (inicios > 0)[None]
    # solo entre estados OBSERVADOS: con un estado aumentado (ADR-v2-36/37) puede haber
    # combinaciones que nunca ocurren (p. ej. arrancar una secuencia en el área rival);
    # cada una sería su propia "componente" sin decir nada de la dinámica.
    obs = np.r_[(C.sum(axis=1) > 0) | (C[:, :nt].sum(axis=0) > 0) | (inicios > 0), C[:, nt:].sum(axis=0) > 0]
    n_comp, _ = connected_components(csr_matrix(A[np.ix_(obs, obs)]), directed=True, connection="strong")
    aperiodica = bool(np.any(np.diag(C[:, :nt]) > 0))
    Pr = cadena_reiniciada(P, mu)
    w, V = np.linalg.eig(Pr.T)
    pi = np.real(V[:, np.argmin(np.abs(w - 1))])
    pi = pi / pi.sum()
    N = sla.inv(np.eye(nt) - Q)
    nu = mu @ N
    nu = nu / nu.sum()
    err = float(np.abs(pi[:nt] / pi[:nt].sum() - nu).max())
    lam = np.sort(np.abs(w))[::-1]
    return {"rho_Q": rho, "termina_cs": rho < 1, "componentes_fuertes": int(n_comp),
            "estados_sin_observar": int((~obs[:nt]).sum()),
            "irreducible": n_comp == 1, "aperiodica": aperiodica,
            "estacionaria_igual_a_visitas_err": err,
            "brecha_espectral_reiniciada": float(1 - lam[1]) if len(lam) > 1 else float("nan")}


# ----------------------------------------------------------------------
# 2. Espectro
# ----------------------------------------------------------------------
def espectro(P: np.ndarray) -> dict:
    nt = P.shape[0]
    Q = P[:, :nt]
    w, V = np.linalg.eig(Q.T)
    i = int(np.argmax(np.abs(w)))
    rho = float(np.abs(w[i]))
    yaglom = np.abs(np.real(V[:, i]))
    yaglom = yaglom / yaglom.sum()
    return {"rho": rho, "vida_media_acciones": float(np.log(0.5) / np.log(rho)) if 0 < rho < 1 else float("nan"),
            "yaglom": yaglom}


# ----------------------------------------------------------------------
# 3. Irreversibilidad
# ----------------------------------------------------------------------
def irreversibilidad(C: np.ndarray, centroides_x: np.ndarray, pseudo: float = 0.5) -> dict:
    """C: conteos (nt, ns) de transiciones. Usa solo el flujo entre estados transitorios."""
    nt = C.shape[0]
    F = C[:, :nt].astype(float) + pseudo
    np.fill_diagonal(F, 0.0)
    N = float(C.sum())
    Fn = F / N
    fuera_diag = ~np.eye(nt, dtype=bool)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = (Fn - Fn.T) * np.log(Fn / np.maximum(Fn.T, _EPS))
    sigma = 0.5 * float(np.nan_to_num(term[fuera_diag]).sum())
    # balance detallado: G² = 2 Σ n_ij log(2 n_ij / (n_ij + n_ji))
    n = C[:, :nt].astype(float)
    np.fill_diagonal(n, 0.0)
    s = n + n.T
    msk = n > 0
    G2 = 2 * float((n[msk] * np.log(2 * n[msk] / s[msk])).sum())
    gl = int(np.triu(s > 0, 1).sum())
    dx = centroides_x[None, :] - centroides_x[:, None]
    avance = float((C[:, :nt] * dx).sum() / max(N, 1))
    return {"sigma_nats_por_transicion": sigma, "G2_balance_detallado": G2, "gl": gl,
            "avance_neto_metros_por_transicion": avance}


# ----------------------------------------------------------------------
# 4. Primer paso
# ----------------------------------------------------------------------
def llegada(P: np.ndarray, mu: np.ndarray, A: np.ndarray, P0: np.ndarray | None = None) -> dict:
    """P(llegar a A) y E[acciones hasta A | llega], desde el inicio de la secuencia."""
    nt = P.shape[0]
    Q = P[:, :nt]
    Q0 = Q if P0 is None else P0[:, :nt]
    A = np.asarray(A, dtype=bool)
    fuera = ~A
    h = np.ones(nt)
    g = np.zeros(nt)
    if fuera.any():
        Qff = Q[np.ix_(fuera, fuera)]
        b = Q[np.ix_(fuera, A)].sum(1)
        M = np.eye(fuera.sum()) - Qff
        h[fuera] = np.linalg.solve(M, b)
        h[A] = 1.0
        g[fuera] = np.linalg.solve(M, h[fuera])
    # desde el inicio: si arranca en A, llegó en 0 acciones; si no, primer paso con Q0
    h_ini = np.where(A, 1.0, Q0 @ h)
    g_ini = np.where(A, 0.0, Q0 @ (h + g))
    P_llega = float(mu @ h_ini)
    return {"P_llega": P_llega, "E_acciones_si_llega": float(mu @ g_ini / max(P_llega, _EPS)),
            "h_por_estado": h}


def llegada_empirica(trans: pl.DataFrame, A: np.ndarray, uid: str) -> dict:
    """Validación: fracción de secuencias que pisan A y acciones hasta pisarla."""
    A = np.asarray(A, dtype=bool)
    df = trans.sort([uid, "event_index"]).select(uid, "from_state")
    df = df.with_columns(pl.int_range(pl.len()).over(uid).alias("t"),
                         pl.Series("en_A", A[df["from_state"].to_numpy()]))
    g = df.group_by(uid).agg(pl.col("en_A").any().alias("llega"),
                             pl.col("t").filter(pl.col("en_A")).min().alias("tau"))
    return {"P_llega": float(g["llega"].mean()),
            "E_acciones_si_llega": float(g.filter(pl.col("llega"))["tau"].mean())}


# ----------------------------------------------------------------------
# 5. Memoria
# ----------------------------------------------------------------------
def tripletas(trans: pl.DataFrame, uid: str) -> dict:
    """Índices (h, i, j) de acciones con al menos una previa en la secuencia, y los pares
    (i, j) con indicador de primer paso. `pos` = índice de secuencia (para pesos por tipo)."""
    df = trans.sort([uid, "event_index"]).with_columns(
        (pl.col(uid) != pl.col(uid).shift(1)).fill_null(True).alias("_n"))
    nuevo = df["_n"].to_numpy()
    pos = np.cumsum(nuevo) - 1
    i = df["from_state"].to_numpy().astype(np.int64)
    j = df["to_state"].to_numpy().astype(np.int64)
    h = np.roll(i, 1)
    tiene_previa = ~nuevo
    return {"h": h, "i": i, "j": j, "pos": pos, "primero": nuevo, "tiene_previa": tiene_previa,
            "match": df["match_id"].to_numpy()}


def _cmi(a: np.ndarray, i: np.ndarray, j: np.ndarray, w: np.ndarray, na: int, ni: int, nj: int) -> tuple[float, float, int]:
    """I(J; A | I) con pesos, en nats, corregida por Miller-Madow. Devuelve (I, I_bruta, gl)."""
    idx = (a * ni + i) * nj + j
    n = np.bincount(idx, weights=w, minlength=na * ni * nj).reshape(na, ni, nj)
    N = n.sum()
    if N <= 0:
        return 0.0, 0.0, 0
    n_ai = n.sum(2, keepdims=True)
    n_ij = n.sum(0, keepdims=True)
    n_i = n.sum((0, 2), keepdims=True)
    m = n > 0
    I = float((n[m] * np.log((n * n_i / np.maximum(n_ai * n_ij, _EPS))[m])).sum() / N)
    # grados de libertad efectivos: celdas observadas menos restricciones marginales (aprox.)
    gl = int(max(m.sum() - (n_ai > 0).sum() - (n_ij > 0).sum() + (n_i > 0).sum(), 0))
    return max(I - gl / (2 * N), 0.0), I, gl


def entropia_condicional(i: np.ndarray, j: np.ndarray, w: np.ndarray, ni: int, nj: int) -> float:
    n = np.bincount(i * nj + j, weights=w, minlength=ni * nj).reshape(ni, nj)
    N = n.sum()
    ni_ = n.sum(1, keepdims=True)
    m = n > 0
    return float(-(n[m] * np.log((n / np.maximum(ni_, _EPS))[m])).sum() / N)


def memoria(tr: dict, nt: int, ns: int, R: np.ndarray | None = None, n_boot: int = 0, seed: int = 0) -> dict:
    """Memoria de orden 2 y efecto de primer toque, sin y con condicionar al tipo."""
    m2 = tr["tiene_previa"]
    h, i, j = tr["h"][m2], tr["i"][m2], tr["j"][m2]
    uno = np.ones(len(tr["i"]))

    def medir(pesos_fila):
        w2 = pesos_fila[m2]
        I2, I2b, gl2 = _cmi(h, i, j, w2, nt, nt, ns)
        If, Ifb, glf = _cmi(tr["primero"].astype(np.int64), tr["i"], tr["j"], pesos_fila, 2, nt, ns)
        H = entropia_condicional(tr["i"], tr["j"], pesos_fila, nt, ns)
        return I2, If, H

    I2, If, H = medir(uno)
    out = {"H_siguiente_dado_actual": H, "I_orden2": I2, "I_primer_toque": If,
           "frac_orden2": I2 / H, "frac_primer_toque": If / H}
    if R is not None:
        # condicionar al tipo: I(J; A | I, Z) = Σ_k (N_k / N) I_k con pesos r_sk
        K = R.shape[1]
        tot2 = totf = 0.0
        for k in range(K):
            wk = R[tr["pos"], k]
            I2k, Ifk, _ = medir(wk)
            tot2 += wk[m2].sum() * I2k
            totf += wk.sum() * Ifk
        out["I_orden2_dado_tipo"] = tot2 / uno[m2].sum()
        out["I_primer_toque_dado_tipo"] = totf / uno.sum()
        out["memoria_explicada_por_tipos"] = 1 - out["I_orden2_dado_tipo"] / max(I2, _EPS)
        out["primer_toque_explicado_por_tipos"] = 1 - out["I_primer_toque_dado_tipo"] / max(If, _EPS)
    if n_boot:
        rng = np.random.default_rng(seed)
        partidos, cod = np.unique(tr["match"], return_inverse=True)
        b2, bf = [], []
        for _ in range(n_boot):
            mult = np.bincount(rng.integers(0, len(partidos), len(partidos)), minlength=len(partidos))
            wb = mult[cod].astype(float)
            a, b, _h = medir(wb)
            b2.append(a)
            bf.append(b)
        out["I_orden2_IC"] = [float(np.quantile(b2, 0.025)), float(np.quantile(b2, 0.975))]
        out["I_primer_toque_IC"] = [float(np.quantile(bf, 0.025)), float(np.quantile(bf, 0.975))]
    return out


# ----------------------------------------------------------------------
# 5b. Memoria FUERA DE MUESTRA (ADR-v2-34): sin el sesgo del estimador plug-in
# ----------------------------------------------------------------------
def _tabla(idx: np.ndarray, w: np.ndarray, n: int) -> np.ndarray:
    return np.bincount(idx, weights=w, minlength=n).astype(float)


def memoria_cv(tr: dict, nt: int, ns: int, R: np.ndarray | None = None, folds: int = 5, seed: int = 0,
               lam1: float = 10.0, lam2_grid=(1.0, 10.0, 100.0, 1000.0)) -> dict:
    """Ganancia de verosimilitud en partidos NO vistos (nats por transición) de:
      - orden 2 sobre orden 1:       P(j | h, i) encogida hacia P(j | i)
      - primer toque sobre orden 1:  P(j | i, primero) encogida hacia P(j | i)
    sin y con condicionar al tipo (pesos r_sk). Una ganancia fuera de muestra no
    tiene el sesgo positivo de la información mutua plug-in, que con 96 zonas
    (≈ 920 mil celdas de orden 2) hacía el IC incompatible con la estimación.
    """
    from .estimate import match_folds
    partidos = tr["match"]
    plg = match_folds(np.unique(partidos), folds, seed)
    fold_de = {int(m): f for f, ms in enumerate(plg) for m in ms}
    fold = np.array([fold_de[int(m)] for m in partidos])
    i, j, h, prim, prev = tr["i"], tr["j"], tr["h"], tr["primero"].astype(np.int64), tr["tiene_previa"]
    grupos = [("todas", np.ones((len(i), 1)))]
    if R is not None:
        grupos.append(("dado_tipo", R[tr["pos"]]))
    out = {}
    for nombre, W in grupos:
        g2 = {l2: [] for l2 in lam2_grid}
        gp = {l2: [] for l2 in lam2_grid}
        for f in range(folds):
            tr_m, te_m = fold != f, fold == f
            num2 = {l2: 0.0 for l2 in lam2_grid}
            nump = {l2: 0.0 for l2 in lam2_grid}
            den2 = denp = 0.0
            for k in range(W.shape[1]):
                w = W[:, k]
                # orden 1 (base común), estimada con TODAS las filas de entrenamiento del tipo
                C1 = _tabla(i[tr_m] * ns + j[tr_m], w[tr_m], nt * ns).reshape(nt, ns)
                pj = C1.sum(0) / max(C1.sum(), _EPS)
                P1 = (C1 + lam1 * pj[None]) / (C1.sum(1, keepdims=True) + lam1)
                # orden 2: filas con acción previa
                m2 = tr_m & prev
                C2 = _tabla((h[m2] * nt + i[m2]) * ns + j[m2], w[m2], nt * nt * ns).reshape(nt, nt, ns)
                # primer toque
                Cp = _tabla((prim[tr_m] * nt + i[tr_m]) * ns + j[tr_m], w[tr_m], 2 * nt * ns).reshape(2, nt, ns)
                t2 = te_m & prev
                wt2, wt = w[t2], w[te_m]
                l1_2 = np.log(np.maximum(P1[i[t2], j[t2]], _EPS))
                l1_p = np.log(np.maximum(P1[i[te_m], j[te_m]], _EPS))
                for l2 in lam2_grid:
                    P2 = (C2 + l2 * P1[None]) / (C2.sum(2, keepdims=True) + l2)
                    Pp = (Cp + l2 * P1[None]) / (Cp.sum(2, keepdims=True) + l2)
                    num2[l2] += float((wt2 * (np.log(np.maximum(P2[h[t2], i[t2], j[t2]], _EPS)) - l1_2)).sum())
                    nump[l2] += float((wt * (np.log(np.maximum(Pp[prim[te_m], i[te_m], j[te_m]], _EPS)) - l1_p)).sum())
                den2 += float(wt2.sum())
                denp += float(wt.sum())
            for l2 in lam2_grid:
                g2[l2].append(num2[l2] / den2)
                gp[l2].append(nump[l2] / denp)
        for clave, g in (("orden2", g2), ("primer_toque", gp)):
            l_best = max(g, key=lambda l: np.mean(g[l]))
            v = np.array(g[l_best])
            out[f"{clave}_{nombre}"] = {"ganancia": float(v.mean()), "se": float(v.std(ddof=1) / np.sqrt(len(v))),
                                        "lam2": l_best}
    if R is not None:
        for clave in ("orden2", "primer_toque"):
            a, b = out[f"{clave}_todas"]["ganancia"], out[f"{clave}_dado_tipo"]["ganancia"]
            out[f"{clave}_explicada_por_tipos"] = float(1 - b / a) if a > 0 else float("nan")
    return out
