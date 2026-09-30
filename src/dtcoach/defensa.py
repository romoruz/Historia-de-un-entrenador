"""
Fase defensiva (reto 5.1, G3): presión, organización y transiciones, contadas para
alguien que no ve fútbol.

LO QUE AGREGA A LAS MÉTRICAS DE `futbol` (03_FRAMEWORK §5 y §9)
  presion_tercio_alto, presion_tercio_medio, presion_tercio_bajo
        fracción de las acciones del RIVAL con un jugador propio a ≤ `presion_m` m (360),
        según dónde toca el rival: en su propio tercio (x < 40, presión alta), en el medio
        o en el tercio del que defiende (x ≥ 80, defensa del área)
  anchura_bloque_vis
        anchura del bloque solo en frames cuya área visible cubre ≥ `ancho_min` m del
        ancho de la cancha: el control del encuadre de la cámara
  profundidad_bloque, ancho_visible
        profundidad del bloque y, como diagnóstico, el ancho que ve la cámara

CURVA DE PRESIÓN
  Para r = 0.5, 1, …, 8 m: P(el rival toca el balón con un jugador propio a ≤ r m),
  foco contra liga, con banda por bootstrap de partidos. Es la figura "de cada 100
  toques del rival, en cuántos hay alguien encima": se lee sin saber qué es un PPDA.

BLOQUE TÍPICO
  Medianas de altura (distancia media de sus defensores a su arco), anchura y
  profundidad del bloque, foco contra liga, para dibujarlo como un rectángulo en la
  cancha. Todo y solo con frames de cámara amplia (el mismo control).
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .futbol import _por_partido

DEFINICIONES = {
    "presion_tercio_alto": {"nombre": "presión encima cuando el rival sale desde atrás (360)", "formato": "{:.3f}"},
    "presion_tercio_medio": {"nombre": "presión encima en el medio campo (360)", "formato": "{:.3f}"},
    "presion_tercio_bajo": {"nombre": "presión encima cerca de su propia área (360)", "formato": "{:.3f}"},
    "anchura_bloque_vis": {"nombre": "anchura del bloque con la cámara abierta (m, 360)", "formato": "{:.1f}"},
    "profundidad_bloque": {"nombre": "profundidad del bloque (m, 360)", "formato": "{:.1f}"},
    "ancho_visible": {"nombre": "ancho de cancha que ve la cámara (m, diagnóstico)", "formato": "{:.1f}"},
}
NUEVAS = list(DEFINICIONES)
RADIOS = np.arange(0.5, 8.01, 0.5)


def _acciones(ev: pl.DataFrame) -> pl.DataFrame:
    return ev.filter(pl.col("type").is_in(["Pass", "Carry", "Shot"])).select(
        "match_id", pl.col("index").alias("event_index"), "team", "x", "y")


def metricas(ev: pl.DataFrame, rasgos: pl.DataFrame | None, bloque: pl.DataFrame | None, tp: pl.DataFrame,
             cfg: dict) -> list[pl.DataFrame]:
    out = []
    acc = _acciones(ev)
    rival = tp.select("match_id", "team", "rival")
    d2 = cfg["presion_m"]
    if rasgos is not None and rasgos.height:
        r = (acc.join(rasgos.select("match_id", "event_index", "d_rival"), on=["match_id", "event_index"])
             .filter(pl.col("d_rival").is_not_nan())
             # quien presiona es el rival del que toca el balón
             .join(rival, on=["match_id", "team"]).drop("team").rename({"rival": "team"}))
        cerca = pl.col("d_rival") <= d2
        for nombre, filtro in (("alto", pl.col("x") < 40), ("medio", (pl.col("x") >= 40) & (pl.col("x") < 80)),
                               ("bajo", pl.col("x") >= 80)):
            s = r.filter(filtro)
            out.append(_por_partido(s, f"presion_tercio_{nombre}", cerca.sum(), pl.len()))
    if bloque is not None and bloque.height and "ancho_visible" in bloque.columns:
        b = (acc.join(bloque, on=["match_id", "event_index"], how="inner")
             .join(rival, on=["match_id", "team"]).drop("team").rename({"rival": "team"}))
        vis = b.filter(pl.col("ancho_visible") >= cfg.get("ancho_min", 70.0))
        out += [_por_partido(vis, "anchura_bloque_vis", pl.col("anchura").sum(), pl.len()),
                _por_partido(b, "profundidad_bloque", pl.col("profundidad").sum(), pl.len()),
                _por_partido(b.filter(pl.col("ancho_visible").is_not_nan()), "ancho_visible",
                             pl.col("ancho_visible").sum(), pl.len())]
    return out


def _grupos(df: pl.DataFrame, tp: pl.DataFrame, foco: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Acciones del rival del foco (lo que el foco defiende) y las de la liga sin el foco."""
    x = df.join(tp.select("match_id", "team", "coach", "coach_rival"), on=["match_id", "team"], how="left")
    pf = x.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique().to_list()
    return x.filter(pl.col("coach_rival") == foco), x.filter(~pl.col("match_id").is_in(pf))


def curva_presion(ev: pl.DataFrame, rasgos: pl.DataFrame, tp: pl.DataFrame, foco: str, n_boot: int = 300,
                  seed: int = 0, radios: np.ndarray = RADIOS) -> dict:
    acc = (_acciones(ev).join(rasgos.select("match_id", "event_index", "d_rival"), on=["match_id", "event_index"])
           .filter(pl.col("d_rival").is_not_nan()))
    f, lg = _grupos(acc, tp, foco)
    rng = np.random.default_rng(seed)

    def cuentas(d: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Por partido: (n acciones, n con alguien a ≤ r para cada r)."""
        u, g = np.unique(d["match_id"].to_numpy(), return_inverse=True)
        dr = d["d_rival"].to_numpy()
        n = np.bincount(g, minlength=len(u)).astype(float)
        k = np.column_stack([np.bincount(g, weights=(dr <= r).astype(float), minlength=len(u)) for r in radios])
        return n, k

    out = {"radios": radios.tolist()}
    for nombre, d in (("foco", f), ("liga", lg)):
        if d.height == 0:
            continue
        n, k = cuentas(d)
        out[nombre] = (k.sum(0) / n.sum()).tolist()
        b = []
        for _ in range(n_boot):
            i = rng.integers(0, len(n), len(n))
            b.append(k[i].sum(0) / n[i].sum())
        out[f"{nombre}_lo"] = np.quantile(b, 0.025, axis=0).tolist()
        out[f"{nombre}_hi"] = np.quantile(b, 0.975, axis=0).tolist()
        out[f"n_{nombre}"] = int(n.sum())
    return out


def bloque_tipico(ev: pl.DataFrame, bloque: pl.DataFrame, tp: pl.DataFrame, foco: str,
                  ancho_min: float = 70.0) -> dict:
    """Medianas del bloque (foco defendiendo contra liga) con la cámara abierta, y el diagnóstico."""
    b = _acciones(ev).join(bloque, on=["match_id", "event_index"], how="inner")
    f, lg = _grupos(b, tp, foco)
    out = {}
    for nombre, d in (("foco", f), ("liga", lg)):
        if d.height == 0:
            continue
        dv = d.filter(pl.col("ancho_visible") >= ancho_min) if "ancho_visible" in d.columns else d
        out[nombre] = {"frames": d.height, "frames_camara_abierta": dv.height,
                       **{c: float(dv[c].median()) for c in ("altura", "anchura", "profundidad", "area")
                          if dv.height},
                       "anchura_todos": float(d["anchura"].median()),
                       "ancho_visible_medio": float(d["ancho_visible"].mean()) if "ancho_visible" in d.columns
                       else float("nan"),
                       "defensores_visibles": float(d["n_def"].mean())}
    return out
