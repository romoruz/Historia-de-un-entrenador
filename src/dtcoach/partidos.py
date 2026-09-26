"""
Partidos y entrenador por partido, directo del endpoint de partidos del API.

DOS FUENTES DE "QUIEN DIRIGIO", A PROPOSITO
-------------------------------------------
1. `data/referencia/eras_api/coach_eras_<club>.csv`: las eras VERIFICADAS del
   proyecto viejo (con interinatos absorbidos, correcciones y candado
   PRIMERA_DE_VENTANA). Son la fuente que se USA.
2. `managers` en cada partido: la fuente CRUDA del API. Se usa para
   VERIFICAR la primera. Si discrepan en un partido, se reporta; no se
   corrige en silencio (la leccion del bug #14).
"""
from __future__ import annotations

import gzip
import json
import unicodedata
from pathlib import Path

import polars as pl


def _abrir(p: Path):
    return gzip.open(p, "rt", encoding="utf-8") if p.suffix == ".gz" else open(p, encoding="utf-8")


def _filas(d) -> list[dict]:
    """El volcado puede venir como lista o como {match_id: partido}."""
    if isinstance(d, list):
        return d
    if isinstance(d, dict) and "match_id" in d:
        return [d]
    if isinstance(d, dict):
        return list(d.values())
    raise ValueError("formato de matches no reconocido")


def normaliza_nombre(s: str | None) -> str | None:
    """Sin acentos, minusculas, espacios colapsados. Para COMPARAR, no para mostrar."""
    if s is None:
        return None
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().split())


_ROMANOS = {"i", "ii", "iii", "iv", "v"}


def tokens_dt(s: str | None) -> frozenset[str]:
    """Tokens del nombre, sin acentos y sin el sufijo de etapa (I, II...).

    El sufijo lo pone el CSV de eras para separar dos etapas del mismo DT en
    un club (Moreno I / Moreno II); el API no lo tiene.
    """
    n = normaliza_nombre(s)
    if not n:
        return frozenset()
    t = n.replace(".", " ").split()
    while t and t[-1] in _ROMANOS:
        t = t[:-1]
    return frozenset(t)


def mismo_dt(era: str | None, api: str | None) -> bool:
    """Misma persona si los tokens de un nombre estan contenidos en los del otro.

    El API trae el nombre legal completo ("André Soares Jardine"); las eras,
    el de uso ("Andre Jardine"). Comparar cadenas daba 2,521 falsas
    discrepancias en la primera corrida real.
    """
    a, b = tokens_dt(era), tokens_dt(api)
    return bool(a) and bool(b) and (a <= b or b <= a)


def _dt(equipo: dict) -> tuple[str | None, int | None, int]:
    mans = equipo.get("managers") or []
    if not mans:
        return None, None, 0
    m = mans[0]
    return m.get("name"), m.get("id"), len(mans)


def leer_partidos(dir_matches: Path) -> pl.DataFrame:
    filas = []
    for f in sorted(Path(dir_matches).glob("*.json*")):
        with _abrir(f) as fh:
            for m in _filas(json.load(fh)):
                h, a = m.get("home_team") or {}, m.get("away_team") or {}
                hn, hid, hk = _dt(h)
                an, aid, ak = _dt(a)
                filas.append({
                    "match_id": int(m["match_id"]),
                    "match_date": m.get("match_date"),
                    "kick_off": m.get("kick_off"),
                    "competition_id": (m.get("competition") or {}).get("competition_id"),
                    "season_id": (m.get("season") or {}).get("season_id"),
                    "season_name": (m.get("season") or {}).get("season_name"),
                    "stage": (m.get("competition_stage") or {}).get("name"),
                    "match_week": m.get("match_week"),
                    "home_team": h.get("home_team_name"),
                    "away_team": a.get("away_team_name"),
                    "home_score": m.get("home_score"),
                    "away_score": m.get("away_score"),
                    "home_coach": hn, "home_coach_id": hid, "home_n_managers": hk,
                    "away_coach": an, "away_coach_id": aid, "away_n_managers": ak,
                    "status_360": m.get("match_status_360"),
                    "archivo": f.name,
                })
    df = pl.DataFrame(filas, infer_schema_length=None)
    dup = df.group_by("match_id").len().filter(pl.col("len") > 1)
    if dup.height:
        raise ValueError(f"match_id repetidos entre archivos de matches: {dup['match_id'].to_list()[:10]}")
    return df.with_columns(pl.col("match_date").str.to_date()).sort(["match_date", "match_id"])


def dt_por_partido(partidos: pl.DataFrame) -> pl.DataFrame:
    """Dos filas por partido: (match_id, team) con su DT según el API, localía y rival."""
    base = ["match_id", "match_date", "season_id", "stage"]
    h = partidos.select(
        *base,
        pl.col("home_team").alias("team"), pl.col("away_team").alias("rival"),
        pl.lit(True).alias("local"),
        pl.col("home_coach").alias("coach_api"), pl.col("home_coach_id").alias("coach_api_id"),
        pl.col("home_n_managers").alias("n_managers"),
        pl.col("home_score").alias("goles_favor"), pl.col("away_score").alias("goles_contra"),
    )
    a = partidos.select(
        *base,
        pl.col("away_team").alias("team"), pl.col("home_team").alias("rival"),
        pl.lit(False).alias("local"),
        pl.col("away_coach").alias("coach_api"), pl.col("away_coach_id").alias("coach_api_id"),
        pl.col("away_n_managers").alias("n_managers"),
        pl.col("away_score").alias("goles_favor"), pl.col("home_score").alias("goles_contra"),
    )
    return pl.concat([h, a]).sort(["match_date", "match_id", "team"])


def verificar_eras(mc: pl.DataFrame, dtp: pl.DataFrame) -> pl.DataFrame:
    """Partidos donde la era verificada y el `managers` del API NO coinciden.

    `mc` es la salida de `eras.match_coach_table_multi` (match_id, coach, club).
    Devuelve solo las discrepancias; vacío = las dos fuentes cuentan lo mismo.
    """
    a = mc.select("match_id", pl.col("club").alias("team"), "coach")
    j = dtp.select("match_id", "team", "match_date", "coach_api").join(
        a, on=["match_id", "team"], how="left"
    )
    iguales = [mismo_dt(a, b) for a, b in zip(j["coach"].to_list(), j["coach_api"].to_list())]
    return j.filter(~pl.Series(iguales)).sort(["team", "match_date"])
