"""
G0 -- Campos adicionales del JSON de eventos, en una tabla lateral.

POR QUÉ UNA TABLA APARTE
------------------------
El parquet de `dtcoach aplanar` alimenta la cadena, el vocabulario y las fases 2–3.
Rehacerlo para agregar columnas obligaría a rehacer todo lo de aguas abajo. Los
campos que piden la fase ofensiva (G1) y el balón parado (G5) se leen UNA vez de
los mismos JSON y se guardan en `data/interim/eventos_extra.parquet`, con la llave
(match_id, id) del evento. `unir` los agrega a la tabla de `eventos.leer`.

CAMPOS (StatsBomb escribe `true` u OMITE la llave: se emite False explícito)
  pase     pass_cross, pass_switch, pass_through_ball, pass_cut_back,
           pass_shot_assist, pass_goal_assist, pass_technique (Inswinging,
           Outswinging, Straight, Through Ball), pass_body_part, pass_length,
           pass_angle, pass_aerial_won
  remate   shot_first_time, shot_key_pass_id, shot_technique, shot_one_on_one
  portero  goalkeeper_type (Punch, Collected, Keeper Sweeper, …), goalkeeper_outcome
  otros    clearance_aerial_won, duel_type, duel_outcome
Solo se guardan filas de los tipos que los usan (Pass, Shot, Goal Keeper,
Clearance, Duel): el resto no tiene ninguno de estos campos.
"""
from __future__ import annotations

import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import polars as pl

from .aplanar import _loads, _n, _num, eventos_de, match_id_de

TIPOS = ("Pass", "Shot", "Goal Keeper", "Clearance", "Duel")

SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "match_id": pl.Int64,
    "pass_cross": pl.Boolean,
    "pass_switch": pl.Boolean,
    "pass_through_ball": pl.Boolean,
    "pass_cut_back": pl.Boolean,
    "pass_shot_assist": pl.Boolean,
    "pass_goal_assist": pl.Boolean,
    "pass_technique": pl.Utf8,
    "pass_body_part": pl.Utf8,
    "pass_length": pl.Float64,
    "pass_angle": pl.Float64,
    "pass_aerial_won": pl.Boolean,
    "shot_first_time": pl.Boolean,
    "shot_key_pass_id": pl.Utf8,
    "shot_technique": pl.Utf8,
    "shot_one_on_one": pl.Boolean,
    "goalkeeper_type": pl.Utf8,
    "goalkeeper_outcome": pl.Utf8,
    "clearance_aerial_won": pl.Boolean,
    "duel_type": pl.Utf8,
    "duel_outcome": pl.Utf8,
}
BANDERAS = [c for c, t in SCHEMA.items() if t == pl.Boolean]


def fila(ev: dict, match_id: int) -> dict | None:
    tipo = _n(ev.get("type"))
    if tipo not in TIPOS:
        return None
    p = ev.get("pass") or {}
    s = ev.get("shot") or {}
    g = ev.get("goalkeeper") or {}
    c = ev.get("clearance") or {}
    d = ev.get("duel") or {}
    # StatsBomb v4 escribe la técnica del pase en `technique`; versiones viejas usaban
    # `inswinging`/`outswinging`/`straight` como banderas sueltas: se aceptan las dos.
    tec = _n(p.get("technique"))
    if tec is None:
        for k, nombre in (("inswinging", "Inswinging"), ("outswinging", "Outswinging"), ("straight", "Straight")):
            if p.get(k):
                tec = nombre
    return {
        "id": ev.get("id"),
        "match_id": match_id,
        "pass_cross": bool(p.get("cross", False)),
        "pass_switch": bool(p.get("switch", False)),
        "pass_through_ball": bool(p.get("through_ball", False)) or tec == "Through Ball",
        "pass_cut_back": bool(p.get("cut_back", False)),
        "pass_shot_assist": bool(p.get("shot_assist", False)),
        "pass_goal_assist": bool(p.get("goal_assist", False)),
        "pass_technique": tec,
        "pass_body_part": _n(p.get("body_part")),
        "pass_length": _num(p.get("length")),
        "pass_angle": _num(p.get("angle")),
        "pass_aerial_won": bool(p.get("aerial_won", False)),
        "shot_first_time": bool(s.get("first_time", False)),
        "shot_key_pass_id": s.get("key_pass_id"),
        "shot_technique": _n(s.get("technique")),
        "shot_one_on_one": bool(s.get("one_on_one", False)),
        "goalkeeper_type": _n(g.get("type")),
        "goalkeeper_outcome": _n(g.get("outcome")),
        "clearance_aerial_won": bool(c.get("aerial_won", False)),
        "duel_type": _n(d.get("type")),
        "duel_outcome": _n(d.get("outcome")),
    }


def leer_partido(path: Path) -> list[dict]:
    import gzip
    with gzip.open(path, "rb") as f:
        data = _loads(f.read())
    mid = match_id_de(path)
    out = []
    for ev in eventos_de(data, path.name):
        r = fila(ev, mid)
        if r is not None:
            out.append(r)
    return out


def _lote(paths: list[str]) -> tuple[pl.DataFrame | None, list[str]]:
    filas, errores = [], []
    for p in paths:
        try:
            filas.extend(leer_partido(Path(p)))
        except Exception as e:  # se reporta, no se esconde (como aplanar)
            errores.append(f"{Path(p).name}: {type(e).__name__}: {e}")
    df = pl.DataFrame(filas, schema=SCHEMA, strict=False, orient="row") if filas else None
    return df, errores


def extraer(src: Path, dst: Path, por_lote: int = 40, hilos: int = 6) -> dict:
    """Lee todos los `<match_id>.json.gz` de `src` y escribe `dst` (un parquet)."""
    archivos = sorted(Path(src).glob("*.json.gz"), key=match_id_de)
    if not archivos:
        raise FileNotFoundError(f"Sin .json.gz en {src}")
    lotes = [archivos[i:i + por_lote] for i in range(0, len(archivos), por_lote)]
    t0 = time.time()
    partes, errores = [], []
    with ProcessPoolExecutor(max_workers=hilos, mp_context=mp.get_context("spawn")) as ex:
        futs = [ex.submit(_lote, [str(p) for p in lote]) for lote in lotes]
        for i, fu in enumerate(as_completed(futs), 1):
            df, err = fu.result()
            errores += err
            if df is not None:
                partes.append(df)
            if i % 10 == 0 or i == len(futs):
                print(f"  lotes {i}/{len(futs)}  ({time.time() - t0:.0f}s)", flush=True)
    out = pl.concat(partes, how="vertical_relaxed") if partes else pl.DataFrame(schema=SCHEMA)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(dst, compression="zstd")
    return {"archivos": len(archivos), "filas": out.height, "errores": sorted(errores),
            "segundos": round(time.time() - t0, 1),
            "centros": int(out["pass_cross"].sum()), "pases_filtrados": int(out["pass_through_ball"].sum()),
            "pases_atras": int(out["pass_cut_back"].sum()),
            "tecnica_con_dato": int(out["pass_technique"].is_not_null().sum())}


def unir(ev: pl.DataFrame, extra: pl.DataFrame | None) -> pl.DataFrame:
    """Agrega los campos extra a `eventos.leer`. Sin la tabla, las columnas quedan en
    nulo/False y las métricas que las usan se reportan como "sin datos" (no se inventan)."""
    if extra is None or extra.height == 0:
        return ev.with_columns([pl.lit(False).alias(c) if c in BANDERAS else
                                pl.lit(None, dtype=SCHEMA[c]).alias(c)
                                for c in SCHEMA if c not in ("id", "match_id") and c not in ev.columns])
    cols = [c for c in SCHEMA if c not in ev.columns or c in ("id", "match_id")]
    out = ev.join(extra.select(cols), on=["match_id", "id"], how="left")
    return out.with_columns([pl.col(c).fill_null(False) for c in BANDERAS if c in out.columns])


def tiene_extra(ev: pl.DataFrame) -> bool:
    """¿Hay campos extra reales? (con la tabla ausente todo es False/nulo)."""
    return "pass_technique" in ev.columns and ev["pass_technique"].is_not_null().any()
