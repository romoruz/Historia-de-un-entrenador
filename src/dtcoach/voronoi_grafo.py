"""
EXPERIMENTO EXPLORATORIO (ADR-v2-54, no adoptado): Voronoi × grafo de jugadores.

La sección 13.3 (espacio: Voronoi, envolvente, húngaro) y la 13.5 (grafo de pases, ν = μN, cortes
espectrales) no se tocan hoy. Aquí se unen: por jugador, el ESPACIO con que EJECUTÓ cada acción
(área de Voronoi local, R = 10 m, 128 puntos) cruzado con QUÉ decidió (pase / conducción / remate)
y con el VALOR de zona de la Prop. 2.4, V = N c. Es «calidad de decisión condicionada al espacio
disponible».

VALOR DE UNA DECISIÓN
---------------------
V(z) = valor de zona = xG esperado que aún le queda a una posesión que está en la zona z (cadena
absorbente de TODA la liga, c_i = xG / acciones desde i; los 4 estados de fase se promedian con
el peso de sus visitas). Para una acción que parte de la zona z0:
  * intención   ΔV_int  = V(z_fin) − V(z0)        pase y conducción: adónde apunta;
                                                   remate: xG del remate − V(z0)
  * realizado   ΔV_real = ΔV_int si el pase/la conducción sale bien; si el pase se pierde, −V(z0)
Como V depende sobre todo de DÓNDE se está, las dos se RESIDUALIZAN contra la media de la liga en
la misma (zona de origen × tipo de acción): ΔV⊥. Así «decidir bien» no es «estar cerca del arco».

LO QUE ESTO NO PUEDE HACER (se escribe en el reporte)
-----------------------------------------------------
* El 360 es una FOTO del evento, no tracking: se mide con cuánto espacio EJECUTÓ, no «qué tan bien
  recibe» (no hay posición antes de la recepción).
* Solo hay jugadores visibles en cámara; el área se recorta a lo visible y se exige frac_visible ≥ 0.5.
* n por jugador (eventos con 360); se descartan los de n < `min_n_jugador` (50).
* Exploratorio: no entra al BH global ni es una hipótesis pre-registrada.
* «¿Depende del entrenador?» solo es identificable con el MISMO jugador bajo DISTINTOS técnicos:
  se cuenta cuántos cumplen n ≥ `min_n_cruce` con ≥ 2 técnicos; con menos de `min_jugadores_cruce`
  (15) no se concluye.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy import stats

from .absorbing import Cadena, recompensa_xg

TIPOS = ("pase", "conduccion", "remate")


def valor_de_zonas(S_total: np.ndarray, X_total: np.ndarray, nt: int, ns: int, n_fases: int) -> np.ndarray:
    """V por ZONA (n_zonas,) con la cadena de la liga. `S_total`: (nt*ns,) transiciones; `X_total`: (nt,) xG por estado."""
    C = np.asarray(S_total, float).reshape(nt, ns)
    n = C.sum(1)
    P = C / np.maximum(n, 1)[:, None]
    P[n == 0] = 0.0
    P[n == 0, nt + 2] = 1.0                                   # estado sin visitas: se pierde (LOSS)
    c = recompensa_xg(n, X_total)
    V = Cadena(P, nt).valor(c)
    Vz = V.reshape(-1, n_fases)
    w = n.reshape(-1, n_fases)
    return (Vz * w).sum(1) / np.maximum(w.sum(1), 1e-12)


def acciones(ev: pl.DataFrame, rasgos: pl.DataFrame, space, Vz: np.ndarray, frac_min: float = 0.5,
             d_max: float = 2.0) -> pl.DataFrame:
    """Una fila por acción con 360 (pase, conducción, remate) con espacio, decisión y ΔV."""
    e = ev.filter(pl.col("type").is_in(["Pass", "Carry", "Shot"]) & pl.col("player_id").is_not_null())
    r = rasgos.select("match_id", "id", "area_local", "frac_visible", "d_actor_evento", "n_rivales")
    a = (e.join(r, on=["match_id", "id"], how="inner")
         .filter((pl.col("frac_visible") >= frac_min) & (pl.col("d_actor_evento") <= d_max)
                 & pl.col("area_local").is_not_null() & pl.col("area_local").is_not_nan()))
    tipo = (pl.when(pl.col("type") == "Pass").then(pl.lit("pase")).when(pl.col("type") == "Carry")
            .then(pl.lit("conduccion")).otherwise(pl.lit("remate")))
    a = a.with_columns(tipo.alias("tipo"))
    z0 = space.zone_of(a["x"].to_numpy(), a["y"].to_numpy())
    zf = space.zone_of(np.nan_to_num(a["fin_x"].to_numpy(), nan=0.0), np.nan_to_num(a["fin_y"].to_numpy(), nan=40.0))
    xg = a["shot_statsbomb_xg"].fill_null(0.0).to_numpy()
    es_remate = (a["tipo"] == "remate").to_numpy()
    fin_ok = a["fin_x"].is_not_null().to_numpy()
    dv_int = np.where(es_remate, xg - Vz[z0], np.where(fin_ok, Vz[zf] - Vz[z0], np.nan))
    perdida = ((a["tipo"] == "pase") & a["pass_outcome"].is_not_null()).to_numpy()
    dv_real = np.where(perdida, -Vz[z0], dv_int)
    return a.select("match_id", "id", "team", "player_id", "player", "tipo", "area_local", "n_rivales").with_columns(
        pl.Series("z0", z0), pl.Series("dv_int", dv_int), pl.Series("dv_real", dv_real),
        pl.Series("perdida", perdida)).filter(pl.col("dv_int").is_not_nan())


def residualizar(a: pl.DataFrame) -> pl.DataFrame:
    """ΔV⊥ = ΔV − media de la liga en la misma (zona de origen × tipo)."""
    m = a.group_by("z0", "tipo").agg(pl.col("dv_int").mean().alias("_mi"), pl.col("dv_real").mean().alias("_mr"))
    return (a.join(m, on=["z0", "tipo"]).with_columns((pl.col("dv_int") - pl.col("_mi")).alias("dv_int_perp"),
                                                      (pl.col("dv_real") - pl.col("_mr")).alias("dv_real_perp"))
            .drop("_mi", "_mr"))


def por_espacio(a: pl.DataFrame, cortes: tuple[float, float] | None = None) -> dict:
    """Descriptivo de la liga: qué decide y cuánto vale según el espacio (terciles del área local)."""
    q = cortes or tuple(np.quantile(a["area_local"].to_numpy(), [1 / 3, 2 / 3]))
    g = a.with_columns(pl.when(pl.col("area_local") <= q[0]).then(pl.lit("poco"))
                       .when(pl.col("area_local") <= q[1]).then(pl.lit("medio")).otherwise(pl.lit("mucho")).alias("espacio"))
    out = {"cortes_m2": [float(q[0]), float(q[1])], "niveles": {}}
    for e in ("poco", "medio", "mucho"):
        s = g.filter(pl.col("espacio") == e)
        n = max(s.height, 1)
        out["niveles"][e] = {"n": s.height, **{f"frac_{t}": float((s["tipo"] == t).sum() / n) for t in TIPOS},
                             "dv_real_perp": float(s["dv_real_perp"].mean()), "dv_int_perp": float(s["dv_int_perp"].mean()),
                             "perdida_pase": float(s.filter(pl.col("tipo") == "pase")["perdida"].mean())}
    return out


def tabla_jugadores(a: pl.DataFrame, min_n: int = 50) -> pl.DataFrame:
    """Una fila por (jugador, técnico-club). `a` debe traer `coach`."""
    g = a.group_by("player_id", "player", "team", "coach").agg(
        pl.len().alias("n"), pl.col("match_id").n_unique().alias("partidos"),
        pl.col("area_local").mean().alias("area_media"), pl.col("area_local").median().alias("area_mediana"),
        (pl.col("tipo") == "conduccion").mean().alias("frac_conduccion"),
        (pl.col("tipo") == "pase").mean().alias("frac_pase"), (pl.col("tipo") == "remate").mean().alias("frac_remate"),
        pl.col("dv_int_perp").mean().alias("dv_int_perp"), pl.col("dv_real_perp").mean().alias("dv_real_perp"),
        pl.col("perdida").filter(pl.col("tipo") == "pase").mean().alias("perdida_pase"))
    return g.filter(pl.col("n") >= min_n).sort("n", descending=True)


def pendiente_espacio(a: pl.DataFrame) -> float:
    """Pendiente de ΔV⊥(real) sobre el área (por 100 m²) con efectos fijos de jugador-etapa; se usa solo el signo y el tamaño."""
    x = a["area_local"].to_numpy() / 100.0
    y = a["dv_real_perp"].to_numpy()
    return float(np.cov(x, y)[0, 1] / np.var(x, ddof=1)) if len(x) > 3 and np.var(x) > 0 else float("nan")


def cruce_grafo(jug: pl.DataFrame, grafo: dict, etapa_team: str, etapa_coach: str) -> list[dict]:
    """Une la tabla del jugador con ν (flujo), P(remate | balón en él) y el grupo espectral de su etapa."""
    if "jugadores" not in grafo or "flujo" not in (grafo["jugadores"][0] if grafo["jugadores"] else {}):
        return []
    g = {r["player_id"]: r for r in grafo["jugadores"]}
    out = []
    for r in jug.filter((pl.col("team") == etapa_team) & (pl.col("coach") == etapa_coach)).iter_rows(named=True):
        if r["player_id"] in g:
            out.append({**r, "flujo": g[r["player_id"]]["flujo"], "P_remate_desde": g[r["player_id"]]["P_remate_desde"],
                        "grupo": g[r["player_id"]]["grupo"], "k_grupos": grafo["k_grupos"]})
    return out


def correlacion(x: list[float], y: list[float]) -> dict:
    if len(x) < 6:
        return {"n": len(x), "rho": float("nan"), "p": float("nan")}
    rho, p = stats.spearmanr(x, y)
    return {"n": len(x), "rho": float(rho), "p": float(p)}


def _celdas(a: pl.DataFrame, min_n: int, min_partidos: int = 3) -> dict:
    """{(jugador, técnico): medias por partido de ΔV⊥(realizado) y del área}, solo celdas con n ≥ min_n y ≥ min_partidos partidos."""
    g = a.filter(pl.col("coach").is_not_null()).group_by("player_id", "coach", "match_id").agg(
        pl.len().alias("n"), pl.col("dv_real_perp").mean().alias("dv"), pl.col("area_local").mean().alias("area"))
    tot = g.group_by("player_id", "coach").agg(pl.col("n").sum().alias("N"), pl.len().alias("m"))
    ok = tot.filter((pl.col("N") >= min_n) & (pl.col("m") >= min_partidos))
    g = g.join(ok.select("player_id", "coach"), on=["player_id", "coach"])
    out: dict = {}
    for (pid, coach), s in g.group_by("player_id", "coach"):
        out[(pid, coach)] = {"dv": s["dv"].to_numpy(), "area": s["area"].to_numpy(), "w": s["n"].to_numpy(),
                             "match": s["match_id"].to_numpy()}
    return out


def _z(x: np.ndarray, y: np.ndarray) -> float:
    """Welch entre dos medias de medias-por-partido (el partido es la unidad: los eventos de un partido no son independientes)."""
    se = np.sqrt(x.var(ddof=1) / len(x) + y.var(ddof=1) / len(y))
    return float((x.mean() - y.mean()) / se) if se > 0 else float("nan")


def mismo_jugador(a: pl.DataFrame, min_n_cruce: int, foco: str | None = None, n_perm: int = 500, seed: int = 0) -> dict:
    """El único diseño identificable de «¿depende del técnico?»: el MISMO jugador con ≥ 2 técnicos.

    Para cada par (técnico A, técnico B) del mismo jugador, z = diferencia de medias de ΔV⊥(realizado)
    por partido / error estándar (Welch, unidad = partido). Bajo «el técnico no importa», E[z²] ≈ 1. El
    estadístico es la media de z² sobre todos los pares; su nula sale de PERMUTAR, dentro de cada jugador,
    qué partidos pertenecen a qué técnico (tamaños de celda fijos). OJO: un mismo jugador con técnicos distintos
    casi siempre cambia también de club, de compañeros y de época; esta prueba NO separa técnico de club/época."""
    celdas = _celdas(a, min_n_cruce)
    por: dict = {}
    for (pid, coach), c in celdas.items():
        por.setdefault(pid, {})[coach] = c
    multi = {pid: cs for pid, cs in por.items() if len(cs) >= 2}
    nombre = dict(a.group_by("player_id").agg(pl.col("player").first()).iter_rows())
    pares, z_obs = [], []
    for pid, cs in multi.items():
        ks = sorted(cs)
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                z = _z(cs[ks[i]]["dv"], cs[ks[j]]["dv"])
                if np.isfinite(z):
                    pares.append({"player_id": pid, "player": nombre.get(pid), "coach_a": ks[i], "coach_b": ks[j], "z": z,
                                  "partidos_a": len(cs[ks[i]]["dv"]), "partidos_b": len(cs[ks[j]]["dv"]),
                                  "d_dv_real_perp": float(cs[ks[i]]["dv"].mean() - cs[ks[j]]["dv"].mean()),
                                  "d_area": float(cs[ks[i]]["area"].mean() - cs[ks[j]]["area"].mean())})
                    z_obs.append(z * z)
    out = {"jugadores_con_2_tecnicos": len(multi), "pares_n": len(pares), "pares": pares,
           "con_el_foco": len({p["player_id"] for p in pares if foco in (p["coach_a"], p["coach_b"])}) if foco else 0,
           "z2_media": float(np.mean(z_obs)) if z_obs else float("nan"), "p_perm": float("nan")}
    if len(pares) >= 3:
        rng = np.random.default_rng(seed)
        nulas = []
        for _ in range(n_perm):
            zs = []
            for pid, cs in multi.items():
                ks = sorted(cs)
                pool = np.concatenate([cs[k]["dv"] for k in ks])
                perm = rng.permutation(len(pool))
                trozos, ini = {}, 0
                for k in ks:
                    m = len(cs[k]["dv"])
                    trozos[k] = pool[perm[ini:ini + m]]
                    ini += m
                for i in range(len(ks)):
                    for j in range(i + 1, len(ks)):
                        z = _z(trozos[ks[i]], trozos[ks[j]])
                        if np.isfinite(z):
                            zs.append(z * z)
            nulas.append(np.mean(zs) if zs else np.nan)
        nulas = np.array(nulas)
        out["z2_nula_media"] = float(np.nanmean(nulas))
        out["p_perm"] = float((1 + np.sum(nulas >= out["z2_media"])) / (1 + np.sum(np.isfinite(nulas))))
    return out
