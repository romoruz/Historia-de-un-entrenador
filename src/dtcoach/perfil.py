"""
Fase 2 -- Perfiles crudos (sin modelo) con bootstrap por partido.

Tres grupos de secuencias, en partidos DISJUNTOS salvo ataque/defensa del foco:
  ataque_foco   f = 1   (las ejecuta el equipo del foco)
  defensa_foco  g = 1   (las ejecutan sus rivales contra él)
  liga          partidos donde el foco no jugó
El bootstrap remuestrea PARTIDOS, estratificado: partidos del foco por un lado
y partidos de la liga por otro, con reemplazo y el mismo número de cada uno.
Ataque y defensa del foco se remuestrean juntos (salen del mismo partido).

Para cada familia k:
  uso_k       = sum_s r_sk / n                         cuánto se usa
  xg_k        = sum_s r_sk xg_s / sum_s r_sk           xG por secuencia DENTRO de la familia
  remate_k    = sum_s r_sk 1{remata} / sum_s r_sk
Todas son razones de sumas por partido: el bootstrap se hace sobre las sumas
por partido (rápido, exacto para razones de sumas).
"""
from __future__ import annotations

import numpy as np
import polars as pl


def _sumas_por_partido(t: pl.DataFrame, filtro: pl.Expr, K: int) -> tuple[np.ndarray, np.ndarray]:
    """(partidos, M) con M[:, bloque] = [n, sum r_k (K), sum r_k xg (K), sum r_k remata (K)]."""
    agg = [pl.len().alias("n")]
    agg += [pl.col(f"r_{k + 1}").sum().alias(f"u{k}") for k in range(K)]
    agg += [(pl.col(f"r_{k + 1}") * pl.col("xg")).sum().alias(f"x{k}") for k in range(K)]
    agg += [(pl.col(f"r_{k + 1}") * pl.col("remata").cast(pl.Float64)).sum().alias(f"s{k}") for k in range(K)]
    g = t.filter(filtro).group_by("match_id").agg(agg).sort("match_id")
    cols = ["n"] + [f"u{k}" for k in range(K)] + [f"x{k}" for k in range(K)] + [f"s{k}" for k in range(K)]
    return g["match_id"].to_numpy(), g.select(cols).to_numpy().astype(float)


def _metricas(M: np.ndarray, K: int) -> np.ndarray:
    tot = M.sum(0) if M.ndim == 2 else M
    n, u = tot[0], tot[1:1 + K]
    x, s = tot[1 + K:1 + 2 * K], tot[1 + 2 * K:1 + 3 * K]
    return np.concatenate([u / n, x / np.maximum(u, 1e-12), s / np.maximum(u, 1e-12),
                           [x.sum() / n]])


def nombres_metricas(K: int, familias: list[str]) -> list[str]:
    return ([f"uso · {f}" for f in familias] + [f"xG por secuencia · {f}" for f in familias]
            + [f"P(remate) · {f}" for f in familias] + ["xG por secuencia · total"])


def perfiles(t: pl.DataFrame, K: int, n_boot: int = 2000, seed: int = 0, nivel: float = 0.95) -> dict:
    ids_a, Ma = _sumas_por_partido(t, pl.col("f"), K)
    ids_d, Md = _sumas_por_partido(t, pl.col("g"), K)
    ids_l, Ml = _sumas_por_partido(t, ~pl.col("partido_foco"), K)
    if not np.array_equal(ids_a, ids_d):
        comun = np.intersect1d(ids_a, ids_d)
        Ma, Md = Ma[np.isin(ids_a, comun)], Md[np.isin(ids_d, comun)]
    obs = {"ataque": _metricas(Ma, K), "defensa": _metricas(Md, K), "liga": _metricas(Ml, K)}
    rng = np.random.default_rng(seed)
    nf, nl = len(Ma), len(Ml)
    B = {k: np.empty((n_boot, len(v))) for k, v in obs.items()}
    for b in range(n_boot):
        i = rng.integers(0, nf, nf)
        j = rng.integers(0, nl, nl)
        B["ataque"][b] = _metricas(Ma[i], K)
        B["defensa"][b] = _metricas(Md[i], K)
        B["liga"][b] = _metricas(Ml[j], K)
    a = (1 - nivel) / 2
    out = {"n_partidos_foco": int(nf), "n_partidos_liga": int(nl)}
    for lado in ("ataque", "defensa"):
        dif = B[lado] - B["liga"]
        d_obs = obs[lado] - obs["liga"]
        # basico (percentil invertido), igual que el resto del proyecto
        lo, hi = 2 * d_obs - np.quantile(dif, 1 - a, 0), 2 * d_obs - np.quantile(dif, a, 0)
        p = np.minimum(1.0, 2 * np.minimum((dif <= 0).mean(0), (dif >= 0).mean(0)) + 1 / (n_boot + 1))
        out[lado] = {"foco": obs[lado].tolist(), "liga": obs["liga"].tolist(),
                     "dif": d_obs.tolist(), "lo": lo.tolist(), "hi": hi.tolist(), "p": p.tolist()}
    return out
