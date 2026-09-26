import gzip
import json
from pathlib import Path

import pytest

from dtcoach.config import Config
from dtcoach.grid import StateSpace


@pytest.fixture
def cfg():
    return Config.load()


@pytest.fixture
def space(cfg):
    """Malla FIJA 5×4 para las pruebas: el pipeline cambia config.pitch (mallado --aplicar,
    vocabulario.sh) y las pruebas no pueden depender de un valor que cambia."""
    return StateSpace(nx=5, ny=4, phases=tuple(cfg["phase_order"]))


def _ev(i, poss, team, ptype, pattern, loc=None, **kw):
    e = {"id": f"e{i}", "index": i, "period": 1, "timestamp": "00:00:01.000",
         "minute": i, "second": 0, "type": {"id": 0, "name": ptype},
         "possession": poss, "possession_team": {"id": 1 if team == "A" else 2, "name": team},
         "play_pattern": {"id": 1, "name": pattern},
         "team": {"id": 1 if team == "A" else 2, "name": team},
         "player": {"id": 10 if team == "A" else 20, "name": f"J{team}"},
         "position": {"id": 1, "name": "Center Forward"}}
    if loc is not None:
        e["location"] = loc
    e.update(kw)
    return e


def partido_sintetico():
    """3 posesiones: A marca, B pierde el balón, A muere en transitorio."""
    return [
        _ev(1, 1, "A", "Starting XI", "Regular Play",
            tactics={"formation": 433, "lineup": [{"player": {"id": 10}, "jersey_number": 9}]}),
        _ev(2, 1, "A", "Pass", "Regular Play", [20.0, 40.0], **{"pass": {"end_location": [50.0, 40.0]}}),
        _ev(3, 1, "A", "Ball Receipt*", "Regular Play", [50.0, 40.0]),
        _ev(4, 1, "A", "Carry", "Regular Play", [50.0, 40.0], carry={"end_location": [80.0, 30.0]}),
        _ev(5, 1, "A", "Pass", "Regular Play", [80, 30], under_pressure=True,
            **{"pass": {"end_location": [105.0, 40.0]}}),
        _ev(6, 1, "A", "Shot", "Regular Play", [105.0, 40.0],
            shot={"end_location": [120.0, 40.0, 1.0], "outcome": {"name": "Goal"},
                  "statsbomb_xg": 0.3,
                  "freeze_frame": [{"location": [110.0, 40.0], "teammate": False,
                                    "player": {"id": 20}, "position": {"name": "Goalkeeper"}}]}),
        _ev(7, 2, "B", "Pass", "From Kick Off", [60.0, 40.0], **{"pass": {"end_location": [40.0, 20.0]}}),
        _ev(8, 2, "B", "Pass", "From Kick Off", [40.0, 20.0],
            **{"pass": {"end_location": [70.0, 10.0], "outcome": {"name": "Incomplete"}}}),
        _ev(9, 3, "A", "Pass", "Regular Play", [30.0, 40.0], **{"pass": {"end_location": [45.0, 60.0]}}),
        _ev(10, 3, "A", "Carry", "Regular Play", [45.0, 60.0], carry={"end_location": [50.0, 62.0]}),
    ]


@pytest.fixture
def dir_eventos(tmp_path) -> Path:
    d = tmp_path / "events"
    d.mkdir()
    for mid in (111, 222):
        with gzip.open(d / f"{mid}.json.gz", "wt", encoding="utf-8") as f:
            json.dump(partido_sintetico(), f)
    return d
