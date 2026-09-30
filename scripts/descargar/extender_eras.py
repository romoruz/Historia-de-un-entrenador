#!/usr/bin/env python3
"""
extender_eras.py — alarga la era vigente de cada club para cubrir los partidos nuevos, SOLO si el
técnico que reporta StatsBomb (`managers` del partido) es el mismo de la era.

Las eras son la fuente verificada de "quién dirigió" (dtcoach.partidos). Un partido nuevo que cae
después del `end_date` de la última era de su club no se le asigna a nadie. Este script:
  - por club, toma sus partidos posteriores al fin de la última era, en orden de fecha;
  - mientras el técnico del API sea la misma persona (dtcoach.partidos.mismo_dt), alarga la era;
  - al primer partido con OTRO técnico se detiene y lo reporta: un cambio de técnico se agrega a
    mano, con su fecha verificada (interinatos incluidos), como el resto de las eras.
Por omisión solo muestra lo que haría. Con --aplicar reescribe los CSV (van en el repo: revisa el
diff antes de hacer commit).

Uso (raíz del repo, venv del proyecto):
  python scripts/descargar/extender_eras.py            # qué cambiaría
  python scripts/descargar/extender_eras.py --aplicar
"""
import argparse
import csv
from pathlib import Path

import polars as pl

from dtcoach.config import Config
from dtcoach.eras import _slug_club
from dtcoach.partidos import dt_por_partido, leer_partidos, mismo_dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    cfg = Config.load(a.config)
    dtp = dt_por_partido(leer_partidos(cfg.ruta("raw_matches")))
    d = cfg.ruta("eras_dir")
    cambios, avisos = [], []
    for f in sorted(Path(d).glob("coach_eras_*.csv")):
        with open(f, newline="", encoding="utf-8") as fh:
            filas = list(csv.DictReader(fh))
            campos = list(filas[0].keys()) if filas else []
        if not filas:
            continue
        ult = max(range(len(filas)), key=lambda i: filas[i]["start_date"])
        era = filas[ult]
        slug = f.stem.removeprefix("coach_eras_")
        partidos = (dtp.filter(pl.col("team").map_elements(_slug_club, return_dtype=pl.Utf8) == slug)
                    .filter(pl.col("match_date") > pl.lit(era["end_date"]).str.to_date()).sort("match_date"))
        if partidos.height == 0:
            continue
        nuevo_fin = None
        for r in partidos.iter_rows(named=True):
            if r["coach_api"] and not mismo_dt(era["coach"], r["coach_api"]):
                avisos.append(f"{slug}: desde {r['match_date']} el API dice «{r['coach_api']}» (la era vigente es "
                              f"«{era['coach']}»). Agrega la era nueva a mano y vuelve a correr.")
                break
            nuevo_fin = r["match_date"]
        if nuevo_fin and str(nuevo_fin) > era["end_date"]:
            cambios.append(f"{slug}: «{era['coach']}» {era['end_date']} → {nuevo_fin}")
            viejo = era["end_date"]
            era["end_date"] = str(nuevo_fin)
            if a.aplicar:      # edición en sitio: no cambia comillas ni saltos de línea del resto del archivo
                ls = f.read_text(encoding="utf-8").splitlines(keepends=True)
                ls[ult + 1] = ls[ult + 1].replace(f",{viejo},", f",{nuevo_fin},", 1)
                f.write_text("".join(ls), encoding="utf-8", newline="")
    print("Eras que se alargan:" if cambios else "Ninguna era que alargar.")
    for c in cambios:
        print("  ", c)
    for x in avisos:
        print("  [revisar]", x)
    if cambios and not a.aplicar:
        print("\n(sin --aplicar no se escribió nada)")


if __name__ == "__main__":
    main()
