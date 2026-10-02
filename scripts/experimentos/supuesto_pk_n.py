#!/usr/bin/env python3
"""
Mejora A, segunda parte (ADR-v2-55, EXPERIMENTO): ¿el percentil de Almada es EFECTO o POTENCIA?

El exceso T/gl de la prueba de score crece con el número de partidos cuando hay una desviación fija
(bajo una alternativa fija, E[T] ≈ gl + n·δ²), y Almada tiene 168 partidos contra ≥ 30 de la nula.
La TV no crece con n, pero está sesgada hacia ARRIBA con n chico (ruido de muestreo de una fila):
tampoco se compara limpio entre n distintos. Por eso:

  1. exceso y TV de los técnicos-club contra su número de partidos (¿hay tendencia?);
  2. percentil de Almada por exceso y por TV, a n completo, lado a lado;
  3. el número honesto: TODOS a igual n (cada unidad remuestreada a exactamente n partidos, R veces;
     la nula P^k_liga de cada unidad se estima una vez con su liga completa) y el percentil de
     Almada en cada sorteo; se reporta la mediana. También Almada por club (técnico-club, como la nula).

Regla de lectura, fijada ANTES de ver los datos (ADR-v2-55), con la mediana a n = 30:
  - percentil ≤ 80 por exceso Y por TV  → el supuesto es una aproximación razonable (limitación);
  - percentil ≥ 95 por exceso Y por TV  → el supuesto NO se sostiene para Almada;
  - cualquier otra cosa                  → no concluyente: se reporta así, sin elegir rama.

No reajusta la mezcla (usa la de reports/mezcla y sus responsabilidades): se puede correr mientras corre B.

Uso:
  python scripts/experimentos/supuesto_pk_n.py --muestra 8 --remuestras 3      # humo
  python scripts/experimentos/supuesto_pk_n.py                                  # completa (n = 30 y 40, R = 20)
Necesita reports/experimentos/supuesto_pk/supuesto_pk.json (corre antes supuesto_pk.py).
Salida: reports/experimentos/supuesto_pk_n/{SUPUESTO_PK_N.md, supuesto_pk_n.json, unidades.csv, exceso_vs_n.png}
"""
import argparse
import json
import time

import numpy as np
import polars as pl
from scipy import stats

from dtcoach import supuesto_pk as spk
from dtcoach.cli import _elo, _space, _trans
from dtcoach.config import Config
from dtcoach.contexto import tabla_secuencias
from dtcoach.mezcla import DatosPosesion, Mezcla, responsabilidades

FAM = ["Directa", "Circulación estéril", "Ataque elaborado"]


def lectura(p_ex: float, p_tv: float) -> str:
    if p_ex <= 80 and p_tv <= 80:
        return "APROXIMACIÓN RAZONABLE"
    if p_ex >= 95 and p_tv >= 95:
        return "NO SE SOSTIENE"
    return "NO CONCLUYENTE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/exp_mejoras.yaml")
    ap.add_argument("--n-igual", type=int, nargs="+", default=[30, 40])
    ap.add_argument("--remuestras", type=int, default=20)
    ap.add_argument("--muestra", type=int, default=0, help="humo: solo los primeros N técnicos-club de la nula")
    a = ap.parse_args()
    t0 = time.time()
    cfg = Config.load(a.config)
    ec = cfg["experimentos"]["supuesto_pk"]
    foco = cfg["foco"]["coach"]      # fijo en config/exp_mejoras.yaml: Guillermo Almada
    base = cfg.ruta("reportes") / cfg["experimentos"]["salida"]
    previo = json.loads((base / "supuesto_pk" / "supuesto_pk.json").read_text())
    out = base / "supuesto_pk_n"
    out.mkdir(parents=True, exist_ok=True)
    K = cfg["fase2"]["K"]
    fam = (cfg["fase2"].get("familias") or FAM)[:K]

    # ---- 1 y 2: con la corrida completa (no hace falta recalcular nada)
    nula = previo["nula_empirica"]
    tab = pl.DataFrame([{"coach": n["coach"], "team": n["team"], "partidos": n["partidos"],
                         **{f"exceso_{k + 1}": n["exceso"][k] for k in range(K)},
                         **{f"tv_{k + 1}": n["tv"][k] for k in range(K)}} for n in nula])
    tab.write_csv(out / "unidades.csv")
    fo = {k: previo["familias"][k]["P"] for k in range(K)}
    tendencia, completo = [], []
    for k in range(K):
        ex, tv, n = (tab[f"exceso_{k + 1}"].to_numpy(), tab[f"tv_{k + 1}"].to_numpy(), tab["partidos"].to_numpy())
        ok = np.isfinite(ex) & np.isfinite(tv)
        r_ex = stats.spearmanr(n[ok], ex[ok])
        r_tv = stats.spearmanr(n[ok], tv[ok])
        # pendiente de (exceso − 1) sobre partidos: bajo una desviación fija, (exceso − 1) ∝ n
        b = np.polyfit(n[ok], ex[ok] - 1, 1)
        tendencia.append({"familia": k + 1, "rho_exceso": float(r_ex.statistic), "p_exceso": float(r_ex.pvalue),
                          "rho_tv": float(r_tv.statistic), "p_tv": float(r_tv.pvalue),
                          "pendiente_exceso_por_10_partidos": float(10 * b[0]),
                          "exceso_predicho_168": float(1 + np.polyval(b, previo["partidos_foco"]))})
        completo.append({"familia": k + 1, "exceso": fo[k]["exceso"], "tv": fo[k]["tv"],
                         "pct_exceso": spk.percentil(fo[k]["exceso"], ex), "pct_tv": spk.percentil(fo[k]["tv"], tv)})
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, K, figsize=(4.2 * K, 7), sharex=True)
        for k in range(K):
            for fila, col, nom in ((0, "exceso", "exceso T/gl"), (1, "tv", "TV media")):
                axx = ax[fila, k]
                axx.scatter(tab["partidos"], tab[f"{col}_{k + 1}"], s=18, color="#777", label="técnicos-club")
                axx.scatter([previo["partidos_foco"]], [fo[k][col]], s=90, marker="*", color="#c0392b", label=foco)
                if fila == 0:
                    axx.axhline(1, lw=0.8, ls="--", color="#999")
                    axx.set_title(fam[k], fontsize=10)
                axx.set_ylabel(nom)
                if fila == 1:
                    axx.set_xlabel("partidos")
        ax[0, 0].legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out / "exceso_vs_n.png", dpi=130)
    except Exception as e:                                    # la figura no es parte del resultado
        print("aviso: no hice la figura:", e)

    # ---- 3: todos a igual n
    m = Mezcla.cargar(cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz")
    space, trans = _space(cfg), _trans(cfg)
    d = DatosPosesion.desde_transiciones(trans, space)
    t = tabla_secuencias(trans, space, m, pl.read_parquet(cfg.ruta("partidos")), _elo(cfg), cfg, foco)
    r = responsabilidades(m, d)
    match = t["match_id"].to_numpy()
    es_foco, pfoco = t["f"].to_numpy(), t["partido_foco"].to_numpy()
    S1 = d.S1.tocsr()
    unidades = [{"nombre": f"FOCO · {foco}", "f": es_foco, "excl": pfoco}]
    for team in t.filter(pl.col("f"))["team"].unique().sort().to_list():
        unidades.append({"nombre": f"FOCO · {foco} · {team}",
                         "f": (es_foco & (t["team"] == team).fill_null(False).to_numpy()), "excl": pfoco})
    filas_n = nula[: a.muestra] if a.muestra else nula
    for n in filas_n:
        f = ((t["coach"] == n["coach"]) & (t["team"] == n["team"])).fill_null(False).to_numpy().astype(bool)
        suyos = t.filter(((pl.col("coach") == n["coach"]) & (pl.col("team") == n["team"]))
                         | (pl.col("coach_faced") == n["coach"]))["match_id"]
        unidades.append({"nombre": f"{n['coach']} · {n['team']}", "f": f,
                         "excl": np.isin(match, suyos.unique().to_numpy()) | pfoco, "nula": True})
    igual = {}
    for n_eq in a.n_igual:
        t1 = time.time()
        res = spk.igualar_n(S1, r, match, unidades, m.P, d.n_transient, d.n_states, n_eq, a.remuestras,
                            ec["a"], ec["n_min"], seed=cfg["seed"] + n_eq)
        nombres_nula = [u["nombre"] for u in unidades if u.get("nula")]
        filas = []
        for u in unidades:
            if u.get("nula"):
                continue
            ru = res[u["nombre"]]
            if not np.isfinite(ru["exceso"]).any():
                filas.append({"unidad": u["nombre"], "partidos": ru["partidos"], "familias": None})
                continue
            fams = []
            for k in range(K):
                pe = [spk.percentil(ru["exceso"][b, k], np.array([res[x]["exceso"][b, k] for x in nombres_nula]))
                      for b in range(a.remuestras)]
                pt = [spk.percentil(ru["tv"][b, k], np.array([res[x]["tv"][b, k] for x in nombres_nula]))
                      for b in range(a.remuestras)]
                fams.append({"familia": k + 1, "exceso_med": float(np.nanmedian(ru["exceso"][:, k])),
                             "tv_med": float(np.nanmedian(ru["tv"][:, k])),
                             "pct_exceso_med": float(np.nanmedian(pe)), "pct_exceso_q": [float(np.nanpercentile(pe, 25)), float(np.nanpercentile(pe, 75))],
                             "pct_tv_med": float(np.nanmedian(pt)), "pct_tv_q": [float(np.nanpercentile(pt, 25)), float(np.nanpercentile(pt, 75))]})
            filas.append({"unidad": u["nombre"], "partidos": ru["partidos"], "familias": fams})
        n_nula = int(sum(np.isfinite(res[x]["exceso"]).any() for x in nombres_nula))
        igual[n_eq] = {"unidades_nula": n_nula, "filas": filas, "segundos": time.time() - t1,
                       "nula_mediana_exceso": [float(np.nanmedian([np.nanmedian(res[x]["exceso"][:, k]) for x in nombres_nula]))
                                               for k in range(K)],
                       "nula_mediana_tv": [float(np.nanmedian([np.nanmedian(res[x]["tv"][:, k]) for x in nombres_nula]))
                                           for k in range(K)]}
        print(f"  n = {n_eq}: {n_nula} técnicos-club comparables · {igual[n_eq]['segundos']:.0f} s", flush=True)

    n_ref = 30 if 30 in igual else a.n_igual[0]
    foco_ref = igual[n_ref]["filas"][0]["familias"]
    veredictos = [lectura(f["pct_exceso_med"], f["pct_tv_med"]) for f in foco_ref] if foco_ref else []
    res_json = {"foco": foco, "partidos_foco": previo["partidos_foco"], "tendencia": tendencia, "completo": completo,
                "igual_n": igual, "n_referencia": n_ref, "veredictos": veredictos, "remuestras": a.remuestras,
                "muestra": a.muestra or None}
    (out / "supuesto_pk_n.json").write_text(json.dumps(res_json, indent=1, ensure_ascii=False, default=float))

    md = [f"# Mejora A (2) — ¿el percentil de {foco} es efecto o potencia? (ADR-v2-55)", "",
          "**EXPERIMENTO, no adoptado.** La prueba es la de `supuesto_pk.py`; aquí solo se compara a igual tamaño.",
          (f"**HUMO:** solo {a.muestra} técnicos-club y {a.remuestras} remuestras: no interpretar." if a.muestra else ""), "",
          "## 1. ¿El estadístico crece con el número de partidos? (técnicos-club de la nula)", "",
          f"{len(nula)} técnicos-club con ≥ {ec['min_partidos_nula']} partidos (de {int(tab['partidos'].min())} a "
          f"{int(tab['partidos'].max())}); {foco}: {previo['partidos_foco']}. Figura: `exceso_vs_n.png`.", "",
          "| familia | ρ(exceso, partidos) | p | (exceso−1) por cada 10 partidos | exceso predicho con los partidos del foco | ρ(TV, partidos) | p |",
          "|---|---|---|---|---|---|---|"]
    for tr, nom in zip(tendencia, fam):
        md.append(f"| {nom} | {tr['rho_exceso']:+.2f} | {tr['p_exceso']:.3g} | {tr['pendiente_exceso_por_10_partidos']:+.3f} | "
                  f"{tr['exceso_predicho_168']:.2f} | {tr['rho_tv']:+.2f} | {tr['p_tv']:.3g} |")
    md += ["", "*Si ρ(exceso, partidos) es claramente positiva, el percentil por exceso a n completo está confundido con "
           "la potencia. La TV tiende a BAJAR con n (su sesgo de muestreo se encoge), así que ρ(TV, partidos) negativa es "
           "lo esperable sin ningún efecto.*", "",
           "## 2. Percentil de " + foco + " a n completo: exceso contra TV", "",
           "| familia | exceso | percentil por exceso | TV | percentil por TV |", "|---|---|---|---|---|"]
    for c, nom in zip(completo, fam):
        md.append(f"| {nom} | {c['exceso']:.2f} | {c['pct_exceso']:.0f} | {c['tv']:.3f} | {c['pct_tv']:.0f} |")
    md += ["", f"*La TV de {foco} sale de {previo['partidos_foco']} partidos y la de la nula de {int(tab['partidos'].min())}–{int(tab['partidos'].max())}: el sesgo de "
           "muestreo de la TV favorece a los de menos partidos (TV más alta), así que este percentil por TV está "
           "sesgado hacia ABAJO para el foco. Ninguno de los dos números de esta tabla es el honesto.*", "",
           "## 3. El número honesto: todos a igual número de partidos", ""]
    for n_eq, ig in igual.items():
        md += [f"### n = {n_eq} partidos ({a.remuestras} remuestras; {ig['unidades_nula']} técnicos-club con ≥ {n_eq})", "",
               "| unidad | partidos | familia | exceso (mediana) | percentil por exceso [IQR] | TV (mediana) | percentil por TV [IQR] |",
               "|---|---|---|---|---|---|---|"]
        for fl in ig["filas"]:
            if not fl["familias"]:
                md.append(f"| {fl['unidad']} | {fl['partidos']} | — | menos de {n_eq} partidos | | | |")
                continue
            for f, nom in zip(fl["familias"], fam):
                md.append(f"| {fl['unidad']} | {fl['partidos']} | {nom} | {f['exceso_med']:.2f} | {f['pct_exceso_med']:.0f} "
                          f"[{f['pct_exceso_q'][0]:.0f}–{f['pct_exceso_q'][1]:.0f}] | {f['tv_med']:.3f} | {f['pct_tv_med']:.0f} "
                          f"[{f['pct_tv_q'][0]:.0f}–{f['pct_tv_q'][1]:.0f}] |")
        md += ["", "Mediana de la nula a este n: exceso " + ", ".join(f"{x:.2f}" for x in ig["nula_mediana_exceso"])
               + " · TV " + ", ".join(f"{x:.3f}" for x in ig["nula_mediana_tv"]) + ".", ""]
    md += ["## Lectura (regla fijada antes de correr, ADR-v2-55)", "",
           f"Con la mediana a n = {n_ref}: percentil ≤ 80 por exceso **y** por TV → aproximación razonable; ≥ 95 por "
           "los dos → el supuesto no se sostiene; otra cosa → no concluyente.", ""]
    for f, nom, v in zip(foco_ref or [], fam, veredictos):
        md.append(f"- **{nom}:** exceso {f['pct_exceso_med']:.0f}, TV {f['pct_tv_med']:.0f} → **{v}**")
    md += ["", f"Tiempo: {time.time() - t0:.0f} s."]
    (out / "SUPUESTO_PK_N.md").write_text("\n".join(x for x in md if x is not None), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
