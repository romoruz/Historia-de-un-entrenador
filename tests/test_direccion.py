"""Experimento direccional (ADR-v2-37): niveles, recodificación consistente y
validación cruzada contra una inercia sembrada (y contra su ausencia)."""
import numpy as np
import polars as pl

from dtcoach.cli import _space
from dtcoach.config import RAIZ, Config
from dtcoach.direccion import aumentar_direccion, etiquetas_direccion, nivel_direccion
from dtcoach.grid import StateSpace
from dtcoach.voronoi import comparar, conteos_marginales, pliegues_partido, puntaje_cv

SP = StateSpace(nx=5, ny=4, phases=("all",))
NZ = SP.n_zones


def test_niveles_de_direccion():
    dx, dy, z = np.array([10.0, -10.0, 1.0, 0.0]), np.array([0.0, 0.0, 5.0, 8.0]), np.zeros(4, int)
    et = etiquetas_direccion("x3:5")
    assert [et[k] for k in nivel_direccion("x3:5", dx, dy, z)] == ["adelante", "atras", "lateral", "lateral"]
    et = etiquetas_direccion("oct8")
    assert [et[k] for k in nivel_direccion("oct8", dx, dy, z)][:2] == ["adelante", "atras"]
    et = etiquetas_direccion("cuad4")
    assert [et[k] for k in nivel_direccion("cuad4", dx, dy, z)] == ["adelante", "atras", "y+", "y+"]
    assert etiquetas_direccion("previa", NZ)[0] == "inicio" and len(etiquetas_direccion("previa", NZ)) == NZ + 1


def _simular(inercia: bool, n_partidos=40, por_partido=120, seed=0):
    rng = np.random.default_rng(seed)
    filas, coords = [], []
    for m in range(n_partidos):
        ev = 0
        for p in range(por_partido):
            uid = f"{m}_{p}"
            x, y, prev = rng.uniform(10, 70), rng.uniform(5, 75), 0
            while True:
                ev += 1
                if inercia and prev == 1:
                    dx = rng.normal(14, 4)          # tras avanzar, sigue avanzando
                elif inercia and prev == -1:
                    dx = rng.normal(-8, 4)          # tras recircular, vuelve a recircular
                else:
                    dx = rng.uniform(-15, 18)
                dy = rng.uniform(-12, 12)
                x2, y2 = float(np.clip(x + dx, 0, 119.9)), float(np.clip(y + dy, 0, 79.9))
                zf, zt = int(SP.zone_of(x, y)), int(SP.zone_of(x2, y2))
                u = rng.random()
                if x2 > 100 and u < 0.25:
                    to = NZ + 1
                elif u < 0.12:
                    to = NZ + 2
                elif u < 0.14:
                    filas.append((uid, m, ev, "Pass", zf, zt))
                    coords.append((m, ev, x, y, x2, y2))
                    filas.append((uid, m, ev + 1, "TERMINAL", zt, NZ + 2))
                    ev += 1
                    break
                else:
                    to = zt
                filas.append((uid, m, ev, "Pass", zf, to))
                coords.append((m, ev, x, y, x2, y2))
                if to >= NZ:
                    break
                prev = 1 if (x2 - x) > 5 else (-1 if (x2 - x) < -5 else 0)
                x, y = x2, y2
    t = pl.DataFrame(filas, schema={"seq_uid": pl.Utf8, "match_id": pl.Int64, "event_index": pl.Int64,
                                    "action_type": pl.Utf8, "from_state": pl.Int64, "to_state": pl.Int64},
                     orient="row").with_columns(pl.col("seq_uid").alias("poss_uid"))
    c = pl.DataFrame(coords, schema={"match_id": pl.Int64, "event_index": pl.Int64, "start_x": pl.Float64,
                                     "start_y": pl.Float64, "end_x": pl.Float64, "end_y": pl.Float64},
                     orient="row")
    return t, c


def test_recodificacion_consistente():
    t, c = _simular(True, n_partidos=3, por_partido=30)
    a, diag = aumentar_direccion(t, c, "x3:5", SP)
    L = diag["L"]
    assert L == 4 and a.height == t.height and diag["frac_destino_sin_coordenadas"] == 0
    a, o = a.sort(["seq_uid", "event_index"]), t.sort(["seq_uid", "event_index"])
    fr, to, uid = a["from_state"].to_numpy(), a["to_state"].to_numpy(), a["seq_uid"].to_numpy()
    primero = np.r_[True, uid[1:] != uid[:-1]]
    assert ((fr % L)[primero] == 0).all() and ((fr % L)[~primero] > 0).all()     # inicio solo al arrancar
    assert ((fr // L) == o["from_state"].to_numpy()).all()                       # la zona no cambia
    sigue = ~primero[1:]
    assert (to[:-1][sigue] == fr[1:][sigue]).all()                               # destino(t) = origen(t+1)
    nt = NZ * L
    ab = o["to_state"].to_numpy() >= NZ
    assert (to[ab] == o["to_state"].to_numpy()[ab] - NZ + nt).all()
    assert (to[~ab] % L > 0).all()                                               # nadie vuelve a "inicio"


def _cv(inercia):
    t, c = _simular(inercia)
    folds = pliegues_partido(t["match_id"].to_numpy(), 5, 0)
    res = {"base:1": puntaje_cv(conteos_marginales(t, NZ, 1, folds), NZ, [1, 10, 100])}
    for cand in ("x3:5", "oct8", "previa"):
        tk, dk = aumentar_direccion(t, c, cand, SP)
        res[cand] = puntaje_cv(conteos_marginales(tk, NZ, dk["L"], folds), NZ, [1, 10, 100, 1000])
    return comparar({k: v for k, v in res.items() if k != "previa"}), res


def test_cv_detecta_la_inercia_sembrada():
    (elegido, tab), res = _cv(True)
    assert elegido == "x3:5"                                  # la regla con la que se sembró, y la más simple
    assert tab.filter(pl.col("candidato") == "x3:5")["mejora"][0]
    g = res["x3:5"]["score"] - res["base:1"]["score"]
    assert g > res["previa"]["score"] - res["base:1"]["score"]   # coordenadas exactas > zona anterior gruesa


def test_cv_no_inventa_inercia():
    # sin inercia, la zona anterior aún informa algo (la zona es gruesa: dónde dentro de la celda);
    # lo que se exige es que la DIRECCIÓN no gane casi nada
    _, res = _cv(False)
    g = {k: res[k]["score"] - res["base:1"]["score"] for k in ("x3:5", "oct8")}
    t_con = _cv(True)[1]
    assert max(g.values()) < 0.2 * (t_con["x3:5"]["score"] - t_con["base:1"]["score"])


def test_config_direccion():
    c = Config.load(RAIZ / "config" / "direccion.yaml")
    base = Config.load()
    assert c["direccion"]["activo"] and not base["direccion"]["activo"]
    assert c.ruta("transiciones") != base.ruta("transiciones")
    sp = _space(c)
    assert sp.phases[0] == "inicio" and sp.n_transient == sp.n_zones * len(sp.phases)


def test_contrato_con_la_extraccion_real(dir_eventos, tmp_path, cfg, space):
    """Las coordenadas salen de la MISMA extracción que las transiciones: toda acción
    con destino transitorio encuentra su inicio y su fin."""
    from dtcoach import ingest
    from dtcoach.aplanar import aplanar
    from dtcoach.direccion import coordenadas
    from dtcoach.possessions import build_transitions
    aplanar(dir_eventos, tmp_path / "out", por_lote=1, hilos=1)
    lf = ingest.load(tmp_path / "out")
    tr = build_transitions(lf, space, cfg)
    a, diag = aumentar_direccion(tr, coordenadas(lf, cfg), "x3:5", space)
    assert diag["frac_destino_sin_coordenadas"] == 0 and a.height == tr.height
    p1 = a.filter(pl.col("poss_uid") == "111_1").sort("event_index")
    # pase 20→50 (adelante), conducción 50→80 (adelante), pase 80→105 (adelante), remate
    assert p1["phase"].to_list() == ["inicio", "adelante", "adelante", "adelante"]


def test_direccion_con_zona_previa_para_la_memoria_residual():
    et = etiquetas_direccion("x3:5+previa", NZ)
    assert len(et) == 1 + 3 * NZ and et[0] == "inicio"
    lv = nivel_direccion("x3:5+previa", np.array([10.0, -10.0]), np.zeros(2), np.array([7, 19]), NZ)
    assert [et[k] for k in lv] == ["adelante|de_z7", "atras|de_z19"]
