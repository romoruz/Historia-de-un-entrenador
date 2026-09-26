"""Fase 3: la referencia nunca contiene al foco, y un rasgo sembrado en dos clubes 'viaja'."""
import numpy as np
import polars as pl

from dtcoach.fase3 import atlas, por_club, reasignar_foco

FAM = ["Directa", "Circulación estéril", "Ataque elaborado"]
CFG2 = {"n_sim": 60, "n_boot": 150, "alpha": 0.05, "ref": 1, "foco": "X",
        "n_sim_atlas": 40, "n_boot_atlas": 60}


def _liga(seed=0, efecto_def=0.08):
    """El DT 'Foco' dirige el club A (partidos 0-29) y el club B (30-49). 150 partidos de liga."""
    rng = np.random.default_rng(seed)
    filas = []
    for mid in range(200):
        if mid < 30:
            eq, dt = ("A", "R"), ("Foco", "DT_R")
        elif mid < 50:
            eq, dt = ("B", "R"), ("Foco", "DT_R")
        else:   # 6 equipos de liga, cada uno con SU técnico fijo
            a, b = mid % 6, (mid + 1 + mid // 6 % 5) % 6
            b = b if b != a else (a + 1) % 6
            eq, dt = (f"L{a}", f"L{b}"), (f"DT_L{a}", f"DT_L{b}")
        for s in range(80):
            lado = s % 2
            team, coach, faced = eq[lado], dt[lado], dt[1 - lado]
            base = np.array([0.32, 0.27, 0.41])
            if faced == "Foco":      # sus rivales juegan menos Directa: rasgo defensivo sembrado en A y B
                base = base + np.array([-efecto_def, 0, efecto_def])
            r = rng.dirichlet(40 * base)
            filas.append({"match_id": mid, "season_id": 1, "team": team, "coach": coach, "coach_faced": faced,
                          "score_state": rng.choice(["losing", "drawing", "winning"]),
                          "tramo": rng.choice(["0-29", "30-44", "45-59", "60-74", "75+"]),
                          "local": bool(lado == 0), "elo_dif": float(rng.normal()),
                          "origen": rng.choice(["open", "transition"]),
                          "r_1": r[0], "r_2": r[1], "r_3": r[2],
                          "xg": float(rng.exponential(0.01)), "remata": bool(rng.random() < 0.1)})
    t = pl.DataFrame(filas)
    return t.with_columns((pl.col("coach") == "Foco").alias("f"), (pl.col("coach_faced") == "Foco").alias("g"),
                          pl.col("match_id").lt(50).alias("partido_foco"))


def test_reasignar_excluye_las_otras_etapas_de_la_referencia():
    t = reasignar_foco(_liga(), "Foco", "A")
    assert t.filter(pl.col("f"))["team"].unique().to_list() == ["A"]
    assert t.filter(pl.col("match_id").is_between(30, 49)).height == 0      # club B fuera de la referencia
    assert not t.filter(~pl.col("partido_foco"))["coach"].is_in(["Foco"]).any()


def test_un_rasgo_sembrado_en_ambos_clubes_viaja():
    res = por_club(_liga(), "Foco", ["A", "B"], FAM, CFG2, seed=0)
    assert res["principal"] == "A"
    ver = res["veredicto"]["A vs B"]
    v = ver["H9 identidad defensiva"]
    assert v["Directa"] and v["Ataque elaborado"]
    assert set(ver) >= {"H10 eficiencia ofensiva", "H11 eficiencia defensiva",
                        "H12 mezcla ofensiva distinta entre clubes"}
    assert "_aviso" in ver                  # B tiene 20 partidos: se avisa la poca potencia


def test_sin_rasgo_no_viaja():
    res = por_club(_liga(efecto_def=0.0, seed=4), "Foco", ["A", "B"], FAM, CFG2, seed=0)
    v = res["veredicto"]["A vs B"]["H9 identidad defensiva"]
    assert not (v["Directa"] and v["Ataque elaborado"])


def test_atlas_una_fila_por_era_y_el_foco_destaca():
    tab = atlas(_liga(), FAM, CFG2, seed=0, min_partidos=15, verbose=False)
    assert {"Foco"} <= set(tab["coach"].to_list())
    foco = tab.filter(pl.col("coach") == "Foco")
    otros = tab.filter(pl.col("coach") != "Foco")
    assert foco["norma_defensa_pp"].min() > otros["norma_defensa_pp"].median()


def test_tres_clubes_el_principal_contra_cada_uno():
    t = _liga()
    # tercer club: los 10 últimos partidos de B pasan a llamarse C
    t = t.with_columns(pl.when((pl.col("team") == "B") & (pl.col("match_id") >= 40)).then(pl.lit("C"))
                       .otherwise(pl.col("team")).alias("team"))
    res = por_club(t, "Foco", ["A", "B", "C"], FAM, CFG2, seed=0)
    assert set(res["veredicto"]) == {"A vs B", "A vs C"}
    c = res["clubes"]["C"]
    assert "aviso_foco" in c["modelo"]                                   # 10 partidos
    assert all(h["etiqueta"] != "🟢" for h in c["hipotesis"].values())   # con pocos partidos, nunca 🟢
