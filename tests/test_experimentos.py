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
