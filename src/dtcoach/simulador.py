"""
Fase 3b -- Simulador (exploratorio).

1. PUNTOS ESPERADOS, exactos y sin simular. Cada remate i es un Bernoulli(xG_i),
   asi que los goles de un equipo siguen una Poisson-binomial:
       f_s(k) = f_{s-1}(k) (1 - p_s) + f_{s-1}(k-1) p_s
   Con los dos equipos independientes, P(gana), P(empata), P(pierde) salen de la
   convolucion, y xPts = 3 P(gana) + P(empata). La varianza de los puntos por
   partido tambien es exacta, asi que la suma sobre N partidos tiene media y
   varianza conocidas.
   Mide SUERTE Y DEFINICION (goles contra xG), no estilo.

2. ESCENARIOS: el modelo de contexto de la fase 2 hacia adelante. Para un
   escenario (marcador, minuto, localia, rival), la mezcla de familias que usa
   el equipo del foco y la que usaria la liga EN ESE MISMO escenario, con sus
   propias secuencias (origenes y temporadas) como base. xG por secuencia =
   sum_k pi_k · xG_k, con xG_k la eficiencia medida dentro de cada familia.
   Supuesto declarado: la eficiencia dentro de cada familia no depende del contexto.

3. CALIBRACION del modelo de contexto: por celda de contexto con suficientes
   secuencias del foco, pi predicha contra responsabilidad media observada.
"""
from __future__ import annotations

import itertools

import numpy as np
import polars as pl


# ----------------------------------------------------------------------
# 1. Poisson-binomial y puntos esperados
# ----------------------------------------------------------------------
def poisson_binomial(p: np.ndarray) -> np.ndarray:
    f = np.zeros(len(p) + 1)
    f[0] = 1.0
    for s, ps in enumerate(p, start=1):
        f[1:s + 1] = f[1:s + 1] * (1 - ps) + f[:s] * ps
        f[0] *= 1 - ps
    return f


def resultado_esperado(xg_a: np.ndarray, xg_b: np.ndarray) -> dict:
    fa, fb = poisson_binomial(np.asarray(xg_a, float)), poisson_binomial(np.asarray(xg_b, float))
    J = np.outer(fa, fb)                         # J[i, j] = P(A = i, B = j)
    i, j = np.indices(J.shape)
    pg, pe, pp = J[i > j].sum(), J[i == j].sum(), J[i < j].sum()
    ptos = 3 * pg + pe
    var = 9 * pg + pe - ptos ** 2
    return {"P_gana": pg, "P_empata": pe, "P_pierde": pp, "xPts": ptos, "var_pts": var,
            "xG": float(np.sum(xg_a)), "xG_rival": float(np.sum(xg_b))}


def xpts_por_equipo_partido(lf: pl.LazyFrame, tp: pl.DataFrame) -> pl.DataFrame:
    """Una fila por equipo-partido: xPts exactos y puntos reales a 90'."""
    ev = lf.select("match_id", "period", "type", "team", "shot_statsbomb_xg", "shot_outcome").filter(
        (pl.col("period") <= 2) & pl.col("type").is_in(["Shot", "Own Goal For"])).collect()
    remates = ev.filter(pl.col("type") == "Shot").group_by("match_id", "team").agg(
        pl.col("shot_statsbomb_xg").fill_null(0.0).alias("xgs"),
        (pl.col("shot_outcome") == "Goal").sum().alias("goles"))
    autogoles = ev.filter(pl.col("type") == "Own Goal For").group_by("match_id", "team").len().rename({"len": "og"})
    g = (tp.select("match_id", "team", "coach").join(remates, on=["match_id", "team"], how="left")
           .join(autogoles, on=["match_id", "team"], how="left")
           .with_columns((pl.col("goles").fill_null(0) + pl.col("og").fill_null(0)).alias("gf")))
    filas = []
    por_partido = {mid[0]: sub for mid, sub in g.group_by("match_id")}
    for mid, sub in por_partido.items():
        if sub.height != 2:
            continue
        a, b = sub.row(0, named=True), sub.row(1, named=True)
        for x, y in ((a, b), (b, a)):
            r = resultado_esperado(np.array(x["xgs"] or []), np.array(y["xgs"] or []))
            pts = 3 if x["gf"] > y["gf"] else (1 if x["gf"] == y["gf"] else 0)
            filas.append({"match_id": mid, "team": x["team"], "coach": x["coach"], "gf": int(x["gf"]),
                          "gc": int(y["gf"]), "pts": pts, **r})
    return pl.DataFrame(filas)


def resumen_xpts(x: pl.DataFrame, foco: str) -> dict:
    def bloque(d: pl.DataFrame) -> dict:
        dif = float((d["pts"] - d["xPts"]).sum())
        sd = float(np.sqrt(d["var_pts"].sum()))
        from scipy import stats
        return {"partidos": d.height, "puntos": int(d["pts"].sum()), "xPts": float(d["xPts"].sum()),
                "dif": dif, "sd": sd, "z": dif / sd if sd else float("nan"),
                "p": float(2 * stats.norm.sf(abs(dif / sd))) if sd else float("nan"),
                "puntos_por_partido": float(d["pts"].mean()), "xPts_por_partido": float(d["xPts"].mean())}
    out = {"liga_completa": bloque(x), "foco": bloque(x.filter(pl.col("coach") == foco))}
    # validación: en toda la liga la suma de puntos y de xPts debe coincidir (no 3 puntos por empate)
    out["validacion"] = {"puntos_totales": out["liga_completa"]["puntos"],
                         "xPts_totales": out["liga_completa"]["xPts"],
                         "error_relativo": abs(out["liga_completa"]["dif"]) / max(out["liga_completa"]["xPts"], 1)}
    return out


# ----------------------------------------------------------------------
# 2. Escenarios
# ----------------------------------------------------------------------
MARCADORES = {"perdiendo": "losing", "empatando": "drawing", "ganando": "winning"}
TRAMOS_ESC = ("0-29", "45-59", "75+")
ELO_ESC = {"rival más débil": 1.0, "rival parejo": 0.0, "rival más fuerte": -1.0}


def escenarios(t: pl.DataFrame, m, D, xg_foco: list[float], xg_liga: list[float], familias: list[str],
               sims: np.ndarray, se_xg_foco: list[float] | None = None, seed: int = 0) -> pl.DataFrame:
    """Rejilla de escenarios: mezcla de familias y xG por secuencia, foco contra liga.

    El IC combina las dos fuentes de incertidumbre: la de la mezcla (simulación de
    los coeficientes) y la de la eficiencia del foco dentro de cada familia
    (normal con el SE del bootstrap por partido). La de la liga es despreciable
    (~1,600 partidos) y se ignora.
    """
    tf = t.filter(pl.col("f"))
    xf, xl = np.asarray(xg_foco), np.asarray(xg_liga)
    se = np.zeros_like(xf) if se_xg_foco is None else np.asarray(se_xg_foco)
    rng = np.random.default_rng(seed)
    n_s = min(len(sims), 200)
    xf_draws = xf[None] + rng.standard_normal((n_s, len(xf))) * se[None]
    filas = []
    for (mk, mv), tr, loc, (ek, ev) in itertools.product(MARCADORES.items(), TRAMOS_ESC, (True, False),
                                                        ELO_ESC.items()):
        tab = tf.with_columns(pl.lit(mv).alias("score_state"), pl.lit(tr).alias("tramo"),
                              pl.lit(loc).alias("local"), pl.lit(ev).alias("elo_dif"))
        X1, X0 = D(tab), D(tab, f=np.zeros(tab.height))
        p1, p0 = m.predecir(X1).mean(0), m.predecir(X0).mean(0)
        d = np.array([m.predecir(X1, th).mean(0) @ xf_draws[i] - m.predecir(X0, th).mean(0) @ xl
                      for i, th in enumerate(sims[:n_s])])
        fila = {"marcador": mk, "minuto": tr, "local": loc, "rival": ek,
                "xG_sec_foco": float(p1 @ xf), "xG_sec_liga": float(p0 @ xl),
                "dif_xG_sec": float(p1 @ xf - p0 @ xl),
                "lo": float(np.quantile(d, 0.025)), "hi": float(np.quantile(d, 0.975))}
        for k, fam in enumerate(familias):
            fila[f"foco_{fam}"] = float(p1[k])
            fila[f"liga_{fam}"] = float(p0[k])
        filas.append(fila)
    return pl.DataFrame(filas)


# ----------------------------------------------------------------------
# 3. Calibración
# ----------------------------------------------------------------------
def calibracion_contexto(t: pl.DataFrame, m, D, K: int, min_n: int = 300) -> pl.DataFrame:
    tf = t.filter(pl.col("f"))
    pred = m.predecir(D(tf))
    tf = tf.with_columns(*[pl.Series(f"pred_{k + 1}", pred[:, k]) for k in range(K)])
    g = (tf.group_by("score_state", "tramo", "local")
           .agg(pl.len().alias("n"),
                *[pl.col(f"r_{k + 1}").mean().alias(f"obs_{k + 1}") for k in range(K)],
                *[pl.col(f"pred_{k + 1}").mean().alias(f"pred_{k + 1}") for k in range(K)],
                *[pl.col(f"r_{k + 1}").std().alias(f"sd_{k + 1}") for k in range(K)])
           .filter(pl.col("n") >= min_n))
    err = sum((pl.col(f"obs_{k + 1}") - pl.col(f"pred_{k + 1}")).abs() for k in range(K)) / 2
    # Ruido esperado si el modelo fuera PERFECTO: E|N(0, se)| = se·sqrt(2/π) por familia.
    # Ignora la correlación entre secuencias de un mismo partido, así que es una cota
    # inferior del ruido: un cociente error/ruido cercano a 1 ya indica buena calibración.
    ruido = sum(pl.col(f"sd_{k + 1}") / pl.col("n").sqrt() for k in range(K)) * float(np.sqrt(2 / np.pi)) / 2
    return g.with_columns(err.alias("error_tv"), ruido.alias("ruido_tv")).sort("n", descending=True)
