#!/usr/bin/env python3
"""
Mejora C (ADR-v2-54, EXPERIMENTO EXPLORATORIO): Voronoi × grafo de jugadores. Ver src/dtcoach/voronoi_grafo.py.

Uso (raíz del repo, venv activo, con data/interim/rasgos_360.parquet de `dtcoach voronoi`):
  python scripts/experimentos/voronoi_grafo.py --config config/exp_mejoras.yaml --muestra 200   # humo
  python scripts/experimentos/voronoi_grafo.py --config config/exp_mejoras.yaml
Salida: <reportes>/experimentos/voronoi_grafo/. Exploratorio: NO entra al BH global.
"""
import argparse
import json
import time

import numpy as np
import polars as pl

from dtcoach import voronoi_grafo as vg
from dtcoach.cli import _space, _trans
from dtcoach.cli_historia import _eventos, _ruta, _tp
from dtcoach.config import Config
from dtcoach.jugadores import cadena_jugadores
from dtcoach.mezcla import DatosPosesion


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/exp_mejoras.yaml")
    ap.add_argument("--foco", default=None)
    ap.add_argument("--muestra", type=int, default=0, help="humo: solo N partidos (todos los del foco)")
    a = ap.parse_args()
    t0 = time.time()
    cfg = Config.load(a.config)
    ec = cfg["experimentos"]["voronoi_grafo"]
    foco = a.foco or cfg["foco"]["coach"]
    space, trans = _space(cfg), _trans(cfg)
    d = DatosPosesion.desde_transiciones(trans, space)
    Vz = vg.valor_de_zonas(np.asarray(d.S.sum(0)).ravel(), np.asarray(d.X.sum(0)).ravel(), d.n_transient, d.n_states,
                           d.n_phases)
    ev = _eventos(cfg, con_extra=False)
    rasgos = pl.read_parquet(_ruta(cfg, cfg["voronoi"]["rasgos"]))
    tp = _tp(cfg).select("match_id", "team", "coach")
    if a.muestra:
        rng = np.random.default_rng(cfg["seed"])
        con = tp.filter(pl.col("coach") == foco)["match_id"].unique().to_list()
        resto = np.setdiff1d(tp["match_id"].unique().to_numpy(), con)
        keep = set(con) | set(rng.choice(resto, min(a.muestra, len(resto)), replace=False).tolist())
        ev, rasgos, tp = (x.filter(pl.col("match_id").is_in(list(keep))) for x in (ev, rasgos, tp))
    acc = vg.residualizar(vg.acciones(ev, rasgos, space, Vz)).join(tp, on=["match_id", "team"], how="left")
    liga = vg.por_espacio(acc)
    tab = vg.tabla_jugadores(acc, ec["min_n_jugador"])
    pend = []
    for (pid, team, coach), g in acc.group_by("player_id", "team", "coach"):
        if g.height >= ec["min_n_jugador"]:
            pend.append({"player_id": pid, "team": team, "coach": coach, "pendiente": vg.pendiente_espacio(g)})
    tab = tab.join(pl.DataFrame(pend), on=["player_id", "team", "coach"], how="left") if pend else tab
    # el grafo de pases de las etapas del foco, cruzado con el espacio y el valor de la decisión
    cruces = []
    for team in tp.filter(pl.col("coach") == foco)["team"].unique().to_list():
        parts = tp.filter((pl.col("coach") == foco) & (pl.col("team") == team))["match_id"].unique().to_list()
        gr = cadena_jugadores(ev, parts, team, cfg["futbol"]["min_acciones_jugador"])
        cruces += vg.cruce_grafo(tab, gr, team, foco)
    corr = {"area_vs_flujo": vg.correlacion([c["area_media"] for c in cruces], [c["flujo"] for c in cruces]),
            "dv_vs_flujo": vg.correlacion([c["dv_real_perp"] for c in cruces], [c["flujo"] for c in cruces]),
            "dv_vs_P_remate": vg.correlacion([c["dv_real_perp"] for c in cruces], [c["P_remate_desde"] for c in cruces]),
            "area_vs_dv": vg.correlacion(tab["area_media"].to_list(), tab["dv_real_perp"].to_list())}
    mj = vg.mismo_jugador(acc, ec["min_n_cruce"], foco, seed=cfg["seed"])
    alcanza = mj["jugadores_con_2_tecnicos"] >= ec["min_jugadores_cruce"]
    res = {"foco": foco, "exploratorio": True, "acciones_con_360": acc.height, "jugadores_etapa_n_min": tab.height,
           "valor_zonas": Vz.tolist(), "liga_por_espacio": liga, "correlaciones_foco": corr, "cruces_grafo": cruces,
           "mismo_jugador": {k: v for k, v in mj.items() if k != "pares"} | {"alcanza": bool(alcanza)}, "pares_mismo_jugador": mj["pares"],
           "muestra": a.muestra or None, "pendiente_liga_por_100m2": vg.pendiente_espacio(acc)}
    out = cfg.ruta("reportes") / cfg["experimentos"]["salida"] / "voronoi_grafo"
    out.mkdir(parents=True, exist_ok=True)
    (out / "voronoi_grafo.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))
    tab.write_csv(out / "jugadores.csv")
    L = liga["niveles"]
    md = [f"# Mejora C — Voronoi × grafo de jugadores ({foco})", "",
          "> **EXPLORATORIO (ADR-v2-54).** No es una hipótesis pre-registrada y NO entra al BH global. Nada de esto se narra como resultado.", "",
          "**Lo que esto no puede decir.** El 360 es una *foto del evento*, no tracking: se mide con cuánto espacio **ejecutó** el jugador, "
          "no «qué tan bien recibe». Solo hay jugadores visibles en cámara (se exige ≥ 50 % del disco visible y que el actor del frame "
          f"coincida con el evento a ≤ 2 m). Se descartan jugador-etapa con n < {ec['min_n_jugador']} acciones con 360.", "",
          f"- acciones con 360 usadas: **{acc.height:,}** · jugador-etapa con n ≥ {ec['min_n_jugador']}: **{tab.height}**"
          + (f" · humo con {a.muestra} partidos" if a.muestra else ""), "",
          "## La liga: qué decide y cuánto vale según el espacio", "",
          f"Terciles del área local (m²): ≤ {liga['cortes_m2'][0]:.0f} · ≤ {liga['cortes_m2'][1]:.0f} · mayor.", "",
          "| espacio | n | % pase | % conducción | % remate | pase perdido | ΔV⊥ intención | ΔV⊥ realizado |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {e} | {L[e]['n']:,} | {100 * L[e]['frac_pase']:.1f} | {100 * L[e]['frac_conduccion']:.1f} | {100 * L[e]['frac_remate']:.1f} | "
           f"{100 * L[e]['perdida_pase']:.1f} % | {L[e]['dv_int_perp']:+.5f} | {L[e]['dv_real_perp']:+.5f} |" for e in ("poco", "medio", "mucho")]
    md += ["", f"Pendiente de ΔV⊥(realizado) sobre el área, toda la liga: {res['pendiente_liga_por_100m2']:+.5f} por 100 m².", "",
           "## El grafo de pases de las etapas del foco, cruzado con el espacio", "",
           "| par de variables (entre jugadores) | n | ρ de Spearman | p |", "|---|---|---|---|"]
    for k, v in corr.items():
        md.append(f"| {k} | {v['n']} | {v['rho']:+.2f} | {v['p']:.3g} |")
    md += ["", "ν = por quién pasa el balón (cadena de jugadores); P(remate) = que la posesión termine en remate si el balón está en él. "
           "Con muestras así de chicas, las correlaciones son descriptivas.", "",
           "## ¿Depende del entrenador? El único diseño identificable: el mismo jugador bajo distintos técnicos", "",
           f"- jugadores con ≥ 2 técnicos y n ≥ {ec["min_n_cruce"]} acciones con 360 y ≥ 3 partidos con cada uno: **{mj['jugadores_con_2_tecnicos']}** "
           f"(con el foco: {mj['con_el_foco']}); umbral para concluir: {ec['min_jugadores_cruce']}."]
    if alcanza:
        md.append(f"- {mj['pares_n']} pares jugador-técnico (z de Welch por partido): **media de z² = {mj['z2_media']:.2f}** "
                  f"(≈ 1 si el técnico no importa; nula por permutación {mj.get('z2_nula_media', float('nan')):.2f}), p de permutación = {mj['p_perm']:.3f}. "
                  "El mismo jugador con técnicos distintos casi siempre cambia también de club, compañeros y época: esto NO separa técnico de contexto.")
    else:
        md.append(f"- **No alcanza** ({mj['jugadores_con_2_tecnicos']} < {ec['min_jugadores_cruce']}): no se concluye si el técnico cambia el uso del espacio de un jugador.")
    md += ["", f"Tiempo: {time.time() - t0:.0f} s."]
    (out / "VORONOI_GRAFO.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
