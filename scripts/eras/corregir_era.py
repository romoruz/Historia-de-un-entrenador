#!/usr/bin/env python3
"""Correcciones A MANO de eras, sin editar CSV a ojo (ADR-v2-08).

Dos operaciones, las dos sobre la carpeta a la que apunta `rutas.eras_dir`:
  --excluir     añade (club, match_id) del partido de esa fecha a absorbidos.csv:
                el partido queda sin DT en las dos columnas (coach y coach_faced),
                como el interinato de Cervantes. Sus secuencias siguen en la liga.
  --borrar-era  elimina la fila de ese DT en coach_eras_<club>.csv.
Valida todas las eras al final. Nunca borra nada sin decir qué borró.

Ejemplos:
  python scripts/corregir_era.py --club "Juárez" --fecha 2026-08-16 --excluir \\
         --borrar-era "Salvador Valero"
  python scripts/corregir_era.py --club "Mazatlán" --fecha 2022-03-13 --excluir
"""
import argparse
from datetime import date

import polars as pl

from dtcoach.config import Config
from dtcoach.eras import _slug_club, load_eras

ap = argparse.ArgumentParser()
ap.add_argument("--club", required=True)
ap.add_argument("--fecha", required=True)
ap.add_argument("--excluir", action="store_true")
ap.add_argument("--borrar-era", default=None)
a = ap.parse_args()
cfg = Config.load()
d = cfg.ruta("eras_dir")
if not d.name.endswith("_v2"):
    raise SystemExit(f"rutas.eras_dir apunta a {d.name}: las correcciones van en la copia _v2.")

part = pl.read_parquet(cfg.ruta("partidos"))
f = date.fromisoformat(a.fecha)
m = part.filter((pl.col("match_date") == f) & ((pl.col("home_team") == a.club) | (pl.col("away_team") == a.club)))
if m.height != 1:
    raise SystemExit(f"se esperaba 1 partido de {a.club} el {f}, hay {m.height}")
mid = int(m["match_id"][0])
print(f"partido: {mid}  {m['home_team'][0]} vs {m['away_team'][0]}  "
      f"(API: {m['home_coach'][0]} / {m['away_coach'][0]})")

if a.excluir:
    ex_p = cfg.ruta("exclusiones")
    ex = pl.read_csv(ex_p, infer_schema_length=None)
    ya = ex.filter((pl.col("club") == a.club) & (pl.col("match_id").cast(pl.Int64) == mid))
    if ya.height:
        print("ya estaba en absorbidos.csv: no se añade de nuevo")
    else:
        fila = {c: None for c in ex.columns} | {"club": a.club, "match_id": mid}
        if "dirigio_la_era" in ex.columns:
            fila["dirigio_la_era"] = 0      # load_exclusions solo lee las filas con 0
        nuevo = pl.DataFrame([fila]).cast({c: t for c, t in ex.schema.items()}, strict=False)
        pl.concat([ex, nuevo.select(ex.columns)], how="vertical_relaxed").write_csv(ex_p)
        print(f"añadido a {ex_p.name}: ({a.club}, {mid})")

if a.borrar_era:
    ep = d / f"coach_eras_{_slug_club(a.club)}.csv"
    e = pl.read_csv(ep, infer_schema_length=None)
    # Solo la fila de ESE DT que CONTIENE la fecha. Borrar por nombre borraba
    # tambien etapas legitimas del mismo DT en otra fecha (paso con Valero:
    # su interinato de 2024 se fue junto con el de 2026).
    quita = e.filter((pl.col("coach") == a.borrar_era)
                     & (pl.col("start_date") <= a.fecha) & (pl.col("end_date") >= a.fecha))
    if quita.height == 0:
        raise SystemExit(f"no hay era '{a.borrar_era}' en {ep.name}. Hay: {e['coach'].to_list()}")
    print(f"borrando de {ep.name}:\n{quita}")
    e.join(quita, on=e.columns, how="anti", nulls_equal=True).write_csv(ep)

for q in d.glob("coach_eras_*.csv"):
    load_eras(q)
print("eras OK (sin solapes)")
