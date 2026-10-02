"""
EXPERIMENTO (ADR-v2-52, no adoptado): ¿el técnico solo mueve π_k, o también P^k?

El modelo de la fase 2 (04 §7) deja que un técnico cambie los PESOS π_k(x) de las tres
familias, pero supone que cada familia, hecha por él, es la MISMA cadena P^k que hace la liga
(hace «Ataque elaborado» igual que todos, solo que más seguido). Aquí se prueba:

    H0:  P^k_foco = P^k_liga        (por familia k; filas de las acciones siguientes)
    H0': P0^k_foco = P0^k_liga      (el primer toque, aparte)

PRUEBA DE SCORE (no se reajusta nada: se evalúa en θ = 0)
---------------------------------------------------------
Se parametriza la fila i de la familia k del foco como P_ij(θ) ∝ P^k_ij · exp(θ_ij), θ_i,ref = 0.
Con las responsabilidades r_sk de la secuencia s (la mezcla de la liga ya ajustada), el score
en θ = 0 de la secuencia es

    u_s(i, j) = r_sk · ( c_s(i, j) − n_s(i) · P^k_ij ),        n_s(i) = Σ_j c_s(i, j),

y el del partido g es U_g = Σ_{s ∈ g, f_s = 1} u_s. Bajo H0, E[U_g] = 0, así que la varianza es
la de conglomerados SIN centrar, V̂ = Σ_g U_g U_gᵀ (partidos independientes, secuencias de un
partido no). Por fila i (bloque de d_i = J_i − 1 destinos):

    T_i = U_iᵀ V̂_i⁻¹ U_i ,      F_i = T_i · (G − d_i) / ((G − 1) d_i)  ~  F(d_i, G − d_i)

(corrección de muestra pequeña de conglomerados). Las filas de una misma cadena de Markov tienen
scores no correlacionados (diferencias de martingala) y se combinan con Fisher por familia.

DETALLES QUE IMPORTAN
---------------------
* P^k_liga se recalcula con las secuencias de partidos SIN el foco (conteos ponderados por r_sk,
  encogidos hacia la P^k de la mezcla con `a` pseudo-conteos), para que el foco no entre en su
  propia nula. Es la misma convención de «liga sin el foco» de toda la fase 2.
* Filas con menos de `n_min` visitas ponderadas del foco no se prueban. Los destinos con conteo
  esperado < 5 se funden en «otros».
* r_sk es GENERADO por el EM de la etapa 1 (ver `regresor_generado.py`): esta prueba lo trata como
  dato, igual que H1–H8. Es un límite que se declara, no se arregla aquí.
* Con ruido de plantel un Wald «rechaza» a casi cualquier técnico. Por eso se reporta también
  cómo queda el foco frente a los DEMÁS técnicos-club (la nula empírica: ¿se desvía más que lo
  que se desvía un técnico cualquiera?) y la distancia (TV ponderada) y su efecto en E[T].
"""
from __future__ import annotations

import numpy as np
import polars as pl
import scipy.sparse as sp
from scipy import stats

from .absorbing import Cadena


def _conteos_por_partido(S: sp.csr_matrix, w: np.ndarray, gid: np.ndarray, n_g: int) -> np.ndarray:
    """(n_g, celdas) conteos de transición ponderados por w y sumados por partido."""
    M = sp.csr_matrix((w, (gid, np.arange(len(gid)))), shape=(n_g, len(gid)))
    return np.asarray((M @ S).todense())


def p_liga(S: sp.csr_matrix, r_k: np.ndarray, usar: np.ndarray, P_prior: np.ndarray, a: float,
           nt: int, ns: int) -> np.ndarray:
    """P^k de la liga SIN el foco: conteos ponderados por r_sk, encogidos hacia `P_prior`."""
    C = np.asarray(S[usar].T @ r_k[usar]).ravel().reshape(nt, ns)
    return (C + a * P_prior) / (C.sum(1, keepdims=True) + a)


def prueba_familia(S: sp.csr_matrix, r_k: np.ndarray, match: np.ndarray, foco: np.ndarray, P: np.ndarray,
                   nt: int, ns: int, n_min: float = 30.0, e_min: float = 5.0,
                   liga: np.ndarray | None = None) -> dict:
    """Score por fila de la familia k. `foco`: secuencias de ATAQUE del foco; `P`: la nula (nt, ns).

    `liga`: las secuencias con que se ESTIMÓ `P`. Si se da, la varianza incluye ese error de estimación
    (delta: Û_f(P̂) ≈ U_f(P) − n_f (P̂ − P), con P̂ − P ≈ Σ_liga U_g / n_liga), es decir V = V_f + c² V_liga con
    c = n_f / n_liga por fila. Sin esto el estadístico es anticonservador (visto en datos sembrados: 22 %
    de rechazos al 5 % bajo H0 con 70 partidos del foco contra 250 de la liga)."""
    idx = np.flatnonzero(foco)
    u, gid = np.unique(match[idx], return_inverse=True)
    G = len(u)
    A = _conteos_por_partido(S[idx], r_k[idx], gid, G).reshape(G, nt, ns)      # conteos ponderados
    N = A.sum(2)                                                                 # (G, nt) visitas
    U = A - N[:, :, None] * P[None]                                              # score por partido
    UL = NL = None
    if liga is not None:
        il = np.flatnonzero(liga)
        ul, gl = np.unique(match[il], return_inverse=True)
        AL = _conteos_por_partido(S[il], r_k[il], gl, len(ul)).reshape(len(ul), nt, ns)
        NL = AL.sum(2)
        UL = AL - NL[:, :, None] * P[None]
    filas = []
    for i in range(nt):
        n_i = float(N[:, i].sum())
        if n_i < n_min or G < 8:
            continue
        E = n_i * P[i]
        orden = np.argsort(-E)
        grupos, otros = [], []
        for j in orden:
            (grupos if E[j] >= e_min else otros).append(j)
        if otros:
            if sum(E[j] for j in otros) >= e_min or not grupos:
                grupos.append(np.array(otros))
            else:
                grupos[0] = np.append(grupos[0], otros)
        grupos = [np.atleast_1d(g) for g in grupos]
        if len(grupos) < 2:
            continue
        Ug = np.stack([U[:, i, g].sum(1) for g in grupos[:-1]], axis=1)         # (G, d): destino de ref = último
        d = Ug.shape[1]
        tot = Ug.sum(0)
        V = Ug.T @ Ug
        if UL is not None and NL[:, i].sum() > 0:
            Ul = np.stack([UL[:, i, g].sum(1) for g in grupos[:-1]], axis=1)
            V = V + (n_i / NL[:, i].sum()) ** 2 * (Ul.T @ Ul)
        w = np.linalg.eigvalsh(V)
        if w.min() <= 1e-10 * max(w.max(), 1e-300):
            Vi = np.linalg.pinv(V, rcond=1e-10)
            d_ef = int(np.sum(w > 1e-10 * w.max()))
        else:
            Vi, d_ef = np.linalg.inv(V), d
        if d_ef == 0 or G - d_ef <= 0:
            continue
        T = float(tot @ Vi @ tot)
        F = T * (G - d_ef) / ((G - 1) * d_ef)
        # desviación observada (en proporción de la fila): TV ponderada contra la nula
        obs = A[:, i, :].sum(0) / max(n_i, 1e-300)
        filas.append({"estado": i, "visitas": n_i, "d": d_ef, "T": T, "F": float(F),
                      "p": float(stats.f.sf(F, d_ef, G - d_ef)), "tv": float(0.5 * np.abs(obs - P[i]).sum())})
    if not filas:
        return {"filas": [], "G": G, "T": 0.0, "df": 0, "p_fisher": float("nan"), "p_min_bonf": float("nan"),
                "tv": float("nan"), "exceso": float("nan")}
    p = np.array([f["p"] for f in filas])
    p_f = float(stats.chi2.sf(-2 * np.sum(np.log(np.maximum(p, 1e-300))), 2 * len(p)))
    peso = np.array([f["visitas"] for f in filas])
    return {"filas": filas, "G": G, "T": float(sum(f["T"] for f in filas)), "df": int(sum(f["d"] for f in filas)),
            "p_fisher": p_f, "p_min_bonf": float(min(1.0, p.min() * len(p))),
            "tv": float(np.average([f["tv"] for f in filas], weights=peso)),
            "exceso": float(sum(f["T"] for f in filas) / sum(f["d"] for f in filas))}


def efecto_en_cadena(S: sp.csr_matrix, r_k: np.ndarray, foco: np.ndarray, P_nula: np.ndarray, mu_k: np.ndarray,
                     nt: int, ns: int, a: float = 20.0) -> dict:
    """¿Cuánto importaría esta diferencia? E[T] y P(absorción) de la cadena de la liga contra la del foco
    (P del foco = conteos ponderados del foco encogidos con `a` pseudo-conteos hacia la nula)."""
    C = np.asarray(S[foco].T @ r_k[foco]).ravel().reshape(nt, ns)
    Pf = (C + a * P_nula) / (C.sum(1, keepdims=True) + a)
    out = {}
    for nom, P in (("liga", P_nula), ("foco", Pf)):
        try:
            cad = Cadena(P, nt)
            B = cad.absorcion()                    # (nt, 4): GOAL, SHOT_NOGOAL, LOSS, OUT
            out[nom] = {"E_T": float(mu_k @ cad.largo_esperado()), "P_remate": float(mu_k @ (B[:, 0] + B[:, 1]))}
        except Exception as e:                       # rho(Q) ≥ 1 por ruido en la fila
            out[nom] = {"E_T": float("nan"), "error": str(e)[:80]}
    out["dif_E_T"] = out["foco"]["E_T"] - out["liga"]["E_T"]
    out["dif_P_remate"] = out["foco"].get("P_remate", float("nan")) - out["liga"].get("P_remate", float("nan"))
    return out


def correr(S1: sp.csr_matrix, S0: sp.csr_matrix | None, r: np.ndarray, match: np.ndarray, es_foco: np.ndarray,
           partido_foco: np.ndarray, P: np.ndarray, P0: np.ndarray | None, mu: np.ndarray, nt: int, ns: int,
           a: float = 10.0, n_min: float = 30.0) -> dict:
    """Todas las familias, para P (acciones siguientes) y, si hay, P0 (primer toque)."""
    K = r.shape[1]
    liga = ~partido_foco
    res = {"familias": [], "K": K}
    for k in range(K):
        fila = {"familia": k + 1}
        for nombre, S, Pk in (("P", S1, P[k]), ("P0", S0, None if P0 is None else P0[k])):
            if S is None or Pk is None:
                continue
            Pl = p_liga(S, r[:, k], liga, Pk, a, nt, ns)
            pr = prueba_familia(S, r[:, k], match, es_foco, Pl, nt, ns, n_min, liga=liga)
            if nombre == "P":
                pr["efecto"] = efecto_en_cadena(S, r[:, k], es_foco, Pl, mu[k], nt, ns)
            fila[nombre] = pr
        res["familias"].append(fila)
    return res
