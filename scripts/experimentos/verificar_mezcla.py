#!/usr/bin/env python3
"""
Verificación (ADR-v2-67): ¿la optimización de mezcla.py (ADR-v2-64) cambió el vocabulario oficial?

Reajusta K = 3 con config/default.yaml y los datos reales TRES veces de forma comparable:
  1. «nuevo»: mezcla.py tal como está (optimizado);
  2. «previo»: mezcla.py de antes de la optimización, leído de git (`828c6b7~1`) y cargado como módulo aparte, sobre
     los MISMOS datos y con los mismos argumentos que `dtcoach mezcla`;
  3. «publicado»: la mezcla guardada en `mezcla_dir` (la de la entrega), sin reajustar.

La comparación decisiva es nuevo contra previo (mismo código salvo la optimización, mismos datos). Contra lo
publicado puede haber diferencias por OTRAS razones (datos actualizados después de publicar, p. ej. eras extendidas);
si nuevo = previo y ambos ≠ publicado, la optimización no es la causa.

Compara: J final, los π_k, P, P0, μ, número de iteraciones del último EM y el acuerdo suave de las responsabilidades.
NO escribe en reports/mezcla ni en mezcla_dir. Salida: reports/experimentos/verificar_mezcla/VERIFICAR.md (+ .json).

Uso (raíz del repo):  python scripts/experimentos/verificar_mezcla.py         (dos ajustes completos, minutos)
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from dtcoach import mezcla as nuevo
from dtcoach.cli import _datos
from dtcoach.config import RAIZ, Config

REF = "828c6b7~1"         # último commit con mezcla.py anterior a la optimización (ADR-v2-64)


def _previo():
    """mezcla.py de REF como módulo `dtcoach._mezcla_previa` (sus importaciones relativas resuelven contra dtcoach)."""
    src = subprocess.run(["git", "-C", str(RAIZ), "show", f"{REF}:src/dtcoach/mezcla.py"], check=True,
                         capture_output=True, text=True).stdout
    f = Path(tempfile.mkdtemp()) / "_mezcla_previa.py"
    f.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("dtcoach._mezcla_previa", f)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "dtcoach"
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert "_lse" not in src, "REF ya trae la optimización: no sirve de referencia"
    return mod


def _ajuste(mod, d, K, mc, seed):
    t0 = time.time()
    m = mod.ajustar(d, K, mc["lam"], mc["a0"], mc["n_init"], mc["max_iter"], mc["tol"], seed, init="escalera",
                    n_corto=mc.get("n_corto", 25), paso_inicial=mc.get("paso_inicial", True), lam0=mc.get("lam0"))
    # el módulo previo devuelve SU clase Mezcla: se pasa a la del módulo nuevo (mismos campos) para comparar
    m = nuevo.Mezcla(m.pi, m.mu, m.P, m.lam, m.a0, list(m.objetivo), m.diagnostico, m.P0)
    return m, time.time() - t0


def _rel(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape:
        return float("inf")
    return float(np.max(np.abs(a - b) / np.maximum(np.abs(b), 1e-300))) if a.size else 0.0


def comparar(a, b, d, mod_r) -> dict:
    ra, rb = mod_r.responsabilidades(a, d), mod_r.responsabilidades(b, d)
    return {"J": _rel(a.objetivo[-1], b.objetivo[-1]), "pi": _rel(a.pi, b.pi), "P": _rel(a.P, b.P),
            "P0": _rel(a.P0, b.P0) if a.P0 is not None and b.P0 is not None else float("nan"), "mu": _rel(a.mu, b.mu),
            "iteraciones": [len(a.objetivo), len(b.objetivo)], "acuerdo_suave": nuevo.acuerdo_suave(ra, rb),
            "identico_bit_a_bit": bool(np.array_equal(a.P, b.P) and np.array_equal(a.pi, b.pi)
                                       and a.objetivo == b.objetivo)}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None, help="por omisión config/default.yaml (el vocabulario oficial)")
    cfg = Config.load(ap.parse_args().config)
    mc, K = cfg["mezcla"], 3
    out = cfg.ruta("reportes") / "experimentos" / "verificar_mezcla"
    out.mkdir(parents=True, exist_ok=True)
    d = _datos(cfg)
    print(f"{d.n:,} secuencias; ajustando K = {K} con el código nuevo y con el previo ({REF})…", flush=True)
    previo = _previo()
    m_new, t_new = _ajuste(nuevo, d, K, mc, cfg["seed"])
    print(f"  nuevo: {t_new:.0f} s, J = {m_new.objetivo[-1]!r}", flush=True)
    m_old, t_old = _ajuste(previo, d, K, mc, cfg["seed"])
    print(f"  previo: {t_old:.0f} s, J = {m_old.objetivo[-1]!r}", flush=True)
    res = {"datos": {"secuencias": d.n}, "tiempos_s": {"nuevo": t_new, "previo": t_old},
           "nuevo_vs_previo": comparar(m_new, m_old, d, nuevo)}
    pub = cfg.ruta("mezcla_dir") / f"mezcla_K{K}.npz"
    if pub.exists():
        m_pub = nuevo.Mezcla.cargar(pub)
        res["nuevo_vs_publicado"] = comparar(m_new, m_pub, d, nuevo)
        res["previo_vs_publicado"] = comparar(m_old, m_pub, d, nuevo)
    (out / "verificar.json").write_text(json.dumps(res, indent=1, default=float))
    ok = res["nuevo_vs_previo"]["identico_bit_a_bit"]
    md = ["# ¿La optimización de mezcla.py cambió el vocabulario oficial? (ADR-v2-67)", "",
          f"{d.n:,} secuencias, config/default.yaml, K = {K}, semilla {cfg['seed']}. Código previo: `{REF}`.", "",
          "| comparación | J | π | P | P0 | μ | iteraciones | acuerdo suave | ¿idéntico bit a bit? |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k, nom in (("nuevo_vs_previo", "nuevo vs previo (decisiva)"), ("nuevo_vs_publicado", "nuevo vs publicado"),
                   ("previo_vs_publicado", "previo vs publicado")):
        if k in res:
            c = res[k]
            md.append(f"| {nom} | {c['J']:.2e} | {c['pi']:.2e} | {c['P']:.2e} | {c['P0']:.2e} | {c['mu']:.2e} | "
                      f"{c['iteraciones'][0]} / {c['iteraciones'][1]} | {c['acuerdo_suave']:.6f} | "
                      f"{'sí' if c['identico_bit_a_bit'] else 'no'} |")
    md += ["", "*Diferencias relativas máximas. Las iteraciones son las del último EM de cada ajuste.*", "",
           f"Tiempo de un ajuste: nuevo {t_new:.0f} s, previo {t_old:.0f} s ({t_old / max(t_new, 1e-9):.1f}×).", "",
           ("**VEREDICTO: la optimización NO cambió nada** (nuevo = previo bit a bit)." if ok else
            "**VEREDICTO: DIFIEREN. PARA: no integrar nada y avisar.**")]
    if ok and "nuevo_vs_publicado" in res and not res["nuevo_vs_publicado"]["identico_bit_a_bit"]:
        md.append("Nuevo = previo pero ambos ≠ publicado: la diferencia con lo publicado NO viene de la optimización "
                  "(datos o código posteriores a la publicación); revisar aparte.")
    (out / "VERIFICAR.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
