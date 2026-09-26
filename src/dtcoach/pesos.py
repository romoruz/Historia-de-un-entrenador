"""
Fase 2 -- Pesos de la mezcla segun el contexto, con la desviacion del tecnico.

MODELO: logit multinomial FRACCIONAL (Papke y Wooldridge, 1996)
---------------------------------------------------------------
La "respuesta" de cada secuencia no es una etiqueta, es el vector de
responsabilidades r_s ∈ simplex (cuanto pertenece a cada familia). Se modela

    E[r_sk | x_s] = pi_k(x_s) = exp(x_s' b_k) / sum_l exp(x_s' b_l),   b_ref = 0

y se estima maximizando la cuasi-verosimilitud  sum_s sum_k r_sk log pi_k(x_s).
Es consistente para b aunque r no sea multinomial, siempre que la media este
bien especificada. La varianza se estima con el SANDWICH agrupado por partido,

    V = H^-1 (sum_g u_g u_g') H^-1 · G/(G-1),

porque las secuencias de un mismo partido no son independientes (ADR-v2-04) y
porque r no es multinomial (el sandwich no supone la varianza del modelo).
Limitacion declarada: la mezcla (que produce r) se trata como fija; su
incertidumbre es pequeña frente a la de b (461 mil secuencias contra ~180
partidos del foco), pero no es cero.

EFECTOS EN LA CANCHA (no se reportan coeficientes)
--------------------------------------------------
Efecto promedio sobre las secuencias del foco:
    Δpi_k = mean_{s ∈ foco} [ pi_k(x_s, f=1) - pi_k(x_s, f=0) ]
"con sus mismas situaciones de juego, cuanto mas usa cada familia que la liga".
Intervalos por simulacion de b ~ N(b_hat, V) (metodo de Krinsky-Robb).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy import stats
from scipy.optimize import minimize
from scipy.special import logsumexp


@dataclass
class ModeloPesos:
    nombres: list[str]
    theta: np.ndarray          # (p*(K-1),) libres, orden [j*(K-1) + a]
    V: np.ndarray              # (p*(K-1), p*(K-1)) sandwich por partido
    K: int
    ref: int
    n: int
    n_grupos: int
    cuasi_loglik: float
    convergio: bool

    @property
    def p(self) -> int:
        return len(self.nombres)

    @property
    def libres(self) -> list[int]:
        return [k for k in range(self.K) if k != self.ref]

    def B(self, theta: np.ndarray | None = None) -> np.ndarray:
        th = self.theta if theta is None else theta
        B = np.zeros((self.p, self.K))
        B[:, self.libres] = th.reshape(self.p, self.K - 1)
        return B

    def indices(self, nombre: str) -> list[int]:
        j = self.nombres.index(nombre)
        return [j * (self.K - 1) + a for a in range(self.K - 1)]

    def predecir(self, X: np.ndarray, theta: np.ndarray | None = None) -> np.ndarray:
        Z = X @ self.B(theta)
        return np.exp(Z - logsumexp(Z, axis=1, keepdims=True))

    def wald(self, nombres: list[str]) -> dict:
        """H0: todos los coeficientes (de todas las familias) de `nombres` son 0.

        Si una columna se eliminó por colineal (no estimable con estos datos),
        se dice explícitamente en vez de inventar un p-valor.
        """
        presentes = [n_ for n_ in nombres if n_ in self.nombres]
        if not presentes:
            return {"coeficientes": nombres, "W": float("nan"), "gl": 0, "p": 1.0,
                    "nota": "no estimable: columnas colineales o sin variación"}
        idx = [i for n_ in presentes for i in self.indices(n_)]
        b = self.theta[idx]
        Vs = self.V[np.ix_(idx, idx)]
        W = float(b @ np.linalg.pinv(Vs) @ b)
        gl = int(np.linalg.matrix_rank(Vs))
        out = {"coeficientes": presentes, "W": W, "gl": gl, "p": float(stats.chi2.sf(W, max(gl, 1)))}
        if len(presentes) < len(nombres):
            out["nota"] = f"no estimables: {sorted(set(nombres) - set(presentes))}"
        return out

    def simular(self, n_sim: int, seed: int) -> np.ndarray:
        """θ ~ N(θ̂, V). Raíz por eigendescomposición: V es PSD pero puede ser singular."""
        rng = np.random.default_rng(seed)
        w, Q = np.linalg.eigh((self.V + self.V.T) / 2)
        L = Q * np.sqrt(np.clip(w, 0, None))
        return self.theta[None] + rng.standard_normal((n_sim, len(self.theta))) @ L.T


def _agrupar(codigos: np.ndarray, n_grupos: int, M: np.ndarray) -> np.ndarray:
    A = sp.csr_matrix((np.ones(len(codigos)), (codigos, np.arange(len(codigos)))),
                      shape=(n_grupos, len(codigos)))
    return np.asarray(A @ M)


def ajustar_pesos(X: np.ndarray, R: np.ndarray, grupos: np.ndarray, nombres: list[str],
                  ref: int = 1, ridge: float = 1e-6, max_iter: int = 2000) -> ModeloPesos:
    """`ref` por defecto = familia 2 (Circulación estéril): los coeficientes se leen
    como "más o menos que circulación estéril". Los efectos reportados no dependen
    de la referencia."""
    n, p = X.shape
    K = R.shape[1]
    libres = [k for k in range(K) if k != ref]
    if not np.allclose(R.sum(1), 1.0, atol=1e-6):
        raise ValueError("Las responsabilidades deben sumar 1 por secuencia.")

    def f(theta):
        B = np.zeros((p, K))
        B[:, libres] = theta.reshape(p, K - 1)
        Z = X @ B
        lse = logsumexp(Z, axis=1)
        P = np.exp(Z - lse[:, None])
        ll = float((R * Z).sum() - lse.sum())
        G = X.T @ (R - P)
        obj = -ll / n + 0.5 * ridge * theta @ theta
        grad = -G[:, libres].ravel() / n + ridge * theta
        return obj, grad

    res = minimize(f, np.zeros(p * (K - 1)), jac=True, method="L-BFGS-B",
                   options={"maxiter": max_iter, "gtol": 1e-10, "ftol": 1e-14})
    theta = res.x
    B = np.zeros((p, K))
    B[:, libres] = theta.reshape(p, K - 1)
    Z = X @ B
    P = np.exp(Z - logsumexp(Z, axis=1, keepdims=True))

    # Hessiana (del negativo de la cuasi-loglik) y "carne" agrupada por partido
    Km = K - 1
    H = np.zeros((p, Km, p, Km))
    for ia, a in enumerate(libres):
        for ib, b in enumerate(libres):
            w = P[:, a] * ((a == b) - P[:, b])
            H[:, ia, :, ib] = X.T @ (X * w[:, None])
    H = H.reshape(p * Km, p * Km) + ridge * n * np.eye(p * Km)
    U = (R - P)[:, libres]                                   # (n, K-1)
    codigos, _ = _factorizar(grupos)
    G = int(codigos.max()) + 1
    S = np.stack([_agrupar(codigos, G, X * U[:, ia][:, None]) for ia in range(Km)], axis=2)
    S = S.reshape(G, p * Km)                                  # orden [j*(K-1)+a]
    Hi = np.linalg.inv(H)
    V = Hi @ (S.T @ S) @ Hi * G / max(G - 1, 1)
    ll = float((R * np.log(np.maximum(P, 1e-300))).sum())
    return ModeloPesos(nombres, theta, V, K, ref, n, G, ll, bool(res.success))


def columnas_estimables(X: np.ndarray, nombres: list[str], tol: float = 1e-8) -> np.ndarray:
    """Máscara de columnas linealmente independientes (QR con pivoteo).

    Con datos reales casi siempre son todas; con pocos partidos o un foco que
    nunca jugó de local en cierta temporada, alguna interacción es colineal y
    su coeficiente NO es estimable: se quita y se reporta, en vez de dejar que
    la matriz sandwich salga singular.
    """
    from scipy.linalg import qr
    Xs = X / np.maximum(np.abs(X).max(0), 1e-12)
    _, Rq, piv = qr(Xs, mode="economic", pivoting=True)
    d = np.abs(np.diag(Rq))
    rango = int((d > tol * d.max()).sum())
    keep = np.zeros(X.shape[1], dtype=bool)
    keep[piv[:rango]] = True
    return keep


def _factorizar(x: np.ndarray):
    uniq, cod = np.unique(np.asarray(x), return_inverse=True)
    return cod, uniq


# ----------------------------------------------------------------------
# Efectos en probabilidad, con intervalos por simulacion
# ----------------------------------------------------------------------
def efecto_promedio(m: ModeloPesos, X1: np.ndarray, X0: np.ndarray, sims: np.ndarray,
                    nivel: float = 0.95) -> dict:
    """Δpi_k = mean[pi_k(X1) - pi_k(X0)] con IC y Wald conjunto sobre K-1 familias."""
    est = (m.predecir(X1) - m.predecir(X0)).mean(0)
    draws = np.stack([(m.predecir(X1, th) - m.predecir(X0, th)).mean(0) for th in sims])
    a = (1 - nivel) / 2
    lo, hi = np.quantile(draws, a, axis=0), np.quantile(draws, 1 - a, axis=0)
    C = np.atleast_2d(np.cov(draws[:, :-1].T))          # K-1 libres (suman 0)
    d = est[:-1]
    W = float(d @ np.linalg.pinv(C) @ d)
    return {"delta_pi": est.tolist(), "lo": lo.tolist(), "hi": hi.tolist(),
            "W": W, "gl": m.K - 1, "p": float(stats.chi2.sf(W, m.K - 1))}


def pi_en(m: ModeloPesos, X: np.ndarray, sims: np.ndarray, nivel: float = 0.95) -> dict:
    """pi promedio sobre las filas de X, con IC."""
    est = m.predecir(X).mean(0)
    draws = np.stack([m.predecir(X, th).mean(0) for th in sims])
    a = (1 - nivel) / 2
    return {"pi": est.tolist(), "lo": np.quantile(draws, a, 0).tolist(),
            "hi": np.quantile(draws, 1 - a, 0).tolist(), "draws": draws}
