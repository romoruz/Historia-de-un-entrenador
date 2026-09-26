"""
Fase 0.-1 -- Aplanado: eventos crudos del API (un .json.gz por partido) ->
parquet plano con el esquema que esperan `ingest` y `possessions`.

POR QUE EXISTE
--------------
El proyecto viejo leia un CSV ya aplanado (`pass_end_location`, `shot_outcome`,
...). El volcado nuevo es el JSON anidado del API. Este modulo es el UNICO
lugar donde se traduce un formato a otro: todo lo de aguas abajo sigue igual.

CONTRATO (se comprueba en tests/test_aplanar.py)
  - `match_id` sale del NOMBRE del archivo (`<match_id>.json.gz`).
  - Nombres (`type`, `team`, `play_pattern`, outcomes) como texto: `{"name": X}` -> X.
  - Coordenadas como List(Float64). Los remates traen 3 componentes; se conservan.
  - `shot_freeze_frame` y `tactics_lineup` como JSON (true/false), NO repr de
    Python: es el bug #21 del proyecto viejo.
  - Esquema EXPLICITO: nada se infiere de las primeras filas (bug de
    `infer_schema_length`).
  - Un archivo vacio o ilegible NO se aplana en silencio: queda en el reporte.
"""
from __future__ import annotations

import gzip
import json
import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import polars as pl

try:  # 3-5x mas rapido; opcional
    import orjson

    def _loads(b: bytes):
        return orjson.loads(b)
except ImportError:  # pragma: no cover
    def _loads(b: bytes):
        return json.loads(b)


LOC = pl.List(pl.Float64)
SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "index": pl.Int64,
    "match_id": pl.Int64,
    "period": pl.Int64,
    "timestamp": pl.Utf8,
    "minute": pl.Int64,
    "second": pl.Int64,
    "type": pl.Utf8,
    "team": pl.Utf8,
    "team_id": pl.Int64,
    "possession": pl.Int64,
    "possession_team": pl.Utf8,
    "possession_team_id": pl.Int64,
    "play_pattern": pl.Utf8,
    "player": pl.Utf8,
    "player_id": pl.Int64,
    "position": pl.Utf8,
    "location": LOC,
    "duration": pl.Float64,
    "under_pressure": pl.Boolean,
    "counterpress": pl.Boolean,
    "pass_end_location": LOC,
    "pass_outcome": pl.Utf8,
    "pass_type": pl.Utf8,
    "pass_height": pl.Utf8,
    "pass_recipient_id": pl.Int64,
    "carry_end_location": LOC,
    "shot_end_location": LOC,
    "shot_outcome": pl.Utf8,
    "shot_statsbomb_xg": pl.Float64,
    "shot_type": pl.Utf8,
    "shot_body_part": pl.Utf8,
    "shot_freeze_frame": pl.Utf8,
    "substitution_replacement": pl.Utf8,
    "substitution_replacement_id": pl.Int64,
    "substitution_outcome": pl.Utf8,
    "tactics_formation": pl.Int64,
    "tactics_lineup": pl.Utf8,
    "obv_for_net": pl.Float64,
    "obv_against_net": pl.Float64,
    "obv_total_net": pl.Float64,
}


def _n(d):
    return d.get("name") if isinstance(d, dict) else None


def _i(d):
    return d.get("id") if isinstance(d, dict) else None


def _loc(v):
    if not isinstance(v, list):
        return None
    try:
        return [float(x) for x in v]
    except (TypeError, ValueError):
        return None


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def fila(ev: dict, match_id: int) -> dict:
    p = ev.get("pass") or {}
    c = ev.get("carry") or {}
    s = ev.get("shot") or {}
    sub = ev.get("substitution") or {}
    tac = ev.get("tactics") or {}
    ff = s.get("freeze_frame")
    lu = tac.get("lineup")
    form = tac.get("formation")
    return {
        "id": ev.get("id"),
        "index": ev.get("index"),
        "match_id": match_id,
        "period": ev.get("period"),
        "timestamp": ev.get("timestamp"),
        "minute": ev.get("minute"),
        "second": ev.get("second"),
        "type": _n(ev.get("type")),
        "team": _n(ev.get("team")),
        "team_id": _i(ev.get("team")),
        "possession": ev.get("possession"),
        "possession_team": _n(ev.get("possession_team")),
        "possession_team_id": _i(ev.get("possession_team")),
        "play_pattern": _n(ev.get("play_pattern")),
        "player": _n(ev.get("player")),
        "player_id": _i(ev.get("player")),
        "position": _n(ev.get("position")),
        "location": _loc(ev.get("location")),
        "duration": _num(ev.get("duration")),
        # Banderas: StatsBomb escribe true u OMITE la llave. Se emite False
        # explicito: null aqui fue el casi-bug #13 del proyecto viejo.
        "under_pressure": bool(ev.get("under_pressure", False)),
        "counterpress": bool(ev.get("counterpress", False)),
        "pass_end_location": _loc(p.get("end_location")),
        "pass_outcome": _n(p.get("outcome")),
        "pass_type": _n(p.get("type")),
        "pass_height": _n(p.get("height")),
        "pass_recipient_id": _i(p.get("recipient")),
        "carry_end_location": _loc(c.get("end_location")),
        "shot_end_location": _loc(s.get("end_location")),
        "shot_outcome": _n(s.get("outcome")),
        "shot_statsbomb_xg": _num(s.get("statsbomb_xg")),
        "shot_type": _n(s.get("type")),
        "shot_body_part": _n(s.get("body_part")),
        "shot_freeze_frame": json.dumps(ff, ensure_ascii=False) if ff else None,
        "substitution_replacement": _n(sub.get("replacement")),
        "substitution_replacement_id": _i(sub.get("replacement")),
        "substitution_outcome": _n(sub.get("outcome")),
        "tactics_formation": int(form) if isinstance(form, (int, float, str)) and str(form).isdigit() else None,
        "tactics_lineup": json.dumps(lu, ensure_ascii=False) if lu else None,
        "obv_for_net": _num(ev.get("obv_for_net")),
        "obv_against_net": _num(ev.get("obv_against_net")),
        "obv_total_net": _num(ev.get("obv_total_net")),
    }


def match_id_de(path: Path) -> int:
    return int(path.name.split(".")[0])


def eventos_de(data, nombre: str = "") -> list[dict]:
    """Extrae la lista de eventos de los envoltorios conocidos del volcado.

    - lista de eventos                      (formato del API)
    - {"events": [...]} / {"data": [...]}   (envoltorio del descargador)
    - {event_id: evento, ...}               (diccionario por id)
    Cualquier otra cosa FALLA mostrando las claves: adivinar aqui seria un
    bug silencioso.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("events", "data", "eventos", "result", "results"):
            if isinstance(data.get(k), list):
                return data[k]
        vals = list(data.values())
        if vals and all(isinstance(v, dict) and "type" in v for v in vals):
            return vals
        claves = list(data.keys())[:10]
        raise ValueError(f"{nombre}: formato no reconocido; claves de primer nivel: {claves}")
    raise ValueError(f"{nombre}: formato no reconocido ({type(data).__name__})")


def leer_partido(path: Path) -> list[dict]:
    with gzip.open(path, "rb") as f:
        data = _loads(f.read())
    mid = match_id_de(path)
    return [fila(ev, mid) for ev in eventos_de(data, path.name)]


def a_frame(filas: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(filas, schema=SCHEMA, strict=False, orient="row")


def _lote(paths: list[str], destino: str) -> dict:
    filas, vacios, errores = [], [], []
    for p in paths:
        try:
            f = leer_partido(Path(p))
        except Exception as e:  # se reporta, no se esconde
            errores.append(f"{Path(p).name}: {type(e).__name__}: {e}")
            continue
        if not f:
            vacios.append(Path(p).name)
            continue
        filas.extend(f)
    n = 0
    if filas:
        df = a_frame(filas)
        df.write_parquet(destino, compression="zstd")
        n = df.height
    return {"destino": destino, "n": n, "vacios": vacios, "errores": errores}


def aplanar(src: Path, dst: Path, por_lote: int = 40, hilos: int = 6,
            forzar: bool = False) -> dict:
    """Aplana todos los `<match_id>.json.gz` de `src` en `dst/part-XXXXX.parquet`."""
    src, dst = Path(src), Path(dst)
    archivos = sorted(src.glob("*.json.gz"), key=match_id_de)
    if not archivos:
        raise FileNotFoundError(f"Sin .json.gz en {src}")
    dst.mkdir(parents=True, exist_ok=True)
    viejos = list(dst.glob("part-*.parquet"))
    if viejos and not forzar:
        raise FileExistsError(
            f"{dst} ya tiene {len(viejos)} partes. Usa --forzar para rehacer: "
            "mezclar partes de dos corridas es estado inconsistente (bug #7)."
        )
    for v in viejos:
        v.unlink()

    lotes = [archivos[i:i + por_lote] for i in range(0, len(archivos), por_lote)]
    t0 = time.time()
    res = []
    # spawn, NO fork: polars es multihilo y un fork con hilos vivos se
    # congela sin error (visto en los tests). Es un bug silencioso mas.
    with ProcessPoolExecutor(max_workers=hilos, mp_context=mp.get_context("spawn")) as ex:
        futs = [
            ex.submit(_lote, [str(p) for p in lote], str(dst / f"part-{k:05d}.parquet"))
            for k, lote in enumerate(lotes)
        ]
        for i, fu in enumerate(as_completed(futs), 1):
            res.append(fu.result())
            if i % 10 == 0 or i == len(futs):
                print(f"  lotes {i}/{len(futs)}  ({time.time() - t0:.0f}s)", flush=True)

    reporte = {
        "archivos": len(archivos),
        "eventos": int(sum(r["n"] for r in res)),
        "vacios": sorted(v for r in res for v in r["vacios"]),
        "errores": sorted(e for r in res for e in r["errores"]),
        "segundos": round(time.time() - t0, 1),
    }
    return reporte
