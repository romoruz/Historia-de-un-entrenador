"""
EXPERIMENTO (ADR-v2-53, no adoptado): el regresor generado de la fase 2.

Las responsabilidades r_sk NO son un dato: salen del EM de la etapa 1 (la mezcla). El sandwich
de la Prop. 7.2 y el bootstrap de los perfiles las tratan como observadas, así que no propagan
el error de la primera etapa (Murphy & Topel 1985; Pagan 1984, «generated regressors»). Los IC de
H1–H8 podrían estar estrechos de más.

CÓMO SE CUANTIFICA
------------------
Bootstrap por PARTIDO (estratificado: partidos con el foco / resto, mismos tamaños que los
observados). En cada réplica b, con la misma remuestra de partidos:
  (fijo)  las r ORIGINALES de esas secuencias → etapa 2.   [la fase 2 de hoy]
  (doble) la mezcla se REAJUSTA en la remuestra (arranque en escalera, semilla fija por réplica),
          se recalculan las r, y se hace la etapa 2.        [propaga la etapa 1]
Las etiquetas de las familias se alinean con la mezcla original (asignación húngara sobre las r).
Para cada cantidad de H1–H8 se comparan las amplitudes:
  w_doble = q97.5 − q2.5 de las réplicas «doble»   w_fijo = igual con «fijo»   w_actual = IC publicado
  inflación limpia = w_doble / w_fijo   (lo que añade la etapa 1)
  inflación vs actual = w_doble / w_actual
Regla: si la inflación es < 1.1 se reporta como despreciable. Con R réplicas, el error relativo de
una amplitud de percentiles es ≈ 1/√(2(R−1)) (≈ 5 % con 200): por debajo de ~50 réplicas no se
puede decidir entre 1.0 y 1.1.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy.optimize import linear_sum_assignment

from .hipotesis import ESCENARIOS, _con, modelo_contexto
from .perfil import nombres_metricas, perfiles

NO_FOCO = "partido_foco"


def estratos(match: np.ndarray, partido_foco: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ids de partido con el foco y del resto."""
    con = np.unique(match[partido_foco])
    return con, np.setdiff1d(np.unique(match), con)


def remuestra(match: np.ndarray, con: np.ndarray, sin: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Índices de secuencias de una remuestra por partido (con reemplazo, estratificada)."""
    orden = np.argsort(match, kind="stable")
    ms = match[orden]
    ini = np.searchsorted(ms, np.concatenate([con, sin]), side="left")
    fin = np.searchsorted(ms, np.concatenate([con, sin]), side="right")
    ids = np.concatenate([rng.integers(0, len(con), len(con)), len(con) + rng.integers(0, len(sin), len(sin))])
    return np.concatenate([orden[ini[i]:fin[i]] for i in ids])


def alinear(R_ref: np.ndarray, R: np.ndarray) -> np.ndarray:
    """Permutación de las columnas de R que mejor empata con las de R_ref (misma secuencia, misma fila)."""
    K = R.shape[1]
    costo = -(R_ref.T @ R)
    i, j = linear_sum_assignment(costo)
    perm = np.empty(K, int)
    perm[i] = j
    return perm


def cantidades(t: pl.DataFrame, K: int, ref: int, suave: bool, familias: list[str]) -> dict[str, float]:
    """Estimaciones puntuales de H1–H8 (sin IC): lo que se compara entre réplicas."""
    m, D, _ = modelo_contexto(t, K, ref, suave)
    tf, tg = t.filter(pl.col("f")), t.filter(pl.col("g"))
    out = {}
    for h, tab, kw in (("H1", tf, "f"), ("H2", tg, "g")):
        z = np.zeros(tab.height)
        d = (m.predecir(D(tab)) - m.predecir(D(tab, **{kw: z}))).mean(0)
        for k in range(K):
            out[f"{h} Δπ · {familias[k]}"] = float(d[k])
    z = np.zeros(tf.height)
    for esc, (col, v1, v0) in ESCENARIOS.items():
        a1, a0 = D(_con(tf, col, v1)), D(_con(tf, col, v0))
        b1, b0 = D(_con(tf, col, v1), f=z), D(_con(tf, col, v0), f=z)
        dif = (m.predecir(a1) - m.predecir(a0)).mean(0) - (m.predecir(b1) - m.predecir(b0)).mean(0)
        for k in range(K):
            out[f"H3–H6 {esc} · {familias[k]}"] = float(dif[k])
    pf = perfiles(t, K, n_boot=2, seed=0)
    nom = nombres_metricas(K, familias)
    for lado, h in (("ataque", "H7"), ("defensa", "H8")):
        for i, n in enumerate(nom):
            if n.startswith(("xG por secuencia", "P(remate)", "uso")):
                out[f"{h}/{lado} · {n}"] = float(pf[lado]["dif"][i])
    return out


def actuales(res: dict, K: int, familias: list[str]) -> dict[str, tuple[float, float, float]]:
    """(estimación, lo, hi) publicados por la fase 2 para las mismas cantidades."""
    out = {}
    for h in ("H1", "H2"):
        e = res["hipotesis"][h]
        for k in range(K):
            out[f"{h} Δπ · {familias[k]}"] = (e["delta_pi"][k], e["lo"][k], e["hi"][k])
    for esc, c in res["contexto"].items():
        for k in range(K):
            out[f"H3–H6 {esc} · {familias[k]}"] = (c["dif"][k], c["lo"][k], c["hi"][k])
    nom = res["metricas_perfil"]
    for lado, h in (("ataque", "H7"), ("defensa", "H8")):
        p = res["perfiles"][lado]
        for i, n in enumerate(nom):
            if n.startswith(("xG por secuencia", "P(remate)", "uso")):
                out[f"{h}/{lado} · {n}"] = (p["dif"][i], p["lo"][i], p["hi"][i])
    return out


def amplitud(x: np.ndarray) -> float:
    return float(np.quantile(x, 0.975) - np.quantile(x, 0.025))


def resumen(fijo: list[dict], doble: list[dict], act: dict) -> list[dict]:
    """Una fila por cantidad con las tres amplitudes y las dos inflaciones."""
    filas = []
    for n in doble[0]:
        wd = amplitud(np.array([r[n] for r in doble]))
        wf = amplitud(np.array([r[n] for r in fijo]))
        e, lo, hi = act.get(n, (np.nan, np.nan, np.nan))
        wa = hi - lo
        filas.append({"cantidad": n, "estimacion": e, "w_actual": wa, "w_fijo": wf, "w_doble": wd,
                      "infl_limpia": wd / wf if wf > 0 else float("nan"),
                      "infl_vs_actual": wd / wa if wa > 0 else float("nan"),
                      "calibracion_fijo": wf / wa if wa > 0 else float("nan"),
                      "sd_doble": float(np.std([r[n] for r in doble], ddof=1)),
                      "sesgo_doble_menos_fijo": float(np.mean([r[n] for r in doble]) - np.mean([r[n] for r in fijo]))})
    return filas
