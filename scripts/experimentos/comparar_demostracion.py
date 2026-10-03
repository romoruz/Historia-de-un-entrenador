#!/usr/bin/env python3
"""
Compara dos corridas de `dtcoach demostracion` (ADR-v2-70): qué afirmaciones cambiaron de veredicto y cuánto se
movieron los p. Sirve para el paso 2 de la integración (el orden fijo del bootstrap del balón parado, ADR-v2-61) y
para el paso 4 (el quinto absorbente).

Empareja por (seccion, id), que es la ruta de la afirmación en el JSON de su sección. Escribe COMPARAR.md junto a la
demostración nueva y lo imprime.

Uso:  python scripts/experimentos/comparar_demostracion.py ANTES.csv DESPUES.csv [--salida DIR] [--titulo TEXTO]
"""
import argparse
from pathlib import Path

import polars as pl


def comparar(a: pl.DataFrame, b: pl.DataFrame) -> pl.DataFrame:
    cols = ["seccion", "id", "afirmacion", "p", "q", "veredicto", "efecto"]
    a, b = a.select([c for c in cols if c in a.columns]), b.select([c for c in cols if c in b.columns])
    return (a.join(b, on=["seccion", "id"], how="full", suffix="_nuevo", coalesce=True)
            .with_columns((pl.col("p_nuevo") - pl.col("p")).alias("dp"),
                          (pl.col("veredicto") != pl.col("veredicto_nuevo")).fill_null(True).alias("cambia")))


def reporte(c: pl.DataFrame, titulo: str) -> list[str]:
    dem0 = c.filter(pl.col("veredicto") == "demostrado").height
    dem1 = c.filter(pl.col("veredicto_nuevo") == "demostrado").height
    md = [f"# {titulo}", "",
          f"Afirmaciones: {c.filter(pl.col('veredicto').is_not_null()).height} antes, "
          f"{c.filter(pl.col('veredicto_nuevo').is_not_null()).height} después. "
          f"Demostradas: **{dem0} → {dem1}**.", "",
          "## Por sección: cuántos p se movieron y cuánto", "",
          "| sección | afirmaciones | p distintos | máx. abs(Δp) | cambian de veredicto |", "|---|---|---|---|---|"]
    for (sec,), g in sorted(c.group_by(["seccion"]), key=lambda t: str(t[0][0])):
        d = g.filter(pl.col("dp").is_not_null() & pl.col("dp").is_not_nan())
        mx = d["dp"].abs().max() if d.height else 0.0
        md.append(f"| {sec} | {g.height} | {d.filter(pl.col('dp') != 0).height} | {mx or 0.0:.4g} | "
                  f"{g['cambia'].sum()} |")
    ch = c.filter(pl.col("cambia")).sort(["seccion", "id"])
    md += ["", f"## Afirmaciones que cambian de veredicto ({ch.height})", ""]
    if ch.height:
        md += ["| sección | afirmación | p antes → después | q antes → después | veredicto antes → después |",
               "|---|---|---|---|---|"]
        for r in ch.iter_rows(named=True):
            af = r.get("afirmacion") or r.get("afirmacion_nuevo") or r["id"]
            md.append(f"| {r['seccion']} | {af} | {r['p']} → {r['p_nuevo']} | {r['q']} → {r['q_nuevo']} | "
                      f"{r['veredicto']} → {r['veredicto_nuevo']} |")
    else:
        md.append("Ninguna.")
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("antes")
    ap.add_argument("despues")
    ap.add_argument("--salida", default=None, help="por omisión, la carpeta de DESPUES")
    ap.add_argument("--titulo", default="Demostración: antes contra después")
    a = ap.parse_args()
    c = comparar(pl.read_csv(a.antes, infer_schema_length=None), pl.read_csv(a.despues, infer_schema_length=None))
    md = reporte(c, a.titulo)
    out = Path(a.salida or Path(a.despues).parent)
    out.mkdir(parents=True, exist_ok=True)
    (out / "COMPARAR.md").write_text("\n".join(md), encoding="utf-8")
    c.write_csv(out / "comparar.csv")
    print("\n".join(md))


if __name__ == "__main__":
    main()
