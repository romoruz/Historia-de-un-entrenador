"""
EXPERIMENTO (Mejora E, ADR-v2-59, no adoptado): la arista marcada pase / conducción.

Hoy un pase y una conducción entre las mismas celdas son la misma arista. Aquí cada transición lleva su marca
m ∈ {pase, conducción, remate, terminal} (las dos últimas son estructurales: el remate va a GOL / REMATE y la
absorción terminal artificial va a PÉRDIDA), y cada familia factoriza la arista:

    P^k(m, j | i) = P^k(m | i) · P^k(j | i, m),       P^k(j | i) = Σ_m P^k(m, j | i).

NO se amplía el espacio de estados: los 20 estados, los absorbentes y el paso inicial son los mismos. Lo que crece
es el número de celdas por fila (de ns a M·ns).

LAS FORMAS CERRADAS SE CONSERVAN (Prop. 4.2)
--------------------------------------------
La dinámica de la ZONA de una familia es la cadena marginal P^k(j | i), que es estocástica por filas. N, B, V,
E[T] y la supervivencia salen de esa marginal exactamente como en el §2; la marca no entra.

CON LAS MISMAS r_sk, LA MARGINAL ES LA DEL MODELO BASE
------------------------------------------------------
Paso M con prior de Dirichlet hacia la cadena de la liga encogida a la uniforme U = 1/(M·ns):
    P^k(m, j | i) = (C^k_imj + λ Q_imj) / (C^k_i + λ),
    Σ_m:  P^k(j | i) = (C^k_ij + λ Q_ij) / (C^k_i + λ),     Q_ij = Σ_m Q_imj = (C_ij + 1/ns) / (C_i + 1),
que es el paso M del modelo base. Así que la arista NO cambia cómo se estima la cadena de una familia dadas sus
secuencias: todo lo que cambia está en el paso E, que usa la marca para decidir a qué familia pertenece cada
secuencia. Consecuencia: con UNA sola cadena (K = 1) la predicción de la siguiente zona es idéntica a la del modelo
base (ganancia 0 por construcción). La única ganancia posible en la escala común es la de la MEZCLA.

CÓMO SE COMPARA (escala común, Prop. 5.1; CV por partido)
---------------------------------------------------------
Para cada secuencia de un partido no visto, acción por acción y sin mirar adelante: el peso de cada familia se
actualiza con lo ya observado (en la arista, incluidas las marcas pasadas), y la siguiente zona se predice con la
MARGINAL: p(z_{t+1}) = Σ_k w_k(t) P^k(z_{t+1} | z_t). Ambos modelos predicen el mismo evento (zona o absorbente),
con el mismo pasado disponible. Puntaje: log p − log a_j si j es transitorio (a_j = fracción de cancha de la zona).
"""
from __future__ import annotations

import numpy as np
import polars as pl
import scipy.sparse as sp
from scipy.special import logsumexp

from . import mezcla as mz
from .estimate import shrink
from .grid import StateSpace

MARCAS = ("pase", "conducción", "remate", "terminal")
TIPO_A_MARCA = {"Pass": 0, "Carry": 1, "Shot": 2, "TERMINAL": 3}
M = len(MARCAS)


# ---------------------------------------------------------------- datos
def _orden(trans: pl.DataFrame) -> pl.DataFrame:
    uid = "seq_uid" if "seq_uid" in trans.columns else "poss_uid"
    return trans.sort([uid, "event_index"]).with_columns(
        (pl.col(uid) != pl.col(uid).shift(1)).fill_null(True).alias("_nuevo"))


def marcas(trans: pl.DataFrame) -> np.ndarray:
    m = trans["action_type"].replace_strict(TIPO_A_MARCA, default=-1).to_numpy()
    if (m < 0).any():
        raise ValueError(f"tipos de acción sin marca: {sorted(set(trans.filter(pl.Series(m < 0))['action_type'].to_list()))}")
    return m.astype(np.int64)


def datos(trans: pl.DataFrame, space: StateSpace) -> mz.DatosPosesion:
    """Como `DatosPosesion.desde_transiciones`, con la celda (i, m, j): n_states = M·ns («pseudo-destinos»).
    El resto (inicio, largo, meta, X) es idéntico al del modelo base."""
    base = mz.DatosPosesion.desde_transiciones(trans, space)
    df = _orden(trans)
    nuevo = df["_nuevo"].to_numpy()
    pid = np.cumsum(nuevo) - 1
    starts = np.flatnonzero(nuevo)
    nt, ns = space.n_transient, space.n_states
    fr = df["from_state"].to_numpy().astype(np.int64)
    to = df["to_state"].to_numpy().astype(np.int64)
    celda = fr * (M * ns) + marcas(df) * ns + to
    n = len(starts)
    S = sp.csr_matrix((np.ones(len(fr)), (pid, celda)), shape=(n, nt * M * ns))
    S.sum_duplicates()
    S0 = sp.csr_matrix((np.ones(n), (np.arange(n), celda[starts])), shape=(n, nt * M * ns))
    return mz.DatosPosesion(S, base.X, base.inicio, base.largo, base.meta, nt, M * ns, base.nx, base.ny,
                            base.n_phases, S0, base.X0)


def marginal(m: mz.Mezcla, ns: int) -> mz.Mezcla:
    """La mezcla de zonas: P^k(j | i) = Σ_m P^k(m, j | i). Es una Mezcla del modelo base (formas cerradas del §2)."""
    K, nt = m.P.shape[0], m.P.shape[1]
    P = m.P.reshape(K, nt, M, ns).sum(2)
    P0 = None if m.P0 is None else m.P0.reshape(K, nt, M, ns).sum(2)
    return mz.Mezcla(m.pi, m.mu, P, m.lam, m.a0, m.objetivo, m.diagnostico, P0)


def reparto_marcas(m: mz.Mezcla, d: mz.DatosPosesion, ns: int) -> np.ndarray:
    """(K, M): fracción de las transiciones de cada familia con cada marca (conteos ponderados por r_sk)."""
    r = mz.responsabilidades(m, d)
    C = np.asarray(d.S.T @ r).T.reshape(r.shape[1], d.n_transient, M, ns).sum((1, 3))
    return C / C.sum(1, keepdims=True)


# ---------------------------------------------------------------- ajuste (escalera, como mezcla.ajustar)
def ajustar(d: mz.DatosPosesion, K: int, lam: float, a0: float = 1.0, max_iter: int = 1000, tol: float = 1e-7,
            seed: int = 0, n_corto: int = 25, lam0: float | None = None, pr: mz.Prior | None = None,
            ns: int | None = None, verbose: bool = False) -> mz.Mezcla:
    """La escalera de `mezcla.ajustar` sobre las celdas (i, m, j). Solo cambia el orden final de los tipos, que se
    fija con el E[T] de la MARGINAL (la cadena expandida no es una cadena de zonas)."""
    ns = ns or d.n_states // M
    pr = pr or mz.prior(d, lam, a0, True, lam0)
    C = np.asarray(d.S.sum(axis=0)).ravel().reshape(d.n_transient, d.n_states)
    pt = mz.Prior(shrink(C, np.full(C.shape, 1.0 / C.shape[1]), 1.0), None, pr.mup, pr.lam, pr.lam, pr.a0, False)
    pt.Q0p = pt.Qp
    rng = np.random.default_rng([seed, K])
    m, _ = mz._em(d, *mz._desde_kmeans(d, 1, None, rng, pt), pt, max_iter, tol)
    for nivel in range(2, K + 1):
        cand = []
        for k in range(m.K):
            mk, _ = mz._em(d, *mz._partir(m, k, rng), pt, n_corto, tol)
            cand.append((mk.objetivo[-1], k, mk))
        _, k0, m0 = max(cand, key=lambda t: t[0])
        m, _ = mz._em(d, m0.pi, m0.mu, m0.P, m0.P0, pt, max_iter, tol)
        if verbose:
            print(f"    K={nivel}: partiendo el tipo {k0 + 1} -> J={m.objetivo[-1]:.1f}", flush=True)
    m, _ = mz._em(d, m.pi, m.mu, m.P, m.P.copy(), pr, max_iter, tol)
    o = np.argsort([marginal(m, ns).inicio(k)["E_T"] for k in range(m.K)])
    return mz.Mezcla(m.pi[o], m.mu[o], m.P[o], m.lam, m.a0, m.objetivo, m.diagnostico, m.P0[o])


def reproducibilidad(d: mz.DatosPosesion, K: int, lam: float, a0: float, semillas: list[int], max_iter: int,
                     tol: float, n_corto: int = 25, lam0: float | None = None, ns: int | None = None) -> dict:
    """El criterio de `mezcla.reproducibilidad` (ADR-v2-30, 35) con las tarjetas de la marginal."""
    ns = ns or d.n_states // M
    pr = mz.prior(d, lam, a0, True, lam0)
    ms = [ajustar(d, K, lam, a0, max_iter, tol, s, n_corto, lam0, pr, ns) for s in semillas]
    J = np.array([m.objetivo[-1] for m in ms])
    mejor = ms[int(J.argmax())]
    R0 = mz.responsabilidades(mejor, d)
    t0 = mz._tarjetas(marginal(mejor, ns))
    filas = []
    for s_, m in zip(semillas, ms):
        R = mz.responsabilidades(m, d)
        j, acuerdo = mz._emparejar(R0.argmax(1), R.argmax(1), K)
        t = mz._tarjetas(marginal(m, ns))[j]
        filas.append({"semilla": s_, "delta_J": float(J.max() - m.objetivo[-1]), "acuerdo": float(acuerdo),
                      "acuerdo_suave": mz.acuerdo_suave(R0, R[:, j]),
                      "max_dif_pi": float(np.abs(t[:, 0] - t0[:, 0]).max()),
                      "max_dif_ET_rel": float((np.abs(t[:, 1] - t0[:, 1]) / t0[:, 1]).max())})
    rango = float(J.max() - J.min())
    suave = float(min(f["acuerdo_suave"] for f in filas))
    return {"K": K, "semillas": filas, "rango_J": rango, "rango_J_por_secuencia": rango / d.n,
            "acuerdo_suave_minimo": suave, "acuerdo_minimo": float(min(f["acuerdo"] for f in filas)),
            "pi_minimo": float(mejor.pi.min()),
            "reproducible": bool(rango / d.n <= mz.TOL_J_POR_SECUENCIA and suave >= 0.95
                                 and mejor.pi.min() >= mz.PI_MINIMO), "mejor": mejor}


# ---------------------------------------------------------------- predicción secuencial en la escala común
def pasos(trans: pl.DataFrame) -> dict:
    """Arreglos por transición, en orden, con el índice de su secuencia y su posición en ella."""
    df = _orden(trans)
    nuevo = df["_nuevo"].to_numpy()
    pid = np.cumsum(nuevo) - 1
    starts = np.flatnonzero(nuevo)
    pos = np.arange(len(pid)) - starts[pid]
    return {"seq": pid, "pos": pos, "fr": df["from_state"].to_numpy().astype(np.int64),
            "to": df["to_state"].to_numpy().astype(np.int64), "m": marcas(df),
            "match": df["match_id"].to_numpy(), "n_seq": len(starts), "inicio": df["from_state"].to_numpy()[starts]}


def puntaje(m: mz.Mezcla, pz: dict, nt: int, ns: int, area: np.ndarray, con_marca: bool) -> np.ndarray:
    """Log-puntaje (Prop. 5.1) de cada transición con filtrado de la familia: el peso w_k(t) usa solo el pasado
    (con las marcas pasadas si `con_marca`); la zona siguiente se predice con la marginal. Devuelve un arreglo
    alineado con `pz` (una entrada por transición)."""
    K = m.K
    if con_marca:
        Pj, P0j = m.P.reshape(K, nt, M, ns), m.P0.reshape(K, nt, M, ns)
        Pm, P0m = Pj.sum(2), P0j.sum(2)
    else:
        Pm, P0m = m.P, m.P0
    logw = np.log(m.pi)[None] + np.log(np.maximum(m.mu[:, pz["inicio"]], 1e-300)).T     # (n_seq, K)
    out = np.empty(len(pz["seq"]))
    orden = np.argsort(pz["pos"], kind="stable")
    cortes = np.searchsorted(pz["pos"][orden], np.arange(pz["pos"].max() + 2))
    pen = np.zeros(ns)                                                                 # − log a_j solo transitorios
    pen[:nt] = np.log(np.maximum(area, 1e-300))
    for t in range(len(cortes) - 1):
        idx = orden[cortes[t]:cortes[t + 1]]
        if len(idx) == 0:
            continue
        s, i, j = pz["seq"][idx], pz["fr"][idx], pz["to"][idx]
        Pmt = P0m if t == 0 else Pm
        w = logw[s] - logsumexp(logw[s], axis=1, keepdims=True)
        lp = np.log(np.maximum(Pmt[:, i, j].T, 1e-300))                                  # (n, K)
        out[idx] = logsumexp(w + lp, axis=1) - pen[j]
        if con_marca:
            Pjt = P0j if t == 0 else Pj
            logw[s] += np.log(np.maximum(Pjt[:, i, pz["m"][idx], j].T, 1e-300))
        else:
            logw[s] += lp
    return out


def ganancia(dif: np.ndarray, match: np.ndarray) -> dict:
    """Media por acción de la diferencia de puntajes y su EE por conglomerados (partido), razón de sumas."""
    u, g = np.unique(match, return_inverse=True)
    num = np.bincount(g, weights=dif)
    den = np.bincount(g).astype(float)
    th = num.sum() / den.sum()
    G = len(u)
    se = np.sqrt(G / (G - 1) * ((num - th * den) ** 2).sum()) / den.sum() if G > 1 else float("nan")
    return {"nats_por_accion": float(th), "ee": float(se), "acciones": int(den.sum()), "partidos": int(G)}
