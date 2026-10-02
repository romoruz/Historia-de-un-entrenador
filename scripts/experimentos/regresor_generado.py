#!/usr/bin/env python3
"""
Mejora B (ADR-v2-53, EXPERIMENTO): ¿cuánto se estrechan de más los IC de H1–H8 por tratar r_sk como dato?
Bootstrap por partido que REAJUSTA la mezcla en cada réplica. Ver src/dtcoach/regresor_generado.py.

Uso (raíz del repo, venv activo, con data/ y reports/mezcla/ de la entrega):
  python scripts/experimentos/regresor_generado.py --config config/exp_mejoras.yaml --replicas 200 --muestra 300   # humo
  python scripts/experimentos/regresor_generado.py --config config/exp_mejoras.yaml --replicas 200 --max-minutos 600
Cada réplica reajusta la mezcla (≈ minutos con los 467 mil secuencias de la liga completa): el avance se guarda
tras cada una y se puede reanudar con --reanudar. Salida: <reportes>/experimentos/regresor_generado/.
NO escribe en reports/mezcla, fase1, fase2, fase3 ni historia.
"""
import argparse
import json
import time

import numpy as np
import polars as pl

from dtcoach import regresor_generado as rg
from dtcoach.cli import _elo, _space, _trans
from dtcoach.config import Config
from dtcoach.contexto import tabla_secuencias
from dtcoach.hipotesis import correr
from dtcoach.mezcla import DatosPosesion, Mezcla, ajustar, responsabilidades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/exp_mejoras.yaml")
    ap.add_argument("--foco", default=None)
    ap.add_argument("--replicas", type=int, default=None)
    ap.add_argument("--muestra", type=int, default=0, help="humo: solo N partidos de la liga (todos los del foco)")
    ap.add_argument("--max-minutos", type=float, default=0, help="presupuesto de tiempo (0 = sin límite)")
    ap.add_argument("--reanudar", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    cfg = Config.load(a.config)
    ec = cfg["experimentos"]["regresor_generado"]
    R = a.replicas or ec["replicas"]
    foco = a.foco or cfg["foco"]["coach"]
    c2, mc = dict(cfg["fase2"]), cfg["mezcla"]
    K, familias = c2["K"], c2["familias"]
    c2["foco"] = foco
    m0 = Mezcla.cargar(cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz")
    space, trans = _space(cfg), _trans(cfg)
    d = DatosPosesion.desde_transiciones(trans, space)
    t = tabla_secuencias(trans, space, m0, pl.read_parquet(cfg.ruta("partidos")), _elo(cfg), cfg, foco)
    r0 = responsabilidades(m0, d)
    match, pfoco = t["match_id"].to_numpy(), t["partido_foco"].to_numpy()
    if a.muestra:
        rng = np.random.default_rng(cfg["seed"])
        liga = np.unique(match[~pfoco])
        keep = set(rng.choice(liga, min(a.muestra, len(liga)), replace=False).tolist()) | set(np.unique(match[pfoco]).tolist())
        mask = np.isin(match, list(keep))
        d, r0, t = d.sub(mask), r0[mask], t.filter(pl.Series(mask))
        match, pfoco = match[mask], pfoco[mask]
    con, sin = rg.estratos(match, pfoco)
    print(f"{d.n:,} secuencias · {len(con)} partidos con el foco · {len(sin)} del resto · {R} réplicas", flush=True)
    base = correr(t, familias, c2, cfg["seed"])
    act = rg.actuales(base, K, familias)
    out = cfg.ruta("reportes") / cfg["experimentos"]["salida"] / "regresor_generado"
    out.mkdir(parents=True, exist_ok=True)
    parcial = out / "replicas.json"
    fijo, doble, diag = [], [], []
    if a.reanudar and parcial.exists():
        z = json.loads(parcial.read_text())
        fijo, doble, diag = z["fijo"], z["doble"], z["diag"]
        print(f"reanudo con {len(doble)} réplicas hechas", flush=True)
    tiempos = []
    for b in range(len(doble), R):
        if a.max_minutos and (time.time() - t0) / 60 > a.max_minutos:
            print(f"presupuesto de {a.max_minutos:.0f} min agotado en la réplica {b}", flush=True)
            break
        tb0 = time.time()
        rng = np.random.default_rng([cfg["seed"], b])
        idx = rg.remuestra(match, con, sin, rng)
        d_b, t_fijo = d.sub(idx), t[idx]
        m_b = ajustar(d_b, K, mc["lam"], mc["a0"], mc["n_init"], mc["max_iter"], mc["tol"], seed=cfg["seed"] + 1000 + b,
                      init="escalera", n_corto=mc.get("n_corto", 25), paso_inicial=mc.get("paso_inicial", True),
                      lam0=mc.get("lam0"))
        r_b = responsabilidades(m_b, d_b)
        perm = rg.alinear(r0[idx], r_b)
        r_b = r_b[:, perm]
        t_doble = t_fijo.with_columns(*[pl.Series(f"r_{k + 1}", r_b[:, k]) for k in range(K)])
        fijo.append(rg.cantidades(t_fijo, K, c2.get("ref", 1), c2.get("suave", False), familias))
        doble.append(rg.cantidades(t_doble, K, c2.get("ref", 1), c2.get("suave", False), familias))
        diag.append({"acuerdo_duro": float((r0[idx].argmax(1) == r_b.argmax(1)).mean()),
                     "pi": m_b.pi[perm].tolist(), "convergio": bool(m_b.diagnostico.get("todos_convergieron", True))})
        tiempos.append(time.time() - tb0)
        parcial.write_text(json.dumps({"fijo": fijo, "doble": doble, "diag": diag}))
        print(f"  réplica {b + 1}/{R}: {tiempos[-1]:.0f} s · acuerdo con la mezcla original {diag[-1]['acuerdo_duro']:.3f}", flush=True)
    if len(doble) < 3:
        raise SystemExit("muy pocas réplicas para resumir")
    filas = rg.resumen(fijo, doble, act)
    n = len(doble)
    err = 1 / np.sqrt(2 * (n - 1))
    inf = np.array([f["infl_limpia"] for f in filas])
    infa = np.array([f["infl_vs_actual"] for f in filas])
    if n < 50:
        veredicto = "NECESITA MÁS RÉPLICAS (con menos de 50 no se distingue 1.0 de 1.1)"
    elif np.nanmax(inf) < 1.1:
        veredicto = "DESPRECIABLE: la inflación limpia máxima es < 1.1"
    elif np.nanmedian(inf) < 1.1:
        veredicto = "NO UNIFORMEMENTE DESPRECIABLE: la mediana es < 1.1 pero hay cantidades más infladas"
    else:
        veredicto = "NO DESPRECIABLE: los IC de H1–H8 están estrechos de más"
    res = {"foco": foco, "replicas": n, "muestra": a.muestra or None, "veredicto": veredicto, "filas": filas,
           "diag": diag, "segundos_por_replica": float(np.mean(tiempos)) if tiempos else None}
    (out / "regresor_generado.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))
    md = [f"# Mejora B — regresor generado en la fase 2 ({foco})", "",
          "**EXPERIMENTO (ADR-v2-53), no adoptado.** Bootstrap por partido (estratificado) que reajusta la mezcla en cada réplica.", "",
          f"- réplicas: **{n}** (error relativo de una amplitud ≈ {100 * err:.0f} %)" + (f" · humo con {a.muestra} partidos de liga" if a.muestra else ""),
          f"- acuerdo medio de las familias con la mezcla original: {np.mean([x['acuerdo_duro'] for x in diag]):.3f}",
          f"- **inflación limpia** (doble / fijo): mediana {np.nanmedian(inf):.3f}, máxima {np.nanmax(inf):.3f}",
          f"- inflación contra el IC publicado: mediana {np.nanmedian(infa):.3f}, máxima {np.nanmax(infa):.3f}",
          f"- **veredicto:** {veredicto}", "",
          "| cantidad | estimación | amplitud actual | amplitud «fijo» | amplitud «doble» | inflación limpia | inflación vs actual |",
          "|---|---|---|---|---|---|---|"]
    md += [f"| {f['cantidad']} | {f['estimacion']:+.4f} | {f['w_actual']:.4f} | {f['w_fijo']:.4f} | {f['w_doble']:.4f} | "
           f"{f['infl_limpia']:.2f} | {f['infl_vs_actual']:.2f} |" for f in filas]
    md += ["", "*«fijo» = misma remuestra con las r originales (calibra el bootstrap contra el IC publicado: ≈ 1 si es consistente); "
           "«doble» = mezcla reajustada. La inflación limpia aísla lo que añade la etapa 1.*"]
    (out / "REGRESOR_GENERADO.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:14]))
    print(f"tiempo total: {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
