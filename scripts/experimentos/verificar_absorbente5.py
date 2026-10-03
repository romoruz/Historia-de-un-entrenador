#!/usr/bin/env python3
"""
Verificación del paso 4 de la integración (ADR-v2-72): el quinto absorbente INTERRUPCIÓN_FAVOR, variante (ii).

Correr DESPUÉS de `dtcoach fase0` y `dtcoach mezcla --K 3` con el código nuevo, y ANTES de regenerar la historia:

  1. xG por secuencia IDÉNTICO (lo que leen H7 y H8): las transiciones de antes (cuatro absorbentes, archivadas) contra
     las de ahora, por `seq_uid`. Mismas secuencias, mismo xG bit a bit, mismo origen de cada transición, y el único
     cambio de destino es PÉRDIDA → INTERRUPCIÓN_FAVOR en la última transición. Si no, sale con 1: PARA.
  2. El quinto absorbente contra CUATRO absorbentes sobre los MISMOS datos de hoy (nunca contra el archivo
     publicado): se reajusta K = 3 con `absorbente5.a_cuatro` (INTERRUPCIÓN vuelve a PÉRDIDA) y se compara con la
     mezcla oficial nueva: acuerdo suave de las responsabilidades y las tarjetas por familia. Así la diferencia es del
     absorbente, no de los 22 partidos nuevos (ADR-v2-68). Si el acuerdo es < 0.95, sale con 1: PARA.
  3. Como referencia (no decide): el reajuste de cuatro absorbentes contra el archivo publicado (debe repetir el
     0.9968 de ADR-v2-68) y el quinto absorbente contra el publicado (el experimento dio 0.981–0.983).

Uso (raíz del repo):
  python scripts/experimentos/verificar_absorbente5.py --antes data/processed/archivo_4abs/transitions.parquet \\
      --publicada data/processed/archivo_4abs/mezcla/mezcla_K3.npz
Salida: reports/experimentos/absorbente5_integrado/VERIFICAR.md (+ .json).
"""
import argparse
import json
import sys
import time

import numpy as np
import polars as pl

from dtcoach import absorbente5 as ab
from dtcoach import mezcla as mz
from dtcoach.cli import _space, _trans
from dtcoach.config import Config

K = 3


def xg_identico(antes: pl.DataFrame, ahora: pl.DataFrame, space) -> dict:
    uid = "seq_uid"
    xa = antes.group_by(uid).agg(pl.col("xg").fill_null(0.0).sum().alias("xg_a"), pl.len().alias("n_a"))
    xb = ahora.group_by(uid).agg(pl.col("xg").fill_null(0.0).sum().alias("xg_b"), pl.len().alias("n_b"))
    j = xa.join(xb, on=uid, how="full", coalesce=True)
    faltan = j.filter(pl.col("xg_a").is_null() | pl.col("xg_b").is_null()).height
    jj = j.drop_nulls()
    xg_ok = faltan == 0 and bool((jj["xg_a"] == jj["xg_b"]).all()) and bool((jj["n_a"] == jj["n_b"]).all())
    # transición por transición
    k = ["seq_uid", "event_index"]
    t = antes.select(*k, "from_state", pl.col("to_state").alias("to_a"), pl.col("xg").alias("xg_ta")).join(
        ahora.select(*k, pl.col("from_state").alias("from_b"), pl.col("to_state").alias("to_b"),
                     pl.col("xg").alias("xg_tb")), on=k, how="inner")
    LOSS, INT = space.absorbing_index("LOSS"), space.absorbing_index(ab.INTERRUPCION)
    cambia = t.filter(pl.col("to_a") != pl.col("to_b"))
    solo_perdida = bool(((cambia["to_a"] == LOSS) & (cambia["to_b"] == INT)).all())
    ult = ahora.group_by(uid).agg(pl.col("event_index").max().alias("_u"))
    en_ultima = cambia.join(ult, on=uid).filter(pl.col("event_index") == pl.col("_u")).height == cambia.height
    return {"secuencias_antes": xa.height, "secuencias_ahora": xb.height, "secuencias_no_emparejadas": faltan,
            "transiciones_emparejadas": t.height, "transiciones_antes": antes.height, "transiciones_ahora": ahora.height,
            "xg_por_secuencia_identico": xg_ok,
            "max_dif_xg_secuencia": float((jj["xg_a"] - jj["xg_b"]).abs().max() or 0.0),
            "origen_identico": bool((t["from_state"] == t["from_b"]).all()),
            "xg_transicion_identico": bool(t.select((pl.col("xg_ta").fill_null(-1.0) == pl.col("xg_tb").fill_null(-1.0))
                                                    .all()).item()),
            "destinos_cambiados": cambia.height, "solo_perdida_a_interrupcion": solo_perdida,
            "solo_en_la_ultima_transicion": en_ultima}


def _ajuste(d, mc, seed):
    return mz.ajustar(d, K, mc["lam"], mc["a0"], mc["n_init"], mc["max_iter"], mc["tol"], seed, init="escalera",
                      n_corto=mc.get("n_corto", 25), paso_inicial=mc.get("paso_inicial", True), lam0=mc.get("lam0"))


def _tarjetas(m, d) -> list[dict]:
    out = []
    for k in range(m.K):
        q = m.inicio(k)
        B = q["B"]
        out.append({"pi": float(m.pi[k]), "E_T": float(q["E_T"]), "P_remate": float(B[:2].sum()),
                    "P_perdida": float(B[2]), "P_fuera": float(B[3]),
                    "P_interrupcion": float(B[4]) if len(B) > 4 else 0.0})
    return out


def comparar(ma, da, mb, db) -> dict:
    """Responsabilidades de cada mezcla sobre SUS datos (las mismas secuencias, en el mismo orden)."""
    if da.meta["seq_uid"].to_list() != db.meta["seq_uid"].to_list():
        raise ValueError("las dos mezclas no se evalúan sobre las mismas secuencias")
    Ra, Rb = mz.responsabilidades(ma, da), mz.responsabilidades(mb, db)
    return {"acuerdo_suave": mz.acuerdo_suave(Ra, Rb), "acuerdo_duro": float((Ra.argmax(1) == Rb.argmax(1)).mean()),
            "impureza_a": impureza(Ra), "impureza_b": impureza(Rb),
            "tarjetas_a": _tarjetas(ma, da), "tarjetas_b": _tarjetas(mb, db)}


def impureza(R) -> list[float]:
    """Por familia: Σ_s r_sk (1 − r_sk) / Σ_s r_sk (04 §7.2). La de Circulación estéril era 0.48 con cuatro absorbentes."""
    return [float((R[:, k] * (1 - R[:, k])).sum() / max(R[:, k].sum(), 1e-300)) for k in range(R.shape[1])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--antes", required=True, help="transitions.parquet de cuatro absorbentes (archivado antes de fase0)")
    ap.add_argument("--publicada", default=None, help="mezcla_K3.npz de la entrega (archivada), solo como referencia")
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    cfg = Config.load(a.config)
    mc = cfg["mezcla"]
    out = cfg.ruta("reportes") / "experimentos" / "absorbente5_integrado"
    out.mkdir(parents=True, exist_ok=True)
    s5 = _space(cfg)
    if ab.INTERRUPCION not in s5.absorbing:
        sys.exit("el espacio de estados no tiene INTERRUPCION_FAVOR: ¿código de antes del paso 4?")
    s4 = ab.espacio4(s5)
    ahora = _trans(cfg)
    if "valor_reanudacion" not in ahora.columns:
        sys.exit("las transiciones no traen `valor_reanudacion`: corre `dtcoach fase0` con el código del paso 4")
    antes = pl.read_parquet(a.antes)
    res = {"xg": xg_identico(antes, ahora, s5)}
    print(json.dumps(res["xg"], indent=1), flush=True)
    x = res["xg"]
    ok_xg = (x["xg_por_secuencia_identico"] and x["origen_identico"] and x["xg_transicion_identico"]
             and x["solo_perdida_a_interrupcion"] and x["solo_en_la_ultima_transicion"])

    d5 = mz.DatosPosesion.desde_transiciones(ahora, s5)
    d4 = mz.DatosPosesion.desde_transiciones(ab.a_cuatro(ahora, s5), s4)
    m5 = mz.Mezcla.cargar(cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz")
    if m5.P.shape[2] != s5.n_states:
        sys.exit("la mezcla de mezcla_dir no es de cinco absorbentes: corre `dtcoach mezcla --K 3` antes")
    t0 = time.time()
    print(f"Ajustando K = {K} con CUATRO absorbentes sobre las mismas {d4.n:,} secuencias…", flush=True)
    m4 = _ajuste(d4, mc, cfg["seed"])
    res["tiempo_ajuste_4_s"] = time.time() - t0
    res["cinco_vs_cuatro_mismos_datos"] = comparar(m5, d5, m4, d4)
    cc = res["cinco_vs_cuatro_mismos_datos"]
    ok_acuerdo = cc["acuerdo_suave"] >= 0.95
    # 04 §7.2: B (200 réplicas, cuatro absorbentes) no se repite si las responsabilidades apenas se mueven
    d_imp = max(abs(x - y) for x, y in zip(cc["impureza_a"], cc["impureza_b"]))
    repetir_B = cc["acuerdo_suave"] < 0.98 or d_imp > 0.02
    res["repetir_B"] = {"repetir": repetir_B, "max_dif_impureza": d_imp}
    if a.publicada:
        mp = mz.Mezcla.cargar(a.publicada)
        res["cuatro_hoy_vs_publicada"] = comparar(m4, d4, mp, d4)
        res["cinco_vs_publicada"] = {"acuerdo_suave": mz.acuerdo_suave(mz.responsabilidades(m5, d5),
                                                                       mz.responsabilidades(mp, d4))}
    (out / "verificar.json").write_text(json.dumps(res, indent=1, default=float))

    fam = cfg["fase2"]["familias"]
    c = res["cinco_vs_cuatro_mismos_datos"]
    md = ["# Paso 4: el quinto absorbente, verificado con los datos reales (ADR-v2-72)", "",
          "## 1. xG por secuencia (H7–H8): ¿idéntico?", "",
          f"- secuencias antes / ahora: {x['secuencias_antes']:,} / {x['secuencias_ahora']:,}; sin pareja: "
          f"{x['secuencias_no_emparejadas']:,}",
          f"- transiciones antes / ahora / emparejadas: {x['transiciones_antes']:,} / {x['transiciones_ahora']:,} / "
          f"{x['transiciones_emparejadas']:,}",
          f"- xG por secuencia idéntico bit a bit: **{'sí' if x['xg_por_secuencia_identico'] else 'NO'}** "
          f"(máx. diferencia {x['max_dif_xg_secuencia']!r})",
          f"- origen de cada transición idéntico: {'sí' if x['origen_identico'] else 'NO'}; xG de cada transición "
          f"idéntico: {'sí' if x['xg_transicion_identico'] else 'NO'}",
          f"- destinos cambiados: {x['destinos_cambiados']:,}; todos PÉRDIDA → INTERRUPCIÓN: "
          f"{'sí' if x['solo_perdida_a_interrupcion'] else 'NO'}; todos en la última transición: "
          f"{'sí' if x['solo_en_la_ultima_transicion'] else 'NO'}", "",
          "## 2. Cinco absorbentes contra cuatro, sobre los MISMOS datos de hoy", "",
          f"Acuerdo suave **{c['acuerdo_suave']:.6f}** (duro {c['acuerdo_duro']:.4f}).", "",
          "| familia | π 5 / 4 | E[T] 5 / 4 | P(remate) 5 / 4 | PÉRDIDA 5 / 4 | INTERRUPCIÓN (5) | PÉRDIDA + INTERRUPCIÓN (5) |",
          "|---|---|---|---|---|---|---|"]
    for k in range(K):
        p, q = c["tarjetas_a"][k], c["tarjetas_b"][k]
        md.append(f"| {fam[k] if k < len(fam) else k + 1} | {p['pi']:.4f} / {q['pi']:.4f} | {p['E_T']:.3f} / "
                  f"{q['E_T']:.3f} | {p['P_remate']:.4f} / {q['P_remate']:.4f} | {p['P_perdida']:.4f} / "
                  f"{q['P_perdida']:.4f} | {p['P_interrupcion']:.4f} | {p['P_perdida'] + p['P_interrupcion']:.4f} |")
    md += ["", "Impureza por familia (5 / 4): " + ", ".join(
        f"{fam[k] if k < len(fam) else k + 1} {c['impureza_a'][k]:.3f} / {c['impureza_b'][k]:.3f}" for k in range(K))
        + f". Máx. diferencia {d_imp:.4f}.", "",
        ("**AVISO: repetir B antes de narrar** (04 §7.2: acuerdo < 0.98 o impureza que cambia > 0.02)." if repetir_B
         else "B (§7.2) no necesita repetirse: acuerdo ≥ 0.98 e impureza estable (≤ 0.02).")]
    if a.publicada:
        md += ["", "## 3. Referencia (no decide)", "",
               f"- cuatro absorbentes hoy contra el archivo publicado: acuerdo suave "
               f"{res['cuatro_hoy_vs_publicada']['acuerdo_suave']:.6f} (ADR-v2-68: 0.996787)",
               f"- cinco absorbentes contra el archivo publicado: {res['cinco_vs_publicada']['acuerdo_suave']:.6f} "
               f"(experimento: 0.981–0.983; mezcla absorbente y datos nuevos a la vez)"]
    md += ["", ("**VEREDICTO: el xG por secuencia es idéntico y el quinto absorbente no cambia las familias "
                f"(acuerdo {c['acuerdo_suave']:.4f} ≥ 0.95). Se puede regenerar la historia.**")
           if ok_xg and ok_acuerdo else
           "**VEREDICTO: PARA.** " + ("El xG por secuencia NO es idéntico. " if not ok_xg else "")
           + ("El acuerdo con cuatro absorbentes es < 0.95." if not ok_acuerdo else "")]
    (out / "VERIFICAR.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    sys.exit(0 if ok_xg and ok_acuerdo else 1)


if __name__ == "__main__":
    main()
