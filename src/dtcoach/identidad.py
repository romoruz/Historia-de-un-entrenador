"""
Fase C -- Identidad y tiempo (reto 5.2): ¿el equipo tiene una identidad clara y
cómo evoluciona partido a partido?

1. ¿SE LE RECONOCE? (aprendizaje supervisado, interpretable)
   Huella de un equipo-partido: su mezcla de familias en ataque y la de sus rivales
   contra él (fase 1), más las métricas de la fase B, estandarizadas contra la liga.
   Un logit con penalización L2 aprende a distinguir los partidos del técnico de
   los del resto; se mide en partidos NO vistos (validación cruzada por partido)
   con el AUC. Nula: el mismo procedimiento con las etiquetas permutadas. Dos
   preguntas distintas:
     contra la liga   ¿su equipo juega distinto al promedio?
     contra su club   ¿se distingue del MISMO club con otros técnicos? (técnico, no plantel)
   El mismo AUC para cada técnico-club de la liga dice qué tan reconocible es el
   foco comparado con los demás. Los coeficientes (en desviaciones estándar) dicen
   por qué se le reconoce.

2. EVOLUCIÓN (sistema dinámico lineal con ruido: modelo de nivel local)
       nivel_t = nivel_{t-1} + w_t,   w_t ~ N(0, q)       (el estilo que cambia)
       y_t     = nivel_t + v_t,       v_t ~ N(0, r_t)     (el ruido de un partido)
   Filtro de Kalman hacia adelante, suavizado de Rauch-Tung-Striebel hacia atrás, q
   por máxima verosimilitud. q ≈ 0: identidad estable, lo que cambia partido a
   partido es ruido; q grande: el estilo se mueve. El cambio de club se lee como la
   diferencia del nivel suavizado entre el último partido en un club y el primero en el otro.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy.optimize import minimize, minimize_scalar


# ----------------------------------------------------------------------
# 1. Huella y clasificador
# ----------------------------------------------------------------------
def huella(t_seq: pl.DataFrame, M: pl.DataFrame, K: int, metricas: list[str]) -> pl.DataFrame:
    """Una fila por equipo-partido: mezcla de ataque (a_k), de defensa (d_k) y métricas."""
    r = [f"r_{k + 1}" for k in range(K)]
    ata = t_seq.group_by("match_id", "team").agg([pl.col(c).mean().alias(f"ataque_{i + 1}") for i, c in enumerate(r)])
    riv = M.select("match_id", "team", "rival")
    dfn = (ata.rename({"team": "rival", **{f"ataque_{i + 1}": f"defensa_{i + 1}" for i in range(K)}})
           .join(riv, on=["match_id", "rival"]).drop("rival"))
    val = M.select("match_id", "team", "rival", "coach", "coach_rival", "match_date",
                   *[pl.when(pl.col(f"{m}__d") > 0).then(pl.col(f"{m}__n") / pl.col(f"{m}__d")).alias(m)
                     for m in metricas])
    return val.join(ata, on=["match_id", "team"], how="inner").join(dfn, on=["match_id", "team"], how="inner")


def _estandarizar(H: pl.DataFrame, cols: list[str]) -> np.ndarray:
    X = H.select(cols).to_numpy().astype(float)
    vacia = ~np.isfinite(X).any(axis=0)                  # métrica sin datos (p. ej. sin 360): no aporta
    X[:, vacia] = 0.0
    mu, sd = np.nanmean(X, 0), np.nanstd(X, 0)
    Z = (X - mu) / np.where(sd > 0, sd, 1.0)
    return np.nan_to_num(Z)


def logit_l2(X: np.ndarray, y: np.ndarray, lam: float = 1.0, pesos: np.ndarray | None = None) -> np.ndarray:
    n, p = X.shape
    w = np.ones(n) if pesos is None else pesos
    Xa = np.column_stack([np.ones(n), X])

    def f(b):
        z = Xa @ b
        ll = w * (y * z - np.logaddexp(0, z))
        pr = 1 / (1 + np.exp(-z))
        g = -(Xa.T @ (w * (y - pr))) / n
        g[1:] += lam * b[1:] / n
        return -ll.sum() / n + 0.5 * lam * (b[1:] @ b[1:]) / n, g
    return minimize(f, np.zeros(p + 1), jac=True, method="L-BFGS-B").x


def auc(score: np.ndarray, y: np.ndarray) -> float:
    """Área bajo la curva ROC = P(score de un positivo > score de un negativo) (Mann-Whitney)."""
    from scipy.stats import rankdata
    y = np.asarray(y, bool)
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = rankdata(score)
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def auc_cv(X: np.ndarray, y: np.ndarray, grupos: np.ndarray, folds: int = 5, lam: float = 1.0,
           seed: int = 0) -> float:
    """AUC fuera de muestra; los pliegues son PARTIDOS. Clases balanceadas por peso."""
    u = np.unique(grupos)
    rng = np.random.default_rng(seed)
    rng.shuffle(u)
    plg = {g: i % folds for i, g in enumerate(u)}
    f = np.array([plg[g] for g in grupos])
    s = np.full(len(y), np.nan)
    for k in range(folds):
        tr, te = f != k, f == k
        if y[tr].sum() == 0 or (~y[tr].astype(bool)).sum() == 0 or te.sum() == 0:
            continue
        w = np.where(y[tr] == 1, 0.5 / y[tr].mean(), 0.5 / (1 - y[tr].mean()))
        b = logit_l2(X[tr], y[tr], lam, w)
        s[te] = np.column_stack([np.ones(te.sum()), X[te]]) @ b
    ok = np.isfinite(s)
    return auc(s[ok], y[ok])


def reconocimiento(H: pl.DataFrame, cols: list[str], foco: str, contra: str = "liga", n_perm: int = 200,
                   lam: float = 1.0, seed: int = 0) -> dict:
    """AUC fuera de muestra de 'es un partido de `foco`', su nula por permutación y los rasgos."""
    if contra == "club":
        clubes = H.filter(pl.col("coach") == foco)["team"].unique().to_list()
        D = H.filter(pl.col("team").is_in(clubes) & pl.col("coach").is_not_null())
    else:
        partidos_rival = H.filter(pl.col("coach_rival") == foco)["match_id"].unique()
        D = H.filter(pl.col("coach").is_not_null() & ((pl.col("coach") == foco)
                                                       | ~pl.col("match_id").is_in(partidos_rival.to_list())))
    y = (D["coach"] == foco).to_numpy().astype(float)
    if y.sum() < 10 or (1 - y).sum() < 10:
        return {"contra": contra, "nota": "muy pocos partidos para comparar"}
    X = _estandarizar(D, cols)
    g = D["match_id"].to_numpy()
    a = auc_cv(X, y, g, lam=lam, seed=seed)
    rng = np.random.default_rng(seed)
    nula = np.array([auc_cv(X, rng.permutation(y), g, lam=lam, seed=seed) for _ in range(n_perm)])
    w = np.where(y == 1, 0.5 / y.mean(), 0.5 / (1 - y.mean()))
    b = logit_l2(X, y, lam, w)[1:]
    orden = np.argsort(-np.abs(b))
    return {"contra": contra, "auc": a, "auc_nula_media": float(np.nanmean(nula)),
            "auc_nula_p95": float(np.nanquantile(nula, 0.95)),
            "p": float((1 + np.sum(nula >= a)) / (1 + np.sum(np.isfinite(nula)))),
            "partidos_foco": int(y.sum()), "partidos_otros": int((1 - y).sum()),
            "rasgos": [{"rasgo": cols[i], "coef_de": float(b[i])} for i in orden[:8]]}


def ranking_reconocimiento(H: pl.DataFrame, cols: list[str], min_partidos: int = 30, lam: float = 1.0,
                           seed: int = 0) -> pl.DataFrame:
    """AUC contra la liga para cada técnico-club con ≥ `min_partidos` (sin permutación)."""
    X = _estandarizar(H, cols)
    g = H["match_id"].to_numpy()
    filas = []
    eras = (H.filter(pl.col("coach").is_not_null()).group_by("coach", "team").len()
            .filter(pl.col("len") >= min_partidos))
    for coach, team, n in eras.iter_rows():
        y = ((H["coach"] == coach) & (H["team"] == team)).fill_null(False).to_numpy().astype(float)
        filas.append({"coach": coach, "team": team, "partidos": n, "auc": auc_cv(X, y, g, lam=lam, seed=seed)})
    return pl.DataFrame(filas).sort("auc", descending=True)


# ----------------------------------------------------------------------
# 2. Nivel local: Kalman + Rauch-Tung-Striebel
# ----------------------------------------------------------------------
def kalman_nivel(y: np.ndarray, r: np.ndarray, q: float, m0: float, p0: float,
                 reinicio: tuple = (), v_reinicio: float = 0.0) -> dict:
    """`reinicio`: índices donde el nivel puede saltar (cambio de club, una INTERVENCIÓN):
    ahí se suma `v_reinicio` a la varianza del estado y el nivel se reaprende del nuevo club."""
    n = len(y)
    mf, pf, mp, pp = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    ll = 0.0
    m, p = m0, p0
    reinicio = set(reinicio)
    for t in range(n):
        mp[t], pp[t] = m, p + q + (v_reinicio if t in reinicio else 0.0)
        if np.isfinite(y[t]):
            s = pp[t] + r[t]
            k = pp[t] / s
            e = y[t] - mp[t]
            m, p = mp[t] + k * e, (1 - k) * pp[t]
            ll += -0.5 * (np.log(2 * np.pi * s) + e * e / s)
        else:
            m, p = mp[t], pp[t]
        mf[t], pf[t] = m, p
    ms, ps = mf.copy(), pf.copy()
    for t in range(n - 2, -1, -1):              # Rauch-Tung-Striebel
        c = pf[t] / pp[t + 1]
        ms[t] = mf[t] + c * (ms[t + 1] - mp[t + 1])
        ps[t] = pf[t] + c * c * (ps[t + 1] - pp[t + 1])
    return {"nivel": ms, "var": ps, "loglik": ll}


def nivel_local(y: np.ndarray, r: np.ndarray | None = None, cortes: tuple = ()) -> dict:
    """q (y el ruido r, si no se da) por máxima verosimilitud. `cortes`: cambios de club,
    modelados como intervención (el nivel puede saltar ahí sin inflar q en el resto)."""
    y = np.asarray(y, float)
    ok = np.isfinite(y)
    m0, v0 = float(np.nanmean(y[: max(3, ok.sum() // 10)])), float(np.nanvar(y) + 1e-12)
    vr = 10.0 * v0 if cortes else 0.0

    def kal(q, rr):
        return kalman_nivel(y, rr, q, m0, v0, tuple(cortes), vr)
    if r is None:
        def nll(th):
            q, rr = np.exp(th)
            return -kal(q, np.full(len(y), rr))["loglik"]
        th = minimize(nll, np.log([v0 / 20, v0 / 2]), method="Nelder-Mead").x
        q, rr = np.exp(th)
        r = np.full(len(y), rr)
    else:
        r = np.asarray(r, float)
        res = minimize_scalar(lambda lq: -kal(np.exp(lq), r)["loglik"],
                              bounds=(np.log(v0) - 20, np.log(v0) + 2), method="bounded")
        q = float(np.exp(res.x))
    k = kal(q, r)
    return {"nivel": k["nivel"].tolist(), "lo": (k["nivel"] - 1.96 * np.sqrt(k["var"])).tolist(),
            "hi": (k["nivel"] + 1.96 * np.sqrt(k["var"])).tolist(), "q": float(q),
            "r_medio": float(np.nanmean(r)), "q_sobre_r": float(q / max(np.nanmean(r), 1e-12)),
            "var": k["var"].tolist()}


def evolucion(t_seq: pl.DataFrame, H: pl.DataFrame, foco: str, K: int, metricas: list[str]) -> dict:
    """Nivel suavizado de cada familia (ataque y defensa) y de las métricas, partido a partido."""
    Hf = H.filter(pl.col("coach") == foco).sort("match_date")
    orden = Hf.select("match_id", "team", "match_date")
    equipos = Hf["team"].to_list()
    cortes = tuple(i for i in range(1, len(equipos)) if equipos[i] != equipos[i - 1])
    out = {"partidos": orden.with_columns(pl.col("match_date").cast(pl.Utf8)).to_dicts(), "series": {}}
    # El ruido de un partido se estima por máxima verosimilitud en TODAS las series. La varianza
    # de r dentro del partido / n (primera versión) ignora que las secuencias de un partido
    # comparten rival y marcador: subestimaba el ruido y todo el vaivén se volvía "q" (q/r ≈ 3–7).
    for lado in ("ataque", "defensa"):
        for k in range(K):
            out["series"][f"{lado}_{k + 1}"] = nivel_local(Hf[f"{lado}_{k + 1}"].to_numpy().astype(float),
                                                           cortes=cortes)
    for m in metricas:
        if m in Hf.columns and Hf[m].drop_nulls().len() >= 10:
            out["series"][m] = nivel_local(Hf[m].to_numpy().astype(float), cortes=cortes)
    # cambio de club: diferencia entre el nivel al salir de un club y al llegar al siguiente.
    # Con la intervención, el salto se estima con los partidos de cada club. z usa var_i + var_{i-1}
    # e ignora su covarianza: es CONSERVADOR.
    out["cambios_de_club"] = []
    for i in cortes:
        fila = {"de": equipos[i - 1], "a": equipos[i], "partido": i, "series": {}}
        for s, v in out["series"].items():
            n, var = np.array(v["nivel"]), np.array(v["var"])
            d = n[i] - n[i - 1]
            fila["series"][s] = {"salto": float(d), "z": float(d / np.sqrt(var[i] + var[i - 1]))}
        out["cambios_de_club"].append(fila)
    return out
