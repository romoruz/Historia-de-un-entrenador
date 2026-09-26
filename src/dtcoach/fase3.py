"""
Fase 3 -- ¿Es el tecnico o es el plantel?

1. `reasignar_foco`: redefine f, g y la referencia para cualquier tecnico (y,
   opcionalmente, un solo club suyo). Los partidos de sus OTRAS etapas se
   EXCLUYEN: si quedaran en la referencia, el tecnico se compararia contra
   si mismo (fuga de prior, en su forma mas simple).
2. `por_club`: H1, H2, H7 y H8 para cada club del foco + la comparacion entre
   clubes (H9-H12, pre-registradas en docs/11_HIPOTESIS.md).
3. `atlas`: los mismos efectos para cada era (tecnico × club) con suficientes
   partidos. EXPLORATORIO: sirve para poner en escala los efectos del foco.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .hipotesis import correr


def reasignar_foco(t: pl.DataFrame, coach: str, club: str | None = None) -> pl.DataFrame:
    sel = pl.col("coach") == coach
    if club is not None:
        sel = sel & (pl.col("team") == club)
    propios = t.filter(sel)["match_id"].unique().to_list()
    if not propios:
        raise ValueError(f"sin secuencias para {coach}" + (f" en {club}" if club else ""))
    todos = t.filter((pl.col("coach") == coach) | (pl.col("coach_faced") == coach))["match_id"].unique().to_list()
    otros = sorted(set(todos) - set(propios))
    en = pl.col("match_id").is_in(propios)
    return (t.filter(~pl.col("match_id").is_in(otros))
             .with_columns((sel & en).fill_null(False).alias("f"),
                           ((pl.col("coach_faced") == coach) & en).fill_null(False).alias("g"),
                           en.alias("partido_foco")))


def _signo(lo: float, hi: float) -> int:
    return 1 if lo > 0 else (-1 if hi < 0 else 0)


def _viaja_lista(a: dict, b: dict, k: int) -> bool:
    """Familia k: ambos IC excluyen 0 con el mismo signo."""
    sa, sb = _signo(a["lo"][k], a["hi"][k]), _signo(b["lo"][k], b["hi"][k])
    return sa != 0 and sa == sb


def _viaja_escalar(a: dict, b: dict) -> bool:
    sa, sb = _signo(a["lo"], a["hi"]), _signo(b["lo"], b["hi"])
    return sa != 0 and sa == sb


def _veredicto(A: dict, S: dict, familias: list[str]) -> dict:
    K = len(familias)
    v = {
        "H9 identidad defensiva": {familias[k]: _viaja_lista(A["H2"], S["H2"], k) for k in range(K)},
        "H10 eficiencia ofensiva": {familias[k]: _viaja_escalar(A[f"H7.{k + 1}"], S[f"H7.{k + 1}"])
                                    for k in range(K)},
        "H11 eficiencia defensiva": {familias[k]: _viaja_escalar(A[f"H8.{k + 1}"], S[f"H8.{k + 1}"])
                                     for k in range(K)},
    }
    # H12: diferencia de Δπ ofensivo entre clubes (SE aproximado desde los IC, independencia)
    h12 = {}
    for k in range(K):
        da, db = A["H1"]["delta_pi"][k], S["H1"]["delta_pi"][k]
        sa = (A["H1"]["hi"][k] - A["H1"]["lo"][k]) / (2 * 1.96)
        sb = (S["H1"]["hi"][k] - S["H1"]["lo"][k]) / (2 * 1.96)
        d, se = da - db, float(np.hypot(sa, sb))
        h12[familias[k]] = {"dif": d, "lo": d - 1.96 * se, "hi": d + 1.96 * se,
                            "excluye_0": bool(abs(d) > 1.96 * se)}
    v["H12 mezcla ofensiva distinta entre clubes"] = h12
    return v


POCOS_PARTIDOS = 30


def por_club(t: pl.DataFrame, coach: str, clubes: list[str], familias: list[str],
             cfg2: dict, seed: int) -> dict:
    """Cada club del foco contra la liga; el club con MÁS partidos es el principal y
    se compara contra cada uno de los demás (H9–H12). Con 2 clubes es exactamente el
    diseño pre-registrado; con 3 o más, cada par es una réplica de ese diseño."""
    res = {}
    for club in clubes:
        tc = reasignar_foco(t, coach, club)
        r = correr(tc, familias, {**cfg2, "foco": f"{coach} ({club})"}, seed)
        r["partidos"] = int(tc.filter(pl.col("f"))["match_id"].n_unique())
        res[club] = r
    orden = sorted(res, key=lambda c: -res[c]["partidos"])
    if len(orden) < 2:
        return {"clubes": res}
    principal = orden[0]
    ver = {}
    for c in orden[1:]:
        v = _veredicto(res[principal]["hipotesis"], res[c]["hipotesis"], familias)
        n = res[c]["partidos"]
        v["_partidos"] = {principal: res[principal]["partidos"], c: n}
        if n < POCOS_PARTIDOS:
            v["_aviso"] = (f"{c} tiene {n} partidos: poca potencia. Un «no se detecta en ambos» aquí "
                           f"NO significa «no viaja»; y sus IC son poco fiables (sandwich con pocos partidos).")
        ver[f"{principal} vs {c}"] = v
    return {"clubes": res, "principal": principal, "veredicto": ver}


def atlas(t: pl.DataFrame, familias: list[str], cfg2: dict, seed: int, min_partidos: int = 50,
          verbose: bool = True) -> pl.DataFrame:
    eras = (t.filter(pl.col("coach").is_not_null())
             .group_by("coach", "team").agg(pl.col("match_id").n_unique().alias("partidos"))
             .filter(pl.col("partidos") >= min_partidos).sort("partidos", descending=True))
    ligero = {**cfg2, "n_sim": cfg2.get("n_sim_atlas", 200), "n_boot": cfg2.get("n_boot_atlas", 300),
              "contexto": False}
    filas = []
    K = len(familias)
    for i, (coach, team, n) in enumerate(eras.iter_rows()):
        try:
            r = correr(reasignar_foco(t, coach, team), familias, {**ligero, "foco": coach}, seed)
        except Exception as e:  # una era problemática no tumba el atlas, pero se reporta
            if verbose:
                print(f"  [{i + 1}/{eras.height}] {coach} ({team}): ERROR {type(e).__name__}: {e}")
            continue
        H = r["hipotesis"]
        fila = {"coach": coach, "team": team, "partidos": n,
                "p_H1": H["H1"]["p"], "p_H2": H["H2"]["p"]}
        for k, fam in enumerate(familias):
            fila[f"ataque_{fam}"] = H["H1"]["delta_pi"][k]
            fila[f"defensa_{fam}"] = H["H2"]["delta_pi"][k]
            fila[f"efic_ataque_{fam}"] = H[f"H7.{k + 1}"]["dif"]
            fila[f"efic_defensa_{fam}"] = H[f"H8.{k + 1}"]["dif"]
        fila["norma_ataque_pp"] = 100 * float(np.abs(H["H1"]["delta_pi"]).sum() / 2)
        fila["norma_defensa_pp"] = 100 * float(np.abs(H["H2"]["delta_pi"]).sum() / 2)
        filas.append(fila)
        if verbose:
            print(f"  [{i + 1}/{eras.height}] {coach} ({team}, {n} p.): ataque {fila['norma_ataque_pp']:.1f} pp · "
                  f"defensa {fila['norma_defensa_pp']:.1f} pp", flush=True)
    return pl.DataFrame(filas).sort("norma_ataque_pp", descending=True)
