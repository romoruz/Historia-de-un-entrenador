"""
Fase 1 (experimento, ADR-v2-36) -- Estado topológico con 360: zona × nivel de presión.

LA PREGUNTA
-----------
¿Mejora la cadena si el estado, además de DÓNDE está el balón (malla 5×4), dice
CUÁNTO espacio tiene quien lo juega? Si mejora, ¿permite más de 3 tipos
reproducibles? El experimento NO toca el vocabulario oficial: escribe en rutas
propias (`config/presion.yaml`) y se puede borrar sin dejar rastro.

LOS RASGOS (uno por evento con freeze frame 360)
------------------------------------------------
Con la posición del ejecutante p_c y la de los demás jugadores visibles:

  d_rival     distancia al rival más cercano (m).
  n_rivales   rivales a menos de `r_presion` metros.
  area_local  área de la celda de Voronoi del ejecutante, recortada al disco de
              radio R, a la cancha y al área visible de la cámara:
                  μ( V_c ∩ B(p_c, R) ∩ Ω )
              Se integra por cuadratura: puntos de área igual dentro del disco;
              cada punto es de p_c si ningún otro jugador está más cerca. Los
              puntos fuera del área visible NO cuentan (ahí puede haber jugadores
              que la cámara no ve), y el área se reescala con la fracción visible.

POR QUÉ NO LA CELDA COMPLETA NI DBSCAN
--------------------------------------
- El 360 solo trae a los jugadores VISIBLES. La celda completa del ejecutante se
  extiende hacia donde la cámara no ve y su área sería un artefacto del encuadre;
  el recorte al disco (espacio que puede usar en ~1 s) la hace comparable.
- El estado debe CONSERVAR la zona: el valor de zona, la llegada al área y el xG
  dependen del lugar. Por eso el estado es el PRODUCTO zona × nivel, y el nivel
  ocupa el eje de "fase" que el código ya soporta (`StateSpace.phases`).
- DBSCAN deja puntos "ruido" sin estado (la cadena no puede tener acciones sin
  estado) y depende de un ε arbitrario; GMM con BIC sobre millones de puntos
  elige muchas componentes por tamaño de muestra, no por dinámica. Aquí el número
  de niveles se elige por lo que importa: predecir la SIGUIENTE ACCIÓN en
  partidos no vistos, en la misma escala que la calibración de la malla
  (ADR-v2-32), con la regla de 1 error estándar hacia menos estados.
"""
from __future__ import annotations

import gzip
import json
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl

from .estimate import match_folds, shrink

_EPS = 1e-300
RASGOS = ("d_rival", "n_rivales", "area_local")

try:  # opcional, igual que en aplanar
    import orjson

    def _loads(b: bytes):
        return orjson.loads(b)
except ImportError:  # pragma: no cover
    def _loads(b: bytes):
        return json.loads(b)


# ======================================================================
# Geometría
# ======================================================================
def puntos_disco(R: float, anillos: int = 8, por_anillo: int = 16) -> np.ndarray:
    """(P, 2) desplazamientos de área igual dentro del disco de radio R."""
    r = R * np.sqrt((np.arange(anillos) + 0.5) / anillos)
    out = []
    for a, ra in enumerate(r):
        th = 2 * np.pi * (np.arange(por_anillo) + 0.5 * (a % 2)) / por_anillo
        out.append(np.column_stack([ra * np.cos(th), ra * np.sin(th)]))
    return np.vstack(out)


def dentro_poligono(px: np.ndarray, py: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Prueba de rayo, vectorizada. px, py: (F, P); poly: (F, V, 2) (se puede rellenar
    repitiendo el último vértice: una arista degenerada nunca cruza el rayo)."""
    xi, yi = poly[:, :, 0][:, None, :], poly[:, :, 1][:, None, :]
    xj, yj = np.roll(xi, 1, axis=2), np.roll(yi, 1, axis=2)
    X, Y = px[:, :, None], py[:, :, None]
    cruza = (yi > Y) != (yj > Y)
    den = np.where(yj == yi, 1.0, yj - yi)
    xc = (xj - xi) * (Y - yi) / den + xi
    return ((cruza & (X < xc)).sum(axis=2) % 2) == 1


def _frames_de(obj) -> list[dict]:
    if isinstance(obj, dict):
        for k in ("frames", "data", "360"):
            if isinstance(obj.get(k), list):
                return obj[k]
        return []
    return obj if isinstance(obj, list) else []


def rasgos_frames(frames: list[dict], R: float = 10.0, r_presion: float = 5.0,
                  min_visible: float = 0.25, largo: float = 120.0, ancho: float = 80.0,
                  lote: int = 1000) -> dict[str, np.ndarray]:
    """Rasgos por freeze frame. Devuelve columnas: id, d_rival, n_rivales, area_local,
    frac_visible, n_jugadores, actor_x, actor_y. Sin actor -> rasgos NaN."""
    D = puntos_disco(R)
    P = len(D)
    area_punto = math.pi * R * R / P
    ids, out = [], {k: [] for k in ("d_rival", "n_rivales", "area_local", "frac_visible",
                                     "n_jugadores", "actor_x", "actor_y")}
    for a in range(0, len(frames), lote):
        bloque = frames[a:a + lote]
        F = len(bloque)
        M = max([len(f.get("freeze_frame") or []) for f in bloque] + [1])
        V = max([len(f.get("visible_area") or []) // 2 for f in bloque] + [3])
        pos = np.full((F, M, 2), np.nan)
        comp = np.zeros((F, M), dtype=bool)
        es_actor = np.zeros((F, M), dtype=bool)
        poly = np.zeros((F, V, 2))
        tiene_poly = np.zeros(F, dtype=bool)
        for f, fr in enumerate(bloque):
            ids.append(fr.get("event_uuid") or fr.get("id"))
            for m, pl_ in enumerate(fr.get("freeze_frame") or []):
                loc = pl_.get("location")
                if loc is None or len(loc) < 2:
                    continue
                pos[f, m] = loc[:2]
                comp[f, m] = bool(pl_.get("teammate"))
                es_actor[f, m] = bool(pl_.get("actor"))
            va = fr.get("visible_area") or []
            if len(va) >= 6:
                v = np.asarray(va[: 2 * (len(va) // 2)], dtype=float).reshape(-1, 2)
                poly[f, : len(v)] = v
                poly[f, len(v):] = v[-1]
                tiene_poly[f] = True
        valido = np.isfinite(pos[:, :, 0])
        con_actor = (es_actor & valido).any(axis=1)
        ia = np.argmax(es_actor & valido, axis=1)
        A = pos[np.arange(F), ia]
        A[~con_actor] = np.nan
        # rivales
        rival = valido & ~comp & ~es_actor
        d = np.linalg.norm(pos - A[:, None, :], axis=2)
        d_r = np.where(rival, d, np.inf)
        d_rival = d_r.min(axis=1)
        n_riv = (d_r <= r_presion).sum(axis=1).astype(float)
        # celda de Voronoi local por cuadratura
        Q = A[:, None, :] + D[None, :, :]                            # (F, P, 2)
        en_cancha = (Q[..., 0] >= 0) & (Q[..., 0] <= largo) & (Q[..., 1] >= 0) & (Q[..., 1] <= ancho)
        visible = np.ones((F, P), dtype=bool)
        if tiene_poly.any():
            vis = dentro_poligono(Q[..., 0], Q[..., 1], poly)
            visible = np.where(tiene_poly[:, None], vis, True)
        util = en_cancha & visible
        otros = valido & ~(np.arange(M)[None, :] == ia[:, None])
        d_otros = np.linalg.norm(Q[:, :, None, :] - pos[:, None, :, :], axis=3)   # (F, P, M)
        d_otros = np.where(otros[:, None, :], d_otros, np.inf).min(axis=2)
        d_act = np.linalg.norm(D, axis=1)[None, :]
        propio = (d_act <= d_otros) & util
        n_util, n_cancha = util.sum(axis=1), en_cancha.sum(axis=1)
        frac_vis = np.where(n_cancha > 0, n_util / np.maximum(n_cancha, 1), 0.0)
        area = propio.sum(axis=1) / np.maximum(n_util, 1) * n_cancha * area_punto
        area = np.where(frac_vis >= min_visible, area, np.nan)
        d_rival = np.where(np.isfinite(d_rival), d_rival, np.nan)
        for arr in (d_rival, n_riv, area):
            arr[~con_actor] = np.nan
        out["d_rival"].append(d_rival)
        out["n_rivales"].append(np.where(con_actor, n_riv, np.nan))
        out["area_local"].append(area)
        out["frac_visible"].append(frac_vis)
        out["n_jugadores"].append(valido.sum(axis=1))
        out["actor_x"].append(A[:, 0])
        out["actor_y"].append(A[:, 1])
    res = {k: (np.concatenate(v) if v else np.array([])) for k, v in out.items()}
    res["id"] = np.array(ids, dtype=object)
    return res


def _rasgos_archivo(args) -> pl.DataFrame | None:
    ruta, kw = args
    try:
        with gzip.open(ruta, "rb") as fh:
            frames = _frames_de(_loads(fh.read()))
    except (OSError, ValueError):
        return None
    if not frames:
        return None
    r = rasgos_frames(frames, **kw)
    mid = int(Path(ruta).name.split(".")[0])
    return pl.DataFrame({"match_id": np.full(len(r["id"]), mid, dtype=np.int64),
                         "id": r["id"].astype(str),
                         **{k: r[k] for k in r if k != "id"}})


def rasgos_liga(dir_frames: Path, kw: dict, hilos: int = 4) -> pl.DataFrame:
    """Rasgos de todos los partidos con 360. `spawn`, no `fork` (ADR-v2-09)."""
    archivos = sorted(str(p) for p in Path(dir_frames).glob("*.json*"))
    if not archivos:
        raise FileNotFoundError(f"No hay freeze frames en {dir_frames}")
    tareas = [(a, kw) for a in archivos]
    if hilos <= 1:
        partes = [_rasgos_archivo(t) for t in tareas]
    else:
        with ProcessPoolExecutor(hilos, mp_context=mp.get_context("spawn")) as ex:
            partes = list(ex.map(_rasgos_archivo, tareas, chunksize=4))
    partes = [p for p in partes if p is not None and p.height]
    return pl.concat(partes, how="vertical_relaxed")


def unir_eventos(r: pl.DataFrame, eventos: pl.LazyFrame) -> pl.DataFrame:
    """Agrega `event_index` (la llave de las transiciones) y la distancia entre el
    actor del frame y la ubicación del evento: el contraste que detecta un frame
    en otra orientación (debe ser ~0 m)."""
    ev = (eventos.select("id", "index", "match_id", "location").collect()
          .with_columns(pl.col("location").list.get(0, null_on_oob=True).alias("_x"),
                        pl.col("location").list.get(1, null_on_oob=True).alias("_y"))
          .drop("location").rename({"index": "event_index"}))
    return (r.join(ev, on=["match_id", "id"], how="inner")
            .with_columns((((pl.col("actor_x") - pl.col("_x")) ** 2 + (pl.col("actor_y") - pl.col("_y")) ** 2)
                           .sqrt()).alias("d_actor_evento"))
            .drop("_x", "_y"))


# ======================================================================
# Discretización: rasgos continuos -> nivel de presión
# ======================================================================
def etiquetas_niveles(L: int) -> list[str]:
    return {1: ["all"], 2: ["libre", "presionado"], 3: ["libre", "medio", "presionado"]}.get(
        L, [f"p{l}" for l in range(L)])


def _transformar(df: pl.DataFrame, rasgos: tuple[str, ...]) -> np.ndarray:
    cols = []
    for r in rasgos:
        x = df[r].cast(pl.Float64).to_numpy()
        if r == "d_rival":
            x = np.log(np.clip(x, 0.0, 30.0) + 0.25)
        elif r == "area_local":
            x = np.sqrt(np.clip(x, 0.0, None))
        cols.append(x)
    return np.column_stack(cols)


def _kmeans(Z: np.ndarray, L: int, seed: int, n_init: int = 5, iters: int = 100) -> np.ndarray:
    rng = np.random.default_rng(seed)
    mejor, J_mejor = None, np.inf
    for _ in range(n_init):
        c = [Z[rng.integers(len(Z))]]
        for _ in range(1, L):                              # k-means++
            d2 = np.min(((Z[:, None, :] - np.array(c)[None]) ** 2).sum(-1), axis=1)
            c.append(Z[rng.choice(len(Z), p=d2 / d2.sum())])
        c = np.array(c)
        for _ in range(iters):
            lab = ((Z[:, None, :] - c[None]) ** 2).sum(-1).argmin(1)
            nuevo = np.array([Z[lab == l].mean(0) if (lab == l).any() else c[l] for l in range(L)])
            if np.allclose(nuevo, c):
                break
            c = nuevo
        J = ((Z - c[lab]) ** 2).sum()
        if J < J_mejor:
            mejor, J_mejor = c, J
    return mejor


@dataclass
class Discretizador:
    metodo: str                     # "cuantiles" (solo d_rival) | "kmeans" (todos los rasgos)
    L: int
    rasgos: tuple[str, ...] = RASGOS
    media: list = field(default_factory=list)
    escala: list = field(default_factory=list)
    cortes: list = field(default_factory=list)     # cuantiles, en la escala transformada
    centros: list = field(default_factory=list)    # kmeans, estandarizados

    @property
    def nombre(self) -> str:
        return f"{self.metodo}:{self.L}"

    @property
    def etiquetas(self) -> list[str]:
        return etiquetas_niveles(self.L)

    @classmethod
    def ajustar(cls, rasgos: pl.DataFrame, metodo: str, L: int, seed: int = 0,
                n_max: int = 200_000) -> Discretizador:
        rs = ("d_rival",) if metodo == "cuantiles" else RASGOS
        Z = _transformar(rasgos, rs)
        Z = Z[np.isfinite(Z).all(axis=1)]
        if len(Z) > n_max:
            Z = Z[np.random.default_rng(seed).choice(len(Z), n_max, replace=False)]
        d = cls(metodo, L, rs, Z.mean(0).tolist(), (Z.std(0) + 1e-12).tolist())
        if L == 1:
            return d
        Zs = (Z - d.media) / d.escala
        if metodo == "cuantiles":
            # más distancia al rival = más libre: nivel 0 = cuantil superior
            d.cortes = np.quantile(Zs[:, 0], np.arange(1, L) / L).tolist()
        elif metodo == "kmeans":
            c = _kmeans(Zs, L, seed)
            orden = np.argsort(-c[:, 0])            # nivel 0 = mayor distancia al rival (libre)
            d.centros = c[orden].tolist()
        else:
            raise ValueError(f"método desconocido: {metodo}")
        return d

    def nivel(self, rasgos: pl.DataFrame) -> np.ndarray:
        """Nivel 0..L-1 por fila; -1 si falta algún rasgo."""
        Z = _transformar(rasgos, self.rasgos)
        ok = np.isfinite(Z).all(axis=1)
        out = np.full(len(Z), -1, dtype=np.int64)
        if self.L == 1:
            out[ok] = 0
            return out
        Zs = (Z[ok] - np.asarray(self.media)) / np.asarray(self.escala)
        if self.metodo == "cuantiles":
            out[ok] = (self.L - 1) - np.searchsorted(np.asarray(self.cortes), Zs[:, 0], side="right")
        else:
            c = np.asarray(self.centros)
            out[ok] = ((Zs[:, None, :] - c[None]) ** 2).sum(-1).argmin(1)
        return out

    def guardar(self, ruta: Path) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({**self.__dict__, "rasgos": list(self.rasgos)}, indent=2))

    @classmethod
    def cargar(cls, ruta: Path) -> Discretizador:
        d = json.loads(Path(ruta).read_text())
        d["rasgos"] = tuple(d["rasgos"])
        return cls(**d)


# ======================================================================
# Transiciones aumentadas: (zona) -> (zona, nivel)
# ======================================================================
def aumentar(trans: pl.DataFrame, rasgos: pl.DataFrame, disc: Discretizador, n_zonas: int,
             min_cobertura: float = 0.9) -> tuple[pl.DataFrame, dict]:
    """Recodifica las transiciones de la malla (una sola fase) al estado zona × nivel.

    - Origen de cada acción: el nivel de SU freeze frame.
    - Destino transitorio: el nivel de la SIGUIENTE acción de la posesión (es el
      mismo estado desde el que parte), para que destino(t) y origen(t+1) coincidan.
      Si no hay siguiente acción, el destino hereda el nivel del origen (se cuenta).
    - Fila TERMINAL: parte del destino de la fila anterior.
    - Sin frame: se imputa con el nivel más cercano de la misma posesión (se cuenta).
      Partidos con cobertura < `min_cobertura` salen COMPLETOS (sin 360 no hay estado).
    Todo lo que sale se compara contra la MISMA muestra con L = 1 (`aumentar` con
    un discretizador de un nivel), para que la comparación no mezcle partidos.
    """
    if int(trans["from_state"].max()) >= n_zonas:
        raise ValueError("`aumentar` espera transiciones de UNA fase (from_state = zona)")
    L = disc.L
    n_abs = int(trans["to_state"].max()) - n_zonas + 1
    n_abs = max(n_abs, 4)
    r = rasgos.select("match_id", "event_index", *RASGOS).unique(["match_id", "event_index"], keep="first")
    # la MISMA máscara de faltantes para todos los discretizadores (con todos los rasgos):
    # si no, cada candidato imputaría filas distintas y la comparación no sería pareada
    completo = np.isfinite(_transformar(r, RASGOS)).all(axis=1)
    r = r.with_columns(pl.Series("_nivel", np.where(completo, disc.nivel(r), -1)))
    t = (trans.with_row_index("_fila")
         .join(r.select("match_id", "event_index", "_nivel"), on=["match_id", "event_index"], how="left")
         .with_columns(pl.when(pl.col("action_type") == "TERMINAL").then(None)
                       .otherwise(pl.col("_nivel")).alias("_nivel"))
         .with_columns(pl.when(pl.col("_nivel") >= 0).then(pl.col("_nivel")).otherwise(None).alias("_nivel"))
         .sort(["poss_uid", "event_index"]))
    real = pl.col("action_type") != "TERMINAL"
    cob = (t.filter(real).group_by("match_id")
           .agg(pl.col("_nivel").is_not_null().mean().alias("cob")))
    ok = cob.filter(pl.col("cob") >= min_cobertura)["match_id"]
    diag = {"partidos_total": int(t["match_id"].n_unique()), "partidos_con_360": int(ok.len()),
            "cobertura_media_partidos_ok": float(cob.filter(pl.col("cob") >= min_cobertura)["cob"].mean() or 0.0)}
    t = t.filter(pl.col("match_id").is_in(ok.to_list()))
    n_real = t.filter(real).height
    t = t.with_columns(pl.col("_nivel").is_null().alias("_imp"))
    # imputación dentro de la posesión (solo filas reales)
    t = t.with_columns(pl.when(real).then(pl.col("_nivel")).alias("_nivel")).with_columns(
        pl.when(real).then(pl.col("_nivel").forward_fill().backward_fill().over("poss_uid"))
        .alias("_nivel"))
    diag["frac_origen_imputado"] = float(t.filter(real)["_imp"].mean() or 0.0)
    # destino: nivel de la siguiente fila REAL de la posesión
    sig = pl.when(real).then(pl.col("_nivel")).shift(-1).over("poss_uid")
    sig_real = real.shift(-1).over("poss_uid").fill_null(False)
    t = t.with_columns(pl.when(sig_real).then(sig).otherwise(None).alias("_nivel_to"))
    transit = pl.col("to_state") < n_zonas
    diag["frac_destino_heredado"] = float(
        t.filter(real & transit)["_nivel_to"].is_null().mean() or 0.0)
    t = t.with_columns(pl.col("_nivel_to").fill_null(pl.col("_nivel")))
    t = t.with_columns(pl.when(real).then(pl.col("_nivel"))
                       .otherwise(pl.col("_nivel_to").shift(1).over("poss_uid")).alias("_nivel"))
    t = t.with_columns(pl.when(~real).then(pl.col("_nivel")).otherwise(pl.col("_nivel_to")).alias("_nivel_to"))
    # secuencias sin ningún nivel (posesión completa sin frame) salen
    malas = t.filter(pl.col("_nivel").is_null() | pl.col("_nivel_to").is_null())["seq_uid"].unique()
    diag["secuencias_sin_nivel"] = int(malas.len())
    t = t.filter(~pl.col("seq_uid").is_in(malas.to_list()))
    diag["frac_filas_reales_conservadas"] = float(t.filter(real).height / max(n_real, 1))
    et = disc.etiquetas
    t = t.with_columns(
        (pl.col("from_state") * L + pl.col("_nivel")).alias("from_state"),
        pl.when(transit).then(pl.col("to_state") * L + pl.col("_nivel_to"))
        .otherwise(pl.col("to_state") - n_zonas + n_zonas * L).alias("to_state"),
        pl.col("_nivel").replace_strict(list(range(L)), et, return_dtype=pl.Utf8).alias("phase"),
    ).sort("_fila").drop("_fila", "_nivel", "_nivel_to", "_imp")
    diag.update({"transiciones": t.height, "secuencias": int(t["seq_uid"].n_unique()), "L": L,
                 "n_abs": n_abs})
    return t, diag


# ======================================================================
# Validación cruzada en la escala común (ADR-v2-32)
# ======================================================================
def conteos_marginales(t: pl.DataFrame, n_zonas: int, L: int, folds: list[np.ndarray],
                       n_abs: int = 4) -> np.ndarray:
    """(F, n_zonas*L, n_zonas + n_abs): conteos por pliegue con el DESTINO en la escala
    común (zona o absorbente). El origen conserva el nivel: es la información que se
    evalúa. El nivel del destino no se predice (no existe en el modelo base)."""
    nt, nd = n_zonas * L, n_zonas + n_abs
    fold_de = {int(m): f for f, ms in enumerate(folds) for m in ms}
    f = np.array([fold_de[int(m)] for m in t["match_id"].to_numpy()])
    i = t["from_state"].to_numpy().astype(np.int64)
    j = t["to_state"].to_numpy().astype(np.int64)
    jd = np.where(j < nt, j // L, j - nt + n_zonas)
    F = len(folds)
    return np.bincount((f * nt + i) * nd + jd, minlength=F * nt * nd).reshape(F, nt, nd).astype(float)


def puntaje_cv(C: np.ndarray, n_zonas: int, lam_grid: list[float]) -> dict:
    """Densidad predictiva del siguiente punto (nats/transición) por pliegue, con el
    mejor λ común: log[P(zona | origen) / a_zona] o log P(absorbente | origen).
    Descompuesta en destinos transitorios y absorbentes."""
    F, nt, nd = C.shape
    tot = C.sum(0)
    U = np.full((nt, nd), 1.0 / nd)
    log_a = np.log(1.0 / n_zonas)
    por_lam = {}
    for lam in lam_grid:
        filas = []
        for f in range(F):
            P = shrink(tot - C[f], U, lam)
            lp = np.log(np.maximum(P, _EPS))
            ll_t = float((C[f][:, :n_zonas] * (lp[:, :n_zonas] - log_a)).sum())
            ll_a = float((C[f][:, n_zonas:] * lp[:, n_zonas:]).sum())
            n = C[f].sum()
            filas.append(((ll_t + ll_a) / n, ll_t / n, ll_a / n))
        por_lam[lam] = np.array(filas)
    lam = max(por_lam, key=lambda l: por_lam[l][:, 0].mean())
    v = por_lam[lam]
    return {"lam": lam, "pliegues": v[:, 0], "score": float(v[:, 0].mean()),
            "score_transitorio": float(v[:, 1].mean()), "score_absorbente": float(v[:, 2].mean()),
            "estados": nt}


def comparar(res: dict[str, dict], base: str = "base:1") -> tuple[str, pl.DataFrame]:
    """Diferencia pareada contra la base (L = 1) y contra el mejor. Regla: el mejor
    candidato; entre los que quedan a menos de 1 EE pareado del mejor, el de menos
    estados. `mejora` exige superar a la base por más de 2 EE pareados."""
    mejor = max(res, key=lambda n: res[n]["score"])
    filas = []
    for n, r in res.items():
        db = r["pliegues"] - res[base]["pliegues"]
        dm = r["pliegues"] - res[mejor]["pliegues"]
        se_b = float(db.std(ddof=1) / np.sqrt(len(db))) if n != base else 0.0
        se_m = float(dm.std(ddof=1) / np.sqrt(len(dm))) if n != mejor else 0.0
        filas.append({"candidato": n, "estados": r["estados"], "lam": r["lam"], "score": r["score"],
                      "score_transitorio": r["score_transitorio"], "score_absorbente": r["score_absorbente"],
                      "dif_vs_base": float(db.mean()), "se_vs_base": se_b,
                      "mejora": bool(n != base and db.mean() > 2 * se_b),
                      "dentro_1se_del_mejor": bool(dm.mean() >= -se_m)})
    tab = pl.DataFrame(filas).sort(["estados", "candidato"])
    elegido = tab.filter(pl.col("dentro_1se_del_mejor")).sort(["estados", "score"], descending=[False, True])[
        "candidato"][0]
    return elegido, tab


def pliegues_partido(match_ids: np.ndarray, k: int, seed: int) -> list[np.ndarray]:
    return match_folds(np.unique(match_ids), k, seed)
