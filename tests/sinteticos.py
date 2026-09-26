"""Liga sintética con rasgos SEMBRADOS, en el formato de `eventos.leer`.

Equipos E0..E5, un técnico cada uno (T0..T5), todos contra todos `vueltas` veces.
Rasgos sembrados:
  T0  presiona arriba: sus acciones defensivas y recuperaciones ocurren en x alta y
      recupera la pelota rápido tras perderla; sus rivales pasan menos antes de perderla.
  T1  corners peligrosos: remata en la mitad de sus corners (la liga, en 1 de cada 6).
Todo lo demás es igual entre equipos (la nula para esas métricas).
"""
from __future__ import annotations

import numpy as np
import polars as pl

EQUIPOS = [f"E{i}" for i in range(6)]
TECNICOS = {f"E{i}": f"T{i}" for i in range(6)}


def liga(vueltas: int = 4, seed: int = 0, posesiones_por_partido: int = 60) -> tuple[pl.DataFrame, pl.DataFrame]:
    rng = np.random.default_rng(seed)
    filas, tp = [], []
    mid = 0
    for v in range(vueltas):
        for a in range(6):
            for b in range(a + 1, 6):
                mid += 1
                A, B = EQUIPOS[a], EQUIPOS[b]
                fecha = f"2024-{1 + (mid // 28) % 12:02d}-{1 + mid % 28:02d}"
                for t, r in ((A, B), (B, A)):
                    tp.append({"match_id": mid, "team": t, "coach": TECNICOS[t], "rival": r,
                               "coach_rival": TECNICOS[r], "match_date": fecha, "local": t == A,
                               "elo_dif": 0.0, "season_id": 1})
                filas += _partido(mid, A, B, rng, posesiones_por_partido)
    ev = pl.DataFrame(filas, infer_schema_length=None)
    ev = ev.with_columns(pl.col("reloj").cast(pl.Float64), pl.col("x").cast(pl.Float64), pl.col("y").cast(pl.Float64),
                         pl.col("fin_x").cast(pl.Float64), pl.col("fin_y").cast(pl.Float64),
                         pl.col("shot_statsbomb_xg").cast(pl.Float64), pl.col("obv_total_net").cast(pl.Float64))
    tp_ = pl.DataFrame(tp).with_columns(pl.col("match_date").str.to_date())
    return ev.sort("match_id", "index"), tp_


def _partido(mid, A, B, rng, n_pos):
    filas, idx, reloj = [], 0, 0.0
    equipo = A

    def ev(t, tipo, x, y, **kw):
        nonlocal idx
        idx += 1
        base = {"id": f"{mid}-{idx}", "index": idx, "match_id": mid, "period": 1 if reloj < 2700 else 2,
                "minute": int(reloj // 60), "second": int(reloj % 60), "reloj": reloj, "type": tipo, "team": t,
                "possession": pos_n, "possession_team": equipo, "play_pattern": patron, "player": f"{t}-j{rng.integers(11)}",
                "player_id": int(rng.integers(11)) + 100 * EQUIPOS.index(t), "position": "Center Midfield",
                "x": float(x), "y": float(y), "fin_x": None, "fin_y": None, "pass_outcome": None, "pass_type": None,
                "pass_recipient_id": None, "shot_outcome": None, "shot_statsbomb_xg": None, "obv_total_net": 0.0,
                "under_pressure": False, "counterpress": False, "duration": 1.0}
        base.update(kw)
        filas.append(base)

    pos_n = 0
    for p in range(n_pos):
        pos_n += 1
        rival = B if equipo == A else A
        patron = "Regular Play"
        corner = rng.random() < 0.08
        if corner:
            patron = "From Corner"
            ev(equipo, "Pass", 120, 0, fin_x=110.0, fin_y=40.0, pass_type="Corner")
            reloj += 3
            p_rem = 0.5 if TECNICOS[equipo] == "T1" else 1 / 6
            if rng.random() < p_rem:
                ev(equipo, "Shot", 110, 40, fin_x=120.0, fin_y=40.0, shot_statsbomb_xg=0.1,
                   shot_outcome="Goal" if rng.random() < 0.1 else "Saved")
            reloj += 10
        else:
            x = float(rng.uniform(15, 50))
            for k in range(int(rng.integers(2, 7))):
                fx = min(118.0, x + rng.uniform(-5, 18))
                ev(equipo, "Pass", x, 40, fin_x=fx, fin_y=float(rng.uniform(10, 70)), obv_total_net=0.01)
                reloj += 3
                x = fx
            if x > 95 and rng.random() < 0.3:
                ev(equipo, "Shot", x, 40, fin_x=120.0, fin_y=40.0, shot_statsbomb_xg=0.08, shot_outcome="Saved")
                reloj += 5
            else:
                # pierde: el rival recupera. T0 recupera ARRIBA (en su marco, x alto)
                x_rec = rng.uniform(70, 100) if TECNICOS[rival] == "T0" else rng.uniform(15, 55)
                for _ in range(2):
                    ev(rival, "Duel", x_rec, 40)
                ev(rival, "Ball Recovery", x_rec, 40)
                ev(rival, "Pressure", x_rec, 40, counterpress=TECNICOS[rival] == "T0")
        reloj += 2
        # quién tiene la siguiente posesión: T0 la recupera rápido tras perderla
        siguiente = B if equipo == A else A
        if TECNICOS[equipo] == "T0" and patron == "Regular Play" and rng.random() < 0.6:
            pos_n += 1
            patron = "Regular Play"
            eq_prev = equipo
            equipo = siguiente
            ev(equipo, "Pass", 60, 40, fin_x=62.0, fin_y=40.0, pass_outcome="Incomplete")
            reloj += 2
            equipo = eq_prev                      # recuperó en ~2 s
            continue
        equipo = siguiente
    return filas
