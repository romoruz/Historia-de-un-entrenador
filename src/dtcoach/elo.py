"""
Fuerza del rival: Elo sobre TODOS los partidos de la liga.

    E_A = 1 / (1 + 10^((R_B - R_A - h) / 400)),   R_A <- R_A + K (S_A - E_A)

A es el local y h la ventaja de local en puntos Elo. S ∈ {1, 0.5, 0}.

K y h se eligen minimizando la LOG-PERDIDA de los resultados,
    L(K, h) = - sum [ S log E + (1 - S) log(1 - E) ],
que es la cuasi-verosimilitud binomial de S: con empates S = 0.5 no es una
verosimilitud propia, pero su minimo sigue estimando consistentemente la
probabilidad de "puntos esperados". Se evalua despues de un calentamiento
(`burn_in` partidos), porque al inicio todos valen 1500 y el error es de
arranque, no del modelo.

Se reporta el Elo PREVIO al partido: el del resultado de ese partido no puede
usarse para describirlo (seria fuga de informacion).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

_EPS = 1e-12


@dataclass
class ResultadoElo:
    K: float
    h: float
    logperdida: float
    previo: pl.DataFrame        # match_id, team, elo, elo_rival, E (puntos esperados)
    rejilla: pl.DataFrame       # K, h, logperdida
    calibracion: pl.DataFrame   # bin de E, E medio, S medio, n


def _preparar(partidos: pl.DataFrame) -> pl.DataFrame:
    p = partidos.filter(pl.col("home_score").is_not_null() & pl.col("away_score").is_not_null())
    orden = [c for c in ("match_date", "kick_off", "match_id") if c in p.columns]
    return p.sort(orden)


def correr_elo(partidos: pl.DataFrame, K: float, h: float, inicial: float = 1500.0,
               burn_in: int = 150) -> tuple[float, pl.DataFrame]:
    p = _preparar(partidos)
    R: dict[str, float] = {}
    filas, perdida, n_eval = [], 0.0, 0
    for i, (mid, loc, vis, gl, gv) in enumerate(
        p.select("match_id", "home_team", "away_team", "home_score", "away_score").iter_rows()
    ):
        ra, rb = R.get(loc, inicial), R.get(vis, inicial)
        E = 1.0 / (1.0 + 10 ** ((rb - ra - h) / 400.0))
        S = 1.0 if gl > gv else (0.5 if gl == gv else 0.0)
        filas.append((mid, loc, ra, rb, E))
        filas.append((mid, vis, rb, ra, 1.0 - E))
        if i >= burn_in:
            perdida -= S * np.log(max(E, _EPS)) + (1 - S) * np.log(max(1 - E, _EPS))
            n_eval += 1
        R[loc] = ra + K * (S - E)
        R[vis] = rb - K * (S - E)
    previo = pl.DataFrame(filas, schema={"match_id": pl.Int64, "team": pl.Utf8, "elo": pl.Float64,
                                         "elo_rival": pl.Float64, "E": pl.Float64}, orient="row")
    return perdida / max(n_eval, 1), previo


def ajustar_elo(partidos: pl.DataFrame, K_grid, h_grid, inicial: float = 1500.0,
                burn_in: int = 150) -> ResultadoElo:
    rej = []
    for K in K_grid:
        for h in h_grid:
            L, _ = correr_elo(partidos, K, h, inicial, burn_in)
            rej.append({"K": float(K), "h": float(h), "logperdida": L})
    rej = pl.DataFrame(rej)
    mejor = rej.sort("logperdida").row(0, named=True)
    L, previo = correr_elo(partidos, mejor["K"], mejor["h"], inicial, burn_in)
    return ResultadoElo(mejor["K"], mejor["h"], L, previo, rej, calibracion(partidos, previo))


def calibracion(partidos: pl.DataFrame, previo: pl.DataFrame, bins: int = 5) -> pl.DataFrame:
    """E del local contra los puntos que realmente sacó: un Elo útil está calibrado."""
    p = _preparar(partidos).select(
        "match_id", pl.col("home_team").alias("team"),
        pl.when(pl.col("home_score") > pl.col("away_score")).then(1.0)
        .when(pl.col("home_score") == pl.col("away_score")).then(0.5).otherwise(0.0).alias("S"),
    )
    x = p.join(previo, on=["match_id", "team"])
    cortes = np.quantile(x["E"].to_numpy(), np.linspace(0, 1, bins + 1)[1:-1]).tolist()
    return (x.with_columns(pl.col("E").cut(cortes).alias("bin"))
             .group_by("bin").agg(pl.col("E").mean().alias("E_medio"), pl.col("S").mean().alias("S_medio"),
                                  pl.len().alias("n"))
             .sort("E_medio"))
