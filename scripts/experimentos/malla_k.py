#!/usr/bin/env python3
"""
EXPERIMENTO (ADR-v2-74; diagnóstico, NO se integra): ¿K = 3 es reproducible solo con la malla 5×4, o también con
otras resoluciones?

Para cada malla (por omisión 4×3, 5×4, 6×5 y 8×6) se construyen las transiciones con el pipeline oficial
(`build_transitions` + el quinto absorbente, `absorbente5.integrar`, con config/default.yaml), y para cada K (por
omisión 2–5) se ajusta la mezcla desde 3 semillas con el criterio del §4 de 04:
  acuerdo suave mínimo ≥ 0.95, rango de J ≤ 1.08e-4 por secuencia y π mínimo ≥ 1 %  (`mezcla.reproducibilidad`),
y la duración del mejor ajuste contra la observada (KS, E[T]; `mezcla.bondad_largo`).

No toca el vocabulario oficial: las transiciones de cada malla van a data/processed/experimentos/malla_k/ y los
reportes a reports/experimentos/malla_k/ (MALLA_K.md, malla_k.csv). Se reanuda: las filas (malla, K) ya hechas con la
misma muestra no se recalculan.

Antecedente: en la entrega (ADR-v2-35, cuatro absorbentes, 461,454 secuencias) 8×5 no tuvo K reproducible, 6×4 tuvo
K = 2 y 5×4, K = 3.

Uso (raíz del repo):
  python scripts/experimentos/malla_k.py --muestra 120 --procesos 3      # humo (no decide nada)
  python scripts/experimentos/malla_k.py --procesos 3                     # completa: 4 mallas × 4 K × 3 semillas
"""
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import multiprocessing as mp
import time

import numpy as np
import polars as pl

from dtcoach import absorbente5 as ab
from dtcoach import ingest
from dtcoach import mezcla as mz
from dtcoach.config import Config
from dtcoach.grid import ABSORBING, StateSpace
from dtcoach.possessions import build_transitions

_D: dict = {}


def _rutas(cfg):
    out = cfg.ruta("reportes") / "experimentos" / "malla_k"
    dat = cfg.ruta("transiciones").parent / "experimentos" / "malla_k"
    out.mkdir(parents=True, exist_ok=True)
    dat.mkdir(parents=True, exist_ok=True)
    return out, dat


def _space(cfg, nx: int, ny: int) -> StateSpace:
    p = cfg["pitch"]
    return StateSpace(nx=nx, ny=ny, length=p["length"], width=p["width"], phases=tuple(cfg["phase_order"]),
                      absorbing=ABSORBING)


def transiciones(cfg, nx: int, ny: int, dat, ev) -> pl.DataFrame:
    """Las transiciones de la malla nx × ny, con el quinto absorbente (como `dtcoach fase0`). Se guardan en caché."""
    f = dat / f"trans_{nx}x{ny}.parquet"
    if f.exists():
        return pl.read_parquet(f)
    sp_ = _space(cfg, nx, ny)
    tr = build_transitions(ingest.load(cfg.ruta("eventos_parquet")), sp_, cfg)
    tr, _ = ab.integrar(tr, ev, sp_)
    tr.write_parquet(f)
    return tr


def _muestra(tr: pl.DataFrame, n: int | None, seed: int) -> pl.DataFrame:
    if not n:
        return tr
    u = np.unique(tr["match_id"].to_numpy())
    keep = np.random.default_rng(seed).choice(u, min(n, len(u)), replace=False).tolist()
    return tr.filter(pl.col("match_id").is_in(keep))


def _init(d) -> None:
    _D["d"] = d


def _fit(args):
    """Un ajuste de reproducibilidad: exactamente lo que hace `mezcla.reproducibilidad` por dentro (prior fijo)."""
    K, seed, mc = args
    d = _D["d"]
    pr = mz.prior(d, mc["lam"], mc["a0"], mc.get("paso_inicial", True), mc.get("lam0"))
    return (K, seed), mz.ajustar(d, K, mc["lam"], mc["a0"], max_iter=mc["max_iter"], tol=mc["tol"], seed=seed,
                                 init="escalera", n_corto=mc.get("n_corto", 25), pr=pr)


def _ajustes(d, Ks: list[int], semillas: list[int], mc: dict, procesos: int) -> dict:
    d.S1
    tareas = [(K, s_, mc) for K in Ks for s_ in semillas]
    if procesos <= 1:
        _init(d)
        return dict(_fit(t) for t in tareas)
    with mp.get_context("spawn").Pool(min(procesos, len(tareas)), initializer=_init, initargs=(d,)) as pool:
        return dict(pool.imap_unordered(_fit, tareas, chunksize=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mallas", nargs="+", default=["4x3", "5x4", "6x5", "8x6"])
    ap.add_argument("--K", nargs="+", type=int, default=[2, 3, 4, 5])
    ap.add_argument("--semillas", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--muestra", type=int, default=None, help="partidos (humo); sin esto, toda la liga")
    ap.add_argument("--procesos", type=int, default=min(3, os.cpu_count() or 1))
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    cfg = Config.load(a.config)
    mc, bc = cfg["mezcla"], cfg["bondad"]
    out, dat = _rutas(cfg)
    etiqueta = f"muestra{a.muestra}" if a.muestra else "completa"
    csv = out / f"malla_k_{etiqueta}.csv"
    hechos = set()
    if csv.exists():
        hechos = {(m, k) for m, k in pl.read_csv(csv).select("malla", "K").iter_rows()}
    ev = None
    for malla in a.mallas:
        nx, ny = (int(x) for x in malla.lower().split("x"))
        Ks = [K for K in a.K if (malla, K) not in hechos]
        if not Ks:
            print(f"{malla}: ya hecho, se salta", flush=True)
            continue
        t0 = time.time()
        if ev is None and not (dat / f"trans_{nx}x{ny}.parquet").exists():
            ev = (ingest.scan_events(cfg.ruta("eventos_parquet"))
                  .select("match_id", "index", "type", "team", "pass_type", "shot_type", "location").collect())
        tr = _muestra(transiciones(cfg, nx, ny, dat, ev), a.muestra, cfg["seed"])
        d = mz.DatosPosesion.desde_transiciones(tr, _space(cfg, nx, ny))
        print(f"== {malla}: {d.n:,} secuencias, {d.n_transient} transitorios, {d.n_states} estados; K = {Ks}",
              flush=True)
        ms = _ajustes(d, Ks, a.semillas, mc, a.procesos)
        for K in Ks:
            mK = [ms[(K, s_)] for s_ in a.semillas]
            r = mz.reproducibilidad(d, K, mc["lam"], mc["a0"], a.semillas, mc["max_iter"], mc["tol"],
                                    mc.get("n_corto", 25), paso_inicial=mc.get("paso_inicial", True),
                                    lam0=mc.get("lam0"), ms=mK)
            mejor = mK[int(np.argmax([m.objetivo[-1] for m in mK]))]
            b = mz.bondad_largo(mejor, d, bc["t_min"], bc["kmax"])
            fila = pl.DataFrame([{
                "malla": malla, "zonas": nx * ny, "K": K, "secuencias": d.n,
                "acuerdo_suave_min": r["acuerdo_suave_minimo"], "acuerdo_duro_min": r["acuerdo_minimo"],
                "rango_J_por_secuencia": r["rango_J_por_secuencia"], "pi_min": r["pi_minimo"],
                "KS": b["KS"], "E_T_modelo": b["E_T_modelo"], "E_T_obs": b["E_T_empirico"],
                "reproducible": r["reproducible"], "segundos_malla": round(time.time() - t0, 1)}])
            (pl.concat([pl.read_csv(csv), fila], how="diagonal_relaxed") if csv.exists() else fila).write_csv(csv)
            print(f"   K={K}: acuerdo {r['acuerdo_suave_minimo']:.3f} · rango J {r['rango_J_por_secuencia']:.2e} · "
                  f"π mín {r['pi_minimo']:.3f} · KS {b['KS']:.4f} · reproducible: {r['reproducible']}", flush=True)
    escribir(pl.read_csv(csv), out, etiqueta, a)


def escribir(T: pl.DataFrame, out, etiqueta: str, a) -> None:
    orden = {m: i for i, m in enumerate(a.mallas)}
    T = T.with_columns(pl.col("malla").replace_strict(orden, default=99).alias("_o")).sort("_o", "K").drop("_o")
    md = [f"# ¿K = 3 es reproducible solo con la malla 5×4? (ADR-v2-74, {etiqueta})", "",
          "Criterio del §4 de 04: acuerdo suave mínimo ≥ 0.95, rango de J ≤ 1.08e-4 por secuencia, π mínimo ≥ 1 % "
          f"(semillas {' '.join(map(str, a.semillas))}). Cinco absorbentes, config/default.yaml. KS y E[T]: el mejor de "
          "los ajustes contra la duración observada.", "",
          "| malla | K | acuerdo | rango J / sec. | π mín | KS | E[T] mod / obs | reproducible |", "|---|---|---|---|---|---|---|---|"]
    for r in T.iter_rows(named=True):
        md.append(f"| {r['malla']} | {r['K']} | {r['acuerdo_suave_min']:.3f} | {r['rango_J_por_secuencia']:.2e} | "
                  f"{r['pi_min']:.3f} | {r['KS']:.4f} | {r['E_T_modelo']:.3f} / {r['E_T_obs']:.3f} | "
                  f"{'**sí**' if r['reproducible'] else 'no'} |")
    md += ["", "## Lectura", ""]
    rep = {m: sorted(g.filter(pl.col("reproducible"))["K"].to_list()) for (m,), g in T.group_by(["malla"])}
    for m in sorted(rep, key=lambda x: orden.get(x, 99)):
        md.append(f"- **{m}**: K reproducibles {rep[m] or 'ninguno'}; el mayor: {max(rep[m]) if rep[m] else '—'}.")
    otros = {m: [k for k in ks if k != 3] for m, ks in rep.items() if m in ("6x5", "8x6")}
    if any(otros.values()):
        md += ["", "**ATENCIÓN:** con una malla más fina es reproducible un K distinto de 3 ("
               + "; ".join(f"{m}: {ks}" for m, ks in otros.items() if ks)
               + "). La estabilidad de K = 3 sería propiedad de la malla 5×4, no del juego."]
    if etiqueta != "completa":
        md += ["", "*Pasada de humo con una submuestra: no decide nada (el umbral de J por secuencia y el acuerdo "
                   "dependen del tamaño).*"]
    (out / f"MALLA_K_{etiqueta}.md").write_text("\n".join(md), encoding="utf-8")
    (out / f"malla_k_{etiqueta}.json").write_text(json.dumps(T.to_dicts(), indent=1, default=float))
    print("\n".join(md))


if __name__ == "__main__":
    main()
