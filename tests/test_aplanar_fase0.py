"""De JSON crudo a transiciones: el contrato entre aplanar, ingest y possessions."""
import json

import polars as pl

from dtcoach import ingest
from dtcoach.aplanar import aplanar
from dtcoach.possessions import build_transitions


def test_aplanar_esquema_y_json(dir_eventos, tmp_path):
    rep = aplanar(dir_eventos, tmp_path / "out", por_lote=1, hilos=1)
    assert rep["archivos"] == 2 and rep["eventos"] == 20 and not rep["errores"]
    df = pl.read_parquet(tmp_path / "out")
    assert set(df["match_id"].unique().to_list()) == {111, 222}
    assert df.schema["location"] == pl.List(pl.Float64)
    # el entero [80, 30] del JSON se lee como float
    assert df.filter(pl.col("index") == 5)["location"][0].to_list() == [80.0, 30.0]
    ff = df.filter(pl.col("type") == "Shot")["shot_freeze_frame"][0]
    assert '"teammate": false' in ff and json.loads(ff)[0]["teammate"] is False   # bug #21
    assert df.filter(pl.col("type") == "Starting XI")["tactics_formation"][0] == 433
    # bandera: omitida -> False, no null
    assert df["under_pressure"].null_count() == 0
    assert df["under_pressure"].sum() == 2


def test_no_mezcla_corridas(dir_eventos, tmp_path):
    aplanar(dir_eventos, tmp_path / "out", por_lote=1, hilos=1)
    try:
        aplanar(dir_eventos, tmp_path / "out", por_lote=1, hilos=1)
        raise AssertionError("debió negarse a mezclar corridas")
    except FileExistsError:
        pass
    aplanar(dir_eventos, tmp_path / "out", por_lote=1, hilos=1, forzar=True)


def test_transiciones_de_liga(dir_eventos, tmp_path, cfg, space):
    aplanar(dir_eventos, tmp_path / "out", por_lote=1, hilos=1)
    tr = build_transitions(ingest.load(tmp_path / "out"), space, cfg)
    goal, loss = space.absorbing_index("GOAL"), space.absorbing_index("LOSS")
    assert space.n_transient == 20
    p1 = tr.filter(pl.col("poss_uid") == "111_1").sort("event_index")
    assert p1.height == 4 and p1["to_state"][-1] == goal
    assert abs(p1["xg"].drop_nulls().sum() - 0.3) < 1e-12
    assert p1["score_state"].unique().to_list() == ["drawing"]      # el gol no se autoexplica
    p2 = tr.filter(pl.col("poss_uid") == "111_2")
    assert p2["score_state"].unique().to_list() == ["losing"]
    assert p2["to_state"][-1] == loss and p2["play_pattern"][0] == "From Kick Off"
    p3 = tr.filter(pl.col("poss_uid") == "111_3").sort("event_index")
    assert p3.height == 3 and p3["action_type"][-1] == "TERMINAL" and p3["to_state"][-1] == loss
    assert p3["xg"].null_count() == 3
    assert tr["poss_uid"].n_unique() == 6


def test_envoltorios_conocidos():
    from dtcoach.aplanar import eventos_de
    ev = [{"type": {"name": "Pass"}, "id": "a"}]
    assert eventos_de(ev) == ev
    assert eventos_de({"events": ev}) == ev
    assert eventos_de({"match_id": 1, "data": ev}) == ev
    assert eventos_de({"a": ev[0]}) == ev
    try:
        eventos_de({"raro": 1}, "x.json.gz")
        raise AssertionError("debió fallar")
    except ValueError as e:
        assert "raro" in str(e)


def test_segmentar_secuencias_corta_en_cada_absorcion():
    from dtcoach.possessions import segmentar_secuencias
    # posesión 1: pase, remate atajado, córner a favor, conducción, TERMINAL
    t = pl.DataFrame({
        "poss_uid": ["m_1"] * 5 + ["m_2"] * 2,
        "event_index": [1, 2, 3, 4, 5, 10, 11],
        "is_absorbing": [False, True, False, False, True, False, True],
    })
    s = segmentar_secuencias(t)
    assert s["seq_uid"].to_list() == ["m_1_s0", "m_1_s0", "m_1_s1", "m_1_s1", "m_1_s1", "m_2_s0", "m_2_s0"]
    # cada secuencia termina en exactamente UNA absorción, y es su última fila
    g = s.group_by("seq_uid").agg(pl.col("is_absorbing").sum().alias("a"), pl.col("is_absorbing").last().alias("u"))
    assert g["a"].to_list() == [1] * g.height and all(g["u"])


def test_fase0_trae_secuencias(dir_eventos, tmp_path, cfg, space):
    aplanar(dir_eventos, tmp_path / "out", por_lote=1, hilos=1)
    tr = build_transitions(ingest.load(tmp_path / "out"), space, cfg)
    g = tr.group_by("seq_uid").agg(pl.col("is_absorbing").sum().alias("a"))
    assert (g["a"] == 1).all()
