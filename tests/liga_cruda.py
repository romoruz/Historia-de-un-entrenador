"""Liga SINTÉTICA en el formato CRUDO de StatsBomb (eventos, partidos, 360) y eras, para correr
el pipeline completo de punta a punta (tests/test_integral.py).

8 equipos, `temporadas` temporadas a doble vuelta. El técnico foco ("Guillermo Prueba") llega a
Tuzos en la temporada 1 y se va a Águilas en la 2 (su "club actual", el de la proyección).
Rasgos sembrados del foco: presiona encima (defensor más cerca del que toca el balón), bloque
más estrecho, sale largo, y sus equipos despejan más corners en contra.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
from pathlib import Path

import numpy as np

EQUIPOS = ["Águilas", "Rayados", "Tuzos", "Diablos", "Gallos", "Pumas", "Tigres", "Xolos"]
FOCO = "Guillermo Prueba"
PUESTOS = ["Goalkeeper", "Right Back", "Right Center Back", "Left Center Back", "Left Back",
           "Right Defensive Midfield", "Left Defensive Midfield", "Right Wing", "Center Attacking Midfield",
           "Left Wing", "Center Forward"]
BANCA = ["Center Forward", "Right Wing", "Left Back", "Right Defensive Midfield", "Center Back"]


def tecnicos(temporadas: int) -> dict:
    """(equipo, temporada) → técnico."""
    t = {}
    for s in range(temporadas):
        for e in EQUIPOS:
            t[(e, s)] = f"Técnico {e} {'AB'[min(s, 1)]}" if e in ("Rayados", "Gallos") else f"Técnico {e}"
        t[("Tuzos", s)] = "Técnico Tuzos" if s == 0 else (FOCO if s == 1 else "Técnico Tuzos Nuevo")
        t[("Águilas", s)] = FOCO if s >= 2 else "Técnico Águilas"
    return t


class _Partido:
    def __init__(self, mid, local, visita, coach, rng, jugadores):
        self.mid, self.rng = mid, rng
        self.eq = (local, visita)
        self.coach = coach
        self.jug = jugadores
        self.ev, self.fr = [], []
        self.i, self.poss, self.t = 0, 0, 0.0
        self.goles = {local: 0, visita: 0}
        self.cancha = {e: list(jugadores[e][:11]) for e in self.eq}

    # ------------------------------------------------------------------
    def _base(self, tipo, team, loc=None, patron="Regular Play", pteam=None, jugador=None, **kw):
        self.i += 1
        per = 1 if self.t < 2700 else 2
        m, s = int(self.t // 60), int(self.t % 60)
        pid = jugador if jugador is not None else self.rng.choice(self.cancha[team][1:])
        e = {"id": f"{self.mid}-{self.i}", "index": self.i, "period": per,
             "timestamp": f"00:{m % 45:02d}:{s:02d}.000", "minute": m, "second": s,
             "type": {"id": 1, "name": tipo}, "possession": self.poss,
             "possession_team": {"id": EQUIPOS.index(pteam or team) + 1, "name": pteam or team},
             "play_pattern": {"id": 1, "name": patron}, "team": {"id": EQUIPOS.index(team) + 1, "name": team},
             "player": {"id": int(pid), "name": f"Jugador {pid}"},
             "position": {"id": 1, "name": PUESTOS[int(pid) % 11]}, "duration": 1.0,
             "obv_total_net": float(self.rng.normal(0.002, 0.01))}
        if loc is not None:
            e["location"] = [float(loc[0]), float(loc[1])]
        e.update(kw)
        self.ev.append(e)
        self.t += float(self.rng.uniform(1.5, 4.0))
        return e

    def _frame(self, e, team, rival, sp=False):
        """Frame 360 del evento: actor, compañeros, rivales y portero rival."""
        rng = self.rng
        x, y = e["location"]
        foco_def = self.coach[rival] == FOCO
        d0 = rng.exponential(1.6 if foco_def else 2.8) + 0.3
        ang = rng.uniform(0, 2 * np.pi)
        ff = [{"teammate": True, "actor": True, "keeper": False, "location": [x, y]}]
        for _ in range(4):
            ff.append({"teammate": True, "actor": False, "keeper": False,
                       "location": [float(np.clip(x + rng.normal(0, 12), 0, 120)),
                                    float(np.clip(y + rng.normal(0, 15), 0, 80))]})
        ancho = 0.75 if foco_def else 1.0
        rivales = [[x + d0 * np.cos(ang), y + d0 * np.sin(ang)]]
        for k in range(7):
            rivales.append([float(np.clip(x + rng.normal(8, 10), 0, 119)),
                            float(np.clip(40 + ancho * rng.normal(0, 14), 0, 80))])
        if sp:           # saque a balón parado: gente en el área
            rivales = [[float(rng.uniform(104, 119)), float(rng.uniform(26, 54))] for _ in range(8)]
            for k in range(1, 5):
                ff[k]["location"] = [float(rng.uniform(104, 118)), float(rng.uniform(28, 52))]
        for p in rivales:
            ff.append({"teammate": False, "actor": False, "keeper": False,
                       "location": [float(np.clip(p[0], 0, 120)), float(np.clip(p[1], 0, 80))]})
        ff.append({"teammate": False, "actor": False, "keeper": True, "location": [119.0, 40.0]})
        x0, x1 = max(0.0, x - 40), min(120.0, x + 40)
        w = rng.uniform(55, 80)
        va = [x0, 40 - w / 2, x1, 40 - w / 2, x1, 40 + w / 2, x0, 40 + w / 2, x0, 40 - w / 2]
        self.fr.append({"event_uuid": e["id"], "visible_area": va, "freeze_frame": ff})

    def _remate(self, team, rival, x, y, patron, tipo="Open Play", cabeza=False, clave=None):
        d = float(np.hypot(120 - x, 40 - y))
        xg = float(np.clip(0.6 * np.exp(-d / 9), 0.01, 0.8))
        gol = self.rng.random() < xg
        ff = [{"location": [float(min(119, x + self.rng.uniform(1, 8))), float(40 + self.rng.normal(0, 5))],
               "teammate": False, "player": {"id": 1}, "position": {"name": "Center Back"}} for _ in range(4)]
        ff.append({"location": [119.0, 40.0], "teammate": False, "player": {"id": 2},
                   "position": {"name": "Goalkeeper"}})
        shot = {"statsbomb_xg": xg, "outcome": {"name": "Goal" if gol else "Saved"}, "end_location": [120, 40, 1],
                "type": {"name": tipo}, "body_part": {"name": "Head" if cabeza else "Right Foot"},
                "freeze_frame": ff}
        if self.rng.random() < 0.3:
            shot["first_time"] = True
        if clave:
            shot["key_pass_id"] = clave
        e = self._base("Shot", team, (x, y), patron, shot=shot)
        self._frame(e, team, rival)
        if gol:
            self.goles[team] += 1
        return gol

    # ------------------------------------------------------------------
    def jugar(self):
        rng = self.rng
        for e in self.eq:
            lineup = [{"player": {"id": int(p), "name": f"Jugador {p}"}, "position": {"id": k, "name": PUESTOS[k]},
                      "jersey_number": k + 1} for k, p in enumerate(self.cancha[e])]
            self._base("Starting XI", e, None, jugador=self.cancha[e][0], tactics={"formation": 4231,
                                                                                    "lineup": lineup})
        ataca = self.eq[0]
        patron = "From Kick Off"
        cambios = {e: sorted(rng.choice(np.arange(55, 85), 3, replace=False).tolist()) for e in self.eq}
        while self.t < 5400:
            self.poss += 1
            rival = self.eq[1] if ataca == self.eq[0] else self.eq[0]
            # sustituciones del 2º tiempo
            for e in self.eq:
                while cambios[e] and self.t / 60 >= cambios[e][0]:
                    cambios[e].pop(0)
                    sale = self.cancha[e][rng.integers(1, 11)]
                    entra = next((p for p in self.jug[e][11:] if p not in self.cancha[e]), None)
                    if entra is None:
                        break
                    self._base("Substitution", e, None, pteam=ataca, jugador=sale,
                               substitution={"replacement": {"id": int(entra), "name": f"Jugador {entra}"},
                                             "outcome": {"name": "Tactical"}})
                    self.cancha[e][self.cancha[e].index(sale)] = entra
                    if rng.random() < 0.3:
                        self._base("Tactical Shift", e, None, pteam=ataca, tactics={"formation": 442})
            gol = self._posesion(ataca, rival, patron)
            if gol:
                patron = "From Kick Off"
                ataca = rival
            else:
                r = rng.random()
                patron = ("From Corner" if r < 0.07 else "From Free Kick" if r < 0.12 else
                          "From Throw In" if r < 0.27 else "From Goal Kick" if r < 0.33 else "Regular Play")
                ataca = rival if patron in ("Regular Play", "From Goal Kick") or rng.random() < 0.5 else ataca
        return self.ev, self.fr

    def _posesion(self, team, rival, patron) -> bool:
        rng = self.rng
        directo = self.coach[team] == FOCO
        if patron == "From Kick Off":
            self._base("Pass", team, (60, 40), patron, **{"pass": {"end_location": [45, 40], "type":
                                                                     {"name": "Kick Off"}}})
            x, y = 45.0, 40.0
        elif patron == "From Corner":
            y0 = 0.1 if rng.random() < 0.5 else 79.9
            tec = "Inswinging" if rng.random() < 0.5 else "Outswinging"
            fin = [float(rng.uniform(104, 118)), float(rng.uniform(30, 50))]
            e = self._base("Pass", team, (119.9, y0), patron, **{"pass": {"end_location": fin, "type": {"name": "Corner"},
                                                                          "technique": {"name": tec},
                                                                          "height": {"name": "High Pass"}}})
            self._frame(e, team, rival, sp=True)
            despeja = 0.75 if self.coach[rival] == FOCO else 0.5
            if rng.random() < despeja:
                self._base("Clearance", rival, (120 - fin[0], 80 - fin[1]), patron, pteam=team,
                           clearance={"aerial_won": True})
                return False
            return self._remate(team, rival, fin[0], fin[1], patron, cabeza=True, clave=e["id"])
        elif patron == "From Free Kick":
            x0, y0 = float(rng.uniform(60, 95)), float(rng.uniform(5, 75))
            if x0 > 85 and rng.random() < 0.3:
                return self._remate(team, rival, x0, y0, patron, tipo="Free Kick")
            al_area = rng.random() < 0.6
            fin = [float(rng.uniform(104, 116)), float(rng.uniform(25, 55))] if al_area else [x0 + 5, y0]
            fuera = rng.random() < (0.25 if self.coach[rival] == FOCO else 0.08)
            p = {"end_location": fin, "type": {"name": "Free Kick"}}
            if fuera:
                p["outcome"] = {"name": "Pass Offside"}
            e = self._base("Pass", team, (x0, y0), patron, **{"pass": p})
            self._frame(e, team, rival, sp=True)
            if fuera:
                return False
            if al_area and rng.random() < 0.3:
                return self._remate(team, rival, fin[0], fin[1], patron, cabeza=True, clave=e["id"])
            x, y = fin
        elif patron == "From Throw In":
            x0 = float(rng.uniform(20, 110))
            y0 = 0.1 if rng.random() < 0.5 else 79.9
            largo = x0 > 85 and rng.random() < 0.4
            fin = [float(rng.uniform(104, 114)), float(rng.uniform(30, 50))] if largo else [x0 + 3, 12 if y0 < 1 else 68]
            e = self._base("Pass", team, (x0, y0), patron, **{"pass": {"end_location": fin, "type": {"name": "Throw-in"}}})
            if largo:
                self._frame(e, team, rival, sp=True)
                if rng.random() < 0.25:
                    return self._remate(team, rival, fin[0], fin[1], patron, cabeza=True, clave=e["id"])
                return False
            x, y = fin
        elif patron == "From Goal Kick":
            largo = 60.0 if (directo or rng.random() < 0.5) else 20.0
            self._base("Pass", team, (6, 40), patron, **{"pass": {"end_location": [6 + largo, 40],
                                                                   "type": {"name": "Goal Kick"}}})
            x, y = 6 + largo, 40.0
        else:
            x, y = float(rng.uniform(15, 55)), float(rng.uniform(10, 70))
        ultimo = None
        for _ in range(int(rng.integers(2, 8))):
            paso = rng.uniform(4, 22 if directo else 14)
            fx, fy = float(min(118, x + paso)), float(np.clip(y + rng.normal(0, 12), 1, 79))
            falla = rng.random() < 0.18
            pr_ = {"end_location": [fx, fy], "recipient": {"id": int(rng.choice(self.cancha[team][1:]))}}
            if (y < 18 or y > 62) and x > 80 and 18 < fy < 62 and fx > 102:
                pr_["cross"] = True
            if rng.random() < 0.05:
                pr_["through_ball"] = True
            if falla:
                pr_["outcome"] = {"name": "Incomplete"}
            if rng.random() < 0.25:
                self._base("Pressure", rival, (120 - x, 80 - y), patron, pteam=team)
            e = self._base("Pass", team, (x, y), patron, under_pressure=bool(rng.random() < 0.2), **{"pass": pr_})
            self._frame(e, team, rival)
            if falla:
                self._base("Ball Recovery", rival, (120 - fx, 80 - fy), patron, pteam=team)
                return False
            ultimo = e
            x, y = fx, fy
            if rng.random() < 0.4:
                cx = float(min(119, x + rng.uniform(2, 10)))
                c = self._base("Carry", team, (x, y), patron, carry={"end_location": [cx, y]})
                self._frame(c, team, rival)
                x = cx
            if x > 95:
                break
        if x > 88 and rng.random() < 0.5:
            if ultimo is not None:
                ultimo["pass"]["shot_assist"] = True
            return self._remate(team, rival, x, y, patron, clave=ultimo["id"] if ultimo else None)
        self._base("Interception", rival, (120 - x, 80 - y), patron, pteam=team)
        return False


def generar(raiz: Path, eras_dir: Path, temporadas: int = 3, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    for d in ("events", "matches", "frames"):
        (raiz / d).mkdir(parents=True, exist_ok=True)
    eras_dir.mkdir(parents=True, exist_ok=True)
    tec = tecnicos(temporadas)
    jugadores = {e: list(range(1000 * (k + 1), 1000 * (k + 1) + 16)) for k, e in enumerate(EQUIPOS)}
    mid = 100
    fechas = {}
    for s in range(temporadas):
        partidos = []
        fecha = dt.date(2021 + s, 7, 1)
        cal = [(a, b) for a in EQUIPOS for b in EQUIPOS if a != b]
        rng.shuffle(cal)
        for k, (a, b) in enumerate(cal):
            mid += 1
            fecha_p = fecha + dt.timedelta(days=int(k // 4) * 3)
            coach = {a: tec[(a, s)], b: tec[(b, s)]}
            ev, fr = _Partido(mid, a, b, coach, rng, jugadores).jugar()
            gl = sum(1 for e in ev if e["type"]["name"] == "Shot" and e["team"]["name"] == a
                     and e["shot"]["outcome"]["name"] == "Goal")
            gv = sum(1 for e in ev if e["type"]["name"] == "Shot" and e["team"]["name"] == b
                     and e["shot"]["outcome"]["name"] == "Goal")
            with gzip.open(raiz / "events" / f"{mid}.json.gz", "wt", encoding="utf-8") as f:
                json.dump(ev, f)
            with gzip.open(raiz / "frames" / f"{mid}.json.gz", "wt", encoding="utf-8") as f:
                json.dump(fr, f)
            partidos.append({"match_id": mid, "match_date": fecha_p.isoformat(), "kick_off": "19:00:00.000",
                             "competition": {"competition_id": 73}, "season": {"season_id": 100 + s,
                                                                                 "season_name": f"{2021 + s}/{2022 + s}"},
                             "competition_stage": {"name": "Regular Season"}, "match_week": k // 4 + 1,
                             "home_team": {"home_team_name": a, "managers": [{"name": coach[a], "id": 1}]},
                             "away_team": {"away_team_name": b, "managers": [{"name": coach[b], "id": 2}]},
                             "home_score": gl, "away_score": gv, "match_status_360": "available"})
            for e in (a, b):
                fechas.setdefault((e, s), []).append(fecha_p)
        with gzip.open(raiz / "matches" / f"73_{100 + s}.json.gz", "wt", encoding="utf-8") as f:
            json.dump(partidos, f)
    # eras verificadas: una por técnico y equipo, de su primer a su último partido
    from dtcoach.eras import _slug_club
    for e in EQUIPOS:
        filas, actual = [], None
        for s in range(temporadas):
            c = tec[(e, s)]
            ini, fin = min(fechas[(e, s)]), max(fechas[(e, s)])
            if actual and actual[0] == c:
                actual[2] = fin
            else:
                if actual:
                    filas.append(actual)
                actual = [c, ini, fin]
        filas.append(actual)
        with open(eras_dir / f"coach_eras_{_slug_club(e)}.csv", "w", encoding="utf-8") as f:
            f.write("club,coach,start_date,end_date\n")
            for c, i, fn in filas:
                f.write(f"{e},{c},{i.isoformat()},{fn.isoformat()}\n")
    return {"foco": FOCO, "partidos": mid - 100, "equipos": EQUIPOS}
