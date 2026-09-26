"""
Fase F -- Simulador de partido (reto 06): repetir un partido miles de veces con
el ESTILO de cada equipo, para explicar el resultado, no para apostar.

EL MODELO (todo sale del vocabulario de la fase 1)
--------------------------------------------------
Para el equipo A (una etapa técnico-club) atacando a B:
  1. Número de secuencias: proceso de Poisson en el partido,
         n_A ~ Poisson(λ),  λ = λ_A^ataque · λ_B^concede / λ̄
  2. Familia de cada secuencia: multinomial con
         π ∝ π_A^ataque ⊙ π_B^concede / π̄              (log-lineal, como el "log5")
  3. Remate: dentro de la familia k, Bernoulli(p_k), con
         p_k = p̄_k · (p_{A,k} / p̄_k) · (p_{B,k}^concede / p̄_k)
  4. Gol: cada remate de la familia k es gol con probabilidad g_k (xG por remate,
     combinado igual que p_k).
Cada parámetro de etapa se encoge hacia la liga con `a` pseudo-secuencias
(parámetro del config), para que una etapa corta no dé tasas extremas.

LO QUE RESPONDE
---------------
  - P(gana / empata / pierde), goles y xG esperados, P(más xG que el rival): dominio.
  - Para un partido REAL: con los parámetros de la etapa SIN ese partido (se restan
    sus sumas: validación exacta dejando uno fuera), qué tan probable era el
    resultado que ocurrió.
  - Validación de liga: puntos esperados contra reales, puntuación de Brier del
    resultado contra la de las frecuencias base (habilidad), sobre todos los partidos.

Supuestos declarados: las secuencias de un partido son independientes dado el
estilo; el contexto (marcador) no cambia la mezcla dentro de la simulación (eso
lo mide la fase 2). Exploratorio, como el resto del simulador.
"""
from __future__ import annotations

import numpy as np
import polars as pl


def estadisticos(t_seq: pl.DataFrame, K: int) -> pl.DataFrame:
    """Suficientes por equipo-partido (lado ATAQUE): n, Σr_k, Σr_k·remata, Σr_k·xG."""
    r = [f"r_{k + 1}" for k in range(K)]
    return t_seq.group_by("match_id", "team").agg(
        pl.len().alias("n"), *[pl.col(c).sum().alias(f"u{k}") for k, c in enumerate(r)],
        *[(pl.col(c) * pl.col("remata").cast(pl.Float64)).sum().alias(f"s{k}") for k, c in enumerate(r)],
        *[(pl.col(c) * pl.col("xg")).sum().alias(f"x{k}") for k, c in enumerate(r)])


def _vec(row: dict, K: int) -> np.ndarray:
    return np.array([row["n"], *[row[f"u{k}"] for k in range(K)], *[row[f"s{k}"] for k in range(K)],
                     *[row[f"x{k}"] for k in range(K)]], dtype=float)


class Parametros:
    """Suficientes por etapa (ataque y concedido), con la liga como ancla."""

    def __init__(self, st: pl.DataFrame, tp: pl.DataFrame, K: int, a: float = 200.0):
        self.K, self.a = K, a
        x = st.join(tp.select("match_id", "team", "coach", "rival", "coach_rival"), on=["match_id", "team"])
        cols = ["n"] + [f"{p}{k}" for p in "usx" for k in range(K)]
        self.partido = {(r["match_id"], r["team"]): _vec(r, K) for r in x.iter_rows(named=True)}
        self.eta = {(r["match_id"], r["team"]): (r["coach"], r["team"]) for r in x.iter_rows(named=True)}
        self.eta_rival = {(r["match_id"], r["team"]): (r["coach_rival"], r["rival"]) for r in x.iter_rows(named=True)}
        self.ataque: dict = {}
        self.concede: dict = {}
        self.partidos_eta: dict = {}
        self.partidos_concede: dict = {}
        for (mid, team), v in self.partido.items():
            e, er = self.eta[(mid, team)], self.eta_rival[(mid, team)]
            self.ataque[e] = self.ataque.get(e, 0) + v
            self.concede[er] = self.concede.get(er, 0) + v
            self.partidos_eta.setdefault(e, set()).add(mid)
            self.partidos_concede.setdefault(er, set()).add(mid)
        tot = x.select(cols).sum().to_numpy().ravel().astype(float)
        self.n_partidos = x["match_id"].n_unique()
        self.liga = self._tasas(tot, 2 * self.n_partidos)
        self.cols = cols

    def _tasas(self, v: np.ndarray, partidos: float, ancla: dict | None = None) -> dict:
        K, a = self.K, self.a
        n, u, s, x = v[0], v[1:1 + K], v[1 + K:1 + 2 * K], v[1 + 2 * K:]
        if ancla is None:
            return {"lam": n / max(partidos, 1), "pi": u / max(n, 1e-12), "p": s / np.maximum(u, 1e-12),
                    "g": x / np.maximum(s, 1e-12)}
        L = ancla
        pi = (u + a * L["pi"]) / (n + a)
        p = (s + a * L["pi"] * L["p"]) / (u + a * L["pi"])
        g = (x + a * L["pi"] * L["p"] * L["g"]) / (s + a * L["pi"] * L["p"])
        lam = (n + a) / (partidos + a / max(L["lam"], 1e-12))
        return {"lam": lam, "pi": pi, "p": p, "g": g}

    def etapa(self, e: tuple, lado: str, sin_partido: int | None = None, team_del_partido: str | None = None) -> dict:
        """Tasas encogidas de la etapa; si `sin_partido`, se restan las sumas de ese partido."""
        v = (self.ataque if lado == "ataque" else self.concede).get(e)
        if v is None:
            return self.liga
        v = v.copy()
        partidos = len((self.partidos_eta if lado == "ataque" else self.partidos_concede).get(e, ()))
        if sin_partido is not None:
            clave = (sin_partido, team_del_partido)
            if clave in self.partido:
                v = v - self.partido[clave]
                partidos -= 1
        return self._tasas(np.maximum(v, 0), max(partidos, 0), self.liga)

    def combinar(self, A: dict, B: dict) -> dict:
        L = self.liga
        pi = A["pi"] * B["pi"] / np.maximum(L["pi"], 1e-12)
        pi = pi / pi.sum()
        p = np.clip(L["p"] * (A["p"] / np.maximum(L["p"], 1e-12)) * (B["p"] / np.maximum(L["p"], 1e-12)), 0, 1)
        g = np.clip(L["g"] * (A["g"] / np.maximum(L["g"], 1e-12)) * (B["g"] / np.maximum(L["g"], 1e-12)), 0, 1)
        lam = A["lam"] * B["lam"] / max(L["lam"], 1e-12)
        return {"lam": lam, "pi": pi, "p": p, "g": g}


def simular(ta: dict, tb: dict, n_rep: int = 10000, seed: int = 0) -> dict:
    """Repite el partido: goles y xG de cada lado en cada repetición."""
    rng = np.random.default_rng(seed)
    out = {}
    for lado, th in (("A", ta), ("B", tb)):
        n = rng.poisson(th["lam"], n_rep)
        fam = rng.multinomial(n, th["pi"])                                    # (n_rep, K)
        rem = rng.binomial(fam, th["p"][None, :])
        gol = rng.binomial(rem, th["g"][None, :])
        out[lado] = {"goles": gol.sum(1), "xg": (rem * th["g"][None, :]).sum(1), "secuencias": n,
                     "familias": fam.mean(0)}
    ga, gb = out["A"]["goles"], out["B"]["goles"]
    return {"P_gana": float((ga > gb).mean()), "P_empata": float((ga == gb).mean()), "P_pierde": float((ga < gb).mean()),
            "goles_A": float(ga.mean()), "goles_B": float(gb.mean()), "xg_A": float(out["A"]["xg"].mean()),
            "xg_B": float(out["B"]["xg"].mean()), "P_domina_xg": float((out["A"]["xg"] > out["B"]["xg"]).mean()),
            "xPts": float(3 * (ga > gb).mean() + (ga == gb).mean()),
            "marcadores": _marcadores(ga, gb), "familias_A": out["A"]["familias"].tolist(),
            "familias_B": out["B"]["familias"].tolist()}


def _marcadores(ga: np.ndarray, gb: np.ndarray, top: int = 8) -> list:
    pares, n = np.unique(np.column_stack([ga, gb]), axis=0, return_counts=True)
    orden = np.argsort(-n)[:top]
    return [{"marcador": f"{int(pares[i, 0])}-{int(pares[i, 1])}", "P": float(n[i] / len(ga))} for i in orden]


def partido_real(par: Parametros, match_id: int, team: str, rival: str, n_rep: int, seed: int) -> dict:
    """El partido con los parámetros de ambas etapas SIN ese partido."""
    ea, eb = par.eta[(match_id, team)], par.eta[(match_id, rival)]
    A_at = par.etapa(ea, "ataque", match_id, team)
    B_at = par.etapa(eb, "ataque", match_id, rival)
    A_co = par.etapa(ea, "concede", match_id, rival)        # lo que concede A = el ataque de B en ese partido
    B_co = par.etapa(eb, "concede", match_id, team)
    return simular(par.combinar(A_at, B_co), par.combinar(B_at, A_co), n_rep, seed)


def validar_liga(par: Parametros, resultados: pl.DataFrame, n_rep: int = 2000, seed: int = 0,
                 max_partidos: int | None = None) -> dict:
    """Brier del resultado (dejando el partido fuera) contra frecuencias base, y puntos."""
    r = resultados.select("match_id", "team", "rival", "goles", "goles_rival").unique(["match_id"], keep="first")
    if max_partidos:
        r = r.head(max_partidos)
    obs, pred, ptos, xpts = [], [], [], []
    for i, (mid, team, rival, g, gr) in enumerate(r.iter_rows()):
        if (mid, team) not in par.eta or (mid, rival) not in par.eta:
            continue
        s = partido_real(par, mid, team, rival, n_rep, seed + i)
        pred.append([s["P_gana"], s["P_empata"], s["P_pierde"]])
        obs.append([g > gr, g == gr, g < gr])
        ptos.append(3 * (g > gr) + (g == gr))
        xpts.append(s["xPts"])
    P, O = np.array(pred), np.array(obs, float)
    base = O.mean(0)
    brier = float(((P - O) ** 2).sum(1).mean())
    brier_base = float(((base[None] - O) ** 2).sum(1).mean())
    return {"partidos": len(O), "brier": brier, "brier_frecuencias": brier_base,
            "habilidad": float(1 - brier / brier_base), "puntos_reales": float(np.mean(ptos)),
            "xPts_modelo": float(np.mean(xpts)),
            "corr_puntos": float(np.corrcoef(ptos, xpts)[0, 1]) if len(ptos) > 2 else float("nan")}
