"""
Capa 1 -- Mezcla de cadenas de Markov: el VOCABULARIO de secuencias de la liga.

MODELO (v3, ADR-v2-29: paso inicial propio)
-------------------------------------------
Cada secuencia s tiene un tipo oculto Z_s en {1..K}. Dado el tipo:

    Pr(s | k) = mu^k[z_1] · P0^k[z_1, z_2] · prod_{t>=2} P^k[z_t, z_{t+1}]

mu^k : distribucion de inicio del tipo k
P0^k : transicion de la PRIMERA accion de la secuencia
P^k  : transicion de las acciones siguientes
pi_k : proporcion de secuencias de tipo k (NO es una estacionaria; ADR-v2-07)

Por que P0: con una sola P, la mezcla reproducia la cola de la duracion pero
sobreestimaba las secuencias de una accion (P(T>1): 0.821 modelado contra 0.859
empirico). La primera accion de una secuencia (tras recuperar, sacar o reponer)
no se comporta como una accion cualquiera desde la misma zona. P0 modela ese
"primer toque" sin agrandar el espacio de estados. Con paso_inicial=False,
P0 = P y se recupera exactamente el modelo anterior.

La dinamica tras el primer paso sigue siendo Markov (P), asi que las formas
cerradas se conservan:
    t   = N 1,  B = N R,  V = N c            (con N = (I - Q)^-1 de P)
    E[T]      = mu·(1 + Q0 t)
    P(absorbe)= mu·(R0 + Q0 B)
    xG/sec    = mu·(c0 + Q0 V)
    S(t)      = (mu Q0) Q^{t-1} 1,  t >= 1   (phase-type)

ESTIMACION: EM-MAP con encogimiento. P^k se encoge hacia la cadena de la liga
(acciones siguientes) y P0^k hacia la cadena de primeros pasos de la liga, que
a su vez se encoge hacia la general (filas de primer paso con poco soporte).
El objetivo J (log-verosimilitud + log-priors Dirichlet) es monotono en el EM.

INICIALIZACION: escalera (ADR-v2-17). K por reproducibilidad (ADR-v2-18/19).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl
import scipy.sparse as sp
from scipy.cluster.vq import kmeans2
from scipy.optimize import linear_sum_assignment
from scipy.special import logsumexp

from .absorbing import Cadena, recompensa_xg
from .estimate import match_folds, shrink
from .grid import StateSpace

_EPS = 1e-300
# ADR-v2-35: el umbral de rango de J (50) escalado al tamaño de muestra en que se fijó
# (461,454 secuencias). Así el criterio no depende de la escala de J, que crece con la malla.
TOL_J_POR_SECUENCIA = 50.0 / 461_454
# Un tipo con menos del 1 % de las secuencias no es una familia: sin este mínimo, un
# componente VACÍO hace "reproducible" a K+1 de forma trivial (visto en datos sintéticos).
PI_MINIMO = 0.01

META_COLS = (
    "seq_uid", "seq_n", "poss_uid", "match_id", "team", "coach", "coach_faced", "match_date",
    "play_pattern", "phase", "score_state", "period", "minute", "local", "rival",
)


# ======================================================================
# Datos
# ======================================================================
@dataclass
class DatosPosesion:
    S: sp.csr_matrix          # (n_sec, nt*ns) conteos de TODAS las transiciones
    X: sp.csr_matrix          # (n_sec, nt) xG de remates por estado de origen
    inicio: np.ndarray        # (n_sec,) estado inicial
    largo: np.ndarray         # (n_sec,) transiciones hasta absorcion
    meta: pl.DataFrame
    n_transient: int
    n_states: int
    nx: int
    ny: int
    n_phases: int
    S0: sp.csr_matrix | None = None   # solo la PRIMERA transicion de cada secuencia
    X0: sp.csr_matrix | None = None   # xG de la primera transicion
    # valor de la reanudacion a balon parado (ADR-v2-72) por estado de origen: SOLO entra en c para V = N c, nunca en
    # el xG por secuencia (H7-H8). None si las transiciones no traen `valor_reanudacion`.
    XV: sp.csr_matrix | None = None
    XV0: sp.csr_matrix | None = None

    @property
    def n(self) -> int:
        return self.S.shape[0]

    @property
    def S1(self) -> sp.csr_matrix:
        # S − S0 se pedía en CADA iteración del EM (dos veces: verosimilitud y paso M); es constante. Se calcula una
        # vez por instancia (ADR-v2-64); `sub()` crea una instancia nueva, así que el caché no se comparte.
        s1 = self.__dict__.get("_S1")
        if s1 is None:
            s1 = self.__dict__["_S1"] = self.S - self.S0
        return s1

    @property
    def X1(self) -> sp.csr_matrix:
        return self.X - self.X0

    def Xc(self, primera: bool | None = None) -> sp.csr_matrix:
        """Lo que entra en c para V = N c: xG de los remates + valor de la reanudacion (ADR-v2-72). `primera`: None =
        todas las transiciones, True = solo la primera, False = las siguientes."""
        X = self.X if primera is None else (self.X0 if primera else self.X1)
        if self.XV is None:
            return X
        XV = self.XV if primera is None else (self.XV0 if primera else self.XV - self.XV0)
        return X + XV

    @classmethod
    def desde_transiciones(cls, trans: pl.DataFrame, space: StateSpace) -> "DatosPosesion":
        """Una fila por SECUENCIA (`seq_uid`, ADR-v2-14) si existe; si no, por posesion."""
        uid = "seq_uid" if "seq_uid" in trans.columns else "poss_uid"
        df = trans.sort([uid, "event_index"]).with_columns(
            (pl.col(uid) != pl.col(uid).shift(1)).fill_null(True).alias("_nuevo")
        )
        nuevo = df["_nuevo"].to_numpy()
        pid = np.cumsum(nuevo) - 1
        starts = np.flatnonzero(nuevo)
        n = len(starts)
        nt, ns = space.n_transient, space.n_states
        fr = df["from_state"].to_numpy().astype(np.int64)
        to = df["to_state"].to_numpy().astype(np.int64)
        if fr.max(initial=0) >= nt or to.max(initial=0) >= ns:
            raise ValueError("Estados fuera del espacio: ¿cambió la malla sin rehacer fase0?")
        celda = fr * ns + to
        S = sp.csr_matrix((np.ones(len(fr)), (pid, celda)), shape=(n, nt * ns))
        S.sum_duplicates()
        S0 = sp.csr_matrix((np.ones(n), (np.arange(n), celda[starts])), shape=(n, nt * ns))
        xg = df["xg"].fill_null(0.0).to_numpy() if "xg" in df.columns else np.zeros(len(fr))
        X = sp.csr_matrix((xg, (pid, fr)), shape=(n, nt))
        X.sum_duplicates()
        X0 = sp.csr_matrix((xg[starts], (np.arange(n), fr[starts])), shape=(n, nt))
        largo = np.diff(np.append(starts, len(fr)))
        cols = [c for c in META_COLS if c in df.columns]
        XV = XV0 = None
        if "valor_reanudacion" in df.columns:
            vr = df["valor_reanudacion"].fill_null(0.0).to_numpy()
            XV = sp.csr_matrix((vr, (pid, fr)), shape=(n, nt))
            XV.sum_duplicates()
            XV0 = sp.csr_matrix((vr[starts], (np.arange(n), fr[starts])), shape=(n, nt))
        return cls(S, X, fr[starts], largo, df[starts].select(cols), nt, ns,
                   space.nx, space.ny, len(space.phases), S0, X0, XV, XV0)

    def sub(self, mask: np.ndarray) -> "DatosPosesion":
        idx = np.flatnonzero(mask) if mask.dtype == bool else np.asarray(mask)
        return DatosPosesion(self.S[idx], self.X[idx], self.inicio[idx], self.largo[idx], self.meta[idx],
                             self.n_transient, self.n_states, self.nx, self.ny, self.n_phases,
                             self.S0[idx], self.X0[idx], None if self.XV is None else self.XV[idx],
                             None if self.XV0 is None else self.XV0[idx])

    def columna_x(self, estados: np.ndarray) -> np.ndarray:
        zona = np.asarray(estados) // self.n_phases
        return zona // self.ny


# ======================================================================
# Modelo
# ======================================================================
@dataclass
class Mezcla:
    pi: np.ndarray            # (K,)
    mu: np.ndarray            # (K, nt)
    P: np.ndarray             # (K, nt, ns) acciones siguientes
    lam: float
    a0: float
    objetivo: list[float] = field(default_factory=list)
    diagnostico: dict = field(default_factory=dict)
    P0: np.ndarray | None = None   # (K, nt, ns) primera accion; None = atado a P

    @property
    def K(self) -> int:
        return len(self.pi)

    @property
    def paso_inicial(self) -> bool:
        return self.P0 is not None

    def P0e(self, k: int) -> np.ndarray:
        return self.P[k] if self.P0 is None else self.P0[k]

    def cadena(self, k: int) -> Cadena:
        """Cadena de las acciones SIGUIENTES del tipo k."""
        return Cadena(self.P[k], self.mu.shape[1])

    def inicio(self, k: int, c: np.ndarray | None = None, c0: np.ndarray | None = None) -> dict:
        """Cantidades desde el INICIO de una secuencia del tipo k (incluye el primer paso)."""
        nt = self.mu.shape[1]
        cad = self.cadena(k)
        P0 = self.P0e(k)
        Q0, R0 = P0[:, :nt], P0[:, nt:]
        t = cad.largo_esperado()
        B = cad.absorcion()
        mu = self.mu[k]
        out = {"E_T": float(mu @ (1 + Q0 @ t)), "B": mu @ (R0 + Q0 @ B), "t": t}
        if c is not None:
            V = cad.valor(c)
            c0 = c if c0 is None else c0
            out["xG"] = float(mu @ (c0 + Q0 @ V))
            out["V"] = V
        return out

    def guardar(self, path: Path) -> None:
        extra = {} if self.P0 is None else {"P0": self.P0}
        np.savez_compressed(path, pi=self.pi, mu=self.mu, P=self.P, lam=self.lam, a0=self.a0,
                            objetivo=np.asarray(self.objetivo), **extra)

    @classmethod
    def cargar(cls, path: Path) -> "Mezcla":
        z = np.load(path)
        return cls(z["pi"], z["mu"], z["P"], float(z["lam"]), float(z["a0"]), list(z["objetivo"]),
                   {}, z["P0"] if "P0" in z.files else None)


@dataclass
class Prior:
    Qp: np.ndarray        # destino del encogimiento de P
    Q0p: np.ndarray       # destino del encogimiento de P0
    mup: np.ndarray
    lam: float
    lam0: float
    a0: float
    paso: bool


def pooled(d: DatosPosesion, lam0: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Cadena agregada (TODAS las transiciones), encogida levemente a la uniforme.
    Se conserva por compatibilidad; `prior()` es la version con paso inicial."""
    nt, ns = d.n_transient, d.n_states
    C = np.asarray(d.S.sum(axis=0)).ravel().reshape(nt, ns)
    Q = shrink(C, np.full((nt, ns), 1.0 / ns), lam0)
    m = np.bincount(d.inicio, minlength=nt).astype(float) + lam0 / nt
    return Q, m / m.sum()


def prior(d: DatosPosesion, lam: float, a0: float = 1.0, paso: bool = True, lam0: float | None = None,
          lam_u: float = 1.0, lam_puente: float = 10.0) -> Prior:
    nt, ns = d.n_transient, d.n_states
    U = np.full((nt, ns), 1.0 / ns)
    m = np.bincount(d.inicio, minlength=nt).astype(float) + lam_u / nt
    mup = m / m.sum()
    if not paso:
        Q = shrink(np.asarray(d.S.sum(axis=0)).ravel().reshape(nt, ns), U, lam_u)
        return Prior(Q, Q, mup, lam, lam, a0, False)
    C1 = np.asarray(d.S1.sum(axis=0)).ravel().reshape(nt, ns)
    C0 = np.asarray(d.S0.sum(axis=0)).ravel().reshape(nt, ns)
    Q = shrink(C1, U, lam_u)
    Q0 = shrink(C0, Q, lam_puente)            # primer paso con poco soporte -> dinamica general
    return Prior(Q, Q0, mup, lam, lam if lam0 is None else lam0, a0, True)


def _loglik_tipos(d: DatosPosesion, m_or_P, mu=None, P0=None, paso=None) -> np.ndarray:
    """(n_sec, K) con log L_k(s). Acepta una Mezcla o (P, mu[, P0])."""
    if isinstance(m_or_P, Mezcla):
        P, mu, P0 = m_or_P.P, m_or_P.mu, m_or_P.P0
    else:
        P = m_or_P
    K = P.shape[0]
    logP = np.log(np.maximum(P.reshape(K, -1), _EPS)).T
    if P0 is None:
        L = np.asarray(d.S @ logP)
    else:
        logP0 = np.log(np.maximum(P0.reshape(K, -1), _EPS)).T
        L = np.asarray(d.S1 @ logP) + np.asarray(d.S0 @ logP0)
    return L + np.log(np.maximum(mu[:, d.inicio], _EPS)).T


def _m_step(d: DatosPosesion, r: np.ndarray, pr: Prior):
    K = r.shape[1]
    nt, ns = d.n_transient, d.n_states
    if pr.paso:
        C = np.asarray(d.S1.T @ r).T.reshape(K, nt, ns)
        C0 = np.asarray(d.S0.T @ r).T.reshape(K, nt, ns)
        P = (C + pr.lam * pr.Qp[None]) / (C.sum(2, keepdims=True) + pr.lam)
        # Prior FIJO (primeros pasos de la liga): mantiene el EM exacto y monótono.
        # Un prior jerárquico hacia la P del mismo tipo acoplaba P y P0 y rompía la
        # monotonía (hasta −5.8e-4 relativo en datos sintéticos). La identificabilidad
        # se resuelve con el arranque atado (ver `ajustar`), no con el prior.
        P0 = (C0 + pr.lam0 * pr.Q0p[None]) / (C0.sum(2, keepdims=True) + pr.lam0)
    else:
        C = np.asarray(d.S.T @ r).T.reshape(K, nt, ns)
        P0 = None
        P = (C + pr.lam * pr.Qp[None]) / (C.sum(2, keepdims=True) + pr.lam)
    M = np.stack([np.bincount(d.inicio, weights=r[:, k], minlength=nt) for k in range(K)])
    mu = (M + pr.a0 * pr.mup[None]) / (M.sum(axis=1, keepdims=True) + pr.a0)
    pi = np.clip(r.mean(axis=0), 1e-12, None)
    return pi / pi.sum(), mu, P, P0


def _lse(a: np.ndarray) -> np.ndarray:
    """logsumexp por filas, (n, 1). La MISMA aritmética que `scipy.special.logsumexp(a, axis=1, keepdims=True)` para
    entradas finitas (el máximo se saca de la suma y se cuenta con `m`: log1p(s) + log(m) + máx), sin la maquinaria
    genérica de scipy, que era ~2/3 del tiempo de cada iteración del EM (ADR-v2-64). Con K = 2 o 3 (el
    caso de la mezcla) se opera columna por columna, que es mucho más rápido que reducir un eje de 3 elementos, y se
    respeta el orden de suma de numpy (primer término + suma secuencial del resto) para dar los mismos bits (verificado
    para K = 2 y 3; con K = 4 el orden de numpy es otro y se usa la ruta genérica). Si hay algo no finito, delega en
    scipy."""
    K = a.shape[1]
    if K in (2, 3):
        c = [a[:, k] for k in range(K)]
        mx = c[0].copy()
        for x in c[1:]:
            np.maximum(mx, x, out=mx)
        if not np.isfinite(mx).all():
            return logsumexp(a, axis=1, keepdims=True)
        es = [x == mx for x in c]
        m = es[0].astype(a.dtype)
        for z in es[1:]:
            m += z
        e = [np.exp(np.where(z, -np.inf, x) - mx) for x, z in zip(c, es)]
        resto = e[1].copy()
        for x in e[2:]:
            resto += x
        t = e[0] + resto
        t = np.where(t == 0, t, t / m)
        return (np.log1p(t) + np.log(m) + mx)[:, None]
    mx = a.max(axis=1, keepdims=True)
    if not np.isfinite(mx).all():
        return logsumexp(a, axis=1, keepdims=True)
    es_max = a == mx
    m = es_max.sum(axis=1, keepdims=True).astype(a.dtype)
    e = np.exp(np.where(es_max, -np.inf, a) - mx)
    t = e.sum(axis=1, keepdims=True)
    t = np.where(t == 0, t, t / m)
    return np.log1p(t) + np.log(m) + mx


def _objetivo(Lpi, P, P0, mu, pr: Prior, lse: np.ndarray | None = None) -> float:
    J = float((_lse(Lpi) if lse is None else lse).sum())
    J += pr.lam * float((pr.Qp[None] * np.log(np.maximum(P, _EPS))).sum())
    if P0 is not None:
        J += pr.lam0 * float((pr.Q0p[None] * np.log(np.maximum(P0, _EPS))).sum())
    return J + pr.a0 * float((pr.mup[None] * np.log(np.maximum(mu, _EPS))).sum())


def rasgos(d: DatosPosesion) -> np.ndarray:
    """Rasgos baratos SOLO para inicializar con k-means (no entran al modelo)."""
    nt, ns = d.n_transient, d.n_states
    celdas = np.arange(nt * ns)
    col_from = d.columna_x(celdas // ns).astype(float)
    remate = _es_remate(nt, ns)
    media_x = np.asarray(d.S @ col_from).ravel() / np.maximum(d.largo, 1)
    datos_x = col_from[d.S.indices]
    max_x = np.maximum.reduceat(datos_x, d.S.indptr[:-1]) if d.S.nnz else np.zeros(d.n)
    remata = np.asarray(d.S @ remate).ravel()
    F = np.column_stack([np.log(d.largo), d.columna_x(d.inicio), media_x, max_x, remata])
    return (F - F.mean(0)) / np.maximum(F.std(0), 1e-9)


def _em(d, pi, mu, P, P0, pr: Prior, max_iter, tol):
    obj, convergio = [], len(pi) == 1 and not pr.paso
    for it in range(max_iter):
        Lpi = _loglik_tipos(d, P, mu, P0) + np.log(pi)[None]
        lse = _lse(Lpi)                                  # una vez: lo usan el objetivo y las responsabilidades
        obj.append(_objetivo(Lpi, P, P0, mu, pr, lse))
        r = np.exp(Lpi - lse)
        pi, mu, P, P0 = _m_step(d, r, pr)
        if len(pi) == 1 or (it > 0 and abs(obj[-1] - obj[-2]) < tol * abs(obj[-2])):
            convergio = True
            break
    Lpi = _loglik_tipos(d, P, mu, P0) + np.log(pi)[None]
    obj.append(_objetivo(Lpi, P, P0, mu, pr, _lse(Lpi)))
    return Mezcla(pi, mu, P, pr.lam, pr.a0, obj, {}, P0), convergio


def _desde_kmeans(d, K, F, rng, pr):
    if K == 1:
        r = np.ones((d.n, 1))
    else:
        _, lab = kmeans2(F, K, minit="++", seed=rng, iter=20)
        r = np.full((d.n, K), 0.1 / K)
        r[np.arange(d.n), lab] += 0.9
    return _m_step(d, r, pr)


def _partir(m: Mezcla, k: int, rng, eps: float = 0.25):
    """Duplica el tipo k perturbando su distribucion de inicio en direcciones opuestas."""
    u = rng.normal(size=m.mu.shape[1])
    a = np.clip(m.mu[k] * np.exp(eps * u), 1e-12, None)
    b = np.clip(m.mu[k] * np.exp(-eps * u), 1e-12, None)
    mu = np.vstack([np.delete(m.mu, k, 0), a / a.sum(), b / b.sum()])
    P = np.concatenate([np.delete(m.P, k, 0), m.P[k][None], m.P[k][None]])
    P0 = None if m.P0 is None else np.concatenate([np.delete(m.P0, k, 0), m.P0[k][None], m.P0[k][None]])
    pi = np.append(np.delete(m.pi, k), [m.pi[k] / 2, m.pi[k] / 2])
    return pi / pi.sum(), mu, P, P0


def ajustar(
    d: DatosPosesion, K: int, lam: float, a0: float = 1.0, n_init: int = 3,
    max_iter: int = 300, tol: float = 1e-6, seed: int = 0,
    Qp: np.ndarray | None = None, mup: np.ndarray | None = None, verbose: bool = False,
    init: str = "escalera", n_corto: int = 25, paso_inicial: bool = True, lam0: float | None = None,
    pr: Prior | None = None,
) -> Mezcla:
    """Ajusta la mezcla de K cadenas (con paso inicial propio si `paso_inicial`).

    init="escalera" (ADR-v2-17): sube de K-1 a K partiendo el tipo que mas mejora J.
    init="kmeans": `n_init` arranques desde k-means sobre rasgos (contraste).
    """
    if lam <= 0:
        raise ValueError("lam debe ser > 0 (sin encogimiento, un tipo vacio da filas 0/0)")
    if pr is None:
        if Qp is not None and mup is not None and not paso_inicial:
            pr = Prior(Qp, Qp, mup, lam, lam, a0, False)
        else:
            pr = prior(d, lam, a0, paso_inicial, lam0)
    todos: list[tuple[Mezcla, bool]] = []
    # Con paso inicial, los TIPOS se encuentran con el modelo atado (P0 = P) y después
    # se libera P0 continuando el EM (ADR-v2-29). Arrancar la escalera con P0 libre
    # desordenaba la mezcla aun sin efecto de primer toque (datos sintéticos): P0 da a
    # cada tipo otra forma de explicar secuencias cortas y la escalera cae en otro óptimo.
    pr_tipos = Prior(pr.Qp, pr.Qp, pr.mup, pr.lam, pr.lam, pr.a0, False) if pr.paso else pr
    if pr.paso:
        C = np.asarray(d.S.sum(axis=0)).ravel().reshape(d.n_transient, d.n_states)
        pr_tipos = Prior(shrink(C, np.full(C.shape, 1.0 / C.shape[1]), 1.0), None, pr.mup,
                         pr.lam, pr.lam, pr.a0, False)
        pr_tipos.Q0p = pr_tipos.Qp
    if init == "escalera":
        rng = np.random.default_rng([seed, K])
        m, conv = _em(d, *_desde_kmeans(d, 1, None, rng, pr_tipos), pr_tipos, max_iter, tol)
        for nivel in range(2, K + 1):
            cand = []
            for k in range(m.K):
                mk, _ = _em(d, *_partir(m, k, rng), pr_tipos, n_corto, tol)
                cand.append((mk.objetivo[-1], k, mk))
            _, k0, m0 = max(cand, key=lambda t: t[0])
            m, conv = _em(d, m0.pi, m0.mu, m0.P, m0.P0, pr_tipos, max_iter, tol)
            if verbose:
                print(f"    K={nivel}: partiendo el tipo {k0 + 1} -> J={m.objetivo[-1]:.1f} "
                      f"({len(m.objetivo) - 1} iteraciones)", flush=True)
        if pr.paso:
            J_atado = m.objetivo[-1]
            m, conv = _em(d, m.pi, m.mu, m.P, m.P.copy(), pr, max_iter, tol)
            if verbose:
                print(f"    paso inicial liberado: J {J_atado:.1f} (atado) -> {m.objetivo[-1]:.1f}", flush=True)
        todos, mejor = [(m, conv)], m
    elif init == "kmeans":
        F = rasgos(d) if K > 1 else None
        mejor = None
        for i in range(n_init if K > 1 else 1):
            rng = np.random.default_rng([seed, K, i])
            m, conv = _em(d, *_desde_kmeans(d, K, F, rng, pr_tipos), pr_tipos, max_iter, tol)
            if pr.paso:
                m, conv = _em(d, m.pi, m.mu, m.P, m.P.copy(), pr, max_iter, tol)
            todos.append((m, conv))
            if verbose:
                print(f"    K={K} init={i}: J={m.objetivo[-1]:.1f}", flush=True)
            if mejor is None or m.objetivo[-1] > mejor.objetivo[-1]:
                mejor = m
    else:
        raise ValueError(f"init desconocido: {init}")
    mejor.diagnostico = estabilidad(mejor, todos, d)
    mejor.diagnostico.update({"init": init, "paso_inicial": pr.paso})
    return ordenar_por_largo(mejor)


# ======================================================================
# Tarjetas, estabilidad, reproducibilidad
# ======================================================================
def _tarjetas(m: Mezcla) -> np.ndarray:
    """(K, 3): pi, E[T] y P(remate) por tipo, desde el inicio de la secuencia."""
    out = []
    for k in range(m.K):
        q = m.inicio(k)
        out.append([m.pi[k], q["E_T"], q["B"][:2].sum()])
    return np.array(out)


def _emparejar(a_ref: np.ndarray, a: np.ndarray, K: int):
    """Empareja los tipos de dos ajustes por sus asignaciones duras SOBRE LAS MISMAS SECUENCIAS, en el mismo orden
    (matriz de confusión + asignación húngara). Con secuencias distintas no hay nada que emparejar (ADR-v2-65)."""
    a_ref, a = np.asarray(a_ref), np.asarray(a)
    if a_ref.shape != a.shape:
        raise ValueError(f"_emparejar: las dos asignaciones deben ser de las MISMAS secuencias en el mismo orden; llegaron "
                         f"{a_ref.shape[0]:,} y {a.shape[0]:,} (¿datos de submuestras distintas?)")
    conf = np.zeros((K, K))
    np.add.at(conf, (a_ref, a), 1)
    i, j = linear_sum_assignment(-conf)
    return j, conf[i, j].sum() / len(a_ref)


def estabilidad(mejor: Mezcla, todos: list, d: DatosPosesion, tol_J: float = 50.0) -> dict:
    if mejor.K == 1:
        return {"arranques": [{"J": mejor.objetivo[-1], "convergio": True, "acuerdo": 1.0}],
                "reproducibilidad": 1, "todos_convergieron": True, "acuerdo_minimo": 1.0}
    R_mejor = responsabilidades(mejor, d)
    a_mejor = R_mejor.argmax(1)
    t_mejor = _tarjetas(mejor)
    J0 = mejor.objetivo[-1]
    filas = []
    for m, conv in todos:
        if m.K != mejor.K:
            continue
        R = responsabilidades(m, d)
        j, acuerdo = _emparejar(a_mejor, R.argmax(1), mejor.K)
        t = _tarjetas(m)[j]
        filas.append({"J": float(m.objetivo[-1]), "delta_J": float(J0 - m.objetivo[-1]),
                      "iteraciones": len(m.objetivo) - 1, "convergio": bool(conv), "acuerdo": float(acuerdo),
                      "acuerdo_suave": acuerdo_suave(R_mejor, R[:, j]),
                      "max_dif_pi": float(np.abs(t[:, 0] - t_mejor[:, 0]).max()),
                      "max_dif_ET_rel": float((np.abs(t[:, 1] - t_mejor[:, 1]) / t_mejor[:, 1]).max()),
                      "max_dif_Premate": float(np.abs(t[:, 2] - t_mejor[:, 2]).max())})
    otros = [f["acuerdo"] for f in filas if f["delta_J"] > 1e-9]
    return {"arranques": filas, "reproducibilidad": sum(f["delta_J"] <= tol_J for f in filas), "tol_J": tol_J,
            "acuerdo_minimo": float(min(otros)) if otros else 1.0,
            "todos_convergieron": all(f["convergio"] for f in filas)}


def ordenar_por_largo(m: Mezcla) -> Mezcla:
    """Fija el cambio de etiquetas: tipo 1 = el de secuencias mas cortas."""
    o = np.argsort([m.inicio(k)["E_T"] for k in range(m.K)])
    return Mezcla(m.pi[o], m.mu[o], m.P[o], m.lam, m.a0, m.objetivo, m.diagnostico,
                  None if m.P0 is None else m.P0[o])


def reproducibilidad(d: DatosPosesion, K: int, lam: float, a0: float, semillas: list[int],
                     max_iter: int, tol: float, n_corto: int = 25, paso_inicial: bool = True,
                     lam0: float | None = None, ms: list[Mezcla] | None = None) -> dict:
    """¿La escalera llega al mismo optimo desde semillas distintas? (ADR-v2-17)

    `ms`: los ajustes ya hechos, uno por semilla y en el mismo orden (p. ej. en paralelo; ADR-v2-64). Debe ser lo que
    daría `ajustar(..., seed=s, init="escalera", pr=prior(d, lam, a0, paso_inicial, lam0))`; sin él se ajustan aquí."""
    if ms is None:
        pr = prior(d, lam, a0, paso_inicial, lam0)
        ms = [ajustar(d, K, lam, a0, max_iter=max_iter, tol=tol, seed=s, init="escalera",
                      n_corto=n_corto, pr=pr) for s in semillas]
    elif len(ms) != len(semillas):
        raise ValueError("`ms` debe traer un ajuste por semilla")
    J = np.array([m.objetivo[-1] for m in ms])
    mejor = ms[int(J.argmax())]
    R0 = responsabilidades(mejor, d)
    a0_ = R0.argmax(1)
    t0 = _tarjetas(mejor)
    filas = []
    for s_, m in zip(semillas, ms):
        R = responsabilidades(m, d)
        j, acuerdo = _emparejar(a0_, R.argmax(1), K)
        t = _tarjetas(m)[j]
        filas.append({"semilla": s_, "delta_J": float(J.max() - m.objetivo[-1]), "acuerdo": float(acuerdo),
                      "acuerdo_suave": acuerdo_suave(R0, R[:, j]),
                      "max_dif_pi": float(np.abs(t[:, 0] - t0[:, 0]).max()),
                      "max_dif_ET_rel": float((np.abs(t[:, 1] - t0[:, 1]) / t0[:, 1]).max())})
    rango = float(J.max() - J.min())
    suave = float(min(f["acuerdo_suave"] for f in filas))
    pi_min = float(mejor.pi.min())
    return {"K": K, "semillas": filas, "rango_J": rango, "rango_J_por_secuencia": rango / d.n,
            "acuerdo_minimo": float(min(f["acuerdo"] for f in filas)), "acuerdo_suave_minimo": suave,
            "pi_minimo": pi_min,
            "reproducible": bool(rango / d.n <= TOL_J_POR_SECUENCIA and suave >= 0.95 and pi_min >= PI_MINIMO),
            "paso_inicial": paso_inicial}


def acuerdo_suave(R0: np.ndarray, R1: np.ndarray) -> float:
    """1 − distancia de variación total media entre responsabilidades emparejadas (ADR-v2-30).

    El acuerdo "duro" (mismo argmax) castiga empates: una secuencia con
    responsabilidades 0.51/0.49 en una solución y 0.49/0.51 en otra cuenta como
    desacuerdo total aunque las dos soluciones sean la misma. Con paso inicial,
    en datos sintéticos los 699 desacuerdos duros de dos soluciones idénticas
    (ΔJ = 0.08) eran TODOS secuencias ambiguas.
    """
    return float(1 - 0.5 * np.abs(R0 - R1).sum(1).mean())


def responsabilidades(m: Mezcla, d: DatosPosesion) -> np.ndarray:
    Lpi = _loglik_tipos(d, m) + np.log(m.pi)[None]
    return np.exp(Lpi - logsumexp(Lpi, axis=1, keepdims=True))


def loglik_por_posesion(m: Mezcla, d: DatosPosesion) -> np.ndarray:
    return logsumexp(_loglik_tipos(d, m) + np.log(m.pi)[None], axis=1)


# ======================================================================
# Eleccion de K
# ======================================================================
def cv_k(
    d: DatosPosesion, k_grid: list[int], lam: float, a0: float = 1.0, folds: int = 5,
    seed: int = 0, n_init: int = 2, max_iter: int = 200, tol: float = 1e-6,
    frac_partidos: float = 1.0, verbose: bool = True, paso_inicial: bool = True, lam0: float | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Log-verosimilitud fuera de muestra (nats/transicion), pliegues POR PARTIDO."""
    partidos = d.meta["match_id"].to_numpy()
    uniq = np.unique(partidos)
    rng = np.random.default_rng(seed)
    if frac_partidos < 1.0:
        uniq = np.sort(rng.choice(uniq, size=max(folds, int(frac_partidos * len(uniq))), replace=False))
    sel = np.isin(partidos, uniq)
    pliegues = match_folds(uniq, folds, seed)
    filas = []
    for K in k_grid:
        for f, test_m in enumerate(pliegues):
            te = sel & np.isin(partidos, test_m)
            dtr, dte = d.sub(sel & ~te), d.sub(te)
            pr = prior(dtr, lam, a0, paso_inicial, lam0)
            m = ajustar(dtr, K, lam, a0, n_init, max_iter, tol, seed, pr=pr)
            ll = float(loglik_por_posesion(m, dte).sum())
            nt_ = float(dte.largo.sum())
            filas.append({"K": K, "pliegue": f, "loglik": ll, "transiciones": nt_, "nats_por_transicion": ll / nt_})
            if verbose:
                print(f"  K={K} pliegue={f}: {ll / nt_:.5f} nats/transición", flush=True)
    det = pl.DataFrame(filas)
    return resumen_cv(det, folds), det


def resumen_cv(det: pl.DataFrame, folds: int) -> pl.DataFrame:
    """Resumen por K con errores PAREADOS por pliegue (ADR-v2-10)."""
    ancho = det.pivot(on="K", index="pliegue", values="nats_por_transicion").sort("pliegue")
    ks = sorted(det["K"].unique().to_list())
    M = np.column_stack([ancho[str(k)].to_numpy() for k in ks])
    score = np.array([det.filter(pl.col("K") == k)["loglik"].sum() / det.filter(pl.col("K") == k)["transiciones"].sum()
                      for k in ks])
    total = (M[:, -1] - M[:, 0]).mean() if len(ks) > 1 else 1.0
    delta, se, frac = [np.nan], [np.nan], [0.0]
    for j in range(1, len(ks)):
        dd = M[:, j] - M[:, j - 1]
        delta.append(dd.mean())
        se.append(dd.std(ddof=1) / np.sqrt(len(dd)))
        frac.append(((M[:, j] - M[:, 0]).mean() / total) if total else np.nan)
    return pl.DataFrame({"K": ks, "score": score, "delta_vs_Km1": delta, "se_pareado": se,
                         "t": np.array(delta) / np.array(se), "ganancia_acumulada": frac})


# ======================================================================
# Lectura de los tipos
# ======================================================================
def resumen_tipos(m: Mezcla, d: DatosPosesion, r: np.ndarray, n_tipicas: int = 5, t_min: int = 1) -> list[dict]:
    """Por tipo: peso, E[T], desenlaces, xG por secuencia (modelo Y empirico),
    visitas por zona y secuencias tipicas. Modelo y empirico deben parecerse."""
    if t_min != 1:
        raise ValueError("con secuencias (min_actions = 1) no hay truncamiento: t_min debe ser 1")
    nt, ns = d.n_transient, d.n_states
    n_zonas = nt // d.n_phases
    uids = d.meta["seq_uid" if "seq_uid" in d.meta.columns else "poss_uid"].to_numpy()
    arg = r.argmax(axis=1)
    remata = np.asarray(d.S @ _es_remate(nt, ns)).ravel() > 0
    xg_sec = np.asarray(d.X.sum(axis=1)).ravel()
    S1, X1 = (d.S1, d.X1) if m.paso_inicial else (d.S, d.X)
    out = []
    # V = N c con c = (xG de remates + valor de la reanudacion) / acciones (ADR-v2-72); el xG por posesion del
    # modelo usa solo los remates, para compararlo con el empirico (que es la suma del xG de los remates)
    XC1 = d.Xc(primera=False) if m.paso_inicial else d.Xc()
    for k in range(m.K):
        w = r[:, k]
        C1 = np.asarray(S1.T @ w).reshape(nt, ns)
        c = recompensa_xg(C1.sum(axis=1), np.asarray(X1.T @ w).ravel())
        cv = recompensa_xg(C1.sum(axis=1), np.asarray(XC1.T @ w).ravel())
        if m.paso_inicial:
            C0 = np.asarray(d.S0.T @ w).reshape(nt, ns)
            c0 = recompensa_xg(C0.sum(axis=1), np.asarray(d.X0.T @ w).ravel())
            cv0 = recompensa_xg(C0.sum(axis=1), np.asarray(d.Xc(primera=True).T @ w).ravel())
        else:
            c0, cv0 = c, cv
        q = m.inicio(k, c, c0)
        qv = q if d.XV is None else m.inicio(k, cv, cv0)
        cad = m.cadena(k)
        Q0 = m.P0e(k)[:, :nt]
        vis = m.mu[k] + (m.mu[k] @ Q0) @ cad.fundamental()      # visitas esperadas por estado
        vis_z = (vis / vis.sum()).reshape(n_zonas, d.n_phases).sum(axis=1)
        pesos = w / max(w.sum(), _EPS)
        cand = np.flatnonzero((arg == k) & (w > 0.9))
        tip = []
        if cand.size:
            med = np.median(d.largo[cand])
            cerca = cand[np.abs(d.largo[cand] - med) <= max(1, 0.1 * med)]
            cerca = cerca if cerca.size else cand
            tip = uids[cerca[np.argsort(-w[cerca])][:n_tipicas]].tolist()
        out.append({
            "tipo": k + 1, "pi": float(m.pi[k]), "rho_Q": cad.check()["rho_Q"],
            "E_T_modelo": q["E_T"], "E_T_empirico": float(pesos @ d.largo),
            "P_gol": float(q["B"][0]), "P_remate_sin_gol": float(q["B"][1]),
            "P_perdida": float(q["B"][2]), "P_fuera": float(q["B"][3]),
            **({"P_interrupcion_favor": float(q["B"][4])} if len(q["B"]) > 4 else {}),
            "P_remate_empirico": float(pesos @ remata),
            "xG_por_posesion_modelo": q["xG"], "xG_por_posesion_empirico": float(pesos @ xg_sec),
            "valor_por_posesion_modelo": qv["xG"],      # = xG + valor de las reanudaciones a favor (V = N c)
            "visitas_por_zona": vis_z.tolist(),
            "inicio_por_zona": m.mu[k].reshape(n_zonas, d.n_phases).sum(axis=1).tolist(),
            # con el estado zona × nivel de presión (ADR-v2-36): qué fracción de sus visitas es en cada nivel
            "visitas_por_fase": (vis / vis.sum()).reshape(n_zonas, d.n_phases).sum(axis=0).tolist(),
            "valor_por_zona": _por_zona(qv["V"], C1, n_zonas, d.n_phases),
            "posesiones_tipicas": tip,
        })
    return out


def _es_remate(nt: int, ns: int) -> np.ndarray:
    to = np.arange(nt * ns) % ns
    return ((to == nt) | (to == nt + 1)).astype(float)


def _por_zona(V, Ck, n_zonas, n_phases):
    w = Ck.sum(axis=1)
    return ((V * w).reshape(n_zonas, n_phases).sum(1)
            / np.maximum(w.reshape(n_zonas, n_phases).sum(1), _EPS)).tolist()


# ======================================================================
# Bondad de ajuste de la duracion
# ======================================================================
def supervivencia_tipo(m: Mezcla, k: int, kmax: int) -> np.ndarray:
    """S[t] = P(T > t): S[0] = 1, S[t] = (mu Q0) Q^{t-1} 1 para t >= 1."""
    nt = m.mu.shape[1]
    Q = m.P[k][:, :nt]
    v = m.mu[k] @ m.P0e(k)[:, :nt]
    S = np.empty(kmax + 1)
    S[0] = 1.0
    for t in range(1, kmax + 1):
        S[t] = v.sum()
        v = v @ Q
    return np.clip(S, 0.0, 1.0)


def supervivencia_mezcla(m: Mezcla, kmax: int) -> np.ndarray:
    return sum(m.pi[k] * supervivencia_tipo(m, k, kmax) for k in range(m.K))


def _pmf_condicionada(S: np.ndarray, t_min: int) -> np.ndarray:
    pmf = np.clip(-np.diff(S), 0.0, None)
    pmf[: max(t_min - 1, 0)] = 0.0
    return pmf / max(pmf.sum(), _EPS)


def ks_largo(largos: np.ndarray, S: np.ndarray, t_min: int) -> float:
    kmax = len(S) - 1
    obs = largos[largos >= t_min]
    cnt = np.bincount(np.clip(obs, 1, kmax), minlength=kmax + 1)[1:]
    ecdf = np.cumsum(cnt) / max(cnt.sum(), 1)
    return float(np.abs(ecdf - np.cumsum(_pmf_condicionada(S, t_min))).max())


def simular_largos(m: Mezcla, n: int, rng: np.random.Generator, t_min: int = 1, kmax: int = 400) -> np.ndarray:
    """Largos simulados: primer paso con P0, los siguientes con P."""
    nt = m.mu.shape[1]
    out, faltan = [], n
    while faltan > 0:
        tipos = rng.choice(m.K, size=int(faltan * 1.6) + 50, p=m.pi)
        for k in range(m.K):
            nk = int((tipos == k).sum())
            if nk == 0:
                continue
            est = rng.choice(nt, size=nk, p=m.mu[k])
            T = np.zeros(nk, dtype=int)
            vivos = np.ones(nk, dtype=bool)
            cum0, cum = np.cumsum(m.P0e(k), axis=1), np.cumsum(m.P[k], axis=1)
            for paso in range(kmax):
                idx = np.flatnonzero(vivos)
                if idx.size == 0:
                    break
                C = cum0 if paso == 0 else cum
                nxt = np.minimum((C[est[idx]] < rng.random(idx.size)[:, None]).sum(axis=1), m.P.shape[2] - 1)
                T[idx] += 1
                ab = nxt >= nt
                vivos[idx[ab]] = False
                est[idx[~ab]] = nxt[~ab]
            out.append(T[T >= t_min])
        faltan = n - sum(len(o) for o in out)
    return np.concatenate(out)[:n]


def bondad_largo(m: Mezcla, d: DatosPosesion, t_min: int = 1, kmax: int = 60,
                 n_boot: int = 0, seed: int = 0) -> dict:
    """KS entre la duracion empirica y la phase-type de la mezcla (p conservador sin reajuste)."""
    S = supervivencia_mezcla(m, kmax)
    ks = ks_largo(d.largo, S, t_min)
    obs = d.largo[d.largo >= t_min]
    K_ = min(kmax, int(obs.max()))
    cnt = np.bincount(np.clip(obs, 1, K_), minlength=K_ + 1)[1:]
    S_emp = 1.0 - np.cumsum(cnt) / cnt.sum()
    S_teo = 1.0 - np.cumsum(_pmf_condicionada(S, t_min))[:K_]
    res = {"K": m.K, "paso_inicial": m.paso_inicial, "KS": ks, "n": int(len(obs)), "t_min": t_min,
           "E_T_empirico": float(obs.mean()),
           "E_T_modelo": float(sum(m.pi[k] * m.inicio(k)["E_T"] for k in range(m.K))),
           "supervivencia": [{"t": t + 1, "empirica": float(S_emp[t]), "modelo": float(S_teo[t])}
                             for t in range(min(K_, 30))]}
    if n_boot:
        rng = np.random.default_rng(seed)
        nulos = np.array([ks_largo(simular_largos(m, len(obs), rng, t_min), S, t_min) for _ in range(n_boot)])
        res["KS_nula_p95"] = float(np.percentile(nulos, 95))
        res["p_conservador"] = float((1 + (nulos >= ks).sum()) / (1 + n_boot))
    return res


def guardar_json(obj, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
