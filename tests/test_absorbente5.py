"""El quinto absorbente INTERRUPCIÓN_FAVOR integrado (variante (ii), ADR-v2-72): solo cambia el destino de la última
transición; el valor de la reanudación va en `valor_reanudacion` y el xG por secuencia (H7–H8) queda IDÉNTICO."""
import numpy as np
import polars as pl

from dtcoach import absorbente5 as ab
from dtcoach.grid import StateSpace
from dtcoach.mezcla import DatosPosesion, ajustar, responsabilidades, resumen_tipos

SP = StateSpace(nx=2, ny=2, phases=("all",))            # 4 zonas; GOAL 4, SHOT 5, LOSS 6, OUT 7, INTERRUPCIÓN 8
GOAL, SHOT, LOSS, OUT = (SP.absorbing_index(a) for a in ("GOAL", "SHOT_NOGOAL", "LOSS", "OUT"))
INT = SP.absorbing_index(ab.INTERRUPCION)


def _liga(rep: int = 30):
    """`rep` partidos iguales. Por partido: a) termina (TERMINAL) y el mismo equipo saca un córner, que abre la
    secuencia d (remate 0.3); b) pierde y el rival juega; c) pierde, le hacen falta y saca un tiro libre, que abre la
    secuencia e (xG 0.05 y fuera)."""
    tr, ev = [], []
    for m in range(rep):
        tr += [(m, "a", "X", 1, 0, 1, None, "Pass"), (m, "a", "X", 2, 1, LOSS, None, "TERMINAL"),
               (m, "b", "X", 10, 2, LOSS, None, "Pass"),
               (m, "c", "X", 20, 3, LOSS, None, "Pass"),
               (m, "d", "X", 4, 3, 2, None, "Pass"), (m, "d", "X", 5, 2, SHOT, 0.3, "Shot"),
               (m, "e", "X", 22, 1, OUT, 0.05, "Pass")]
        ev += [(m, 1, "Pass", "X", None, None, [10.0, 10.0]), (m, 4, "Pass", "X", "Corner", None, [119.0, 79.0]),
               (m, 5, "Shot", "X", None, None, [110.0, 40.0]), (m, 10, "Pass", "X", None, None, [70.0, 10.0]),
               (m, 11, "Pass", "Y", None, None, [50.0, 40.0]), (m, 20, "Pass", "X", None, None, [80.0, 60.0]),
               (m, 21, "Foul Won", "X", None, None, [90.0, 50.0]),
               (m, 22, "Pass", "X", "Free Kick", None, [90.0, 50.0])]
    trans = pl.DataFrame(tr, schema={"match_id": pl.Int64, "uid": pl.Utf8, "team": pl.Utf8, "event_index": pl.Int64,
                                     "from_state": pl.Int64, "to_state": pl.Int64, "xg": pl.Float64,
                                     "action_type": pl.Utf8}, orient="row")
    trans = trans.with_columns((pl.col("match_id").cast(pl.Utf8) + "_" + pl.col("uid")).alias("seq_uid")).drop("uid")
    ev = pl.DataFrame(ev, schema={"match_id": pl.Int64, "index": pl.Int64, "type": pl.Utf8, "team": pl.Utf8,
                                  "pass_type": pl.Utf8, "shot_type": pl.Utf8, "location": pl.List(pl.Float64)},
                      orient="row")
    return trans, ev


def test_integrar_solo_cambia_el_destino_final():
    trans, ev = _liga()
    out, res = ab.integrar(trans, ev, SP)
    assert out.height == trans.height and out.columns == trans.columns + ["valor_reanudacion"]
    j = trans.join(out, on=["seq_uid", "event_index"], suffix="_n")
    cambia = j.filter(pl.col("to_state") != pl.col("to_state_n"))
    # a (córner) y c (falta + tiro libre) pasan a INTERRUPCIÓN; b (el rival juega) se queda en PÉRDIDA
    assert sorted(set(s.split("_")[1] for s in cambia["seq_uid"])) == ["a", "c"]
    assert (cambia["to_state"] == LOSS).all() and (cambia["to_state_n"] == INT).all()
    assert res["a_interrupcion"] == 60 and res["secuencias_perdida_antes"] == 90
    # el xG no se toca; el valor solo en la transición reclasificada, y vale lo que vale la reanudación
    assert np.array_equal(j["xg"].fill_null(-1).to_numpy(), j["xg_n"].fill_null(-1).to_numpy())
    v = j.with_columns(pl.col("seq_uid").str.split("_").list.get(1).alias("s"))
    assert (v.filter(pl.col("to_state_n") != INT)["valor_reanudacion"] == 0).all()
    va = v.filter((pl.col("s") == "a") & (pl.col("to_state_n") == INT))["valor_reanudacion"]
    vc = v.filter((pl.col("s") == "c") & (pl.col("to_state_n") == INT))["valor_reanudacion"]
    assert np.allclose(va.to_numpy(), 0.3) and np.allclose(vc.to_numpy(), 0.05)      # 30 iguales: el encogimiento no mueve
    # el inverso devuelve exactamente lo de antes
    back = ab.a_cuatro(out, SP)
    assert back["to_state"].to_list() == trans["to_state"].to_list() and "valor_reanudacion" not in back.columns


def test_xg_por_secuencia_identico_antes_y_despues():
    """La prueba que exige ADR-v2-72: el xG por secuencia de H7–H8 (contexto.tabla_secuencias lo lee de d.X) es
    IDÉNTICO con y sin el quinto absorbente; el valor de la reanudación solo aparece en V = N c."""
    trans, ev = _liga()
    out, _ = ab.integrar(trans, ev, SP)
    d4 = DatosPosesion.desde_transiciones(ab.a_cuatro(out, SP), ab.espacio4(SP))
    d5 = DatosPosesion.desde_transiciones(out, SP)
    assert d4.meta["seq_uid"].to_list() == d5.meta["seq_uid"].to_list()
    xg4, xg5 = np.asarray(d4.X.sum(axis=1)).ravel(), np.asarray(d5.X.sum(axis=1)).ravel()
    assert np.array_equal(xg4, xg5)                                          # bit a bit
    assert (d4.X != d5.X).nnz == 0 and (d4.X0 != d5.X0).nnz == 0
    assert d4.XV is None and d5.XV is not None and d5.XV.sum() > 0
    # resumen de tipos: el xG por posesión (modelo y empírico) no ve la reanudación; el valor sí
    m = ajustar(d5, 1, lam=1.0, paso_inicial=True)
    t = resumen_tipos(m, d5, responsabilidades(m, d5))[0]
    assert abs(t["xG_por_posesion_empirico"] - xg5.mean()) < 1e-12
    assert t["valor_por_posesion_modelo"] > t["xG_por_posesion_modelo"] and "P_interrupcion_favor" in t


def test_sin_puesto_cuando_tau2_es_cero():
    """Con τ² = 0 todos los contraídos empatan y el puesto es arbitrario: se imprime un guion, no un número."""
    from dtcoach.cli_historia import _md_etapa
    E = pl.DataFrame({"coach": ["A", "B", "C"], "team": ["x", "y", "z"], "theta": [0.1, 0.2, 0.3], "var": [1.0] * 3,
                      "contraido": [0.2] * 3, "confiabilidad": [0.0] * 3, "mu": [0.2] * 3, "tau2": [0.0] * 3})
    txt = "\n".join(_md_etapa(E, "B", "t", "u"))
    assert "puesto: —" in txt and "de 3" not in txt
    txt = "\n".join(_md_etapa(E.with_columns(pl.lit(0.5).alias("tau2")), "B", "t", "u"))
    assert "puesto 2 de 3" in txt
