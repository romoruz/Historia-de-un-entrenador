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
