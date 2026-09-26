"""
Capa de fútbol -- lectura ÚNICA de los eventos para las fases B–F (03_FRAMEWORK §5).

Todo lo que se mide en la capa de fútbol sale de aquí, con las mismas
convenciones que la cadena:
  - coordenadas StatsBomb [0,120] × [0,80] en el marco de ataque de QUIEN EJECUTA
    el evento (un evento defensivo en x = 100 ocurre en el campo del rival);
  - `fin_x, fin_y`: destino de pases, conducciones y remates (como `extract_actions`);
  - `reloj`: segundos de juego continuos (minute·60 + second), el mismo reloj de
    StatsBomb en los dos tiempos;
  - solo tiempo reglamentario (period ≤ 2), como el resto del proyecto.
"""
from __future__ import annotations

import numpy as np
import polars as pl

COLUMNAS = ["id", "index", "match_id", "period", "minute", "second", "type", "team", "possession",
            "possession_team", "play_pattern", "player", "player_id", "position", "location", "duration",
            "under_pressure", "counterpress", "pass_end_location", "pass_outcome", "pass_type",
            "pass_recipient_id", "carry_end_location", "shot_end_location", "shot_outcome",
            "shot_statsbomb_xg", "obv_total_net", "substitution_replacement_id"]

AREA = (102.0, 18.0, 62.0)          # x ≥ 102 y 18 ≤ y ≤ 62: el área rival (marco de quien ataca)
ULTIMO_TERCIO = 80.0
BALON_PARADO = ("Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off")


def leer(lf: pl.LazyFrame) -> pl.DataFrame:
    """Eventos con coordenadas planas y reloj. `lf`: `ingest.scan_events` (esquema de `aplanar`)."""
    have = lf.collect_schema().names()
    ev = lf.select([c for c in COLUMNAS if c in have]).filter(pl.col("period") <= 2).collect()
    for c in COLUMNAS:
        if c not in ev.columns:
            ev = ev.with_columns(pl.lit(None).alias(c))

    def xy(col, i):
        return pl.col(col).list.get(i, null_on_oob=True).cast(pl.Float64)

    fin_x = (pl.when(pl.col("type") == "Pass").then(xy("pass_end_location", 0))
             .when(pl.col("type") == "Carry").then(xy("carry_end_location", 0))
             .when(pl.col("type") == "Shot").then(xy("shot_end_location", 0)))
    fin_y = (pl.when(pl.col("type") == "Pass").then(xy("pass_end_location", 1))
             .when(pl.col("type") == "Carry").then(xy("carry_end_location", 1))
             .when(pl.col("type") == "Shot").then(xy("shot_end_location", 1)))
    return (ev.with_columns(xy("location", 0).alias("x"), xy("location", 1).alias("y"),
                            fin_x.alias("fin_x"), fin_y.alias("fin_y"),
                            (pl.col("minute") * 60 + pl.col("second")).cast(pl.Float64).alias("reloj"),
                            pl.col("under_pressure").fill_null(False), pl.col("counterpress").fill_null(False),
                            pl.col("obv_total_net").cast(pl.Float64),
                            pl.col("shot_statsbomb_xg").cast(pl.Float64))
              .drop("location", "pass_end_location", "carry_end_location", "shot_end_location")
              .sort("match_id", "index"))


def con_rival(tp: pl.DataFrame) -> pl.DataFrame:
    """Agrega a la tabla equipo-partido el rival y el técnico del rival."""
    r = tp.select("match_id", pl.col("team").alias("rival"), pl.col("coach").alias("coach_rival"))
    out = tp.join(r, on="match_id", how="left").filter(pl.col("team") != pl.col("rival"))
    return out


def en_area(x: pl.Expr, y: pl.Expr) -> pl.Expr:
    return (x >= AREA[0]) & (y >= AREA[1]) & (y <= AREA[2])


def posesiones(ev: pl.DataFrame) -> pl.DataFrame:
    """Una fila por posesión de StatsBomb (sus eventos, sin los del rival en ella).

    inicio, fin     reloj del primer y último evento de la posesión (de cualquier equipo)
    x0              x del primer evento del equipo en posesión (su marco)
    x_max           mayor x alcanzada por un pase completo, conducción o evento del equipo
    remates, xg     remates y xG del equipo en la posesión, con su reloj
    patron          play_pattern de la posesión
    """
    base = ev.filter(pl.col("possession").is_not_null())
    tiempos = base.group_by("match_id", "possession").agg(
        pl.col("reloj").min().alias("inicio"), pl.col("reloj").max().alias("fin"),
        pl.col("possession_team").first().alias("team"), pl.col("play_pattern").first().alias("patron"),
        pl.col("period").first())
    propios = base.filter(pl.col("team") == pl.col("possession_team"))
    completo = pl.col("pass_outcome").is_null() | (pl.col("type") != "Pass")
    alcance = pl.when(pl.col("type").is_in(["Pass", "Carry"]) & completo).then(
        pl.max_horizontal("x", "fin_x")).otherwise(pl.col("x"))
    agg = propios.group_by("match_id", "possession").agg(
        pl.col("x").drop_nulls().first().alias("x0"),
        alcance.max().alias("x_max"),
        (pl.col("type") == "Shot").sum().alias("remates"),
        pl.col("shot_statsbomb_xg").fill_null(0.0).sum().alias("xg"),
        ((pl.col("type") == "Shot") & (pl.col("shot_outcome") == "Goal")).sum().alias("goles"),
        pl.col("reloj").filter(pl.col("type") == "Shot").alias("reloj_remates"),
        pl.col("shot_statsbomb_xg").filter(pl.col("type") == "Shot").fill_null(0.0).alias("xg_remates"),
        pl.len().alias("eventos"))
    return (tiempos.join(agg, on=["match_id", "possession"], how="left")
            .with_columns(pl.col("remates").fill_null(0), pl.col("xg").fill_null(0.0), pl.col("goles").fill_null(0))
            .sort("match_id", "possession"))


def distancia_arco(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.hypot(120.0 - np.asarray(x, float), 40.0 - np.asarray(y, float))
