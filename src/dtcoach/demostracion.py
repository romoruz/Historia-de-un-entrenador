"""
La regla de demostración (11_HIPOTESIS, enmienda del 2026-09-30): nada se narra sin prueba.

QUÉ SE JUNTA
------------
De TODOS los resultados del foco (fase 2, fase 3a por club, decisiones y las siete secciones):
  1. las hipótesis (H1–H26), con su p;
  2. cada comparación foco contra liga de cada métrica (p por bootstrap de partidos);
  3. cada efecto con IC que se narra (contexto de la fase 2, perfiles por familia): p por la
     aproximación normal de su IC, p = 2 Φ(−|dif| / ee), ee = (hi − lo) / (2 · 1.96);
  4. las pruebas formales que cada sección declara en `pruebas` (cadena del xDefense,
     heterogeneidad entre técnicos, rutinas, receta Arsenal, laterales, proyección…).

UNA SOLA FAMILIA
----------------
Todo entra a un único Benjamini-Hochberg (α = 0.05). Una afirmación queda DEMOSTRADA si su q < α
y, si es del foco, tiene ≥ 20 partidos del foco (ADR-v2-28). Lo demás no se narra. Las afirmaciones
que por diseño no se pueden probar con estos datos (las 🔎: confundidas con el calendario) se
listan aparte como no demostrables. Para una prueba de equivalencia (TOST) "demostrado" quiere decir
que la diferencia CABE en el margen declarado; para una de heterogeneidad, que los técnicos sí
difieren (τ² > 0).

BH controla la proporción esperada de falsos descubrimientos también bajo dependencia positiva
entre pruebas (Benjamini & Yekutieli 2001), que es el caso aquí (métricas del mismo partido).
No corrige que algunas preguntas se hayan formulado después de ver datos: eso se declara.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
from scipy import stats

from .inference import benjamini_hochberg

MIN_PARTIDOS = 20
# ramas que no son afirmaciones nuevas (diagnósticos) o que ya entran por `pruebas` (sin duplicar)
SALTAR = {"hipotesis", "pruebas", "score_boot", "calibracion", "modelo", "bh_global", "validacion_liga", "xpts",
          "cadena", "tasas", "rutinas", "laterales", "tiros_libres", "validacion", "eficiencia", "modelos_xdefensa",
          "perfil_defensivo", "marca_vs_remate", "proyeccion", "partido_tipo", "mas_sorprendentes", "resumen_foco"}


def _nombres() -> dict:
    from . import balon_parado as bp
    from . import defensa as df_
    from . import futbol as fb
    from . import ofensiva as of
    from . import xdefensa as xd
    d = {}
    for m in (fb, of, df_, bp, xd):
        d.update({k: v["nombre"] for k, v in m.DEFINICIONES.items()})
    d.update({k: v["nombre"] for k, v in xd.DEFINICIONES_CADENA.items()})
    return d


def _p_de_ic(dif: float, lo: float, hi: float) -> float:
    ee = (hi - lo) / (2 * 1.959964)
    return float(2 * stats.norm.sf(abs(dif) / ee)) if ee > 0 else float("nan")


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and np.isfinite(x)


def _etiquetas(padre: str, ctx: list) -> list | None:
    """Nombres de los componentes de un efecto en lista, según dónde está."""
    from .decisiones import TIPOS
    fams = [n.split(" · ", 1)[1] for n in ctx if n.startswith("uso · ")]
    if padre == "perfiles":
        return ctx
    if padre == "contexto":
        return fams
    if padre == "tipo_cambio":
        return list(TIPOS)
    return None


def recolectar(obj, seccion: str, ruta: str, nombres: dict, out: list, pocos_rama: bool = False,
               padre: str = "", ctx: list | None = None) -> None:
    """Recorre un JSON de resultados y agrega cada afirmación con p."""
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            recolectar(v, seccion, f"{ruta}[{i}]", nombres, out, pocos_rama, padre, ctx)
        return
    if not isinstance(obj, dict):
        return
    ctx = obj.get("metricas_perfil") if isinstance(obj.get("metricas_perfil"), list) else (ctx or [])
    mod = obj.get("modelo") or {}
    pocos_rama = pocos_rama or bool("aviso_foco" in mod or (mod.get("partidos_foco") or 99) < MIN_PARTIDOS)
    # 1. hipótesis
    if isinstance(obj.get("hipotesis"), dict):
        for k, h in obj["hipotesis"].items():
            if not isinstance(h, dict):
                continue
            base = {"seccion": seccion, "id": f"{ruta}/{k}".lstrip("/"), "clase": "hipótesis",
                    "afirmacion": f"{k}: {h.get('nombre', '')}", "efecto": h.get("dif"), "lo": h.get("lo"),
                    "hi": h.get("hi"), "partidos_foco": h.get("partidos_foco"), "tipo": "diferencia"}
            if h.get("etiqueta") == "🔎":
                out.append(base | {"p": float("nan"), "no_demostrable": h.get("nota", "confundida por diseño")})
            elif _num(h.get("p")):
                out.append(base | {"p": float(h["p"]), "pocos": pocos_rama})
    # 4. pruebas declaradas
    for pr in obj.get("pruebas") or []:
        if isinstance(pr, dict) and _num(pr.get("p")):
            out.append({"seccion": seccion, "id": f"{ruta}/{pr['id']}".lstrip("/"), "clase": "prueba",
                        "afirmacion": pr["afirmacion"], "p": pr["p"], "efecto": pr.get("efecto"), "lo": pr.get("lo"),
                        "hi": pr.get("hi"), "partidos_foco": pr.get("partidos_foco"), "tipo": pr.get("tipo", "diferencia"),
                        "pocos": pocos_rama})
    for k, v in obj.items():
        if k in SALTAR or k.startswith("etapas_"):
            continue
        r = f"{ruta}/{k}"
        if isinstance(v, dict) and _num(v.get("p")) and _num(v.get("dif")) and "foco" in v:
            # 2. comparación de una métrica (o de una hipótesis ya incluida con otro nombre)
            fila = {"seccion": seccion, "id": r.lstrip("/"), "clase": "métrica",
                    "afirmacion": nombres.get(k, k) + (f" ({v['lado']})" if v.get("lado") == "rival" else ""),
                    "p": float(v["p"]), "efecto": v["dif"], "lo": v.get("lo"), "hi": v.get("hi"),
                    "partidos_foco": v.get("partidos_foco"), "tipo": "diferencia", "pocos": pocos_rama}
            if v.get("etiqueta") == "🔎":
                fila |= {"p": float("nan"), "no_demostrable": "confundida con el calendario (Copa y Concachampions "
                                                               "no están en los datos)"}
            out.append(fila)
            continue
        if isinstance(v, dict) and isinstance(v.get("dif"), list) and isinstance(v.get("lo"), list):
            # 3. efectos con IC en listas (contexto de la fase 2)
            ps = v.get("p") if isinstance(v.get("p"), list) else None
            et = _etiquetas(padre, ctx) or []
            for i, (d, lo, hi) in enumerate(zip(v["dif"], v["lo"], v["hi"])):
                if not (_num(d) and _num(lo) and _num(hi)):
                    continue
                p = ps[i] if ps and _num(ps[i]) else _p_de_ic(d, lo, hi)
                comp = et[i] if i < len(et) else f"componente {i + 1}"
                pref = {"contexto": "cambio del foco contra la liga", "tipo_cambio": "cambios"}.get(padre, "")
                out.append({"seccion": seccion, "id": f"{r}[{i}]".lstrip("/"), "clase": "efecto",
                            "afirmacion": f"{pref + ' ' if pref else ''}{k} · {comp}", "p": p, "efecto": d, "lo": lo,
                            "hi": hi, "partidos_foco": None, "tipo": "diferencia", "pocos": pocos_rama})
            continue
        recolectar(v, seccion, r, nombres, out, pocos_rama, k, ctx)


def demostrar(archivos: dict[str, Path], alpha: float = 0.05) -> pl.DataFrame:
    """Un solo BH sobre todo lo que se afirma. `archivos`: {sección: json}."""
    nombres, filas = _nombres(), []
    for sec, a in archivos.items():
        if Path(a).exists():
            recolectar(json.loads(Path(a).read_text()), sec, "", nombres, filas)
    if not filas:
        return pl.DataFrame()
    # efecto, IC y partidos: solo escalares (algunas hipótesis globales guardan vectores)
    for f in filas:
        for c in ("efecto", "lo", "hi", "partidos_foco"):
            f[c] = float(f[c]) if _num(f.get(c)) else None
    d = pl.DataFrame(filas, infer_schema_length=None).with_columns(
        pl.col("p").cast(pl.Float64), pl.col("efecto").cast(pl.Float64), pl.col("lo").cast(pl.Float64),
        pl.col("hi").cast(pl.Float64), pl.col("partidos_foco").cast(pl.Float64),
        pl.col("pocos").fill_null(False))
    if "no_demostrable" not in d.columns:
        d = d.with_columns(pl.lit(None, dtype=pl.Utf8).alias("no_demostrable"))
    prob = d.filter(pl.col("p").is_not_nan() & pl.col("no_demostrable").is_null())
    resto = d.filter(~(pl.col("p").is_not_nan() & pl.col("no_demostrable").is_null()))
    q, rech = benjamini_hochberg(prob["p"].to_numpy(), alpha)
    pocos = prob["pocos"].to_numpy() | (prob["partidos_foco"].fill_null(99).to_numpy() < MIN_PARTIDOS)
    prob = prob.with_columns(pl.Series("q", q), pl.Series("veredicto", np.where(
        rech & ~pocos, "demostrado", np.where(rech, "pocos partidos", "no demostrado"))))
    resto = resto.with_columns(pl.lit(float("nan")).alias("q"), pl.lit("no demostrable").alias("veredicto"))
    return pl.concat([prob, resto], how="diagonal_relaxed")


def _fmt(x) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:+.4g}"


def reporte(D: pl.DataFrame, foco: str, alpha: float = 0.05) -> list[str]:
    n = D.filter(pl.col("veredicto") != "no demostrable").height
    dem = D.filter(pl.col("veredicto") == "demostrado")
    md = [f"# Demostración — {foco}", "",
          f"**Regla:** se juntan {n:,} afirmaciones con prueba formal (hipótesis, comparaciones de métricas, efectos y "
          f"pruebas de cada sección) en **un solo Benjamini-Hochberg** (α = {alpha}). Queda **demostrado** lo que tiene "
          f"q < {alpha} y, si es del foco, ≥ {MIN_PARTIDOS} partidos suyos. Lo demás **no se narra**.", "",
          f"- demostradas: **{dem.height:,}**",
          f"- no demostradas: {D.filter(pl.col('veredicto') == 'no demostrado').height:,}",
          f"- significativas pero con pocos partidos del foco: {D.filter(pl.col('veredicto') == 'pocos partidos').height:,}",
          f"- no demostrables por diseño: {D.filter(pl.col('veredicto') == 'no demostrable').height:,}", "",
          "*Nota honesta: BH controla la multiplicidad, no el hecho de que algunas preguntas (balón parado por familias, "
          "pruebas de la proyección) se formularon después de ver la fase G. Por eso también se reportan por separado.*",
          ""]
    for sec in D["seccion"].unique(maintain_order=True).to_list():
        s = dem.filter(pl.col("seccion") == sec).sort("q")
        tot = D.filter((pl.col("seccion") == sec) & (pl.col("veredicto") != "no demostrable")).height
        md += [f"## {sec}: {s.height} de {tot} demostradas", ""]
        if s.height:
            md += ["| afirmación | clase | efecto [IC 95 %] | p | q |", "|---|---|---|---|---|"]
            md += [f"| {r['afirmacion']} | {r['clase']}{' (equivalencia)' if r['tipo'] == 'equivalencia' else ''} | "
                   f"{_fmt(r['efecto'])} [{_fmt(r['lo'])}, {_fmt(r['hi'])}] | {r['p']:.2g} | {r['q']:.2g} |"
                   for r in s.iter_rows(named=True)]
            md.append("")
    nd = D.filter(pl.col("veredicto") == "no demostrable")
    if nd.height:
        md += ["## No demostrables con estos datos (se retiran de la historia)", ""]
        md += [f"- {r['afirmacion']}: {r['no_demostrable']}" for r in nd.iter_rows(named=True)]
        md.append("")
    md += ["La lista completa, con cada p y q, está en `demostracion.csv`.", ""]
    return md
