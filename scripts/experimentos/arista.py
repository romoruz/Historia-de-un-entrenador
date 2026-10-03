#!/usr/bin/env python3
"""
Mejora E (ADR-v2-59, EXPERIMENTO): la arista marcada pase / conducción. Matemática en src/dtcoach/arista.py.

  1. Ajuste de K = 3 con la arista sobre toda la liga y el criterio de aceptación del vocabulario (04 §4):
     (a) reproducible: acuerdo suave ≥ 0.95, rango de J entre semillas ≤ 1.08e-4 por secuencia, ningún π < 1 %;
     (b) KS de duración ≤ 0.0051 (o mejor que el de la entrega);  (c) |E[T] modelo − observado| ≤ 0.02.
     Si falla (a), la mejora queda RECHAZADA.
  2. Reparto pase / conducción por familia (arista y, como referencia, la mezcla oficial).
  3. Ganancia fuera de muestra (CV por partido) en nats por acción en la escala común (Prop. 5.1), prediciendo
     la siguiente zona con filtrado de la familia: arista contra base, K = 3; y K = 1 como control (0 por construcción).

Uso:
  python scripts/experimentos/arista.py --muestra 200 --semillas 1 2 --folds 2      # humo
  python scripts/experimentos/arista.py                                              # completa (decenas de minutos)
  python scripts/experimentos/arista.py --sin-cv                                     # solo 1 y 2
Salida: reports/experimentos/arista/{ARISTA.md, arista.json}. No escribe en reports/mezcla.
"""
import argparse
import json
import time

import numpy as np
import polars as pl

from dtcoach import arista as ar
from dtcoach import mezcla as mz
from dtcoach.cli import _space, _trans
from dtcoach.config import Config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/arista.yaml")
    ap.add_argument("--muestra", type=int, default=0, help="humo: solo N partidos")
    ap.add_argument("--semillas", type=int, nargs="+", default=None)
    ap.add_argument("--folds", type=int, default=None)
    ap.add_argument("--sin-cv", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    cfg = Config.load(a.config)
    mc, ac = cfg["mezcla"], cfg["arista"]
    K = ac["K"]
    semillas = a.semillas or ac["semillas"]
    folds = a.folds or ac["folds"]
    out = cfg.ruta("reportes") / cfg["experimentos"]["salida"] / "arista"
    out.mkdir(parents=True, exist_ok=True)
    space = _space(cfg)
    trans = _trans(cfg)
    if a.muestra:
        u = np.unique(trans["match_id"].to_numpy())
        keep = np.random.default_rng(cfg["seed"]).choice(u, min(a.muestra, len(u)), replace=False)
        trans = trans.filter(pl.col("match_id").is_in(keep.tolist()))
    nt, ns = space.n_transient, space.n_states
    tipos = dict(trans["action_type"].value_counts().iter_rows())
    db = mz.DatosPosesion.desde_transiciones(trans, space)
    da = ar.datos(trans, space)
    lam, a0, lam0 = mc["lam"], mc["a0"], mc.get("lam0")
    print(f"{db.n:,} secuencias · {len(trans):,} transiciones · tipos de acción {tipos}", flush=True)

    # ---------------------------------------------------------------- 1. criterio de aceptación
    t1 = time.time()
    rep = ar.reproducibilidad(da, K, lam, a0, semillas, mc["max_iter"], mc["tol"], mc.get("n_corto", 25), lam0, ns)
    mejor = rep.pop("mejor")
    marg = ar.marginal(mejor, ns)
    bc = cfg["bondad"]
    bond = mz.bondad_largo(marg, db, bc["t_min"], bc["kmax"])
    of_path = cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz"
    oficial = mz.Mezcla.cargar(of_path) if of_path.exists() and not a.muestra else None
    if oficial is None:          # en humo (o sin la mezcla oficial) la referencia se ajusta aquí, misma muestra
        oficial = mz.ajustar(db, K, lam, a0, max_iter=mc["max_iter"], tol=mc["tol"], seed=cfg["seed"],
                             n_corto=mc.get("n_corto", 25), lam0=lam0)
    bond0 = mz.bondad_largo(oficial, db, bc["t_min"], bc["kmax"])
    crit = {"a_reproducible": rep["reproducible"], "b_KS": bond["KS"], "b_KS_entrega": bond0["KS"],
            "b_ok": bool(bond["KS"] <= max(0.0051, bond0["KS"])),
            "c_ET_modelo": bond["E_T_modelo"], "c_ET_obs": bond["E_T_empirico"],
            "c_ok": bool(abs(bond["E_T_modelo"] - bond["E_T_empirico"]) <= 0.02)}
    print(f"  criterio: reproducible {rep['reproducible']} (suave {rep['acuerdo_suave_minimo']:.3f}, rango J/sec "
          f"{rep['rango_J_por_secuencia']:.2e}, π mín {rep['pi_minimo']:.3f}) · KS {bond['KS']:.4f} (entrega "
          f"{bond0['KS']:.4f}) · E[T] {bond['E_T_modelo']:.3f} vs {bond['E_T_empirico']:.3f} · {time.time() - t1:.0f} s",
          flush=True)

    # ---------------------------------------------------------------- 2. reparto por familia
    fam = cfg["fase2"]["familias"][:K]
    rep_ar = ar.reparto_marcas(mejor, da, ns)
    r_of = mz.responsabilidades(oficial, db)
    C = np.asarray(da.S.T @ r_of).T.reshape(K, nt, ar.M, ns).sum((1, 3))
    rep_of = C / C.sum(1, keepdims=True)
    r_ar = mz.responsabilidades(mejor, da)
    perm, acuerdo = mz._emparejar(r_of.argmax(1), r_ar.argmax(1), K)       # tipo de la arista ↔ familia oficial
    suave = mz.acuerdo_suave(r_of, r_ar[:, perm])
    tar_of, tar_ar = mz._tarjetas(oficial), mz._tarjetas(marg)[perm]

    # ---------------------------------------------------------------- 3. ganancia fuera de muestra
    cv = None
    if not a.sin_cv:
        pz_all = ar.pasos(trans)
        match_seq = db.meta["match_id"].to_numpy()
        u = np.unique(match_seq)
        f_match = dict(zip(u, np.random.default_rng(cfg["seed"]).permutation(len(u)) % folds))
        fseq = np.array([f_match[x] for x in match_seq])
        area = np.full(nt, 1.0 / space.n_zones)
        dif3, dif1, base3, partido = [], [], [], []
        for f in range(folds):
            t2 = time.time()
            tr, te = fseq != f, fseq == f
            mb = mz.ajustar(db.sub(tr), K, lam, a0, max_iter=mc["max_iter"], tol=mc["tol"], seed=cfg["seed"],
                            n_corto=mc.get("n_corto", 25), lam0=lam0)
            ma = ar.ajustar(da.sub(tr), K, lam, a0, mc["max_iter"], mc["tol"], cfg["seed"], mc.get("n_corto", 25), lam0,
                            ns=ns)
            mb1 = mz.ajustar(db.sub(tr), 1, lam, a0, max_iter=mc["max_iter"], tol=mc["tol"], seed=cfg["seed"], lam0=lam0)
            ma1 = ar.ajustar(da.sub(tr), 1, lam, a0, mc["max_iter"], mc["tol"], cfg["seed"], lam0=lam0, ns=ns)
            sel = te[pz_all["seq"]]
            pz = {k: (v[sel] if isinstance(v, np.ndarray) and len(v) == len(sel) else v) for k, v in pz_all.items()}
            mapa = -np.ones(db.n, int)
            mapa[np.flatnonzero(te)] = np.arange(te.sum())
            pz["seq"] = mapa[pz["seq"]]
            pz["n_seq"] = int(te.sum())
            pz["inicio"] = db.inicio[te]
            sb3 = ar.puntaje(mb, pz, nt, ns, area, False)
            sa3 = ar.puntaje(ma, pz, nt, ns, area, True)
            sb1 = ar.puntaje(mb1, pz, nt, ns, area, False)
            sa1 = ar.puntaje(ma1, pz, nt, ns, area, True)
            dif3.append(sa3 - sb3)
            dif1.append(sa1 - sb1)
            base3.append(sb3)
            partido.append(pz["match"])
            print(f"  pliegue {f + 1}/{folds}: K=3 {np.mean(sa3 - sb3):+.4f} nats/acción · K=1 {np.mean(sa1 - sb1):+.2e} · "
                  f"{time.time() - t2:.0f} s", flush=True)
        pm = np.concatenate(partido)
        cv = {"K3": ar.ganancia(np.concatenate(dif3), pm), "K1": ar.ganancia(np.concatenate(dif1), pm),
              "puntaje_base_K3": float(np.concatenate(base3).mean()), "folds": folds}

    res = {"muestra": a.muestra or None, "secuencias": db.n, "tipos_accion": tipos, "reproducibilidad": rep,
           "bondad": bond, "bondad_entrega": bond0, "criterio": crit,
           "reparto_arista": rep_ar.tolist(), "reparto_oficial": rep_of.tolist(), "emparejamiento": perm.tolist(),
           "acuerdo_con_oficial": {"duro": float(acuerdo), "suave": float(suave)},
           "tarjetas_oficial": tar_of.tolist(), "tarjetas_arista": tar_ar.tolist(), "cv": cv,
           "parametros_libres_por_fila": {"base": ns - 1, "arista": ar.M * ns - 1}}
    (out / "arista.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))

    veredicto = ("RECHAZADA: falla (a), el vocabulario con la arista no es reproducible" if not rep["reproducible"] else
                 ("criterio cumplido" if crit["b_ok"] and crit["c_ok"] else "falla (b) o (c)"))
    md = ["# Mejora E — arista marcada pase / conducción (ADR-v2-59)", "",
          "**EXPERIMENTO, no adoptado.** " + (f"**HUMO** con {a.muestra} partidos: no interpretar." if a.muestra else ""), "",
          f"{db.n:,} secuencias, {len(trans):,} transiciones. Marcas: pase, conducción, remate, terminal (las dos últimas "
          "estructurales). Parámetros libres por fila de cada P^k: "
          f"{ns - 1} → {ar.M * ns - 1} (no «~20 por familia»: son ~{(ar.M - 1) * ns} más **por fila**, aunque muchas celdas "
          "son estructuralmente cero).", "",
          "## 1. Criterio de aceptación del vocabulario (04 §4)", "",
          "| criterio | arista | entrega | ¿cumple? |", "|---|---|---|---|",
          f"| (a) acuerdo suave mínimo ≥ 0.95 | {rep['acuerdo_suave_minimo']:.3f} | 0.997 | "
          f"{'sí' if rep['acuerdo_suave_minimo'] >= 0.95 else '**no**'} |",
          f"| (a) rango de J por secuencia ≤ 1.08e-4 | {rep['rango_J_por_secuencia']:.2e} | 4e-6 | "
          f"{'sí' if rep['rango_J_por_secuencia'] <= mz.TOL_J_POR_SECUENCIA else '**no**'} |",
          f"| (a) π mínimo ≥ 1 % | {100 * rep['pi_minimo']:.1f} % | — | {'sí' if rep['pi_minimo'] >= 0.01 else '**no**'} |",
          f"| (b) KS de duración ≤ 0.0051 | {bond['KS']:.4f} | {bond0['KS']:.4f} | {'sí' if crit['b_ok'] else '**no**'} |",
          f"| (c) \\|E[T] modelo − observado\\| ≤ 0.02 | {bond['E_T_modelo']:.3f} vs {bond['E_T_empirico']:.3f} | "
          f"{bond0['E_T_modelo']:.3f} vs {bond0['E_T_empirico']:.3f} | {'sí' if crit['c_ok'] else '**no**'} |", "",
          f"Semillas {semillas}. **{veredicto}.**", "",
          "## 2. ¿Qué familias salen y cómo reparten pase y conducción?", "",
          f"Acuerdo con la mezcla oficial (tipos emparejados): duro {acuerdo:.3f}, suave {suave:.3f}.", "",
          "| familia oficial | π (oficial → arista) | E[T] (oficial → arista) | P(remate) (oficial → arista) | "
          "% pase / conducción / remate / terminal (oficial) | ídem (arista) |", "|---|---|---|---|---|---|"]
    for k in range(K):
        md.append(f"| {fam[k]} | {tar_of[k, 0]:.3f} → {tar_ar[k, 0]:.3f} | {tar_of[k, 1]:.2f} → {tar_ar[k, 1]:.2f} | "
                  f"{tar_of[k, 2]:.3f} → {tar_ar[k, 2]:.3f} | {' / '.join(f'{100 * x:.1f}' for x in rep_of[k])} | "
                  f"{' / '.join(f'{100 * x:.1f}' for x in rep_ar[perm[k]])} |")
    md += ["", "*Hipótesis previa: Directa con más conducción, Circulación estéril con más pase. Se lee en la tabla, no se asume.*", ""]
    if cv:
        g3, g1 = cv["K3"], cv["K1"]
        md += ["## 3. ¿Predice mejor la siguiente acción? (CV por partido, escala común)", "",
               f"- **K = 3 (mezcla): {g3['nats_por_accion']:+.4f} nats por acción** (EE por partido {g3['ee']:.4f}; "
               f"{g3['acciones']:,} acciones de {g3['partidos']:,} partidos no vistos).",
               f"- K = 1 (control): {g1['nats_por_accion']:+.2e}: cero por construcción (la marginal de una sola cadena "
               "es la del modelo base).", "",
               "**Cómo leerlo contra §14.** Dirección (+0.066) y presión (+0.031) ponían información NUEVA en el ORIGEN de "
               "la transición (el estado), y su ganancia es la de una sola cadena. La marca de la arista está en la "
               "transición que se predice, así que para una sola cadena no informa nada (K = 1 ≈ 0): lo único que puede "
               "ganar es que las marcas PASADAS ayuden a reconocer la familia de la secuencia. No es la misma cantidad que "
               "la de §14; la comparación numérica es solo de orden de magnitud.", ""]
    md += [f"Tiempo: {time.time() - t0:.0f} s."]
    (out / "ARISTA.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
