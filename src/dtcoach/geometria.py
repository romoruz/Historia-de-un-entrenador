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

  ancho_visible  extensión en y del área que ve la cámara (recortada a la cancha).
               Control del encuadre (G3): un bloque "estrecho" solo es del equipo si
               sobrevive entre frames con la cancha entera a la vista.

EL FRAME DEL SAQUE A BALÓN PARADO (reto 5.4, G5)
------------------------------------------------
En el frame del SAQUE (corner, tiro libre en campo rival, lateral largo), en el
marco del que saca (ataca hacia x = 120). Atacantes = compañeros del lanzador sin
él; defensores = rivales sin su portero.
  at_area, de_area        en el área (x ≥ 102, 18 ≤ y ≤ 62)
  at_chica, de_chica      en el área chica (x ≥ 114, 30 ≤ y ≤ 50)
  palo_cercano, palo_lejano  un defensor a ≤ 2 m del poste (cercano = del lado del saque)
  at_portero              atacantes a ≤ 2 m del portero: "acosar al portero" (la receta
                          que popularizó el Arsenal de N. Jover; Shaw & Gopaladesikan 2020)
  dist_marca, sobra       cada defensor se asigna a un atacante de la zona de remate
                          minimizando la distancia total (algoritmo húngaro; Kuhn 1955):
                          distancia media de la asignación y defensores − atacantes
  al_hombre, zonales      defensores del área con su atacante asignado a ≤ 2 m / el resto
                          (sin atacante o lejos de él): marca individual contra zonal
                          (Pulling, Robins & Rixon 2013)
  linea_x, altura_linea   LÍNEA DEL FUERA DE LUGAR: x del penúltimo defensor, portero
                          incluido (regla 11). altura_linea = 120 − linea_x: a cuántos metros
                          de su arco la pone el que defiende. Solo con el portero visible.
  altura_linea_tactica    la misma línea sin contar a los defensores parados sobre la línea de gol
                          (x ≥ 118: los que cuidan los palos). Un defensor en el poste deja la
                          línea legal casi en el arco, pero no es la línea que arma el técnico:
                          esta es la que se narra; la legal se guarda al lado.
  en_linea                defensores de campo a ≤ 2 m de la línea táctica (qué tan "línea" es)
  at_adelantados          atacantes por delante de la línea al momento del saque
  cobertura_area          fracción del área que ve la cámara: los conteos solo valen con
                          el área a la vista (se filtra en las métricas)
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
AREA = (102.0, 18.0, 62.0)
AREA_CHICA = (114.0, 30.0, 50.0)
POSTES = (36.0, 44.0)
_REJ_AREA = np.array([(x, y) for x in np.linspace(102.5, 119.5, 7) for y in np.linspace(18.5, 61.5, 9)])


def _dentro(p: np.ndarray, zona: tuple) -> np.ndarray:
    return (p[:, 0] >= zona[0]) & (p[:, 1] >= zona[1]) & (p[:, 1] <= zona[2])


def _poligono(fr: dict) -> np.ndarray | None:
    va = fr.get("visible_area") or []
    if len(va) < 6:
        return None
    return np.asarray(va[: 2 * (len(va) // 2)], dtype=float).reshape(-1, 2)


def ancho_visible(fr: dict) -> float:
    v = _poligono(fr)
    if v is None:
        return float("nan")
    y = np.clip(v[:, 1], 0.0, 80.0)
    return float(y.max() - y.min())


def cobertura(fr: dict, puntos: np.ndarray = _REJ_AREA) -> float:
    """Fracción de los `puntos` dentro del área visible (1.0 si el frame no trae polígono)."""
    v = _poligono(fr)
    if v is None:
        return 1.0
    from .voronoi import dentro_poligono
    dentro = dentro_poligono(puntos[None, :, 0], puntos[None, :, 1], v[None])
    return float(dentro.mean())


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
            "profundidad": float(x.max() - x.min()), "area": area, "n_def": len(d),
            "ancho_visible": ancho_visible(fr)}


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


def saque(fr: dict, r_marca: float = 2.0, r_poste: float = 2.0) -> dict | None:
    """Rasgos del frame del saque a balón parado (ver el encabezado). None sin lanzador."""
    pos, comp, actor, port = _jugadores(fr)
    ok = np.isfinite(pos).all(axis=1)
    if not (actor & ok).any():
        return None
    lanz = pos[actor & ok][0]
    at = pos[ok & comp & ~actor]
    de = pos[ok & ~comp & ~port]
    gk = pos[ok & ~comp & port]
    lado = -1.0 if lanz[1] < 40 else 1.0           # y < 40: saque desde la banda de y = 0
    cercano = np.array([120.0, POSTES[0] if lado < 0 else POSTES[1]])
    lejano = np.array([120.0, POSTES[1] if lado < 0 else POSTES[0]])
    out = {"at_area": int(_dentro(at, AREA).sum()), "de_area": int(_dentro(de, AREA).sum()),
           "at_chica": int(_dentro(at, AREA_CHICA).sum()), "de_chica": int(_dentro(de, AREA_CHICA).sum()),
           "palo_cercano": int((np.linalg.norm(de - cercano, axis=1) <= r_poste).any()) if len(de) else 0,
           "palo_lejano": int((np.linalg.norm(de - lejano, axis=1) <= r_poste).any()) if len(de) else 0,
           "gk_visible": int(len(gk) > 0), "cobertura_area": cobertura(fr)}
    if len(gk):
        g = gk[0]
        out |= {"gk_x": float(g[0]), "gk_y": float(g[1]),
                "at_portero": int((np.linalg.norm(at - g, axis=1) <= r_marca).sum()) if len(at) else 0}
    else:
        out |= {"gk_x": float("nan"), "gk_y": float("nan"), "at_portero": 0}
    # marcaje en la zona de remate (algoritmo húngaro)
    m = marcaje(fr)
    out |= ({k: m[k] for k in ("dist_marca", "sobra")} if m else {"dist_marca": float("nan"), "sobra": 0})
    at_a, de_a = at[_dentro(at, AREA)], de[_dentro(de, AREA)]
    if len(at_a) and len(de_a):
        D = np.linalg.norm(de_a[:, None, :] - at_a[None, :, :], axis=2)
        i, j = linear_sum_assignment(D)
        hombre = int((D[i, j] <= r_marca).sum())
    else:
        hombre = 0
    out |= {"al_hombre": hombre, "zonales": int(len(de_a) - hombre)}
    # línea del fuera de lugar: penúltimo defensor, portero incluido (solo con portero visible)
    todos = np.concatenate([de[:, 0], gk[:, 0]]) if len(gk) else de[:, 0]
    campo = de[de[:, 0] < 118.0] if len(de) else de            # sin los que cuidan la línea de gol
    tact = np.concatenate([campo[:, 0], gk[:, 0]]) if len(gk) else campo[:, 0]
    if len(gk) and len(todos) >= 2 and len(tact) >= 2:
        lx, tx = float(np.sort(todos)[-2]), float(np.sort(tact)[-2])
        out |= {"linea_x": lx, "altura_linea": 120.0 - lx, "altura_linea_tactica": 120.0 - tx,
                "en_linea": int((np.abs(campo[:, 0] - tx) <= 2.0).sum()),
                "at_adelantados": int((at[:, 0] > lx + 0.5).sum()) if len(at) else 0,
                "dist_linea_balon": tx - float(lanz[0])}
    else:
        out |= {"linea_x": float("nan"), "altura_linea": float("nan"), "altura_linea_tactica": float("nan"),
                "en_linea": 0, "at_adelantados": 0, "dist_linea_balon": float("nan")}
    return out


SAQUE_ESQUEMA = {"match_id": pl.Int64, "id": pl.Utf8, "at_area": pl.Int64, "de_area": pl.Int64,
                 "at_chica": pl.Int64, "de_chica": pl.Int64, "palo_cercano": pl.Int64, "palo_lejano": pl.Int64,
                 "gk_visible": pl.Int64, "cobertura_area": pl.Float64, "gk_x": pl.Float64, "gk_y": pl.Float64,
                 "at_portero": pl.Int64, "dist_marca": pl.Float64, "sobra": pl.Int64, "al_hombre": pl.Int64,
                 "zonales": pl.Int64, "linea_x": pl.Float64, "altura_linea": pl.Float64,
                 "altura_linea_tactica": pl.Float64, "en_linea": pl.Int64,
                 "at_adelantados": pl.Int64, "dist_linea_balon": pl.Float64}


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
            m = saque(fr)
            if m is not None:
                Mk.append({"match_id": mid, "id": str(uid), **m})
    return B, Mk


def geometria_liga(dir_frames: Path, ids_marcaje: dict[int, set], min_def: int = 6,
                   hilos: int = 4) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Recorre todos los frames una vez. `ids_marcaje`: por partido, los saques a balón parado."""
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
                 "profundidad": pl.Float64, "area": pl.Float64, "n_def": pl.Int64, "ancho_visible": pl.Float64}
    return pl.DataFrame(B, schema=esquema_b), pl.DataFrame(M, schema=SAQUE_ESQUEMA)
