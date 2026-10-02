"""
EXPERIMENTO (ADR-v2-56, no adoptado): partir «portero y definición» de la Prop. 16.6 con xGOT.

El cuarto término de la descomposición exacta, s_i (F_i − g_i), junta dos cosas: el remate que el
atacante mandó fuera (falla de DEFINICIÓN) y el remate a puerta que el portero atajó (mérito del
PORTERO). Con la ubicación del remate en el plano de la portería se separan:

    xGOT_i = Σ_remates E[G | remate a puerta, ubicación (y, z) en el marco, calidad previa]   (0 si va fuera)
    definición = s_i (F_i − xGOT_i)        portero = s_i (xGOT_i − g_i)

La suma es s_i (F_i − g_i): la descomposición sigue EXACTA, ahora en cinco términos.

DATOS
-----
StatsBomb da `shot.end_location = [x, y, z]`: z es la altura al cruzar la línea de meta y SOLO viene
cuando el balón llega a la portería (los remates fuera por un lado o bloqueados no la traen). «A puerta»
se deduce de `shot.outcome` ∈ {Goal, Saved, Saved to Post}: StatsBomb no trae un booleano aparte.
Si los remates a puerta no traen z, NO se inventa nada con la (x, y) en la cancha: `disponibilidad`
lo dice y el script se detiene.

MODELO
------
Logit L2 sobre los remates a puerta de toda la liga, fuera de muestra (pliegues por partido, como las dos
capas del xDefense): ubicación en el marco (u = |y − 40| / 4 desde el centro, v = z / 2.67 de alto; sus
cuadrados, su producto y las esquinas) y la calidad previa del remate (logit del xG con que entra en F, y
cabeza). Así xGOT ≥ xG en las esquinas y ≤ xG al centro, que es lo que separa portero de definición.

Remate a puerta sin z (raro si la verificación pasa): entra con su propio xG en xGOT, neutro para la
definición. Remate fuera: xGOT = 0.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .xdefensa import auc, coeficientes, fuera_de_muestra

A_PUERTA = ("Goal", "Saved", "Saved to Post")
POSTE_Y = (36.0, 44.0)          # StatsBomb: arco de 8 yardas centrado en y = 40
ALTO = 2.67                     # 8 pies en yardas
COMP5 = ("prev", "lej", "sup", "def", "portero", "total")
COMP5_NOMBRE = {"prev": "prevención (remates negados)", "lej": "alejamiento (remates desde peores lugares)",
                "sup": "supresión (geometría al remate)", "def": "definición (remate fuera de lo esperado a puerta)",
                "portero": "portero (atajadas por encima de lo esperado)", "total": "total"}


def remates(ev_lazy: pl.LazyFrame) -> pl.DataFrame:
    """Todos los remates con su end_location completo y su resultado (del parquet de eventos crudo)."""
    cols = ev_lazy.collect_schema().names()
    st = pl.col("shot_type") if "shot_type" in cols else pl.lit(None, pl.Utf8)
    bp = pl.col("shot_body_part") if "shot_body_part" in cols else pl.lit(None, pl.Utf8)
    e = (ev_lazy.filter(pl.col("type") == "Shot")
         .select("match_id", "id", "shot_end_location", "shot_outcome", st.alias("shot_type"),
                 pl.col("shot_statsbomb_xg").cast(pl.Float64).alias("xg_sb"), bp.alias("parte"))
         .collect())
    loc = e["shot_end_location"]
    if loc.dtype == pl.Utf8:              # algunos volcados guardan la lista como texto
        loc = loc.str.strip_chars("[] ").str.split(",").list.eval(pl.element().str.strip_chars().cast(pl.Float64))
    return e.with_columns(
        loc.list.len().alias("n_end"),
        loc.list.get(1, null_on_oob=True).cast(pl.Float64).alias("end_y"),
        loc.list.get(2, null_on_oob=True).cast(pl.Float64).alias("end_z"),
        pl.col("shot_outcome").is_in(list(A_PUERTA)).fill_null(False).alias("a_puerta"),
        (pl.col("shot_outcome") == "Goal").fill_null(False).alias("gol"),
        (pl.col("parte") == "Head").fill_null(False).cast(pl.Float64).alias("cabeza"),
    ).drop("shot_end_location", "parte")


def disponibilidad(r: pl.DataFrame, min_frac: float = 0.9) -> dict:
    """¿Viene la ubicación en el plano de la portería? Sin penales. `ok` exige que ≥ `min_frac` de los
    remates A PUERTA traigan z y que la (y, z) caiga en el marco (con tolerancia)."""
    s = r.filter((pl.col("shot_type") != "Penalty").fill_null(True))
    ap = s.filter(pl.col("a_puerta"))
    conz = ap.filter(pl.col("end_z").is_not_null() & pl.col("end_y").is_not_null())
    en_marco = conz.filter(pl.col("end_y").is_between(POSTE_Y[0] - 0.5, POSTE_Y[1] + 0.5)
                           & pl.col("end_z").is_between(-0.1, ALTO + 0.3))
    res = {"remates": s.height, "con_3_coordenadas": int((s["n_end"] >= 3).sum()),
           "a_puerta": ap.height, "a_puerta_con_z": conz.height,
           "frac_a_puerta_con_z": conz.height / max(ap.height, 1),
           "frac_con_z_en_marco": en_marco.height / max(conz.height, 1),
           "fuera_con_z": int(s.filter(~pl.col("a_puerta") & pl.col("end_z").is_not_null()).height),
           "resultados": dict(s.group_by("shot_outcome").len().sort("len", descending=True).iter_rows()),
           "z_p01_p50_p99": [float(x) for x in np.nanpercentile(conz["end_z"].to_numpy(), [1, 50, 99])] if conz.height else [],
           "y_p01_p50_p99": [float(x) for x in np.nanpercentile(conz["end_y"].to_numpy(), [1, 50, 99])] if conz.height else [],
           "z_distintos": int(conz["end_z"].n_unique()) if conz.height else 0}
    res["ok"] = bool(ap.height > 0 and res["frac_a_puerta_con_z"] >= min_frac and res["frac_con_z_en_marco"] >= 0.9
                     and res["z_distintos"] > 10)
    return res


def diseno(r: pl.DataFrame, xg_previo: np.ndarray) -> tuple[np.ndarray, list[str]]:
    u = np.clip(np.abs(r["end_y"].to_numpy() - 40.0) / 4.0, 0, 1.5)
    v = np.clip(r["end_z"].to_numpy() / ALTO, 0, 1.5)
    q = np.clip(xg_previo, 1e-4, 1 - 1e-4)
    X = np.column_stack([u, v, u ** 2, v ** 2, u * v, (u > 0.75).astype(float), (v > 0.75).astype(float),
                         ((u > 0.75) & (v > 0.75)).astype(float), (v < 0.25).astype(float),
                         np.log(q / (1 - q)), r["cabeza"].to_numpy()])
    return X, ["|y−40|", "altura", "|y−40|²", "altura²", "|y−40|·altura", "cerca del palo", "arriba", "esquina alta",
               "a ras", "logit xG previo", "cabeza"]


def ajustar(r: pl.DataFrame, xg_previo: dict, folds: int = 5, lam: float = 1.0, seed: int = 0) -> tuple[pl.DataFrame, dict]:
    """xGOT por remate, fuera de muestra. `xg_previo`: {id: xG con que el remate entra en F}
    (xg_full si tiene foto 360, xg_sb si no). Devuelve id, xgot, f_previo y diagnósticos."""
    f = np.array([xg_previo.get(i, x if x is not None else 0.0) for i, x in zip(r["id"].to_list(), r["xg_sb"].to_list())],
                 dtype=float)
    r = r.with_columns(pl.Series("f_previo", f))
    usar = r.filter(pl.col("a_puerta") & pl.col("end_z").is_not_null() & pl.col("end_y").is_not_null()
                    & (pl.col("shot_type") != "Penalty").fill_null(True))
    X, nom = diseno(usar, usar["f_previo"].to_numpy())
    y = usar["gol"].cast(pl.Float64).to_numpy()
    p = fuera_de_muestra(X, y, usar["match_id"].to_numpy(), folds, lam, seed)
    # referencia: el propio xG previo como predictor de gol en los mismos remates a puerta
    diag = {"remates_a_puerta_modelo": usar.height, "goles": int(y.sum()), "tasa_gol": float(y.mean()),
            "auc_xgot": auc(p, y), "auc_xg_previo": auc(usar["f_previo"].to_numpy(), y),
            "calibracion": float(p.mean() / max(y.mean(), 1e-12)),
            "coeficientes": coeficientes(X, y, nom, lam)}
    xgot = dict(zip(usar["id"].to_list(), p.tolist()))
    # a puerta con z → modelo; fuera → 0; a puerta sin z (o penal) → su propio xG previo (neutro para la definición)
    out = r.with_columns(pl.Series("xgot", [xgot[i] if i in xgot else (0.0 if not ap else fp) for i, ap, fp in
                                            zip(r["id"].to_list(), r["a_puerta"].to_list(), f.tolist())]))
    return out.select("match_id", "id", "a_puerta", "gol", "f_previo", "xgot"), diag


def partir(D: pl.DataFrame, j: pl.DataFrame, rx: pl.DataFrame) -> pl.DataFrame:
    """Agrega a la descomposición por saque (`xdefensa.descomposicion`) X = Σ xGOT de sus remates y los
    términos def y portero. Los remates del saque que no estén en `rx` entran neutros (su parte de F)."""
    rem = (j.select("id_saque", "ids_remate").explode("ids_remate", empty_as_null=True).rename({"ids_remate": "id"})
           .filter(pl.col("id").is_not_null()).join(rx.select("id", "xgot", "f_previo"), on="id", how="left")
           .group_by("id_saque").agg(pl.col("xgot").sum().alias("_x"), pl.col("f_previo").sum().alias("_fk")))
    d = D.join(rem, on="id_saque", how="left").with_columns(pl.col("_x").fill_null(0.0), pl.col("_fk").fill_null(0.0))
    s = pl.col("s")
    X = pl.when(s > 0).then(pl.col("_x") + (pl.col("F") - pl.col("_fk"))).otherwise(0.0)    # remates sin dato: neutros
    return d.with_columns(X.alias("X")).drop("_x", "_fk").with_columns(
        (s * (pl.col("F") - pl.col("X"))).alias("def"), (s * (pl.col("X") - pl.col("g"))).alias("portero"))


def error_exactitud(d: pl.DataFrame) -> float:
    """máx |prev + lej + sup + def + portero − (p κ − g)| sobre los saques."""
    lhs = d["prev"] + d["lej"] + d["sup"] + d["def"] + d["portero"]
    rhs = d["p"] * d["kappa"] - d["g"]
    return float((lhs - rhs).abs().max()) if d.height else 0.0


def metricas(d: pl.DataFrame, tp: pl.DataFrame, familias: dict) -> list[pl.DataFrame]:
    """Por equipo-partido, goles por 100 saques: xd_<def|portero>_<familia> (del que defiende) y xo_ (= −xd,
    del que saca). Mismo formato __n/__d que `xdefensa.metricas_descomposicion`."""
    rival = tp.select("match_id", "team", "rival")
    dd = d.join(rival, on=["match_id", "team"]).drop("team").rename({"rival": "team"})
    out = []
    for fam, ts in {**familias, "todas": None}.items():
        for lado, df, sg in (("xd", dd, 100.0), ("xo", d, -100.0)):
            x = df if ts is None else df.filter(pl.col("tipo").is_in(list(ts)))
            out.append(x.group_by("match_id", "team").agg(
                *[(sg * pl.col(c).sum()).alias(f"{lado}_{c}_{fam}__n") for c in ("port", "def", "portero")],
                *[pl.len().cast(pl.Float64).alias(f"{lado}_{c}_{fam}__d") for c in ("port", "def", "portero")]))
    return out
