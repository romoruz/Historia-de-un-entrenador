"""
Impacto de las sustituciones (reto 5.3, G4): qué cambia en el juego cuando el técnico mueve la banca.

EL EFECTO DE UN CAMBIO: DIFERENCIAS EN DIFERENCIAS EMPAREJADAS (03_FRAMEWORK §10)
--------------------------------------------------------------------------------
Para cada cambio en el minuto m (45 + v ≤ m ≤ 90 − v), y una medida Y del partido:
    Δ = Y[m, m + v) − Y[m − v, m)        (lo que cambió en los v minutos siguientes)
El final del partido cambia solo (cansancio, marcador): por eso Δ se compara con el Δ
medio de los cambios de la LIGA en la misma celda (tramo de 5 min × signo del marcador):
    efecto = media_foco [ Δ_i − Δ̄_liga(celda_i) ]
IC por bootstrap de PARTIDOS (los del foco y los de la liga se remuestrean por separado).
Medidas:
  xg_propio, obv_propio, xg_rival      sumas en la ventana
  field_tilt                           pases propios en el último tercio / los de ambos
  fam_k                                fracción de secuencias propias de cada familia
                                       (responsabilidades de la mezcla)
Se estima para TODOS los cambios y por tipo (defensivo, mismo puesto, ofensivo; como H15).
No es causal: los cambios responden a lo que pasa. Emparejar por celda quita lo que
tienen en común con los cambios de la liga, no lo que el técnico ve y la liga no.

QUIÉN ENTRA
-----------
Los suplentes más usados: entradas, minuto medio de entrada, y xG a favor y en contra
por 90 minutos del equipo con él en la cancha contra el mismo equipo antes de su entrada
en esos partidos (descriptivo; pocos partidos por jugador).

REACOMODO TRAS EL CAMBIO
------------------------
Fracción de los cambios seguidos de un Tactical Shift del mismo equipo en ≤ `ventana_shift`
minutos: ¿el cambio viene con cambio de dibujo? Foco contra liga, bootstrap de partidos.
"""
from __future__ import annotations

import numpy as np
import polars as pl

TIPOS = {0: "defensivo", 1: "mismo puesto", 2: "ofensivo"}


def panel_minuto(ev: pl.DataFrame, t_seq: pl.DataFrame | None, K: int) -> pl.DataFrame:
    """Por partido, equipo y minuto del 2º tiempo: xG, OBV, pases al último tercio y secuencias por familia."""
    p = (ev.filter(pl.col("period") == 2).group_by("match_id", "team", "minute")
         .agg(pl.col("shot_statsbomb_xg").fill_null(0.0).sum().alias("xg"),
              pl.col("obv_total_net").fill_null(0.0).sum().alias("obv"),
              ((pl.col("type") == "Pass") & (pl.col("x") >= 80)).sum().cast(pl.Float64).alias("tercio")))
    if t_seq is not None and t_seq.height:
        s = (t_seq.filter(pl.col("period") == 2).group_by("match_id", "team", "minute")
             .agg(pl.len().cast(pl.Float64).alias("n_seq"),
                  *[pl.col(f"r_{k + 1}").sum().alias(f"r{k}") for k in range(K)]))
        p = p.join(s, on=["match_id", "team", "minute"], how="full", coalesce=True)
    llaves = ("match_id", "team", "minute")
    return p.with_columns([pl.col(c).fill_null(0.0) for c in p.columns if c not in llaves])


MEDIDAS_SUMA = ("xg_propio", "obv_propio", "xg_rival")


def _deltas(p_eq: dict, p_riv: dict, m: int, v: int, K: int) -> list[float]:
    """Δ de cada medida para un cambio en el minuto m (NaN si la razón no está definida)."""
    def suma(d, col, a, b):
        if d is None:
            return 0.0
        mi, x = d["minute"], d[col]
        return float(x[(mi >= a) & (mi < b)].sum())

    out = [suma(p_eq, "xg", m, m + v) - suma(p_eq, "xg", m - v, m),
           suma(p_eq, "obv", m, m + v) - suma(p_eq, "obv", m - v, m),
           suma(p_riv, "xg", m, m + v) - suma(p_riv, "xg", m - v, m)]
    # field tilt
    ta, tb = suma(p_eq, "tercio", m, m + v), suma(p_riv, "tercio", m, m + v)
    ta0, tb0 = suma(p_eq, "tercio", m - v, m), suma(p_riv, "tercio", m - v, m)
    out.append(ta / (ta + tb) - ta0 / (ta0 + tb0) if (ta + tb) > 0 and (ta0 + tb0) > 0 else np.nan)
    for k in range(K):
        if p_eq is None or "n_seq" not in p_eq:
            out.append(np.nan)
            continue
        n1, n0 = suma(p_eq, "n_seq", m, m + v), suma(p_eq, "n_seq", m - v, m)
        r1, r0 = suma(p_eq, f"r{k}", m, m + v), suma(p_eq, f"r{k}", m - v, m)
        out.append(r1 / n1 - r0 / n0 if n1 > 0 and n0 > 0 else np.nan)
    return out


def did_cambios(panel: pl.DataFrame, subs: pl.DataFrame, tp: pl.DataFrame, foco: str, familias: list[str],
                ventana: int = 10, n_boot: int = 1000, seed: int = 0) -> dict:
    """Efecto de TODOS los cambios del foco (dif. en dif. emparejada por celda), total y por tipo."""
    K = len(familias)
    medidas = [*MEDIDAS_SUMA, "field_tilt", *[f"fam_{k}" for k in range(K)]]
    s = (subs.filter((pl.col("minute") >= 45 + ventana) & (pl.col("minute") <= 90 - ventana))
         .join(tp.select("match_id", "team", "rival", "coach_rival"), on=["match_id", "team"], how="left"))
    arr = {}
    for (mid, team), d in panel.group_by("match_id", "team"):
        arr[(mid, team)] = {c: d[c].to_numpy() for c in d.columns if c not in ("match_id", "team")}
    filas = []
    for r in s.iter_rows(named=True):
        dl = _deltas(arr.get((r["match_id"], r["team"])), arr.get((r["match_id"], r["rival"])), r["minute"],
                     ventana, K)
        filas.append((r["match_id"], r["coach"], r["coach_rival"], int(r["minute"] // 5),
                      int(np.sign(r["dif_goles"])), int(r["tipo"]), dl))
    if not filas:
        return {"nota": "sin cambios en la ventana"}
    mids = np.array([f[0] for f in filas])
    coach = np.array([f[1] for f in filas], dtype=object)
    riv = np.array([f[2] for f in filas], dtype=object)
    celda = np.array([f[3] * 10 + f[4] for f in filas])
    tipo = np.array([f[5] for f in filas])
    D = np.array([f[6] for f in filas], dtype=float)
    partidos_foco = set(mids[(coach == foco) | (riv == foco)])
    es_f = coach == foco
    es_l = np.array([m not in partidos_foco for m in mids])
    celdas = np.unique(celda)
    ci = {c: i for i, c in enumerate(celdas)}
    cidx = np.array([ci[c] for c in celda])

    def por_partido(mask):
        u = np.unique(mids[mask])
        mi = {m: i for i, m in enumerate(u)}
        S = np.zeros((len(u), len(celdas), D.shape[1]))
        N = np.zeros_like(S)
        for m, c, d in zip(mids[mask], cidx[mask], D[mask]):
            ok = np.isfinite(d)
            S[mi[m], c, ok] += d[ok]
            N[mi[m], c, ok] += 1
        return S, N

    def efecto(Sf, Nf, Sl, Nl):
        base = Sl.sum(0) / np.maximum(Nl.sum(0), 1)            # (celdas, medidas)
        num = (Sf.sum(0) - Nf.sum(0) * base).sum(0)
        return num / np.maximum(Nf.sum(0).sum(0), 1)

    def resultado(mask_f):
        Sf, Nf = por_partido(mask_f)
        Sl, Nl = por_partido(es_l)
        if len(Sf) == 0:
            return None
        est = efecto(Sf, Nf, Sl, Nl)
        rng = np.random.default_rng(seed)
        B = np.array([efecto(Sf[i], Nf[i], Sl[j], Nl[j]) for i, j in
                      ((rng.integers(0, len(Sf), len(Sf)), rng.integers(0, len(Sl), len(Sl))) for _ in range(n_boot))])
        out = {"n": int(mask_f.sum())}
        for c, nombre in enumerate(medidas):
            b = B[:, c]
            out[nombre] = {"efecto": float(est[c]), "lo": float(np.quantile(b, 0.025)),
                           "hi": float(np.quantile(b, 0.975)),
                           "p": float(max(1 / n_boot, min(1, 2 * min((b <= 0).mean(), (b >= 0).mean()))))}
        return out
    out = {"ventana_min": ventana, "medidas": medidas, "familias": familias,
           "n_cambios_foco": int(es_f.sum()), "n_cambios_liga": int(es_l.sum()), "todos": resultado(es_f),
           "por_tipo": {}}
    for t, nombre in TIPOS.items():
        m = es_f & (tipo == t)
        if m.sum() >= 10:
            out["por_tipo"][nombre] = resultado(m)
    return out


def quien_entra(subs: pl.DataFrame, panel: pl.DataFrame, nombres: dict, foco: str, top: int = 12) -> list[dict]:
    """Suplentes más usados del foco y el xG del equipo por 90' con él en cancha contra antes de entrar."""
    s = subs.filter(pl.col("coach") == foco).join(
        panel.select("match_id", "team").unique(), on=["match_id", "team"], how="inner")
    if s.height == 0:
        return []
    rival_de = {}
    for (mid,), g in panel.select("match_id", "team").unique().group_by("match_id"):
        eq = g["team"].to_list()
        if len(eq) == 2:
            rival_de[(mid, eq[0])], rival_de[(mid, eq[1])] = eq[1], eq[0]
    arr = {(mid, t): (d["minute"].to_numpy(), d["xg"].to_numpy()) for (mid, t), d in panel.group_by("match_id", "team")}
    filas = []
    for pid, g in s.group_by("substitution_replacement_id"):
        pid = pid[0]
        if pid is None:
            continue
        xf1 = xa1 = m1 = xf0 = xa0 = m0 = 0.0
        for mid, team, minuto in g.select("match_id", "team", "minute").iter_rows():
            a = arr.get((mid, team))
            b = arr.get((mid, rival_de.get((mid, team))))
            for (mi, xg), es_f in ((a, True), (b, False)):
                if mi is None:
                    continue
                d, antes = xg[mi >= minuto].sum(), xg[(mi >= 45) & (mi < minuto)].sum()
                if es_f:
                    xf1, xf0 = xf1 + d, xf0 + antes
                else:
                    xa1, xa0 = xa1 + d, xa0 + antes
            m1 += max(90 - minuto, 1)
            m0 += max(minuto - 45, 1)
        filas.append({"player_id": int(pid), "jugador": nombres.get(int(pid), str(pid)), "entradas": g.height,
                      "minuto_medio": float(g["minute"].mean()),
                      "puesto_entra": g["puesto_entra"].drop_nulls().mode().to_list()[0]
                      if g["puesto_entra"].drop_nulls().len() else None,
                      "xg_favor_90_con": 90 * xf1 / m1, "xg_contra_90_con": 90 * xa1 / m1,
                      "xg_favor_90_antes": 90 * xf0 / m0, "xg_contra_90_antes": 90 * xa0 / m0})
    return sorted(filas, key=lambda r: -r["entradas"])[:top]


def reacomodo_tras_cambio(subs: pl.DataFrame, shift: pl.DataFrame, tp: pl.DataFrame, foco: str,
                          ventana: int = 3, n_boot: int = 1000, seed: int = 0) -> dict:
    """Fracción de cambios con un Tactical Shift del mismo equipo en ≤ `ventana` min después."""
    sh = {}
    for mid, team, per, minute in shift.select("match_id", "team", "period", "minute").iter_rows():
        sh.setdefault((mid, team), []).append(minute)
    s = subs.join(tp.select("match_id", "team", "coach_rival"), on=["match_id", "team"], how="left")
    y = np.array([any(m <= x <= m + ventana for x in sh.get((mid, team), []))
                  for mid, team, m in s.select("match_id", "team", "minute").iter_rows()], dtype=float)
    mid = s["match_id"].to_numpy()
    coach = s["coach"].to_numpy()
    riv = s["coach_rival"].to_numpy()
    pf = set(mid[(coach == foco) | (riv == foco)])
    f = coach == foco
    lg = np.array([m not in pf for m in mid])
    if f.sum() == 0:
        return {"nota": "sin cambios del foco"}
    rng = np.random.default_rng(seed)

    def boot(mask):
        u, g = np.unique(mid[mask], return_inverse=True)
        sy, sn = np.bincount(g, weights=y[mask]), np.bincount(g).astype(float)
        return sy, sn
    fy, fn = boot(f)
    ly, ln = boot(lg)
    B = []
    for _ in range(n_boot):
        i, j = rng.integers(0, len(fy), len(fy)), rng.integers(0, len(ly), len(ly))
        B.append(fy[i].sum() / fn[i].sum() - ly[j].sum() / ln[j].sum())
    B = np.array(B)
    vf, vl = fy.sum() / fn.sum(), ly.sum() / ln.sum()
    return {"foco": float(vf), "liga": float(vl), "dif": float(vf - vl), "lo": float(np.quantile(B, 0.025)),
            "hi": float(np.quantile(B, 0.975)),
            "p": float(max(1 / n_boot, min(1, 2 * min((B <= 0).mean(), (B >= 0).mean())))),
            "cambios_foco": int(f.sum()), "ventana_min": ventana}
