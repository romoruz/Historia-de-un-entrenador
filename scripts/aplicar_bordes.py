#!/usr/bin/env python3
"""Propone eras corregidas a partir de reports/eras_sugerencias.csv. NO pisa nada.

Escribe una COPIA completa de eras_api en data/referencia/eras_api_v2/ con:
  - A_borde: fin extendido / inicio adelantado hasta el partido que el API
    atribuye al DT de la era vecina (típicamente liguilla y 2026/27);
  - con --nuevas: eras nuevas para DT del API que aparecen DESPUÉS de la
    última era del club (temporada 2026/27), con el nombre del API.
Valida cada CSV con eras.load_eras (sin solapes) e imprime el diff.
Después: revisa el diff y apunta `rutas.eras_dir` y `rutas.exclusiones` del
config a eras_api_v2. Los casos C se corrigen A MANO.
Uso: python scripts/aplicar_bordes.py [--nuevas]
"""
import argparse
import re
import shutil
from datetime import date

import polars as pl

from dtcoach.config import Config
from dtcoach.eras import _slug_club, load_eras

ap = argparse.ArgumentParser()
ap.add_argument("--nuevas", action="store_true")
ap.add_argument("--rehacer", action="store_true", help="borra y regenera eras_api_v2")
a = ap.parse_args()
cfg = Config.load()
src = cfg.ruta("eras_dir")
# Si el config ya apunta a la copia corregida, la FUENTE sigue siendo la
# original: sin esto, --rehacer copiaria eras_api_v2 sobre eras_api_v2_v2.
if src.name.endswith("_v2"):
    src = src.parent / src.name[: -len("_v2")]
dst = src.parent / (src.name + "_v2")
if dst.exists() and not a.rehacer:
    raise SystemExit(
        f"{dst} ya existe. Este script REGENERA desde cero y borraria tus correcciones\n"
        f"a mano (fue lo que paso la primera vez). Si de verdad quieres rehacerlo:\n"
        f"  python scripts/aplicar_bordes.py --rehacer [--nuevas]\n"
        f"Para solo VALIDAR lo que ya tienes:\n"
        f"  python -c \"from pathlib import Path; from dtcoach.eras import load_eras; "
        f"[load_eras(f) for f in Path('{dst}').glob('coach_eras_*.csv')]; print('eras OK')\"")
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst)

s = pl.read_csv(cfg.ruta("reportes") / "eras_sugerencias.csv", try_parse_dates=True)
print(f"fuente: {src}\ndestino: {dst}")
pat = re.compile(r"^(extender fin|adelantar inicio) de '(.+)' (?:hasta|a) (\d{4}-\d{2}-\d{2})$")
cambios: dict[tuple[str, str], dict] = {}
for team, sug in s.filter(pl.col("causa") == "A_borde").select("team", "sugerencia").iter_rows():
    accion, coach, f = pat.match(sug).groups()
    f = date.fromisoformat(f)
    c = cambios.setdefault((team, coach), {"fin": None, "inicio": None})
    if accion.startswith("extender"):
        c["fin"] = max(c["fin"] or f, f)
    else:
        c["inicio"] = min(c["inicio"] or f, f)

# Nombre canónico: si el DT del API ya existe en CUALQUIER club con su nombre de
# uso ("Guillermo Almada"), se usa ese. Sin esto, Almada en el América y en
# Pachuca serían dos personas y se perdería un mover (ADR-v2-13).
from dtcoach.partidos import mismo_dt  # noqa: E402
conocidos = sorted({c for f in src.glob("coach_eras_*.csv") for c in load_eras(f)["coach"].to_list()})
_ROM = re.compile(r"\s+(I|II|III|IV)$")


def canonico(api: str) -> str:
    hits = {_ROM.sub("", c) for c in conocidos if mismo_dt(c, api)}
    return hits.pop() if len(hits) == 1 else api


nuevas = {}
if a.nuevas:
    for (team, api), g in s.filter(pl.col("causa") == "A_sin_era").group_by("team", "coach_api"):
        f = dst / f"coach_eras_{_slug_club(team)}.csv"
        if not f.exists() or api is None:
            continue
        ultimo = load_eras(f)["end_date"].max()
        if g["match_date"].min() > ultimo:
            nuevas.setdefault(team, []).append((canonico(api), g["match_date"].min(), g["match_date"].max()))

errores = []
for team in sorted({t for t, _ in cambios} | set(nuevas)):
    f = dst / f"coach_eras_{_slug_club(team)}.csv"
    e = pl.read_csv(f, infer_schema_length=None)
    antes = e.clone()
    for (t, coach), c in cambios.items():
        if t != team:
            continue
        m = pl.col("coach") == coach
        if c["fin"]:
            e = e.with_columns(pl.when(m & (pl.col("end_date") < str(c["fin"])))
                               .then(pl.lit(str(c["fin"]))).otherwise(pl.col("end_date")).alias("end_date"))
        if c["inicio"]:
            e = e.with_columns(pl.when(m & (pl.col("start_date") > str(c["inicio"])))
                               .then(pl.lit(str(c["inicio"]))).otherwise(pl.col("start_date")).alias("start_date"))
    for api, d0, d1 in sorted(nuevas.get(team, []), key=lambda x: x[1]):
        fila = {c: None for c in e.columns} | {"coach": api, "start_date": str(d0), "end_date": str(d1)}
        e = pl.concat([e, pl.DataFrame([fila], schema=e.schema)], how="vertical")
    e.write_csv(f)
    try:
        load_eras(f)
    except Exception as ex:
        errores.append(f"{team}: {ex}")
    print(f"\n== {team}")
    j = antes.join(e, on="coach", how="full", suffix="_nuevo", coalesce=True)
    print(j.filter((pl.col("start_date") != pl.col("start_date_nuevo")) | (pl.col("end_date") != pl.col("end_date_nuevo"))
                   | pl.col("start_date").is_null())
          .select("coach", "start_date", "start_date_nuevo", "end_date", "end_date_nuevo"))

print(f"\nCopia escrita en {dst}. Casos C (a mano):")
print(s.filter(pl.col("causa") == "C").select("team", "match_date", "coach", "coach_api"))
if errores:
    print("\nERRORES DE VALIDACIÓN (solapes): corrige a mano antes de usar la copia:")
    for x in errores:
        print("  ", x)
else:
    print("\nTodas las eras validan. ESTE PASO FALTA (sin el, fase0 sigue usando las viejas):")
    print("  sed -i 's#eras_dir: data/referencia/eras_api$#eras_dir: data/referencia/eras_api_v2#; "
          "s#exclusiones: data/referencia/eras_api/#exclusiones: data/referencia/eras_api_v2/#' "
          "config/default.yaml")
    print("  grep -n 'eras_dir\\|exclusiones' config/default.yaml   # verifica que digan _v2")
    print("  dtcoach fase0")
