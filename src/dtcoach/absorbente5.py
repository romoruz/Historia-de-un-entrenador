"""
EXPERIMENTO (Mejora F, ADR-v2-60, 63): quinto absorbente INTERRUPCIÓN_FAVOR.

Una secuencia que acaba porque al equipo le hicieron falta (o ganó un córner, un lateral, un penal) no terminó en
una PÉRDIDA: la Def. 1.3 la manda ahí porque la falta recibida no es acción. Aquí:

  clasificar      cada secuencia que termina en PÉRDIDA: ¿la reanuda el mismo equipo con un balón parado? ¿cuál, y
                  en qué zona?
  valor           E[xG de la secuencia que arranca con la reanudación | tipo, zona], de TODAS las reanudaciones de la
                  liga, encogido hacia la media del tipo (a pseudo-reanudaciones).
  variante        las transiciones con el quinto absorbente: la última transición de la secuencia (la terminal
                  artificial o el pase que se registró como perdido) va a INTERRUPCIÓN_FAVOR; su recompensa es 0 o el
                  valor de la reanudación (entra a c = xG por acción desde el estado de origen, como un remate).
  por_zona        B = N R y V = N c por zona de la cadena de la liga y de cada familia.

Las tres variantes (ADR-v2-63): (i) con laterales, c = 0; (ii) con laterales, c = valor; (iii) sin laterales (solo
tiro libre, córner, penal y falta), c = valor. Ningún cambio parte PÉRDIDA en robo / mal pase / intercepción.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .absorbing import Cadena
from .estimate import shrink
from .grid import ABSORBING, StateSpace

INTERRUPCION = "INTERRUPCION_FAVOR"
TIPO_PASE = {"Throw-in": "lateral", "Corner": "corner", "Free Kick": "tiro_libre"}
TIPO_REMATE = {"Free Kick": "tiro_libre", "Penalty": "penal"}
VARIANTES = {"i": {"laterales": True, "valor": False, "nombre": "(i) con laterales, c = 0"},
             "ii": {"laterales": True, "valor": True, "nombre": "(ii) con laterales, c = valor del balón parado"},
             "iii": {"laterales": False, "valor": True, "nombre": "(iii) sin laterales, c = valor del balón parado"}}


def espacio5(space: StateSpace) -> StateSpace:
    """El mismo espacio con INTERRUPCIÓN_FAVOR al FINAL: los índices de los cuatro absorbentes no cambian."""
    return StateSpace(nx=space.nx, ny=space.ny, length=space.length, width=space.width, phases=space.phases,
                      absorbing=tuple(space.absorbing) + (INTERRUPCION,))


def _xy(loc: pl.Series) -> tuple[np.ndarray, np.ndarray]:
    x = loc.list.get(0, null_on_oob=True).cast(pl.Float64).fill_null(np.nan).to_numpy()
    y = loc.list.get(1, null_on_oob=True).cast(pl.Float64).fill_null(np.nan).to_numpy()
    return x, y


def reanudaciones(ev: pl.DataFrame, space: StateSpace) -> pl.DataFrame:
    """Todas las reanudaciones a balón parado de la liga: match_id, index, team, tipo, zona."""
    r = ev.filter(((pl.col("type") == "Pass") & pl.col("pass_type").is_in(list(TIPO_PASE)))
                  | ((pl.col("type") == "Shot") & pl.col("shot_type").is_in(list(TIPO_REMATE))))
    tipo = (pl.when(pl.col("type") == "Pass").then(pl.col("pass_type").replace_strict(TIPO_PASE, default=None))
            .otherwise(pl.col("shot_type").replace_strict(TIPO_REMATE, default=None)))
    r = r.with_columns(tipo.alias("tipo"))
    x, y = _xy(r["location"])
    ok = np.isfinite(x) & np.isfinite(y)
    z = np.where(ok, space.zone_of(np.nan_to_num(x), np.nan_to_num(y)), -1)
    return r.select("match_id", "index", "team", "tipo").with_columns(pl.Series("zona", z))


def clasificar(trans: pl.DataFrame, ev: pl.DataFrame, space: StateSpace) -> pl.DataFrame:
    """Una fila por secuencia que termina en PÉRDIDA: si la reanuda el mismo equipo a balón parado (a_favor), con qué
    (tipo) y desde qué zona. Regla de la compuerta (ADR-v2-60): la PRIMERA acción de cualquier equipo después de la
    última acción real es del mismo equipo y es un balón parado, o antes hay un `Foul Won` del mismo equipo."""
    LOSS = space.absorbing_index("LOSS")
    uid = "seq_uid" if "seq_uid" in trans.columns else "poss_uid"
    fin = (trans.sort(uid, "event_index").group_by(uid, maintain_order=True)
           .agg(pl.col("match_id").first(), pl.col("team").first(), pl.col("to_state").last().alias("fin"),
                pl.col("action_type").last().alias("ultimo_tipo"),
                pl.col("event_index").filter(pl.col("action_type") != "TERMINAL").max().alias("ult"))
           .filter(pl.col("fin") == LOSS).rename({uid: "uid"}))
    mov = (ev.filter(pl.col("type").is_in(["Pass", "Carry", "Shot"]))
           .select("match_id", pl.col("index").alias("sig_idx"), pl.col("team").alias("sig_team"),
                   pl.col("type").alias("sig_tipo"), "pass_type", "shot_type", pl.col("location").alias("sig_loc"))
           .sort("match_id", "sig_idx"))
    faltas = (ev.filter(pl.col("type") == "Foul Won")
              .select("match_id", "team", pl.col("index").alias("falta_idx"), pl.col("location").alias("falta_loc"))
              .sort("match_id", "team", "falta_idx"))
    p = (fin.with_columns((pl.col("ult") + 1).alias("desde")).sort("match_id", "desde")
         .join_asof(mov.with_columns(pl.col("sig_idx").alias("_m")), left_on="desde", right_on="_m", by="match_id",
                    strategy="forward", check_sortedness=False)
         .sort("match_id", "team", "desde")
         .join_asof(faltas.with_columns(pl.col("falta_idx").alias("_f")), left_on="desde", right_on="_f",
                    by=["match_id", "team"], strategy="forward", check_sortedness=False))
    mismo = (pl.col("sig_team") == pl.col("team")).fill_null(False)
    tp = (pl.when(pl.col("sig_tipo") == "Pass").then(pl.col("pass_type").replace_strict(TIPO_PASE, default=None))
          .when(pl.col("sig_tipo") == "Shot").then(pl.col("shot_type").replace_strict(TIPO_REMATE, default=None)))
    falta = pl.col("falta_idx").is_not_null() & (pl.col("sig_idx").is_null() | (pl.col("falta_idx") < pl.col("sig_idx")))
    p = p.with_columns(pl.when(mismo).then(tp).alias("_tp"), falta.alias("_falta")).with_columns(
        pl.when(pl.col("_tp").is_not_null()).then(pl.col("_tp"))
        .when(pl.col("_falta")).then(pl.lit("falta")).otherwise(pl.lit(None)).alias("tipo"))
    p = p.with_columns(pl.col("tipo").is_not_null().alias("a_favor"))
    # zona de la reanudación: donde se cobra; si solo hay falta, donde se recibió
    sx, sy = _xy(p["sig_loc"])
    fx, fy = _xy(p["falta_loc"])
    usa_f = (p["tipo"] == "falta").fill_null(False).to_numpy()
    x, y = np.where(usa_f, fx, sx), np.where(usa_f, fy, sy)
    ok = np.isfinite(x) & np.isfinite(y) & p["a_favor"].to_numpy()
    z = np.where(ok, space.zone_of(np.nan_to_num(x), np.nan_to_num(y)), -1)
    return p.select("uid", "match_id", "team", "ultimo_tipo", "a_favor", "tipo", "sig_idx").with_columns(
        pl.Series("zona", z))


def valor(trans: pl.DataFrame, rean: pl.DataFrame, a: float = 50.0) -> pl.DataFrame:
    """E[xG de la secuencia que empieza con la reanudación | tipo, zona], encogido hacia la media del tipo con `a`
    pseudo-reanudaciones. La «falta» sin balón parado inmediato toma el valor del tiro libre de su zona."""
    uid = "seq_uid" if "seq_uid" in trans.columns else "poss_uid"
    xs = trans.group_by(uid).agg(pl.col("xg").fill_null(0.0).sum().alias("xg_sec"),
                                 pl.col("match_id").first(), pl.col("event_index").min().alias("index"))
    r = rean.join(xs.select("match_id", "index", "xg_sec"), on=["match_id", "index"], how="inner")
    tipo = r.group_by("tipo").agg(pl.col("xg_sec").mean().alias("m_tipo"))
    v = (r.filter(pl.col("zona") >= 0).group_by("tipo", "zona").agg(pl.len().alias("n"), pl.col("xg_sec").sum().alias("s"))
         .join(tipo, on="tipo").with_columns(((pl.col("s") + a * pl.col("m_tipo")) / (pl.col("n") + a)).alias("valor")))
    falta = v.filter(pl.col("tipo") == "tiro_libre").with_columns(pl.lit("falta").alias("tipo"))
    return pl.concat([v, falta]).select("tipo", "zona", "n", "valor", "m_tipo")


def variante(trans: pl.DataFrame, clas: pl.DataFrame, val: pl.DataFrame | None, laterales: bool,
             space5: StateSpace) -> pl.DataFrame:
    """Transiciones con el quinto absorbente. Solo cambia la ÚLTIMA transición (la que iba a PÉRDIDA) de las
    secuencias a favor (sin laterales si `laterales` es False); con `val`, esa transición lleva como xG el valor de la
    reanudación (entra a c como un remate); sin `val`, xG nulo (c = 0)."""
    uid = "seq_uid" if "seq_uid" in trans.columns else "poss_uid"
    LOSS, INT = space5.absorbing_index("LOSS"), space5.absorbing_index(INTERRUPCION)
    sel = clas.filter(pl.col("a_favor"))
    if not laterales:
        sel = sel.filter(pl.col("tipo") != "lateral")
    sel = sel.select(pl.col("uid").alias(uid), "tipo", "zona")
    if val is not None:
        sel = sel.join(val.select("tipo", "zona", "valor"), on=["tipo", "zona"], how="left").join(
            val.group_by("tipo").agg(pl.col("m_tipo").first()), on="tipo", how="left").with_columns(
            pl.coalesce("valor", "m_tipo").fill_null(0.0).alias("valor"))
    else:
        sel = sel.with_columns(pl.lit(None, pl.Float64).alias("valor"))
    t = trans.sort(uid, "event_index").with_columns(
        (pl.col("event_index") == pl.col("event_index").max().over(uid)).alias("_ult"))
    t = t.join(sel.select(uid, pl.col("valor").alias("_v"), pl.lit(True).alias("_sel")), on=uid, how="left")
    cambia = pl.col("_sel").fill_null(False) & pl.col("_ult") & (pl.col("to_state") == LOSS)
    return t.with_columns(pl.when(cambia).then(INT).otherwise(pl.col("to_state")).alias("to_state"),
                          pl.when(cambia).then(pl.col("_v")).otherwise(pl.col("xg")).alias("xg")
                          ).drop("_ult", "_v", "_sel")


def por_zona(P: np.ndarray, c: np.ndarray, nt: int, n_zonas: int) -> dict:
    """B (nt × n_abs) y V (nt) de una cadena, promediados a zona (las fases, si hay más de una, en partes iguales)."""
    cad = Cadena(P, nt)
    B, V = cad.absorcion(), cad.valor(c)
    f = nt // n_zonas
    return {"B": B.reshape(n_zonas, f, -1).mean(1), "V": V.reshape(n_zonas, f).mean(1)}


def cadena_liga(S, X, nt: int, ns: int) -> tuple[np.ndarray, np.ndarray]:
    """La cadena de toda la liga (una sola, encogida levemente a la uniforme) y su c = xG por acción desde cada estado."""
    C = np.asarray(S.sum(axis=0)).ravel().reshape(nt, ns)
    P = shrink(C, np.full((nt, ns), 1.0 / ns), 1.0)
    n = C.sum(1)
    x = np.asarray(X.sum(axis=0)).ravel()
    return P, np.where(n > 0, x / np.maximum(n, 1e-300), 0.0)


def cadena_familia(m, d, r: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """P^k de la mezcla y c^k = Σ_s r_sk xG_s(i) / Σ_s r_sk n_s(i)."""
    nt, ns = d.n_transient, d.n_states
    n = np.asarray(d.S.T @ r[:, k]).ravel().reshape(nt, ns).sum(1)
    x = np.asarray(d.X.T @ r[:, k]).ravel()
    return m.P[k], np.where(n > 0, x / np.maximum(n, 1e-300), 0.0)


__all__ = ["ABSORBING", "INTERRUPCION", "VARIANTES", "espacio5", "reanudaciones", "clasificar", "valor", "variante",
           "por_zona", "cadena_liga", "cadena_familia"]
