"""
Fase 3b -- Las decisiones del tecnico desde la banca (H13-H17).

Todo sale de los eventos aplanados:
  Substitution   (player = el que sale, position = su puesto; substitution_replacement_id = el que entra)
  Tactical Shift (cambio de formacion)
  Starting XI    (tactics_lineup: los once titulares)
  Shot / Own Goal For (goles, para el marcador minuto a minuto)

Tres tablas:
  panel_cambios  una fila por equipo-partido-minuto del 2º tiempo  -> H13, H14
  sustituciones  una fila por sustitución, con su tipo              -> H15
  equipo_partido una fila por equipo-partido (reacomodos, rotacion)  -> H16, H17
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from .inference import benjamini_hochberg
from .pesos import ajustar_pesos, columnas_estimables

MAX_CAMBIOS = 5
TRAMOS_5 = (50, 55, 60, 65, 70, 75, 80, 85)


def nivel_puesto(p: str | None) -> int | None:
    """Portero 0, defensa 1, contención 2, medio 3, mediapunta/extremo 4, delantero 5."""
    if p is None:
        return None
    if "Goalkeeper" in p:
        return 0
    if "Back" in p:                       # incluye Wing Back
        return 1
    if "Defensive Midfield" in p:
        return 2
    if "Attacking Midfield" in p or "Wing" in p:
        return 4
    if "Midfield" in p:
        return 3
    if "Forward" in p or "Striker" in p:
        return 5
    return None


# ----------------------------------------------------------------------
# Lectura
# ----------------------------------------------------------------------
def leer_eventos(lf: pl.LazyFrame) -> dict[str, pl.DataFrame]:
    cols = ["match_id", "index", "period", "minute", "type", "team", "player_id", "position",
            "substitution_replacement_id", "tactics_formation", "tactics_lineup", "shot_outcome"]
    ev = lf.select([c for c in cols if c in lf.collect_schema().names()]).filter(pl.col("period") <= 2)
    sub = ev.filter(pl.col("type") == "Substitution").collect()
    shift = ev.filter(pl.col("type") == "Tactical Shift").select("match_id", "team", "period", "minute").collect()
    xi = ev.filter(pl.col("type") == "Starting XI").select("match_id", "team", "tactics_formation",
                                                           "tactics_lineup").collect()
    goles = (ev.filter(((pl.col("type") == "Shot") & (pl.col("shot_outcome") == "Goal"))
                       | (pl.col("type") == "Own Goal For"))
               .select("match_id", "team", "minute").collect())
    # puesto del que ENTRA: el de su primer evento con puesto en ese partido
    ids = sub["substitution_replacement_id"].drop_nulls().unique().to_list()
    pos = (ev.filter(pl.col("player_id").is_in(ids) & pl.col("position").is_not_null())
             .sort("match_id", "index").group_by("match_id", "player_id")
             .agg(pl.col("position").first().alias("puesto_entra")).collect())
    return {"sub": sub, "shift": shift, "xi": xi, "goles": goles, "pos": pos}


# ----------------------------------------------------------------------
# H13, H14: tiempo de los cambios
# ----------------------------------------------------------------------
def panel_cambios(ev: dict, tp: pl.DataFrame, minutos=range(45, 91)) -> pl.DataFrame:
    sub = ev["sub"]
    ventanas = (sub.group_by("match_id", "team", "period", "minute").len()
                   .rename({"len": "n_cambios"}))
    goles = ev["goles"]
    gol = {}
    for mid, team, minute in goles.iter_rows():
        gol.setdefault(mid, []).append((minute, team))
    vent = {}
    for mid, team, per, minute, n in ventanas.iter_rows():
        vent.setdefault((mid, team), []).append((per, minute, n))
    rival = {}
    for mid, g in tp.group_by("match_id"):
        eq = g["team"].to_list()
        if len(eq) == 2:
            rival[(mid[0], eq[0])], rival[(mid[0], eq[1])] = eq[1], eq[0]
    filas = []
    for mid, team, coach, local, elo_dif, season in tp.select(
            "match_id", "team", "coach", "local", "elo_dif", "season_id").iter_rows():
        rv = rival.get((mid, team))
        if rv is None:
            continue
        vs = vent.get((mid, team), [])
        usados_1t = sum(n for per, m, n in vs if per == 1)
        v2 = {m: n for per, m, n in vs if per == 2}
        cambios = usados_1t
        ventanas_usadas = int(usados_1t > 0)
        gs = gol.get(mid, [])
        for m in minutos:
            if cambios >= MAX_CAMBIOS:
                break
            gf = sum(1 for mm, t in gs if mm < m and t == team)
            gc = sum(1 for mm, t in gs if mm < m and t == rv)
            y = m in v2
            filas.append((mid, team, coach, local, elo_dif, season, m, gf - gc, ventanas_usadas, y))
            if y:
                cambios += v2[m]
                ventanas_usadas += 1
    return pl.DataFrame(filas, schema={"match_id": pl.Int64, "team": pl.Utf8, "coach": pl.Utf8,
                                       "local": pl.Boolean, "elo_dif": pl.Float64, "season_id": pl.Int64,
                                       "minuto": pl.Int64, "dif_goles": pl.Int64,
                                       "ventanas_usadas": pl.Int64, "cambia": pl.Boolean}, orient="row")


def _diseno_panel(p: pl.DataFrame, f: np.ndarray, temporadas: list) -> tuple[np.ndarray, list[str]]:
    per = (p["dif_goles"] < 0).to_numpy().astype(float)
    gan = (p["dif_goles"] > 0).to_numpy().astype(float)
    m = p["minuto"].to_numpy()
    cols = {"intercepto": np.ones(p.height), "perdiendo": per, "ganando": gan}
    for a in TRAMOS_5:                       # referencia: minuto 45-49
        cols[f"min_{a}"] = ((m >= a) & (m < a + 5)).astype(float) if a < 85 else (m >= a).astype(float)
    vu = p["ventanas_usadas"].to_numpy()
    cols["ventanas_1"] = (vu == 1).astype(float)
    cols["ventanas_2+"] = (vu >= 2).astype(float)
    cols["local"] = p["local"].to_numpy().astype(float)
    cols["elo_dif"] = p["elo_dif"].to_numpy().astype(float)
    for s in temporadas[1:]:
        cols[f"temporada_{s}"] = (p["season_id"] == s).to_numpy().astype(float)
    cols["f"] = f
    # Forma temporal PROPIA del foco (ADR-v2-25): sin esto, un técnico que desplaza
    # sus cambios en el tiempo se lee como un efecto proporcional y se aplana.
    # Desviación temporal SUAVE del foco (ADR-v2-25): nivel f y pendiente f×tiempo.
    # Escalones por tramo producían separación cuando el foco no cambiaba en algún
    # tramo (coeficiente → −∞, varianza → 0, rechazo sin efecto en datos sintéticos).
    cols["f×tiempo"] = f * (m - 67.5) / 10.0
    cols["f×perdiendo"] = f * per
    cols["f×ganando"] = f * gan
    n = list(cols)
    return np.column_stack([cols[c] for c in n]), n


def modelo_tiempo(p: pl.DataFrame, foco: str, n_sim: int, seed: int) -> dict:
    temporadas = sorted(p["season_id"].drop_nulls().unique().to_list())
    f = (p["coach"] == foco).fill_null(False).to_numpy().astype(float)
    X, nom = _diseno_panel(p, f, temporadas)
    keep = columnas_estimables(X, nom)
    nom = [n for n, k in zip(nom, keep) if k]
    y = p["cambia"].to_numpy().astype(float)
    m = ajustar_pesos(X[:, keep], np.column_stack([1 - y, y]), p["match_id"].to_numpy(), nom, ref=0)
    sims = m.simular(n_sim, seed)
    # Traducción: minuto esperado de la PRIMERA ventana del 2º tiempo, sin cambios previos,
    # con el marcador fijo, promediando sobre los partidos del foco (sus localías y Elo).
    base = p.filter((pl.col("coach") == foco) & (pl.col("minuto") == 45)).select(
        "match_id", "team", "coach", "local", "elo_dif", "season_id")
    out = {}
    for marcador, dg in (("empatando", 0), ("perdiendo", -1), ("ganando", 1)):
        filas = base.join(pl.DataFrame({"minuto": list(range(45, 91))}), how="cross").with_columns(
            pl.lit(dg).alias("dif_goles"), pl.lit(0).alias("ventanas_usadas"), pl.lit(False).alias("cambia"))
        filas = filas.sort("match_id", "team", "minuto")
        X1, _ = _diseno_panel(filas, np.ones(filas.height), temporadas)
        X0, _ = _diseno_panel(filas, np.zeros(filas.height), temporadas)
        X1, X0 = X1[:, keep], X0[:, keep]
        nmin = 46

        def minuto_esperado(X_, th=None):
            h = m.predecir(X_, th)[:, 1].reshape(-1, nmin)
            S = np.cumprod(1 - h, axis=1)
            dens = h * np.concatenate([np.ones((h.shape[0], 1)), S[:, :-1]], axis=1)
            mins = np.arange(45, 91)
            return float(((dens * mins).sum(1) / np.maximum(dens.sum(1), 1e-12)).mean()), float(dens.sum(1).mean())
        e1, p1 = minuto_esperado(X1)
        e0, p0 = minuto_esperado(X0)
        d = np.array([minuto_esperado(X1, th)[0] - minuto_esperado(X0, th)[0] for th in sims])
        out[marcador] = {"minuto_foco": e1, "minuto_liga": e0, "dif": e1 - e0,
                         "lo": float(np.quantile(d, 0.025)), "hi": float(np.quantile(d, 0.975)),
                         "P_cambia_antes_90_foco": p1, "P_cambia_antes_90_liga": p0}
    return {"modelo": m, "H13": m.wald(["f", "f×tiempo"]),
            "H14": m.wald(["f×perdiendo", "f×ganando"]),
            "primer_cambio": out, "n_filas": p.height}


# ----------------------------------------------------------------------
# H15: tipo de cambio
# ----------------------------------------------------------------------
TIPOS = ("defensivo", "mismo puesto", "ofensivo")


def sustituciones(ev: dict, tp: pl.DataFrame) -> pl.DataFrame:
    s = (ev["sub"].join(ev["pos"], left_on=["match_id", "substitution_replacement_id"],
                        right_on=["match_id", "player_id"], how="left")
                  .with_columns(pl.col("position").map_elements(nivel_puesto, return_dtype=pl.Int64).alias("n_sale"),
                                pl.col("puesto_entra").map_elements(nivel_puesto, return_dtype=pl.Int64).alias("n_entra"))
                  .filter(pl.col("n_sale").is_not_null() & pl.col("n_entra").is_not_null()
                          & (pl.col("n_sale") > 0) & (pl.col("n_entra") > 0)))       # sin porteros
    goles = ev["goles"]
    s = s.join(tp.select("match_id", "team", "coach", "local", "elo_dif", "season_id"), on=["match_id", "team"])
    gl = goles.group_by("match_id").agg(pl.col("team"), pl.col("minute"))
    gd = {mid: list(zip(ts, ms)) for mid, ts, ms in gl.iter_rows()}
    dif = [sum((1 if t == team else -1) for t, mm in gd.get(mid, []) if mm < minute)
           for mid, team, minute in s.select("match_id", "team", "minute").iter_rows()]
    delta = (s["n_entra"] - s["n_sale"]).to_numpy()
    tipo = np.where(delta >= 1, 2, np.where(delta <= -1, 0, 1))
    return s.with_columns(pl.Series("dif_goles", dif, dtype=pl.Int64), pl.Series("tipo", tipo))


def modelo_tipo(s: pl.DataFrame, foco: str, n_sim: int, seed: int) -> dict:
    temporadas = sorted(s["season_id"].drop_nulls().unique().to_list())
    f = (s["coach"] == foco).fill_null(False).to_numpy().astype(float)
    per = (s["dif_goles"] < 0).to_numpy().astype(float)
    gan = (s["dif_goles"] > 0).to_numpy().astype(float)
    mi = s["minute"].to_numpy()
    cols = {"intercepto": np.ones(s.height), "perdiendo": per, "ganando": gan,
            "min_60-74": ((mi >= 60) & (mi < 75)).astype(float), "min_75+": (mi >= 75).astype(float),
            "local": s["local"].to_numpy().astype(float), "elo_dif": s["elo_dif"].to_numpy().astype(float)}
    for t_ in temporadas[1:]:
        cols[f"temporada_{t_}"] = (s["season_id"] == t_).to_numpy().astype(float)
    cols["f"] = f
    cols["f×perdiendo"] = f * per
    nom = list(cols)
    X = np.column_stack([cols[c] for c in nom])
    keep = columnas_estimables(X, nom)
    nom = [n for n, k in zip(nom, keep) if k]
    R = np.eye(3)[s["tipo"].to_numpy()]
    m = ajustar_pesos(X[:, keep], R, s["match_id"].to_numpy(), nom, ref=1)
    sims = m.simular(n_sim, seed)
    jf = nom.index("f") if "f" in nom else None
    # P(tipo) del foco contra la liga, en sus propios cambios, perdiendo y empatando
    Xf = X[:, keep][f == 1]
    res = {}
    for marcador, (vp, vg) in (("perdiendo", (1, 0)), ("empatando", (0, 0))):
        X1 = Xf.copy()
        for n_, v in (("perdiendo", vp), ("ganando", vg), ("f×perdiendo", vp)):
            if n_ in nom:
                X1[:, nom.index(n_)] = v
        X0 = X1.copy()
        for n_ in ("f", "f×perdiendo"):
            if n_ in nom:
                X0[:, nom.index(n_)] = 0
        p1, p0 = m.predecir(X1).mean(0), m.predecir(X0).mean(0)
        d = np.stack([m.predecir(X1, th).mean(0) - m.predecir(X0, th).mean(0) for th in sims])
        res[marcador] = {"P_foco": p1.tolist(), "P_liga": p0.tolist(), "dif": (p1 - p0).tolist(),
                         "lo": np.quantile(d, 0.025, 0).tolist(), "hi": np.quantile(d, 0.975, 0).tolist()}
    return {"modelo": m, "H15": m.wald(["f", "f×perdiendo"]), "por_marcador": res,
            "n": s.height, "n_foco": int(f.sum()), "estimable_f": jf is not None}


# ----------------------------------------------------------------------
# H16, H17: reacomodos y rotación
# ----------------------------------------------------------------------
def once_titular(lineup_json: str | None) -> frozenset:
    if not lineup_json:
        return frozenset()
    try:
        return frozenset(int(x["player"]["id"]) for x in json.loads(lineup_json) if x.get("player"))
    except (ValueError, KeyError, TypeError):
        return frozenset()


def tabla_equipo_partido(ev: dict, tp: pl.DataFrame) -> pl.DataFrame:
    shifts = ev["shift"].group_by("match_id", "team").len().rename({"len": "reacomodos"})
    xi = ev["xi"].with_columns(pl.col("tactics_lineup").map_elements(
        lambda s: sorted(once_titular(s)), return_dtype=pl.List(pl.Int64)).alias("once"))
    t = (tp.join(shifts, on=["match_id", "team"], how="left").with_columns(pl.col("reacomodos").fill_null(0))
           .join(xi.select("match_id", "team", "tactics_formation", "once"), on=["match_id", "team"], how="left")
           .sort("team", "match_date", "match_id"))
    rot = []
    prev: dict = {}
    for team, coach, once in t.select("team", "coach", "once").iter_rows():
        s = frozenset(once or [])
        k = (team, coach)
        if k in prev and prev[k] and len(s) == 11:
            a = prev[k]
            rot.append(1 - len(a & s) / len(a | s))
        else:
            rot.append(None)
        if len(s) == 11:
            prev[k] = s
    return t.with_columns(pl.Series("rotacion", rot, dtype=pl.Float64))


def _boot_media(foco: np.ndarray, liga: np.ndarray, n_boot: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    d_obs = foco.mean() - liga.mean()
    d = np.array([rng.choice(foco, len(foco)).mean() - rng.choice(liga, len(liga)).mean() for _ in range(n_boot)])
    lo, hi = 2 * d_obs - np.quantile(d, 0.975), 2 * d_obs - np.quantile(d, 0.025)
    p = min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean()) + 1 / (n_boot + 1))
    return {"foco": float(foco.mean()), "liga": float(liga.mean()), "dif": float(d_obs),
            "lo": float(lo), "hi": float(hi), "p": float(p), "n_foco": int(len(foco)), "n_liga": int(len(liga))}


def correr_decisiones(ev: dict, tp: pl.DataFrame, foco: str, cfg2: dict, seed: int) -> dict:
    if ev["sub"].height == 0:
        raise ValueError("Los eventos no traen sustituciones. ¿El aplanado incluye "
                         "`substitution_replacement_id` y `position`? (dtcoach aplanar --forzar)")
    partidos_foco = tp.filter(pl.col("coach") == foco)["match_id"].unique().to_list()
    if not partidos_foco:
        raise ValueError(f"'{foco}' no aparece como DT en la tabla equipo-partido")
    # referencia: equipos-partido de partidos donde el foco NO jugó (como en la fase 2)
    muestra = (pl.col("coach") == foco) | ~pl.col("match_id").is_in(partidos_foco)
    tp_ref = tp.filter(muestra)
    # El panel se arma con la tabla COMPLETA: el marcador necesita al rival. Armarlo
    # con tp_ref descartaba en silencio todas las filas del foco (su rival no estaba).
    pan = panel_cambios(ev, tp).filter(muestra)
    n_foco = pan.filter(pl.col("coach") == foco).height
    if n_foco == 0:
        raise RuntimeError("El panel de cambios no tiene filas del foco: revisar la unión con el rival.")
    t13 = modelo_tiempo(pan, foco, cfg2["n_sim"], seed)
    sus = sustituciones(ev, tp_ref)
    t15 = modelo_tipo(sus, foco, cfg2["n_sim"], seed)
    ep = tabla_equipo_partido(ev, tp_ref)
    es = pl.col("coach") == foco
    h16 = _boot_media(ep.filter(es)["reacomodos"].to_numpy().astype(float),
                      ep.filter(~es)["reacomodos"].to_numpy().astype(float), cfg2["n_boot"], seed)
    r = ep.filter(pl.col("rotacion").is_not_null())
    h17 = _boot_media(r.filter(es)["rotacion"].to_numpy(), r.filter(~es)["rotacion"].to_numpy(),
                      cfg2["n_boot"], seed)
    H = {"H13": {"nombre": "tiempo de los cambios", **t13["H13"]},
         "H14": {"nombre": "banca contra el marcador", **t13["H14"]},
         "H15": {"nombre": "tipo de cambio", **t15["H15"]},
         "H16": {"nombre": "reacomodos de formación por partido", **h16},
         "H17": {"nombre": "rotación del once (1 − Jaccard)", **h17}}
    # H17 es EXPLORATORIA (enmienda del 2026-09-26, 11_HIPOTESIS): la rotación se confunde
    # con el calendario de competiciones que no están en los datos. Se reporta, pero no
    # entra a la familia de BH ni recibe 🟢.
    claves = [k for k in H if k != "H17"]
    q, rech = benjamini_hochberg(np.array([H[k]["p"] for k in claves]), cfg2["alpha"])
    for k, qi, ri in zip(claves, q, rech):
        H[k]["q"] = float(qi)
        H[k]["etiqueta"] = "🟢" if ri else ("🟡" if H[k]["p"] < cfg2["alpha"] else "⚪")
    H["H17"]["q"] = float("nan")
    H["H17"]["etiqueta"] = "🔎"
    H["H17"]["nota"] = "exploratoria: confundida con el calendario (Copa, Concachampions no están en los datos)"
    formaciones = (ep.filter(es & pl.col("tactics_formation").is_not_null())
                     .group_by("team", "tactics_formation").len().sort(["team", "len"], descending=[False, True]))
    return {"hipotesis": H, "primer_cambio": t13["primer_cambio"], "tipo_cambio": t15["por_marcador"],
            "n": {"equipo_minuto": t13["n_filas"], "sustituciones": t15["n"], "sustituciones_foco": t15["n_foco"],
                  "equipo_partido": ep.height},
            "formaciones_foco": formaciones.to_dicts(), "_ep": ep, "_pan": pan}
