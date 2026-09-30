#!/usr/bin/env python3
"""Candidatos a técnico focal (criterios de docs/00_ROADMAP.md §Elección).

Por entrenador (juntando etapas I/II): partidos con DT asignado, clubes, si es
MOVER (≥ 2 clubes: permite separar técnico de plantel), partidos de fase
regular y fracción con 360 disponible.
Uso: python scripts/candidatos_dt.py [--min 60]
"""
import argparse

import polars as pl

from dtcoach.config import Config

ap = argparse.ArgumentParser()
ap.add_argument("--min", type=int, default=60)
a = ap.parse_args()
cfg = Config.load()

tr = pl.read_parquet(cfg.ruta("transiciones"), columns=["match_id", "team", "coach"])
p = pl.read_parquet(cfg.ruta("partidos"), columns=["match_id", "stage", "status_360"])
# `stage` no es "Regular Season" en todos los torneos: se muestra y se toma la
# etapa MÁS frecuente como fase regular (la primera versión contaba 17 o 0).
print(p.group_by("stage").len().sort("len", descending=True))
ES_LIGUILLA = pl.col("stage").str.contains("(?i)final|play|quarter|semi|repech|reclas")
x = (tr.filter(pl.col("coach").is_not_null()).unique(["match_id", "team", "coach"])
       .with_columns(pl.col("coach").str.replace(r"\s+(I|II|III|IV)$", "").alias("dt"))
       .join(p, on="match_id", how="left"))
por_club = x.group_by("dt", "team").len().sort("len", descending=True)
g = (x.group_by("dt").agg(
        pl.len().alias("partidos"),
        pl.col("team").n_unique().alias("n_clubes"),
        (~ES_LIGUILLA).sum().alias("fase_regular"),
        (pl.col("status_360") == "available").mean().round(3).alias("frac_360"))
     .join(por_club.group_by("dt").agg(
        pl.concat_str([pl.col("team"), pl.lit(" ("), pl.col("len").cast(pl.Utf8), pl.lit(")")])
        .str.join(", ").alias("clubes")), on="dt")
     .filter(pl.col("partidos") >= a.min)
     .with_columns((pl.col("n_clubes") >= 2).alias("mover"))
     .sort(["mover", "partidos"], descending=True))
with pl.Config(tbl_rows=40, fmt_str_lengths=90, tbl_width_chars=220):
    print(g)
print("\nSin 360 alto no hay capítulo de bloque defensivo; sin 'mover' no hay capítulo 'es él o el plantel'.")
