#!/usr/bin/env python3
"""Clasifica reports/verificacion_eras.csv (ya sin diferencias de formato de nombre).

  A_borde    la era no cubre el partido, pero el API dice que lo dirigió el DT de la
             era VECINA del mismo club -> probable fecha de cese/inicio corta. Sugerencia.
  A_sin_era  no hay era y el DT del API no es vecino -> interino o temporada nueva.
  AB         ni era ni API.
  C          los dos traen DT y son PERSONAS distintas -> revisar a mano (bug #14).
Escribe reports/eras_sugerencias.csv. NO modifica ningún CSV de eras.
Uso: python scripts/revisar_eras.py
"""
import polars as pl

from dtcoach.config import Config
from dtcoach.eras import load_eras, _slug_club
from dtcoach.partidos import mismo_dt

cfg = Config.load()
v = pl.read_csv(cfg.ruta("reportes") / "verificacion_eras.csv", try_parse_dates=True)


def vecinos(team, fecha):
    f = cfg.ruta("eras_dir") / f"coach_eras_{_slug_club(team)}.csv"
    if not f.exists():
        return None, None
    e = load_eras(f)
    antes = e.filter(pl.col("end_date") < fecha).tail(1)
    despues = e.filter(pl.col("start_date") > fecha).head(1)
    return (antes["coach"][0] if antes.height else None, despues["coach"][0] if despues.height else None)


causas, sug = [], []
for row in v.iter_rows(named=True):
    if row["coach"] is None and row["coach_api"] is None:
        causas.append("AB"); sug.append(None)
    elif row["coach"] is None:
        a, d = vecinos(row["team"], row["match_date"])
        if mismo_dt(a, row["coach_api"]):
            causas.append("A_borde"); sug.append(f"extender fin de '{a}' hasta {row['match_date']}")
        elif mismo_dt(d, row["coach_api"]):
            causas.append("A_borde"); sug.append(f"adelantar inicio de '{d}' a {row['match_date']}")
        else:
            causas.append("A_sin_era"); sug.append(None)
    elif row["coach_api"] is None:
        causas.append("B_sin_api"); sug.append(None)
    else:
        causas.append("C"); sug.append(None)
v = v.with_columns(pl.Series("causa", causas), pl.Series("sugerencia", sug, dtype=pl.Utf8))
v.write_csv(cfg.ruta("reportes") / "eras_sugerencias.csv")

print(v.group_by("causa").len().sort("causa"))
with pl.Config(tbl_rows=80, fmt_str_lengths=60, tbl_width_chars=200):
    print("\nC · personas distintas (REVISAR A MANO):")
    print(v.filter(pl.col("causa") == "C").group_by("team", "coach", "coach_api").agg(
        pl.len().alias("n"), pl.col("match_date").min().alias("desde"), pl.col("match_date").max().alias("hasta")
    ).sort("n", descending=True))
    print("\nA_borde · la era vecina probablemente termina/empieza mal:")
    print(v.filter(pl.col("causa") == "A_borde").group_by("team", "sugerencia").len().sort("team"))
    print("\nA_sin_era · por equipo:")
    print(v.filter(pl.col("causa") == "A_sin_era").group_by("team").agg(
        pl.len().alias("n"), pl.col("match_date").min().alias("desde"), pl.col("match_date").max().alias("hasta"),
        pl.col("coach_api").unique().alias("dt_api")).sort("n", descending=True))
