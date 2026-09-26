"""
CLI de dtcoach. Un comando por paso del roadmap; ningún módulo importa cli.

    dtcoach aplanar          eventos .json.gz  -> data/interim/events/*.parquet
    dtcoach partidos         matches .json.gz  -> partidos + DT por partido
    dtcoach fase0            transiciones de TODA la liga con DT, rival y localía
    dtcoach cv-k             elige K fuera de muestra, por partido
    dtcoach mezcla --K k     ajusta la mezcla, responsabilidades, resumen y figuras
    dtcoach bondad --K k     KS de duración: K=1 contra la mezcla
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

from . import eras, ingest
from .config import Config
from .grid import StateSpace
from .possessions import build_transitions, coordinate_sanity


def _space(cfg: Config) -> StateSpace:
    p = cfg["pitch"]
    vc = cfg.get("voronoi") or {}
    if vc.get("activo"):              # ADR-v2-36: el nivel de presión ocupa el eje de "fase"
        from .voronoi import etiquetas_niveles
        fases = tuple(etiquetas_niveles(int(vc["L"])))
    else:
        fases = tuple(cfg["phase_order"])
    return StateSpace(nx=p["nx"], ny=p["ny"], length=p["length"], width=p["width"], phases=fases)


def _json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _trans(cfg) -> pl.DataFrame:
    p = cfg.ruta("transiciones")
    if not p.exists():
        sys.exit(f"No existe {p}. Corre `dtcoach fase0` primero.")
    return pl.read_parquet(p)


# ----------------------------------------------------------------------
def cmd_aplanar(a, cfg):
    from .aplanar import aplanar
    rep = aplanar(cfg.ruta("raw_events"), cfg.ruta("eventos_parquet"),
                  por_lote=a.por_lote, hilos=a.hilos, forzar=a.forzar)
    _json(rep, cfg.ruta("reportes") / "aplanar.json")
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in rep.items()}, indent=2))
    if rep["errores"]:
        print(f"\n{len(rep['errores'])} archivos con error (ver reports/aplanar.json). NO se ignoran:")
        for e in rep["errores"][:10]:
            print("  ", e)
        sys.exit(2)


def cmd_partidos(a, cfg):
    from .partidos import dt_por_partido, leer_partidos
    df = leer_partidos(cfg.ruta("raw_matches"))
    dtp = dt_por_partido(df)
    cfg.ruta("partidos").parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(cfg.ruta("partidos"))
    dtp.write_parquet(cfg.ruta("dt_partido"))
    sin_dt = dtp.filter(pl.col("coach_api").is_null()).height
    multi = dtp.filter(pl.col("n_managers") > 1).height
    print(f"partidos: {df.height} · temporadas: {df['season_id'].n_unique()} · "
          f"equipos: {dtp['team'].n_unique()}")
    print(f"filas equipo-partido sin DT en el API: {sin_dt} · con >1 DT: {multi}")
    print(df.group_by("season_id", "season_name").len().sort("season_id"))


def cmd_fase0(a, cfg):
    from .partidos import dt_por_partido, verificar_eras
    t0 = time.time()
    space = _space(cfg)
    lf = ingest.load(cfg.ruta("eventos_parquet"))
    print("construyendo transiciones de toda la liga...", flush=True)
    trans = build_transitions(lf, space, cfg)
    print(f"  {trans.height:,} transiciones en {time.time() - t0:.0f}s", flush=True)

    v2 = cfg.ruta("eras_dir").parent / (cfg.ruta("eras_dir").name + "_v2")
    if v2.exists():
        print(f"  [AVISO] existe {v2.name} pero el config usa {cfg.ruta('eras_dir').name}. "
              "Si ya lo corregiste, apunta rutas.eras_dir y rutas.exclusiones a la versión _v2.")
    partidos = pl.read_parquet(cfg.ruta("partidos"))
    dtp = dt_por_partido(partidos)
    md = partidos.select("match_id", "match_date")
    eras.check_dates_cover(trans, md)

    equipos = trans["team"].unique().drop_nulls().to_list()
    mc = eras.match_coach_table_multi(md, cfg.ruta("eras_dir"), equipos)

    # Interinatos absorbidos (bug de Cervantes/Jardine): el par (partido, club)
    # se queda SIN DT en las dos columnas. Las posesiones siguen en la liga.
    excl_p = cfg.ruta("exclusiones")
    n_excl = 0
    if excl_p.exists():
        pares = []
        for club in equipos:
            try:
                ids = eras.load_exclusions(excl_p, club)
            except KeyError as e:
                print(f"  [aviso] exclusiones ignoradas: {e}")
                break
            pares += [(i, club) for i in ids]
        if pares:
            ex = pl.DataFrame(pares, schema={"match_id": pl.Int64, "club": pl.Utf8}, orient="row")
            antes = mc.height
            mc = mc.join(ex, on=["match_id", "club"], how="anti")
            n_excl = antes - mc.height
    print(f"  pares (partido, club) excluidos por interinato: {n_excl}")

    trans = eras.attach_coach(trans, mc, club=None)
    trans = eras.attach_coach_faced(trans, mc)
    trans = trans.join(dtp.select("match_id", "team", "local", "rival"),
                       on=["match_id", "team"], how="left")

    verif = verificar_eras(mc, dtp)
    rep_dir = cfg.ruta("reportes")
    rep_dir.mkdir(parents=True, exist_ok=True)
    verif.write_csv(rep_dir / "verificacion_eras.csv")

    san = coordinate_sanity(trans, space)
    cob = (trans.filter(pl.col("coach").is_not_null())
           .group_by("team", "coach")
           .agg(pl.col("match_id").n_unique().alias("partidos"),
                pl.col("poss_uid").n_unique().alias("posesiones"))
           .sort("partidos", descending=True))
    cob.write_csv(rep_dir / "cobertura_eras.csv")
    frac_null = trans.select(pl.col("coach").is_null().mean()).item()
    # ADR-v2-14: cuantas posesiones de StatsBomb contienen mas de una secuencia,
    # y que absorciones ocurren a mitad de posesion.
    medio = trans.filter(pl.col("is_absorbing")).with_columns(
        pl.len().over("poss_uid").alias("_n_abs")
    ).filter(pl.col("_n_abs") > 1)
    abs_names = {space.absorbing_index(a): a for a in space.absorbing}
    rep_seg = {
        "posesiones_con_varias_secuencias": medio["poss_uid"].n_unique(),
        "absorciones_a_mitad_por_tipo": {
            abs_names[int(k)]: int(v) for k, v in
            trans.filter(pl.col("is_absorbing")).sort(["poss_uid", "event_index"])
            .with_columns(pl.int_range(pl.len()).over("poss_uid").alias("_i"),
                          pl.len().over("poss_uid").alias("_n"))
            .filter(pl.col("_i") < pl.col("_n") - 1)
            .group_by("to_state").len().iter_rows()
        },
    }
    rep = {
        "transiciones": trans.height,
        "posesiones": trans["poss_uid"].n_unique(),
        "secuencias": trans["seq_uid"].n_unique(),
        **rep_seg,
        "partidos": trans["match_id"].n_unique(),
        "equipos": len(equipos),
        "estados_transitorios": space.n_transient,
        "frac_filas_sin_dt": round(float(frac_null), 4),
        "discrepancias_eras_vs_api": verif.height,
        "coordinate_sanity": san,
        "segundos": round(time.time() - t0, 1),
    }
    _json(rep, rep_dir / "fase0.json")
    out = cfg.ruta("transiciones")
    out.parent.mkdir(parents=True, exist_ok=True)
    trans.write_parquet(out, compression="zstd")
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    print("\nTop eras por partidos (reports/cobertura_eras.csv):")
    print(cob.head(15))
    if not san["ok"]:
        print("\n[ALERTA] coordinate_sanity falló: la tasa de gol no crece hacia x=120.")
    if verif.height:
        print(f"\n[REVISAR] {verif.height} filas equipo-partido donde la era verificada y el "
              "`managers` del API no coinciden -> reports/verificacion_eras.csv")


def _datos(cfg):
    from .mezcla import DatosPosesion
    return DatosPosesion.desde_transiciones(_trans(cfg), _space(cfg))


def cmd_cv_k(a, cfg):
    from .graficas import curva_cv
    from .mezcla import cv_k
    mc = cfg["mezcla"]
    d = _datos(cfg)
    print(f"{d.n:,} posesiones · {int(d.largo.sum()):,} transiciones", flush=True)
    k_grid = a.k or mc["k_grid"]
    res, det = cv_k(d, k_grid, mc["lam"], mc["a0"], mc["folds"], cfg["seed"],
                    mc["n_init_cv"], mc["max_iter"], mc["tol"],
                    a.frac if a.frac is not None else mc["frac_partidos_cv"], paso_inicial=mc.get("paso_inicial", True), lam0=mc.get("lam0"))
    out = cfg.ruta("reportes") / "mezcla"
    out.mkdir(parents=True, exist_ok=True)
    res.write_csv(out / "cv_k.csv")
    det.write_csv(out / "cv_k_pliegues.csv")
    curva_cv(res, out / "cv_k.png")
    print(res)
    print("\nLa verosimilitud NO elige K sola (ADR-v2-10): mira la ganancia acumulada,"
          "\nel KS de `dtcoach bondad` y si los tipos son distintos y estables.")


def cmd_mezcla(a, cfg):
    from .graficas import mapa_tipos
    from .mezcla import ajustar, guardar_json, responsabilidades, resumen_tipos
    mc = cfg["mezcla"]
    d = _datos(cfg)
    t0 = time.time()
    m = ajustar(d, a.K, mc["lam"], mc["a0"], mc["n_init"], mc["max_iter"], mc["tol"],
                cfg["seed"], verbose=True, init=a.init, n_corto=mc.get("n_corto", 25), paso_inicial=mc.get("paso_inicial", True), lam0=mc.get("lam0"))
    r = responsabilidades(m, d)
    dirm = cfg.ruta("mezcla_dir")
    dirm.mkdir(parents=True, exist_ok=True)
    m.guardar(dirm / f"mezcla_K{a.K}.npz")
    resp = d.meta.with_columns(
        *[pl.Series(f"r_{k + 1}", r[:, k]) for k in range(a.K)],
        pl.Series("tipo", r.argmax(axis=1) + 1),
        pl.Series("largo", d.largo),
    )
    resp.write_parquet(dirm / f"responsabilidades_K{a.K}.parquet")
    res = resumen_tipos(m, d, r, t_min=cfg["bondad"]["t_min"])
    rep = cfg.ruta("reportes") / "mezcla"
    guardar_json(res, rep / f"tipos_K{a.K}.json")
    guardar_json(m.diagnostico, rep / f"estabilidad_K{a.K}.json")
    mapa_tipos(res, d.nx, d.ny, rep / f"tipos_K{a.K}_visitas.png")
    mapa_tipos(res, d.nx, d.ny, rep / f"tipos_K{a.K}_inicio.png",
               clave="inicio_por_zona", etiqueta="inicio")
    print(f"\najustado en {time.time() - t0:.0f}s")
    print(f"{'tipo':>4} {'pi':>6} {'E[T] mod':>9} {'E[T] emp':>9} {'P(rem)':>7} "
          f"{'xG/pos mod':>11} {'xG/pos emp':>11}")
    for t in res:
        print(f"{t['tipo']:>4} {t['pi']:6.3f} {t['E_T_modelo']:9.2f} {t['E_T_empirico']:9.2f} "
              f"{t['P_gol'] + t['P_remate_sin_gol']:7.3f} {t['xG_por_posesion_modelo']:11.4f} "
              f"{t['xG_por_posesion_empirico']:11.4f}")
    dg = m.diagnostico
    if a.K > 1:
        if dg.get("init") == "escalera":
            print(f"\nAjustado por escalera (ADR-v2-17). Confirma con: dtcoach reproducibilidad --K {a.K}")
        else:
            print(f"\nEstabilidad (ADR-v2-15): el mejor óptimo lo alcanzan {dg['reproducibilidad']} de "
                  f"{len(dg['arranques'])} arranques (|ΔJ| ≤ {dg['tol_J']:.0f})")
        print(f"   {'ΔJ':>9} {'it':>5} {'acuerdo':>8} {'máx|Δπ|':>8} {'máx|ΔE[T]|rel':>14} {'máx|ΔP(rem)|':>13}")
        for f in sorted(dg["arranques"], key=lambda f: f["delta_J"]):
            print(f"   {f['delta_J']:9.1f} {f['iteraciones']:5d} {f['acuerdo']:8.3f} {f['max_dif_pi']:8.3f} "
                  f"{f['max_dif_ET_rel']:14.3f} {f['max_dif_Premate']:13.3f}")
    print("\nNOMBRA LOS TIPOS SOLO DESPUÉS DE MIRAR LAS FIGURAS (ADR-v2-06).")


def cmd_repro(a, cfg):
    from .mezcla import guardar_json, reproducibilidad
    mc = cfg["mezcla"]
    d = _datos(cfg)
    r = reproducibilidad(d, a.K, mc["lam"], mc["a0"], a.semillas, mc["max_iter"], mc["tol"],
                         mc.get("n_corto", 25), paso_inicial=mc.get("paso_inicial", True), lam0=mc.get("lam0"))
    guardar_json(r, cfg.ruta("reportes") / "mezcla" / f"reproducibilidad_K{a.K}.json")
    print(f"K={a.K} · rango de J entre semillas = {r['rango_J']:.1f} ({r['rango_J_por_secuencia']:.2e} por secuencia) · "
          f"acuerdo suave mínimo = {r['acuerdo_suave_minimo']:.3f} (duro {r['acuerdo_minimo']:.3f}) · "
          f"reproducible: {r['reproducible']}")
    print(f"{'semilla':>8} {'ΔJ':>9} {'acuerdo':>8} {'máx|Δπ|':>8} {'máx|ΔE[T]|rel':>14}")
    for f in r["semillas"]:
        print(f"{f['semilla']:8d} {f['delta_J']:9.1f} {f['acuerdo']:8.3f} {f['max_dif_pi']:8.3f} "
              f"{f['max_dif_ET_rel']:14.3f}")
    print("\nCriterio (ADR-v2-35): rango de J por secuencia <= 1.08e-4 (= 50 / 461,454), acuerdo SUAVE >= 0.95 "
          "y cada tipo con al menos 1 % de las secuencias.")


def cmd_curva_k(a, cfg):
    """Estabilidad y ajuste para muchos K: la figura que justifica la elección de K.

    Escribe una fila por K en cuanto termina (si se corta, lo corrido no se
    pierde y se reanuda saltando los K ya hechos).
    """
    import time as _t

    from .graficas import curva_estabilidad
    from .mezcla import ajustar, bondad_largo, loglik_por_posesion, reproducibilidad
    mc, bc = cfg["mezcla"], cfg["bondad"]
    out = cfg.ruta("reportes") / "mezcla"
    out.mkdir(parents=True, exist_ok=True)
    etiqueta = f"{cfg['pitch']['nx']}x{cfg['pitch']['ny']}_{'p0' if mc.get('paso_inicial', True) else 'atado'}"
    csv = out / f"curva_k_{etiqueta}.csv"     # una curva por malla y variante: no se mezclan corridas
    CRITERIO = "v35b"                         # ADR-v2-35 (+ π mínimo): filas de otro criterio no se reutilizan
    if csv.exists():
        viejo = pl.read_csv(csv)
        if "criterio" not in viejo.columns or (viejo["criterio"] != CRITERIO).any():
            csv.rename(csv.with_name(csv.stem + "_criterio_anterior.csv"))
            print(f"{csv.name}: calculado con otro criterio de reproducibilidad; se archiva y se recalcula")
    hechos = set(pl.read_csv(csv)["K"].to_list()) if csv.exists() else set()
    d = _datos(cfg)
    for K in a.k:
        if K in hechos:
            print(f"K={K}: ya estaba en {csv.name}, se salta")
            continue
        t0 = _t.time()
        r = reproducibilidad(d, K, mc["lam"], mc["a0"], a.semillas, mc["max_iter"], mc["tol"],
                             mc.get("n_corto", 25), paso_inicial=mc.get("paso_inicial", True), lam0=mc.get("lam0"))
        m = ajustar(d, K, mc["lam"], mc["a0"], max_iter=mc["max_iter"], tol=mc["tol"],
                    seed=a.semillas[0], init="escalera", n_corto=mc.get("n_corto", 25), paso_inicial=mc.get("paso_inicial", True), lam0=mc.get("lam0"))
        b = bondad_largo(m, d, bc["t_min"], bc["kmax"])
        fila = pl.DataFrame([{
            "K": K, "rango_J": r["rango_J"], "acuerdo_minimo": r["acuerdo_suave_minimo"],
            "acuerdo_duro_minimo": r["acuerdo_minimo"],
            # J incluye el prior (crece con K): NO sirve entre K distintos.
            # Se compara la log-verosimilitud de los DATOS.
            "loglik_datos": float(loglik_por_posesion(m, d).sum()),
            "nats_por_transicion": float(loglik_por_posesion(m, d).sum()) / float(d.largo.sum()),
            "KS": b["KS"], "pi_minimo": float(m.pi.min()),
            "rango_J_por_secuencia": r["rango_J_por_secuencia"],
            "reproducible": r["reproducible"], "criterio": CRITERIO,
            "segundos": round(_t.time() - t0, 1),
        }])
        (pl.concat([pl.read_csv(csv), fila], how="diagonal_relaxed") if csv.exists() else fila).sort("K").write_csv(csv)
        print(f"K={K}: acuerdo={r['acuerdo_minimo']:.3f} rango_J={r['rango_J']:.1f} KS={b['KS']:.4f} "
              f"π_min={m.pi.min():.3f} ({_t.time() - t0:.0f}s)", flush=True)
    tabla = pl.read_csv(csv).sort("K")
    curva_estabilidad(tabla, out / f"curva_k_{etiqueta}.png")
    rep_ = tabla.filter(pl.col("reproducible"))["K"].to_list()
    print(f"\nK reproducibles ({etiqueta}): {rep_} · regla (fase 1 v3): el MAYOR K reproducible -> "
          f"{max(rep_) if rep_ else 'ninguno'}")
    with pl.Config(tbl_rows=60):
        print(tabla)


def _elo(cfg, forzar=False):
    from .elo import ajustar_elo
    ruta = cfg.ruta("elo")
    if ruta.exists() and not forzar:
        return pl.read_parquet(ruta)
    ec = cfg["elo"]
    r = ajustar_elo(pl.read_parquet(cfg.ruta("partidos")), ec["K_grid"], ec["h_grid"],
                    ec["inicial"], ec["burn_in"])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    r.previo.write_parquet(ruta)
    rep = cfg.ruta("reportes") / "fase2"
    rep.mkdir(parents=True, exist_ok=True)
    _json({"K": r.K, "h": r.h, "logperdida": r.logperdida,
           "calibracion": r.calibracion.with_columns(pl.col("bin").cast(pl.Utf8)).to_dicts()},
          rep / "elo.json")
    print(f"Elo: K={r.K:g}, h={r.h:g}, log-pérdida={r.logperdida:.4f}")
    print(r.calibracion)
    if r.K in (min(ec["K_grid"]), max(ec["K_grid"])) or r.h in (min(ec["h_grid"]), max(ec["h_grid"])):
        print("[AVISO] el óptimo cae en el borde de la rejilla: amplíala en config.elo")
    return r.previo


def cmd_elo(a, cfg):
    _elo(cfg, forzar=True)


def cmd_fase2(a, cfg):
    from .contexto import tabla_secuencias
    from .graficas import efectos_contexto, eficiencia, perfil_familias
    from .hipotesis import correr, tabla_md
    from .mezcla import Mezcla
    c2 = dict(cfg["fase2"])
    foco = a.foco or cfg["foco"]["coach"]
    c2["foco"] = foco
    K = c2["K"]
    fams = c2["familias"]
    elo = _elo(cfg)
    m = Mezcla.cargar(cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz")
    t = tabla_secuencias(_trans(cfg), _space(cfg), m, pl.read_parquet(cfg.ruta("partidos")), elo, cfg, foco)
    print(f"{t.height:,} secuencias · foco «{foco}»: {int(t['f'].sum()):,} de ataque, "
          f"{int(t['g'].sum()):,} de defensa, {t.filter(pl.col('f'))['match_id'].n_unique()} partidos", flush=True)
    res = correr(t, fams, c2, cfg["seed"])
    rep = cfg.ruta("reportes") / "fase2"
    rep.mkdir(parents=True, exist_ok=True)
    slug = foco.lower().replace(" ", "_")
    _json({k: v for k, v in res.items()}, rep / f"hipotesis_{slug}.json")
    perfil_familias(res, fams, foco, rep / f"familias_{slug}.png")
    efectos_contexto(res, fams, foco, rep / f"contexto_{slug}.png")
    eficiencia(res, fams, foco, rep / f"eficiencia_{slug}.png")
    md = [f"# Resultados de la fase 2 — {foco}", "",
          f"Secuencias del foco: {int(t['f'].sum()):,} (ataque), {int(t['g'].sum()):,} (defensa). "
          f"Partidos: {res['perfiles']['n_partidos_foco']} del foco, {res['perfiles']['n_partidos_liga']} de la liga.",
          f"Modelo convergió: {res['modelo']['convergio']}. "
          f"Columnas no estimables: {res['modelo']['columnas_no_estimables'] or 'ninguna'}. "
          + (f"⚠ {res['modelo']['aviso']}" if 'aviso' in res['modelo'] else ""),
          "", tabla_md(res), "", "## En la cancha", ""]
    md += [f"- {f}" for f in res["frases"]]
    (rep / f"RESULTADOS_{slug}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"columnas no estimables: {res['modelo']['columnas_no_estimables'] or 'ninguna'}")
    if "aviso" in res["modelo"]:
        print("⚠", res["modelo"]["aviso"])
    print(tabla_md(res))
    print()
    for f in res["frases"]:
        print("·", f)
    print(f"\nReporte: {rep / f'RESULTADOS_{slug}.md'}")


def _tabla_fase2(cfg, foco):
    from .contexto import tabla_secuencias
    from .mezcla import Mezcla
    K = cfg["fase2"]["K"]
    m = Mezcla.cargar(cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz")
    return tabla_secuencias(_trans(cfg), _space(cfg), m, pl.read_parquet(cfg.ruta("partidos")),
                            _elo(cfg), cfg, foco)


def cmd_fase3(a, cfg):
    from .fase3 import por_club
    from .graficas import comparar_clubes
    c2 = dict(cfg["fase2"])
    foco = a.foco or cfg["foco"]["coach"]
    t = _tabla_fase2(cfg, foco)
    clubes = (t.filter(pl.col("f")).group_by("team").agg(pl.col("match_id").n_unique().alias("p"))
               .filter(pl.col("p") >= a.min_partidos).sort("p", descending=True)["team"].to_list())
    print(f"{foco}: clubes con ≥ {a.min_partidos} partidos: {clubes}", flush=True)
    res = por_club(t, foco, clubes, c2["familias"], c2, cfg["seed"])
    rep = cfg.ruta("reportes") / "fase3"
    rep.mkdir(parents=True, exist_ok=True)
    slug = foco.lower().replace(" ", "_")
    _json(res, rep / f"por_club_{slug}.json")
    comparar_clubes(res, c2["familias"], foco, rep / f"por_club_{slug}.png")
    from .hipotesis import tabla_md
    md = [f"# ¿Es él o el plantel? — {foco}", ""]
    for club, r in res["clubes"].items():
        md += [f"## {club} ({r['partidos']} partidos)", ""]
        if "aviso_foco" in r["modelo"]:
            md += [f"⚠ {r['modelo']['aviso_foco']}", ""]
        md += [tabla_md(r), ""]
    for par, v in res.get("veredicto", {}).items():
        md += [f"## Veredicto {par} (H9–H12, pre-registradas)", ""]
        if "_aviso" in v:
            md += [f"⚠ {v['_aviso']}", ""]
        for h, x_ in v.items():
            if h.startswith("_"):
                continue
            md.append(f"**{h}**")
            for fam, x in x_.items():
                if isinstance(x, dict):
                    md.append(f"- {fam}: dif {100 * x['dif']:+.1f} pp, IC [{100 * x['lo']:+.1f}, {100 * x['hi']:+.1f}]"
                              f" → {'distinta' if x['excluye_0'] else 'no detectamos diferencia'}")
                else:
                    md.append(f"- {fam}: {'VIAJA (ambos clubes, mismo signo)' if x else 'no se detecta en ambos'}")
            md.append("")
    (rep / f"POR_CLUB_{slug}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


def cmd_atlas(a, cfg):
    """El atlas NO depende del foco (ajusta todas las eras); el foco solo se resalta.
    Se reutiliza reports/fase3/atlas.csv si existe (usa --rehacer para recalcular)."""
    from .fase3 import atlas
    from .graficas import mapa_atlas
    c2 = dict(cfg["fase2"])
    foco = a.foco or cfg["foco"]["coach"]
    rep = cfg.ruta("reportes") / "fase3"
    rep.mkdir(parents=True, exist_ok=True)
    csv = rep / "atlas.csv"
    if csv.exists() and not a.rehacer:
        tab = pl.read_csv(csv)
        print(f"atlas reutilizado de {csv.name} ({tab.height} eras); --rehacer para recalcular")
    else:
        t = _tabla_fase2(cfg, cfg["foco"]["coach"])
        tab = atlas(t, c2["familias"], c2, cfg["seed"], a.min_partidos)
        tab.write_csv(csv)
    slug = foco.lower().replace(" ", "_")
    mapa_atlas(tab, foco, c2["familias"], rep / f"atlas_{slug}.png")
    with pl.Config(tbl_rows=80, tbl_cols=8, fmt_str_lengths=24):
        print(tab.select("coach", "team", "partidos", "norma_ataque_pp", "norma_defensa_pp", "p_H1", "p_H2"))
    for col, nombre in (("norma_ataque_pp", "ofensiva"), ("norma_defensa_pp", "defensiva")):
        orden = tab.sort(col, descending=True).with_row_index("rango")
        for r in orden.filter(pl.col("coach") == foco).iter_rows(named=True):
            print(f"{foco} ({r['team']}): puesto {r['rango'] + 1} de {tab.height} en separación {nombre} "
                  f"({r[col]:.1f} pp); mediana de la liga: {tab[col].median():.1f} pp")
    if tab.filter(pl.col("coach") == foco).height == 0:
        print(f"{foco} no tiene eras con ≥ {a.min_partidos} partidos en el atlas.")


def _equipo_partido(cfg) -> pl.DataFrame:
    """Una fila por equipo-partido: DT, localía, Elo, temporada y fecha."""
    tr = pl.read_parquet(cfg.ruta("transiciones"), columns=["match_id", "team", "coach", "local"])
    tp = tr.group_by("match_id", "team").agg(pl.col("coach").drop_nulls().first(), pl.col("local").first())
    elo = _elo(cfg).with_columns(((pl.col("elo") - pl.col("elo_rival")) / 100).alias("elo_dif"))
    part = pl.read_parquet(cfg.ruta("partidos")).select("match_id", "season_id", "match_date")
    return (tp.join(elo.select("match_id", "team", "elo_dif"), on=["match_id", "team"], how="left")
              .join(part, on="match_id", how="left")
              .with_columns(pl.col("local").fill_null(False), pl.col("elo_dif").fill_null(0.0)))


def cmd_decisiones(a, cfg):
    from .decisiones import correr_decisiones, leer_eventos
    from .graficas import figura_decisiones
    c2 = dict(cfg["fase2"])
    foco = a.foco or cfg["foco"]["coach"]
    print("leyendo cambios, reacomodos y onces...", flush=True)
    ev = leer_eventos(ingest.scan_events(cfg.ruta("eventos_parquet")))
    res = correr_decisiones(ev, _equipo_partido(cfg), foco, c2, cfg["seed"])
    rep = cfg.ruta("reportes") / "fase3"
    rep.mkdir(parents=True, exist_ok=True)
    slug = foco.lower().replace(" ", "_")
    _json({k: v for k, v in res.items() if not k.startswith("_")}, rep / f"decisiones_{slug}.json")
    figura_decisiones(res, foco, rep / f"decisiones_{slug}.png")
    H = res["hipotesis"]
    L = [f"# Decisiones desde la banca — {foco}", "",
         f"Equipo-minuto: {res['n']['equipo_minuto']:,} · sustituciones: {res['n']['sustituciones']:,} "
         f"({res['n']['sustituciones_foco']} de {foco}) · equipo-partido: {res['n']['equipo_partido']:,}", "",
         "| id | qué se prueba | resultado | p | q (BH) | evidencia |", "|---|---|---|---|---|---|"]
    for k, h in H.items():
        est = f"W={h['W']:.1f} (gl {h['gl']})" if "W" in h else \
              f"{h['foco']:.3f} vs {h['liga']:.3f} (dif {h['dif']:+.3f} [{h['lo']:+.3f}, {h['hi']:+.3f}])"
        L.append(f"| {k} | {h['nombre']} | {est} | {h['p']:.4f} | {h['q']:.4f} | {h['etiqueta']} |")
    L += ["", "## En la cancha", ""]
    for marc, v in res["primer_cambio"].items():
        L.append(f"- **Primer cambio del 2º tiempo, {marc}:** minuto {v['minuto_foco']:.1f} contra "
                 f"{v['minuto_liga']:.1f} de la liga ({v['dif']:+.1f} min, IC [{v['lo']:+.1f}, {v['hi']:+.1f}]).")
    tipos = ["defensivo", "mismo puesto", "ofensivo"]
    for marc, v in res["tipo_cambio"].items():
        L.append(f"- **Tipo de cambio, {marc}:** " + "; ".join(
            f"{t} {100 * v['P_foco'][i]:.0f} % (liga {100 * v['P_liga'][i]:.0f} %, "
            f"dif {100 * v['dif'][i]:+.1f} pp [{100 * v['lo'][i]:+.1f}, {100 * v['hi'][i]:+.1f}])"
            for i, t in enumerate(tipos)))
    por_club: dict = {}
    for r in res["formaciones_foco"]:
        por_club.setdefault(r["team"], []).append(r)
    for club, fs in por_club.items():
        tot = sum(r["len"] for r in fs)
        L.append(f"- **Formaciones iniciales en {club}** ({tot} partidos, {len(fs)} sistemas): " + ", ".join(
            f"{r['tactics_formation']} ({r['len']}, {100 * r['len'] / tot:.0f} %)" for r in fs[:5]))
    (rep / f"DECISIONES_{slug}.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


def cmd_simulador(a, cfg):
    from .graficas import figura_escenarios, figura_xpts
    from .hipotesis import modelo_contexto
    from .perfil import perfiles
    from .simulador import calibracion_contexto, escenarios, resumen_xpts, xpts_por_equipo_partido
    c2 = dict(cfg["fase2"])
    foco = a.foco or cfg["foco"]["coach"]
    fams = c2["familias"]
    K = len(fams)
    rep = cfg.ruta("reportes") / "fase3"
    rep.mkdir(parents=True, exist_ok=True)
    slug = foco.lower().replace(" ", "_")
    tp = _equipo_partido(cfg)
    print("puntos esperados (Poisson-binomial exacta)...", flush=True)
    x = xpts_por_equipo_partido(ingest.scan_events(cfg.ruta("eventos_parquet")), tp)
    x = x.join(tp.select("match_id", "team", "match_date"), on=["match_id", "team"], how="left")
    rx = resumen_xpts(x, foco)
    figura_xpts(x.filter(pl.col("coach") == foco), foco, rep / f"xpts_{slug}.png")
    print("escenarios y calibración del modelo de contexto...", flush=True)
    t = _tabla_fase2(cfg, foco)
    m, D, _ = modelo_contexto(t, K, c2.get("ref", 1))
    pf = perfiles(t, K, n_boot=c2["n_boot"], seed=cfg["seed"])
    xg_f, xg_l = pf["ataque"]["foco"][K:2 * K], pf["ataque"]["liga"][K:2 * K]
    se_f = [(h - l) / 3.92 for l, h in zip(pf["ataque"]["lo"][K:2 * K], pf["ataque"]["hi"][K:2 * K])]
    esc = escenarios(t, m, D, xg_f, xg_l, fams, m.simular(200, cfg["seed"]), se_f, cfg["seed"])
    esc.write_csv(rep / f"escenarios_{slug}.csv")
    figura_escenarios(esc, foco, rep / f"escenarios_{slug}.png")
    cal = calibracion_contexto(t, m, D, K)
    cal.write_csv(rep / f"calibracion_contexto_{slug}.csv")
    _json({"xpts": rx, "calibracion_error_tv_medio": float(cal["error_tv"].mean()) if cal.height else None,
           "calibracion_ruido_tv_medio": float(cal["ruido_tv"].mean()) if cal.height else None},
          rep / f"simulador_{slug}.json")
    v, f_ = rx["validacion"], rx["foco"]
    L = [f"# Simulador — {foco} (exploratorio)", "",
         "## Puntos contra puntos esperados", "",
         f"Validación en toda la liga: {v['puntos_totales']:,} puntos reales contra {v['xPts_totales']:,.0f} "
         f"esperados (error relativo {100 * v['error_relativo']:.2f} %).", "",
         f"{foco}: {f_['puntos']} puntos en {f_['partidos']} partidos contra {f_['xPts']:.1f} esperados "
         f"({f_['dif']:+.1f} puntos, z = {f_['z']:+.2f}, p = {f_['p']:.3f}). "
         f"Por partido: {f_['puntos_por_partido']:.2f} reales contra {f_['xPts_por_partido']:.2f} esperados.", "",
         "## Calibración del modelo de contexto (celdas con ≥ 300 secuencias del foco)", "",
         (f"Error medio (distancia de variación total, predicha contra observada): "
          f"{100 * float(cal['error_tv'].mean()):.2f} pp en {cal.height} celdas; el ruido de muestreo esperado "
          f"con esos tamaños de celda es {100 * float(cal['ruido_tv'].mean()):.2f} pp "
          f"(cociente {float(cal['error_tv'].mean() / cal['ruido_tv'].mean()):.2f}: cerca de 1 = el error es ruido)."
          if cal.height else "Sin celdas suficientes."),
         "", "## Escenarios (xG por secuencia, foco contra liga en el mismo escenario)", ""]
    for r in esc.sort("dif_xG_sec").iter_rows(named=True):
        L.append(f"- {r['marcador']}, min {r['minuto']}, {'local' if r['local'] else 'visitante'}, {r['rival']}: "
                 f"{r['xG_sec_foco']:.4f} contra {r['xG_sec_liga']:.4f} ({r['dif_xG_sec']:+.4f} "
                 f"[{r['lo']:+.4f}, {r['hi']:+.4f}])")
    (rep / f"SIMULADOR_{slug}.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:12]))
    print(f"... escenarios completos en {rep / f'SIMULADOR_{slug}.md'}")


def cmd_mallado(a, cfg):
    """Calibra el mallado: validación cruzada en densidad + agregación contigua (ADR-v2-32)."""
    import re as _re
    from .graficas import figura_mallado
    from .mallado import conteos_por_pliegue, elegir_malla, evaluar_agregacion, evaluar_rectangular
    mcfg = cfg["mallado"]
    lf = ingest.load(cfg.ruta("eventos_parquet"))
    res = {}
    for nombre in (a.candidatos or mcfg["candidatos"]):
        nx, ny = (int(x) for x in nombre.split("x"))
        C, _ = conteos_por_pliegue(lf, cfg, nx, ny, mcfg["folds"], cfg["seed"])
        res[nombre] = {**evaluar_rectangular(C, mcfg["lam_grid"]), "zonas": nx * ny}
        print(f"  {nombre:>6}: {res[nombre]['score']:+.5f} nats/transición (λ={res[nombre]['lam']:g}, "
              f"parámetros/obs {res[nombre]['params_por_obs']:.3f})", flush=True)
    elegida, tab = elegir_malla(res)
    fx, fy = mcfg["fina"]
    print(f"  agregación contigua desde {fx}×{fy}...", flush=True)
    Cf, _ = conteos_por_pliegue(lf, cfg, fx, fy, mcfg["folds"], cfg["seed"])
    ag = evaluar_agregacion(Cf, fx, fy, R_min=mcfg.get("R_min", 4), lam=mcfg.get("lam_agregacion", 10.0))
    rep = cfg.ruta("reportes") / "fase1"
    rep.mkdir(parents=True, exist_ok=True)
    tab.write_csv(rep / "mallado_rectangular.csv")
    ag["tabla"].write_csv(rep / "mallado_agregacion.csv")
    figura_mallado(tab, ag, elegida, rep / "mallado.png")
    mejor_ag = float(ag["tabla"]["score"].max())
    mejor_rect = float(tab["score"].max())
    with pl.Config(tbl_rows=30):
        print(tab)
    print(f"\nMalla elegida (1-EE pareado hacia menos zonas): {elegida}")
    print(f"Agregación contigua: óptimo en {ag['R_opt']} regiones, puntaje {mejor_ag:+.5f} "
          f"(mejor rectangular {mejor_rect:+.5f}; diferencia {mejor_ag - mejor_rect:+.5f}).")
    _json({"elegida": elegida, "rectangular": tab.to_dicts(), "agregacion_R_opt": ag["R_opt"],
           "agregacion_mejor": mejor_ag, "rectangular_mejor": mejor_rect,
           "etiquetas_agregacion": ag["etiquetas"].tolist()}, rep / "mallado.json")
    if a.aplicar:
        nx, ny = (int(x) for x in elegida.split("x"))
        ruta = cfg.archivo
        txt = ruta.read_text()
        txt = _re.sub(r"pitch:\s*\{nx:\s*\d+,\s*ny:\s*\d+", f"pitch: {{nx: {nx}, ny: {ny}", txt)
        ruta.write_text(txt)
        print(f"config actualizado: pitch nx={nx}, ny={ny}. Siguiente: dtcoach fase0 (rehace transiciones).")


def cmd_markov(a, cfg):
    """Propiedades formales y métricas de la cadena, de la liga y por tipo (ADR-v2-31)."""
    from .estimate import count_matrix, shrink
    from .graficas import mapas_zona
    from .markov import (espectro, irreversibilidad, llegada, llegada_empirica, memoria, memoria_cv,
                         tripletas, verificar)
    from .mezcla import DatosPosesion, Mezcla, ajustar, responsabilidades
    mc = cfg["mezcla"]
    trans, space = _trans(cfg), _space(cfg)
    nt, ns = space.n_transient, space.n_states
    uid = "seq_uid" if "seq_uid" in trans.columns else "poss_uid"
    d = DatosPosesion.desde_transiciones(trans, space)
    C = count_matrix(trans, space)
    inicios = np.bincount(d.inicio, minlength=nt)
    P = shrink(C, np.full((nt, ns), 1.0 / ns), 1.0)
    mu = (inicios + 1.0 / nt) / (inicios.sum() + 1.0)
    cx = np.repeat(space.zone_centroids()[:, 0], len(space.phases))
    cy = np.repeat(space.zone_centroids()[:, 1], len(space.phases))
    objetivos = {"último tercio": cx >= 80, "frente al área": (cx >= 102) & (cy >= 18) & (cy <= 62)}
    out = {"liga": {"verificacion": verificar(P, mu, C, inicios)}}
    e = espectro(P)
    out["liga"]["espectro"] = {"rho": e["rho"], "vida_media_acciones": e["vida_media_acciones"]}
    out["liga"]["irreversibilidad"] = irreversibilidad(C, cx)
    m1 = ajustar(d, 1, mc["lam"], mc["a0"], paso_inicial=True, lam0=mc.get("lam0"))
    out["liga"]["llegada"] = {}
    for nombre, A in objetivos.items():
        if not A.any():
            continue
        mod = llegada(m1.P[0], m1.mu[0], A, m1.P0[0])
        emp = llegada_empirica(trans, A, uid)
        out["liga"]["llegada"][nombre] = {"modelo": {k: v for k, v in mod.items() if k != "h_por_estado"},
                                          "empirico": emp}
    K = a.K or cfg.get("fase2", {}).get("K", 3)
    ruta_m = cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz"
    tr3 = tripletas(trans, uid)
    R = None
    mapas, titulos = [e["yaglom"].reshape(-1, len(space.phases)).sum(1).tolist()], ["liga"]
    m = Mezcla.cargar(ruta_m) if ruta_m.exists() else None
    if m is not None and m.mu.shape[1] != nt:
        print(f"[aviso] {ruta_m.name} tiene {m.mu.shape[1]} estados y la malla actual {nt}: es de otra malla; "
              "se omiten las métricas por tipo (corre `dtcoach mezcla --K {K}` con la malla actual)")
        m = None
    if m is not None:
        R = responsabilidades(m, d)
        fams = cfg.get("fase2", {}).get("familias", [])
        if len(fams) != m.K:            # nombres de otro K: no se usan (no se inventan correspondencias)
            fams = [f"Tipo {k + 1}" for k in range(m.K)]
        out["tipos"] = []
        for k in range(m.K):
            Ck = np.asarray(d.S.T @ R[:, k]).reshape(nt, ns)
            ek = espectro(m.P[k])
            fila = {"tipo": k + 1, "nombre": fams[k] if k < len(fams) else f"tipo {k + 1}",
                    "rho": ek["rho"], "vida_media_acciones": ek["vida_media_acciones"],
                    "irreversibilidad": irreversibilidad(Ck, cx), "llegada": {}}
            for nombre, A in objetivos.items():
                if A.any():
                    q = llegada(m.P[k], m.mu[k], A, m.P0e(k))
                    fila["llegada"][nombre] = {"P_llega": q["P_llega"], "E_acciones_si_llega": q["E_acciones_si_llega"]}
            out["tipos"].append(fila)
            mapas.append(ek["yaglom"].reshape(-1, len(space.phases)).sum(1).tolist())
            titulos.append(fila["nombre"])
        # llegada a nivel MEZCLA: Σ π_k P_k y E ponderado por π_k P_k (comparable con lo observado)
        out["liga"]["llegada_mezcla"] = {}
        for nombre in objetivos:
            if not objetivos[nombre].any():
                continue
            Pk = np.array([t_["llegada"][nombre]["P_llega"] for t_ in out["tipos"]])
            Ek = np.array([t_["llegada"][nombre]["E_acciones_si_llega"] for t_ in out["tipos"]])
            Pm = float(m.pi @ Pk)
            out["liga"]["llegada_mezcla"][nombre] = {"P_llega": Pm, "E_acciones_si_llega": float((m.pi * Pk) @ Ek / Pm)}
    else:
        print(f"[aviso] no existe {ruta_m.name}: se omiten las métricas por tipo")
    print("memoria fuera de muestra (orden 2 y primer toque)...", flush=True)
    out["memoria_cv"] = memoria_cv(tr3, nt, ns, R, folds=mc["folds"], seed=cfg["seed"])
    mm_plugin = memoria(tr3, nt, ns, None)          # solo como diagnóstico del sesgo
    out["memoria_plugin_sesgada"] = {k: mm_plugin[k] for k in ("H_siguiente_dado_actual", "I_orden2", "I_primer_toque")}
    rep = cfg.ruta("reportes") / "fase1"
    rep.mkdir(parents=True, exist_ok=True)
    tag = f"{space.nx}x{space.ny}"
    _json(out, rep / f"markov_{tag}.json")
    mapas_zona(mapas, titulos, space.nx, space.ny, rep / f"yaglom_{tag}.png",
               "Distribución cuasi-estacionaria (Yaglom): dónde vive el balón en las secuencias largas")
    v, ir, mc_ = out["liga"]["verificacion"], out["liga"]["irreversibilidad"], out["memoria_cv"]
    L = ["# Propiedades de la cadena (fase 1)", "",
         f"Malla {space.nx}×{space.ny} · {nt} estados · K = {m.K if m is not None else '—'} · paso inicial: "
         f"{mc.get('paso_inicial', True)}", "",
         "## Verificación formal (cadena reiniciada)", "",
         f"- ρ(Q) = {v['rho_Q']:.4f} → toda secuencia termina con probabilidad 1: **{v['termina_cs']}**",
         f"- irreducible (grafo de lo observado): **{v['irreducible']}** ({v['componentes_fuertes']} componente(s) fuerte(s))",
         f"- aperiódica (hay P_ii > 0 observados): **{v['aperiodica']}**",
         f"- estacionaria de la reiniciada = visitas μᵀN normalizadas: error máx. {v['estacionaria_igual_a_visitas_err']:.2e}",
         f"- brecha espectral de la reiniciada: {v['brecha_espectral_reiniciada']:.4f}", "",
         "## Espectro y vida media", "",
         f"- liga: ρ = {out['liga']['espectro']['rho']:.4f}, vida media = {out['liga']['espectro']['vida_media_acciones']:.2f} acciones",
         "", "## Irreversibilidad (direccionalidad del juego)", "",
         f"- liga: σ = {ir['sigma_nats_por_transicion']:.4f} nats/transición · avance neto "
         f"{ir['avance_neto_metros_por_transicion']:+.2f} m/transición · G² balance detallado = {ir['G2_balance_detallado']:,.0f} (gl {ir['gl']})",
         "", "## Llegada (análisis de primer paso): observado · K = 1 · mezcla", ""]
    for nombre, x in out["liga"]["llegada"].items():
        mz = out["liga"].get("llegada_mezcla", {}).get(nombre)
        L.append(f"- {nombre}: P(llega) obs. {x['empirico']['P_llega']:.3f} · K=1 {x['modelo']['P_llega']:.3f}"
                 + (f" · mezcla {mz['P_llega']:.3f}" if mz else "")
                 + f"; acciones si llega obs. {x['empirico']['E_acciones_si_llega']:.2f} · K=1 "
                 f"{x['modelo']['E_acciones_si_llega']:.2f}" + (f" · mezcla {mz['E_acciones_si_llega']:.2f}" if mz else ""))
    for t in out.get("tipos", []):
        ll = "; ".join(f"{n}: P {q['P_llega']:.3f}, {q['E_acciones_si_llega']:.2f} acc."
                       for n, q in t["llegada"].items())
        L.append(f"- **{t['nombre']}**: vida media {t['vida_media_acciones']:.2f} acc. · σ "
                 f"{t['irreversibilidad']['sigma_nats_por_transicion']:.4f} · avance "
                 f"{t['irreversibilidad']['avance_neto_metros_por_transicion']:+.2f} m · {ll}")
    L += ["", "## Memoria fuera de muestra (ganancia sobre orden 1, nats por transición, pliegues por partido)", ""]
    for clave, nombre in (("orden2", "orden 2"), ("primer_toque", "primer toque")):
        g = mc_[f"{clave}_todas"]
        L.append(f"- {nombre}: {g['ganancia']:+.5f} ± {g['se']:.5f} (λ₂ = {g['lam2']:g})"
                 + (f" · dado el tipo: {mc_[f'{clave}_dado_tipo']['ganancia']:+.5f} ± {mc_[f'{clave}_dado_tipo']['se']:.5f}"
                    f" → **{100 * mc_[f'{clave}_explicada_por_tipos']:.1f} % la explican los tipos**"
                    if f"{clave}_dado_tipo" in mc_ else ""))
    pl_ = out["memoria_plugin_sesgada"]
    L += [f"- (diagnóstico) información mutua plug-in, SESGADA con esta malla: orden 2 {pl_['I_orden2']:.4f}, "
          f"primer toque {pl_['I_primer_toque']:.4f}, H(X_t+1|X_t) {pl_['H_siguiente_dado_actual']:.4f}"]
    (rep / f"MARKOV_{tag}.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


def cmd_comparar_paso(a, cfg):
    """¿Paso inicial propio o cadena atada? Validación cruzada PAREADA + KS (ADR-v2-29, regla pre-registrada)."""
    import re as _re
    from .mezcla import ajustar, bondad_largo, cv_k
    mc = cfg["mezcla"]
    d = _datos(cfg)
    dets, ks = {}, {}
    for paso in (False, True):
        _, det = cv_k(d, [a.K], mc["lam"], mc["a0"], mc["folds"], cfg["seed"], mc["n_init_cv"], mc["max_iter"],
                      mc["tol"], a.frac if a.frac is not None else mc["frac_partidos_cv"], verbose=False,
                      paso_inicial=paso, lam0=mc.get("lam0"))
        dets[paso] = det.sort("pliegue")["nats_por_transicion"].to_numpy()
        m = ajustar(d, a.K, mc["lam"], mc["a0"], max_iter=mc["max_iter"], tol=mc["tol"], seed=cfg["seed"],
                    n_corto=mc.get("n_corto", 25), paso_inicial=paso, lam0=mc.get("lam0"))
        ks[paso] = bondad_largo(m, d, 1, cfg["bondad"]["kmax"])
        print(f"  paso_inicial={paso}: {dets[paso].mean():+.5f} nats/transición · KS {ks[paso]['KS']:.4f} · "
              f"P(T>1) modelo {ks[paso]['supervivencia'][0]['modelo']:.4f} (obs. {ks[paso]['supervivencia'][0]['empirica']:.4f})",
              flush=True)
    dif = dets[True] - dets[False]
    se = float(dif.std(ddof=1) / np.sqrt(len(dif)))
    t = float(dif.mean() / se) if se > 0 else float("inf")
    adoptar = bool(t > 2 and ks[True]["KS"] < ks[False]["KS"])
    print(f"\nmejora pareada: {dif.mean():+.5f} nats/transición (EE {se:.5f}, t = {t:.1f}) · "
          f"KS {ks[False]['KS']:.4f} -> {ks[True]['KS']:.4f}")
    print(f"Regla (t > 2 y KS menor): {'ADOPTAR paso inicial' if adoptar else 'quedarse con la cadena atada'}")
    rep = cfg.ruta("reportes") / "fase1"
    rep.mkdir(parents=True, exist_ok=True)
    _json({"K": a.K, "mejora": float(dif.mean()), "se": se, "t": t, "KS_atado": ks[False]["KS"],
           "KS_paso": ks[True]["KS"], "adoptar": adoptar,
           "supervivencia_atado": ks[False]["supervivencia"][:10], "supervivencia_paso": ks[True]["supervivencia"][:10]},
          rep / f"comparar_paso_K{a.K}.json")
    if a.aplicar:
        ruta = cfg.archivo
        txt = _re.sub(r"(\n\s*paso_inicial:\s*)(true|false)", lambda m_: m_.group(1) + ("true" if adoptar else "false"),
                      ruta.read_text(), count=1)
        ruta.write_text(txt)
        print(f"config actualizado: mezcla.paso_inicial = {str(adoptar).lower()}")


def cmd_bondad(a, cfg):
    from .mezcla import Mezcla, ajustar, bondad_largo, guardar_json
    mc, bc = cfg["mezcla"], cfg["bondad"]
    d = _datos(cfg)
    salida = []
    for K in a.K:
        p = cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz"
        m = Mezcla.cargar(p) if p.exists() else ajustar(
            d, K, mc["lam"], mc["a0"], mc["n_init"], mc["max_iter"], mc["tol"], cfg["seed"], paso_inicial=mc.get("paso_inicial", True), lam0=mc.get("lam0"))
        b = bondad_largo(m, d, bc["t_min"], bc["kmax"], a.n_boot, cfg["seed"])
        salida.append(b)
        extra = f" · p_conservador={b['p_conservador']:.4f}" if "p_conservador" in b else ""
        print(f"K={K}: KS={b['KS']:.5f} · E[T] modelo={b['E_T_modelo']:.3f} "
              f"vs empírico={b['E_T_empirico']:.3f}{extra}")
    guardar_json(salida, cfg.ruta("reportes") / "mezcla" / "bondad_largo.json")
    print("\nSupervivencia P(T > t) empírica vs modelo (primeros t):")
    print(f"{'t':>3} {'empírica':>9} " + " ".join(f"{'K=' + str(b['K']):>9}" for b in salida))
    for i in range(min(20, len(salida[0]["supervivencia"]))):
        fila = salida[0]["supervivencia"][i]
        print(f"{fila['t']:>3} {fila['empirica']:9.4f} " +
              " ".join(f"{b['supervivencia'][i]['modelo']:9.4f}" for b in salida))


# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# Experimento 360: estado zona × nivel de presión (ADR-v2-36)
# ----------------------------------------------------------------------
def cmd_voronoi(a, cfg):
    """Rasgos de cada freeze frame (celda de Voronoi local, rival más cercano) -> parquet."""
    from .voronoi import rasgos_liga, unir_eventos
    vc, p = cfg["voronoi"], cfg["pitch"]
    t0 = time.time()
    kw = {"R": vc["R"], "r_presion": vc["r_presion"], "min_visible": vc["min_visible"],
          "largo": p["length"], "ancho": p["width"]}
    r = rasgos_liga(cfg.ruta("raw_frames"), kw, a.hilos or vc.get("hilos", 4))
    n_frames = r.height
    r = unir_eventos(r, ingest.scan_events(cfg.ruta("eventos_parquet")))   # crudo: basta id, index, location
    destino = _ruta(cfg, vc["rasgos"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    r.write_parquet(destino)
    d = r["d_actor_evento"].drop_nulls()
    def q(c, x):
        v = r[c].fill_nan(None).drop_nulls()
        return float(v.quantile(x)) if v.len() else float("nan")
    res = {"frames": n_frames, "unidos_a_eventos": r.height, "partidos": int(r["match_id"].n_unique()),
           "d_actor_evento_mediana_m": float(d.median()) if d.len() else None,
           "frac_d_actor_evento_mayor_2m": float((d > 2).mean()) if d.len() else None,
           "frac_sin_rival_o_actor": float(r["d_rival"].fill_nan(None).is_null().mean()),
           "frac_area_nan": float(r["area_local"].is_nan().mean()),
           "d_rival_p10_p50_p90": [q("d_rival", x) for x in (.1, .5, .9)],
           "area_local_p10_p50_p90": [q("area_local", x) for x in (.1, .5, .9)],
           "segundos": round(time.time() - t0)}
    _json(res, cfg.ruta("reportes") / "fase1" / "voronoi_rasgos.json")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if res["d_actor_evento_mediana_m"] is not None and res["d_actor_evento_mediana_m"] > 2:
        print("[ALERTA] el actor del frame no coincide con la ubicación del evento: ¿orientación distinta? "
              "No sigas hasta revisarlo.")


def _ruta(cfg, r: str) -> Path:
    from .config import RAIZ
    q = Path(r)
    return q if q.is_absolute() else RAIZ / q


def _presion_insumos(cfg):
    vc = cfg["voronoi"]
    t = pl.read_parquet(_ruta(cfg, vc["transiciones_origen"]))
    rp = _ruta(cfg, vc["rasgos"])
    if not rp.exists():
        sys.exit(f"No existe {rp}. Corre `dtcoach voronoi` primero.")
    r = pl.read_parquet(rp)
    nz = cfg["pitch"]["nx"] * cfg["pitch"]["ny"]
    if int(t["from_state"].max()) >= nz:
        sys.exit("Las transiciones de origen no son de una sola fase con la malla del config.")
    # el discretizador se ajusta con los frames de las acciones de la cadena, no con todos los eventos
    r_acc = r.join(t.select("match_id", "event_index").unique(), on=["match_id", "event_index"], how="semi")
    return t, r, r_acc, nz


def cmd_presion_cv(a, cfg):
    """¿Cuántos niveles de presión mejoran la predicción de la siguiente acción? (ADR-v2-36)"""
    from .voronoi import Discretizador, aumentar, comparar, conteos_marginales, pliegues_partido, puntaje_cv
    vc = cfg["voronoi"]
    t, r, r_acc, nz = _presion_insumos(cfg)
    base, diag = aumentar(t, r, Discretizador("cuantiles", 1), nz, vc["min_cobertura"])
    print(json.dumps(diag, indent=2), flush=True)
    folds = pliegues_partido(base["match_id"].to_numpy(), vc["folds"], cfg["seed"])
    res = {"base:1": puntaje_cv(conteos_marginales(base, nz, 1, folds), nz, vc["lam_grid"])}
    print(f"  base:1 ({nz} estados): {res['base:1']['score']:+.5f} nats/transición", flush=True)
    niveles = {}
    for cand in (a.candidatos or vc["candidatos"]):
        metodo, L = cand.split(":")
        disc = Discretizador.ajustar(r_acc, metodo, int(L), cfg["seed"])
        tk, dk = aumentar(t, r, disc, nz, vc["min_cobertura"])
        if dk["transiciones"] != diag["transiciones"]:
            sys.exit(f"{cand}: la muestra cambió ({dk['transiciones']} vs {diag['transiciones']}); no es comparable")
        res[cand] = puntaje_cv(conteos_marginales(tk, nz, int(L), folds), nz, vc["lam_grid"])
        niveles[cand] = _describir_niveles(tk, r, disc, nz)
        print(f"  {cand} ({nz * int(L)} estados): {res[cand]['score']:+.5f} "
              f"({res[cand]['score'] - res['base:1']['score']:+.5f} vs base)", flush=True)
    elegido, tab = comparar(res)
    rep = cfg.ruta("reportes") / "fase1"
    rep.mkdir(parents=True, exist_ok=True)
    tab.write_csv(rep / "presion_cv.csv")
    _json({"elegido": elegido, "muestra": diag, "tabla": tab.to_dicts(), "niveles": niveles},
          rep / "presion_cv.json")
    with pl.Config(tbl_rows=30, tbl_cols=20, tbl_width_chars=200):
        print(tab)
    mejora = bool(tab.filter(pl.col("candidato") == elegido)["mejora"][0]) if elegido != "base:1" else False
    print(f"\nElegido (1-EE hacia menos estados): {elegido} · mejora sobre la malla sola: {mejora}")
    if elegido in niveles:
        print(pl.DataFrame(niveles[elegido]))
    if not mejora:
        print("La presión NO mejora la predicción de la siguiente acción más allá del ruido: "
              "según la regla pre-registrada, el experimento se cierra aquí (se queda la malla 5×4).")
    else:
        m, L = elegido.split(":")
        print(f"Siguiente: pon `metodo: {m}` y `L: {L}` en config/presion.yaml y corre "
              "`dtcoach --config config/presion.yaml presion-aplicar`.")


def _describir_niveles(t: pl.DataFrame, r: pl.DataFrame, disc, nz: int) -> list[dict]:
    """Por nivel: participación, rasgos medianos y desenlace inmediato de la acción."""
    L = disc.L
    real = t.filter(pl.col("action_type") != "TERMINAL").with_columns(
        (pl.col("from_state") % L).alias("nivel"))
    x = real.join(r.select("match_id", "event_index", "d_rival", "n_rivales", "area_local"),
                  on=["match_id", "event_index"], how="left")
    nt = nz * L
    out = []
    for l, et in enumerate(disc.etiquetas):
        g = x.filter(pl.col("nivel") == l)
        to = g["to_state"].to_numpy()
        out.append({"nivel": et, "frac_acciones": g.height / max(x.height, 1),
                    "d_rival_mediana": _num(g["d_rival"].fill_nan(None).median()),
                    "n_rivales_media": _num(g["n_rivales"].fill_nan(None).mean()),
                    "area_local_mediana": _num(g["area_local"].fill_nan(None).median()),
                    "P_remate": float(np.isin(to, [nt, nt + 1]).mean()) if len(to) else float("nan"),
                    "P_perdida": float((to == nt + 2).mean()) if len(to) else float("nan")})
    return out


def _num(v) -> float:
    return float("nan") if v is None else float(v)


def cmd_presion_aplicar(a, cfg):
    """Escribe las transiciones zona × nivel (y su control con L = 1) en las rutas del experimento."""
    from .voronoi import Discretizador, aumentar
    vc = cfg["voronoi"]
    if not vc.get("activo"):
        sys.exit("Este comando se corre con `--config config/presion.yaml` (voronoi.activo: true).")
    t, r, r_acc, nz = _presion_insumos(cfg)
    disc = Discretizador.ajustar(r_acc, vc["metodo"], int(vc["L"]), cfg["seed"])
    ta, diag = aumentar(t, r, disc, nz, vc["min_cobertura"])
    tb, diag_b = aumentar(t, r, Discretizador("cuantiles", 1), nz, vc["min_cobertura"])
    if ta.height != tb.height:
        sys.exit("El control y el experimento no tienen la misma muestra.")
    dest = cfg.ruta("transiciones")
    dest.parent.mkdir(parents=True, exist_ok=True)
    ta.write_parquet(dest)
    db = _ruta(cfg, vc["transiciones_base"])
    db.parent.mkdir(parents=True, exist_ok=True)
    tb.write_parquet(db)
    disc.guardar(dest.parent / "discretizador.json")
    _json({"discretizador": disc.nombre, "muestra": diag}, cfg.ruta("reportes") / "fase1" / "presion_aplicar.json")
    print(json.dumps(diag, indent=2))
    print(f"escrito: {dest} ({_space(cfg).n_transient} estados transitorios) y el control {db}")
    print("Siguiente (cada uno tarda como la curva de K de la malla):\n"
          "  dtcoach --config config/presion_base.yaml curva-k --k 2 3 4 5\n"
          "  dtcoach --config config/presion.yaml curva-k --k 2 3 4 5")

def main(argv=None):
    ap = argparse.ArgumentParser(prog="dtcoach", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None)
    sp = ap.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("aplanar")
    s.add_argument("--por-lote", type=int, default=40)
    s.add_argument("--hilos", type=int, default=6)
    s.add_argument("--forzar", action="store_true")
    s.set_defaults(f=cmd_aplanar)

    sp.add_parser("partidos").set_defaults(f=cmd_partidos)

    s = sp.add_parser("voronoi", help="rasgos 360 por evento (ADR-v2-36)")
    s.add_argument("--hilos", type=int, default=None)
    s.set_defaults(f=cmd_voronoi)
    s = sp.add_parser("presion-cv", help="¿mejora la presión la predicción? (ADR-v2-36)")
    s.add_argument("--candidatos", nargs="*", default=None)
    s.set_defaults(f=cmd_presion_cv)
    sp.add_parser("presion-aplicar", help="transiciones zona × nivel (con --config config/presion.yaml)"
                  ).set_defaults(f=cmd_presion_aplicar)
    sp.add_parser("fase0").set_defaults(f=cmd_fase0)

    s = sp.add_parser("cv-k")
    s.add_argument("--k", type=int, nargs="*", help="rejilla de K (default: config)")
    s.add_argument("--frac", type=float, default=None, help="fracción de partidos para la CV")
    s.set_defaults(f=cmd_cv_k)

    s = sp.add_parser("mezcla")
    s.add_argument("--K", type=int, required=True)
    s.add_argument("--init", default="escalera", choices=["escalera", "kmeans"])
    s.set_defaults(f=cmd_mezcla)

    s = sp.add_parser("reproducibilidad")
    s.add_argument("--K", type=int, required=True)
    s.add_argument("--semillas", type=int, nargs="+", default=[1, 2, 3])
    s.set_defaults(f=cmd_repro)

    sp.add_parser("elo").set_defaults(f=cmd_elo)

    s = sp.add_parser("fase2")
    s.add_argument("--foco", default=None, help="DT focal (default: config.foco.coach)")
    s.set_defaults(f=cmd_fase2)

    s = sp.add_parser("fase3")
    s.add_argument("--foco", default=None)
    s.add_argument("--min-partidos", type=int, default=30)
    s.set_defaults(f=cmd_fase3)

    s = sp.add_parser("atlas")
    s.add_argument("--min-partidos", type=int, default=50)
    s.add_argument("--foco", default=None, help="técnico a resaltar (default: config.foco.coach)")
    s.add_argument("--rehacer", action="store_true")
    s.set_defaults(f=cmd_atlas)

    s = sp.add_parser("decisiones")
    s.add_argument("--foco", default=None)
    s.set_defaults(f=cmd_decisiones)

    s = sp.add_parser("simulador")
    s.add_argument("--foco", default=None)
    s.set_defaults(f=cmd_simulador)

    s = sp.add_parser("curva-k")
    s.add_argument("--k", type=int, nargs="+", default=list(range(2, 11)))
    s.add_argument("--semillas", type=int, nargs="+", default=[1, 2, 3])
    s.set_defaults(f=cmd_curva_k)

    s = sp.add_parser("mallado")
    s.add_argument("--candidatos", nargs="+", default=None, help="p.ej. 4x3 5x4 6x4 8x5")
    s.add_argument("--aplicar", action="store_true", help="escribe la malla elegida en config.pitch")
    s.set_defaults(f=cmd_mallado)

    s = sp.add_parser("markov")
    s.add_argument("--K", type=int, default=None)
    s.add_argument("--n-boot", type=int, default=50)
    s.set_defaults(f=cmd_markov)

    s = sp.add_parser("comparar-paso")
    s.add_argument("--K", type=int, required=True)
    s.add_argument("--frac", type=float, default=None)
    s.add_argument("--aplicar", action="store_true")
    s.set_defaults(f=cmd_comparar_paso)

    s = sp.add_parser("bondad")
    s.add_argument("--K", type=int, nargs="+", required=True, help="p.ej. --K 1 6")
    s.add_argument("--n-boot", type=int, default=0)
    s.set_defaults(f=cmd_bondad)

    a = ap.parse_args(argv)
    cfg = Config.load(a.config)
    a.f(a, cfg)


if __name__ == "__main__":
    main()
