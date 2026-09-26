"""
Cadena absorbente: los objetos cerrados que se reportan.

    P = [[Q, R], [0, I]],   N = (I - Q)^{-1} = sum_k Q^k   (rho(Q) < 1)
    t = N 1                 acciones esperadas hasta que la posesion termina
    B = N R                 probabilidad de terminar en cada absorbente
    V = N c                 valor de zona (Bellman: V = Q V + c)

VALOR DE ZONA (ADR-v2-05)
-------------------------
c_i = xG esperado que se genera AL REMATAR desde i, por visita a i:
      c_i = (suma de xG de los remates que salen de i) / (acciones desde i).
Asi V_i = xG esperado que termina produciendo una posesion que pasa por i.
Gol y remate fallado se tratan igual (su xG): usar 1 para el gol mezcla
resultado con expectativa y mete varianza sin informacion.

DISTRIBUCION DE VISITAS vs ESTACIONARIA (ADR-v2-07)
---------------------------------------------------
La cadena absorbente solo tiene estacionarias concentradas en los absorbentes.
La cadena REINICIADA (cada absorcion arranca otra posesion con alpha) si tiene
estacionaria unica, y por el argumento regenerativo es  pi ∝ alpha^T N.
`visitas(alpha)` devuelve exactamente ese objeto, normalizado.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.linalg as sla


@dataclass
class Cadena:
    P: np.ndarray          # (n_transient, n_states), filas suman 1
    n_transient: int

    @property
    def Q(self) -> np.ndarray:
        return self.P[:, : self.n_transient]

    @property
    def R(self) -> np.ndarray:
        return self.P[:, self.n_transient:]

    def check(self) -> dict:
        rho = float(np.max(np.abs(np.linalg.eigvals(self.Q))))
        filas = float(np.max(np.abs(self.P.sum(axis=1) - 1.0)))
        if rho >= 1.0:
            raise ValueError(f"rho(Q) = {rho:.6f} >= 1: hay posesiones que no terminan")
        return {"rho_Q": rho, "max_err_filas": filas}

    def _lu(self):
        if not hasattr(self, "_lu_cache"):
            I = np.eye(self.n_transient)
            self._lu_cache = sla.lu_factor(I - self.Q)
        return self._lu_cache

    def fundamental(self) -> np.ndarray:
        """N resolviendo (I-Q) N = I. No se invierte explicitamente."""
        return sla.lu_solve(self._lu(), np.eye(self.n_transient))

    def largo_esperado(self) -> np.ndarray:
        return sla.lu_solve(self._lu(), np.ones(self.n_transient))

    def absorcion(self) -> np.ndarray:
        return sla.lu_solve(self._lu(), self.R)

    def valor(self, c: np.ndarray) -> np.ndarray:
        return sla.lu_solve(self._lu(), np.asarray(c, dtype=float))

    def visitas(self, alpha: np.ndarray) -> np.ndarray:
        """alpha^T N, normalizado: estacionaria de la cadena reiniciada."""
        v = sla.lu_solve(self._lu(), np.asarray(alpha, dtype=float), trans=1)
        return v / max(v.sum(), 1e-300)

    def supervivencia(self, alpha: np.ndarray, kmax: int) -> np.ndarray:
        """S[k] = P(T > k) = alpha^T Q^k 1, k = 0..kmax (phase-type discreta)."""
        S = np.empty(kmax + 1)
        v = np.asarray(alpha, dtype=float).copy()
        Q = self.Q
        for k in range(kmax + 1):
            S[k] = v.sum()
            v = v @ Q
        return np.clip(S, 0.0, 1.0)


def recompensa_xg(C_filas: np.ndarray, xg_por_estado: np.ndarray) -> np.ndarray:
    """c_i = xG total desde i / acciones desde i (0 si no hay acciones)."""
    n = np.asarray(C_filas, dtype=float)
    return np.where(n > 0, np.asarray(xg_por_estado, dtype=float) / np.maximum(n, 1e-300), 0.0)
