"""
Fase B -- Estilo de juego (reto 5.1 y 5.5): las métricas que un analista espera,
definidas sobre los objetos del framework (03_FRAMEWORK §5) y comparadas con la
liga por `comparar.py`.

Cada constructor devuelve una fila por equipo-partido con `m__n` y `m__d`
(razón de sumas). Umbrales en `config.futbol`; ninguno está escrito aquí.

OFENSIVA
  pases_prog, conducciones_prog   progresivas: terminan ≥ `prog_min_m` más cerca del
                                  centro del arco y a ≤ `prog_frac` de la distancia
                                  inicial; pases completos y de juego (sin balón parado)
  entradas_tercio, entradas_area  pase completo o conducción que ENTRA (empieza fuera)
  remates, xg, xg_por_remate, goles
  obv                             suma del OBV de StatsBomb de los eventos del equipo
  field_tilt                      pases del equipo en su último tercio / los de ambos
  posesion                        pases del equipo / pases de ambos
  saque_corto                     saques de meta de menos de `saque_corto_m`
  salida_limpia                   posesiones que nacen en su tercio (x0 < 40) y llegan a x ≥ 60
DEFENSIVA
  ppda                            pases del rival en su 60 % / acciones defensivas propias
                                  (Duel, Interception, Foul Committed) en x ≥ 48 del marco propio
  altura_recuperacion             x media de Ball Recovery e Interception (marco propio)
  recuperaciones_altas            recuperaciones con x ≥ 80 por partido
  presion_alta, contrapresion     fracción de presiones en x ≥ 72; fracción marcada counterpress
TRANSICIONES
  recupera_5s                     tras perder en juego abierto, recupera en ≤ `ventana_perdida` s
  xg_tras_recuperar               xG en los `ventana_recuperar` s siguientes a una recuperación
  remate_tras_recuperar           fracción de recuperaciones con remate en esa ventana
"""
from __future__ import annotations

import numpy as np
import polars as pl

from .eventos import BALON_PARADO, ULTIMO_TERCIO, en_area

DEFENSIVAS = ("Duel", "Interception", "Foul Committed")
RECUPERACIONES = ("Ball Recovery", "Interception")

DEFINICIONES = {
    "pases_prog": {"nombre": "pases progresivos por partido", "formato": "{:.1f}"},
    "conducciones_prog": {"nombre": "conducciones progresivas por partido", "formato": "{:.1f}"},
    "entradas_tercio": {"nombre": "entradas al último tercio por partido", "formato": "{:.1f}"},
    "entradas_area": {"nombre": "entradas al área por partido", "formato": "{:.1f}"},
    "remates": {"nombre": "remates por partido", "formato": "{:.1f}"},
    "xg": {"nombre": "xG por partido", "formato": "{:.2f}"},
    "xg_por_remate": {"nombre": "xG por remate", "formato": "{:.3f}"},
    "goles": {"nombre": "goles por partido", "formato": "{:.2f}"},
    "obv": {"nombre": "OBV por partido", "formato": "{:.2f}"},
    "field_tilt": {"nombre": "field tilt", "formato": "{:.3f}"},
    "posesion": {"nombre": "posesión (fracción de pases)", "formato": "{:.3f}"},
    "saque_corto": {"nombre": "saques de meta en corto", "formato": "{:.3f}"},
    "salida_limpia": {"nombre": "salidas desde su tercio que pasan de x = 60", "formato": "{:.3f}"},
    "ppda": {"nombre": "PPDA (menos = presiona más)", "formato": "{:.2f}"},
    "altura_recuperacion": {"nombre": "altura media de recuperación (m)", "formato": "{:.1f}"},
    "recuperaciones_altas": {"nombre": "recuperaciones en el último tercio por partido", "formato": "{:.2f}"},
    "presion_alta": {"nombre": "fracción de presiones en campo rival (x ≥ 72)", "formato": "{:.3f}"},
    "contrapresion": {"nombre": "fracción de presiones de contrapresión", "formato": "{:.3f}"},
    "recupera_5s": {"nombre": "pérdidas recuperadas en ≤ 5 s", "formato": "{:.3f}"},
    "xg_tras_recuperar": {"nombre": "xG en 10 s tras recuperar", "formato": "{:.4f}"},
    "remate_tras_recuperar": {"nombre": "recuperaciones con remate en 10 s", "formato": "{:.3f}"},
    "presion_aplicada": {"nombre": "acciones del rival con un jugador propio a ≤ 2 m (360)", "formato": "{:.3f}"},
    "presion_sufrida": {"nombre": "acciones propias con un rival a ≤ 2 m (360)", "formato": "{:.3f}"},
    "espacio_propio": {"nombre": "área de Voronoi local de sus acciones (m², 360)", "formato": "{:.0f}"},
    "altura_bloque": {"nombre": "altura media del bloque sin balón (m, 360)", "formato": "{:.1f}"},
    "area_bloque": {"nombre": "área de la envolvente del bloque (m², 360)", "formato": "{:.0f}"},
    "anchura_bloque": {"nombre": "anchura del bloque (m, 360)", "formato": "{:.1f}"},
}

OFENSIVAS = ["pases_prog", "conducciones_prog", "entradas_tercio", "entradas_area", "remates", "xg",
             "xg_por_remate", "goles", "obv", "field_tilt", "posesion", "saque_corto", "salida_limpia"]
DEFENSIVAS_M = ["ppda", "altura_recuperacion", "recuperaciones_altas", "presion_alta", "contrapresion"]
TRANSICIONES = ["recupera_5s", "xg_tras_recuperar", "remate_tras_recuperar"]
M360 = ["presion_aplicada", "presion_sufrida", "espacio_propio", "altura_bloque", "area_bloque", "anchura_bloque"]


def _por_partido(df: pl.DataFrame, nombre: str, n: pl.Expr, d: pl.Expr | None = None) -> pl.DataFrame:
    d = pl.lit(1.0) if d is None else d
    return df.group_by("match_id", "team").agg(n.cast(pl.Float64).alias(f"{nombre}__n"),
                                               d.cast(pl.Float64).alias(f"{nombre}__d"))


def _progresivo(x, y, fx, fy, cfg) -> pl.Expr:
    d0 = ((120 - x) ** 2 + (40 - y) ** 2).sqrt()
    d1 = ((120 - fx) ** 2 + (40 - fy) ** 2).sqrt()
    return ((d0 - d1) >= cfg["prog_min_m"]) & (d1 <= cfg["prog_frac"] * d0)


def ofensiva(ev: pl.DataFrame, pos: pl.DataFrame, cfg: dict) -> list[pl.DataFrame]:
    x, y, fx, fy = pl.col("x"), pl.col("y"), pl.col("fin_x"), pl.col("fin_y")
    pase = pl.col("type") == "Pass"
    completo = pase & pl.col("pass_outcome").is_null()
    de_juego = ~pl.col("pass_type").is_in(list(BALON_PARADO)).fill_null(False)
    cond = pl.col("type") == "Carry"
    avanza = (completo & de_juego) | cond
    remate = pl.col("type") == "Shot"
    out = [
        _por_partido(ev, "pases_prog", (completo & de_juego & _progresivo(x, y, fx, fy, cfg)).sum()),
        _por_partido(ev, "conducciones_prog", (cond & _progresivo(x, y, fx, fy, cfg)).sum()),
        _por_partido(ev, "entradas_tercio", (avanza & (x < ULTIMO_TERCIO) & (fx >= ULTIMO_TERCIO)).sum()),
        _por_partido(ev, "entradas_area", (avanza & ~en_area(x, y) & en_area(fx, fy)).sum()),
        _por_partido(ev, "remates", remate.sum()),
        _por_partido(ev, "xg", pl.col("shot_statsbomb_xg").fill_null(0.0).sum()),
        _por_partido(ev, "xg_por_remate", pl.col("shot_statsbomb_xg").fill_null(0.0).sum(), remate.sum()),
        _por_partido(ev, "goles", (remate & (pl.col("shot_outcome") == "Goal")).sum()),
        _por_partido(ev, "obv", pl.col("obv_total_net").fill_null(0.0).sum()),
    ]
    # field tilt y posesión: necesitan los pases de AMBOS equipos del partido
    p = ev.group_by("match_id", "team").agg(pase.sum().alias("pases"),
                                            (pase & (x >= ULTIMO_TERCIO)).sum().alias("pases_tercio"))
    tot = p.group_by("match_id").agg(pl.col("pases").sum().alias("tp"), pl.col("pases_tercio").sum().alias("tt"))
    p = p.join(tot, on="match_id")
    out.append(p.select("match_id", "team", pl.col("pases_tercio").cast(pl.Float64).alias("field_tilt__n"),
                        pl.col("tt").cast(pl.Float64).alias("field_tilt__d")))
    out.append(p.select("match_id", "team", pl.col("pases").cast(pl.Float64).alias("posesion__n"),
                        pl.col("tp").cast(pl.Float64).alias("posesion__d")))
    gk = ev.filter(pase & (pl.col("pass_type") == "Goal Kick"))
    largo = ((fx - x) ** 2 + (fy - y) ** 2).sqrt()
    out.append(_por_partido(gk, "saque_corto", (largo < cfg["saque_corto_m"]).sum(), pl.len()))
    sal = pos.filter(pl.col("x0") < 40)
    out.append(_por_partido(sal, "salida_limpia", (pl.col("x_max") >= 60).sum(), pl.len()))
    return out


def defensiva(ev: pl.DataFrame, tp: pl.DataFrame) -> list[pl.DataFrame]:
    x = pl.col("x")
    t = pl.col("type")
    rival = tp.select("match_id", "team", "rival")
    # PPDA: numerador = pases del RIVAL en su propio 60 % (x ≤ 72 en su marco)
    pases_rival = (ev.filter((t == "Pass") & (x <= 72)).group_by("match_id", "team").len()
                   .rename({"team": "rival", "len": "ppda__n"}))
    acc = ev.filter(t.is_in(list(DEFENSIVAS)) & (x >= 48)).group_by("match_id", "team").len().rename({"len": "ppda__d"})
    ppda = (rival.join(pases_rival, on=["match_id", "rival"], how="left")
            .join(acc, on=["match_id", "team"], how="left")
            .select("match_id", "team", pl.col("ppda__n").fill_null(0).cast(pl.Float64),
                    pl.col("ppda__d").fill_null(0).cast(pl.Float64)))
    rec = ev.filter(t.is_in(list(RECUPERACIONES)))
    pres = ev.filter(t == "Pressure")
    return [
        ppda,
        _por_partido(rec, "altura_recuperacion", x.sum(), pl.len()),
        _por_partido(rec, "recuperaciones_altas", (x >= ULTIMO_TERCIO).sum()),
        _por_partido(pres, "presion_alta", (x >= 72).sum(), pl.len()),
        _por_partido(pres, "contrapresion", pl.col("counterpress").sum(), pl.len()),
    ]


# ----------------------------------------------------------------------
# Transiciones: la secuencia de posesiones de un partido
# ----------------------------------------------------------------------
def cadenas_de_posesion(pos: pl.DataFrame) -> pl.DataFrame:
    """Para cada posesión A seguida de una del rival B en juego abierto (una PÉRDIDA de A):
    t_recupera = inicio de la siguiente posesión de A en juego abierto − inicio de B, o
    censurada al inicio de la posesión que corta la secuencia (balón parado, remate del
    rival, fin del tiempo)."""
    p = pos.sort("match_id", "possession").with_columns(
        pl.col("team").shift(-1).over("match_id", "period").alias("team_b"),
        pl.col("patron").shift(-1).over("match_id", "period").alias("patron_b"),
        pl.col("inicio").shift(-1).over("match_id", "period").alias("inicio_b"),
        pl.col("remates").shift(-1).over("match_id", "period").alias("remates_b"),
        pl.col("team").shift(-2).over("match_id", "period").alias("team_c"),
        pl.col("patron").shift(-2).over("match_id", "period").alias("patron_c"),
        pl.col("inicio").shift(-2).over("match_id", "period").alias("inicio_c"),
        pl.col("fin").shift(-1).over("match_id", "period").alias("fin_b"))
    perdida = p.filter((pl.col("team_b") != pl.col("team")) & (pl.col("patron_b") == "Regular Play")
                       & (pl.col("remates") == 0))
    recupera = ((pl.col("team_c") == pl.col("team")) & (pl.col("patron_c") == "Regular Play")
                & (pl.col("remates_b") == 0))
    return perdida.with_columns(
        recupera.fill_null(False).alias("evento"),
        pl.when(recupera.fill_null(False)).then(pl.col("inicio_c") - pl.col("inicio_b"))
        .otherwise(pl.coalesce(pl.col("inicio_c"), pl.col("fin_b")) - pl.col("inicio_b"))
        .clip(0, None).alias("t"))


def transiciones(pos: pl.DataFrame, cfg: dict) -> list[pl.DataFrame]:
    c = cadenas_de_posesion(pos)
    w = cfg["ventana_perdida"]
    out = [_por_partido(c, "recupera_5s", (pl.col("evento") & (pl.col("t") <= w)).sum(), pl.len())]
    # recuperaciones: posesión propia en juego abierto que sigue a una del rival
    p = pos.sort("match_id", "possession").with_columns(
        pl.col("team").shift(1).over("match_id", "period").alias("team_prev"))
    rec = p.filter((pl.col("patron") == "Regular Play") & (pl.col("team_prev") != pl.col("team")))
    v = cfg["ventana_recuperar"]
    filas = rec.select("inicio", "xg_remates", "reloj_remates").iter_rows()
    xg10, rem10 = [], []
    for ini, xgs, ts in filas:
        dentro = [xg for xg, tt in zip(xgs or [], ts or []) if tt - ini <= v]
        xg10.append(float(sum(dentro)))
        rem10.append(bool(dentro))
    rec = rec.select("match_id", "team").with_columns(pl.Series("xg10", xg10, dtype=pl.Float64),
                                                      pl.Series("rem10", rem10, dtype=pl.Boolean))
    out.append(_por_partido(rec, "xg_tras_recuperar", pl.col("xg10").sum(), pl.len()))
    out.append(_por_partido(rec, "remate_tras_recuperar", pl.col("rem10").sum(), pl.len()))
    return out


def kaplan_meier(t: np.ndarray, evento: np.ndarray, rejilla: np.ndarray) -> np.ndarray:
    """S(u) = P(aún sin recuperar a los u segundos), con censura por la derecha."""
    orden = np.argsort(t, kind="stable")
    t, e = np.asarray(t, float)[orden], np.asarray(evento, bool)[orden]
    tiempos = np.unique(t[e])
    S = []
    en_riesgo = len(t) - np.searchsorted(t, tiempos, side="left")
    muertes = np.array([np.sum((t == u) & e) for u in tiempos])
    surv = np.cumprod(1 - muertes / np.maximum(en_riesgo, 1))
    for u in rejilla:
        k = np.searchsorted(tiempos, u, side="right") - 1
        S.append(surv[k] if k >= 0 else 1.0)
    return np.array(S)


def curva_recuperacion(pos: pl.DataFrame, tp: pl.DataFrame, foco: str, n_boot: int = 300,
                       seed: int = 0, tmax: int = 30) -> dict:
    """Supervivencia de la pérdida (foco contra liga), con banda por bootstrap de partidos."""
    c = cadenas_de_posesion(pos).join(tp.select("match_id", "team", "coach", "coach_rival"),
                                      on=["match_id", "team"], how="left")
    pf = c.filter(pl.col("coach") == foco)
    partidos_foco = c.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique()
    pl_ = c.filter(~pl.col("match_id").is_in(partidos_foco.to_list()))
    rej = np.arange(0, tmax + 1)
    rng = np.random.default_rng(seed)

    def km(df):
        return kaplan_meier(df["t"].to_numpy(), df["evento"].to_numpy(), rej)

    def boot(df):
        # por partido: arreglos de (t, evento); cada réplica concatena arreglos, no tablas
        d = df.sort("match_id")
        mid = d["match_id"].to_numpy()
        t_, e_ = d["t"].to_numpy(), d["evento"].to_numpy()
        cortes = np.flatnonzero(np.r_[True, mid[1:] != mid[:-1], True])
        trozos = [(t_[a:b], e_[a:b]) for a, b in zip(cortes[:-1], cortes[1:])]
        cur = []
        for _ in range(n_boot):
            sel = rng.integers(0, len(trozos), len(trozos))
            cur.append(kaplan_meier(np.concatenate([trozos[i][0] for i in sel]),
                                    np.concatenate([trozos[i][1] for i in sel]), rej))
        return np.quantile(np.array(cur), [0.025, 0.975], axis=0)
    out = {"t": rej.tolist(), "foco": km(pf).tolist(), "liga": km(pl_).tolist(),
           "n_foco": pf.height, "n_liga": pl_.height}
    if n_boot:
        bf, bl = boot(pf), boot(pl_)
        out |= {"foco_lo": bf[0].tolist(), "foco_hi": bf[1].tolist(), "liga_lo": bl[0].tolist(),
                "liga_hi": bl[1].tolist()}
    return out


# ----------------------------------------------------------------------
# 360: presión (Voronoi local, ADR-v2-36) y bloque (envolvente convexa)
# ----------------------------------------------------------------------
def del_360(ev: pl.DataFrame, rasgos: pl.DataFrame | None, bloque: pl.DataFrame | None,
            tp: pl.DataFrame, cfg: dict) -> list[pl.DataFrame]:
    """Presión aplicada / sufrida y espacio propio desde `rasgos_360`; bloque desde `bloque_360`.
    Solo acciones de la cadena (Pass, Carry, Shot) con frame; NO hay filtro de cobertura por
    partido (a diferencia de la cadena aumentada): cada acción con frame cuenta."""
    out = []
    acc = ev.filter(pl.col("type").is_in(["Pass", "Carry", "Shot"])).select(
        "match_id", pl.col("index").alias("event_index"), "team", "x")
    rival = tp.select("match_id", "team", "rival")
    d2 = cfg["presion_m"]
    if rasgos is not None and rasgos.height:
        r = acc.join(rasgos.select("match_id", "event_index", "d_rival", "area_local"),
                     on=["match_id", "event_index"], how="inner").filter(pl.col("d_rival").is_not_nan())
        sufre = _por_partido(r, "presion_sufrida", (pl.col("d_rival") <= d2).sum(), pl.len())
        aplica = (sufre.rename({"team": "rival", "presion_sufrida__n": "presion_aplicada__n",
                                "presion_sufrida__d": "presion_aplicada__d"})
                  .join(rival, on=["match_id", "rival"]).select("match_id", "team", "presion_aplicada__n",
                                                               "presion_aplicada__d"))
        esp = _por_partido(r.filter(pl.col("area_local").is_not_nan()), "espacio_propio",
                           pl.col("area_local").sum(), pl.len())
        out += [sufre, aplica, esp]
    if bloque is not None and bloque.height:
        # el bloque es del equipo SIN balón: el que defiende la acción del rival
        b = (acc.join(bloque, on=["match_id", "event_index"], how="inner")
             .join(rival, on=["match_id", "team"]).drop("team").rename({"rival": "team"}))
        out += [_por_partido(b, "altura_bloque", pl.col("altura").sum(), pl.len()),
                _por_partido(b, "area_bloque", pl.col("area").sum(), pl.len()),
                _por_partido(b, "anchura_bloque", pl.col("anchura").sum(), pl.len())]
    return out


def mapa_presion(ev: pl.DataFrame, rasgos: pl.DataFrame, tp: pl.DataFrame, foco: str, nx: int, ny: int,
                 d2: float) -> dict:
    """Por zona del campo del DEFENSOR: fracción de acciones del rival con un defensor a ≤ d2 m."""
    acc = (ev.filter(pl.col("type").is_in(["Pass", "Carry", "Shot"]))
           .select("match_id", pl.col("index").alias("event_index"), "team", "x", "y")
           .join(rasgos.select("match_id", "event_index", "d_rival"), on=["match_id", "event_index"])
           .filter(pl.col("d_rival").is_not_nan())
           .join(tp.select("match_id", "team", "coach_rival"), on=["match_id", "team"], how="left"))
    xd = 120 - acc["x"].to_numpy()
    yd = 80 - acc["y"].to_numpy()          # marco del defensor (ADR de grid.mirror_zone)
    ix = np.clip((xd / 120 * nx).astype(int), 0, nx - 1)
    iy = np.clip((yd / 80 * ny).astype(int), 0, ny - 1)
    z = ix * ny + iy
    cerca = (acc["d_rival"].to_numpy() <= d2).astype(float)
    es = (acc["coach_rival"] == foco).fill_null(False).to_numpy()
    out = {}
    for nombre, m in (("foco", es), ("liga", ~es)):
        n = np.bincount(z[m], minlength=nx * ny)
        k = np.bincount(z[m], weights=cerca[m], minlength=nx * ny)
        out[nombre] = (k / np.maximum(n, 1)).tolist()
        out[f"n_{nombre}"] = n.tolist()
    return out


# ----------------------------------------------------------------------
# Construcción y progresión con la cadena (primer paso, ADR-v2-31)
# ----------------------------------------------------------------------
def conteos_por_partido(trans: pl.DataFrame, nt: int, ns: int) -> tuple[pl.DataFrame, np.ndarray, np.ndarray]:
    """Por equipo-partido: conteos de transiciones (nt·ns), inicios de secuencia (nt) y xG por
    estado de origen (nt). Suficiente para rehacer la cadena de cualquier grupo de partidos."""
    t = trans.sort("seq_uid", "event_index")
    t = t.with_columns((pl.col("seq_uid") != pl.col("seq_uid").shift(1)).fill_null(True).alias("_ini"))
    claves = t.select("match_id", "team").unique().sort("match_id", "team").with_row_index("_g")
    t = t.join(claves, on=["match_id", "team"])
    g = t["_g"].to_numpy().astype(np.int64)
    G = claves.height
    i, j = t["from_state"].to_numpy(), t["to_state"].to_numpy()
    C = np.bincount(g * nt * ns + i * ns + j, minlength=G * nt * ns).reshape(G, nt * ns).astype(float)
    ini = t["_ini"].to_numpy()
    S0 = np.bincount(g[ini] * nt + i[ini], minlength=G * nt).reshape(G, nt).astype(float)
    xg = t["xg"].fill_null(0.0).to_numpy() if "xg" in t.columns else np.zeros(len(g))
    X = np.bincount(g * nt + i, weights=xg, minlength=G * nt).reshape(G, nt)
    return claves.drop("_g"), np.concatenate([C, S0, X], axis=1), np.array([nt, ns])


def llegada_grupo(A: np.ndarray, dims: np.ndarray, objetivos: dict, lam: float, Q_liga: np.ndarray) -> dict:
    """Cadena del grupo (suma de sus equipo-partido, encogida hacia la liga) y su llegada."""
    from .estimate import shrink
    from .markov import llegada
    nt, ns = int(dims[0]), int(dims[1])
    s = A.sum(0)
    C = s[:nt * ns].reshape(nt, ns)
    S0 = s[nt * ns: nt * ns + nt]
    xg = s[nt * ns + nt:]
    P = shrink(C, Q_liga, lam)
    mu = (S0 + 1e-9) / (S0.sum() + 1e-9 * nt)
    out = {}
    for n, obj in objetivos.items():
        r = llegada(P, mu, obj)
        out[n] = {"P": r["P_llega"], "E_acciones": r["E_acciones_si_llega"]}
    N = np.linalg.inv(np.eye(nt) - P[:, :nt])
    c = xg / np.maximum(C.sum(1), 1e-12)
    out["V"] = (N @ c).tolist()
    return out


def comparar_llegada(claves: pl.DataFrame, A: np.ndarray, dims: np.ndarray, tp: pl.DataFrame, foco: str,
                     objetivos: dict, lam: float, n_boot: int, seed: int, lado: str = "propio") -> dict:
    """P(llegar) y E[acciones | llega] del foco contra la liga, con bootstrap de partidos."""
    from .estimate import shrink
    k = claves.join(tp.select("match_id", "team", "coach", "coach_rival"), on=["match_id", "team"], how="left")
    col = "coach" if lado == "propio" else "coach_rival"
    es_f = (k[col] == foco).fill_null(False).to_numpy()
    partidos_foco = k.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique()
    es_l = ~k["match_id"].is_in(partidos_foco.to_list()).to_numpy()
    nt, ns = int(dims[0]), int(dims[1])
    tot = A[es_l].sum(0)[:nt * ns].reshape(nt, ns)
    Q_liga = shrink(tot, np.full((nt, ns), 1.0 / ns), 1.0)

    def resumen(r):
        return {n: [r[n]["P"], r[n]["E_acciones"]] for n in objetivos}
    rf = llegada_grupo(A[es_f], dims, objetivos, lam, Q_liga)
    rl = llegada_grupo(A[es_l], dims, objetivos, lam, Q_liga)
    # bootstrap por partido (las filas de un mismo partido van juntas)
    rng = np.random.default_rng(seed)
    mf, ml = k["match_id"].to_numpy()[es_f], k["match_id"].to_numpy()[es_l]
    Af, Al = A[es_f], A[es_l]
    uf, ul = np.unique(mf), np.unique(ml)
    idx_f = {m: np.flatnonzero(mf == m) for m in uf}
    idx_l = {m: np.flatnonzero(ml == m) for m in ul}
    D = []
    for _ in range(n_boot):
        sf = np.concatenate([idx_f[m] for m in rng.choice(uf, len(uf))])
        sl = np.concatenate([idx_l[m] for m in rng.choice(ul, len(ul))])
        a, b = resumen(llegada_grupo(Af[sf], dims, objetivos, lam, Q_liga)), \
            resumen(llegada_grupo(Al[sl], dims, objetivos, lam, Q_liga))
        D.append([[a[n][0] - b[n][0], a[n][1] - b[n][1]] for n in objetivos])
    D = np.array(D)
    out = {"V_foco": rf["V"], "V_liga": rl["V"]}
    for c, n in enumerate(objetivos):
        out[n] = {}
        for e, qué in enumerate(("P", "E_acciones")):
            d = D[:, c, e]
            out[n][qué] = {"foco": rf[n][qué], "liga": rl[n][qué], "dif": rf[n][qué] - rl[n][qué],
                           "lo": float(np.quantile(d, 0.025)), "hi": float(np.quantile(d, 0.975)),
                           "p": float(max(1.0 / n_boot, min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean()))))}
    return out


def unir(tablas: list[pl.DataFrame], tp: pl.DataFrame) -> pl.DataFrame:
    """Todas las métricas en una tabla equipo-partido, con técnico, rival y fecha."""
    base = tp.select("match_id", "team")
    for t in tablas:
        base = base.join(t, on=["match_id", "team"], how="left")
    num = [c for c in base.columns if c.endswith(("__n", "__d"))]
    return base.with_columns([pl.col(c).fill_null(0.0) for c in num]).join(tp, on=["match_id", "team"], how="left")


def metricas_de(M: pl.DataFrame) -> list[str]:
    return [c[:-3] for c in M.columns if c.endswith("__n")]
