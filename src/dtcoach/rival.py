"""
Contexto por nivel del rival (reto 5.2, G2): ¿juega igual contra fuertes y contra débiles?

ESTRATOS (03_FRAMEWORK §8)
--------------------------
Con el Elo PREVIO al partido del rival (`dtcoach elo`), sobre todos los equipo-partido
de la liga:
  fuerte   Elo del rival ≥ percentil 75
  medio    entre los percentiles 25 y 75
  debil    Elo del rival ≤ percentil 25
Los cortes son de la liga entera, no del foco: "fuerte" significa lo mismo para todos.

DOS PREGUNTAS
-------------
1. Dentro de cada estrato, foco contra liga (la liga en el MISMO estrato): así no se
   confunde "Almada" con "jugar contra un fuerte" (Taylor et al. 2008; Lago-Peñas 2012).
2. ¿Su ajuste es distinto al de la liga? Para cada métrica,
       Δ = (foco − liga)_fuerte − (foco − liga)_débil
   con error estándar de los dos bootstraps (estratos disjuntos de partidos del foco) y
   BH sobre las métricas pre-registradas (H22). Δ ≈ 0: se ajusta como todos; Δ ≠ 0:
   su idea cambia con el rival de otra forma que la de la liga.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy import stats

from .comparar import foco_vs_liga
from .inference import benjamini_hochberg

ESTRATOS = ("fuerte", "medio", "debil")
NOMBRE = {"fuerte": "rivales fuertes (Elo ≥ p75)", "medio": "rivales medios (p25–p75)",
          "debil": "rivales débiles (Elo ≤ p25)"}


def estratos(elo: pl.DataFrame, q: tuple[float, float] = (0.25, 0.75)) -> tuple[pl.DataFrame, dict]:
    """`elo`: match_id, team, elo, elo_rival (previos). Devuelve match_id, team, estrato."""
    lo, hi = (float(elo["elo_rival"].quantile(x)) for x in q)
    e = elo.select("match_id", "team", pl.when(pl.col("elo_rival") >= hi).then(pl.lit("fuerte"))
                   .when(pl.col("elo_rival") <= lo).then(pl.lit("debil")).otherwise(pl.lit("medio")).alias("estrato"))
    return e, {"p25": lo, "p75": hi}


def por_estrato(M: pl.DataFrame, est: pl.DataFrame, metricas: list[str], foco: str, lado: str = "propio",
                n_boot: int = 1000, seed: int = 0) -> dict:
    """foco contra liga dentro de cada estrato del RIVAL del foco.
    lado "propio": cada fila es un equipo atacando; su estrato es el nivel de SU rival.
    lado "rival": cada fila es lo que le hacen a un equipo; el estrato es el nivel de quien
    ataca (el de la fila), que es el estrato de la fila de su rival."""
    if lado == "rival":
        e2 = est.rename({"team": "rival"})
        X = M.join(e2, on=["match_id", "rival"], how="left")
    else:
        X = M.join(est, on=["match_id", "team"], how="left")
    ms = [m for m in metricas if f"{m}__n" in X.columns]
    out = {}
    for e in ESTRATOS:
        sub = X.filter(pl.col("estrato") == e)
        try:
            out[e] = foco_vs_liga(sub, ms, foco, lado, n_boot, seed)
        except ValueError:
            out[e] = {}
    return out


def ajuste_distinto(res: dict, metricas: list[str], alpha: float = 0.05) -> dict:
    """Δ = (foco − liga)_fuerte − (foco − liga)_débil, z con los IC de cada estrato, BH (H22)."""
    filas = {}
    for m in metricas:
        a, b = res.get("fuerte", {}).get(m), res.get("debil", {}).get(m)
        if not a or not b or not all(np.isfinite([a["dif"], b["dif"], a["lo"], a["hi"], b["lo"], b["hi"]])):
            continue
        se = np.hypot((a["hi"] - a["lo"]) / 3.92, (b["hi"] - b["lo"]) / 3.92)
        d = a["dif"] - b["dif"]
        z = d / se if se > 0 else 0.0
        filas[m] = {"delta": float(d), "lo": float(d - 1.96 * se), "hi": float(d + 1.96 * se),
                    "p": float(2 * stats.norm.sf(abs(z))), "fuerte": a["dif"], "debil": b["dif"]}
    if filas:
        q, rech = benjamini_hochberg(np.array([v["p"] for v in filas.values()]), alpha)
        for (m, v), qi, ri in zip(filas.items(), q, rech):
            v["q"] = float(qi)
            v["etiqueta"] = "🟢" if ri else ("🟡" if v["p"] < alpha else "⚪")
    return filas


def puntos_por_estrato(x: pl.DataFrame, est: pl.DataFrame, foco: str, n_boot: int = 1000, seed: int = 0) -> dict:
    """Puntos y diferencia de xG por partido del foco en cada estrato, contra la liga en el mismo.
    `x`: de `simulador.xpts_por_equipo_partido` (match_id, team, coach, pts, xG, xG_rival)."""
    X = x.join(est, on=["match_id", "team"], how="left")
    rival_coach = X.select("match_id", pl.col("team").alias("_t2"), pl.col("coach").alias("coach_rival"))
    X = X.join(rival_coach, on="match_id").filter(pl.col("_t2") != pl.col("team"))
    partidos_foco = X.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique()
    rng = np.random.default_rng(seed)
    out = {}
    for e in ESTRATOS:
        s = X.filter(pl.col("estrato") == e)
        f = s.filter(pl.col("coach") == foco)
        lg = s.filter(~pl.col("match_id").is_in(partidos_foco.to_list()))
        if f.height == 0:
            continue
        r = {"partidos": f.height}
        for c, v in (("pts", "pts"), ("xg_dif", None)):
            vf = f["pts"].to_numpy() if v else (f["xG"] - f["xG_rival"]).to_numpy()
            vl = lg["pts"].to_numpy() if v else (lg["xG"] - lg["xG_rival"]).to_numpy()
            b = [rng.choice(vf, len(vf)).mean() - rng.choice(vl, len(vl)).mean() for _ in range(n_boot)]
            r[c] = {"foco": float(vf.mean()), "liga": float(vl.mean()), "dif": float(vf.mean() - vl.mean()),
                    "lo": float(np.quantile(b, 0.025)), "hi": float(np.quantile(b, 0.975))}
        out[e] = r
    return out


def tabla_md(res: dict, defs: dict, metricas: list[str], ajuste: dict | None = None) -> str:
    L = ["| métrica | " + " | ".join(NOMBRE[e] for e in ESTRATOS) + " | ¿ajuste distinto al de la liga? (H22) |",
         "|---|" + "---|" * (len(ESTRATOS) + 1)]
    for m in metricas:
        celdas = []
        for e in ESTRATOS:
            v = res.get(e, {}).get(m)
            if not v or not np.isfinite(v["foco"]):
                celdas.append("—")
                continue
            fmt = defs.get(m, {}).get("formato", "{:.3f}")
            celdas.append(f"{fmt.format(v['foco'])} vs {fmt.format(v['liga'])} ({v['dif']:+.3f})")
        a = (ajuste or {}).get(m)
        aj = f"Δ {a['delta']:+.3f} [{a['lo']:+.3f}, {a['hi']:+.3f}] {a['etiqueta']}" if a else "—"
        L.append(f"| {defs.get(m, {}).get('nombre', m)} | " + " | ".join(celdas) + f" | {aj} |")
    return "\n".join(L)
