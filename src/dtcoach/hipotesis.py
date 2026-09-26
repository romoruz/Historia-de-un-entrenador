"""
Fase 2 -- Las hipotesis, pre-registradas en docs/11_HIPOTESIS.md.

H1  identidad ofensiva      Δpi (ataque del foco vs liga en sus mismas situaciones)   Wald gl=K-1
H2  identidad defensiva     Δpi (lo que le logran sus rivales vs liga)               Wald gl=K-1
H3  reacción al marcador    f×perdiendo, f×ganando                                    Wald gl=2(K-1)
H4  final del partido       f×tramo_75+                                               Wald gl=K-1
H5  localía                 f×local                                                   Wald gl=K-1
H6  fuerza del rival        f×elo_dif                                                 Wald gl=K-1
H7  eficiencia ofensiva     xG por secuencia DENTRO de cada familia, foco vs liga      bootstrap
H8  eficiencia defensiva    xG concedido por secuencia dentro de cada familia          bootstrap

Todas son bilaterales. Multiplicidad: Benjamini-Hochberg sobre la familia completa
de p-valores. Etiquetas: 🟢 q < alpha · 🟡 p < alpha pero no sobrevive BH ·
⚪ no detectado (se reporta el mayor efecto compatible, nunca "no hay efecto").
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .contexto import diseno
from .inference import benjamini_hochberg
from .pesos import ajustar_pesos, columnas_estimables, efecto_promedio, pi_en
from .perfil import nombres_metricas, perfiles

ESCENARIOS = {
    # nombre: (columna de la tabla, valor "tratado", valor "base")
    "perdiendo vs empatando": ("score_state", "losing", "drawing"),
    "ganando vs empatando": ("score_state", "winning", "drawing"),
    "minuto 75+ vs 60-74": ("tramo", "75+", "60-74"),
    "local vs visitante": ("local", True, False),
    "rival 100 Elo más fuerte vs igual": ("elo_dif", -1.0, 0.0),
}


def _con(t: pl.DataFrame, col: str, val) -> pl.DataFrame:
    return t.with_columns(pl.lit(val, dtype=t.schema[col]).alias(col))


def modelo_contexto(t: pl.DataFrame, K: int, ref: int = 1):
    """Ajusta el logit fraccional de la fase 2. Devuelve (modelo, D, quitadas), con
    D(tabla, f=..., g=...) la matriz de diseño con las MISMAS columnas del ajuste."""
    temporadas = sorted(t["season_id"].drop_nulls().unique().to_list())
    X_all, nombres_all = diseno(t, temporadas=temporadas)
    keep = columnas_estimables(X_all, nombres_all)
    nombres = [n_ for n_, k in zip(nombres_all, keep) if k]
    quitadas = [n_ for n_, k in zip(nombres_all, keep) if not k]

    def D(tab, **kw):
        return diseno(tab, temporadas=temporadas, **kw)[0][:, keep]

    R = t.select([f"r_{k + 1}" for k in range(K)]).to_numpy()
    m = ajustar_pesos(X_all[:, keep], R, t["match_id"].to_numpy(), nombres, ref=ref)
    return m, D, quitadas


def correr(t: pl.DataFrame, familias: list[str], cfg2: dict, seed: int) -> dict:
    K = len(familias)
    m, D, quitadas = modelo_contexto(t, K, cfg2.get("ref", 1))
    nombres = m.nombres
    sims = m.simular(cfg2["n_sim"], seed)

    tf = t.filter(pl.col("f"))
    tg = t.filter(pl.col("g"))
    X1f, X0f = D(tf), D(tf, f=np.zeros(tf.height))
    X1g, X0g = D(tg), D(tg, g=np.zeros(tg.height))

    res: dict = {"modelo": {"n": m.n, "partidos": m.n_grupos, "convergio": m.convergio,
                            "cuasi_loglik": m.cuasi_loglik, "coeficientes": nombres,
                            "columnas_no_estimables": quitadas}}
    n_pf = int(t.filter(pl.col("f"))["match_id"].n_unique())
    res["modelo"]["partidos_foco"] = n_pf
    if n_pf < 20:
        res["modelo"]["aviso_foco"] = (f"solo {n_pf} partidos del foco: la varianza sandwich de sus "
                                       "coeficientes se apoya en muy pocos conglomerados y sus IC tienden a "
                                       "ser demasiado estrechos. Lectura exploratoria, sin 🟢.")
    if m.n_grupos <= len(m.theta):
        res["modelo"]["aviso"] = (f"{m.n_grupos} partidos para {len(m.theta)} parámetros: "
                                  "la varianza sandwich es poco fiable")
    H = {}
    e1 = efecto_promedio(m, X1f, X0f, sims)
    e1["pi_foco"] = pi_en(m, X1f, sims)["pi"]
    e1["pi_liga"] = pi_en(m, X0f, sims)["pi"]
    H["H1"] = {"nombre": "identidad ofensiva", **e1}
    e2 = efecto_promedio(m, X1g, X0g, sims)
    e2["pi_foco"] = pi_en(m, X1g, sims)["pi"]
    e2["pi_liga"] = pi_en(m, X0g, sims)["pi"]
    H["H2"] = {"nombre": "identidad defensiva", **e2}
    H["H3"] = {"nombre": "reacción al marcador", **m.wald(["f×perdiendo", "f×ganando"])}
    H["H4"] = {"nombre": "final del partido", **m.wald(["f×tramo_75+"])}
    H["H5"] = {"nombre": "localía", **m.wald(["f×local"])}
    H["H6"] = {"nombre": "fuerza del rival", **m.wald(["f×elo_dif"])}

    # Traducción de H3-H6 a la cancha: diferencia de diferencias en probabilidad
    contexto = {}
    for esc, (col, v1, v0) in (ESCENARIOS.items() if cfg2.get("contexto", True) else []):
        a1, a0 = D(_con(tf, col, v1)), D(_con(tf, col, v0))
        b1, b0 = D(_con(tf, col, v1), f=np.zeros(tf.height)), D(_con(tf, col, v0), f=np.zeros(tf.height))

        def dd(th=None):
            foco = (m.predecir(a1, th) - m.predecir(a0, th)).mean(0)
            liga = (m.predecir(b1, th) - m.predecir(b0, th)).mean(0)
            return foco, liga
        foco, liga = dd()
        draws = np.stack([np.subtract(*dd(th)) for th in sims])
        contexto[esc] = {"cambio_foco": foco.tolist(), "cambio_liga": liga.tolist(),
                         "dif": (foco - liga).tolist(),
                         "lo": np.quantile(draws, 0.025, 0).tolist(),
                         "hi": np.quantile(draws, 0.975, 0).tolist()}
    res["contexto"] = contexto

    pf = perfiles(t, K, cfg2["n_boot"], seed)
    res["perfiles"] = pf
    res["metricas_perfil"] = nombres_metricas(K, familias)
    for lado, h in (("ataque", "H7"), ("defensa", "H8")):
        for k in range(K):
            i = K + k                                   # bloque "xG por secuencia · familia"
            H[f"{h}.{k + 1}"] = {
                "nombre": f"eficiencia {'ofensiva' if lado == 'ataque' else 'defensiva'} · {familias[k]}",
                "foco": pf[lado]["foco"][i], "liga": pf[lado]["liga"][i],
                "dif": pf[lado]["dif"][i], "lo": pf[lado]["lo"][i], "hi": pf[lado]["hi"][i],
                "p": pf[lado]["p"][i]}

    claves = list(H)
    p = np.array([H[c]["p"] for c in claves])
    q, rech = benjamini_hochberg(p, cfg2["alpha"])
    pocos = n_pf < 20
    for c, qi, ri, pi_ in zip(claves, q, rech, p):
        H[c]["q"] = float(qi)
        H[c]["etiqueta"] = ("🟡" if (ri or pi_ < cfg2["alpha"]) else "⚪") if pocos else \
                           ("🟢" if ri else ("🟡" if pi_ < cfg2["alpha"] else "⚪"))
    res["hipotesis"] = H
    res["frases"] = frases(H, contexto, familias, cfg2)
    return res


def _pp(x: float) -> str:
    return f"{100 * x:+.1f} pp"


def frases(H: dict, contexto: dict, familias: list[str], cfg2: dict) -> list[str]:
    foco = cfg2["foco"]
    out = []
    for h, quien in (("H1", "sus secuencias"), ("H2", "las secuencias de sus rivales")):
        e = H[h]
        for k, fam in enumerate(familias):
            out.append(
                f"[{h} {e['etiqueta']}] Con {foco}, {100 * e['pi_foco'][k]:.1f} % de {quien} son "
                f"«{fam}», contra {100 * e['pi_liga'][k]:.1f} % de la liga en las mismas situaciones "
                f"({_pp(e['delta_pi'][k])}, IC 95 % [{_pp(e['lo'][k])}, {_pp(e['hi'][k])}]).")
    for esc, c in contexto.items():
        for k, fam in enumerate(familias):
            excluye = c["lo"][k] > 0 or c["hi"][k] < 0
            if excluye:
                out.append(
                    f"[contexto] {esc}: el equipo de {foco} cambia su uso de «{fam}» {_pp(c['cambio_foco'][k])}; "
                    f"la liga, {_pp(c['cambio_liga'][k])} (diferencia {_pp(c['dif'][k])}, "
                    f"IC [{_pp(c['lo'][k])}, {_pp(c['hi'][k])}]).")
    for h in [k for k in H if k.startswith(("H7", "H8"))]:
        e = H[h]
        if e["etiqueta"] == "⚪":
            cota = max(abs(e["lo"]), abs(e["hi"]))
            out.append(f"[{h} ⚪] {e['nombre']}: no detectamos una diferencia mayor a "
                       f"{cota:.4f} xG por secuencia.")
        else:
            out.append(f"[{h} {e['etiqueta']}] {e['nombre']}: {e['foco']:.4f} contra {e['liga']:.4f} "
                       f"xG por secuencia (dif. {e['dif']:+.4f}, IC [{e['lo']:+.4f}, {e['hi']:+.4f}]).")
    return out


def tabla_md(res: dict) -> str:
    L = ["| hipótesis | qué se prueba | estadístico | p | q (BH) | evidencia |",
         "|---|---|---|---|---|---|"]
    for k, h in res["hipotesis"].items():
        est = (f"W={h['W']:.1f} (gl {h['gl']})" + (" ⚠" if "nota" in h else "")) if "W" in h else f"dif={h['dif']:+.4f} [{h['lo']:+.4f}, {h['hi']:+.4f}]"
        L.append(f"| {k} | {h['nombre']} | {est} | {h['p']:.4f} | {h['q']:.4f} | {h['etiqueta']} |")
    return "\n".join(L)
