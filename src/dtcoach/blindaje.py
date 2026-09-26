"""
Fase A -- Blindaje: las objeciones que un jurado técnico haría primero.

1. EFICIENCIA SIN DEPENDER DEL xG DEL PROVEEDOR (H7, H8)
   El xG de StatsBomb tiene sesgos propios (Davis y Robberechts, 2024). Se repite la
   eficiencia por familia con el OBV de StatsBomb (valor de TODAS las acciones de la
   secuencia, no solo del remate) y con la tasa de remate (sin ningún modelo). Si las
   tres medidas coinciden en signo, la conclusión no es un artefacto del xG.
2. POCOS PARTIDOS (H3–H6): p por bootstrap de score por conglomerado (`pesos.score_bootstrap`).
3. MULTIPLICIDAD GLOBAL: Benjamini-Hochberg sobre TODAS las hipótesis del foco (fases
   2, 3a por club y 3b) en una sola familia, como sensibilidad de los BH por familia.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from .inference import benjamini_hochberg
from .perfil import perfiles


def obv_por_secuencia(t_seq: pl.DataFrame, trans: pl.DataFrame, ev: pl.DataFrame) -> pl.DataFrame:
    obv = ev.select("match_id", pl.col("index").alias("event_index"), "obv_total_net")
    s = (trans.filter(pl.col("action_type") != "TERMINAL").select("seq_uid", "match_id", "event_index")
         .join(obv, on=["match_id", "event_index"], how="left")
         .group_by("seq_uid").agg(pl.col("obv_total_net").fill_null(0.0).sum().alias("obv")))
    return t_seq.join(s, on="seq_uid", how="left").with_columns(pl.col("obv").fill_null(0.0))


def eficiencia_robusta(t_seq: pl.DataFrame, K: int, familias: list[str], n_boot: int, seed: int) -> dict:
    """Por familia y lado: diferencia foco − liga en xG, OBV y tasa de remate por secuencia."""
    out = {}
    base = perfiles(t_seq, K, n_boot, seed)
    obv = perfiles(t_seq.with_columns(pl.col("obv").alias("xg")), K, n_boot, seed)
    for lado in ("ataque", "defensa"):
        out[lado] = {}
        for k, fam in enumerate(familias):
            fila = {}
            for medida, pf, i in (("xg", base, K + k), ("obv", obv, K + k), ("remate", base, 2 * K + k)):
                fila[medida] = {c: pf[lado][c][i] for c in ("foco", "liga", "dif", "lo", "hi", "p")}
            signos = {np.sign(fila[m]["dif"]) for m in fila if fila[m]["lo"] > 0 or fila[m]["hi"] < 0}
            fila["coinciden"] = len(signos) <= 1
            out[lado][fam] = fila
    return out


def _recolectar(obj, prefijo: str, out: list) -> None:
    """Toda hipótesis con p en un JSON de resultados (fase 2, 3a por club, 3b). Las de una
    muestra con < 20 partidos del foco se marcan `pocos`: nunca reciben 🟢 (ADR-v2-28)."""
    if isinstance(obj, dict):
        if "hipotesis" in obj and isinstance(obj["hipotesis"], dict):
            mod = obj.get("modelo") or {}
            pocos = bool("aviso_foco" in mod or (mod.get("partidos_foco") or 99) < 20)
            for k, h in obj["hipotesis"].items():
                if isinstance(h, dict) and "p" in h and h.get("etiqueta") != "🔎":
                    out.append({"id": f"{prefijo}{k}", "nombre": h.get("nombre", ""), "p": float(h["p"]),
                                "etiqueta_familia": h.get("etiqueta", ""), "pocos": pocos})
        for k, v in obj.items():
            if k != "hipotesis" and isinstance(v, dict):
                _recolectar(v, f"{prefijo}{k}/" if k not in ("clubes",) else prefijo, out)


def bh_global(archivos: list[Path], alpha: float = 0.05) -> pl.DataFrame:
    filas: list = []
    for a in archivos:
        if a.exists():
            _recolectar(json.loads(a.read_text()), f"{a.stem.split('_')[0]}:", filas)
    if not filas:
        return pl.DataFrame()
    d = pl.DataFrame(filas).filter(pl.col("p").is_not_nan())
    q, rech = benjamini_hochberg(d["p"].to_numpy(), alpha)
    return d.with_columns(pl.Series("q_global", q), pl.Series("rechaza_global", rech)).with_columns(
        pl.when(pl.col("rechaza_global") & ~pl.col("pocos")).then(pl.lit("🟢"))
        .when(pl.col("p") < alpha).then(pl.lit("🟡")).otherwise(pl.lit("⚪")).alias("etiqueta_global"))
