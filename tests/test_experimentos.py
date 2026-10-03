"""Experimentos no adoptados (ADR-v2-52 a 54): se valida el CÓDIGO con datos sembrados."""
import numpy as np
import scipy.sparse as sp

from dtcoach import supuesto_pk as spk

NT, NS = 6, 10


def _cadenas(rng, K=2):
    P = rng.dirichlet(np.ones(NS) * 0.7, size=(K, NT))
    P[:, :, NT:] += 0.12                                   # que las posesiones terminen
    return P / P.sum(2, keepdims=True)


def _simular(rng, P, mu, n_partidos, por_partido, pi, tipo_foco=None, Pf=None, id0=0):
    filas, match, fam = [], [], []
    for g in range(n_partidos):
        for _ in range(por_partido):
            k = rng.choice(len(pi), p=pi)
            Pk = Pf[k] if (Pf is not None and k == tipo_foco) else P[k]
            z = rng.choice(NT, p=mu[k])
            c = np.zeros(NT * NS)
            first = True
            c0 = np.zeros(NT * NS)
            for _t in range(60):
                to = rng.choice(NS, p=Pk[z])
                (c0 if first else c)[z * NS + to] += 1
                first = False
                if to >= NT:
                    break
                z = to
            filas.append((c, c0))
            match.append(id0 + g)
            fam.append(k)
    S1 = sp.csr_matrix(np.array([f[0] for f in filas]))
    S0 = sp.csr_matrix(np.array([f[1] for f in filas]))
    return S1, S0, np.array(match), np.array(fam)


def _una(rng, perturbar: bool, G=70):
    P = _cadenas(rng)
    mu = rng.dirichlet(np.ones(NT), size=2)
    pi = np.array([0.55, 0.45])
    Pf = P.copy()
    if perturbar:
        for i in range(NT):
            Pf[0, i] = 0.6 * P[0, i] + 0.4 * rng.dirichlet(np.ones(NS) * 0.7)
        Pf[0] /= Pf[0].sum(1, keepdims=True)
    Sl = _simular(rng, P, mu, 250, 12, pi)
    Sf = _simular(rng, P, mu, G, 12, pi, 0, Pf, id0=1000)
    S1 = sp.vstack([Sl[0], Sf[0]]).tocsr()
    S0 = sp.vstack([Sl[1], Sf[1]]).tocsr()
    match = np.concatenate([Sl[2], Sf[2]])
    fam = np.concatenate([Sl[3], Sf[3]])
    r = np.eye(2)[fam]
    es_foco = match >= 1000
    return spk.correr(S1, S0, r, match, es_foco, es_foco, P, P, mu, NT, NS, a=10.0)


def test_supuesto_pk_tamano_y_potencia():
    rng = np.random.default_rng(7)
    p0 = [_una(rng, False)["familias"][0]["P"]["p_fisher"] for _ in range(60)]
    p1 = [_una(rng, True)["familias"][0]["P"]["p_fisher"] for _ in range(20)]
    assert np.mean(np.array(p0) < 0.05) <= 0.10              # tamaño ≤ 5 % (conservador: la nula usa pseudo-conteos)
    assert np.median(p0) > 0.25                                  # p ≈ uniforme bajo H0
    assert np.mean(np.array(p1) < 0.05) >= 0.6                   # potencia (≈ 0.7 medida): la prueba es conservadora
    r = _una(rng, True)
    assert r["familias"][0]["P"]["tv"] > r["familias"][1]["P"]["tv"]   # la familia perturbada se desvía más


def test_regresor_generado_piezas():
    from dtcoach import regresor_generado as rg
    rng = np.random.default_rng(0)
    match = np.repeat(np.arange(40), 5)
    pf = match < 10
    con, sin = rg.estratos(match, pf)
    assert len(con) == 10 and len(sin) == 30
    idx = rg.remuestra(match, con, sin, rng)
    assert len(idx) == 200 and np.mean(match[idx] < 10) in (0.25,)       # estratificada: mismos tamaños
    R0 = rng.dirichlet(np.ones(3) * 0.3, 300)
    perm = np.array([2, 0, 1])
    assert np.array_equal(rg.alinear(R0, R0[:, perm]), np.argsort(perm))
    fijo = [{"a": float(x)} for x in rng.normal(0, 1, 200)]
    filas = rg.resumen(fijo, fijo, {"a": (0.0, -2.0, 2.0)})
    assert filas[0]["infl_limpia"] == 1.0
    doble = [{"a": 1.5 * x["a"]} for x in fijo]
    assert abs(rg.resumen(fijo, doble, {"a": (0.0, -2.0, 2.0)})[0]["infl_limpia"] - 1.5) < 1e-9


def test_voronoi_grafo_piezas():
    import polars as pl

    from dtcoach import voronoi_grafo as vg
    # cadena de 2 estados transitorios (1 zona, 2 fases) con 4 absorbentes: V = N c a mano
    nt, ns = 2, 6
    C = np.zeros((nt, ns))
    C[0] = [0, 5, 0, 0, 5, 0]          # estado 0: 5 → 1, 5 → LOSS
    C[1] = [0, 0, 0, 10, 0, 0]         # estado 1: 10 → SHOT_NOGOAL(nt+1)
    X = np.array([0.0, 1.0])           # xG 1.0 en 10 acciones desde el estado 1
    Vz = vg.valor_de_zonas(C.ravel(), X, nt, ns, 2)
    assert abs(Vz[0] - 0.075) < 1e-9       # V1 = 0.1, V0 = 0 + 0.5·0.1 = 0.05, promedio con pesos iguales
    rng = np.random.default_rng(0)
    n = 4000
    a = pl.DataFrame({"z0": rng.integers(0, 3, n), "tipo": rng.choice(["pase", "conduccion"], n),
                      "dv_int": rng.normal(0, 1, n) + 5.0, "dv_real": rng.normal(0, 1, n) + 5.0})
    r = vg.residualizar(a)
    assert abs(r["dv_int_perp"].mean()) < 1e-9 and abs(r["dv_real_perp"].mean()) < 1e-9
    # mismo jugador: sin efecto del técnico, z² ≈ nula; con efecto, p de permutación chico
    def acc(efecto):
        filas = []
        for pid in range(40):
            for coach, base in (("A", 0.0), ("B", efecto)):
                for m in range(8):
                    mid = pid * 100 + (0 if coach == "A" else 50) + m
                    for _ in range(12):
                        filas.append((pid, f"j{pid}", coach, mid, rng.normal(base, 1.0), 80.0))
        return pl.DataFrame(filas, schema=["player_id", "player", "coach", "match_id", "dv_real_perp", "area_local"],
                            orient="row")
    sin = vg.mismo_jugador(acc(0.0), 50, n_perm=100)
    con = vg.mismo_jugador(acc(0.8), 50, n_perm=100)
    assert sin["jugadores_con_2_tecnicos"] == 40 and sin["p_perm"] > 0.05
    assert con["p_perm"] < 0.05 and con["z2_media"] > 2 * sin["z2_media"]


def test_supuesto_pk_igual_n_desconfunde_potencia():
    """ADR-v2-55: con la MISMA magnitud de desviación en todos, el foco con 5× partidos queda arriba por
    exceso a n completo (potencia), pero no a igual n."""
    rng = np.random.default_rng(11)
    P = _cadenas(rng)
    mu = rng.dirichlet(np.ones(NT), size=2)
    pi = np.array([0.55, 0.45])

    def desviada():
        Pf = P.copy()
        for i in range(NT):
            Pf[0, i] = 0.7 * P[0, i] + 0.3 * rng.dirichlet(np.ones(NS) * 0.7)
        return Pf / Pf.sum(2, keepdims=True)

    bloques = [_simular(rng, P, mu, 200, 20, pi)]
    tam = [150] + [30] * 9                                    # el foco y 9 técnicos-club
    for u, G in enumerate(tam):
        bloques.append(_simular(rng, P, mu, G, 20, pi, 0, desviada(), id0=1000 * (u + 1)))
    S1 = sp.vstack([b[0] for b in bloques]).tocsr()
    match = np.concatenate([b[2] for b in bloques])
    r = np.eye(2)[np.concatenate([b[3] for b in bloques])]
    foco = (match >= 1000) & (match < 2000)
    unidades = [{"nombre": u, "f": (match >= 1000 * (u + 1)) & (match < 1000 * (u + 2)), "excl": None}
                for u in range(len(tam))]
    for u in unidades:
        u["excl"] = u["f"] | foco
    completo = {u["nombre"]: spk.prueba_familia(S1, r[:, 0], match, u["f"],
                                                spk.p_liga(S1, r[:, 0], ~u["excl"], P[0], 10.0, NT, NS), NT, NS,
                                                liga=~u["excl"])["exceso"] for u in unidades}
    otros = np.array([completo[u] for u in range(1, len(tam))])
    assert spk.percentil(completo[0], otros) >= 85            # a n completo: arriba de casi todos
    res = spk.igualar_n(S1, r, match, unidades, P, NT, NS, 30, 8, seed=3)
    pct = [spk.percentil(res[0]["exceso"][b, 0], np.array([res[u]["exceso"][b, 0] for u in range(1, len(tam))]))
           for b in range(8)]
    assert np.median(pct) < 85                                 # a igual n deja de destacar
    assert np.isnan(res[0]["exceso"]).sum() == 0 and res[1]["partidos"] == 30


def test_xgot_cinco_terminos_exactos_y_verificacion():
    """ADR-v2-56: definición + portero = portero y definición, y los 5 términos suman p κ − g (< 1e-10)."""
    import polars as pl

    from dtcoach import xgot as xg
    rng = np.random.default_rng(5)
    n = 400
    s = (rng.random(n) < 0.3).astype(float)
    k = np.where(rng.random(n) < 0.5, 0.08, 0.12)
    p = np.clip(rng.beta(2, 6, n), 0.01, 0.99)
    nrem = np.where(s > 0, rng.integers(1, 3, n), 0)
    ids = [[f"r{i}_{t}" for t in range(m)] for i, m in enumerate(nrem)]
    todos = [x for l in ids for x in l]
    fprev = dict(zip(todos, rng.uniform(0.01, 0.6, len(todos)).tolist()))
    ap = dict(zip(todos, (rng.random(len(todos)) < 0.4).tolist()))
    gol = {x: bool(ap[x] and rng.random() < 0.3) for x in todos}
    B = np.array([sum(fprev[x] for x in l) * 1.1 for l in ids])
    F = np.array([sum(fprev[x] for x in l) for l in ids])
    g = np.array([float(sum(gol[x] for x in l)) for l in ids])
    D = pl.DataFrame({"id_saque": [f"s{i}" for i in range(n)], "match_id": rng.integers(0, 40, n), "team": "A",
                      "tipo": "corner", "p": p, "s": s, "B": B, "F": F, "g": g, "kappa": k})
    D = D.with_columns(((pl.col("p") - pl.col("s")) * pl.col("kappa")).alias("prev"),
                       (pl.col("s") * (pl.col("kappa") - pl.col("B"))).alias("lej"),
                       (pl.col("s") * (pl.col("B") - pl.col("F"))).alias("sup"),
                       (pl.col("s") * (pl.col("F") - pl.col("g"))).alias("port"))
    j = pl.DataFrame({"id_saque": [f"s{i}" for i in range(n)], "ids_remate": ids})
    conocidos = todos[: int(0.8 * len(todos))]                # el 20 % no está en la tabla de xGOT: entra neutro
    rx = pl.DataFrame({"id": conocidos, "xgot": [rng.uniform(0, 0.9) if ap[x] else 0.0 for x in conocidos],
                       "f_previo": [fprev[x] for x in conocidos]})
    d5 = xg.partir(D, j, rx)
    assert xg.error_exactitud(d5) < 1e-10
    assert float((d5["port"] - d5["def"] - d5["portero"]).abs().max()) < 1e-10
    assert float(d5.filter(pl.col("s") == 0)["def"].abs().max()) == 0.0
    # verificación: sin z en los remates a puerta, NO pasa
    m = 300
    out = rng.random(m) < 0.5
    base = {"match_id": rng.integers(0, 30, m), "id": [f"x{i}" for i in range(m)], "shot_outcome":
            np.where(out, "Off T", np.where(rng.random(m) < 0.3, "Goal", "Saved")), "shot_type": "Open Play",
            "xg_sb": rng.uniform(0.02, 0.5, m), "cabeza": 0.0, "n_end": 3}
    r_ok = pl.DataFrame(base | {"end_y": rng.uniform(36.2, 43.8, m), "end_z": np.where(out, np.nan, rng.uniform(0.05, 2.6, m))}).with_columns(pl.col("end_z").fill_nan(None)) \
        .with_columns(pl.col("shot_outcome").is_in(list(xg.A_PUERTA)).alias("a_puerta"), (pl.col("shot_outcome") == "Goal").alias("gol"))
    assert xg.disponibilidad(r_ok)["ok"]
    assert not xg.disponibilidad(r_ok.with_columns(pl.lit(None, pl.Float64).alias("end_z")))["ok"]


def test_arista_marginal_igual_al_modelo_base():
    """ADR-v2-59: con las mismas r_sk, Σ_m del paso M de la arista = paso M del modelo base; con K = 1 el puntaje
    secuencial de la siguiente zona es idéntico (la ganancia de la arista solo puede venir de la mezcla)."""
    import polars as pl

    from dtcoach import arista as ar
    from dtcoach import mezcla as mz
    rng = np.random.default_rng(2)
    nt, ns, n = 4, 7, 600
    filas = []
    for s in range(n):
        z = int(rng.integers(0, nt))
        for t in range(12):
            m = int(rng.choice([0, 1, 2], p=[0.6, 0.3, 0.1]))
            to = int(rng.integers(nt, ns)) if m == 2 or rng.random() < 0.15 else int(rng.integers(0, nt))
            tipo = ("Pass", "Carry", "Shot")[m] if to < nt or m == 2 else "Pass"
            filas.append((f"s{s}", s // 10, t, z, to, tipo))
            if to >= nt:
                break
            z = to
    tr = pl.DataFrame(filas, schema=["seq_uid", "match_id", "event_index", "from_state", "to_state", "action_type"],
                      orient="row")

    class Esp:
        n_transient, n_states, nx, ny, phases = nt, ns, 2, 2, ["all"]
    db = mz.DatosPosesion.desde_transiciones(tr, Esp)
    da = ar.datos(tr, Esp)
    assert da.n_states == ar.M * ns and np.allclose(np.asarray(da.S.sum(1)).ravel(), np.asarray(db.S.sum(1)).ravel())
    r = rng.dirichlet(np.ones(3), db.n)
    pb, pa = mz.prior(db, 50.0, 1.0, True), mz.prior(da, 50.0, 1.0, True)
    _, mub, Pb, P0b = mz._m_step(db, r, pb)
    _, mua, Pa, P0a = mz._m_step(da, r, pa)
    assert np.allclose(Pa.reshape(3, nt, ar.M, ns).sum(2), Pb, atol=1e-12)
    assert np.allclose(P0a.reshape(3, nt, ar.M, ns).sum(2), P0b, atol=1e-12) and np.allclose(mua, mub)
    # K = 1: misma predicción de la siguiente zona, acción por acción
    one = np.ones((db.n, 1))
    pib, mub1, Pb1, P0b1 = mz._m_step(db, one, pb)
    pia, mua1, Pa1, P0a1 = mz._m_step(da, one, pa)
    mb = mz.Mezcla(pib, mub1, Pb1, 50.0, 1.0, [], {}, P0b1)
    ma = mz.Mezcla(pia, mua1, Pa1, 50.0, 1.0, [], {}, P0a1)
    pz = ar.pasos(tr)
    area = np.full(nt, 1 / nt)
    sb = ar.puntaje(mb, pz, nt, ns, area, con_marca=False)
    sa = ar.puntaje(ma, pz, nt, ns, area, con_marca=True)
    assert np.allclose(sa, sb, atol=1e-10)
    g = ar.ganancia(sa - sb, pz["match"])
    assert abs(g["nats_por_accion"]) < 1e-10 and g["partidos"] == n // 10
