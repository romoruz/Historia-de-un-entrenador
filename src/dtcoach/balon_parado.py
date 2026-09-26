"""
Fase E -- Balón parado (reto 5.4): ofensivo y defensivo, desde los objetos del framework.

JUGADA A BALÓN PARADO (03_FRAMEWORK §5)
---------------------------------------
Una posesión de StatsBomb cuyo `play_pattern` es From Corner, From Free Kick o From
Throw In, clasificada por dónde se ejecuta el SAQUE (primer evento del equipo):
  corner          todos
  tiro_libre      x ≥ `tl_min_x` (campo rival)
  lateral         x ≥ `lateral_min_x` (lateral en zona de peligro)
Su desenlace es el de la posesión: remates, xG y goles del equipo en ella.

TASAS COMO PROCESO DE POISSON CON EXPOSICIÓN
--------------------------------------------
Remates (o goles) de un equipo-partido desde un tipo de jugada:
    y ~ Poisson(n_jugadas · exp(β0 + β1 · foco))
exp(β1) = cuántas veces más remata (o marca) el foco por jugada que la liga. Se
estima por IRLS con varianza sandwich por partido (válida aunque haya
sobredispersión, que se reporta con el cociente de Pearson).

ZONAS
-----
Densidad de los remates y del primer contacto (fin del saque), por kernel
gaussiano, normalizada POR JUGADA: "remates por jugada y por m²". La diferencia
foco − liga es el mapa de zonas fuertes (ataque) o vulnerables (defensa).
"""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy import stats

PATRONES = {"From Corner": "corner", "From Free Kick": "tiro_libre", "From Throw In": "lateral"}
TIPOS = ("corner", "tiro_libre", "lateral")

_SING = {"corner": "corner", "tiro_libre": "tiro libre en campo rival", "lateral": "lateral en zona de peligro"}
_PLUR = {"corner": "corners", "tiro_libre": "tiros libres en campo rival", "lateral": "laterales en zona de peligro"}
DEFINICIONES = {
    **{f"xg_{t}": {"nombre": f"xG por {_SING[t]}", "formato": "{:.3f}"} for t in TIPOS},
    **{f"remate_{t}": {"nombre": f"{_PLUR[t]} con remate", "formato": "{:.3f}"} for t in TIPOS},
    "goles_bp": {"nombre": "goles a balón parado por partido", "formato": "{:.3f}"},
    "dist_marca": {"nombre": "distancia media de marca en corners (m, 360)", "formato": "{:.2f}"},
    "sobra": {"nombre": "defensores menos atacantes en la zona de remate (360)", "formato": "{:.2f}"},
}


def jugadas(ev: pl.DataFrame, cfg: dict) -> pl.DataFrame:
    """Una fila por jugada a balón parado, con su saque, primer contacto y desenlace."""
    base = ev.filter(pl.col("play_pattern").is_in(list(PATRONES)) & (pl.col("team") == pl.col("possession_team")))
    primero = (base.sort("match_id", "index").group_by("match_id", "possession", maintain_order=True)
               .agg(pl.col("team").first(), pl.col("play_pattern").first().alias("patron"),
                    pl.col("id").first().alias("id_saque"), pl.col("x").first().alias("x_saque"),
                    pl.col("y").first().alias("y_saque"), pl.col("fin_x").first().alias("x_contacto"),
                    pl.col("fin_y").first().alias("y_contacto"), pl.col("type").first().alias("tipo_saque")))
    rem = base.filter(pl.col("type") == "Shot")
    des = rem.group_by("match_id", "possession").agg(
        pl.len().alias("remates"), pl.col("shot_statsbomb_xg").fill_null(0.0).sum().alias("xg"),
        (pl.col("shot_outcome") == "Goal").sum().alias("goles"),
        pl.col("x").alias("x_remates"), pl.col("y").alias("y_remates"))
    j = (primero.join(des, on=["match_id", "possession"], how="left")
         .with_columns(pl.col("remates").fill_null(0), pl.col("xg").fill_null(0.0), pl.col("goles").fill_null(0),
                       pl.col("patron").replace_strict(PATRONES).alias("tipo")))
    return j.filter((pl.col("tipo") == "corner")
                    | ((pl.col("tipo") == "tiro_libre") & (pl.col("x_saque") >= cfg["tl_min_x"]))
                    | ((pl.col("tipo") == "lateral") & (pl.col("x_saque") >= cfg["lateral_min_x"])))


def metricas(j: pl.DataFrame, marc: pl.DataFrame | None, tp: pl.DataFrame) -> list[pl.DataFrame]:
    out = []
    for t in TIPOS:
        s = j.filter(pl.col("tipo") == t).group_by("match_id", "team").agg(
            pl.col("xg").sum().alias(f"xg_{t}__n"), pl.len().cast(pl.Float64).alias(f"xg_{t}__d"),
            (pl.col("remates") > 0).sum().cast(pl.Float64).alias(f"remate_{t}__n"),
            pl.len().cast(pl.Float64).alias(f"remate_{t}__d"))
        out.append(s)
    out.append(j.group_by("match_id", "team").agg(pl.col("goles").sum().cast(pl.Float64).alias("goles_bp__n"),
                                                   pl.lit(1.0).alias("goles_bp__d")))
    if marc is not None and marc.height:
        # el marcaje es del equipo que DEFIENDE el saque: el rival del que saca
        m = (marc.join(j.select("id_saque", "match_id", "team"), left_on=["match_id", "id"],
                       right_on=["match_id", "id_saque"])
             .join(tp.select("match_id", "team", "rival"), on=["match_id", "team"])
             .drop("team").rename({"rival": "team"}))
        out.append(m.group_by("match_id", "team").agg(
            pl.col("dist_marca").sum().alias("dist_marca__n"), pl.len().cast(pl.Float64).alias("dist_marca__d"),
            pl.col("sobra").sum().cast(pl.Float64).alias("sobra__n"), pl.len().cast(pl.Float64).alias("sobra__d")))
    return out


def ids_saques(ev: pl.DataFrame, cfg: dict) -> dict[int, set]:
    """Por partido, los ids de los saques de corner y tiro libre lateral (para el marcaje 360)."""
    j = jugadas(ev, cfg).filter(pl.col("tipo").is_in(["corner", "tiro_libre"]))
    out: dict[int, set] = {}
    for m, i in j.select("match_id", "id_saque").iter_rows():
        out.setdefault(int(m), set()).add(i)
    return out


# ----------------------------------------------------------------------
# Poisson con exposición, IRLS y sandwich por partido
# ----------------------------------------------------------------------
def poisson_exposicion(y: np.ndarray, n: np.ndarray, X: np.ndarray, grupos: np.ndarray,
                       max_iter: int = 100) -> dict:
    y, n = np.asarray(y, float), np.asarray(n, float)
    keep = n > 0
    y, n, X, grupos = y[keep], n[keep], X[keep], np.asarray(grupos)[keep]
    b = np.zeros(X.shape[1])
    b[0] = np.log(max(y.sum(), 1e-9) / n.sum())
    for _ in range(max_iter):
        mu = n * np.exp(X @ b)
        H = X.T @ (X * mu[:, None])
        paso = np.linalg.solve(H + 1e-10 * np.eye(len(b)), X.T @ (y - mu))
        b = b + paso
        if np.abs(paso).max() < 1e-10:
            break
    mu = n * np.exp(X @ b)
    H = X.T @ (X * mu[:, None])
    U = X * (y - mu)[:, None]
    _, g = np.unique(grupos, return_inverse=True)
    S = np.zeros((g.max() + 1, X.shape[1]))
    np.add.at(S, g, U)
    G = S.shape[0]
    Hi = np.linalg.inv(H)
    V = Hi @ (S.T @ S) @ Hi * G / max(G - 1, 1)
    dispersion = float(((y - mu) ** 2 / np.maximum(mu, 1e-12)).sum() / max(len(y) - len(b), 1))
    return {"b": b, "V": V, "dispersion_pearson": dispersion, "n": len(y), "partidos": int(G)}


def razon_de_tasas(j: pl.DataFrame, tp: pl.DataFrame, foco: str, tipo: str, que: str = "remates",
                   lado: str = "propio") -> dict:
    """exp(β1): remates (o goles) por jugada del foco sobre los de la liga, con IC sandwich."""
    s = (j.filter(pl.col("tipo") == tipo).group_by("match_id", "team")
         .agg(pl.col(que).sum().alias("y"), pl.len().alias("n"))
         .join(tp.select("match_id", "team", "coach", "coach_rival"), on=["match_id", "team"], how="left"))
    col = "coach" if lado == "propio" else "coach_rival"
    partidos_foco = s.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique()
    es_f = (s[col] == foco).fill_null(False)
    s = s.filter(es_f | ~pl.col("match_id").is_in(partidos_foco.to_list()))
    f = (s[col] == foco).fill_null(False).to_numpy().astype(float)
    if f.sum() == 0:
        return {"nota": "sin jugadas del foco"}
    X = np.column_stack([np.ones(s.height), f])
    r = poisson_exposicion(s["y"].to_numpy(), s["n"].to_numpy(), X, s["match_id"].to_numpy())
    se = float(np.sqrt(r["V"][1, 1]))
    z = r["b"][1] / se if se > 0 else float("nan")
    return {"tipo": tipo, "que": que, "lado": lado, "tasa_liga": float(np.exp(r["b"][0])),
            "tasa_foco": float(np.exp(r["b"][0] + r["b"][1])), "razon": float(np.exp(r["b"][1])),
            "lo": float(np.exp(r["b"][1] - 1.96 * se)), "hi": float(np.exp(r["b"][1] + 1.96 * se)),
            "p": float(2 * stats.norm.sf(abs(z))) if np.isfinite(z) else float("nan"),
            "dispersion_pearson": r["dispersion_pearson"], "jugadas_foco": int(np.sum(s["n"].to_numpy()[f == 1])),
            "partidos_foco": int((f == 1).sum())}


# ----------------------------------------------------------------------
# Zonas: densidad por jugada
# ----------------------------------------------------------------------
def densidad(x: np.ndarray, y: np.ndarray, n_jugadas: int, bw: float = 3.0, paso: float = 2.0,
             xmin: float = 60.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Kernel gaussiano en la mitad rival: remates por jugada y por m²."""
    gx = np.arange(xmin, 120 + 1e-9, paso)
    gy = np.arange(0, 80 + 1e-9, paso)
    X, Y = np.meshgrid(gx, gy)
    Z = np.zeros_like(X)
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    for a, b in zip(x[ok], y[ok]):
        Z += np.exp(-((X - a) ** 2 + (Y - b) ** 2) / (2 * bw * bw))
    Z /= 2 * np.pi * bw * bw * max(n_jugadas, 1)
    return gx, gy, Z


def mapas(j: pl.DataFrame, tp: pl.DataFrame, foco: str, tipo: str, lado: str = "propio") -> dict:
    s = j.filter(pl.col("tipo") == tipo).join(tp.select("match_id", "team", "coach", "coach_rival"),
                                              on=["match_id", "team"], how="left")
    col = "coach" if lado == "propio" else "coach_rival"
    partidos_foco = s.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique()
    f = s.filter(pl.col(col) == foco)
    lg = s.filter(~pl.col("match_id").is_in(partidos_foco.to_list()))
    out = {}
    for nombre, d in (("foco", f), ("liga", lg)):
        xs = np.concatenate([np.asarray(v, float) for v in d["x_remates"].drop_nulls().to_list()] or [np.array([])])
        ys = np.concatenate([np.asarray(v, float) for v in d["y_remates"].drop_nulls().to_list()] or [np.array([])])
        gx, gy, Zr = densidad(xs, ys, d.height)
        _, _, Zc = densidad(d["x_contacto"].to_numpy(), d["y_contacto"].to_numpy(), d.height)
        out[nombre] = {"remates": Zr, "contacto": Zc, "jugadas": d.height, "n_remates": len(xs)}
    out["gx"], out["gy"] = gx, gy
    return out
