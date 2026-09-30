"""
Proyección (reto 06, G6): ¿cómo le iría al técnico en su club actual, con su identidad y
los jugadores que encontró? Un modelo simple, validado contra todos los cambios de
técnico de la liga. Explica, no apuesta.

1. FUERZA DE CADA EQUIPO CON xG (modelo multiplicativo de Maher 1982; Dixon & Coles 1997,
   sin su corrección de marcadores bajos)
   Para el equipo i contra j:  E[xG_i] = μ · A_i · D_j · h^{±1}
     A_i  ataque (1 = promedio), D_j  defensa del rival (> 1 = concede más), h  localía.
   Se usa xG y no goles: es mucho más estable con pocos partidos.
   Los ÍNDICES de un equipo en una ventana de partidos son razones ajustadas por los rivales
   que enfrentó:
       A_i(W) = Σ_W xG_a_favor / Σ_W μ·D_rival^{(−i)}·h^{±1}
       D_i(W) = Σ_W xG_en_contra / Σ_W μ·A_rival^{(−i)}·h^{∓1}
   donde la fuerza del rival en esa temporada sale de Maher (puntos fijos) SIN los partidos
   de i: el rendimiento de i no entra en la vara con que se le mide.

2. EL EFECTO DE LLEGAR (qué pasa cuando cambia el técnico)
   Para cada llegada de un técnico a un club con ≥ `n_pre` partidos antes y ≥ `n_post`
   con él:  e_ataque = log A(post) − log A(pre),  e_defensa = log D(post) − log D(pre).
   La media de la liga NO es cero: incluye la regresión a la media que sigue a un
   despido (van Ours & van Tuijl 2016). Por eso el efecto de UN técnico se mide contra
   esa media y se contrae hacia ella (normal-normal, τ² por DerSimonian-Laird; Efron &
   Morris 1975):
       ê_técnico = μ_e + τ²/(τ² + v̄/n_llegadas) · (ē_técnico − μ_e)
   con sus llegadas ANTERIORES al club objetivo (nunca las del club que se proyecta).

3. LA PROYECCIÓN
   Plantel = los índices del club en sus últimos `n_pre` partidos antes de la llegada (los
   jugadores que encontró). Con el técnico: A·exp(ê_a), D·exp(ê_d). Sin él (inercia): A·exp(μ_e_a),
   D·exp(μ_e_d). Se simula el torneo completo (todos contra todos, una vuelta, `n_sim`
   veces; goles ~ Poisson(xG esperado)): puntos, posición, P(liguilla directa), P(play-in).

4. VALIDACIÓN
   La misma receta se aplica a CADA llegada de la liga (dejándola fuera de μ_e y τ²) y se
   compara lo proyectado para sus primeros `n_post` partidos con lo que pasó: error por
   partido, correlación, cobertura del intervalo del 80 %. Y contra los partidos reales
   del técnico en el club objetivo.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .xdefensa import contraccion


def base(x: pl.DataFrame, tp: pl.DataFrame) -> pl.DataFrame:
    """Una fila por equipo-partido con fecha, localía, rival, técnico, xG a favor y en contra, goles y puntos.
    `x`: de `simulador.xpts_por_equipo_partido`."""
    b = (x.select("match_id", "team", "coach", "gf", "gc", "pts", pl.col("xG").alias("xgf"),
                  pl.col("xG_rival").alias("xga"))
         .join(tp.select("match_id", "team", "rival", "match_date", "local", "season_id"), on=["match_id", "team"],
               how="inner"))
    return b.sort("match_date", "match_id", "team")


def localia(b: pl.DataFrame) -> tuple[float, float]:
    mu = float(b["xgf"].mean())
    loc, vis = float(b.filter(pl.col("local"))["xgf"].mean()), float(b.filter(~pl.col("local"))["xgf"].mean())
    return mu, float(np.sqrt(loc / vis)) if vis > 0 and loc > 0 else 1.0


def _maher(ti: np.ndarray, ri: np.ndarray, f: np.ndarray, c: np.ndarray, hs: np.ndarray, n: int, mu: float,
           iters: int = 30) -> tuple[np.ndarray, np.ndarray]:
    """Puntos fijos de Maher: A_i = Σ xG_i / Σ μ D_rival h, D_i = Σ xGc_i / Σ μ A_rival / h (media 1)."""
    A, D = np.ones(n), np.ones(n)
    jugo = np.bincount(ti, minlength=n) > 0
    for _ in range(iters):
        A = np.bincount(ti, weights=f, minlength=n) / np.maximum(np.bincount(ti, weights=mu * D[ri] * hs,
                                                                             minlength=n), 1e-12)
        A = np.where(jugo, A / A[jugo].mean(), 1.0)
        D = np.bincount(ti, weights=c, minlength=n) / np.maximum(np.bincount(ti, weights=mu * A[ri] / hs,
                                                                             minlength=n), 1e-12)
        D = np.where(jugo, D / D[jugo].mean(), 1.0)
    return A, D


def fuerza_temporada(b: pl.DataFrame, mu: float, h: float) -> dict:
    """(temporada, equipo evaluado i) → fuerza (A, D) de cada rival en esa temporada, estimada por
    Maher SIN los partidos de i. Así el rendimiento del equipo no se cuela en la vara con que se le
    mide: un ataque que mejora no infla la "defensa floja" de sus rivales ni se esconde a sí mismo."""
    out = {}
    for (s,), g in b.group_by("season_id"):
        eq = sorted(set(g["team"].to_list()) | set(g["rival"].to_list()))
        k = {t: i for i, t in enumerate(eq)}
        ti = np.array([k[t] for t in g["team"]])
        ri = np.array([k[t] for t in g["rival"]])
        f, c = g["xgf"].to_numpy(), g["xga"].to_numpy()
        hs = np.where(g["local"].to_numpy(), h, 1 / h)
        for t, i in k.items():
            m = (ti != i) & (ri != i)
            A, D = _maher(ti[m], ri[m], f[m], c[m], hs[m], len(eq), mu)
            out[(s, t)] = {e: (float(A[j]), float(D[j])) for e, j in k.items() if e != t}
    return {"sin": out, "mu": mu}


def rival_sin(fz: dict, s, j: str, i: str) -> tuple[float, float]:
    """(A_j, D_j) de la temporada s estimados sin los partidos del equipo i (1, 1 si no hay datos)."""
    return fz["sin"].get((s, i), {}).get(j, (1.0, 1.0))


def _esperados(filas: pl.DataFrame, fz: dict, mu: float, h: float) -> tuple[np.ndarray, np.ndarray]:
    """Denominadores de los índices: xG esperado a favor y en contra ante un equipo promedio."""
    ef, ec = [], []
    for s, t, r, loc in filas.select("season_id", "team", "rival", "local").iter_rows():
        Ar, Dr = rival_sin(fz, s, r, t)
        hh = h if loc else 1 / h
        ef.append(mu * Dr * hh)
        ec.append(mu * Ar / hh)
    return np.array(ef), np.array(ec)


def indices(filas: pl.DataFrame, fz: dict, mu: float, h: float) -> tuple[float, float]:
    if filas.height == 0:
        return 1.0, 1.0
    ef, ec = _esperados(filas, fz, mu, h)
    return float(filas["xgf"].sum() / ef.sum()), float(filas["xga"].sum() / ec.sum())


def _boot_log(filas_pre, filas_post, fz, mu, h, n_boot, rng) -> tuple[float, float]:
    """Varianza por bootstrap de partidos de (log A_post − log A_pre, log D_post − log D_pre)."""
    ef0, ec0 = _esperados(filas_pre, fz, mu, h)
    ef1, ec1 = _esperados(filas_post, fz, mu, h)
    f0, c0 = filas_pre["xgf"].to_numpy(), filas_pre["xga"].to_numpy()
    f1, c1 = filas_post["xgf"].to_numpy(), filas_post["xga"].to_numpy()
    ea, ed = [], []
    for _ in range(n_boot):
        i, j = rng.integers(0, len(f0), len(f0)), rng.integers(0, len(f1), len(f1))
        a0, a1 = f0[i].sum() / ef0[i].sum(), f1[j].sum() / ef1[j].sum()
        d0, d1 = c0[i].sum() / ec0[i].sum(), c1[j].sum() / ec1[j].sum()
        if min(a0, a1, d0, d1) > 0:
            ea.append(np.log(a1 / a0))
            ed.append(np.log(d1 / d0))
    return float(np.var(ea)), float(np.var(ed))


def llegadas(b: pl.DataFrame, fz: dict, mu: float, h: float, n_pre: int, n_post: int, n_boot: int = 200,
             seed: int = 0) -> pl.DataFrame:
    """Cada llegada de un técnico: índices antes (plantel) y en sus primeros `n_post` partidos."""
    rng = np.random.default_rng(seed)
    filas = []
    for (team,), g in b.group_by("team"):
        g = g.sort("match_date", "match_id")
        co = g["coach"].to_list()
        for k in range(1, g.height):
            if co[k] is None or co[k] == co[k - 1] or k < n_pre:
                continue
            fin = k
            while fin < g.height and co[fin] == co[k]:
                fin += 1
            if fin - k < n_post:
                continue
            pre, post = g[k - n_pre:k], g[k:k + n_post]
            A0, D0 = indices(pre, fz, mu, h)
            A1, D1 = indices(post, fz, mu, h)
            if min(A0, D0, A1, D1) <= 0:
                continue
            va, vd = _boot_log(pre, post, fz, mu, h, n_boot, rng)
            filas.append({"coach": co[k], "team": team, "fecha": g["match_date"][k], "A_pre": A0, "D_pre": D0,
                          "A_post": A1, "D_post": D1, "e_ataque": float(np.log(A1 / A0)),
                          "e_defensa": float(np.log(D1 / D0)), "v_ataque": va, "v_defensa": vd,
                          "pts_post": float(post["pts"].sum()), "partidos_post": post.height,
                          "match_ids_post": post["match_id"].to_list()})
    return pl.DataFrame(filas)


def efecto_tecnico(ll: pl.DataFrame, coach: str, excluir_team: str | None = None) -> dict:
    """ê del técnico (ataque y defensa), contraído hacia la media de todas las llegadas."""
    otras = ll.filter(pl.col("coach") != coach)
    suyas = ll.filter((pl.col("coach") == coach) & (pl.col("team") != (excluir_team or "")))
    out = {"llegadas_liga": otras.height, "llegadas_suyas": suyas.height,
           "clubes": suyas["team"].to_list() if suyas.height else []}
    for lado in ("ataque", "defensa"):
        c = contraccion(otras[f"e_{lado}"].to_numpy(), otras[f"v_{lado}"].to_numpy())
        mu_e, tau2 = c["mu"], c["tau2"]
        if suyas.height:
            e_bar = float(suyas[f"e_{lado}"].mean())
            v_bar = float(suyas[f"v_{lado}"].mean()) / suyas.height
            w = tau2 / (tau2 + v_bar) if tau2 > 0 else 0.0
        else:
            e_bar, v_bar, w = float("nan"), float("nan"), 0.0
        est = mu_e + w * ((e_bar if np.isfinite(e_bar) else mu_e) - mu_e)
        out[lado] = {"mu_liga": mu_e, "tau2": tau2, "suyo_crudo": e_bar, "peso": w, "contraido": float(est),
                     "var_posterior": float(1 / (1 / tau2 + 1 / v_bar)) if tau2 > 0 and np.isfinite(v_bar) and v_bar > 0
                     else float(tau2)}
    return out


def simular_torneo(equipos: list[str], A: np.ndarray, D: np.ndarray, mu: float, h: float, n_sim: int,
                   seed: int = 0) -> dict:
    """Todos contra todos a una vuelta (localía al azar), goles ~ Poisson. Puntos y posición de cada equipo."""
    rng = np.random.default_rng(seed)
    n = len(equipos)
    i, j = np.triu_indices(n, 1)
    P = len(i)
    pts = np.zeros((n_sim, n))
    dg = np.zeros((n_sim, n))
    gfav = np.zeros((n_sim, n))
    loc = rng.random((n_sim, P)) < 0.5                              # True: i es local
    hi = np.where(loc, h, 1 / h)
    li = mu * A[i] * D[j] * hi
    lj = mu * A[j] * D[i] / hi
    gi, gj = rng.poisson(li), rng.poisson(lj)
    pi_ = np.where(gi > gj, 3, np.where(gi == gj, 1, 0))
    pj_ = np.where(gj > gi, 3, np.where(gi == gj, 1, 0))
    for k in range(P):
        pts[:, i[k]] += pi_[:, k]
        pts[:, j[k]] += pj_[:, k]
        dg[:, i[k]] += gi[:, k] - gj[:, k]
        dg[:, j[k]] += gj[:, k] - gi[:, k]
        gfav[:, i[k]] += gi[:, k]
        gfav[:, j[k]] += gj[:, k]
    clave = pts * 1e6 + dg * 1e3 + gfav + rng.random((n_sim, n)) * 1e-3    # desempate: DG, GF, azar
    pos = np.argsort(np.argsort(-clave, axis=1), axis=1) + 1
    return {"equipos": equipos, "pts": pts, "pos": pos}


def resumen_equipo(sim: dict, team: str, directos: int, play_in: tuple[int, int]) -> dict:
    k = sim["equipos"].index(team)
    p, pos = sim["pts"][:, k], sim["pos"][:, k]
    return {"pts_media": float(p.mean()), "pts_p10": float(np.quantile(p, 0.1)), "pts_p90": float(np.quantile(p, 0.9)),
            "pos_media": float(pos.mean()), "P_directo": float((pos <= directos).mean()),
            "P_play_in": float(((pos >= play_in[0]) & (pos <= play_in[1])).mean()),
            "P_fuera": float((pos > play_in[1]).mean()), "P_lider": float((pos == 1).mean()),
            "dist_pos": np.bincount(pos, minlength=len(sim["equipos"]) + 1)[1:].tolist(),
            "dist_pts": np.bincount(p.astype(int), minlength=int(p.max()) + 1).tolist()}


def _pred_partidos(filas: pl.DataFrame, A: float, D: float, fz: dict, mu: float, h: float, n_sim: int,
                   rng) -> dict:
    """Predicción de unos partidos concretos (rival y localía reales) con índices (A, D) del equipo."""
    ef, ec = _esperados(filas, fz, mu, h)
    lf, lc = A * ef, D * ec
    gf, gc = rng.poisson(lf, (n_sim, len(lf))), rng.poisson(lc, (n_sim, len(lc)))
    pts = np.where(gf > gc, 3, np.where(gf == gc, 1, 0)).sum(1)
    return {"xg_favor": float(lf.sum()), "xg_contra": float(lc.sum()), "pts_media": float(pts.mean()),
            "pts_p10": float(np.quantile(pts, 0.1)), "pts_p90": float(np.quantile(pts, 0.9))}


def validar(ll: pl.DataFrame, b: pl.DataFrame, fz: dict, mu: float, h: float, n_sim: int = 2000,
            seed: int = 0) -> dict:
    """Cada llegada proyectada con la receta (sin ella en μ_e, τ²) contra lo que pasó en sus primeros partidos.
    Se compara con la inercia (el plantel sin efecto de llegada)."""
    rng = np.random.default_rng(seed)
    por_id = {m: g for (m,), g in b.group_by("match_id")}
    err_m, err_0, cub, pred, real = [], [], [], [], []
    for r in ll.iter_rows(named=True):
        otras = ll.filter(~((pl.col("coach") == r["coach"]) & (pl.col("team") == r["team"])
                            & (pl.col("fecha") == r["fecha"])))
        ef = efecto_tecnico(otras, r["coach"], r["team"])
        filas = pl.concat([por_id[m].filter(pl.col("team") == r["team"]) for m in r["match_ids_post"] if m in por_id])
        A = r["A_pre"] * np.exp(ef["ataque"]["contraido"])
        D = r["D_pre"] * np.exp(ef["defensa"]["contraido"])
        p = _pred_partidos(filas, A, D, fz, mu, h, n_sim, rng)
        p0 = _pred_partidos(filas, r["A_pre"], r["D_pre"], fz, mu, h, n_sim, rng)
        y = r["pts_post"]
        pred.append(p["pts_media"])
        real.append(y)
        err_m.append(abs(p["pts_media"] - y) / r["partidos_post"])
        err_0.append(abs(p0["pts_media"] - y) / r["partidos_post"])
        cub.append(p["pts_p10"] <= y <= p["pts_p90"])
    if not pred:
        return {"llegadas": 0}
    from scipy import stats
    em, e0 = np.array(err_m), np.array(err_0)
    d = em - e0
    # ¿la receta le gana a la inercia? prueba pareada de los errores (Diebold-Mariano con pérdida absoluta,
    # llegadas independientes) y, como respaldo sin supuesto de normalidad, Wilcoxon de rangos con signo
    dm_t = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))) if len(d) > 1 and d.std(ddof=1) > 0 else float("nan")
    p_dm = float(2 * stats.t.sf(abs(dm_t), len(d) - 1)) if np.isfinite(dm_t) else float("nan")
    p_w = float(stats.wilcoxon(d).pvalue) if len(d) > 5 and np.any(d != 0) else float("nan")
    # ¿el intervalo del 80 % cubre el 80 %? binomial bilateral
    k = int(np.sum(cub))
    p_cob = float(stats.binomtest(k, len(cub), 0.8).pvalue)
    # intervalo CONFORME: el cuantil ⌈(n+1)·0.8⌉/n de los errores de todas las llegadas (puntos por partido).
    # Con llegadas intercambiables cubre ≥ 80 % por construcción (Vovk et al. 2005; Lei et al. 2018)
    res_pp = np.abs(np.array(pred) - np.array(real)) / np.array([r["partidos_post"] for r in ll.iter_rows(named=True)])
    kq = min(len(res_pp), int(np.ceil((len(res_pp) + 1) * 0.8)))
    q80 = float(np.sort(res_pp)[kq - 1])
    return {"llegadas": len(pred), "error_abs_por_partido": float(em.mean()),
            "error_abs_inercia": float(e0.mean()), "correlacion": float(np.corrcoef(pred, real)[0, 1]),
            "p_correlacion": float(stats.pearsonr(pred, real)[1]),
            "dif_error": float(d.mean()), "p_dm": p_dm, "p_wilcoxon": p_w,
            "cobertura_80": float(np.mean(cub)), "p_cobertura": p_cob, "conforme_80_pp": q80,
            "pred": pred, "real": real}


def proyectar(b: pl.DataFrame, coach: str, n_pre: int = 17, n_post: int = 17, n_sim: int = 10000,
              directos: int = 6, play_in: tuple[int, int] = (7, 10), seed: int = 0, validar_liga: bool = True) -> dict:
    """La proyección completa del técnico en su club más reciente."""
    mu, h = localia(b)
    fz = fuerza_temporada(b, mu, h)
    suyos = b.filter(pl.col("coach") == coach).sort("match_date")
    if suyos.height == 0:
        raise ValueError(f"«{coach}» no tiene partidos")
    club = suyos["team"][-1]
    en_club = suyos.filter(pl.col("team") == club)
    T = en_club["match_date"].min()
    ll = llegadas(b, fz, mu, h, n_pre, n_post, seed=seed)
    ef = efecto_tecnico(ll, coach, club)
    # el plantel que encontró: el club en sus últimos n_pre partidos antes de la llegada
    antes = b.filter((pl.col("team") == club) & (pl.col("match_date") < T)).tail(n_pre)
    A0, D0 = indices(antes, fz, mu, h)
    temporada = en_club["season_id"][0]
    equipos = sorted(set(b.filter(pl.col("season_id") == temporada)["team"].to_list()))
    Aeq, Deq = [], []
    for t in equipos:
        f = b.filter((pl.col("team") == t) & (pl.col("match_date") < T)).tail(n_pre)
        a, d = indices(f, fz, mu, h) if f.height >= 5 else (1.0, 1.0)
        Aeq.append(a)
        Deq.append(d)
    Aeq, Deq = np.array(Aeq), np.array(Deq)
    k = equipos.index(club)
    esc = {}
    for nombre, (ea, ed) in {"con_el": (ef["ataque"]["contraido"], ef["defensa"]["contraido"]),
                             "inercia": (ef["ataque"]["mu_liga"], ef["defensa"]["mu_liga"])}.items():
        A, D = Aeq.copy(), Deq.copy()
        A[k], D[k] = A0 * np.exp(ea), D0 * np.exp(ed)
        sim = simular_torneo(equipos, A, D, mu, h, n_sim, seed)
        esc[nombre] = {"A": float(A[k]), "D": float(D[k]), "xg_favor_partido": float(mu * A[k] * Deq.mean()),
                       "xg_contra_partido": float(mu * D[k] * Aeq.mean()),
                       **resumen_equipo(sim, club, directos, play_in)}
    # contraste: sus partidos reales en el club
    rng = np.random.default_rng(seed)
    reales = _pred_partidos(en_club, esc["con_el"]["A"], esc["con_el"]["D"], fz, mu, h, n_sim, rng)
    out = {"coach": coach, "club": club, "llegada": str(T), "temporada": temporada, "equipos": len(equipos),
           "mu": mu, "h": h, "n_pre": n_pre, "n_post": n_post, "plantel_A": A0, "plantel_D": D0, "efecto": ef,
           "escenarios": esc, "llegadas_suyas": ll.filter(pl.col("coach") == coach).drop("match_ids_post").to_dicts(),
           "contraste_real": {"partidos": en_club.height, "pts_reales": float(en_club["pts"].sum()),
                              "xg_favor_real": float(en_club["xgf"].sum()), "xg_contra_real": float(en_club["xga"].sum()),
                              **{f"proy_{k_}": v for k_, v in reales.items()}}}
    if validar_liga:
        out["validacion"] = v = validar(ll.filter(pl.col("coach") != coach), b, fz, mu, h, min(n_sim, 2000), seed)
        q = v.get("conforme_80_pp")
        if q is not None:
            # intervalos conformes del 80 %: la proyección ± q puntos por partido
            n_t = out["equipos"] - 1
            for e in out["escenarios"].values():
                e["pts_conforme"] = [max(0.0, e["pts_media"] - q * n_t), e["pts_media"] + q * n_t]
            c = out["contraste_real"]
            c["proy_conforme"] = [max(0.0, c["proy_pts_media"] - q * c["partidos"]), c["proy_pts_media"] + q * c["partidos"]]
    return out
