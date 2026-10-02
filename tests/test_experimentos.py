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
