import numpy as np

from dtcoach.absorbing import Cadena


def _cadena(seed=0, nt=6, na=4):
    rng = np.random.default_rng(seed)
    P = rng.random((nt, nt + na))
    P[:, nt:] += 0.5
    return Cadena(P / P.sum(1, keepdims=True), nt)


def test_neumann_y_absorcion():
    c = _cadena()
    N = c.fundamental()
    serie = sum(np.linalg.matrix_power(c.Q, k) for k in range(400))
    assert np.allclose(N, serie, atol=1e-10)
    assert np.allclose(c.absorcion().sum(1), 1.0)
    assert np.allclose(c.largo_esperado(), N.sum(1))


def test_bellman():
    c = _cadena(1)
    x = np.random.default_rng(2).random(6)
    V = c.valor(x)
    assert np.allclose(V, c.Q @ V + x)


def test_visitas_es_estacionaria_de_la_cadena_reiniciada():
    """ADR-v2-07: pi de la cadena reiniciada ∝ alpha^T N, en sentido estricto."""
    c = _cadena(3)
    nt, na = 6, 4
    alpha = np.random.default_rng(4).dirichlet(np.ones(nt))
    Pr = np.zeros((nt + na, nt + na))
    Pr[:nt] = c.P
    Pr[nt:, :nt] = alpha            # cada absorción arranca otra posesión
    w, v = np.linalg.eig(Pr.T)
    pi = np.real(v[:, np.argmin(np.abs(w - 1))])
    pi = pi / pi.sum()
    assert np.allclose(pi[:nt] / pi[:nt].sum(), c.visitas(alpha), atol=1e-10)


def test_supervivencia_es_phase_type():
    c = _cadena(5)
    alpha = np.full(6, 1 / 6)
    S = c.supervivencia(alpha, 200)
    assert abs(S[0] - 1.0) < 1e-12 and np.all(np.diff(S) <= 1e-15)
    assert abs(S.sum() - alpha @ c.largo_esperado()) < 1e-8     # E[T] = sum_k P(T>k)
