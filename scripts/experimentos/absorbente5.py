#!/usr/bin/env python3
"""
Mejora F (ADR-v2-60, EXPERIMENTO) — COMPUERTA: ¿cuánta de la masa de PÉRDIDA es en realidad una interrupción
A FAVOR (falta recibida, córner, lateral o penal para el mismo equipo)?

Una falta recibida no es acción (Def. 1.1): si la secuencia termina por ella, muere por la absorción terminal
(Def. 1.3) y cae en PÉRDIDA. Antes de tocar el espacio de estados o el EM se mide cuántas secuencias que terminan en
PÉRDIDA siguen así:

  la PRIMERA acción (Pase, Conducción o Remate, de cualquier equipo) después de la última acción de la secuencia es
  del MISMO equipo y es un balón parado (pass_type ∈ {Free Kick, Corner, Throw-in} o shot_type ∈ {Free Kick,
  Penalty}), o entre ambas hay un `Foul Won` del mismo equipo.

Regla (ADR-v2-60): si esa fracción de la masa de PÉRDIDA es < 3 %, la mejora se marca NO RENTABLE y no se reajusta
nada. Solo si pasa se implementa el quinto absorbente (config/absorbente5.yaml).

Uso:  python scripts/experimentos/absorbente5.py [--muestra N]
Salida: reports/experimentos/absorbente5/{COMPUERTA.md, compuerta.json}
"""
import argparse
import json
import time

import numpy as np
import polars as pl

from dtcoach import ingest
from dtcoach.cli import _space, _trans
from dtcoach.config import Config

PARADO_PASE = ("Free Kick", "Corner", "Throw-in")
PARADO_REMATE = ("Free Kick", "Penalty")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/exp_mejoras.yaml")
    ap.add_argument("--muestra", type=int, default=0)
    ap.add_argument("--umbral", type=float, default=0.03)
    a = ap.parse_args()
    t0 = time.time()
    cfg = Config.load(a.config)
    out = cfg.ruta("reportes") / cfg["experimentos"]["salida"] / "absorbente5"
    out.mkdir(parents=True, exist_ok=True)
    space = _space(cfg)
    LOSS = space.absorbing_index("LOSS")
    trans = _trans(cfg)
    if a.muestra:
        u = np.unique(trans["match_id"].to_numpy())
        keep = np.random.default_rng(cfg["seed"]).choice(u, min(a.muestra, len(u)), replace=False).tolist()
        trans = trans.filter(pl.col("match_id").is_in(keep))
    uid = "seq_uid" if "seq_uid" in trans.columns else "poss_uid"
    n_seq = trans[uid].n_unique()
    # la secuencia, cómo terminó y su última acción REAL (la terminal es artificial: índice + 1)
    fin = (trans.sort(uid, "event_index").group_by(uid, maintain_order=True)
           .agg(pl.col("match_id").first(), pl.col("team").first(), pl.col("to_state").last().alias("fin"),
                pl.col("action_type").last().alias("ultimo_tipo"),
                pl.col("event_index").filter(pl.col("action_type") != "TERMINAL").max().alias("ult")))
    perd = fin.filter(pl.col("fin") == LOSS).with_columns(
        pl.when(pl.col("ultimo_tipo") == "TERMINAL").then(pl.lit("terminal (la posesión se acabó sin evento propio)"))
        .when(pl.col("ultimo_tipo") == "Pass").then(pl.lit("pase perdido"))
        .otherwise(pl.lit("acción sin destino (conducción truncada u otra)")).alias("como"))
    ids = perd["match_id"].unique().to_list()
    ev = (ingest.scan_events(cfg.ruta("eventos_parquet")).filter(pl.col("match_id").is_in(ids))
          .select("match_id", "index", "type", "team", "pass_type", "shot_type").collect())
    mov = (ev.filter(pl.col("type").is_in(["Pass", "Carry", "Shot"]))
           .select("match_id", pl.col("index").alias("sig_idx"), pl.col("team").alias("sig_team"),
                   pl.col("type").alias("sig_tipo"), "pass_type", "shot_type").sort("match_id", "sig_idx"))
    faltas = (ev.filter(pl.col("type") == "Foul Won")
              .select("match_id", pl.col("team"), pl.col("index").alias("falta_idx")).sort("match_id", "team", "falta_idx"))
    p = perd.with_columns((pl.col("ult") + 1).alias("desde")).sort("match_id", "desde")
    p = p.join_asof(mov.with_columns(pl.col("sig_idx").alias("desde_m")), left_on="desde", right_on="desde_m",
                    by="match_id", strategy="forward", check_sortedness=False)
    p = p.sort("match_id", "team", "desde").join_asof(faltas.with_columns(pl.col("falta_idx").alias("desde_f")),
                                                     left_on="desde", right_on="desde_f", by=["match_id", "team"], check_sortedness=False,
                                                     strategy="forward")
    mismo = (pl.col("sig_team") == pl.col("team")).fill_null(False)
    parado = (((pl.col("sig_tipo") == "Pass") & pl.col("pass_type").is_in(list(PARADO_PASE)))
              | ((pl.col("sig_tipo") == "Shot") & pl.col("shot_type").is_in(list(PARADO_REMATE)))).fill_null(False)
    falta = (pl.col("falta_idx").is_not_null() & (pl.col("sig_idx").is_null() | (pl.col("falta_idx") < pl.col("sig_idx"))))
    p = p.with_columns((mismo & parado).alias("_parado"), falta.alias("_falta")).with_columns(
        (pl.col("_parado") | pl.col("_falta")).alias("a_favor"),
        pl.when(mismo & parado).then(pl.coalesce(pl.col("pass_type"), pl.col("shot_type")))
        .when(pl.col("_falta")).then(pl.lit("falta recibida (sin balón parado propio inmediato)"))
        .otherwise(pl.lit(None)).alias("reanuda"))
    n_p = p.height
    n_f = int(p["a_favor"].sum())
    frac = n_f / max(n_p, 1)
    por_como = (p.group_by("como").agg(pl.len().alias("perdidas"), pl.col("a_favor").sum().alias("a_favor"))
                .with_columns((pl.col("a_favor") / pl.col("perdidas")).alias("frac")).sort("perdidas", descending=True))
    por_reanuda = p.filter(pl.col("a_favor")).group_by("reanuda").len().sort("len", descending=True)
    rentable = frac >= a.umbral
    res = {"muestra": a.muestra or None, "secuencias": n_seq, "perdidas": n_p, "frac_perdida_de_todas": n_p / n_seq,
           "a_favor": n_f, "frac_de_la_perdida": frac, "frac_de_todas": n_f / n_seq, "umbral": a.umbral,
           "rentable": bool(rentable), "por_como": por_como.to_dicts(), "por_reanuda": por_reanuda.to_dicts(),
           "foul_won_en_datos": int(ev.filter(pl.col("type") == "Foul Won").height)}
    (out / "compuerta.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))
    md = ["# Mejora F — compuerta: ¿cuánta PÉRDIDA es una interrupción a favor? (ADR-v2-60)", "",
          (f"**HUMO** con {a.muestra} partidos." if a.muestra else ""), "",
          f"- secuencias: {n_seq:,}; terminan en PÉRDIDA: {n_p:,} ({100 * n_p / n_seq:.1f} %)",
          f"- de ellas, **interrupción a favor: {n_f:,} = {100 * frac:.2f} % de la masa de PÉRDIDA** "
          f"({100 * n_f / n_seq:.2f} % de todas las secuencias)",
          f"- eventos `Foul Won` en los partidos: {res['foul_won_en_datos']:,}", "",
          "| cómo terminó en PÉRDIDA | secuencias | a favor | % |", "|---|---|---|---|"]
    md += [f"| {r['como']} | {r['perdidas']:,} | {r['a_favor']:,} | {100 * r['frac']:.2f} |" for r in por_como.to_dicts()]
    md += ["", "| cómo se reanuda (las a favor) | secuencias |", "|---|---|"]
    md += [f"| {r['reanuda']} | {r['len']:,} |" for r in por_reanuda.to_dicts()]
    md += ["", (f"**Veredicto: {'PASA' if rentable else 'NO RENTABLE'}** (umbral {100 * a.umbral:.0f} % de la masa de PÉRDIDA). "
                + ("Se implementa el quinto absorbente." if rentable else
                   "No se reajusta el EM ni se toca el espacio de estados.")), "", f"Tiempo: {time.time() - t0:.0f} s."]
    (out / "COMPUERTA.md").write_text("\n".join(x for x in md if x is not None), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
