#!/usr/bin/env python3
"""
Mejora B, consecuencias (ADR-v2-57, EXPERIMENTO): ¿qué afirmaciones publicadas dejan de sostenerse si los IC de
H1–H8 se ensanchan a la amplitud «doble» (la que propaga el error de la mezcla)?

  1. Por cantidad: ¿el IC publicado excluye el 0? ¿Y el IC ensanchado? El ensanchado conserva la forma del
     publicado: [lo − δ, hi + δ] con δ = (w − w_actual)/2 y w = máx(w_actual, w_doble). Nunca se ESTRECHA un IC
     publicado porque el bootstrap haya salido más angosto (regla conservadora).
  2. El BH global de la demostración (730 afirmaciones) rehecho con esos errores: cada p de la fase 2 se recalcula
     escalando su z por el factor f = w / w_actual (p' = 2 Φ(−z/f), z = Φ⁻¹(1 − p/2); con f = 1 la p no cambia,
     sea cual sea el método con que se calculó). Las Wald H1–H6 se escalan con el f MÁS grande de sus componentes
     (W' = W / f²; conservador). Sensibilidad: f = máx(1, inflación limpia) (doble / fijo), que descuenta la
     calibración del propio bootstrap.
  3. ¿Por qué Circulación estéril? Separación de las familias en la mezcla original: entropía de las r_sk, r máxima
     media y la matriz E[r_sj | argmax = k], por familia.

Solo LEE: reports/experimentos/regresor_generado/regresor_generado.json, reports/fase2/hipotesis_<foco>.json,
reports/historia/<foco>/demostracion/demostracion.csv y la mezcla de reports/mezcla. No reajusta nada.
Salida: reports/experimentos/regresor_generado/IMPACTO.md e impacto.json.

Uso:  python scripts/experimentos/regresor_generado_impacto.py            (segundos; la entropía, ~1 min)
      python scripts/experimentos/regresor_generado_impacto.py --sin-entropia
"""
import argparse
import json
import re

import numpy as np
import polars as pl
from scipy import stats

from dtcoach.config import Config
from dtcoach.inference import benjamini_hochberg

COMP_H = {"H1": r"^H1 Δπ", "H2": r"^H2 Δπ", "H3": r"^H3–H6 (perdiendo|ganando) vs empatando", "H4": r"^H3–H6 minuto",
          "H5": r"^H3–H6 local", "H6": r"^H3–H6 rival"}


def cantidad_de(id_: str, afirmacion: str, familias: list[str], metricas_perfil: list[str]) -> str | None:
    """Fila de la demostración (sección fase 2) → nombre de la cantidad en el JSON de B."""
    m = re.match(r"^contexto/(.+)\[(\d)\]$", id_)
    if m:
        return f"H3–H6 {m.group(1)} · {familias[int(m.group(2))]}"
    m = re.match(r"^perfiles/(ataque|defensa)\[(\d+)\]$", id_)
    if m:
        h = "H7" if m.group(1) == "ataque" else "H8"
        return f"{h}/{m.group(1)} · {metricas_perfil[int(m.group(2))]}"
    m = re.match(r"^H([78])\.(\d)$", id_)
    if m:
        lado = "ataque" if m.group(1) == "7" else "defensa"
        return f"H{m.group(1)}/{lado} · xG por secuencia · {familias[int(m.group(2)) - 1]}"
    return None


def p_escalada(p: float, f: float, z_ic: float | None = None) -> float:
    """p con el error estándar multiplicado por f. El z de partida es el MAYOR entre el que implica el p publicado
    y el que implica su IC (|e| / ((hi − lo)/3.92)): un p de bootstrap en el piso (1/n_boot) subestima su z, y
    escalar ese z subestimado tumbaba afirmaciones que su propio IC sostiene (primera corrida, 2026-10-03).
    Nunca devuelve un p menor que el publicado."""
    if not np.isfinite(p) or f <= 1:
        return p
    z = stats.norm.isf(max(p, 1e-300) / 2)
    if z_ic is not None and np.isfinite(z_ic):
        z = max(z, z_ic)
    return float(max(p, 2 * stats.norm.sf(z / f)))


def p_escalada_previa(p: float, f: float) -> float:
    """El método de la primera corrida (solo el z del p): se conserva para mostrar qué caídas eran artefacto."""
    if not np.isfinite(p) or f <= 1:
        return p
    return float(2 * stats.norm.sf(stats.norm.isf(max(p, 1e-300) / 2) / f))


def bh(d: pl.DataFrame, col: str, alpha: float = 0.05) -> np.ndarray:
    from dtcoach.demostracion import MIN_PARTIDOS
    ok = d["p"].is_not_nan().to_numpy() & d["no_demostrable"].is_null().to_numpy()
    q, rech = benjamini_hochberg(d[col].to_numpy()[ok], alpha)
    pocos = d["pocos"].fill_null(False).to_numpy()[ok] | (d["partidos_foco"].fill_null(99).to_numpy()[ok] < MIN_PARTIDOS)
    v = np.full(d.height, "no demostrable", dtype=object)
    v[ok] = np.where(rech & ~pocos, "demostrado", np.where(rech, "pocos partidos", "no demostrado"))
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/exp_mejoras.yaml")
    ap.add_argument("--sin-entropia", action="store_true")
    a = ap.parse_args()
    cfg = Config.load(a.config)
    foco = cfg["foco"]["coach"]
    slug = foco.lower().replace(" ", "_")
    K = cfg["fase2"]["K"]
    fam = cfg["fase2"]["familias"][:K]
    rep = cfg.ruta("reportes")
    out = rep / cfg["experimentos"]["salida"] / "regresor_generado"
    B = json.loads((out / "regresor_generado.json").read_text())
    F2 = json.loads((rep / "fase2" / f"hipotesis_{slug}.json").read_text())
    from dtcoach.regresor_generado import actuales
    act = actuales(F2, K, fam)
    filas = {f["cantidad"]: f for f in B["filas"]}

    # ------------------------------------------------------------ 1. ¿excluye el 0?
    t1 = []
    for n, f in filas.items():
        e, lo, hi = act[n]
        wa, wd, wf = hi - lo, f["w_doble"], f["w_fijo"]
        w = max(wa, wd)
        dl = (w - wa) / 2
        a_ = lo > 0 or hi < 0
        d_ = (lo - dl) > 0 or (hi + dl) < 0
        dd = (wd - wa) / 2                     # sin la regla conservadora (puede estrechar)
        d_libre = (lo - dd) > 0 or (hi + dd) < 0
        t1.append({"cantidad": n, "estimacion": e, "lo": lo, "hi": hi, "lo_doble": lo - dl, "hi_doble": hi + dl,
                   "excluye_actual": a_, "excluye_doble": d_, "cambia": a_ != d_, "excluye_doble_sin_piso": d_libre,
                   "f": w / wa if wa > 0 else 1.0, "f_limpia": max(1.0, f["infl_limpia"]),
                   "z_ic": abs(e) / ((hi - lo) / 3.919928) if hi > lo else float("nan")})
    T1 = {x["cantidad"]: x for x in t1}

    # ------------------------------------------------------------ 2. el BH global
    dem = rep / "historia" / slug / "demostracion" / "demostracion.csv"
    res_bh = None
    if dem.exists():
        d = pl.read_csv(dem, infer_schema_length=None)
        if "no_demostrable" not in d.columns:
            d = d.with_columns(pl.lit(None, pl.Utf8).alias("no_demostrable"))
        d = d.with_columns(pl.col("p").cast(pl.Float64), pl.col("partidos_foco").cast(pl.Float64),
                           pl.col("no_demostrable").cast(pl.Utf8), pl.col("pocos").cast(pl.Boolean))
        sec2 = d["seccion"].str.contains("fase 2").to_numpy()
        p_f, p_l, p_prev, p_dom, cant = [], [], [], [], []
        for i, (sid, idd, af, p) in enumerate(zip(d["seccion"], d["id"], d["afirmacion"], d["p"])):
            c, f1, f2, z_ic = None, 1.0, 1.0, None
            if sec2[i]:
                c = cantidad_de(idd, af, fam, F2["metricas_perfil"])
                if c in T1:
                    f1, f2, z_ic = T1[c]["f"], T1[c]["f_limpia"], T1[c]["z_ic"]
                elif idd in COMP_H:
                    # Wald global: sin la covarianza «doble» no se puede escalar exacto. Regla CONSERVADORA: el f más
                    # grande de sus componentes (W' = W / f²). Sensibilidad: el f del componente que más pesa en la
                    # prueba (el de mayor z por su IC).
                    comps = [x for x in T1 if re.search(COMP_H[idd], x)]
                    if comps:
                        gl = F2["hipotesis"][idd]["gl"]
                        W = stats.chi2.isf(max(p, 1e-300), gl)
                        f_max = max(T1[x]["f"] for x in comps)
                        dom = max(comps, key=lambda x: T1[x]["z_ic"] if np.isfinite(T1[x]["z_ic"]) else -1)
                        p_f.append(max(p, float(stats.chi2.sf(W / f_max ** 2, gl))))
                        p_l.append(max(p, float(stats.chi2.sf(W / max(T1[x]["f_limpia"] for x in comps) ** 2, gl))))
                        p_prev.append(p_f[-1])
                        p_dom.append(max(p, float(stats.chi2.sf(W / T1[dom]["f"] ** 2, gl))))
                        cant.append(f"Wald {idd}: f máx {f_max:.2f}; dominante «{dom}» f {T1[dom]['f']:.2f}")
                        continue
            p_f.append(p_escalada(p, f1, z_ic))
            p_l.append(p_escalada(p, f2, z_ic))
            p_prev.append(p_escalada_previa(p, f1))
            p_dom.append(p_f[-1])
            cant.append(c)
        d = d.with_columns(pl.Series("p_doble", p_f), pl.Series("p_limpia", p_l), pl.Series("p_previo", p_prev),
                           pl.Series("p_dominante", p_dom), pl.Series("cantidad_B", cant))
        v0, v1, v2 = bh(d, "p"), bh(d, "p_doble"), bh(d, "p_limpia")
        v3, v4 = bh(d, "p_previo"), bh(d, "p_dominante")
        d = d.with_columns(pl.Series("antes", v0), pl.Series("doble", v1), pl.Series("limpia", v2),
                           pl.Series("previo", v3), pl.Series("dominante", v4))
        caen = d.filter((pl.col("antes") == "demostrado") & (pl.col("doble") != "demostrado"))
        artefacto = d.filter((pl.col("antes") == "demostrado") & (pl.col("previo") != "demostrado")
                             & (pl.col("doble") == "demostrado"))
        caen_dom = d.filter((pl.col("antes") == "demostrado") & (pl.col("dominante") != "demostrado"))
        caen_l = d.filter((pl.col("antes") == "demostrado") & (pl.col("limpia") != "demostrado"))
        suben = d.filter((pl.col("antes") != "demostrado") & (pl.col("doble") == "demostrado"))
        res_bh = {"afirmaciones": d.height, "demostradas_antes": int((v0 == "demostrado").sum()),
                  "demostradas_doble": int((v1 == "demostrado").sum()), "demostradas_limpia": int((v2 == "demostrado").sum()),
                  "caen": caen.select("seccion", "id", "afirmacion", "efecto", "p", "p_doble", "cantidad_B").to_dicts(),
                  "caen_limpia": caen_l.select("id", "afirmacion", "p", "p_limpia").to_dicts(),
                  "caen_dominante": caen_dom.select("id", "afirmacion", "p", "p_dominante").to_dicts(),
                  "artefacto_metodo_previo": artefacto.select("id", "afirmacion", "p", "p_previo", "p_doble").to_dicts(),
                  "demostradas_previo": int((v3 == "demostrado").sum()),
                  "demostradas_dominante": int((v4 == "demostrado").sum()),
                  "suben": suben.select("id", "afirmacion", "p", "p_doble").to_dicts()}
        d.write_csv(out / "impacto_demostracion.csv")

    # ------------------------------------------------------------ 3. separación de las familias
    sep = None
    if not a.sin_entropia:
        from dtcoach.cli import _space, _trans
        from dtcoach.mezcla import DatosPosesion, Mezcla, responsabilidades
        m = Mezcla.cargar(cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz")
        dpos = DatosPosesion.desde_transiciones(_trans(cfg), _space(cfg))
        r = responsabilidades(m, dpos)
        H = -(r * np.log(np.clip(r, 1e-300, 1))).sum(1) / np.log(K)
        am = r.argmax(1)
        sep = []
        for k in range(K):
            s = am == k
            sep.append({"familia": fam[k], "secuencias": int(s.sum()), "pi": float(r[:, k].mean()),
                        "entropia_media": float(H[s].mean()), "r_max_media": float(r[s, k].mean()),
                        "frac_r_max_bajo_0.6": float((r[s, k] < 0.6).mean()),
                        "impureza": float((r[:, k] * (1 - r[:, k])).sum() / r[:, k].sum()),
                        "E_r_dado_argmax": [float(x) for x in r[s].mean(0)]})
        infl = {k: [] for k in fam}
        for n, f in filas.items():
            for k in fam:
                if n.endswith(f"· {k}"):
                    infl[k].append(f["infl_limpia"])
        for x in sep:
            x["inflacion_limpia_mediana"] = float(np.median(infl[x["familia"]])) if infl[x["familia"]] else float("nan")
            x["inflacion_limpia_max"] = float(np.max(infl[x["familia"]])) if infl[x["familia"]] else float("nan")

    json.dump({"tabla": t1, "bh": res_bh, "separacion": sep}, open(out / "impacto.json", "w"), indent=1,
              ensure_ascii=False, default=float)
    md = [f"# Mejora B — qué se cae con la amplitud «doble» ({foco}) · ADR-v2-57", "",
          "IC ensanchado = el publicado con su forma, abierto (w − w_actual)/2 por lado, w = máx(w_actual, w_doble): "
          "un IC publicado nunca se estrecha.", "",
          "## 1. ¿El IC excluye el 0?", "", "| cantidad | estimación | IC publicado | ¿excluye? | IC «doble» | ¿excluye? | |",
          "|---|---|---|---|---|---|---|"]
    for x in t1:
        md.append(f"| {x['cantidad']} | {x['estimacion']:+.4f} | [{x['lo']:+.4f}, {x['hi']:+.4f}] | {'sí' if x['excluye_actual'] else 'no'} | "
                  f"[{x['lo_doble']:+.4f}, {x['hi_doble']:+.4f}] | {'sí' if x['excluye_doble'] else 'no'} | "
                  f"{'**CAMBIA**' if x['cambia'] else 'no cambia'} |")
    est = [x["cantidad"] for x in t1 if x["excluye_doble_sin_piso"] and not x["excluye_actual"]]
    md += ["", f"Cambian: **{sum(x['cambia'] for x in t1)}** de {len(t1)}. Sin la regla del piso (dejando que el "
           f"bootstrap ESTRECHE un IC) {len(est)} cantidades pasarían a excluir el 0: {', '.join(est) or 'ninguna'}; no "
           "se cuentan.", ""]
    if res_bh:
        md += ["## 2. El BH global de la demostración con los errores «doble»", "",
               f"{res_bh['afirmaciones']} afirmaciones. Demostradas: **{res_bh['demostradas_antes']} → {res_bh['demostradas_doble']}** "
               f"(sensibilidad con la inflación limpia: {res_bh['demostradas_limpia']}).", "",
               f"### Dejan de estar demostradas ({len(res_bh['caen'])})", ""]
        for x in res_bh["caen"]:
            ef = "—" if x["efecto"] is None else f"{x['efecto']:+.4f}"
            md.append(f"- **{x['afirmacion']}** (`{x['id']}`, efecto {ef}): p {x['p']:.3g} → {x['p_doble']:.3g}")
        if not res_bh["caen"]:
            md.append("- ninguna")
        md += ["", f"**Sensibilidad para las Wald H1–H6** (f del componente dominante en vez del máximo): demostradas "
               f"{res_bh['demostradas_dominante']}; caen: " + (", ".join(f"`{x['id']}`" for x in res_bh["caen_dominante"]) or "ninguna") + ".",
               "", f"**Corrección de método.** La primera corrida escalaba solo el z que implica el p publicado; con p de "
               f"bootstrap en el piso eso tumbaba afirmaciones que su IC sostiene (demostradas con ese método: "
               f"{res_bh['demostradas_previo']}). Caían por el método, no por los datos: "
               + (", ".join(f"`{x['id']}` (p {x['p_previo']:.3g} → con el IC {x['p_doble']:.3g})" for x in res_bh["artefacto_metodo_previo"]) or "ninguna") + "."]
        md += ["", "Con la inflación limpia (sensibilidad): " + (", ".join(f"`{x['id']}`" for x in res_bh["caen_limpia"]) or "ninguna")
               + ". Por el BH, una caída puede arrastrar a otras afirmaciones (de cualquier sección) que estaban en el margen.", ""]
    else:
        md += ["*Sin reports/historia/<foco>/demostracion/demostracion.csv: no se rehízo el BH.*", ""]
    if sep:
        md += ["## 3. ¿Por qué Circulación estéril? Separación de las familias en la mezcla original", "",
               "| familia | secuencias | π | entropía media (0–1) de las asignadas | r máxima media | % con r máx < 0.6 | impureza Σr(1−r)/Σr | E[r · | argmax = k] | inflación limpia mediana / máx |",
               "|---|---|---|---|---|---|---|---|---|"]
        for x in sep:
            md.append(f"| {x['familia']} | {x['secuencias']:,} | {x['pi']:.3f} | {x['entropia_media']:.3f} | {x['r_max_media']:.3f} | "
                      f"{100 * x['frac_r_max_bajo_0.6']:.1f} | {x['impureza']:.3f} | "
                      f"{', '.join(f'{v:.2f}' for v in x['E_r_dado_argmax'])} | {x['inflacion_limpia_mediana']:.2f} / {x['inflacion_limpia_max']:.2f} |")
        md += ["", "*Si Circulación estéril es la de mayor entropía / impureza, el error de primera etapa se concentra "
               "donde la mezcla separa peor: una secuencia dudosa reparte su peso con otra familia, y al reajustar la "
               "mezcla ese reparto se mueve.*"]
    (out / "IMPACTO.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
