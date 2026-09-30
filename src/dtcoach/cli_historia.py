"""Comandos de la historia del técnico, uno por SECCIÓN del reto. Cada comando escribe en
reports/historia/<foco>/<sección>/ un Markdown para leer, un JSON con las cifras exactas (y sus
hipótesis pre-registradas, `11_HIPOTESIS.md`) y sus figuras.

  identidad     ¿se le reconoce?, contexto (H1–H8, rival por Elo, H22) y evolución entre clubes
  ofensiva      salida, progresión, llegada, ocasión, motivos, las familias dibujadas (H18–H21)
  defensa       presión, bloque (con control de cámara), transiciones, lo que concede
  jugadores     red de pases, roles, protagonistas, decisiones y sustituciones (H23)
  balon_parado  corners, tiros libres, laterales largos y xDefense (H24–H26)
  simulacion    simulador de partido, puntos esperados y proyección en su club actual
  blindaje      xG contra OBV, pocos partidos, BH global
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

from . import ingest

TABLA_VERSION = 7          # sube cuando cambia lo que calcula `tabla_liga`: fuerza a rehacerla


def _slug(foco: str) -> str:
    return foco.lower().replace(" ", "_")


def _dir(cfg, foco: str, seccion: str) -> Path:
    d = cfg.ruta("reportes") / "historia" / _slug(foco) / seccion
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ruta(cfg, r: str) -> Path:
    from .config import RAIZ
    q = Path(r)
    return q if q.is_absolute() else RAIZ / q


def _json(obj, path: Path) -> None:
    from .cli import _json as j
    j(obj, path)


def _escribir(out: Path, nombre: str, md: list[str], res: dict) -> None:
    _json(res, out / f"{nombre.lower()}.json")
    (out / f"{nombre.upper()}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    print(f"\nSalidas: {out}")


def _tp(cfg) -> pl.DataFrame:
    from .cli import _equipo_partido
    from .eventos import con_rival
    return con_rival(_equipo_partido(cfg))


def _eventos(cfg, con_extra: bool = True) -> pl.DataFrame:
    from .eventos import leer
    from .extra import unir
    t0 = time.time()
    ev = leer(ingest.scan_events(cfg.ruta("eventos_parquet")))
    if con_extra:
        p = cfg.ruta("eventos_extra")
        if p.exists():
            ev = unir(ev, pl.read_parquet(p))
        else:
            print(f"[aviso] sin {p} (`dtcoach extra`): no hay centros, técnica de corners ni asistencias")
            ev = unir(ev, None)
    print(f"eventos: {ev.height:,} en {time.time() - t0:.0f}s", flush=True)
    return ev


def _opcional(p: Path) -> pl.DataFrame | None:
    return pl.read_parquet(p) if p.exists() else None


def _clubes(M: pl.DataFrame, foco: str, minimo: int) -> list[str]:
    return (M.filter(pl.col("coach") == foco).group_by("team").agg(pl.col("match_id").n_unique().alias("p"))
            .filter(pl.col("p") >= minimo).sort("p", descending=True)["team"].to_list())


def _foco(a, cfg) -> str:
    return a.foco or cfg["foco"]["coach"]


# ----------------------------------------------------------------------
# geometría 360 (una pasada por los frames)
# ----------------------------------------------------------------------
def cmd_geometria(a, cfg):
    from .balon_parado import ids_saques
    from .geometria import geometria_liga
    fc = cfg["futbol"]
    ev = _eventos(cfg, con_extra=False)
    ids = ids_saques(ev, fc)
    print(f"saques a balón parado para el frame del cobro: {sum(len(v) for v in ids.values()):,}", flush=True)
    t0 = time.time()
    B, Mk = geometria_liga(cfg.ruta("raw_frames"), ids, fc["min_defensores"], a.hilos or 4)
    idx = ev.select("match_id", "id", pl.col("index").alias("event_index"))
    B = B.join(idx, on=["match_id", "id"], how="inner")
    Mk = Mk.join(idx, on=["match_id", "id"], how="inner")
    for df, clave in ((B, "bloque"), (Mk, "saques")):
        p = _ruta(cfg, fc[clave])
        p.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(p)
    res = {"frames_con_bloque": B.height, "saques_con_frame": Mk.height, "segundos": round(time.time() - t0),
           "altura_bloque_p10_p50_p90": [float(B["altura"].quantile(q)) for q in (.1, .5, .9)] if B.height else None,
           "ancho_visible_mediana": float(B["ancho_visible"].median()) if B.height else None,
           "defensores_visibles_mediana": float(B["n_def"].median()) if B.height else None,
           "dist_marca_mediana": float(Mk["dist_marca"].median()) if Mk.height else None,
           "altura_linea_mediana": float(Mk["altura_linea_tactica"].median()) if Mk.height else None}
    _json(res, cfg.ruta("reportes") / "fase1" / "geometria_360.json")
    print(json.dumps(res, indent=2, ensure_ascii=False))


def cmd_extra(a, cfg):
    from .extra import extraer
    rep = extraer(cfg.ruta("raw_events"), cfg.ruta("eventos_extra"), hilos=a.hilos or 6)
    print(json.dumps({k: v for k, v in rep.items() if k != "errores"}, indent=2, ensure_ascii=False))
    if rep["errores"]:
        print(f"[aviso] {len(rep['errores'])} archivos con error; primeros: {rep['errores'][:5]}")


# ----------------------------------------------------------------------
# la tabla equipo-partido de TODA la liga (se calcula una vez)
# ----------------------------------------------------------------------
def _rutas_bp(cfg) -> dict:
    base = _ruta(cfg, cfg["futbol"]["tabla"]).parent
    return {"jugadas": base / "bp_jugadas.parquet", "capa1": base / "xd_capa1.parquet",
            "capa2": base / "xd_capa2.parquet", "xdefensa": base / "xdefensa.json",
            "cadena": base / "xd_cadena.parquet"}


def _estado(cfg) -> dict:
    fc = cfg["futbol"]
    b = _ruta(cfg, fc["bloque"])
    return {"version": TABLA_VERSION, "extra": cfg.ruta("eventos_extra").exists(),
            "saques360": _ruta(cfg, fc["saques"]).exists(), "rasgos360": _ruta(cfg, cfg["voronoi"]["rasgos"]).exists(),
            "bloque_visible": b.exists() and "ancho_visible" in pl.read_parquet_schema(b)}


def tabla_liga(cfg, ev: pl.DataFrame | None = None, rehacer: bool = False) -> pl.DataFrame:
    from . import balon_parado as bp
    from . import defensa as df_
    from . import futbol as fb
    from . import ofensiva as of
    from . import xdefensa as xd
    from .decisiones import leer_eventos
    from .eventos import posesiones
    from .extra import tiene_extra
    from .jugadores import estabilidad_once
    fc = cfg["futbol"]
    p = _ruta(cfg, fc["tabla"])
    meta = p.with_suffix(".json")
    est = _estado(cfg)
    if p.exists() and not rehacer and meta.exists() and json.loads(meta.read_text()) == est:
        return pl.read_parquet(p)
    if p.exists() and not rehacer:
        print("[tabla de la liga] cambió lo que se calcula o hay insumos nuevos (extra/360): se rehace", flush=True)
    ev = _eventos(cfg) if ev is None else ev
    tp = _tp(cfg)
    pos = posesiones(ev)
    rasgos = _opcional(_ruta(cfg, cfg["voronoi"]["rasgos"]))
    bloque = _opcional(_ruta(cfg, fc["bloque"]))
    s360 = _opcional(_ruta(cfg, fc["saques"]))
    for falta, que in ((rasgos is None, "rasgos 360 (dtcoach voronoi): sin presión 360"),
                       (bloque is None, "bloque 360 (dtcoach geometria): sin bloque"),
                       (s360 is None, "saques 360 (dtcoach geometria): sin organización a balón parado")):
        if falta:
            print(f"[aviso] sin {que}")
    con_extra = tiene_extra(ev)
    rb = _rutas_bp(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    j = bp.con_360(bp.jugadas(ev, fc), s360)
    j.write_parquet(rb["jugadas"])
    # xDefense: las dos capas sobre toda la liga (fuera de muestra)
    print("xDefense: capa 1 (prevención) y capa 2 (supresión)...", flush=True)
    p1, r1 = xd.capa1(j, fc["xd_folds"], fc["xd_lam"], cfg["seed"])
    # modelo APARTE para los saques que no van al área (el de los centros, pre-registrado, no cambia)
    p1o, r1o = xd.capa1(j, fc["xd_folds"], fc["xd_lam"], cfg["seed"], tipos=("tl_otro", "lateral_zona"))
    p1 = pl.concat([p1, p1o])
    ff = (ingest.scan_events(cfg.ruta("eventos_parquet")).filter(pl.col("type") == "Shot")
          .select("id", "shot_freeze_frame").collect())
    rem = xd.remates_liga(ev, j, ff)
    p2, r2 = xd.capa2(rem, fc["xd_folds"], fc["xd_lam"], cfg["seed"])
    p1.write_parquet(rb["capa1"])
    p2.write_parquet(rb["capa2"])
    D = xd.descomposicion(j, p1, p2, fc["lateral_cuarto_x"])
    D.write_parquet(rb["cadena"])
    kappa = {t: float(v) for t, v in D.group_by("tipo").agg(pl.col("kappa").first()).iter_rows()}
    _json({"capa1": r1, "capa1_otros": r1o, "capa2": r2, "kappa": kappa}, rb["xdefensa"])
    tablas = (fb.ofensiva(ev, pos, fc) + fb.defensiva(ev, tp) + fb.transiciones(pos, fc)
              + fb.del_360(ev, rasgos, bloque, tp, fc) + of.metricas(ev, pos, fc, con_extra)
              + df_.metricas(ev, rasgos, bloque, tp, fc) + bp.metricas(j, tp, fc["cobertura_min"], fc["lateral_cuarto_x"])
              + xd.metricas_equipo(p1, p2, tp) + xd.metricas_descomposicion(D, tp) + xd.metricas_tl(p2, j, tp)
              + [estabilidad_once(leer_eventos(ingest.scan_events(cfg.ruta("eventos_parquet")))["xi"], tp)])
    M = fb.unir(tablas, tp)
    p.parent.mkdir(parents=True, exist_ok=True)
    M.write_parquet(p)
    meta.write_text(json.dumps(est))
    print(f"tabla equipo-partido: {M.height:,} filas · {len(fb.metricas_de(M))} métricas → {p}", flush=True)
    return M


def cmd_tabla(a, cfg):
    tabla_liga(cfg, rehacer=a.rehacer)


# ----------------------------------------------------------------------
# utilidades de comparación y de hipótesis
# ----------------------------------------------------------------------
def _bloque(M, metricas, foco, lado, fc, seed, club=None):
    from .comparar import etiquetar, foco_vs_liga
    ms = [m for m in metricas if f"{m}__n" in M.columns and float(M[f"{m}__d"].sum()) > 0]
    return etiquetar(foco_vs_liga(M, ms, foco, lado, fc["n_boot"], seed, club), 0.05, 20) if ms else {}


def _percentiles(M, metricas, foco, lado, minimo):
    from .comparar import percentil, por_era
    ms = [m for m in metricas if f"{m}__n" in M.columns and float(M[f"{m}__d"].sum()) > 0]
    eras = por_era(M, ms, lado, minimo)
    return {m: percentil(eras, m, foco) for m in ms}


def _comparar_bloques(M, bloques: dict, defs: dict, foco: str, fc: dict, seed: int, titulos: dict) -> tuple[dict, list]:
    """Para cada bloque {nombre: (lado, métricas)}: comparación, percentiles, fiabilidad y su tabla."""
    from .comparar import fiabilidad, tabla
    res, md = {}, []
    for nombre, (lado, ms) in bloques.items():
        r = _bloque(M, ms, foco, lado, fc, seed)
        if not r:
            continue
        pc = _percentiles(M, list(r), foco, lado, fc["min_partidos_era"])
        fi = fiabilidad(M, list(r), lado, fc["min_partidos_era"])
        res[nombre] = {"comparacion": r, "percentiles": pc, "fiabilidad": fi}
        md += [f"## {titulos.get(nombre, nombre)}", "", tabla(r, fi, pc, defs), ""]
    return res, md


def _hipotesis(defs: dict, resultados: dict, alpha: float = 0.05, min_partidos: int = 20) -> dict:
    """Una hipótesis = un conjunto de métricas pre-registradas. p = mín de sus p con Bonferroni
    dentro de la hipótesis; BH entre las hipótesis de la sección (11_HIPOTESIS, reglas G)."""
    from .inference import benjamini_hochberg
    out = {}
    for h, (nombre, ms) in defs.items():
        rs = {m: resultados[m] for m in ms if m in resultados and np.isfinite(resultados[m].get("p", np.nan))}
        if not rs:
            continue
        p = min(1.0, min(r["p"] for r in rs.values()) * len(rs))
        pf = min(r.get("partidos_foco", 99) for r in rs.values())
        out[h] = {"nombre": nombre, "p": float(p), "metricas": list(rs), "partidos_foco": pf,
                  "decide": min(rs, key=lambda m: rs[m]["p"])}
    if out:
        q, rech = benjamini_hochberg(np.array([v["p"] for v in out.values()]), alpha)
        for (h, v), qi, ri in zip(out.items(), q, rech):
            v["q"] = float(qi)
            v["etiqueta"] = ("🟢" if ri and v["partidos_foco"] >= min_partidos else
                             ("🟡" if v["p"] < alpha else "⚪"))
    return out


def _tabla_hipotesis(H: dict, defs: dict) -> list[str]:
    if not H:
        return []
    L = ["## Hipótesis pre-registradas (11_HIPOTESIS.md)", "",
         "| id | qué se prueba | métrica que decide | p (Bonferroni) | q (BH) | evidencia |", "|---|---|---|---|---|---|"]
    for h, v in H.items():
        L.append(f"| {h} | {v['nombre']} | {defs.get(v['decide'], {}).get('nombre', v['decide'])} | {v['p']:.4f} | "
                 f"{v['q']:.4f} | {v['etiqueta']} |")
    return L + [""]


def _plano(res: dict) -> dict:
    """{bloque: {comparacion: {m: r}}} → {m: r}."""
    return {m: r for b in res.values() for m, r in b.get("comparacion", {}).items()}


def _rival(cfg, M, metricas, defs, foco, lado, fc):
    from .cli import _elo
    from .rival import ajuste_distinto, estratos, por_estrato, tabla_md
    est, cortes = estratos(_elo(cfg))
    ms = [m for m in metricas if f"{m}__n" in M.columns]
    r = por_estrato(M, est, ms, foco, lado, min(fc["n_boot"], 600), cfg["seed"])
    aj = ajuste_distinto(r, ms)
    return {"cortes_elo": cortes, "por_estrato": r, "ajuste": aj}, tabla_md(r, defs, ms, aj)


# ----------------------------------------------------------------------
# IDENTIDAD: reconocimiento, contexto, rival, evolución
# ----------------------------------------------------------------------
HUELLA = ["pases_prog", "conducciones_prog", "entradas_tercio", "entradas_area", "xg_por_remate", "field_tilt",
          "posesion", "saque_corto", "ppda", "altura_recuperacion", "presion_alta", "recupera_5s",
          "presion_aplicada", "altura_bloque", "area_bloque", "directness", "velocidad_avance", "pase_largo"]
EVOLUCION = ["ppda", "field_tilt", "altura_recuperacion", "presion_aplicada", "altura_bloque", "directness"]
RIVAL_CLAVE = ["posesion", "field_tilt", "directness", "remates", "xg", "ppda", "presion_aplicada", "altura_bloque",
               "saque_corto"]


def cmd_identidad(a, cfg):
    from . import futbol as fb
    from . import ofensiva as of
    from .cli import _elo, _equipo_partido, _tabla_fase2
    from .graficas_historia import evolucion as fig_evolucion
    from .graficas_secciones import rival_estratos
    from .identidad import evolucion, huella, ranking_reconocimiento, reconocimiento
    from .rival import NOMBRE, estratos, puntos_por_estrato
    from .simulador import xpts_por_equipo_partido
    fc = cfg["futbol"]
    foco = _foco(a, cfg)
    K = cfg["fase2"]["K"]
    fams = cfg["fase2"]["familias"]
    M = tabla_liga(cfg)
    out = _dir(cfg, foco, "identidad")
    t_seq = _tabla_fase2(cfg, foco)
    defs = {**fb.DEFINICIONES, **of.DEFINICIONES}
    ms = [m for m in HUELLA if f"{m}__n" in M.columns]
    H = huella(t_seq, M, K, ms)
    cols = [f"ataque_{k + 1}" for k in range(K)] + [f"defensa_{k + 1}" for k in range(K)] + ms
    res = {"liga": reconocimiento(H, cols, foco, "liga", fc["n_perm"], fc["lam_logit"], cfg["seed"]),
           "club": reconocimiento(H, cols, foco, "club", fc["n_perm"], fc["lam_logit"], cfg["seed"])}
    rk = ranking_reconocimiento(H, cols, fc["min_partidos_era"], fc["lam_logit"], cfg["seed"])
    rk.write_csv(out / "reconocimiento_ranking.csv")
    res["ranking"] = rk.with_row_index("puesto", offset=1).filter(pl.col("coach") == foco).to_dicts()
    res["ranking_n"] = rk.height
    nombres = {f"ataque_{k + 1}": f"ataque · {f}" for k, f in enumerate(fams)}
    nombres |= {f"defensa_{k + 1}": f"rivales · {f}" for k, f in enumerate(fams)}
    nombres |= {m: defs[m]["nombre"].split(" (")[0] for m in EVOLUCION if m in defs}
    md = [f"# 1. Identidad y contexto — {foco}", "",
          "¿Tiene una idea propia? ¿Se le reconoce? ¿Cambia con el marcador, el rival o el club?", ""]
    for contra in ("liga", "club"):
        r = res[contra]
        if "auc" not in r:
            md += [f"- contra {contra}: {r.get('nota')}"]
            continue
        md += [f"## ¿Se le reconoce contra {'la liga' if contra == 'liga' else 'su mismo club con otros técnicos'}?",
               "", f"AUC fuera de muestra **{r['auc']:.3f}** (nula por permutación: media {r['auc_nula_media']:.3f}, "
               f"p95 {r['auc_nula_p95']:.3f}; p = {r['p']:.3f}). {r['partidos_foco']} partidos suyos contra "
               f"{r['partidos_otros']}.", "", "Rasgos que más lo distinguen (coeficiente en desviaciones estándar):", ""]
        md += [f"- {nombres.get(x['rasgo'], defs.get(x['rasgo'], {}).get('nombre', x['rasgo']))}: {x['coef_de']:+.2f}"
               for x in r["rasgos"]]
        md.append("")
    for x in res["ranking"]:
        md.append(f"- **Ranking de reconocimiento:** {x['team']}: puesto {x['puesto']} de {res['ranking_n']} "
                  f"técnicos-club (AUC {x['auc']:.3f}).")
    # contexto (fase 2): lo resume si ya se corrió
    h2 = cfg.ruta("reportes") / "fase2" / f"hipotesis_{_slug(foco)}.json"
    if h2.exists():
        f2 = json.loads(h2.read_text())
        res["contexto_fase2"] = {k: {c: v.get(c) for c in ("nombre", "p", "q", "etiqueta")}
                                 for k, v in f2.get("hipotesis", {}).items()}
        md += ["", "## El técnico como mezcla de las tres familias, bajo contexto (fase 2, H1–H8)", "",
               "| id | qué se prueba | p | q | evidencia |", "|---|---|---|---|---|"]
        md += [f"| {k} | {v['nombre']} | {v['p']:.4f} | {v.get('q') or float('nan'):.4f} | {v['etiqueta']} |"
               for k, v in res["contexto_fase2"].items()]
        md += ["", *[f"- {f}" for f in f2.get("frases", [])]]
    else:
        md += ["", "_(Sin fase 2: corre `bash scripts/correr_foco.sh` para H1–H8.)_"]
    # rival por Elo (G2)
    est, cortes = estratos(_elo(cfg))
    x = xpts_por_equipo_partido(ingest.scan_events(cfg.ruta("eventos_parquet")), _equipo_partido(cfg))
    pts = puntos_por_estrato(x, est, foco, min(fc["n_boot"], 1000), cfg["seed"])
    rv, tabla_rv = _rival(cfg, M, RIVAL_CLAVE, defs, foco, "propio", fc)
    Hh = _hipotesis({"H22": ("su estilo se ajusta al nivel del rival distinto que la liga", RIVAL_CLAVE)},
                    {m: {"p": v["p"], "partidos_foco": 99} for m, v in rv["ajuste"].items()})
    res |= {"rival": rv, "puntos_por_estrato": pts, "hipotesis": Hh}
    md += ["", "## ¿Juega distinto según el rival? (Elo previo del rival; G2)", "",
           f"Cortes de la liga: débil ≤ {cortes['p25']:.0f}, fuerte ≥ {cortes['p75']:.0f} de Elo.", "",
           "| estrato | partidos | puntos por partido (foco vs liga) | xG a favor − en contra (foco vs liga) |",
           "|---|---|---|---|"]
    for e, v in pts.items():
        md.append(f"| {NOMBRE[e]} | {v['partidos']} | {v['pts']['foco']:.2f} vs {v['pts']['liga']:.2f} "
                  f"({v['pts']['dif']:+.2f} [{v['pts']['lo']:+.2f}, {v['pts']['hi']:+.2f}]) | "
                  f"{v['xg_dif']['foco']:+.2f} vs {v['xg_dif']['liga']:+.2f} ({v['xg_dif']['dif']:+.2f} "
                  f"[{v['xg_dif']['lo']:+.2f}, {v['xg_dif']['hi']:+.2f}]) |")
    md += ["", "Cada celda: foco vs liga EN EL MISMO estrato (diferencia). Última columna: Δ = (foco − liga) contra "
           "fuertes − (foco − liga) contra débiles.", "", tabla_rv, ""]
    md += _tabla_hipotesis(Hh, defs)
    rival_estratos(pts, rv["por_estrato"], [("field_tilt", "dominio territorial (field tilt)"),
                                            ("directness", "verticalidad"), ("ppda", "PPDA (menos = presiona más)")],
                   foco, out / "rival.png")
    # evolución
    ev_ = evolucion(t_seq, H, foco, K, [m for m in EVOLUCION if m in ms])
    res["evolucion"] = ev_
    fig_evolucion(ev_, list(nombres) + [m for m in EVOLUCION if m in ms], nombres, foco, out / "evolucion.png")
    md += ["## Evolución partido a partido (nivel local, Kalman + Rauch-Tung-Striebel)", "",
           "| serie | q/r (≈ 0 = identidad estable) |", "|---|---|"]
    md += [f"| {nombres.get(s, s)} | {v['q_sobre_r']:.4f} |" for s, v in ev_["series"].items()]
    for c in ev_["cambios_de_club"]:
        md += ["", f"**Cambio {c['de']} → {c['a']}** (salto del nivel suavizado; |z| > 2 = cambio claro):", ""]
        md += [f"- {nombres.get(s, s)}: {v['salto']:+.3f} (z = {v['z']:+.2f})" for s, v in c["series"].items()]
    _escribir(out, "identidad", md, res)


# ----------------------------------------------------------------------
# OFENSIVA
# ----------------------------------------------------------------------
OF_TITULOS = {"base": "Lo básico: volumen, dominio y peligro", "salida": "1. Salida desde atrás",
              "progresion": "2. Progresión: por dónde y a qué velocidad avanza",
              "llegada": "3. Llegada: cómo entra al área", "ocasion": "4. Ocasión: qué remates genera",
              "motivos": "5. Motivos de pase: los dibujos de tres pases que repite"}
OF_RIVAL = ["posesion", "field_tilt", "directness", "velocidad_avance", "pase_largo", "remates", "xg",
            "xg_por_remate", "entradas_area", "prog_banda"]
H_OFENSIVA = {"H18": ("ataca más vertical que la liga", ["directness", "velocidad_avance"]),
              "H19": ("progresa por carriles distintos a los de la liga", ["prog_banda", "prog_interior", "prog_centro"]),
              "H20": ("llega al área y genera remates de otra manera",
                      ["entrada_centro", "entrada_filtrado", "entrada_atras", "entrada_conduccion", "asist_centro",
                       "asist_filtrado", "asist_atras", "asist_sin"]),
              "H21": ("sus motivos de pase difieren de los de la liga", [f"motivo_{m}" for m in
                                                                        ("ABAB", "ABAC", "ABCA", "ABCB", "ABCD")])}


def cmd_ofensiva(a, cfg):
    from . import futbol as fb
    from . import ofensiva as of
    from .cli import _space, _trans
    from .comparar import tabla
    from .graficas_historia import diferencia_zonas, percentiles
    from .graficas_secciones import familias_cancha, reparto
    fc = cfg["futbol"]
    foco = _foco(a, cfg)
    ev = _eventos(cfg)
    M = tabla_liga(cfg, ev, a.rehacer)
    tp = _tp(cfg)
    out = _dir(cfg, foco, "ofensiva")
    defs = {**fb.DEFINICIONES, **of.DEFINICIONES}
    bloques = {"base": ("propio", fb.OFENSIVAS + ["presion_sufrida", "espacio_propio"]),
               **{k: ("propio", v) for k, v in of.BLOQUES.items()}}
    md = [f"# 2. Fase ofensiva — {foco}", "",
          "Cada métrica: foco contra la liga sin sus partidos (IC 95 % por bootstrap de partidos), su percentil entre "
          f"los técnicos-club con ≥ {fc['min_partidos_era']} partidos y su fiabilidad entre mitades (≥ 0.7 = rasgo "
          "estable). Definiciones: 03_FRAMEWORK §5 y §7.", ""]
    if not (cfg.ruta("eventos_extra").exists()):
        md += ["> ⚠ Sin `dtcoach extra`: faltan los tipos de entrada al área, las asistencias y los remates de "
               "primera.", ""]
    res, md_b = _comparar_bloques(M, bloques, defs, foco, fc, cfg["seed"], OF_TITULOS)
    md += md_b
    plano = _plano(res)
    todas = list(plano)
    res["por_club"] = {}
    for club in _clubes(M, foco, fc["min_partidos_club"]):
        res["por_club"][club] = _bloque(M, todas, foco, "propio", fc, cfg["seed"], club)
        md += [f"## Solo en {club}", "", tabla(res["por_club"][club], None, None, defs), ""]
    # llegada con la cadena (primer paso) y valor de zona
    space = _space(cfg)
    trans = _trans(cfg)
    claves, A, dims = fb.conteos_por_partido(trans, space.n_transient, space.n_states)
    cx = np.repeat(space.zone_centroids()[:, 0], len(space.phases))
    cy = np.repeat(space.zone_centroids()[:, 1], len(space.phases))
    objetivos = {"último tercio": cx >= 80, "frente al área": (cx >= 102) & (cy >= 18) & (cy <= 62)}
    ll = fb.comparar_llegada(claves, A, dims, tp, foco, objetivos, fc["lam_llegada"], min(fc["n_boot"], 300),
                             cfg["seed"], "propio")
    res["llegada_cadena"] = ll
    md += ["## Llegada desde el inicio de la secuencia (la cadena)", "",
           "| destino | medida | foco | liga | dif [IC 95 %] | p |", "|---|---|---|---|---|---|"]
    for n in objetivos:
        for q, v in ll[n].items():
            md.append(f"| {n} | {'P(llegar)' if q == 'P' else 'acciones si llega'} | {v['foco']:.3f} | "
                      f"{v['liga']:.3f} | {v['dif']:+.3f} [{v['lo']:+.3f}, {v['hi']:+.3f}] | {v['p']:.4f} |")
    diferencia_zonas(ll["V_foco"], ll["V_liga"], space.nx, space.ny, out / "valor_zona.png",
                     f"Dónde vale más el balón para {foco} que para la liga (xG que produce una secuencia que pasa "
                     "por esa zona)", "diferencia de xG por secuencia")
    # las familias en la cancha
    from .mezcla import DatosPosesion, Mezcla, responsabilidades
    K = cfg["fase2"]["K"]
    fams = cfg["fase2"]["familias"]
    m = Mezcla.cargar(cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz")
    d = DatosPosesion.desde_transiciones(trans, space)
    r = responsabilidades(m, d)
    coach = d.meta["coach"].to_numpy()
    cf = d.meta["coach_faced"].to_numpy() if "coach_faced" in d.meta.columns else np.full(len(coach), None)
    mid = d.meta["match_id"].to_numpy()
    pf = set(mid[(coach == foco) | (cf == foco)])
    es_f = coach == foco
    es_l = np.array([x not in pf for x in mid])
    fam = of.familias_en_cancha(d, r, es_f, es_l, m.P, m.mu, fc["lam_llegada"])
    res["familias"] = [{"familia": n, **f} for n, f in zip(fams, fam)]
    familias_cancha(fam, fams, space.nx, space.ny, foco, out / "familias_cancha.png")
    md += ["", "## Las tres familias, dibujadas", ""]
    for n, f in zip(fams, fam):
        md.append(f"- *{n}*: {foco} {f['foco']['secuencias']:.0f} secuencias; camino típico por las zonas "
                  f"{f['foco']['camino']} (liga {f['liga']['camino']}); probabilidad del camino "
                  f"{100 * f['foco']['prob_camino']:.2f} % contra {100 * f['liga']['prob_camino']:.2f} %.")
    # según el rival
    rv, tabla_rv = _rival(cfg, M, OF_RIVAL, defs, foco, "propio", fc)
    res["rival"] = rv
    md += ["", "## Según el nivel del rival (G2)", "", tabla_rv, ""]
    # hipótesis
    res["hipotesis"] = _hipotesis(H_OFENSIVA, plano)
    md += _tabla_hipotesis(res["hipotesis"], defs)
    # figuras
    pct = {}
    for b in res.values():
        if isinstance(b, dict) and "percentiles" in b:
            pct.update(b["percentiles"])
    percentiles({k: v for k, v in pct.items() if k in plano}, defs, foco, out / "percentiles.png", "Fase ofensiva")
    etq = {m: defs[m]["nombre"].split(" por partido")[0] for m in defs}
    reparto(plano, {"¿Cómo entra al área?": ["entrada_centro", "entrada_filtrado", "entrada_atras",
                                             "entrada_conduccion", "entrada_otro"],
                    "¿Qué asiste sus remates?": ["asist_centro", "asist_filtrado", "asist_atras", "asist_pase",
                                                 "asist_sin"],
                    "¿Por dónde progresa?": ["prog_banda", "prog_interior", "prog_centro"],
                    "¿Qué dibujos de tres pases repite?": [f"motivo_{x}" for x in ("ABAB", "ABAC", "ABCA", "ABCB",
                                                                                     "ABCD")]},
            etq, foco, out / "reparto.png", f"Cómo ataca {foco} contra la liga (cada barra suma 100 %)")
    _escribir(out, "ofensiva", md, res)


# ----------------------------------------------------------------------
# DEFENSA
# ----------------------------------------------------------------------
DEF_TITULOS = {"presion": "Presión", "bloque": "Organización: el bloque sin balón (360)",
               "transiciones": "Transiciones", "concedido": "Lo que le hacen sus rivales (concedido)"}
CONCEDIDO = ["remates", "xg", "entradas_area", "entradas_tercio", "pases_prog", "obv", "xg_por_remate", "directness",
             "velocidad_avance", "zona14"]
DEF_RIVAL = ["ppda", "presion_aplicada", "presion_tercio_alto", "altura_recuperacion", "altura_bloque",
             "anchura_bloque", "recupera_5s"]


def cmd_defensa(a, cfg):
    from . import defensa as df_
    from . import futbol as fb
    from . import ofensiva as of
    from .eventos import posesiones
    from .graficas_historia import curva_recuperacion, diferencia_zonas, percentiles
    from .graficas_secciones import bloque_tipico, curva_presion, esquema_bloque, pictograma, presion_tercios
    fc = cfg["futbol"]
    foco = _foco(a, cfg)
    ev = _eventos(cfg)
    M = tabla_liga(cfg, ev)
    tp = _tp(cfg)
    out = _dir(cfg, foco, "defensa")
    defs = {**fb.DEFINICIONES, **of.DEFINICIONES, **df_.DEFINICIONES}
    bloques = {"presion": ("propio", fb.DEFENSIVAS_M + ["presion_aplicada", "presion_tercio_alto",
                                                        "presion_tercio_medio", "presion_tercio_bajo"]),
               "bloque": ("propio", ["altura_bloque", "anchura_bloque", "anchura_bloque_vis", "area_bloque",
                                     "profundidad_bloque", "ancho_visible"]),
               "transiciones": ("propio", fb.TRANSICIONES), "concedido": ("rival", CONCEDIDO)}
    md = [f"# 3. Fase defensiva — {foco}", "", "Presión, organización y transiciones (reto 5.1). Definiciones: "
          "03_FRAMEWORK §5 y §9.", ""]
    res, md_b = _comparar_bloques(M, bloques, defs, foco, fc, cfg["seed"], DEF_TITULOS)
    md += md_b
    plano = _plano(res)
    bl = res.get("bloque", {}).get("comparacion", {})
    if "anchura_bloque" in bl and "anchura_bloque_vis" in bl:
        a_, v_ = bl["anchura_bloque"], bl["anchura_bloque_vis"]
        sobrevive = (v_["hi"] < 0) == (a_["hi"] < 0) and (v_["lo"] > 0) == (a_["lo"] > 0)
        res["control_camara"] = {"sobrevive": bool(sobrevive), "anchura_todos": a_, "anchura_camara_abierta": v_,
                                 "ancho_visible": bl.get("ancho_visible")}
        md += ["## Control de cámara (¿el bloque estrecho es un artefacto del encuadre?)", "",
               f"Anchura con todos los frames: {a_['dif']:+.2f} m [{a_['lo']:+.2f}, {a_['hi']:+.2f}]; solo con la "
               f"cámara abierta (≥ {fc['ancho_min']:g} m visibles): {v_['dif']:+.2f} m [{v_['lo']:+.2f}, "
               f"{v_['hi']:+.2f}]. " + ("**Sobrevive:** la conclusión no depende del encuadre." if sobrevive else
                                         "**No sobrevive:** la diferencia depende del encuadre; no se afirma."), ""]
    rasgos = _opcional(_ruta(cfg, cfg["voronoi"]["rasgos"]))
    bloque = _opcional(_ruta(cfg, fc["bloque"]))
    if rasgos is not None:
        c = df_.curva_presion(ev, rasgos, tp, foco, min(fc["n_boot"], 300), cfg["seed"])
        res["curva_presion"] = c
        curva_presion(c, foco, out / "curva_presion.png", fc["presion_m"])
        if "presion_aplicada" in plano:
            pictograma(plano["presion_aplicada"]["foco"], plano["presion_aplicada"]["liga"], foco,
                       out / "pictograma_presion.png", fc["presion_m"])
        from .cli import _space
        from .futbol import mapa_presion
        space = _space(cfg)
        mp = mapa_presion(ev, rasgos, tp, foco, space.nx, space.ny, fc["presion_m"])
        diferencia_zonas(mp["foco"], mp["liga"], space.nx, space.ny, out / "presion_zonas.png",
                         f"Dónde aprieta {foco} más que la liga (azul) o menos (rojo), en su campo: fracción de "
                         f"toques del rival con alguien a ≤ {fc['presion_m']:g} m", "diferencia de fracción")
    presion_tercios(plano, foco, out / "presion_tercios.png")
    esquema_bloque(out / "esquema_bloque.png")
    if bloque is not None and "ancho_visible" in bloque.columns:
        bt = df_.bloque_tipico(ev, bloque, tp, foco, fc["ancho_min"])
        res["bloque_tipico"] = bt
        bloque_tipico(bt, foco, out / "bloque_tipico.png")
    km = fb.curva_recuperacion(posesiones(ev), tp, foco, n_boot=200, seed=cfg["seed"])
    res["curva_recuperacion"] = km
    curva_recuperacion(km, foco, out / "recuperacion.png")
    rv, tabla_rv = _rival(cfg, M, DEF_RIVAL, defs, foco, "propio", fc)
    rvc, tabla_rvc = _rival(cfg, M, ["remates", "xg", "entradas_area"], defs, foco, "rival", fc)
    res["rival"], res["rival_concedido"] = rv, rvc
    md += ["## Según el nivel del rival (G2)", "", tabla_rv, "", "### Lo que le hacen, según quién ataca", "",
           tabla_rvc, ""]
    pct = {}
    for b in res.values():
        if isinstance(b, dict) and "percentiles" in b:
            pct.update(b["percentiles"])
    percentiles({k: v for k, v in pct.items() if k in plano and k != "ancho_visible"}, defs, foco,
                out / "percentiles.png", "Fase defensiva")
    _escribir(out, "defensa", md, res)


# ----------------------------------------------------------------------
# JUGADORES: red, roles, decisiones y sustituciones
# ----------------------------------------------------------------------
def cmd_jugadores(a, cfg):
    from .cli import _equipo_partido, _tabla_fase2, _trans
    from .comparar import tabla
    from .decisiones import leer_eventos, sustituciones
    from .eventos import con_rival
    from .graficas_historia import red_pases
    from .graficas_secciones import efecto_cambios
    from .jugadores import cadena_jugadores, protagonistas
    from .sustituciones import did_cambios, panel_minuto, quien_entra, reacomodo_tras_cambio
    fc = cfg["futbol"]
    foco = _foco(a, cfg)
    K = cfg["fase2"]["K"]
    fams = cfg["fase2"]["familias"]
    ev = _eventos(cfg, con_extra=False)
    M = tabla_liga(cfg)
    tp0 = _equipo_partido(cfg)
    tp = con_rival(tp0)
    out = _dir(cfg, foco, "jugadores")
    t_seq = _tabla_fase2(cfg, foco)
    trans = _trans(cfg)
    res = {"clubes": {}}
    md = [f"# 4. Uso de jugadores — {foco}", "", "Roles dentro del sistema, cambios de alineación e impacto de las "
          "sustituciones (reto 5.3).", ""]
    for club in _clubes(M, foco, fc["min_partidos_club"]):
        partidos = M.filter((pl.col("coach") == foco) & (pl.col("team") == club))["match_id"].unique().to_list()
        cad = cadena_jugadores(ev, partidos, club, fc["min_acciones_jugador"])
        prot = protagonistas(trans, t_seq, partidos, club, K)
        res["clubes"][club] = {"cadena": {k: v for k, v in cad.items() if k != "W"}, "protagonistas": prot}
        if "nota" in cad:
            md += [f"## {club}: {cad['nota']}", ""]
            continue
        red_pases(cad, f"{foco} en {club}: red de pases ({len(partidos)} partidos)", out / f"red_{_slug(club)}.png")
        md += [f"## {club} ({len(partidos)} partidos, {cad['k_grupos']} grupos espectrales)", "",
               "| jugador | puesto | partidos | por quién pasa el balón | P(remate) desde él | grupo |",
               "|---|---|---|---|---|---|"]
        for j in sorted(cad["jugadores"], key=lambda r: -r["flujo"])[:16]:
            md.append(f"| {j['player']} | {j['position']} | {j['partidos']} | {100 * j['flujo']:.1f} % | "
                      f"{j['P_remate_desde']:.3f} | {j['grupo']} |")
        md += ["", "**Protagonistas de cada familia** (fracción de sus acciones · quién las inicia):", ""]
        for k, fam in enumerate(fams):
            e = ", ".join(f"{r['player']} {100 * r['frac_acciones']:.0f} %" for r in prot[k]["ejecutan"][:3])
            i = ", ".join(f"{r['player']} {100 * r['frac_inicios']:.0f} %" for r in prot[k]["inician"][:3])
            md.append(f"- *{fam}*: ejecutan {e} · inician {i}")
        md.append("")
    # decisiones (fase 3b), si ya se corrieron
    dj = cfg.ruta("reportes") / "fase3" / f"decisiones_{_slug(foco)}.json"
    if dj.exists():
        d = json.loads(dj.read_text())
        res["decisiones"] = {k: {c: v.get(c) for c in ("nombre", "p", "q", "etiqueta")}
                             for k, v in d.get("hipotesis", {}).items()}
        md += ["## Decisiones desde la banca (fase 3b, H13–H17)", "", "| id | qué se prueba | p | evidencia |",
               "|---|---|---|---|"]
        md += [f"| {k} | {v['nombre']} | {v['p']:.4f} | {v['etiqueta']} |" for k, v in res["decisiones"].items()]
        md.append("")
    # sustituciones a fondo (G4)
    dec = leer_eventos(ingest.scan_events(cfg.ruta("eventos_parquet")))
    subs = sustituciones(dec, tp0)
    panel = panel_minuto(ev, t_seq, K)
    did = did_cambios(panel, subs, tp, foco, fams, fc["ventana_cambio"], fc["n_boot"], cfg["seed"])
    nombres_med = {"xg_propio": "xG propio", "obv_propio": "OBV propio", "xg_rival": "xG del rival",
                   "field_tilt": "field tilt (dominio territorial)",
                   **{f"fam_{k}": f"fracción de secuencias «{f}»" for k, f in enumerate(fams)}}
    res["sustituciones"] = did
    if did.get("todos"):
        md += [f"## ¿Qué cambia cuando hace un cambio? (dif. en dif. emparejada, ±{did['ventana_min']} min)", "",
               f"{did['n_cambios_foco']} cambios suyos contra {did['n_cambios_liga']} de la liga en el mismo tramo "
               "de 5 minutos y el mismo marcador.", "", "| medida | todos | " +
               " | ".join(did["por_tipo"]) + " |", "|---|---|" + "---|" * len(did["por_tipo"])]
        for mm in did["medidas"]:
            celdas = []
            for bloque_ in [did["todos"], *did["por_tipo"].values()]:
                v = bloque_.get(mm) if bloque_ else None
                celdas.append(f"{v['efecto']:+.3f} [{v['lo']:+.3f}, {v['hi']:+.3f}]" if v else "—")
            md.append(f"| {nombres_med.get(mm, mm)} | " + " | ".join(celdas) + " |")
        efecto_cambios(did, nombres_med, foco, out / "efecto_cambios.png")
    nombres_j = dict(ev.select("player_id", "player").unique("player_id").iter_rows())
    qe = quien_entra(subs, panel, nombres_j, foco)
    res["quien_entra"] = qe
    if qe:
        md += ["", "## Quién entra desde la banca (descriptivo)", "",
               "| jugador | puesto | entradas | minuto medio | xG a favor /90 (con él · antes) | "
               "xG en contra /90 (con él · antes) |", "|---|---|---|---|---|---|"]
        md += [f"| {q['jugador']} | {q['puesto_entra'] or ''} | {q['entradas']} | {q['minuto_medio']:.0f} | "
               f"{q['xg_favor_90_con']:.2f} · {q['xg_favor_90_antes']:.2f} | {q['xg_contra_90_con']:.2f} · "
               f"{q['xg_contra_90_antes']:.2f} |" for q in qe]
    rc = reacomodo_tras_cambio(subs, dec["shift"], tp, foco, fc["ventana_shift"], fc["n_boot"], cfg["seed"])
    res["reacomodo_tras_cambio"] = rc
    if "foco" in rc:
        md += ["", f"**¿El cambio viene con cambio de dibujo?** {100 * rc['foco']:.0f} % de sus cambios van seguidos "
               f"de un reacomodo en ≤ {rc['ventana_min']} min, contra {100 * rc['liga']:.0f} % en la liga "
               f"({100 * rc['dif']:+.1f} pp [{100 * rc['lo']:+.1f}, {100 * rc['hi']:+.1f}]).", ""]
    if did.get("todos"):
        H = {m: {"p": did["todos"][m]["p"], "partidos_foco": 99} for m in ("xg_propio", "obv_propio", "xg_rival")}
        res["hipotesis"] = _hipotesis({"H23": ("sus cambios cambian el juego distinto que los de la liga",
                                                ["xg_propio", "obv_propio", "xg_rival"])}, H)
        md += _tabla_hipotesis(res["hipotesis"], {k: {"nombre": v} for k, v in nombres_med.items()})
    if "estabilidad_once__n" in M.columns:
        r = _bloque(M, ["estabilidad_once"], foco, "propio", fc, cfg["seed"])
        r["estabilidad_once"]["etiqueta"] = "🔎"
        res["estabilidad_once"] = r
        md += ["## Estabilidad del once (Jaccard con el partido anterior)", "",
               "🔎 Exploratoria: como H17, se confunde con el calendario (Copa, Concachampions no están en los datos).",
               "", tabla(r, None, _percentiles(M, ["estabilidad_once"], foco, "propio", fc["min_partidos_era"]),
                         {"estabilidad_once": {"nombre": "once repetido (Jaccard)", "formato": "{:.3f}"}})]
    _escribir(out, "jugadores", md, res)


# ----------------------------------------------------------------------
# BALÓN PARADO
# ----------------------------------------------------------------------
BP_TITULOS = {"corner_favor": "A favor: cuántos, cuánto remate y cuánto xG", "corner_rutina": "A favor: cómo los cobra",
              "corner_contra": "En contra: lo que le generan", "corner_org": "En contra: cómo se para (360)",
              "tl_favor": "A favor", "tl_contra": "En contra", "tl_org": "En contra: la línea y la barrera (360)",
              "lat_favor": "A favor", "lat_contra": "En contra"}
H_BP = {"H24": ("prevención: niega remates en centros a balón parado más que la liga", ["xd_prev"]),
        "H25": ("supresión: empeora los remates que concede más que la liga", ["xd_remate"]),
        "H26": ("se organiza distinto que la liga (marca, línea, trampa)",
                ["al_hombre", "dist_marca", "altura_linea_tl", "fuera_juego_tl"])}
CORNER_FAVOR = ["n_corner", "remate_corner", "xg_corner"]
CORNER_ORG = ["de_area_corner", "de_chica_corner", "palo_cercano", "palo_lejano", "al_hombre", "dist_marca", "sobra",
              "primer_contacto_def"]
TL_FAVOR = ["n_tl_directo", "n_tl_centrado", "n_tl_otro", "tl_peligro", "xg_tl_directo", "remate_tl_centrado",
            "xg_tl_centrado", "remate_tl_otro", "xg_tl_otro"]
TL_ORG = ["altura_linea_tl", "en_linea_tl", "fuera_juego_tl", "arco_libre_tl", "barrera_tl"]
LAT_FAVOR = ["lat_cuarto", "lat_cuarto_area", "lat_cuarto_remate", "lat_cuarto_xg", "lat_segunda", "n_lateral_largo",
             "remate_lateral_largo", "xg_lateral_largo"]


def _sub(md: list[str]) -> list[str]:
    """Baja un nivel los títulos de `_comparar_bloques` (## → ###) para las subsecciones 5.x."""
    return [("#" + x) if x.startswith("## ") else x for x in md]


def _ic(r: dict, f: str = "{:+.2f}", e: float = 1.0) -> str:
    if not r or not np.isfinite(r.get("valor", np.nan)):
        return "—"
    return f"{f.format(e * r['valor'])} [{f.format(e * r['lo'])}, {f.format(e * r['hi'])}]"


def _md_cadena(cad: dict, claves: dict[str, str], foco: str) -> list[str]:
    """La cadena C → S → G y los cuatro términos por grupo (foco a favor, foco en contra, liga)."""
    nom = {"foco_ataque": f"{foco} a favor (xO)", "foco_defensa": f"{foco} en contra (xD)", "liga": "liga"}
    L = ["| jugada | quién | saques | P(remate) real · esperada | goles por saque con remate: real · κ | "
         "goles por 100: real · esperados | prevención | alejamiento | supresión | portero | **total** |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c, etq in claves.items():
        for g in ("foco_ataque", "foco_defensa", "liga"):
            r = cad.get(c, {}).get(g)
            if not r:
                continue
            t = ["—"] * 5 if g == "liga" else [_ic(r[x]) for x in ("prev", "lej", "sup", "port", "total")]
            L.append(f"| {etq} | {nom[g]} | {r['saques']:,} | {100 * r['p_obs']:.1f} % · {100 * r['p_esp']:.1f} % | "
                     f"{r['v_obs']:.3f} · {r['v_kappa']:.3f} | {100 * r['g_obs']:.2f} · {100 * r['g_esp']:.2f} | "
                     + " | ".join(t[:4]) + f" | **{t[4]}** |")
    return L + ["", "*Términos en goles por cada 100 saques respecto de lo esperado con una defensa (o un ataque) "
                "promedio de la liga; positivo = bueno para " + foco + ". La liga es la referencia: sus términos son "
                "≈ 0 por construcción.*", ""]


def _md_etapa(E, foco: str, tit: str, n_etq: str) -> list[str]:
    if E is None or E.height == 0:
        return []
    fila = E.with_row_index("puesto", 1).filter(pl.col("coach") == foco).to_dicts()
    tau2 = float(E["tau2"][0])
    L = [f"**{tit}** — contracción empírico-bayesiana entre {E.height} técnicos-club (media μ = {float(E['mu'][0]):+.4f}; "
         f"τ² = {tau2:.2e}; τ² ≈ 0 = no se detecta variación real entre equipos):", ""]
    if tau2 <= 0:
        L += ["*τ² = 0: todos se contraen a la media y el puesto no significa nada.*", ""]
    L += [f"- {f['team']}: crudo {f['theta']:+.4f} ± {1.96 * np.sqrt(f['var']):.4f}, contraído {f['contraido']:+.4f} "
          f"{n_etq} (confiabilidad {f['confiabilidad']:.2f}; puesto {f['puesto']} de {E.height}, 1 = el mejor)"
          for f in fila]
    return L + [""]


def _tasas(j, tp, foco, tipos, res) -> list[str]:
    from . import balon_parado as bp
    L = ["| tipo | qué | lado | foco | liga | razón [IC 95 %] | p | dispersión |", "|---|---|---|---|---|---|---|---|"]
    for tipo in tipos:
        for que in ("remates", "goles"):
            for lado in ("propio", "rival"):
                r = bp.razon_de_tasas(j, tp, foco, tipo, que, lado)
                if "razon" not in r:
                    continue
                res.append(r)
                L.append(f"| {bp.NOMBRE[tipo]} | {que} por jugada | {'a favor' if lado == 'propio' else 'en contra'} | "
                         f"{r['tasa_foco']:.3f} | {r['tasa_liga']:.3f} | {r['razon']:.2f} [{r['lo']:.2f}, "
                         f"{r['hi']:.2f}] | {r['p']:.4f} | {r['dispersion_pearson']:.2f} |")
    return L + ["", "*Poisson con exposición (número de jugadas) y varianza sandwich por partido.*", ""]


def _prueba(pruebas: list, id_: str, afirmacion: str, p: float, efecto: float | None = None, lo=None, hi=None,
            partidos: int | None = None, tipo: str = "diferencia") -> None:
    """Una afirmación con su prueba formal; `dtcoach demostracion` la corrige junto con todo lo demás."""
    if p is None or not np.isfinite(p):
        return
    pruebas.append({"id": id_, "afirmacion": afirmacion, "p": float(p), "tipo": tipo,
                    "efecto": None if efecto is None else float(efecto), "lo": None if lo is None else float(lo),
                    "hi": None if hi is None else float(hi), "partidos_foco": partidos})


def _pruebas_cadena(cad: dict, foco: str, pruebas: list) -> None:
    nom = {"prev": "prevención", "lej": "alejamiento", "sup": "supresión", "port": "portero y definición",
           "total": "total"}
    for clave, gs in cad.items():
        for g in ("foco_ataque", "foco_defensa"):
            r = gs.get(g)
            if not r:
                continue
            for c, n in nom.items():
                t = r.get(c, {})
                if clave == "tl_directo" and c == "prev":
                    continue                                    # el directo no tiene capa 1: vale 0 por definición
                _prueba(pruebas, f"cadena/{clave}/{g}/{c}",
                        f"{'xO' if g == 'foco_ataque' else 'xD'} {n} en {clave} "
                        f"({'a favor' if g == 'foco_ataque' else 'en contra'}) distinto de 0 (goles por 100 saques)",
                        t.get("p"), t.get("valor"), t.get("lo"), t.get("hi"), r.get("partidos"))


def cmd_balon_parado(a, cfg):
    from . import balon_parado as bp
    from . import graficas_secciones as gs
    from . import xdefensa as xd
    from .graficas_historia import densidad_balon_parado
    fc = cfg["futbol"]
    foco = _foco(a, cfg)
    M = tabla_liga(cfg)
    tp = _tp(cfg)
    out = _dir(cfg, foco, "balon_parado")
    rb = _rutas_bp(cfg)
    j = pl.read_parquet(rb["jugadas"])
    D = pl.read_parquet(rb["cadena"]) if rb["cadena"].exists() else None
    p2 = pl.read_parquet(rb["capa2"]) if rb["capa2"].exists() else None
    defs = {**bp.DEFINICIONES, **xd.DEFINICIONES, **xd.DEFINICIONES_CADENA}
    nb, seed, mp = min(fc["n_boot"], 500), cfg["seed"], fc["min_partidos_era"]
    res, plano, tasas, pruebas = {}, {}, [], []
    fam_nom = {"corner": "corners", "tiro_libre": "tiros libres", "lateral": "laterales"}

    def comparar(bloques):
        r, m = _comparar_bloques(M, bloques, defs, foco, fc, seed, BP_TITULOS)
        res.update(r)
        plano.update(_plano(r))
        return _sub(m)

    def etapa(m, tit, etq, lado="propio", fig=True, varianza="comun"):
        if f"{m}__n" not in M.columns:
            return None, []
        E = xd.por_etapa(M, m, lado, mp, varianza)
        if E.height == 0:
            return None, []
        E.write_csv(out / f"etapas_{m}.csv")
        res[f"etapas_{m}"] = {"mu": float(E["mu"][0]), "tau2": float(E["tau2"][0]), "p_Q": float(E["p_Q"][0]),
                              "etapas": E.height,
                              "foco": E.with_row_index("puesto", 1).filter(pl.col("coach") == foco).to_dicts()}
        _prueba(pruebas, f"heterogeneidad/{m}", f"los {E.height} técnicos-club difieren de verdad en «{tit}» "
                f"(τ² > 0; si no, el puesto no significa nada)", float(E["p_Q"][0]), float(E["tau2"][0]),
                tipo="heterogeneidad")
        if fig:
            gs.xdefensa_etapas(E, foco, out / f"{m}_etapas.png", tit, etq)
        return E, _md_etapa(E, foco, tit, etq)

    cad = xd.cadena(D, tp, foco, nb, seed) if D is not None and D.height else {}
    res["cadena"] = cad
    _pruebas_cadena(cad, foco, pruebas)
    md = [f"# 5. Balón parado — {foco}", "",
          "Corners, tiros libres y laterales, **a favor y en contra**, comparados con la liga (reto 5.4). "
          "Definiciones: 03_FRAMEWORK §6; el xDefense, 04_MODELO_MATEMATICO §16.", ""]

    # ------------------------------------------------------------------ 5.1 el xDefense
    md += ["## 5.1 El xDefense: nuestra métrica, y cómo se calcula", "",
           "**El xDefense es una métrica propia del equipo** (trabajo previo de xDefense de corners, extendido aquí a "
           "toda la liga, a los tres tipos de balón parado y al ataque). Parte un gol en dos preguntas: ¿te rematan? "
           "(capa 1, prevención) y, si te rematan, ¿el remate entra? (capa 2, supresión). Sumando y restando, lo "
           "que evita una defensa se parte **exactamente** en cuatro términos: prevención, alejamiento, supresión y "
           "portero (04 §16.5–16.6).", ""]
    for fam, nom in (("corner", "corner"), ("tiro_libre", "tiro libre"), ("lateral", "lateral")):
        gs.arbol_xdefensa(cad, foco, fam, nom, out / f"arbol_{fam}.png")
    gs.goal_open_esquema(out / "goal_open_esquema.png")
    if rb["xdefensa"].exists():
        cap = json.loads(rb["xdefensa"].read_text())
        res["modelos_xdefensa"] = cap
        c1, c2, c1o = cap["capa1"], cap["capa2"], cap.get("capa1_otros", {})
        md += ["### Los modelos (toda la liga, fuera de muestra)", "",
               f"- **Capa 1, centros al área** (corners, tiros libres y laterales al área; el modelo de H24): "
               f"{c1['centros']:,} saques, {100 * c1['tasa_remate']:.1f} % con remate; AUC {c1['auc_fuera_de_muestra']:.3f}; "
               f"calibración {c1['calibracion']:.3f} (1 = perfecta)."]
        if "auc_fuera_de_muestra" in c1o:
            md.append(f"- **Capa 1, saques que no van al área** (tiros libres cortos y laterales del último cuarto; "
                      f"modelo aparte, para no tocar el de H24): {c1o['centros']:,} saques, {100 * c1o['tasa_remate']:.1f} % con "
                      f"remate; AUC {c1o['auc_fuera_de_muestra']:.3f}; calibración {c1o['calibracion']:.3f}.")
        md += [f"- **Capa 2:** {c2['remates']:,} remates con foto ({c2['remates_bp']:,} a balón parado, "
               f"{c2['goles_bp']} goles); AUC sin defensa {c2['auc_base']:.3f} → con defensa {c2['auc_full']:.3f} "
               f"(ΔAUC {c2['delta_auc']:+.3f} [{c2['delta_auc_lo']:+.3f}, {c2['delta_auc_hi']:+.3f}]). Dirección de la "
               "geometría defensiva (coeficientes en desviaciones estándar): " +
               ", ".join(f"{x['rasgo']} {x['coef_de']:+.2f}" for x in c2["coeficientes_full"] if x["rasgo"] in xd.DEFENSA),
               "- **κ (goles que vale un saque con remate, liga):** " +
               ", ".join(f"{bp.NOMBRE.get(t, t)} {v:.3f}" for t, v in sorted(cap.get("kappa", {}).items())), ""]
    if cad:
        md += ["### La cadena de cada familia", ""] + _md_cadena(cad, {f: fam_nom[f] for f in xd.FAMILIAS} |
                                                              {"todas": "todo"}, foco)
        gs.descomposicion(cad, foco, out / "descomposicion.png", fam_nom)
    md += ["### Las hipótesis pre-registradas del xDefense (centros al área, H24 y H25)", ""]
    md += comparar({"xdefensa": ("propio", ["xd_prev", "xd_remate", "xd_gol"])})
    # H24 y H25: como se corrieron en la fase G (varianza propia de cada etapa)
    Ep, L1 = etapa("xd_prev", "Capa 1 · prevención: remates evitados por centro en contra", "remates evitados por centro",
                   varianza="propia")
    Es, L2 = etapa("xd_remate", "Capa 2 · supresión: xG que su defensa le quita a cada remate", "xG quitado por remate",
                   varianza="propia")
    md += L1 + L2
    gs.mapa_xdefensa(Ep, Es, foco, out / "mapa_xdefensa.png", "prevención (remates evitados por centro)",
                     "supresión (xG quitado por remate)")
    of = _bloque(M, ["xo_prev"], foco, "propio", fc, seed)
    res["xo_prev"] = of
    if "xo_prev" in of:
        v = of["xo_prev"]
        md += [f"**Ejecución ofensiva** (remates generados por encima de lo esperado por centro propio): "
               f"{v['foco']:+.4f} contra {v['liga']:+.4f} ({v['dif']:+.4f} [{v['lo']:+.4f}, {v['hi']:+.4f}]) "
               f"{v.get('etiqueta', '')}", ""]

    # ------------------------------------------------------------------ 5.2 corners
    md += ["## 5.2 Corners", ""]
    md += comparar({"corner_favor": ("propio", CORNER_FAVOR), "corner_rutina": ("propio", bp.RUTINA_BP),
                    "corner_contra": ("rival", CORNER_FAVOR), "corner_org": ("propio", CORNER_ORG)})
    md += ["### Remates y goles por corner", ""] + _tasas(j, tp, foco, ["corner"], tasas)
    if cad:
        md += ["### El xDefense de los corners (a favor y en contra)", ""] + _md_cadena(cad, {"corner": "corner"}, foco)
    for m, tit, etq in (("xd_total_corner", "Corners en contra · goles evitados (xD total)", "goles evitados por 100 corners"),
                        ("xo_total_corner", "Corners a favor · goles de más (xO total)", "goles de más por 100 corners"),
                        ("xd_prev_corner", "Corners en contra · prevención", "goles evitados por 100 corners"),
                        ("xd_sup_corner", "Corners en contra · supresión", "goles evitados por 100 corners")):
        md += etapa(m, tit, etq)[1]
    # marca al hombre contra remates concedidos, técnico por técnico
    if "al_hombre__n" in M.columns and "remate_corner__n" in M.columns:
        A = xd.por_etapa(M, "al_hombre", "propio", mp)
        B = xd.por_etapa(M, "remate_corner", "rival", mp)
        if A.height and B.height:
            Dd = A.select("coach", "team", pl.col("theta").alias("x")).join(
                B.select("coach", "team", pl.col("theta").alias("y")), on=["coach", "team"])
            from scipy import stats as st
            if Dd.height >= 5:
                rr, pp = st.pearsonr(Dd["x"].to_numpy(), Dd["y"].to_numpy())
                res["marca_vs_remate"] = {"r": float(rr), "p": float(pp), "etapas": Dd.height}
                _prueba(pruebas, "correlacion/marca_vs_remate", "entre técnicos, marcar más al hombre se asocia con "
                        "conceder menos remates por corner", float(pp), float(rr), tipo="correlacion")
            gs.dispersion_etapas(Dd.with_columns(pl.col("x") * 100, pl.col("y") * 100), foco,
                                 out / "marca_vs_remate.png", "% de defensores del área marcando al hombre",
                                 "% de corners en contra que terminan en remate",
                                 "¿Marcar al hombre evita remates en los corners en contra?",
                                 "Cada punto es un técnico en un club. Asociación entre técnicos, no causa.")
    rut = bp.rutinas(j, tp, foco, nb, seed)
    res["rutinas"] = rut
    for r in rut["rutinas"]:
        _prueba(pruebas, f"rutina/{r['tecnica']}/{r['zona']}", f"en la liga, el corner {r['tecnica']} → "
                f"{bp.ZONA_NOMBRE.get(r['zona'], r['zona'])} rinde distinto que el resto (xG por corner)",
                r["p"], r["xg_por_corner"] - r["xg_resto"], r["lo"] - r["xg_resto"], r["hi"] - r["xg_resto"])
    if "receta_arsenal" in rut:
        ra = rut["receta_arsenal"]
        _prueba(pruebas, "arsenal/ventaja", "la receta Arsenal rinde distinto que el resto de los corners de la liga",
                ra["p"], ra["dif"], ra["lo"], ra["hi"])
        _prueba(pruebas, "arsenal/equivalencia", f"la receta Arsenal rinde igual que el resto (± {ra['margen']:.3f} xG "
                "por corner; prueba de equivalencia TOST)", ra["p_tost"], ra["dif"], ra["lo90"], ra["hi90"],
                tipo="equivalencia")
    gs.rutinas_corner(rut, foco, out / "rutinas_corner.png", bp.ZONA_NOMBRE)
    md += ["### ¿Qué corners funcionan en la Liga MX? (rutina = técnica × destino)", "",
           "| rutina | corners en la liga | xG por corner [IC 95 %] | remate | uso liga | uso foco |",
           "|---|---|---|---|---|---|"]
    md += [f"| {r['tecnica']} → {bp.ZONA_NOMBRE.get(r['zona'], r['zona'])} | {r['corners_liga']:,} | "
           f"{r['xg_por_corner']:.3f} [{r['lo']:.3f}, {r['hi']:.3f}] | {100 * r['remate']:.0f} % | "
           f"{100 * r['uso_liga']:.0f} % | {100 * r['uso_foco']:.0f} % |" for r in rut["rutinas"]]
    if "receta_arsenal" in rut:
        ra = rut["receta_arsenal"]
        md += ["", f"**La receta Arsenal en la Liga MX** (corner cerrado al área chica o primer palo con atacantes "
               f"encima del portero): {ra['corners']:,} corners, {ra['xg_receta']:.3f} xG por corner contra "
               f"{ra['xg_resto']:.3f} del resto ({ra['dif']:+.3f} [{ra['lo']:+.3f}, {ra['hi']:+.3f}], "
               f"p = {ra['p']:.3f}). {foco} la usa en {100 * ra['uso_foco']:.0f} % de sus corners; la liga en "
               f"{100 * ra['uso_liga']:.0f} %."]
    md.append("")
    perfil = bp.perfil_defensivo(j, tp, foco, fc["cobertura_min"])
    res["perfil_defensivo"] = perfil
    gs.corner_defensivo(perfil, foco, out / "corner_defensivo.png")

    # ------------------------------------------------------------------ 5.3 tiros libres
    md += ["## 5.3 Tiros libres", ""]
    md += comparar({"tl_favor": ("propio", TL_FAVOR), "tl_contra": ("rival", TL_FAVOR), "tl_org": ("propio", TL_ORG)})
    directos = None
    if p2 is not None and "barrera" in p2.columns:
        directos = p2.select("match_id", "id", "goal_open", "barrera")
    rtl = bp.resumen_tiros_libres(j, directos, tp, foco, nb, seed)
    res["tiros_libres"] = rtl
    gs.tiros_libres(rtl, foco, out / "tiros_libres.png")
    nom = {"foco_ataque": f"{foco} a favor", "foco_defensa": f"{foco} en contra", "liga": "liga (cada equipo)"}
    md += ["### Cuántos, dónde y cómo se juegan", "",
           "| quién | por partido | a ≤ 30 m por partido | de esos: directo · al área · corto | distancia del directo | "
           "xG por directo | goles por 100 directos | arco libre en el directo | en la barrera |",
           "|---|---|---|---|---|---|---|---|---|"]
    for g in ("foco_ataque", "foco_defensa", "liga"):
        r = rtl.get(g)
        if not r:
            continue
        rp, di = r["reparto_peligrosos"], r["directo"]
        md.append(f"| {nom[g]} | {r['por_partido']:.2f} | {r['peligrosos_por_partido']:.2f} | "
                  f"{100 * rp['tl_directo']:.0f} · {100 * rp['tl_centrado']:.0f} · {100 * rp['tl_otro']:.0f} % | "
                  f"{_ic(di['dist'], '{:.1f}')} | {_ic(di['xg'], '{:.3f}')} | {_ic(di['gol'], '{:.1f}', 100)} | "
                  f"{_ic(di.get('goal_open'), '{:.0f}', 100)} % | {_ic(di.get('barrera'), '{:.1f}')} |")
    md += ["", "*En contra, la barrera y el arco libre son de SU defensa. Arco libre = fracción del arco que ve el que "
           "cobra, descontando la sombra de la barrera y de los defensores (capa 2).*", ""]
    md += ["### Remates y goles por tiro libre", ""] + _tasas(j, tp, foco, ["tl_directo", "tl_centrado", "tl_otro"], tasas)
    if cad:
        md += ["### El xDefense de los tiros libres", ""] + _md_cadena(
            cad, {"tiro_libre": "tiros libres (todos)", "tl_directo": "directo", "tl_centrado": "al área",
                  "tl_otro": "corto / a la banda"}, foco)
    for m, tit, etq in (("xd_total_tiro_libre", "Tiros libres en contra · goles evitados (xD total)",
                         "goles evitados por 100 tiros libres"),
                        ("xo_total_tiro_libre", "Tiros libres a favor · goles de más (xO total)",
                         "goles de más por 100 tiros libres")):
        md += etapa(m, tit, etq)[1]
    if "altura_linea_tactica" in j.columns:
        tl = (j.filter(pl.col("tipo").is_in(["tl_centrado", "tl_otro"]) & pl.col("altura_linea_tactica").is_not_nan())
              .join(tp.select("match_id", "team", "coach", "coach_rival"), on=["match_id", "team"]))
        pf = tl.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique().to_list()
        gs.linea_tiros_libres(tl.filter(pl.col("coach_rival") == foco)["altura_linea_tactica"].to_numpy(),
                              tl.filter(~pl.col("match_id").is_in(pf))["altura_linea_tactica"].to_numpy(), foco,
                              out / "linea_tiros_libres.png")

    # ------------------------------------------------------------------ 5.4 laterales
    x0, x8 = fc["lateral_cuarto_x"], fc.get("lateral_octavo_x", 105.0)
    md += [f"## 5.4 Laterales en el último cuarto (x ≥ {x0:.0f} m) y en el último octavo (x ≥ {x8:.0f} m)", ""]
    md += comparar({"lat_favor": ("propio", LAT_FAVOR), "lat_contra": ("rival", LAT_FAVOR)})
    rl = bp.resumen_laterales(j, tp, foco, x0, x8, nb, seed)
    res["laterales"] = rl
    for tramo in ("cuarto", "octavo"):
        for g in ("foco_ataque", "foco_defensa"):
            c = rl[tramo].get(g, {}).get("chica_segunda", {})
            _prueba(pruebas, f"laterales/{tramo}/{g}/chica_2mas", f"laterales del último {tramo} "
                    f"{'a favor' if g == 'foco_ataque' else 'en contra'} que caen en el área chica y acaban en remate con "
                    "≥ 2 que intervienen: distinto de la liga (Fisher exacta)", c.get("p_fisher"),
                    c.get("remate_2mas", 0) / max(c.get("de_todos", 1), 1), partidos=None)
    for tramo in ("cuarto", "octavo"):
        gs.laterales(rl, foco, out / f"laterales_{tramo}.png", tramo)
        md += [f"### Desde el último {tramo} (x ≥ {x0 if tramo == 'cuarto' else x8:.0f} m)", "",
               "| quién | por partido | al área | al área chica | primer toque propio | con remate | "
               "remate con ≥ 2 que intervienen | gol | xG por lateral | intervienen hasta el remate (1 · 2 · 3+) |",
               "|---|---|---|---|---|---|---|---|---|---|"]
        for g in ("foco_ataque", "foco_defensa", "liga"):
            r = rl[tramo].get(g)
            if not r:
                continue
            iv = r["intervienen"]
            md.append(f"| {nom[g]} | {r['por_partido']:.2f} | {_ic(r['al_area'], '{:.1f}', 100)} % | "
                      f"{_ic(r['area_chica'], '{:.1f}', 100)} % | {_ic(r['primer_contacto'], '{:.1f}', 100)} % | "
                      f"{_ic(r['remate'], '{:.1f}', 100)} % | {_ic(r['segunda'], '{:.1f}', 100)} % | "
                      f"{_ic(r['gol'], '{:.2f}', 100)} % | {_ic(r['xg'], '{:.3f}')} | {iv['1']} · {iv['2']} · {iv['3+']} |")
        md += ["", "**Caen en el área chica y terminan en remate con ≥ 2 que intervienen** (lo que pide el reto):", ""]
        for g in ("foco_ataque", "foco_defensa", "liga"):
            r = rl[tramo].get(g)
            if r:
                c = r["chica_segunda"]
                md.append(f"- {nom[g]}: {c['laterales']:,} laterales al área chica → {c['remate']:,} con remate, "
                          f"{c['remate_2mas']:,} de ellos con ≥ 2 que intervienen; {c['goles']} goles.")
        md.append("")
    md += ["### Remates y goles por lateral", ""] + _tasas(j, tp, foco, ["lateral_largo", "lateral_zona"], tasas)
    if cad:
        md += ["### El xDefense de los laterales", ""] + _md_cadena(
            cad, {"lateral": "laterales (todos)", "lateral_largo": "al área", "lateral_zona": "no al área"}, foco)
    for m, tit, etq in (("xd_total_lateral", "Laterales en contra · goles evitados (xD total)",
                         "goles evitados por 100 laterales"),
                        ("xo_total_lateral", "Laterales a favor · goles de más (xO total)", "goles de más por 100 laterales")):
        md += etapa(m, tit, etq)[1]

    # ------------------------------------------------------------------ zonas y cierre
    for tipo in ("corner", "tl_centrado", "lateral_largo"):
        for lado in ("propio", "rival"):
            mp_ = bp.mapas(j, tp, foco, tipo, lado)
            densidad_balon_parado(mp_, foco, bp.NOMBRE[tipo], lado, out / f"zonas_{tipo}_{lado}.png")
    res["tasas"] = tasas
    for r in tasas:
        _prueba(pruebas, f"tasa/{r['tipo']}/{r['que']}/{r['lado']}", f"{r['que']} por {bp.NOMBRE[r['tipo']]} "
                f"{'a favor' if r['lado'] == 'propio' else 'en contra'}: razón foco / liga distinta de 1", r["p"],
                r["razon"], r["lo"], r["hi"], r.get("partidos_foco"))
    res["pruebas"] = pruebas
    res["hipotesis"] = _hipotesis(H_BP, plano)
    md += _tabla_hipotesis(res["hipotesis"], defs)
    md += [f"*Además de H24–H26, esta sección hace {len(pruebas)} pruebas formales (cadena, heterogeneidad, rutinas, "
           "receta Arsenal, laterales, tasas) y todas sus comparaciones de métricas. Ninguna se da por buena aquí: "
           "`dtcoach demostracion` las corrige TODAS juntas con las del resto de la historia (un solo Benjamini-"
           "Hochberg) y solo lo que sobrevive se narra (11_HIPOTESIS, regla de demostración).*", ""]
    _escribir(out, "balon_parado", md, res)


# ----------------------------------------------------------------------
# SIMULACIÓN: simulador de partido, puntos esperados y proyección
# ----------------------------------------------------------------------
def cmd_simular(a, cfg):
    from .cli import _tabla_fase2
    from .graficas_historia import simulacion as fig_sim
    from .graficas_secciones import proyeccion as fig_proy
    from .proyeccion import base, proyectar
    from .simulacion import Parametros, estadisticos, partido_real, simular, validar_liga
    from .simulador import resumen_xpts, xpts_por_equipo_partido
    fc = cfg["futbol"]
    pc = cfg["proyeccion"]
    foco = _foco(a, cfg)
    K = cfg["fase2"]["K"]
    out = _dir(cfg, foco, "simulacion")
    tp = _tp(cfg)
    t_seq = _tabla_fase2(cfg, foco)
    par = Parametros(estadisticos(t_seq, K), tp, K, fc["sim_a"])
    x = xpts_por_equipo_partido(ingest.scan_events(cfg.ruta("eventos_parquet")), tp)
    resultados = (x.select("match_id", "team", pl.col("gf").alias("goles"), pl.col("gc").alias("goles_rival"))
                  .join(tp.select("match_id", "team", "rival"), on=["match_id", "team"]))
    print("validación en toda la liga (dejando cada partido fuera)...", flush=True)
    val = validar_liga(par, resultados, fc["sim_validacion_rep"], cfg["seed"])
    mios = resultados.join(tp.select("match_id", "team", "coach"), on=["match_id", "team"]).filter(
        pl.col("coach") == foco)
    filas = []
    for i, (mid, team, g, gr, rival, _) in enumerate(mios.iter_rows()):
        s = partido_real(par, mid, team, rival, fc["sim_rep"], cfg["seed"] + i)
        obs = "gana" if g > gr else ("empata" if g == gr else "pierde")
        filas.append({"match_id": mid, "team": team, "rival": rival, "marcador": f"{g}-{gr}", "resultado": obs,
                      "P_resultado": s[f"P_{obs}"], "xPts_estilo": s["xPts"], "puntos": 3 * (g > gr) + (g == gr),
                      "P_domina_xg": s["P_domina_xg"]})
    tab = pl.DataFrame(filas).sort("P_resultado")
    tab.write_csv(out / "simulacion_partidos.csv")
    tipo = {}
    for club in tab["team"].unique().to_list():
        e = (foco, club)
        s = simular(par.combinar(par.etapa(e, "ataque"), par.liga), par.combinar(par.liga, par.etapa(e, "concede")),
                    fc["sim_rep"], cfg["seed"])
        tipo[club] = s
        fig_sim(s, f"{foco} ({club}) contra un rival promedio de la liga: {fc['sim_rep']:,} repeticiones",
                out / f"partido_tipo_{_slug(club)}.png")
    rx = resumen_xpts(x, foco)
    res = {"validacion_liga": val, "partido_tipo": tipo, "xpts": rx,
           "resumen_foco": {"partidos": tab.height, "puntos": int(tab["puntos"].sum()),
                            "xPts_estilo": float(tab["xPts_estilo"].sum()),
                            "P_domina_xg_media": float(tab["P_domina_xg"].mean())},
           "mas_sorprendentes": tab.head(8).to_dicts()}
    f_ = rx["foco"]
    md = [f"# 6. Simulación — {foco}", "", "Herramientas para EXPLICAR el juego, no para apostar (reto 06).", "",
          "## Puntos: lo que hizo contra lo que merecía", "",
          f"- **Por la calidad de sus ocasiones (xPts, Poisson-binomial exacta):** {f_['puntos']} puntos en "
          f"{f_['partidos']} partidos contra {f_['xPts']:.1f} esperados ({f_['dif']:+.1f}, z = {f_['z']:+.2f}, "
          f"p = {f_['p']:.3f}). Validación en la liga: error relativo {100 * rx['validacion']['error_relativo']:.2f} %.",
          f"- **Por su estilo (simulador de partido):** {res['resumen_foco']['xPts_estilo']:.1f} esperados. Validación "
          f"en la liga dejando cada partido fuera: Brier {val['brier']:.3f} contra {val['brier_frecuencias']:.3f} de "
          f"las frecuencias base (habilidad {100 * val['habilidad']:.1f} %).", "",
          "## Su partido tipo (contra un rival promedio)", ""]
    for club, s in tipo.items():
        md.append(f"- Con su estilo en {club}: gana {100 * s['P_gana']:.0f} %, empata {100 * s['P_empata']:.0f} %, "
                  f"pierde {100 * s['P_pierde']:.0f} %; xG {s['xg_A']:.2f}–{s['xg_B']:.2f}.")
    md += ["", "**Resultados menos probables según el estilo:**", "", "| partido | rival | marcador | P(ese resultado) |",
           "|---|---|---|---|"]
    md += [f"| {r['match_id']} | {r['rival']} | {r['marcador']} | {100 * r['P_resultado']:.0f} % |"
           for r in res["mas_sorprendentes"]]
    # proyección en su club actual (G6)
    print("proyección en su club actual (y validación con todas las llegadas de la liga)...", flush=True)
    b = base(x, tp)
    pr = proyectar(b, foco, pc["n_pre"], pc["n_post"], pc["n_sim"], pc["directos"], tuple(pc["play_in"]),
                   cfg["seed"])
    res["proyeccion"] = {k: v for k, v in pr.items() if k != "validacion"} | {
        "validacion": {k: v for k, v in (pr.get("validacion") or {}).items() if k not in ("pred", "real")}}
    fig_proy(pr, out / "proyeccion.png")
    e, c, ef = pr["escenarios"], pr["contraste_real"], pr["efecto"]
    v = pr.get("validacion") or {}
    md += ["", f"## Proyección: {foco} en {pr['club']} con los jugadores que encontró", "",
           f"Llegó el {pr['llegada']}. El plantel que encontró (sus últimos {pr['n_pre']} partidos antes): ataque "
           f"{pr['plantel_A']:.2f} y defensa {pr['plantel_D']:.2f} (1 = promedio de la liga; defensa < 1 = concede "
           "menos).", "",
           f"Su efecto al llegar a un club, medido en {ef['llegadas_suyas']} llegada(s) anteriores ({', '.join(ef['clubes'])}) "
           f"y contraído hacia la media de {ef['llegadas_liga']} llegadas de la liga: ataque "
           f"{100 * (np.exp(ef['ataque']['contraido']) - 1):+.0f} % de xG (liga "
           f"{100 * (np.exp(ef['ataque']['mu_liga']) - 1):+.0f} %), defensa "
           f"{100 * (np.exp(ef['defensa']['contraido']) - 1):+.0f} % de xG concedido (liga "
           f"{100 * (np.exp(ef['defensa']['mu_liga']) - 1):+.0f} %).", "",
           "| escenario | xG a favor/partido | xG en contra/partido | puntos (p10–p90) | posición media | "
           "P(liguilla directa) | P(play-in) |", "|---|---|---|---|---|---|---|"]
    for n, lab in (("con_el", f"con {foco}"), ("inercia", "solo el plantel (inercia de una llegada cualquiera)")):
        s = e[n]
        md.append(f"| {lab} | {s['xg_favor_partido']:.2f} | {s['xg_contra_partido']:.2f} | {s['pts_media']:.1f} "
                  f"({s['pts_p10']:.0f}–{s['pts_p90']:.0f}) | {s['pos_media']:.1f} | {100 * s['P_directo']:.0f} % | "
                  f"{100 * s['P_play_in']:.0f} % |")
    md += ["", f"**Contra lo que ya pasó** ({c['partidos']} partidos reales en {pr['club']}): proyectado "
           f"{c['proy_pts_media']:.1f} puntos (80 %: {c['proy_pts_p10']:.0f}–{c['proy_pts_p90']:.0f}), xG "
           f"{c['proy_xg_favor']:.1f}–{c['proy_xg_contra']:.1f}; real {c['pts_reales']:.0f} puntos, xG "
           f"{c['xg_favor_real']:.1f}–{c['xg_contra_real']:.1f}.", ""]
    pruebas = []
    _prueba(pruebas, "xpts/foco", f"{foco} sacó más puntos de los que valían sus ocasiones (xPts)", f_["p"], f_["dif"],
            partidos=f_["partidos"])
    if v.get("llegadas"):
        md += [f"**¿Sirve la receta?** Aplicada a {v['llegadas']} llegadas de técnicos de la liga (cada una fuera de "
               f"su propio ajuste):", "",
               f"- error medio {v['error_abs_por_partido']:.2f} puntos por partido contra {v['error_abs_inercia']:.2f} de "
               f"la inercia (diferencia {v['dif_error']:+.3f}; Diebold-Mariano p = {v['p_dm']:.3f}, Wilcoxon p = "
               f"{v['p_wilcoxon']:.3f});",
               f"- correlación entre lo proyectado y lo real {v['correlacion']:.2f} (p = {v['p_correlacion']:.2g});",
               f"- el intervalo del 80 % del simulador contiene lo real en {100 * v['cobertura_80']:.0f} % de los casos "
               f"(binomial contra 80 %: p = {v['p_cobertura']:.3f}). Por eso se reporta el **intervalo conforme**: ± "
               f"{v['conforme_80_pp']:.2f} puntos por partido, que cubre el 80 % por construcción.", ""]
        md += ["| escenario | puntos proyectados | intervalo conforme del 80 % |", "|---|---|---|"]
        for n, lab in (("con_el", f"con {foco}"), ("inercia", "solo el plantel")):
            if "pts_conforme" in e[n]:
                md.append(f"| {lab} | {e[n]['pts_media']:.1f} | {e[n]['pts_conforme'][0]:.0f}–{e[n]['pts_conforme'][1]:.0f} |")
        if "proy_conforme" in c:
            md += ["", f"Sus {c['partidos']} partidos reales: proyectado {c['proy_pts_media']:.1f} (conforme 80 %: "
                   f"{c['proy_conforme'][0]:.0f}–{c['proy_conforme'][1]:.0f}); real {c['pts_reales']:.0f}.", ""]
        _prueba(pruebas, "proyeccion/receta_vs_inercia", "la receta (plantel × efecto de llegada) proyecta mejor que la "
                "inercia (Diebold-Mariano)", v["p_dm"], v["dif_error"])
        _prueba(pruebas, "proyeccion/correlacion", "lo proyectado se asocia con lo real en las llegadas de la liga",
                v["p_correlacion"], v["correlacion"], tipo="correlacion")
    res["pruebas"] = pruebas
    _escribir(out, "simulacion", md, res)


# ----------------------------------------------------------------------
# BLINDAJE
# ----------------------------------------------------------------------
def cmd_blindaje(a, cfg):
    from .blindaje import bh_global, eficiencia_robusta, obv_por_secuencia
    from .cli import _tabla_fase2, _trans
    from .fase3 import reasignar_foco
    from .hipotesis import modelo_contexto
    from .pesos import score_bootstrap
    from .simulador import calibracion_contexto
    fc = cfg["futbol"]
    c2 = cfg["fase2"]
    foco = _foco(a, cfg)
    K = c2["K"]
    out = _dir(cfg, foco, "blindaje")
    ev = _eventos(cfg, con_extra=False)
    t = obv_por_secuencia(_tabla_fase2(cfg, foco), _trans(cfg), ev)
    res = {"eficiencia": eficiencia_robusta(t, K, c2["familias"], c2["n_boot"], cfg["seed"])}
    pruebas = {"H3": ["f×perdiendo", "f×ganando"], "H4": ["f×tramo_75+"], "H5": ["f×local"], "H6": ["f×elo_dif"]}
    res["score_boot"] = {}
    clubes = (t.filter(pl.col("f")).group_by("team").agg(pl.col("match_id").n_unique().alias("p"))
              .filter(pl.col("p") >= fc["min_partidos_club"])["team"].to_list())
    for club in [None, *clubes]:
        tc = t if club is None else reasignar_foco(t, foco, club)
        m, D, _ = modelo_contexto(tc, K, c2.get("ref", 1))
        X = D(tc)
        R = tc.select([f"r_{k + 1}" for k in range(K)]).to_numpy()
        clave = club or "todos"
        res["score_boot"][clave] = {h: {**m.wald(cols), **score_bootstrap(X, R, tc["match_id"].to_numpy(), m.nombres,
                                                                          cols, c2.get("ref", 1), 999, cfg["seed"])}
                                    for h, cols in pruebas.items()}
        print(f"score bootstrap {clave}: " + ", ".join(
            f"{h} p_wald={v['p']:.3f} p_boot={v['p_boot']:.3f}" for h, v in res["score_boot"][clave].items()), flush=True)
    res["calibracion"] = {}
    for suave in (False, True):
        m, D, _ = modelo_contexto(t, K, c2.get("ref", 1), suave)
        cal = calibracion_contexto(t, m, D, K)
        res["calibracion"]["splines" if suave else "tramos"] = {
            "error_tv": float(cal["error_tv"].mean()), "ruido_tv": float(cal["ruido_tv"].mean()),
            "cociente": float(cal["error_tv"].mean() / cal["ruido_tv"].mean()), "celdas": cal.height,
            "H3_H6": {h: m.wald(cols)["p"] for h, cols in pruebas.items()}}
    slug = _slug(foco)
    rep = cfg.ruta("reportes")
    h = rep / "historia" / slug
    bh = bh_global([rep / "fase2" / f"hipotesis_{slug}.json", rep / "fase3" / f"por_club_{slug}.json",
                    rep / "fase3" / f"decisiones_{slug}.json"]
                   + [h / s / f"{s}.json" for s in ("identidad", "ofensiva", "jugadores", "balon_parado")])
    if bh.height:
        bh.write_csv(out / "bh_global.csv")
        res["bh_global"] = {"hipotesis": bh.height,
                            "cambian": bh.filter(pl.col("etiqueta_global") != pl.col("etiqueta_familia")).to_dicts()}
    md = [f"# 7. Blindaje — {foco}", "", "## Eficiencia con tres medidas (xG, OBV, tasa de remate)", "",
          "| lado | familia | xG dif [IC] | OBV dif [IC] | remate dif [IC] | coinciden |", "|---|---|---|---|---|---|"]
    for lado, fams in res["eficiencia"].items():
        for fam, v in fams.items():
            celdas = [f"{v[m]['dif']:+.4f} [{v[m]['lo']:+.4f}, {v[m]['hi']:+.4f}]" for m in ("xg", "obv", "remate")]
            md.append(f"| {lado} | {fam} | " + " | ".join(celdas) + f" | {'sí' if v['coinciden'] else '**no**'} |")
    md += ["", "## H3–H6 con pocos partidos: Wald sandwich contra bootstrap de score", "",
           "| muestra | hipótesis | p Wald | p bootstrap | partidos |", "|---|---|---|---|---|"]
    for clave, hs in res["score_boot"].items():
        for hh, v in hs.items():
            md.append(f"| {clave} | {hh} | {v['p']:.4f} | {v['p_boot']:.4f} | {v.get('partidos', '')} |")
    md += ["", "## Calibración del modelo de contexto", "",
           "| diseño | error (pp) | ruido (pp) | cociente | p H3 | p H4 | p H5 | p H6 |", "|---|---|---|---|---|---|---|---|"]
    for k, v in res["calibracion"].items():
        md.append(f"| {k} | {100 * v['error_tv']:.2f} | {100 * v['ruido_tv']:.2f} | {v['cociente']:.2f} | "
                  + " | ".join(f"{v['H3_H6'][hh]:.4f}" for hh in ("H3", "H4", "H5", "H6")) + " |")
    if "bh_global" in res:
        md += ["", f"## BH global ({res['bh_global']['hipotesis']} hipótesis en una sola familia)", ""]
        cambios = res["bh_global"]["cambian"]
        md += [f"- {c['id']} ({c['nombre']}): {c['etiqueta_familia']} → {c['etiqueta_global']} (q = {c['q_global']:.4f})"
               for c in cambios] or ["- Ninguna etiqueta cambia al pasar a una sola familia."]
    _escribir(out, "blindaje", md, res)


# ----------------------------------------------------------------------
# DEMOSTRACIÓN: un solo BH sobre todo lo que se afirma
# ----------------------------------------------------------------------
def cmd_demostracion(a, cfg):
    from .demostracion import demostrar, reporte
    foco = _foco(a, cfg)
    slug = _slug(foco)
    rep = cfg.ruta("reportes")
    h = rep / "historia" / slug
    archivos = {"fase 2 (familias y contexto)": rep / "fase2" / f"hipotesis_{slug}.json",
                "fase 3 (por club)": rep / "fase3" / f"por_club_{slug}.json",
                "decisiones desde la banca": rep / "fase3" / f"decisiones_{slug}.json",
                **{s: h / s / f"{s}.json" for s in ("identidad", "ofensiva", "defensa", "jugadores", "balon_parado",
                                                    "simulacion")}}
    D = demostrar(archivos)
    out = _dir(cfg, foco, "demostracion")
    if D.height == 0:
        sys.exit("sin resultados: corre antes las secciones (scripts/historia.sh)")
    D.write_csv(out / "demostracion.csv")
    md = reporte(D, foco)
    res = {"afirmaciones": D.height, "por_veredicto": dict(D.group_by("veredicto").len().iter_rows()),
           "demostradas": D.filter(pl.col("veredicto") == "demostrado").drop("pocos").to_dicts()}
    _escribir(out, "demostracion", md, res)


def registrar(sp) -> None:
    s = sp.add_parser("extra", help="G0: campos extra del JSON (centros, técnica, asistencias…)")
    s.add_argument("--hilos", type=int, default=None)
    s.set_defaults(f=cmd_extra)
    s = sp.add_parser("geometria", help="bloque, ancho visible y frame del saque a balón parado (360)")
    s.add_argument("--hilos", type=int, default=None)
    s.set_defaults(f=cmd_geometria)
    s = sp.add_parser("tabla-liga", help="tabla equipo-partido de toda la liga (todas las métricas)")
    s.add_argument("--rehacer", action="store_true")
    s.set_defaults(f=cmd_tabla)
    for nombre, f, ayuda in (("identidad", cmd_identidad, "1: reconocimiento, contexto, rival y evolución"),
                             ("ofensiva", cmd_ofensiva, "2: salida, progresión, llegada, ocasión, familias"),
                             ("defensa", cmd_defensa, "3: presión, bloque, transiciones, concedido"),
                             ("jugadores", cmd_jugadores, "4: roles, decisiones y sustituciones"),
                             ("balon-parado", cmd_balon_parado, "5: corners, tiros libres, laterales, xDefense"),
                             ("simular", cmd_simular, "6: simulador, puntos esperados y proyección"),
                             ("blindaje", cmd_blindaje, "7: xG contra OBV, pocos partidos, BH global"),
                             ("demostracion", cmd_demostracion, "8: un solo BH sobre TODO; solo se narra lo demostrado")):
        s = sp.add_parser(nombre, help=ayuda)
        s.add_argument("--foco", default=None)
        if nombre == "ofensiva":
            s.add_argument("--rehacer", action="store_true", help="recalcula la tabla equipo-partido de la liga")
        s.set_defaults(f=f)


if __name__ == "__main__":  # pragma: no cover
    sys.exit("usa `dtcoach <comando>`")
