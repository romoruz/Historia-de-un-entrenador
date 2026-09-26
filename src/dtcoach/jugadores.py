"""
Fase D -- Uso de jugadores (reto 5.3): roles, protagonistas, cambios y alineaciones.

1. LA CADENA SOBRE JUGADORES (grafo de pases)
   Estados: los jugadores de una etapa (técnico-club) con ≥ `min_acciones`, más dos
   absorbentes: REMATE y PÉRDIDA. Desde el jugador i: pase completo a j, remate, o
   pérdida (pase incompleto, Dispossessed, Miscontrol). Es la misma matemática de la
   fase 1 con otro espacio de estados:
     N = (I − Q)⁻¹           toques esperados de cada jugador por posesión
     ν = μᵀN / Σ             por quién pasa el balón (estacionaria de la cadena reiniciada)
     B = N R                 P(la posesión termina en remate | el balón está en i): quién
                             tiene el balón cuando la jugada "se vuelve peligrosa"
2. ROLES POR CLUSTERING ESPECTRAL
   A = W + Wᵀ (pases entre jugadores), laplaciano normalizado L = I − D^{-1/2} A D^{-1/2}.
   El número de grupos es el mayor salto entre autovalores consecutivos (eigengap,
   von Luxburg 2007); los grupos salen de k-means sobre los autovectores
   normalizados. Un grupo = jugadores que se pasan el balón entre sí más que con el
   resto: la estructura del sistema (un lado, la salida, el triángulo de ataque).
3. PROTAGONISTAS DE CADA FAMILIA: fracción de las acciones de cada familia (pesadas
   por la responsabilidad r_sk de su secuencia) que ejecuta cada jugador, y quién las inicia.
4. IMPACTO DE LOS CAMBIOS: diferencia en diferencias. Para el primer cambio del
   segundo tiempo, Δ = (xG, OBV, xG del rival en los `ventana` minutos después) −
   (los `ventana` antes). Contrafactual: el Δ medio de la liga en el mismo tramo de 5
   minutos y con el mismo signo del marcador. IC por bootstrap de partidos.
5. ESTABILIDAD DEL ONCE: Jaccard entre el once titular y el del partido anterior del
   mismo equipo con el mismo técnico.
"""
from __future__ import annotations

import numpy as np
import polars as pl

PERDIDAS = ("Dispossessed", "Miscontrol")


def cadena_jugadores(ev: pl.DataFrame, partidos: list[int], team: str, min_acciones: int = 150) -> dict:
    e = ev.filter(pl.col("match_id").is_in(partidos) & (pl.col("team") == team) & pl.col("player_id").is_not_null())
    cuenta = e.filter(pl.col("type").is_in(["Pass", "Carry", "Shot"])).group_by("player_id").agg(
        pl.len().alias("acciones"), pl.col("player").first(), pl.col("position").mode().first(),
        pl.col("x").mean().alias("x_media"), pl.col("y").mean().alias("y_media"),
        pl.col("match_id").n_unique().alias("partidos"))
    jug = cuenta.filter(pl.col("acciones") >= min_acciones).sort("acciones", descending=True)
    ids = jug["player_id"].to_list()
    m = len(ids)
    if m < 3:
        return {"jugadores": jug.to_dicts(), "nota": "menos de 3 jugadores con acciones suficientes"}
    pos = {p: i for i, p in enumerate(ids)}
    W = np.zeros((m, m))
    Rm = np.zeros((m, 2))                       # remate, pérdida
    pases = e.filter((pl.col("type") == "Pass") & pl.col("player_id").is_in(ids))
    comp = pases.filter(pl.col("pass_outcome").is_null() & pl.col("pass_recipient_id").is_in(ids))
    for a, b, n in comp.group_by("player_id", "pass_recipient_id").len().iter_rows():
        W[pos[a], pos[b]] += n
    inc = pases.filter(pl.col("pass_outcome").is_not_null()).group_by("player_id").len()
    for a, n in inc.iter_rows():
        Rm[pos[a], 1] += n
    for a, n in e.filter(pl.col("type").is_in(list(PERDIDAS)) & pl.col("player_id").is_in(ids)).group_by(
            "player_id").len().iter_rows():
        Rm[pos[a], 1] += n
    for a, n in e.filter((pl.col("type") == "Shot") & pl.col("player_id").is_in(ids)).group_by(
            "player_id").len().iter_rows():
        Rm[pos[a], 0] += n
    # pases a jugadores fuera del grupo (pocos minutos): el balón sale del grupo = se trata como pérdida del grupo
    fuera = pases.filter(pl.col("pass_outcome").is_null() & ~pl.col("pass_recipient_id").is_in(ids)).group_by(
        "player_id").len()
    for a, n in fuera.iter_rows():
        Rm[pos[a], 1] += n
    tot = W.sum(1) + Rm.sum(1)
    Q = W / np.maximum(tot, 1)[:, None]
    R = Rm / np.maximum(tot, 1)[:, None]
    rho = float(np.max(np.abs(np.linalg.eigvals(Q))))
    if rho >= 1 - 1e-9:
        return {"jugadores": jug.to_dicts(), "nota": "la cadena de jugadores no absorbe (clase cerrada): revisar datos"}
    N = np.linalg.inv(np.eye(m) - Q)
    B = N @ R
    ini = (e.sort("match_id", "index").group_by("match_id", "possession", maintain_order=True)
           .agg(pl.col("player_id").first()).filter(pl.col("player_id").is_in(ids)))
    mu = np.bincount([pos[p] for p in ini["player_id"].to_list()], minlength=m).astype(float)
    mu = mu / max(mu.sum(), 1)
    nu = mu @ N
    grupos, k, autovalores = roles_espectrales(W)
    filas = []
    for p, r in zip(ids, jug.iter_rows(named=True)):
        i = pos[p]
        filas.append({**r, "flujo": float(nu[i] / nu.sum()), "toques_por_posesion": float(nu[i]),
                      "P_remate_desde": float(B[i, 0]), "grupo": int(grupos[i])})
    return {"jugadores": filas, "W": W.tolist(), "ids": ids, "k_grupos": int(k),
            "autovalores": autovalores.tolist(), "rho_Q": rho}


def roles_espectrales(W: np.ndarray, kmax: int = 6, seed: int = 0) -> tuple[np.ndarray, int, np.ndarray]:
    from .voronoi import _kmeans
    A = W + W.T
    d = A.sum(1)
    Dm = 1.0 / np.sqrt(np.maximum(d, 1e-12))
    L = np.eye(len(A)) - (Dm[:, None] * A * Dm[None, :])
    w, V = np.linalg.eigh(L)
    m = len(A)
    kmax = min(kmax, m - 1)
    if kmax < 2:
        return np.zeros(m, int), 1, w
    gaps = np.diff(w[: kmax + 1])                  # w[k] - w[k-1], k = 1..kmax
    k = int(np.argmax(gaps[1:]) + 2)              # al menos 2 grupos
    U = V[:, :k]
    U = U / np.maximum(np.linalg.norm(U, axis=1, keepdims=True), 1e-12)
    c = _kmeans(U, k, seed)
    lab = ((U[:, None, :] - c[None]) ** 2).sum(-1).argmin(1)
    return lab, k, w


def protagonistas(trans: pl.DataFrame, t_seq: pl.DataFrame, partidos: list[int], team: str, K: int,
                  top: int = 5) -> dict:
    """Por familia: los jugadores que ejecutan (y los que inician) más de sus acciones."""
    r = t_seq.select("seq_uid", *[f"r_{k + 1}" for k in range(K)])
    a = (trans.filter(pl.col("match_id").is_in(partidos) & (pl.col("team") == team)
                      & (pl.col("action_type") != "TERMINAL") & pl.col("player_id").is_not_null())
         .sort("seq_uid", "event_index")
         .with_columns((pl.col("seq_uid") != pl.col("seq_uid").shift(1)).fill_null(True).alias("inicia"))
         .join(r, on="seq_uid", how="inner"))
    out = {}
    for k in range(K):
        c = f"r_{k + 1}"
        g = a.group_by("player_id").agg(pl.col("player").drop_nulls().mode().first(), pl.col(c).sum().alias("peso"),
                                                  pl.col(c).filter(pl.col("inicia")).sum().alias("inicios"))
        tot, tot_i = float(g["peso"].sum()), float(g["inicios"].sum())
        g = g.with_columns((pl.col("peso") / tot).alias("frac_acciones"),
                           (pl.col("inicios") / max(tot_i, 1e-12)).alias("frac_inicios"))
        out[k] = {"ejecutan": g.sort("frac_acciones", descending=True).head(top).to_dicts(),
                  "inician": g.sort("frac_inicios", descending=True).head(top).to_dicts()}
    return out


# ----------------------------------------------------------------------
# Impacto de los cambios
# ----------------------------------------------------------------------
def panel_minuto(ev: pl.DataFrame) -> pl.DataFrame:
    """xG y OBV por equipo y minuto (segundo tiempo)."""
    return (ev.filter(pl.col("period") == 2).group_by("match_id", "team", "minute")
            .agg(pl.col("shot_statsbomb_xg").fill_null(0.0).sum().alias("xg"),
                 pl.col("obv_total_net").fill_null(0.0).sum().alias("obv")))


def impacto_cambios(ev: pl.DataFrame, subs: pl.DataFrame, tp: pl.DataFrame, foco: str, ventana: int = 10,
                    n_boot: int = 1000, seed: int = 0) -> dict:
    """`subs`: de `decisiones.sustituciones` (match_id, team, minute, tipo, dif_goles, coach)."""
    pm = panel_minuto(ev)
    primero = (subs.filter((pl.col("minute") >= 45 + ventana) & (pl.col("minute") <= 90 - ventana))
               .sort("minute").group_by("match_id", "team").agg(pl.all().first()))
    pm_r = pm.rename({"team": "rival", "xg": "xg_r", "obv": "obv_r"})
    x = primero.join(tp.select("match_id", "team", "rival", "coach_rival"), on=["match_id", "team"], how="left")
    filas = []
    g_pm = {k: d for k, d in pm.group_by("match_id", "team")}
    g_r = {k: d for k, d in pm_r.group_by("match_id", "rival")}
    for r in x.iter_rows(named=True):
        a = g_pm.get((r["match_id"], r["team"]))
        b = g_r.get((r["match_id"], r["rival"]))
        m = r["minute"]
        vals = {}
        for nombre, d, cols in (("propio", a, ("xg", "obv")), ("rival", b, ("xg_r",))):
            for c in cols:
                if d is None:
                    vals[c] = 0.0
                    continue
                mi, v = d["minute"].to_numpy(), d[c].to_numpy()
                vals[c] = float(v[(mi >= m) & (mi < m + ventana)].sum() - v[(mi >= m - ventana) & (mi < m)].sum())
        filas.append({"match_id": r["match_id"], "team": r["team"], "coach": r["coach"],
                      "coach_rival": r["coach_rival"], "minute": m, "tipo": r["tipo"],
                      "marcador": int(np.sign(r["dif_goles"])), "tramo": int(m // 5), **vals})
    d = pl.DataFrame(filas)
    partidos_foco = d.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique()
    f = d.filter(pl.col("coach") == foco)
    lg = d.filter(~pl.col("match_id").is_in(partidos_foco.to_list()))
    cols = ["xg", "obv", "xg_r"]

    # celdas del contrafactual: (tramo de 5 min, signo del marcador)
    celdas = sorted(set(d.select("tramo", "marcador").iter_rows()))
    ci = {c: i for i, c in enumerate(celdas)}

    def por_partido(df):
        """(partidos, celdas, 1 + 3): conteo y sumas de Δ por celda, para bootstrap por sumas."""
        ms = df["match_id"].unique().sort().to_list()
        mi = {m: i for i, m in enumerate(ms)}
        A = np.zeros((len(ms), len(celdas), 1 + len(cols)))
        for r in df.select("match_id", "tramo", "marcador", *cols).iter_rows():
            A[mi[r[0]], ci[(r[1], r[2])], 0] += 1
            A[mi[r[0]], ci[(r[1], r[2])], 1:] += r[3:]
        return A

    def did_sumas(F, Lg):
        nf, nl = F[:, :, 0].sum(0), Lg[:, :, 0].sum(0)
        base = Lg[:, :, 1:].sum(0) / np.maximum(nl, 1)[:, None]         # Δ medio de la liga por celda
        return (F[:, :, 1:].sum(0) - nf[:, None] * base).sum(0) / max(nf.sum(), 1)

    Af, Al = por_partido(f), por_partido(lg)
    est = did_sumas(Af, Al)
    rng = np.random.default_rng(seed)
    D = np.array([did_sumas(Af[rng.integers(0, len(Af), len(Af))], Al[rng.integers(0, len(Al), len(Al))])
                  for _ in range(n_boot)])
    out = {"n_cambios_foco": f.height, "n_cambios_liga": lg.height, "ventana_min": ventana}
    for c_, nombre in enumerate(["xg_propio", "obv_propio", "xg_rival"]):
        dd = D[:, c_]
        out[nombre] = {"did": float(est[c_]), "lo": float(np.quantile(dd, 0.025)), "hi": float(np.quantile(dd, 0.975)),
                       "p": float(max(1 / n_boot, min(1, 2 * min((dd <= 0).mean(), (dd >= 0).mean()))))}
    out["por_tipo"] = {}
    for t, nombre in ((0, "defensivo"), (1, "mismo puesto"), (2, "ofensivo")):
        ft, lt = f.filter(pl.col("tipo") == t), lg.filter(pl.col("tipo") == t)
        if ft.height >= 5 and lt.height:
            out["por_tipo"][nombre] = {"n": ft.height, "did": did_sumas(por_partido(ft), por_partido(lt)).tolist()}
    return out


def estabilidad_once(xi: pl.DataFrame, tp: pl.DataFrame) -> pl.DataFrame:
    """Métrica equipo-partido: Jaccard del once con el del partido anterior (mismo equipo y técnico)."""
    from .decisiones import once_titular
    x = (xi.join(tp.select("match_id", "team", "coach", "match_date"), on=["match_id", "team"], how="inner")
         .sort("match_date"))
    filas = []
    prev: dict = {}
    for r in x.iter_rows(named=True):
        s = once_titular(r["tactics_lineup"])
        clave = (r["team"], r["coach"])
        if clave in prev and s and prev[clave]:
            p = prev[clave]
            filas.append({"match_id": r["match_id"], "team": r["team"],
                          "estabilidad_once__n": len(s & p) / len(s | p), "estabilidad_once__d": 1.0})
        if s:
            prev[clave] = s
    return pl.DataFrame(filas, schema={"match_id": pl.Int64, "team": pl.Utf8, "estabilidad_once__n": pl.Float64,
                                       "estabilidad_once__d": pl.Float64})
