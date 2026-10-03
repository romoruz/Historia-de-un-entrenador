#!/usr/bin/env python3
"""
Mejora F (ADR-v2-63, EXPERIMENTO): el quinto absorbente INTERRUPCIÓN_FAVOR, en tres variantes.

FASE «preparar» (NO reajusta la mezcla; se puede correr mientras corre B):
  1. Distribución POR ZONA de cada tipo de reanudación a favor (lateral, tiro libre, córner, penal, falta).
  2. Valor de cada reanudación: E[xG de la secuencia que arranca con ella | tipo, zona], de toda la liga.
  3. Las transiciones de las tres variantes (data/processed/experimentos/absorbente5/trans_<v>.parquet):
       (i)   con laterales, c = 0
       (ii)  con laterales, c = valor del balón parado
       (iii) sin laterales (tiro libre, córner, penal, falta), c = valor
FASE «ajustar» (reajusta la mezcla 4 veces por variante; correr SOLO cuando B haya terminado):
  4. K = 3 para cada variante y el criterio del vocabulario (04 §4): acuerdo suave ≥ 0.95, rango de J ≤ 1.08e-4 por
     secuencia, π mín ≥ 1 %, KS ≤ 0.0051 (o mejor que la entrega), |E[T] modelo − obs| ≤ 0.02. Si falla (a): RECHAZADA.
  5. ΔB (PÉRDIDA) y ΔV por zona, de la cadena de la liga y de cada familia (mapa de calor), y los percentiles de
     Almada entre técnicos-club que se mueven más de 5 puntos.

Uso:
  python scripts/experimentos/absorbente5_variantes.py preparar --muestra 50      # humo
  python scripts/experimentos/absorbente5_variantes.py preparar
  python scripts/experimentos/absorbente5_variantes.py ajustar --muestra 200 --semillas 1 2   # humo (después de B)
  python scripts/experimentos/absorbente5_variantes.py ajustar
Salida: reports/experimentos/absorbente5/{PREPARAR.md, AJUSTAR.md, *.json, *.csv, *.png}. No toca reports/mezcla.
"""
import os

# Un hilo de BLAS por proceso: el EM es casi todo álgebra dispersa y elementwise (no usa BLAS multihilo) y varios procesos
# con varios hilos cada uno se pelean los núcleos (sobresuscripción). Se respeta lo que el usuario ya haya fijado.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import multiprocessing as mp
import time

import numpy as np
import polars as pl

from dtcoach import absorbente5 as ab
from dtcoach import ingest
from dtcoach import mezcla as mz
from dtcoach.cli import _space, _trans
from dtcoach.config import Config

TIPOS = ["lateral", "tiro_libre", "corner", "penal", "falta"]
ABS = ["GOL", "REMATE", "PÉRDIDA", "FUERA", "INTERRUPCIÓN"]


def _rutas(cfg):
    out = cfg.ruta("reportes") / cfg["experimentos"]["salida"] / "absorbente5"
    dat = cfg.ruta("transiciones").parent / "experimentos" / "absorbente5"
    out.mkdir(parents=True, exist_ok=True)
    dat.mkdir(parents=True, exist_ok=True)
    return out, dat


def _muestra(trans, n, seed):
    if not n:
        return trans
    u = np.unique(trans["match_id"].to_numpy())
    keep = np.random.default_rng(seed).choice(u, min(n, len(u)), replace=False).tolist()
    return trans.filter(pl.col("match_id").is_in(keep))


def _grid(v, space):
    """vector por zona (ix·ny + iy) → matriz (ny, nx) para dibujar con x a la derecha."""
    return np.asarray(v, float).reshape(space.nx, space.ny).T


def preparar(a, cfg):
    t0 = time.time()
    out, dat = _rutas(cfg)
    space = _space(cfg)
    s5 = ab.espacio5(space)
    trans = _muestra(_trans(cfg), a.muestra, cfg["seed"])
    ids = trans["match_id"].unique().to_list()
    ev = (ingest.scan_events(cfg.ruta("eventos_parquet")).filter(pl.col("match_id").is_in(ids))
          .select("match_id", "index", "type", "team", "pass_type", "shot_type", "location").collect())
    clas = ab.clasificar(trans, ev, space)
    rean = ab.reanudaciones(ev, space)
    val = ab.valor(trans, rean)
    fav = clas.filter(pl.col("a_favor"))
    nx = space.nx
    col = (pl.when(pl.col("zona") >= 0).then(pl.col("zona") // space.ny + 1).otherwise(None)).alias("columna")
    fav = fav.with_columns(col)
    tab = (fav.group_by("tipo", "columna").len().pivot(on="columna", index="tipo", values="len").fill_null(0))
    porz = fav.group_by("tipo", "zona").len().sort("tipo", "zona")
    porz.write_csv(out / "reanudaciones_por_zona.csv")
    val.write_csv(out / "valor_reanudacion.csv")
    xg_sec = float(trans.group_by("seq_uid" if "seq_uid" in trans.columns else "poss_uid")
                   .agg(pl.col("xg").fill_null(0.0).sum())["xg"].mean())
    vcol = (val.filter(pl.col("zona") >= 0).with_columns((pl.col("zona") // space.ny + 1).alias("columna"))
            .group_by("tipo", "columna").agg(((pl.col("valor") * pl.col("n")).sum() / pl.col("n").sum()).alias("v"),
                                             pl.col("n").sum()).sort("tipo", "columna"))
    # figura: conteos y valor por zona, una columna por tipo
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, len(TIPOS), figsize=(3.4 * len(TIPOS), 5.4))
        for i, t in enumerate(TIPOS):
            c = np.zeros(space.n_zones)
            for z, n in porz.filter((pl.col("tipo") == t) & (pl.col("zona") >= 0)).select("zona", "len").iter_rows():
                c[z] = n
            v = np.full(space.n_zones, np.nan)
            for z, x in val.filter((pl.col("tipo") == t) & (pl.col("zona") >= 0)).select("zona", "valor").iter_rows():
                v[z] = x
            for f, (M, tit) in enumerate(((c, f"{t}: reanudaciones tras PÉRDIDA"), (v, f"{t}: xG de la secuencia"))):
                im = ax[f, i].imshow(_grid(M, space), origin="lower", cmap="viridis", aspect="auto")
                ax[f, i].set_title(tit, fontsize=8)
                ax[f, i].set_xticks(range(nx), [str(k + 1) for k in range(nx)])
                ax[f, i].set_yticks([])
                plt.colorbar(im, ax=ax[f, i], fraction=0.046)
        fig.suptitle("columna 1 = arco propio … 5 = arco rival", fontsize=9)
        fig.tight_layout()
        fig.savefig(out / "reanudaciones_por_zona.png", dpi=130)
    except Exception as e:                                            # la figura no es parte del resultado
        print("aviso: sin figura:", e)

    # las tres variantes
    var = {}
    uid = "seq_uid" if "seq_uid" in trans.columns else "poss_uid"
    total_xg = float(trans["xg"].fill_null(0.0).sum())
    for v, spec in ab.VARIANTES.items():
        tv = ab.variante(trans, clas, val if spec["valor"] else None, spec["laterales"], s5)
        tv.write_parquet(dat / f"trans_{v}{'_muestra' if a.muestra else ''}.parquet")
        fin = tv.sort(uid, "event_index").group_by(uid).agg(pl.col("to_state").last())["to_state"].to_numpy() - space.n_transient
        masa = np.bincount(fin, minlength=5) / len(fin)
        cambiadas = int((fin == 4).sum())
        var[v] = {"nombre": spec["nombre"], "masa": masa.tolist(), "secuencias_a_interrupcion": cambiadas,
                  "xg_agregado": float(tv["xg"].fill_null(0.0).sum()) - total_xg}
    fin0 = trans.sort(uid, "event_index").group_by(uid).agg(pl.col("to_state").last())["to_state"].to_numpy() - space.n_transient
    masa0 = (np.bincount(fin0, minlength=5) / len(fin0)).tolist()
    res = {"muestra": a.muestra or None, "a_favor": fav.height, "perdidas": clas.height,
           "por_tipo_columna": tab.to_dicts(), "valor_por_columna": vcol.to_dicts(), "xg_medio_por_secuencia": xg_sec,
           "masa_entrega": masa0, "variantes": var}
    (out / "preparar.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))

    cols = [str(k) for k in range(1, nx + 1)]
    md = ["# Mejora F — preparar las tres variantes (ADR-v2-63)", "",
          (f"**HUMO** con {a.muestra} partidos." if a.muestra else ""), "",
          f"De {clas.height:,} secuencias que terminan en PÉRDIDA, {fav.height:,} ({100 * fav.height / max(clas.height, 1):.1f} %) "
          "las reanuda el mismo equipo a balón parado.", "",
          "## 1. ¿Dónde se reanudan? (columna 1 = junto al arco propio … 5 = junto al arco rival)", "",
          "| tipo | " + " | ".join(cols) + " | total | % en la mitad propia (col. 1–2) |", "|---|" + "---|" * (nx + 2)]
    for t in TIPOS:
        r = tab.filter(pl.col("tipo") == t)
        if r.height == 0:
            continue
        r = r.to_dicts()[0]
        n = [int(r.get(c, 0) or 0) for c in cols]
        tot = sum(n)
        md.append(f"| {t} | " + " | ".join(f"{x:,}" for x in n) + f" | {tot:,} | {100 * (n[0] + n[1]) / max(tot, 1):.0f} % |")
    md += ["", "Mapa por zona: `reanudaciones_por_zona.png` (y `.csv`).", "",
           "## 2. ¿Cuánto vale cada reanudación? xG de la secuencia que arranca con ella (toda la liga)", "",
           f"Referencia: una secuencia cualquiera vale {xg_sec:.4f} xG en promedio.", "",
           "| tipo | " + " | ".join(cols) + " |", "|---|" + "---|" * nx]
    for t in TIPOS:
        r = vcol.filter(pl.col("tipo") == t)
        if r.height == 0:
            continue
        d = dict(zip(r["columna"].to_list(), r["v"].to_list()))
        md.append(f"| {t} | " + " | ".join(f"{d.get(k, float('nan')):.4f}" for k in range(1, nx + 1)) + " |")
    md += ["", "*Si un lateral en las columnas 1–2 vale lo que una secuencia cualquiera (o menos), meterlo como «a favor» "
           "con c = 0 lo trata igual que un penal: esa es la sobrecorrección que separa (i) de (ii) y (iii).*", "",
           "## 3. Las tres variantes (masa de absorción de las secuencias)", "",
           "| | " + " | ".join(ABS) + " | xG agregado a c |", "|---|" + "---|" * 6,
           "| entrega | " + " | ".join(f"{100 * x:.2f} %" for x in masa0) + " | — |"]
    for v, x in var.items():
        md.append(f"| {x['nombre']} | " + " | ".join(f"{100 * y:.2f} %" for y in x["masa"]) + f" | {x['xg_agregado']:,.1f} |")
    md += ["", f"Transiciones escritas en `{dat}`. **No se reajustó nada.** Siguiente: `ajustar`, cuando termine B.",
           "", f"Tiempo: {time.time() - t0:.0f} s."]
    (out / "PREPARAR.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


def _metricas_unidad(m, d, r, perm, ns, foco, minp, space):
    """Por técnico-club: uso de cada familia (alineada a la oficial), fracción a PÉRDIDA y a INTERRUPCIÓN, y valor
    esperado al empezar la secuencia."""
    nt = d.n_transient
    K = m.K
    from dtcoach.absorbing import Cadena
    v0 = np.zeros((K, nt))
    for k in range(K):
        P, c = ab.cadena_familia(m, d, r, k)
        V = Cadena(P, nt).valor(c)
        v0[k] = c + m.P0e(k)[:, :nt] @ V
    meta = d.meta.with_columns(pl.Series("_v", (r * v0[:, d.inicio].T).sum(1)))
    # destino absorbente de cada secuencia: cada una absorbe exactamente una vez
    celda_abs = np.arange(nt * ns) % ns - nt
    onehot = np.zeros((nt * ns, ns - nt))
    ok = celda_abs >= 0
    onehot[np.flatnonzero(ok), celda_abs[ok]] = 1.0
    A = np.asarray(d.S @ onehot)
    to = np.where(A.sum(1) > 0, A.argmax(1), -1)
    meta = meta.with_columns(pl.Series("_loss", (to == 2).astype(float)), pl.Series("_int", (to == 4).astype(float)),
                             *[pl.Series(f"_u{k}", r[:, perm[k]]) for k in range(K)])
    g = (meta.filter(pl.col("coach").is_not_null())
         .group_by("coach", "team").agg(pl.col("match_id").n_unique().alias("partidos"),
                                        *[pl.col(f"_u{k}").mean().alias(f"uso_{k + 1}") for k in range(K)],
                                        pl.col("_loss").mean().alias("perdida"), pl.col("_int").mean().alias("interrupcion"),
                                        pl.col("_v").mean().alias("valor_inicio"))
         .filter(pl.col("partidos") >= minp))
    tot = meta.filter(pl.col("coach") == foco).select(
        *[pl.col(f"_u{k}").mean().alias(f"uso_{k + 1}") for k in range(K)], pl.col("_loss").mean().alias("perdida"),
        pl.col("_int").mean().alias("interrupcion"), pl.col("_v").mean().alias("valor_inicio"))
    return g, tot


def _percentiles(g, tot, foco, metricas):
    nula = g.filter(pl.col("coach") != foco)
    filas = []
    unidades = [(f"{foco} · {t}", g.filter((pl.col("coach") == foco) & (pl.col("team") == t)).to_dicts()[0])
                for t in g.filter(pl.col("coach") == foco)["team"].to_list()]
    if tot.height:
        unidades.append((f"{foco} (todo)", tot.to_dicts()[0]))
    for nom, u in unidades:
        for mtr in metricas:
            x = nula[mtr].to_numpy()
            filas.append({"unidad": nom, "metrica": mtr, "valor": u[mtr],
                          "percentil": float(100 * np.mean(x <= u[mtr])) if len(x) else float("nan")})
    return filas


_DATOS: dict = {}          # variante → DatosPosesion; en cada worker lo llena `_init` (una vez por proceso)


def _init(variantes: dict) -> None:
    _DATOS.clear()
    _DATOS.update(variantes)


def _fit(args):
    """Un ajuste de la mezcla. Las dos formas de llamada replican EXACTAMENTE las del código serie original: las
    semillas de reproducibilidad con el prior fijo, y el ajuste «oficial» de la variante sin él."""
    v, seed, forma, K, mc = args
    d = _DATOS[v]
    if forma == "repro":
        pr = mz.prior(d, mc["lam"], mc["a0"], mc.get("paso_inicial", True), mc.get("lam0"))
        return (v, seed, forma), mz.ajustar(d, K, mc["lam"], mc["a0"], max_iter=mc["max_iter"], tol=mc["tol"], seed=seed,
                                            init="escalera", n_corto=mc.get("n_corto", 25), pr=pr)
    return (v, seed, forma), mz.ajustar(d, K, mc["lam"], mc["a0"], max_iter=mc["max_iter"], tol=mc["tol"], seed=seed,
                                        n_corto=mc.get("n_corto", 25), lam0=mc.get("lam0"))


def _ajustes(variantes: dict, semillas: list[int], seed_cfg: int, K: int, mc: dict, procesos: int) -> dict:
    """Los 4 ajustes de cada variante (len(semillas) de reproducibilidad + 1) con `procesos` procesos. Las tareas son
    independientes y deterministas (cada una trae su semilla), así que el resultado no depende del reparto ni del orden."""
    for d in variantes.values():
        d.S1                                                   # el caché de S − S0 se calcula una vez, antes de repartir
    tareas = [(v, s_, "repro", K, mc) for v in variantes for s_ in semillas] + [(v, seed_cfg, "oficial", K, mc) for v in variantes]
    if procesos <= 1:
        _init(variantes)
        return dict(_fit(t) for t in tareas)
    # «spawn» y no «fork»: el proceso padre ya tiene hilos (polars, BLAS) y fork con hilos puede dejar un candado tomado en el
    # hijo (Python 3.12 lo avisa); un cuelgue silencioso en una corrida larga es peor que ~2 s de arranque. Los datos
    # viajan UNA vez por worker (initargs), no una por tarea.
    with mp.get_context("spawn").Pool(min(procesos, len(tareas)), initializer=_init, initargs=(variantes,)) as pool:
        return dict(pool.imap_unordered(_fit, tareas, chunksize=1))


def ajustar(a, cfg):
    t0 = time.time()
    out, dat = _rutas(cfg)
    space = _space(cfg)
    s5 = ab.espacio5(space)
    mc, bc = cfg["mezcla"], cfg["bondad"]
    K = cfg["fase2"]["K"]
    fam = cfg["fase2"]["familias"][:K]
    foco = cfg["foco"]["coach"]
    minp = cfg["experimentos"]["supuesto_pk"]["min_partidos_nula"]
    semillas = a.semillas or [1, 2, 3]
    trans = _muestra(_trans(cfg), a.muestra, cfg["seed"])
    nt, n4 = space.n_transient, space.n_states
    d4 = mz.DatosPosesion.desde_transiciones(trans, space)
    of = cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz"
    m4 = mz.Mezcla.cargar(of) if of.exists() and not a.muestra else mz.ajustar(
        d4, K, mc["lam"], mc["a0"], max_iter=mc["max_iter"], tol=mc["tol"], seed=cfg["seed"], lam0=mc.get("lam0"))
    r4 = mz.responsabilidades(m4, d4)
    b4 = mz.bondad_largo(m4, d4, bc["t_min"], bc["kmax"])
    P4, c4 = ab.cadena_liga(d4.S, d4.X, nt, n4)
    Z4 = {"liga": ab.por_zona(P4, c4, nt, space.n_zones)}
    for k in range(K):
        P, c = ab.cadena_familia(m4, d4, r4, k)
        Z4[fam[k]] = ab.por_zona(P, c, nt, space.n_zones)
    met = [f"uso_{k + 1}" for k in range(K)] + ["perdida", "interrupcion", "valor_inicio"]
    g4, tot4 = _metricas_unidad(m4, d4, r4, np.arange(K), n4, foco, minp, space)
    pc4 = {(x["unidad"], x["metrica"]): x for x in _percentiles(g4, tot4, foco, met)}

    res, mapas = {"muestra": a.muestra or None, "semillas": semillas, "entrega": {"KS": b4["KS"], "E_T": b4["E_T_modelo"],
                                                                              "E_T_obs": b4["E_T_empirico"]}}, {}
    D5 = {}
    for v in ab.VARIANTES:
        f = dat / f"trans_{v}{'_muestra' if a.muestra else ''}.parquet"
        if not f.exists():
            raise SystemExit(f"falta {f}: corre antes `preparar`{' --muestra ' + str(a.muestra) if a.muestra else ''}")
        D5[v] = mz.DatosPosesion.desde_transiciones(pl.read_parquet(f), s5)
    t_aj = time.time()
    fits = _ajustes(D5, semillas, cfg["seed"], K, mc, a.procesos)
    print(f"  {len(fits)} ajustes de la mezcla con {a.procesos} proceso(s): {time.time() - t_aj:.0f} s", flush=True)
    for v, spec in ab.VARIANTES.items():
        t1 = time.time()
        d5 = D5[v]
        rep = mz.reproducibilidad(d5, K, mc["lam"], mc["a0"], semillas, mc["max_iter"], mc["tol"], mc.get("n_corto", 25),
                                  paso_inicial=mc.get("paso_inicial", True), lam0=mc.get("lam0"),
                                  ms=[fits[(v, s_, "repro")] for s_ in semillas])
        m5 = fits[(v, cfg["seed"], "oficial")]
        b5 = mz.bondad_largo(m5, d5, bc["t_min"], bc["kmax"])
        r5 = mz.responsabilidades(m5, d5)
        perm, acuerdo = mz._emparejar(r4.argmax(1), r5.argmax(1), K)
        crit = {"a": bool(rep["reproducible"]), "suave": rep["acuerdo_suave_minimo"], "rango": rep["rango_J_por_secuencia"],
                "pi_min": rep["pi_minimo"], "KS": b5["KS"], "b": bool(b5["KS"] <= max(0.0051, b4["KS"])),
                "E_T": b5["E_T_modelo"], "E_T_obs": b5["E_T_empirico"],
                "c": bool(abs(b5["E_T_modelo"] - b5["E_T_empirico"]) <= 0.02)}
        P5, c5 = ab.cadena_liga(d5.S, d5.X, nt, s5.n_states)
        Z5 = {"liga": ab.por_zona(P5, c5, nt, space.n_zones)}
        for k in range(K):
            P, c = ab.cadena_familia(m5, d5, r5, perm[k])
            Z5[fam[k]] = ab.por_zona(P, c, nt, space.n_zones)
        delta = {u: {"dV": (Z5[u]["V"] - Z4[u]["V"]).tolist(), "dB_perdida": (Z5[u]["B"][:, 2] - Z4[u]["B"][:, 2]).tolist(),
                     "B_interrupcion": Z5[u]["B"][:, 4].tolist()} for u in Z4}
        mapas[v] = delta
        g5, tot5 = _metricas_unidad(m5, d5, r5, perm, s5.n_states, foco, minp, space)
        mueven = []
        nuevo_int = [x for x in _percentiles(g5, tot5, foco, ["interrupcion"])]
        for x in _percentiles(g5, tot5, foco, met):
            if x["metrica"] == "interrupcion":              # en la entrega vale 0 para todos: no hay «antes»
                continue
            y = pc4.get((x["unidad"], x["metrica"]))
            if y and np.isfinite(x["percentil"]) and np.isfinite(y["percentil"]) and abs(x["percentil"] - y["percentil"]) > 5:
                mueven.append({"unidad": x["unidad"], "metrica": x["metrica"], "antes": y["percentil"], "despues": x["percentil"]})
        res[v] = {"nombre": spec["nombre"], "criterio": crit, "acuerdo_con_oficial": float(acuerdo),
                  "suave_con_oficial": mz.acuerdo_suave(r4, r5[:, perm]),
                  "veredicto": "RECHAZADA (falla a)" if not crit["a"] else ("cumple" if crit["b"] and crit["c"] else "falla b o c"),
                  "delta_zona": delta, "percentiles_que_se_mueven": mueven, "percentil_interrupcion": nuevo_int,
                  "segundos": time.time() - t1}
        print(f"  {spec['nombre']}: {res[v]['veredicto']} (suave {crit['suave']:.3f}, rango {crit['rango']:.2e}, "
              f"KS {crit['KS']:.4f}, E[T] {crit['E_T']:.3f} vs {crit['E_T_obs']:.3f}) · {time.time() - t1:.0f} s", flush=True)
    (out / "ajustar.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        unidades = ["liga", *fam]
        for v in ab.VARIANTES:
            fig, ax = plt.subplots(2, len(unidades), figsize=(3.4 * len(unidades), 5.4))
            for j, u in enumerate(unidades):
                for i, (key, tit) in enumerate((("dV", "ΔV = Δ(N c)"), ("dB_perdida", "ΔB(PÉRDIDA)"))):
                    M = _grid(mapas[v][u][key], space)
                    lim = np.nanmax(np.abs(M)) or 1e-9
                    im = ax[i, j].imshow(M, origin="lower", cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
                    ax[i, j].set_title(f"{u}: {tit}", fontsize=8)
                    ax[i, j].set_xticks(range(space.nx), [str(k + 1) for k in range(space.nx)])
                    ax[i, j].set_yticks([])
                    plt.colorbar(im, ax=ax[i, j], fraction=0.046)
            fig.suptitle(f"{ab.VARIANTES[v]['nombre']} — cambio contra la entrega (columna 1 = arco propio)", fontsize=9)
            fig.tight_layout()
            fig.savefig(out / f"delta_{v}.png", dpi=130)
    except Exception as e:
        print("aviso: sin figura:", e)

    md = ["# Mejora F — las tres variantes, ajustadas (ADR-v2-63)", "",
          (f"**HUMO** con {a.muestra} partidos." if a.muestra else ""), "",
          f"Entrega: KS {b4['KS']:.4f}, E[T] {b4['E_T_modelo']:.3f} vs {b4['E_T_empirico']:.3f}. Semillas {semillas}.", "",
          "## Criterio de aceptación (04 §4)", "",
          "| variante | acuerdo suave ≥ 0.95 | rango J ≤ 1.08e-4 | π mín ≥ 1 % | KS | \\|ΔE[T]\\| ≤ 0.02 | acuerdo con la oficial | veredicto |",
          "|---|---|---|---|---|---|---|---|"]
    for v in ab.VARIANTES:
        c, x = res[v]["criterio"], res[v]
        md.append(f"| {x['nombre']} | {c['suave']:.3f} | {c['rango']:.2e} | {100 * c['pi_min']:.1f} % | {c['KS']:.4f} | "
                  f"{c['E_T']:.3f} vs {c['E_T_obs']:.3f} | {x['suave_con_oficial']:.3f} | **{x['veredicto']}** |")
    md += ["", "## Cambio por zona", "", "Mapas: `delta_i.png`, `delta_ii.png`, `delta_iii.png` (ΔV y ΔB(PÉRDIDA), liga y "
           "familias). Resumen (mín / máx entre las 20 zonas):", "", "| variante | unidad | ΔV | ΔB(PÉRDIDA) | B(INTERRUPCIÓN) |",
           "|---|---|---|---|---|"]
    for v in ab.VARIANTES:
        for u, dd in mapas[v].items():
            md.append(f"| {v} | {u} | {min(dd['dV']):+.4f} / {max(dd['dV']):+.4f} | {min(dd['dB_perdida']):+.3f} / "
                      f"{max(dd['dB_perdida']):+.3f} | {min(dd['B_interrupcion']):.3f} / {max(dd['B_interrupcion']):.3f} |")
    md += ["", f"## Percentiles de {foco} entre técnicos-club (≥ {minp} partidos) que se mueven más de 5 puntos", ""]
    for v in ab.VARIANTES:
        mv = res[v]["percentiles_que_se_mueven"]
        md.append(f"**{res[v]['nombre']}:** " + ("ninguno." if not mv else ""))
        for x in mv:
            md.append(f"- {x['unidad']} · {x['metrica']}: {x['antes']:.0f} → {x['despues']:.0f}")
        md.append("Métrica nueva (sin «antes»), fracción de sus secuencias que terminan en INTERRUPCIÓN: "
                  + "; ".join(f"{x['unidad']} {100 * x['valor']:.1f} % (percentil {x['percentil']:.0f})"
                              for x in res[v]["percentil_interrupcion"]))
        md.append("")
    md += ["*uso_k: fracción de sus secuencias en la familia k (alineada a la oficial); pérdida: fracción de sus secuencias "
           "que terminan en PÉRDIDA (cambia por definición: parte se va a INTERRUPCIÓN); valor_inicio: "
           "xG esperado al empezar la secuencia según su mezcla.*", "", f"Tiempo: {time.time() - t0:.0f} s."]
    (out / "AJUSTAR.md").write_text("\n".join(x for x in md if x is not None), encoding="utf-8")
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fase", choices=["preparar", "ajustar"])
    ap.add_argument("--config", default="config/absorbente5.yaml")
    ap.add_argument("--muestra", type=int, default=0)
    ap.add_argument("--semillas", type=int, nargs="+", default=None)
    ap.add_argument("--procesos", type=int, default=min(4, os.cpu_count() or 1),
                    help="ajustes de la mezcla en paralelo (ajustar). Por omisión min(4, núcleos); 1 = serie. No cambia "
                         "ningún número (cada ajuste es determinista y trae su semilla). Máx. razonable = núcleos físicos")
    a = ap.parse_args()
    cfg = Config.load(a.config)
    (preparar if a.fase == "preparar" else ajustar)(a, cfg)


if __name__ == "__main__":
    main()
