"""
Fase 2 -- La tabla por SECUENCIA sobre la que se prueban las hipotesis.

Una fila por secuencia (ADR-v2-14) con:
  - r_1..r_K   responsabilidades de cada familia (mezcla ya ajustada, K fijo)
  - xg, remata  lo que produjo la secuencia
  - contexto    marcador, tramo de minuto, localia, Elo propio - rival,
                origen de la secuencia, temporada
  - f, g        f = la secuencia la ejecuta el equipo del tecnico foco (ATAQUE)
                g = la ejecuta un rival CONTRA el foco            (DEFENSA)
La liga de referencia son las secuencias con f = g = 0, es decir, las de
partidos donde el foco no jugó: "la liga sin el foco", por construccion.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .mezcla import DatosPosesion, Mezcla, _es_remate, responsabilidades

TRAMOS = ("0-29", "30-44", "45-59", "60-74", "75+")


def _tramo(minuto: pl.Expr) -> pl.Expr:
    return (pl.when(minuto < 30).then(pl.lit("0-29"))
              .when(minuto < 45).then(pl.lit("30-44"))
              .when(minuto < 60).then(pl.lit("45-59"))
              .when(minuto < 75).then(pl.lit("60-74"))
              .otherwise(pl.lit("75+")))


def mapa_origen(cfg) -> dict[str, str]:
    return {pp: o for o, pps in cfg["origen"].items() for pp in pps}


def tabla_secuencias(trans: pl.DataFrame, space, mezcla: Mezcla, partidos: pl.DataFrame,
                     elo: pl.DataFrame, cfg, foco: str) -> pl.DataFrame:
    d = DatosPosesion.desde_transiciones(trans, space)
    if mezcla.mu.shape[1] != d.n_transient:
        raise ValueError("La mezcla y las transiciones no comparten espacio de estados.")
    r = responsabilidades(mezcla, d)
    xg = np.asarray(d.X.sum(axis=1)).ravel()
    remata = np.asarray(d.S @ _es_remate(d.n_transient, d.n_states)).ravel() > 0
    K = mezcla.K
    t = d.meta.with_columns(
        *[pl.Series(f"r_{k + 1}", r[:, k]) for k in range(K)],
        pl.Series("xg", xg), pl.Series("remata", remata), pl.Series("largo", d.largo),
    )
    origen = mapa_origen(cfg)
    t = (t.join(partidos.select("match_id", "season_id"), on="match_id", how="left")
          .join(elo.select("match_id", "team", "elo", "elo_rival"), on=["match_id", "team"], how="left")
          .with_columns(
              _tramo(pl.col("minute")).alias("tramo"),
              pl.col("play_pattern").replace_strict(origen, default="open").alias("origen"),
              ((pl.col("elo") - pl.col("elo_rival")) / 100.0).alias("elo_dif"),
              pl.col("local").fill_null(False),
              (pl.col("coach") == foco).fill_null(False).alias("f"),
              (pl.col("coach_faced") == foco).fill_null(False).alias("g"),
          ))
    faltan = t.filter(pl.col("elo_dif").is_null()).height
    if faltan:
        raise ValueError(f"{faltan} secuencias sin Elo: ¿partidos sin resultado o equipos con otro nombre?")
    if t["f"].sum() == 0:
        disp = trans["coach"].drop_nulls().unique().sort().to_list()
        raise ValueError(f"El foco '{foco}' no tiene secuencias. DT disponibles: {disp[:40]}...")
    # partidos del foco: la liga de referencia no los incluye en ningún lado
    partidos_foco = t.filter(pl.col("f") | pl.col("g"))["match_id"].unique()
    return t.with_columns(pl.col("match_id").is_in(partidos_foco.to_list()).alias("partido_foco"))


# ----------------------------------------------------------------------
# Diseño del modelo de pesos
# ----------------------------------------------------------------------
INTERACCIONES_ATAQUE = ("perdiendo", "ganando", "tramo_75+", "local", "elo_dif")
INTERACCIONES_DEFENSA = ("local",)


def rcs(x: np.ndarray, nudos: np.ndarray) -> np.ndarray:
    """Spline cúbico restringido (natural) de Harrell: lineal fuera de los nudos
    extremos. Devuelve las k−2 columnas NO lineales (la lineal va aparte)."""
    x = np.asarray(x, float)
    t = np.asarray(nudos, float)
    k = len(t)
    esc = (t[-1] - t[0]) ** 2

    def c3(u):
        return np.clip(u, 0, None) ** 3
    cols = [(c3(x - t[j]) - c3(x - t[k - 2]) * (t[k - 1] - t[j]) / (t[k - 1] - t[k - 2])
             + c3(x - t[k - 1]) * (t[k - 2] - t[j]) / (t[k - 1] - t[k - 2])) / esc for j in range(k - 2)]
    return np.column_stack(cols) if cols else np.zeros((len(x), 0))


def nudos_suaves(t: pl.DataFrame) -> dict:
    """Nudos en los cuantiles 5-35-65-95 % (Harrell, 4 nudos) de minuto y Elo."""
    q = [0.05, 0.35, 0.65, 0.95]
    return {"minuto": np.quantile(t["minute"].to_numpy(), q), "elo": np.quantile(t["elo_dif"].to_numpy(), q)}


def diseno(t: pl.DataFrame, f: np.ndarray | None = None, g: np.ndarray | None = None,
           temporadas: list | None = None, suave: dict | None = None) -> tuple[np.ndarray, list[str]]:
    """Matriz de diseño. `f` y `g` se pueden sustituir para contrafactuales.

    Referencia: empatando, minuto 0-29, visitante, Elo igual, juego abierto,
    primera temporada, fuera del foco.

    `suave` (nudos de `nudos_suaves`): en la parte de LA LIGA, el minuto y el Elo
    entran como splines cúbicos restringidos y se agrega marcador × minuto. Las
    desviaciones del foco (f × ...) no cambian: H3–H6 prueban lo mismo con una
    referencia mejor especificada (sensibilidad a la calibración 1.3–1.4).
    """
    n = t.height
    f = t["f"].to_numpy().astype(float) if f is None else np.asarray(f, float)
    g = t["g"].to_numpy().astype(float) if g is None else np.asarray(g, float)
    base = {
        "intercepto": np.ones(n),
        "perdiendo": (t["score_state"] == "losing").to_numpy().astype(float),
        "ganando": (t["score_state"] == "winning").to_numpy().astype(float),
    }
    for tr in TRAMOS[1:]:
        base[f"tramo_{tr}"] = (t["tramo"] == tr).to_numpy().astype(float)
    base["local"] = t["local"].to_numpy().astype(float)
    base["elo_dif"] = t["elo_dif"].to_numpy().astype(float)
    for o in ("transition", "restart", "set_piece"):
        base[f"origen_{o}"] = (t["origen"] == o).to_numpy().astype(float)
    temporadas = temporadas or sorted(t["season_id"].drop_nulls().unique().to_list())
    for s in temporadas[1:]:
        base[f"temporada_{s}"] = (t["season_id"] == s).to_numpy().astype(float)
    cols = dict(base)
    if suave is not None:
        mi = t["minute"].to_numpy().astype(float)
        for c in [c for c in cols if c.startswith("tramo_")]:
            del cols[c]                                   # el minuto entra como spline
        cols["minuto"] = mi / 90.0
        for j, v in enumerate(rcs(mi, suave["minuto"]).T):
            cols[f"minuto_s{j + 1}"] = v
        for j, v in enumerate(rcs(base["elo_dif"], suave["elo"]).T):
            cols[f"elo_s{j + 1}"] = v
        cols["perdiendo×minuto"] = base["perdiendo"] * mi / 90.0
        cols["ganando×minuto"] = base["ganando"] * mi / 90.0
    cols["f"] = f
    for c in INTERACCIONES_ATAQUE:
        cols[f"f×{c}"] = f * base[c]
    cols["g"] = g
    for c in INTERACCIONES_DEFENSA:
        cols[f"g×{c}"] = g * base[c]
    nombres = list(cols)
    return np.column_stack([cols[c] for c in nombres]), nombres
