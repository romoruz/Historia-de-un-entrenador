#!/usr/bin/env python3
"""
Diagnóstico (ADR-v2-68): ¿por qué el reajuste de hoy no reproduce la mezcla publicada, y se puede reproducir?

`verificar_mezcla.py` mostró nuevo = previo bit a bit, pero ambos ≠ la mezcla guardada en `mezcla_dir`. La hipótesis
(a) es que los datos crecieron después de publicar (ADR-v2-51: la temporada en curso se sumó SIN reajustar el
vocabulario). Este script la pone a prueba con evidencia, sin escribir en `mezcla_dir` ni en `reports/mezcla`:

  1. Muestras: secuencias, partidos y fechas de la muestra publicada (las `seq_uid` de
     `responsabilidades_K3.parquet`, que `dtcoach mezcla` escribió con la MISMA muestra con la que ajustó) contra
     las de hoy. Qué partidos son nuevos y si falta alguna secuencia publicada.
  2. ¿Cambiaron los datos de los partidos viejos? La mezcla publicada, aplicada hoy a las secuencias publicadas, debe
     dar las MISMAS responsabilidades que guardó (si los eventos de esos partidos no cambiaron al reaplanar).
  3. Reproducción: K = 3 con config/default.yaml SOLO sobre las secuencias publicadas. Debe salir idéntica bit a bit
     a la mezcla guardada (J, π, P, P0, μ, iteraciones).
  4. Tamaño práctico del cambio: la mezcla publicada contra el reajuste con TODOS los datos de hoy, en las cantidades
     que se narran (π, E[T], P(remate) por familia), en distancia de variación total por fila de P ponderada por uso,
     en J por secuencia y en acuerdo suave; junto al ruido entre semillas de la entrega como referencia.

Salida: reports/experimentos/reproducir_publicada/REPRODUCIR.md (+ .json). Sale con 1 si 3 no es bit a bit.
Uso (raíz del repo):  python scripts/experimentos/reproducir_publicada.py      (dos ajustes K = 3; minutos)
"""
import json
import sys
import time

import numpy as np
import polars as pl

from dtcoach import mezcla as mz
from dtcoach.cli import _space, _trans
from dtcoach.config import Config

K = 3


def _ajuste(d, mc, seed):
    t0 = time.time()
    m = mz.ajustar(d, K, mc["lam"], mc["a0"], mc["n_init"], mc["max_iter"], mc["tol"], seed, init="escalera",
                   n_corto=mc.get("n_corto", 25), paso_inicial=mc.get("paso_inicial", True), lam0=mc.get("lam0"))
    return m, time.time() - t0


def _muestra(meta: pl.DataFrame) -> dict:
    f = meta["match_date"].cast(pl.Utf8)
    return {"secuencias": meta.height, "partidos": meta["match_id"].n_unique(), "fecha_min": f.min(),
            "fecha_max": f.max(), "tecnicos": meta["coach"].n_unique() if "coach" in meta.columns else None}


def _tarjetas(m) -> np.ndarray:
    return mz._tarjetas(m)          # (K, 3): π, E[T], P(remate)


def _tv_P(a, b) -> list[float]:
    """Por familia: la mayor distancia de variación total entre una fila de P de `a` y la de `b` (en probabilidad: lo
    que una diferencia relativa en celdas casi vacías exagera)."""
    return [float((0.5 * np.abs(a.P[k] - b.P[k]).sum(1)).max()) for k in range(K)]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None, help="por omisión config/default.yaml (el vocabulario oficial)")
    cfg = Config.load(ap.parse_args().config)
    mc = cfg["mezcla"]
    dirm = cfg.ruta("mezcla_dir")
    out = cfg.ruta("reportes") / "experimentos" / "reproducir_publicada"
    out.mkdir(parents=True, exist_ok=True)
    m_pub = mz.Mezcla.cargar(dirm / f"mezcla_K{K}.npz")
    r_pub = pl.read_parquet(dirm / f"responsabilidades_K{K}.parquet")
    res: dict = {}

    # 1. muestras
    tr = _trans(cfg)
    sp_ = _space(cfg)
    d_hoy = mz.DatosPosesion.desde_transiciones(tr, sp_)
    uids_pub = set(r_pub["seq_uid"].to_list())
    en_pub = d_hoy.meta["seq_uid"].is_in(list(uids_pub)).to_numpy()
    nuevos = d_hoy.meta.filter(~pl.Series(en_pub)).select("match_id", "match_date", "team").unique()
    res["muestras"] = {"publicada": _muestra(r_pub), "hoy": _muestra(d_hoy.meta),
                       "secuencias_publicadas_que_faltan_hoy": len(uids_pub) - int(en_pub.sum()),
                       "secuencias_nuevas": int((~en_pub).sum()),
                       "partidos_nuevos": nuevos["match_id"].n_unique(),
                       "partidos_viejos_con_secuencias_nuevas": int(nuevos["match_id"].is_in(
                           r_pub["match_id"].unique().to_list()).sum()),
                       "fechas_partidos_nuevos": [str(nuevos["match_date"].cast(pl.Utf8).min()),
                                                  str(nuevos["match_date"].cast(pl.Utf8).max())] if nuevos.height else None}
    print(json.dumps(res["muestras"], indent=1, default=str), flush=True)

    # 2. ¿datos de los partidos viejos idénticos? (la mezcla publicada sobre las secuencias publicadas, hoy)
    tr_pub = tr.filter(pl.col("seq_uid").is_in(list(uids_pub)))
    d_pub = mz.DatosPosesion.desde_transiciones(tr_pub, sp_)
    R_hoy = mz.responsabilidades(m_pub, d_pub)
    guard = (r_pub.join(d_pub.meta.select("seq_uid").with_row_index("_i"), on="seq_uid", how="inner")
             .sort("_i").select([f"r_{k + 1}" for k in range(K)]).to_numpy())
    mismas = guard.shape == R_hoy.shape
    res["datos_viejos"] = {"filas_emparejadas": int(guard.shape[0]),
                           "max_dif_responsabilidad": float(np.abs(guard - R_hoy).max()) if mismas else None,
                           "identicas": bool(mismas and np.array_equal(guard, R_hoy))}
    print(res["datos_viejos"], flush=True)

    # 3. reproducción sobre la muestra publicada
    print(f"Ajustando K = {K} sobre las {d_pub.n:,} secuencias publicadas…", flush=True)
    m_rep, t_rep = _ajuste(d_pub, mc, cfg["seed"])
    rep = {"J": [m_rep.objetivo[-1], m_pub.objetivo[-1]], "iteraciones": [len(m_rep.objetivo), len(m_pub.objetivo)],
           "max_dif_abs": {"pi": float(np.abs(m_rep.pi - m_pub.pi).max()), "P": float(np.abs(m_rep.P - m_pub.P).max()),
                           "P0": float(np.abs(m_rep.P0 - m_pub.P0).max()) if m_pub.P0 is not None else None,
                           "mu": float(np.abs(m_rep.mu - m_pub.mu).max())},
           "identico_bit_a_bit": bool(np.array_equal(m_rep.P, m_pub.P) and np.array_equal(m_rep.pi, m_pub.pi)
                                      and np.array_equal(m_rep.mu, m_pub.mu) and m_rep.objetivo == m_pub.objetivo
                                      and (m_pub.P0 is None or np.array_equal(m_rep.P0, m_pub.P0))),
           "tiempo_s": t_rep}
    res["reproduccion"] = rep
    print(rep, flush=True)

    # 4. tamaño práctico: publicada contra el reajuste con todo lo de hoy
    print(f"Ajustando K = {K} sobre las {d_hoy.n:,} secuencias de hoy…", flush=True)
    m_hoy, _ = _ajuste(d_hoy, mc, cfg["seed"])
    Ra, Rb = mz.responsabilidades(m_hoy, d_hoy), mz.responsabilidades(m_pub, d_hoy)
    ta, tb = _tarjetas(m_hoy), _tarjetas(m_pub)
    pesos = Ra.sum(0)
    res["hoy_vs_publicada"] = {
        "acuerdo_suave": mz.acuerdo_suave(Ra, Rb),
        "acuerdo_duro": float((Ra.argmax(1) == Rb.argmax(1)).mean()),
        "J_por_secuencia": [m_hoy.objetivo[-1] / d_hoy.n, m_pub.objetivo[-1] / d_pub.n],
        "tarjetas_hoy": ta.tolist(), "tarjetas_publicada": tb.tolist(),
        "max_dif_pi_pp": float(100 * np.abs(ta[:, 0] - tb[:, 0]).max()),
        "max_dif_ET_rel": float((np.abs(ta[:, 1] - tb[:, 1]) / tb[:, 1]).max()),
        "max_dif_Premate_pp": float(100 * np.abs(ta[:, 2] - tb[:, 2]).max()),
        "tv_max_fila_P": _tv_P(m_hoy, m_pub), "uso_hoy": (pesos / pesos.sum()).tolist(),
        "max_dif_abs_P": float(np.abs(m_hoy.P - m_pub.P).max()),
    }
    rp = cfg.ruta("reportes") / "mezcla" / f"reproducibilidad_K{K}.json"
    if rp.exists():
        r0 = json.loads(rp.read_text())
        res["entre_semillas_entrega"] = {"acuerdo_suave_minimo": r0.get("acuerdo_suave_minimo"),
                                         "rango_J_por_secuencia": r0.get("rango_J_por_secuencia"),
                                         "max_dif_pi": max(f.get("max_dif_pi", 0) for f in r0["semillas"]),
                                         "max_dif_ET_rel": max(f.get("max_dif_ET_rel", 0) for f in r0["semillas"])}
    (out / "reproducir.json").write_text(json.dumps(res, indent=1, default=float))

    mu_, h = res["muestras"], res["hoy_vs_publicada"]
    fam = cfg["fase2"]["familias"]
    md = ["# ¿Por qué el reajuste de hoy no da la mezcla publicada? (ADR-v2-68)", "",
          "## 1. Muestras", "", "| | secuencias | partidos | fechas | técnicos |", "|---|---|---|---|---|"]
    for k in ("publicada", "hoy"):
        s = mu_[k]
        md.append(f"| {k} | {s['secuencias']:,} | {s['partidos']:,} | {s['fecha_min']} a {s['fecha_max']} | {s['tecnicos']} |")
    md += ["", f"Secuencias nuevas: {mu_['secuencias_nuevas']:,} en {mu_['partidos_nuevos']} partidos "
               f"({mu_['fechas_partidos_nuevos']}); de esos partidos, {mu_['partidos_viejos_con_secuencias_nuevas']} ya "
               f"estaban en la muestra publicada. Secuencias publicadas que faltan hoy: "
               f"{mu_['secuencias_publicadas_que_faltan_hoy']:,}.", "",
           "## 2. ¿Cambiaron los datos de los partidos viejos?", "",
           f"La mezcla publicada aplicada hoy a las {res['datos_viejos']['filas_emparejadas']:,} secuencias publicadas: "
           f"máx. |Δr| = {res['datos_viejos']['max_dif_responsabilidad']!r}; idénticas: "
           f"**{'sí' if res['datos_viejos']['identicas'] else 'no'}**.", "",
           "## 3. Reproducción sobre la muestra publicada (decisiva)", "",
           f"J {float(rep['J'][0])!r} contra {float(rep['J'][1])!r}; iteraciones {rep['iteraciones'][0]} / {rep['iteraciones'][1]}; "
           f"máx. |Δ| π {rep['max_dif_abs']['pi']:.1e}, P {rep['max_dif_abs']['P']:.1e}, "
           f"P0 {rep['max_dif_abs']['P0']:.1e}, μ {rep['max_dif_abs']['mu']:.1e}.", "",
           ("**La mezcla publicada SE REPRODUCE bit a bit** con el código de hoy sobre su propia muestra." if
            rep["identico_bit_a_bit"] else "**NO se reproduce bit a bit sobre su propia muestra. PARA y avisa.**"), "",
           "## 4. Tamaño práctico del cambio: publicada contra reajuste con todos los datos de hoy", "",
           "| familia | π hoy / publicada | E[T] hoy / publicada | P(remate) hoy / publicada | TV máx. de una fila de P |",
           "|---|---|---|---|---|"]
    for k in range(K):
        a, b = h["tarjetas_hoy"][k], h["tarjetas_publicada"][k]
        md.append(f"| {fam[k] if k < len(fam) else k + 1} | {a[0]:.4f} / {b[0]:.4f} | {a[1]:.3f} / {b[1]:.3f} | "
                  f"{a[2]:.4f} / {b[2]:.4f} | {h['tv_max_fila_P'][k]:.4f} |")
    md += ["", f"Acuerdo suave {h['acuerdo_suave']:.6f} (duro {h['acuerdo_duro']:.4f}); J por secuencia "
               f"{h['J_por_secuencia'][0]:.6f} hoy contra {h['J_por_secuencia'][1]:.6f} publicada; máx. |ΔP| = "
               f"{h['max_dif_abs_P']:.1e} (absoluta). Máx. Δπ {h['max_dif_pi_pp']:.2f} pp, máx. ΔE[T] relativa "
               f"{h['max_dif_ET_rel']:.4f}, máx. ΔP(remate) {h['max_dif_Premate_pp']:.2f} pp."]
    if "entre_semillas_entrega" in res:
        e = res["entre_semillas_entrega"]
        md += ["", f"Referencia, entre semillas en la entrega: acuerdo suave mínimo {e['acuerdo_suave_minimo']}, "
                   f"rango de J {e['rango_J_por_secuencia']} por secuencia, máx. Δπ {e['max_dif_pi']}, "
                   f"máx. ΔE[T] relativa {e['max_dif_ET_rel']}."]
    (out / "REPRODUCIR.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    sys.exit(0 if rep["identico_bit_a_bit"] else 1)


if __name__ == "__main__":
    main()
