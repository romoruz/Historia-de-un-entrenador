"""
xDefense a balón parado (reto 5.4, G5): cuánto evita un equipo, separado en dos capas.

LA DESCOMPOSICIÓN (ley de probabilidad total)
---------------------------------------------
Para un centro a balón parado C (corner, tiro libre al área, lateral largo al área):
    P(gol | C) = P(remate | C) · P(gol | remate, C)
  Capa 1, PREVENCIÓN:  P(remate | C). ¿Niega el remate?
  Capa 2, SUPRESIÓN:   P(gol | remate). Si le rematan, ¿empeora el remate?
Es el marco del trabajo previo del equipo (xDefense de corners). Dos límites que ese
trabajo declaraba y que aquí se corrigen:
  1. SESGO DE SELECCIÓN. Con solo la foto del remate, la mejor defensa (el centro
     despejado sin remate) era invisible. Aquí la capa 1 usa el frame 360 DEL COBRO,
     que existe haya o no remate.
  2. POCO PODER (51 goles). Aquí entra toda la Liga MX (1,767 partidos).

CAPA 1 — logit L2 de "hubo remate del que saca en la ventana" con los rasgos de la
INTENCIÓN del cobro y del ataque: tipo de jugada, lado, técnica, altura, zona de
destino, largo, posición del saque, minuto y, del 360, atacantes en el área, en el
área chica y encima del portero. NO entran rasgos de la defensa (ni el desenlace del
pase: fuga del objetivo), porque lo que se quiere medir es justamente la defensa.
    xD_prev(equipo) = Σ_i [ p̂_i − S_i ] / n     (> 0: concede menos remates de los esperados)
Las p̂ son FUERA DE MUESTRA (validación cruzada por partido): ningún centro se predice
con un modelo que lo vio.

CAPA 2 — sobre los remates a balón parado con su `shot_freeze_frame`, dos modelos
de gol en la MISMA muestra, que difieren solo en la geometría defensiva:
    xG_base = E[G | ataque]            distancia, ángulo, cabeza, de primera, tipo de jugada
    xG_full = E[G | ataque, defensa]   + visibilidad del arco, defensor más cercano,
                                         defensores a ≤ 3 m, profundidad y desvío del portero
    xD_remate(i) = xG_base(i) − xG_full(i)   (> 0: la defensa empeoró ese remate)
Para tener poder, los modelos se ajustan con TODOS los remates de la liga (juego abierto
incluido, con el tipo de jugada como covariable): la física del arco es la misma.
xG_base NO es "un remate sin defensa": es el promedio sobre las defensas de la muestra,
así que xD_remate es relativo a la defensa promedio.

VISIBILIDAD DEL ARCO (goal_open, del trabajo previo)
----------------------------------------------------
Desde el punto de remate s, el arco subtiende el intervalo angular I = [φ(P1), φ(P2)].
Cada defensor de campo j entre el remate y el arco (x_j > x_s), como un disco de radio
r, proyecta la sombra [φ_j − α_j, φ_j + α_j], α_j = arcsin(r / ‖s − D_j‖). Entonces
    goal_open = 1 − | I ∩ ∪_j S_j | / |I|
por unión de intervalos en una dimensión (O(m log m)).

LA CADENA COMPLETA Y SU DESCOMPOSICIÓN EXACTA (04_MODELO_MATEMATICO §16.5–16.6)
--------------------------------------------------------------------------------
En la ventana puede haber varios remates (el rechace vuelve). Con S_k = "hay un k-ésimo
remate" y q_k = P(gol en el k-ésimo | los anteriores fallaron), la probabilidad total
aplicada en cadena da la recursión
    V_k = P(S_k | ...) · [ q_k + (1 − q_k) · V_{k+1} ],     P(G | C) = V_1,
y por linealidad E[goles | C] = P(S | C) · E[Σ_k G_k | S, C]. Con κ_t = el valor medio de
un saque de tipo t que SÍ tuvo remate (Σ xG_base de sus remates, promedio de la liga), para
cada saque i vale, sin aproximación (sumar y restar):
    p̂_i κ_t − g_i = (p̂_i − s_i) κ_t        prevención   (remates negados, en goles)
                  + s_i (κ_t − B_i)        alejamiento  (remates desde peores lugares)
                  + s_i (B_i − F_i)        supresión    (la geometría defensiva al remate)
                  + s_i (F_i − g_i)        portero y definición
B_i, F_i = Σ xG_base, Σ xG_full de los remates del saque; g_i = goles. Para el que defiende
cada término positivo es un gol evitado; para el que saca, el signo cambia (xO = −xD).
El tiro libre directo no tiene capa 1 (el saque ES el remate): p̂ = s = 1.

POR ENTRENADOR
--------------
Las dos capas se agregan por equipo-partido (razón de sumas) y entran a la misma
maquinaria que el resto (foco contra liga, percentiles, fiabilidad). Además, como
muchas etapas tienen pocos centros, se contraen hacia la media de la liga con un
modelo normal-normal (Efron & Morris 1975; τ² por DerSimonian-Laird): lo que queda
tras descontar el ruido es la habilidad que se puede afirmar.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from .identidad import auc, logit_l2

POSTES = (36.0, 44.0)
R_CUERPO = 0.5


# ----------------------------------------------------------------------
# Geometría del remate
# ----------------------------------------------------------------------
def goal_open(sx: float, sy: float, defensores: np.ndarray, r: float = R_CUERPO) -> float:
    """Fracción del arco que ve el que remata, descontando la sombra de los defensores."""
    a1, a2 = np.arctan2(POSTES[0] - sy, 120.0 - sx), np.arctan2(POSTES[1] - sy, 120.0 - sx)
    lo, hi = min(a1, a2), max(a1, a2)
    ancho = hi - lo
    if ancho <= 0:
        return 0.0
    d = np.asarray(defensores, float).reshape(-1, 2)
    d = d[np.isfinite(d).all(axis=1) & (d[:, 0] > sx)]
    if len(d) == 0:
        return 1.0
    dist = np.hypot(d[:, 0] - sx, d[:, 1] - sy)
    fi = np.arctan2(d[:, 1] - sy, d[:, 0] - sx)
    al = np.arcsin(np.clip(r / np.maximum(dist, 1e-9), 0, 1))
    seg = np.column_stack([np.maximum(fi - al, lo), np.minimum(fi + al, hi)])
    seg = seg[seg[:, 1] > seg[:, 0]]
    if len(seg) == 0:
        return 1.0
    seg = seg[np.argsort(seg[:, 0])]
    cubierto, ini, fin = 0.0, seg[0, 0], seg[0, 1]
    for a, b in seg[1:]:
        if a > fin:
            cubierto += fin - ini
            ini, fin = a, b
        else:
            fin = max(fin, b)
    cubierto += fin - ini
    return float(1 - cubierto / ancho)


def barrera(sx: float, sy: float, defensores: np.ndarray, d_max: float = 12.0, r: float = R_CUERPO) -> int:
    """Defensores de campo a ≤ `d_max` m del balón que tapan parte del arco (la barrera de un tiro libre:
    la regla 13 la pone a 9.15 m)."""
    a1, a2 = np.arctan2(POSTES[0] - sy, 120.0 - sx), np.arctan2(POSTES[1] - sy, 120.0 - sx)
    lo, hi = min(a1, a2), max(a1, a2)
    d = np.asarray(defensores, float).reshape(-1, 2)
    d = d[np.isfinite(d).all(axis=1) & (d[:, 0] > sx)]
    if len(d) == 0:
        return 0
    dist = np.hypot(d[:, 0] - sx, d[:, 1] - sy)
    fi = np.arctan2(d[:, 1] - sy, d[:, 0] - sx)
    al = np.arcsin(np.clip(r / np.maximum(dist, 1e-9), 0, 1))
    return int(((dist <= d_max) & (fi + al > lo) & (fi - al < hi)).sum())


def angulo_arco(sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
    a1 = np.arctan2(POSTES[0] - sy, 120.0 - sx)
    a2 = np.arctan2(POSTES[1] - sy, 120.0 - sx)
    return np.abs(a2 - a1)


def rasgos_remate(sx: float, sy: float, ff_json: str | None) -> dict:
    """Rasgos defensivos del `shot_freeze_frame` (marco del que remata)."""
    nan = float("nan")
    base = {"goal_open": nan, "d_def": nan, "def_cerca": nan, "gk_prof": nan, "gk_desvio": nan, "barrera": nan,
            "con_frame": 0}
    if not ff_json:
        return base
    try:
        ff = json.loads(ff_json)
    except (TypeError, ValueError):
        return base
    de, gk = [], None
    for p in ff:
        loc = p.get("location")
        if not loc or len(loc) < 2 or p.get("teammate"):
            continue
        es_gk = ((p.get("position") or {}).get("name") == "Goalkeeper") or bool(p.get("keeper"))
        if es_gk:
            gk = (float(loc[0]), float(loc[1]))
        else:
            de.append((float(loc[0]), float(loc[1])))
    de = np.array(de, float).reshape(-1, 2)
    out = {"goal_open": goal_open(sx, sy, de), "barrera": float(barrera(sx, sy, de)), "con_frame": 1}
    if len(de):
        dist = np.hypot(de[:, 0] - sx, de[:, 1] - sy)
        out |= {"d_def": float(dist.min()), "def_cerca": float((dist <= 3.0).sum())}
    else:
        out |= {"d_def": 30.0, "def_cerca": 0.0}
    if gk is not None:
        # desvío: distancia del portero a la recta remate → centro del arco
        vx, vy = 120.0 - sx, 40.0 - sy
        n = np.hypot(vx, vy) or 1.0
        out |= {"gk_prof": 120.0 - gk[0], "gk_desvio": abs(vx * (gk[1] - sy) - vy * (gk[0] - sx)) / n}
    else:
        out |= {"gk_prof": nan, "gk_desvio": nan}
    return out


# ----------------------------------------------------------------------
# Diseño y ajuste fuera de muestra
# ----------------------------------------------------------------------
def _onehot(v: list, niveles: list, prefijo: str) -> tuple[np.ndarray, list[str]]:
    v = ["sin dato" if x is None else x for x in v]
    niv = [n for n in niveles if n in set(v)][1:]           # el primero es la referencia
    return np.column_stack([[x == n for x in v] for n in niv]).astype(float) if niv else \
        np.zeros((len(v), 0)), [f"{prefijo}={n}" for n in niv]


def _numerica(x: np.ndarray, nombre: str) -> tuple[np.ndarray, list[str]]:
    """Columna numérica con imputación por la media e indicador de faltante."""
    x = np.asarray(x, float)
    falta = ~np.isfinite(x)
    if falta.all():
        return np.zeros((len(x), 0)), []
    m = np.nanmean(x)
    xx = np.where(falta, m, x)
    if falta.any():
        return np.column_stack([xx, falta.astype(float)]), [nombre, f"{nombre}_falta"]
    return xx[:, None], [nombre]


def diseno_capa1(j: pl.DataFrame, tipos: tuple = ("corner", "tl_centrado", "lateral_largo")) -> tuple[np.ndarray, list[str]]:
    from .balon_parado import TECNICAS, ZONAS
    bloques = [_onehot(j["tipo"].to_list(), list(tipos), "tipo"),
               _onehot(j["lado"].to_list(), ["y0", "y80"], "lado"),
               _onehot(j["tecnica"].to_list(), ["sin dato", *TECNICAS, "Through Ball"], "tecnica"),
               _onehot(j["altura"].to_list(), ["sin dato", "Ground Pass", "Low Pass", "High Pass"], "altura"),
               _onehot(j["zona"].to_list(), list(ZONAS), "zona"),
               _numerica(j["largo"].to_numpy(), "largo"),
               _numerica(j["x_saque"].to_numpy(), "x_saque"),
               _numerica(np.abs(j["y_saque"].to_numpy() - 40.0), "abs_y_saque"),
               _numerica(j["minute"].to_numpy() / 90.0, "minuto")]
    if "at_area" in j.columns:
        vis = (j["cobertura_area"].fill_null(0.0).to_numpy() >= 0.8)
        for c in ("at_area", "at_chica", "at_portero"):
            v = j[c].cast(pl.Float64).to_numpy()
            bloques.append(_numerica(np.where(vis, v, np.nan), c))
    X = np.column_stack([b[0] for b in bloques])
    return X, [n for b in bloques for n in b[1]]


ATAQUE = ["log_dist", "angulo", "cabeza", "de_primera", "bp_corner", "bp_tl_centrado", "bp_lateral_largo",
          "bp_tl_directo", "bp_otro"]
DEFENSA = ["goal_open", "d_def", "def_cerca", "gk_prof", "gk_desvio"]


def diseno_capa2(r: pl.DataFrame, con_defensa: bool) -> tuple[np.ndarray, list[str]]:
    cols = [r[c].cast(pl.Float64).to_numpy() for c in ATAQUE]
    X, nom = np.column_stack(cols), list(ATAQUE)
    if con_defensa:
        for c in DEFENSA:
            b, n = _numerica(r[c].cast(pl.Float64).to_numpy(), c)
            X, nom = np.column_stack([X, b]), nom + n
    return X, nom


def _estandar(X: np.ndarray) -> np.ndarray:
    mu, sd = X.mean(0), X.std(0)
    return (X - mu) / np.where(sd > 0, sd, 1.0)


def fuera_de_muestra(X: np.ndarray, y: np.ndarray, grupos: np.ndarray, folds: int = 5, lam: float = 1.0,
                     seed: int = 0) -> np.ndarray:
    """p̂ de cada fila con un modelo ajustado SIN su partido (validación cruzada por partido)."""
    Z = _estandar(X)
    u = np.unique(grupos)
    rng = np.random.default_rng(seed)
    f = dict(zip(u, rng.permutation(len(u)) % folds))
    fold = np.array([f[g] for g in grupos])
    p = np.empty(len(y))
    for k in range(folds):
        te = fold == k
        if not te.any():
            continue
        b = logit_l2(Z[~te], y[~te], lam)
        p[te] = 1 / (1 + np.exp(-(b[0] + Z[te] @ b[1:])))
    return p


def coeficientes(X: np.ndarray, y: np.ndarray, nombres: list[str], lam: float = 1.0) -> list[dict]:
    """Coeficientes en desviaciones estándar (dirección, no magnitud exacta)."""
    b = logit_l2(_estandar(X), y, lam)
    return sorted([{"rasgo": n, "coef_de": float(c)} for n, c in zip(nombres, b[1:])],
                  key=lambda d: -abs(d["coef_de"]))


# ----------------------------------------------------------------------
# Las dos capas sobre la liga
# ----------------------------------------------------------------------
def capa1(j: pl.DataFrame, folds: int = 5, lam: float = 1.0, seed: int = 0,
          tipos: tuple | None = None) -> tuple[pl.DataFrame, dict]:
    """Prevención: p̂(remate | intención del cobro y ataque), fuera de muestra, por saque.
    Por omisión, los centros al área (el modelo pre-registrado de H24). Con `tipos` se ajusta un modelo
    APARTE para otros saques (tiros libres y laterales que no van al área), sin tocar el de los centros."""
    from .balon_parado import TIPOS_CENTRO
    tipos = tuple(TIPOS_CENTRO) if tipos is None else tuple(tipos)
    c = j.filter(pl.col("tipo").is_in(list(tipos)))
    X, nom = diseno_capa1(c, tipos)
    y = (c["remates"].to_numpy() > 0).astype(float)
    g = c["match_id"].to_numpy()
    if c.height < 50 or y.min() == y.max() or len(np.unique(g)) < folds:
        # muy pocos saques para un modelo: la tasa de la liga (xD = tasa − observado)
        p = np.full(c.height, y.mean() if c.height else 0.0)
        return c.select("match_id", "team", "id_saque", "tipo").with_columns(
            pl.Series("p_remate", p), pl.Series("remato", y)), {"tipos": list(tipos), "centros": c.height,
                                                                 "nota": "sin modelo: muy pocos saques"}
    p = fuera_de_muestra(X, y, g, folds, lam, seed)
    res = {"tipos": list(tipos), "centros": c.height, "tasa_remate": float(y.mean()), "auc_fuera_de_muestra": auc(p, y),
           "calibracion": float(p.mean() / max(y.mean(), 1e-12)), "coeficientes": coeficientes(X, y, nom, lam)[:12]}
    return c.select("match_id", "team", "id_saque", "tipo").with_columns(
        pl.Series("p_remate", p), pl.Series("remato", y)), res


def remates_liga(ev: pl.DataFrame, j: pl.DataFrame, ff: pl.DataFrame) -> pl.DataFrame:
    """Todos los remates (sin penales) con rasgos de ataque, tipo de jugada y su freeze frame.
    `ff`: id, shot_freeze_frame (del parquet de eventos)."""
    from .balon_parado import TIPOS_CENTRO  # noqa: F401  (documenta de dónde sale el tipo)
    tipo_de = {}
    for tipo, ids in j.select("tipo", "ids_remate").iter_rows():
        for i in ids or []:
            tipo_de[i] = tipo
    st = pl.col("shot_type") if "shot_type" in ev.columns else pl.lit(None)
    r = (ev.filter((pl.col("type") == "Shot") & (st != "Penalty").fill_null(True))
         .select("match_id", "id", "team", "x", "y", pl.col("shot_statsbomb_xg").fill_null(0.0).alias("xg_sb"),
                 (pl.col("shot_outcome") == "Goal").fill_null(False).alias("gol"),
                 (pl.col("shot_body_part") == "Head").fill_null(False).alias("cabeza")
                 if "shot_body_part" in ev.columns else pl.lit(False).alias("cabeza"),
                 pl.col("shot_first_time").fill_null(False).alias("de_primera")
                 if "shot_first_time" in ev.columns else pl.lit(False).alias("de_primera"))
         .join(ff, on="id", how="left"))
    tipos = [tipo_de.get(i, "abierto") for i in r["id"].to_list()]
    sx, sy = r["x"].to_numpy(), r["y"].to_numpy()
    rasgos = [rasgos_remate(a, b, f) for a, b, f in zip(sx, sy, r["shot_freeze_frame"].to_list())]
    R = pl.DataFrame(rasgos)
    return pl.concat([r.drop("shot_freeze_frame"), R], how="horizontal").with_columns(
        pl.Series("tipo_bp", tipos),
        pl.Series("log_dist", np.log(np.maximum(np.hypot(120.0 - sx, 40.0 - sy), 0.5))),
        pl.Series("angulo", angulo_arco(sx, sy)),
        *[pl.Series(f"bp_{t}", [float(x == t) for x in tipos]) for t in
          ("corner", "tl_centrado", "lateral_largo", "tl_directo")],
        pl.Series("bp_otro", [float(x in ("tl_otro", "lateral_zona")) for x in tipos]),
        pl.col("cabeza").cast(pl.Float64), pl.col("de_primera").cast(pl.Float64))


def capa2(r: pl.DataFrame, folds: int = 5, lam: float = 1.0, seed: int = 0, n_boot: int = 300) -> tuple[pl.DataFrame, dict]:
    """Supresión: xG_base contra xG_full (misma muestra), fuera de muestra, por remate."""
    r = r.filter(pl.col("con_frame") == 1)
    y = r["gol"].cast(pl.Float64).to_numpy()
    g = r["match_id"].to_numpy()
    Xb, nb = diseno_capa2(r, False)
    Xf, nf = diseno_capa2(r, True)
    pb = fuera_de_muestra(Xb, y, g, folds, lam, seed)
    pf = fuera_de_muestra(Xf, y, g, folds, lam, seed)
    rng = np.random.default_rng(seed)
    u, gi = np.unique(g, return_inverse=True)
    idx = [np.flatnonzero(gi == k) for k in range(len(u))]
    d = []
    for _ in range(n_boot):
        s = np.concatenate([idx[k] for k in rng.integers(0, len(u), len(u))])
        if y[s].min() == y[s].max():
            continue
        d.append(auc(pf[s], y[s]) - auc(pb[s], y[s]))
    d = np.array(d)
    res = {"remates": r.height, "goles": int(y.sum()), "auc_base": auc(pb, y), "auc_full": auc(pf, y),
           "delta_auc": auc(pf, y) - auc(pb, y),
           "delta_auc_lo": float(np.quantile(d, 0.025)) if len(d) else float("nan"),
           "delta_auc_hi": float(np.quantile(d, 0.975)) if len(d) else float("nan"),
           "coeficientes_full": coeficientes(Xf, y, nf, lam),
           "remates_bp": int((r["tipo_bp"] != "abierto").sum()),
           "goles_bp": int(r.filter(pl.col("tipo_bp") != "abierto")["gol"].sum())}
    extra = [c for c in ("x", "y", "goal_open", "barrera", "d_def", "gk_prof", "cabeza") if c in r.columns]
    return r.select("match_id", "id", "team", "tipo_bp", "gol", "xg_sb", *extra).with_columns(
        pl.Series("xg_base", pb), pl.Series("xg_full", pf)), res


def metricas_equipo(p1: pl.DataFrame, p2: pl.DataFrame, tp: pl.DataFrame) -> list[pl.DataFrame]:
    """xD por equipo-partido (razón de sumas): del que DEFIENDE (xd_*) y del que saca (xo_prev)."""
    from .balon_parado import TIPOS_CENTRO
    rival = tp.select("match_id", "team", "rival")
    p1 = p1.filter(pl.col("tipo").is_in(list(TIPOS_CENTRO)))          # H24: solo centros al área
    d1 = p1.join(rival, on=["match_id", "team"]).drop("team").rename({"rival": "team"})
    bp = p2.filter(pl.col("tipo_bp") != "abierto")
    d2 = bp.join(rival, on=["match_id", "team"]).drop("team").rename({"rival": "team"})
    return [
        d1.group_by("match_id", "team").agg((pl.col("p_remate") - pl.col("remato")).sum().alias("xd_prev__n"),
                                            pl.len().cast(pl.Float64).alias("xd_prev__d")),
        p1.group_by("match_id", "team").agg((pl.col("remato") - pl.col("p_remate")).sum().alias("xo_prev__n"),
                                            pl.len().cast(pl.Float64).alias("xo_prev__d")),
        d2.group_by("match_id", "team").agg((pl.col("xg_base") - pl.col("xg_full")).sum().alias("xd_remate__n"),
                                            pl.len().cast(pl.Float64).alias("xd_remate__d")),
        d2.group_by("match_id", "team").agg((pl.col("xg_full") - pl.col("gol").cast(pl.Float64)).sum()
                                            .alias("xd_gol__n"), pl.len().cast(pl.Float64).alias("xd_gol__d")),
    ]


DEFINICIONES = {
    "xd_prev": {"nombre": "xD prevención: remates evitados por centro en contra (esperados − reales)",
                "formato": "{:+.4f}"},
    "xo_prev": {"nombre": "remates generados por centro propio por encima de lo esperado", "formato": "{:+.4f}"},
    "xd_remate": {"nombre": "xD supresión: xG que su defensa le quita a cada remate (base − full)",
                  "formato": "{:+.4f}"},
    "xd_gol": {"nombre": "goles evitados por remate a balón parado (xG full − goles)", "formato": "{:+.4f}"},
    "arco_libre_tl": {"nombre": "fracción del arco que deja libre en tiros libres directos en contra (360)",
                      "formato": "{:.3f}"},
    "barrera_tl": {"nombre": "jugadores en la barrera en tiros libres directos en contra", "formato": "{:.2f}"},
}



# ----------------------------------------------------------------------
# La cadena completa: descomposición exacta por saque (04 §16.5–16.6)
# ----------------------------------------------------------------------
FAMILIAS = {"corner": ("corner",), "tiro_libre": ("tl_centrado", "tl_otro", "tl_directo"),
            "lateral": ("lateral_largo", "lateral_zona")}
FAMILIA_NOMBRE = {"corner": "corners", "tiro_libre": "tiros libres", "lateral": "laterales",
                  "todas": "todo el balón parado"}
COMPONENTES = ("prev", "lej", "sup", "port", "total")
COMPONENTE_NOMBRE = {"prev": "prevención (remates negados)", "lej": "alejamiento (remates desde peores lugares)",
                     "sup": "supresión (geometría al remate)", "port": "portero y definición",
                     "total": "total"}


DEFINICIONES_CADENA = {
    f"{lado}_{c}_{fam}": {"nombre": f"{'xD' if lado == 'xd' else 'xO'} · {COMPONENTE_NOMBRE[c]} · "
                                   f"{FAMILIA_NOMBRE[fam]} {'en contra' if lado == 'xd' else 'a favor'} "
                                   f"(goles por 100 saques)", "formato": "{:+.2f}"}
    for lado in ("xd", "xo") for c in COMPONENTES for fam in (*FAMILIAS, "todas")}


def familia_de(tipo: str) -> str | None:
    return next((f for f, ts in FAMILIAS.items() if tipo in ts), None)


def descomposicion(j: pl.DataFrame, p1: pl.DataFrame, p2: pl.DataFrame, lateral_cuarto_x: float = 0.0) -> pl.DataFrame:
    """Una fila por saque (de las tres familias) con p̂, s, B, F, g, κ y los cuatro términos de
    p̂κ − g, en goles, desde el punto de vista del que DEFIENDE (positivo = gol evitado).
    `p1`: capa 1 (todas las p̂ fuera de muestra); `p2`: capa 2 (xg_base, xg_full por remate con foto).
    Un remate sin foto entra con su xG del proveedor en B y en F (neutro para la supresión)."""
    tipos = [t for ts in FAMILIAS.values() for t in ts]
    rem = (j.select("id_saque", "ids_remate").explode("ids_remate", empty_as_null=True).rename({"ids_remate": "id"})
           .filter(pl.col("id").is_not_null())
           .join(p2.select("id", "xg_base", "xg_full", "xg_sb"), on="id", how="left")
           .group_by("id_saque").agg(pl.col("xg_base").sum().alias("_b"), pl.col("xg_full").sum().alias("_f"),
                                     pl.col("xg_sb").sum().alias("_sb")))
    # laterales que no van al área: solo los del último cuarto (5.4)
    atras = (pl.col("tipo") == "lateral_zona") & (pl.col("x_saque") < lateral_cuarto_x)
    d = (j.filter(pl.col("tipo").is_in(tipos) & ~atras)
         .select("match_id", "team", "id_saque", "tipo", "x_saque", "y_saque", "zona", "remates", "goles", "xg")
         .join(p1.select("id_saque", "p_remate"), on="id_saque", how="left")
         .join(rem, on="id_saque", how="left"))
    hay = pl.col("remates") > 0
    fuera = pl.col("xg") - pl.col("_sb").fill_null(0.0)                   # xG de los remates sin foto
    d = d.with_columns(
        pl.when(pl.col("tipo") == "tl_directo").then(1.0).otherwise(pl.col("p_remate")).alias("p"),
        hay.cast(pl.Float64).alias("s"),
        pl.when(hay).then(pl.col("_b").fill_null(0.0) + fuera).otherwise(0.0).alias("B"),
        pl.when(hay).then(pl.col("_f").fill_null(0.0) + fuera).otherwise(0.0).alias("F"),
        pl.col("goles").cast(pl.Float64).alias("g"),
        pl.col("tipo").replace_strict({t: f for f, ts in FAMILIAS.items() for t in ts}).alias("familia"),
    ).filter(pl.col("p").is_not_null()).drop("_b", "_f", "_sb", "p_remate")
    kappa = d.filter(pl.col("s") == 1).group_by("tipo").agg(pl.col("B").mean().alias("kappa"))
    d = d.join(kappa, on="tipo", how="left").with_columns(pl.col("kappa").fill_null(0.0))
    k, sv = pl.col("kappa"), pl.col("s")
    return d.with_columns(((pl.col("p") - sv) * k).alias("prev"), (sv * (k - pl.col("B"))).alias("lej"),
                          (sv * (pl.col("B") - pl.col("F"))).alias("sup"), (sv * (pl.col("F") - pl.col("g"))).alias("port"),
                          (pl.col("p") * k - pl.col("g")).alias("total"))


def metricas_descomposicion(d: pl.DataFrame, tp: pl.DataFrame) -> list[pl.DataFrame]:
    """Por equipo-partido, en goles por cada 100 saques: xd_<término>_<familia> del que defiende y
    xo_<término>_<familia> (= −xd) del que saca."""
    rival = tp.select("match_id", "team", "rival")
    dd = d.join(rival, on=["match_id", "team"]).drop("team").rename({"rival": "team"})
    out = []
    for fam, ts in {**FAMILIAS, "todas": None}.items():
        for lado, df, sg in (("xd", dd, 100.0), ("xo", d, -100.0)):
            x = df if ts is None else df.filter(pl.col("tipo").is_in(list(ts)))
            out.append(x.group_by("match_id", "team").agg(
                *[(sg * pl.col(c).sum()).alias(f"{lado}_{c}_{fam}__n") for c in COMPONENTES],
                *[pl.len().cast(pl.Float64).alias(f"{lado}_{c}_{fam}__d") for c in COMPONENTES]))
    return out


def metricas_tl(p2: pl.DataFrame, j: pl.DataFrame, tp: pl.DataFrame) -> list[pl.DataFrame]:
    """Tiros libres directos EN CONTRA (del que pone la barrera): cuánto arco deja y cuántos la forman."""
    if "barrera" not in p2.columns:
        return []
    ids = j.filter(pl.col("tipo") == "tl_directo").select("match_id", pl.col("id_saque").alias("id"))
    t = (p2.join(ids, on=["match_id", "id"]).filter(pl.col("goal_open").is_not_nan())
         .join(tp.select("match_id", "team", "rival"), on=["match_id", "team"]).drop("team")
         .rename({"rival": "team"}))
    return [t.group_by("match_id", "team").agg(pl.col("goal_open").sum().alias("arco_libre_tl__n"),
                                               pl.len().cast(pl.Float64).alias("arco_libre_tl__d"),
                                               pl.col("barrera").sum().cast(pl.Float64).alias("barrera_tl__n"),
                                               pl.len().cast(pl.Float64).alias("barrera_tl__d"))]


def cadena(d: pl.DataFrame, tp: pl.DataFrame, foco: str, n_boot: int = 500, seed: int = 0) -> dict:
    """La cadena C → S → G de cada familia (y de cada tipo) para el foco atacando, el foco defendiendo y
    la liga: probabilidades observadas y esperadas, y los cuatro términos por 100 saques con IC 95 %
    (bootstrap de partidos). Signo: xD (goles evitados) al defender; xO (goles de más) al atacar."""
    from .balon_parado import grupos
    rng = np.random.default_rng(seed)
    G = grupos(d, tp, foco)
    out = {}
    claves = [(f, pl.col("familia") == f) for f in FAMILIAS] + [("todas", pl.lit(True))] + \
        [(t, pl.col("tipo") == t) for ts in FAMILIAS.values() for t in ts]
    for clave, filtro in claves:
        out[clave] = {}
        for g, x0 in G.items():
            x = x0.filter(filtro)
            if x.height == 0:
                continue
            sg = -1.0 if g == "foco_ataque" else 1.0          # el foco al atacar: xO = −xD
            a = x.group_by("match_id").agg(pl.len().alias("n"), *[pl.col(c).sum() for c in
                                                                   ("s", "p", "g", "B", "F", *COMPONENTES)],
                                            (pl.col("s") * pl.col("kappa")).sum().alias("sk"),
                                            (pl.col("p") * pl.col("kappa")).sum().alias("pk"))
            A = {c: a[c].to_numpy().astype(float) for c in a.columns if c != "match_id"}
            n, S = A["n"].sum(), max(A["s"].sum(), 1e-12)
            r = {"saques": int(n), "p_obs": A["s"].sum() / n, "p_esp": A["p"].sum() / n,
                 "v_obs": A["g"].sum() / S, "v_kappa": A["sk"].sum() / S, "v_base": A["B"].sum() / S,
                 "v_full": A["F"].sum() / S, "g_obs": A["g"].sum() / n, "g_esp": A["pk"].sum() / n}
            idx = [rng.integers(0, len(A["n"]), len(A["n"])) for _ in range(n_boot)]
            for c in COMPONENTES:
                v = sg * 100 * A[c].sum() / n
                b = [sg * 100 * A[c][i].sum() / A["n"][i].sum() for i in idx]
                r[c] = {"valor": float(v), "lo": float(np.quantile(b, 0.025)), "hi": float(np.quantile(b, 0.975))}
            out[clave][g] = {k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in r.items()}
    return out


# ----------------------------------------------------------------------
# Contracción empírico-bayesiana (normal-normal)
# ----------------------------------------------------------------------
def razon_y_varianza(n: np.ndarray, d: np.ndarray) -> tuple[float, float]:
    """θ = Σn/Σd y su varianza por conglomerados (partidos), método delta."""
    n, d = np.asarray(n, float), np.asarray(d, float)
    D = d.sum()
    if D <= 0:
        return float("nan"), float("nan")
    th = n.sum() / D
    G = len(n)
    v = ((n - th * d) ** 2).sum() / D ** 2 * G / max(G - 1, 1)
    return float(th), float(v)


def contraccion(theta: np.ndarray, var: np.ndarray) -> dict:
    """θ_j ~ N(μ, τ²), x_j | θ_j ~ N(θ_j, v_j). τ² por DerSimonian-Laird.
    Devuelve μ, τ², θ contraído y la confiabilidad τ²/(τ² + v_j)."""
    x, v = np.asarray(theta, float), np.asarray(var, float)
    ok = np.isfinite(x) & np.isfinite(v) & (v > 0)
    x, v = x[ok], v[ok]
    w = 1 / v
    mu_w = (w * x).sum() / w.sum()
    Qs = (w * (x - mu_w) ** 2).sum()
    c = w.sum() - (w ** 2).sum() / w.sum()
    tau2 = max(0.0, (Qs - (len(x) - 1)) / c) if c > 0 else 0.0
    ws = 1 / (v + tau2)
    mu = (ws * x).sum() / ws.sum()
    rel = tau2 / (tau2 + v) if tau2 > 0 else np.zeros_like(v)
    out = np.full(len(theta), np.nan)
    out[ok] = mu + rel * (x - mu)
    confi = np.full(len(theta), np.nan)
    confi[ok] = rel
    return {"mu": float(mu), "tau2": float(tau2), "contraido": out, "confiabilidad": confi, "etapas": int(ok.sum())}


def por_etapa(M: pl.DataFrame, m: str, lado: str = "propio", min_partidos: int = 30,
              varianza: str = "propia") -> pl.DataFrame:
    """Una fila por técnico-club: θ (razón de sumas), su varianza por partidos y el θ contraído.

    `varianza`: "propia" = método delta con los residuos de cada etapa; "comun" = la misma varianza por
    saque para todas las etapas (la de la liga), v_j = σ² Σ d_m² / (Σ d_m)². Con métricas de goles la
    propia está acoplada a la media (quien no recibe goles tiene poca varianza Y un θ alto), así que pesa
    de más a esas etapas y sesga μ; la común corta ese acoplamiento (04 §16.4).

    Ordenada de mayor a menor θ contraído: en xd_prev y xd_remate más alto = mejor defensa, así que la
    fila 1 es la mejor."""
    coach, team = ("coach", "team") if lado == "propio" else ("coach_rival", "rival")
    filas = []
    for (c, t), g in M.filter(pl.col(coach).is_not_null()).group_by(coach, team):
        if g["match_id"].n_unique() < min_partidos:
            continue
        n, d = g[f"{m}__n"].to_numpy(), g[f"{m}__d"].to_numpy()
        th, v = razon_y_varianza(n, d)
        filas.append({"coach": c, "team": t, "partidos": g["match_id"].n_unique(), "theta": th, "var": v,
                      "_r2": float(((n - th * d) ** 2).sum()), "_d2": float((d ** 2).sum()), "_D": float(d.sum())})
    if not filas:
        return pl.DataFrame()
    E = pl.DataFrame(filas)
    if varianza == "comun":
        s2 = E["_r2"].sum() / max(E["_d2"].sum(), 1e-12)
        E = E.with_columns((s2 * pl.col("_d2") / pl.col("_D") ** 2).alias("var"))
    E = E.drop("_r2", "_d2", "_D")
    cc = contraccion(E["theta"].to_numpy(), E["var"].to_numpy())
    return E.with_columns(pl.Series("contraido", cc["contraido"]), pl.Series("confiabilidad", cc["confiabilidad"]),
                          pl.lit(cc["mu"]).alias("mu"), pl.lit(cc["tau2"]).alias("tau2")).sort("contraido", descending=True)
