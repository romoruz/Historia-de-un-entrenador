"""Comandos de la capa de fútbol (fases A–F). Cada comando escribe en
reports/historia/<foco>/ un JSON (para el informe), un Markdown (para leer) y figuras."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

from . import ingest


def _slug(foco: str) -> str:
    return foco.lower().replace(" ", "_")


def _dir(cfg, foco: str) -> Path:
    d = cfg.ruta("reportes") / "historia" / _slug(foco)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ruta(cfg, r: str) -> Path:
    from .config import RAIZ
    q = Path(r)
    return q if q.is_absolute() else RAIZ / q


def _json(obj, path: Path) -> None:
    from .cli import _json as j
    j(obj, path)


def _tp(cfg) -> pl.DataFrame:
    from .cli import _equipo_partido
    from .eventos import con_rival
    return con_rival(_equipo_partido(cfg))


def _eventos(cfg) -> pl.DataFrame:
    from .eventos import leer
    t0 = time.time()
    ev = leer(ingest.scan_events(cfg.ruta("eventos_parquet")))
    print(f"eventos: {ev.height:,} en {time.time() - t0:.0f}s", flush=True)
    return ev


def _opcional(p: Path) -> pl.DataFrame | None:
    return pl.read_parquet(p) if p.exists() else None


def _clubes(M: pl.DataFrame, foco: str, minimo: int) -> list[str]:
    return (M.filter(pl.col("coach") == foco).group_by("team").agg(pl.col("match_id").n_unique().alias("p"))
            .filter(pl.col("p") >= minimo).sort("p", descending=True)["team"].to_list())


# ----------------------------------------------------------------------
# geometría 360 (una pasada por los frames)
# ----------------------------------------------------------------------
def cmd_geometria(a, cfg):
    from .balon_parado import ids_saques
    from .geometria import geometria_liga
    fc = cfg["futbol"]
    ev = _eventos(cfg)
    ids = ids_saques(ev, fc)
    print(f"saques a balón parado para el marcaje: {sum(len(v) for v in ids.values()):,}", flush=True)
    t0 = time.time()
    B, Mk = geometria_liga(cfg.ruta("raw_frames"), ids, fc["min_defensores"], a.hilos or 4)
    idx = ev.select("match_id", "id", pl.col("index").alias("event_index"))
    B = B.join(idx, on=["match_id", "id"], how="inner")
    Mk = Mk.join(idx, on=["match_id", "id"], how="inner")
    for df, clave in ((B, "bloque"), (Mk, "marcaje")):
        p = _ruta(cfg, fc[clave])
        p.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(p)
    res = {"frames_con_bloque": B.height, "saques_con_marcaje": Mk.height, "segundos": round(time.time() - t0),
           "altura_bloque_p10_p50_p90": [float(B["altura"].quantile(q)) for q in (.1, .5, .9)] if B.height else None,
           "defensores_visibles_mediana": float(B["n_def"].median()) if B.height else None,
           "dist_marca_mediana": float(Mk["dist_marca"].median()) if Mk.height else None}
    _json(res, cfg.ruta("reportes") / "fase1" / "geometria_360.json")
    print(json.dumps(res, indent=2, ensure_ascii=False))


# ----------------------------------------------------------------------
# la tabla equipo-partido de TODA la liga (se calcula una vez)
# ----------------------------------------------------------------------
def tabla_liga(cfg, ev: pl.DataFrame | None = None, rehacer: bool = False) -> pl.DataFrame:
    from . import balon_parado as bp
    from . import futbol as fb
    from .decisiones import leer_eventos
    from .eventos import posesiones
    from .jugadores import estabilidad_once
    fc = cfg["futbol"]
    p = _ruta(cfg, fc["tabla"])
    if p.exists() and not rehacer:
        return pl.read_parquet(p)
    ev = _eventos(cfg) if ev is None else ev
    tp = _tp(cfg)
    pos = posesiones(ev)
    rasgos = _opcional(_ruta(cfg, cfg["voronoi"]["rasgos"]))
    bloque = _opcional(_ruta(cfg, fc["bloque"]))
    marc = _opcional(_ruta(cfg, fc["marcaje"]))
    if rasgos is None:
        print("[aviso] sin rasgos 360 (dtcoach voronoi): no hay métricas de presión 360")
    if bloque is None:
        print("[aviso] sin bloque 360 (dtcoach geometria): no hay métricas de bloque ni marcaje")
    tablas = (fb.ofensiva(ev, pos, fc) + fb.defensiva(ev, tp) + fb.transiciones(pos, fc)
              + fb.del_360(ev, rasgos, bloque, tp, fc)
              + bp.metricas(bp.jugadas(ev, fc), marc, tp)
              + [estabilidad_once(leer_eventos(ingest.scan_events(cfg.ruta("eventos_parquet")))["xi"], tp)])
    M = fb.unir(tablas, tp)
    p.parent.mkdir(parents=True, exist_ok=True)
    M.write_parquet(p)
    print(f"tabla equipo-partido: {M.height:,} filas · {len(fb.metricas_de(M))} métricas → {p}", flush=True)
    return M


def _bloque(M, metricas, foco, lado, fc, seed, club=None):
    from .comparar import etiquetar, foco_vs_liga
    ms = [m for m in metricas if f"{m}__n" in M.columns]
    return etiquetar(foco_vs_liga(M, ms, foco, lado, fc["n_boot"], seed, club), 0.05, 20)


def _percentiles(M, metricas, foco, lado, minimo):
    from .comparar import percentil, por_era
    ms = [m for m in metricas if f"{m}__n" in M.columns]
    eras = por_era(M, ms, lado, minimo)
    return {m: percentil(eras, m, foco) for m in ms}


# ----------------------------------------------------------------------
# B. estilo de juego
# ----------------------------------------------------------------------
BLOQUES = {
    "ofensiva": ("propio", "OFENSIVAS"),
    "defensiva": ("propio", "DEFENSIVAS_M"),
    "transiciones": ("propio", "TRANSICIONES"),
    "360": ("propio", "M360"),
}
CONCEDIDO = ["remates", "xg", "entradas_area", "entradas_tercio", "pases_prog", "obv", "xg_por_remate"]


def cmd_futbol(a, cfg):
    from . import futbol as fb
    from .cli import _space, _trans
    from .comparar import fiabilidad, tabla
    from .eventos import posesiones
    from .graficas_historia import curva_recuperacion, diferencia_zonas, percentiles
    fc = cfg["futbol"]
    foco = a.foco or cfg["foco"]["coach"]
    ev = _eventos(cfg)
    M = tabla_liga(cfg, ev, a.rehacer)
    tp = _tp(cfg)
    out_dir = _dir(cfg, foco)
    clubes = _clubes(M, foco, fc["min_partidos_club"])
    res = {"foco": foco, "clubes": clubes, "bloques": {}, "por_club": {}, "percentiles": {}}
    md = [f"# Estilo de juego — {foco}", "",
          "Cada métrica: foco contra la liga sin sus partidos (IC 95 % por bootstrap de partidos), su percentil "
          "entre todos los técnicos-club con ≥ "
          f"{fc['min_partidos_era']} partidos y su fiabilidad entre mitades (Spearman-Brown; ≥ 0.7 = rasgo estable "
          "de un técnico). Definiciones: 03_FRAMEWORK §5.", ""]
    todas = []
    for nombre, (lado, lista) in BLOQUES.items():
        ms = [m for m in getattr(fb, lista) if f"{m}__n" in M.columns]
        if not ms:
            continue
        todas += ms
        r = _bloque(M, ms, foco, lado, fc, cfg["seed"])
        pc = _percentiles(M, ms, foco, lado, fc["min_partidos_era"])
        fi = fiabilidad(M, ms, lado, fc["min_partidos_era"])
        res["bloques"][nombre] = {"comparacion": r, "percentiles": pc, "fiabilidad": fi}
        res["percentiles"].update(pc)
        md += [f"## {nombre.capitalize()}", "", tabla(r, fi, pc, fb.DEFINICIONES), ""]
    ms = [m for m in CONCEDIDO if f"{m}__n" in M.columns]
    r = _bloque(M, ms, foco, "rival", fc, cfg["seed"])
    pc = _percentiles(M, ms, foco, "rival", fc["min_partidos_era"])
    fi = fiabilidad(M, ms, "rival", fc["min_partidos_era"])
    res["bloques"]["concedido"] = {"comparacion": r, "percentiles": pc, "fiabilidad": fi}
    md += ["## Lo que le hacen sus rivales (concedido)", "", tabla(r, fi, pc, fb.DEFINICIONES), ""]
    for club in clubes:
        res["por_club"][club] = {"propio": _bloque(M, todas, foco, "propio", fc, cfg["seed"], club),
                                 "concedido": _bloque(M, ms, foco, "rival", fc, cfg["seed"], club)}
        md += [f"## Solo en {club}", "", tabla(res["por_club"][club]["propio"], None, None, fb.DEFINICIONES), ""]
    # construcción y progresión con la cadena (primer paso)
    space = _space(cfg)
    trans = _trans(cfg)
    claves, A, dims = fb.conteos_por_partido(trans, space.n_transient, space.n_states)
    cx = np.repeat(space.zone_centroids()[:, 0], len(space.phases))
    cy = np.repeat(space.zone_centroids()[:, 1], len(space.phases))
    objetivos = {"último tercio": cx >= 80, "frente al área": (cx >= 102) & (cy >= 18) & (cy <= 62)}
    for lado in ("propio", "rival"):
        ll = fb.comparar_llegada(claves, A, dims, tp, foco, objetivos, fc["lam_llegada"],
                                 min(fc["n_boot"], 300), cfg["seed"], lado)
        res[f"llegada_{lado}"] = ll
        md += [f"## Llegada desde el inicio de la secuencia ({'ataque' if lado == 'propio' else 'sus rivales'})", "",
               "| destino | medida | foco | liga | dif [IC 95 %] | p |", "|---|---|---|---|---|---|"]
        for n in objetivos:
            for q, v in ll[n].items():
                md.append(f"| {n} | {'P(llegar)' if q == 'P' else 'acciones si llega'} | {v['foco']:.3f} | "
                          f"{v['liga']:.3f} | {v['dif']:+.3f} [{v['lo']:+.3f}, {v['hi']:+.3f}] | {v['p']:.4f} |")
        md.append("")
        if lado == "propio":
            diferencia_zonas(ll["V_foco"], ll["V_liga"], space.nx, space.ny, out_dir / "valor_zona.png",
                             f"Valor de zona V = Nc: {foco} − liga", "xG que produce una secuencia que pasa por ahí")
    # transiciones: curva de supervivencia de la pérdida
    pos = posesiones(ev)
    km = fb.curva_recuperacion(pos, tp, foco, n_boot=200, seed=cfg["seed"])
    res["curva_recuperacion"] = km
    curva_recuperacion(km, foco, out_dir / "recuperacion.png")
    rasgos = _opcional(_ruta(cfg, cfg["voronoi"]["rasgos"]))
    if rasgos is not None:
        mp = fb.mapa_presion(ev, rasgos, tp, foco, space.nx, space.ny, fc["presion_m"])
        res["mapa_presion"] = mp
        diferencia_zonas(mp["foco"], mp["liga"], space.nx, space.ny, out_dir / "presion_360.png",
                         f"Presión 360 que aplica {foco}: fracción de acciones del rival con un defensor a ≤ "
                         f"{fc['presion_m']:g} m (foco − liga, en SU campo)", "diferencia de fracción")
    percentiles(res["percentiles"], fb.DEFINICIONES, foco, out_dir / "percentiles.png", "Estilo de juego")
    _json(res, out_dir / "futbol.json")
    (out_dir / "FUTBOL.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    print(f"\nSalidas: {out_dir}")


# ----------------------------------------------------------------------
# E. balón parado
# ----------------------------------------------------------------------
def cmd_balon_parado(a, cfg):
    from . import balon_parado as bp
    from .comparar import tabla
    from .graficas_historia import densidad_balon_parado
    fc = cfg["futbol"]
    foco = a.foco or cfg["foco"]["coach"]
    ev = _eventos(cfg)
    M = tabla_liga(cfg, ev)
    tp = _tp(cfg)
    out_dir = _dir(cfg, foco)
    j = bp.jugadas(ev, fc)
    ofe = [m for m in bp.DEFINICIONES if f"{m}__n" in M.columns and m not in ("dist_marca", "sobra")]
    res = {"a_favor": _bloque(M, ofe, foco, "propio", fc, cfg["seed"]),
           "en_contra": _bloque(M, ofe, foco, "rival", fc, cfg["seed"]), "tasas": [], "marcaje": None}
    marc = [m for m in ("dist_marca", "sobra") if f"{m}__n" in M.columns]
    if marc:
        res["marcaje"] = _bloque(M, marc, foco, "propio", fc, cfg["seed"])
    md = [f"# Balón parado — {foco}", "", "## A favor", "", tabla(res["a_favor"], None, None, bp.DEFINICIONES), "",
          "## En contra", "", tabla(res["en_contra"], None, None, bp.DEFINICIONES), ""]
    if res["marcaje"]:
        md += ["## Marcaje en corners y tiros libres (360, asignación húngara)", "",
               tabla(res["marcaje"], None, None, bp.DEFINICIONES), ""]
    md += ["## Tasas por jugada (Poisson con exposición, sandwich por partido)", "",
           "| tipo | qué | lado | foco | liga | razón [IC 95 %] | p | dispersión |", "|---|---|---|---|---|---|---|---|"]
    for tipo in bp.TIPOS:
        for que in ("remates", "goles"):
            for lado in ("propio", "rival"):
                r = bp.razon_de_tasas(j, tp, foco, tipo, que, lado)
                if "razon" not in r:
                    continue
                res["tasas"].append(r)
                md.append(f"| {tipo} | {que} | {'a favor' if lado == 'propio' else 'en contra'} | {r['tasa_foco']:.3f} | "
                          f"{r['tasa_liga']:.3f} | {r['razon']:.2f} [{r['lo']:.2f}, {r['hi']:.2f}] | {r['p']:.4f} | "
                          f"{r['dispersion_pearson']:.2f} |")
    for tipo in ("corner", "tiro_libre"):
        for lado in ("propio", "rival"):
            mp = bp.mapas(j, tp, foco, tipo, lado)
            densidad_balon_parado(mp, foco, tipo, lado, out_dir / f"bp_{tipo}_{lado}.png")
    _json(res, out_dir / "balon_parado.json")
    (out_dir / "BALON_PARADO.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


# ----------------------------------------------------------------------
# D. jugadores
# ----------------------------------------------------------------------
def cmd_jugadores(a, cfg):
    from .cli import _equipo_partido, _tabla_fase2, _trans
    from .comparar import tabla
    from .decisiones import leer_eventos, sustituciones
    from .eventos import con_rival
    from .graficas_historia import red_pases
    from .jugadores import cadena_jugadores, impacto_cambios, protagonistas
    fc = cfg["futbol"]
    foco = a.foco or cfg["foco"]["coach"]
    K = cfg["fase2"]["K"]
    fams = cfg["fase2"]["familias"]
    ev = _eventos(cfg)
    M = tabla_liga(cfg, ev)
    tp0 = _equipo_partido(cfg)
    tp = con_rival(tp0)
    out_dir = _dir(cfg, foco)
    t_seq = _tabla_fase2(cfg, foco)
    trans = _trans(cfg)
    res = {"clubes": {}}
    md = [f"# Uso de jugadores — {foco}", ""]
    for club in _clubes(M, foco, fc["min_partidos_club"]):
        partidos = M.filter((pl.col("coach") == foco) & (pl.col("team") == club))["match_id"].unique().to_list()
        cad = cadena_jugadores(ev, partidos, club, fc["min_acciones_jugador"])
        prot = protagonistas(trans, t_seq, partidos, club, K)
        res["clubes"][club] = {"cadena": {k: v for k, v in cad.items() if k != "W"}, "protagonistas": prot}
        if "nota" in cad:
            md += [f"## {club}: {cad['nota']}", ""]
            continue
        red_pases(cad, f"{foco} en {club}: red de pases ({len(partidos)} partidos)",
                  out_dir / f"red_{_slug(club)}.png")
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
    dec = leer_eventos(ingest.scan_events(cfg.ruta("eventos_parquet")))
    subs = sustituciones(dec, tp0)
    imp = impacto_cambios(ev, subs, tp, foco, fc["ventana_cambio"], fc["n_boot"], cfg["seed"])
    res["impacto_cambios"] = imp
    md += [f"## Impacto del primer cambio del 2º tiempo (dif. en dif., ±{imp['ventana_min']} min)", "",
           f"{imp['n_cambios_foco']} cambios del foco, {imp['n_cambios_liga']} de la liga.", "",
           "| medida | efecto (foco − liga) [IC 95 %] | p |", "|---|---|---|"]
    for nombre in ("xg_propio", "obv_propio", "xg_rival"):
        v = imp[nombre]
        md.append(f"| {nombre} | {v['did']:+.3f} [{v['lo']:+.3f}, {v['hi']:+.3f}] | {v['p']:.4f} |")
    if "estabilidad_once__n" in M.columns:
        r = _bloque(M, ["estabilidad_once"], foco, "propio", fc, cfg["seed"])
        # misma medida que H17 (rotación), con la misma confusión con el calendario: exploratoria
        r["estabilidad_once"]["etiqueta"] = "🔎"
        res["estabilidad_once"] = r
        md += ["", "## Estabilidad del once (Jaccard con el partido anterior)", "",
               "🔎 Exploratoria: como H17, se confunde con el calendario (Copa, Concachampions no están en los datos).", "",
               tabla(r, None, _percentiles(M, ["estabilidad_once"], foco, "propio", fc["min_partidos_era"]),
                     {"estabilidad_once": {"nombre": "once repetido (Jaccard)", "formato": "{:.3f}"}})]
    _json(res, out_dir / "jugadores.json")
    (out_dir / "JUGADORES.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


# ----------------------------------------------------------------------
# C. identidad y tiempo
# ----------------------------------------------------------------------
HUELLA = ["pases_prog", "conducciones_prog", "entradas_tercio", "entradas_area", "xg_por_remate", "field_tilt",
          "posesion", "saque_corto", "ppda", "altura_recuperacion", "presion_alta", "recupera_5s",
          "presion_aplicada", "altura_bloque", "area_bloque"]
EVOLUCION = ["ppda", "field_tilt", "altura_recuperacion", "presion_aplicada", "altura_bloque"]


def cmd_identidad(a, cfg):
    from .cli import _tabla_fase2
    from .graficas_historia import evolucion as fig_evolucion
    from .identidad import evolucion, huella, ranking_reconocimiento, reconocimiento
    fc = cfg["futbol"]
    foco = a.foco or cfg["foco"]["coach"]
    K = cfg["fase2"]["K"]
    fams = cfg["fase2"]["familias"]
    M = tabla_liga(cfg)
    out_dir = _dir(cfg, foco)
    t_seq = _tabla_fase2(cfg, foco)
    ms = [m for m in HUELLA if f"{m}__n" in M.columns]
    H = huella(t_seq, M, K, ms)
    cols = [f"ataque_{k + 1}" for k in range(K)] + [f"defensa_{k + 1}" for k in range(K)] + ms
    res = {"liga": reconocimiento(H, cols, foco, "liga", fc["n_perm"], fc["lam_logit"], cfg["seed"]),
           "club": reconocimiento(H, cols, foco, "club", fc["n_perm"], fc["lam_logit"], cfg["seed"])}
    rk = ranking_reconocimiento(H, cols, fc["min_partidos_era"], fc["lam_logit"], cfg["seed"])
    rk.write_csv(out_dir / "reconocimiento_ranking.csv")
    res["ranking"] = rk.with_row_index("puesto", offset=1).filter(pl.col("coach") == foco).to_dicts()
    res["ranking_n"] = rk.height
    nombres = {f"ataque_{k + 1}": f"ataque · {f}" for k, f in enumerate(fams)}
    nombres |= {f"defensa_{k + 1}": f"rivales · {f}" for k, f in enumerate(fams)}
    from .futbol import DEFINICIONES as DEF_F
    nombres |= {m: DEF_F[m]["nombre"].split(" (")[0] for m in EVOLUCION if m in DEF_F}
    ev_ = evolucion(t_seq, H, foco, K, [m for m in EVOLUCION if m in ms])
    res["evolucion"] = ev_
    fig_evolucion(ev_, list(nombres) + [m for m in EVOLUCION if m in ms], nombres, foco, out_dir / "evolucion.png")
    md = [f"# Identidad y evolución — {foco}", ""]
    for contra in ("liga", "club"):
        r = res[contra]
        if "auc" not in r:
            md += [f"- contra {contra}: {r.get('nota')}"]
            continue
        md += [f"## ¿Se le reconoce contra {'la liga' if contra == 'liga' else 'su mismo club con otros técnicos'}?", "",
               f"AUC fuera de muestra **{r['auc']:.3f}** (nula por permutación: media {r['auc_nula_media']:.3f}, "
               f"p95 {r['auc_nula_p95']:.3f}; p = {r['p']:.3f}). {r['partidos_foco']} partidos suyos contra "
               f"{r['partidos_otros']}.", "", "Rasgos que más lo distinguen (coeficiente en desviaciones estándar):", ""]
        from .futbol import DEFINICIONES as DEF
        md += [f"- {nombres.get(x['rasgo'], DEF.get(x['rasgo'], {}).get('nombre', x['rasgo']))}: {x['coef_de']:+.2f}"
               for x in r["rasgos"]]
        md.append("")
    for x in res["ranking"]:
        md.append(f"- **Ranking de reconocimiento:** {x['team']}: puesto {x['puesto']} de {res['ranking_n']} "
                  f"técnicos-club (AUC {x['auc']:.3f}).")
    md += ["", "## Evolución (nivel local, Kalman + Rauch-Tung-Striebel)", "",
           "| serie | q/r (≈ 0 = identidad estable) |", "|---|---|"]
    md += [f"| {nombres.get(s, s)} | {v['q_sobre_r']:.4f} |" for s, v in ev_["series"].items()]
    for c in ev_["cambios_de_club"]:
        md += ["", f"**Cambio {c['de']} → {c['a']}** (salto del nivel suavizado; |z| > 2 = cambio claro, z conservador):", ""]
        md += [f"- {nombres.get(s, s)}: {v['salto']:+.3f} (z = {v['z']:+.2f})" for s, v in c["series"].items()]
    _json(res, out_dir / "identidad.json")
    (out_dir / "IDENTIDAD.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


# ----------------------------------------------------------------------
# F. simulador de partido
# ----------------------------------------------------------------------
def cmd_simular(a, cfg):
    from .cli import _tabla_fase2
    from .graficas_historia import simulacion as fig_sim
    from .simulacion import Parametros, estadisticos, partido_real, simular, validar_liga
    from .simulador import xpts_por_equipo_partido
    fc = cfg["futbol"]
    foco = a.foco or cfg["foco"]["coach"]
    K = cfg["fase2"]["K"]
    out_dir = _dir(cfg, foco)
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
    tab.write_csv(out_dir / "simulacion_partidos.csv")
    # el foco contra un rival "promedio" de la liga, con su estilo en cada club
    tipo = {}
    for club in tab["team"].unique().to_list():
        e = (foco, club)
        A_at, A_co = par.etapa(e, "ataque"), par.etapa(e, "concede")
        s = simular(par.combinar(A_at, par.liga), par.combinar(par.liga, A_co), fc["sim_rep"], cfg["seed"])
        tipo[club] = s
        fig_sim(s, f"{foco} ({club}) contra un rival promedio de la liga: {fc['sim_rep']:,} repeticiones",
                out_dir / f"simulacion_{_slug(club)}.png")
    res = {"validacion_liga": val, "partido_tipo": tipo,
           "resumen_foco": {"partidos": tab.height, "puntos": int(tab["puntos"].sum()),
                            "xPts_estilo": float(tab["xPts_estilo"].sum()),
                            "P_domina_xg_media": float(tab["P_domina_xg"].mean())},
           "mas_sorprendentes": tab.head(8).to_dicts()}
    md = [f"# Simulador de partido — {foco}", "",
          f"**Validación en toda la liga** (cada partido con parámetros estimados SIN él): Brier {val['brier']:.3f} contra "
          f"{val['brier_frecuencias']:.3f} de las frecuencias base (habilidad {100 * val['habilidad']:.1f} %); "
          f"correlación puntos reales–esperados {val['corr_puntos']:.2f} en {val['partidos']} partidos.", "",
          f"**{foco}:** {res['resumen_foco']['puntos']} puntos reales contra "
          f"{res['resumen_foco']['xPts_estilo']:.1f} esperados por su estilo y el de sus rivales en "
          f"{tab.height} partidos.", ""]
    for club, s in tipo.items():
        md.append(f"- Contra un rival promedio, con su estilo en {club}: gana {100 * s['P_gana']:.0f} %, empata "
                  f"{100 * s['P_empata']:.0f} %, pierde {100 * s['P_pierde']:.0f} %; xG {s['xg_A']:.2f}–{s['xg_B']:.2f}.")
    md += ["", "**Resultados menos probables según el estilo** (los más sorprendentes):", "",
           "| partido | rival | marcador | P(ese resultado) |", "|---|---|---|---|"]
    md += [f"| {r['match_id']} | {r['rival']} | {r['marcador']} | {100 * r['P_resultado']:.0f} % |"
           for r in res["mas_sorprendentes"]]
    _json(res, out_dir / "simulacion.json")
    (out_dir / "SIMULACION.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


# ----------------------------------------------------------------------
# A. blindaje
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
    foco = a.foco or cfg["foco"]["coach"]
    K = c2["K"]
    out_dir = _dir(cfg, foco)
    ev = _eventos(cfg)
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
    # calibración del modelo de contexto: tramos (oficial) contra splines + marcador × minuto
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
    bh = bh_global([rep / "fase2" / f"hipotesis_{slug}.json", rep / "fase3" / f"por_club_{slug}.json",
                    rep / "fase3" / f"decisiones_{slug}.json"])
    if bh.height:
        bh.write_csv(out_dir / "bh_global.csv")
        res["bh_global"] = {"hipotesis": bh.height,
                            "cambian": bh.filter(pl.col("etiqueta_global") != pl.col("etiqueta_familia")).to_dicts()}
    md = [f"# Blindaje — {foco}", "", "## Eficiencia con tres medidas (xG, OBV, tasa de remate)", "",
          "| lado | familia | xG dif [IC] | OBV dif [IC] | remate dif [IC] | coinciden |", "|---|---|---|---|---|---|"]
    for lado, fams in res["eficiencia"].items():
        for fam, v in fams.items():
            celdas = [f"{v[m]['dif']:+.4f} [{v[m]['lo']:+.4f}, {v[m]['hi']:+.4f}]" for m in ("xg", "obv", "remate")]
            md.append(f"| {lado} | {fam} | " + " | ".join(celdas) + f" | {'sí' if v['coinciden'] else '**no**'} |")
    md += ["", "## H3–H6 con pocos partidos: Wald sandwich contra bootstrap de score", "",
           "| muestra | hipótesis | p Wald | p bootstrap | partidos |", "|---|---|---|---|---|"]
    for clave, hs in res["score_boot"].items():
        for h, v in hs.items():
            md.append(f"| {clave} | {h} | {v['p']:.4f} | {v['p_boot']:.4f} | {v.get('partidos', '')} |")
    md += ["", "## Calibración del modelo de contexto", "",
           "| diseño | error (pp) | ruido (pp) | cociente | p H3 | p H4 | p H5 | p H6 |", "|---|---|---|---|---|---|---|---|"]
    for k, v in res["calibracion"].items():
        md.append(f"| {k} | {100 * v['error_tv']:.2f} | {100 * v['ruido_tv']:.2f} | {v['cociente']:.2f} | "
                  + " | ".join(f"{v['H3_H6'][h]:.4f}" for h in ("H3", "H4", "H5", "H6")) + " |")
    if "bh_global" in res:
        md += ["", f"## BH global ({res['bh_global']['hipotesis']} hipótesis en una sola familia)", ""]
        cambios = res["bh_global"]["cambian"]
        md += [f"- {c['id']} ({c['nombre']}): {c['etiqueta_familia']} → {c['etiqueta_global']} (q = {c['q_global']:.4f})"
               for c in cambios] or ["- Ninguna etiqueta cambia al pasar a una sola familia."]
    _json(res, out_dir / "blindaje.json")
    (out_dir / "BLINDAJE.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


def registrar(sp) -> None:
    s = sp.add_parser("geometria", help="bloque (envolvente convexa) y marcaje (húngaro) desde el 360")
    s.add_argument("--hilos", type=int, default=None)
    s.set_defaults(f=cmd_geometria)
    for nombre, f, ayuda in (("futbol", cmd_futbol, "B: estilo de juego contra la liga"),
                             ("balon-parado", cmd_balon_parado, "E: balón parado"),
                             ("jugadores", cmd_jugadores, "D: roles, protagonistas y cambios"),
                             ("identidad", cmd_identidad, "C: reconocimiento y evolución"),
                             ("simular", cmd_simular, "F: simulador de partido"),
                             ("blindaje", cmd_blindaje, "A: OBV, bootstrap de score, BH global")):
        s = sp.add_parser(nombre, help=ayuda)
        s.add_argument("--foco", default=None)
        if nombre == "futbol":
            s.add_argument("--rehacer", action="store_true", help="recalcula la tabla equipo-partido de la liga")
        s.set_defaults(f=f)


if __name__ == "__main__":  # pragma: no cover
    sys.exit("usa `dtcoach <comando>`")
