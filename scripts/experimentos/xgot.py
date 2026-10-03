#!/usr/bin/env python3
"""
Experimento xGOT (ADR-v2-56, no adoptado): partir «portero y definición» (Prop. 16.6) en dos.

  0. VERIFICACIÓN: ¿los remates a puerta traen la altura z en el plano de la portería? Si no, se DETIENE
     (código de salida 2) y no calcula nada con la (x, y) en la cancha.
  1. xGOT = E[G | a puerta, (y, z) en el marco, calidad previa], fuera de muestra con pliegues por partido.
  2. Cinco términos por saque: prevención, alejamiento, supresión, definición = s(F − xGOT), portero = s(xGOT − g).
     Se verifica que suman p κ − g (error máximo reportado).
  3. τ² de cada término nuevo entre técnicos-club (Prop. 16.4, varianza común) y el lugar del foco.
  4. H24–H26 vueltas a correr (no usan el cuarto término: deben salir idénticas) y el BH global de la
     demostración con las pruebas de la cadena «portero y definición» reemplazadas por las dos nuevas:
     ¿cambia alguna etiqueta?

Solo LEE lo que ya existe (tabla de la liga, capas y cadena del xDefense, eventos, demostración); no reajusta
la mezcla ni toca reports/historia. Salida: reports/experimentos/xgot/{XGOT.md, xgot.json, etapas.csv}.

Uso:
  python scripts/experimentos/xgot.py --solo-verificar           # solo el paso 0
  python scripts/experimentos/xgot.py --muestra 300              # humo: 300 partidos (y todos los del foco)
  python scripts/experimentos/xgot.py                            # completa
"""
import argparse
import json
import re
import sys
import time

import numpy as np
import polars as pl

from dtcoach import ingest
from dtcoach import xdefensa as xd
from dtcoach import xgot as xg
from dtcoach.cli_historia import H_BP, _bloque, _hipotesis, _ruta, _rutas_bp, _slug, _tp
from dtcoach.config import Config
from dtcoach.inference import benjamini_hochberg

FAM_NOM = {"corner": "corners", "tiro_libre": "tiros libres", "lateral": "laterales", "todas": "todo el balón parado"}


def _bh(d: pl.DataFrame, alpha: float = 0.05) -> pl.DataFrame:
    """La misma regla que `demostracion.demostrar` sobre una tabla ya recolectada."""
    from dtcoach.demostracion import MIN_PARTIDOS
    prob = d.filter(pl.col("p").is_not_nan() & pl.col("no_demostrable").is_null())
    q, rech = benjamini_hochberg(prob["p"].to_numpy(), alpha)
    pocos = prob["pocos"].fill_null(False).to_numpy() | (prob["partidos_foco"].fill_null(99).to_numpy() < MIN_PARTIDOS)
    return prob.with_columns(pl.Series("q", q), pl.Series("veredicto", np.where(
        rech & ~pocos, "demostrado", np.where(rech, "pocos partidos", "no demostrado"))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/exp_mejoras.yaml")
    ap.add_argument("--muestra", type=int, default=0, help="humo: solo N partidos de la liga (todos los del foco)")
    ap.add_argument("--solo-verificar", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    cfg = Config.load(a.config)
    fc = cfg["futbol"]
    foco = cfg["foco"]["coach"]      # fijo en config/exp_mejoras.yaml: Guillermo Almada
    seed = cfg["seed"]
    out = cfg.ruta("reportes") / cfg["experimentos"]["salida"] / "xgot"
    out.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- 0. verificación
    r = xg.remates(ingest.scan_events(cfg.ruta("eventos_parquet")))
    disp = xg.disponibilidad(r)
    ver = ["## 0. ¿Viene la ubicación del remate en el plano de la portería?", "",
           f"- remates sin penales: {disp['remates']:,}; con end_location de 3 coordenadas: {disp['con_3_coordenadas']:,}",
           f"- a puerta (outcome ∈ Goal / Saved / Saved to Post): {disp['a_puerta']:,}; con z: {disp['a_puerta_con_z']:,} "
           f"(**{100 * disp['frac_a_puerta_con_z']:.1f} %**); de ellos con (y, z) dentro del marco: "
           f"{100 * disp['frac_con_z_en_marco']:.1f} %; valores distintos de z: {disp['z_distintos']:,}",
           f"- y (p1, p50, p99): {disp['y_p01_p50_p99']} · z: {disp['z_p01_p50_p99']} · remates fuera con z: {disp['fuera_con_z']:,}",
           f"- resultados: {disp['resultados']}",
           "- «a puerta» se deduce del `shot.outcome` de StatsBomb (no trae un booleano aparte).", "",
           f"**Verificación: {'PASA' if disp['ok'] else 'NO PASA'}** (≥ 90 % de los remates a puerta con z, ≥ 90 % dentro "
           "del marco y z con más de 10 valores distintos).", ""]
    if not disp["ok"] or a.solo_verificar:
        md = [f"# xGOT — portero y definición ({foco}) · ADR-v2-56", ""] + ver
        if not disp["ok"]:
            md += ["**SE DETIENE AQUÍ.** Sin la altura en el marco no se puede separar portero de definición, y no se "
                   "inventa con la (x, y) en la cancha."]
        (out / "XGOT.md").write_text("\n".join(md), encoding="utf-8")
        (out / "xgot.json").write_text(json.dumps({"disponibilidad": disp}, indent=1, ensure_ascii=False, default=float))
        print("\n".join(md))
        sys.exit(0 if disp["ok"] else 2)

    # ---------------------------------------------------------------- insumos (solo lectura)
    rb = _rutas_bp(cfg)
    faltan = [k for k in ("jugadas", "capa2", "cadena") if not rb[k].exists()]
    tabla = _ruta(cfg, fc["tabla"])
    if faltan or not tabla.exists():
        sys.exit(f"faltan insumos de la tabla de la liga ({faltan or 'tabla'}): corre antes `dtcoach tabla` "
                 "(este experimento no la reconstruye)")
    j, p2, D = pl.read_parquet(rb["jugadas"]), pl.read_parquet(rb["capa2"]), pl.read_parquet(rb["cadena"])
    M, tp = pl.read_parquet(tabla), _tp(cfg)
    if a.muestra:
        rng = np.random.default_rng(seed)
        mf = set(M.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique().to_list())
        otros = np.array(sorted(set(M["match_id"].unique().to_list()) - mf))
        keep = mf | set(rng.choice(otros, min(a.muestra, len(otros)), replace=False).tolist())
        f = pl.col("match_id").is_in(list(keep))
        r, j, p2, D, M, tp = r.filter(f), j.filter(f), p2.filter(f), D.filter(f), M.filter(f), tp.filter(f)

    # ---------------------------------------------------------------- 1. xGOT
    xg_previo = dict(zip(p2["id"].to_list(), p2["xg_full"].to_list()))
    rx, diag = xg.ajustar(r, xg_previo, fc["xd_folds"], fc["xd_lam"], seed)

    # ---------------------------------------------------------------- 2. cinco términos, exactos
    D5 = xg.partir(D, j, rx)
    err = xg.error_exactitud(D5)
    err4 = float((D5["port"] - D5["def"] - D5["portero"]).abs().max())

    # ---------------------------------------------------------------- 2b. cuánto dato hay por tipo de saque
    ap_ = (j.select("id_saque", "ids_remate").explode("ids_remate", empty_as_null=True).rename({"ids_remate": "id"})
           .filter(pl.col("id").is_not_null()).join(rx.select("id", "a_puerta", "gol"), on="id", how="left")
           .group_by("id_saque").agg(pl.col("a_puerta").fill_null(False).sum().alias("_ap")))
    Dn = D5.join(ap_, on="id_saque", how="left").with_columns(pl.col("_ap").fill_null(0))
    n_tipo = []
    for fam_, ts in {**xd.FAMILIAS, "todas": None}.items():
        x = Dn if ts is None else Dn.filter(pl.col("tipo").is_in(list(ts)))
        por = x.group_by("match_id", "team").agg(pl.len().alias("saques"), pl.col("_ap").sum().alias("ap"),
                                                 pl.col("g").sum().alias("goles"))
        n_tipo.append({"familia": fam_, "saques": x.height, "con_remate": int(x["s"].sum()),
                       "remates_a_puerta": int(x["_ap"].sum()), "goles": float(x["g"].sum()),
                       "equipo_partidos": por.height,
                       "a_puerta_por_equipo_partido": float(por["ap"].mean()) if por.height else 0.0,
                       "frac_equipo_partido_sin_a_puerta": float((por["ap"] == 0).mean()) if por.height else 1.0,
                       "goles_por_equipo_partido": float(por["goles"].mean()) if por.height else 0.0})

    # ---------------------------------------------------------------- 3. τ² por etapa (Prop. 16.4, varianza común)
    llaves = [c for c in ("match_id", "team", "coach", "rival", "coach_rival") if c in M.columns]
    M2 = M.select(llaves)
    for t in xg.metricas(D5, tp, xd.FAMILIAS):
        M2 = M2.join(t, on=["match_id", "team"], how="left")
    # un equipo-partido sin saques de esa familia no es un dato faltante: es 0 de 0. Con nulos, la razón de la
    # etapa entera salía NaN y la contracción «sin varianza» (corrida del 2026-10-02).
    nd = [c for c in M2.columns if c.endswith(("__n", "__d"))]
    nulos = {c: int(M2[c].null_count()) for c in nd if c.endswith("__n") and M2[c].null_count()}
    M2 = M2.with_columns(pl.col(nd).fill_null(0.0))
    mp = fc["min_partidos_era"]
    etapas, filas_csv = [], []
    for lado in ("xd", "xo"):
        for fam in (*xd.FAMILIAS, "todas"):
            for c in ("port", "def", "portero"):
                m = f"{lado}_{c}_{fam}"
                E = xd.por_etapa(M2, m, "propio", mp, "comun")
                if E.height == 0:
                    continue
                Ei = E.with_row_index("puesto", 1)
                fo = Ei.filter(pl.col("coach") == foco).to_dicts()
                etapas.append({"metrica": m, "lado": lado, "familia": fam, "termino": c, "etapas": E.height,
                               "mu": float(E["mu"][0]), "tau2": float(E["tau2"][0]), "p_Q": float(E["p_Q"][0]),
                               "foco": [{k: x[k] for k in ("team", "partidos", "theta", "contraido", "puesto")} for x in fo]})
                filas_csv.append(Ei.with_columns(pl.lit(m).alias("metrica")))
    if filas_csv:
        pl.concat(filas_csv, how="diagonal_relaxed").write_csv(out / "etapas.csv")

    # ---------------------------------------------------------------- 4a. la cadena con cinco términos (pruebas)
    nb = min(fc["n_boot"], 500)
    cad = xd.cadena(D5, tp, foco, nb, seed, componentes=("prev", "lej", "sup", "port", "def", "portero", "total"))

    # ---------------------------------------------------------------- 4b. H24–H26 otra vez
    cols = sorted({m for _, ms in H_BP.values() for m in ms})
    hres = _bloque(M, cols, foco, "propio", fc, seed)
    hip = _hipotesis(H_BP, hres)
    prev_bp = cfg.ruta("reportes") / "historia" / _slug(foco) / "balon_parado" / "balon_parado.json"
    hip_ent = json.loads(prev_bp.read_text()).get("hipotesis", {}) if prev_bp.exists() else {}

    # ---------------------------------------------------------------- 4c. el BH global con las pruebas nuevas
    dem = cfg.ruta("reportes") / "historia" / _slug(foco) / "demostracion" / "demostracion.csv"
    bh = None
    if dem.exists() and not a.muestra:
        d0 = pl.read_csv(dem, infer_schema_length=None)
        if "no_demostrable" not in d0.columns:
            d0 = d0.with_columns(pl.lit(None, pl.Utf8).alias("no_demostrable"))
        d0 = d0.with_columns(pl.col("p").cast(pl.Float64), pl.col("partidos_foco").cast(pl.Float64),
                             pl.col("no_demostrable").cast(pl.Utf8), pl.col("pocos").cast(pl.Boolean))
        pat = re.compile(r"cadena/(.+)/(foco_ataque|foco_defensa)/port$")
        es_port = d0["id"].map_elements(lambda s: bool(pat.search(s)), return_dtype=pl.Boolean)
        nuevas = []
        for fila in d0.filter(es_port).to_dicts():
            clave, g = pat.search(fila["id"]).groups()
            rr = cad.get(clave, {}).get(g, {})
            for c, nom in (("def", "definición"), ("portero", "portero")):
                t = rr.get(c, {})
                if np.isfinite(t.get("p", np.nan)):
                    nuevas.append(fila | {"id": fila["id"][:-4] + c, "p": t["p"], "efecto": t.get("valor"),
                                          "lo": t.get("lo"), "hi": t.get("hi"),
                                          "afirmacion": fila["afirmacion"].replace("portero y definición", nom)})
        d1 = pl.concat([d0.filter(~es_port), pl.DataFrame(nuevas, schema_overrides=d0.schema)], how="diagonal_relaxed") \
            if nuevas else d0.filter(~es_port)
        v0 = _bh(d0).select("id", "afirmacion", "p", pl.col("q").alias("q_antes"), pl.col("veredicto").alias("antes"))
        v1 = _bh(d1).select("id", pl.col("q").alias("q_despues"), pl.col("veredicto").alias("despues"))
        comun = v0.join(v1, on="id", how="inner")
        cambian = comun.filter(pl.col("antes") != pl.col("despues"))
        hrows = comun.filter(pl.col("id").str.contains(r"(^|/)H2[456]$"))
        bh = {"pruebas_antes": int(_bh(d0).height), "pruebas_despues": int(_bh(d1).height),
              "port_reemplazadas": int(es_port.sum()), "nuevas": len(nuevas),
              "demostradas_antes": int((v0["antes"] == "demostrado").sum()),
              "demostradas_despues": int((_bh(d1)["veredicto"] == "demostrado").sum()),
              "cambian": cambian.to_dicts(), "H24_H26": hrows.to_dicts(),
              "nuevas_veredicto": _bh(d1).filter(pl.col("id").str.contains(r"/(def|portero)$"))
              .select("id", "afirmacion", "p", "q", "veredicto").to_dicts()}

    res = {"foco": foco, "muestra": a.muestra or None, "disponibilidad": disp, "modelo": diag,
           "error_exactitud_5": err, "error_port_igual_def_mas_portero": err4, "saques": D5.height,
           "etapas": etapas, "n_por_tipo": n_tipo, "nulos_rellenados": nulos, "cadena": cad, "H24_H26": hip, "H24_H26_entrega": hip_ent, "bh": bh}
    (out / "xgot.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))

    md = [f"# xGOT — portero y definición ({foco}) · ADR-v2-56", "",
          "**EXPERIMENTO, no adoptado.** Matemática en `src/dtcoach/xgot.py` y 04 §16.7.",
          (f"**HUMO** con {a.muestra} partidos de la liga: no interpretar." if a.muestra else ""), ""] + ver
    md += ["## 1. El modelo xGOT (remates a puerta de toda la liga, fuera de muestra por partido)", "",
           f"- remates a puerta en el modelo: {diag['remates_a_puerta_modelo']:,}; goles: {diag['goles']:,} "
           f"({100 * diag['tasa_gol']:.1f} %)",
           f"- AUC fuera de muestra: **xGOT {diag['auc_xgot']:.3f}** contra xG previo {diag['auc_xg_previo']:.3f} "
           f"(en los mismos remates a puerta) · calibración media {diag['calibracion']:.3f}",
           "- **Esto NO es una mejora de modelo.** xGOT usa dónde terminó el balón (y, z en el marco), información "
           "POSTERIOR al remate; el xG previo solo la anterior. No son modelos competidores: el AUC más alto es lo esperable "
           "y lo único que dice es que la ubicación en el marco separa bien atajada de gol, que es lo que se necesita "
           "para partir portero de definición.",
           "- coeficientes (en desviaciones estándar): " + ", ".join(f"{c['rasgo']} {c['coef_de']:+.2f}"
                                                                    for c in diag["coeficientes"][:8]), "",
           "## 2. Cinco términos, exactos", "",
           f"Saques: {D5.height:,}. máx |prevención + alejamiento + supresión + definición + portero − (p κ − g)| = "
           f"**{err:.2e}**; máx |portero y definición − (definición + portero)| = {err4:.2e}.", "",
           "### Cuánto dato hay por tipo de saque", "",
           "| familia | saques | con remate | remates a puerta | goles | equipo-partidos | a puerta por equipo-partido | % equipo-partidos sin remate a puerta |",
           "|---|---|---|---|---|---|---|---|"] + [
           f"| {FAM_NOM[x['familia']]} | {x['saques']:,} | {x['con_remate']:,} | {x['remates_a_puerta']:,} | {x['goles']:.0f} | "
           f"{x['equipo_partidos']:,} | {x['a_puerta_por_equipo_partido']:.2f} | {100 * x['frac_equipo_partido_sin_a_puerta']:.0f} |"
           for x in n_tipo] + ["",
           (f"*Equipo-partidos sin saques de una familia ({sum(nulos.values()):,} celdas nulas) se cuentan como 0 de 0. "
            "En la primera corrida quedaban nulos y vaciaban la etapa entera: de ahí el «sin varianza».*" if nulos else ""), "",
           "## 3. ¿Hay variación real entre técnicos-club? (τ², Prop. 16.4, varianza común)", "",
           "| métrica | etapas | μ | τ² | p (Q de Cochran) | foco: θ → contraído (puesto) |", "|---|---|---|---|---|---|"]
    for e in etapas:
        nom = f"{'xD' if e['lado'] == 'xd' else 'xO'} · {xg.COMP5_NOMBRE.get(e['termino'], 'portero y definición (el de 4 términos)')} · {FAM_NOM[e['familia']]}"
        fo = "; ".join(f"{x['team']}: {x['theta']:+.2f} → {x['contraido']:+.2f} ({x['puesto']}/{e['etapas']})" for x in e["foco"]) or "—"
        if not np.isfinite(e["mu"]):
            md.append(f"| {nom} | {e['etapas']} | — | **no estimable** (menos de 2 etapas con varianza) | — | — |")
            continue
        md.append(f"| {nom} | {e['etapas']} | {e['mu']:+.3f} | {e['tau2']:.4f}{' **(= 0)**' if e['tau2'] == 0 else ''} | "
                  f"{e['p_Q']:.3g} | {fo} |")
    md += ["", "*Unidades: goles por 100 saques; xD del que defiende (positivo = evitó), xO del que saca. τ² = 0: no hay "
           "variación real detectable entre equipos y todos se contraen a μ: el puesto no significa nada. En xO, «portero» es el "
           "portero RIVAL (goles por encima de lo que valían a puerta) y «definición», la del propio equipo.*", "",
           "## 4. H24–H26 y las etiquetas", "",
           "H24 (prevención), H25 (supresión) y H26 (organización) **no usan el cuarto término**: sus métricas no cambian "
           "con la partición. Vueltas a correr:", "",
           "| hipótesis | p (esta corrida) | p (entrega) | etiqueta (esta corrida) | etiqueta (entrega) |", "|---|---|---|---|---|"]
    for h in H_BP:
        x, y = hip.get(h, {}), hip_ent.get(h, {})
        md.append(f"| {h} | {x.get('p', float('nan')):.4g} | {y.get('p', float('nan')):.4g} | {x.get('etiqueta', '—')} | "
                  f"{y.get('etiqueta', '—')} |")
    if bh:
        md += ["", f"**BH global de la demostración** con las {bh['port_reemplazadas']} pruebas de «portero y definición» de la "
               f"cadena reemplazadas por {bh['nuevas']} (definición y portero): {bh['pruebas_antes']} → {bh['pruebas_despues']} "
               f"pruebas; demostradas {bh['demostradas_antes']} → {bh['demostradas_despues']}.", ""]
        for x in bh["H24_H26"]:
            md.append(f"- `{x['id']}`: q {x['q_antes']:.4g} → {x['q_despues']:.4g} · {x['antes']} → **{x['despues']}**")
        md += ["", f"Afirmaciones que cambiarían de veredicto: **{len(bh['cambian'])}**."]
        for x in bh["cambian"]:
            md.append(f"- {x['afirmacion']} (`{x['id']}`): {x['antes']} → {x['despues']} (q {x['q_antes']:.4g} → {x['q_despues']:.4g})")
        md += ["", "Las pruebas nuevas (no entran a la entrega; así quedarían si se adoptara):", ""]
        for x in bh["nuevas_veredicto"]:
            md.append(f"- {x['afirmacion']}: p {x['p']:.3g}, q {x['q']:.3g} → {x['veredicto']}")
    else:
        md += ["", "*Sin `reports/historia/<foco>/demostracion/demostracion.csv` (o en humo): no se recalculó el BH global.*"]
    md += ["", f"Tiempo: {time.time() - t0:.0f} s."]
    (out / "XGOT.md").write_text("\n".join(x for x in md if x is not None), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
