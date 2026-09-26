"""
Fase 1 (experimento, ADR-v2-37) -- Aumento de estado direccional: zona × dirección de llegada.

LA PREGUNTA
-----------
La fase 1 v3 midió memoria real en el DESTINO del balón: saber de qué zona venía
mejora la predicción de la siguiente en +0.058 nats por acción, y los tipos solo
explican el 4.5 % (10_RESULTADOS §16). Si el estado es (zona actual, dirección de
la acción que trajo el balón), esa memoria entra en una cadena de PRIMER orden:
N = (I − Q)⁻¹, V = N c, la llegada y la vida media siguen en forma cerrada.

EL ESTADO
---------
Nivel = dirección de la acción ANTERIOR de la secuencia (o "inicio" si es la
primera). El destino transitorio de la acción t es (zona final, dirección de t):
se conoce con la propia acción, sin mirar hacia adelante. El nivel ocupa el eje de
"fase" de `StateSpace`, como en ADR-v2-36. Los estados "inicio" solo son de
arranque (nadie transita hacia ellos): el paso inicial P⁰ vive ahí.

CUÁNTAS DIRECCIONES
-------------------
Se eligen por validación cruzada por partido en la escala común (ADR-v2-32):
densidad predictiva de la siguiente zona o absorbente en partidos no vistos, con
1 EE pareado hacia menos estados. El candidato "previa" (nivel = zona anterior
completa, 20 × 21 estados) es la REFERENCIA de la memoria medida en la v3
(+0.058 nats). No es un techo: la dirección se calcula con coordenadas exactas y
puede informar más que la zona anterior (que es gruesa). No compite como
vocabulario.

LO QUE NO SE ADOPTÓ DE LA PROPUESTA
-----------------------------------
- La analogía de fluidos no aporta cálculo: el modelo es una cadena de Markov y
  su "equilibrio" es la absorción; nada de Picard ni Poincaré-Bendixson.
- K y d no se optimizan juntos por verosimilitud: d se elige por predicción (aquí)
  y K por reproducibilidad (ADR-v2-35), como hasta ahora.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .possessions import extract_actions

_OCT = ["adelante", "adel_y+", "y+", "atr_y+", "atras", "atr_y-", "y-", "adel_y-"]


def etiquetas_direccion(metodo: str, n_zonas: int = 20) -> list[str]:
    """Niveles del estado; el primero siempre es "inicio"."""
    if metodo.endswith("+previa"):              # dirección × zona anterior: mide la memoria RESIDUAL
        d = etiquetas_direccion(metodo[: -len("+previa")], n_zonas)[1:]
        return ["inicio", *[f"{a}|de_z{z}" for a in d for z in range(n_zonas)]]
    tipo = metodo.partition(":")[0]
    if tipo == "base":
        return ["all"]
    if tipo == "x3":
        return ["inicio", "adelante", "lateral", "atras"]
    if tipo == "cuad4":
        return ["inicio", "adelante", "y+", "atras", "y-"]
    if tipo == "oct8":
        return ["inicio", *_OCT]
    if tipo == "previa":
        return ["inicio", *[f"de_z{z}" for z in range(n_zonas)]]
    raise ValueError(f"método de dirección desconocido: {metodo}")


def nivel_direccion(metodo: str, dx: np.ndarray, dy: np.ndarray, z_origen: np.ndarray,
                    n_zonas: int = 20) -> np.ndarray:
    """Nivel 1..d de la dirección de una acción (0 queda para "inicio")."""
    if metodo.endswith("+previa"):
        base = nivel_direccion(metodo[: -len("+previa")], dx, dy, z_origen, n_zonas)
        return 1 + (base - 1) * n_zonas + np.asarray(z_origen, dtype=int)
    tipo, _, arg = metodo.partition(":")
    if tipo == "x3":
        eps = float(arg or 5.0)
        return np.where(dx > eps, 1, np.where(dx < -eps, 3, 2))
    ang = np.arctan2(dy, dx)                                  # 0 = hacia el arco rival
    if tipo == "cuad4":
        return 1 + (np.round(ang / (np.pi / 2)).astype(int) % 4)
    if tipo == "oct8":
        return 1 + (np.round(ang / (np.pi / 4)).astype(int) % 8)
    if tipo == "previa":
        return 1 + np.asarray(z_origen, dtype=int)
    raise ValueError(f"método de dirección desconocido: {metodo}")


def coordenadas(lf: pl.LazyFrame, cfg: dict) -> pl.DataFrame:
    """(match_id, event_index) -> inicio y fin de cada acción, con la MISMA
    extracción que usa `build_transitions` (no una segunda definición de "fin")."""
    return (extract_actions(lf, cfg)
            .select("match_id", pl.col("index").alias("event_index"), "start_x", "start_y", "end_x", "end_y")
            .collect().unique(["match_id", "event_index"], keep="first"))


def aumentar_direccion(trans: pl.DataFrame, coords: pl.DataFrame, metodo: str, space) -> tuple[pl.DataFrame, dict]:
    """Recodifica transiciones de UNA fase (from_state = zona) a zona × dirección de llegada.

    origen(t)  = (zona, dirección de la acción t−1 de la secuencia) o (zona, inicio)
    destino(t) = (zona final, dirección de t) si es transitorio; absorbentes igual.
    Así destino(t) y origen(t+1) comparten nivel por construcción.
    """
    nz = space.n_zones
    if int(trans["from_state"].max()) >= nz:
        raise ValueError("`aumentar_direccion` espera transiciones de UNA fase (from_state = zona)")
    et = etiquetas_direccion(metodo, nz)
    L = len(et)
    t = trans.with_row_index("_fila").join(coords, on=["match_id", "event_index"], how="left")
    t = t.sort(["seq_uid", "event_index"])
    zf = t["from_state"].to_numpy().astype(int)
    to = t["to_state"].to_numpy().astype(int)
    # sin coordenadas (o fila TERMINAL): centroides de las zonas; solo importa si el destino es transitorio
    cen = space.zone_centroids()
    sx, sy = t["start_x"].fill_null(np.nan).to_numpy(), t["start_y"].fill_null(np.nan).to_numpy()
    ex, ey = t["end_x"].fill_null(np.nan).to_numpy(), t["end_y"].fill_null(np.nan).to_numpy()
    transit = to < nz
    falta = transit & ~(np.isfinite(sx) & np.isfinite(sy) & np.isfinite(ex) & np.isfinite(ey))
    zt = np.where(transit, to, 0)
    sx = np.where(falta, cen[zf, 0], sx)
    sy = np.where(falta, cen[zf, 1], sy)
    ex = np.where(falta, cen[zt, 0], ex)
    ey = np.where(falta, cen[zt, 1], ey)
    dx, dy = np.nan_to_num(ex - sx), np.nan_to_num(ey - sy)     # las filas no transitorias no se usan
    dirs = np.where(transit, nivel_direccion(metodo, dx, dy, zf, nz), 0)
    uid = t["seq_uid"].to_numpy()
    primero = np.r_[True, uid[1:] != uid[:-1]]
    lvl_from = np.where(primero, 0, np.r_[0, dirs[:-1]])
    # una fila no primera cuya anterior absorbió no existe (la secuencia termina en la absorción)
    new_from = zf * L + lvl_from
    new_to = np.where(transit, to * L + dirs, to - nz + nz * L)
    out = t.with_columns(pl.Series("from_state", new_from), pl.Series("to_state", new_to),
                         pl.Series("phase", np.array(et, dtype=object)[lvl_from].astype(str))
                         ).drop("start_x", "start_y", "end_x", "end_y").sort("_fila").drop("_fila")
    real = (t["action_type"] != "TERMINAL").to_numpy() if "action_type" in t.columns else np.ones(len(t), bool)
    diag = {"metodo": metodo, "L": L, "estados_transitorios": nz * L, "transiciones": out.height,
            "frac_destino_sin_coordenadas": float(falta[real & transit].mean()) if (real & transit).any() else 0.0,
            "frac_por_nivel_origen": {e: float((lvl_from == k).mean()) for k, e in enumerate(et)
                                      if L <= 9}}
    return out, diag
