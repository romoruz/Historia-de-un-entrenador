import numpy as np

from dtcoach.grid import StateSpace


def test_una_fase_da_veinte_zonas(space):
    assert space.n_transient == 20 and space.n_states == 25          # 5 absorbentes (ADR-v2-72)


def test_quinto_absorbente_al_final(space):
    """ADR-v2-72: INTERRUPCION_FAVOR va al final; los índices de los cuatro de la entrega no cambian."""
    from dtcoach.grid import ABSORBING_4
    s4 = StateSpace(nx=5, ny=4, phases=space.phases, absorbing=ABSORBING_4)
    for a in ABSORBING_4:
        assert space.absorbing_index(a) == s4.absorbing_index(a)
    assert space.absorbing_index("INTERRUPCION_FAVOR") == s4.n_states


def test_zonas_y_espejo():
    s = StateSpace(nx=5, ny=4, phases=("all",))
    assert s.zone_of(np.array([0.0]), np.array([0.0]))[0] == 0
    assert s.zone_of(np.array([120.1]), np.array([80.5]))[0] == 19     # recorte al campo
    z = np.arange(20)
    assert np.array_equal(s.mirror_zone(s.mirror_zone(z)), z)
