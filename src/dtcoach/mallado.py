"""
Fase 1 -- Calibración del mallado (ADR-v2-32).

EL PROBLEMA
-----------
Comparar mallas por verosimilitud directa no es válido: con más zonas cambia el
espacio muestral (predecir "zona 7 de 20" no es lo mismo que "zona 7 de 96").
La solución estándar es comparar la DENSIDAD predictiva del siguiente punto en
el campo continuo (como en la elección del ancho de histograma por validación
cruzada, Rudemo 1982): si la cadena da P(j | i) y la zona j ocupa una fracción
a_j del campo, la densidad relativa a la uniforme es P(j | i) / a_j. Para los
absorbentes (gol, remate, pérdida, fuera), que no tienen área, se usa la
probabilidad. Así, todas las mallas se miden en la MISMA escala:

    puntaje = (1/n) sum log[ P(destino | origen) / a_destino ]    (nats por transición)

en partidos NO vistos (pliegues por partido), con encogimiento λ elegido en una
rejilla. Mallas finas ganan resolución pero pierden precisión por esparsidad;
la validación cruzada mide ese equilibrio directamente.

DOS FAMILIAS DE PARTICIONES
---------------------------
1. Rectangulares nx × ny (las que usa el pipeline).
2. AGREGACIÓN CONTIGUA desde una malla fina (diagnóstico): se parte de celdas de
   10 × 10 m y se fusionan pares de regiones VECINAS (grafo de adyacencia) que
   menos verosimilitud pierden. Es la versión voraz de la agregación de cadenas
   de Markov que minimiza pérdida de información (Deng, Mehta y Meyn, 2011;
   lumpability de Kemeny y Snell): una partición es buena si las celdas
   fusionadas "se comportan igual" como origen y como destino. La curva de
   validación cruzada contra el número de regiones dice cuántas zonas
   distinguen realmente los datos, y el mapa muestra DÓNDE conviene más
   resolución (típicamente el último tercio).

Regla de decisión (pre-registrada en `docs/11_HIPOTESIS.md`, fase 1): se adopta
la malla rectangular de mayor puntaje; entre las que quedan a menos de un error
estándar PAREADO de la mejor, la de menos zonas.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .estimate import match_folds, shrink
from .grid import StateSpace
from .possessions import build_transitions

_EPS = 1e-300


def conteos_por_pliegue(lf, cfg, nx: int, ny: int, folds: int, seed: int,
                        pitch: dict | None = None) -> tuple[np.ndarray, StateSpace]:
    """(folds, nt, ns): conteos de transiciones de cada pliegue (partidos disjuntos)."""
    p = pitch or cfg["pitch"]
    space = StateSpace(nx=nx, ny=ny, length=p["length"], width=p["width"], phases=tuple(cfg["phase_order"]))
    tr = build_transitions(lf, space, cfg).select("match_id", "from_state", "to_state")
    partidos = tr["match_id"].to_numpy()
    plg = match_folds(np.unique(partidos), folds, seed)
    fold_de = np.empty(partidos.max() + 1, dtype=np.int64)
    for f, ms in enumerate(plg):
        fold_de[ms] = f
    f = fold_de[partidos]
    i = tr["from_state"].to_numpy().astype(np.int64)
    j = tr["to_state"].to_numpy().astype(np.int64)
    nt, ns = space.n_transient, space.n_states
    C = np.bincount((f * nt + i) * ns + j, minlength=folds * nt * ns).reshape(folds, nt, ns).astype(float)
    return C, space


def _loglik_densidad(C_te: np.ndarray, P: np.ndarray, area_rel: np.ndarray) -> float:
    """Σ C log(P / a) en destinos transitorios y Σ C log P en absorbentes (nats)."""
    nt = P.shape[0]
    ll = float((C_te * np.log(np.maximum(P, _EPS))).sum())
    ll -= float((C_te[:, :nt].sum(0) * np.log(area_rel)).sum())
    return ll


def evaluar_rectangular(C: np.ndarray, lam_grid: list[float]) -> dict:
    """Puntaje por pliegue para el mejor λ (el mismo λ en todos los pliegues)."""
    F, nt, ns = C.shape
    area = np.full(nt, 1.0 / nt)
    U = np.full((nt, ns), 1.0 / ns)
    tot = C.sum(0)
    por_lam = {}
    for lam in lam_grid:
        vals = []
        for f in range(F):
            P = shrink(tot - C[f], U, lam)
            vals.append(_loglik_densidad(C[f], P, area) / C[f].sum())
        por_lam[lam] = np.array(vals)
    lam_mejor = max(por_lam, key=lambda l: por_lam[l].mean())
    filas = tot.sum(1)
    return {"lam": lam_mejor, "pliegues": por_lam[lam_mejor], "score": float(por_lam[lam_mejor].mean()),
            "params_por_obs": float(nt * (ns - 1) / tot.sum()), "frac_filas_menos_30": float((filas < 30).mean())}


def elegir_malla(res: dict) -> tuple[str, pl.DataFrame]:
    """Regla 1-EE pareada hacia la malla con menos zonas."""
    nombres = list(res)
    mejor = max(nombres, key=lambda n: res[n]["score"])
    filas = []
    for n in nombres:
        d = res[n]["pliegues"] - res[mejor]["pliegues"]
        se = float(d.std(ddof=1) / np.sqrt(len(d))) if n != mejor else 0.0
        filas.append({"malla": n, "zonas": res[n]["zonas"], "score": res[n]["score"], "lam": res[n]["lam"],
                      "dif_vs_mejor": float(d.mean()), "se_pareado": se,
                      "dentro_1se": bool(d.mean() >= -se), "params_por_obs": res[n]["params_por_obs"],
                      "frac_filas_menos_30": res[n]["frac_filas_menos_30"]})
    tab = pl.DataFrame(filas).sort("zonas")
    elegida = tab.filter(pl.col("dentro_1se")).sort("zonas")["malla"][0]
    return elegida, tab


# ----------------------------------------------------------------------
# Agregación contigua (diagnóstico)
# ----------------------------------------------------------------------
def _vecinos(nx: int, ny: int) -> set[tuple[int, int]]:
    """Adyacencia de 4 vecinos en la malla fina (z = ix*ny + iy)."""
    E = set()
    for ix in range(nx):
        for iy in range(ny):
            z = ix * ny + iy
            if ix + 1 < nx:
                E.add((z, (ix + 1) * ny + iy))
            if iy + 1 < ny:
                E.add((z, z + 1))
    return E


def _agregar(C: np.ndarray, lab: np.ndarray, R: int) -> np.ndarray:
    nf = C.shape[0]
    A = np.zeros((nf, R))
    A[np.arange(nf), lab] = 1.0
    return np.hstack([A.T @ C[:, :nf] @ A, A.T @ C[:, nf:]])


def _ll_region(M: np.ndarray, tam: np.ndarray, nf: int) -> float:
    R = M.shape[0]
    fila = M.sum(1, keepdims=True)
    m = M > 0
    ll = float((M[m] * np.log((M / np.maximum(fila, _EPS))[m])).sum())
    return ll - float((M[:, :R].sum(0) * np.log(tam / nf)).sum())


def camino_agregacion(C: np.ndarray, nx: int, ny: int, R_min: int = 4) -> list[np.ndarray]:
    """Fusiones voraces de regiones vecinas. Devuelve las etiquetas para R = nf, nf-1, ..., R_min."""
    nf = nx * ny
    lab = np.arange(nf)
    caminos = [lab.copy()]
    aristas = _vecinos(nx, ny)
    while lab.max() + 1 > R_min:
        R = lab.max() + 1
        M = _agregar(C, lab, R)
        tam = np.bincount(lab, minlength=R).astype(float)
        pares = {(min(lab[a], lab[b]), max(lab[a], lab[b])) for a, b in aristas if lab[a] != lab[b]}
        mejor, mejor_ll = None, -np.inf
        for a, b in pares:
            Mn = M.copy()
            Mn[a] += Mn[b]
            Mn[:, a] += Mn[:, b]
            Mn = np.delete(np.delete(Mn, b, 0), b, 1)
            tn = np.delete(tam.copy(), b)
            tn[a if a < b else a - 1] += tam[b]
            ll = _ll_region(Mn, tn, nf)
            if ll > mejor_ll:
                mejor, mejor_ll = (a, b), ll
        a, b = mejor
        lab = np.where(lab == b, a, lab)
        lab = np.unique(lab, return_inverse=True)[1]
        caminos.append(lab.copy())
    return caminos


def evaluar_agregacion(C: np.ndarray, nx: int, ny: int, R_min: int = 4, lam: float = 10.0) -> dict:
    """Puntaje de validación cruzada contra el número de regiones (camino por pliegue)."""
    F, nf, ns = C.shape
    tot = C.sum(0)
    punt = {}
    for f in range(F):
        tr = tot - C[f]
        for lab in camino_agregacion(tr, nx, ny, R_min):
            R = lab.max() + 1
            M_tr, M_te = _agregar(tr, lab, R), _agregar(C[f], lab, R)
            tam = np.bincount(lab, minlength=R).astype(float)
            P = shrink(M_tr, np.full(M_tr.shape, 1.0 / M_tr.shape[1]), lam)
            punt.setdefault(R, []).append(_loglik_densidad(M_te, P, tam / nf) / C[f].sum())
    tab = pl.DataFrame([{"regiones": R, "score": float(np.mean(v)), "se": float(np.std(v, ddof=1) / np.sqrt(len(v)))}
                        for R, v in punt.items()]).sort("regiones")
    R_opt = int(tab.sort("score", descending=True)["regiones"][0])
    lab_final = next(l for l in camino_agregacion(tot, nx, ny, R_min) if l.max() + 1 == R_opt)
    return {"tabla": tab, "R_opt": R_opt, "etiquetas": lab_final, "nx": nx, "ny": ny}
