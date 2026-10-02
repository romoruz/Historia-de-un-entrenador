#!/usr/bin/env python3
"""
Mejora A (ADR-v2-52, EXPERIMENTO): ¿el técnico solo mueve π_k o también P^k?  Prueba de score de H0: P^k_foco = P^k_liga.

Uso (raíz del repo, venv activo, con data/ y reports/mezcla/ de la entrega):
  python scripts/experimentos/supuesto_pk.py --config config/exp_mejoras.yaml
  python scripts/experimentos/supuesto_pk.py --config config/exp_mejoras.yaml --muestra 300   # humo: 300 partidos de la liga
Salida: <reportes>/experimentos/supuesto_pk/SUPUESTO_PK.md y supuesto_pk.json.
NO escribe en reports/mezcla, fase1, fase2, fase3 ni historia.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import polars as pl

from dtcoach import supuesto_pk as spk
from dtcoach.cli import _elo, _space, _trans
from dtcoach.config import Config
from dtcoach.contexto import tabla_secuencias
from dtcoach.mezcla import DatosPosesion, Mezcla, responsabilidades



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/exp_mejoras.yaml")
    ap.add_argument("--muestra", type=int, default=0, help="humo: solo N partidos de la liga (todos los del foco)")
    a = ap.parse_args()
    t0 = time.time()
    cfg = Config.load(a.config)
    ec = cfg["experimentos"]["supuesto_pk"]
    foco = cfg["foco"]["coach"]      # fijo en config/exp_mejoras.yaml: Guillermo Almada
    K = cfg["fase2"]["K"]
    m = Mezcla.cargar(cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz")
    space, trans = _space(cfg), _trans(cfg)
    d = DatosPosesion.desde_transiciones(trans, space)
    t = tabla_secuencias(trans, space, m, pl.read_parquet(cfg.ruta("partidos")), _elo(cfg), cfg, foco)
    r = responsabilidades(m, d)
    match = t["match_id"].to_numpy()
    es_foco, pfoco = t["f"].to_numpy(), t["partido_foco"].to_numpy()
    nt, ns = d.n_transient, d.n_states
    if a.muestra:
        rng = np.random.default_rng(cfg["seed"])
        liga = np.unique(match[~pfoco])
        keep = set(rng.choice(liga, min(a.muestra, len(liga)), replace=False).tolist()) | set(np.unique(match[pfoco]).tolist())
        mask = np.isin(match, list(keep))
        d, r, match, es_foco, pfoco, t = d.sub(mask), r[mask], match[mask], es_foco[mask], pfoco[mask], t.filter(pl.Series(mask))
    S1, S0 = d.S1.tocsr(), d.S0.tocsr()
    res = spk.correr(S1, S0, r, match, es_foco, pfoco, m.P, m.P0, m.mu, nt, ns, ec["a"], ec["n_min"])
    res |= {"foco": foco, "secuencias_foco": int(es_foco.sum()), "partidos_foco": int(len(np.unique(match[es_foco]))),
            "muestra": a.muestra or None}
    # la nula empírica: cómo se desvía un técnico-club cualquiera (misma prueba, sin cambiar nada más)
    otros = (t.filter(pl.col("coach").is_not_null() & (pl.col("coach") != foco))
             .group_by("coach", "team").agg(pl.col("match_id").n_unique().alias("p"))
             .filter(pl.col("p") >= ec["min_partidos_nula"]))
    nula = []
    for coach, team, _ in otros.iter_rows():
        f = ((t["coach"] == coach) & (t["team"] == team)).fill_null(False).to_numpy().astype(bool)
        # la liga de cada comparación excluye los partidos del propio técnico-club (como local o rival) y los del foco
        suyos = t.filter(((pl.col("coach") == coach) & (pl.col("team") == team)) | (pl.col("coach_faced") == coach))["match_id"]
        excl = np.isin(match, suyos.unique().to_numpy()) | pfoco
        rr = spk.correr(S1, None, r, match, f, excl, m.P, None, m.mu, nt, ns, ec["a"], ec["n_min"])
        nula.append({"coach": coach, "team": team, "partidos": int(len(np.unique(match[f]))),
                     "exceso": [x["P"]["exceso"] for x in rr["familias"]], "tv": [x["P"]["tv"] for x in rr["familias"]],
                     "p_fisher": [x["P"]["p_fisher"] for x in rr["familias"]]})
    res["nula_empirica"] = nula
    for fam in res["familias"]:
        k = fam["familia"] - 1
        ex = np.array([n["exceso"][k] for n in nula if np.isfinite(n["exceso"][k])])
        fam["percentil_vs_tecnicos"] = float(100 * np.mean(ex <= fam["P"]["exceso"])) if len(ex) else None
    out = cfg.ruta("reportes") / cfg["experimentos"]["salida"] / "supuesto_pk"
    out.mkdir(parents=True, exist_ok=True)
    (out / "supuesto_pk.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))
    md = [f"# Mejora A — ¿el técnico solo mueve π_k? Prueba de score de H0: P^k_foco = P^k_liga ({foco})", "",
          "**EXPERIMENTO (ADR-v2-52), no adoptado.** Matemática en `src/dtcoach/supuesto_pk.py` y `04_MODELO_MATEMATICO.md` §15.",
          "", f"Secuencias de ataque del foco: {res['secuencias_foco']:,} en {res['partidos_foco']} partidos"
          + (f" · humo con {a.muestra} partidos de liga" if a.muestra else "") + ".", "",
          "| familia | filas probadas | p Fisher (P) | p mín. Bonferroni | exceso T/gl | TV media | ΔE[T] | ΔP(remate) | percentil entre técnicos | p Fisher (P0, 1.er toque) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for f in res["familias"]:
        P, P0 = f["P"], f.get("P0", {})
        ef = P.get("efecto", {})
        md.append(f"| {f['familia']} | {len(P['filas'])} | {P['p_fisher']:.3g} | {P['p_min_bonf']:.3g} | {P['exceso']:.2f} | "
                  f"{P['tv']:.3f} | {ef.get('dif_E_T', float('nan')):+.2f} | {100 * ef.get('dif_P_remate', float('nan')):+.1f} pp | "
                  f"{f['percentil_vs_tecnicos'] if f['percentil_vs_tecnicos'] is None else round(f['percentil_vs_tecnicos'])} | "
                  f"{P0.get('p_fisher', float('nan')):.3g} |")
    md += ["", "*exceso = ΣT/Σgl (≈ 1 bajo H0). Percentil = qué parte de los técnicos-club con ≥ "
           f"{ec['min_partidos_nula']} partidos se desvía MENOS que el foco (misma prueba). TV = distancia de variación total media "
           "de las filas probadas. ΔE[T] y ΔP(remate): efecto de cambiar P^k de la liga por la del foco (encogida).*", "",
           f"Técnicos-club de la nula empírica: {len(nula)}. Tiempo: {time.time() - t0:.0f} s."]
    (out / "SUPUESTO_PK.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
