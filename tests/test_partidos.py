import gzip
import json

import polars as pl

from dtcoach.partidos import dt_por_partido, leer_partidos, normaliza_nombre, verificar_eras


def _m(mid, fecha, h, a, dh, da):
    return {"match_id": mid, "match_date": fecha, "kick_off": "19:00:00.000",
            "competition": {"competition_id": 73}, "season": {"season_id": 1, "season_name": "2024/2025"},
            "competition_stage": {"name": "Regular Season"}, "match_week": 1,
            "home_team": {"home_team_name": h, "managers": [{"id": 1, "name": dh}]},
            "away_team": {"away_team_name": a, "managers": [{"id": 2, "name": da}]},
            "home_score": 2, "away_score": 1, "match_status_360": "available"}


def test_partidos_y_verificacion(tmp_path):
    d = tmp_path / "matches"
    d.mkdir()
    datos = {"10": _m(10, "2024-08-01", "América", "Toluca", "André Jardine", "Renato Paiva"),
             "11": _m(11, "2024-08-08", "Toluca", "América", "Renato Paiva", "André Jardine")}
    with gzip.open(d / "73_1.json.gz", "wt", encoding="utf-8") as f:
        json.dump(datos, f)
    p = leer_partidos(d)
    assert p.height == 2 and p.schema["match_date"] == pl.Date
    dtp = dt_por_partido(p)
    assert dtp.height == 4
    am = dtp.filter((pl.col("match_id") == 10) & (pl.col("team") == "América"))
    assert am["local"][0] and am["goles_favor"][0] == 2 and am["rival"][0] == "Toluca"
    # la era verificada escribe sin acento: NO es discrepancia
    mc = pl.DataFrame({"match_id": [10, 11, 10, 11], "club": ["América", "América", "Toluca", "Toluca"],
                       "coach": ["Andre Jardine", "Andre Jardine", "Renato Paiva", "Otro DT"]})
    v = verificar_eras(mc, dtp)
    assert v.height == 1 and v["match_id"][0] == 11 and v["team"][0] == "Toluca"
    assert normaliza_nombre("  André   JARDINE ") == "andre jardine"


def test_mismo_dt_por_tokens():
    from dtcoach.partidos import mismo_dt
    assert mismo_dt("Andre Jardine", "André Soares Jardine")
    assert mismo_dt("Joaquin Moreno Garduno II", "Joaquín Moreno Garduño")
    assert mismo_dt("Efrain Valdez", "Efraín Juárez Váldez")
    assert not mismo_dt("Miguel Herrera", "Robert Dante Siboldi Badiola")
    assert not mismo_dt(None, "Alguien")
