"""
Fases B y E -- Geometría del 360: el bloque sin balón y el marcaje a balón parado.

BLOQUE (organización defensiva, reto 5.1)
-----------------------------------------
En cada freeze frame, los jugadores visibles del equipo SIN balón (no compañeros
del actor, sin portero) en SU marco (x' = 120 − x, y' = 80 − y):
  altura    x' media: a qué distancia de su arco defiende el bloque
  anchura   max y' − min y'
  profundidad  max x' − min x'
  area      área de la envolvente convexa (Barber et al., Quickhull)
Solo si hay ≥ `min_defensores` visibles: con menos, la envolvente describe lo que
la cámara vio, no el bloque. Límite declarado: el 360 no es tracking; los
jugadores fuera de `visible_area` no se imputan (03_FRAMEWORK §4).

MARCAJE A BALÓN PARADO (reto 5.4)
---------------------------------
En el frame del SAQUE de un corner o tiro libre lateral, atacantes (compañeros del
lanzador, sin él) y defensores (sin portero) dentro de la zona de remate. Cada
defensor se asigna a un atacante minimizando la distancia total (problema de
asignación lineal, algoritmo húngaro; Kuhn 1955):
  dist_marca   distancia media defensor–atacante en la asignación óptima: baja =
               marcas cerca de su hombre (individual); alta = defensores en zonas
  sobra        defensores − atacantes en la zona (superioridad numérica)
"""
from __future__ import annotations

import gzip
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import polars as pl
from scipy.optimize import linear_sum_assignment
from scipy.spatial import ConvexHull, QhullError

from .voronoi import _frames_de, _loads

ZONA_REMATE = (96.0, 14.0, 66.0)       # x ≥ 96, 14 ≤ y ≤ 66 en el marco del que ataca


def _jugadores(fr: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    ff = fr.get("freeze_frame") or []
    pos = np.array([p.get("location", [np.nan, np.nan])[:2] for p in ff], dtype=float).reshape(-1, 2)
    comp = np.array([bool(p.get("teammate")) for p in ff], dtype=bool)
    actor = np.array([bool(p.get("actor")) for p in ff], dtype=bool)
    port = np.array([bool(p.get("keeper")) for p in ff], dtype=bool)
    return pos, comp, actor, port


def bloque(fr: dict, min_defensores: int = 6) -> dict | None:
    pos, comp, actor, port = _jugadores(fr)
    ok = np.isfinite(pos).all(axis=1)
    d = pos[ok & ~comp & ~actor & ~port]
    if len(d) < min_defensores:
        return None
    x, y = 120.0 - d[:, 0], 80.0 - d[:, 1]
    try:
        area = float(ConvexHull(np.column_stack([x, y])).volume)
    except QhullError:
        area = 0.0
    return {"altura": float(x.mean()), "anchura": float(y.max() - y.min()),
            "profundidad": float(x.max() - x.min()), "area": area, "n_def": len(d)}


def marcaje(fr: dict, zona: tuple = ZONA_REMATE) -> dict | None:
    pos, comp, actor, port = _jugadores(fr)
    ok = np.isfinite(pos).all(axis=1)
    dentro = ok & (pos[:, 0] >= zona[0]) & (pos[:, 1] >= zona[1]) & (pos[:, 1] <= zona[2])
    at = pos[dentro & comp & ~actor]
    de = pos[dentro & ~comp & ~port]
    if len(at) == 0 or len(de) == 0:
        return None
    D = np.linalg.norm(de[:, None, :] - at[None, :, :], axis=2)
    i, j = linear_sum_assignment(D)
    return {"dist_marca": float(D[i, j].mean()), "n_atacantes": len(at), "n_defensores": len(de),
            "sobra": int(len(de) - len(at))}


def _archivo(args) -> tuple[list, list]:
    ruta, ids_marcaje, min_def = args
    try:
        with gzip.open(ruta, "rb") as fh:
            frames = _frames_de(_loads(fh.read()))
    except (OSError, ValueError):
        return [], []
    mid = int(Path(ruta).name.split(".")[0])
    B, Mk = [], []
    for fr in frames:
        uid = fr.get("event_uuid") or fr.get("id")
        b = bloque(fr, min_def)
        if b is not None:
            B.append({"match_id": mid, "id": str(uid), **b})
        if uid in ids_marcaje:
            m = marcaje(fr)
            if m is not None:
                Mk.append({"match_id": mid, "id": str(uid), **m})
    return B, Mk


def geometria_liga(dir_frames: Path, ids_marcaje: dict[int, set], min_def: int = 6,
                   hilos: int = 4) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Recorre todos los frames una vez. `ids_marcaje`: por partido, los eventos (saques) a marcar."""
    archivos = sorted(str(p) for p in Path(dir_frames).glob("*.json*"))
    if not archivos:
        raise FileNotFoundError(f"No hay freeze frames en {dir_frames}")
    tareas = [(a, ids_marcaje.get(int(Path(a).name.split(".")[0]), set()), min_def) for a in archivos]
    if hilos <= 1:
        partes = [_archivo(t) for t in tareas]
    else:
        with ProcessPoolExecutor(hilos, mp_context=mp.get_context("spawn")) as ex:
            partes = list(ex.map(_archivo, tareas, chunksize=4))
    B = [r for b, _ in partes for r in b]
    M = [r for _, m in partes for r in m]
    esquema_b = {"match_id": pl.Int64, "id": pl.Utf8, "altura": pl.Float64, "anchura": pl.Float64,
                 "profundidad": pl.Float64, "area": pl.Float64, "n_def": pl.Int64}
    esquema_m = {"match_id": pl.Int64, "id": pl.Utf8, "dist_marca": pl.Float64, "n_atacantes": pl.Int64,
                 "n_defensores": pl.Int64, "sobra": pl.Int64}
    return pl.DataFrame(B, schema=esquema_b), pl.DataFrame(M, schema=esquema_m)
