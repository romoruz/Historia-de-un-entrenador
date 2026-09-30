"""
Capa de fútbol -- el motor de comparación que usan todas las métricas (fases B–E).

CADA MÉTRICA ES UNA RAZÓN DE SUMAS POR EQUIPO-PARTIDO
-----------------------------------------------------
Una métrica m tiene, por equipo-partido, un numerador y un denominador
(`m__n`, `m__d`). Su valor para un grupo de partidos es Σ n / Σ d: "por partido"
si d = 1, "por pase", "por corner", etc. si d cuenta oportunidades. Así una sola
maquinaria sirve para todo y el bootstrap es exacto para razones de sumas.

TRES PREGUNTAS, SIEMPRE LAS MISMAS
----------------------------------
1. Foco contra liga (`foco_vs_liga`). Foco: los equipo-partido de su técnico
   (lado "propio") o los de sus RIVALES contra él (lado "rival": lo que le hacen).
   Liga: los equipo-partido de partidos donde el foco no jugó (ADR-v2-22). IC por
   bootstrap estratificado por PARTIDO (ADR-v2-04), p bilateral por bootstrap.
2. Dónde cae entre todos los técnicos (`por_era`, `percentil`): la misma razón
   para cada técnico-club con suficientes partidos. Es la comparación con OTROS
   técnicos que pide el reto, sin elegir a mano contra quién.
3. ¿Es un rasgo o es ruido? (`fiabilidad`): partidos de cada técnico-club en dos
   mitades (pares e impares por fecha); correlación entre técnicos de la métrica
   en una mitad y en la otra, con la corrección de Spearman-Brown. Una métrica que
   no se repite entre mitades no describe a un técnico, por significativa que salga.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .inference import benjamini_hochberg


def valor(df: pl.DataFrame, m: str) -> float:
    d = float(df[f"{m}__d"].sum())
    return float(df[f"{m}__n"].sum()) / d if d > 0 else float("nan")


def _filas(M: pl.DataFrame, foco: str, lado: str, club: str | None = None) -> tuple[pl.DataFrame, pl.DataFrame]:
    col = "coach" if lado == "propio" else "coach_rival"
    f = M.filter(pl.col(col) == foco)
    if club is not None:
        f = f.filter(pl.col("team" if lado == "propio" else "rival") == club)
    partidos_foco = M.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique()
    liga = M.filter(~pl.col("match_id").is_in(partidos_foco.to_list()) & pl.col("coach").is_not_null())
    return f, liga


def _sumas(df: pl.DataFrame, metricas: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    agg = [pl.col(f"{m}__n").sum() for m in metricas] + [pl.col(f"{m}__d").sum() for m in metricas]
    g = df.group_by("match_id").agg(agg).sort("match_id")
    k = len(metricas)
    A = g.select([f"{m}__n" for m in metricas] + [f"{m}__d" for m in metricas]).to_numpy().astype(float)
    return g["match_id"].to_numpy(), A[:, :k], A[:, k:]


def foco_vs_liga(M: pl.DataFrame, metricas: list[str], foco: str, lado: str = "propio",
                 n_boot: int = 2000, seed: int = 0, club: str | None = None) -> dict:
    """Por métrica: valor del foco, de la liga, diferencia, IC 95 % y p por bootstrap de partidos.
    `club`: solo la etapa del foco en ese club (la liga de referencia no cambia)."""
    f, liga = _filas(M, foco, lado, club)
    if f.height == 0:
        raise ValueError(f"«{foco}» no tiene equipo-partido (lado {lado})")
    _, Fn, Fd = _sumas(f, metricas)
    _, Ln, Ld = _sumas(liga, metricas)
    with np.errstate(invalid="ignore", divide="ignore"):
        vf, vl = Fn.sum(0) / Fd.sum(0), Ln.sum(0) / Ld.sum(0)
        rng = np.random.default_rng(seed)
        D = np.empty((n_boot, len(metricas)))
        for b in range(n_boot):
            i = rng.integers(0, len(Fn), len(Fn))
            j = rng.integers(0, len(Ln), len(Ln))
            D[b] = Fn[i].sum(0) / Fd[i].sum(0) - Ln[j].sum(0) / Ld[j].sum(0)
    out = {}
    for c, m in enumerate(metricas):
        d = D[:, c][np.isfinite(D[:, c])]
        p = float(min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean()))) if len(d) else float("nan")
        out[m] = {"foco": float(vf[c]), "liga": float(vl[c]), "dif": float(vf[c] - vl[c]),
                  "lo": float(np.quantile(d, 0.025)) if len(d) else float("nan"),
                  "hi": float(np.quantile(d, 0.975)) if len(d) else float("nan"),
                  "p": max(p, 1.0 / n_boot) if len(d) else float("nan"),
                  "partidos_foco": len(Fn), "partidos_liga": len(Ln), "lado": lado}
    return out


def etiquetar(res: dict, alpha: float = 0.05, min_partidos: int = 20) -> dict:
    """BH sobre las métricas de un bloque; 🟢 q < alpha, 🟡 p < alpha, ⚪ no detectado.
    Con menos de `min_partidos` del foco no hay 🟢 (ADR-v2-28)."""
    claves = [k for k in res if np.isfinite(res[k]["p"])]
    if not claves:
        return res
    q, rech = benjamini_hochberg(np.array([res[k]["p"] for k in claves]), alpha)
    for k, qi, ri in zip(claves, q, rech):
        pocos = res[k]["partidos_foco"] < min_partidos
        res[k]["q"] = float(qi)
        res[k]["etiqueta"] = ("🟡" if res[k]["p"] < alpha else "⚪") if pocos else \
                             ("🟢" if ri else ("🟡" if res[k]["p"] < alpha else "⚪"))
    return res


def por_era(M: pl.DataFrame, metricas: list[str], lado: str = "propio", min_partidos: int = 30) -> pl.DataFrame:
    """Una fila por técnico-club con ≥ `min_partidos`: la razón de sumas de cada métrica."""
    coach, team = ("coach", "team") if lado == "propio" else ("coach_rival", "rival")
    g = (M.filter(pl.col(coach).is_not_null())
         .group_by(coach, team).agg(pl.col("match_id").n_unique().alias("partidos"),
                                    *[pl.col(f"{m}__n").sum() for m in metricas],
                                    *[pl.col(f"{m}__d").sum() for m in metricas])
         .filter(pl.col("partidos") >= min_partidos))
    return g.select(pl.col(coach).alias("coach"), pl.col(team).alias("team"), "partidos",
                    *[(pl.col(f"{m}__n") / pl.col(f"{m}__d")).alias(m) for m in metricas])


def percentil(eras: pl.DataFrame, m: str, foco: str) -> list[dict]:
    """Percentil (0–100) de cada etapa del foco entre todas las etapas, en la métrica m."""
    v = eras[m].drop_nulls().to_numpy()
    out = []
    for r in eras.filter(pl.col("coach") == foco).iter_rows(named=True):
        if r[m] is None or not np.isfinite(r[m]):
            continue
        out.append({"team": r["team"], "valor": float(r[m]), "partidos": int(r["partidos"]),
                    "percentil": float(100 * (np.sum(v < r[m]) + 0.5 * np.sum(v == r[m])) / len(v)),
                    "etapas": len(v)})
    return out


def fiabilidad(M: pl.DataFrame, metricas: list[str], lado: str = "propio", min_partidos: int = 30) -> dict:
    """Spearman-Brown de la correlación entre mitades (partidos pares e impares por fecha)."""
    coach, team = ("coach", "team") if lado == "propio" else ("coach_rival", "rival")
    orden = "match_date" if "match_date" in M.columns else "match_id"
    X = (M.filter(pl.col(coach).is_not_null()).sort(orden)
         .with_columns((pl.col("match_id").rank("ordinal").over(coach, team) % 2).alias("_mitad"),
                       pl.col("match_id").n_unique().over(coach, team).alias("_n"))
         .filter(pl.col("_n") >= min_partidos))
    g = X.group_by(coach, team, "_mitad").agg(*[pl.col(f"{m}__n").sum() for m in metricas],
                                              *[pl.col(f"{m}__d").sum() for m in metricas])
    out = {}
    for m in metricas:
        w = (g.with_columns((pl.col(f"{m}__n") / pl.col(f"{m}__d")).alias("v"))
             .pivot(on="_mitad", index=[coach, team], values="v").drop_nulls())
        if w.height < 5 or "0" not in w.columns or "1" not in w.columns:
            out[m] = {"r": float("nan"), "spearman_brown": float("nan"), "etapas": int(w.height)}
            continue
        a, b = w["0"].to_numpy(), w["1"].to_numpy()
        ok = np.isfinite(a) & np.isfinite(b)
        r = float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() >= 5 else float("nan")
        out[m] = {"r": r, "spearman_brown": float(2 * r / (1 + r)) if np.isfinite(r) and r > -1 else float("nan"),
                  "etapas": int(ok.sum())}
    return out


def tabla(res: dict, fiab: dict | None, pct: dict | None, defs: dict) -> str:
    """Tabla markdown: métrica, foco, liga, diferencia [IC], percentil entre etapas, fiabilidad, etiqueta."""
    L = ["| métrica | foco | liga | diferencia [IC 95 %] | percentil entre técnicos | fiabilidad | evidencia |",
         "|---|---|---|---|---|---|---|"]
    for m, r in res.items():
        fmt = defs.get(m, {}).get("formato", "{:.3f}")
        if not (np.isfinite(r["foco"]) and np.isfinite(r["liga"])):
            L.append(f"| {defs.get(m, {}).get('nombre', m)} | sin datos | | | | | |")
            continue
        pc = "; ".join(f"{p['team']}: {p['percentil']:.0f}" for p in (pct or {}).get(m, [])) or "—"
        sb = (fiab or {}).get(m, {}).get("spearman_brown", float("nan"))
        L.append(f"| {defs.get(m, {}).get('nombre', m)} | {fmt.format(r['foco'])} | {fmt.format(r['liga'])} | "
                 f"{r['dif']:+.3f} [{r['lo']:+.3f}, {r['hi']:+.3f}] | {pc} | "
                 f"{'—' if not np.isfinite(sb) else ('< 0' if sb < 0 else f'{sb:.2f}')} | {r.get('etiqueta', '')} |")
    return "\n".join(L)
